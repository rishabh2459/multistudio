"""Face detection with YuNet (OpenCV Zoo, MIT licence) on onnxruntime.

onnxruntime already ships with the app (Silero VAD), so this adds a 230 KB model
and no new runtime. Input: BGR uint8 frames of any size; they are letterboxed
into the model's 640x640 input. Output boxes are normalized to the frame (0..1).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt
import onnxruntime as ort

from multicam_engine.analysis.vad import models_dir

YUNET_MODEL_FILE = "face_detection_yunet_2023mar.onnx"
STRIDES = (8, 16, 32)

Image = npt.NDArray[np.uint8]


@dataclass(frozen=True)
class Face:
    """A detected face; coordinates are fractions of the frame width / height."""

    x: float
    y: float
    w: float
    h: float
    score: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> float:
        return self.w * self.h


class FaceDetector(Protocol):
    name: str

    def detect(self, image: Image) -> list[Face]:  # pragma: no cover - protocol
        ...


def _iou(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """IoU of box ``a`` (x1, y1, x2, y2) with each row of ``b``."""
    x1 = np.maximum(a[0], b[:, 0])
    y1 = np.maximum(a[1], b[:, 1])
    x2 = np.minimum(a[2], b[:, 2])
    y2 = np.minimum(a[3], b[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    result: npt.NDArray[np.float64] = inter / np.maximum(area_a + area_b - inter, 1e-9)
    return result


def nms(boxes: npt.NDArray[np.float64], scores: npt.NDArray[np.float64], iou: float) -> list[int]:
    order = np.argsort(-scores)
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        order = rest[_iou(boxes[i], boxes[rest]) < iou]
    return keep


class YuNetDetector:
    name = "yunet"

    def __init__(
        self,
        model_path: Path | None = None,
        *,
        score_threshold: float = 0.6,
        nms_iou: float = 0.3,
        min_size: float = 0.02,
    ) -> None:
        path = model_path or models_dir() / YUNET_MODEL_FILE
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(
            str(path), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        shape = self.session.get_inputs()[0].shape
        self.size = int(shape[2]) if isinstance(shape[2], int) else 640
        self.score_threshold = score_threshold
        self.nms_iou = nms_iou
        self.min_size = min_size
        self.output_names = [o.name for o in self.session.get_outputs()]

    def _letterbox(self, image: Image) -> tuple[npt.NDArray[np.float32], float]:
        h, w = image.shape[:2]
        scale = self.size / max(h, w)
        nh, nw = max(1, round(h * scale)), max(1, round(w * scale))
        # nearest-neighbour resize in numpy (no OpenCV dependency)
        ys = np.minimum((np.arange(nh) / scale).astype(np.int64), h - 1)
        xs = np.minimum((np.arange(nw) / scale).astype(np.int64), w - 1)
        resized = image[ys][:, xs]
        canvas = np.zeros((self.size, self.size, 3), dtype=np.float32)
        canvas[:nh, :nw] = resized
        return canvas.transpose(2, 0, 1)[None], scale

    def detect(self, image: Image) -> list[Face]:
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("expected an HxWx3 BGR image")
        h, w = image.shape[:2]
        blob, scale = self._letterbox(image)
        outputs = dict(zip(self.output_names, self.session.run(None, {"input": blob}), strict=True))
        boxes, scores = self._decode(outputs)
        if not len(scores):
            return []
        faces = []
        for i in nms(boxes, scores, self.nms_iou):
            x1, y1, x2, y2 = boxes[i] / scale
            x1, y1 = max(0.0, float(x1)), max(0.0, float(y1))
            x2, y2 = min(float(w), float(x2)), min(float(h), float(y2))
            if x2 - x1 < self.min_size * w or y2 - y1 < self.min_size * h:
                continue
            faces.append(Face(x1 / w, y1 / h, (x2 - x1) / w, (y2 - y1) / h, float(scores[i])))
        return sorted(faces, key=lambda f: -f.area)

    def _decode(
        self, out: dict[str, Any]
    ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        all_boxes, all_scores = [], []
        for stride in STRIDES:
            cols = rows = self.size // stride
            cls = np.clip(out[f"cls_{stride}"][0, :, 0], 0, 1)
            obj = np.clip(out[f"obj_{stride}"][0, :, 0], 0, 1)
            score = np.sqrt(cls * obj)
            keep = np.flatnonzero(score >= self.score_threshold)
            if not keep.size:
                continue
            bbox = out[f"bbox_{stride}"][0, keep].astype(np.float64)
            r, c = np.divmod(keep, cols)
            del rows
            cx = (c + bbox[:, 0]) * stride
            cy = (r + bbox[:, 1]) * stride
            bw = np.exp(bbox[:, 2]) * stride
            bh = np.exp(bbox[:, 3]) * stride
            all_boxes.append(np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1))
            all_scores.append(score[keep].astype(np.float64))
        if not all_boxes:
            return np.zeros((0, 4)), np.zeros(0)
        return np.concatenate(all_boxes), np.concatenate(all_scores)


def load_face_detector(model_path: Path | None = None) -> YuNetDetector | None:
    """The detector, or None when the model file is missing (framing then falls
    back to centred crops instead of failing)."""
    path = model_path or models_dir() / YUNET_MODEL_FILE
    if not path.is_file():
        return None
    return YuNetDetector(path)
