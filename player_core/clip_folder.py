"""The clips folder, and what sits beside it.

A clips folder has two siblings: ``frames/``, where the decoded frame caches
live, and ``weird/``, the pile a condemned clip is moved to.  Condemning does the
least it can — one file move.  A clip's other traces (its ``.rhcache``, the
clipper session it was cut from, the source video's metadata) stay where they
are, for Evolver to reconcile against the pile later.  Which clip was condemned
is the whole of the state this leaves, and the filename carries it.
"""
from __future__ import annotations

import random
from pathlib import Path

SUPPORTED_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}


def _modified_at(path: Path) -> float:
    """*path*'s modification time; one we cannot stat sorts oldest."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def scan_clips(
    folder: Path, *, shuffle_on_load: bool = True, recent: bool = False,
    shuffle=random.shuffle,
) -> list[Path]:
    """Every clip in *folder*, in the browse order asked for.

    *recent* is Latest — newest-first, so the clips that have just arrived head
    the sequence — and it outranks *shuffle_on_load*: an order named outright is
    not then randomized away.  Without it the folder's own order stands,
    shuffled when the config says to.

    *shuffle* is a dependency rather than a module global so the shuffled order
    can be asked about at all: the reorder path is otherwise only testable by
    running it until a different order comes out.
    """
    files = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTS]
    if not files:
        raise RuntimeError(f"No video clips found in: {folder}")
    if recent:
        return sorted(files, key=_modified_at, reverse=True)
    if shuffle_on_load:
        shuffle(files)
    return files


def cache_dir_for_clips_folder(folder: Path) -> Path:
    return folder.parent / "frames"


def weird_dir_for_clips_folder(folder: Path) -> Path:
    """The condemned pile beside a clips folder, as ``frames/`` sits beside it."""
    return folder.parent / "weird"


def move_clip_to_weird(clip_path: Path, weird_dir: Path) -> Path | None:
    """Move *clip_path* into *weird_dir*, returning where it landed.

    Returns None when the clip is already gone — two WEIRD verbs can name the
    same clip before the first has finished, and the second must not take the
    player down with it.
    """
    if not clip_path.exists():
        return None
    weird_dir.mkdir(parents=True, exist_ok=True)
    destination = weird_dir / clip_path.name
    clip_path.replace(destination)
    return destination
