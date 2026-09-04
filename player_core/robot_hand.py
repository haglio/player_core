"""The Robot Hand: the stroke this family generates itself, a waveform shaped
by speed, amplitude and center.

It is what drives the OSR2 whenever no funscript has it — the family's own auto
mode, made so the stroke could be steered from the room instead of left to the
device's built-in one.  Genau drives it from a clip's beats and visualizes it;
Origenerator free-runs it over slideshows of stills.  Both stroke from this one
arithmetic, so :func:`phase_advanced` is offered here rather than owned here:
what advances the phase is the caller's own clock.

Pure arithmetic: no toolkit, no device, no clock.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .tcode import POSITION_MAX


class WaveformShape(Enum):
    SINE = "sine"
    TRIANGLE = "triangle"
    ROUNDED_SQUARE = "rounded_square"
    SAWTOOTH = "sawtooth"

MIN_BPM = 5.0
MAX_BPM = 200.0
MIN_SPEED = 5
MAX_SPEED = 100

# The most wall time one tick of a caller's clock may move the phase — see
# :func:`phase_advanced`.
MAX_TICK_SECONDS = 0.1


def bpm_for_speed(speed: int) -> float:
    """Map speed MIN_SPEED-MAX_SPEED to BPM using exponential curve."""
    t = (speed - MIN_SPEED) / (MAX_SPEED - MIN_SPEED)
    return MIN_BPM * (MAX_BPM / MIN_BPM) ** t


@dataclass
class RobotHandState:
    playing: bool = False
    speed: int = 50
    bpm: float = 0.0
    amplitude: int = 100
    center: int = 50
    intended_center: int = 50
    shape: WaveformShape = WaveformShape.SINE

    def __post_init__(self) -> None:
        if self.bpm == 0.0:
            self.bpm = bpm_for_speed(self.speed)
        _recompute_center(self)


def toggle_playing(state: RobotHandState) -> None:
    state.playing = not state.playing


def pause_playing(state: RobotHandState) -> None:
    state.playing = False


def space_action(state: RobotHandState, *, pause_only: bool) -> None:
    if pause_only:
        pause_playing(state)
    else:
        toggle_playing(state)


def set_speed(state: RobotHandState, speed: int) -> None:
    speed = max(MIN_SPEED, min(MAX_SPEED, speed))
    state.speed = speed
    state.bpm = bpm_for_speed(speed)


def adjust_speed(state: RobotHandState, delta: int) -> None:
    set_speed(state, state.speed + delta)


def _recompute_center(state: RobotHandState) -> None:
    """Set effective center from intended_center, clamped to amplitude range."""
    half = state.amplitude // 2
    state.center = max(half, min(100 - half, state.intended_center))


def set_amplitude(state: RobotHandState, value: int) -> None:
    state.amplitude = max(0, min(100, value))
    _recompute_center(state)


def adjust_amplitude(state: RobotHandState, delta: int) -> None:
    set_amplitude(state, state.amplitude + delta)


def set_center(state: RobotHandState, value: int) -> None:
    state.intended_center = max(0, min(100, value))
    _recompute_center(state)


def adjust_center(state: RobotHandState, delta: int) -> None:
    half = state.amplitude // 2
    lo, hi = half, 100 - half
    new = state.intended_center + delta
    if new < lo:
        if state.intended_center <= lo:
            return
        new = lo
    elif new > hi:
        if state.intended_center >= hi:
            return
        new = hi
    new = max(0, min(100, new))
    state.intended_center = new
    _recompute_center(state)


def cycle_shape(state: RobotHandState, step: int = 1) -> None:
    """Advance the waveform shape by *step* (default +1; pass -1 to go back)."""
    shapes = list(WaveformShape)
    idx = shapes.index(state.shape)
    state.shape = shapes[(idx + step) % len(shapes)]


def _waveform_raw(phase: float, shape: WaveformShape) -> float:
    """Return 0-1 normalized waveform value for one round trip per cycle."""
    frac = phase % 1.0
    if shape is WaveformShape.TRIANGLE:
        return 1 - abs(2 * frac - 1)
    if shape is WaveformShape.ROUNDED_SQUARE:
        k = 3.0
        return (1 - math.tanh(k * math.cos(2 * math.pi * frac)) / math.tanh(k)) / 2
    if shape is WaveformShape.SAWTOOTH:
        rise = 0.3
        if frac < rise:
            return frac / rise
        return 1 - (frac - rise) / (1 - rise)
    # SINE, and the fall-through with it: an unhandled shape strokes.
    return (1 - math.cos(2 * math.pi * phase)) / 2


def sample_waveform(
    shape: WaveformShape,
    amplitude: int,
    center: int,
    n_points: int,
    *,
    start_phase: float = 0.0,
    phase_range: float = 1.0,
) -> list[float]:
    """Sample waveform over a phase range, returning 0-1 normalized positions."""
    return [
        position_fraction(
            start_phase + (i / n_points) * phase_range,
            shape=shape, amplitude=amplitude, center=center,
        )
        for i in range(n_points)
    ]


def position_fraction(
    phase: float,
    *,
    shape: WaveformShape = WaveformShape.SINE,
    amplitude: int = 100,
    center: int = 50,
) -> float:
    """Where the stroke sits at *phase*, 0 (bottom of the axis) to 1 (top).

    The scale-free form of :func:`phase_to_position`. Callers speaking T-Code
    want that one's 0-9999; a readout drawing a trace, or an app whose device
    layer takes percent, wants this.
    """
    raw = _waveform_raw(phase, shape)
    half = amplitude / 100 / 2
    low = max(0.0, center / 100 - half)
    high = min(1.0, center / 100 + half)
    return min(1.0, max(0.0, low + raw * (high - low)))


def phase_to_position(
    phase: float,
    *,
    shape: WaveformShape = WaveformShape.SINE,
    amplitude: int = 100,
    center: int = 50,
) -> int:
    return round(POSITION_MAX * position_fraction(
        phase, shape=shape, amplitude=amplitude, center=center))


def phase_advanced(phase: float, bpm: float, dt_s: float) -> float:
    """*phase* moved on by *dt_s* seconds of stroking at *bpm* strokes a minute.

    The step is capped at :data:`MAX_TICK_SECONDS`, because a clock that stalled
    — the app blocked, the machine suspended — comes back owing a step no device
    should be asked to take at once. The stroke slows through the gap instead of
    slingshotting across it, which is the same cap Genau's engine puts on its
    own tick.
    """
    return (phase + max(0.0, min(dt_s, MAX_TICK_SECONDS)) * bpm / 60.0) % 1.0
