"""Cruise control's waves — the dice, and what they are not allowed to do.

Two techniques are on trial. Waves are summed, so the stroke is the pace you set
with a much slower swell of its own size carrying it from base to tip and back;
and every parameter of every wave is a ramp rather than a number, so the stroke
is plainly somewhere different from where it was a minute ago. A ramp too small
or too quick to feel is the failure this is tuned against, so the tests here
measure how far things actually move, not merely that they moved.
"""
from __future__ import annotations

import random

import pytest

from player_core import wave_stack
from player_core.cruise_control import (
    CruiseControlState,
    disable_cruise_control,
    enable_cruise_control,
    tick_cruise_control,
    toggle_cruise_control,
)
from player_core.direct_control import (
    DirectControlState, WaveformShape, bpm_for_speed, set_amplitude,
)


def _cruising(seed, **dials):
    """A stroke running under cruise control, one tick in."""
    direct = DirectControlState(playing=True, **dials)
    cc = CruiseControlState(rng=random.Random(seed))
    enable_cruise_control(cc)
    tick_cruise_control(direct, cc, now=1000.0)
    return direct, cc


def _run(direct, cc, seconds, *, dt=0.05, start=1000.0, watch=None):
    """Carry the stroke forward, handing each tick to *watch* if there is one."""
    now = start
    for _ in range(int(seconds / dt)):
        now += dt
        tick_cruise_control(direct, cc, now)
        if watch is not None:
            watch(direct, cc)
    return now


def _bpm(wave, cc):
    return bpm_for_speed(wave.speed.at(cc.clock))


class TestArming:
    def test_toggle_arms_and_disarms(self):
        cc = CruiseControlState(rng=random.Random(42))
        assert toggle_cruise_control(cc) is None
        assert cc.active is True
        toggle_cruise_control(cc)
        assert cc.active is False

    def test_enable_and_disable_are_idempotent(self):
        cc = CruiseControlState(rng=random.Random(42))
        enable_cruise_control(cc)
        enable_cruise_control(cc)
        assert cc.active is True
        disable_cruise_control(cc)
        disable_cruise_control(cc)
        assert cc.active is False

    def test_arming_alone_moves_nothing(self):
        # The waves are drawn on the first tick, from whatever the dials say
        # then — so arming against a parked device cannot change the stroke.
        direct = DirectControlState(speed=50, amplitude=80, intended_center=50)
        cc = CruiseControlState(rng=random.Random(42))
        enable_cruise_control(cc)
        assert not cc.stack
        tick_cruise_control(direct, cc, now=10.0)  # not playing
        assert (direct.speed, direct.amplitude, direct.center) == (50, 80, 50)
        assert not cc.stack

    def test_an_unarmed_tick_changes_nothing(self):
        direct = DirectControlState(speed=50, amplitude=80, intended_center=50)
        cc = CruiseControlState(active=False, rng=random.Random(42))
        tick_cruise_control(direct, cc, now=10.0)
        assert (direct.speed, direct.amplitude, direct.center) == (50, 80, 50)


class TestTakingTheStrokeOver:
    def test_the_takeover_cannot_be_felt(self):
        # The dial's travel and center are divided evenly among the waves and
        # every ramp is born already arrived, so the sum is the dials to the
        # point — and with every wave at the phase the stroke is already at and
        # running the same speed, the sum is the single wave. Anything else is a
        # step on the wire the device has to lurch through.
        for seed in range(8):
            direct = DirectControlState(playing=True, speed=35, amplitude=70,
                                        intended_center=40)
            cc = CruiseControlState(rng=random.Random(seed))
            enable_cruise_control(cc)
            tick_cruise_control(direct, cc, now=1000.0, phase=0.42)
            assert (direct.amplitude, direct.center) == (70, 40)
            assert direct.speed == 35
            assert all(wave.shape is WaveformShape.SINE
                       for wave in cc.stack.waves)
            assert all(wave.phase == 0.42 for wave in cc.stack.waves)
            assert wave_stack.position(cc.stack, cc.clock) == pytest.approx(
                100 * _single_wave_fraction(0.42, 70, 40))

    def test_handing_it_back_says_where_the_single_wave_picks_up(self):
        direct, cc = _cruising(2)
        _run(direct, cc, seconds=45)
        expected = wave_stack.biggest(cc.stack, cc.clock).phase
        assert toggle_cruise_control(cc) == expected
        assert not cc.active and not cc.stack


