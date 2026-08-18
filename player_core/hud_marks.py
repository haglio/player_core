"""How a HUD control says it wants one of the family's drawn marks.

A console model is a plain description the painter reads -- no colors, no
Pillow -- and that is worth keeping: it is what lets the model be built, tested
and sent around without a drawing toolkit anywhere near it.  So a control that
wants one of :mod:`shared_ui.icon_geometry`'s marks NAMES it, with the marker
below, and the painter is what turns the name into pixels
(:func:`player_core.hud_panel.draw_mark`).

This module holds only the naming, and imports nothing, so both a model module
and a painter can use it without either dragging the other's dependencies along.
"""

from __future__ import annotations

SHARED_MARK = "\x00glyph:"


def shared_mark(name: str) -> str:
    """The marker standing for one of :mod:`shared_ui.icon_geometry`'s marks."""
    return SHARED_MARK + name


def shared_mark_name(glyph: str) -> str:
    """Which mark *glyph* stands for; only call it on a :data:`SHARED_MARK` one."""
    return glyph[len(SHARED_MARK):]
