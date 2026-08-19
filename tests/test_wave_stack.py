"""The summed stroke's arithmetic — the part with no dice in it.

Two promises are what matter here. Every wave carries its own travel and its own
center, so one can drift while another holds and the console's numbers are read
back off what they came to rather than handed down to them. And however many
waves there are and whatever their parameters are doing, the sum lands on the
axis: the stroke the device is sent can never run off either end of it.
"""

import math
import random

import pytest

from player_core import wave_stack
from player_core.direct_control import WaveformShape, position_fraction
from player_core.wave_stack import Ramp, Wave, WaveStack


def _stack(rng, count):
    return WaveStack(waves=[
        Wave(shape=rng.choice(list(WaveformShape)),
             speed=Ramp(rng.uniform(10, 90), rng.uniform(10, 90), 0.0, 30.0),
             amplitude=Ramp(rng.uniform(5, 100 / count),
                            rng.uniform(5, 100 / count), 0.0, 30.0),
             center=Ramp(rng.uniform(10, 90) / count,
                         rng.uniform(10, 90) / count, 0.0, 30.0),
             phase=rng.random())
        for _ in range(count)
    ])


def test_a_ramp_reads_where_it_has_got_to():
    ramp = Ramp(40.0, 20.0, begun=100.0, seconds=10.0)
    assert ramp.at(99.0) == 40.0     # before it starts
    assert ramp.at(100.0) == 40.0
    assert ramp.at(105.0) == 30.0    # halfway
    assert ramp.at(110.0) == 20.0
    assert ramp.at(999.0) == 20.0    # and holds until it is drawn a new one
    assert not ramp.finished(109.0) and ramp.finished(110.0)


def test_a_ramp_with_no_time_to_take_is_simply_its_end():
    # How engaging seeds every ramp: born holding one value and already arrived,
    # so the first tick is what gives it somewhere to go.
    assert Ramp(7.0, 7.0, 0.0, 0.0).at(0.0) == 7.0
    assert Ramp(7.0, 7.0, 0.0, 0.0).finished(0.0)


def test_a_ramp_picked_up_by_hand_carries_on_from_there():
    ramp = Ramp(40.0, 20.0, begun=0.0, seconds=10.0)
    moved = ramp.resumed(80.0, now=4.0)
    assert moved.at(4.0) == 80.0     # where the hand put it
    assert moved.at(10.0) == 20.0    # same destination, in the time that was left
    assert moved.seconds == pytest.approx(6.0)


def test_one_wave_is_the_plain_single_stroke():
    # The stack is not a different kind of motion — with one wave it is exactly
    # the wave the dials have always described.
    stack = WaveStack(waves=[Wave(shape=WaveformShape.TRIANGLE, phase=0.3,
                                  amplitude=Ramp(60.0, 60.0),
                                  center=Ramp(40.0, 40.0))])
    assert wave_stack.position(stack, 0.0) == pytest.approx(
        100 * position_fraction(0.3, shape=WaveformShape.TRIANGLE,
                                amplitude=60, center=40))


def test_every_wave_carries_its_own_center():
    # The stroke's center is what the waves' centers came to, not something they
    # were each handed a share of: move one wave's center and the stroke moves
    # with it, while the other wave stays exactly where it was sitting.
    slow = Wave(amplitude=Ramp(20.0, 20.0), center=Ramp(20.0, 20.0))
    main = Wave(amplitude=Ramp(30.0, 30.0), center=Ramp(30.0, 30.0), phase=0.25)
    stack = WaveStack(waves=[slow, main])
    assert wave_stack.dials(stack, 0.0).center == 50.0
    was = wave_stack.position(stack, 0.0)

    slow.center = Ramp(35.0, 35.0)
    assert wave_stack.dials(stack, 0.0).center == 65.0
    assert wave_stack.position(stack, 0.0) == pytest.approx(was + 15.0)
    assert main.center.at(0.0) == 30.0  # the other wave never moved


def test_the_summed_stroke_never_leaves_the_axis():
    # Summed carelessly, waves climb: two each swinging 50 around 50 reach 150,
    # and the device spends its evening pinned at the top.
    rng = random.Random(11)
    for count in (1, 2, 3, 5):
        for _ in range(40):
            stack = _stack(rng, count)
            for now in (0.0, 7.0, 30.0, 100.0):
                for wave in stack.waves:
                    wave.phase = rng.random()
                assert 0.0 <= wave_stack.position(stack, now) <= 100.0


