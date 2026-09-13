"""A player's declared rows, for the tests that lay them out, draw them and press
them: the family's standard band, exactly as a source declares it."""
from __future__ import annotations

from player_core.hud_button import Button
from player_core.satellite_hud import HudModel, standard_rows


def player_rows(player: str = "portrait", **fields) -> tuple[tuple[Button, ...], ...]:
    return standard_rows(HudModel(player=player, **fields))


def band(player: str = "portrait", **fields) -> tuple[Button, ...]:
    """The player's own band -- the last row, under the mode row where there is one."""
    return player_rows(player, **fields)[-1]


def short_name(button: Button) -> str:
    """What a standard button is for, the player prefix dropped: "lock", "fmode";
    a mode button keeps its whole verb, naming no player."""
    for prefix in ("portrait_", "landscape_"):
        if button.command.startswith(prefix):
            return button.command[len(prefix):]
    return button.command
