"""A window of Fun Time: it plays what it is handed, draws the HUD, the scrubber and the
volume over it, answers their presses, and is driven through files by whatever runs on it."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from .drive_gate import DriveGate
from .file_channel import consume_command_file, read_paused_state
from .funestra_controls import FunestraControls, apply_command
from .funestra_status import status_fields
from .heatmap import ScriptColors
from .hud_overlay import HudOverlay
from .mpv_player import MpvPlayer
from .play_points import PlayPoints
from .playback import Playback, funscripts_of
from .playhead import PlayheadHudPainter, readout_xy, video_playhead
from .playlist import PlaylistItem, read_playlist
from .pointer import Pointer
from .session_quit import quit_gesture
from .status import StatusWriter
from .tcode import UdpTCodeSink
from .tcode_driver import FunscriptTCodeDriver
from .timeline import TIMELINE_HEIGHT, bar_track_x, progress_bar_bgra
from .volume import VolumeHudPainter, chip_xy
from .volume_control import VolumeControl

__all__ = [
    "Channels",
    "Funestra",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Channels:
    """The files a Funestra is driven through, and the inlet it drives the OSR2 from; each optional."""

    playlist: Path | None = None
    command: Path | None = None
    paused: Path | None = None
    status: Path | None = None
    play_points: Path | None = None
    hud: Path | None = None
    dashboard_cmd: Path | None = None
    drive: Path | None = None
    tcode_host: str | None = None
    tcode_port: int | None = None


def osr2_line(channels: Channels) -> FunscriptTCodeDriver | None:
    if not channels.tcode_host or not channels.tcode_port:
        return None
    return FunscriptTCodeDriver(UdpTCodeSink(channels.tcode_host, channels.tcode_port))


class Funestra:
    SCRUBBER_OVERLAY_ID = 11
    VOLUME_OVERLAY_ID = 12
    READOUT_OVERLAY_ID = 13

    def __init__(
        self,
        player,
        *,
        channels: Channels,
        playlist: list[PlaylistItem],
        tcode=None,
        audible: bool = True,
        tiles: bool = False,
    ) -> None:
        self._player = player
        self._channels = channels
        self._tiles = tiles
        self._stop = threading.Event()
        start_paused = (channels.paused is not None
                        and read_paused_state(channels.paused, logger=logger))
        self.playback = Playback(
            [item.path for item in playlist], player=player, start_paused=start_paused,
            play_points=PlayPoints(channels.play_points), funscripts=funscripts_of(playlist),
            tcode=tcode,
        )
        self._drive_gate = DriveGate(self.playback)
        self._hud = (
            HudOverlay(
                hud_file=channels.hud, command_file=channels.dashboard_cmd, player=player,
                drive_file=channels.drive, drive_gate=self._drive_gate,
            )
            if channels.hud and channels.dashboard_cmd
            else None
        )
        self._volume = VolumeControl(player, live=audible)
        self._pointer = Pointer(playback=self.playback, volume=self._volume, hud=self._hud,
                                dashboard_cmd_file=channels.dashboard_cmd)
        self._controls = FunestraControls(
            self.playback, stop_event=self._stop, reload_playlist=self._reload_playlist)
        self._status = (
            StatusWriter(channels.status, lambda playback: status_fields(
                playback, self._drive_gate.handoff_touch()))
            if channels.status else None
        )
        self._volume_painter = VolumeHudPainter()
        self._readout_painter = PlayheadHudPainter()
        self._scrubber_colors = ScriptColors()

    @classmethod
    def on_window(cls, wid: int, *, channels: Channels, playlist: list[PlaylistItem],
                  audible: bool = True, tiles: bool = False) -> Funestra:
        return cls(
            MpvPlayer(wid, muted=True, loop_file=False, prefetch=True),
            channels=channels, playlist=playlist, tcode=osr2_line(channels),
            audible=audible, tiles=tiles,
        )

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def close_requested(self) -> None:
        if quit_gesture(self._channels.dashboard_cmd):
            self._stop.set()

    def press(self, x: int, y: int, *, window: tuple[int, int]) -> None:
        self._pointer.press(x, y, win_w=window[0], win_h=window[1])

    def motion(self, x: int, y: int, *, held: bool, window: tuple[int, int]) -> None:
        self._pointer.motion(x, y, held=held, win_w=window[0], win_h=window[1])

    def tick(self, *, window: tuple[int, int]) -> None:
        channels = self._channels
        if channels.paused is not None:
            self.playback.set_paused(read_paused_state(channels.paused, logger=logger))
        if channels.command is not None:
            for command in consume_command_file(channels.command, logger=logger, uppercase=False):
                apply_command(command, self._controls)
        self.playback.advance()
        if self._tiles:
            self._player.tile_to_fill(*window)
        self._player.push_still()
        if self._status is not None:
            self._status.write(self.playback)
        if self._hud is not None:
            self._hud.tick(video=self.playback.name_on_screen,
                           playback_speed=self.playback.speed, window=window)
        self._paint_controls(window)

    def close(self) -> None:
        self.playback.close()

    def _reload_playlist(self) -> None:
        if self._channels.playlist is None:
            return
        items = read_playlist(self._channels.playlist)
        if items:
            self.playback.replace_playlist([item.path for item in items], funscripts_of(items))

    def _paint_controls(self, window: tuple[int, int]) -> None:
        win_w, win_h = window
        playback, player = self.playback, self._player
        if playback.showing_picture:
            player.remove_overlay(self.SCRUBBER_OVERLAY_ID)
        else:
            x0, x1 = bar_track_x(win_w)
            colors = self._scrubber_colors.across(
                playback.current_video, playback.current_funscript, playback.duration_ms, x1 - x0)
            bar = progress_bar_bgra(playback.position_ms, playback.duration_ms, None, win_w,
                                    heatmap=colors)
            player.overlay(self.SCRUBBER_OVERLAY_ID, 0, win_h - bar.shape[0], bar)
        vx, vy = chip_xy(win_w=win_w, win_h=win_h, timeline_h=TIMELINE_HEIGHT)
        player.overlay(self.VOLUME_OVERLAY_ID, vx, vy, self._volume_painter.bgra(self._volume.hud))
        readout = video_playhead(playback.position_ms, playback.duration_ms, player.frame_rate)
        if readout is None:
            player.remove_overlay(self.READOUT_OVERLAY_ID)
        else:
            pill = self._readout_painter.bgra(readout)
            player.overlay(self.READOUT_OVERLAY_ID, *readout_xy(
                pill.shape[1], win_w=win_w, win_h=win_h, timeline_h=TIMELINE_HEIGHT), pill)
