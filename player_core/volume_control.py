"""A Funestra's own volume chip: what it shows, and the mpv level and mute a press on it sets."""
from __future__ import annotations

from dataclasses import replace

from .volume import (
    MAX_VOLUME,
    MIN_VOLUME,
    VolumeHud,
    chip_local,
    hit_part,
    volume_at,
)

__all__: list[str] = []


class VolumeControl:
    def __init__(self, player, *, live: bool = True) -> None:
        self._player = player
        self._live = live
        self._hud = VolumeHud(volume=MAX_VOLUME if live else MIN_VOLUME, muted=True)

    @property
    def hud(self) -> VolumeHud:
        return self._hud

    def press_at(self, mx: int, my: int, *,
                 win_w: int, win_h: int, timeline_h: int) -> bool:
        cx, cy = chip_local(mx, my, win_w=win_w, win_h=win_h, timeline_h=timeline_h)
        part = hit_part(cx, cy)
        if part and self._live:
            self._apply(part, cx)
        return bool(part)

    def drag_at(self, mx: int, my: int, *,
                win_w: int, win_h: int, timeline_h: int) -> None:
        cx, cy = chip_local(mx, my, win_w=win_w, win_h=win_h, timeline_h=timeline_h)
        if self._live and hit_part(cx, cy) == "track":
            self._apply("track", cx)

    def toggle_mute(self) -> None:
        if self._live:
            self._set(replace(self._hud, muted=not self._hud.muted))

    def set_level(self, volume: int) -> None:
        if self._live:
            self._set(VolumeHud(volume=volume, muted=False))

    def _apply(self, part: str, cx: int) -> None:
        if part == "mute":
            self.toggle_mute()
        else:
            self.set_level(volume_at(cx))

    def _set(self, hud: VolumeHud) -> None:
        self._hud = hud
        self._player.set_volume(hud.volume)
        self._player.set_muted(hud.muted)
