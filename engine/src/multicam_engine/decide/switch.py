"""Turn "who is speaking" into camera cuts, like a TV director would.

Input: per-frame speaker labels (``SpeakerActivity``, 100 frames/s).
Output: shots ``(start_frame, target)`` and finally CutList segments.

How it decides
--------------
We edit offline, so instead of reacting frame by frame we choose the *whole*
sequence of shots at once, as the best trade-off between:

* **reward** - every 0.1 s showing the person who is speaking scores 1 (the wide
  shot scores during sustained cross-talk and, a little, during long silences);
* **cost of a cut** - each cut costs ``switch_delay_s`` seconds of reward, so a
  cut is only made when it pays for itself. A 0.5 s "mm-hmm" never does; this is
  the hysteresis / interruption tolerance;
* **minimum shot length** - a hard rule: no shot shorter than ``min_shot_s``.

This is solved exactly with dynamic programming (a Viterbi search over
"camera, time since last cut"). Speaker rewards are shifted ``lead_s`` earlier,
so cuts land just before the new speaker's first word, not after it.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from uuid import UUID

import numpy as np
import numpy.typing as npt

from multicam_engine.analysis.speakers import CROSSTALK, SILENCE, SpeakerActivity
from multicam_engine.decide.presets import SwitchParams
from multicam_engine.models.cutlist import Segment, SegmentSource
from multicam_engine.models.time import Rational, Rounding, seconds_to_frames

WIDE = -3  # shot target: the wide camera
STEP_S = 0.1  # decision resolution (cuts land on 100 ms boundaries before frame snapping)

_UNAVAILABLE = -10.0  # reward per step for showing a camera that isn't recording
_CROSSTALK_SPEAKER = 0.4  # reward for one of the speakers during cross-talk
_TALK_OVER_SHARE = 0.3  # share of cross-talk frames that makes a stretch "talk-over"
_SILENCE_WIDE = 0.3  # reward for the wide shot during a long silence
_HOLD = 0.05  # tiny reward for staying on the last speaker during a pause, so that
# cuts land just before the next speaker rather than anywhere inside the pause

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class Shot:
    start: int  # analysis frame (activity.frame_rate per second)
    target: int  # speaker index or WIDE


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


def frame_rewards(activity: SpeakerActivity, params: SwitchParams, has_wide: bool) -> FloatArray:
    """Reward for showing each camera at each analysis frame.

    Rows: one per speaker, plus a last row for the wide camera if ``has_wide``.
    """
    rate = activity.frame_rate
    n_spk, n = len(activity.speakers), activity.n_frames
    rewards = np.zeros((n_spk + int(has_wide), n))

    lead = round(params.lead_s * rate)
    labels = fill_short_gaps(activity.labels, round(params.bridge_gap_s * rate))
    shifted = np.concatenate([labels[lead:], np.full(lead, SILENCE)]) if lead else labels
    for i in range(n_spk):
        rewards[i, shifted == i] = 1.0

    crosstalk_min = round(params.crosstalk_to_wide_s * rate)
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
            rewards[previous, start:end] = np.maximum(rewards[previous, start:end], _HOLD)
        if value != SILENCE:
            previous = value
        if value == CROSSTALK:
            rewards[:n_spk, start:end] = _CROSSTALK_SPEAKER
            if has_wide:
                rewards[n_spk, start:end] = _CROSSTALK_SPEAKER
        elif value == SILENCE and has_wide and end - start >= silence_min:
            rewards[n_spk, start + silence_min // 2 : end] = _SILENCE_WIDE

    if has_wide:
        rewards[:n_spk, talk_over] = np.minimum(rewards[:n_spk, talk_over], _CROSSTALK_SPEAKER)
        rewards[n_spk, talk_over] = 1.0
    for i in range(n_spk):
        rewards[i, ~activity.available[i]] = _UNAVAILABLE
    return rewards


def _best_path(rewards: FloatArray, min_steps: int, switch_cost: float) -> npt.NDArray[np.int64]:
    """Viterbi over states (camera k, steps in shot d). Returns the camera per step.

    ``d`` runs 0..M-1 where M = ``min_steps``; ``d = M-1`` means "the shot is long
    enough, a cut is allowed". A cut enters ``(j, 0)`` from ``(k, M-1)``, ``k != j``.
    """
    n_cams, n_steps = rewards.shape
    m = max(1, min(min_steps, n_steps))
    neg = -np.inf
    score = np.full((n_cams, m), neg)
    score[:, 0] = rewards[:, 0]
    came_from = np.zeros((n_steps, n_cams), dtype=np.int64)  # source camera of a cut
    cut_taken = np.zeros((n_steps, n_cams), dtype=bool)  # (k, 0) entered by a cut?
    held = np.zeros((n_steps, n_cams), dtype=bool)  # (k, M-1) came from (k, M-1)?
    cams = np.arange(n_cams)

    for t in range(1, n_steps):
        done = score[:, m - 1]
        if n_cams > 1:  # best other camera to cut from
            order = np.argsort(-done, kind="stable")
            src = np.where(cams == order[0], order[1], order[0])
            cut = done[src] - switch_cost
        else:
            src = cams
            cut = np.full(n_cams, neg)
        new = np.full_like(score, neg)
        if m > 1:
            new[:, 1:] = score[:, :-1]  # the shot continues: d -> d + 1
            held[t] = done >= new[:, m - 1]
            new[:, m - 1] = np.maximum(done, new[:, m - 1])
            new[:, 0] = cut
            cut_taken[t] = True
        else:
            cut_taken[t] = cut > done
            new[:, 0] = np.where(cut_taken[t], cut, done)
        came_from[t] = src
        score = new + rewards[:, t][:, None]

    finished = score[:, m - 1]
    k = int(np.argmax(finished)) if np.isfinite(finished).any() else int(np.argmax(score.max(1)))
    d = m - 1 if np.isfinite(score[k, m - 1]) else int(np.argmax(score[k]))
    path = np.zeros(n_steps, dtype=np.int64)
    for t in range(n_steps - 1, 0, -1):
        path[t] = k
        if d == 0 and cut_taken[t, k]:
            k, d = int(came_from[t, k]), m - 1
        elif d == m - 1 and held[t, k]:
            pass
        elif d > 0:
            d -= 1
    path[0] = k
    return path


def plan_shots(activity: SpeakerActivity, params: SwitchParams, has_wide: bool) -> list[Shot]:
    """Best shot sequence for ``activity``. The first shot starts at frame 0."""
    rate = activity.frame_rate
    n = activity.n_frames
    if n == 0:
        return [Shot(0, WIDE if has_wide else 0)]
    per_step = max(1, round(STEP_S * rate))
    rewards = frame_rewards(activity, params, has_wide)
    n_steps = -(-n // per_step)
    padded = np.zeros((rewards.shape[0], n_steps * per_step))
    padded[:, :n] = rewards
    step_rewards = padded.reshape(rewards.shape[0], n_steps, per_step).mean(axis=2)

    step_s = per_step / rate
    path = _best_path(
        step_rewards,
        min_steps=int(np.ceil(params.min_shot_s / step_s - 1e-9)),
        switch_cost=params.switch_delay_s / step_s,
    )
    n_spk = len(activity.speakers)
    shots: list[Shot] = []
    for value, start, _end in _runs(path):
        target = WIDE if value == n_spk else value
        shots.append(Shot(min(start * per_step, n - 1), target))
    return shots


def shots_to_segments(
    shots: list[Shot],
    *,
    analysis_rate: int,
    fps: Rational,
    duration_frames: int,
    speaker_clips: list[UUID],
    wide_clip: UUID | None,
) -> list[Segment]:
    """Convert analysis-frame shots to contiguous output-frame segments."""
    if duration_frames <= 0:
        raise ValueError("duration_frames must be positive")
    if not shots:
        raise ValueError("no shots")
    bounds: list[tuple[int, UUID]] = []
    for shot in shots:
        if shot.target == WIDE:
            if wide_clip is None:
                raise ValueError("shot targets the wide camera but there is none")
            clip = wide_clip
        else:
            clip = speaker_clips[shot.target]
        frame = seconds_to_frames(Fraction(shot.start, analysis_rate), fps, Rounding.NEAREST)
        frame = 0 if not bounds else min(frame, duration_frames - 1)
        if bounds and (frame <= bounds[-1][0] or clip == bounds[-1][1]):
            continue  # collapsed by frame snapping, or no actual change
        bounds.append((frame, clip))
    return [
        Segment(
            start_frame=start,
            end_frame=bounds[i + 1][0] if i + 1 < len(bounds) else duration_frames,
            clip_id=clip,
            source=SegmentSource.AUTO,
        )
        for i, (start, clip) in enumerate(bounds)
    ]
