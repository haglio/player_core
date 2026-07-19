"""The status file a player publishes for its orchestrator to read.

The reverse leg of :mod:`player_core.file_channel`: commands and the paused flag
go in, this comes back out.  Fun Time polls it to know what each player is
showing — the current clip, the playhead, and whatever else that player's
features need — which is what the retired VLC players needed an HTTP
``status.xml`` poll for.

Writes are throttled because the playhead changes every tick, while a poller
only ever samples a few times a second.

*What* to publish is the player's business and differs per player, so it arrives
as a ``fields`` callable; *how* to publish it — the throttle, the directory, and
surviving a locked or vanished file — is identical everywhere and lives here.
Each player therefore controls its own key order and format, and two players'
status files can never drift apart in their write mechanics.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Mapping

from .file_channel import publish_whole


class StatusWriter:
    def __init__(
        self,
        path: Path,
        fields: Callable[[object], Mapping[str, str]],
        *,
        min_interval: float = 0.2,
        now_source=time.monotonic,
    ) -> None:
        self._path = path
        self._fields = fields
        self._min_interval = min_interval
        self._now = now_source
        self._last_write: float | None = None

    def write(self, session) -> bool:
        """Publish *session*'s status, unless the last write was too recent.

        Returns whether anything reached disk, so a caller can tell a throttled
        tick from a failed one.
        """
        now = self._now()
        if self._last_write is not None and now - self._last_write < self._min_interval:
            return False
        text = "".join(f"{key}={value}\n" for key, value in self._fields(session).items())
        # Published whole rather than truncated in place: the orchestrator polls
        # this file, and a poller that caught a truncating write would read no
        # clip at all — which it cannot tell from a player that has none.
        if not publish_whole(self._path, text):
            return False
        self._last_write = now
        return True
