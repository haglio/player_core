"""Where a press on a Funestra's window lands: the panel, or the picture under it.

The track, the time and the volume are a block of the panel, which places a
press on them itself (test_hud_overlay.py), so nothing over the picture takes
one any more.
"""
from __future__ import annotations

from pathlib import Path

from player_core.pointer import OMNIPAUSE_TOGGLE, Pointer

WIN_W, WIN_H = 640, 480
ON_THE_VIDEO = (300, 200)
LOWER_EDGE = (300, WIN_H - 4)


class _StubHud:
    """The lock HUD's half of the pointer's interface, and nothing else.

    *takes* is whether its slab is under the press — the real HUD answers that
    from the panel it last drew, which is a question about a bitmap's size.
    """

    def __init__(self, *, takes: bool = True) -> None:
        self._takes = takes
        self.presses: list[tuple[int, int]] = []
        self.motions: list[tuple[int, int]] = []
        self.drags: list[tuple[int, int]] = []
        self.holding = False

    def press(self, x: int, y: int) -> bool:
        self.presses.append((x, y))
        return self._takes

    def motion(self, x: int, y: int) -> None:
        self.motions.append((x, y))

    def drag_to(self, x: int, y: int) -> str:
        self.drags.append((x, y))
        return ""

    def release(self) -> None:
        self.holding = False


def _asks(tmp_path) -> Path:
    return tmp_path / "dashboard_cmd.txt"


def _asked(tmp_path) -> list[str]:
    path = _asks(tmp_path)
    return path.read_text(encoding="utf-8").split() if path.exists() else []


def _pointer(tmp_path, *, hud: bool = True,
             hud_takes: bool = True, in_a_session: bool = True):
    stub = _StubHud(takes=hud_takes) if hud else None
    return Pointer(hud=stub,
                   dashboard_cmd_file=_asks(tmp_path) if in_a_session else None), stub


def _press(pointer, point) -> None:
    pointer.press(*point, win_w=WIN_W, win_h=WIN_H)


def _motion(pointer, point, *, held: bool) -> None:
    pointer.motion(*point, held=held, win_w=WIN_W, win_h=WIN_H)


class TestThePicture:
    """A Funestra has no pause of its own to give — its paused state is the
    room's flag file, re-read every pass — so a press on the picture asks
    the session to pause or resume the whole room, and asks it off again."""

    def test_a_press_the_panel_refused_asks_the_room_to_pause(self, tmp_path):
        pointer, hud = _pointer(tmp_path, hud_takes=False)

        _press(pointer, ON_THE_VIDEO)

        assert hud.presses == [ON_THE_VIDEO]
        assert _asked(tmp_path) == [OMNIPAUSE_TOGGLE]

    def test_a_window_with_no_panel_asks_from_the_whole_picture(self, tmp_path):
        pointer, _hud = _pointer(tmp_path, hud=False)

        _press(pointer, ON_THE_VIDEO)

        assert _asked(tmp_path) == [OMNIPAUSE_TOGGLE]

    def test_a_press_the_panel_took_asks_for_nothing(self, tmp_path):
        pointer, _hud = _pointer(tmp_path)

        _press(pointer, ON_THE_VIDEO)

        assert _asked(tmp_path) == []

    def test_the_lower_edge_is_the_picture_now_that_no_row_is_drawn_there(self, tmp_path):
        """The track used to span it; a press there is a press on the picture."""
        pointer, _hud = _pointer(tmp_path, hud_takes=False)

        _press(pointer, LOWER_EDGE)

        assert _asked(tmp_path) == [OMNIPAUSE_TOGGLE]

    def test_a_window_with_no_session_to_ask_does_nothing(self, tmp_path):
        pointer, _hud = _pointer(tmp_path, hud_takes=False, in_a_session=False)

        _press(pointer, ON_THE_VIDEO)

        assert _asked(tmp_path) == []


class TestDragging:
    """Everything a held pointer can set is on the panel, so this is only about
    telling the panel where the pointer went and letting go of what it took."""

    def test_the_panel_is_told_where_the_pointer_went_either_way(self, tmp_path):
        pointer, hud = _pointer(tmp_path)

        _motion(pointer, ON_THE_VIDEO, held=False)
        _motion(pointer, LOWER_EDGE, held=True)

        assert hud.motions == [ON_THE_VIDEO, LOWER_EDGE]

    def test_what_the_panel_took_hold_of_keeps_the_drag(self, tmp_path):
        pointer, hud = _pointer(tmp_path)
        hud.holding = True

        _motion(pointer, LOWER_EDGE, held=True)

        assert hud.drags == [LOWER_EDGE]

    def test_the_button_coming_up_lets_go_of_what_it_took(self, tmp_path):
        pointer, hud = _pointer(tmp_path)
        hud.holding = True

        _motion(pointer, ON_THE_VIDEO, held=False)

        assert hud.holding is False

    def test_a_window_with_no_panel_has_nothing_to_tell(self, tmp_path):
        pointer, _hud = _pointer(tmp_path, hud=False)

        _motion(pointer, LOWER_EDGE, held=True)

        assert _asked(tmp_path) == []
