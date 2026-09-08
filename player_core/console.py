"""The controls on the main console, and where they sit.

Whichever player holds the main slot draws it: Nau in video mode, Genau in
genau mode.  The console is the same in both, so the mode switch and the drive
controls do not move as you flip between them; only the transport changes,
because prev/next step Nau's video in video mode and Genau's clips in genau.

Kept free of Pillow, as :mod:`player_core.satellite_hud` is, so the rows, the
geometry and the hit-testing are testable without a font.  :mod:`player_core.console_hud` paints them; the
drive readout's own arrows come from :mod:`player_core.drive_readout`.

The action on each button is a Fun Time dashboard command verbatim, because that
is where a press goes: appended to the same command file the dashboard wrote, so
nothing new has to learn what these buttons mean, and Fun Time routes each to the
player the mode says owns it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .geometry import Rect, contains
from .hud_marks import shared_mark
from .hud_status import LATEST_LABEL, SHUFFLE_LABEL

__all__ = [
    "CONSOLE_VERBS",
    "ConsoleModel",
    "console_rows",
    "read_console",
    "tooltip_at",
]

BUTTON = 18   # a square control; the wider ones are multiples plus the gaps
VALUE_W = 22  # a value read-out between a pair of buttons (the playback rate)
# The words naming that pair.  A FLOOR, not the width: the cell is widened to
# whatever the row's own label measures (console_rows takes the measurement,
# since this module is font-free by design -- see mode_button_rects for the
# same split).  Fixed at 66 it was narrower than "Playback speed" is at 80, so
# the words ran out of their cell and the "d" sat under the - button beside it.
PLAYBACK_LABEL_W = 66
# The words those cells carry, named here so whoever CAN measure text sizes the
# cell to them rather than to a number that drifts from the font.
_ROW_LABELS = ("Playback speed", "Clip seconds")
GAP = 4       # between buttons along a row
ROW_GAP = 5   # between rows
GROUP_GAP = 12  # between groups of buttons that mean different things

# Nau's length modes, named here because the buttons for them are built here and
# nothing else in this package cares what they are.  MIXED is the one with no
# button: it is every length there is, so it narrows nothing, and it is what the
# console says by leaving both the others dark.
FULL, SHORTS, MIXED = "full", "shorts", "mixed"

_SHAPE_LABELS = {"rounded_square": "Square"}


def shape_label(shape: str) -> str:
    """The waveform's name, for the control that cycles it to say what it is on.

    ``rounded_square`` is the one whose internal name reads badly spelled out;
    the rest title-case.
    """
    if shape in _SHAPE_LABELS:
        return _SHAPE_LABELS[shape]
    return " ".join(word.capitalize() for word in shape.split("_"))


@dataclass(frozen=True)
class ModeHud:
    """Nau's own answer to "what am I playing?" — what only the player knows.

    *video* is the name of the clip on screen, drawn as the muted line beneath
    the status.  *length_mode* is the library's filter, empty when there is no
    library backing the playlist; *compilation* is the volume holding the
    playlist, with *position*/*total* placing the current video in it; *f_mode*
    is Fun Time's filter over whichever of those runs.  All empty in genau mode,
    where there is no Nau playlist to describe.

    The last three are what a control can and cannot do to the video on screen,
    and each defaults to "cannot": a Nau too old to publish them leaves its
    buttons dim, which is the honest answer when nothing has said otherwise.
    """

    video: str = ""
    length_mode: str = ""
    compilation: str = ""
    position: int = 0
    total: int = 0
    f_mode: bool = False
    # Whether the video on screen belongs to a compilation at all — what says
    # the button can be pressed, where ``compilation`` says you are inside one.
    has_compilation: bool = False
    # Whether the library holds another cut of this same video.
    has_other_versions: bool = False
    # Where the clip/scene jump would go from here: "scene" from a clip to the
    # scene it was cut from, "clip" back the other way, "" from a video that is
    # neither.  Most clips' source scenes are not in the library, so "" is the
    # common answer and the button is dim more often than not.
    jump_to: str = ""


@dataclass(frozen=True)
class Button:
    """One item on the console: what it posts, what it looks like, how it is drawn.

    ``lit``, ``warn`` and ``hold`` are the live states — white for on, red for a
    live recording, blue for the loop that recording leaves running.  On is white
    rather than green because across this family green means the favorites and
    the funscripts; a mode being selected or cruise being armed is neither.
    ``favorite`` names the controls that *are* one of those, so their on-state
    keeps the green — F-mode is the only one so far.  ``enhanced`` is the same
    idea in the other color this family spends on a meaning: an enhanced picture
    wears a yellow plus in its corner in Origenerator, so the control that keeps
    only those wears its mark in that yellow at rest and fills with it when it
    is on.  ``dim`` is a control at the
    end of its range or with nothing to act on: drawn faded and left out of the
    hit targets, so a press that could do nothing is not offered.

    An empty ``action`` makes it a read-out: laid out in the row like anything
    else, drawn as a bare value with no button, and never a hit target.
    """

    action: str
    glyph: str
    tooltip: str
    width: int = BUTTON
    lit: bool = False
    warn: bool = False
    hold: bool = False
    dim: bool = False
    favorite: bool = False
    enhanced: bool = False
    # A control that takes something away.  Its mark is drawn red -- the color
    # Origenerator's Delete wears -- so the one button on a panel worth stopping
    # at before clicking says so before its tooltip does.  Red is otherwise this
    # family's alarm, and nothing here is alarming enough to spend it on twice.
    danger: bool = False
    # A choice the player is holding on to but not applying — the browse order
    # and the length filter while a compilation is playing, which replaces both
    # and gives them back on the way out.  Drawn on the family's active gray:
    # visibly set, visibly not the blue of something in force.
    remembered: bool = False
    # Start a new group here: the row opens a GROUP_GAP before this button
    # instead of the ordinary one, so a control that is about something else
    # than its neighbours reads as separate without a rule drawn between them.
    group_break: bool = False


@dataclass(frozen=True)
class ConsoleModel:
    """What Fun Time tells the main player about its slot, so the console can
    draw it — none of which the player can see for itself.

    Everything here arrives published (``nau_console.json``) except
    ``playback_speed``, which is Nau's own and folded in by whoever is drawing.
    """

    mode: str = "video"
    # The dot: whether a bare, player-less command ("next", "lock") lands on the
    # main player rather than on a satellite.
    active: bool = False
    # What is driving the OSR2 right now: off / auto / funscript / robot_hand / idle.
    osr2: str = "off"
    # Whether the OSR2 broker service is up — its own concern, only the main player's.
    broker: bool = False
    # Where Nau's loop machine is: normal / recording (the record key is down and
    # the out point has not landed yet) / looping.  Nau publishes it in its status
    # file and Fun Time forwards it, because the console is drawn in genau mode too
    # — by a player that has no loop machine of its own to ask.
    record: str = "normal"
    # Whether the player on the main slot is holding what is on screen rather
    # than letting it move on — Nau's video in video mode, Genau's clip in
    # genau.  One flag for one padlock, because whichever player is showing is the
    # one the lock holds.  On is where both players open, so it is the default
    # here too: a console drawn before the first panel arrives must not show the
    # lock off when it is not.  Published the same way ``record`` is, and for the
    # same reason — the player drawing this console is not always the one it is
    # describing.
    locked: bool = True
    # Whether the main player's own F-mode is on — its playlist narrowed to the videos
    # that have a funscript.  Nau is told the flag directly as well (its subtitle
    # says so), but the button lights off what Fun Time publishes, because the
    # flag is set from three places — this button, the F key, and a spoken phrase —
    # and only one of them is the player.
    f_mode: bool = False
    # Which browse order the main player is in: newest-first ("Latest") when set,
    # shuffled when clear.  Published for the same reason F-mode is — the order is
    # Fun Time's to set, and the playlist Nau is handed looks the same either way
    # round, so nothing in the file says which order built it.  None is a third
    # answer, the one ``enhanced_filter`` and ``favorites_filter`` below give: this
    # host has no browse order to switch at all, so the console neither draws the
    # pair of buttons for it nor names an order on its status line.  Origenerator's
    # motion panel is the one console that answers that way — its slides are a
    # show's own set, not a browse.
    latest: bool | None = None
    cruise: bool = False
    shape: str = "sine"
    # Nau's video playback rate, shown while Nau is on screen.  Not published —
    # Nau knows its own rate and folds it in; Genau leaves it at 1.
    playback_speed: float = 1.0
    # Seconds an unlocked Genau leaves each clip on screen.  Also not published —
    # Genau owns the pace and says it on the drive readout, which whoever draws
    # the console folds in here.
    advance_interval: int = 0
    # Whether the host is showing only the pictures it has enhanced — and None
    # where the host has no such filter at all, which is every one of these
    # players but Origenerator: an enhancement is a thing IT makes, so nothing
    # else has a set to narrow.  None draws no button rather than a dead one
    # nobody could explain.  Not published either — Fun Time neither sets this
    # filter nor hears about it — so the host that owns it folds it in the way
    # it folds in the pace.
    enhanced_filter: bool | None = None
    # And whether it is showing only its favorites — the same shape, and the
    # same reason: a genau-mode host with a set of its own to narrow has these
    # switches, and one with no set has neither.  ``f_mode`` above is the video
    # branch's flag, published by Fun Time for a playlist IT owns; this one is
    # the genau branch's, folded in by the host that owns the set.  Both light
    # the same F, because a reader glancing between two screens is looking at
    # one switch: play the favorites only.
    favorites_filter: bool | None = None
    # Which shape of video the main player's browse may reach: the VR masters
    # that wrap the view, the flat ones that hang on a screen, or both.  Two
    # flags rather than one word, because all four answers are legal here —
    # including neither, which asks for a browse with nothing in it.  None from
    # a session whose library holds one shape only, which is every one outside
    # the headset: no pair of buttons, exactly as ``latest`` None draws none.
    plays_vr: bool | None = None
    plays_flat: bool | None = None


def read_console(path: Path) -> ConsoleModel | None:
    """The console panel Fun Time published, or None when there is not a whole one.

    None means "keep the console you have": Fun Time replaces this file while the
    player polls it, so a lost race must not empty the panel for a frame.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or "mode" not in raw:
        return None
    return ConsoleModel(
        mode=str(raw.get("mode", "video")),
        active=bool(raw.get("active", False)),
        f_mode=bool(raw.get("f_mode", False)),
        # Absent is None — no browse order to switch — rather than "shuffled":
        # the pair of buttons is drawn only for a publisher that says which order
        # it is in, so a panel nothing would answer does not grow two dead ones.
        latest=(None if raw.get("latest") is None else bool(raw.get("latest"))),
        osr2=str(raw.get("osr2", "off") or "off"),
        broker=bool(raw.get("broker", False)),
        record=str(raw.get("record", "normal") or "normal"),
        locked=bool(raw.get("locked", True)),
        cruise=bool(raw.get("cruise", False)),
        shape=str(raw.get("shape", "sine") or "sine"),
        plays_vr=(None if raw.get("plays_vr") is None else bool(raw.get("plays_vr"))),
        plays_flat=(None if raw.get("plays_flat") is None else bool(raw.get("plays_flat"))),
    )


# The glyphs this console types, as against the marks it draws above.
_GLYPHS = {
    # The transport, in one family of marks: to the ends of the video with a bar,
    # ten seconds either way without one.
    "prev": "⏮", "next": "⏭", "back": "⏪", "fwd": "⏩",
    "open": "📂", "record": "⏺", "save": "💾",
    "lock": "🔒", "minus": "−", "plus": "+",
    # These two are the family's own drawings rather than characters out of a
    # symbol face: the bin is the very bin Origenerator's toolbar wears, and
    # reset is a gear with a circular arrow at its corner — a bare circular
    # arrow is an undo, which is a different act and lives elsewhere.  Each
    # satellite's HUD gives its own reset the same mark, so one gesture wears
    # one face across the room.
    "trash": shared_mark("trash"),
    "reset": shared_mark("reset"),
}

# The switch that keeps only the enhanced pictures wears the family's own mark
# for exactly that: the plus an enhanced picture carries in its corner, with a
# funnel hanging off it.  A bare plus is Enhance — the button that MAKES one, which
# Origenerator's toolbar already has — so the funnel is what tells the two apart.
ENHANCE_FILTER_ICON = shared_mark("enhance_filter")

# The two browse orders, each with a mark of its own: the family's crossed arrows
# for shuffle and the same arrows uncrossed for latest.  A pair rather than one
# button that cycles, because which of the two the player is in is what the panel
# has to say at a glance, and a cycling button says only "press me".  The same
# pair each satellite's HUD carries, so one order wears one face across the room.
SHUFFLE_ICON = shared_mark("shuffle")
LATEST_ICON = shared_mark("latest")

# The two length filters, as one dial read twice: a sector filled to say how much
# of a scene the filter keeps.  Mixed gets no mark of its own — it is every
# length there is, which is what the panel says by lighting both of these.
FULL_LENGTH_ICON = shared_mark("clock_full")
SHORTS_ICON = shared_mark("clock_short")

# The two shapes a video is watched on, read the same way: a gridded hemisphere
# for a VR master that wraps the view, a gridded panel seen at an angle for an
# ordinary flat one.
VR_ICON = shared_mark("vr_hemisphere")
FLAT_ICON = shared_mark("flat_2d")

# Stepping to another cut of the video on screen: two pages offset along a
# diagonal with a double-headed arrow across them.
VERSIONS_ICON = shared_mark("versions")

# The set the video belongs to, played in its own order: a stack of sheets.
COMPILATION_ICON = shared_mark("compilation")

# The jump between a clip and its scene, one mark per direction: the two length
# dials with an arrow underneath saying which of them the press is going to.
CLIP_TO_SCENE_ICON = shared_mark("clip_to_scene")
SCENE_TO_CLIP_ICON = shared_mark("scene_to_clip")

# Skipping ahead to where this video's scripting starts up again: an arrow
# running into the F every scripted thing in this family is marked with.
FUNSCRIPT_JUMP_ICON = shared_mark("funscript_jump")

# The three motion holds, as one drawing of the device from above read three
# ways — the sleeve at the near end, at the far end, or free in between.
PARK_ICON = shared_mark("park")
RETRACT_ICON = shared_mark("retract")
RELEASE_ICON = shared_mark("release")

# The phase nudge: the fraction stacked rather than typed, which makes it as tall
# as the marks beside it and leaves room for the arrow saying which way it goes.
QUARTER_ICON = shared_mark("quarter_offset")

# The waveform control wears a drawn mark rather than a glyph: ∿ is a small mark
# low in the bounds its face lays out, so it read as a smudge in the corner of
# its button whatever the centering.  It is the family's sine now — the very
# one Origenerator's OSR2 switch wears — because from the outside the two are
# the same thing: motion the app is sending the device.
WAVE_ICON = shared_mark("wave")

# The two controls that stand for an app rather than for an action, and so wear
# that app's mark: the magenta five-by-five letter its .ico carries.  The broker's
# "B" sits on blue while the service is up and red while it is down; F-mode's "F"
# on the green the funscripts own.  These are app marks rather than family ones,
# so they keep their own markers rather than naming a shared glyph.
BROKER_ICON = "\x00broker"
FMODE_ICON = "\x00fmode"

# A marker rather than a glyph, because the minimize bar is drawn: the painters
# say why, each beside the rectangle it draws.
MINIMIZE_ICON = "\x00minimize"

# Every dispatch verb a console button can post, as data: the verbs are the
# dashboard's vocabulary, spelled here because the console's buttons post them,
# and a consumer holds its dispatch table to this set rather than finding out
# at the first click that a verb has drifted (which is how the clip-seconds
# buttons came to post a verb nothing answered).  tests/test_console.py holds
# this set to the buttons; the consumer's own test holds its table to this set.
CONSOLE_VERBS = frozenset({
    "broker_panel",
    "browse_library",
    "clipper_save",
    "genau_activate",
    "genau_clip_seconds_down",
    "genau_clip_seconds_up",
    "genau_filter_enhanced",
    "genau_next_clip",
    "genau_prev_clip",
    "genau_weird_clip",
    "main_fmode",
    "main_latest",
    "main_lock",
    "main_minimize",
    "main_next",
    "main_nudge_next",
    "main_nudge_prev",
    "main_prev",
    "main_projection_both",
    "main_projection_flat",
    "main_projection_none",
    "main_projection_vr",
    "main_reset",
    "main_shuffle",
    "main_video_activate",
    "nau_clip_jump",
    "nau_compilation",
    "nau_cycle_version",
    "nau_end_compilation",
    "nau_full_vid",
    "nau_funscript_jump",
    "nau_length_full",
    "nau_length_mixed",
    "nau_length_shorts",
    "nau_record_tap",
    "nau_speed_down",
    "nau_speed_up",
    "quarter_button",
    "robot_hand_cycle_shape",
    "robot_hand_park",
    "robot_hand_release",
    "robot_hand_retract",
    "robot_hand_toggle_cruise",
})

_MODE_BUTTONS = (
    ("main_video_activate", "Video", "video"),
    ("genau_activate", "Genau", "genau"),
)


def nau_displays(mode: str) -> bool:
    """Whether Nau's video is on the main slot — video mode.

    The transport steps Nau's video then, and the nudge / open / clip / record
    that act on a video make sense; in genau mode the transport steps Genau's own
    clips instead and those video actions have nothing to act on.
    """
    return mode == "video"


def _format_rate(rate: float) -> str:
    """A playback rate as a compact label: 1.0 -> '1×', 1.5 -> '1.5×'."""
    return f"{rate:g}×"


def console_rows(model: ConsoleModel, *, modes: bool = True,
                 label_width: int = PLAYBACK_LABEL_W,
                 nau: ModeHud | None = None) -> list[list[Button]]:
    """The console's buttons, row by row, for the mode Fun Time says it is in.

    The mode row leads, so it holds the same place in every mode.  Then the
    transport — Nau's video or Genau's clips — then the pace of whatever that
    transport is stepping (the video's playback rate, or the seconds a clip holds
    the screen), and the Robot Hand's hands-free control row (the drive
    readout's amplitude/center/speed arrows are drawn on the readout itself, not
    here).

    The file controls ride the mode row rather than the transport: browsing for
    another video, recording a loop and saving what it caught are all about
    files rather than about the video on screen, and the transport row below had
    grown long enough that its own groups stopped reading as groups.  They are
    video-mode only, like the rest of that branch, so the mode row's leading
    half — the two mode buttons and the minimize riding them — is what holds its
    place across a mode switch.

    *modes* off drops that whole row.  A player embedded in another app's window
    is not one of the two that row switches between, has no borderless window of
    its own to park, and does its own file handling — but everything below it
    means exactly what it means here, which is the whole point of asking for this
    console rather than building a second one.

    *nau* is what only the player on the slot knows — the length filter, the
    compilation it is inside, whether the video has another version or a scene to
    jump to.  It arrives whole rather than field by field because it already
    travels whole: :class:`ModeHud` is what the status line is built from too,
    and two copies of one fact is what drifts.
    """
    nau = nau or ModeHud()
    rows: list[list[Button]] = [] if not modes else [
        [
            *(
                Button(action, label, f"{label} mode", width=BUTTON * 2 + GAP,
                       lit=model.mode == mode)
                for action, label, mode in _MODE_BUTTONS
            ),
            # Minimize rides the mode row because it is about the main *slot*
            # rather than about what is playing on it — and because this row is
            # the one that is the same in every mode, so the button holds its
            # place as you flip between them where the transport below does not.
            # The window it parks is borderless, like the satellites', so there is
            # no title bar to carry this; the only other way to put it away is the
            # dashboard's own minimize, which takes the whole room.
            Button("main_minimize", MINIMIZE_ICON,
                   "Minimize this player — bring it back from the taskbar",
                   group_break=True),
            *_file_controls(model),
        ],
    ]
    rows.append(_transport_row(model, nau))
    if nau_displays(model.mode):
        rows.append(_playback_speed_row(model, label_width))
    else:
        rows.append(_clip_seconds_row(model, label_width))
    rows.append(_control_row(model))
    return rows


def _file_controls(model: ConsoleModel) -> list[Button]:
    """The file actions, riding the mode row: browse for another video, record a
    loop, save the clip it caught.

    Nau's own, so nothing in genau mode, where there is no video for any of them
    to act on — the same branch the transport row takes, one row up.
    """
    if not nau_displays(model.mode):
        return []
    return [
        Button("browse_library", _GLYPHS["open"], "Browse the library"),
        # Recording a loop and saving what it caught are one job in two presses,
        # so they sit together and apart from the browser.  The record button
        # carries the loop machine: red while the out point is still being
        # marked, blue once the loop is running — the two halves of the gesture
        # look different, so a press that is still open cannot be mistaken for
        # one that landed.
        Button("nau_record_tap", _GLYPHS["record"],
               "Stop recording — mark the loop's out point"
               if model.record == "recording" else
               "Looping — press to drop the loop" if model.record == "looping"
               else "Record loop",
               warn=model.record == "recording",
               hold=model.record == "looping"),
        Button("clipper_save", _GLYPHS["save"], "Save clip"),
    ]


def _browse_order_buttons(model: ConsoleModel, *,
                          remembered: bool = False) -> list[Button]:
    """Which way round the browse runs: shuffled, or newest-first.

    A button each, with exactly one of them lit — the pair each satellite's HUD
    carries, meaning the same thing there.  Both modes have it: in video mode it
    reorders the playlist Fun Time built for Nau, in genau mode it tells Genau to
    rescan its clips the other way round.

    Nothing at all for a host with no browse order to name (``latest`` None) —
    see :attr:`ConsoleModel.latest`.
    """
    if model.latest is None:
        return []
    on = (not model.latest, bool(model.latest))
    return [
        Button("main_shuffle", SHUFFLE_ICON, f"{SHUFFLE_LABEL} — reshuffle what plays",
               lit=on[0] and not remembered, remembered=on[0] and remembered),
        Button("main_latest", LATEST_ICON, f"{LATEST_LABEL} — reload it newest-first",
               lit=on[1] and not remembered, remembered=on[1] and remembered),
    ]


def _projection_buttons(model: ConsoleModel, *, remembered: bool) -> list[Button]:
    """Which shape of video the browse may reach: VR masters, flat ones, or both.

    Each button is a shape it INCLUDES, exactly as the length pair beside it is a
    length it includes, so both lit is every shape there is.  Unlike the lengths,
    turning the last one off is allowed: it asks for a browse with nothing in it,
    which is a degenerate answer but a real one, and no press here is refused.

    Nothing at all where the library holds one shape only — see
    :attr:`ConsoleModel.plays_vr`.
    """
    if model.plays_vr is None or model.plays_flat is None:
        return []
    vr, flat = bool(model.plays_vr), bool(model.plays_flat)

    def state(on: bool) -> dict:
        return {"lit": on and not remembered, "remembered": on and remembered}

    return [
        Button(
            ("main_projection_flat" if flat else "main_projection_none") if vr
            else ("main_projection_both" if flat else "main_projection_vr"),
            VR_ICON,
            "Only the VR videos are playing" if vr and not flat
            else "Drop the VR videos" if vr
            else "Put the VR videos back", **state(vr)),
        Button(
            ("main_projection_vr" if vr else "main_projection_none") if flat
            else ("main_projection_both" if vr else "main_projection_flat"),
            FLAT_ICON,
            "Only the flat videos are playing" if flat and not vr
            else "Drop the flat videos" if flat
            else "Put the flat videos back", **state(flat)),
    ]


def _length_buttons(nau: ModeHud, *, remembered: bool) -> list[Button]:
    """How long a thing has to be to play: full length, shorts, or both.

    Each button is a length it INCLUDES, so both lit is every length there is,
    which is Mixed.  Turning one off asks for the other on its own, and turning
    it back on asks for Mixed again — the third mode reachable without a button
    of its own, and no button ever meaning "off".  Turning off the only one
    still lit would ask for nothing at all, which the player cannot play, so the
    last lit button is dim rather than offering it.

    Written out rather than looped: the verbs a button posts are read off this
    source (``tests/test_console.py``), so each has to be a literal here.

    Nothing at all where there is no length mode to name: a playlist Fun Time
    handed over with no library under it has no length filter running, exactly
    as the status line's own slot is empty there.
    """
    if not nau.length_mode:
        return []
    mixed = nau.length_mode not in (FULL, SHORTS)
    full, shorts = mixed or nau.length_mode == FULL, mixed or nau.length_mode == SHORTS

    def state(on: bool) -> dict:
        # The last lit one is unpressable only while the length is what is
        # actually running: inside a compilation it is held rather than in
        # force, and naming a length there is one of the ways back out.
        return {"lit": on and not remembered, "remembered": on and remembered,
                "dim": on and not mixed and not remembered}

    return [
        Button("nau_length_shorts" if full else "nau_length_mixed", FULL_LENGTH_ICON,
               "Only the full-length scenes are playing" if full and not mixed
               else "Drop the full-length scenes" if full
               else "Put the full-length scenes back", **state(full)),
        Button("nau_length_full" if shorts else "nau_length_mixed", SHORTS_ICON,
               "Only the shorts are playing" if shorts and not mixed
               else "Drop the shorts" if shorts
               else "Put the shorts back", **state(shorts)),
    ]


def _compilation_button(nau: ModeHud) -> Button:
    """The set the video on screen belongs to, played in its own order.

    One button for both halves of the gesture: pressing it enters the
    compilation, and pressing the lit one leaves it again.  Dim for a video that
    belongs to no compilation, which is most of the library.
    """
    inside = bool(nau.compilation)
    return Button(
        "nau_end_compilation" if inside else "nau_compilation",
        COMPILATION_ICON,
        "Playing this compilation in order — press to leave it" if inside
        else "Play this video's compilation, in order"
        + ("" if nau.has_compilation else " (this one belongs to none)"),
        lit=inside, dim=not (inside or nau.has_compilation),
    )


def _clip_scene_button(nau: ModeHud) -> Button:
    """The jump between a clip and the scene it was cut from.

    One button both ways: from a clip it goes to the scene, from a scene to the
    clip, and the mark says which by the direction of its arrow.  Neither
    touches the playlist — one video, and "next" carries on from where it was.
    Dim wherever there is nothing on the other end, which is the common case:
    most clips' source scenes are not in the library.
    """
    to_scene = nau.jump_to == "scene"
    return Button(
        "nau_full_vid" if to_scene else "nau_clip_jump",
        CLIP_TO_SCENE_ICON if to_scene else SCENE_TO_CLIP_ICON,
        "Play the full scene this clip came from" if to_scene
        else "Back to the clip taken from this scene" if nau.jump_to == "clip"
        else "Jump between a clip and its full scene (neither for this video)",
        dim=not nau.jump_to,
    )


def _transport_row(model: ConsoleModel, nau: ModeHud) -> list[Button]:
    """Stepping and the actions on what is on screen, then the browse itself.

    In video mode the stepping is Nau's video — step it, nudge inside it, hold it
    against the end of the playlist's advance.  In genau it is Genau's own clips
    — step them, hold one, mark one weird; the nudges have no video to act on.
    Both branches end with what narrows the browse and what orders it.

    The padlock is in both, because both players have one and it means the same
    thing on each: hold what is on screen.  Which player it reaches is the mode's
    business, not this row's — the same rule prev/next already follow.
    """
    if nau_displays(model.mode):
        return [
            # Ordered as the video runs: back to the last one, back ten, forward
            # ten, on to the next.
            Button("main_prev", _GLYPHS["prev"], "Previous video"),
            Button("main_nudge_prev", _GLYPHS["back"], "Back 10s"),
            Button("main_nudge_next", _GLYPHS["fwd"], "Forward 10s"),
            Button("main_next", _GLYPHS["next"], "Next video"),
            # What the end of the video does, so it belongs with the stepping:
            # locked (the main player's default) the video repeats and the two
            # buttons beside it are the only way off it; unlocked it plays out
            # into the next one and the playlist runs around.  The same padlock a
            # satellite's HUD carries, and lit the same way when it is on.
            Button("main_lock", _GLYPHS["lock"],
                   "Locked — this video repeats; press to play on through the "
                   "playlist" if model.locked
                   else "Unlocked — plays on through the playlist; press to hold "
                        "this video",
                   # Green, like the satellite HUDs' lock: a lock puts the clip
                   # in the favorites, and green is what this family spends on
                   # the favorites and the funscripts.  On the ordinary active
                   # gray it was indistinguishable from every other toggle.
                   lit=model.locked, favorite=True),
            # F-mode is per player now — Fun Time's dashboard used to carry one
            # switch for the room and every player carries its own instead.  Here
            # it narrows the playlist to the videos that have a funscript, so it
            # sits with the browser: both change what there is to step through,
            # rather than acting on the video on screen or on where it ends.
            Button("main_fmode", FMODE_ICON,
                   "F-Mode — play only the videos that have a funscript",
                   lit=model.f_mode, favorite=True),
            # And the way back out of all of it, the same button each satellite's
            # HUD carries: drop everything narrowing what plays — the length mode
            # (with any compilation it was feeding) and F-mode together.  It sits
            # past the two switches because it is the wider gesture: they each
            # turn one thing on or off, this puts the lot back.  Only in this
            # branch, like F-mode above — in genau mode there is no Nau playlist
            # for either of them to be narrowing.
            Button("main_reset", _GLYPHS["reset"],
                   "Reset — the whole library back, with F-Mode off"),
            # Then the browse itself, group by group: which way round it runs,
            # which shape of video is in it, how long a thing has to be to be in
            # it, the set the video belongs to, the scene it came from, and
            # another cut of it.  Reset stands
            # apart from all of them, being what puts them back rather than one
            # more of them.  A compilation replaces the browse while it plays, so
            # the order and the length show as held rather than in force.
            *_browse_order_buttons(model, remembered=bool(nau.compilation)),
            *_projection_buttons(model, remembered=bool(nau.compilation)),
            *_length_buttons(nau, remembered=bool(nau.compilation)),
            _compilation_button(nau),
            _clip_scene_button(nau),
            Button("nau_cycle_version", VERSIONS_ICON,
                   "Another version of this video"
                   + ("" if nau.has_other_versions else " (none for this one)"),
                   dim=not nau.has_other_versions),
        ]
    return [
        Button("genau_prev_clip", _GLYPHS["prev"], "Previous clip"),
        Button("genau_next_clip", _GLYPHS["next"], "Next clip"),
        Button("main_lock", _GLYPHS["lock"],
               "Locked — this clip repeats; press to move on every "
               f"{model.advance_interval}s" if model.locked
               else "Unlocked — moving on every "
                    f"{model.advance_interval}s; press to hold this clip",
               lit=model.locked, favorite=True),
        # The narrowing switches sit straight after the lock, in the order the
        # other branch puts them in: both say what there is to step through
        # rather than acting on what is on screen or on where it ends.  F leads,
        # holding the place it holds over there, and the rest group after it.
        # Each appears only where the host has that filter at all — see
        # ConsoleModel.favorites_filter and .enhanced_filter.
        *([] if model.favorites_filter is None else [
            Button("main_fmode", FMODE_ICON,
                   "Showing the favorites only — press for all of them"
                   if model.favorites_filter
                   else "F-Mode — play only the favorites",
                   lit=model.favorites_filter, favorite=True),
        ]),
        *([] if model.enhanced_filter is None else [
            Button("genau_filter_enhanced", ENHANCE_FILTER_ICON,
                   "Showing the enhanced pictures only — press for all of them"
                   if model.enhanced_filter
                   else "Show only the pictures that have been enhanced",
                   lit=model.enhanced_filter, enhanced=True),
        ]),
        Button("genau_weird_clip", _GLYPHS["trash"], "Mark weird — move it out",
               danger=True),
        # And which way round Genau walks its clips — the same pair the video
        # branch ends on, because the question is the same one.
        *_browse_order_buttons(model),
    ]


def _playback_speed_row(model: ConsoleModel, label_width: int = PLAYBACK_LABEL_W) -> list[Button]:
    """Nau's video playback rate: slower, the rate itself, faster.

    Named, because "Speed" already means the *motion* rate down on the drive
    readout and an unlabelled −/+ pair beside a number said neither.
    """
    return [
        Button("", "Playback speed", "", width=label_width),
        Button("nau_speed_down", _GLYPHS["minus"], "Play the video slower"),
        Button("", _format_rate(model.playback_speed), "", width=VALUE_W),
        Button("nau_speed_up", _GLYPHS["plus"], "Play the video faster"),
    ]


def _clip_seconds_row(model: ConsoleModel, label_width: int = PLAYBACK_LABEL_W) -> list[Button]:
    """How long an unlocked Genau leaves each clip on screen: fewer, the number
    itself, more.

    Genau's clips are fractions of a second, so an unlocked Genau cannot simply
    play through them — it would strobe — and this is the only thing that says how
    fast it does move.  Shaped like the playback-speed row above, and named for the
    same reason: a bare −/+ pair beside a number says "less/more" of nothing.

    The padlock in the transport row is the only switch; this row is just its
    pace.
    """
    return [
        Button("", "Clip seconds", "", width=label_width),
        Button("genau_clip_seconds_down", _GLYPHS["minus"], "Move on sooner"),
        Button("", f"{model.advance_interval}s", "", width=VALUE_W),
        Button("genau_clip_seconds_up", _GLYPHS["plus"], "Leave each clip longer"),
    ]


def _control_row(model: ConsoleModel) -> list[Button]:
    """Everything the Robot Hand does that is not a level on the readout: the
    shape of the motion, then the three ways to stop it and start it again.

    The holds are a group of their own because they are a different kind of
    thing from the three before them — those say what the motion IS, these say
    whether there is one.  Park settles the device home and retract sends it to
    the far end, away; release puts back whatever it was doing before either,
    cruise included.  Unlike OmniPause the room plays on through all three.

    The funscript jump rides the end of this row rather than the transport's:
    the transport row is full, and this is the row about what the device is
    doing, which is the very thing that jump goes looking for.  Nau's, so it is
    not there in genau mode, where there is no scripted video to skip inside.
    """
    return [
        Button("robot_hand_toggle_cruise", "cc",
               "Cruise control: vary the motion hands-free", lit=model.cruise),
        Button("robot_hand_cycle_shape", WAVE_ICON, f"Waveform: {shape_label(model.shape)}"),
        Button("quarter_button", QUARTER_ICON, "Offset the motion a ¼ cycle"),
        Button("robot_hand_park", PARK_ICON,
               "Park — hold the motion still, settled home"),
        Button("robot_hand_retract", RETRACT_ICON,
               "Retract — hold it still at the far end, away from you"),
        Button("robot_hand_release", RELEASE_ICON,
               "Release — back to whatever the motion was doing, cruise included"),
        *([
            Button("nau_funscript_jump", FUNSCRIPT_JUMP_ICON,
                   "Skip ahead to where this video's scripting starts up again"),
        ] if nau_displays(model.mode) else []),
    ]


def osr2_row(model: ConsoleModel) -> list[Button]:
    """The control that sits beside the OSR2 read-out.

    The broker is the service that talks to the OSR2 at all, so it acts on the
    device rather than on a player and shares the device's line.
    """
    return [
        Button("broker_panel", BROKER_ICON,
               "OSR2 broker is running — press to stop it" if model.broker
               else "OSR2 broker is not running — press to start it",
               lit=model.broker, warn=not model.broker),
    ]


def place_rows(rows: list[list[Button]], *, x: int, y: int) -> list[tuple[Rect, Button]]:
    """Each button's rect, rows stacked down from ``(x, y)``.

    One placement feeds both the painting and the hit-testing, so what is drawn
    and what is clickable cannot drift apart.
    """
    placed: list[tuple[Rect, Button]] = []
    row_y = y
    for row in rows:
        run_x = x
        for index, button in enumerate(row):
            if index and _group_break(row, index):
                run_x += GROUP_GAP - GAP
            placed.append(((run_x, row_y, button.width, BUTTON), button))
            run_x += button.width + GAP
        row_y += BUTTON + ROW_GAP
    return placed


def _group_break(row: list[Button], index: int) -> bool:
    """Whether a wider gap belongs before ``row[index]``.

    The controls fall into groups that mean different things — stepping the video,
    nudging inside it, the file actions — and a run of evenly spaced squares reads
    as one long undifferentiated strip.
    """
    previous, current = row[index - 1], row[index]
    if current.group_break:
        return True  # the button says so itself (the mode row's minimize)
    if not current.action or not previous.action:
        # A word naming the row stands apart from the controls; a value sitting
        # between a pair of them belongs with them, and pushing the − and + that
        # far apart made the pair read as two unrelated buttons.
        readout = current if not current.action else previous
        return readout.glyph.replace(" ", "").isalpha()
    return _family(previous.action) != _family(current.action)


# Robot Hand controls whose command name does not begin with robot_hand_.
_ROBOT_HAND_CONTROLS = frozenset({"quarter_button"})
# Recording a loop and saving what it caught: one job, two presses.
_CAPTURE_CONTROLS = frozenset({"nau_record_tap", "clipper_save"})
# The two switches: the lock holds what is on screen against moving on, F-mode
# narrows what there is to play at all.  Both are states the player sits *in*,
# where everything around them does its thing once and is over.  The lock also
# shares the transport's command prefix, so it has to be named here to leave
# that run.
_SWITCH_CONTROLS = frozenset({"main_lock", "main_fmode"})
# The tail of the transport row, in four groups.  Reset stands alone between the
# switches and the rest: it is what turns all of them back off, so it must read
# as neither a third switch nor one of the three things it undoes.  Then which
# way round the browse runs, then how long a thing has to be to be in it, then
# stepping to another cut of the one on screen.  Named here because most of them
# share a command prefix with a run they are not part of.
_RESET_CONTROLS = frozenset({"main_reset"})
_ORDER_CONTROLS = frozenset({"main_shuffle", "main_latest"})
_PROJECTION_CONTROLS = frozenset({
    "main_projection_both", "main_projection_vr",
    "main_projection_flat", "main_projection_none",
})
_LENGTH_CONTROLS = frozenset({"nau_length_full", "nau_length_shorts", "nau_length_mixed"})
_COMPILATION_CONTROLS = frozenset({"nau_compilation", "nau_end_compilation"})
_CLIP_JUMP_CONTROLS = frozenset({"nau_full_vid", "nau_clip_jump"})
_VERSION_CONTROLS = frozenset({"nau_cycle_version"})
# The three ways to stop the motion and start it again, on the control row.  A
# different kind of thing from the shape controls before them — those say what
# the motion IS, these say whether there is one — and they share the Robot Hand's
# prefix, so they have to be named to leave that run.  The funscript jump is not
# the Robot Hand's at all, and closes that row on its own.
_HOLD_CONTROLS = frozenset({"robot_hand_park", "robot_hand_retract", "robot_hand_release"})
_JUMP_CONTROLS = frozenset({"nau_funscript_jump"})
# The controls that act on the window rather than on anything inside it, so they
# stand apart from whatever they share a row with.  Named rather than left to the
# main_ prefix below: minimize sits beside the mode buttons and would otherwise
# read as a fourth mode.
_WINDOW_CONTROLS = frozenset({"main_minimize"})

# Every group named by a set rather than by a command prefix, in the order the
# question is asked.  A dict rather than a run of ifs: each new group was one
# more branch in a function whose whole body was branches.
_NAMED_GROUPS: dict[str, frozenset[str]] = {
    "window": _WINDOW_CONTROLS,
    "robot_hand_": _ROBOT_HAND_CONTROLS,
    "hold": _HOLD_CONTROLS,
    "jump": _JUMP_CONTROLS,
    "capture": _CAPTURE_CONTROLS,
    "switch": _SWITCH_CONTROLS,
    "reset": _RESET_CONTROLS,
    "order": _ORDER_CONTROLS,
    "projection": _PROJECTION_CONTROLS,
    "length": _LENGTH_CONTROLS,
    "compilation": _COMPILATION_CONTROLS,
    "clip_jump": _CLIP_JUMP_CONTROLS,
    "version": _VERSION_CONTROLS,
}


def _family(action: str) -> str:
    """Which group of controls *action* belongs to."""
    # The two mode buttons are one group; genau_activate would otherwise fall
    # to the Genau controls' prefix below.
    if action.endswith("_activate"):
        return "mode"
    for group, verbs in _NAMED_GROUPS.items():
        if action in verbs:
            return group
    # Stepping the video and nudging inside it are one run of four marks, so they
    # are one family: prev, back ten, forward ten, next, evenly spaced.
    for prefix in ("main_", "nau_speed", "robot_hand_", "genau_"):
        if action.startswith(prefix):
            return prefix
    return "file"


def _row_width(rows: list[list[Button]]) -> int:
    """How wide the widest row runs — what the panel has to be to hold them."""
    placed = place_rows(rows, x=0, y=0)
    return max((rect[0] + rect[2] for rect, _b in placed), default=0)


def rows_height(rows: list[list[Button]]) -> int:
    """How tall the stack runs, with no trailing row gap."""
    return max(0, len(rows) * (BUTTON + ROW_GAP) - ROW_GAP)


def hit_test(placed: list[tuple[Rect, Button]], px: int, py: int) -> str:
    """The command for a press at ``(px, py)``, or "" over none of the buttons.

    A dimmed control is skipped: it is at its limit or has nothing to act on, so
    the press it would post is one Fun Time would ignore.
    """
    for rect, button in placed:
        if button.dim or not button.action:
            continue
        if contains(rect, px, py):
            return button.action
    return ""


def tooltip_at(placed: list[tuple[Rect, Button]], px: int, py: int) -> str:
    """What the button under ``(px, py)`` is — every glyph here is cryptic on
    purpose, so each one names itself on hover.  A dimmed control still answers:
    knowing why it cannot be pressed is the point."""
    for (bx, by, bw, bh), button in placed:
        if bx <= px < bx + bw and by <= py < by + bh:
            return button.tooltip
    return ""
