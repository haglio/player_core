"""The published panel kept on the picture: polled, rendered when it changes, composited, pressed."""
from __future__ import annotations

import logging
import time
from dataclasses import replace
from pathlib import Path

from .drive_readout import DriveHud, read_drive
from .file_channel import append_command
from .hud_placement import HudCorner, HudEdge, hud_origin
from .modes import Osr2State
from .playhead import lower_edge_height
from .satellite_hud import (
    MARGIN,
    HudClicks,
    HudModel,
    HudTargets,
    button_tooltip,
    hit_test_targets,
    parse_hud,
)
from .satellite_hud_paint import HudRenderer
from .timeline import TIMELINE_HEIGHT

__all__: list[str] = []

logger = logging.getLogger(__name__)

HUD_OVERLAY_ID = 10

_EMPTY_TARGETS = HudTargets(click=[], loop=[], filter=[], expand=None)


class HudOverlay:
    def __init__(
        self,
        *,
        hud_file: Path,
        command_file: Path,
        player,
        overlay_id: int = HUD_OVERLAY_ID,
        clock=time.monotonic,
        drive_file: Path | None = None,
        drive_gate=None,
        over_the_video: bool = True,
    ) -> None:
        self._hud_file = Path(hud_file)
        self._drive_file = None if drive_file is None else Path(drive_file)
        self._drive_gate = drive_gate
        self._published_drive: DriveHud | None = None
        self._drive: DriveHud | None = None
        self._command_file = Path(command_file)
        self._player = player
        self.overlay_id = overlay_id
        self._clock = clock
        self._over_the_video = over_the_video
        self._renderer: HudRenderer | None = None
        self._clicks: HudClicks | None = None
        self._published = ""
        self._model: HudModel | None = None
        self._video = ""
        self._playback_speed: float | None = None
        self._hover_loop = ""
        self._hover_tip = ""
        self._hover_pos = (0, 0)
        self._shown = False
        self._window: tuple[int, int] | None = None
        self._origin = (MARGIN, MARGIN)
        self._panel_size: tuple[int, int] | None = None
        self.targets: HudTargets = _EMPTY_TARGETS

    @property
    def edge(self) -> HudEdge:
        return self._model.hud_edge if self._model is not None else HudEdge.LOWER

    @property
    def active_loop(self) -> str:
        return self._clicks.active_loop if self._clicks is not None else ""

    def tick(self, video: str = "", playback_speed: float | None = None,
             window: tuple[int, int] | None = None) -> None:
        text = self._read()
        redraw = (video != self._video or playback_speed != self._playback_speed
                  or window != self._window)
        self._video = video
        self._playback_speed = playback_speed
        self._window = window
        if text is not None and text != self._published:
            self._published = text
            model = parse_hud(text) if text else None
            if model is not None:
                if self._renderer is None:
                    self._renderer = HudRenderer(model.player)
                    self._clicks = HudClicks(model.player)
                self._clicks.active_loop = model.active_loop
                self._clicks.active_filter = model.filter_query
            self._model = model
            redraw = True
        drive = self._motion()
        if drive != self._drive:
            self._drive = drive
            redraw = True
        if redraw:
            self._draw()
        if self._clicks is not None:
            command = self._clicks.due(now=self._clock())
            if command:
                self._post(command)

    def press(self, x: int, y: int) -> bool:
        if self._clicks is None or not self._covers(x, y):
            return False
        command = self._clicks.press(self.targets, *self._local(x, y), now=self._clock())
        if command:
            self._post(command)
            self._draw()
        return True

    @property
    def holding(self) -> bool:
        return self._clicks is not None and self._clicks.holding

    def drag_to(self, x: int, y: int) -> str:
        command = self._clicks.drag_to(*self._local(x, y)) if self._clicks is not None else ""
        if command:
            self._post(command)
        return command

    def release(self) -> None:
        if self._clicks is not None:
            self._clicks.release()

    def motion(self, x: int, y: int) -> None:
        px, py = self._local(x, y)
        hover = hit_test_targets(self.targets.loop, px, py)
        tip = button_tooltip(self.targets, px, py)
        if hover == self._hover_loop and tip == self._hover_tip:
            return
        self._hover_loop, self._hover_tip, self._hover_pos = hover, tip, (px, py)
        self._draw()

    def close(self) -> None:
        self._panel_size = None
        if self._shown:
            self._player.remove_overlay(self.overlay_id)
            self._shown = False

    def _covers(self, x: int, y: int) -> bool:
        if self._panel_size is None:
            return False
        left, top = self._origin
        width, height = self._panel_size
        return left <= x < left + width and top <= y < top + height

    def _local(self, x: int, y: int) -> tuple[int, int]:
        left, top = self._origin
        return x - left, y - top

    def _place(self, corner: HudCorner, size: tuple[int, int]) -> tuple[int, int]:
        if self._window is None:
            return MARGIN, MARGIN
        width, _height = self._window
        return hud_origin(corner, panel=size, window=self._window, margin=MARGIN,
                          lower_edge=lower_edge_height(width, timeline_h=TIMELINE_HEIGHT))

    def _read(self) -> str | None:
        """The published panel's text, "" when there is none to show, or None
        for a frame that lost the race with the source replacing the file."""
        try:
            return self._hud_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""
        except OSError:
            return None

    def _motion(self) -> DriveHud | None:
        if self._drive_file is None or self._model is None or not self._model.osr2:
            return None
        self._published_drive = read_drive(self._drive_file) or self._published_drive
        if self._drive_gate is None:
            return self._published_drive
        return self._drive_gate.readout(
            self._published_drive, device_drives_itself=self._model.osr2 == Osr2State.AUTO)

    def _draw(self) -> None:
        if self._model is None or self._renderer is None:
            self.targets = _EMPTY_TARGETS
            self.close()
            return
        corner = self._model.hud_corner if self._over_the_video else HudCorner.UPPER_LEFT
        rendered = self._renderer.render(
            replace(self._model, playback_speed=self._playback_speed, drive=self._drive,
                    drive_composed=self._drive_gate is not None, hud_corner=corner),
            video=self._video, hover_loop=self._hover_loop,
            hover_tip=self._hover_tip, hover_pos=self._hover_pos,
            may_grow_on_hover=self._over_the_video,
        )
        self.targets = rendered.targets
        height, width = rendered.bgra.shape[:2]
        self._panel_size = (width, height)
        self._origin = self._place(corner, self._panel_size)
        self._player.overlay(self.overlay_id, *self._origin, rendered.bgra)
        self._shown = True

    def _post(self, command: str) -> None:
        if not append_command(self._command_file, command):
            logger.warning("Dropped HUD command (command file locked): %s", command)
