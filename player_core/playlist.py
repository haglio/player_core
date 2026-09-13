"""The playlist a content source hands a player: one item per line.

Fun Time owns video discovery and its filters; it writes this file, tells the
player to RELOAD_PLAYLIST, and the player reads it back.  Each line names one
item, with a TAB and its funscript after it when it has one; blank lines and
#-comments are ignored.  The same line is what PLAY_FILE carries, so a source
naming an item to jump to spells it exactly as the file does.

Written and read here, in one module, because more than one player reads the
one shape Fun Time writes: the main player drives the OSR2 from the funscript
column, and a satellite (silent and unscripted) drops it.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from app_support.file_channel import write_whole

__all__ = [
    "read_playlist",
]


class PlaylistItem(NamedTuple):
    """One thing a player shows: its path, and the script that drives the
    device while it plays, when it has one.

    A tuple as well as a record, on purpose: every reader in the family took
    the item as a ``(video, funscript)`` pair before it had a name, and a
    checkout that has not moved to the names yet still unpacks it.
    """

    path: Path
    funscript: Path | None = None


def item_from_line(line: str) -> PlaylistItem | None:
    """The item one line names, or None for a line naming nothing."""
    path_part, _, funscript_part = line.partition("\t")
    path_part = path_part.strip()
    funscript_part = funscript_part.strip()
    if not path_part:
        return None
    return PlaylistItem(Path(path_part), Path(funscript_part) if funscript_part else None)


def item_line(item: PlaylistItem) -> str:
    """*item* as the one line that names it, the inverse of :func:`item_from_line`."""
    return f"{item.path}\t{item.funscript}" if item.funscript else f"{item.path}"


def read_playlist(path: Path) -> list[PlaylistItem]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    items: list[PlaylistItem] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        item = item_from_line(line)
        if item is not None:
            items.append(item)
    return items


def write_playlist(path: Path, items: Iterable[PlaylistItem]) -> None:
    """Write *items* as the file :func:`read_playlist` reads back, whole or not at all."""
    write_whole(path, "".join(f"{item_line(item)}\n" for item in items))
