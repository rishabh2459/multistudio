"""jumpcut — find pauses and turn them into removals (AutoPod's Jump Cut Editor)."""

from multicam_engine.jumpcut.detect import (
    JumpCutParams,
    find_silences,
    jump_cut_cutlist,
    removals_for,
    silent_frames,
    with_silences,
)

__all__ = [
    "JumpCutParams",
    "find_silences",
    "jump_cut_cutlist",
    "removals_for",
    "silent_frames",
    "with_silences",
]
