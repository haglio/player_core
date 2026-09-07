"""Hands-free variation of the motion — the Robot Hand's cruise control, shared.

It lives beside :mod:`player_core.robot_hand` because the state it varies is
that one's: an app that has the motion gets this with it, rather than growing
its own idea of what "vary it for me" means.

What it hands the device is :mod:`player_core.wave_stack`'s — waves summed, each
with its own travel, center and speed. This is the part with the dice in it. It
decides how many waves there are and how far below the main one the others run,
and then never stops: every ramp that arrives somewhere is given somewhere else
to be, over its own stretch of seconds, so no dial in the motion is ever simply
a number.

Four things it is careful about.

**Every range is pinned to the dials you set.** The speed, the travel and the
center the motion had when this took it over are kept as anchors, and every draw
here is an excursion around one of them rather than a draw from the axis at
large. Nothing accumulates: the tenth minute is drawn from the same ranges as
the first, so an hour of cruising is still recognizably the motion you asked
for, at a pace within sight of the one you set. Only a hand on a dial moves an
anchor, and it moves it by exactly what the hand turned.

**What rides on what.** The first wave *is* the motion: it keeps most of the
travel and runs at the pace the dial names. Every other one runs far slower — a
fifth of it down to a fortieth — and gets what travel is left, so what it adds
is a swell carrying the whole motion from base to tip and back. A wave at half
the main pace with as much travel is not a swell; it is a second motion
interfering with the first, and that interference is what makes a stack sound
busy while feeling weak — no two swings the same depth, and none of them the
depth you asked for.

**Room to be dramatic.** A ramp that moves a dial five points over twenty
seconds is a ramp nobody can feel. The times here are long and the bands as wide
as being anchored allows: a speed crossing its whole band over half a minute, a
travel closing to two thirds of yours and opening back to all of it, a center
walking as far either way as the swing leaves room for. The motion should be
plainly somewhere different from where it was a minute ago.

**The sum, not the parts.** Every range here is what the *whole* motion is drawn
from, split among the waves — so two waves average what one used to, rather than
piling two full motions on top of each other and sitting the device high and
wide.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import wave_stack
from .robot_hand import (
    MAX_SPEED,
    MAX_TICK_SECONDS,
    MIN_SPEED,
    WaveformShape,
    set_amplitude,
    set_center,
    set_speed,
)
from .wave_stack import Ramp, Wave, WaveStack

__all__ = [
    "CruiseControlState",
    "disable_cruise_control",
    "enable_cruise_control",
    "tick_cruise_control",
    "toggle_cruise_control",
]

if TYPE_CHECKING:
    from .robot_hand import RobotHandState

# How many waves a session gets: a pair most of the time, sometimes the plain
# single wave, sometimes three.
_COUNTS = (1, 2, 2, 2, 3)
# What the whole motion's travel wanders over, as a fraction of the travel the
# dial was set to. It reaches what you asked for and never passes it — there is
# no room above — and the shallow end is still most of what you asked for.
_TRAVEL_BAND = (0.62, 1.0)
# How far the whole motion's center may wander either side of the one you set,
# and the ends of the axis it is kept off. How much of that wander survives is
# the swing's to say: :func:`wave_stack.room` pulls the center in far enough
# that the travel still lands, so a motion using the whole axis has nowhere to
# walk and a shallow one has the width of this.
_CENTER_SWING = 25.0
_CENTER_LIMITS = (10.0, 90.0)
# What the wave the speed dial names keeps of the travel. The rest is split
# among the swells — enough to carry the motion about, not enough to be a second
# motion of its own.
_MAIN_SHARE = (0.68, 0.88)
# How long a ramp on each axis takes. Long, because what is wanted is a motion
# gradually speeding up or opening out, not a dial being flicked.
_SPEED_S = (10.0, 40.0)
_TRAVEL_S = (8.0, 30.0)
_CENTER_S = (15.0, 60.0)
# Where each wave's speed wanders, in dial units either side of the session's
# base. The dial is exponential — about 18 units doubles the cycles a minute —
# so the first wave is the motion you set, and the ones under it run at a fifth
# to a fortieth of it: swells, not partials.
_MAIN_SPAN = (-12.0, 12.0)
_UNDER_SPANS = ((-72.0, -45.0), (-95.0, -70.0))
# The base drifts, so an hour of cruising is not all one pace — but only within
# sight of the speed you set. Unbounded, the same walk arrives an hour later at
# half the pace you asked for and has no way back to it.
_BASE_STEP = (-10.0, -5.0, 5.0, 10.0)
_BASE_SWING = 10.0
_BASE_S = (60.0, 120.0)
# What a swell may be shaped like. The main wave can be any of them; a swell is
# an envelope, and one that snaps between two levels is a lurch, not a carry.
_SWELL_SHAPES = (WaveformShape.SINE, WaveformShape.TRIANGLE)


@dataclass
class CruiseControlState:
    """Hands-free variation of the motion itself — never of which clip plays.

    Moving on to another clip is :mod:`genau.clip_advance`'s job, and the two are
    independent: a session can vary the motion on one held clip, or hold the
    motion steady while the clips change, or both.

    ``active`` is the only part of this a caller reads. The stack under it is
    what the device follows while it is set; ``clock`` is the motion's own
    seconds, which move only while it is actually running, so every ramp
    freezes where it stood through a pause.

    The three anchors are the dials as the session set them. Every range the
    dice are drawn from is measured off one of them, and only a hand on a dial
    moves one — which is what keeps an hour of this from wandering off.
    """

    active: bool = False
    rng: random.Random = field(default_factory=random.Random)
    stack: WaveStack = field(default_factory=WaveStack)
    clock: float = 0.0
    anchor_speed: float = 50.0
    anchor_travel: float = 100.0
    anchor_center: float = 50.0
    base_speed: float = 50.0
    bands: list[tuple[float, float]] = field(default_factory=list)
    # How the travel is divided: most of it to the wave the dial names.
    shares: list[float] = field(default_factory=list)
    next_base: float = 0.0
    # The dials as this last wrote them, so a hand that has moved one since can
    # be told from this module's own writing.
    wrote: tuple | None = None
    # None until the first tick: the wall clock a caller hands in is whatever
    # its own clock reads, so the first tick has no interval before it and must
    # not be given one — the motion would jump the whole of it in a step.
    _last_tick: float | None = None


def toggle_cruise_control(state: CruiseControlState) -> float | None:
    """Hands off, or hands back on.

    Returns the phase the single wave should pick up at when this hands the
    motion back — the phase of the wave that had the most travel, which is the
    one the device was mostly following — or None when it has just taken over.
    A caller with nowhere to put that may ignore it.
    """
    if state.active:
        return disable_cruise_control(state)
    enable_cruise_control(state)
    return None


def enable_cruise_control(state: CruiseControlState) -> None:
    """Arm it. The waves themselves are drawn on the first tick, from whatever
    the dials say then, so arming cannot move the motion."""
    state.active = True


def disable_cruise_control(state: CruiseControlState) -> float | None:
    """Give the motion back, and say where the single wave should pick it up."""
    phase = (wave_stack.biggest(state.stack, state.clock).phase
             if state.stack else None)
    state.active = False
    state.stack = WaveStack()
    state.bands = []
    state.shares = []
    state.wrote = None
    return phase


def tick_cruise_control(
    robot_hand: RobotHandState,
    cc: CruiseControlState,
    now: float,
    *,
    phase: float = 0.0,
) -> None:
    """One tick of the dice: carry the waves forward, pick up any hand on the
    dials, give every arrived ramp somewhere new to go, and write what the
    motion now is back to the dials for the console to read.

    *phase* is where the motion is, used only when this is the tick that draws
    the waves — they all start there, so taking over cannot be felt.

    Nothing moves while the motion is not running: the wall clock keeps up so
    resuming picks up where it left off, but the motion's own clock — the one
    every ramp is timed against — does not.
    """
    if not cc.active:
        return

    dt = 0.0 if cc._last_tick is None else now - cc._last_tick
    cc._last_tick = now

    if not robot_hand.playing:
        return

    if not cc.stack:
        _draw_the_waves(cc, robot_hand, phase)

    # A clock that stalled — the app blocked, the machine suspended — comes back
    # owing a step no motion should take at once, and the same cap the phase
    # puts on that is what the ramps under it get.
    step = max(0.0, min(dt, MAX_TICK_SECONDS))
    cc.clock += step
    wave_stack.advance(cc.stack, cc.clock, step)
    _hand_turns(cc, robot_hand)
    _onward_all(cc)
    _write_dials(cc, robot_hand)


def _clamped(speed: float) -> float:
    return min(float(MAX_SPEED), max(float(MIN_SPEED), speed))


def _within(low: float, high: float, value: float) -> float:
    return min(high, max(low, value))


def _bands(base: float, count: int) -> list[tuple[float, float]]:
    """Where each wave's speed may wander: the main one first, then the swells,
    each running slower than the one before it."""
    spans = (_MAIN_SPAN,) + _UNDER_SPANS[:max(0, count - 1)]
    return [(_clamped(base + low), _clamped(base + high)) for low, high in spans]


def _shares(rng: random.Random, count: int) -> list[float]:
    """How the travel is divided among the waves: most of it to the first, the
    rest split evenly among the swells under it.

    Drawn once, when the waves are, so which wave is the big one is settled for
    the session rather than swapping about — the pace the dial names is the pace
    with most of the travel under it, every minute this is on.
    """
    if count == 1:
        return [1.0]
    main = rng.uniform(*_MAIN_SHARE)
    return [main] + [(1.0 - main) / (count - 1)] * (count - 1)


def _travel_span(cc: CruiseControlState, index: int) -> tuple[float, float]:
    """What one wave's travel is drawn from: its share of the whole motion's
    band, which is itself a fraction of the travel the dial was set to."""
    share = cc.anchor_travel * cc.shares[index]
    return (share * _TRAVEL_BAND[0], share * _TRAVEL_BAND[1])


def _center_span(cc: CruiseControlState, count: int) -> tuple[float, float]:
    """What one wave's center is drawn from: the whole motion's wander either
    side of the center the dial was set to, divided among the waves."""
    low, high = _CENTER_LIMITS
    return (_within(low, high, cc.anchor_center - _CENTER_SWING) / count,
            _within(low, high, cc.anchor_center + _CENTER_SWING) / count)


def _settled(value: float, now: float) -> Ramp:
    """A ramp already arrived and holding *value* — what every parameter looks
    like the moment cruise control takes the motion over, before the first tick
    gives it somewhere to go."""
    return Ramp(value, value, now, 0.0)


def _onward(cc: CruiseControlState, ramp: Ramp, span: tuple[float, float],
            seconds: tuple[float, float]) -> Ramp:
    """*ramp* given somewhere new to be — from where it got to, to a fresh draw
    out of *span*, over a fresh stretch of seconds."""
    return Ramp(ramp.at(cc.clock), cc.rng.uniform(*span), cc.clock,
                cc.rng.uniform(*seconds))


def _draw_the_waves(cc: CruiseControlState, robot_hand: RobotHandState,
                    phase: float) -> None:
    """Take the motion over, from exactly where the dials have it.

    The dials become the anchors every later draw is measured off, and the
    travel is divided among the waves in the shares they will keep. Every ramp
    is born already arrived, so the sum is the dials to the point — and with
    every wave at the phase the motion is already at and running the same speed,
    the sum *is* the single wave. The rest of this tick draws them all somewhere
    to go, and the motion opens out from where it stood.
    """
    count = cc.rng.choice(_COUNTS)
    now = cc.clock
    cc.anchor_speed = cc.base_speed = float(robot_hand.speed)
    cc.anchor_travel = float(robot_hand.amplitude)
    cc.anchor_center = float(robot_hand.intended_center)
    cc.shares = _shares(cc.rng, count)
    cc.bands = _bands(cc.base_speed, count)
    cc.next_base = now + cc.rng.uniform(*_BASE_S)
    cc.wrote = None
    cc.stack = WaveStack(waves=[
        Wave(
            shape=robot_hand.shape,
            speed=_settled(float(robot_hand.speed), now),
            amplitude=_settled(robot_hand.amplitude * share, now),
            center=_settled(robot_hand.center / count, now),
            phase=phase,
        )
        for share in cc.shares
    ])


def _onward_all(cc: CruiseControlState) -> None:
    now = cc.clock
    waves = cc.stack.waves
    count = len(waves)
    if now >= cc.next_base:
        cc.base_speed = _clamped(_within(
            cc.anchor_speed - _BASE_SWING, cc.anchor_speed + _BASE_SWING,
            cc.base_speed + cc.rng.choice(_BASE_STEP)))
        cc.bands = _bands(cc.base_speed, count)
        cc.next_base = now + cc.rng.uniform(*_BASE_S)
    for index, (wave, band) in enumerate(zip(waves, cc.bands)):
        if wave.speed.finished(now):
            # A shape swapping under the phase steps the position a little, so
            # it is not free: a wave takes one only when its speed arrives
            # somewhere, and never on the ramp born finished at the takeover,
            # whose whole point is that it cannot be felt.
            if wave.speed.seconds > 0:
                wave.shape = cc.rng.choice(
                    list(WaveformShape) if index == 0 else list(_SWELL_SHAPES))
            wave.speed = _onward(cc, wave.speed, band, _SPEED_S)
        if wave.amplitude.finished(now):
            wave.amplitude = _onward(cc, wave.amplitude,
                                     _travel_span(cc, index), _TRAVEL_S)
        if wave.center.finished(now):
            wave.center = _onward(cc, wave.center,
                                  _center_span(cc, count), _CENTER_S)


def _write_dials(cc: CruiseControlState, robot_hand: RobotHandState) -> None:
    """The stack as the dials, so every console and status file draws what is
    actually being sent."""
    dials = wave_stack.dials(cc.stack, cc.clock)
    set_amplitude(robot_hand, round(dials.travel))
    set_center(robot_hand, round(dials.center))
    set_speed(robot_hand, round(dials.speed))
    robot_hand.shape = dials.shape
    cc.wrote = (robot_hand.amplitude, robot_hand.intended_center, robot_hand.speed,
                robot_hand.shape)


def _hand_turns(cc: CruiseControlState, robot_hand: RobotHandState) -> None:
    """A dial that has moved since this last wrote it moved by hand — so cruise
    carries on from there rather than yanking it back.

    Every dial is the whole motion's, and the motion is several waves, so each
    turn has to be spread over them: travel in proportion, so the shares survive
    the turn; center and pace by the same amount each, so their spacing does.
    The anchor moves by what the hand turned as well — a hand asking for more
    travel is asking for it from here on, not for one ramp's worth of it.
    """
    if cc.wrote is None:
        return
    now = cc.clock
    amplitude, center, speed, shape = cc.wrote
    waves = cc.stack.waves
    count = len(waves)
    if robot_hand.amplitude != amplitude:
        cc.anchor_travel = _within(
            0.0, 100.0, cc.anchor_travel + robot_hand.amplitude - amplitude)
        travel = sum(wave.amplitude.at(now) for wave in waves)
        for wave in waves:
            part = (wave.amplitude.at(now) * robot_hand.amplitude / travel
                    if travel > 0 else robot_hand.amplitude / count)
            wave.amplitude = wave.amplitude.resumed(part, now)
    if robot_hand.intended_center != center:
        cc.anchor_center = _within(
            *_CENTER_LIMITS,
            cc.anchor_center + robot_hand.intended_center - center)
        moved = (robot_hand.intended_center
                 - sum(wave.center.at(now) for wave in waves)) / count
        for wave in waves:
            wave.center = wave.center.resumed(wave.center.at(now) + moved, now)
    if robot_hand.speed != speed:
        delta = robot_hand.speed - speed
        cc.anchor_speed = _clamped(cc.anchor_speed + delta)
        cc.base_speed = _clamped(cc.base_speed + delta)
        cc.bands = _bands(cc.base_speed, count)
        for wave in waves:
            shifted = wave.speed.shifted(delta)
            wave.speed = Ramp(_clamped(shifted.start), _clamped(shifted.end),
                              shifted.begun, shifted.seconds)
    if robot_hand.shape is not shape:
        waves[0].shape = robot_hand.shape  # the console named the main wave's
