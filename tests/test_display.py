"""The black a Funestra puts up when the room gives its rectangle to another window."""
from __future__ import annotations

import numpy as np

from player_core.display import BLACK_OVERLAY_ID, Display, black_bgra


class SpyPlayer:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.up: dict[int, np.ndarray] = {}

    def overlay(self, ident: int, x: int, y: int, bgra) -> None:
        self.calls.append(("overlay", ident, x, y, bgra.shape))
        self.up[ident] = bgra

    def remove_overlay(self, ident: int) -> None:
        self.calls.append(("remove", ident))
        self.up.pop(ident, None)


HUD_IDS = (8, 10, 12)


def _display() -> tuple[Display, SpyPlayer]:
    player = SpyPlayer()
    return Display(player, HUD_IDS), player


class TestBlackBgra:
    def test_is_opaque_black_at_the_asked_size(self):
        frame = black_bgra(320, 240)

        assert frame.shape == (240, 320, 4)
        assert frame.dtype == np.uint8
        assert not frame[:, :, :3].any()
        assert (frame[:, :, 3] == 255).all()

    def test_a_degenerate_size_still_makes_a_block(self):
        assert black_bgra(0, 0).shape == (1, 1, 4)


class TestDisplay:
    def test_starts_on_so_a_funestra_nobody_tells_paints(self):
        display, player = _display()

        display.sync(800, 600)

        assert display.active
        assert player.calls == []

    def test_off_covers_the_window_and_takes_the_hud_down(self):
        display, player = _display()

        display.set_active(False)
        display.sync(800, 600)

        assert player.calls[:len(HUD_IDS)] == [("remove", ident) for ident in HUD_IDS]
        assert list(player.up) == [BLACK_OVERLAY_ID]
        assert player.up[BLACK_OVERLAY_ID].shape == (600, 800, 4)

    def test_the_black_is_above_every_id_it_takes_down(self):
        assert max(HUD_IDS) < BLACK_OVERLAY_ID

    def test_the_black_covers_the_whole_window(self):
        display, player = _display()

        display.set_active(False)
        display.sync(1280, 720)

        _call, _ident, x, y, shape = player.calls[-1]
        assert (x, y) == (0, 0)
        assert shape == (720, 1280, 4)

    def test_staying_off_repaints_nothing(self):
        display, player = _display()
        display.set_active(False)
        display.sync(800, 600)
        player.calls.clear()

        for _ in range(3):
            display.sync(800, 600)

        assert player.calls == []

    def test_a_resize_while_off_repaints_the_black_to_fit(self):
        display, player = _display()
        display.set_active(False)
        display.sync(800, 600)
        player.calls.clear()

        display.sync(1024, 768)

        assert player.up[BLACK_OVERLAY_ID].shape == (768, 1024, 4)

    def test_coming_back_on_takes_the_black_down(self):
        display, player = _display()
        display.set_active(False)
        display.sync(800, 600)
        player.calls.clear()

        display.set_active(True)
        display.sync(800, 600)

        assert player.calls == [("remove", BLACK_OVERLAY_ID)]
        assert player.up == {}

    def test_staying_on_removes_nothing(self):
        display, player = _display()

        for _ in range(3):
            display.sync(800, 600)

        assert player.calls == []
