"""One turn of Genau's loop: the clip player's tick.

Everything Genau does each frame, in the order the order matters, against the
collaborators a shell hands it.  The shell -- a pygame window, a headset -- owns
the surface the frame is blitted to and the loop that calls :meth:`refresh`;
what happens inside a turn is the same wherever Genau is drawn.
"""
from __future__ import annotations

import time
from pathlib import Path

from .broker_feed import snapshot
from .broker_park import BrokerPark
from .clip_advance import tick_clip_advance
from .clip_renderer import display_index_for_phase
from .clip_scrub import ClipScrub, scrub_clip
from .cruise_control import tick_cruise_control
from .file_channel import consume_command_file
from .genau_controls import GenauControls, apply_runtime_command
from .genau_readout import AutoMotion, GenauReadout
from .genau_status import GENAU_STATUS_FILENAME, write_status_file
from .learned_motion import tick_learned_motion
from .robot_hand import POSITION_MAX, phase_for_position_fraction
from .robot_hand_beat import Beat, advance_beat
from .robot_hand_driver import DeviceHandoff
from .tick_failures import TickFailures

__all__ = [
    "GenauRefreshController",
]

class GenauRefreshController:
    def __init__(
        self,
        *,
        controls: GenauControls,
        broker,
        loader,
        notifier,
        renderer,
        selection,
        command_file: Path,
        paused_file: Path,
        beats_per_loop: float,
        bpm_smoothing: float,
        sync_strength: float,
        set_loading_text,
        logger,
        now_source=time.monotonic,
        consume_command=consume_command_file,
        read_paused_state=None,
        tcode_sender=None,
        status_file: Path | None = None,
        drive_file: Path | None = None,
        console_file: Path | None = None,
        set_console=None,
        present_scene=None,
        set_hud_mode=None,
    ):
        self.controls = controls
        # The seven the tick itself reads, named here rather than reached for
        # through the controls on every line below.
        self.engine = controls.engine
        self.paused = controls.paused
        self.robot_hand = controls.robot_hand
        self.cruise_control = controls.cruise_control_state
        self.learned = controls.learned_motion_state
        self.clip_advance = controls.clip_advance_state
        self.hud = controls.hud
        self.tcode_enabled = controls.tcode_enabled
        self.flip = controls.clip_flip
        self.parked = controls.parked
        self.broker = broker
        self.loader = loader
        self.notifier = notifier
        self.renderer = renderer
        self.selection = selection
        self.command_file = command_file
        self.paused_file = paused_file
        self.beats_per_loop = beats_per_loop
        self.bpm_smoothing = bpm_smoothing
        self.sync_strength = sync_strength
        self.set_loading_text = set_loading_text
        self.logger = logger
        self.failures = TickFailures(logger)
        self.now_source = now_source
        self.consume_command = consume_command
        self.read_paused_state = read_paused_state or (lambda _path, logger=None: False)
        self.tcode_sender = tcode_sender
        # Beside the command file when the orchestrator has not named one --
        # which is where every version of it so far has looked.
        self.status_file = status_file or command_file.parent / GENAU_STATUS_FILENAME
        self.handoff = DeviceHandoff(
            playing=self.robot_hand.playing,
            tcode_sender=tcode_sender,
        )
        self.readout = GenauReadout(
            controls=controls,
            beats_per_loop=beats_per_loop,
            tcode_sender=tcode_sender,
            drive_file=drive_file,
            console_file=console_file,
            set_console=set_console,
            current_clip=lambda: renderer.current_clip_path,
        )
        self.present_scene = present_scene or (lambda: None)
        self.set_hud_mode = set_hud_mode or (lambda _active: None)
        # Which half of the clip is showing, and what is known about the end
        # the motion is at — see :meth:`_scrub_the_clip`.
        self._scrub = ClipScrub()
        self._broker_park: BrokerPark | None = None

    def refresh(self) -> None:
        try:
            self._refresh_once()
        except Exception as exc:
            # Said once per kind rather than every frame: the loop calls this
            # again immediately, so a persistent fault would otherwise fill the
            # state directory the IPC files live in.
            self.failures.failed(exc)
            return
        self.failures.worked()

    def _refresh_once(self) -> None:
        now = self.now_source()
        self._adopt_whatever_finished_decoding()
        self.flip.follow(self.renderer.current_clip_path)
        self._drain_commands()

        beat = self._who_is_driving(now)

        # Said every tick and heard once: the notifier drops a repeat.  The
        # clip that goes with it is the clip selection's to announce, and it
        # already has by the time the first tick runs.
        self.notifier.notify_visible(not self._over_a_video)

        advance_beat(
            self.engine,
            now=now,
            auto_active=beat.auto_active,
            raw_bpm=beat.raw_bpm,
            sync_pulse_id=beat.sync_pulse_id,
            beats_per_loop=self.beats_per_loop,
            bpm_smoothing=self.bpm_smoothing,
            sync_strength=self.sync_strength,
            paused=beat.paused,
        )

        # Seen the same tick the command landed, because the drain above runs
        # first.
        self.handoff.watch(self.robot_hand.playing)

        if self.tcode_sender is not None and beat.robot_hand_active and self.robot_hand.playing:
            self.tcode_sender.maybe_send(
                self.engine.phase, now, output=self.tcode_enabled.on)

        if beat.robot_hand_active:
            self.readout.update(now)
        else:
            # The device is running itself.  The panel stays up and the line
            # goes on moving -- on the broker's beat, the same one the frames
            # below are scrubbed by.
            self.readout.update(now, AutoMotion(
                phase=self.engine.phase, bpm=self.engine.estimated_bpm or 0.0))

        self._follow_the_window_flags()
        self._follow_the_room_park(now)
        self._show_the_frame(beat, now)

        pending = self.selection.pending_clip_name
        self.set_loading_text(f"Loading {pending}" if pending else None)

        self.selection.request_nearby_prefetch()
        self.present_scene()
        self._publish_status()

    def _adopt_whatever_finished_decoding(self) -> None:
        self.loader.adopt_loaded_clip_if_ready()
        self.loader.adopt_prefetch_if_ready()
        self.selection.adopt_pending_clip()

    def _drain_commands(self) -> None:
        for cmd in self.consume_command(self.command_file, logger=self.logger):
            apply_runtime_command(cmd, self.controls)

    def _who_is_driving(self, now: float) -> Beat:
        """Genau's own hand, or the broker — and what the engine is told either way."""
        shared = snapshot(self.broker)
        if shared.auto_active:
            self.paused.on = self.read_paused_state(
                self.paused_file, logger=self.logger)
            return Beat(
                robot_hand_active=False,
                auto_active=shared.auto_active,
                raw_bpm=shared.raw_bpm,
                paused=self.paused.on,
                sync_pulse_id=shared.sync_pulse_id,
            )
        self._tick_the_hand(now)
        return Beat(
            robot_hand_active=True,
            auto_active=self.robot_hand.playing,
            raw_bpm=self.robot_hand.bpm,
            paused=not self.robot_hand.playing,
            sync_pulse_id=0,
        )

    def _tick_the_hand(self, now: float) -> None:
        """The three things that move the hand on their own: the cruise stack
        varying it, the learned motion replacing it, and the clip advance
        letting the picture move on."""
        if self.cruise_control is not None:
            # The phase is only read on the tick that draws the waves: they
            # all start where the motion already is, so taking over cannot
            # be felt.
            tick_cruise_control(
                self.robot_hand, self.cruise_control, now,
                phase=(self.tcode_sender.motion_phase
                       if self.tcode_sender is not None else 0.0),
            )
        if self.learned is not None:
            # Likewise where the device is, read on the tick that lays out the
            # first phrase, so it begins from there.
            tick_learned_motion(
                self.robot_hand, self.learned, now,
                start_fraction=self._where_the_device_is(),
            )
        if self.clip_advance is not None:
            # The interval is timed against the clip actually on screen — a
            # decoded, rendering one — so a slow load can't make a short
            # interval fire repeatedly and stack switches that never play.
            entry = self.renderer.current_clip_entry()
            on_screen_clip = (
                self.renderer.current_clip_path if entry and entry.get("frames") else None
            )
            tick_clip_advance(
                self.clip_advance,
                now,
                playing=self.robot_hand.playing,
                on_screen_clip=on_screen_clip,
                step_clip=self.selection.step,
            )

    def _where_the_device_is(self) -> float:
        """How far up its envelope the device is, 0 at the floor and 1 at the
        ceiling -- where the learned motion begins so that taking over cannot be
        felt.  A build with no sender, or a motion with no travel, begins at the
        floor."""
        hand = self.robot_hand
        if self.tcode_sender is None or hand.amplitude <= 0:
            return 0.0
        low = max(0.0, hand.center - hand.amplitude / 2)
        span = min(100.0, hand.center + hand.amplitude / 2) - low
        height = 100.0 * self.tcode_sender.current_position() / POSITION_MAX
        return (height - low) / span if span > 0 else 0.0

    def _follow_the_window_flags(self) -> None:
        """The one thing an orchestrator flips that the window has to be told."""
        if self.hud is not None and self.hud.moved():
            self.set_hud_mode(self.hud.on)

    def _follow_the_room_park(self, now: float) -> None:
        if self.robot_hand.playing:
            self.parked.on = False
            self._broker_park = None
        elif self.parked.on and self._broker_park is None:
            self._broker_park = BrokerPark(self._scrub.height, now)

    def _show_the_frame(self, beat: Beat, now: float) -> None:
        """Which frame of the decoded clip to put up.

        Driving its own hand, the frame is the picture of where the device is;
        under the broker it is where the engine's phase has reached.
        """
        active_entry = self.renderer.current_clip_entry()
        if not (active_entry and active_entry["frames"]):
            return
        if beat.robot_hand_active and self._the_picture_holds_still:
            return
        frame_count = len(active_entry["frames"])
        display_phase = self.flip.applied_to(
            self._scrub_the_clip(frame_count, now) if beat.robot_hand_active
            else self.engine.phase
        )
        self.renderer.show_frame_at(display_index_for_phase(display_phase, frame_count))

    @property
    def _the_picture_holds_still(self) -> bool:
        return (not self.robot_hand.playing and self._broker_park is None
                and self.renderer.current_frame_index is not None)

    @property
    def _over_a_video(self) -> bool:
        return self.hud is not None and self.hud.on

    def _publish_status(self) -> None:
        if self.cruise_control is None:
            return
        write_status_file(
            self.status_file,
            self.robot_hand,
            self.cruise_control,
            learned=self.learned,
            clip_advance=self.clip_advance,
            hud_active=self._over_a_video,
            clip=self.renderer.current_clip_path,
            flipped=self.flip.on,
        )

    def seek_the_clip(self, fraction: float) -> None:
        """Put the clip *fraction* of the way along its bar, and the device where
        that is.

        The frame is a picture of where the device is (:mod:`player_core.clip_scrub`),
        so seeking the picture is moving the device rather than moving the picture
        away from it.  Which half of the loop the fraction falls in says which way
        the motion is travelling -- the front half runs A to B, the back half back
        -- and how far into that half says how far up the axis it has to be.  The
        jump is the point: it is what the hand would have had to travel to get the
        picture there.
        """
        entry = self.renderer.current_clip_entry()
        if self.tcode_sender is None or not (entry and entry["frames"]):
            return
        fraction = self.flip.applied_to(min(1.0, max(0.0, fraction)))
        back_half = fraction > 0.5
        height = 2 * (1 - fraction) if back_half else 2 * fraction
        self._scrub.back_half = back_half
        # Not arrived at either end by travelling, so the next tick may not read
        # this as a turn and swap the half back out from under the seek.
        self._scrub.started = False
        self.tcode_sender.set_motion_phase(phase_for_position_fraction(
            height,
            shape=self.robot_hand.shape,
            amplitude=self.robot_hand.amplitude,
            center=self.robot_hand.center,
            rising=not back_half,
        ))

    def _scrub_the_clip(self, frame_count: int, now: float) -> float:
        """How far through the clip to be: exactly as far as the device is up
        its own axis.

        The frame is the picture of where the device is, which is the same
        number the readout's dot draws — so the two cannot drift apart, and a
        motion that only works part of the axis only ever shows that part of the
        clip. :mod:`player_core.clip_scrub` is the whole rule, including which
        half is showing and when that may change.
        """
        if self.tcode_sender is None:
            return self.engine.phase
        return scrub_clip(self._scrub, self._height_of_the_device(now), frame_count)

    def _height_of_the_device(self, now: float) -> float:
        if self._broker_park is not None:
            return self._broker_park.height_at(now)
        return self.tcode_sender.current_position() / POSITION_MAX
