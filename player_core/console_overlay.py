"""The console kept on the picture: the panel the room publishes for the main slot,
read every frame, composited, pressed.

The room's two files -- the console, and the motion whoever drives the OSR2
publishes -- are replaced while this polls them, so a torn read keeps what was
there: blanking either for a frame is a visible flicker on a panel redrawn at
60fps.  The motion is read through the gate before the panel believes it, or
the pill and the drawn line describe the frame before this one.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .console import ConsoleModel, ModeHud, read_console
from .console_hud import ConsoleHud, ConsolePainter, with_playback_speed
from .dashboard import ask
from .drive_readout import DriveHud, read_drive
from .hud_overlay import HUD_OVERLAY_ID
from .hud_placement import HudEdge, PointerReading
from .hud_row import RowHud, RowPress, track_on_screen

__all__ = []


class ConsoleOverlay:
    def __init__(
        self,
        *,
        console_file: Path,
        drive_file: Path | None,
        command_file: Path | None,
        player,
        drive_gate,
        top_block: Callable[[], ModeHud],
        overlay_id: int = HUD_OVERLAY_ID,
        width: int | None = None,
        seek=None,
        set_volume=None,
        toggle_mute=None,
    ) -> None:
        self._console_file = Path(console_file)
        self._drive_file = None if drive_file is None else Path(drive_file)
        self._command_file = command_file
        self._player = player
        self._drive_gate = drive_gate
        self._top_block = top_block
        self.overlay_id = overlay_id
        self._painter = ConsolePainter(width=width)
        self._console = ConsoleModel()
        self._drive: DriveHud | None = None
        self._hover: PointerReading[tuple[int, int] | None] = PointerReading(None)
        self._shown = False
        self._origin = (0, 0)
        self._panel_height = 0
        self._clip_row: RowHud | None = None
        # The console draws the clip's row, so it places a press on it too.
        self._row = RowPress(seek=seek, set_volume=set_volume, toggle_mute=toggle_mute)

    @property
    def console(self) -> ConsoleModel:
        return self._console

    @property
    def edge(self) -> HudEdge:
        return self._console.hud_edge

    def tick(self, *, playback_speed: float, window: tuple[int, int],
             clip_row: RowHud | None = None, heatmap=None) -> None:
        self._console = read_console(self._console_file) or self._console
        if self._drive_file is not None:
            self._drive = read_drive(self._drive_file) or self._drive
        drive = self._drive_gate.readout(
            self._drive, device_drives_itself=self._console.device_drives_itself)
        self._clip_row = clip_row
        bgra = self._painter.bgra(ConsoleHud(
            modes=self._top_block(),
            console=with_playback_speed(self._console, playback_speed),
            drive=drive,
        ), hover=self._hover.on(self._console), clip_row=clip_row, heatmap=heatmap)
        self._origin = self._painter.place(window=window)
        self._panel_height = bgra.shape[0]
        self._player.overlay(self.overlay_id, *self._origin, bgra)
        self._shown = True

    @property
    def row_rect(self) -> tuple[int, int, int, int] | None:
        """Where the clip's row landed in this panel, for a host measuring the
        track it is to fill."""
        return self._painter.row_rect

    @property
    def row_track(self) -> tuple[int, int, int] | None:
        """The row's track in the window's coordinates, for a host hanging the
        loop's frames under it."""
        return track_on_screen(self._painter.row_rect, origin=self._origin,
                               panel_height=self._panel_height)

    def press(self, x: int, y: int) -> bool:
        if self._row.press(*self._local(x, y), rect=self._painter.row_rect,
                           duration_ms=self._track_duration()):
            return True
        asked = self._painter.press_at(x, y)
        if asked:
            ask(self._command_file, asked)
            return True
        return self._painter.covers(x, y)

    @property
    def holding(self) -> bool:
        return self._row.holding or self._painter.holding

    def drag_to(self, x: int, y: int) -> str:
        if self._row.drag_to(*self._local(x, y), rect=self._painter.row_rect,
                             duration_ms=self._track_duration()):
            return ""
        dragged = self._painter.drag_to(x, y)
        if dragged:
            ask(self._command_file, dragged)
        return dragged

    def release(self) -> None:
        self._row.release()
        self._painter.release()

    def _local(self, x: int, y: int) -> tuple[int, int]:
        return x - self._origin[0], y - self._origin[1]

    def _track_duration(self) -> float:
        """How long the track spans -- the clip, or the window a loop being
        recorded has zoomed it to, which is what the row was drawn from."""
        return 0.0 if self._clip_row is None else self._clip_row.duration_ms

    def motion(self, x: int, y: int) -> None:
        self._hover.take(self._painter.hover_at(x, y))

    def close(self) -> None:
        if self._shown:
            self._player.remove_overlay(self.overlay_id)
            self._shown = False
