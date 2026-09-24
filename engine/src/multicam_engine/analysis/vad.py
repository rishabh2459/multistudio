"""Voice activity detection: probability that someone is speaking, per 10 ms frame.

Backends
    ``SileroVad``  Silero VAD v5 (MIT) run with ONNX Runtime. Accurate on noisy
                   rooms, fans, music beds. The model file is bundled with the app
                   (dev: ``make fetch-models``).
    ``EnergyVad``  Loudness above the track's own noise floor. No model needed;
                   used as a fallback and in fast synthetic tests.

Silero is recurrent, so a long recording would need ~110 000 sequential model
calls per hour. Instead the audio is cut into 30 s blocks, each primed with 1 s
of the preceding audio (outputs discarded), and all blocks run as one batch:
~1 000 calls per hour of audio regardless of length.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import numpy.typing as npt
import onnxruntime as ort

from multicam_engine.analysis.energy import FEATURE_RATE, frame_energy_db, noise_floor_db

FloatArray = npt.NDArray[np.float64]
VadKind = Literal["auto", "silero", "energy"]

SILERO_MODEL_FILE = "silero_vad.onnx"


class VadUnavailableError(RuntimeError):
    """The requested VAD backend cannot be used (model or runtime missing)."""


class Vad(Protocol):
    name: str

    def speech_probability(
        self, audio: npt.NDArray[np.floating], sample_rate: int
    ) -> FloatArray:  # pragma: no cover - protocol
        """Speech probability (0..1) per 10 ms frame; length ``len(audio) // hop``."""
        ...


def models_dir() -> Path:
    """Where bundled model files live. ``MULTICAM_MODELS_DIR`` overrides (the
    desktop app sets it); otherwise the source tree's ``packaging/models``."""
    override = os.environ.get("MULTICAM_MODELS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[4] / "packaging" / "models"


def _n_frames(n_samples: int, sample_rate: int) -> int:
    return n_samples // (sample_rate // FEATURE_RATE)


# ------------------------------------------------------------------- energy
class EnergyVad:
    """Speech = clearly louder than this track's background."""

    name = "energy"

    def __init__(self, margin_db: float = 12.0, min_level_db: float = -60.0) -> None:
        self.margin_db = margin_db
        self.min_level_db = min_level_db

    def speech_probability(self, audio: npt.NDArray[np.floating], sample_rate: int) -> FloatArray:
        db = frame_energy_db(audio, sample_rate)
        if len(db) == 0:
            return db
        threshold = max(noise_floor_db(db) + self.margin_db, self.min_level_db)
        prob: FloatArray = 1.0 / (1.0 + np.exp(-(db - threshold) / 2.0))
        return prob


# ------------------------------------------------------------------- silero
class SileroVad:
    """Silero VAD v5 via ONNX Runtime, batched over blocks (see module docstring)."""

    name = "silero"
    BLOCK_S = 30.0
    WARMUP_S = 1.0

    def __init__(self, model_path: Path | None = None, threads: int = 4) -> None:
        path = model_path or models_dir() / SILERO_MODEL_FILE
        if not path.is_file():
            raise VadUnavailableError(
                f"Silero VAD model not found at {path} (run: make fetch-models)"
            )
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, min(threads, os.cpu_count() or 1))
        opts.inter_op_num_threads = 1
        self._session: Any = ort.InferenceSession(
            str(path), sess_options=opts, providers=["CPUExecutionProvider"]
        )

    def speech_probability(self, audio: npt.NDArray[np.floating], sample_rate: int) -> FloatArray:
        if sample_rate == 8000:
            chunk, context = 256, 32
        elif sample_rate == 16000:
            chunk, context = 512, 64
        else:
            raise ValueError("Silero VAD supports 8000 or 16000 Hz audio")
        x = np.asarray(audio, dtype=np.float32)
        n_frames = _n_frames(len(x), sample_rate)
        if n_frames == 0:
            return np.zeros(0)

        block = int(self.BLOCK_S * sample_rate) // chunk * chunk
        warm = int(self.WARMUP_S * sample_rate) // chunk * chunk
        starts = list(range(0, len(x), block))
        batch = np.zeros((len(starts), warm + block), dtype=np.float32)
        for b, s in enumerate(starts):
            lo = max(0, s - warm)
            seg = x[lo : s + block]
            batch[b, warm - (s - lo) : warm - (s - lo) + len(seg)] = seg

        state = np.zeros((2, len(starts), 128), dtype=np.float32)
        ctx = np.zeros((len(starts), context), dtype=np.float32)
        sr = np.array(sample_rate, dtype=np.int64)
        n_chunks = (warm + block) // chunk
        probs = np.zeros((len(starts), n_chunks), dtype=np.float64)
        for c in range(n_chunks):
            inp = np.concatenate([ctx, batch[:, c * chunk : (c + 1) * chunk]], axis=1)
            out, state = self._session.run(None, {"input": inp, "state": state, "sr": sr})
            probs[:, c] = np.asarray(out, dtype=np.float64)[:, 0]
            ctx = inp[:, -context:]

        per_chunk = probs[:, warm // chunk :].reshape(-1)  # drop warm-up, join blocks
        # Map each 10 ms frame (by its centre) to the 32 ms chunk containing it.
        hop = sample_rate // FEATURE_RATE
        centres = np.arange(n_frames) * hop + hop // 2
        idx = np.minimum(centres // chunk, len(per_chunk) - 1)
        result: FloatArray = per_chunk[idx]
        return result


def load_vad(kind: VadKind = "auto") -> tuple[Vad, str | None]:
    """Return a VAD backend and an optional warning (when falling back)."""
    if kind == "energy":
        return EnergyVad(), None
    try:
        return SileroVad(), None
    except VadUnavailableError as exc:
        if kind == "silero":
            raise
        return EnergyVad(), f"{exc}; using the simpler energy-based VAD"
