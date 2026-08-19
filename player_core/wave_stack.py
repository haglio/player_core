"""The stroke as a sum of waves, each of them always on its way somewhere.

One wave is one shape at one speed, and a minute of it is the same sentence over
and over. Several make a stroke: the main wave at the pace the dial is set to,
and under it a much slower swell of its own size, so the place the stroke is
working drifts from base to tip and back while the stroking goes on. Nothing
inside a wave holds still either — its speed, its travel and its center are all
:class:`Ramp`s rather than numbers, each on its way from what it was to
somewhere else over its own stretch of seconds, drawing a new somewhere when it
arrives.

Every wave owns its own travel and its own center outright. The stroke's travel
and center — the numbers on the console, the dashed line on the readout — are
read back off the sum rather than handed down to the waves, so a wave can drift
where it likes without asking the others. What keeps that from walking off the
end of the axis is :func:`fit`, at the last moment before a position is taken:
the summed swing is scaled down if the waves have between them asked for more
than the axis has, and the summed center is moved in far enough that the swing
still lands. Both are rare, because the draws that feed the ramps are already
divided by how many waves there are (see :mod:`player_core.cruise_control`) — the
fit is the guarantee, not the mechanism.

Pure arithmetic, as :mod:`player_core.direct_control` is. No clock of its own —
the caller says what time it is — and no randomness: drawing the ramps is
:mod:`player_core.cruise_control`'s job. The waveform itself is
:mod:`player_core.direct_control`'s; this only sums copies of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .direct_control import (
    WaveformShape, bpm_for_speed, phase_advanced, position_fraction,
)


@dataclass
class Ramp:
    """A value on its way from *start* to *end*, taking *seconds* over it.

    This is the dynamic half of the stroke: a travel that is 40 going on 20
    rather than a travel that is 30. Before it begins it reads *start* and after
    it ends it reads *end*, so a finished ramp is simply a number until
    something draws it a new one.
    """

    start: float
    end: float
    begun: float = 0.0
    seconds: float = 0.0

    def at(self, now: float) -> float:
        if self.seconds <= 0:
            return self.end
        through = (now - self.begun) / self.seconds
        if through <= 0.0:
            return self.start
        if through >= 1.0:
            return self.end
        return self.start + (self.end - self.start) * through

    def finished(self, now: float) -> bool:
        return now >= self.begun + self.seconds

    def resumed(self, value: float, now: float) -> Ramp:
        """This ramp carried on from *value* — a hand on the dial mid-glide.

        Same destination, and the time that was left to reach it, but starting
        from where the hand put it rather than snapping back to where the glide
        had got to on its own.
        """
        return Ramp(value, self.end, now,
                    max(0.0, self.begun + self.seconds - now))

    def shifted(self, delta: float) -> Ramp:
        """This ramp with both ends moved by *delta*, keeping its schedule —
        a dial nudged by hand while cruise control is steering it."""
        return Ramp(self.start + delta, self.end + delta, self.begun,
                    self.seconds)


@dataclass
class Wave:
    """One of the summed waves: a shape, and a speed, a travel and a center of
    its own, each of the three on its way somewhere.

    The center is the wave's alone. Only the sum of them is a place on the axis,
    which is what the console shows — but a wave whose center is ramping while
    another's holds is a different stroke from one where they move together, and
    that difference is the whole reason each carries its own.
    """

    shape: WaveformShape = WaveformShape.SINE
    speed: Ramp = field(default_factory=lambda: Ramp(50.0, 50.0))
    amplitude: Ramp = field(default_factory=lambda: Ramp(100.0, 100.0))
    center: Ramp = field(default_factory=lambda: Ramp(50.0, 50.0))
    phase: float = 0.0


@dataclass
class WaveStack:
    """The waves that are summed to make the stroke.

    The first is the stroke's own pace — the one the speed dial is set to and
    the one a hand on that dial is turning. The ones after it run slower, and
    are the swells that carry it about (:mod:`player_core.cruise_control` is what
    makes that so, and the console's speed and shape name that first wave
    because of it).
    """

    waves: list[Wave] = field(default_factory=list)

    def __bool__(self) -> bool:
        """False while there are no waves — while the stroke is the single
        hand-driven one and this is not what the device is following."""
        return bool(self.waves)


@dataclass
class Fit:
    """The sum squeezed into the axis: how much every wave's travel had to give
    (``scale``, 1.0 nearly always), and what the stroke's travel and center come
    to once it has."""

    scale: float
    travel: float
    center: float


@dataclass
class Dials:
    """The stack as the three numbers and the shape a console can show."""

    travel: float
    center: float
    speed: float
    shape: WaveformShape


def room(travel: float, center: float) -> float:
    """*center*, moved in far enough that a swing of *travel* still fits.

    A stroke 90 wide cannot sit at 25 — a quarter of it would be under the floor
    — so the center gives way, exactly as player_core's ``_recompute_center``
    makes it give way on the dials. Here it gives way continuously, because
    every ramp under it moves on its own schedule and none waits for the others.
    """
    half = travel / 2
    return min(100.0 - half, max(half, center))


def fit(stack: WaveStack, now: float) -> Fit:
    """The waves added up and made to land on the axis.

    Their travels sum to the stroke's travel and their centers to its center —
    that way round, so no wave has to be told where to sit. Only when the sum
    asks for more swing than the axis has does anything give: every travel is
    scaled by the same fraction, which shrinks the stroke without changing which
    wave is the big one.
    """
    travel = sum(wave.amplitude.at(now) for wave in stack.waves)
    center = sum(wave.center.at(now) for wave in stack.waves)
    scale = 1.0 if travel <= 100.0 else 100.0 / travel
    travel *= scale
    return Fit(scale=scale, travel=travel, center=room(travel, center))


def position(stack: WaveStack, now: float,
             phases: list[float] | None = None) -> float:
    """Where the summed stroke sits at *now*, 0-100.

    *phases* is where each wave is, defaulting to where they actually are — the
    projections below pass their own rather than moving the waves to ask.
    """
    if phases is None:
        phases = [wave.phase for wave in stack.waves]
    landed = fit(stack, now)
    total = landed.center
    for wave, phase in zip(stack.waves, phases):
        # position_fraction on its default dials is the bare waveform, 0-1.
        raw = position_fraction(phase, shape=wave.shape)
        total += landed.scale * wave.amplitude.at(now) * (raw - 0.5)
    return min(100.0, max(0.0, total))


def advance(stack: WaveStack, now: float, dt_s: float) -> None:
    """Carry every wave's phase forward by *dt_s* seconds of stroking."""
    for wave in stack.waves:
        wave.phase = phase_advanced(
            wave.phase, bpm_for_speed(wave.speed.at(now)), dt_s)


