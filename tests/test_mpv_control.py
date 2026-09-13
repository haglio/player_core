"""The shared mpv control surface: how it trims mpv's playlist.

``_MpvControl`` is the half of the player that needs no window and no DLL — it
only drives an mpv handle — so the playlist bookkeeping every player depends on
is testable against a fake handle here, rather than only through an app's
integration suite.
"""
from __future__ import annotations

import threading
from pathlib import Path

from player_core.mpv_player import _MpvControl


class FakeMpv:
    """An mpv handle that records what was asked of it.

    ``playlist_pos`` is settable so a test can put the handle in the states the
    real one reaches: on the head, rolled onto a prefetched entry, or holding no
    entry at all (-1, mpv's "nothing is playing").
    """

    def __init__(self, *, pos: int = 0, count: int = 2) -> None:
        self.playlist_pos = pos
        self.playlist_count = count
        self.calls: list[tuple] = []
        self.observers: dict[str, object] = {}

    def observe_property(self, name: str, handler) -> None:
        self.observers[name] = handler

    def report(self, name: str, value) -> None:
        self.observers[name](name, value)

    def playlist_clear(self) -> None:
        self.calls.append(("clear",))

    def playlist_remove(self, index: int) -> None:
        self.calls.append(("remove", index))

    def loadfile(self, path: str, mode: str) -> None:
        self.calls.append(("loadfile", path, mode))

    def play(self, path: str) -> None:
        self.calls.append(("play", path))


class Control(_MpvControl):
    def __init__(self, mpv) -> None:
        super().__init__()  # the call gate every method here runs under
        self._adopt(mpv)


def test_the_frame_rate_is_the_one_mpv_reported_for_the_file_on_screen():
    mpv = FakeMpv()
    control = Control(mpv)

    mpv.report("container-fps", 29.970029830932617)

    assert control.frame_rate == 29.970029830932617


def test_between_files_there_is_no_frame_rate():
    mpv = FakeMpv()
    control = Control(mpv)
    mpv.report("container-fps", 60.0)

    mpv.report("container-fps", None)

    assert control.frame_rate == 0.0


def test_staging_the_next_clip_never_removes_by_index():
    """The staged entry goes through ``playlist-clear``, which mpv resolves against
    whatever is playing at that instant.

    Removing by an index read a moment earlier is the bug this pins: with prefetch
    on, mpv rolls onto the staged entry by itself at end-of-file, so ``pos + 1``
    can already name the clip now on screen — and removing it leaves mpv on an
    empty playlist, which is a black window for the rest of the session.
    """
    mpv = FakeMpv(pos=0, count=2)
    Control(mpv).stage_next(Path("alpha.mp4"))
    assert ("clear",) in mpv.calls
    assert not [call for call in mpv.calls if call[0] == "remove"]
    assert mpv.calls[-1] == ("loadfile", "alpha.mp4", "append")


def test_staging_holds_up_when_mpv_says_nothing_is_playing():
    """-1 is mpv's "no entry playing", not entry zero.

    Read as a position it made the trim walk the playlist to nothing — so a player
    that had lost its file could never get one back.
    """
    mpv = FakeMpv(pos=-1, count=3)
    Control(mpv).stage_next(Path("beta.mp4"))
    assert not [call for call in mpv.calls if call[0] == "remove"]
    assert mpv.calls[-1] == ("loadfile", "beta.mp4", "append")


def test_clearing_the_staged_entry_keeps_the_clip_on_screen():
    """A lock drops the prefetched next; the clip being held must not go with it."""
    mpv = FakeMpv(pos=0, count=2)
    Control(mpv).clear_next()
    assert mpv.calls == [("clear",)]


def test_dropping_the_spent_head_keeps_the_clip_on_screen():
    """After an auto-advance the played-out clip still sits ahead of the one now
    playing; clearing around the current entry is what shifts it back to the head."""
    mpv = FakeMpv(pos=1, count=2)
    Control(mpv).drop_consumed()
    assert mpv.calls == [("clear",)]


def test_no_entry_playing_does_not_read_as_having_advanced():
    """A player holding no file has not moved past the head — it has fallen off
    the playlist, and treating that as an advance walks the session's index on
    past a clip that never played."""
    assert Control(FakeMpv(pos=-1)).advanced_to_next is False
    assert Control(FakeMpv(pos=0)).advanced_to_next is False
    assert Control(FakeMpv(pos=1)).advanced_to_next is True


class BlockingMpv(FakeMpv):
    """A handle whose property read can be held open, the way a real one is
    while a file it is opening holds the core's lock."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.terminated = 0

    @property
    def time_pos(self):
        self.entered.set()
        self.release.wait(10.0)
        return 1.0

    def terminate(self) -> None:
        self.terminated += 1
        self.calls.append(("terminate",))


def test_close_waits_for_a_read_that_is_still_inside_mpv():
    """The shutdown crash, in miniature: python-mpv's terminate() nulls its
    handle before destroying the core, so a property read that began a moment
    earlier dereferences NULL.  close() may not run until the read is out."""
    mpv = BlockingMpv()
    control = Control(mpv)
    reading = threading.Thread(target=lambda: control.position_ms)
    reading.start()
    assert mpv.entered.wait(5.0)

    closing = threading.Thread(target=control.close)
    closing.start()
    closing.join(timeout=0.3)
    assert closing.is_alive()
    assert mpv.terminated == 0

    mpv.release.set()
    closing.join(timeout=10.0)
    reading.join(timeout=10.0)
    assert mpv.terminated == 1


def test_the_frame_rate_is_answered_while_a_read_is_stuck_inside_mpv():
    """A file being opened holds mpv's core lock for hundreds of milliseconds,
    and a player asks for the frame rate every frame it paints."""
    mpv = BlockingMpv()
    control = Control(mpv)
    mpv.report("container-fps", 25.0)
    reading = threading.Thread(target=lambda: control.position_ms)
    reading.start()
    assert mpv.entered.wait(5.0)

    try:
        assert control.frame_rate == 25.0
    finally:
        mpv.release.set()
        reading.join(timeout=10.0)


def test_a_call_arriving_after_the_close_reaches_no_handle():
    """A worker that never noticed the stop flag keeps calling; every one of
    those calls has to become a no-op rather than a use-after-free."""
    mpv = BlockingMpv()
    mpv.release.set()
    control = Control(mpv)
    control.close()
    assert mpv.terminated == 1

    control.load(Path("alpha.mp4"))
    control.seek_ms(1000)
    assert control.position_ms == 0.0
    assert control.duration_ms == 0.0
    assert control.eof is False
    assert control.advanced_to_next is False
    assert mpv.calls == [("terminate",)]


def test_closing_twice_frees_once():
    """``MpvRenderContext.free`` is a bare ``mpv_render_context_free`` with no
    double-free guard of its own, so the guard is here."""
    mpv = BlockingMpv()
    mpv.release.set()
    control = Control(mpv)
    control.close()
    control.close()
    assert mpv.terminated == 1
