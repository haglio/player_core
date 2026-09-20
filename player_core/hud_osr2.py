"""The device's own line: who has the OSR2, and the controls that aim it.

Every panel whose host drives the device draws this line, so the word for a
parked OSR2 is the same word wherever it is read — the main player's console
(:mod:`player_core.console_hud`) and a HUD over a host that drives it itself
(:mod:`player_core.satellite_hud_paint`) share this one rather than each
spelling the states again.

The controls sit together at the head of the line because they act on the
device rather than on any player: placed by hand rather than through the row
layout, which would read them as different families and open a gap between
them.  The label then hugs its pill, well clear of them, so "OSR2 Robot Hand"
reads as one read-out instead of as another button.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw
from shared_ui.palette import (
    BLUE,
    GREEN,
    MAGENTA,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

from .console import GAP, OSR2_CONTROL_OFF, OSR2_PARKED, OSR2_RETRACTED
from .geometry import Rect, contains
from .hud_button import BUTTON, Button
from .hud_panel import SYMBOL_FONT, draw_button, load_font, text_width
from .modes import Osr2State

# Package-internal: the two panels that draw this line are both in here, and a
# host says what its line shows through the model it already hands over
# (:class:`player_core.console.ConsoleModel`,
# :class:`player_core.satellite_hud.HudModel`) rather than by building one.
__all__: list[str] = []

# The line is as deep as the controls sharing it.
HEIGHT = BUTTON
LABEL = "OSR2"
_LABEL_GAP = 5   # "OSR2" sits right up against the pill it names …
_GROUP_GAP = 16  # … and well clear of the controls beside them
_PILL_PAD = 10   # the room the state word keeps either side of itself

_SIZE_BODY = 11
_SIZE_TINY = 8

# The pill's own word for a device that belongs to neither driver at the
# playhead -- drawn, never published, so it is not one of the wire's states.
BUFFER = "buffer"
# The buffer pill wears the trace's own neutral gray, so the word and the line
# under the dot are visibly the same state.
_NEUTRAL_PILL = (168, 168, 174)

LABELS = {
    Osr2State.OFF: "Off", Osr2State.AUTO: "Auto", Osr2State.FUNSCRIPT: "FunScript",
    Osr2State.ROBOT_HAND: "Robot Hand", BUFFER: "Buffer",
    # Said in three words because two of them would be read as the device: the
    # OSR2 is on and well, this app has simply stopped sending it anything.  In
    # the red its own button wears, so the lit control and the pill saying what
    # it did are visibly the one fact.
    OSR2_CONTROL_OFF: "Control off",
    OSR2_PARKED: "Parked", OSR2_RETRACTED: "Retracted",
}
COLORS = {
    Osr2State.FUNSCRIPT: GREEN, Osr2State.ROBOT_HAND: BLUE, Osr2State.AUTO: MAGENTA,
    Osr2State.OFF: TEXT_MUTED, BUFFER: _NEUTRAL_PILL,
    OSR2_CONTROL_OFF: RED,
    # The held device's line is the handoff's gray -- nobody is moving it -- and
    # the word beside it says so in the same ink.
    OSR2_PARKED: _NEUTRAL_PILL, OSR2_RETRACTED: _NEUTRAL_PILL,
}


@dataclass(frozen=True)
class Osr2Line:
    """What the line says: which driver has the device, and the controls a
    source put on it.

    *state* is already resolved by whoever is drawing — one of
    :class:`~player_core.modes.Osr2State`, :data:`BUFFER`, or one of the
    control states — because what has the device is a different question on
    every panel and only the host can answer it.
    """

    state: str = Osr2State.OFF
    controls: tuple[Button, ...] = ()


class Osr2Section:
    """The line itself, drawn into whatever panel is hosting it."""

    def __init__(self) -> None:
        self._tiny = load_font(_SIZE_TINY)
        self._glyph = load_font(_SIZE_BODY, SYMBOL_FONT)

    def width(self, line: Osr2Line) -> int:
        """How wide the line runs — a floor on the panel holding it."""
        return (self._controls_width(line.controls)
                + text_width(self._tiny, LABEL) + _LABEL_GAP
                + self._pill_width(line.state))

    def draw(self, image: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int,
             line: Osr2Line, *, hover: tuple[int, int] | None = None,
             ) -> list[tuple[Rect, Button]]:
        """Paint the line with its top-left corner at ``(x, y)``, and hand back
        where each control landed so a press finds exactly what was drawn."""
        placed: list[tuple[Rect, Button]] = []
        run_x = x
        for button in line.controls:
            rect = (run_x, y, button.width, HEIGHT)
            draw_button(image, draw, rect, button,
                        hovered=hover is not None and contains(rect, *hover),
                        glyph_font=self._glyph, word_font=self._tiny)
            placed.append((rect, button))
            run_x += button.width + GAP

        label_x = x + self._controls_width(line.controls)
        draw.text((label_x, y + HEIGHT / 2), LABEL, font=self._tiny, anchor="lm",
                  fill=(*TEXT_MUTED, 255))
        state = LABELS.get(line.state, line.state)
        color = COLORS.get(line.state, TEXT_PRIMARY)
        pill_x = label_x + text_width(self._tiny, LABEL) + _LABEL_GAP
        # No frame around it: what has the device is a read-out, and an outlined
        # word beside two real buttons reads as a third one you can press.
        draw.text((pill_x + self._pill_width(line.state) / 2, y + HEIGHT / 2), state,
                  font=self._tiny, anchor="mm", fill=(*color, 255))
        return placed

    @staticmethod
    def _controls_width(controls: tuple[Button, ...]) -> int:
        """The controls' run and the gap after it -- nothing at all for a line
        with no controls, whose label then starts where they would have."""
        if not controls:
            return 0
        return sum(b.width for b in controls) + GAP * (len(controls) - 1) + _GROUP_GAP

    def _pill_width(self, state: str) -> int:
        return text_width(self._tiny, LABELS.get(state, state)) + _PILL_PAD
