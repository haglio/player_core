"""The main console — the HUD the player on the main slot draws.

The same console is drawn whichever player holds the slot: Nau over its video in
video mode, Genau into its own window in genau mode.  So the mode switch and the
drive controls keep their places as you flip between modes — only the transport
changes, because it steps Nau's video in one and Genau's clips in the other.

Its top block is Nau's own answer to "what am I playing?" — the status line (the
length mode, or the compilation and your place in it) beside the active-player
dot, with the file on screen as a muted line under it, the same shape each
satellite's HUD leads with.  Both are empty in genau mode, where there is no Nau
playlist behind the screen.  Everything else is the console the orchestrator
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
    AMBER,
    BG_BUTTON,
    BG_BUTTON_ACTIVE,
    BG_PRIMARY,
    BLUE,
    GREEN,
    PINK,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WHITE,
)
from shared_ui.spacing import BUTTON_GAP

from .console import (
    _ROW_LABELS,
    BROKER_ICON,
    BUTTON,
    FMODE_ICON,
    GAP,
    MINIMIZE_ICON,
    PLAYBACK_LABEL_W,
    Button,
    ConsoleModel,
    _row_width,
    console_rows,
    hit_test,
    nau_displays,
    osr2_row,
    place_rows,
    rows_height,
    tooltip_at,
)
from .drive_readout import (
    DRIVEN_BY_FUNSCRIPT,
    DRIVEN_BY_NEUTRAL,
    DRIVEN_BY_NOTHING,
    DRIVEN_BY_ROBOT_HAND,
    DriveHud,
    DriveSection,
    DriveTrack,
    section_size,
    track_command,
)
from .drive_readout import controls as drive_controls
from .drive_readout import tracks as drive_tracks
from .geometry import Rect, contains
from .hud_marks import SHARED_MARK, shared_mark_name
from .hud_panel import (
    ACTIVE_DOT,
    SYMBOL_FONT,
    HudPanel,
    draw_active_dot,
    draw_glyph,
    draw_icon,
    draw_mark,
    draw_tooltip,
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

# Nau's two length modes, named here because the console prints them and nothing
# else in this package cares what they are.  MIXED is deliberately absent: it
# applies no length filter at all, so it narrows nothing and prints nothing — the
# same silence a satellite keeps where its act filter would go when it has none.
FULL, SHORTS = "full", "shorts"
_LENGTH_LABELS = {FULL: "Full length", SHORTS: "Shorts"}

# The two controls that wear an app mark rather than a glyph, and which mark:
# the broker's "B" and F-mode's "F", each the pink five-by-five letter its .ico
# carries (:data:`player_core.hud_panel.ICON_GRIDS`).  Keyed by the marker the
# console puts on the button, the way the waveform's is.
_APP_MARKS = {BROKER_ICON: "B", FMODE_ICON: "F"}

# A compilation is titled for a shelf: "various - Ultimate Example Studio Alpha
# Collection - Volume 6 (v1)".  Everything up to the last dash is the series and
# the trailing "(v1)" the archivist's revision, leaving the volume as the part
# that says which one you are inside.
_REVISION = re.compile(r"\s*\(v\d+\)$")

# What the OSR2 line says by what is driving the device, and the color it says
# it in — green when a funscript is driving, blue when the Robot Hand is, muted
# when nothing is, and the device's own pink when it is running itself in auto.
OSR2_ROBOT_HAND = "robot_hand"  # the one state in which the drive readout can be pressed
OSR2_FUNSCRIPT = "funscript"
OSR2_BUFFER = "buffer"
# The buffer pill wears the trace's own neutral grey, so the word and the line
# under the dot are visibly the same state.
_NEUTRAL_PILL = (168, 168, 174)
_OSR2_LABELS = {
    "off": "Off", "auto": "Auto", OSR2_FUNSCRIPT: "FunScript",
    OSR2_ROBOT_HAND: "Robot Hand", "idle": "Idle", OSR2_BUFFER: "Buffer",
}
_OSR2_COLORS = {
    "funscript": GREEN, OSR2_ROBOT_HAND: BLUE, "auto": PINK,
    "off": TEXT_MUTED, "idle": TEXT_MUTED, OSR2_BUFFER: _NEUTRAL_PILL,
}

# What the OSR2 state means for the trace.  Auto is the device running itself and
# idle is nothing running at all; either way nothing here is being sent, so there
# is no motion of ours to draw.
_DRIVEN_BY_OSR2 = {OSR2_ROBOT_HAND: DRIVEN_BY_ROBOT_HAND, OSR2_FUNSCRIPT: DRIVEN_BY_FUNSCRIPT}


def _driven_by(osr2: str) -> str:
    return _DRIVEN_BY_OSR2.get(osr2, DRIVEN_BY_NOTHING)


# The drive readout's own arrows are drawn by the readout, but the console still
# has to know what each posts and name it on hover.
_DRIVE_TIPS = {
    "robot_hand_speed_down": "Stroke slower", "robot_hand_speed_up": "Stroke faster",
    "robot_hand_amplitude_up": "Amplitude up", "robot_hand_amplitude_down": "Amplitude down",
    "robot_hand_center_up": "Center up", "robot_hand_center_down": "Center down",
}


def compilation_label(title: str) -> str:
    """*title* cut down to what tells one compilation from another."""
    volume = title.rsplit(" - ", 1)[-1]
    return _REVISION.sub("", volume).strip()


@dataclass(frozen=True)
class ModeHud:
    """Nau's own answer to "what am I playing?" — the console's top block.

    *video* is the name of the clip on screen, drawn as the muted line beneath the
    status.  The rest is what the status line is built from:
    *length_mode* is the library's filter, empty when there is no library behind
    the playlist; *compilation* is the volume holding the playlist, with
    *position*/*total* placing the current video in it; *f_mode* is Fun Time's
    filter over whichever of those runs.  All empty in genau mode, where there is
    no Nau playlist to describe and the line is the lock and Genau's own pace —
    see :attr:`ConsoleHud.status_line`, which is where these are put in order,
    since the lock they are said beside is the console's rather than Nau's.
    """

    video: str = ""
    length_mode: str = ""
    compilation: str = ""
    position: int = 0
    total: int = 0
    f_mode: bool = False


# --- the panel ---------------------------------------------------------------

_SIZE_BODY = 11
_SIZE_TINY = 8
_PAD = 10
# How far in a word NAMING its row starts: not at all.  Its cell begins on the
# same left edge as every box in the rows above and below it, so the word lines
# up with that column -- which is what "the margin everything else has" means
# here, the panel's own _PAD.  Anything added on top of that reads as an indent.
# (What made the label look unindented in the first place was its cell being too
# narrow for it: centered, an 80px word in a 66px cell started 7px LEFT of the
# column.  _row_label_width fixes that at the source.)
_ROW_LABEL_INSET = 0
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
    # The grey the slab is made of, or None for the canvas colour every player
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
        # for Latest reads the same word back wherever they asked it.
        order = LATEST_LABEL if self.console.latest else SHUFFLE_LABEL
        # The pace an unheld Genau clip moves on at, after the order rather than in
        # place of it: the order says which clip is next, the pace says when.  Only
        # while Genau is the one showing — video mode draws the drive readout too, but
        # an unlocked Nau there plays through a playlist rather than on a timer —
        # and only unheld, since nothing is going to move a held clip.
        if not nau_displays(self.console.mode) and not self.console.locked and self.advance_interval:
            order = f"{order}{SEPARATOR}{self.advance_interval}s"
        return status_line(
            playing_set=compilation,
            locked=self.console.locked,
            order=order,
            f_mode=self.modes.f_mode or bool(self.console.favorites_filter),
            filter_label=self._filter_label,
        )

    @property
    def _filter_label(self) -> str:
        """What has been cut out of what is playing, in the one slot for it.

        Two players fill it and neither can fill it at once: Nau narrows a
        library by length, and Origenerator keeps only the pictures it has
        enhanced — a genau-mode console with no Nau playlist behind it, so the
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

    def __init__(self) -> None:
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
        """*hud* as an mpv overlay bitmap — what Nau composites into its video."""
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
        # it: adjusting a stroke Genau is not sending is what woke it against the
        # funscript.
        # Not where a composed trace already names who has the device at the
        # playhead — set by the same function that drew the line under the dot —
        # since the round trip lags the arbiter, and the arbiter itself decides
        # seconds before the device is done riding the blue.
        if not (nau_displays(hud.console.mode) and drive.segments):
            drive = replace(drive, driven=_driven_by(hud.console.osr2))
        # In video mode the readout is not a picture of the Robot Hand's stroke: it is the
        # picture of the handoff, and the device changes hands inside it.  The
        # OSR2 reads "off" whenever nothing is answering on the wire, which is
        # exactly the gap between Genau letting go and the script's driver
        # picking up.
        # Frozen ONLY when the trace is Genau's own resampled stroke — a
        # motion nobody is sending, which must not keep animating.  A composed
        # trace (video mode) is the script's plan, computed fresh per
        # frame from the playhead: it keeps sliding through every rest and
        # every handoff whatever the OSR2 state says, because the rests ARE
        # part of what it draws — freezing it on the round-tripped "idle"/"off"
        # was the picture that stopped scrolling for the length of each gap.
        if not drive.live and not nau_displays(hud.console.mode):
            # Genau goes on stroking regardless — it cannot see that the OSR2 is
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
        latched behind it.
        """
        self.release()
        px, py = self._local(mx, my)
        return hit_test(self.buttons, px, py) or self._grab(px, py)

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
                      and nau_displays(console.mode)) else None)
        rows = console_rows(console, modes=hud.modes_row,
                            label_width=self._row_label_width())
        status = hud.status_line
        filename = hud.modes.video
        drive_w, drive_h = section_size() if drive is not None else (0, 0)
        body_ascent, body_descent = self._body.getmetrics()
        top_h = body_ascent + body_descent
        tiny_h = sum(self._tiny.getmetrics())
        filename_h = (_SUBTITLE_GAP + tiny_h) if filename else 0

        width = 2 * _PAD + max(
            _row_width(rows), drive_w, self._osr2_width(console),
            ACTIVE_DOT + DOT_GAP + text_width(self._body, status),
            ACTIVE_DOT + DOT_GAP + text_width(self._tiny, filename),
        )
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
            self._button(panel.image, draw, rect, button)
        y += rows_height(rows) + _ROW_GAP

        self._osr2(panel.image, draw, _PAD, y, console)
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
                    Button(control.action, "", _DRIVE_TIPS.get(control.action, ""),
                           dim=control.dim),
                ))
            # A band takes its value from where you press in it, so it is its own
            # target (:meth:`_grab`) — and joins the buttons with no action to
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
        the line under the dot changes hands, and says Buffer through the grey
        where the device belongs to neither driver.  The round-tripped osr2
        stands in everywhere else, and for its own device-level states."""
        drive = self._composed_drive
        if drive is None:
            return model.osr2
        return {
            DRIVEN_BY_ROBOT_HAND: OSR2_ROBOT_HAND,
            DRIVEN_BY_FUNSCRIPT: OSR2_FUNSCRIPT,
            DRIVEN_BY_NEUTRAL: OSR2_BUFFER,
        }.get(drive.driven, model.osr2)

    def _osr2_pill_width(self, model: ConsoleModel) -> int:
        osr2 = self._osr2_state(model)
        return text_width(self._tiny, _OSR2_LABELS.get(osr2, osr2)) + 10

    def _osr2_width(self, model: ConsoleModel) -> int:
        return (self._osr2_controls_width(osr2_row(model)) + _OSR2_GROUP_GAP
                + text_width(self._tiny, "OSR2") + _OSR2_LABEL_GAP
                + self._osr2_pill_width(model))

    def _osr2(self, image, draw, x: int, y: int, model: ConsoleModel) -> None:
        """The device's own line: its two controls, then what has it.

        The broker and the takeover switch act on the OSR2 rather than on any
        player, so they share the OSR2's line and sit together at its head —
        placed by hand rather than through the row layout, which would read them
        as different families and open a gap between them.  The label then hugs
        its pill, well clear of the controls, so "OSR2 Robot Hand" reads as one
        read-out instead of as a third button.
        """
        controls = osr2_row(model)
        run_x = x
        for button in controls:
            rect = (run_x, y, button.width, _OSR2_H)
            self._button(image, draw, rect, button)
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
        draw.rounded_rectangle([pill_x, y, pill_x + pill_w - 1, y + _OSR2_H - 1],
                               radius=3, outline=(*color, 255), width=1)
        draw.text((pill_x + pill_w / 2, y + _OSR2_H / 2), state, font=self._tiny,
                  anchor="mm", fill=(*color, 255))

    def _row_label_width(self) -> int:
        """How wide a cell holding a row's NAME has to be.

        Measured, because the words do not fit the fixed 66px the layout used:
        "Playback speed" is 80 at this font, so it ran out of its cell and its
        last letter sat under the button beside it.  Both named rows take one
        width so their controls line up under each other, and the family's own
        floor keeps a short label from pulling the pair in tight.
        """
        widest = max(text_width(self._tiny, label) for label in _ROW_LABELS)
        return max(PLAYBACK_LABEL_W, widest + _ROW_LABEL_INSET + BUTTON_GAP)

    def _button(self, image, draw, rect: Rect, button: Button) -> None:
        """One control, in the one button shape this family's HUDs use: an outline
        when off, filled when on, faded when it cannot be pressed.

        On is white, except where a color already means something: green across
        this family is kept for the favorites and the funscripts, so F-mode —
        which narrows the playlist to what has a funscript — lights green and a
        mode, cruise or auto advance does not; and yellow is what an enhanced
        picture is marked with, so the switch that keeps only those wears its
        mark in yellow at rest and fills with it when it is on.  Two controls wear an app mark instead of a glyph and
        keep its pink whatever the button is doing: F-mode's "F", and the broker's
        "B" on blue or red, the face it wore on the dashboard — the broker being
        the room's own service and not one of these controls at all.

        A read-out — an item with nothing to post — is bare text with no box, in
        the readout's own key/value colors: a muted word names the value beside
        it, which is bright."""
        x, y, w, h = rect
        if not button.action:
            ink = TEXT_MUTED if button.glyph.replace(" ", "").isalpha() else TEXT_PRIMARY
            if x == _PAD:
                # A word NAMING its row, at the panel's left edge.  Centered in
                # its cell it started hard against that edge while every other
                # row opens with a box whose mark is inset -- so the one row
                # that leads with a word read as unindented beside them.  Left
                # aligned on the family's tight button pad, it lines up with
                # them instead.
                draw.text((x + _ROW_LABEL_INSET, y + h / 2), button.glyph,
                          font=self._tiny, anchor="lm", fill=(*ink, 255))
                return
            draw.text((x + w / 2, y + h / 2), button.glyph, font=self._tiny, anchor="mm",
                      fill=(*ink, 255))
            return
        broker = button.glyph == BROKER_ICON
        # A plain toggle lights the family's ACTIVE ground -- a step up from the
        # resting one, the same step Origenerator's checked buttons take.  It
        # used to fill white, which is the loudest thing on the panel for a
        # control whose whole news is "this is on", and it left the console
        # reading as a different app from the windows beside it.  Where a color
        # already MEANS something it still wins: green is the favorites and the
        # funscripts, amber is an enhanced picture, and those say more than
        # "engaged".
        lit = (GREEN if button.favorite else AMBER if button.enhanced
               else BLUE if button.choice else BG_BUTTON_ACTIVE)
        # A control at rest sits on the family's button ground rather than on
        # nothing: an outline over the slab read as a hole in it, and made these
        # look like a different kind of control from the ones in the windows.
        fill = (lit if button.lit else RED if button.warn else BLUE if button.hold
                else BG_BUTTON)
        if broker:
            fill = BLUE if button.lit else RED
        # And it carries the family's thin edge whatever it is doing.  The edge
        # used to be the fill's own color at rest, which is no edge at all --
        # the satellite HUDs beside this one draw theirs in the muted gray the
        # rest of the chrome uses, and these read as borderless slabs next to
        # them.
        edge = TEXT_MUTED if (button.dim or fill in (BG_BUTTON, BG_BUTTON_ACTIVE)) else (
            fill or TEXT_MUTED)
        draw.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=3,
                               fill=(*fill, 255) if fill else None,
                               outline=(*edge, 255), width=1)
        # The mark stays white over a colored fill and reverses out of a white
        # one, so a control that changes state changes only what is behind its
        # mark — the way the Dash's mic keeps its white glyph while the panel
        # under it goes blue.  The gray grounds are both dark, so a mark on
        # either keeps its own ink rather than reversing -- only a light fill
        # (white, amber) reverses.
        resting = fill in (BG_BUTTON, BG_BUTTON_ACTIVE)
        ink = (BG_PRIMARY if fill in (WHITE, AMBER) else TEXT_MUTED if button.dim
               else RED if button.danger
               else AMBER if button.enhanced
               else TEXT_PRIMARY if resting else WHITE)
        if button.glyph in _APP_MARKS:
            draw_icon(draw, rect, _APP_MARKS[button.glyph])
        elif button.glyph.startswith(SHARED_MARK):
            draw_mark(image, shared_mark_name(button.glyph), rect, (*ink, 255))
        elif button.glyph == MINIMIZE_ICON:
            self._minimize_icon(draw, rect, ink)
        elif len(button.glyph) == 1 and not button.glyph.isalnum():
            # A symbol needs the face that actually has it, and centring on its
            # own ink — the font's box would drop it toward the button's floor.
            draw_glyph(draw, x + w / 2, y + h / 2, button.glyph, self._glyph, (*ink, 255))
        else:
            draw.text((x + w / 2, y + h / 2), button.glyph, font=self._tiny,
                      anchor="mm", fill=(*ink, 255))

    @staticmethod
    def _minimize_icon(draw, rect: Rect, ink) -> None:
        """The minimize control's face: the bar a Windows title bar puts there.

        Drawn rather than typed for the reason the curve above is — the mark
        Windows uses is U+E921 of Segoe MDL2 Assets, a face this HUD does not
        load, and Pillow draws tofu for a codepoint a face lacks.  Two pixels
        deep across the middle of the button: the same proportion the title bar
        has, so it reads as that gesture and not as an underscore or a dash.
        """
        x, y, w, h = rect
        pad = 5
        cy = y + h / 2
        draw.rectangle([x + pad, cy - 1, x + w - pad - 1, cy], fill=(*ink, 255))


def with_playback_speed(console: ConsoleModel, speed: float) -> ConsoleModel:
    """*console* with the drawing player's own video rate folded in — Nau knows
    its rate, Fun Time does not publish it, so it is added at draw time."""
    return replace(console, playback_speed=speed)