def _single_wave_fraction(phase, amplitude, center):
    from player_core.direct_control import position_fraction
    return position_fraction(phase, amplitude=amplitude, center=center)


class TestTheStrokeItMakes:
    def test_it_sits_and_swings_where_a_single_cruising_wave_did(self):
        # The bias that makes summing safe. Drawn per wave from the ranges the
        # whole stroke uses, two waves would average a center and a travel half
        # again too big; dividing each draw by how many waves are sharing it is
        # what keeps the sum where one wave has always sat.
        centers, travels, positions = [], [], []

        def watch(direct, cc):
            centers.append(direct.center)
            travels.append(direct.amplitude)
            positions.append(wave_stack.position(cc.stack, cc.clock))

        # Ten sessions of ten minutes: the center ramps are slow enough that a
        # shorter sample is mostly noise rather than the average asked after.
        for seed in range(10):
            direct, cc = _cruising(seed)
            _run(direct, cc, seconds=600, watch=watch)
        assert sum(centers) / len(centers) == pytest.approx(50, abs=3)
        assert sum(travels) / len(travels) == pytest.approx(55, abs=5)
        assert all(0.0 <= where <= 100.0 for where in positions)
        assert min(positions) < 5 and max(positions) > 95

    def test_what_rides_the_stroke_is_a_swell_and_not_a_vibration(self):
        # A quicker wave of small travel on top of the stroke is a vibration,
        # which is the opposite of what is wanted: everything after the main
        # wave runs much slower than it, so what it adds is the stroke being
        # carried from base to tip and back while the stroking goes on.
        ratios = []

        def watch(direct, cc):
            main, *under = cc.stack.waves
            for wave in under:
                assert _bpm(wave, cc) <= _bpm(main, cc)
                ratios.append(_bpm(main, cc) / _bpm(wave, cc))

        for seed in range(12):
            direct, cc = _cruising(seed)
            if len(cc.stack.waves) < 2:
                continue
            _run(direct, cc, seconds=200, dt=0.25, watch=watch)
        assert sum(ratios) / len(ratios) > 2.0
        assert max(ratios) > 4.0

    def test_the_swell_is_as_often_the_bigger_wave(self):
        swell_bigger = total = 0

        def watch(direct, cc):
            nonlocal swell_bigger, total
            main, under = cc.stack.waves[:2]
            swell_bigger += (under.amplitude.at(cc.clock)
                             > main.amplitude.at(cc.clock))
            total += 1

        for seed in range(12):
            direct, cc = _cruising(seed)
            if len(cc.stack.waves) < 2:
                continue
            _run(direct, cc, seconds=300, dt=0.25, watch=watch)
        assert 0.25 < swell_bigger / total < 0.75

    def test_the_dials_move_far_enough_to_notice(self):
        # The complaint this is tuned against: ramps that are there in the code
        # and cannot be felt on the device. Over a few minutes the stroke has to
        # open and close most of the axis, walk a good way from base to tip, and
        # speed up and slow down by more than a nudge.
        for seed in range(4):
            direct, cc = _cruising(seed)
            travels, centers, bpms = [], [], []

            def watch(direct, cc, travels=travels, centers=centers, bpms=bpms):
                travels.append(direct.amplitude)
                centers.append(direct.center)
                bpms.append(_bpm(cc.stack.waves[0], cc))

            _run(direct, cc, seconds=400, watch=watch)
            assert max(travels) - min(travels) > 50
            assert max(centers) - min(centers) > 25
            assert max(bpms) / min(bpms) > 2.0

    def test_every_dial_it_claims_to_move_moves(self):
        # It moved only speed for years: a tick stepped a dial by a twentieth of
        # the gap to its target and the result was snapped to fives, so any
        # target nearer than about fifty points rounded back to where it
        # started.
        seen = {"amplitude": set(), "center": set(), "speed": set(),
                "shape": set()}

        def watch(direct, cc):
            for dial in seen:
                seen[dial].add(getattr(direct, dial))

        direct, cc = _cruising(5)
        _run(direct, cc, seconds=300, watch=watch)
        assert len(seen["amplitude"]) > 20
        assert len(seen["center"]) > 20
        assert len(seen["speed"]) > 5
        assert len(seen["shape"]) > 1


