"""The scrubber, the volume chip, the playhead readout and a flick's loop dial, drawn on a panel.

Every Funestra here laid this row along the lower edge of its own video, which is
where a video player has always put it — and where, in this family, it keeps
turning out to be the wrong place.  A wrapped video smears it into a ring round
the nadir, out of the controller's reach, so the headset draws it on the console
instead.  Everything else has the same defect in slower form: a row over the
picture is a second panel, on a screen that already carries one.

So the row is a block a panel hosts, the way the device line and the drive
readout are: one line, laid out from what is on it against the block's own
width rather than the window's.  The track is what the room is for -- the
heatmap and a seek need it wide -- so everything else takes only what it
must: a video's readout at the left end; a flick's dial with its frame count,
then its time, each readout against the control it reads out; the chip flush
with the right end.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from .loop_dial import DIAL_SIZE, LoopDialPainter, on_dial, turn_at
from .playhead import (
    PlayheadHud,
    PlayheadHudPainter,
    flick_playhead,
    readout_width,
    video_playhead,
)
from .timeline import TIMELINE_HEIGHT, bar_track_x, progress_bar_bgra
from .volume import (
    CHIP_H,
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
DIAL = "dial"

_CHIP_PARTS = {"mute": MUTE, "track": VOLUME}

ROW_H = TIMELINE_HEIGHT
# The readout, the dial and the chip are as tall as each other, centered in the row.
PARTS_Y = (ROW_H - CHIP_H) // 2
# Between a readout and the control it reads out, and between the dial's pair
# and the time's.
GAP = 4
GROUP_GAP = 10

# Between the panel's lower edge and the loop's two frames hanging under it.
UNDER_THE_PANEL_GAP = 2

# The readouts a panel is held wide enough for, so it keeps one width from one
# flick or video to the next instead of moving with the digits of each: a flick
# of up to 999 frames, and a video of under an hour at up to 60 frames a second.
_HELD_FRAME_COUNT = flick_playhead(999, 999)
_HELD_VIDEO_READOUT = video_playhead(3_599_000, 3_599_000, 60.0)


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
    # A flick's loop: how many of its frames have played, of how many.  The
    # dial goes round with it and the frame count after the dial counts it;
    # None on a video's row, which has neither.
    loop: tuple[int, int] | None = None


# The widest rows a panel carries, each with the longest readouts it is held for.
_WIDEST_ROWS = (
    RowHud(playhead=video_playhead(599_000, 599_000, 0.0), loop=(0, 999)),
    RowHud(playhead=_HELD_VIDEO_READOUT),
)


@dataclass(frozen=True)
class RowLayout:
    """Where the row lies in its panel, and where each part lands across it,
    left to right: a flick's dial and its frame count, the time, the track,
    and the chip."""

    rect: tuple[int, int, int, int]
    readout: tuple[int, int] | None  # the time's x and width, in the row's own pixels
    dial: int | None                  # the dial's x
    frame: tuple[int, int] | None    # the frame count's x and width
    track: tuple[int, int]            # the track's two ends

    @property
    def width(self) -> int:
        return self.rect[2]

    def inside(self, px: int, py: int) -> bool:
        x, y, width, height = self.rect
        return x <= px < x + width and y <= py < y + height

    def local(self, px: int, py: int) -> tuple[int, int]:
        return px - self.rect[0], py - self.rect[1]


def _frame_count(row: RowHud) -> PlayheadHud | None:
    return None if row.loop is None else flick_playhead(*row.loop)


def _before_the_track(row: RowHud, *, held: bool = False) -> tuple[
        tuple[int, int] | None, int | None, tuple[int, int] | None, int]:
    """The dial's place and its frame count's, the time's, and where the track
    starts after them, from the row's own left edge; *held*, with each readout
    as wide as the widest a panel is held for."""
    x = 0
    readout = dial = frame = None
    count = _frame_count(row)
    if count is not None:
        dial = x
        x += DIAL_SIZE + GAP
        width = _width(count, _HELD_FRAME_COUNT if held else None)
        frame = (x, width)
        x += width + GROUP_GAP
    if row.playhead is not None:
        width = _width(row.playhead, _HELD_VIDEO_READOUT if held and count is None else None)
        readout = (x, width)
        x += width + GAP
    return readout, dial, frame, x


def _width(readout: PlayheadHud, held_for: PlayheadHud | None) -> int:
    width = readout_width(readout)
    return width if held_for is None else max(width, readout_width(held_for))


def row_layout(row: RowHud, *, rect: tuple[int, int, int, int]) -> RowLayout:
    readout, dial, frame, left = _before_the_track(row)
    return RowLayout(rect, readout, dial, frame, bar_track_x(rect[2], left=left))


class RowSection:
    """The row itself, drawn into whatever panel is hosting it."""

    def __init__(self) -> None:
        self._volume = VolumeHudPainter()
        self._readout = PlayheadHudPainter()
        self._dial = LoopDialPainter()

    @staticmethod
    def least_width(row: RowHud) -> int:
        """The narrowest panel the row can be laid out in: one that leaves the
        track no shorter than everything else on the line, since the heatmap
        and a seek are what the row is for."""
        return 2 * (_before_the_track(row, held=True)[3] + SLOT_W)

    @staticmethod
    def least_width_for_any_row() -> int:
        """The narrowest panel every row a panel can carry fits in."""
        return max(RowSection.least_width(row) for row in _WIDEST_ROWS)

    def draw(self, image: Image.Image, layout: RowLayout, row: RowHud,
             *, heatmap: np.ndarray | None = None) -> None:
        """Paint the row where *layout* put it in *image*.

        *heatmap* is the funscript's colors across the track; without it, or
        with colors measured across some other width, the track is the plain
        bar.
        """
        x, y, width, _height = layout.rect
        bar = progress_bar_bgra(row.position_ms, row.duration_ms, row.loop_bounds,
                                width, record_in_ms=row.record_in_ms,
                                heatmap=fitting(heatmap, layout.track), track=layout.track)
        image.alpha_composite(_rgba(bar), (x, y))
        if row.volume is not None:
            chip = _rgba(self._volume.bgra(row.volume))
            image.alpha_composite(chip, _offset((x, y), chip_xy(
                win_w=width, win_h=ROW_H, timeline_h=ROW_H)))
        if layout.dial is not None:
            played, count = row.loop
            dial = _rgba(self._dial.bgra(LoopDialPainter.hand(played / count)))
            image.alpha_composite(dial, (x + layout.dial, y + PARTS_Y))
        if layout.frame is not None:
            frame = _rgba(self._readout.bgra(_frame_count(row)))
            image.alpha_composite(frame, (x + layout.frame[0], y + PARTS_Y))
        if layout.readout is not None:
            readout = _rgba(self._readout.bgra(row.playhead))
            image.alpha_composite(readout, (x + layout.readout[0], y + PARTS_Y))


def fitting(heatmap, track: tuple[int, int]):
    """The colors if they were measured across *track*, else None.

    A panel is as wide as what is on it, so how wide its track came out is an
    answer only a render gives: a host measures one panel and fills the next.
    Between those two the panel can change width, and a fill of the wrong
    length raises out of the track painter rather than stretching -- which
    takes the window's drawing down with it and leaves it showing no picture at
    all.  Dropping the stale fill costs one frame of plain track instead.
    """
    if heatmap is None or not len(heatmap):
        return None
    x0, x1 = track
    return heatmap if len(heatmap) == x1 - x0 else None


def track_on_screen(layout: RowLayout | None, *, origin: tuple[int, int],
                    panel_height: int) -> tuple[int, int, int] | None:
    """Where the row's track runs in the window's own coordinates: its two ends
    and the y just under the panel, or None where no row is drawn.  A window
    hangs its loop's frames there, below their own marks on the track.
    """
    if layout is None:
        return None
    left, top = origin
    x0, x1 = layout.track
    return (left + layout.rect[0] + x0, left + layout.rect[0] + x1,
            top + panel_height + UNDER_THE_PANEL_GAP)


def _rgba(bgra: np.ndarray) -> Image.Image:
    """One of this package's BGRA bitmaps as an image a panel can composite."""
    return Image.fromarray(np.ascontiguousarray(bgra[:, :, [2, 1, 0, 3]]), "RGBA")


