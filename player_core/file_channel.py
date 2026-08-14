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

The other direction of that best-effort contract is :func:`publish_whole`: a
file one side polls has to be written aside and renamed over, never truncated in
place, or the poller reads a blank and cannot tell it from an empty state.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path


def publish_whole(
    path: Path, text: str, *, attempts: int = 5, delay_s: float = 0.005,
) -> bool:
    """Write *text* to *path* so a concurrent poller reads all of it or none.

    The reader polls several times a second while the writer republishes several
    times a second, so an ordinary truncate-and-write leaves a window in which
    the file is empty — and a poller cannot tell "I caught it mid-write" from
    "there is nothing here", so it acts on the blank.  Writing a sibling temp
    file and renaming it over closes that window.

    The rename itself is retried: Windows refuses to replace a file another
    process holds open, so a publish landing inside one of those reads fails
    with a sharing violation.  Retrying turns that into a sub-millisecond wait;
    a file locked for longer reports False, leaving the previous whole record in
    place for the next tick to replace — never a half-published one.
    """
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(text, encoding="utf-8")
    except OSError:
        return False
    for attempt in range(attempts):
        try:
            os.replace(tmp, path)
            return True
        except OSError:
            if attempt < attempts - 1:
                time.sleep(delay_s)
    # Nothing landed, so nothing is left behind: the temp file lives in the
    # state directory beside the real one, where a stray copy per failed publish
    # would accumulate and read as a file some component owns.
    tmp.unlink(missing_ok=True)
    return False


def append_command(
    path: Path, line: str, *, attempts: int = 5, delay_s: float = 0.005,
) -> bool:
    """Queue one verb on *path*, keeping whatever is already waiting there.

    The channel is a queue and this is how a verb joins it.  Writing the file
    whole instead — the obvious way, and the one several callers reached for —
    silently drops any verb queued since the last drain, which is how an
    edge-triggered command that fires once and is never re-asserted goes missing
    for good.

    The verb is put on a line of its own even when what is already queued does not
    end in a newline.  A writer that replaces the file whole rarely bothers with a
    trailing one, and appending straight onto that welds the two into a single word
    matching neither, which loses both — a "NEXT" written whole and a flag appended
    behind it left a player sitting on the video it was told to leave.

    The reader drains this ~20x/s by rewriting it, so a write that overlaps a
    drain hits a transient Windows sharing violation.  Retrying briefly turns
    that into a millisecond's delay instead of a lost verb; a file locked for
    longer drops the line (the next one lands) rather than raising into a run
    loop that has a frame to draw.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    for attempt in range(attempts):
        try:
            # Checked inside the retry loop: the queue can be drained between
            # attempts, and whether a separator is needed goes with it.
            with path.open("a+", encoding="utf-8") as handle:
                handle.seek(0, 2)
                if handle.tell():
                    handle.seek(handle.tell() - 1)
                    unterminated = handle.read(1) not in ("\n", "\r")
                    handle.seek(0, 2)
                    if unterminated:
                        handle.write("\n")
                handle.write(line + "\n")
            return True
        except OSError:
            if attempt < attempts - 1:
                time.sleep(delay_s)
    return False


def consume_command_file(
    path: Path, *, logger: logging.Logger | None = None, uppercase: bool = True
) -> list[str]:
    """Take every queued command line, emptying the file so none replays.

    *uppercase* folds the whole payload, which suits a player whose verbs carry
    no arguments.  A player whose commands take a case-sensitive argument (a
    path) passes ``uppercase=False`` and folds just the keyword itself.

    The queue is CLAIMED by renaming it aside and read from the claimed copy.
    Read-then-truncate had a hole exactly one verb wide: a writer appending
    between the read and the ``write_text("")`` was erased unread, and because
    the hybrid handoff is edge-triggered, an erased SET_TCODE_ENABLED or PAUSE
    stayed lost — the split-brain where Genau is paused and the funscript never
    enabled, everything idle for a whole scripted cluster.  A rename is atomic
    against appenders: the writer lands either in the claimed file (drained now)
    or in a fresh queue (drained next tick), never in between.
    """
    claimed = path.with_suffix(path.suffix + ".consuming")
    try:
        if not path.exists():
            return []
        try:
            os.replace(path, claimed)
        except OSError:
            # A writer holds the file this instant (Windows sharing violation).
            # The queue is intact; next tick is milliseconds away.
            return []
        text = claimed.read_text(encoding="utf-8").replace("﻿", "").strip()
        claimed.unlink(missing_ok=True)
        if uppercase:
            text = text.upper()
        if not text:
            return []
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
