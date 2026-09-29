"""Turn "who is speaking" into camera cuts, like a TV director would.

Input: per-frame speaker labels (``SpeakerActivity``, 100 frames/s) and the
cameras: which speakers each one shows (a solo shows one person, a two-shot two,
a wide everyone).
Output: shots ``(start_frame, camera)`` and finally CutList segments.

How it decides
--------------
We edit offline, so instead of reacting frame by frame we choose the *whole*
sequence of shots at once, as the best trade-off between:

* **reward** - every 0.1 s showing the person who is speaking scores 1 for a solo
  shot of them, ``group_reward`` for a group shot that contains them; wide shots
  score during sustained cross-talk and, a little, during long silences;
* **cost of a cut** - each cut costs ``switch_delay_s`` seconds of reward, so a
  cut is only made when it pays for itself. A 0.5 s "mm-hmm" never does; this is
  the hysteresis / interruption tolerance;
* **minimum shot length** - a hard rule: no shot shorter than ``min_shot_s``;
* **variety** (``max_shot_s``) - past that length a shot pays a growing cost, so
  a cut to another camera that also shows the speaker becomes worth it.

This is solved exactly with dynamic programming (a Viterbi search over
"camera, time since last cut"). Speaker rewards are shifted ``lead_s`` earlier,
so cuts land just before the new speaker's first word; each cut is then snapped
to the new speaker's true onset at 10 ms resolution.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from uuid import UUID

import numpy as np
import numpy.typing as npt

from multicam_engine.analysis.speakers import CROSSTALK, SILENCE, SpeakerActivity
from multicam_engine.decide.presets import SwitchParams
from multicam_engine.models.cutlist import Segment, SegmentSource
from multicam_engine.models.time import Rational, Rounding, seconds_to_frames

WIDE = -3  # legacy shot target (``plan_shots``): the wide camera
STEP_S = 0.1  # decision resolution (cuts land on 100 ms boundaries before onset snapping)

_UNAVAILABLE = -10.0  # reward per step for showing a camera that isn't recording
_CROSSTALK_SPEAKER = 0.4  # reward for one of the speakers during cross-talk
_TALK_OVER_SHARE = 0.3  # share of cross-talk frames that makes a stretch "talk-over"
_SILENCE_WIDE = 0.3  # reward for the wide shot during a long silence
_HOLD = 0.05  # tiny reward for staying on the last speaker during a pause, so that
# cuts land just before the next speaker rather than anywhere inside the pause
_GROUP_MAX = 0.95  # a group shot never beats a solo of the speaker on its own
_WIDE_MAX = 0.9
_GROUP_TALK_OVER = 0.6  # group shot during talk-over when a wide camera exists
_VARIETY_RAMP_S = 4.0  # past max_shot_s the cost grows to _VARIETY_MAX over this long
_VARIETY_MAX = 1.0
_CONFIDENCE_WINDOW_S = 0.5
_CONFIDENT_MARGIN_DB = 6.0

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class Shot:
    start: int  # analysis frame (activity.frame_rate per second)
    target: int  # camera index (``plan_camera_shots``); speaker index or WIDE (``plan_shots``)
    confidence: float = 1.0


@dataclass(frozen=True)
class Camera:
    """A camera as switching sees it."""

    covers: frozenset[int]  # speaker indices visible in the shot
    wide: bool = False  # shows everyone (wide / establishing shot)
    priority: float = 1.0  # user bias, 0.5 - 1.5
    available: BoolArray | None = None  # per analysis frame; None = always recording

    @property
    def solo(self) -> bool:
        return not self.wide and len(self.covers) == 1

    @property
    def group(self) -> bool:
        return not self.wide and len(self.covers) >= 2


def _runs(values: npt.NDArray[np.int64]) -> list[tuple[int, int, int]]:
    """(value, start, end) for each run of equal values."""
    if len(values) == 0:
        return []
    change = np.flatnonzero(np.diff(values)) + 1
    starts = np.concatenate([[0], change])
    ends = np.concatenate([change, [len(values)]])
    return [(int(values[s]), int(s), int(e)) for s, e in zip(starts, ends, strict=True)]


def fill_short_gaps(labels: npt.NDArray[np.int64], max_gap: int) -> npt.NDArray[np.int64]:
    """Silences shorter than ``max_gap`` frames inside speech belong to the previous
    speaker (pauses between words and sentences do not end a turn)."""
    out = labels.copy()
    runs = _runs(labels)
    for i, (value, start, end) in enumerate(runs):
        if value == SILENCE and 0 < i < len(runs) - 1 and end - start <= max_gap:
            out[start:end] = runs[i - 1][0]
    return out


def legacy_cameras(activity: SpeakerActivity, has_wide: bool) -> list[Camera]:
    """One solo camera per speaker (in speaker order), plus a wide camera last."""
    n_spk = len(activity.speakers)
    cams = [Camera(frozenset({i}), available=activity.available[i]) for i in range(n_spk)]
    if has_wide:
        cams.append(Camera(frozenset(range(n_spk)), wide=True))
    return cams


def _scales(params: SwitchParams) -> tuple[float, float, float]:
    """(group reward, wide reward during single speech, cross-talk window factor)."""
    wf = min(1.0, max(0.0, params.wide_frequency))
    group = min(_GROUP_MAX, params.group_reward * (0.5 + wf) / 0.8)
    varied = wf > 0.3 or params.max_shot_s > 0
    wide_single = min(_WIDE_MAX, params.group_reward * (0.4 + wf)) if varied else 0.0
    return group, wide_single, 1.3 - wf


def camera_rewards(
    activity: SpeakerActivity, cameras: Sequence[Camera], params: SwitchParams
) -> FloatArray:
    """Reward for showing each camera at each analysis frame (rows = cameras)."""
    rate = activity.frame_rate
    n_spk, n = len(activity.speakers), activity.n_frames
    n_cams = len(cameras)
    rewards = np.zeros((n_cams, n))
    group_r, wide_single, crosstalk_factor = _scales(params)

    solos = [[k for k, c in enumerate(cameras) if c.solo and i in c.covers] for i in range(n_spk)]
    groups = [[k for k, c in enumerate(cameras) if c.group and i in c.covers] for i in range(n_spk)]
    wides = [k for k, c in enumerate(cameras) if c.wide]
    group_cams = [k for k, c in enumerate(cameras) if c.group]
    # "Wide-like" cameras for talk-over and long silences: the wide shots, or else
    # the group shots showing the most people.
    if wides:
        establishing = wides
    elif group_cams:
        most = max(len(cameras[k].covers) for k in group_cams)
        establishing = [k for k in group_cams if len(cameras[k].covers) == most]
    else:
        establishing = []

    lead = round(params.lead_s * rate)
    labels = fill_short_gaps(activity.labels, round(params.bridge_gap_s * rate))
    shifted = np.concatenate([labels[lead:], np.full(lead, SILENCE)]) if lead else labels
    for i in range(n_spk):
        speaking = shifted == i
        for k in solos[i]:
            rewards[k, speaking] = cameras[k].priority
        for k in groups[i]:
            rewards[k, speaking] = np.maximum(rewards[k, speaking], group_r * cameras[k].priority)
        # A wide shows the speaker too: worth something when variety is wanted, and
        # it is the best shot of a person no solo / group camera shows.
        wide_value = wide_single if (solos[i] or groups[i]) else group_r
        for k in wides:
            value = wide_value * cameras[k].priority
            rewards[k, speaking] = np.maximum(rewards[k, speaking], value)

    crosstalk_min = max(1, round(params.crosstalk_to_wide_s * crosstalk_factor * rate))
    silence_min = round(params.silence_to_wide_s * rate)
    # Sustained talk-over: over a window of crosstalk_to_wide_s, a good share of the
    # frames are cross-talk (labels flicker between the voices in between).
    density = np.convolve(
        (labels == CROSSTALK).astype(np.float64), np.ones(crosstalk_min) / crosstalk_min, "same"
    )
    talk_over = density >= _TALK_OVER_SHARE
    previous = SILENCE
    for value, start, end in _runs(labels):
        if value == SILENCE and 0 <= previous < n_spk:
            for k in solos[previous] or groups[previous]:
                rewards[k, start:end] = np.maximum(rewards[k, start:end], _HOLD)
        if value != SILENCE:
            previous = value
        if value == CROSSTALK:
            rewards[:, start:end] = _CROSSTALK_SPEAKER
        elif value == SILENCE and establishing and end - start >= silence_min:
            for k in establishing:
                rewards[k, start + silence_min // 2 : end] = _SILENCE_WIDE

    if establishing:
        others = np.array([k for k in range(n_cams) if k not in establishing], dtype=np.int64)
        rows, cols = np.ix_(others, np.flatnonzero(talk_over))
        rewards[rows, cols] = np.minimum(rewards[rows, cols], _CROSSTALK_SPEAKER)
        if wides:
            for k in group_cams:
                rewards[k, talk_over] = np.maximum(rewards[k, talk_over], _GROUP_TALK_OVER)
        for k in establishing:
            rewards[k, talk_over] = 1.0
    for k, cam in enumerate(cameras):
        if cam.available is not None:
            rewards[k, ~cam.available[:n]] = _UNAVAILABLE
    return rewards


def frame_rewards(activity: SpeakerActivity, params: SwitchParams, has_wide: bool) -> FloatArray:
    """Legacy layout: rows = one per speaker, plus the wide camera last if ``has_wide``."""
    return camera_rewards(activity, legacy_cameras(activity, has_wide), params)


def _age_cost(params: SwitchParams, step_s: float, min_steps: int) -> FloatArray | None:
    """Per-step cost by shot age (variety). None when ``max_shot_s`` is off."""
    if params.max_shot_s <= 0:
        return None
    free = max(min_steps, int(np.ceil(params.max_shot_s / step_s - 1e-9)))
    ramp = max(1, int(np.ceil(_VARIETY_RAMP_S / step_s)))
    cost = np.zeros(free + ramp)
    cost[free:] = np.arange(1, ramp + 1) / ramp * _VARIETY_MAX
    return cost


def _best_path(
    rewards: FloatArray,
    min_steps: int,
    switch_cost: float,
    age_cost: FloatArray | None = None,
) -> npt.NDArray[np.int64]:
    """Viterbi over states (camera k, steps in shot d). Returns the camera per step.

    ``d`` runs 0..D-1; the last state is "at least that old". A cut into ``(j, 0)``
    is allowed from ``(k, d)`` with ``d >= M-1`` (M = ``min_steps``), ``k != j``.
    ``age_cost[d]`` is subtracted from the reward of every step spent in state d
    (D = max(M, len(age_cost))). Without ``age_cost``, D = M.
    """
    n_cams, n_steps = rewards.shape
    m = max(1, min(min_steps, n_steps))
    cost = np.zeros(m) if age_cost is None else np.asarray(age_cost, dtype=np.float64)
    if len(cost) < m:
        cost = np.concatenate([cost, np.full(m - len(cost), cost[-1] if len(cost) else 0.0)])
    d_max = len(cost)
    neg = -np.inf
    score = np.full((n_cams, d_max), neg)
    score[:, 0] = rewards[:, 0] - cost[0]
    came_from = np.zeros((n_steps, n_cams), dtype=np.int64)  # source camera of a cut
    came_age = np.zeros((n_steps, n_cams), dtype=np.int64)  # source shot age of a cut
    cut_taken = np.zeros((n_steps, n_cams), dtype=bool)  # (k, 0) entered by a cut?
    held = np.zeros((n_steps, n_cams), dtype=bool)  # (k, D-1) came from (k, D-1)?
    cams = np.arange(n_cams)

    for t in range(1, n_steps):
        ready = score[:, m - 1 :]
        ready_age = np.argmax(ready, axis=1) + (m - 1)
        done = ready.max(axis=1)
        if n_cams > 1:  # best other camera to cut from
            order = np.argsort(-done, kind="stable")
            src = np.where(cams == order[0], order[1], order[0])
            cut = done[src] - switch_cost
        else:
            src = cams
            cut = np.full(n_cams, neg)
        new = np.full_like(score, neg)
        if d_max > 1:
            new[:, 1:] = score[:, :-1]  # the shot continues: d -> d + 1
            held[t] = score[:, d_max - 1] >= new[:, d_max - 1]
            new[:, d_max - 1] = np.maximum(score[:, d_max - 1], new[:, d_max - 1])
            new[:, 0] = cut
            cut_taken[t] = True
        else:
            cut_taken[t] = cut > done
            new[:, 0] = np.where(cut_taken[t], cut, done)
        came_from[t] = src
        came_age[t] = ready_age[src]
        score = new + rewards[:, t][:, None] - cost[None, :]

    finished = score[:, m - 1 :]
    k: int
    d: int
    if np.isfinite(finished).any():
        best_k, best_d = np.unravel_index(int(np.argmax(finished)), finished.shape)
        k, d = int(best_k), int(best_d) + m - 1
    else:
        k = int(np.argmax(score.max(1)))
        d = int(np.argmax(score[k]))
    path = np.zeros(n_steps, dtype=np.int64)
    for t in range(n_steps - 1, 0, -1):
        path[t] = k
        if d == 0 and cut_taken[t, k]:
            k, d = int(came_from[t, k]), int(came_age[t, k])
        elif d == d_max - 1 and held[t, k]:
            pass
        elif d > 0:
            d -= 1
    path[0] = k
    return path


def _snap_to_onsets(
    starts: list[int],
    path_cams: list[int],
    cameras: Sequence[Camera],
    labels: npt.NDArray[np.int64],
    *,
    per_step: int,
    lead: int,
    min_frames: int,
    n: int,
) -> list[int]:
    """Move each cut onto the new speaker's true first word (minus ``lead``), at
    frame resolution, within one decision step and without breaking min shot."""
    out = list(starts)
    for i in range(1, len(out)):
        cam, prev = cameras[path_cams[i]], cameras[path_cams[i - 1]]
        if not cam.solo:
            continue
        (who,) = tuple(cam.covers)
        if who in prev.covers:
            continue
        lo = max(0, out[i] + lead - per_step)
        hi = min(n, out[i] + lead + 2 * per_step)
        hits = np.flatnonzero(labels[lo:hi] == who)
        if len(hits) == 0:
            continue
        onset = lo + int(hits[0])
        if lo > 0 and labels[lo - 1] == who:
            continue  # already speaking before the window: not an onset
        new = onset - lead
        earliest = out[i - 1] + min_frames
        latest = (out[i + 1] if i + 1 < len(out) else n) - min_frames
        if earliest <= new <= latest:
            out[i] = new
    return out


def _confidence(
    activity: SpeakerActivity,
    labels: npt.NDArray[np.int64],
    cam: Camera,
    start: int,
    end: int,
    lead: int,
) -> float:
    """How clearly the audio supports showing ``cam`` at the start of a shot
    (measured from the first word, i.e. ``lead`` frames after the cut)."""
    start = min(start + lead, max(start, end - 1))
    window = labels[start : min(end, start + round(_CONFIDENCE_WINDOW_S * activity.frame_rate))]
    if len(window) == 0:
        return 1.0
    shows = np.isin(window, list(cam.covers))
    if cam.wide or cam.group:
        agree = shows | (window == CROSSTALK) | (window == SILENCE)
    else:
        agree = shows | (window == SILENCE)
    share = float(agree.mean())
    spoken = window >= 0
    margins = activity.margin_db[start : start + len(window)][spoken & shows]
    clarity = 1.0 if len(margins) == 0 else min(1.0, 0.5 + float(np.mean(margins)) / 12.0)
    return round(max(0.0, min(1.0, share * clarity)), 2)


def plan_camera_shots(
    activity: SpeakerActivity, cameras: Sequence[Camera], params: SwitchParams
) -> list[Shot]:
    """Best shot sequence (``Shot.target`` = camera index). First shot starts at 0."""
    if not cameras:
        raise ValueError("no cameras to switch between")
    rate = activity.frame_rate
    n = activity.n_frames
    if n == 0:
        default = next((k for k, c in enumerate(cameras) if c.wide), 0)
        return [Shot(0, default)]
    per_step = max(1, round(STEP_S * rate))
    rewards = camera_rewards(activity, cameras, params)
    n_steps = -(-n // per_step)
    padded = np.zeros((rewards.shape[0], n_steps * per_step))
    padded[:, :n] = rewards
    step_rewards = padded.reshape(rewards.shape[0], n_steps, per_step).mean(axis=2)

    step_s = per_step / rate
    min_steps = int(np.ceil(params.min_shot_s / step_s - 1e-9))
    path = _best_path(
        step_rewards,
        min_steps=min_steps,
        switch_cost=params.switch_delay_s / step_s,
        age_cost=_age_cost(params, step_s, min_steps),
    )
    runs = _runs(path)
    cams = [value for value, _s, _e in runs]
    starts = [min(start * per_step, n - 1) for _v, start, _e in runs]
    labels = fill_short_gaps(activity.labels, round(params.bridge_gap_s * rate))
    lead = round(params.lead_s * rate)
    starts = _snap_to_onsets(
        starts,
        cams,
        cameras,
        labels,
        per_step=per_step,
        lead=lead,
        min_frames=round(params.min_shot_s * rate),
        n=n,
    )
    shots: list[Shot] = []
    for i, (cam, start) in enumerate(zip(cams, starts, strict=True)):
        end = starts[i + 1] if i + 1 < len(starts) else n
        conf = _confidence(activity, labels, cameras[cam], start, end, lead)
        shots.append(Shot(start, cam, conf))
    return shots


def plan_shots(activity: SpeakerActivity, params: SwitchParams, has_wide: bool) -> list[Shot]:
    """Legacy layout (one solo camera per speaker + optional wide): targets are
    speaker indices or ``WIDE``."""
    n_spk = len(activity.speakers)
    cams = legacy_cameras(activity, has_wide)
    return [
        Shot(s.start, WIDE if s.target == n_spk else s.target, s.confidence)
        for s in plan_camera_shots(activity, cams, params)
    ]


def camera_shots_to_segments(
    shots: list[Shot],
    *,
    analysis_rate: int,
    fps: Rational,
    duration_frames: int,
    camera_clips: Sequence[UUID],
) -> list[Segment]:
    """Convert analysis-frame shots (targets = camera index) to contiguous
    output-frame segments."""
    if duration_frames <= 0:
        raise ValueError("duration_frames must be positive")
    if not shots:
        raise ValueError("no shots")
    bounds: list[tuple[int, UUID, float]] = []
    for shot in shots:
        clip = camera_clips[shot.target]
        frame = seconds_to_frames(Fraction(shot.start, analysis_rate), fps, Rounding.NEAREST)
        frame = 0 if not bounds else min(frame, duration_frames - 1)
        if bounds and (frame <= bounds[-1][0] or clip == bounds[-1][1]):
            continue  # collapsed by frame snapping, or no actual change
        bounds.append((frame, clip, shot.confidence))
    return [
        Segment(
            start_frame=start,
            end_frame=bounds[i + 1][0] if i + 1 < len(bounds) else duration_frames,
            clip_id=clip,
            source=SegmentSource.AUTO,
            confidence=confidence,
        )
        for i, (start, clip, confidence) in enumerate(bounds)
    ]


def shots_to_segments(
    shots: list[Shot],
    *,
    analysis_rate: int,
    fps: Rational,
    duration_frames: int,
    speaker_clips: list[UUID],
    wide_clip: UUID | None,
) -> list[Segment]:
    """Legacy targets (speaker index or ``WIDE``) to contiguous segments."""
    cams: list[UUID] = list(speaker_clips)
    wide_index = len(cams)
    if wide_clip is not None:
        cams.append(wide_clip)
    mapped: list[Shot] = []
    for shot in shots:
        if shot.target == WIDE:
            if wide_clip is None:
                raise ValueError("shot targets the wide camera but there is none")
            mapped.append(Shot(shot.start, wide_index, shot.confidence))
        else:
            mapped.append(shot)
    return camera_shots_to_segments(
        mapped,
        analysis_rate=analysis_rate,
        fps=fps,
        duration_frames=duration_frames,
        camera_clips=cams,
    )
