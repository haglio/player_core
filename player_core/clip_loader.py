"""Decoding clips off the frame loop's thread, one load and one prefetch at a time.

A load is a clip somebody asked for; a prefetch is a neighbor decoded ahead of
being asked for.  Each runs on its own thread and reports through a
:class:`~player_core.clip_cache.DecodeRequestState`, which the loop polls on its
own tick -- so frames are adopted on the thread that draws them, and a request
superseded while its decode was still running is dropped rather than adopted
late.
"""
from __future__ import annotations

import time
from pathlib import Path

__all__ = [
    "ClipLoadController",
]

class ClipLoadController:
    def __init__(
        self,
        *,
        clip_store,
        load_state,
        prefetch_state,
        current_clip_path_getter,
        decode_clip,
        start_thread,
        logger,
        on_active_clip_loaded,
    ):
        self.clip_store = clip_store
        self.load_state = load_state
        self.prefetch_state = prefetch_state
        self.current_clip_path_getter = current_clip_path_getter
        self.decode_clip = decode_clip
        self.start_thread = start_thread
        self.logger = logger
        self.on_active_clip_loaded = on_active_clip_loaded

    @property
    def is_busy(self) -> bool:
        return self.load_state.loading or self.prefetch_state.loading

    def frames_ready(self, path: Path) -> bool:
        """Whether *path* can go on screen now, taking up a prefetch that landed.

        The two caches are one question to everyone outside this class: a clip
        decoded ahead is as ready as one that has been up before, and asking
        moves it across.
        """
        if path in self.clip_store.clip_cache:
            return True
        if self.clip_store.adopt_decoded_frames(
                path, protected_paths=self._clip_on_screen()):
            self.logger.info("Adopted prefetched clip %s", path.name)
            return True
        return False

    def request_clip_load(self, path: Path) -> None:
        if self.frames_ready(path) or self._already_decoding(path):
            return

        self.logger.info("Loading clip %s (no prefetch available)", path.name)
        request_id = self.load_state.begin(path)
        self.start_thread(
            target=self._loader_thread_fn,
            args=(path, request_id),
            name="genau-loader",
        )

    def request_prefetch(self, path: Path) -> None:
        if self.clip_store.holds(path) or self.is_busy:
            return

        self.logger.info("Prefetching clip %s", path.name)
        request_id = self.prefetch_state.begin(path)
        self.start_thread(
            target=self._prefetch_thread_fn,
            args=(path, request_id),
            name="genau-prefetch",
        )

    def adopt_loaded_clip_if_ready(self) -> None:
        result = self.load_state.take_completed_result()
        if result is None:
            return

        path, frames, err = result
        if err:
            return

        self.clip_store.cache_clip(
            path, frames, protected_paths=self._clip_on_screen())

        if self.current_clip_path_getter() == path:
            self.on_active_clip_loaded()

    def adopt_prefetch_if_ready(self) -> None:
        result = self.prefetch_state.take_completed_result()
        if result is None:
            return

        path, frames, err = result
        if err:
            return

        self.logger.info("Prefetch ready: %s (%d frames)", path.name, len(frames) if frames else 0)
        self.clip_store.cache_decoded_frames(
            path, frames, protected_paths=self._clip_on_screen())

    def _already_decoding(self, path: Path) -> bool:
        """Whether a decode of this very clip is running, either side.

        A clip asked for while it is being decoded ahead is waited for rather
        than decoded twice over: the second decode would take half the machine
        from the first, and the two finish later than the one would have.
        """
        return (self.load_state.is_decoding(path)
                or self.prefetch_state.is_decoding(path))

    def _clip_on_screen(self) -> set[Path]:
        """What trimming may never take: whatever is up now."""
        return {self.current_clip_path_getter()}

    def _decode_thread_fn(self, path: Path, request_id: int, state, log_error) -> None:
        # Not the frame loop's clock: this runs on a decode thread and the two
        # reads are one duration for one log line, not a timing decision the
        # loop makes.  The loop's clock is injected -- see the refresh controller.
        t0 = time.monotonic()
        try:
            frames = self.decode_clip(path)
            elapsed = time.monotonic() - t0
            self.logger.info("Decoded %s: %d frames in %.2fs", path.name, len(frames), elapsed)
            state.record_success(path, frames, request_id)
        except Exception as exc:
            log_error(path, exc)
            state.record_error(path, str(exc), request_id)

    def _loader_thread_fn(self, path: Path, request_id: int) -> None:
        self._decode_thread_fn(
            path, request_id, self.load_state,
            lambda p, e: self.logger.exception("Failed to decode clip %s", p),
        )

    def _prefetch_thread_fn(self, path: Path, request_id: int) -> None:
        self._decode_thread_fn(
            path, request_id, self.prefetch_state,
            lambda p, e: self.logger.warning("Prefetch decode failed for %s: %s", p, e),
        )