class TestPausing:
    """Armed but not stroking — paused by hand, frozen under OmniPause, or
    sitting out a funscript's turn in Hybrid. Auto advance has always sat still
    then; this used to go on moving the stroke, so a session came back from a
    pause to a stroke it never asked for."""

    def test_a_paused_hand_freezes_the_stroke(self):
        direct, cc = _cruising(3)
        _run(direct, cc, seconds=30)
        direct.playing = False
        was = (cc.clock, wave_stack.position(cc.stack, cc.clock),
               direct.amplitude, direct.center, direct.speed, direct.shape)
        now = _run(direct, cc, seconds=60)
        assert (cc.clock, wave_stack.position(cc.stack, cc.clock),
                direct.amplitude, direct.center, direct.speed,
                direct.shape) == was
        assert cc._last_tick == pytest.approx(now)  # the wall clock kept up

    def test_it_picks_up_where_it_left_off_rather_than_lurching_on_resume(self):
        direct, cc = _cruising(3)
        _run(direct, cc, seconds=30)
        direct.playing = False
        _run(direct, cc, seconds=300)   # five minutes of pause
        held = cc.clock
        direct.playing = True
        _run(direct, cc, seconds=1)
        assert cc.clock == pytest.approx(held + 1, abs=0.1)


class TestAHandOnTheDials:
    def test_a_dial_moved_by_hand_is_carried_on_from_not_yanked_back(self):
        direct, cc = _cruising(5)
        _run(direct, cc, seconds=20)
        speeds = [wave.speed.at(cc.clock) for wave in cc.stack.waves]
        parts = [wave.amplitude.at(cc.clock) for wave in cc.stack.waves]

        set_amplitude(direct, 40)
        direct.intended_center = 70
        direct.speed += 10
        turned_to = direct.speed
        tick_cruise_control(direct, cc, now=1000.0 + 20 + 0.05)

        assert direct.amplitude == 40
        assert direct.center == 70
        assert direct.speed == turned_to
        assert [wave.speed.at(cc.clock) for wave in cc.stack.waves] == \
            pytest.approx([speed + 10 for speed in speeds], abs=0.1)
        # the travel was spread in proportion, so the balance survives the turn
        # (to within the tick's own drift — every ramp moved on while it ran)
        now = [wave.amplitude.at(cc.clock) for wave in cc.stack.waves]
        assert [part / sum(parts) for part in parts] == \
            pytest.approx([part / sum(now) for part in now], abs=0.01)


class TestTheDialsStayInRange:
    @pytest.mark.parametrize("seed", range(4))
    def test_nothing_leaves_the_axis_or_the_dial(self, seed):
        direct, cc = _cruising(seed)

        def watch(direct, cc):
            assert 0 <= direct.amplitude <= 100
            assert 0 <= direct.center <= 100
            assert 5 <= direct.speed <= 100
            assert direct.shape in list(WaveformShape)
            assert 0.0 <= wave_stack.position(cc.stack, cc.clock) <= 100.0

        _run(direct, cc, seconds=300, watch=watch)
