"""What the mouse does to a Funestra's window: the panel, or the picture.

The track, the time and the volume are a block of the panel now
(:mod:`player_core.hud_row`), and the panel places a press on them itself, so
what is left here is the panel first and the picture under it.
"""
from __future__ import annotations

from pathlib import Path

from .dashboard import ask
from .timeline import bar_track_x

__all__ = [
    "OMNIPAUSE_TOGGLE",
    "time_at",
]

OMNIPAUSE_TOGGLE = "omnipause_toggle"


def time_at(mx: int, *, win_w: int, duration_ms: float,
            window: tuple[float, float] | None = None) -> float:
    """The time a press *mx* across a track *win_w* wide names.  The headset
    places a squeeze on the row under its console with it."""
    start_ms, end_ms = window or (0.0, duration_ms)
    if end_ms <= start_ms:
        end_ms = start_ms + duration_ms
    x0, x1 = bar_track_x(win_w)
    fraction = min(1.0, max(0.0, (mx - x0) / max(1, x1 - x0)))
    return start_ms + fraction * (end_ms - start_ms)


class Pointer:
    def __init__(self, *, hud=None, dashboard_cmd_file: Path | None = None) -> None:
        self._hud = hud
        self._dashboard_cmd_file = dashboard_cmd_file

    def press(self, mx: int, my: int, *, win_w: int, win_h: int) -> None:
        """The panel takes what is on it -- its buttons and the clip's row --
        and a press anywhere else is a press on the picture, which asks the
        session to pause everything."""
        if self._hud is not None and self._hud.press(mx, my):
            return
        ask(self._dashboard_cmd_file, OMNIPAUSE_TOGGLE)

    def release(self) -> None:
        if self._hud is not None:
            self._hud.release()

    def motion(self, mx: int, my: int, *, held: bool, win_w: int, win_h: int) -> None:
        if self._hud is None:
            return
        self._hud.motion(mx, my)
        if not held:
            self._hud.release()
        elif self._hud.holding:
            self._hud.drag_to(mx, my)
