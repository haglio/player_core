"""A Genau arriving beside the one that has the room: following it, then taking it."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from player_core.clip_advance import ClipAdvanceState
from player_core.crossing import Crossing
from player_core.cruise_control import CruiseControlState
from player_core.drive_readout import DriveHud, publish_drive
from player_core.flag import Flag
from player_core.genau_arrival import GenauArrival
from player_core.genau_controls import GenauControls
from player_core.learned_motion import LearnedMotionState
from player_core.robot_hand import (
    RobotHandState,
    WaveformShape,
    phase_for_position_fraction,
)
from player_core.robot_hand_beat import BeatEngine
from player_core.tcode import POSITION_MAX

ONE = Path("C:/clips/one.mp4")
TWO = Path("C:/clips/two.mp4")


class FakeSelection:
    def __init__(self, holds=(ONE, TWO)):
        self.holds = [str(clip).lower() for clip in holds]
        self.followed: list[Path] = []

    def follow(self, clip: Path) -> bool:
        if str(clip).lower() not in self.holds:
            return False
        self.followed.append(clip)
        return True


class FakeRenderer:
    def __init__(self, clip: Path = ONE, *, decoded: bool = True):
        self.current_clip_path = clip
        self.decoded = decoded

    def current_clip_entry(self):
        return {"frames": ["f0"]} if self.decoded else None


class FakeSender:
    def __init__(self):
        self.let_go_position: int | None = None
        self.phases: list[float] = []
        self.eased = 0

    def set_motion_phase(self, phase: float) -> None:
        self.phases.append(phase)

    def ease_in(self) -> None:
        self.eased += 1


def _controls(**over) -> GenauControls:
    return GenauControls(
        engine=BeatEngine(phase=0.0, last_tick=0.0),
        paused=Flag(),
        step_clip=lambda _step: None,
        robot_hand=over.get("hand") or RobotHandState(speed=50, amplitude=100, center=50),
        cruise_control_state=over.get("cruise") or CruiseControlState(),
        learned_motion_state=over.get("learned") or LearnedMotionState(model=None),
        clip_advance_state=over.get("advance") or ClipAdvanceState(interval=20),
    )


class _Room:
    def __init__(self, state: Path, *, selection=None, renderer=None, controls=None):
        self.state = state
        self.drive_file = state / "genau_drive.txt"
        self.status_file = state / "genau_status.txt"
        self.selection = selection or FakeSelection()
        self.renderer = renderer or FakeRenderer()
        self.controls = controls or _controls()
        self.sender = FakeSender()
        self.let_go_calls = 0
        self.arrival = GenauArrival(
            controls=self.controls,
            selection=self.selection,
            renderer=self.renderer,
            tcode_sender=self.sender,
            drive_file=self.drive_file,
            status_file=self.status_file,
        )

    def says(self, *, clip: Path = ONE, playing: bool = True, cruise: bool = False,
             learned: bool = False, locked: bool = True, interval: int = 20,
             drive: DriveHud | None = None) -> None:
        self.status_file.write_text(
            f"cruise={int(cruise)}\nlearned={int(learned)}\nlocked={int(locked)}\n"
            f"clip={clip}\nshape=sine\nplaying={int(playing)}\ninterval={interval}\n",
            encoding="utf-8")
        publish_drive(self.drive_file, drive or DriveHud(speed=50, amplitude=100, center=50))

    def let_go(self) -> None:
        self.let_go_calls += 1


@pytest.fixture
def room(tmp_path) -> _Room:
    return _Room(tmp_path)


class TestFollowingTheClip:
    def test_it_goes_to_the_clip_the_room_shows(self, room):
        room.says(clip=TWO)
        room.arrival.follow()
        assert room.selection.followed == [TWO]

    def test_the_clip_it_already_shows_is_left_alone(self, room):
        room.says(clip=ONE)
        room.arrival.follow()
        assert room.selection.followed == []

    def test_a_clip_it_does_not_hold_is_asked_for_once(self, tmp_path):
        room = _Room(tmp_path, selection=FakeSelection(holds=(ONE,)))
        room.says(clip=TWO)
        room.arrival.follow()
        room.arrival.follow()
        assert room.selection.followed == []


class TestFollowingTheMotion:
    def test_it_takes_the_rooms_dials(self, room):
        room.says(drive=DriveHud(speed=80, amplitude=40, center=30, shape="triangle"))
        room.arrival.follow()
        hand = room.controls.robot_hand
        assert (hand.speed, hand.amplitude, hand.center, hand.shape) == (
            80, 40, 30, WaveformShape.TRIANGLE)

    def test_it_moves_when_the_room_moves(self, room):
        room.says(playing=True)
        room.arrival.follow()
        assert room.controls.robot_hand.playing is True

    def test_it_stops_when_the_room_stops(self, room):
        room.controls.robot_hand.playing = True
        room.says(playing=False)
        room.arrival.follow()
        assert room.controls.robot_hand.playing is False

    def test_it_takes_cruise_control(self, room):
        room.says(cruise=True)
        room.arrival.follow()
        assert room.controls.cruise_control_state.active is True

    def test_it_takes_the_lock_and_the_seconds_a_clip_holds(self, room):
        room.says(locked=False, interval=33)
        room.arrival.follow()
        advance = room.controls.clip_advance_state
        assert (advance.locked, advance.interval) == (False, 33)

    def test_a_room_that_has_said_nothing_moves_nothing(self, room):
        before = replace(room.controls.robot_hand)
        room.arrival.follow()
        assert room.controls.robot_hand == before


class TestWhenItIsInStep:
    def _in_step(self, room) -> bool:
        return Crossing(room.state, ["genau"]).everyone_in_step

    def test_on_the_rooms_clip_and_decoded(self, room):
        room.says(clip=ONE)
        room.arrival.follow()
        assert self._in_step(room)

    def test_not_while_its_clip_is_still_decoding(self, tmp_path):
        room = _Room(tmp_path, renderer=FakeRenderer(decoded=False))
        room.says(clip=ONE)
        room.arrival.follow()
        assert not self._in_step(room)

    def test_not_while_it_is_on_another_clip(self, tmp_path):
        room = _Room(tmp_path, renderer=FakeRenderer(clip=ONE))
        room.says(clip=TWO)
        room.arrival.follow()
        assert not self._in_step(room)

    def test_a_clip_it_cannot_show_does_not_hold_the_crossing_up(self, tmp_path):
        room = _Room(tmp_path, selection=FakeSelection(holds=(ONE,)))
        room.says(clip=TWO)
        room.arrival.follow()
        assert self._in_step(room)

    def test_not_while_one_of_them_is_still_climbing_out_of_the_park(self, room):
        room.says(drive=DriveHud(speed=50, amplitude=100, center=50, let_go=0.4))
        room.arrival.follow()
        assert not self._in_step(room)


class TestTakingTheRoom:
    def test_it_waits_to_be_told(self, room):
        room.says()
        room.arrival.follow()
        assert room.arrival.told_to_take_the_room is False
        Crossing(room.state, ["genau"]).say_take_the_room()
        assert room.arrival.told_to_take_the_room is True

    def test_the_motion_picks_up_where_the_rooms_device_is(self, room):
        room.says(drive=DriveHud(speed=50, amplitude=100, center=50, position=2500,
                                 waveform=(0.25, 0.3, 0.35)))
        room.arrival.take_the_room(room.let_go)
        assert room.sender.phases == [pytest.approx(phase_for_position_fraction(
            2500 / POSITION_MAX, rising=True))]

    def test_on_its_way_down_if_the_room_was(self, room):
        room.says(drive=DriveHud(speed=50, amplitude=100, center=50, position=2500,
                                 waveform=(0.25, 0.2, 0.15)))
        room.arrival.take_the_room(room.let_go)
        assert room.sender.phases == [pytest.approx(phase_for_position_fraction(
            2500 / POSITION_MAX, rising=False))]

    def test_a_motion_of_its_own_making_keeps_its_own_start(self, room):
        room.controls.cruise_control_state.active = True
        room.says(cruise=True, drive=DriveHud(position=2500, waveform=(0.25, 0.3)))
        room.arrival.take_the_room(room.let_go)
        assert room.sender.phases == []

    def test_its_first_moves_meet_the_device(self, room):
        room.says()
        room.arrival.take_the_room(room.let_go)
        assert room.sender.eased == 1

    def test_it_lets_go_then_answers(self, room):
        room.says()
        room.arrival.take_the_room(room.let_go)
        assert room.let_go_calls == 1
        assert Crossing(room.state, ["genau"]).everyone_has_the_room


def test_the_clip_on_screen_is_matched_whatever_its_case(tmp_path):
    """The path comes back through a file another process wrote."""
    room = _Room(tmp_path, renderer=FakeRenderer(clip=Path("C:/CLIPS/ONE.MP4")))
    room.says(clip=ONE)
    room.arrival.follow()
    assert room.selection.followed == []


def test_a_genau_built_without_cruise_or_learned_motion_follows_the_rest(tmp_path):
    controls = GenauControls(
        engine=BeatEngine(phase=0.0, last_tick=0.0),
        paused=Flag(),
        step_clip=lambda _step: None,
        robot_hand=RobotHandState(),
    )
    room = _Room(tmp_path, controls=controls)
    room.says(cruise=True, learned=True, playing=True)
    room.arrival.follow()
    assert controls.robot_hand.playing is True
