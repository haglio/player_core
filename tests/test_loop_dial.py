"""The dial beside a flick's track: a clock hand going round once per loop."""
from __future__ import annotations

import pytest

from player_core.loop_dial import DIAL_SIZE, LoopDialPainter, dial_xy, on_dial, turn_at
from player_core.playhead import lower_edge_height, readout_xy
from player_core.timeline import TIMELINE_HEIGHT, bar_track_x
from player_core.volume import MARGIN

NARROW = 380   # the readout takes a line of its own above the track
WIDE = 900     # the readout shares the track's row


def _row(width: int) -> dict:
    return {"win_w": width, "win_h": lower_edge_height(width, timeline_h=TIMELINE_HEIGHT),
            "timeline_h": TIMELINE_HEIGHT}


class TestWhereTheDialSits:
    def test_it_sits_against_the_start_of_the_track_on_the_tracks_own_row(self):
        x, y = dial_xy(**_row(NARROW))
        row_top = _row(NARROW)["win_h"] - TIMELINE_HEIGHT

        assert x + DIAL_SIZE + MARGIN == bar_track_x(NARROW)[0]
        assert row_top <= y and y + DIAL_SIZE <= row_top + TIMELINE_HEIGHT

    def test_on_a_wide_row_the_readout_moves_over_to_make_room_for_it(self):
        x, _y = dial_xy(**_row(WIDE))
        readout_w = 80

        assert x + DIAL_SIZE + MARGIN == bar_track_x(WIDE)[0]
        assert readout_xy(readout_w, **_row(WIDE), dial=True)[0] + readout_w + MARGIN == x
        assert readout_xy(readout_w, **_row(WIDE))[0] + readout_w + MARGIN == bar_track_x(WIDE)[0]


class TestAPressOnTheDial:
    def _center(self, width: int) -> tuple[int, int]:
        x, y = dial_xy(**_row(width))
        return x + DIAL_SIZE // 2, y + DIAL_SIZE // 2

    def test_inside_the_dial_is_on_it_and_beside_it_is_not(self):
        cx, cy = self._center(NARROW)

        assert on_dial(cx, cy, **_row(NARROW))
        assert on_dial(cx + DIAL_SIZE // 2 - 1, cy, **_row(NARROW))
        assert not on_dial(cx + DIAL_SIZE, cy, **_row(NARROW))
        assert not on_dial(cx, cy - DIAL_SIZE, **_row(NARROW))

    def test_twelve_o_clock_is_the_start_of_the_turn_and_the_hand_goes_clockwise(self):
        cx, cy = self._center(NARROW)

        assert turn_at(cx, cy - 8, **_row(NARROW)) == pytest.approx(0.0, abs=0.02)
        assert turn_at(cx + 8, cy, **_row(NARROW)) == pytest.approx(0.25, abs=0.02)
        assert turn_at(cx, cy + 8, **_row(NARROW)) == pytest.approx(0.5, abs=0.02)
        assert turn_at(cx - 8, cy, **_row(NARROW)) == pytest.approx(0.75, abs=0.02)


class TestHowItIsDrawn:
    def _brightness(self, turn: float):
        bgra = LoopDialPainter().bgra(LoopDialPainter.hand(turn))
        assert bgra.shape == (DIAL_SIZE, DIAL_SIZE, 4)
        return bgra[:, :, :3].astype(int).sum(axis=2)  # row by column

    def test_the_hand_points_up_at_the_start_of_the_turn(self):
        ink = self._brightness(0.0)
        c = DIAL_SIZE // 2

        assert ink[c - 6, c] > ink[c + 6, c] + 150
        assert ink[c - 6, c] > ink[c, c + 6] + 150

    def test_and_a_quarter_turn_on_it_points_right(self):
        ink = self._brightness(0.25)
        c = DIAL_SIZE // 2

        assert ink[c, c + 6] > ink[c, c - 6] + 150
        assert ink[c, c + 6] > ink[c + 6, c] + 150

    def test_it_is_a_disc_that_leaves_its_corners_clear(self):
        alpha = LoopDialPainter().bgra(LoopDialPainter.hand(0.0))[:, :, 3]

        assert alpha[0, 0] == 0 and alpha[DIAL_SIZE - 1, DIAL_SIZE - 1] == 0
        assert alpha[DIAL_SIZE // 2, DIAL_SIZE // 2] > 0

    def test_it_is_repainted_only_when_the_hand_moves_a_step(self):
        assert LoopDialPainter.hand(0.0) == LoopDialPainter.hand(0.001)
        assert LoopDialPainter.hand(0.0) != LoopDialPainter.hand(0.25)
        assert LoopDialPainter.hand(1.0) == LoopDialPainter.hand(0.0)
