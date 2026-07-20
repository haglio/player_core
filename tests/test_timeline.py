"""The shared scrubber: inset track geometry and the plain progress bar."""
from __future__ import annotations

from player_core.timeline import (
    BAR_INSET_Y,
    bar_track_x,
    progress_bar_bgra,
)
from player_core.volume import SLOT_W


def _rgba(bar, y, x):
    px = bar[y, x]
    return int(px[2]), int(px[1]), int(px[0]), int(px[3])


class TestBarTrackX:
    def test_insets_from_the_left_and_leaves_the_volume_slot_at_the_right(self):
        # The start sits a fixed margin in from the left; the end stops clear of
        # the volume control the way VLC's seek bar stopped short of its slider.
        assert bar_track_x(1000) == (40, 1000 - SLOT_W)

    def test_clamps_so_the_track_never_inverts_on_a_narrow_window(self):
        x0, x1 = bar_track_x(50)
        assert 0 <= x0 < x1 <= 50


class TestProgressBar:
    def test_track_is_inset_with_transparent_margins(self):
        bar = progress_bar_bgra(0, 10_000, None, 1000)
        x0, x1 = bar_track_x(1000)
        my = bar.shape[0] // 2
        # Nothing is drawn out at the window's side edges...
        assert bar[my, 5, 3] == 0
        assert bar[my, 995, 3] == 0
        # ...but the track interior is painted.
        assert bar[my, (x0 + x1) // 2, 3] > 0

    def test_has_a_two_tone_border_around_the_track(self):
        bar = progress_bar_bgra(0, 10_000, None, 1000)
        x0, x1 = bar_track_x(1000)
        xc = (x0 + x1) // 2
        fill = _rgba(bar, bar.shape[0] // 2, xc)      # interior fill
        outer = _rgba(bar, BAR_INSET_Y, xc)           # dark outer edge
        inner = _rgba(bar, BAR_INSET_Y + 1, xc)       # light inner border
        assert max(outer[:3]) < min(fill[:3])                     # darker than fill
        assert min(inner[:3]) > max(fill[:3]) and inner[3] >= 200  # lighter than fill

    def test_a_prominent_white_playcursor(self):
        bar = progress_bar_bgra(5_000, 10_000, None, 1000)  # 50%
        x0, x1 = bar_track_x(1000)
        my = bar.shape[0] // 2
        cursor_x = x0 + (x1 - x0 - 1) // 2
        # A bright, opaque column at the halfway mark.
        assert tuple(int(v) for v in bar[my, cursor_x]) == (255, 255, 255, 255)

    def test_the_track_ends_before_the_volume_slot(self):
        """The whole point of reserving SLOT_W: the fill and border stop clear of
        where the volume chip sits, so the two never draw over each other."""
        bar = progress_bar_bgra(10_000, 10_000, None, 1000)
        my = bar.shape[0] // 2
        _x0, x1 = bar_track_x(1000)
        # Just past the track's right edge is transparent, all the way to the chip.
        assert bar[my, x1 + 2, 3] == 0
