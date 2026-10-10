"""The scrubber, the volume chip and the playhead readout, drawn on a panel.

Every Funestra here laid this row along the lower edge of its own video, which is
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

# Between the panel's lower edge and the loop's two frames hanging under it.
UNDER_THE_PANEL_GAP = 2


@dataclass(frozen=True)
class RowHud:
    """What the row says: where the video is, how long it runs, how loud it is,
    and the ends of the loop it is playing — the in point red while that loop is
    still being recorded."""

    position_ms: float = 0.0
    duration_ms: float = 0.0
    volume: VolumeHud | None = None
    playhead: PlayheadHud | None = None
    loop_bounds: tuple[float, float] | None = None
    record_in_ms: float | None = None


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

        *heatmap* is the funscript's colors across the track; without it, or
        with colors measured across some other width, the track is the plain
        bar.
        """
        _width, height = self.size(width)
        bar = progress_bar_bgra(row.position_ms, row.duration_ms, row.loop_bounds,
                                width, record_in_ms=row.record_in_ms,
                                heatmap=fitting(heatmap, width))
        image.alpha_composite(_rgba(bar), (x, y + height - bar.shape[0]))
        if row.volume is not None:
            chip = _rgba(self._volume.bgra(row.volume))
            image.alpha_composite(chip, _offset((x, y), chip_xy(
                win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT)))
        if row.playhead is not None:
            pill = _rgba(self._readout.bgra(row.playhead))
            image.alpha_composite(pill, _offset((x, y), readout_xy(
                pill.width, win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT)))


def fitting(heatmap, width: int):
    """The colors if they were measured across a track this wide, else None.

    A panel is as wide as what is on it, so how wide its track came out is an
    answer only a render gives: a host measures one panel and fills the next.
    Between those two the panel can change width, and a fill of the wrong
    length raises out of the track painter rather than stretching -- which
    takes the window's drawing down with it and leaves it showing no picture at
    all.  Dropping the stale fill costs one frame of plain track instead.
    """
    if heatmap is None or not len(heatmap):
        return None
    x0, x1 = bar_track_x(width)
    return heatmap if len(heatmap) == x1 - x0 else None


def track_on_screen(rect: tuple[int, int, int, int] | None, *, origin: tuple[int, int],
                    panel_height: int) -> tuple[int, int, int] | None:
    """Where the row's track runs in the window's own coordinates: its two ends
    and the y just under the panel, or None where no row is drawn.  A window
    hangs its loop's frames there, below their own marks on the track.
    """
    if rect is None:
        return None
    left, top = origin
    x0, x1 = bar_track_x(rect[2])
    return (left + rect[0] + x0, left + rect[0] + x1,
            top + panel_height + UNDER_THE_PANEL_GAP)


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


class RowPress:
    """What a press on the clip's row asks of the window that draws it.

    Every panel that hosts the row places a press on it with this, so the
    track, the slider and the speaker answer the same way wherever the row is
    drawn.  *rect* is where the row landed in the panel's own coordinates, and
    *duration_ms* how long the track spans -- the clip, or the window a loop
    being recorded has zoomed it to.
    """

    def __init__(self, *, seek=None, set_volume=None, toggle_mute=None) -> None:
        self._seek = seek
        self._set_volume = set_volume
        self._toggle_mute = toggle_mute
        self._holding = ""

    @property
    def holding(self) -> bool:
        return bool(self._holding)

    def press(self, px: int, py: int, *, rect, duration_ms: float) -> bool:
        """Whether this press landed on a control of the row, and if it did,
        what it asked: the track runs the clip there, the slider sets the level,
        the speaker mutes."""
        if rect is None:
            return False
        x, y, width, height = rect
        if not (x <= px < x + width and y <= py < y + height):
            return False
        self._holding = row_part(px - x, py - y, width=width)
        if not self._holding:
            return False
        self._act(px, py, rect=rect, duration_ms=duration_ms)
        return True

    def drag_to(self, px: int, py: int, *, rect, duration_ms: float) -> bool:
        """The track and the slider go on being set while the pointer is held
        down.  The speaker does not: the mute is a press, so a pointer crossing
        it on its way along the slider must not flip it."""
        if rect is None or self._holding not in (SCRUBBER, VOLUME):
            return False
        self._act(px, py, rect=rect, duration_ms=duration_ms)
        return True

    def release(self) -> None:
        self._holding = ""

    def _act(self, px: int, py: int, *, rect, duration_ms: float) -> None:
        x, y, width, _height = rect
        px, py = px - x, py - y
        if self._holding == SCRUBBER and self._seek is not None:
            self._seek(scrub_to(px, width=width, duration_ms=duration_ms))
        elif self._holding == VOLUME and self._set_volume is not None:
            self._set_volume(volume_to(px, py, width=width))
        elif self._holding == MUTE and self._toggle_mute is not None:
            self._toggle_mute()


def scrub_to(px: int, *, width: int, duration_ms: float) -> float:
    """The time a press along the track asks for, saturating past either end."""
    x0, x1 = bar_track_x(width)
    return min(1.0, max(0.0, (px - x0) / max(1, x1 - x0))) * duration_ms


def volume_to(px: int, py: int, *, width: int) -> int:
    """The level a press along the slider asks for."""
    height = lower_edge_height(width, timeline_h=TIMELINE_HEIGHT)
    return volume_at(chip_local(px, py, win_w=width, win_h=height,
                                timeline_h=TIMELINE_HEIGHT)[0])
