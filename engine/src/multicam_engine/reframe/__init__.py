"""Auto zoom / reframe (Phase 8): face detection, smooth subject tracking,
punch-ins and crops for 16:9 and 9:16 output."""

from multicam_engine.reframe.auto import (
    VERTICAL_SIZE,
    ClipGeometry,
    FaceTracks,
    ReframeCancelledError,
    ReframeReport,
    ReframeSettings,
    auto_reframe,
    clip_geometry,
    detect_faces,
    detections_from_json,
    detections_to_json,
    plan_crop,
)
from multicam_engine.reframe.detect import (
    YUNET_MODEL_FILE,
    Face,
    FaceDetector,
    YuNetDetector,
    load_face_detector,
)
from multicam_engine.reframe.punch import PUNCH_PRESETS, PunchParams
from multicam_engine.reframe.track import Detections, SubjectPoint

__all__ = [
    "PUNCH_PRESETS",
    "VERTICAL_SIZE",
    "YUNET_MODEL_FILE",
    "ClipGeometry",
    "Detections",
    "Face",
    "FaceDetector",
    "FaceTracks",
    "PunchParams",
    "ReframeCancelledError",
    "ReframeReport",
    "ReframeSettings",
    "SubjectPoint",
    "YuNetDetector",
    "auto_reframe",
    "clip_geometry",
    "detect_faces",
    "detections_from_json",
    "detections_to_json",
    "load_face_detector",
    "plan_crop",
]
