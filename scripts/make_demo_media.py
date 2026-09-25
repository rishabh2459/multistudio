"""Make a small synthetic 3-camera recording to try the app without real footage.

    uv run python scripts/make_demo_media.py            # -> samples/demo/
    uv run python scripts/make_demo_media.py OUT --seconds 60

Two "speaker" cameras (each mic hears its own person loudest) and a wide camera,
started at different times: cam2 1 s before cam1, the wide 0.5 s after cam1 and at
25 fps. The pictures are test patterns; the sound is speech-like noise with turns,
so sync and speaker detection behave like on a real conversation.
Used by the UI end-to-end test.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # the synthetic generators live in tests/

from multicam_engine.media.ffmpeg import find_tool  # noqa: E402
from tests.media_factory import write_clip  # noqa: E402
from tests.synth import conversation_mics  # noqa: E402

SR = 8000


def make_demo(out: Path, seconds: float = 40.0, seed: int = 21) -> list[Path]:
    ffmpeg = find_tool("ffmpeg")
    out.mkdir(parents=True, exist_ok=True)
    _, mics = conversation_mics(seconds, SR, gains=(1.0, 0.35), seed=seed)
    cam1 = write_clip(ffmpeg, out / "cam1.mp4", mics[0], SR)
    cam2 = write_clip(ffmpeg, out / "cam2.mp4", np.concatenate([np.zeros(SR), mics[1]]), SR)
    wide_audio = mics[0] * 0.5 + mics[1] * 1.2
    wide = write_clip(ffmpeg, out / "wide.mp4", wide_audio[SR // 2 :], SR, fps="25")
    for wav in out.glob("*.src.wav"):
        wav.unlink()
    return [cam1, cam2, wide]


def main() -> int:
    parser = argparse.ArgumentParser(description="Make a synthetic 3-camera demo recording.")
    parser.add_argument("out", nargs="?", type=Path, default=ROOT / "samples" / "demo")
    parser.add_argument("--seconds", type=float, default=40.0)
    args = parser.parse_args()
    for path in make_demo(args.out, args.seconds):
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
