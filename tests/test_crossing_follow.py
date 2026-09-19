"""The arithmetic of one player holding itself to another's clock."""
from __future__ import annotations

import pytest

from player_core.crossing import (
    ELSEWHERE_S,
    IN_STEP_MS,
    SEEK_LEAD_MS,
    STEADY_S,
    WIDE_S,
    KeepingStep,
    RoomClock,
)


def _turns(keeping: KeepingStep, room: RoomClock, position_ms: float, *,
           now: float, turns: int, video: str = "clip.mp4", paused: bool = False):
    """Hold the same position for *turns* turns, returning the last step."""
    step = None
    for _ in range(turns):
        step = keeping.turn(room, video=video, position_ms=position_ms,
                            paused=paused, now=now)
    return step


PAST_THE_MOMENT = ELSEWHERE_S + 0.01  # a hair past, so the float arithmetic cannot land short


def _elsewhere(keeping: KeepingStep, room: RoomClock, *, seconds: float, from_now: float = 10.0,
               video: str = "mine.mp4", every: float = 0.05):
    """Turn for *seconds* with the room on a video this player is not on."""
    return _holding(keeping, room, seconds=seconds, from_now=from_now, video=video, every=every)


def _holding(keeping: KeepingStep, room: RoomClock, *, seconds: float, offset_ms: float = 0.0,
             from_now: float = 10.0, every: float = 0.05, video: str = "clip.mp4",
             paused: bool = False):
    """Keep *offset_ms* off the room's clock for *seconds*, a turn every *every*."""
    step = None
    for turn in range(int(round(seconds / every)) + 1):
        now = from_now + turn * every
        step = keeping.turn(room, video=video, position_ms=room.position_at(now) + offset_ms,
                            paused=paused, now=now)
    return step


class TestWhereTheRoomIs:
    def test_a_playing_room_has_moved_on_since_it_said_so(self):
        room = RoomClock(video="clip.mp4", position_ms=10_000, said_at=100.0)
        assert room.position_at(100.5) == pytest.approx(10_500)

    def test_a_paused_room_is_where_it_said_it_was(self):
        room = RoomClock(video="clip.mp4", position_ms=10_000, said_at=100.0, paused=True)
        assert room.position_at(105.0) == pytest.approx(10_000)

    def test_a_room_at_double_speed_has_moved_twice_as_far(self):
        room = RoomClock(video="clip.mp4", position_ms=10_000, said_at=100.0, speed=2.0)
        assert room.position_at(100.5) == pytest.approx(11_000)

    def test_a_clock_read_before_it_was_written_is_read_as_now(self):
        """Two processes' clocks agree to milliseconds, not exactly; a stamp a
        hair in the future must not wind the position backwards."""
        room = RoomClock(video="clip.mp4", position_ms=10_000, said_at=100.0)
        assert room.position_at(99.9) == pytest.approx(10_000)


class TestOpeningWhatTheRoomIsPlaying:
    def test_a_different_video_is_opened(self):
        keeping = KeepingStep()
        room = RoomClock(video="theirs.mp4", position_ms=4_000, said_at=10.0)
        _elsewhere(keeping, room, seconds=ELSEWHERE_S / 2)
        step = keeping.turn(room, video="mine.mp4", position_ms=0, paused=False,
                            now=10.0 + PAST_THE_MOMENT)
        assert step.open == "theirs.mp4"

    def test_the_room_is_given_a_moment_to_say_it_has_moved_on_too(self):
        """Both rooms roll onto the next clip within a moment of each other, and
        the one that rolls first sees the other still on the clip it just left.
        Reopening that one there and then is a reload of a clip it is about to
        leave — and another the moment the room says so."""
        keeping = KeepingStep()
        room = RoomClock(video="theirs.mp4", position_ms=4_000, said_at=10.0)
        step = _elsewhere(keeping, room, seconds=ELSEWHERE_S / 2)
        assert step.open == ""

    def test_a_room_that_catches_up_within_that_moment_is_never_reopened(self):
        keeping = KeepingStep()
        room = RoomClock(video="theirs.mp4", position_ms=4_000, said_at=10.0)
        _elsewhere(keeping, room, seconds=ELSEWHERE_S / 2)
        step = _holding(keeping, room, seconds=ELSEWHERE_S, from_now=10.0 + ELSEWHERE_S / 2,
                        video="theirs.mp4")
        assert step.open == ""

    def test_nothing_is_opened_twice(self):
        keeping = KeepingStep()
        room = RoomClock(video="theirs.mp4", position_ms=4_000, said_at=10.0)
        _elsewhere(keeping, room, seconds=ELSEWHERE_S / 2)
        keeping.turn(room, video="mine.mp4", position_ms=0, paused=False,
                     now=10.0 + PAST_THE_MOMENT)
        step = keeping.turn(room, video="theirs.mp4", position_ms=0, paused=False,
                            now=10.0 + PAST_THE_MOMENT + 0.05)
        assert step.open == ""

    def test_the_room_playing_nothing_yet_asks_for_nothing(self):
        keeping = KeepingStep()
        step = keeping.turn(RoomClock(), video="mine.mp4", position_ms=0,
                            paused=False, now=10.0)
        assert step.open == ""
        assert step.seek_ms is None

    def test_a_video_just_opened_is_seeked_to_where_the_room_is(self):
        keeping = KeepingStep()
        room = RoomClock(video="theirs.mp4", position_ms=4_000, said_at=10.0)
        _elsewhere(keeping, room, seconds=ELSEWHERE_S / 2)
        keeping.turn(room, video="mine.mp4", position_ms=0, paused=False,
                     now=10.0 + PAST_THE_MOMENT)
        landed_at = 10.0 + PAST_THE_MOMENT + 0.05
        step = keeping.turn(room, video="theirs.mp4", position_ms=0, paused=False, now=landed_at)
        assert step.seek_ms == pytest.approx(room.position_at(landed_at) + SEEK_LEAD_MS)


