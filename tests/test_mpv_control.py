"""The shared mpv control surface: how it trims mpv's playlist.

``_MpvControl`` is the half of the player that needs no window and no DLL — it
only drives an mpv handle — so the playlist bookkeeping every player depends on
is testable against a fake handle here, rather than only through an app's
integration suite.
"""
from __future__ import annotations

import math
import threading
from pathlib import Path

import pytest

from player_core import audio_outputs
from player_core.mpv_player import _MpvControl, _shared_options


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
        self.audio_device_list: list[dict] = []
        self.audio_device = "auto"

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
    """A control surface whose clock a test moves by hand.

    The creep into a still is paced by a clock rather than by a playhead --
    mpv leaves a picture's at nought -- so ``now`` is what a test winds on to
    say how far into the hold the picture has got.
    """

    def __init__(self, mpv, now: float = 0.0) -> None:
        super().__init__()  # the call gate every method here runs under
        self.now = now
        self._adopt(mpv)

    def _now(self) -> float:
        return self.now


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


def test_a_picture_holds_the_screen_for_the_pace_it_was_given():
    mpv = FakeMpv()

    Control(mpv).set_pace(2.5)

    assert mpv.image_display_duration == 2.5


def test_a_pace_of_nought_holds_the_picture_until_something_moves_it():
    mpv = FakeMpv()

    Control(mpv).set_pace(0)

    assert mpv.image_display_duration == "inf"


def test_the_player_shows_a_picture_when_mpv_says_its_video_track_is_an_image():
    mpv = FakeMpv()
    control = Control(mpv)

    mpv.report("current-tracks/video/image", True)
    assert control.showing_picture is True

    mpv.report("current-tracks/video/image", None)
    assert control.showing_picture is False


def test_a_player_holds_a_picture_four_seconds_until_a_source_sets_a_pace():
    options = _shared_options(muted=False, loop_file=False, prefetch=True)

    assert options["image_display_duration"] == 4.0


# Every Lua script mpv loads for itself, by the option that keeps it out.
MPVS_OWN_SCRIPTS = (
    "osc", "load_scripts", "load_stats_overlay", "load_osd_console",
    "load_auto_profiles", "load_select", "load_positioning", "load_commands",
    "ytdl",
)


def test_a_player_runs_none_of_mpvs_lua_scripts():
    """All of them, not just the on-screen controller.

    A player here is driven through the client API alone, so mpv's scripting
    layer can only cost.  What it costs is a crash: these scripts error on the
    way out often enough to matter, LuaJIT unwinds a Lua error through a Windows
    structured exception, and a process with faulthandler armed answers every one
    by dumping all threads' Python frames without the GIL -- while python-mpv's
    event thread is exiting, so the walk reaches a thread state being freed and
    faults.  Measured on this family's options: 22 of 40 core teardowns raised
    one with these left on, none of 60 with them off.
    """
    options = _shared_options(muted=False, loop_file=True, prefetch=False)

    assert {name: options.get(name) for name in MPVS_OWN_SCRIPTS} == dict.fromkeys(
        MPVS_OWN_SCRIPTS, "no")


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


STREAMING = {"name": "wasapi/{stream-id}", "description": "Speakers (Example AirLink)"}
HEADSET = {"name": "wasapi/{headset-id}", "description": "Headphones (Example Headset)"}


def test_a_headset_named_for_its_maker_takes_the_sound_over_that_makers_software_output(
        monkeypatch):
    """Two outputs can carry the maker's name — the headset's own, and the
    streaming driver its software installed — and the streaming one is listed
    first, so taking the first match leaves the headset silent."""
    monkeypatch.setattr(audio_outputs, "software_outputs",
                        lambda: frozenset({STREAMING["description"]}))
    mpv = FakeMpv()
    mpv.audio_device_list = [STREAMING, HEADSET]

    picked = Control(mpv).set_audio_device_matching("Example")

    assert mpv.audio_device == HEADSET["name"]
    assert picked == HEADSET["description"]


def test_an_output_no_device_is_named_by_leaves_the_sound_on_the_system_default():
    mpv = FakeMpv()
    mpv.audio_device_list = [STREAMING, HEADSET]

    assert Control(mpv).set_audio_device_matching("Nowhere") is None
    assert mpv.audio_device == "auto"


def test_a_picture_is_drawn_closer_as_its_hold_runs_out():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    mpv.report("path", "made-up-scene.png")
    mpv.report("current-tracks/video/image", True)

    control.now = 102.0
    control.push_still()

    assert mpv.video_zoom == pytest.approx(math.log2(1.05))


def test_a_clip_after_a_picture_is_drawn_as_it_comes():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    mpv.report("path", "made-up-scene.png")
    mpv.report("current-tracks/video/image", True)
    control.now = 102.0
    control.push_still()

    mpv.report("path", "made-up-scene.mp4")
    mpv.report("current-tracks/video/image", False)
    control.push_still()

    assert mpv.video_zoom == 0.0


def test_a_frozen_room_holds_the_picture_where_the_creep_had_got_to():
    mpv = FakeMpv()
    control = Control(mpv, now=100.0)
    control.set_pace(4.0)
    mpv.report("path", "made-up-scene.png")
    mpv.report("current-tracks/video/image", True)

    control.now = 101.0
    control.set_paused(True)
    control.now = 103.0
    control.push_still()

    assert mpv.video_zoom == pytest.approx(math.log2(1.025))
