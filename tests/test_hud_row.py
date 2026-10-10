"""The scrubber, the volume chip, the playhead readout and a flick's dial, laid out on one line of a panel."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from funestra_core.hud_row import (
    DIAL,
    MUTE,
    PARTS_Y,
    READOUT,
    ROW_H,
    SCRUBBER,
    VOLUME,
    RowHud,
    RowPress,
    RowSection,
    row_layout,
    row_part,
    scrub_to,
    turn_to,
    volume_to,
)
from funestra_core.loop_dial import DIAL_SIZE
from funestra_core.playhead import PlayheadHud, readout_width, video_playhead
from funestra_core.timeline import (
    AMBER,
    BAR_INSET_X,
    HEATMAP_ALPHA,
    RED,
    TIMELINE_HEIGHT,
)
from funestra_core.volume import (
    CHIP_H,
    CHIP_W,
    MARGIN,
    MAX_VOLUME,
    MIN_VOLUME,
    PAD,
    SLOT_W,
    SPEAKER_W,
    VolumeHud,
    chip_xy,
)

WIDTH = 400
TIME = PlayheadHud(text="0:04 / 0:10", widest="0:10 / 0:10")
VIDEO = RowHud(position_ms=4_000, duration_ms=10_000, playhead=TIME, volume=VolumeHud(volume=50))
CLIP = RowHud(position_ms=4_000, duration_ms=10_000, playhead=TIME, loop_turn=0.3,
              volume=VolumeHud(volume=50))


def _layout(row: RowHud, width: int = WIDTH, at: tuple[int, int] = (0, 0)):
    return row_layout(row, rect=(*at, width, ROW_H))


class TestHowTheRowIsLaidOut:
    """One line, laid out from what is on it: the readout, a flick's dial, the
    track, and the chip at the right end."""

    def test_a_videos_row_is_its_readout_then_the_track_then_the_chip(self):
        layout = _layout(VIDEO)

        x, width = layout.readout
        assert (x, width) == (MARGIN, readout_width(TIME))
        assert layout.dial is None
        assert layout.track == (x + width + MARGIN, WIDTH - SLOT_W)

    def test_a_flicks_row_puts_its_dial_between_the_readout_and_the_track(self):
        layout = _layout(CLIP)

        x, width = layout.readout
        assert layout.dial == x + width + PAD
        assert layout.track[0] == layout.dial + DIAL_SIZE + MARGIN

    def test_a_row_with_nothing_before_its_track_starts_it_a_little_in(self):
        layout = _layout(RowHud(duration_ms=10_000))

        assert (layout.readout, layout.dial) == (None, None)
        assert layout.track == (BAR_INSET_X, WIDTH - SLOT_W)

    def test_a_longer_video_moves_the_track_along_rather_than_the_readout_over_it(self):
        short = _layout(RowHud(duration_ms=195_000, playhead=video_playhead(0, 195_000, 30)))
        long = _layout(RowHud(duration_ms=7_200_000,
                              playhead=video_playhead(0, 7_200_000, 60)))

        assert long.track[0] > short.track[0]
        assert long.readout[0] == short.readout[0] == MARGIN

    def test_it_is_one_line_however_narrow_the_panel(self):
        """The headset's console is 380 across; the row used to stack its
        readout on a line of its own there, and now fits beside the track."""
        layout = _layout(CLIP, width=380)

        assert layout.rect[3] == TIMELINE_HEIGHT
        assert layout.track[0] > layout.dial + DIAL_SIZE
        assert layout.track[1] - layout.track[0] >= 60

    def test_the_narrowest_panel_still_leaves_the_track_room_to_press(self):
        for row in (VIDEO, CLIP, RowHud(duration_ms=10_000)):
            layout = _layout(row, width=RowSection.least_width(row))
            assert layout.track[1] - layout.track[0] >= 60
        assert RowSection.least_width(CLIP) > RowSection.least_width(VIDEO)


def _painted(row: RowHud, *, width: int = WIDTH, at: tuple[int, int] = (0, 0), heatmap=None):
    layout = _layout(row, width=width, at=at)
    panel = Image.new("RGBA", (at[0] + width + 20, at[1] + ROW_H + 20), (0, 0, 0, 0))
    RowSection().draw(panel, layout, row, heatmap=heatmap)
    return np.asarray(panel), layout


def test_it_draws_everything_inside_the_room_it_was_laid_out_in():
    painted, layout = _painted(CLIP, at=(20, 20))

    inked = np.argwhere(painted[:, :, 3] > 0)
    assert inked.size
    assert inked[:, 0].min() >= 20 and inked[:, 0].max() < 20 + ROW_H
    assert inked[:, 1].min() >= 20 and inked[:, 1].max() < 20 + WIDTH


def test_it_draws_each_part_where_it_laid_it_out_and_nothing_between_them():
    painted, layout = _painted(CLIP)
    (readout_x, readout_w), dial_x, (track_x0, _x1) = layout.readout, layout.dial, layout.track
    middle = PARTS_Y + CHIP_H // 2

    assert painted[PARTS_Y:PARTS_Y + CHIP_H, readout_x:readout_x + readout_w, 3].any()
    assert painted[middle, dial_x + DIAL_SIZE // 2, 3] > 0
    assert painted[ROW_H // 2, track_x0 + 5, 3] > 0
    assert painted[middle, readout_x + readout_w + PAD // 2, 3] == 0
    assert painted[middle, dial_x + DIAL_SIZE + MARGIN // 2, 3] == 0


def test_a_host_with_a_funscript_fills_the_track_with_its_colors():
    row = RowHud(position_ms=0, duration_ms=60_000, playhead=TIME)
    x0, x1 = _layout(row).track
    colors = np.array([(200, 40 + x % 150, 30) for x in range(x1 - x0)], dtype=np.uint8)

    painted, _layout_ = _painted(row, heatmap=colors)

    middle = painted[ROW_H // 2]
    assert middle[x0 + 10:x1 - 10].tolist() == [
        [*color, HEATMAP_ALPHA] for color in colors[10:-10].tolist()]


def test_colors_measured_across_some_other_track_leave_it_plain():
    x0, x1 = _layout(VIDEO).track
    colors = np.array([(200, 40, 30)] * (x1 - x0 + 7), dtype=np.uint8)

    painted, _layout_ = _painted(VIDEO, heatmap=colors)

    assert painted[ROW_H // 2, x0 + 10, :3].tolist() != [200, 40, 30]


def _marks(painted, color) -> list[int]:
    """The middle of each mark the track carries in *color*, left to right."""
    pixels = painted[ROW_H // 2]
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
    row = RowHud(position_ms=0, duration_ms=60_000, loop_bounds=(15_000, 45_000))

    painted, layout = _painted(row)

    x0, x1 = layout.track
    assert _marks(painted, AMBER) == [
        pytest.approx(x0 + (x1 - x0) // 4, abs=3),
        pytest.approx(x0 + 3 * (x1 - x0) // 4, abs=3),
    ]


def test_a_loop_still_being_recorded_shows_its_in_point_in_red():
    painted, layout = _painted(RowHud(position_ms=0, duration_ms=60_000, record_in_ms=30_000))

    x0, x1 = layout.track
    assert _marks(painted, RED) == [pytest.approx(x0 + (x1 - x0) // 2, abs=3)]


class TestWhatAPressOnTheRowIsOn:
    """The row is pressed where it is drawn: a panel hands it the press in its
    own coordinates and it says which control was under it."""

    LAYOUT = _layout(VIDEO)

    def _part(self, px, py):
        return row_part(px, py, self.LAYOUT)

    def test_the_track_is_the_scrubber(self):
        assert self._part(sum(self.LAYOUT.track) // 2, ROW_H - 4) == SCRUBBER

    def test_the_speaker_mutes_and_the_slider_sets_the_level(self):
        chip_x, chip_y = chip_xy(win_w=WIDTH, win_h=ROW_H, timeline_h=ROW_H)

        assert self._part(chip_x + 4, chip_y + CHIP_H // 2) == MUTE
        assert self._part(chip_x + CHIP_W - 6, chip_y + CHIP_H // 2) == VOLUME

    def test_left_of_the_track_is_the_readout(self):
        """Saturated like a margin, a press on the time would throw the clip
        back to its start, so it is its own part and does nothing."""
        assert self._part(self.LAYOUT.track[0] - 1, ROW_H // 2) == READOUT
        assert self._part(self.LAYOUT.readout[0] + 3, ROW_H // 2) == READOUT

    def test_above_or_under_the_row_is_on_nothing(self):
        assert self._part(WIDTH // 2, -1) == ""
        assert self._part(WIDTH // 2, ROW_H) == ""

    def test_a_press_along_the_track_names_the_time_under_it(self):
        x0, x1 = self.LAYOUT.track

        assert scrub_to(x0, self.LAYOUT, duration_ms=60_000) == 0
        assert scrub_to(x1, self.LAYOUT, duration_ms=60_000) == 60_000
        assert 29_000 < scrub_to((x0 + x1) // 2, self.LAYOUT, duration_ms=60_000) < 31_000

    def test_a_press_along_the_slider_names_the_level_under_it(self):
        chip_x, chip_y = chip_xy(win_w=WIDTH, win_h=ROW_H, timeline_h=ROW_H)

        assert volume_to(chip_x + SPEAKER_W, chip_y, self.LAYOUT) == MIN_VOLUME
        assert volume_to(chip_x + CHIP_W, chip_y, self.LAYOUT) == MAX_VOLUME


class TestWhatAPressOnTheRowAsksFor:
    """One placement for every panel that hosts the row, so the track, the
    slider and the speaker answer the same way wherever the row is drawn."""

    LAYOUT = _layout(VIDEO, at=(10, 40))
    DURATION_MS = 10_000.0

    def _press(self):
        asked = SimpleNamespace(seeks=[], levels=[], mutes=0)
        press = RowPress(seek=asked.seeks.append, set_volume=asked.levels.append,
                         toggle_mute=lambda: setattr(asked, "mutes", asked.mutes + 1))
        return press, asked

    def _at(self, part: str, along: int = 0) -> tuple[int, int]:
        x, y, width, height = self.LAYOUT.rect
        if part == "track":
            x0, x1 = self.LAYOUT.track
            return x + (along or (x0 + x1) // 2), y + height - 4
        cx, cy = chip_xy(win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT)
        across = 4 if part == "speaker" else CHIP_W - 6
        return x + cx + across, y + cy + CHIP_H // 2

    def _squeeze(self, press, point):
        return press.press(*point, layout=self.LAYOUT, duration_ms=self.DURATION_MS)

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
        x, y, _width, _height = self.LAYOUT.rect

        assert self._squeeze(press, (x - 5, y + 2)) is False
        assert (asked.seeks, asked.levels, asked.mutes) == ([], [], 0)

    def test_a_row_the_panel_never_drew_takes_nothing(self):
        press, _asked = self._press()

        assert press.press(20, 50, layout=None, duration_ms=self.DURATION_MS) is False

    def test_a_drag_along_the_track_keeps_running_the_clip(self):
        press, asked = self._press()
        self._squeeze(press, self._at("track", along=self.LAYOUT.track[0]))

        assert press.drag_to(*self._at("track"), layout=self.LAYOUT,
                             duration_ms=self.DURATION_MS) is True
        assert asked.seeks[-1] == pytest.approx(self.DURATION_MS / 2, abs=200)

    def test_a_drag_across_the_speaker_does_not_flip_the_mute(self):
        """The mute is a press, so a pointer on its way along the slider must
        not toggle it as it passes."""
        press, asked = self._press()
        self._squeeze(press, self._at("slider"))

        press.drag_to(*self._at("speaker"), layout=self.LAYOUT, duration_ms=self.DURATION_MS)

        assert asked.mutes == 0

    def test_a_drag_that_began_elsewhere_is_not_the_rows(self):
        press, asked = self._press()

        assert press.drag_to(*self._at("track"), layout=self.LAYOUT,
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

    def _dial_center(self, layout) -> tuple[int, int]:
        return layout.dial + DIAL_SIZE // 2, PARTS_Y + DIAL_SIZE // 2

    def test_a_flicks_row_draws_the_dial_beside_the_track(self):
        painted, layout = _painted(CLIP)
        cx, cy = self._dial_center(layout)

        assert painted[cy, cx, 3] > 0

    def test_a_videos_row_has_no_dial_and_runs_its_track_where_one_would_be(self):
        layout = _layout(VIDEO)
        cx, cy = self._dial_center(_layout(CLIP))

        assert layout.dial is None
        assert row_part(cx, cy, layout) == SCRUBBER

    def test_a_press_on_the_dial_is_on_the_dial_only_where_the_row_has_one(self):
        clip, video = _layout(CLIP), _layout(VIDEO)
        cx, cy = self._dial_center(clip)

        assert row_part(cx, cy, clip) == DIAL
        assert row_part(cx, cy, video) != DIAL

    def test_a_press_round_the_dial_names_the_turn_under_it(self):
        layout = _layout(CLIP)
        cx, cy = self._dial_center(layout)

        assert turn_to(cx, cy - 8, layout) == pytest.approx(0.0, abs=0.02)
        assert turn_to(cx + 8, cy, layout) == pytest.approx(0.25, abs=0.02)
        assert turn_to(cx - 8, cy, layout) == pytest.approx(0.75, abs=0.02)

    def test_a_press_on_the_dial_turns_the_loop_and_a_drag_keeps_turning_it(self):
        layout = _layout(CLIP, at=(10, 40))
        cx, cy = self._dial_center(layout)
        turns: list[float] = []
        press = RowPress(seek_loop=turns.append)

        assert press.press(10 + cx + 8, 40 + cy, layout=layout, duration_ms=10_000.0) is True
        assert press.drag_to(10 + cx, 40 + cy + 8, layout=layout, duration_ms=10_000.0) is True

        assert turns == [pytest.approx(0.25, abs=0.03), pytest.approx(0.5, abs=0.03)]
