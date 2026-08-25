"""Where the drive readout's parts sit, and what a press on one of them asks for.

The readout — the trace of the stroke with Centre down its left, Amplitude down
its right and Speed under it — is placed here and painted in
:mod:`player_core.drive_readout`. This module draws nothing: it says how big the
block is, where each mark and band lands, which marks are dead at the end of
their range, and what value a press at a point is asking for.

Kept apart from the painter because the halves fail differently. A painter can
be wrong and look wrong; this can be wrong and look right — a hit target that
has drifted a few pixels from the mark over it is invisible until a press lands
on the wrong thing. So it is plain functions over plain numbers, and every panel
showing the readout is a thin painter over one tested layout.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry import Rect

# The three axes, named as the numeric set commands name them (``genau_amp_57``).
AMPLITUDE, CENTER, SPEED = "amp", "center", "speed"

# One pair of marks for every axis: the triangles that used to move amplitude
# and centre said "up/down" where speed said "less/more", which read as two
# different kinds of control for three things that are the same kind.
LESS, MORE = "−", "+"

_LABEL_H = 14        # a "key value" line
_BAR_H = 12          # the speed track's thickness
_CTRL = 14           # an integrated control button (square)
_GAP = 6
_AMP_W = 18          # the amplitude bar's width
_WAVE_H = 96         # the trace's own height
# The side labels stack their number under their word, so each column is only as
# wide as the wider of the two rather than as wide as both plus a gap.
_CTR_LABEL_W = 34    # room for "Center" down the left
_AMP_LABEL_W = 24    # room for "Amp" down the right
_WAVE_W = 120        # the trace, between the two axis columns

# The block: the trace's band, then the speed row and its number under it.
SECTION_W = _CTR_LABEL_W + _GAP + _CTRL + _GAP + _WAVE_W + _GAP + _AMP_W + _GAP + _AMP_LABEL_W
SECTION_H = _WAVE_H + _GAP + _CTRL + 2 + _LABEL_H

# The trace on its own, which is the whole readout in Nau: there is no Genau
# behind that screen, so its amplitude, centre and speed have nothing to act on
# and only the picture of what the device is being sent is worth drawing.
TRACE_ONLY_SIZE = (_WAVE_W, _WAVE_H)

# How many points the trace is drawn from. Shared, because a funscript sampled
# to take the trace over has to arrive at the same resolution as the stroke it
# replaces — a coarser or finer line would read as a different kind of thing.
TRACE_SAMPLES = 80

# What a painter needs to place its own text and marks beside these rects.
LABEL_H = _LABEL_H
CONTROL_SIZE = _CTRL
GAP = _GAP


def section_size(*, trace_only: bool = False) -> tuple[int, int]:
    """How much room the readout needs — the whole block, or the trace alone."""
    return TRACE_ONLY_SIZE if trace_only else (SECTION_W, SECTION_H)


@dataclass(frozen=True)
class DriveControl:
    rect: Rect
    action: str
    glyph: str
    dim: bool


@dataclass(frozen=True)
class DriveTrack:
    """A band of the readout that takes its value from where you press in it.

    The marks beside each axis step it; these are the axis itself, and each band
    is already the picture of its own value — so a press reads straight off what
    is drawn. Along the speed bar for the rate, up the amplitude bar for how far
    the stroke reaches, anywhere in the trace for the height it swings about.

    ``center`` is where the stroke sits as a 0-1 height, which the amplitude
    band mirrors about: the bar is drawn out from there in both directions, so
    grabbing either end and pulling sets how far the stroke has to reach.
    ``dim`` is the whole readout being unpressable — something else has the
    device — the same state the marks wear, and for the same reason.
    """

    rect: Rect
    axis: str
    tooltip: str
    center: float = 0.5
    dim: bool = False


@dataclass(frozen=True)
class Geometry:
    """Every rect the readout draws or hit-tests, placed once from the block's
    top-left corner, so the trace and the mark over it cannot drift apart."""

    wave: Rect
    speed_bar: Rect
    speed_down: Rect
    speed_up: Rect
    amp_bar: Rect
    amp_up: Rect
    amp_down: Rect
    center_up: Rect
    center_down: Rect
    center_label_right: int
    amp_label_left: int
    axis_label_y: int
    speed_label_y: int
    speed_label_x: int


def geometry(x: int, y: int, center_frac: float) -> Geometry:
    ctr_ctrl_x = x + _CTR_LABEL_W + _GAP
    wave_x = ctr_ctrl_x + _CTRL + _GAP
    amp_x = wave_x + _WAVE_W + _GAP
    wave = (wave_x, y, _WAVE_W, _WAVE_H)
    wave_bottom = y + _WAVE_H

    amp_up = (amp_x, y, _AMP_W, _CTRL)
    amp_down = (amp_x, wave_bottom - _CTRL, _AMP_W, _CTRL)
    amp_bar = (amp_x, y + _CTRL + 2, _AMP_W, _WAVE_H - 2 * (_CTRL + 2))

    # The centre marks ride its dotted line, kept inside the trace's band so a
    # centre at either end cannot push one off the block.
    center_y = y + round((1 - center_frac) * (_WAVE_H - 1))
    up_y = min(max(y, center_y - _CTRL - 1), wave_bottom - 2 * _CTRL - 2)
    center_up = (ctr_ctrl_x, up_y, _CTRL, _CTRL)
    center_down = (ctr_ctrl_x, up_y + _CTRL + 2, _CTRL, _CTRL)

    speed_y = wave_bottom + _GAP
    speed_down = (wave_x, speed_y, _CTRL, _CTRL)
    speed_up = (amp_x + _AMP_W - _CTRL, speed_y, _CTRL, _CTRL)
    bar_x = wave_x + _CTRL + 4
    speed_bar = (bar_x, speed_y + (_CTRL - _BAR_H) // 2,
                 (amp_x + _AMP_W - _CTRL - 4) - bar_x, _BAR_H)

    return Geometry(
        wave=wave, speed_bar=speed_bar, speed_down=speed_down, speed_up=speed_up,
        amp_bar=amp_bar, amp_up=amp_up, amp_down=amp_down,
        center_up=center_up, center_down=center_down,
        center_label_right=x + _CTR_LABEL_W,
        amp_label_left=amp_x + _AMP_W + _GAP,
        axis_label_y=y + (_WAVE_H - 2 * _LABEL_H) // 2,
        speed_label_y=speed_y + _CTRL + 2,
        speed_label_x=(wave_x + amp_x + _AMP_W) // 2,
    )


@dataclass(frozen=True)
class Limits:
    """Which of the three axes have run out of road, in which direction.

    Carried as a bundle so a caller cannot hand six booleans over in the wrong
    order: what they do is dim the mark that would now do nothing, and a
    transposed pair dims the wrong end of the wrong axis — a readout that is
    only quietly wrong.
    """

    spd_at_min: bool = False
    spd_at_max: bool = False
    amp_at_min: bool = False
    amp_at_max: bool = False
    ctr_at_min: bool = False
    ctr_at_max: bool = False


def controls(x: int, y: int, center: int, limits: Limits, *,
             dim: bool = False, trace_only: bool = False) -> list[DriveControl]:
    """The readout's marks at ``(x, y)`` — a −/+ pair for each of speed,
    amplitude and centre — each carrying the command it posts and whether it is
    dimmed at the end of its range.

    The commands are the ones Fun Time routes to Genau, written out so a verb
    can be grepped from either end.  *dim* dims all of them at once, which is
    what a readout nobody can adjust looks like — a funscript has the device, or
    the stroke is not running.

    None at all when only the trace is drawn: in Nau there is no engine behind
    the screen for a mark to reach.
    """
    if trace_only:
        return []
    g = geometry(x, y, fraction(center))
    return [
        DriveControl(g.speed_down, "genau_speed_down", LESS, dim or limits.spd_at_min),
        DriveControl(g.speed_up, "genau_speed_up", MORE, dim or limits.spd_at_max),
        DriveControl(g.amp_up, "genau_amplitude_up", MORE, dim or limits.amp_at_max),
        DriveControl(g.amp_down, "genau_amplitude_down", LESS, dim or limits.amp_at_min),
        DriveControl(g.center_up, "genau_center_up", MORE, dim or limits.ctr_at_max),
        DriveControl(g.center_down, "genau_center_down", LESS, dim or limits.ctr_at_min),
    ]


def tracks(x: int, y: int, center: int, *, dim: bool = False,
           trace_only: bool = False) -> list[DriveTrack]:
    """The readout's bands at ``(x, y)`` — the three you press to set a level
    outright instead of walking to it with the marks.

    A press anywhere on a bar asks for exactly the value drawn under the
    pointer, and holding the button keeps asking as the pointer moves. None of
    them carries a limit flag: a band sets an absolute value, so there is no end
    of a range to run out of. None at all when only the trace is drawn, for the
    same reason the marks are gone.
    """
    if trace_only:
        return []
    center_frac = fraction(center)
    g = geometry(x, y, center_frac)
    return [
        DriveTrack(g.amp_bar, AMPLITUDE, "Set how far the stroke reaches",
                   center_frac, dim),
        DriveTrack(g.wave, CENTER, "Set where the stroke is centered",
                   center_frac, dim),
        DriveTrack(g.speed_bar, SPEED, "Set how fast the stroke goes",
                   center_frac, dim),
    ]


def track_value(track: DriveTrack, px: int, py: int) -> int:
    """The 0-100 level a press at ``(px, py)`` asks *track* for.

    Read off the drawing rather than merely off the rect, so what you point at
    is what you get: the speed bar fills from its left edge, so a press is how
    far along it sits; the trace puts the centre's dotted line at its own
    height, so a press is that height; and the amplitude bar is drawn out from
    the centre in both directions, so a press is how far the stroke has to reach
    to arrive there — grab either end of the bar and pull.

    A point outside the band reads as its nearer end, so a drag that wanders off
    the bar goes on setting it rather than stopping dead at the edge.
    """
    x, y, w, h = track.rect
    if track.axis == SPEED:
        return percent((px - x) / max(1, w - 1))
    height = clamp01(1 - (py - y) / max(1, h - 1))
    if track.axis == CENTER:
        return percent(height)
    return percent(2 * abs(height - track.center))


def fraction(percent_value: int) -> float:
    """A 0-100 control value as a 0-1 bar fill, clamped."""
    return clamp01(percent_value / 100)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def percent(fraction_value: float) -> int:
    """A 0-1 bar fill back as the 0-100 value that would draw it."""
    return round(100 * clamp01(fraction_value))
