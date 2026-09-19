"""Reading the clock of the player that has the room off its status file."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from player_core.crossing import HeldSink, read_the_room


def _status(tmp_path: Path, text: str, *, written_at: float) -> Path:
    path = tmp_path / "main_player_status.txt"
    path.write_text(text, encoding="utf-8")
    os.utime(path, (written_at, written_at))
    return path


class TestTheRoomsClock:
    def test_it_is_the_status_the_room_published(self, tmp_path: Path):
        path = _status(tmp_path, "video=C:/v/one.mp4\nposition_ms=4000\nduration_ms=9000\n"
                                 "paused=0\nlocked=1\nspeed=1.5\npicture=0\n",
                       written_at=1_000.0)
        clock, _fields = read_the_room(path)
        assert (clock.video, clock.position_ms, clock.paused, clock.locked, clock.speed) == (
            str(Path("C:/v/one.mp4")), 4000, False, True, 1.5)

    def test_the_video_is_spelled_as_a_path_the_follower_compares_against(self, tmp_path: Path):
        """The follower names its own video through ``Path``, which spells a
        Windows path one way whatever the writer typed."""
        path = _status(tmp_path, "video=C:/v/one.mp4\nposition_ms=4000\n", written_at=1_000.0)
        clock, _fields = read_the_room(path)
        assert clock.video == str(Path("C:\\v\\one.mp4"))

    def test_it_is_stamped_when_the_file_was_written(self, tmp_path: Path):
        """A status is written the moment after its position is read, so the
        file's own clock is the position's."""
        path = _status(tmp_path, "video=C:/v/one.mp4\nposition_ms=4000\n", written_at=1_000.0)
        clock, _fields = read_the_room(path)
        assert clock.said_at == pytest.approx(1_000.0)

    def test_the_players_own_lines_come_back_too(self, tmp_path: Path):
        path = _status(tmp_path, "video=C:/v/one.mp4\nposition_ms=4000\nfunscript=C:/s/one.funscript\n",
                       written_at=1_000.0)
        _clock, fields = read_the_room(path)
        assert fields["funscript"] == "C:/s/one.funscript"

    def test_no_status_yet_is_a_room_playing_nothing(self, tmp_path: Path):
        clock, fields = read_the_room(tmp_path / "missing.txt")
        assert clock.video == ""
        assert fields == {}


class _Sink:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    def send(self, command: str) -> None:
        self.sent.append(command)

    def close(self) -> None:
        self.closed = True


class TestTheHeldSink:
    def test_nothing_reaches_the_device_while_it_is_held(self):
        sink = _Sink()
        HeldSink(sink).send("L05000I100")
        assert sink.sent == []

    def test_letting_go_passes_what_follows(self):
        sink = _Sink()
        held = HeldSink(sink)
        held.send("L05000I100")
        held.let_go()
        held.send("L06000I100")
        assert sink.sent == ["L06000I100"]

    def test_a_sink_nobody_follows_with_is_never_held(self):
        sink = _Sink()
        HeldSink(sink, held=False).send("L05000I100")
        assert sink.sent == ["L05000I100"]

    def test_closing_it_closes_the_socket_behind_it(self):
        sink = _Sink()
        HeldSink(sink).close()
        assert sink.closed
