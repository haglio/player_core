"""Which clips get decoded over a session, and which one is on screen while.

`test_clip_selection.py` drives the selection against a fake loader and
`test_clip_loader.py` drives the loader against a hand-filled store.  Between
them sits what the two caches do to each other turn after turn, which neither
can see: a sweep that re-decoded the same two clips for as long as Genau ran,
and an advance that showed the loading line for a clip it already had.

A decode asked for during a turn comes back at the top of the next one -- the
same one turn of lag the real threads have, without the clock -- so a test can
also step while one is still running, by stepping between turns.
"""
from __future__ import annotations

from pathlib import Path

from player_core.clip_cache import ClipCacheStore, DecodeRequestState
from player_core.clip_loader import ClipLoadController
from player_core.clip_renderer import ClipRenderController
from player_core.clip_selection import ClipSelectionController
from player_core.clip_sequence import ClipSequenceController

# What Genau's own config gives it: the clip on screen, and room for one more.
CACHE_LIMIT = 2


class FakeNotifier:
    def __init__(self):
        self.clips: list[Path] = []

    def notify_clip(self, path: Path) -> None:
        self.clips.append(path)


class Pipeline:
    """The three parts that get a clip onto the screen, wired as the app wires
    them, driven one turn of the tick at a time."""

    def __init__(self, *names: str, logger=None):
        self.decodes: list[str] = []
        self.blits: list[object] = []
        self._running: list[tuple] = []
        self.clip_store = ClipCacheStore(limit=CACHE_LIMIT)
        self.renderer = ClipRenderController(
            clip_store=self.clip_store, blit_frame=self.blits.append,
        )
        self.notifier = FakeNotifier()
        self.loader = ClipLoadController(
            clip_store=self.clip_store,
            load_state=DecodeRequestState(),
            prefetch_state=DecodeRequestState(),
            current_clip_path_getter=lambda: self.renderer.current_clip_path,
            decode_clip=self._decode,
            start_thread=self._start_decode,
            logger=logger if logger is not None else _SilentLog(),
            on_active_clip_loaded=self.renderer.prepare_active_clip_for_current_size,
        )
        self.selection = ClipSelectionController(
            sequence=ClipSequenceController([Path(name) for name in names]),
            clip_store=self.clip_store,
            loader=self.loader,
            renderer=self.renderer,
            notifier=self.notifier,
        )

    def _decode(self, path: Path) -> list[str]:
        self.decodes.append(path.name)
        return [f"{path.name}:0"]

    def _start_decode(self, *, target, args, name) -> None:
        self._running.append((target, args))

    def open_on(self, name: str) -> None:
        self.selection.set_current_clip(Path(name))

    def turn(self) -> None:
        """One turn of the tick, with whatever was asked for last turn come back."""
        running, self._running = self._running, []
        for target, args in running:
            target(*args)
        self.loader.adopt_loaded_clip_if_ready()
        self.loader.adopt_prefetch_if_ready()
        self.selection.adopt_pending_clip()
        self.selection.request_nearby_prefetch()

    @property
    def on_screen(self) -> str | None:
        path = self.renderer.current_clip_path
        return None if path is None else path.name


class _SilentLog:
    def info(self, *_args, **_kwargs) -> None:
        pass

    def warning(self, *_args, **_kwargs) -> None:
        pass

    def exception(self, *_args, **_kwargs) -> None:
        pass


def test_a_clip_is_decoded_once_however_long_the_sweep_runs():
    """The clip on screen must not take a slot in the decode-ahead cache.

    Genau holds two clips' frames and has two neighbors to decode ahead.  With
    the clip on screen sitting in that cache as well -- and protected from
    trimming, so never leaving -- only one neighbor fits, and decoding either
    one throws the other out: the sweep then re-decoded both, alternately, for
    as long as the session ran.
    """
    pipeline = Pipeline("on_screen.mp4", "after.mp4", "before.mp4")

    pipeline.open_on("on_screen.mp4")
    for _ in range(20):
        pipeline.turn()

    assert pipeline.decodes == ["on_screen.mp4", "after.mp4", "before.mp4"]


def test_an_advance_to_a_clip_decoded_ahead_puts_it_up_with_no_wait():
    """Nothing is pending when the clip was already decoded, so the loading
    line -- which is drawn from exactly that -- never comes up.

    The switch used to be deferred a turn whatever the state of the clip: the
    selection asked only whether it was in the clips-on-screen cache, and a
    clip decoded ahead is not in that one yet.  So every advance raised the
    loading line for the frame before the clip it already had went up.
    """
    pipeline = Pipeline("on_screen.mp4", "after.mp4", "before.mp4")
    pipeline.open_on("on_screen.mp4")
    for _ in range(4):
        pipeline.turn()
    assert pipeline.decodes == ["on_screen.mp4", "after.mp4", "before.mp4"]

    pipeline.selection.step(1)

    assert pipeline.on_screen == "after.mp4"
    assert pipeline.selection.pending_clip_name is None


def test_a_clip_that_goes_up_gives_its_decode_ahead_slot_back():
    """Decode-ahead room is for clips not yet up, and Genau has room for two.

    Condemning is where taking one up and leaving it there shows: the successor
    comes off the decode-ahead pile, and if it stays on that pile as well it
    leaves one slot for its own two neighbors -- so the sweep decodes them
    alternately, for as long as the session runs.
    """
    pipeline = Pipeline("weird.mp4", "after.mp4", "third.mp4", "before.mp4")
    pipeline.open_on("weird.mp4")
    for _ in range(4):
        pipeline.turn()
    assert pipeline.decodes == ["weird.mp4", "after.mp4", "before.mp4"]

    assert pipeline.selection.condemn_current() is True
    for _ in range(20):
        pipeline.turn()

    assert pipeline.on_screen == "after.mp4"
    assert pipeline.decodes == [
        "weird.mp4", "after.mp4", "before.mp4", "third.mp4"]


def test_an_advance_that_catches_a_decode_running_does_not_start_it_again():
    """The clip the advance lands on is often the one being decoded ahead --
    whenever a decode takes longer than the clip holds the screen, which is
    every advance at a short interval.

    Asking for it again started a second decode of the same file beside the
    first, so the two halved each other's share of the machine at exactly the
    moment it was already too slow.  The advance waits for the decode that is
    running instead.
    """
    pipeline = Pipeline("on_screen.mp4", "after.mp4", "before.mp4")
    pipeline.open_on("on_screen.mp4")
    pipeline.turn()
    assert pipeline.decodes == ["on_screen.mp4"]

    pipeline.selection.step(1)
    assert pipeline.selection.pending_clip_name == "after.mp4"
    pipeline.turn()

    assert pipeline.on_screen == "after.mp4"
    assert pipeline.decodes == ["on_screen.mp4", "after.mp4"]
