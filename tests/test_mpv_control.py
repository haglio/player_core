"""The shared mpv control surface: how it trims mpv's playlist.

``_MpvControl`` is the half of the player that needs no window and no DLL — it
only drives an mpv handle — so the playlist bookkeeping every player depends on
is testable against a fake handle here, rather than only through an app's
integration suite.
"""
from __future__ import annotations

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
        self._mpv = mpv


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
