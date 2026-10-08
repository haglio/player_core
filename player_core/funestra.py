"""A window of Fun Time: it plays what it is handed, draws the HUD, the scrubber and the
volume over it, answers their presses, and is driven through files by whatever runs on it."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .console import ModeHud
from .console_overlay import ConsoleOverlay
from .control_registry import look_up
from .display import Display
from .drive_gate import DriveGate
from .file_channel import consume_command_file, read_paused_state
from .funestra_controls import VERBS, FunestraControls
from .funestra_status import status_fields
from .hud_overlay import HUD_OVERLAY_ID, HudOverlay
from .hud_row import RowHud
from .mpv_player import MpvPlayer
from .play_points import PlayPoints
from .playback import Playback, funscripts_of
from .playhead import video_playhead
from .playlist import PlaylistItem
from .playlist_follower import PlaylistFollower
from .pointer import Pointer
from .scrubber import HeatmapStrip, LoopThumbCapture, loop_thumbnail_xys
from .session_quit import quit_gesture
from .status import StatusWriter
from .tcode import UdpTCodeSink
from .tcode_driver import FunscriptTCodeDriver
from .volume_control import RoomVolume, VolumeControl

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
    console: Path | None = None
    dashboard_cmd: Path | None = None
    drive: Path | None = None
    tcode_host: str | None = None
    tcode_port: int | None = None


class User(Protocol):
    """What runs on a Funestra, as the Funestra sees it."""

    def apply_command(self, command: str) -> bool: ...

    def tick(self) -> None: ...

    def status_fields(self) -> Mapping[str, str]: ...

    def top_block(self) -> ModeHud: ...


class _Nobody:
    """A Funestra driven through its files alone."""

    def apply_command(self, command: str) -> bool:
        return False

    def tick(self) -> None:
        pass

    def status_fields(self) -> Mapping[str, str]:
        return {}

    def top_block(self) -> ModeHud:
        return ModeHud()


def osr2_line(channels: Channels) -> FunscriptTCodeDriver | None:
    if not channels.tcode_host or not channels.tcode_port:
        return None
    return FunscriptTCodeDriver(UdpTCodeSink(channels.tcode_host, channels.tcode_port))


class Funestra:
    IN_FRAME_OVERLAY_ID = 8
    OUT_FRAME_OVERLAY_ID = 9
    PANEL_OVERLAY_ID = HUD_OVERLAY_ID
    OVERLAY_IDS = (IN_FRAME_OVERLAY_ID, OUT_FRAME_OVERLAY_ID, PANEL_OVERLAY_ID)

    def __init__(
        self,
        player,
        *,
        channels: Channels,
        playlist: list[PlaylistItem],
        tcode=None,
        audible: bool = True,
        tiles: bool = False,
        locked: bool = False,
        sound_is_the_rooms: bool = False,
        user: Callable[[Playback], User] | None = None,
    ) -> None:
        self._player = player
        self._channels = channels
        self._tiles = tiles
        self._stop = threading.Event()
        start_paused = (channels.paused is not None
                        and read_paused_state(channels.paused, logger=logger))
        self.playback = Playback(
            [item.path for item in playlist], player=player, start_paused=start_paused,
            locked=locked, play_points=PlayPoints(channels.play_points),
            funscripts=funscripts_of(playlist), tcode=tcode,
        )
        self._follower = (None if channels.playlist is None
                          else PlaylistFollower(channels.playlist, take=self._take_the_list))
        self._user: User = _Nobody() if user is None else user(self.playback)
        self._drive_gate = DriveGate(self.playback)
        self._strip = HeatmapStrip()
        self._volume = (
            RoomVolume(player, dashboard_cmd_file=channels.dashboard_cmd, live=audible)
            if sound_is_the_rooms else VolumeControl(player, live=audible)
        )
        self._panel = self._panel_for(channels, player)
        self._display = Display(player, self.OVERLAY_IDS)
        self._pointer = Pointer(hud=self._panel, dashboard_cmd_file=channels.dashboard_cmd)
        self._controls = FunestraControls(
            self.playback, stop_event=self._stop,
            reload_playlist=None if self._follower is None else self._follower.read_now,
            room_volume=self._volume if sound_is_the_rooms else None, display=self._display)
        self._status = (
            StatusWriter(channels.status, lambda playback: {
                **status_fields(playback, self._drive_gate.handoff_touch()),
                **self._user.status_fields()})
            if channels.status else None
        )
        self._loop_frames = LoopThumbCapture()

    def _panel_for(self, channels: Channels, player) -> HudOverlay | ConsoleOverlay | None:
        """The one panel this window wears, which carries the clip's row: the
        room's console on the main slot, else the published HUD.  Both place a
        press on the row themselves, so each is handed what it asks of the
        window when one lands.
        """
        if channels.dashboard_cmd is None:
            return None
        if channels.console is not None:
            return ConsoleOverlay(
                console_file=channels.console, drive_file=channels.drive,
                command_file=channels.dashboard_cmd, player=player,
                drive_gate=self._drive_gate, top_block=self._user.top_block,
                seek=self._seek_along_the_track, set_volume=self._volume.set_level,
                toggle_mute=self._volume.toggle_mute,
            )
        if channels.hud is not None:
            return HudOverlay(
                hud_file=channels.hud, command_file=channels.dashboard_cmd, player=player,
                drive_file=channels.drive, drive_gate=self._drive_gate,
                seek=self._seek_along_the_track, set_volume=self._volume.set_level,
                toggle_mute=self._volume.toggle_mute,
            )
        return None

    def _seek_along_the_track(self, ms: float) -> None:
        """A press on the track names a time in the stretch the track spans,
        which is the whole clip until a loop being recorded zooms it in."""
        start_ms, _end_ms = self._strip.window
        self.playback.seek_to(start_ms + ms)

    @classmethod
    def on_window(cls, wid: int, *, channels: Channels, playlist: list[PlaylistItem],
                  audible: bool = True, tiles: bool = False, locked: bool = False,
                  sound_is_the_rooms: bool = False,
                  user: Callable[[Playback], User] | None = None) -> Funestra:
        return cls(
            MpvPlayer(wid, muted=True, loop_file=False, prefetch=True),
            channels=channels, playlist=playlist, tcode=osr2_line(channels),
            audible=audible, tiles=tiles, locked=locked, sound_is_the_rooms=sound_is_the_rooms,
            user=user,
        )

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def close_requested(self) -> None:
        if quit_gesture(self._channels.dashboard_cmd):
            self._stop.set()

    def press(self, x: int, y: int, *, window: tuple[int, int]) -> None:
        self._pointer.press(x, y, win_w=window[0], win_h=window[1])

    def release(self) -> None:
        self._pointer.release()

    def motion(self, x: int, y: int, *, held: bool, window: tuple[int, int]) -> None:
        self._pointer.motion(x, y, held=held, win_w=window[0], win_h=window[1])

    def tick(self, *, window: tuple[int, int]) -> None:
        channels = self._channels
        if channels.paused is not None:
            self.playback.set_paused(read_paused_state(channels.paused, logger=logger))
        if channels.command is not None:
            for command in consume_command_file(channels.command, logger=logger, uppercase=False):
                self._apply(command)
        if self._follower is not None:
            self._follower.tick()
        self._user.tick()
        self.playback.advance()
        if self._status is not None:
            self._status.write(self.playback)
        self._display.sync(*window)
        if not self._display.active:
            return
        if self._tiles:
            self._player.tile_to_fill(*window)
        self._player.push_still()
        self._paint(window)

    def close(self) -> None:
        self.playback.close()

    def _apply(self, command: str) -> None:
        if self._user.apply_command(command):
            return
        if not look_up(command, VERBS, self._controls):
            logger.warning("Unhandled command: %s", command.strip())

    def _take_the_list(self, items: list[PlaylistItem]) -> None:
        self.playback.replace_playlist([item.path for item in items], funscripts_of(items))

    def _paint(self, window: tuple[int, int]) -> None:
        self._paint_panel(window, self.clip_row())
        self._paint_loop_frames(window)

    def clip_row(self) -> RowHud | None:
        """Where the clip has got to, how long it runs, how loud it is and where
        its loop ends -- the row the panel carries at its foot, or None on a
        picture, which has nothing to run through.  Timed against the stretch
        the track spans, which is the whole clip until a loop being recorded
        zooms it in.
        """
        playback, player = self.playback, self._player
        self._strip.update(playback.showing, playback.current_funscript,
                           playback.duration_ms, self._track_width(),
                           mark_in_ms=playback.mark, position_ms=playback.position_ms)
        if playback.showing_picture:
            return None
        start_ms, end_ms = self._strip.window
        bounds = playback.ab_loop
        return RowHud(
            position_ms=playback.position_ms - start_ms,
            duration_ms=end_ms - start_ms,
            volume=self._volume.hud,
            playhead=video_playhead(playback.position_ms, playback.duration_ms,
                                    player.frame_rate),
            loop_bounds=None if bounds is None else (bounds[0] - start_ms,
                                                     bounds[1] - start_ms),
            record_in_ms=None if playback.mark is None else playback.mark - start_ms,
        )

    def _track_width(self) -> int:
        """How wide the panel drew the track last frame, which is what the
        colors have to cover.  A panel is as wide as what is on it, so there is
        no answer until one has been drawn: 0 leaves the first row plain.
        """
        rect = None if self._panel is None else self._panel.row_rect
        return 0 if rect is None else rect[2]

    def _paint_panel(self, window: tuple[int, int], row: RowHud | None) -> None:
        if self._panel is None:
            return
        colors = self._strip.colors if row is not None else None
        if isinstance(self._panel, ConsoleOverlay):
            self._panel.tick(playback_speed=self.playback.speed, window=window,
                             clip_row=row, heatmap=colors)
        else:
            self._panel.tick(video=self.playback.name_on_screen,
                             playback_speed=self.playback.speed, window=window,
                             clip_row=row, heatmap=colors)

    def _paint_loop_frames(self, window: tuple[int, int]) -> None:
        """The loop's in and out frames, each hanging under the panel below its
        own mark on the track."""
        playback, player, frames = self.playback, self._player, self._loop_frames
        which = frames.needed(playback.ab_loop, playback.position_ms)
        if which is not None:
            frames.set(which, player.screenshot_bgra())
        track = None if self._panel is None else self._panel.row_track
        if playback.ab_loop is None or track is None:
            player.remove_overlay(self.IN_FRAME_OVERLAY_ID)
            player.remove_overlay(self.OUT_FRAME_OVERLAY_ID)
            return
        x0, x1, top = track
        in_at, out_at = loop_thumbnail_xys(
            self._strip, frames, playback.ab_loop,
            track=(x0, x1), win_w=window[0], top=top)
        if in_at is not None:
            player.overlay(self.IN_FRAME_OVERLAY_ID, *in_at, frames.in_thumb)
        if out_at is not None:
            player.overlay(self.OUT_FRAME_OVERLAY_ID, *out_at, frames.out_thumb)
