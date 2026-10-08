"""A Funestra, ticked: it plays what it was handed, answers its files, publishes its status and paints its own controls."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
from console_rows import console_rows
from funestra_fakes import FakePlayer

from player_core.console import ConsoleModel, ModeHud, console_text
from player_core.display import BLACK_OVERLAY_ID
from player_core.funestra import Channels, Funestra
from player_core.hud_overlay import HUD_OVERLAY_ID
from player_core.modes import LengthMode, MainMode, Osr2State
from player_core.playlist import read_playlist
from player_core.session_quit import SESSION_QUIT
from player_core.timeline import TIMELINE_HEIGHT, bar_track_x
from player_core.volume import CHIP_H, CHIP_W, chip_xy

WINDOW = (640, 480)


def _on_the_row(funestra, player, part: str = "track", *, along: int | None = None):
    """A window point on one of the row's controls, which the panel draws at
    its foot.  The panel is wherever the room put it, so this is read back off
    the overlay it was composited at."""
    left, top, _bgra = player.overlays[HUD_OVERLAY_ID]
    x, y, width, height = funestra._panel.row_rect
    if part == "track":
        x0, x1 = bar_track_x(width)
        return left + x + (along if along is not None else (x0 + x1) // 2), top + y + height - 4
    cx, cy = chip_xy(win_w=width, win_h=height, timeline_h=TIMELINE_HEIGHT)
    across = 4 if part == "speaker" else CHIP_W - 6
    return left + x + cx + across, top + y + cy + CHIP_H // 2


def _clips(tmp_path: Path, *names: str) -> list[Path]:
    clips = []
    for name in names:
        clip = tmp_path / f"{name}.mp4"
        clip.write_bytes(b"")
        clips.append(clip)
    return clips


def _channels(tmp_path: Path, lines: list[str], *, commands: str = "QUIT\n",
              hud: bool = False, in_a_session: bool = False) -> Channels:
    (tmp_path / "playlist.tsv").write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    (tmp_path / "cmd.txt").write_text(commands, encoding="utf-8")
    return Channels(
        playlist=tmp_path / "playlist.tsv",
        command=tmp_path / "cmd.txt",
        paused=tmp_path / "paused.txt",
        status=tmp_path / "status.txt",
        hud=tmp_path / "portrait_hud.json" if hud else None,
        dashboard_cmd=tmp_path / "dashboard_cmd.txt" if hud or in_a_session else None,
    )


def _funestra(tmp_path: Path, lines: list[str], *, audible: bool = True, tiles: bool = False,
              **channel_choices) -> tuple[Funestra, FakePlayer]:
    channels = _channels(tmp_path, lines, **channel_choices)
    player = FakePlayer()
    return Funestra(player, channels=channels, playlist=read_playlist(channels.playlist),
                    audible=audible, tiles=tiles), player


def _status(tmp_path: Path) -> str:
    return (tmp_path / "status.txt").read_text(encoding="utf-8")


def _asked(tmp_path: Path) -> list[str]:
    path = tmp_path / "dashboard_cmd.txt"
    return path.read_text(encoding="utf-8").split() if path.exists() else []


def test_one_pass_plays_publishes_and_paints_then_quit_stops_it(tmp_path):
    clips = _clips(tmp_path, "v0", "v1")
    funestra, player = _funestra(tmp_path, [str(clip) for clip in clips])

    funestra.tick(window=WINDOW)

    assert player.opened[0] == clips[0]
    assert f"video={clips[0]}" in _status(tmp_path)
    assert funestra.stopped is True
    funestra.close()
    assert player.closed is True


def test_a_window_wearing_no_panel_draws_nothing_over_its_picture(tmp_path):
    """The track, the time and the volume are a block of the panel, so a window
    with no panel to wear has nowhere to put them -- and the picture comes
    through untouched instead of carrying a row along its lower edge."""
    funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])

    funestra.tick(window=WINDOW)

    assert player.overlays == {}


def test_the_row_says_where_the_clip_is_and_how_long_it_runs(tmp_path):
    funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])

    funestra.tick(window=WINDOW)

    row = funestra.clip_row()
    assert (row.position_ms, row.duration_ms) == (0.0, player.duration_ms)
    assert row.playhead is not None
    assert row.volume is funestra._volume.hud


def test_a_scripted_clips_track_is_filled_across_the_width_the_panel_drew_it_at(tmp_path):
    """The colors fill the track, and a panel is as wide as what is on it, so
    they are measured across the row the panel drew rather than the window."""
    clip = _clips(tmp_path, "v0")[0]
    script = tmp_path / "v0.funscript"
    script.write_text('{"actions": [{"at": 0, "pos": 0}, {"at": 900, "pos": 100}, '
                      '{"at": 2400, "pos": 10}]}', encoding="utf-8")
    funestra, _player = _funestra(tmp_path, [f"{clip}\t{script}"], hud=True)
    _publish_panel(tmp_path)

    funestra.tick(window=WINDOW)
    funestra.tick(window=WINDOW)

    x0, x1 = bar_track_x(funestra._panel.row_rect[2])
    assert len(funestra._strip.colors) == x1 - x0


def test_a_picture_on_screen_puts_no_row_on_the_panel(tmp_path):
    funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")],
                                 hud=True)
    _publish_panel(tmp_path)
    player.showing_picture = True

    funestra.tick(window=WINDOW)

    assert funestra.clip_row() is None
    assert funestra._panel.row_rect is None


def test_commands_drain_and_act_before_the_frame_is_published(tmp_path):
    clips = _clips(tmp_path, "v0", "v1")
    funestra, _player = _funestra(tmp_path, [str(clip) for clip in clips], commands="NEXT\nQUIT\n")

    funestra.tick(window=WINDOW)

    assert f"video={clips[1]}" in _status(tmp_path)


def test_a_list_written_under_the_window_is_taken_with_no_verb_sent(tmp_path):
    """The host writes the list and then queues one reload, and that queue drops the
    line when the file is held for longer than 25ms -- after which the window went
    on playing what it had, with the new list on disk beside it, for good."""
    clips = _clips(tmp_path, "v0", "v1", "v2")
    funestra, _player = _funestra(tmp_path, [str(clips[0])], commands="")
    (tmp_path / "playlist.tsv").write_text(f"{clips[2]}\n", encoding="utf-8")

    funestra.tick(window=WINDOW)

    assert f"video={clips[2]}" in _status(tmp_path)


def test_reload_playlist_reads_the_list_it_was_handed_again(tmp_path):
    clips = _clips(tmp_path, "v0", "v1", "v2")
    funestra, _player = _funestra(tmp_path, [str(clips[0])], commands="")
    (tmp_path / "playlist.tsv").write_text(f"{clips[0]}\n{clips[2]}\n", encoding="utf-8")
    (tmp_path / "cmd.txt").write_text("RELOAD_PLAYLIST\nNEXT\n", encoding="utf-8")

    funestra.tick(window=WINDOW)

    assert f"video={clips[2]}" in _status(tmp_path)


def test_the_paused_flag_reaches_the_player_each_pass(tmp_path):
    funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])
    (tmp_path / "paused.txt").write_text("1", encoding="utf-8")

    funestra.tick(window=WINDOW)

    assert player.paused is True


def test_a_paused_flag_already_up_opens_the_player_paused(tmp_path):
    clips = _clips(tmp_path, "v0")
    channels = _channels(tmp_path, [str(clips[0])])
    channels.paused.write_text("1", encoding="utf-8")

    funestra = Funestra(FakePlayer(), channels=channels, playlist=read_playlist(channels.playlist))

    assert funestra.playback.is_paused is True


class TestTheWindowsClose:
    def test_in_a_session_it_asks_the_session_and_keeps_playing(self, tmp_path):
        funestra, _player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")],
                                      commands="", in_a_session=True)

        funestra.close_requested()

        assert funestra.stopped is False
        assert _asked(tmp_path) == [SESSION_QUIT]

    def test_with_no_session_to_ask_it_ends_this_player(self, tmp_path):
        funestra, _player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")],
                                      commands="")

        funestra.close_requested()

        assert funestra.stopped is True


class TestAPress:
    """On the row the panel draws, which is where the track, the time and the
    volume are now."""

    def _wearing_a_panel(self, tmp_path, *, audible: bool = True):
        funestra, player = _funestra(
            tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")],
            hud=True, audible=audible)
        _publish_panel(tmp_path)
        funestra.tick(window=WINDOW)
        return funestra, player

    def test_on_the_track_seeks_the_clip(self, tmp_path):
        funestra, player = self._wearing_a_panel(tmp_path)
        x0, x1 = bar_track_x(funestra._panel.row_rect[2])

        funestra.press(*_on_the_row(funestra, player), window=WINDOW)

        assert len(player.seeks) == 1
        assert abs(player.seeks[0] - player.duration_ms / 2) <= player.duration_ms / (x1 - x0)

    def test_on_the_speaker_unmutes_this_player(self, tmp_path):
        funestra, player = self._wearing_a_panel(tmp_path)

        funestra.press(*_on_the_row(funestra, player, "speaker"), window=WINDOW)

        assert player.muted is False
        assert player.seeks == []

    def test_on_the_speaker_of_a_silent_build_sets_nothing(self, tmp_path):
        funestra, player = self._wearing_a_panel(tmp_path, audible=False)

        funestra.press(*_on_the_row(funestra, player, "speaker"), window=WINDOW)

        assert player.muted is True

    def test_held_along_the_slider_keeps_setting_the_level(self, tmp_path):
        funestra, player = self._wearing_a_panel(tmp_path)
        at = _on_the_row(funestra, player, "slider")

        funestra.press(*at, window=WINDOW)
        funestra.motion(*at, held=True, window=WINDOW)

        assert player.volume == 100

    def test_anywhere_off_the_panel_asks_the_session_to_pause_everything(self, tmp_path):
        funestra, player = self._wearing_a_panel(tmp_path)
        left, top, panel = player.overlays[HUD_OVERLAY_ID]

        funestra.press(left + panel.shape[1] + 20, top + panel.shape[0] + 20, window=WINDOW)

        assert _asked(tmp_path) == ["omnipause_toggle"]


def test_each_pass_carries_a_still_s_move_a_little_further(tmp_path):
    funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])

    funestra.tick(window=WINDOW)

    assert player.pushes == 1


def test_a_tiling_player_lays_its_picture_out_across_its_window(tmp_path):
    funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")], tiles=True)

    funestra.tick(window=WINDOW)

    assert player.tiled_to == [WINDOW]


def test_a_player_that_does_not_tile_is_never_asked_to(tmp_path):
    funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])

    funestra.tick(window=WINDOW)

    assert player.tiled_to == []


def _publish_panel(tmp_path: Path) -> None:
    (tmp_path / "portrait_hud.json").write_text(json.dumps({"player": "portrait"}),
                                                encoding="utf-8")


def test_the_panel_its_source_publishes_is_the_one_thing_over_the_picture(tmp_path):
    funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")], hud=True)
    _publish_panel(tmp_path)

    funestra.tick(window=WINDOW)

    assert list(player.overlays) == [HUD_OVERLAY_ID]


def test_on_a_window_the_way_of_playing_is_mpv_opened_on_that_window(tmp_path):
    clips = _clips(tmp_path, "v0")
    channels = _channels(tmp_path, [str(clips[0])])
    player = FakePlayer()

    with patch("player_core.funestra.MpvPlayer", return_value=player) as mpv:
        funestra = Funestra.on_window(4242, channels=channels, playlist=read_playlist(channels.playlist))

    mpv.assert_called_once_with(4242, muted=True, loop_file=False, prefetch=True)
    assert funestra.playback.current_video == clips[0]


def _console_channels(tmp_path: Path, lines: list[str], *, commands: str = "") -> Channels:
    channels = _channels(tmp_path, lines, commands=commands, in_a_session=True)
    return replace(channels, console=tmp_path / "console.json", drive=tmp_path / "drive.txt")


def _publish_console(tmp_path: Path, **over) -> None:
    model = ConsoleModel(main_mode=MainMode.KINO, rows=console_rows(), osr2=Osr2State.ROBOT_HAND, **over)
    (tmp_path / "console.json").write_text(console_text(model), encoding="utf-8")


class Kino:
    """What runs on a Funestra, as the Funestra sees it: its own verbs, a pass
    of its own each frame, lines in the status file, and the console's top block."""

    def __init__(self, playback) -> None:
        self.playback = playback
        self.commands: list[str] = []
        self.ticks: list[tuple[int, float]] = []
        self.video = "Jane Doe - scene one"

    def apply_command(self, command: str) -> bool:
        self.commands.append(command)
        return command.startswith("KINO_")

    def tick(self) -> None:
        self.ticks.append((self.playback.loads, self.playback.position_ms))

    def status_fields(self) -> dict[str, str]:
        return {"length_mode": "shorts", "compilation": "Vol 3"}

    def top_block(self) -> ModeHud:
        return ModeHud(video=self.video, length_mode=LengthMode.SHORTS)


