"""The controls on the main console, and where they sit.

Whichever player holds the main slot draws it: Nau in nau and hybrid, Genau in
genau mode.  The console is the same in every mode, so the mode switch and the
drive controls do not move as you flip between them; only the transport changes,
because prev/next step Nau's video in nau/hybrid and Genau's clips in genau.

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
    else, drawn as a bare value with no box, and never a hit target.
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
    # One of a set of mutually exclusive modes -- Nau/Hybrid/Genau here, the
    # satellite side's Player/Origenerator on its own HUD.  Lit, it fills the
    # family's BLUE rather than the active gray every other toggle takes: with
    # every button now carrying a lit ground, one shade lighter was too small a
    # difference to find the mode you are in at a glance.
    choice: bool = False
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

    mode: str = "nau"
    # The dot: whether a bare, player-less command ("next", "lock") lands on the
    # main player rather than on a satellite.
    active: bool = False
    # What is driving the OSR2 right now: off / auto / funscript / genau / idle.
    osr2: str = "off"
    # Whether the OSR2 broker service is up — its own concern, only the main player's.
    broker: bool = False
    # Where Nau's loop machine is: normal / recording (the record key is down and
    # the out point has not landed yet) / looping.  Nau publishes it in its status
    # file and Fun Time forwards it, because the console is drawn in genau mode too
    # — by a player that has no loop machine of its own to ask.
    record: str = "normal"
    # Whether the player on the main slot is holding what is on screen rather
    # than letting it move on — Nau's video in nau and hybrid, Genau's clip in
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
    # else shuffled.  Published for the same reason F-mode is — the order is Fun
    # Time's to set, and the playlist Nau is handed looks the same either way round,
    # so nothing in the file says which order built it.
    latest: bool = False
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
    # switches, and one with no set has neither.  ``f_mode`` above is the nau
    # branch's flag, published by Fun Time for a playlist IT owns; this one is
    # the genau branch's, folded in by the host that owns the set.  Both light
    # the same F, because a reader glancing between two screens is looking at
    # one switch: play the favorites only.
    favorites_filter: bool | None = None


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
        mode=str(raw.get("mode", "nau")),
        active=bool(raw.get("active", False)),
        f_mode=bool(raw.get("f_mode", False)),
        latest=bool(raw.get("latest", False)),
        osr2=str(raw.get("osr2", "off") or "off"),
        broker=bool(raw.get("broker", False)),
        record=str(raw.get("record", "normal") or "normal"),
        locked=bool(raw.get("locked", True)),
        cruise=bool(raw.get("cruise", False)),
        shape=str(raw.get("shape", "sine") or "sine"),
    )


# The glyphs this console types, as against the marks it draws above.
_GLYPHS = {
    # The transport, in one family of marks: to the ends of the video with a bar,
    # ten seconds either way without one.
    "prev": "⏮", "next": "⏭", "back": "⏪", "fwd": "⏩",
    "open": "📂", "record": "⏺", "save": "💾",
    "lock": "🔒", "quarter": "¼", "minus": "−", "plus": "+",
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
# funnel hung off it.  A bare plus is Enhance — the button that MAKES one, which
# Origenerator's toolbar already has — so the funnel is what tells the two apart.
ENHANCE_FILTER_ICON = shared_mark("enhance_filter")

# The waveform control wears a drawn mark rather than a glyph: ∿ is a small mark
# low in a big box, so it read as a smudge in the corner of its button whatever
# the centring.  It is the family's sine now — the very one Origenerator's OSR2
# switch wears — because from the outside the two are the same thing: motion the
# app is sending the device.
WAVE_ICON = shared_mark("wave")

# The two controls that stand for an app rather than for an action, and so wear
# that app's mark: the pink five-by-five letter its .ico carries.  The broker's
# "B" sits on blue while the service is up and red while it is down; F-mode's "F"
# on the green the funscripts own.  These are app marks rather than family ones,
# so they keep their own markers rather than naming a shared glyph.
BROKER_ICON = "\x00broker"
FMODE_ICON = "\x00fmode"

# A marker rather than a glyph, because the minimize bar is drawn: the painters
# say why, each beside the rectangle it draws.
MINIMIZE_ICON = "\x00minimize"

_MODE_BUTTONS = (
    ("nau_activate", "Nau", "nau"),
    ("hybrid_activate", "Hybrid", "hybrid"),
    ("genau_activate", "Genau", "genau"),
)


def nau_displays(mode: str) -> bool:
    """Whether Nau's video is on the main slot — nau and hybrid.

    The transport steps Nau's video then, and the nudge / open / clip / record
    that act on a video make sense; in genau mode the transport steps Genau's own
    clips instead and those video actions have nothing to act on.
    """
    return mode in ("nau", "hybrid")


def genau_drives(mode: str) -> bool:
    """Whether a waveform is driving the device — genau and hybrid.

    Only then do amplitude, centre, speed, cruise and the rest mean anything, so
    only then does the drive readout and its control row appear.
    """
    return mode in ("genau", "hybrid")


def _format_rate(rate: float) -> str:
    """A playback rate as a compact label: 1.0 -> '1×', 1.5 -> '1.5×'."""
    return f"{rate:g}×"


def console_rows(model: ConsoleModel, *, modes: bool = True,
                 label_width: int = PLAYBACK_LABEL_W) -> list[list[Button]]:
    """The console's buttons, row by row, for the mode Fun Time says it is in.

    The mode row leads, so it holds the same place in every mode.  Then the
    transport — Nau's video or Genau's clips — then the pace of whatever that
    transport is stepping (the video's playback rate, or the seconds a clip holds
    the screen), and, while Genau is driving, the hands-free control row (the
    drive readout's amplitude/centre/speed arrows are drawn on the readout itself,
    not here).

    *modes* off drops that leading row, and the minimize button riding it with
    it.  A player embedded in another app's window is not one of the three that
    row switches between, and has no borderless window of its own to park — but
    everything below it means exactly what it means here, which is the whole
    point of asking for this console rather than building a second one.
    """
    rows: list[list[Button]] = [] if not modes else [
        [
            *(
                Button(action, label, f"{label} mode", width=BUTTON * 2 + GAP,
                       lit=model.mode == mode, choice=True)
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
        ],
    ]
    rows.append(_transport_row(model))
    if nau_displays(model.mode):
        rows.append(_playback_speed_row(model, label_width))
    else:
        rows.append(_clip_seconds_row(model, label_width))
    if genau_drives(model.mode):
        rows.append(_control_row(model))
    return rows


def _transport_row(model: ConsoleModel) -> list[Button]:
    """Stepping and the actions on what is on screen.

    In nau/hybrid that is Nau's video — step it, nudge inside it, hold it against
    the end of the playlist's advance, browse for another, save a clip, record a
    loop.  In genau it is Genau's own clips — step them, hold one, mark one weird;
    nudge/browse/clip/record have no video to act on.

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
            Button("browse_library", _GLYPHS["open"], "Browse the library"),
            # Recording a loop and saving what it caught are one job in two
            # presses, so they sit together and apart from the browser.  The
            # record button carries the loop machine: red while the out point is
            # still being marked, blue once the loop is running — the two halves
            # of the gesture look different, so a press that is still open cannot
            # be mistaken for one that landed.
            Button("nau_record_tap", _GLYPHS["record"],
                   "Stop recording — mark the loop's out point"
                   if model.record == "recording" else
                   "Looping — press to drop the loop" if model.record == "looping"
                   else "Record loop",
                   warn=model.record == "recording",
                   hold=model.record == "looping"),
            Button("clipper_save", _GLYPHS["save"], "Save clip"),
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
        # holding the place it holds over there, and the rest group behind it.
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
    ]


