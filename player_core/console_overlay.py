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
    ) -> None:
        self._console_file = Path(console_file)
        self._drive_file = None if drive_file is None else Path(drive_file)
        self._command_file = command_file
        self._player = player
        self._drive_gate = drive_gate
        self._top_block = top_block
        self.overlay_id = overlay_id
        self._painter = ConsolePainter()
        self._console = ConsoleModel()
        self._drive: DriveHud | None = None
        self._hover: tuple[int, int] | None = None
        self._shown = False

    @property
    def console(self) -> ConsoleModel:
        return self._console

    def tick(self, *, playback_speed: float, window: tuple[int, int], lower_edge: int) -> None:
        self._console = read_console(self._console_file) or self._console
        if self._drive_file is not None:
            self._drive = read_drive(self._drive_file) or self._drive
        drive = self._drive_gate.readout(
            self._drive, device_drives_itself=self._console.device_drives_itself)
        bgra = self._painter.bgra(ConsoleHud(
            modes=self._top_block(),
            console=with_playback_speed(self._console, playback_speed),
            drive=drive,
        ), hover=self._hover)
        left, top = self._painter.place(window=window, lower_edge=lower_edge)
        self._player.overlay(self.overlay_id, left, top, bgra)
        self._shown = True

    def press(self, x: int, y: int) -> bool:
        asked = self._painter.press_at(x, y)
        if asked:
            ask(self._command_file, asked)
            return True
        return self._painter.covers(x, y)

    @property
    def holding(self) -> bool:
        return self._painter.holding

    def drag_to(self, x: int, y: int) -> str:
        dragged = self._painter.drag_to(x, y)
        if dragged:
            ask(self._command_file, dragged)
        return dragged

    def release(self) -> None:
        self._painter.release()

    def motion(self, x: int, y: int) -> None:
        self._hover = self._painter.hover_at(x, y)

    def close(self) -> None:
        if self._shown:
            self._player.remove_overlay(self.overlay_id)
            self._shown = False
