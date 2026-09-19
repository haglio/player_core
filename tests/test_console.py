"""The main console: the panel whichever player holds the slot draws, and where
a press on it lands."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from player_core.console import (
    BUTTON,
    GAP,
    GROUP_GAP,
    OSR2_RETRACTED,
    ROW_LABEL_W,
    VALUE_W,
    ConsoleModel,
    console_text,
    hit_test,
    main_player_displays,
    parse_console,
    place_rows,
    read_console,
    rows_height,
    shape_label,
    tooltip_at,
)
from player_core.hud_button import Button
from player_core.hud_marks import BROKER_ICON, MINIMIZE_ICON
from player_core.modes import MainMode, Osr2State

# A source's rows, made up: a mode pair with minimize standing apart, and a
# named read-out between two arrows.
ROWS = (
    (Button("go_video", "Video", "Video mode", width=40, lit=True),
     Button("go_other", "Other", "The other mode", width=40),
     Button("park", MINIMIZE_ICON, "Park the window", group_break=True)),
    (Button("", "Playback speed", "", width=ROW_LABEL_W),
     Button("slower", "−", "Slower", group_break=True),
     Button("", "", "", width=VALUE_W, host_value="playback_speed"),
     Button("faster", "+", "Faster"),
     Button("spent", "⏭", "Nothing left to step to", dim=True)),
)


def _placed() -> list:
    return place_rows([list(row) for row in ROWS], x=0, y=0)


def _rect(command: str):
    return next(rect for rect, button in _placed() if button.command == command)


class TestShapeLabel:
    """The control that cycles the waveform names it on hover, so the name lives
    with the console rather than with the readout that no longer prints it."""

    def test_names_the_waveform_instead_of_leaving_it_to_the_curve(self):
        assert shape_label("sine") == "Sine"
        assert shape_label("rounded_square") == "Square"
        assert shape_label("sawtooth") == "Sawtooth"

    def test_an_unknown_shape_is_titled_rather_than_dropped(self):
        assert shape_label("half_moon") == "Half Moon"


class TestTheDeviceRunningItself:
    """Auto mode is the OSR2 on its own firmware: the broker stops forwarding
    the script's T-Code and Genau is not sending either.  Asked of the model
    rather than compared against the word, because two apps outside this
    package draw a picture that depends on the answer."""

    def test_auto_is_the_device_driving_itself(self):
        assert ConsoleModel(osr2=Osr2State.AUTO).device_drives_itself is True

    @pytest.mark.parametrize("osr2", [Osr2State.OFF, Osr2State.FUNSCRIPT,
                                      Osr2State.ROBOT_HAND])
    def test_nothing_else_is(self, osr2):
        assert ConsoleModel(osr2=osr2).device_drives_itself is False


class TestModePredicates:
    def test_main_player_displays_covers_video_mode_alone(self):
        assert main_player_displays(MainMode.VIDEO)
        assert not main_player_displays(MainMode.GENAU)


class TestReadConsole:
    def test_it_reads_back_what_fun_time_published(self, tmp_path: Path):
        path = tmp_path / "main_player_console.json"
        path.write_text(json.dumps({
            "main_mode": MainMode.VIDEO, "active": True, "osr2": Osr2State.ROBOT_HAND,
            "osr2_control": OSR2_RETRACTED, "locked": False, "latest": True,
        }), encoding="utf-8")

        model = read_console(path)

        assert model == ConsoleModel(main_mode=MainMode.VIDEO, active=True,
                                     osr2=Osr2State.ROBOT_HAND,
                                     osr2_control=OSR2_RETRACTED, locked=False,
                                     latest=True)

    def test_a_panel_that_says_nothing_about_the_lock_reads_as_locked(self, tmp_path: Path):
        """Which is where both players open, and what a Fun Time too old to
        publish the flag is still describing."""
        path = tmp_path / "main_player_console.json"
        path.write_text(json.dumps({"main_mode": MainMode.VIDEO}), encoding="utf-8")

        assert read_console(path).locked is True
        assert ConsoleModel().locked is True

    def test_a_panel_that_says_nothing_about_the_order_names_none(self, tmp_path: Path):
        """Fun Time publishes the flag every tick; a file that says nothing
        about it is from a host with no browse order to name."""
        path = tmp_path / "main_player_console.json"
        path.write_text(json.dumps({"main_mode": MainMode.VIDEO}), encoding="utf-8")

        assert read_console(path).latest is None

    def test_a_key_the_panel_no_longer_carries_is_passed_over(self):
        """The switches the console's buttons were once lit from still come
        from a publisher on an older release; the panel reads the same without
        them."""
        parsed = parse_console(json.dumps({
            "main_mode": MainMode.GENAU, "scripted_filter": True, "broker": True,
            "loop_state": "looping", "cruise": True, "learned": True,
            "shape": "sawtooth", "plays_vr": True}))

        assert parsed == ConsoleModel(main_mode=MainMode.GENAU)

    def test_a_torn_or_missing_file_keeps_the_console_you_have(self, tmp_path: Path):
        path = tmp_path / "main_player_console.json"
        assert read_console(path) is None

        path.write_text('{"main_mode": "video"', encoding="utf-8")
        assert read_console(path) is None


class TestLayout:
    def test_rows_stack_down_at_the_declared_size(self):
        placed = _placed()

        assert all(rect[3] == BUTTON for rect, _b in placed)
        assert {rect[1] for rect, _b in placed} == {0, _rect("slower")[1]}
        assert rows_height([list(row) for row in ROWS]) == _rect("slower")[1] + BUTTON

    def test_a_group_break_opens_the_wider_gap_and_nothing_else_does(self):
        go_video, go_other, park = _rect("go_video"), _rect("go_other"), _rect("park")

        assert go_other[0] - (go_video[0] + go_video[2]) == GAP
        assert park[0] - (go_other[0] + go_other[2]) == GROUP_GAP

    def test_a_press_finds_the_button_under_it(self):
        x, y, _w, _h = _rect("faster")

        assert hit_test(_placed(), x + 1, y + 1) == "faster"
        assert tooltip_at(_placed(), x + 1, y + 1) == "Faster"

    def test_a_press_off_every_button_posts_nothing(self):
        assert hit_test(_placed(), 5000, 5000) == ""

    def test_a_read_out_is_not_a_hit_target(self):
        rect = next(r for r, b in _placed() if b.host_value == "playback_speed")

        assert hit_test(_placed(), rect[0] + 1, rect[1] + 1) == ""

    def test_a_dimmed_button_posts_nothing_but_still_names_itself(self):
        """Knowing why it cannot be pressed is the point of hovering it."""
        x, y, _w, _h = _rect("spent")

        assert hit_test(_placed(), x + 1, y + 1) == ""
        assert tooltip_at(_placed(), x + 1, y + 1) == "Nothing left to step to"


class TestThePublishedConsoleIsWrittenWhereItIsRead:
    """Fun Time publishes a ConsoleModel as text and the main player parses it
    back; the keys are spelled once, here."""

    def test_every_published_field_survives_the_round_trip(self):
        model = ConsoleModel(
            main_mode=MainMode.GENAU, active=True, osr2=Osr2State.AUTO,
            osr2_control=OSR2_RETRACTED, locked=False, latest=True,
        )

        assert parse_console(console_text(model)) == model

    def test_the_rows_a_source_declares_survive_it_too(self):
        """The buttons themselves ride the panel: what each posts, its face,
        its tooltip and its state, row by row, and the controls on the OSR2
        line beside them."""
        model = ConsoleModel(
            rows=ROWS,
            osr2_controls=(Button("broker_panel", BROKER_ICON, "Broker", warn=True),),
        )

        assert parse_console(console_text(model)) == model

    def test_what_the_drawing_player_folds_in_is_not_published(self):
        """The playback rate and the clip pace are the drawing host's own --
        Fun Time neither sets them nor hears about them -- so the text does not
        carry them and they come back at rest."""
        model = ConsoleModel(playback_speed=1.5, advance_interval=12)

        parsed = parse_console(console_text(model))

        assert parsed == ConsoleModel()
        assert "playback_speed" not in json.loads(console_text(model))

    def test_an_order_the_session_does_not_offer_stays_absent(self):
        assert parse_console(console_text(ConsoleModel(latest=None))).latest is None
        assert parse_console(console_text(ConsoleModel(latest=False))).latest is False

    def test_a_torn_read_is_no_panel(self):
        assert parse_console('{"main_mode": "video"') is None
        assert parse_console("") is None
