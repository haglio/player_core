"""The console a Funestra keeps on its picture: what the room published, read whole, drawn where the room put it, pressed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from console_rows import console_rows
from funestra_fakes import FakePlayer

from player_core.console import ConsoleModel, ModeHud, console_text
from player_core.console_hud import _MARGIN
from player_core.console_overlay import ConsoleOverlay
from player_core.drive_readout import DriveHud, drive_text
from player_core.hud_overlay import HUD_OVERLAY_ID
from player_core.hud_placement import HudCorner
from player_core.modes import LengthMode, MainMode, Osr2State

WINDOW = (1000, 600)
LOWER_EDGE = 24
GENAU_MODE, KINO_MODE = "genau", "kino"


class SpyGate:
    def __init__(self) -> None:
        self.handed: list[DriveHud | None] = []
        self.told_the_device_drives_itself: list[bool] = []

    def readout(self, published, *, device_drives_itself: bool = False):
        self.handed.append(published)
        self.told_the_device_drives_itself.append(device_drives_itself)
        return published if published is not None else DriveHud()


def _console_file(path: Path, mode: str = KINO_MODE, **over) -> Path:
    payload = {"main_mode": mode, "active": True, "osr2": "off"}
    payload.update(over)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _drive_file(path: Path, position: int = 4_000) -> Path:
    path.write_text(drive_text(DriveHud(position=position)), encoding="utf-8")
    return path


def _overlay(tmp_path: Path, *, top_block=None, gate=None, drive: bool = True) -> tuple[ConsoleOverlay, FakePlayer, SpyGate]:
    player = FakePlayer()
    gate = gate or SpyGate()
    overlay = ConsoleOverlay(
        console_file=tmp_path / "console.json",
        drive_file=tmp_path / "drive.txt" if drive else None,
        command_file=tmp_path / "dashboard_cmd.txt",
        player=player, drive_gate=gate, top_block=top_block or ModeHud,
    )
    return overlay, player, gate


def _tick(overlay: ConsoleOverlay, speed: float = 1.0) -> None:
    overlay.tick(playback_speed=speed, window=WINDOW, lower_edge=LOWER_EDGE)


def _asked(tmp_path: Path) -> list[str]:
    path = tmp_path / "dashboard_cmd.txt"
    return path.read_text(encoding="utf-8").split() if path.exists() else []


class TestReadingTheConsole:
    def test_what_the_room_said_is_what_the_panel_shows(self, tmp_path):
        overlay, _player, _gate = _overlay(tmp_path)
        _console_file(tmp_path / "console.json", GENAU_MODE)

        _tick(overlay)

        assert overlay.console.main_mode == MainMode.GENAU

    def test_a_torn_read_keeps_the_panel_that_was_there(self, tmp_path):
        overlay, _player, _gate = _overlay(tmp_path)
        _console_file(tmp_path / "console.json", GENAU_MODE)
        _tick(overlay)

        (tmp_path / "console.json").write_text("{ half a fi", encoding="utf-8")
        _tick(overlay)

        assert overlay.console.main_mode == MainMode.GENAU

    def test_a_file_that_vanished_keeps_it_too(self, tmp_path):
        overlay, _player, _gate = _overlay(tmp_path)
        _console_file(tmp_path / "console.json", GENAU_MODE)
        _tick(overlay)

        (tmp_path / "console.json").unlink()
        _tick(overlay)

        assert overlay.console.main_mode == MainMode.GENAU

    def test_before_the_room_has_published_the_panel_is_drawn_at_rest(self, tmp_path):
        overlay, player, _gate = _overlay(tmp_path)

        _tick(overlay)

        assert overlay.console == ConsoleModel()
        assert HUD_OVERLAY_ID in player.overlays


class TestReadingTheMotion:
    def test_the_motion_published_is_handed_to_the_gate_the_same_frame(self, tmp_path):
        overlay, _player, gate = _overlay(tmp_path)
        _console_file(tmp_path / "console.json", GENAU_MODE)
        _drive_file(tmp_path / "drive.txt", position=4_000)

        _tick(overlay)

        assert gate.handed[-1].position == 4_000

    def test_a_torn_read_keeps_the_motion_that_was_there(self, tmp_path):
        overlay, _player, gate = _overlay(tmp_path)
        _console_file(tmp_path / "console.json", GENAU_MODE)
        _drive_file(tmp_path / "drive.txt", position=4_000)
        _tick(overlay)

        (tmp_path / "drive.txt").write_text("position=", encoding="utf-8")
        _tick(overlay)

        assert gate.handed[-1].position == 4_000

    def test_the_motion_is_read_in_kino_mode_too(self, tmp_path):
        overlay, _player, gate = _overlay(tmp_path)
        _console_file(tmp_path / "console.json", KINO_MODE)
        _drive_file(tmp_path / "drive.txt", position=4_000)

        _tick(overlay)

        assert gate.handed[-1].position == 4_000

    def test_nothing_published_yet_hands_the_gate_nothing(self, tmp_path):
        overlay, _player, gate = _overlay(tmp_path)

        _tick(overlay)

        assert gate.handed == [None]

    def test_a_funestra_with_no_motion_file_asks_the_gate_about_none(self, tmp_path):
        overlay, _player, gate = _overlay(tmp_path, drive=False)
        _drive_file(tmp_path / "drive.txt", position=4_000)

        _tick(overlay)

        assert gate.handed == [None]

    def test_the_gate_is_told_when_the_device_is_running_itself(self, tmp_path):
        overlay, _player, gate = _overlay(tmp_path)
        _console_file(tmp_path / "console.json", KINO_MODE, osr2=Osr2State.AUTO)

        _tick(overlay)

        assert gate.told_the_device_drives_itself == [True]

    def test_the_gate_composes_the_script_in_every_other_state(self, tmp_path):
        overlay, _player, gate = _overlay(tmp_path)
        _console_file(tmp_path / "console.json", KINO_MODE, osr2=Osr2State.FUNSCRIPT)

        _tick(overlay)

        assert gate.told_the_device_drives_itself == [False]


class TestWhatThePanelSays:
    def test_the_top_block_is_asked_of_whoever_runs_on_the_funestra_each_frame(self, tmp_path):
        said = {"video": "one"}
        overlay, player, _gate = _overlay(
            tmp_path, top_block=lambda: ModeHud(video=said["video"], length_mode=LengthMode.MIXED))
        _console_file(tmp_path / "console.json")

        _tick(overlay)
        first = player.overlays[HUD_OVERLAY_ID][2]
        said["video"] = "two"
        _tick(overlay)

        assert player.overlays[HUD_OVERLAY_ID][2] is not first

    def test_the_funestras_own_rate_is_folded_into_the_panel(self, tmp_path):
        overlay, player, _gate = _overlay(tmp_path)
        _console_file(tmp_path / "console.json")

        _tick(overlay, speed=1.0)
        first = player.overlays[HUD_OVERLAY_ID][2]
        _tick(overlay, speed=1.5)

        assert player.overlays[HUD_OVERLAY_ID][2] is not first

    def test_an_unchanged_panel_is_not_repainted(self, tmp_path):
        overlay, player, _gate = _overlay(tmp_path)
        _console_file(tmp_path / "console.json")

        _tick(overlay)
        first = player.overlays[HUD_OVERLAY_ID][2]
        _tick(overlay)

        assert player.overlays[HUD_OVERLAY_ID][2] is first


def _published(tmp_path: Path, corner: HudCorner = HudCorner.UPPER_LEFT, **over) -> ConsoleOverlay:
    model = ConsoleModel(main_mode=MainMode.KINO, hud_corner=corner, rows=console_rows(),
                         osr2=Osr2State.ROBOT_HAND, **over)
    (tmp_path / "console.json").write_text(console_text(model), encoding="utf-8")
    overlay, _player, _gate = _overlay(tmp_path)
    _tick(overlay)
    return overlay


class TestWhereTheConsoleIsDrawn:
    def test_the_panel_is_drawn_in_the_corner_the_room_moved_it_to(self, tmp_path):
        overlay = _published(tmp_path, HudCorner.LOWER_RIGHT)
        player = overlay._player
        panel_w, panel_h = overlay._painter._image.size

        x, y, _bgra = player.overlays[HUD_OVERLAY_ID]
        assert (x, y) == (WINDOW[0] - _MARGIN - panel_w, WINDOW[1] - LOWER_EDGE - _MARGIN - panel_h)

    def test_closing_takes_the_panel_down(self, tmp_path):
        overlay = _published(tmp_path)

        overlay.close()

        assert HUD_OVERLAY_ID not in overlay._player.overlays


class TestAPress:
    def test_on_a_button_posts_the_rooms_verb_and_is_taken(self, tmp_path):
        overlay = _published(tmp_path, HudCorner.LOWER_RIGHT)
        left, top, _bgra = overlay._player.overlays[HUD_OVERLAY_ID]
        (x, y, w, h), button = overlay._painter.buttons[0]

        assert overlay.press(left + x + w // 2, top + y + h // 2) is True

        assert _asked(tmp_path) == [button.command]

    def test_on_the_slab_between_buttons_is_taken_and_posts_nothing(self, tmp_path):
        overlay = _published(tmp_path)
        left, top, bgra = overlay._player.overlays[HUD_OVERLAY_ID]

        assert overlay.press(left + bgra.shape[1] - 2, top + bgra.shape[0] - 2) is True

        assert _asked(tmp_path) == []

    def test_off_the_slab_is_refused(self, tmp_path):
        overlay = _published(tmp_path)

        assert overlay.press(900, 500) is False
        assert _asked(tmp_path) == []

    def test_before_the_first_frame_nothing_is_under_a_press(self, tmp_path):
        overlay, _player, _gate = _overlay(tmp_path)

        assert overlay.press(10, 10) is False


class TestTheBandsOnTheOsr2Line:
    def _max_intensity_band(self, tmp_path):
        overlay = _published(tmp_path, max_intensity=50)
        left, top, _bgra = overlay._player.overlays[HUD_OVERLAY_ID]
        track = next(track for track in overlay._painter.tracks)
        x, y, w, h = track.rect
        return overlay, (left + x, top + y + h // 2), (left + x + w - 1, top + y + h // 2)

    def test_a_press_on_a_band_takes_hold_of_it_and_posts_what_it_asks(self, tmp_path):
        overlay, start, _end = self._max_intensity_band(tmp_path)

        assert overlay.press(*start) is True

        assert overlay.holding is True
        assert len(_asked(tmp_path)) == 1

    def test_a_drag_along_the_held_band_posts_the_new_level(self, tmp_path):
        overlay, start, end = self._max_intensity_band(tmp_path)
        overlay.press(*start)

        dragged = overlay.drag_to(*end)

        assert dragged
        assert _asked(tmp_path) == [_asked(tmp_path)[0], dragged]

    def test_a_drag_that_moves_nothing_posts_nothing(self, tmp_path):
        overlay, start, _end = self._max_intensity_band(tmp_path)
        overlay.press(*start)

        assert overlay.drag_to(*start) == ""
        assert len(_asked(tmp_path)) == 1

    def test_letting_go_ends_the_hold(self, tmp_path):
        overlay, start, _end = self._max_intensity_band(tmp_path)
        overlay.press(*start)

        overlay.release()

        assert overlay.holding is False


class TestNamingTheButtonUnderThePointer:
    def test_the_pointer_over_a_button_names_it_on_the_next_frame(self, tmp_path):
        overlay = _published(tmp_path)
        player = overlay._player
        left, top, before = player.overlays[HUD_OVERLAY_ID]
        (x, y, w, h), _button = overlay._painter.buttons[0]

        overlay.motion(left + x + w // 2, top + y + h // 2)
        _tick(overlay)

        assert player.overlays[HUD_OVERLAY_ID][2] is not before

    def test_the_pointer_over_no_button_names_nothing(self, tmp_path):
        overlay = _published(tmp_path)
        player = overlay._player
        _left, _top, before = player.overlays[HUD_OVERLAY_ID]

        overlay.motion(900, 500)
        _tick(overlay)

        assert player.overlays[HUD_OVERLAY_ID][2] is before


@pytest.mark.parametrize("corner", list(HudCorner))
def test_a_press_lands_on_the_panel_wherever_the_room_put_it(tmp_path, corner):
    overlay = _published(tmp_path, corner)
    left, top, _bgra = overlay._player.overlays[HUD_OVERLAY_ID]
    (x, y, w, h), button = overlay._painter.buttons[0]

    overlay.press(left + x + w // 2, top + y + h // 2)

    assert _asked(tmp_path) == [button.command]
