"""The scrubber every player in this family draws along the bottom of its video.

An inset, floated, bordered track with a full-height playcursor and loop/record
marks — Nau draws it under a funscript heatmap or as a plain bar, and a silent
satellite draws the plain bar as a progress indicator.  Both players are separate
processes in separate repos, so the track and its frame live here in the shared
engine; the funscript heatmap that fills Nau's version stays in Nau, built on the
frame this module owns.

The track stops short of the volume chip that shares its row — ``bar_track_x``
subtracts :data:`player_core.volume.SLOT_W` — so the two never overlap and
click-to-seek maps onto exactly the drawn track.  These are plain numpy arrays
(BGRA, mpv's overlay format); no pygame.
"""
from __future__ import annotations

import numpy as np

from player_core.volume import SLOT_W as _VOLUME_SLOT_W

__all__ = [
    "BAR_BORDER",
    "BAR_INSET_Y",
    "BORDER_W",
    "TIMELINE_HEIGHT",
    "bar_track_x",
    "bar_x",
    "draw_border",
    "draw_track_marks",
    "framed_track",
    "progress_bar_bgra",
]

RED = (220, 40, 40, 245)
AMBER = (235, 180, 60, 245)

# The timeline — heatmap strip or plain bar — is drawn as one shared frame: an
# inset, floated, bordered track with full-height marks.
BAR_INSET_X = 40     # side margin so the timeline's start clears the left edge
BAR_INSET_Y = 3      # top/bottom margin so the timeline floats off the edge
BAR_FILL = (34, 34, 38, 165)       # dark translucent fill (plain bar only)
BAR_BORDER = (215, 215, 220, 235)  # light inner border (reads on the dark fill)
BAR_EDGE = (8, 8, 10, 235)         # dark outer edge (reads on the bright heatmap)
BORDER_W = 2
CURSOR = (255, 255, 255, 255)   # prominent white playcursor
CURSOR_W = 3
MARK_W = 4                      # prominent loop in/out and record marks

TIMELINE_HEIGHT = 24  # bottom strip height when not recording


def bar_track_x(width: int) -> tuple[int, int]:
    """Left/right pixel bounds of the inset timeline track.

    The start sits a fixed margin in from the left edge; the end stops short of
    the volume control that shares the row, the way VLC's seek bar stopped clear
    of its slider — :data:`player_core.volume.SLOT_W` is the room it leaves.
    Clamped so the track never inverts on a very narrow window.  The heatmap strip,
    the plain bar and click-to-seek all use this, so they agree on where the track
    ends.
    """
    inset = min(BAR_INSET_X, max(0, width // 2 - 1))
    return inset, max(inset + 1, width - _VOLUME_SLOT_W)


def paint_rect(bgra, x0, x1, y0, y1, color):
    """Fill rows [y0:y1], cols [x0:x1] with an RGBA ``color``, clamped to the
    array (stored BGRA for mpv)."""
    h, w = bgra.shape[:2]
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return
    bgra[y0:y1, x0:x1] = (color[2], color[1], color[0], color[3])


def _ring(bgra, x0, x1, y0, y1, t, color):
    """Draw a ``t``-thick hollow rectangle just inside [x0:x1] x [y0:y1]."""
    paint_rect(bgra, x0, x1, y0, y0 + t, color)  # top
    paint_rect(bgra, x0, x1, y1 - t, y1, color)  # bottom
    paint_rect(bgra, x0, x0 + t, y0, y1, color)  # left
    paint_rect(bgra, x1 - t, x1, y0, y1, color)  # right


def draw_border(bgra, x0, x1, y0, y1, bw, color):
    """A two-tone frame: a 1px dark outer edge inside a light inner border, so
    it reads against both the plain bar's dark fill and the bright heatmap."""
    _ring(bgra, x0, x1, y0, y1, 1, BAR_EDGE)
    _ring(bgra, x0 + 1, x1 - 1, y0 + 1, y1 - 1, bw - 1, color)


def _paint_mark(bgra, x_center, mark_w, y0, y1, color, *, x_lo, x_hi):
    """Paint a ``mark_w``-wide vertical bar centred on ``x_center``, kept
    within [x_lo, x_hi]."""
    left = max(x_lo, x_center - mark_w // 2)
    right = min(x_hi, left + mark_w)
    paint_rect(bgra, left, right, y0, y1, color)


def bar_x(ms, duration_ms, x0, x1):
    """Track x for a timestamp: its fraction of the video, mapped into
    [x0, x1] and kept on-track."""
    frac = min(1.0, max(0.0, ms / max(1.0, duration_ms)))
    return x0 + int(frac * (x1 - x0 - 1))


def framed_track(width, height):
    """A transparent full-width BGRA array plus the inset, floated track rect
    (x0, x1, y0, y1) that both the plain bar and the heatmap strip draw into."""
    bar = np.zeros((height, width, 4), dtype=np.uint8)
    x0, x1 = bar_track_x(width)
    return bar, x0, x1, BAR_INSET_Y, height - BAR_INSET_Y


def draw_track_marks(bgra, *, x0, x1, y0, y1, to_x, position_ms,
                     loop_bounds, record_in_ms):
    """Full-height playcursor + amber loop in/out (and red record-in) ticks on a
    framed track.  ``to_x(ms)`` maps a timestamp to an absolute x in [x0, x1].
    Ticks span the whole frame (crossing the border) and are fully opaque, so
    they stay prominent over any fill or video."""
    def mark(ms, mark_w, color):
        _paint_mark(bgra, to_x(ms), mark_w, y0, y1, (*color[:3], 255),
                    x_lo=x0, x_hi=x1)

    if record_in_ms is not None:
        mark(record_in_ms, MARK_W, RED)
    if loop_bounds is not None:
        mark(loop_bounds[0], MARK_W, AMBER)
        mark(loop_bounds[1], MARK_W, AMBER)
    mark(position_ms, CURSOR_W, CURSOR)  # playcursor on top


def progress_bar_bgra(position_ms, duration_ms, loop_bounds, width,
                      record_in_ms=None, height=TIMELINE_HEIGHT):
    """A bordered, inset seek bar for videos with no funscript heatmap.

    Shares the heatmap strip's frame — a dark translucent track floated in from
    the window edges under a light border, with a full-height white playcursor
    and full-height loop in/out marks (amber; the in point shows red while it is
    still being recorded) — so every video, scripted or not, has a clear timeline.
    """
    bar, x0, x1, y0, y1 = framed_track(width, height)
    paint_rect(bar, x0, x1, y0, y1, BAR_FILL)
    draw_border(bar, x0, x1, y0, y1, BORDER_W, BAR_BORDER)
    draw_track_marks(
        bar, x0=x0, x1=x1, y0=y0, y1=y1,
        to_x=lambda ms: bar_x(ms, duration_ms, x0, x1),
        position_ms=position_ms, loop_bounds=loop_bounds, record_in_ms=record_in_ms,
    )
    return bar
