"""Tests for player_core.status.

The *fields* each player publishes are that player's own concern and are covered
in its repo (genau's ``test_nau_status.py``, fun_time's ``test_satellite_status.py``).
What is shared — and tested here — is the publishing mechanism: the throttle, the
directory, and surviving a file that cannot be written.
"""
from __future__ import annotations

from pathlib import Path

from player_core.status import StatusWriter


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

    def test_an_unwritable_path_is_reported_not_raised(self, tmp_path):
        # A locked or vanished status file must never take down a run loop; the
        # next tick will try again.
        status_path = tmp_path / "status.txt"
        status_path.mkdir()  # a directory where the file should be
        writer = StatusWriter(status_path, _fields, now_source=lambda: 0.0)

        assert writer.write(StubSession()) is False

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
