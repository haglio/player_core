from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw
from shared_ui.spacing import BUTTON_GAP, BUTTON_SIZE_HUD

from .geometry import Rect
from .hud_button import Button
from .hud_marks import shared_mark
from .hud_panel import draw_button, load_font, to_bgra
from .hud_placement import HudCorner

__all__: list[str] = []

BUTTON = BUTTON_SIZE_HUD
ROOM = BUTTON + BUTTON_GAP

MINIMIZE_GLYPH = shared_mark("minus")
RESTORE_GLYPH = shared_mark("plus")
MINIMIZE_TOOLTIP = "Minimize this HUD"
RESTORE_TOOLTIP = "Show this HUD again"

_MARK_FONT_PT = 9


@lru_cache(maxsize=1)
def _mark_font():
    return load_font(_MARK_FONT_PT)


def minimize_command(player: str) -> str:
    return f"{player}_hud_minimize"


def restore_command(player: str) -> str:
    return f"{player}_hud_restore"


def minimize_button(player: str) -> Button:
    return Button(minimize_command(player), MINIMIZE_GLYPH, MINIMIZE_TOOLTIP)


def restore_button(player: str) -> Button:
    return Button(restore_command(player), RESTORE_GLYPH, RESTORE_TOOLTIP)


def minimize_rect(corner: HudCorner, *, panel_width: int, y: int, pad: int) -> Rect:
    x = pad if corner.right else panel_width - pad - BUTTON
    return (x, y, BUTTON, BUTTON)


def collapsed_button(player: str, *, hovered: bool = False
                     ) -> tuple[Image.Image, list[tuple[Rect, Button]]]:
    image = Image.new("RGBA", (BUTTON, BUTTON), (0, 0, 0, 0))
    rect = (0, 0, BUTTON, BUTTON)
    draw_button(image, ImageDraw.Draw(image), rect, restore_button(player),
                hovered=hovered, glyph_font=_mark_font(), word_font=_mark_font())
    return image, [(rect, restore_button(player))]


def collapsed_panel(player: str, *, hovered: bool = False
                    ) -> tuple[np.ndarray, list[tuple[Rect, Button]]]:
    image, buttons = collapsed_button(player, hovered=hovered)
    return to_bgra(image), buttons
