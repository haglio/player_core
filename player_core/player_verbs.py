"""The verbs a content source sends a player, spelled once.

A player is driven by whoever has content for it -- Fun Time's dispatcher
today -- through a queue of these on its command file
(:mod:`player_core.file_channel`).  Each player declares the ones it answers
in a registry (:mod:`player_core.control_registry`) and refuses the rest; the
spellings live here so a sender and every receiver read them off one line,
which is what stopped one player saying LOCK for the hold another called
LOCK_ON.

A verb about the player's own surface rather than about its content -- a
headset's projection, the Robot Hand's motion -- is that player's own and is
spelled beside its registry.
"""
from __future__ import annotations

import math

from .playlist import PlaylistItem, item_line

__all__ = [
    "DISPLAY_OFF",
    "DISPLAY_ON",
    "LOCK_OFF",
    "LOCK_ON",
    "NEXT",
    "PLAY_FILE",
    "PREV",
    "QUIT",
    "RELOAD_PLAYLIST",
    "SEEK_BACK",
    "SEEK_FWD",
    "SET_F_MODE",
    "SET_PACE",
    "SET_SPEED",
    "SET_TCODE_ENABLED",
    "SET_VOLUME",
    "SPEED_DOWN",
    "SPEED_UP",
    "TOGGLE_LOCK",
    "TRASH",
    "pace_seconds",
    "play_file",
]

# The list: step along it, or read it again after the source rewrote the file
# (keeping the item on screen where it survived).
NEXT = "NEXT"
PREV = "PREV"
RELOAD_PLAYLIST = "RELOAD_PLAYLIST"

# The item on screen: hold it against the list moving on (repeat-one), drop it
# from the list and move on, or name another -- jumped to if it is in the list,
# spliced in after this one if not.  The hold is spelled absolutely as well as
# toggled: a speaker asks for the state they want.
TOGGLE_LOCK = "TOGGLE_LOCK"
LOCK_ON = "LOCK_ON"
LOCK_OFF = "LOCK_OFF"
TRASH = "TRASH"
PLAY_FILE = "PLAY_FILE"  # its value is one playlist line; see play_file

# Inside the item: ten seconds either way, and the rate it plays at
# (SET_SPEED min | max | <multiplier>).
SEEK_FWD = "SEEK_FWD"
SEEK_BACK = "SEEK_BACK"
SPEED_UP = "SPEED_UP"
SPEED_DOWN = "SPEED_DOWN"
SET_SPEED = "SET_SPEED"

# The sound (SET_VOLUME <0-100> [muted]), the device (SET_TCODE_ENABLED 0|1), and
# how hard the device may work (SET_MAX_INTENSITY <0-100>).
SET_VOLUME = "SET_VOLUME"
SET_TCODE_ENABLED = "SET_TCODE_ENABLED"
SET_MAX_INTENSITY = "SET_MAX_INTENSITY"

# What the source holds and the player cannot see: whether the list it was
# handed is the narrowed one (SET_F_MODE 0|1), and whether the player owns its
# rectangle right now -- told OFF it paints nothing, so a switch back to it does
# not land on the frame it was paused on.
SET_F_MODE = "SET_F_MODE"
DISPLAY_ON = "DISPLAY_ON"
DISPLAY_OFF = "DISPLAY_OFF"

# How long a picture holds the screen before the list moves on (SET_PACE
# <seconds>, 0 holding it until something else moves it).
SET_PACE = "SET_PACE"

SHOW_FRAME = "SHOW_FRAME"
CLEAR_FRAME = "CLEAR_FRAME"

# The picture on screen eased onto one part of it and held there until the
# next item (AIM_STILL <x0> <y0> <x1> <y1> <seconds>, fractions of the picture).
AIM_STILL = "AIM_STILL"

QUIT = "QUIT"


def play_file(item: PlaylistItem) -> str:
    """The command that shows *item*."""
    return f"{PLAY_FILE} {item_line(item)}"


def aim_still(part: tuple[float, float, float, float], seconds: float) -> str:
    return " ".join([AIM_STILL, *(f"{number:g}" for number in (*part, seconds))])


def aim_of(value: str) -> tuple[tuple[float, float, float, float], float] | None:
    try:
        x0, y0, x1, y1, seconds = (float(word) for word in value.split())
    except ValueError:
        return None
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        return None
    if not (math.isfinite(seconds) and seconds >= 0):
        return None
    return (x0, y0, x1, y1), seconds


def pace_seconds(value: str) -> float | None:
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None