def _main(tmp_path: Path, *, commands: str = "", user=Kino) -> tuple[Funestra, FakePlayer, Kino]:
    channels = _console_channels(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0", "v1")],
                                 commands=commands)
    _publish_console(tmp_path)
    player = FakePlayer()
    made: list[Kino] = []

    def make(playback):
        made.append(user(playback))
        return made[-1]

    funestra = Funestra(player, channels=channels, playlist=read_playlist(channels.playlist),
                        locked=True, sound_is_the_rooms=True, user=make)
    return funestra, player, made[0]


class TestTheMainFunestra:
    """A Funestra handed a console file draws the room's console in place of a
    satellite panel, opens holding its item, and leaves its sound to the room."""

    def test_it_opens_holding_its_item(self, tmp_path):
        funestra, player, _kino = _main(tmp_path)

        assert funestra.playback.is_locked is True
        assert player.loop_file is True

    def test_it_draws_the_console_the_room_published(self, tmp_path):
        funestra, player, _kino = _main(tmp_path)

        funestra.tick(window=WINDOW)

        assert list(player.overlays) == [HUD_OVERLAY_ID]

    def test_the_console_leads_with_what_runs_on_the_funestra_says_it_is_playing(self, tmp_path):
        funestra, player, kino = _main(tmp_path)
        funestra.tick(window=WINDOW)
        before = player.overlays[HUD_OVERLAY_ID][2]

        kino.video = "Ann Bly - scene two"
        funestra.tick(window=WINDOW)

        assert player.overlays[HUD_OVERLAY_ID][2] is not before

    def test_a_press_on_a_console_button_asks_the_room_and_never_pauses_it(self, tmp_path):
        funestra, player, _kino = _main(tmp_path)
        funestra.tick(window=WINDOW)
        left, top, _bgra = player.overlays[HUD_OVERLAY_ID]
        (x, y, w, h), button = funestra._panel._painter.buttons[0]

        funestra.press(left + x + w // 2, top + y + h // 2, window=WINDOW)

        assert _asked(tmp_path) == [button.command]

    def test_a_press_on_the_slab_between_buttons_asks_for_nothing(self, tmp_path):
        funestra, player, _kino = _main(tmp_path)
        funestra.tick(window=WINDOW)
        left, top, bgra = player.overlays[HUD_OVERLAY_ID]

        funestra.press(left + bgra.shape[1] - 2, top + bgra.shape[0] - 2, window=WINDOW)

        assert _asked(tmp_path) == []

    def test_its_sound_is_the_rooms_so_the_chip_asks_rather_than_sets(self, tmp_path):
        funestra, player, _kino = _main(tmp_path)
        funestra.tick(window=WINDOW)

        funestra.press(*_on_the_row(funestra, player, "slider"), window=WINDOW)

        assert _asked(tmp_path) == ["audio_set_volume|100"]
        assert player.volume == 100

    def test_the_rooms_level_reaches_the_player_through_the_command_file(self, tmp_path):
        funestra, player, _kino = _main(tmp_path, commands="SET_VOLUME 40 0\n")

        funestra.tick(window=WINDOW)

        assert player.volume == 40

    def test_it_opens_unmuted_so_the_rooms_level_is_heard(self, tmp_path):
        _funestra, player, _kino = _main(tmp_path)

        assert player.muted is False

    def test_a_held_band_is_let_go_when_the_button_comes_up(self, tmp_path):
        funestra, player, _kino = _main(tmp_path)
        _publish_console(tmp_path, max_intensity=50)
        funestra.tick(window=WINDOW)
        left, top, _bgra = player.overlays[HUD_OVERLAY_ID]
        x, y, _w, h = funestra._panel._painter.tracks[0].rect
        funestra.press(left + x, top + y + h // 2, window=WINDOW)
        assert funestra._panel.holding is True

        funestra.release()

        assert funestra._panel.holding is False


class TestWhatRunsOnTheFunestra:
    def test_it_is_handed_the_playback_it_runs_on(self, tmp_path):
        funestra, _player, kino = _main(tmp_path)

        assert kino.playback is funestra.playback

    def test_its_verbs_are_asked_before_the_funestras_own(self, tmp_path):
        funestra, _player, kino = _main(tmp_path, commands="KINO_THING\nNEXT\n")

        funestra.tick(window=WINDOW)

        assert kino.commands == ["KINO_THING", "NEXT"]
        assert funestra.playback.index == 1

    def test_a_verb_neither_answers_is_named_on_the_log(self, tmp_path, caplog):
        funestra, _player, _kino = _main(tmp_path, commands="FLOOP\n")

        with caplog.at_level("WARNING", logger="player_core.funestra"):
            funestra.tick(window=WINDOW)

        assert "FLOOP" in caplog.text

    def test_it_takes_a_pass_of_its_own_each_frame_before_the_playback_advances(self, tmp_path):
        funestra, player, kino = _main(tmp_path, commands="NEXT\n")
        funestra.playback.set_locked(False)
        player.position_ms = 1_000.0

        funestra.tick(window=WINDOW)
        player.simulate_eof_advance()
        funestra.tick(window=WINDOW)

        assert [loads for loads, _position in kino.ticks] == [2, 2]
        assert funestra.playback.loads == 3

    def test_its_lines_ride_in_the_status_file_after_the_funestras_own(self, tmp_path):
        funestra, _player, _kino = _main(tmp_path)

        funestra.tick(window=WINDOW)

        status = _status(tmp_path)
        assert "length_mode=shorts\n" in status
        assert "compilation=Vol 3\n" in status
        assert status.index("portrait=") < status.index("length_mode=")


class TestTheDisplay:
    def test_told_off_it_covers_the_picture_and_paints_nothing_else(self, tmp_path):
        funestra, player, _kino = _main(tmp_path, commands="DISPLAY_OFF\n")

        funestra.tick(window=WINDOW)

        assert list(player.overlays) == [BLACK_OVERLAY_ID]
        assert player.pushes == 0

    def test_a_blanked_funestra_still_publishes_its_status(self, tmp_path):
        funestra, _player, _kino = _main(tmp_path, commands="DISPLAY_OFF\n")

        funestra.tick(window=WINDOW)

        assert "video=" in _status(tmp_path)

    def test_told_on_again_it_paints_the_picture_and_its_controls(self, tmp_path):
        funestra, player, _kino = _main(tmp_path, commands="DISPLAY_OFF\n")
        funestra.tick(window=WINDOW)
        (tmp_path / "cmd.txt").write_text("DISPLAY_ON\n", encoding="utf-8")

        funestra.tick(window=WINDOW)

        assert BLACK_OVERLAY_ID not in player.overlays
        assert HUD_OVERLAY_ID in player.overlays
        assert player.pushes == 1


def _scripted_main(tmp_path: Path) -> tuple[Funestra, FakePlayer]:
    clip = _clips(tmp_path, "v0")[0]
    script = tmp_path / "v0.funscript"
    script.write_text('{"actions": [{"at": 0, "pos": 0}, {"at": 900, "pos": 100}, '
                      '{"at": 2400, "pos": 10}]}', encoding="utf-8")
    channels = _console_channels(tmp_path, [f"{clip}\t{script}"])
    _publish_console(tmp_path)
    player = FakePlayer(duration_ms=600_000.0)
    player.screenshot = np.zeros((10, 20, 4), dtype=np.uint8)
    return Funestra(player, channels=channels, playlist=read_playlist(channels.playlist),
                    locked=True, sound_is_the_rooms=True, user=Kino), player


class TestAStretchOfTheItem:
    def test_a_mark_zooms_the_track_to_the_stretch_around_it(self, tmp_path):
        funestra, player = _scripted_main(tmp_path)
        funestra.tick(window=WINDOW)
        assert funestra.clip_row().duration_ms == player.duration_ms

        funestra.playback.set_mark(50_000)
        player.position_ms = 51_000.0
        funestra.tick(window=WINDOW)

        row = funestra.clip_row()
        assert row.duration_ms < player.duration_ms
        assert row.record_in_ms == 50_000 - funestra._strip.window[0]

    def test_a_press_on_the_zoomed_track_seeks_inside_the_stretch_it_shows(self, tmp_path):
        funestra, player = _scripted_main(tmp_path)
        funestra.playback.set_mark(50_000)
        player.position_ms = 51_000.0
        funestra.tick(window=WINDOW)

        funestra.press(*_on_the_row(funestra, player), window=WINDOW)

        assert 48_000 <= player.seeks[-1] <= 70_000

    def test_a_running_range_hangs_its_two_frames_under_the_panel(self, tmp_path):
        funestra, player = _scripted_main(tmp_path)
        funestra.playback.set_ab_loop(2_000, 4_000)
        player.position_ms = 2_000.0

        funestra.tick(window=WINDOW)
        player.position_ms = 3_700.0
        funestra.tick(window=WINDOW)

        assert {Funestra.IN_FRAME_OVERLAY_ID, Funestra.OUT_FRAME_OVERLAY_ID} <= set(player.overlays)
        assert player.overlays[Funestra.IN_FRAME_OVERLAY_ID][2] is player.screenshot
        panel_top, panel = player.overlays[HUD_OVERLAY_ID][1], player.overlays[HUD_OVERLAY_ID][2]
        assert player.overlays[Funestra.IN_FRAME_OVERLAY_ID][1] >= panel_top + panel.shape[0]

    def test_the_end_of_the_range_takes_both_frames_down(self, tmp_path):
        funestra, player = _scripted_main(tmp_path)
        funestra.playback.set_ab_loop(2_000, 4_000)
        funestra.tick(window=WINDOW)

        funestra.playback.clear_ab_loop()
        funestra.tick(window=WINDOW)

        assert not {Funestra.IN_FRAME_OVERLAY_ID, Funestra.OUT_FRAME_OVERLAY_ID} & set(player.overlays)

    def test_a_frame_mpv_could_not_give_is_asked_for_again(self, tmp_path):
        funestra, player = _scripted_main(tmp_path)
        player.screenshot = None
        funestra.playback.set_ab_loop(2_000, 4_000)

        funestra.tick(window=WINDOW)

        assert Funestra.IN_FRAME_OVERLAY_ID not in player.overlays
        assert player.screenshots == 1

    def test_the_frames_sit_under_the_panel_and_the_black_covers_them(self):
        assert max(Funestra.IN_FRAME_OVERLAY_ID, Funestra.OUT_FRAME_OVERLAY_ID) < HUD_OVERLAY_ID
        assert max(Funestra.OVERLAY_IDS) < BLACK_OVERLAY_ID
