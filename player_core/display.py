"""Whether a Funestra's window paints, and the black it shows when it does not.

Told DISPLAY_OFF, a Funestra that shares its rectangle with another window
covers its picture with an opaque black and takes its own overlays down, so a
switch back to it lands on black rather than on the frame it was paused on.
mpv owns the window's pixels, so the black rides the overlay channel the HUD
already does, above every id the Funestra draws with.
"""
from __future__ import annotations

import numpy as np

__all__ = []

BLACK_OVERLAY_ID = 20


def black_bgra(width: int, height: int) -> np.ndarray:
    frame = np.zeros((max(1, height), max(1, width), 4), dtype=np.uint8)
    frame[:, :, 3] = 255
    return frame


class Display:
    def __init__(self, player, hud_ids) -> None:
        self._player = player
        self._hud_ids = tuple(hud_ids)
        self._active = True
        self._blanked_at: tuple[int, int] | None = None

    @property
    def active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active

    def sync(self, width: int, height: int) -> None:
        if self._active:
            self._clear()
        else:
            self._blank(width, height)

    def _blank(self, width: int, height: int) -> None:
        if self._blanked_at == (width, height):
            return
        for ident in self._hud_ids:
            self._player.remove_overlay(ident)
        self._player.overlay(BLACK_OVERLAY_ID, 0, 0, black_bgra(width, height))
        self._blanked_at = (width, height)

    def _clear(self) -> None:
        if self._blanked_at is None:
            return
        self._player.remove_overlay(BLACK_OVERLAY_ID)
        self._blanked_at = None
