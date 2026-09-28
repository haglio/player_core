from __future__ import annotations

import math
import random
from dataclasses import dataclass

__all__: list[str] = []

ZOOMED_IN = 1.10

CLOSEST_AIM = 8.0


@dataclass(frozen=True)
class View:
    zoom: float = 1.0
    align_x: float = 0.0
    align_y: float = 0.0

    def placement(self) -> tuple[float, float, float]:
        return math.log2(self.zoom), self.align_x, self.align_y


@dataclass(frozen=True)
class Move:
    start: View
    end: View

    def at(self, progress: float) -> View:
        return View(self.start.zoom * (self.end.zoom / self.start.zoom) ** progress,
                    _between(self.start.align_x, self.end.align_x, progress),
                    _between(self.start.align_y, self.end.align_y, progress))


STANDSTILL = Move(View(), View())


def _between(start: float, end: float, progress: float) -> float:
    return start + (end - start) * progress


def zoom_in(align_x: float, align_y: float) -> Move:
    return Move(View(1.0, align_x, align_y), View(ZOOMED_IN, align_x, align_y))


def zoom_out(align_x: float, align_y: float) -> Move:
    return Move(View(ZOOMED_IN, align_x, align_y), View(1.0, align_x, align_y))


def pan(align_x: float, align_y: float) -> Move:
    return Move(View(ZOOMED_IN, align_x, align_y), View(ZOOMED_IN, -align_x, -align_y))


class Moves:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._last = None

    def deal(self) -> Move:
        kind = self._rng.choice([kind for kind in (zoom_in, zoom_out, pan) if kind is not self._last])
        self._last = kind
        return pan(*self._corner()) if kind is pan else kind(*self._spot())

    def from_rest(self) -> Move:
        self._last = zoom_in
        return zoom_in(*self._spot())

    def _spot(self) -> tuple[float, float]:
        return self._rng.uniform(-1.0, 1.0), self._rng.uniform(-1.0, 1.0)

    def _corner(self) -> tuple[float, float]:
        return self._rng.choice((-1.0, 1.0)), self._rng.choice((-1.0, 1.0))


@dataclass(frozen=True)
class Fit:
    window: tuple[int, int]
    shown: tuple[int, int]
    tiles: int = 1

    def framing(self, part: tuple[float, float, float, float]) -> View:
        x0, y0, x1, y1 = (min(max(edge, 0.0), 1.0) for edge in part)
        middle_tile = self.tiles // 2
        x0, x1 = (middle_tile + x0) / self.tiles, (middle_tile + x1) / self.tiles
        room_x, room_y = self._room()
        zoom = min(CLOSEST_AIM, _fitting(room_x, x1 - x0), _fitting(room_y, y1 - y0))
        return View(zoom, _align_centering((x0 + x1) / 2, room_x, zoom), _align_centering((y0 + y1) / 2, room_y, zoom))

    def _room(self) -> tuple[float, float]:
        fitted = self._fitted()
        if fitted is None:
            return 1.0, 1.0
        return self.window[0] / fitted[0], self.window[1] / fitted[1]

    def _fitted(self) -> tuple[float, float] | None:
        (window_w, window_h), (shown_w, shown_h) = self.window, self.shown
        if not (window_w and window_h and shown_w and shown_h):
            return None
        scale = min(window_w / shown_w, window_h / shown_h)
        return shown_w * scale, shown_h * scale


def _fitting(room: float, part: float) -> float:
    return room / part if part > 0 else math.inf


def _align_centering(middle: float, room: float, zoom: float) -> float:
    if zoom <= room:
        return 0.0
    return max(-1.0, min(1.0, 2.0 * (room / 2.0 - middle * zoom) / (room - zoom) - 1.0))


class RoomClock:
    def __init__(self) -> None:
        self._lost_s = 0.0
        self._frozen_at_s: float | None = None

    def read(self, now_s: float) -> float:
        return (now_s if self._frozen_at_s is None else self._frozen_at_s) - self._lost_s

    def freeze(self, now_s: float) -> None:
        if self._frozen_at_s is None:
            self._frozen_at_s = now_s

    def thaw(self, now_s: float) -> None:
        if self._frozen_at_s is not None:
            self._lost_s += now_s - self._frozen_at_s
            self._frozen_at_s = None


@dataclass(frozen=True)
class Aim:
    move: Move
    started_s: float
    seconds: float

    def at(self, clock_s: float) -> View:
        if clock_s >= self.started_s + self.seconds:
            return self.move.end
        done = (clock_s - self.started_s) / self.seconds
        return self.move.at(done * done * (3.0 - 2.0 * done))


class KenBurns:
    def __init__(self, moves: Moves | None = None) -> None:
        self._moves = moves or Moves()
        self._clock = RoomClock()
        self._move = STANDSTILL
        self._pace_s = 0.0
        self._started_s = 0.0
        self._held_progress = 0.0
        self._looping = False
        self._aim: Aim | None = None

    @property
    def pace_s(self) -> float:
        return self._pace_s

    def set_looping(self, looping: bool) -> None:
        self._looping = looping

    def set_pace(self, seconds: float, now_s: float) -> None:
        reached = self._progress(now_s)
        if seconds and self._move is STANDSTILL:
            self._move = self._moves.from_rest()
        self._pace_s = seconds
        if seconds:
            self._started_s = self._clock.read(now_s) - reached * seconds
        else:
            self._held_progress = reached

    def new_picture(self, now_s: float) -> None:
        self._aim = None
        self._move = self._moves.deal() if self._pace_s else STANDSTILL
        self._started_s = self._clock.read(now_s)
        self._held_progress = 0.0

    def set_paused(self, paused: bool, now_s: float) -> None:
        if paused:
            self._clock.freeze(now_s)
        else:
            self._clock.thaw(now_s)

    def aim(self, target: View, seconds: float, now_s: float) -> None:
        self._aim = Aim(Move(self.view(now_s), target), self._clock.read(now_s), seconds)

    def view(self, now_s: float) -> View:
        if self._aim is not None:
            return self._aim.at(self._clock.read(now_s))
        return self._move.at(self._progress(now_s))

    def ran_out(self, now_s: float) -> bool:
        return bool(self._pace_s) and self._progress(now_s) >= 1.0

    def _progress(self, now_s: float) -> float:
        if not self._pace_s:
            return self._held_progress
        progress = (self._clock.read(now_s) - self._started_s) / self._pace_s
        return progress % 1.0 if self._looping else min(progress, 1.0)
