"""Hands-free variation of the stroke — Genau's cruise control, shared.

It lives beside :mod:`player_core.direct_control` because the state it varies is
that one's: an app that has the stroke gets this with it, rather than growing
its own idea of what "vary it for me" means.

What it hands the device is :mod:`player_core.wave_stack`'s — waves summed, each
with its own travel, center and speed. This is the part with the dice in it. It
decides how many waves there are and how far below the main one the others run,
and then never stops: every ramp that arrives somewhere is given somewhere else
to be, over its own stretch of seconds, so no dial in the stroke is ever simply
a number.

Three things it is careful about.

**What rides on what.** The first wave runs near the pace the dial is set to.
Every other one runs *much* slower — a half to a fifth of it — and is drawn a
travel from the same range, so what it adds is a swell that carries the stroking
from base to tip and back, not a vibration on top of it. Which wave is the big
one is a separate draw again, so the slow swell is as often the larger.

**Room to be dramatic.** A ramp that moves a dial five points over twenty
seconds is a ramp nobody can feel. The ranges here are the width of the axis and
the times are long: a speed crossing most of the dial over half a minute, a
travel opening from nearly shut to nearly the whole axis, a center walking from
base to tip over a minute. The stroke should be plainly somewhere different from
where it was a minute ago.

**The sum, not the parts.** Every range here is what the *whole* stroke is drawn
from, divided by how many waves are sharing it — so two waves average what one
used to, rather than piling two full strokes on top of each other and sitting
the device high and wide.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import wave_stack
from .direct_control import (
    MAX_SPEED, MAX_TICK_SECONDS, MIN_SPEED, WaveformShape, set_amplitude,
    set_center, set_speed,
)
from .wave_stack import Ramp, Wave, WaveStack

if TYPE_CHECKING:
    from .direct_control import DirectControlState

# How many waves a session gets: a pair most of the time, sometimes the plain
# single wave, sometimes three.
_COUNTS = (1, 2, 2, 2, 3)
# What the *whole* stroke's travel and center are drawn from, before being
# divided among the waves. Nearly the width of the axis, both of them, so the
# stroke has somewhere to travel to.
_TRAVEL = (10.0, 100.0)
_CENTER = (10.0, 90.0)
# How long a ramp on each axis takes. Long, because what is wanted is a stroke
# gradually speeding up or opening out, not a dial being flicked.
_SPEED_S = (10.0, 40.0)
_TRAVEL_S = (8.0, 30.0)
_CENTER_S = (15.0, 60.0)
# Where each wave's speed wanders, in dial units either side of the session's
# base. The dial is exponential — about 18 units doubles the strokes a minute —
# so the first wave is the stroke you set, and the ones under it run at a half
# to a fifth of that: swells, not vibration.
_MAIN_SPAN = (-15.0, 15.0)
_UNDER_SPANS = ((-45.0, -20.0), (-70.0, -40.0))
# The base itself drifts, so an hour of cruising is not all one pace.
_BASE_STEP = (-10.0, -5.0, 5.0, 10.0)
_BASE_S = (60.0, 120.0)


@dataclass
class CruiseControlState:
    """Hands-free variation of the stroke itself — never of which clip plays.

    Moving on to another clip is :mod:`genau.clip_advance`'s job, and the two are
    independent: a session can vary the stroke on one held clip, or hold the
    stroke steady while the clips change, or both.

    ``active`` is the only part of this a caller reads. The stack under it is
    what the device follows while it is set; ``clock`` is the stroke's own
    seconds, which move only while it is actually stroking, so every ramp
    freezes where it stood through a pause.
    """

    active: bool = False
    rng: random.Random = field(default_factory=random.Random)
    stack: WaveStack = field(default_factory=WaveStack)
    clock: float = 0.0
    base_speed: float = 50.0
    bands: list[tuple[float, float]] = field(default_factory=list)
    next_base: float = 0.0
    # The dials as this last wrote them, so a hand that has moved one since can
    # be told from this module's own writing.
    wrote: tuple | None = None
    # None until the first tick: the wall clock a caller hands in is whatever
    # its own clock reads, so the first tick has no interval behind it and must
    # not be given one — the stroke would jump the whole of it in a step.
    _last_tick: float | None = None


def toggle_cruise_control(state: CruiseControlState) -> float | None:
    """Hands off, or hands back on.

    Returns the phase the single wave should pick up at when this hands the
    stroke back — the phase of the wave that had the most travel, which is the
    one the device was mostly following — or None when it has just taken over.
    A caller with nowhere to put that may ignore it.
    """
    if state.active:
        return disable_cruise_control(state)
    enable_cruise_control(state)
    return None


def enable_cruise_control(state: CruiseControlState) -> None:
    """Arm it. The waves themselves are drawn on the first tick, from whatever
    the dials say then, so arming cannot move the stroke."""
    state.active = True


def disable_cruise_control(state: CruiseControlState) -> float | None:
    """Give the stroke back, and say where the single wave should pick it up."""
    phase = (wave_stack.biggest(state.stack, state.clock).phase
             if state.stack else None)
    state.active = False
    state.stack = WaveStack()
    state.bands = []
    state.wrote = None
    return phase


def tick_cruise_control(
    direct: DirectControlState,
    cc: CruiseControlState,
    now: float,
    *,
    phase: float = 0.0,
) -> None:
    """One tick of the dice: carry the waves forward, pick up any hand on the
    dials, give every arrived ramp somewhere new to go, and write what the
    stroke now is back to the dials for the console to read.

    *phase* is where the stroke is, used only when this is the tick that draws
    the waves — they all start there, so taking over cannot be felt.

    Nothing moves while the stroke is not running: the wall clock keeps up so
    resuming picks up where it left off, but the stroke's own clock — the one
    every ramp is timed against — does not.
    """
    if not cc.active:
        return

    dt = 0.0 if cc._last_tick is None else now - cc._last_tick
    cc._last_tick = now

    if not direct.playing:
        return

    if not cc.stack:
        _draw_the_waves(cc, direct, phase)

    # A clock that stalled — the app blocked, the machine suspended — comes back
    # owing a step no stroke should take at once, and the same cap the phase
    # puts on that is what the ramps under it get.
    step = max(0.0, min(dt, MAX_TICK_SECONDS))
    cc.clock += step
    wave_stack.advance(cc.stack, cc.clock, step)
    _hand_turns(cc, direct)
    _onward_all(cc)
    _write_dials(cc, direct)


def _clamped(speed: float) -> float:
    return min(float(MAX_SPEED), max(float(MIN_SPEED), speed))


def _bands(base: float, count: int) -> list[tuple[float, float]]:
    """Where each wave's speed may wander: the main one first, then the swells,
    each running slower than the one before it."""
    spans = (_MAIN_SPAN,) + _UNDER_SPANS[:max(0, count - 1)]
    return [(_clamped(base + low), _clamped(base + high)) for low, high in spans]


def _share(span: tuple[float, float], count: int) -> tuple[float, float]:
    """*span*, as one wave's share of it — what keeps the waves summing to what
    a single one used to be."""
    return (span[0] / count, span[1] / count)


def _settled(value: float, now: float) -> Ramp:
    """A ramp already arrived and holding *value* — what every parameter looks
    like the moment cruise control takes the stroke over, before the first tick
    gives it somewhere to go."""
    return Ramp(value, value, now, 0.0)


def _onward(cc: CruiseControlState, ramp: Ramp, span: tuple[float, float],
            seconds: tuple[float, float]) -> Ramp:
    """*ramp* given somewhere new to be — from where it got to, to a fresh draw
    out of *span*, over a fresh stretch of seconds."""
    return Ramp(ramp.at(cc.clock), cc.rng.uniform(*span), cc.clock,
                cc.rng.uniform(*seconds))


def _draw_the_waves(cc: CruiseControlState, direct: DirectControlState,
                    phase: float) -> None:
    """Take the stroke over, from exactly where the dials have it.

    The dial's travel and center are divided evenly among the waves and every
    ramp is born already arrived, so the sum is the dials to the point — and
    with every wave at the phase the stroke is already at and running the same
    speed, the sum *is* the single wave. The rest of this tick draws them all
    somewhere to go, and the stroke opens out from where it stood.
    """
    count = cc.rng.choice(_COUNTS)
    now = cc.clock
    cc.base_speed = float(direct.speed)
    cc.bands = _bands(cc.base_speed, count)
    cc.next_base = now + cc.rng.uniform(*_BASE_S)
    cc.wrote = None
    cc.stack = WaveStack(waves=[
        Wave(
            shape=direct.shape,
            speed=_settled(float(direct.speed), now),
            amplitude=_settled(direct.amplitude / count, now),
            center=_settled(direct.center / count, now),
            phase=phase,
        )
        for _ in range(count)
    ])


def _onward_all(cc: CruiseControlState) -> None:
    now = cc.clock
    waves = cc.stack.waves
    count = len(waves)
    if now >= cc.next_base:
        cc.base_speed = _clamped(cc.base_speed + cc.rng.choice(_BASE_STEP))
        cc.bands = _bands(cc.base_speed, count)
        cc.next_base = now + cc.rng.uniform(*_BASE_S)
    for wave, band in zip(waves, cc.bands):
        if wave.speed.finished(now):
            # A shape swapping under the phase steps the position a little, so
            # it is not free: a wave takes one only when its speed arrives
            # somewhere, and never on the ramp born finished at the takeover,
            # whose whole point is that it cannot be felt.
            if wave.speed.seconds > 0:
                wave.shape = cc.rng.choice(list(WaveformShape))
            wave.speed = _onward(cc, wave.speed, band, _SPEED_S)
        if wave.amplitude.finished(now):
            wave.amplitude = _onward(cc, wave.amplitude,
                                     _share(_TRAVEL, count), _TRAVEL_S)
        if wave.center.finished(now):
            wave.center = _onward(cc, wave.center,
                                  _share(_CENTER, count), _CENTER_S)


def _write_dials(cc: CruiseControlState, direct: DirectControlState) -> None:
    """The stack as the dials, so every console and status file draws what is
    actually being sent."""
    dials = wave_stack.dials(cc.stack, cc.clock)
    set_amplitude(direct, round(dials.travel))
    set_center(direct, round(dials.center))
    set_speed(direct, round(dials.speed))
    direct.shape = dials.shape
    cc.wrote = (direct.amplitude, direct.intended_center, direct.speed,
                direct.shape)


def _hand_turns(cc: CruiseControlState, direct: DirectControlState) -> None:
    """A dial that has moved since this last wrote it moved by hand — so cruise
    carries on from there rather than yanking it back.

    Every dial is the whole stroke's, and the stroke is several waves, so each
    turn has to be spread over them: travel in proportion, so which wave is the
    big one survives the turn; center and pace by the same amount each, so their
    spacing does.
    """
    if cc.wrote is None:
        return
    now = cc.clock
    amplitude, center, speed, shape = cc.wrote
    waves = cc.stack.waves
    count = len(waves)
    if direct.amplitude != amplitude:
        travel = sum(wave.amplitude.at(now) for wave in waves)
        for wave in waves:
            part = (wave.amplitude.at(now) * direct.amplitude / travel
                    if travel > 0 else direct.amplitude / count)
            wave.amplitude = wave.amplitude.resumed(part, now)
    if direct.intended_center != center:
        moved = (direct.intended_center
                 - sum(wave.center.at(now) for wave in waves)) / count
        for wave in waves:
            wave.center = wave.center.resumed(wave.center.at(now) + moved, now)
    if direct.speed != speed:
        delta = direct.speed - speed
        cc.base_speed = _clamped(cc.base_speed + delta)
        cc.bands = _bands(cc.base_speed, count)
        for wave in waves:
            shifted = wave.speed.shifted(delta)
            wave.speed = Ramp(_clamped(shifted.start), _clamped(shifted.end),
                              shifted.begun, shifted.seconds)
    if direct.shape is not shape:
        waves[0].shape = direct.shape  # the console named the main wave's
