"""The scrubber, the volume chip and the playhead readout, drawn on a panel."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from funestra_core.hud_row import (
    DIAL,
    MUTE,
    SCRUBBER,
    VOLUME,
    RowHud,
    RowPress,
    RowSection,
    row_part,
    scrub_to,
    turn_to,
    volume_to,
)
from funestra_core.loop_dial import DIAL_SIZE, dial_xy
from funestra_core.playhead import PlayheadHud, PlayheadHudPainter, lower_edge_height, readout_xy
from funestra_core.timeline import (
    AMBER,
    HEATMAP_ALPHA,
    RED,
    TIMELINE_HEIGHT,
    bar_track_x,
)
from funestra_core.volume import (
    CHIP_H,
    CHIP_W,
    MAX_VOLUME,
    MIN_VOLUME,
    SPEAKER_W,
    VolumeHud,
    chip_xy,
)


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


def _marks(panel, height, color) -> list[int]:
    """The middle of each mark the track carries in *color*, left to right."""
    pixels = np.asarray(panel)[height - TIMELINE_HEIGHT // 2]
    columns = [x for x, pixel in enumerate(pixels.tolist())
               if tuple(pixel[:3]) == tuple(color[:3])]
    marks: list[list[int]] = []
    for x in columns:
        if marks and x == marks[-1][-1] + 1:
            marks[-1].append(x)
        else:
            marks.append([x])
    return [sum(mark) // len(mark) for mark in marks]


def test_a_loop_being_played_shows_its_ends_on_the_track():
    """The row is the lower edge of a Funestra's video, and the Funestra marks a
    loop's in and out there — so the panel does too."""
    section = RowSection()
    width, height = section.size(400)
    x0, x1 = bar_track_x(width)
    panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    section.draw(panel, 0, 0, width, RowHud(position_ms=0, duration_ms=60_000,
                                            loop_bounds=(15_000, 45_000)))

    assert _marks(panel, height, AMBER) == [
        pytest.approx(x0 + (x1 - x0) // 4, abs=3),
        pytest.approx(x0 + 3 * (x1 - x0) // 4, abs=3),
    ]


def test_a_loop_still_being_recorded_shows_its_in_point_in_red():
    section = RowSection()
    width, height = section.size(400)
    x0, x1 = bar_track_x(width)
    panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    section.draw(panel, 0, 0, width, RowHud(position_ms=0, duration_ms=60_000,
                                            record_in_ms=30_000))

    assert _marks(panel, height, RED) == [pytest.approx(x0 + (x1 - x0) // 2, abs=3)]


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


class TestWhatAPressOnTheRowAsksFor:
    """One placement for every panel that hosts the row, so the track, the
    slider and the speaker answer the same way wherever the row is drawn."""

    WIDTH = 400
    RECT = (10, 40, WIDTH, RowSection().size(WIDTH)[1])
    DURATION_MS = 10_000.0

    def _press(self):
        asked = SimpleNamespace(seeks=[], levels=[], mutes=0)
        press = RowPress(seek=asked.seeks.append, set_volume=asked.levels.append,
                         toggle_mute=lambda: setattr(asked, "mutes", asked.mutes + 1))
        return press, asked

    def _at(self, part: str, along: int = 0) -> tuple[int, int]:
        x, y, width, height = self.RECT
        if part == "track":
            x0, x1 = bar_track_x(width)
            return x + (along or (x0 + x1) // 2), y + height - 4
        cx, cy = chip_xy(win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT)
        across = 4 if part == "speaker" else CHIP_W - 6
        return x + cx + across, y + cy + CHIP_H // 2

    def _squeeze(self, press, point):
        return press.press(*point, rect=self.RECT, duration_ms=self.DURATION_MS)

    def test_a_press_along_the_track_runs_the_clip_there(self):
        press, asked = self._press()

        assert self._squeeze(press, self._at("track")) is True
        assert asked.seeks[-1] == pytest.approx(self.DURATION_MS / 2, abs=200)

    def test_a_press_along_the_slider_sets_the_level(self):
        press, asked = self._press()

        assert self._squeeze(press, self._at("slider")) is True
        assert asked.levels == [100]

    def test_a_press_on_the_speaker_mutes(self):
        press, asked = self._press()

        assert self._squeeze(press, self._at("speaker")) is True
        assert asked.mutes == 1

    def test_a_press_beside_the_row_is_not_taken(self):
        press, asked = self._press()
        x, y, _width, _height = self.RECT

        assert self._squeeze(press, (x - 5, y + 2)) is False
        assert (asked.seeks, asked.levels, asked.mutes) == ([], [], 0)

    def test_a_row_the_panel_never_drew_takes_nothing(self):
        press, _asked = self._press()

        assert press.press(20, 50, rect=None, duration_ms=self.DURATION_MS) is False

    def test_a_drag_along_the_track_keeps_running_the_clip(self):
        press, asked = self._press()
        self._squeeze(press, self._at("track", along=bar_track_x(self.WIDTH)[0]))

        assert press.drag_to(*self._at("track"), rect=self.RECT,
                             duration_ms=self.DURATION_MS) is True
        assert asked.seeks[-1] == pytest.approx(self.DURATION_MS / 2, abs=200)

    def test_a_drag_across_the_speaker_does_not_flip_the_mute(self):
        """The mute is a press, so a pointer on its way along the slider must
        not toggle it as it passes."""
        press, asked = self._press()
        self._squeeze(press, self._at("slider"))

        press.drag_to(*self._at("speaker"), rect=self.RECT, duration_ms=self.DURATION_MS)

        assert asked.mutes == 0

    def test_a_drag_that_began_elsewhere_is_not_the_rows(self):
        press, asked = self._press()

        assert press.drag_to(*self._at("track"), rect=self.RECT,
                             duration_ms=self.DURATION_MS) is False
        assert asked.seeks == []

    def test_letting_go_ends_the_hold(self):
        press, _asked = self._press()
        self._squeeze(press, self._at("track"))
        assert press.holding is True

        press.release()

        assert press.holding is False


class TestAFlicksDial:
    """A flick's row carries a dial beside its track -- a clock hand going round
    once per loop of the clip -- where a video's row has none."""

    WIDTH = 400

    def _painted(self, row: RowHud):
        section = RowSection()
        width, height = section.size(self.WIDTH)
        panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        section.draw(panel, 0, 0, width, row)
        return np.asarray(panel), dial_xy(win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT)

    def test_a_flicks_row_draws_the_dial_beside_the_track(self):
        painted, (x, y) = self._painted(RowHud(position_ms=4_000, duration_ms=10_000, loop_turn=0.3))

        assert painted[y + DIAL_SIZE // 2, x + DIAL_SIZE // 2, 3] > 0

    def test_a_videos_row_has_no_dial(self):
        painted, (x, y) = self._painted(RowHud(position_ms=4_000, duration_ms=10_000))

        assert painted[y + DIAL_SIZE // 2, x + DIAL_SIZE // 2, 3] == 0

    def test_a_press_on_the_dial_is_on_the_dial_only_where_the_row_has_one(self):
        """A video's row keeps the spot as the track's own margin, pressed to
        the start of the track as it always was."""
        height = RowSection().size(self.WIDTH)[1]
        x, y = dial_xy(win_w=self.WIDTH, win_h=height, timeline_h=TIMELINE_HEIGHT)

        assert row_part(x + DIAL_SIZE // 2, y + DIAL_SIZE // 2, width=self.WIDTH, dial=True) == DIAL
        assert row_part(x + DIAL_SIZE // 2, y + DIAL_SIZE // 2, width=self.WIDTH) == SCRUBBER

    def test_a_press_round_the_dial_names_the_turn_under_it(self):
        height = RowSection().size(self.WIDTH)[1]
        x, y = dial_xy(win_w=self.WIDTH, win_h=height, timeline_h=TIMELINE_HEIGHT)
        cx, cy = x + DIAL_SIZE // 2, y + DIAL_SIZE // 2

        assert turn_to(cx, cy - 8, width=self.WIDTH) == pytest.approx(0.0, abs=0.02)
        assert turn_to(cx + 8, cy, width=self.WIDTH) == pytest.approx(0.25, abs=0.02)
        assert turn_to(cx - 8, cy, width=self.WIDTH) == pytest.approx(0.75, abs=0.02)

    def test_on_a_wide_row_the_readout_is_drawn_over_to_make_room_for_the_dial(self):
        section = RowSection()
        width, height = section.size(900)
        panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        playhead = PlayheadHud(text="0:04 / 0:10", widest="0:10 / 0:10")

        section.draw(panel, 0, 0, width, RowHud(position_ms=4_000, duration_ms=10_000,
                                                playhead=playhead, loop_turn=0.0))

        readout_w = PlayheadHudPainter().bgra(playhead).shape[1]
        x, y = readout_xy(readout_w, win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT,
                          dial=True)
        painted = np.asarray(panel)
        assert painted[y:y + CHIP_H, x:x + readout_w, 3].any()
        dx, dy = dial_xy(win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT)
        assert painted[dy + DIAL_SIZE // 2, dx + DIAL_SIZE // 2, 3] > 0
