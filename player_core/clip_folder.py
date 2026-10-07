"""The clips folder, its 2D and VR folders, and the pile beside it a condemned
clip is moved to, laid out the same way.

Condemning does the least it can — one file move.  A clip's other traces (its
metadata record, the clipper session it was cut from) stay where they are, and
the filename carries which clip it was.
"""
from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path

__all__ = [
    "SUPPORTED_VIDEO_EXTS",
    "move_clip_to_weird",
    "scan_clips",
    "weird_dir_for_clips_folder",
]

SUPPORTED_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}


def _modified_at(path: Path) -> float:
    """*path*'s modification time; one we cannot stat sorts oldest."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def scan_clips(
    folders: Path | Iterable[Path], *, shuffle_on_load: bool = True, recent: bool = False,
    shuffle=random.shuffle,
) -> list[Path]:
    """Every clip under *folders* -- one folder, or several browsed as one
    sequence -- in the browse order asked for.

    *recent* is Latest — newest-first across every folder, so the clips that
    have just arrived head the sequence — and it outranks *shuffle_on_load*: an
    order named outright is not then randomized away.  Without it the folders'
    own order stands, one after another, shuffled together when the config says
    to.  A folder with nothing in it contributes nothing; only no clips anywhere
    is an error.

    *shuffle* is a dependency rather than a module global so the shuffled order
    can be asked about at all: the reorder path is otherwise only testable by
    running it until a different order comes out.
    """
    folders = (Path(folders),) if isinstance(folders, (str, Path)) else tuple(Path(f) for f in folders)
    files = [path for folder in folders for path in sorted(folder.rglob("*"))
             if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTS]
    if not files:
        raise RuntimeError(f"No video clips found in: {', '.join(str(f) for f in folders)}")
    if recent:
        return sorted(files, key=_modified_at, reverse=True)
    if shuffle_on_load:
        shuffle(files)
    return files


def flat_clips_in(clips_folder: Path) -> Path:
    return clips_folder / "2D"


def vr_clips_in(clips_folder: Path) -> Path:
    return clips_folder / "VR"


def cache_dir_for_clips_folder(folder: Path) -> Path:
    return folder.parent / "frames"


def weird_dir_for_clips_folder(folder: Path) -> Path:
    return folder.parent / "weird"


def weird_folder_for(clip: Path, clips_folder: Path) -> Path:
    weird = weird_dir_for_clips_folder(clips_folder)
    try:
        return weird / clip.parent.relative_to(clips_folder)
    except ValueError:
        return weird


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
