"""The closed sets a player and Fun Time agree on, each as the words on the wire."""
from __future__ import annotations

import json

import pytest

from player_core.modes import (
    LengthMode,
    LoopState,
    MainMode,
    NoticeLevel,
    Osr2State,
    SatellitesMode,
    read_mode,
)

# Every entry's value is the word the files already carry, so a file written
# before these existed reads back as the same entry, and one written now reads
# back on a player from before them.
_WIRE_WORDS = {
    MainMode: {"video", "genau"},
    SatellitesMode: {"video", "origenerator"},
    LoopState: {"normal", "recording", "looping"},
    Osr2State: {"off", "auto", "funscript", "robot_hand"},
    LengthMode: {"mixed", "shorts", "full", "none"},
    NoticeLevel: {"warning", "notice", "favorite"},
}


@pytest.mark.parametrize("enum", list(_WIRE_WORDS))
def test_each_entry_is_spelled_as_the_files_already_spell_it(enum):
    assert {entry.value for entry in enum} == _WIRE_WORDS[enum]


@pytest.mark.parametrize("enum", list(_WIRE_WORDS))
def test_an_entry_is_its_wire_word_wherever_a_string_is_wanted(enum):
    """A comparison against the bare word still holds, and a JSON writer that
    is handed the entry writes the word and nothing else."""
    for entry in enum:
        assert entry == entry.value
        assert json.dumps(entry) == json.dumps(entry.value)


def test_read_mode_gives_the_entry_a_known_word_names():
    assert read_mode(MainMode, "genau", MainMode.VIDEO) is MainMode.GENAU
    assert read_mode(LoopState, "recording", LoopState.NORMAL) is LoopState.RECORDING


@pytest.mark.parametrize("raw", ["", "hybrid", None, 3, "VIDEO"])
def test_read_mode_answers_the_default_for_a_word_it_does_not_know(raw):
    """A player that raised on a mode it did not know would be worse than one
    that ignored it: a file from a newer or an older session must leave the
    player drawing, in the state the default names."""
    assert read_mode(MainMode, raw, MainMode.VIDEO) is MainMode.VIDEO


def test_read_mode_hands_an_entry_straight_back():
    assert read_mode(SatellitesMode, SatellitesMode.ORIGENERATOR, SatellitesMode.VIDEO) is (
        SatellitesMode.ORIGENERATOR)