class TestHoldingTheClock:
    def test_a_player_already_there_is_left_alone(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0)
        step = keeping.turn(room, video="clip.mp4", position_ms=4_000, paused=False, now=10.0)
        assert step.seek_ms is None
        assert step.speed == pytest.approx(1.0)

    def test_a_small_drift_leans_on_the_speed_rather_than_seeking(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0)
        step = _turns(keeping, room, 4_200, now=10.0, turns=10)
        assert step.seek_ms is None
        assert step.speed < 1.0  # ahead of the room, so ease off

    def test_a_player_behind_the_room_leans_the_other_way(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0)
        step = _turns(keeping, room, 3_800, now=10.0, turns=10)
        assert step.speed > 1.0

    def test_the_lean_is_bounded(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0)
        step = _turns(keeping, room, 3_650, now=10.0, turns=20)
        assert step.speed == pytest.approx(1.05)

    def test_the_lean_rides_the_rooms_own_rate(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0, speed=2.0)
        step = _turns(keeping, room, 3_650, now=10.0, turns=20)
        assert step.speed == pytest.approx(2.1)

    def test_a_gap_too_wide_to_walk_is_seeked(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=40_000, said_at=10.0)
        step = _holding(keeping, room, seconds=WIDE_S, offset_ms=-36_000)
        assert step.seek_ms == pytest.approx(room.position_at(10.0 + WIDE_S) + SEEK_LEAD_MS)

    def test_a_gap_that_is_gone_a_moment_later_is_not_seeked(self):
        """Counted in seconds rather than readings, because the players' loops
        run anywhere from four times a second to sixty: a clip rolling over
        under a player that has not noticed reads as a whole video of drift for
        a turn or two, and seeking on it would undo a follower that is fine."""
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0)
        step = _holding(keeping, room, seconds=WIDE_S / 2, offset_ms=36_000)
        assert step.seek_ms is None

    def test_a_stray_reading_is_left_out_of_the_smoothing(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0)
        _holding(keeping, room, seconds=STEADY_S)
        keeping.turn(room, video="clip.mp4", position_ms=40_000, paused=False, now=10.6)
        step = _holding(keeping, room, seconds=0.1, from_now=10.65)
        assert step.speed == pytest.approx(1.0)  # nothing to walk back off


class TestFollowingTheLock:
    def test_the_lock_comes_across_so_the_video_ends_the_same_way(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0, locked=True)
        assert keeping.turn(room, video="clip.mp4", position_ms=4_000,
                            paused=False, now=10.0).locked is True

    def test_the_lock_is_said_once(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0, locked=True)
        keeping.turn(room, video="clip.mp4", position_ms=4_000, paused=False, now=10.0)
        step = keeping.turn(room, video="clip.mp4", position_ms=4_000,
                            paused=False, now=10.0, locked=True)
        assert step.locked is None


class TestWhenItIsInStep:
    def test_a_follower_that_has_just_opened_is_not_in_step(self):
        keeping = KeepingStep()
        room = RoomClock(video="theirs.mp4", position_ms=4_000, said_at=10.0)
        keeping.turn(room, video="mine.mp4", position_ms=0, paused=False, now=10.0)
        assert keeping.in_step is False

    def test_it_takes_a_stretch_of_holding_the_clock_measured_in_seconds(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0)
        _holding(keeping, room, seconds=STEADY_S - 0.1)
        assert keeping.in_step is False
        _holding(keeping, room, seconds=0.1, from_now=10.0 + STEADY_S - 0.1)
        assert keeping.in_step is True

    def test_drifting_out_again_takes_the_answer_back(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0)
        _holding(keeping, room, seconds=STEADY_S)
        assert keeping.in_step is True
        _holding(keeping, room, seconds=STEADY_S, from_now=11.0, offset_ms=10 * IN_STEP_MS)
        assert keeping.in_step is False

    def test_a_follower_within_a_frame_is_in_step_and_still_walks_back(self):
        """In step is a frame of the slowest video, which is as much as a
        takeover can be out by unseen; the lean goes on closing anything wider
        than the noise in a position read."""
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0)
        step = _holding(keeping, room, seconds=STEADY_S, offset_ms=IN_STEP_MS - 1)
        assert keeping.in_step is True
        assert step.speed < 1.0

    def test_a_room_playing_a_video_this_player_has_not_opened_is_not_in_step(self):
        keeping = KeepingStep()
        room = RoomClock(video="theirs.mp4", position_ms=4_000, said_at=10.0)
        _holding(keeping, room, seconds=STEADY_S, video="mine.mp4")
        assert keeping.in_step is False

    def test_a_paused_room_is_in_step_once_the_follower_is_paused_on_the_spot(self):
        keeping = KeepingStep()
        room = RoomClock(video="clip.mp4", position_ms=4_000, said_at=10.0, paused=True)
        _holding(keeping, room, seconds=STEADY_S, paused=True)
        assert keeping.in_step is True
