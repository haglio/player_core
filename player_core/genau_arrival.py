"""A Genau launched beside the one that has the room, until it takes the room."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from app_support.file_channel import read_key_values

from .crossing import ArrivingPlayer
from .drive_readout import DriveHud, read_drive
from .genau_controls import (
    CLIP_SECONDS,
    CRUISE_OFF,
    CRUISE_ON,
    HAND_AMP,
    HAND_CENTER,
    HAND_SPEED,
    LEARNED_OFF,
    LEARNED_ON,
    PAUSE,
    RESUME,
    GenauControls,
    apply_runtime_command,
)
from .player_verbs import LOCK_OFF, LOCK_ON
from .robot_hand import WaveformShape, phase_for_position_fraction
from .tcode import POSITION_MAX

__all__: list[str] = []


def _flag(said: Mapping[str, str], key: str) -> bool | None:
    value = said.get(key)
    return None if value is None else value.strip() == "1"


def _active(state) -> bool | None:
    return None if state is None else state.active


class GenauArrival:
    def __init__(
        self,
        *,
        controls: GenauControls,
        selection,
        renderer,
        tcode_sender,
        drive_file: Path | None,
        status_file: Path,
    ) -> None:
        self._controls = controls
        self._selection = selection
        self._renderer = renderer
        self._sender = tcode_sender
        self._drive_file = drive_file
        self._status_file = status_file
        self._crossing = ArrivingPlayer.for_status_file(status_file)
        self._cannot_show = ""

    @property
    def told_to_take_the_room(self) -> bool:
        return self._crossing.take_the_room_now

    def follow(self) -> None:
        said = self._the_rooms_status()
        drive = self._the_rooms_drive()
        self._follow_the_clip(said.get("clip", "").strip())
        if drive is not None:
            self._follow_the_dials(drive)
        self._follow_the_switches(said)
        self._crossing.in_step(self._in_step(said, drive))

    def take_the_room(self, let_go: Callable[[], None]) -> None:
        drive = self._the_rooms_drive()
        if drive is not None and self._sender is not None and self._runs_the_plain_wave():
            hand = self._controls.robot_hand
            rising = len(drive.waveform) < 2 or drive.waveform[1] >= drive.waveform[0]
            self._sender.set_motion_phase(phase_for_position_fraction(
                drive.position / POSITION_MAX, shape=hand.shape,
                amplitude=hand.amplitude, center=hand.center, rising=rising))
        if self._sender is not None:
            self._sender.ease_in()
        let_go()
        self._crossing.took_the_room()

    def _the_rooms_status(self) -> dict[str, str]:
        try:
            return read_key_values(self._status_file)
        except (OSError, ValueError):
            return {}

    def _the_rooms_drive(self) -> DriveHud | None:
        return read_drive(self._drive_file) if self._drive_file is not None else None

    def _follow_the_clip(self, clip: str) -> None:
        if not clip or clip == self._cannot_show or clip.lower() == self._showing().lower():
            return
        if not self._selection.follow(Path(clip)):
            self._cannot_show = clip

    def _showing(self) -> str:
        showing = self._renderer.current_clip_path
        return "" if showing is None else str(showing)

    def _follow_the_dials(self, drive: DriveHud) -> None:
        hand = self._controls.robot_hand
        for verb, value, has in ((HAND_SPEED, drive.speed, hand.speed),
                                 (HAND_AMP, drive.amplitude, hand.amplitude),
                                 (HAND_CENTER, drive.center, hand.center)):
            if value != has:
                apply_runtime_command(f"{verb} {value}", self._controls)
        try:
            hand.shape = WaveformShape(drive.shape)
        except ValueError:
            pass

    def _follow_the_switches(self, said: Mapping[str, str]) -> None:
        controls = self._controls
        advance = controls.clip_advance_state
        for key, state, on, off in (
            ("playing", controls.robot_hand.playing, RESUME, PAUSE),
            ("cruise", _active(controls.cruise_control_state), CRUISE_ON, CRUISE_OFF),
            ("learned", _active(controls.learned_motion_state), LEARNED_ON, LEARNED_OFF),
            ("locked", None if advance is None else advance.locked, LOCK_ON, LOCK_OFF),
        ):
            wanted = _flag(said, key)
            if state is not None and wanted is not None and wanted != state:
                apply_runtime_command(on if wanted else off, controls)
        interval = said.get("interval", "").strip()
        if advance is not None and interval.isdigit() and int(interval) != advance.interval:
            apply_runtime_command(f"{CLIP_SECONDS} {interval}", controls)

    def _in_step(self, said: Mapping[str, str], drive: DriveHud | None) -> bool:
        clip = said.get("clip", "").strip()
        if clip and clip != self._cannot_show and clip.lower() != self._showing().lower():
            return False
        entry = self._renderer.current_clip_entry()
        if not (entry and entry.get("frames")):
            return False
        if drive is not None and self._sender is not None:
            return (drive.let_go is None) == (self._sender.let_go_position is None)
        return True

    def _runs_the_plain_wave(self) -> bool:
        controls = self._controls
        return not (_active(controls.cruise_control_state)
                    or _active(controls.learned_motion_state))
