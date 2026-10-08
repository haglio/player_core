"""A Funestra, ticked: it plays what it was handed, answers its files, publishes its status and paints its own controls."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from funestra_fakes import FakePlayer

from player_core.funestra import Channels, Funestra
from player_core.funscript import load as load_funscript
from player_core.heatmap import build_heatmap
from player_core.hud_overlay import HUD_OVERLAY_ID
from player_core.playhead import PlayheadHudPainter, readout_xy, video_playhead
from player_core.playlist import read_playlist
from player_core.session_quit import SESSION_QUIT
from player_core.timeline import TIMELINE_HEIGHT, bar_track_x, progress_bar_bgra
from player_core.volume import chip_xy

WINDOW = (640, 480)


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


def test_one_pass_plays_publishes_and_paints_then_quit_stops_it(tmp_path):
    clips = _clips(tmp_path, "v0", "v1")
    funestra, player = _funestra(tmp_path, [str(clip) for clip in clips])

    funestra.tick(window=WINDOW)

    assert player.opened[0] == clips[0]
    assert f"video={clips[0]}" in _status(tmp_path)
    assert len(player.overlays) == 3
    assert funestra.stopped is True
    funestra.close()
    assert player.closed is True


def test_one_pass_puts_up_where_the_clip_is_and_how_long_it_runs(tmp_path):
    funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])

    funestra.tick(window=WINDOW)

    pill = PlayheadHudPainter().bgra(video_playhead(0.0, player.duration_ms, player.frame_rate))
    at = readout_xy(pill.shape[1], win_w=640, win_h=480, timeline_h=TIMELINE_HEIGHT)
    assert any((x, y) == at and np.array_equal(bgra, pill)
               for x, y, bgra in player.overlays.values())


def test_a_scripted_clips_scrubber_is_filled_with_its_scripts_colors(tmp_path):
    clip = _clips(tmp_path, "v0")[0]
    script = tmp_path / "v0.funscript"
    script.write_text('{"actions": [{"at": 0, "pos": 0}, {"at": 900, "pos": 100}, '
                      '{"at": 2400, "pos": 10}]}', encoding="utf-8")
    funestra, player = _funestra(tmp_path, [f"{clip}\t{script}"])

    funestra.tick(window=WINDOW)

    x0, x1 = bar_track_x(640)
    _x, _y, bar = player.overlays[Funestra.SCRUBBER_OVERLAY_ID]
    assert np.array_equal(bar, progress_bar_bgra(
        0.0, player.duration_ms, None, 640,
        heatmap=build_heatmap(load_funscript(script), x1 - x0,
                              start_ms=0, end_ms=player.duration_ms)))


def test_a_picture_on_screen_has_no_scrubber_under_it(tmp_path):
    funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])
    player.showing_picture = True

    funestra.tick(window=WINDOW)

    assert Funestra.SCRUBBER_OVERLAY_ID not in player.overlays
    assert len(player.overlays) == 2


def test_commands_drain_and_act_before_the_frame_is_published(tmp_path):
    clips = _clips(tmp_path, "v0", "v1")
    funestra, _player = _funestra(tmp_path, [str(clip) for clip in clips], commands="NEXT\nQUIT\n")

    funestra.tick(window=WINDOW)

    assert f"video={clips[1]}" in _status(tmp_path)


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
        assert (tmp_path / "dashboard_cmd.txt").read_text(encoding="utf-8").split() == [SESSION_QUIT]

    def test_with_no_session_to_ask_it_ends_this_player(self, tmp_path):
        funestra, _player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")],
                                      commands="")

        funestra.close_requested()

        assert funestra.stopped is True


class TestAPress:
    def test_on_the_scrubber_seeks_the_clip(self, tmp_path):
        funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])
        x0, x1 = bar_track_x(640)

        funestra.press((x0 + x1) // 2, 476, window=WINDOW)

        assert len(player.seeks) == 1
        assert abs(player.seeks[0] - player.duration_ms / 2) <= player.duration_ms / (x1 - x0)

    def test_on_the_volume_chip_unmutes_this_player(self, tmp_path):
        funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])
        vx, vy = chip_xy(win_w=640, win_h=480, timeline_h=TIMELINE_HEIGHT)

        funestra.press(vx + 7, vy + 11, window=WINDOW)

        assert player.muted is False
        assert player.seeks == []

    def test_on_the_chip_of_a_silent_build_sets_nothing(self, tmp_path):
        funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")],
                                     audible=False)
        vx, vy = chip_xy(win_w=640, win_h=480, timeline_h=TIMELINE_HEIGHT)

        funestra.press(vx + 7, vy + 11, window=WINDOW)

        assert player.muted is True

    def test_held_along_the_chip_keeps_setting_the_level(self, tmp_path):
        funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")])
        vx, vy = chip_xy(win_w=640, win_h=480, timeline_h=TIMELINE_HEIGHT)

        funestra.motion(vx + 66, vy + 11, held=True, window=WINDOW)

        assert player.volume == 50


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


def test_the_panel_its_source_publishes_is_drawn_over_the_picture(tmp_path):
    funestra, player = _funestra(tmp_path, [str(clip) for clip in _clips(tmp_path, "v0")], hud=True)
    (tmp_path / "portrait_hud.json").write_text(json.dumps({"player": "portrait"}), encoding="utf-8")

    funestra.tick(window=WINDOW)

    assert HUD_OVERLAY_ID in player.overlays
    assert len(player.overlays) == 4


def test_on_a_window_the_way_of_playing_is_mpv_opened_on_that_window(tmp_path):
    clips = _clips(tmp_path, "v0")
    channels = _channels(tmp_path, [str(clips[0])])
    player = FakePlayer()

    with patch("player_core.funestra.MpvPlayer", return_value=player) as mpv:
        funestra = Funestra.on_window(4242, channels=channels, playlist=read_playlist(channels.playlist))

    mpv.assert_called_once_with(4242, muted=True, loop_file=False, prefetch=True)
    assert funestra.playback.current_video == clips[0]
