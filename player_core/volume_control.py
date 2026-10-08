"""A Funestra's volume chip: its own level and mute, or the room's.

A Funestra whose sound is its own sets mpv's level and mute from the chip it
draws.  One whose sound is the room's -- the Main Funestra, whose mpv is one of
two sinks the room drives -- shows the level the room publishes and asks the
room for a new one; the ask shows at once so the slider does not trail the
pointer, and the room's answer overwrites it either way.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .dashboard import ask
from .volume import (
    MAX_VOLUME,
    MIN_VOLUME,
    VolumeHud,
    chip_local,
    hit_part,
    volume_at,
)

__all__ = [
    "VolumeControl",
]


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


class RoomVolume:
    def __init__(self, player, *, dashboard_cmd_file: Path | None, live: bool) -> None:
        self._player = player
        self._dashboard_cmd_file = dashboard_cmd_file
        self._hud = VolumeHud()
        if live:
            player.set_muted(False)

    @property
    def hud(self) -> VolumeHud:
        return self._hud

    def set(self, level: int, muted: bool) -> None:
        level = max(MIN_VOLUME, min(MAX_VOLUME, level))
        self._hud = VolumeHud(volume=level, muted=muted)
        self._player.set_volume(0 if muted else level)

    def press_at(self, mx: int, my: int, *,
                 win_w: int, win_h: int, timeline_h: int) -> bool:
        return self._press(*chip_local(mx, my, win_w=win_w, win_h=win_h,
                                       timeline_h=timeline_h))

    def drag_at(self, mx: int, my: int, *,
                win_w: int, win_h: int, timeline_h: int) -> None:
        cx, cy = chip_local(mx, my, win_w=win_w, win_h=win_h, timeline_h=timeline_h)
        if hit_part(cx, cy) == "track":
            self._press(cx, cy)

    def _press(self, cx: int, cy: int) -> bool:
        part = hit_part(cx, cy)
        if part == "mute":
            self._hud = replace(self._hud, muted=not self._hud.muted)
            ask(self._dashboard_cmd_file, "audio_unmute" if not self._hud.muted else "audio_mute")
        elif part == "track":
            level = volume_at(cx)
            self._hud = VolumeHud(volume=level, muted=False)
            ask(self._dashboard_cmd_file, f"audio_set_volume|{level}")
        return bool(part)
