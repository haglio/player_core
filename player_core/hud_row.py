"""The scrubber, the volume chip and the playhead readout, drawn on a panel.

Every player here laid this row along the lower edge of its own video, which is
where a video player has always put it — and where, in this family, it keeps
turning out to be the wrong place.  A wrapped video smears it into a ring round
the nadir, out of the controller's reach, so the headset draws it on the console
instead.  Everything else has the same defect in slower form: a row over the
picture is a second panel, on a screen that already carries one.

So the row is a block a panel hosts, the way the device line and the drive
readout are: the same track, the same chip and the same pill this package
already draws, placed against the block's own width rather than the window's.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from .playhead import (
    PlayheadHud,
    PlayheadHudPainter,
    lower_edge_height,
    on_readout,
    readout_xy,
)
from .timeline import BAR_INSET_X, TIMELINE_HEIGHT, bar_track_x, progress_bar_bgra
from .volume import (
    SLOT_W,
    VolumeHud,
    VolumeHudPainter,
    chip_local,
    chip_xy,
    hit_part,
    volume_at,
)

__all__: list[str] = []

# What a press on the row is on.  The chip's two halves are named apart because
# they do different things to the same control: the speaker mutes, the slider
# sets the level.
SCRUBBER = "scrubber"
READOUT = "readout"
MUTE = "mute"
VOLUME = "volume"

_CHIP_PARTS = {"mute": MUTE, "track": VOLUME}

# The least track worth pressing.  Narrower than this the chip is pushed over
# the track and the row is one control on top of another, so the panel widens
# for the row the way it widens for its own rows.
_LEAST_TRACK = 60


@dataclass(frozen=True)
class RowHud:
    """What the row says: where the video is, how long it runs, how loud it is."""

    position_ms: float = 0.0
    duration_ms: float = 0.0
    volume: VolumeHud | None = None
    playhead: PlayheadHud | None = None


class RowSection:
    """The row itself, drawn into whatever panel is hosting it."""

    def __init__(self) -> None:
        self._volume = VolumeHudPainter()
        self._readout = PlayheadHudPainter()

    def least_width(self) -> int:
        """The narrowest panel the row can be laid out in."""
        return BAR_INSET_X + _LEAST_TRACK + SLOT_W

    def size(self, width: int) -> tuple[int, int]:
        """The room the row takes at *width* — one line where the readout fits
        beside the track, and a line for each where it does not."""
        return width, lower_edge_height(width, timeline_h=TIMELINE_HEIGHT)

    def draw(self, image: Image.Image, x: int, y: int, width: int, row: RowHud,
             *, heatmap: np.ndarray | None = None) -> None:
        """Paint the row with its top-left corner at ``(x, y)`` of *image*.

        *heatmap* is the funscript's colors across the track; without it the
        track is the plain bar.
        """
        _width, height = self.size(width)
        bar = progress_bar_bgra(row.position_ms, row.duration_ms, None, width, heatmap=heatmap)
        image.alpha_composite(_rgba(bar), (x, y + height - bar.shape[0]))
        if row.volume is not None:
            chip = _rgba(self._volume.bgra(row.volume))
            image.alpha_composite(chip, _offset((x, y), chip_xy(
                win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT)))
        if row.playhead is not None:
            pill = _rgba(self._readout.bgra(row.playhead))
            image.alpha_composite(pill, _offset((x, y), readout_xy(
                pill.width, win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT)))


def _rgba(bgra: np.ndarray) -> Image.Image:
    """One of this package's BGRA bitmaps as an image a panel can composite."""
    return Image.fromarray(np.ascontiguousarray(bgra[:, :, [2, 1, 0, 3]]), "RGBA")


def _offset(origin: tuple[int, int], place: tuple[int, int]) -> tuple[int, int]:
    return origin[0] + place[0], origin[1] + place[1]


def row_part(px: int, py: int, *, width: int) -> str:
    """Which control a press at the row's own ``(px, py)`` is on, or "" for none.

    The row is a video's last rows drawn somewhere else, so it is hit-tested as
    one: the same chip and readout placements, against the row's width and its
    own height rather than a window's.
    """
    height = lower_edge_height(width, timeline_h=TIMELINE_HEIGHT)
    part = hit_part(*chip_local(px, py, win_w=width, win_h=height,
                                timeline_h=TIMELINE_HEIGHT))
    if part:
        return _CHIP_PARTS[part]
    if on_readout(px, py, win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT):
        return READOUT
    return SCRUBBER if py >= height - TIMELINE_HEIGHT else ""


def scrub_to(px: int, *, width: int, duration_ms: float) -> float:
    """The time a press along the track asks for, saturating past either end."""
    x0, x1 = bar_track_x(width)
    return min(1.0, max(0.0, (px - x0) / max(1, x1 - x0))) * duration_ms


def volume_to(px: int, py: int, *, width: int) -> int:
    """The level a press along the slider asks for."""
    height = lower_edge_height(width, timeline_h=TIMELINE_HEIGHT)
    return volume_at(chip_local(px, py, win_w=width, win_h=height,
                                timeline_h=TIMELINE_HEIGHT)[0])
