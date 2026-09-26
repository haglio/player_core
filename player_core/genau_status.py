"""What Genau publishes back: the status file an orchestrator reads."""
from __future__ import annotations

from pathlib import Path

from app_support.state_files import GENAU_STATUS

from .clip_advance import ClipAdvanceState
from .cruise_control import CruiseControlState
from .file_channel import publish_whole
from .learned_motion import LearnedMotionState
from .robot_hand import RobotHandState, control_limits

__all__ = [
    "build_status_text",
]

# Where the status goes when nobody names a path: beside the command file, which
# is where every version of the orchestrator so far has looked.  The name is
# the family's, spelled once where the orchestrator reads it too.
GENAU_STATUS_FILENAME = GENAU_STATUS


def _flag_or_unknown(flag: bool | None) -> str:
    return "" if flag is None else "1" if flag else "0"


def build_status_text(
    hand: RobotHandState,
    cruise: CruiseControlState,
    *,
    learned: LearnedMotionState | None = None,
    clip_advance: ClipAdvanceState | None = None,
    hud_active: bool = False,
    clip: Path | None = None,
    flipped: bool = False,
    portrait: bool | None = None,
) -> str:
    limits = control_limits(hand)
    advance = clip_advance or ClipAdvanceState()
    return (
        f"cruise={'1' if cruise.active else '0'}\n"
        f"learned={'1' if learned is not None and learned.active else '0'}\n"
        f"locked={'1' if advance.locked else '0'}\n"
        # Which clip is up.  Empty until the first clip is on screen.
        f"clip={clip if clip is not None else ''}\n"
        f"flipped={'1' if flipped else '0'}\n"
        f"portrait={_flag_or_unknown(portrait)}\n"
        f"shape={hand.shape.value}\n"
        f"amp_at_max={'1' if limits.amp_at_max else '0'}\n"
        f"amp_at_min={'1' if limits.amp_at_min else '0'}\n"
        f"ctr_at_max={'1' if limits.ctr_at_max else '0'}\n"
        f"ctr_at_min={'1' if limits.ctr_at_min else '0'}\n"
        f"spd_at_max={'1' if limits.spd_at_max else '0'}\n"
        f"spd_at_min={'1' if limits.spd_at_min else '0'}\n"
        f"hud={'1' if hud_active else '0'}\n"
    )


def write_status_file(path: Path, text: str) -> bool:
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except (OSError, ValueError):
        pass
    return publish_whole(path, text)
