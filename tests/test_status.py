"""Tests for player_core.status.

The *fields* each player publishes are that player's own concern and are covered
in its repo (fun_time's ``test_main_player_status.py`` and ``test_satellite_status.py``).
What is shared — and tested here — is the publishing mechanism: the throttle, the
directory, and surviving a file that cannot be written.
"""
from __future__ import annotations

import threading
from pathlib import Path

from player_core.status import PlayerStatus, StatusWriter, parse_status, status_fields


class StubSession:
    def __init__(self) -> None:
        self.current_video = Path("C:/vids/clip.mp4")
        self.position_ms = 12345.6


def _fields(session):
    return {
        "video": str(session.current_video),
        "position_ms": str(int(session.position_ms)),
    }


class TestStatusWriter:
    def test_writes_the_fields_the_player_supplies(self, tmp_path):
        status_path = tmp_path / "status.txt"
        writer = StatusWriter(status_path, _fields, now_source=lambda: 0.0)

        assert writer.write(StubSession())

        text = status_path.read_text(encoding="utf-8")
        assert "video=C:\\vids\\clip.mp4\n" in text or "video=C:/vids/clip.mp4\n" in text
        assert "position_ms=12345\n" in text

    def test_writes_one_key_per_line_in_the_players_own_order(self, tmp_path):
        # Each player owns its file's layout, so the writer must not reorder or
        # reformat what the fields callable returned — a reader parses these keys.
        status_path = tmp_path / "status.txt"
        writer = StatusWriter(
            status_path, lambda _s: {"b": "2", "a": "1"}, now_source=lambda: 0.0,
        )

        writer.write(StubSession())

        assert status_path.read_text(encoding="utf-8") == "b=2\na=1\n"

    def test_creates_the_state_directory(self, tmp_path):
        # A player can publish before anything else has created its state dir.
        status_path = tmp_path / "state" / "status.txt"
        writer = StatusWriter(status_path, _fields, now_source=lambda: 0.0)

        assert writer.write(StubSession())
        assert status_path.exists()

    def test_throttles_writes_within_interval(self, tmp_path):
        status_path = tmp_path / "status.txt"
        clock = {"t": 0.0}
        writer = StatusWriter(
            status_path, _fields, min_interval=0.2, now_source=lambda: clock["t"],
        )
        session = StubSession()

        writer.write(session)
        session.position_ms = 12400.0
        clock["t"] = 0.1

        assert not writer.write(session)
        assert "position_ms=12345" in status_path.read_text(encoding="utf-8")

    def test_writes_again_after_interval(self, tmp_path):
        status_path = tmp_path / "status.txt"
        clock = {"t": 0.0}
        writer = StatusWriter(
            status_path, _fields, min_interval=0.2, now_source=lambda: clock["t"],
        )
        session = StubSession()

        writer.write(session)
        session.position_ms = 12400.0
        clock["t"] = 0.25

        assert writer.write(session)
        assert "position_ms=12400" in status_path.read_text(encoding="utf-8")

    def test_a_poller_never_reads_a_half_written_record(self, tmp_path):
        # The orchestrator polls this file several times a second while the
        # player rewrites it several times a second.  A write that truncates the
        # file in place leaves a window in which the poller reads nothing — and
        # a poller cannot tell "I caught it mid-write" from "this player has no
        # clip", so it acts on the blank.  The write has to land whole or not at
        # all.
        status_path = tmp_path / "status.txt"
        writer = StatusWriter(status_path, _fields, min_interval=0.0)
        session = StubSession()
        writer.write(session)

        stop = threading.Event()
        torn: list[str] = []

        def poll() -> None:
            while not stop.is_set():
                try:
                    text = status_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                if "video=" not in text or "position_ms=" not in text:
                    torn.append(text)

        poller = threading.Thread(target=poll, daemon=True)
        poller.start()
        try:
            for tick in range(120):
                session.position_ms = 12345.6 + tick
                writer.write(session)
        finally:
            stop.set()
            poller.join(timeout=5)

        assert not torn, f"the poller read {len(torn)} incomplete records, e.g. {torn[0]!r}"

    def test_an_unwritable_path_is_reported_not_raised(self, tmp_path):
        # A locked or vanished status file must never take down a run loop; the
        # next tick will try again — and a publish that never landed leaves
        # nothing on disk, not even the file it staged.
        status_path = tmp_path / "status.txt"
        status_path.mkdir()  # a directory where the file should be
        writer = StatusWriter(status_path, _fields, now_source=lambda: 0.0)

        assert writer.write(StubSession()) is False
        assert list(tmp_path.iterdir()) == [status_path]

    def test_a_failed_write_does_not_start_the_throttle(self, tmp_path):
        # Throttling off a write that never landed would suppress the retry that
        # is supposed to recover from a transient lock.
        status_path = tmp_path / "state"
        status_path.mkdir()
        clock = {"t": 0.0}
        writer = StatusWriter(
            status_path, _fields, min_interval=0.2, now_source=lambda: clock["t"],
        )

        assert writer.write(StubSession()) is False
        status_path.rmdir()

        assert writer.write(StubSession()) is True


