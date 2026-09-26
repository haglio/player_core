"""The scrubber, the volume chip and the playhead readout, drawn on a panel."""
from __future__ import annotations

import numpy as np
from PIL import Image

from player_core.hud_row import (
    MUTE,
    SCRUBBER,
    VOLUME,
    RowHud,
    RowSection,
    row_part,
    scrub_to,
    volume_to,
)
from player_core.playhead import lower_edge_height
from player_core.timeline import HEATMAP_ALPHA, TIMELINE_HEIGHT, bar_track_x
from player_core.volume import CHIP_H, CHIP_W, MAX_VOLUME, MIN_VOLUME, SPEAKER_W, VolumeHud, chip_xy


def test_a_wide_panel_carries_the_whole_row_on_one_line():
    """Wide enough, the readout sits beside the track, as it does along the lower
    edge of a wide video."""
    assert RowSection().size(900) == (900, TIMELINE_HEIGHT)


def test_a_narrow_panel_stacks_the_readout_above_the_track():
    """A console is narrower than any video, so the readout takes a line of its
    own rather than squeezing the track out."""
    width, height = RowSection().size(380)

    assert (width, height) == (380, lower_edge_height(380, timeline_h=TIMELINE_HEIGHT))
    assert height > TIMELINE_HEIGHT


def test_it_draws_the_track_and_the_chip_inside_the_room_it_asked_for():
    section = RowSection()
    width, height = section.size(400)
    panel = Image.new("RGBA", (width + 40, height + 40), (0, 0, 0, 0))

    section.draw(panel, 20, 20, width, RowHud(position_ms=30_000, duration_ms=60_000,
                                              volume=VolumeHud(volume=50)))

    painted = np.argwhere(np.asarray(panel)[:, :, 3] > 0)
    assert painted.size
    assert painted[:, 0].min() >= 20 and painted[:, 0].max() < 20 + height
    assert painted[:, 1].min() >= 20 and painted[:, 1].max() < 20 + width


def test_a_host_with_a_funscript_fills_the_track_with_its_colors():
    section = RowSection()
    width, height = section.size(400)
    x0, x1 = bar_track_x(width)
    colors = np.array([(200, 40 + x % 150, 30) for x in range(x1 - x0)], dtype=np.uint8)
    panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    section.draw(panel, 0, 0, width, RowHud(position_ms=0, duration_ms=60_000), heatmap=colors)

    middle = np.asarray(panel)[height - TIMELINE_HEIGHT // 2]
    assert middle[x0 + 10:x1 - 10].tolist() == [
        [*color, HEATMAP_ALPHA] for color in colors[10:-10].tolist()]


class TestWhatAPressOnTheRowIsOn:
    """The row is pressed where it is drawn: a panel hands it the press in its
    own coordinates and it says which control was under it."""

    WIDTH = 400

    def _part(self, px, py):
        return row_part(px, py, width=self.WIDTH)

    def test_the_track_is_the_scrubber(self):
        height = RowSection().size(self.WIDTH)[1]
        assert self._part(self.WIDTH // 2, height - 4) == SCRUBBER

    def test_the_speaker_mutes_and_the_slider_sets_the_level(self):
        height = RowSection().size(self.WIDTH)[1]
        chip_x, chip_y = chip_xy(win_w=self.WIDTH, win_h=height, timeline_h=TIMELINE_HEIGHT)

        assert self._part(chip_x + 4, chip_y + CHIP_H // 2) == MUTE
        assert self._part(chip_x + CHIP_W - 6, chip_y + CHIP_H // 2) == VOLUME

    def test_a_press_off_every_control_is_on_none_of_them(self):
        """The line the readout takes on a narrow row is its own; past its end
        there is nothing to press."""
        assert self._part(self.WIDTH - 5, 0) == ""

    def test_a_press_along_the_track_names_the_time_under_it(self):
        x0, x1 = bar_track_x(self.WIDTH)

        assert scrub_to(x0, width=self.WIDTH, duration_ms=60_000) == 0
        assert scrub_to(x1, width=self.WIDTH, duration_ms=60_000) == 60_000
        assert 29_000 < scrub_to((x0 + x1) // 2, width=self.WIDTH,
                                 duration_ms=60_000) < 31_000

    def test_a_press_along_the_slider_names_the_level_under_it(self):
        height = RowSection().size(self.WIDTH)[1]
        chip_x, chip_y = chip_xy(win_w=self.WIDTH, win_h=height, timeline_h=TIMELINE_HEIGHT)

        assert volume_to(chip_x + SPEAKER_W, chip_y, width=self.WIDTH) == MIN_VOLUME
        assert volume_to(chip_x + CHIP_W, chip_y, width=self.WIDTH) == MAX_VOLUME