def test_the_swing_gives_way_only_when_the_waves_ask_for_more_than_the_axis():
    ordinary = WaveStack(waves=[Wave(amplitude=Ramp(30.0, 30.0)),
                                Wave(amplitude=Ramp(50.0, 50.0))])
    assert wave_stack.fit(ordinary, 0.0).scale == 1.0
    assert wave_stack.fit(ordinary, 0.0).travel == 80.0

    greedy = WaveStack(waves=[Wave(amplitude=Ramp(60.0, 60.0)),
                              Wave(amplitude=Ramp(100.0, 100.0))])
    landed = wave_stack.fit(greedy, 0.0)
    assert landed.travel == 100.0
    assert landed.scale == pytest.approx(100 / 160)  # both shrink by the same
    # and the big wave is still the big one afterwards
    assert wave_stack.biggest(greedy, 0.0) is greedy.waves[1]


def test_the_center_gives_way_when_the_swing_will_not_fit():
    # A stroke 90 wide cannot sit at 25 with a quarter of it under the floor.
    assert wave_stack.room(90.0, 25.0) == 45.0
    assert wave_stack.room(90.0, 75.0) == 55.0
    assert wave_stack.room(40.0, 25.0) == 25.0   # room to spare: left alone
    assert wave_stack.room(100.0, 10.0) == 50.0  # no room at all: pinned


def test_aiming_ahead_by_nothing_is_where_the_stroke_is():
    rng = random.Random(2)
    stack = _stack(rng, 2)
    assert wave_stack.position_ahead(stack, 5.0, 0.0) == pytest.approx(
        wave_stack.position(stack, 5.0))


def test_aiming_ahead_lands_where_carrying_the_stroke_forward_gets_to():
    # The claim every command on the wire makes: be at this place in this long.
    stack = WaveStack(waves=[
        Wave(speed=Ramp(60.0, 60.0), amplitude=Ramp(40.0, 40.0),
             center=Ramp(30.0, 30.0)),
        Wave(shape=WaveformShape.TRIANGLE, speed=Ramp(20.0, 20.0),
             amplitude=Ramp(20.0, 20.0), center=Ramp(20.0, 20.0)),
    ])
    aimed = wave_stack.position_ahead(stack, 0.0, 0.04)
    wave_stack.advance(stack, 0.0, 0.04)
    assert aimed == pytest.approx(wave_stack.position(stack, 0.04), abs=1e-9)


def test_the_trace_is_the_motion_being_sent_not_a_drawing_of_it():
    # Held still, the walk and the projection are the same arithmetic, so the
    # end of the trace is exactly the place a command 12 seconds long would aim
    # at. (Under ramping speeds they part company, which is the point of walking
    # it: 12 seconds is long enough for every parameter to have moved.)
    stack = WaveStack(waves=[
        Wave(speed=Ramp(50.0, 50.0), amplitude=Ramp(45.0, 45.0),
             center=Ramp(30.0, 30.0)),
        Wave(shape=WaveformShape.TRIANGLE, speed=Ramp(20.0, 20.0),
             amplitude=Ramp(25.0, 25.0), center=Ramp(20.0, 20.0)),
    ])
    heights = wave_stack.trace(stack, 3.0, samples=80, span_s=12.0)
    assert len(heights) == 80
    assert heights[0] == pytest.approx(wave_stack.position(stack, 3.0) / 100)
    assert heights[-1] == pytest.approx(
        wave_stack.position_ahead(stack, 3.0, 12.0) / 100)

    rng = random.Random(7)
    moving = wave_stack.trace(_stack(rng, 2), 3.0, samples=80, span_s=12.0)
    assert all(0.0 <= height <= 1.0 for height in moving)
    assert not all(math.isclose(height, moving[0]) for height in moving)


def test_the_console_is_told_the_whole_stroke_and_the_wave_you_can_feel():
    stack = WaveStack(waves=[
        Wave(shape=WaveformShape.SAWTOOTH, speed=Ramp(30.0, 30.0),
             amplitude=Ramp(14.0, 14.0), center=Ramp(14.0, 14.0)),
        Wave(shape=WaveformShape.TRIANGLE, speed=Ramp(70.0, 70.0),
             amplitude=Ramp(50.0, 50.0), center=Ramp(30.0, 30.0)),
    ])
    dials = wave_stack.dials(stack, 0.0)
    assert (dials.travel, dials.center) == (64.0, 44.0)   # what they came to
    assert dials.speed == 30.0                            # the main wave's
    assert dials.shape is WaveformShape.SAWTOOTH
    # and the wave the device is mostly following is still the bigger one
    assert wave_stack.biggest(stack, 0.0) is stack.waves[1]
