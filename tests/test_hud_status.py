"""The one status line every player's HUD leads with."""
from __future__ import annotations

from player_core.hud_status import (
    F_MODE_LABEL,
    LOCKED_LABEL,
    UNLOCKED_LABEL,
    status_line,
)


def test_an_idle_player_says_only_whether_it_is_holding_what_is_on_screen():
    """The lock is the one state every player in this family has, so it is the one
    thing the line always carries."""
    assert status_line(locked=True) == LOCKED_LABEL
    assert status_line(locked=False) == UNLOCKED_LABEL


def test_the_slots_run_from_the_set_being_played_down_to_the_finest_filter():
    """Set, hold, order, then the two filters coarse before fine — the order a
    reader's eye takes: what is playing, whether it is stuck, how it advances, and
    what was cut out of it."""
    assert status_line(
        playing_set="Looping seeds", locked=True, order="Latest",
        f_mode=True, filter_label="alpha",
    ) == f"Looping seeds · {LOCKED_LABEL} · Latest · {F_MODE_LABEL} · alpha"


def test_a_set_playing_through_drops_unlocked_but_keeps_locked():
    """A set on repeat holds nothing, so saying "Unlocked" beside one is noise —
    it names the absence of a hold that was never on offer.  A hold taken inside
    the set is real, though: it is a stop at one member of it, and it stays."""
    assert status_line(playing_set="Looping seeds", locked=False) == "Looping seeds"
    assert status_line(playing_set="Looping seeds", locked=True) == (
        f"Looping seeds · {LOCKED_LABEL}")


def test_an_empty_slot_takes_no_room_and_leaves_no_separator():
    """Every slot but the lock is optional, and a player without one prints nothing
    there rather than an empty phrase or a doubled separator."""
    assert status_line(locked=False, order="Shuffle") == f"{UNLOCKED_LABEL} · Shuffle"
    assert status_line(locked=False, filter_label="beta") == f"{UNLOCKED_LABEL} · beta"
