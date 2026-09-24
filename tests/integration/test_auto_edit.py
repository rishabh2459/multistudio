"""Phase 2 end to end: generated camera files -> sync -> who speaks -> CutList. Needs ffmpeg."""

import json
from pathlib import Path

import numpy as np
import pytest

from multicam_engine.analysis.vad import SileroVad
from multicam_engine.benchmark.ground_truth import GroundTruth, GTClip, SpeechTurn
from multicam_engine.benchmark.switch_accuracy import evaluate_switching, score_switching
from multicam_engine.cli import main
from multicam_engine.models import ClipRole, CutList, Project
from multicam_engine.pipeline import auto_edit, build_project
from multicam_engine.sync import sync_files

from ..media_factory import flite_speech, has_flite, write_clip
from ..synth import Turn, conversation_mics, mic_mix

SR = 8000
LINES = [
    (0, "Welcome back to the show. Today we are talking about recording podcasts at home."),
    (1, "Thanks for having me. I have been editing videos for almost ten years now."),
    (0, "So what is the hardest part of editing a long conversation with several cameras?"),
    (1, "Honestly the switching. You watch hours of footage and cut to whoever is talking."),
    (0, "And that is exactly what we want the computer to do for us."),
    (1, "Right. If it gets ninety five percent of the cuts right, I just fix the rest."),
]


def _flite_conversation(ffmpeg: str) -> tuple[list[Turn], list[np.ndarray], float]:
    voices_ = ["slt", "kal"]
    clips = [(spk, flite_speech(ffmpeg, text, voices_[spk], SR)) for spk, text in LINES]
    duration = 1.0 + sum(len(a) / SR + 0.7 for _, a in clips) + 1.0
    n = int(duration * SR)
    tracks = [np.zeros(n), np.zeros(n)]
    turns: list[Turn] = []
    t = 1.0
    for spk, audio in clips:
        a = int(t * SR)
        tracks[spk][a : a + len(audio)] += audio
        turns.append(Turn(spk, t, t + len(audio) / SR))
        t += len(audio) / SR + 0.7
    return turns, tracks, duration


def _gt(
    turns: list[Turn], files: list[str], labels: list[str], wide: str | None = None
) -> GroundTruth:
    clips = [
        GTClip(file=f, speaker_label=lab, clap_start_ms=0)
        for f, lab in zip(files, labels, strict=True)
    ]
    if wide:
        clips.append(GTClip(file=wide, role=ClipRole.WIDE, clap_start_ms=0))
    return GroundTruth(
        recording_id="T2",
        reference_file=files[0],
        clips=clips,
        speech=[
            SpeechTurn(speaker_label=labels[t.speaker], start_ms=round(t.start_s * 1000),
                       end_ms=round(t.end_s * 1000))
            for t in turns
        ],
    )  # fmt: skip


def test_silero_on_real_speech(ffmpeg: str, silero_model: Path) -> None:
    if not has_flite(ffmpeg):
        pytest.skip("this ffmpeg has no flite text-to-speech")
    turns, tracks, duration = _flite_conversation(ffmpeg)
    mix = tracks[0] + tracks[1] + np.random.default_rng(0).standard_normal(len(tracks[0])) * 0.002
    prob = SileroVad(silero_model).speech_probability(mix, SR)
    assert len(prob) == len(mix) // 80
    truth = np.zeros(len(prob), dtype=bool)
    for turn in turns:
        truth[int(turn.start_s * 100) : int(turn.end_s * 100)] = True
    agreement = ((prob > 0.5) == truth).mean()
    assert agreement > 0.85
    assert prob[: int(0.8 * 100)].max() < 0.5  # leading silence
    assert duration > 30  # spans more than one 30 s block


