"""The main console — the HUD the player on the main slot draws.

The same console is drawn whichever player holds the slot: the main player over its video in
video mode, Genau into its own window in genau mode.  So the mode switch and the
drive controls keep their places as you flip between modes — only the transport
changes, because it steps the main player's video in one and Genau's clips in the other.

Its top block is the main player's own answer to "what am I playing?" — the status line (the
length mode, or the compilation and your place in it) beside the active-player
dot, with the file on screen as a muted line under it, the same shape each
satellite's HUD leads with.  Both are empty in genau mode, where there is no main player
playlist backing the screen.  Everything else is the console the orchestrator
publishes (:mod:`player_core.console`) plus the Robot Hand's drive readout
(:mod:`player_core.drive_readout`) with its own controls.

The wording and shape are pure functions; the drawing goes onto the slab
:mod:`player_core.hud_panel` owns, the same slab the satellites' HUD is drawn on,
so every player says things the same way and from the same corner.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

import numpy as np
from PIL import Image
from shared_ui.palette import (
    BG_PRIMARY,
    BLUE,
    GREEN,
    MAGENTA,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
)
from shared_ui.spacing import BUTTON_GAP

from .console import (
    BUTTON,
    GAP,
    OSR2_CONTROL_OFF,
    OSR2_PARKED,
    OSR2_RETRACTED,
    Button,
    ConsoleModel,
    ModeHud,
    _row_width,
    console_rows,
    hit_test,
    main_player_displays,
    osr2_row,
    place_rows,
    rows_height,
    tooltip_at,
)
from .drive_readout import (
    DRIVEN_BY_AUTO,
    DRIVEN_BY_FUNSCRIPT,
    DRIVEN_BY_NEUTRAL,
    DRIVEN_BY_NOTHING,
    DRIVEN_BY_ROBOT_HAND,
    POSITION_MAX,
    DriveHud,
    DriveSection,
    DriveTrack,
    section_size,
    track_command,
)
from .drive_readout import controls as drive_controls
from .drive_readout import tracks as drive_tracks
from .geometry import Rect, contains
from .hud_panel import (
    ACTIVE_DOT,
    SYMBOL_FONT,
    HudPanel,
    draw_active_dot,
    draw_button,
    draw_tooltip,
    fit_text,
    load_font,
    text_width,
    to_bgra,
)
from .hud_status import (
    ENHANCED_LABEL,
    LATEST_LABEL,
    SEPARATOR,
    SHUFFLE_LABEL,
    status_line,
)
from .modes import LengthMode, Osr2State

__all__ = [
    "ConsoleHud",
    "ConsolePainter",
    "ModeHud",
    "hud_xy",
    "with_playback_speed",
]

# What the two length modes are called on the line.  The modes themselves are
# named in :mod:`player_core.console`, which is where the buttons for them are
# built — a font-free module, so it can hold the names a painter also needs.
# MIXED is deliberately absent from this mapping: it applies no length filter at
# all, so it narrows nothing and prints nothing — the same silence a satellite
# keeps where its act filter would go when it has none, and the same silence the
# two buttons keep by both sitting dark.
_LENGTH_LABELS = {LengthMode.FULL: "Full length", LengthMode.SHORTS: "Shorts"}

# A compilation is titled for a shelf: "various - Ultimate Example Studio Alpha
# Collection - Volume 6 (v1)".  Everything up to the last dash is the series and
# the trailing "(v1)" the archivist's revision, leaving the volume as the part
# that says which one you are inside.
_REVISION = re.compile(r"\s*\(v\d+\)$")

# What the OSR2 line says by what is driving the device, and the color it says
# it in — green when a funscript is driving, blue when the Robot Hand is, muted
# when nothing is, and the device's own magenta when it is running itself in auto.
# The pill's own word for a device that belongs to neither driver at the
# playhead -- drawn, never published, so it is not one of the wire's states.
OSR2_BUFFER = "buffer"
# The buffer pill wears the trace's own neutral gray, so the word and the line
# under the dot are visibly the same state.
_NEUTRAL_PILL = (168, 168, 174)
_OSR2_LABELS = {
    Osr2State.OFF: "Off", Osr2State.AUTO: "Auto", Osr2State.FUNSCRIPT: "FunScript",
    Osr2State.ROBOT_HAND: "Robot Hand", OSR2_BUFFER: "Buffer",
    # Said in three words because two of them would be read as the device: the
    # OSR2 is on and well, this app has simply stopped sending it anything.  In
    # the red its own button wears, so the lit control and the pill saying what
    # it did are visibly the one fact.
    OSR2_CONTROL_OFF: "Control off",
    OSR2_PARKED: "Parked", OSR2_RETRACTED: "Retracted",
}
_OSR2_COLORS = {
    Osr2State.FUNSCRIPT: GREEN, Osr2State.ROBOT_HAND: BLUE, Osr2State.AUTO: MAGENTA,
    Osr2State.OFF: TEXT_MUTED, OSR2_BUFFER: _NEUTRAL_PILL,
    OSR2_CONTROL_OFF: RED,
    # The held device's line is the handoff's gray -- nobody is moving it -- and
    # the word beside it says so in the same ink.
    OSR2_PARKED: _NEUTRAL_PILL, OSR2_RETRACTED: _NEUTRAL_PILL,
}

# Where each hold keeps the device, as a trace height: home, and the far end.
_HELD_HEIGHT = {OSR2_PARKED: 0.0, OSR2_RETRACTED: 1.0}

# What the OSR2 state means for the trace.  Auto is the device running itself,
# which is a motion of its own to draw in a color of its own.  Off is nothing
# running at all and control off is this app having let go; in neither is
# anything here being sent, so there is no motion of ours to draw and the
# readout goes gray.
_DRIVEN_BY_OSR2 = {
    Osr2State.ROBOT_HAND: DRIVEN_BY_ROBOT_HAND,
    Osr2State.FUNSCRIPT: DRIVEN_BY_FUNSCRIPT,
    Osr2State.AUTO: DRIVEN_BY_AUTO,
}


def _driven_by(osr2: Osr2State) -> str:
    return _DRIVEN_BY_OSR2.get(osr2, DRIVEN_BY_NOTHING)


# The drive readout's own arrows are drawn by the readout, but the console still
# has to know what each posts and name it on hover.
_DRIVE_TIPS = {
    "robot_hand_speed_down": "Motion slower", "robot_hand_speed_up": "Motion faster",
    "robot_hand_amplitude_up": "Amplitude up", "robot_hand_amplitude_down": "Amplitude down",
    "robot_hand_center_up": "Center up", "robot_hand_center_down": "Center down",
}


def _format_rate(rate: float) -> str:
    """A playback rate as a compact label: 1.0 -> '1×', 1.5 -> '1.5×'."""
    return f"{rate:g}×"


def compilation_label(title: str) -> str:
    """*title* cut down to what tells one compilation from another."""
    volume = title.rsplit(" - ", 1)[-1]
    return _REVISION.sub("", volume).strip()


# --- the panel ---------------------------------------------------------------

_SIZE_BODY = 11
_SIZE_TINY = 8
_PAD = 10
DOT_GAP = 8  # the room between the active-player dot and the words beside it
_MARGIN = 8    # inset from the window's top-left corner
_ROW_GAP = 4   # between the top block, the buttons, the OSR2 row, the readout
_SUBTITLE_GAP = 2  # between the status line and the file name under it
_OSR2_H = BUTTON      # the OSR2 line, sized to the controls sharing it
_OSR2_LABEL_GAP = 5   # "OSR2" sits right up against the pill it names …
_OSR2_GROUP_GAP = 16  # … and well clear of the two controls beside them


def hud_xy() -> tuple[int, int]:
    """Where the panel goes: the window's top-left corner, the same place the
    satellites put theirs."""
    return _MARGIN, _MARGIN


@dataclass(frozen=True)
class ConsoleHud:
    """Everything on the main console: the top line, the room's controls, and
    the Robot Hand's drive readout.

    *modes* is drawn only where it applies (video mode); *console* is what Fun
    Time published; *drive* is the live readout, present once the Robot Hand has
    published one.
    """

    modes: ModeHud = field(default_factory=ModeHud)
    console: ConsoleModel = field(default_factory=ConsoleModel)
    drive: DriveHud | None = None
    # The gray the slab is made of, or None for the canvas color every player
    # floating this over a video wants (see hud_panel.HudPanel).  Part of the
    # value compared for the repaint cache, like the rest.
    ground: tuple[int, int, int] | None = None
    # Whether to draw the row that switches between the two players, and the
    # minimize button riding it.  A console drawn inside another app's window is
    # not one of those three and has no borderless window of its own to park, so
    # that row names nothing it can do; everything below it means what it means
    # here.  Part of the value compared for the repaint cache, like the rest.
    modes_row: bool = True

    @property
    def advance_interval(self) -> int:
        """How long an unlocked Genau leaves each clip up.

        Genau owns the pace, so it rides its own drive readout rather than the
        console panel Fun Time publishes — and is read back off the readout
        wherever the console needs it, which is both the auto-advance button and
        the status line.
        """
        if self.drive is not None:
            return self.drive.advance_interval
        return self.console.advance_interval

    @property
    def status_line(self) -> str:
        """The top line's text — everything selecting what is on the main slot, in
        the order each satellite's HUD says the same things.

        This player's words in the slots
        :func:`player_core.hud_status.status_line` lays out, which is where the
        grammar and the shared states' wording live — the satellites say the same
        sentence, and a reader glancing between two screens is reading one sentence
        in two places.

        F-mode is read from either place it can be set: Fun Time publishes it for
        the playlist it owns, and a genau-mode host with a set of its own folds
        in its own switch.  One word for one switch, whichever side turned it on.

        What fills the slots is the main player's own.  The compilation is its playing
        set — a fixed run it plays through rather than the browse it came from.
        The order slot carries the browse order under either player, and Genau's
        advance pace beside it.  The length mode is the filter, and "Mixed"
        prints nothing there: it is every length there is, so it narrows nothing —
        exactly as a satellite prints nothing where its act filter would go when it
        has none.
        """
        compilation = (
            f"{compilation_label(self.modes.compilation)}"
            f"{SEPARATOR}{self.modes.position}/{self.modes.total}"
        ) if self.modes.compilation else ""
        # The browse order, said the same way for whichever player is on this slot:
        # both of them browse in these two orders, so a reader who has just asked
        # for Latest reads the same word back wherever they asked it.  Nothing at
        # all for a host with no browse order (see :attr:`ConsoleModel.latest`) —
        # an empty slot takes no room, the way every other optional slot here does.
        order = "" if self.console.latest is None else (
            LATEST_LABEL if self.console.latest else SHUFFLE_LABEL)
        # The pace an unheld Genau clip moves on at, after the order rather than in
        # place of it: the order says which clip is next, the pace says when.  Only
        # while Genau is the one showing — video mode draws the drive readout too, but
        # an unlocked main player there plays through a playlist rather than on a timer —
        # and only unheld, since nothing is going to move a held clip.
        if not main_player_displays(self.console.main_mode) and not self.console.locked and self.advance_interval:
            pace = f"{self.advance_interval}s"
            order = f"{order}{SEPARATOR}{pace}" if order else pace
        return status_line(
            playing_set=compilation,
            locked=self.console.locked,
            order=order,
            f_mode=self.modes.scripted_filter or bool(self.console.favorites_filter),
            filter_label=self._filter_label,
        )

    @property
    def _filter_label(self) -> str:
        """What has been cut out of what is playing, in the one slot for it.

        Two players fill it and neither can fill it at once: the main player narrows a
        library by length, and Origenerator keeps only the pictures it has
        enhanced — a genau-mode console with no main player playlist backing it, so the
        length mode is empty there by construction.  One slot rather than two
        because a reader glancing between screens is reading one sentence, and
        the answer to "what is left" is one phrase wherever it is asked.
        """
        if self.console.enhanced_filter:
            return ENHANCED_LABEL
        return _LENGTH_LABELS.get(self.modes.length_mode, "")


class ConsolePainter:
    """Paints the main console, and only when something on it has moved.

    A player redraws its overlays every frame at 60 fps and Pillow is nowhere
    near cheap enough for that, so the bitmap is kept until the panel's contents
    change.  The button rects from the last painting are kept beside it — the
    console's own and the drive readout's arrows — so what is clickable is exactly
    what was drawn, and the readout's own bands with them, so what is draggable is
    too.
    """

    def __init__(self, *, width: int | None = None) -> None:
        """*width* holds every panel to one width, whatever is on it.  A console
        hanging in a scene as a screen of its own (FunTimeVR's) otherwise changes
        size with its contents — the genau-mode rows are narrower than the
        video-mode ones, and a long title widens the panel — and a screen that
        grows and shrinks is a screen that moves.  The rows, the readout and
        the OSR2 line must fit, so a width narrower than them is widened, never
        clipped; the two text lines give way instead, elided to fit.  None
        sizes the panel to its contents, as one drawn over the player's own
        window is."""
        self._width = width
        self._body = load_font(_SIZE_BODY)
        self._tiny = load_font(_SIZE_TINY)
        self._glyph = load_font(_SIZE_BODY, SYMBOL_FONT)
        self._drive = DriveSection()
        self._painted: tuple[ConsoleHud, tuple[int, int] | None] | None = None
        self._composed_drive: DriveHud | None = None
        self._image: Image.Image | None = None
        self._bgra: np.ndarray | None = None
        self.buttons: list[tuple[Rect, Button]] = []
        self.tracks: list[DriveTrack] = []
        # Which band a press took hold of, and what it last asked for, so a drag
        # keeps setting the one it started on and only speaks when the value moves.
        self._held: DriveTrack | None = None
        self._asked = ""
        # The trace and the device's position, held still while nothing is being
        # sent — see :meth:`_resolve`.
        self._still: tuple[tuple[float, ...], int, float, float | None] | None = None

    def bgra(self, hud: ConsoleHud, *, hover: tuple[int, int] | None = None) -> np.ndarray:
        """*hud* as an mpv overlay bitmap — what the main player composites into its video."""
        if self._ensure(self._resolve(hud), hover) or self._bgra is None:
            self._bgra = to_bgra(self._image)
        return self._bgra

    def rgba(self, hud: ConsoleHud, *, hover: tuple[int, int] | None = None,
             ) -> tuple[bytes, tuple[int, int]]:
        """*hud* as ``(rgba_bytes, size)`` — what pygame takes, for Genau to blit
        into its own window in genau mode.  The size varies with the contents, so
        the caller sizes its blit from what comes back."""
        self._ensure(self._resolve(hud), hover)
        return self._image.tobytes(), self._image.size

    def _resolve(self, hud: ConsoleHud) -> ConsoleHud:
        """*hud* with everything the drawing player knows folded into it, before
        anything asks whether the panel has moved.

        Folded here rather than at paint time because a readout that is *not*
        moving has to compare equal: the trace held still while nothing is being
        sent arrives as a fresh scroll of Genau's phase every publish, and folded
        after the comparison it would repaint the whole panel forty times a
        second to draw the same still picture.
        """
        drive = hud.drive
        if drive is None:
            self._still = None
            return hud
        # Genau cannot see the handoff, so whoever draws the console tells the
        # readout who has the device.  Anything but Genau dims every control on
        # it: adjusting a motion Genau is not sending is what woke it against the
        # funscript.
        # Not where a composed trace already names who has the device at the
        # playhead — set by the same function that drew the line under the dot —
        # since the round trip lags the arbiter, and the arbiter itself decides
        # seconds before the device is done riding the blue.
        held = _HELD_HEIGHT.get(hud.console.osr2_control)
        if hud.console.device_drives_itself:
            # The device is running its own firmware, and that wins over
            # everything the room does to it: a hold, a let-go, a handoff
            # between two drivers.  None of those reaches it, so none is the
            # picture — one line, the device's own, in its own color.
            drive = replace(drive, driven=DRIVEN_BY_AUTO, segments=())
        elif held is not None:
            # The device is being kept at one end, so that is the picture: a
            # flat line there with the dot on it, in the gray of a device nobody
            # is moving.  Whatever the motion or the script had planned is not
            # reaching it, and drawn it would be a picture of a device in motion.
            drive = replace(
                drive, waveform=(held,) * len(drive.waveform or (0.0,)),
                position=round(held * POSITION_MAX), segments=(), slide=0.0,
                edge=None, let_go=None, driven=DRIVEN_BY_NEUTRAL)
        elif hud.console.osr2_control == OSR2_CONTROL_OFF:
            # Nothing is going out, so nobody has the device — whatever the
            # round trip or the composed trace last said had it.  The trace's own
            # names go with it: a video-mode plan says who has the device at each
            # knot, and kept, they drew the line in the script's green under a
            # word that read "control off".
            drive = replace(drive, driven=DRIVEN_BY_NOTHING, segments=())
        elif not (main_player_displays(hud.console.main_mode) and drive.segments):
            drive = replace(drive, driven=_driven_by(hud.console.osr2))
        # In video mode the readout is not a picture of the Robot Hand's motion: it is the
        # picture of the handoff, and the device changes hands inside it.  The
        # OSR2 reads "off" whenever nothing is answering on the wire, which is
        # exactly the gap between Genau letting go and the script's driver
        # picking up.
        # Frozen ONLY when the trace is Genau's own resampled motion — one
        # nobody is sending, which must not keep animating.  A composed
        # trace (video mode) is the script's plan, computed fresh per
        # frame from the playhead: it keeps sliding through every rest and
        # every handoff whatever the OSR2 state says, because the rests ARE
        # part of what it draws — freezing it on the round-tripped "off"
        # was the picture that stopped scrolling for the length of each gap.
        if not drive.live and (hud.console.osr2_control == OSR2_CONTROL_OFF
                               or not main_player_displays(hud.console.main_mode)):
            # Genau goes on driving regardless — it cannot see that the OSR2 is
            # off — so both the trace and the position it publishes keep moving,
            # and either one left running is a dead readout still claiming to be
            # live.  The slide freezes with them, or the "still" trace would go on
            # creeping left a fraction of a sample at a time.
            if self._still is None:
                self._still = (drive.waveform, drive.position, drive.slide, drive.edge)
            waveform, position, slide, edge = self._still
            drive = replace(drive, waveform=waveform, position=position,
                            segments=(), slide=slide, edge=edge)
        else:
            self._still = None
        return replace(hud, drive=drive)

    def _ensure(self, hud: ConsoleHud, hover: tuple[int, int] | None) -> bool:
        """Repaint if *hud*/*hover* moved; report whether it did (so a cached
        bitmap can be reused).  The panel is redrawn a few times a minute at most
        — Pillow is too slow to run every frame — so the image is kept until it
        changes."""
        if (hud, hover) == self._painted and self._image is not None:
            return False
        self._painted, self._image = (hud, hover), self._paint(hud, hover)
        return True

    def press_at(self, mx: int, my: int) -> str:
        """The command a press at *window* point ``(mx, my)`` posts, "" over none.

        A press inside one of the drive readout's bands takes hold of it as well
        as posting: :meth:`drag_to` then goes on setting that level as the pointer
        moves, so a bar can be dragged and not only clicked.  Anything already
        held is let go first, so a press on an ordinary button never leaves a band
        still latched.
        """
        self.release()
        px, py = self._local(mx, my)
        return hit_test(self.buttons, px, py) or self._grab(px, py)

    def covers(self, mx: int, my: int) -> bool:
        return self._image is not None and contains(
            (0, 0, *self._image.size), *self._local(mx, my))

    @property
    def holding(self) -> bool:
        """Whether a press took hold of one of the readout's bands and has not let
        go — so the player knows a drag belongs here rather than to whatever else
        it would have offered the pointer."""
        return self._held is not None

    def drag_to(self, mx: int, my: int) -> str:
        """The command the pointer posts while a band is held.

        "" while none is, and "" while the level under the pointer is the one
        already asked for — a drag along a bar fires per mouse motion, and every
        one of those that says nothing new is a line in the command file for Fun
        Time to route to a value Genau is already on.
        """
        if self._held is None:
            return ""
        command = track_command(self._held, *self._local(mx, my))
        if command == self._asked:
            return ""
        self._asked = command
        return command

    def release(self) -> None:
        """Let go of whichever band a press took hold of."""
        self._held, self._asked = None, ""

    def _grab(self, px: int, py: int) -> str:
        """Take hold of the band under panel point ``(px, py)`` and say what that
        press asks of it; "" over none, holding nothing.

        A dimmed band is passed over the way a dimmed button is: the readout is
        dimmed whole while a funscript has the device, and a press that could do
        nothing is not offered.
        """
        for track in self.tracks:
            if not track.dim and contains(track.rect, px, py):
                self._held = track
                self._asked = track_command(track, px, py)
                return self._asked
        return ""

    def hover_at(self, mx: int, my: int) -> tuple[int, int] | None:
        """Where to name the button under *window* point ``(mx, my)``, else None."""
        local = self._local(mx, my)
        return local if tooltip_at(self.buttons, *local) else None

    @staticmethod
    def _local(mx: int, my: int) -> tuple[int, int]:
        """A window point in the panel's own coordinates."""
        left, top = hud_xy()
        return mx - left, my - top

    def _draw_top_block(self, draw, y: int, status: str, filename: str,
                        active: bool) -> int:
        """The active-player dot and the status line — what is selecting this
        playlist — with the file on screen muted under it, and the y the next band
        starts at.

        The same shape each satellite's HUD leads with, so a glance between two
        screens finds the same answer in the same corner.  Both are empty in genau
        mode, and the block is then only the dot.
        """
        ascent, descent = self._body.getmetrics()
        text_x = _PAD + ACTIVE_DOT + DOT_GAP
        draw_active_dot(draw, _PAD, y + (ascent + descent) // 2 - ACTIVE_DOT // 2,
                        active)
        if status:
            draw.text((text_x, y + ascent), status, font=self._body,
                      anchor="ls", fill=(*TEXT_PRIMARY, 255))
        y += ascent + descent
        if filename:
            y += _SUBTITLE_GAP
            draw.text((text_x, y), filename, font=self._tiny, anchor="la",
                      fill=(*TEXT_MUTED, 255))
            y += sum(self._tiny.getmetrics())
        return y

    def _paint(self, hud: ConsoleHud, hover: tuple[int, int] | None = None) -> Image.Image:
        console, drive = hud.console, hud.drive
        # Held for the OSR2 pill: with a composed trace on the panel the pill
        # reads the trace's own answer to who has the device (see _osr2_state),
        # and the width helpers need it before the pill is drawn.
        self._composed_drive = (
            drive if (drive is not None and drive.segments
                      and main_player_displays(console.main_mode)) else None)
        rows = [[self._filled(button, hud) for button in row] for row in self._rows(hud)]
        status = hud.status_line
        filename = hud.modes.video
        drive_w, drive_h = section_size() if drive is not None else (0, 0)
        body_ascent, body_descent = self._body.getmetrics()
        top_h = body_ascent + body_descent
        tiny_h = sum(self._tiny.getmetrics())
        filename_h = (_SUBTITLE_GAP + tiny_h) if filename else 0

        text_x = ACTIVE_DOT + DOT_GAP
        parts_w = max(_row_width(rows), drive_w, self._osr2_width(console))
        if self._width is None:
            width = 2 * _PAD + max(
                parts_w,
                text_x + text_width(self._body, status),
                text_x + text_width(self._tiny, filename),
            )
        else:
            width = max(self._width, 2 * _PAD + parts_w)
            room = width - 2 * _PAD - text_x
            status = fit_text(self._body, status, room)
            filename = fit_text(self._tiny, filename, room)
        height = (
            2 * _PAD + top_h + filename_h + _ROW_GAP + rows_height(rows)
            + _ROW_GAP + _OSR2_H
        )
        if drive is not None:
            height += _ROW_GAP + drive_h

        panel = HudPanel(width, height, ground=hud.ground or BG_PRIMARY)
        draw = panel.draw

        y = self._draw_top_block(draw, _PAD, status, filename, console.active)
        y += _ROW_GAP

        self.buttons, self.tracks = place_rows(rows, x=_PAD, y=y), []
        for rect, button in self.buttons:
            self._button(panel.image, draw, rect, button,
                         hovered=hover is not None and contains(rect, *hover))
        y += rows_height(rows) + _ROW_GAP

        self._osr2(panel.image, draw, _PAD, y, console, hover)
        y += _OSR2_H

        if drive is not None:
            y += _ROW_GAP
            # The panel's image rather than its pen: the readout supersamples
            # its trace and composites it back, which a pen cannot carry.
            self._drive.draw(panel.image, _PAD, y, drive)
            # The readout draws its own arrows; the console only needs them as hit
            # targets, so they answer a press and name themselves on hover.
            for control in drive_controls(_PAD, y, drive):
                self.buttons.append((
                    control.rect,
                    Button(control.command, "", _DRIVE_TIPS.get(control.command, ""),
                           dim=control.dim),
                ))
            # A band takes its value from where you press in it, so it is its own
            # target (:meth:`_grab`) — and joins the buttons with no command to
            # post, purely so it names what it sets on hover.  Nothing else on a
            # HUD in a video says a bar can be dragged.
            self.tracks = drive_tracks(_PAD, y, drive)
            for track in self.tracks:
                self.buttons.append((track.rect, Button("", "", track.tooltip)))

        if hover is not None:
            tip = tooltip_at(self.buttons, *hover)
            if tip:
                draw_tooltip(draw, self._tiny, tip, hover, (width, height))
        return panel.image

    @staticmethod
    def _osr2_controls_width(controls: list[Button]) -> int:
        return sum(b.width for b in controls) + GAP * (len(controls) - 1)

    def _osr2_state(self, model: ConsoleModel) -> str:
        """What the pill says has the device — the drawn line's own answer
        when a composed trace is on the panel, so the pill flips exactly when
        the line under the dot changes hands, and says Buffer through the gray
        where the device belongs to neither driver.  The round-tripped osr2
        stands in everywhere else, and for its own device-level states.

        Control off and the two holds answer ahead of all of it: then nobody is
        driving to be named, and what the reader needs to know is why.  Auto
        answers ahead of those in turn, because the device running itself wins
        over anything the room is doing to it."""
        if model.device_drives_itself:
            return model.osr2
        if model.osr2_control in (OSR2_CONTROL_OFF, *_HELD_HEIGHT):
            return model.osr2_control
        drive = self._composed_drive
        if drive is None:
            return model.osr2
        return {
            DRIVEN_BY_ROBOT_HAND: Osr2State.ROBOT_HAND,
            DRIVEN_BY_FUNSCRIPT: Osr2State.FUNSCRIPT,
            DRIVEN_BY_NEUTRAL: OSR2_BUFFER,
        }.get(drive.driven, model.osr2)

    def _osr2_pill_width(self, model: ConsoleModel) -> int:
        osr2 = self._osr2_state(model)
        return text_width(self._tiny, _OSR2_LABELS.get(osr2, osr2)) + 10

    def _osr2_width(self, model: ConsoleModel) -> int:
        return (self._osr2_controls_width(self._osr2_controls(model)) + _OSR2_GROUP_GAP
                + text_width(self._tiny, "OSR2") + _OSR2_LABEL_GAP
                + self._osr2_pill_width(model))

    def _osr2(self, image, draw, x: int, y: int, model: ConsoleModel,
              hover: tuple[int, int] | None = None) -> None:
        """The device's own line: its two controls, then what has it.

        The broker and the takeover switch act on the OSR2 rather than on any
        player, so they share the OSR2's line and sit together at its head —
        placed by hand rather than through the row layout, which would read them
        as different families and open a gap between them.  The label then hugs
        its pill, well clear of the controls, so "OSR2 Robot Hand" reads as one
        read-out instead of as a third button.
        """
        controls = self._osr2_controls(model)
        run_x = x
        for button in controls:
            rect = (run_x, y, button.width, _OSR2_H)
            self._button(image, draw, rect, button,
                         hovered=hover is not None and contains(rect, *hover))
            self.buttons.append((rect, button))
            run_x += button.width + GAP

        label_x = x + self._osr2_controls_width(controls) + _OSR2_GROUP_GAP
        draw.text((label_x, y + _OSR2_H / 2), "OSR2", font=self._tiny, anchor="lm",
                  fill=(*TEXT_MUTED, 255))
        osr2 = self._osr2_state(model)
        state = _OSR2_LABELS.get(osr2, osr2)
        color = _OSR2_COLORS.get(osr2, TEXT_PRIMARY)
        pill_x = label_x + text_width(self._tiny, "OSR2") + _OSR2_LABEL_GAP
        pill_w = self._osr2_pill_width(model)
        # No frame around it: what has the device is a read-out, and an outlined
        # word beside two real buttons reads as a third one you can press.
        draw.text((pill_x + pill_w / 2, y + _OSR2_H / 2), state, font=self._tiny,
                  anchor="mm", fill=(*color, 255))

    @staticmethod
    def _rows(hud: ConsoleHud) -> list:
        """The buttons to draw: the rows the source declared, or -- from one
        that declared none -- the rows :mod:`player_core.console` still builds
        from the panel's switches."""
        if hud.console.rows:
            return [list(row) for row in hud.console.rows]
        return console_rows(hud.console, modes=hud.modes_row, main_player=hud.modes)

    @staticmethod
    def _osr2_controls(model: ConsoleModel) -> list[Button]:
        return list(model.osr2_controls) or osr2_row(model)

    def _filled(self, button: Button, hud: ConsoleHud) -> Button:
        """A read-out as it is drawn: the host's own number written in where the
        source named one, and a word's cell widened to hold it.  A button comes
        back as it was.

        The two numbers are the drawing host's -- the video's rate, the seconds
        an unheld clip stays up -- which no source can know, so the source
        names them and whoever draws fills them in.  A name that outgrows the
        cell the source gave it widens the cell: "Playback speed" ran under the
        button beside it once, its last letter under the minus.
        """
        if button.command:
            return button
        glyph = button.glyph
        if button.host_value == "playback_speed":
            glyph = _format_rate(hud.console.playback_speed)
        elif button.host_value == "advance_interval":
            glyph = f"{hud.advance_interval}s"
        width = button.width
        if glyph.replace(" ", "").isalpha():
            width = max(width, text_width(self._tiny, glyph) + BUTTON_GAP)
        return replace(button, glyph=glyph, width=width)

    def _button(self, image, draw, rect: Rect, button: Button, *,
                hovered: bool = False) -> None:
        """One control, in the one button shape this family's HUDs use: an outline
        when off, filled when on, faded when it cannot be pressed.

        On is white, except where a color already means something: green across
        this family is kept for the favorites and the funscripts, so F-mode —
        which narrows the playlist to what has a funscript — lights green and a
        mode, cruise or auto advance does not; and yellow is what an enhanced
        picture is marked with, so the switch that keeps only those wears its
        mark in yellow at rest and fills with it when it is on.  Two controls wear an app mark instead of a glyph and
        keep its magenta whatever the button is doing: F-mode's "F", and the broker's
        "B" on blue or red, the face it wore on the dashboard — the broker being
        the room's own service and not one of these controls at all.

        A read-out — an item with nothing to post — is bare text with no button, in
        the readout's own key/value colors: a muted word names the value beside
        it, which is bright."""
        x, y, w, h = rect
        if not button.command:
            ink = TEXT_MUTED if button.glyph.replace(" ", "").isalpha() else TEXT_PRIMARY
            if x == _PAD:
                # A word NAMING its row, at the panel's left edge.  Centered in
                # its cell it started hard against that edge while every other
                # row opens with a button whose mark is inset -- so the one row
                # that leads with a word read as unindented beside them.  Left
                # aligned on the family's tight button pad, it lines up with
                # them instead.
                draw.text((x, y + h / 2), button.glyph,
                          font=self._tiny, anchor="lm", fill=(*ink, 255))
                return
            draw.text((x + w / 2, y + h / 2), button.glyph, font=self._tiny, anchor="mm",
                      fill=(*ink, 255))
            return
        draw_button(image, draw, rect, button, hovered=hovered,
                    glyph_font=self._glyph, word_font=self._tiny)


def with_playback_speed(console: ConsoleModel, speed: float) -> ConsoleModel:
    """*console* with the drawing player's own video rate folded in — the main player knows
    its rate, Fun Time does not publish it, so it is added at draw time."""
    return replace(console, playback_speed=speed)