def _offset(origin: tuple[int, int], place: tuple[int, int]) -> tuple[int, int]:
    return origin[0] + place[0], origin[1] + place[1]


def row_part(px: int, py: int, layout: RowLayout) -> str:
    """Which control a press at the row's own ``(px, py)`` is on, or "" for none.

    The row is a video's last rows drawn somewhere else, so it is hit-tested as
    one: the same chip placement, against the row's width and its own height
    rather than a window's, and the dial and the readout where the layout put
    them.
    """
    if not 0 <= py < ROW_H:
        return ""
    part = hit_part(*chip_local(px, py, win_w=layout.width, win_h=ROW_H, timeline_h=ROW_H))
    if part:
        return _CHIP_PARTS[part]
    if layout.dial is not None and on_dial(px, py, at=(layout.dial, PARTS_Y)):
        return DIAL
    return READOUT if px < layout.track[0] else SCRUBBER


class RowPress:
    """What a press on the clip's row asks of the window that draws it.

    The Funestra's own overlays place a press on the row with this, so the
    track, the dial, the slider and the speaker answer the same way on each of
    them.  *layout* is where the row landed in the panel's own coordinates,
    and *duration_ms* how long the track spans -- the clip, or the window a
    loop being recorded has zoomed it to.
    """

    def __init__(self, *, seek=None, seek_loop=None, set_volume=None, toggle_mute=None) -> None:
        self._seek = seek
        self._seek_loop = seek_loop
        self._set_volume = set_volume
        self._toggle_mute = toggle_mute
        self._holding = ""

    @property
    def holding(self) -> bool:
        return bool(self._holding)

    def press(self, px: int, py: int, *, layout: RowLayout | None, duration_ms: float) -> bool:
        """Whether this press landed on a control of the row, and if it did,
        what it asked: the track runs the clip there, the dial turns its loop,
        the slider sets the level, the speaker mutes."""
        if layout is None or not layout.inside(px, py):
            return False
        self._holding = row_part(*layout.local(px, py), layout)
        if not self._holding:
            return False
        self._act(px, py, layout=layout, duration_ms=duration_ms)
        return True

    def drag_to(self, px: int, py: int, *, layout: RowLayout | None, duration_ms: float) -> bool:
        """The track, the dial and the slider go on being set while the pointer
        is held down.  The speaker does not: the mute is a press, so a pointer
        crossing it on its way along the slider must not flip it."""
        if layout is None or self._holding not in (SCRUBBER, DIAL, VOLUME):
            return False
        self._act(px, py, layout=layout, duration_ms=duration_ms)
        return True

    def release(self) -> None:
        self._holding = ""

    def _act(self, px: int, py: int, *, layout: RowLayout, duration_ms: float) -> None:
        px, py = layout.local(px, py)
        if self._holding == SCRUBBER and self._seek is not None:
            self._seek(scrub_to(px, layout, duration_ms=duration_ms))
        elif self._holding == DIAL and self._seek_loop is not None:
            self._seek_loop(turn_to(px, py, layout))
        elif self._holding == VOLUME and self._set_volume is not None:
            self._set_volume(volume_to(px, py, layout))
        elif self._holding == MUTE and self._toggle_mute is not None:
            self._toggle_mute()


def scrub_to(px: int, layout: RowLayout, *, duration_ms: float) -> float:
    """The time a press along the track asks for, saturating past either end."""
    x0, x1 = layout.track
    return min(1.0, max(0.0, (px - x0) / max(1, x1 - x0))) * duration_ms


def volume_to(px: int, py: int, layout: RowLayout) -> int:
    """The level a press along the slider asks for."""
    return volume_at(chip_local(px, py, win_w=layout.width, win_h=ROW_H, timeline_h=ROW_H)[0])


def turn_to(px: int, py: int, layout: RowLayout) -> float:
    """The turn a press round the dial asks for, clockwise from twelve o'clock."""
    return turn_at(px, py, at=(layout.dial, PARTS_Y))