def position_ahead(stack: WaveStack, now: float, lead_s: float) -> float:
    """Where the sum will be *lead_s* from *now* — what a command aims at.

    Each wave's phase is projected rather than advanced (nothing here moves the
    stack), at the speed it will be running halfway through the lead, which is
    what a ramping speed comes to over so short a hop.
    """
    phases = [
        wave.phase
        + lead_s * bpm_for_speed(wave.speed.at(now + lead_s / 2)) / 60.0
        for wave in stack.waves
    ]
    return position(stack, now + lead_s, phases)


def trace(stack: WaveStack, now: float, samples: int,
          span_s: float) -> list[float]:
    """The sum sampled forward from *now* as 0-1 heights, *span_s* of it.

    Walked step by step rather than solved: every parameter in the stack is
    moving over a span this long, so each sample is taken at its own moment and
    carries the phases on at whatever speed the waves are running by then.
    """
    step = span_s / max(1, samples - 1)
    phases = [wave.phase for wave in stack.waves]
    heights = []
    for i in range(samples):
        at = now + i * step
        heights.append(position(stack, at, phases) / 100.0)
        phases = [
            phase + step * bpm_for_speed(wave.speed.at(at)) / 60.0
            for wave, phase in zip(stack.waves, phases)
        ]
    return heights


def biggest(stack: WaveStack, now: float) -> Wave:
    """The wave with the most travel — the one the device is mostly following,
    whichever of them it happens to be at the moment."""
    return max(stack.waves, key=lambda wave: wave.amplitude.at(now))


def dials(stack: WaveStack, now: float) -> Dials:
    """What the console reads while the stack has the stroke.

    The travel and the center are read off the sum, so the readout's bar and its
    dashed line are the envelope the device is really working in rather than
    anything the waves were told. Speed and shape are the main wave's: there is
    no single number for two speeds at once, and the pace of the stroke you set
    is the one a reader is asking after — the swells under it are slow by
    construction, and naming whichever wave is momentarily the biggest would
    have the number stepping between them while the motion did nothing.
    """
    landed = fit(stack, now)
    lead = stack.waves[0]
    return Dials(travel=landed.travel, center=landed.center,
                 speed=lead.speed.at(now), shape=lead.shape)


def rest_at_bottom(stack: WaveStack) -> None:
    """Put every wave at phase 0 — the foot of the stroke's swing.

    Phase 0 is where every waveform shape's raw value is 0, so all of them at
    once is the lowest point the stack's travel and center reach: the nearest
    the stroke comes to the device's park, and where it should resume from after
    something else has had the device.
    """
    for wave in stack.waves:
        wave.phase = 0.0