class TestWhatEveryPlayerPublishes:
    """The six lines every player's status leads with, written and read here so
    a player and the source polling it cannot disagree about a key."""

    def test_the_lines_in_the_order_they_are_written(self):
        fields = status_fields(PlayerStatus(
            video="C:/vids/a.mp4", position_ms=1500, duration_ms=5000, paused=False, locked=True,
            speed=1.5))

        assert fields == {
            "video": "C:/vids/a.mp4", "position_ms": "1500", "duration_ms": "5000",
            "paused": "0", "locked": "1", "speed": "1.5", "picture": "0",
        }
        assert list(fields) == ["video", "position_ms", "duration_ms", "paused", "locked",
                                "speed", "picture"]

    def test_a_playhead_is_published_as_whole_milliseconds(self):
        assert status_fields(PlayerStatus(position_ms=12345.9))["position_ms"] == "12345"

    def test_what_is_published_is_what_is_read_back(self):
        status = PlayerStatus(
            video="C:/vids/b.mp4", position_ms=250, duration_ms=9000, paused=True, locked=False,
            speed=0.75)

        assert parse_status(status_fields(status)) == status

    def test_a_status_that_says_a_picture_is_on_screen_reads_back_saying_so(self):
        status = PlayerStatus(video="C:/pictures/one.png", locked=True, picture=True)

        assert parse_status(status_fields(status)) == status

    def test_a_key_the_file_does_not_carry_keeps_the_readers_default(self):
        """A status from before a key existed, or a file read before the player's
        first write, says what that player is doing at rest -- and what that is
        differs: a satellite opens unlocked, the main player locked."""
        assert parse_status({}) == PlayerStatus()
        assert parse_status({}, default=PlayerStatus(locked=True)).locked is True
        assert parse_status({"locked": "0"}, default=PlayerStatus(locked=True)).locked is False

    def test_a_flag_is_on_only_when_the_file_says_1(self):
        assert parse_status({"paused": "1"}).paused is True
        assert parse_status({"paused": ""}, default=PlayerStatus(paused=True)).paused is False

    def test_a_number_that_cannot_be_read_keeps_the_default_too(self):
        assert parse_status({"position_ms": "soon", "duration_ms": " 40 "}).position_ms == 0
        assert parse_status({"position_ms": "soon", "duration_ms": " 40 "}).duration_ms == 40
        assert parse_status({"speed": "fast"}, default=PlayerStatus(speed=0.5)).speed == 0.5

    def test_the_lines_a_player_adds_of_its_own_ride_past_the_reader(self):
        status = parse_status({"video": " C:/vids/c.mp4 ", "playlist_length": "3", "state": "looping"})

        assert status == PlayerStatus(video="C:/vids/c.mp4")
