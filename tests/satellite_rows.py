"""A side's declared rows, for the tests that lay them out, draw them and press
them: the family's standard band, exactly as a source declares it."""
from __future__ import annotations

from player_core.hud_button import Button
from player_core.satellite_hud import HudModel, standard_rows


def side_rows(side: str = "portrait", **fields) -> tuple[tuple[Button, ...], ...]:
    return standard_rows(HudModel(side=side, **fields))


def band(side: str = "portrait", **fields) -> tuple[Button, ...]:
    """The side's own band -- the last row, under the mode row where there is one."""
    return side_rows(side, **fields)[-1]


def short_name(button: Button) -> str:
    """What a standard button is for, the side prefix dropped: "lock", "fmode";
    a mode button keeps its whole verb, having no side."""
    for side in ("portrait_", "landscape_"):
        if button.command.startswith(side):
            return button.command[len(side):]
    return button.command
