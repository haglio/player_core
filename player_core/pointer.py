"""What the mouse does to a Funestra's window: the chip, the readout, the scrubber, the panel, or the picture.

Topmost first, the order mpv composites the overlays in.
"""
from __future__ import annotations

from pathlib import Path

from .dashboard import ask
from .playhead import on_readout
from .scrubber import HeatmapStrip, timeline_height
from .timeline import TIMELINE_HEIGHT, bar_track_x

__all__ = [
    "OMNIPAUSE_TOGGLE",
    "time_at",
]

OMNIPAUSE_TOGGLE = "omnipause_toggle"


def time_at(mx: int, *, win_w: int, duration_ms: float,
            window: tuple[float, float] | None = None) -> float:
    start_ms, end_ms = window or (0.0, duration_ms)
    if end_ms <= start_ms:
        end_ms = start_ms + duration_ms
    x0, x1 = bar_track_x(win_w)
    fraction = min(1.0, max(0.0, (mx - x0) / max(1, x1 - x0)))
    return start_ms + fraction * (end_ms - start_ms)


class Pointer:
    def __init__(self, *, playback, volume, hud=None, strip: HeatmapStrip | None = None,
                 dashboard_cmd_file: Path | None = None) -> None:
        self._playback = playback
        self._volume = volume
        self._hud = hud
        self._strip = strip
        self._dashboard_cmd_file = dashboard_cmd_file

    def press(self, mx: int, my: int, *, win_w: int, win_h: int) -> None:
        row_h = self._row_height()
        if self._volume.press_at(mx, my, win_w=win_w, win_h=win_h, timeline_h=row_h):
            return
        if on_readout(mx, my, win_w=win_w, win_h=win_h, timeline_h=row_h):
            return
        if my >= win_h - row_h and not self._playback.showing_picture:
            self._playback.seek_to(time_at(
                mx, win_w=win_w, duration_ms=self._playback.duration_ms,
                window=None if self._strip is None else self._strip.window))
            return
        if self._hud is not None and self._hud.press(mx, my):
            return
        ask(self._dashboard_cmd_file, OMNIPAUSE_TOGGLE)

    def release(self) -> None:
        if self._hud is not None:
            self._hud.release()

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
                                 timeline_h=self._row_height())

    def _row_height(self) -> int:
        return TIMELINE_HEIGHT if self._strip is None else timeline_height(self._strip)