def _playback_speed_row(model: ConsoleModel, label_width: int = PLAYBACK_LABEL_W) -> list[Button]:
    """Nau's video playback rate: slower, the rate itself, faster.

    Named, because "Speed" already means the *stroke* rate down on the drive
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
        Button("genau_advance_down", _GLYPHS["minus"], "Move on sooner"),
        Button("", f"{model.advance_interval}s", "", width=VALUE_W),
        Button("genau_advance_up", _GLYPHS["plus"], "Leave each clip longer"),
    ]


def _control_row(model: ConsoleModel) -> list[Button]:
    """The hands-free stroke switch, the waveform and the offset — everything
    Genau does that is not a level on the readout."""
    return [
        Button("genau_toggle_cruise", "cc",
               "Cruise control: vary the stroke hands-free", lit=model.cruise),
        Button("genau_cycle_shape", WAVE_ICON, f"Waveform: {shape_label(model.shape)}"),
        Button("quarter_button", _GLYPHS["quarter"], "Offset the stroke a ¼ cycle"),
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


# Genau controls whose command name does not begin with genau_.
_GENAU_CONTROLS = frozenset({"quarter_button"})
# Recording a loop and saving what it caught: one job, two presses.
_CAPTURE_CONTROLS = frozenset({"nau_record_tap", "clipper_save"})
# The two switches: the lock holds what is on screen against moving on, F-mode
# narrows what there is to play at all.  Both are states the player sits *in*,
# where everything around them does its thing once and is over.  The lock also
# shares the transport's command prefix, so it has to be named here to leave
# that run.
_SWITCH_CONTROLS = frozenset({"main_lock", "main_fmode"})
# Reset stands alone between the switches and the browser: it shares the
# transport's command prefix but is not one of that run, and it is what turns
# the two switches back off, so it must not read as a third one.
_RESET_CONTROLS = frozenset({"main_reset"})
# The controls that act on the window rather than on anything inside it, so they
# stand apart from whatever they share a row with.  Named rather than left to the
# main_ prefix below: minimize sits beside the mode buttons and would otherwise
# read as a fourth mode.
_WINDOW_CONTROLS = frozenset({"main_minimize"})


def _family(action: str) -> str:
    """Which group of controls *action* belongs to."""
    # The three mode buttons are one group; genau_activate would otherwise fall
    # to the Genau controls' prefix below.
    if action.endswith("_activate"):
        return "mode"
    if action in _WINDOW_CONTROLS:
        return "window"
    if action in _GENAU_CONTROLS:
        return "genau_"
    if action in _CAPTURE_CONTROLS:
        return "capture"
    if action in _SWITCH_CONTROLS:
        return "switch"
    if action in _RESET_CONTROLS:
        return "reset"
    # Stepping the video and nudging inside it are one run of four marks, so they
    # are one family: prev, back ten, forward ten, next, evenly spaced.
    for prefix in ("main_", "nau_speed", "genau_"):
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
