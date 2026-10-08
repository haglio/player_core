"""What the mouse does to a Funestra's window: the chip, the readout, the scrubber, the HUD, or the picture.

Topmost first, the order mpv composites the overlays in.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .file_channel import append_command
from .playhead import on_readout
from .timeline import TIMELINE_HEIGHT, bar_track_x

__all__: list[str] = []

logger = logging.getLogger(__name__)

OMNIPAUSE_TOGGLE = "omnipause_toggle"


def time_at(mx: int, *, win_w: int, duration_ms: float) -> float:
    x0, x1 = bar_track_x(win_w)
    fraction = min(1.0, max(0.0, (mx - x0) / max(1, x1 - x0)))
    return fraction * duration_ms


def ask_for_omnipause(dashboard_cmd_file: Path | None) -> None:
    if dashboard_cmd_file is None:
        return
    if not append_command(Path(dashboard_cmd_file), OMNIPAUSE_TOGGLE):
        logger.warning("Dropped the omnipause ask (command file locked)")


class Pointer:
    def __init__(self, *, playback, volume, hud=None,
                 dashboard_cmd_file: Path | None = None) -> None:
        self._playback = playback
        self._volume = volume
        self._hud = hud
        self._dashboard_cmd_file = dashboard_cmd_file

    def press(self, mx: int, my: int, *, win_w: int, win_h: int) -> None:
        if self._volume.press_at(mx, my, win_w=win_w, win_h=win_h,
                                 timeline_h=TIMELINE_HEIGHT):
            return
        if on_readout(mx, my, win_w=win_w, win_h=win_h, timeline_h=TIMELINE_HEIGHT):
            return
        if my >= win_h - TIMELINE_HEIGHT and not self._playback.showing_picture:
            self._playback.seek_to(
                time_at(mx, win_w=win_w, duration_ms=self._playback.duration_ms))
            return
        if self._hud is not None and self._hud.press(mx, my):
            return
        ask_for_omnipause(self._dashboard_cmd_file)

    def motion(self, mx: int, my: int, *, held: bool,
               win_w: int, win_h: int) -> None:
        if self._hud is not None:
            self._hud.motion(mx, my)
            if not held:
                self._hud.release()
            elif self._hud.holding:
                self._hud.drag_to(mx, my)
                return
        if held:
            self._volume.drag_at(mx, my, win_w=win_w, win_h=win_h,
                                 timeline_h=TIMELINE_HEIGHT)
