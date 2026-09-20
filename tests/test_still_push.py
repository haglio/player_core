"""The creep into a still while it holds the screen."""
from __future__ import annotations

import pytest

from player_core.still_push import StillPush


def test_a_picture_arrives_at_its_own_size():
    push = StillPush()
    push.set_pace(4.0, now_s=100.0)

    push.restart(now_s=100.0)

    assert push.zoom(now_s=100.0) == 1.0


def test_halfway_through_the_hold_it_is_halfway_in():
    push = StillPush()
    push.set_pace(4.0, now_s=100.0)
    push.restart(now_s=100.0)

    assert push.zoom(now_s=102.0) == pytest.approx(1.05)


def test_a_picture_with_no_pace_is_never_moved_into():
    push = StillPush()
    push.set_pace(0.0, now_s=100.0)  # a pace of nought holds the picture

    push.restart(now_s=100.0)

    assert push.zoom(now_s=1000.0) == 1.0


def test_a_frozen_room_holds_the_picture_where_the_creep_had_got_to():
    push = StillPush()
    push.set_pace(4.0, now_s=100.0)
    push.restart(now_s=100.0)

    push.set_paused(True, now_s=101.0)

    assert push.zoom(now_s=103.0) == pytest.approx(1.025)


def test_the_room_thawing_carries_the_creep_on_from_where_it_stopped():
    push = StillPush()
    push.set_pace(4.0, now_s=100.0)
    push.restart(now_s=100.0)
    push.set_paused(True, now_s=101.0)

    push.set_paused(False, now_s=110.0)

    assert push.zoom(now_s=111.0) == pytest.approx(1.05)


def test_turning_the_pace_up_slows_the_creep_instead_of_cropping_harder():
    push = StillPush()
    push.set_pace(4.0, now_s=100.0)
    push.restart(now_s=100.0)

    push.set_pace(8.0, now_s=102.0)  # halfway in, and the show slows down

    assert push.zoom(now_s=102.0) == pytest.approx(1.05)
    assert push.zoom(now_s=104.0) == pytest.approx(1.075)


def test_a_new_picture_starts_the_creep_over():
    push = StillPush()
    push.set_pace(4.0, now_s=100.0)
    push.restart(now_s=100.0)

    push.restart(now_s=102.0)

    assert push.zoom(now_s=102.0) == 1.0


def test_a_locked_picture_creeps_again_each_time_it_repeats():
    push = StillPush()
    push.set_pace(4.0, now_s=100.0)
    push.restart(now_s=100.0)

    assert push.zoom(now_s=106.0) == pytest.approx(1.05)
