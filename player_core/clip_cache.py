"""Decoded clips kept in memory, and the decode requests that fill the cache.

Two caches, both bounded and both least-recently-used: the clips that have been
taken up on screen, and frames decoded ahead of being taken up.  The clip on
screen is protected from trimming, whatever its age -- the picture must not
vanish under the viewer to make room for its neighbor.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


def trim_path_lru_cache[T](
    cache: OrderedDict[Path, T],
    *,
    limit: int,
    protected_paths: set[Path] | None = None,
) -> None:
    limit = max(1, int(limit))
    protected = {path for path in (protected_paths or set()) if path is not None}

    skipped = 0
    while len(cache) > limit and cache:
        oldest_key = next(iter(cache))
        if oldest_key in protected:
            cache.move_to_end(oldest_key)
            skipped += 1
            if skipped >= len(cache):
                break
            continue
        cache.popitem(last=False)
        skipped = 0


@dataclass
class DecodeRequestState:
    """One decode in flight, and the result it left for the loop to take.

    A result carrying a request id older than the latest request is stale --
    the loop asked for something else since -- and is dropped when taken, with
    the state left loading for the request that superseded it.
    """

    request_id: int = 0
    loading: bool = False
    loaded_clip_path: Path | None = None
    loaded_frames: list | None = None
    load_error: str | None = None
    request_id_done: int | None = None

    def begin(self) -> int:
        self.request_id += 1
        self.loading = True
        self.loaded_clip_path = None
        self.loaded_frames = None
        self.load_error = None
        self.request_id_done = None
        return self.request_id

    def record_success(self, path: Path, frames: list, request_id: int) -> None:
        self.loaded_clip_path = path
        self.loaded_frames = frames
        self.load_error = None
        self.request_id_done = request_id

    def record_error(self, path: Path, error: str, request_id: int) -> None:
        self.loaded_clip_path = path
        self.loaded_frames = None
        self.load_error = error
        self.request_id_done = request_id

    def take_completed_result(self) -> tuple[Path | None, list | None, str | None] | None:
        if self.request_id_done is None:
            return None

        if self.request_id_done != self.request_id:
            self.request_id_done = None
            self.loaded_clip_path = None
            self.loaded_frames = None
            self.load_error = None
            return None

        path = self.loaded_clip_path
        frames = self.loaded_frames
        error = self.load_error

        self.request_id_done = None
        self.loading = False
        return path, frames, error


class ClipCacheStore:
    def __init__(self, *, limit: int):
        self.limit = limit
        self.clip_cache: OrderedDict[Path, dict] = OrderedDict()
        self.decoded_frame_cache: OrderedDict[Path, list] = OrderedDict()

    def trim_cache(self, *, protected_paths: set[Path] | None = None) -> None:
        trim_path_lru_cache(
            self.clip_cache,
            limit=self.limit,
            protected_paths=protected_paths,
        )

    def trim_decoded_cache(self, *, protected_paths: set[Path] | None = None) -> None:
        trim_path_lru_cache(
            self.decoded_frame_cache,
            limit=self.limit,
            protected_paths=protected_paths,
        )

    def clip_entry_for(self, path: Path) -> dict:
        entry = self.clip_cache[path]
        self.clip_cache.move_to_end(path)
        return entry

    def cache_decoded_frames(self, path: Path, frames: list, *, protected_paths: set[Path] | None = None) -> None:
        self.decoded_frame_cache[path] = frames
        self.decoded_frame_cache.move_to_end(path)
        self.trim_decoded_cache(protected_paths=protected_paths)

    def adopt_decoded_frames(self, path: Path, *, protected_paths: set[Path] | None = None) -> bool:
        frames = self.decoded_frame_cache.get(path)
        if frames is None:
            return False

        self.decoded_frame_cache.move_to_end(path)
        self.clip_cache[path] = {
            "frames": frames,
        }
        self.clip_cache.move_to_end(path)
        self.trim_cache(protected_paths=protected_paths)
        return True
