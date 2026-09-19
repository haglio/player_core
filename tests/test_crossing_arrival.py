"""A player arriving in a room another player has: following it, then taking it."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from player_core.crossing import SEEK_LEAD_MS, STEADY_TURNS, Arrival, Crossing, follow_channel

NOW = 1_000.0
VIDEO = str(Path("C:/library/scene one.mp4"))


@dataclass
class _Follower:
    video: str = str(Path("C:/library/elsewhere.mp4"))
    position_ms: float = 0.0
    duration_ms: float = 60_000.0
    paused: bool = False
    locked: bool = True
    speed: float = 1.0
    opened: list[tuple[str, dict]] = field(default_factory=list)
    seeks: list[float] = field(default_factory=list)
    leans: list[float] = field(default_factory=list)
    mirrored: list[dict] = field(default_factory=list)
    took: list[dict] = field(default_factory=list)

    def open(self, video: str, room: dict) -> None:
        self.opened.append((video, room))
        self.video = video

    def seek_to(self, position_ms: float) -> None:
        self.seeks.append(position_ms)

    def set_locked(self, locked: bool) -> None:
        self.locked = locked

    def set_speed(self, speed: float) -> None:
        self.speed = speed

    def lean(self, speed: float) -> None:
        self.leans.append(speed)

    def mirror(self, room: dict) -> None:
        self.mirrored.append(room)

    def take_the_room(self, room: dict) -> None:
        self.took.append(room)


@dataclass
class _Room:
    arrival: Arrival
    follower: _Follower
    state: Path

    def says(self, *, video: str = VIDEO, position_ms: int = 4_000, speed: float = 1.0,
             locked: bool = True, extra: str = "") -> None:
        status = self.state / "portrait_status.txt"
        status.write_text(
            f"video={video}\nposition_ms={position_ms}\nduration_ms=60000\npaused=0\n"
            f"locked={int(locked)}\nspeed={speed:g}\npicture=0\n{extra}",
            encoding="utf-8")
        os.utime(status, (NOW, NOW))

    def held_in_step(self) -> None:
        self.says()
        self.follower.video = VIDEO
        self.follower.position_ms = 4_000.0
        for _ in range(STEADY_TURNS):
            self.arrival.turn()

    def told_to_take_it(self) -> None:
        Crossing(self.state, ["portrait"]).say_take_the_room()
        self.arrival.turn()


def _room(state: Path, *, arriving: bool = True) -> _Room:
    follower = _Follower()
    arrival = Arrival(
        arriving=arriving,
        follower=follower,
        room_status=state / "portrait_status.txt",
        command_file=state / "portrait_cmd.txt",
        clock=lambda: NOW,
    )
    return _Room(arrival, follower, state)


@pytest.fixture
def room(tmp_path: Path) -> _Room:
    return _room(tmp_path)


class TestWhatItDrains:
    def test_the_follow_channel_until_it_has_the_room(self, room):
        assert room.arrival.command_file == follow_channel(room.state / "portrait_cmd.txt")

    def test_the_rooms_own_channel_once_it_has(self, room):
        room.held_in_step()
        room.told_to_take_it()
        assert room.arrival.command_file == room.state / "portrait_cmd.txt"

    def test_an_ordinary_launch_drains_the_rooms_own_channel_from_the_start(self, tmp_path):
        here = _room(tmp_path, arriving=False)
        assert here.arrival.command_file == tmp_path / "portrait_cmd.txt"


class TestFollowingTheRoom:
    def test_it_opens_what_the_room_is_playing(self, room):
        room.says(extra="funscript=C:/library/scene one.funscript\n")
        room.arrival.turn()
        video, said = room.follower.opened[0]
        assert video == VIDEO
        assert said["funscript"] == "C:/library/scene one.funscript"

    def test_it_opens_the_rooms_video_while_its_own_is_still_loading(self, room):
        room.says()
        room.follower.duration_ms = 0.0
        room.arrival.turn()
        assert [video for video, _ in room.follower.opened] == [VIDEO]

    def test_it_goes_where_the_room_is_once_the_video_is_open(self, room):
        room.says()
        room.arrival.turn()
        room.arrival.turn()
        assert room.follower.seeks == [pytest.approx(4_000 + SEEK_LEAD_MS)]

    def test_no_seek_is_asked_of_a_video_that_has_not_opened(self, room):
        room.says()
        room.arrival.turn()
        room.follower.duration_ms = 0.0
        room.arrival.turn()
        assert room.follower.seeks == []

    def test_it_leans_on_the_players_rate_and_leaves_the_rooms_rate_alone(self, room):
        room.says()
        room.follower.video = VIDEO
        room.follower.position_ms = 3_800.0
        for _ in range(10):
            room.arrival.turn()
        assert room.follower.leans[-1] > 1.0
        assert room.follower.speed == 1.0

    def test_it_takes_the_rooms_rate(self, room):
        room.says(speed=1.5)
        room.follower.video = VIDEO
        room.arrival.turn()
        assert room.follower.speed == 1.5

    def test_it_takes_the_rooms_lock(self, room):
        room.says(locked=False)
        room.follower.video = VIDEO
        room.arrival.turn()
        assert room.follower.locked is False

    def test_the_rest_of_what_the_room_says_is_handed_on_every_turn(self, room):
        room.says(extra="tcode=0\n")
        room.arrival.turn()
        assert room.follower.mirrored[-1]["tcode"] == "0"

    def test_it_says_when_it_is_in_step(self, room):
        room.held_in_step()
        assert Crossing(room.state, ["portrait"]).everyone_in_step

    def test_an_ordinary_launch_follows_nobody(self, tmp_path):
        here = _room(tmp_path, arriving=False)
        here.says()
        here.arrival.turn()
        assert here.follower.opened == []
        assert here.follower.mirrored == []


class TestTakingTheRoom:
    def test_it_waits_to_be_told(self, room):
        room.held_in_step()
        assert room.arrival.arriving
        assert room.follower.took == []

    def test_it_takes_the_room_with_what_the_room_last_said(self, room):
        room.held_in_step()
        room.says(extra="volume=40\n")
        room.told_to_take_it()
        assert room.follower.took[-1]["volume"] == "40"

    def test_it_answers(self, room):
        room.held_in_step()
        room.told_to_take_it()
        assert Crossing(room.state, ["portrait"]).everyone_has_the_room

    def test_it_follows_nothing_after(self, room):
        room.held_in_step()
        room.told_to_take_it()
        room.says(video=str(Path("C:/library/scene two.mp4")))
        room.arrival.turn()
        assert room.follower.opened == []
        assert not room.arrival.arriving


def test_a_player_that_is_not_ready_is_never_in_step(tmp_path):
    """A headset player routes its sound only once it is worn, and until it has
    it has nothing to hand the room's sound to."""
    follower = _Follower()
    arrival = Arrival(
        arriving=True,
        follower=follower,
        room_status=tmp_path / "portrait_status.txt",
        command_file=tmp_path / "portrait_cmd.txt",
        ready=lambda: False,
        clock=lambda: NOW,
    )
    room = _Room(arrival, follower, tmp_path)
    room.held_in_step()
    assert not Crossing(tmp_path, ["portrait"]).everyone_in_step
