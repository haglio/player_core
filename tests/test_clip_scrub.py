"""Scrubbing the clip with the stroke — the picture being *of* the device.

The rule under test is that the frame shown is where the device is: parked
shows A, fully retracted shows B, and a stroke that only works part of the axis
only shows that part of the half. The half changes when the stroke turns at an
end, and nowhere else, so a stroke that turns back early rewinds the half it is
in rather than rolling on into the other.
"""
from __future__ import annotations

import pytest

from player_core.clip_scrub import ClipScrub, scrub_clip

FRAMES = 120  # a whole loop; one frame is 1/120 of the display phase


def _sweep(state, heights, frames=FRAMES):
    return [scrub_clip(state, height, frames) for height in heights]


def _ramp(start, end, steps=200):
    return [start + (end - start) * i / steps for i in range(steps + 1)]


def _from(height, frames=FRAMES):
    """A scrub already running, with the stroke at *height* — so the first look
    is not mistaken for arriving somewhere."""
    state = ClipScrub()
    scrub_clip(state, height, frames)
    return state


def test_the_frame_is_where_the_device_is():
    state = _from(0.0)
    assert scrub_clip(state, 0.5, FRAMES) == pytest.approx(0.25)
    assert scrub_clip(state, 0.75, FRAMES) == pytest.approx(0.375)
    assert scrub_clip(state, 0.2, FRAMES) == pytest.approx(0.1)


def test_a_stroke_that_turns_back_early_rewinds_the_half_it_is_in():
    # Not rolling on into the back half: the two halves only meet at the ends,
    # and this stroke never reached one.
    state = _from(0.2)
    climbing = _sweep(state, _ramp(0.2, 0.8))
    falling = _sweep(state, _ramp(0.8, 0.3))
    assert climbing == sorted(climbing)
    assert falling == sorted(falling, reverse=True)
    assert state.back_half is False
    assert max(climbing + falling) <= 0.4


def test_the_extent_of_the_animation_is_the_extent_of_the_motor():
    # A stroke working the middle of the axis shows the middle of the half —
    # never its first frames, never its last.
    state = _from(0.2)
    phases = _sweep(state, _ramp(0.2, 0.8)) + _sweep(state, _ramp(0.8, 0.2))
    assert min(phases) == pytest.approx(0.1)
    assert max(phases) == pytest.approx(0.4)


def test_a_full_sweep_plays_the_whole_clip_as_it_always_did():
    # The amplitude-100 groove: up the front half, over at B, down the back
    # half, over at A — one trip through the clip per stroke, which is what
    # genau has always shown for a full stroke.
    state = _from(0.0)
    climbing = _sweep(state, _ramp(0.0, 1.0))
    assert climbing == sorted(climbing)
    assert climbing[-1] == pytest.approx(0.5)    # the shared frame at B
    assert state.back_half is False              # nothing has turned yet
    falling = _sweep(state, _ramp(1.0, 0.0))
    assert state.back_half is True               # it turned at B
    assert falling[0] == pytest.approx(0.5)      # from the same frame
    assert falling == sorted(falling)            # and on forward through the back
    assert falling[-1] == pytest.approx(1.0)     # to the loop's other seam
    _sweep(state, _ramp(0.0, 0.5))
    assert state.back_half is False              # over again at A


def test_arriving_is_a_question_about_frames_not_about_the_axis():
    # The position is read on a tick and lands on exactly retracted essentially
    # never, so the end frame is what counts as the end: it covers the last
    # slice of the axis, and the slice is the clip's own — one frame of it.
    nearly = _from(0.5)
    _sweep(nearly, _ramp(0.5, 0.95) + _ramp(0.95, 0.5))
    assert nearly.back_half is False             # short of the end frame

    arrived = _from(0.5)
    _sweep(arrived, _ramp(0.5, 0.99) + _ramp(0.99, 0.5))
    assert arrived.back_half is True

    coarse = _from(0.5, frames=20)               # a shorter clip, a wider slice
    _sweep(coarse, _ramp(0.5, 0.95) + _ramp(0.95, 0.5), frames=20)
    assert coarse.back_half is True


def test_the_swap_waits_for_the_turn_so_the_picture_does_not_step():
    # Swapping on the way into the end frame would step the picture by a frame
    # or two, because the halves only agree at the very end.
    state = _from(0.5)
    climbing = _sweep(state, _ramp(0.5, 1.0))
    assert state.back_half is False
    assert climbing == sorted(climbing)          # no step on the way in
    over = _sweep(state, _ramp(1.0, 0.99))
    assert state.back_half is True
    assert over[0] == pytest.approx(0.5, abs=0.001)  # nor at the turn


def test_resting_at_an_end_swaps_once_and_not_once_a_tick():
    state = _from(0.5)
    _sweep(state, _ramp(0.5, 1.0) + [1.0] * 50)
    assert state.back_half is False              # sitting there is not a turn
    _sweep(state, _ramp(1.0, 0.99) + _ramp(0.99, 1.0) + _ramp(1.0, 0.99))
    assert state.back_half is True               # and the wobble swaps once


def test_a_stroke_that_never_reaches_an_end_never_swaps():
    state = _from(0.15)
    for _ in range(20):
        _sweep(state, _ramp(0.15, 0.85))
        _sweep(state, _ramp(0.85, 0.15))
    assert state.back_half is False


def test_the_ends_are_where_the_halves_show_the_same_moment():
    # Why the swap is invisible: at B both halves put the frame at 0.5, and at A
    # they put it at the two ends of the loop, which are the same seam.
    front, back = ClipScrub(), ClipScrub(back_half=True)
    assert scrub_clip(front, 1.0, FRAMES) == pytest.approx(0.5)
    assert scrub_clip(back, 1.0, FRAMES) == pytest.approx(0.5)
    front, back = ClipScrub(), ClipScrub(back_half=True)
    assert scrub_clip(front, 0.0, FRAMES) == pytest.approx(0.0)
    assert scrub_clip(back, 0.0, FRAMES) == pytest.approx(1.0)
