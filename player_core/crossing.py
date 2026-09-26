"""One player taking over another's room without stopping it.

The arriving player follows the clock of the player that has the room, says when
it is in step, and takes the room when told; the flags it says so through sit
beside the status file it will publish.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from .status import parse_status

__all__: list[str] = []

DEADBAND_MS = 15.0  # a position read is up to a frame old at either end
IN_STEP_MS = 40.0  # a frame of the slowest video: a takeover inside it is not seen
SEEK_MS = 400.0
SEEK_LEAD_MS = 150.0  # a seek lands a moment after it is asked for
WIDE_S = 0.25
ELSEWHERE_S = 0.6  # three status writes: long enough for both rooms to roll over
LEAN_OVER_MS = 2_000.0
LEAN_LIMIT = 0.05
SMOOTHING = 0.25
STEADY_S = 0.5

_TAKE_THE_ROOM = "crossing_take_the_room.flag"
_IN_STEP = "_in_step.flag"
_HAS_THE_ROOM = "_has_the_room.flag"


@dataclass(frozen=True)
class RoomClock:
    video: str = ""
    position_ms: float = 0.0
    said_at: float = 0.0  # when the room read the playhead it published
    paused: bool = False
    speed: float = 1.0
    locked: bool = False

    def position_at(self, now: float) -> float:
        if self.paused:
            return self.position_ms
        return self.position_ms + max(0.0, now - self.said_at) * 1000.0 * self.speed


@dataclass(frozen=True)
class Step:
    open: str = ""
    seek_ms: float | None = None
    speed: float | None = None
    locked: bool | None = None


class KeepingStep:
    def __init__(self, *, steady_s: float = STEADY_S) -> None:
        self._steady_s = steady_s
        self._drift: float | None = None
        self._wide_since: float | None = None
        self._elsewhere_since: float | None = None
        self._steady_since: float | None = None
        self._followed_something = False
        self._in_step = False
        self._opening = False

    @property
    def in_step(self) -> bool:
        return self._in_step

    def turn(
        self,
        room: RoomClock,
        *,
        video: str,
        position_ms: float,
        paused: bool,
        now: float,
        locked: bool = False,
    ) -> Step:
        if not room.video:
            return Step()
        if video != room.video:
            return self._somewhere_else(room, now)
        self._elsewhere_since = None
        self._followed_something = True
        following = Step(locked=room.locked if room.locked != locked else None)
        target = room.position_at(now)
        if self._opening:
            self._opening = False
            return replace(following, seek_ms=target + SEEK_LEAD_MS)
        drift = position_ms - target
        if abs(drift) > SEEK_MS:
            return self._too_wide_to_walk(following, room, target, now)
        self._wide_since = None
        self._drift = drift if self._drift is None else (
            (1 - SMOOTHING) * self._drift + SMOOTHING * drift)
        self._hold(now, keeping=abs(self._drift) <= IN_STEP_MS and room.paused == paused)
        return replace(following, speed=room.speed * (1 - self._lean()))

    def _somewhere_else(self, room: RoomClock, now: float) -> Step:
        """The room names another video, which is where both are about to be:
        the two roll onto the next clip a moment apart, and the one that rolls
        first would otherwise reload the clip the other is finishing — then the
        next one again the moment the room says so.  A player that has followed
        nothing yet has no clip of its own to roll, so it opens at once."""
        self._out_of_step()
        if self._elsewhere_since is None:
            self._elsewhere_since = now
        if self._followed_something and now - self._elsewhere_since < ELSEWHERE_S:
            return Step()
        self._start_again()
        self._opening = True
        return Step(open=room.video)

    def _too_wide_to_walk(
        self, following: Step, room: RoomClock, target: float, now: float,
    ) -> Step:
        """A reading a seek away from the room — a jump, or a clip rolling over
        under a player that has not noticed yet.  Either way it is left out of
        the smoothing, which would take seconds to walk back off one of them,
        and the seek waits for the gap to still be there a moment later."""
        self._out_of_step()
        if self._wide_since is None:
            self._wide_since = now
        if now - self._wide_since < WIDE_S:
            return replace(following, speed=room.speed * (1 - self._lean()))
        self._start_again()
        return replace(following, seek_ms=target + SEEK_LEAD_MS)

    def _hold(self, now: float, *, keeping: bool) -> None:
        if not keeping:
            self._out_of_step()
            return
        if self._steady_since is None:
            self._steady_since = now
        self._in_step = now - self._steady_since >= self._steady_s

    def _out_of_step(self) -> None:
        self._steady_since = None
        self._in_step = False

    def _lean(self) -> float:
        if self._drift is None or abs(self._drift) <= DEADBAND_MS:
            return 0.0
        return max(-LEAN_LIMIT, min(LEAN_LIMIT, self._drift / LEAN_OVER_MS))

    def _start_again(self) -> None:
        self._drift = None
        self._wide_since = None
        self._elsewhere_since = None
        self._out_of_step()


def read_the_room(status_file: Path) -> tuple[RoomClock, dict[str, str]]:
    try:
        with Path(status_file).open(encoding="utf-8") as status:
            text = status.read()
            written_at = os.fstat(status.fileno()).st_mtime  # the handle's, not a newer file's
    except OSError:
        return RoomClock(), {}
    fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    said = parse_status(fields)
    return RoomClock(
        video=str(Path(said.video)) if said.video else "",
        position_ms=float(said.position_ms),
        said_at=said.read_at or written_at,
        paused=said.paused,
        speed=said.speed,
        locked=said.locked,
    ), fields


class HeldSink:
    def __init__(self, sink, *, held: bool = True) -> None:
        self._sink = sink
        self._held = held

    def send(self, command: str) -> None:
        if not self._held:
            self._sink.send(command)

    def let_go(self) -> None:
        self._held = False

    def close(self) -> None:
        self._sink.close()


def follow_channel(path: Path) -> Path:
    return path.with_name(f"{path.stem}.follow{path.suffix}")


def name_in_a_crossing(status_file: Path) -> str:
    return Path(status_file).stem.removesuffix("_status")


def _raise(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


class ArrivingPlayer:
    def __init__(self, state_dir: Path, who: str) -> None:
        self._in_step = Path(state_dir) / f"crossing_{who}{_IN_STEP}"
        self._has_the_room = Path(state_dir) / f"crossing_{who}{_HAS_THE_ROOM}"
        self._take_the_room = Path(state_dir) / _TAKE_THE_ROOM

    @classmethod
    def for_status_file(cls, status_file: Path) -> ArrivingPlayer:
        return cls(Path(status_file).parent, name_in_a_crossing(status_file))

    def in_step(self, yes: bool) -> None:
        if yes:
            _raise(self._in_step)
        else:
            self._in_step.unlink(missing_ok=True)

    @property
    def take_the_room_now(self) -> bool:
        return self._take_the_room.exists()

    def took_the_room(self) -> None:
        _raise(self._has_the_room)


class Crossing:
    def __init__(self, state_dir: Path, arriving: Iterable[str]) -> None:
        self._state_dir = Path(state_dir)
        self._arriving = tuple(arriving)

    def begin(self) -> None:
        self._clear()

    def finish(self) -> None:
        self._clear()

    @property
    def everyone_in_step(self) -> bool:
        return self._all_raised(_IN_STEP)

    def say_take_the_room(self) -> None:
        _raise(self._state_dir / _TAKE_THE_ROOM)

    @property
    def everyone_has_the_room(self) -> bool:
        return self._all_raised(_HAS_THE_ROOM)

    def _all_raised(self, suffix: str) -> bool:
        return all((self._state_dir / f"crossing_{who}{suffix}").exists()
                   for who in self._arriving)

    def _clear(self) -> None:
        for path in (*self._state_dir.glob(f"crossing_*{_IN_STEP}"),
                     *self._state_dir.glob(f"crossing_*{_HAS_THE_ROOM}"),
                     self._state_dir / _TAKE_THE_ROOM):
            path.unlink(missing_ok=True)


class Follower(Protocol):
    video: str
    position_ms: float
    duration_ms: float
    paused: bool
    locked: bool
    speed: float

    def open(self, video: str, room: Mapping[str, str]) -> None: ...
    def seek_to(self, position_ms: float) -> None: ...
    def set_locked(self, locked: bool) -> None: ...
    def set_speed(self, speed: float) -> None: ...
    def lean(self, speed: float) -> None: ...
    def mirror(self, room: Mapping[str, str]) -> None: ...
    def take_the_room(self, room: Mapping[str, str]) -> None: ...


class Arrival:
    def __init__(
        self,
        *,
        arriving: bool,
        follower: Follower,
        room_status: Path,
        command_file: Path,
        ready: Callable[[], bool] = lambda: True,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._follower = follower
        self._crossing = ArrivingPlayer.for_status_file(room_status) if arriving else None
        self._room_status = room_status
        self._command_file = command_file
        self._ready = ready
        self._clock = clock
        self._keeping = KeepingStep()
        self.arriving = arriving

    @property
    def command_file(self) -> Path:
        return follow_channel(self._command_file) if self.arriving else self._command_file

    def turn(self) -> None:
        if not self.arriving:
            return
        room, said = read_the_room(self._room_status)
        self._follow(room, said)
        self._crossing.in_step(self._keeping.in_step and self._ready())
        if self._crossing.take_the_room_now:
            self.arriving = False
            self._follower.take_the_room(said)
            self._crossing.took_the_room()

    def _follow(self, room: RoomClock, said: Mapping[str, str]) -> None:
        follower = self._follower
        follower.mirror(said)
        if room.speed != follower.speed:
            follower.set_speed(room.speed)
        if follower.video == room.video and follower.duration_ms <= 0:
            return
        step = self._keeping.turn(
            room, video=follower.video, position_ms=follower.position_ms,
            paused=follower.paused, now=self._clock(), locked=follower.locked)
        if step.open:
            follower.open(step.open, said)
        if step.seek_ms is not None:
            follower.seek_to(step.seek_ms)
        if step.locked is not None:
            follower.set_locked(step.locked)
        if step.speed is not None:
            follower.lean(step.speed)
