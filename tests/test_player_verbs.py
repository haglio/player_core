"""The verbs a content source sends a player, and the two whose values it reads: an item and a pace."""
from __future__ import annotations

from pathlib import Path

import pytest

from player_core import player_verbs
from player_core.playlist import PlaylistItem, item_from_line


def _spellings() -> dict[str, str]:
    return {name: value for name, value in vars(player_verbs).items()
            if name.isupper() and isinstance(value, str)}


def test_every_verb_is_spelled_as_a_registry_looks_it_up():
    """A registry folds the keyword to upper case and splits it from its value at
    the first space, so a spelling with a space or a lower-case letter in it is a
    verb nothing could ever answer."""
    for name, spelling in _spellings().items():
        assert spelling == name, f"{name} is spelled {spelling!r}"
        assert spelling == spelling.upper() and " " not in spelling


def test_no_two_verbs_share_a_spelling():
    spellings = list(_spellings().values())
    assert len(spellings) == len(set(spellings))


def test_play_file_carries_the_item_as_the_playlist_would():
    """The value is a playlist line, so a receiver reads it back with the file's
    own parser and cannot take the script for part of the path."""
    item = PlaylistItem(Path("C:/vids/My Clip.mp4"), Path("C:/scripts/My Clip.funscript"))

    line = player_verbs.play_file(item)

    keyword, _, value = line.partition(" ")
    assert keyword == player_verbs.PLAY_FILE
    assert item_from_line(value) == item


def test_a_pace_is_read_as_the_seconds_it_names():
    assert player_verbs.pace_seconds("2.5") == 2.5
    assert player_verbs.pace_seconds("0") == 0.0


@pytest.mark.parametrize("value", ["-1", "soon", "", "inf", "nan"])
def test_a_value_that_names_no_pace_is_refused(value):
    assert player_verbs.pace_seconds(value) is None
