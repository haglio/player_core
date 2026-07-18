"""The file channel an orchestrator drives a player through.

Every player in this family is a separate process that Fun Time steers without
a socket: it appends verbs to a *command file* the player drains each tick, and
owns pause through a *flag file* the player simply obeys.  Reading is
best-effort by design — a missing file, a half-written one, or one being
replaced mid-read must never raise into a player's run loop, because the next
tick is milliseconds away and will see the settled value.

Pause rides its own file rather than the command channel so that being paused is
a *state* the player converges on, not an event it can miss: a player that
starts late, restarts, or drops a verb still reads the flag and lands correctly.
"""
from __future__ import annotations

import logging
from pathlib import Path


def consume_command_file(
    path: Path, *, logger: logging.Logger | None = None, uppercase: bool = True
) -> list[str]:
    """Take every queued command line, emptying the file so none replays.

    *uppercase* folds the whole payload, which suits a player whose verbs carry
    no arguments.  A player whose commands take a case-sensitive argument (a
    path) passes ``uppercase=False`` and folds just the keyword itself.
    """
    try:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8").replace("﻿", "").strip()
        if uppercase:
            text = text.upper()
        if not text:
            return []
        path.write_text("", encoding="utf-8")
        return [line.strip() for line in text.splitlines() if line.strip()]
    except Exception:
        if logger is not None:
            logger.exception("Failed to consume command file %s", path)
        return []


def read_paused_state(path: Path, *, logger: logging.Logger | None = None) -> bool:
    """Whether the orchestrator has the player paused; no file means running."""
    try:
        if not path.exists():
            return False
        return path.read_text(encoding="utf-8").replace("﻿", "").strip() == "1"
    except Exception:
        if logger is not None:
            logger.exception("Failed to read paused state file %s", path)
        return False
