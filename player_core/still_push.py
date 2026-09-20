"""The slow creep into a still while it holds the screen.

Package-internal: the players reach it through the one that owns it
(:class:`player_core.mpv_player._MpvControl`), which is where the picture, the
pace and the pause already are.
"""
from __future__ import annotations

__all__: list[str] = []

# How much closer the picture is by the time its hold runs out.
ZOOM_SPAN = 1.10


class StillPush:
    """Where the creep into the picture on screen has got to."""

    def __init__(self, span: float = ZOOM_SPAN) -> None:
        self._span = span
        self._pace_s = 0.0
        self._started_s = 0.0
        self._held_at_s: float | None = None

    def set_pace(self, seconds: float, now_s: float) -> None:
        """Hold each picture *seconds* long from here on, without jumping the
        one on screen: a show slowing down slows the creep rather than cropping
        harder, so where this picture had got to is where it carries on from."""
        reached = self._progress(now_s)
        self._pace_s = seconds
        self._started_s = self._clock(now_s) - reached * seconds

    def restart(self, now_s: float) -> None:
        self._started_s = now_s

    def set_paused(self, paused: bool, now_s: float) -> None:
        if paused:
            self._held_at_s = now_s
        elif self._held_at_s is not None:
            self._started_s += now_s - self._held_at_s
            self._held_at_s = None

    def zoom(self, now_s: float) -> float:
        """How much bigger than its fitted size the picture is drawn now."""
        return 1.0 + (self._span - 1.0) * self._progress(now_s)

    def _clock(self, now_s: float) -> float:
        """The moment the creep is reading, which a freeze stops."""
        return now_s if self._held_at_s is None else self._held_at_s

    def _progress(self, now_s: float) -> float:
        if not self._pace_s:
            return 0.0
        return ((self._clock(now_s) - self._started_s) / self._pace_s) % 1.0
