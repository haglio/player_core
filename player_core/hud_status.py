"""The one status line every player's HUD leads with.

Three players draw a HUD in this family — the two satellites and whichever of Nau
or Genau holds the primary slot — and each one begins with a line saying what is
selecting what you are looking at.  They say different *things*: a satellite has a
loop over a map of clips, an act filter and a browse order; the primary has a
compilation, a length mode and a pace.  What they must not differ on is the
*grammar* — which fact comes first, which word names the lock, when a fact is worth
saying at all — because a reader glancing between two screens is reading one
sentence in two places.

So the slots and the wording live here, and each player fills them with its own
words.  Kept apart from :mod:`player_core.hud_panel`, which owns how a HUD is
*drawn*: this owns what it *says*, and a player can want one without the other.
"""
from __future__ import annotations

SEPARATOR = " · "

# What the lock is called.  Every player has this one and means the same by it —
# repeat-one on whatever is on screen — so it is named once, here.
LOCKED_LABEL = "Locked"
UNLOCKED_LABEL = "Unlocked"

# What F-mode is called.  One Fun Time key toggles it for every player at once, so
# a reader seeing it lit on one screen and named differently on another would have
# to work out they are the same switch.
F_MODE_LABEL = "F-Mode"


def status_line(*, locked: bool, playing_set: str = "", order: str = "",
                f_mode: bool = False, filter_label: str = "") -> str:
    """The line, from the slots a player fills.

    Read left to right, the slots answer a reader's questions in the order they
    occur: what is playing (*playing_set* — a satellite's loop, the primary's
    compilation), whether it is being held (*locked*), how it moves on (*order* —
    Latest/Shuffle, or the seconds an unheld clip stays up), and what has been cut
    out of it — *f_mode* first, cutting the whole library to the funscripted
    videos, then *filter_label*, narrowing what is left.

    Every slot but the lock is optional and an empty one takes no room, so a player
    with nothing to say in it prints nothing rather than an empty phrase.  The one
    rule beyond that: a *playing_set* drops "Unlocked", because a set playing
    through holds nothing and naming the absence of a hold that was never on offer
    is noise.  "Locked" still joins it — a hold taken inside a set is a stop at one
    member of it, which is worth saying.
    """
    parts = [playing_set] if playing_set else []
    if locked:
        parts.append(LOCKED_LABEL)
    elif not playing_set:
        parts.append(UNLOCKED_LABEL)
    if order:
        parts.append(order)
    if f_mode:
        parts.append(F_MODE_LABEL)
    if filter_label:
        parts.append(filter_label)
    return SEPARATOR.join(parts)
