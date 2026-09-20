"""The device's own line, drawn the same wherever a panel says who has the OSR2."""
from __future__ import annotations

import numpy as np
from shared_ui.palette import BLUE, GREEN, RED, TEXT_MUTED

from player_core.hud_button import Button
from player_core.hud_osr2 import (
    HEIGHT,
    LABELS,
    Osr2Line,
    Osr2Section,
)
from player_core.hud_panel import HudPanel
from player_core.modes import Osr2State


def _drawn(line: Osr2Line) -> tuple[HudPanel, list]:
    section = Osr2Section()
    panel = HudPanel(section.width(line) + 20, HEIGHT + 20)
    placed = section.draw(panel.image, panel.draw, 10, 10, line)
    return panel, placed


def _has(panel: HudPanel, color) -> bool:
    pixels = np.array(panel.image.convert("RGB"))
    return bool((pixels == np.array(color)).all(axis=-1).any())


class TestTheLine:
    def test_it_names_who_has_the_device(self):
        assert LABELS[Osr2State.FUNSCRIPT] == "FunScript"
        assert LABELS[Osr2State.ROBOT_HAND] == "Robot Hand"

    def test_a_funscript_driving_is_said_in_green(self):
        panel, _ = _drawn(Osr2Line(state=Osr2State.FUNSCRIPT))
        assert _has(panel, GREEN)

    def test_the_motion_driving_is_said_in_blue(self):
        panel, _ = _drawn(Osr2Line(state=Osr2State.ROBOT_HAND))
        assert _has(panel, BLUE)

    def test_nothing_driving_is_said_in_the_muted_gray(self):
        panel, _ = _drawn(Osr2Line(state=Osr2State.OFF))
        assert _has(panel, TEXT_MUTED)

    def test_the_app_having_let_go_is_said_in_red(self):
        panel, _ = _drawn(Osr2Line(state="control_off"))
        assert _has(panel, RED)


class TestTheControlsOnIt:
    def test_a_line_with_no_controls_is_just_the_label_and_the_pill(self):
        section = Osr2Section()
        bare = Osr2Line(state=Osr2State.OFF)
        assert section.width(bare) < section.width(
            Osr2Line(state=Osr2State.OFF, controls=(_park(),)))

    def test_each_control_comes_back_as_a_target_where_it_was_drawn(self):
        park = _park()
        _panel, placed = _drawn(Osr2Line(state=Osr2State.OFF, controls=(park,)))
        assert [button for _rect, button in placed] == [park]
        (x, y, w, h), _button = placed[0]
        assert (x, y, w, h) == (10, 10, park.width, HEIGHT)


def _park() -> Button:
    return Button("robot_hand_park", "P", "Parked")
