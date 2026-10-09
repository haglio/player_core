from __future__ import annotations

from funestra_fakes import FakePlayer

from player_core.hud_corners import (
    CORNER_PLUS_OVERLAY_ID,
    HudCorners,
    HudPlace,
    plus_button,
)
from player_core.hud_placement import HudCorner

WINDOW = (1200, 800)
LOWER_RIGHT = (WINDOW[0] - 3, WINDOW[1] - 3)


class _Panel:
    def __init__(self, *, corner: HudCorner = HudCorner.UPPER_LEFT,
                 covering: tuple[int, int, int, int] = (0, 0, 0, 0)) -> None:
        self.hud_place = HudPlace("portrait", corner, 12)
        self._covering = covering

    def covers(self, x: int, y: int) -> bool:
        left, top, width, height = self._covering
        return left <= x < left + width and top <= y < top + height


def _corners(panel: _Panel | None = None,
             asked: list[str] | None = None) -> tuple[HudCorners, FakePlayer]:
    player = FakePlayer()
    post = (asked if asked is not None else []).append
    return HudCorners(panel or _Panel(), player, post=post), player


def _pointed_at(corners: HudCorners, point: tuple[int, int]) -> None:
    corners.motion(*point)
    corners.paint(window=WINDOW)


class TestThePlus:
    def test_the_pointer_over_the_panel_puts_no_plus_under_it(self):
        corners, player = _corners(_Panel(covering=(0, 0, *WINDOW)))

        _pointed_at(corners, LOWER_RIGHT)

        assert CORNER_PLUS_OVERLAY_ID not in player.overlays


class TestAPress:
    def test_in_a_corner_the_hud_is_not_in_asks_for_the_hud_there(self):
        asked: list[str] = []
        corners, _player = _corners(asked=asked)
        corners.paint(window=WINDOW)

        taken = corners.press(*LOWER_RIGHT)

        assert (taken, asked) == (True, ["portrait_hud_restore_at|lower_right"])

    def test_in_the_huds_own_corner_is_left_to_the_picture(self):
        asked: list[str] = []
        corners, _player = _corners(_Panel(corner=HudCorner.LOWER_RIGHT), asked)
        corners.paint(window=WINDOW)

        assert (corners.press(*LOWER_RIGHT), asked) == (False, [])

    def test_over_the_panel_is_left_to_the_panel(self):
        asked: list[str] = []
        corners, _player = _corners(_Panel(covering=(0, 0, *WINDOW)), asked)
        corners.paint(window=WINDOW)

        assert (corners.press(*LOWER_RIGHT), asked) == (False, [])


class TestWhatThePlusSays:
    def test_beside_an_open_hud_it_moves_the_hud_there(self):
        button = plus_button("portrait", HudCorner.LOWER_RIGHT, minimized=False)

        assert button.tooltip == "Move this HUD here"

    def test_beside_a_minimized_hud_it_shows_the_hud_there(self):
        button = plus_button("portrait", HudCorner.LOWER_RIGHT, minimized=True)

        assert button.tooltip == "Show this HUD here"

    def test_a_press_on_it_asks_for_the_hud_at_the_place_it_names(self):
        assert plus_button("landscape", "left", minimized=False).command == (
            "landscape_hud_restore_at|left")