def test_pipeline_with_silero_on_real_speech(
    ffmpeg: str, silero_model: Path, tmp_path: Path
) -> None:
    if not has_flite(ffmpeg):
        pytest.skip("this ffmpeg has no flite text-to-speech")
    turns, tracks, _ = _flite_conversation(ffmpeg)
    host = mic_mix(tracks, 0, bleed_db=-8, seed=1)
    guest = mic_mix(tracks, 1, bleed_db=-8, gain=0.4, seed=2)
    write_clip(ffmpeg, tmp_path / "cam1.mp4", host, SR)
    pre = np.zeros(int(1.5 * SR))  # guest camera started 1.5 s earlier
    write_clip(ffmpeg, tmp_path / "cam2.mp4", np.concatenate([pre, guest]), SR)

    report = sync_files([tmp_path / "cam1.mp4", tmp_path / "cam2.mp4"])
    assert report.clip("cam2.mp4").offset_seconds == pytest.approx(1.5, abs=0.005)
    project = build_project(report, labels={"cam1.mp4": "Host", "cam2.mp4": "Guest"})
    result = auto_edit(project, vad="silero")
    assert result.vad_backend == "silero"
    gt = _gt(turns, ["cam1.mp4", "cam2.mp4"], ["Host", "Guest"])
    acc = score_switching(gt, result.cutlist, project, min_shot_s=2.5)
    assert acc.accuracy >= 0.9, acc
    assert acc.short_shots == 0


def _synthetic_recording(ffmpeg: str, folder: Path) -> list[Turn]:
    folder.mkdir(parents=True, exist_ok=True)
    turns, mics = conversation_mics(150, SR, gains=(1.0, 0.35), seed=12)
    write_clip(ffmpeg, folder / "cam1.mp4", mics[0], SR)
    write_clip(ffmpeg, folder / "cam2.mp4", np.concatenate([np.zeros(SR), mics[1]]), SR)
    wide = mics[0] * 0.5 + mics[1] * 1.2
    write_clip(ffmpeg, folder / "wide.mp4", wide[SR // 2 :], SR, fps="25")
    return turns


def test_cli_sync_then_cutlist(
    ffmpeg: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _synthetic_recording(ffmpeg, tmp_path)
    sync_json = tmp_path / "sync.json"
    files = [str(tmp_path / f) for f in ("cam1.mp4", "cam2.mp4", "wide.mp4")]
    assert main(["sync", *files, "--out", str(sync_json), "--no-cache"]) == 0
    out = tmp_path / "cutlist.json"
    code = main(
        ["cutlist", "--sync", str(sync_json), "--wide", "wide.mp4",
         "--label", "cam1.mp4=Host", "--label", "cam2.mp4=Guest",
         "--preset", "balanced", "--vad", "energy", "--out", str(out), "--name", "Ep 1"]
    )  # fmt: skip
    assert code == 0
    printed = capsys.readouterr().out
    assert "Host" in printed and "Guest" in printed
    project = Project.model_validate_json((tmp_path / "project.json").read_text(encoding="utf-8"))
    cutlist = CutList.model_validate_json(out.read_text(encoding="utf-8"))
    cutlist.check_against(project)
    assert project.name == "Ep 1"
    roles = {Path(c.path).name: c.role for c in project.clips}
    assert roles == {
        "cam1.mp4": ClipRole.SPEAKER,
        "cam2.mp4": ClipRole.SPEAKER,
        "wide.mp4": ClipRole.WIDE,
    }
    assert len({s.clip_id for s in cutlist.segments}) >= 2
    assert main(["validate", "cutlist", str(out)]) == 0
    assert main(["cutlist", "--sync", str(sync_json), "--label", "bad"]) == 1
    json.loads(sync_json.read_text(encoding="utf-8"))


def test_eval_switch_on_synthetic_recording(ffmpeg: str, tmp_path: Path) -> None:
    rec = tmp_path / "T2"
    turns = _synthetic_recording(ffmpeg, rec)
    gt = _gt(turns, ["cam1.mp4", "cam2.mp4"], ["Host", "Guest"], wide="wide.mp4")
    (rec / "ground_truth.json").write_text(gt.model_dump_json(), encoding="utf-8")
    acc = evaluate_switching(rec, vad="energy")
    assert acc.accuracy >= 0.95, acc
    assert acc.short_shots == 0 and acc.passed
    assert main(["gt", "eval-switch", str(rec), "--vad", "energy"]) == 0
