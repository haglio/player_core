"""Which frame of the clip the stroke is showing.

Genau scrubs a looping clip with the stroke it is driving the device with. The
loop is one action and back: through its front half the clip travels from A to
B, through its back half from B to A, and the two ends are the one place a jump
between halves is invisible, because the frame there serves both.

What the frame means is the whole question, and there are three answers. It
could be timed off the stroke's turning points, stretching a whole A-to-B into
whatever stretch of seconds lies between two of them — which shows the full
action for a twitch that barely moved the device, and is a lie about what the
motor did. It could be carried along by how far the stroke has travelled, which
is smooth and needs no notion of a cycle, but leaves the frame with no standing
relationship to where the device actually is: after a while the clip is simply
somewhere, and the picture and the machine have nothing to say to each other.

This module is the third answer, and the only one where the picture is *of* the
device: the frame is where the device is. Parked shows A, fully retracted shows
B, and everything between shows the frame that far through the half. A stroke
that only ever works the middle of the axis therefore only ever shows the middle
of the half — the extent of what you watch is the extent of what moves — and a
stroke that turns back before an end rewinds the half it is in rather than
rolling on into the other one. The half changes only on arriving at A or B,
where the frames coincide.

Arriving is asked as a question about frames, not about the axis, and that is
what keeps it from needing a tolerance of its own. The device's position is read
on a tick, so it lands on exactly parked or exactly retracted essentially never;
but the frame at either end covers the last slice of the axis before it, and
being in that frame is being at the end. How wide the slice is, is the clip's
own answer — one frame of it.

Inside that slice the swap waits for the turn, rather than firing on the way in.
The two halves agree on the frame only at the very end, and disagree by however
far short of it you are, so swapping the moment the slice is entered would step
the picture by a frame or two. At the turn there is nothing left to be short by:
that is the highest (or lowest) the stroke got, and it is also, exactly, the
moment it reached the end and started back.
"""
from __future__ import annotations

from dataclasses import dataclass

# The two ends, named for the frames the loop shares there.
A_END = "A"
B_END = "B"


@dataclass
class ClipScrub:
    """Which half of the clip is showing, and what is known about the end the
    stroke is at — enough to swap halves once a visit, at the turn."""

    back_half: bool = False
    # The end the stroke is inside, if it is inside one, and whether this visit
    # has already had its swap.
    at_end: str | None = None
    spent: bool = True
    # The last position seen, which is how the turn is spotted, and whether
    # anything has been seen at all: a session opens with the device parked,
    # which is an end it did not arrive at.
    height: float = 0.0
    started: bool = False


def _turned(end: str, height: float, was: float) -> bool:
    """Whether the stroke has just started back from *end*."""
    return height < was if end is B_END else height > was


def scrub_clip(state: ClipScrub, height: float, frame_count: int) -> float:
    """The clip's display phase for a device sitting at *height*.

    *height* is 0 at the park and 1 fully retracted — the device's own position
    on its axis, which is the number the readout's dot draws, so the picture and
    the dot cannot disagree.

    The returned phase is a place around the loop: 0 and 1 are its A end, 0.5 the
    B end, and the halves are the two ways between. Whoever is showing the clip
    turns that into a frame.
    """
    height = min(1.0, max(0.0, height))
    span = 2.0 / frame_count if frame_count > 0 else 0.0
    end = B_END if height >= 1.0 - span else (A_END if height <= span else None)
    if not state.started:
        state.at_end, state.spent = end, True
    elif end != state.at_end:
        state.at_end, state.spent = end, end is None
    elif end is not None and not state.spent and _turned(end, height, state.height):
        state.back_half = not state.back_half
        state.spent = True
    state.height, state.started = height, True
    half = height / 2
    return 1.0 - half if state.back_half else half
