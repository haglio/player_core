"""The main console painter: the top line, the controls, and the readout."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
from player_core.hud_panel import ICON_GRIDS, TEXT_MUTED, WHITE, load_font, text_width

from player_core.drive_readout import AMPLITUDE, CENTER, SPEED, DriveHud
from player_core.console import ConsoleModel
from player_core.console_hud import (
    ConsoleHud,
    ConsolePainter,
    ModeHud,
    compilation_label,
    hud_xy,
    with_playback_speed,
)
from player_core.console_hud import _DRIVE_TIPS, _PAD as PAD
from player_core.console_hud import FULL, SHORTS

MIXED = "mixed"


def _drive(offset: float = 0.0, **over) -> DriveHud:
    """A readout whose trace has scrolled *offset* along, the way Genau's does."""
    return DriveHud(speed=50, amplitude=80, center=50, shape="sine",
                    waveform=tuple(0.5 + 0.4 * np.sin(i / 6 + offset) for i in range(80)),
                    **over)


def _line(*, locked: bool = True, order_latest: bool = False, **modes) -> str:
    """The status line for a main player in *modes*, with that lock and order."""
    return ConsoleHud(modes=ModeHud(**modes),
                      console=ConsoleModel(mode="nau", locked=locked,
                                           latest=order_latest)).status_line


class TestLine:
    def test_says_whether_the_main_player_is_holding_the_video_on_screen(self):
        """Each satellite leads its line with this word, and the main player has the
        same lock — one padlock, for whichever player holds the slot."""
        assert _line(locked=True) == "Locked · Shuffle"
        assert _line(locked=False) == "Unlocked · Shuffle"

    def test_says_which_length_mode_the_library_is_in_and_says_it_last(self):
        """The length mode is what the satellites' act filter is — a narrowing of
        what may play — so it takes the same place, at the end of the line.

        "Mixed" is every length there is, so it narrows nothing and prints nothing,
        exactly as a satellite prints nothing where its filter would go when it has
        none.  It also no longer says enough to be worth the room: the library has
        grown a third kind of thing, and one word for "some of each" cannot say
        which.
        """
        assert _line(length_mode=MIXED) == "Locked · Shuffle"
        assert _line(length_mode=FULL) == "Locked · Shuffle · Full length"
        assert _line(length_mode=SHORTS) == "Locked · Shuffle · Shorts"

    def test_claims_no_length_mode_without_a_library_behind_the_playlist(self):
        """A playlist Fun Time drives has no length filter of its own to report, so
        that slot stays empty.  The lock is still said: it belongs to the main player
        slot whatever is feeding it."""
        assert _line(length_mode="") == "Locked · Shuffle"

    def test_a_genau_primary_says_its_order_and_the_pace_it_moves_at(self):
        """Genau has no library, no compilation and no filters.  What it has is the
        same lock every player has, the same two browse orders, and — while that
        lock is off — the seconds it leaves each clip up.  Order then pace, in the
        slot the satellites put theirs in: the order says which clip is next, the
        pace says when.  Held, there is no pace to report: the clip stays until
        something moves it."""
        def line(**over) -> str:
            return ConsoleHud(console=ConsoleModel(mode="genau", **over),
                              drive=_drive(advance_interval=5)).status_line

        assert line(locked=False) == "Unlocked · Shuffle · 5s"
        assert line(locked=True) == "Locked · Shuffle"

    def test_a_genau_primary_says_which_order_it_was_put_in(self):
        """Genau browses in the same two orders every other player does, and asking
        it for one used to leave the answer nowhere on screen: this slot printed the
        pace instead, so "latest" changed the clips and said nothing."""
        def line(**over) -> str:
            return ConsoleHud(console=ConsoleModel(mode="genau", **over),
                              drive=_drive(advance_interval=5)).status_line

        assert line(locked=False, latest=True) == "Unlocked · Latest · 5s"
        assert line(locked=True, latest=True) == "Locked · Latest"

    def test_the_pace_belongs_to_genau_and_is_not_claimed_while_nau_is_showing(self):
        """Hybrid draws the readout, so the pace is there to read — but Nau is on
        screen and an unlocked Nau plays through its playlist rather than moving on
        a timer, so saying seconds would describe the wrong player."""
        assert ConsoleHud(console=ConsoleModel(mode="hybrid", locked=False),
                          drive=_drive(advance_interval=5)).status_line == "Unlocked · Shuffle"

    def test_an_enhanced_only_host_says_so_in_the_filter_slot(self):
        """Origenerator narrows a show to the pictures it has enhanced, and that
        is the same kind of fact as Nau's length mode — what has been cut out of
        what is playing — so it takes the same slot, at the end of the line."""
        def line(**over) -> str:
            return ConsoleHud(console=ConsoleModel(mode="genau", **over),
                              drive=_drive(advance_interval=5)).status_line

        assert line(locked=True, enhanced_filter=False) == "Locked · Shuffle"
        assert line(locked=True, enhanced_filter=True) == "Locked · Shuffle · Enhanceds"
        assert line(locked=False, enhanced_filter=True) == (
            "Unlocked · Shuffle · 5s · Enhanceds")

    def test_a_genau_hosts_own_f_mode_says_so_in_the_same_word(self):
        """One switch, one word, whichever side turned it on: Fun Time publishes
        F-mode for the playlist it owns, and a genau host folds in its own."""
        def line(**over) -> str:
            return ConsoleHud(console=ConsoleModel(mode="genau", locked=True,
                                                   **over)).status_line

        assert line(favorites_filter=False) == "Locked · Shuffle"
        assert line(favorites_filter=True) == "Locked · Shuffle · F-Mode"
        assert line(favorites_filter=True, enhanced_filter=True) == (
            "Locked · Shuffle · F-Mode · Enhanceds")

    def test_a_host_with_no_such_filter_says_nothing_there(self):
        """None is "this player has no such filter" — not "it is off" — and both
        print nothing, so the slot is free for the length mode Nau fills."""
        assert ConsoleHud(console=ConsoleModel(mode="genau")).status_line == (
            "Locked · Shuffle")
        assert _line(length_mode=SHORTS) == "Locked · Shuffle · Shorts"

    def test_names_the_compilation_and_where_you_are_in_it(self):
        """A compilation is the main player's loop — a fixed set it plays through
        rather than the browse it came from — so it leads the line the way a
        satellite's loop does, and displaces "Unlocked" there for the same reason:
        a loop is repeat-all, and nothing is being held.  "Locked" still joins it,
        being a hold at one place inside the set.  The length mode stays on behind
        it, since ending the compilation drops you back into it."""
        def line(**over) -> str:
            return _line(compilation="Vol6", position=9, total=20, **over)

        assert line(locked=False) == "Vol6 · 9/20 · Shuffle"
        assert line(locked=True) == "Vol6 · 9/20 · Locked · Shuffle"
        assert line(locked=False, length_mode=SHORTS) == "Vol6 · 9/20 · Shuffle · Shorts"

    def test_says_which_browse_order_the_main_player_is_in(self):
        """The satellites have said Latest/Shuffle all along and the main player
        does now too, in the same slot — between the lock and the filters, since it
        is how the set advances rather than what is in it."""
        assert _line(order_latest=True) == "Locked · Latest"
        assert _line(order_latest=False) == "Locked · Shuffle"
        assert _line(order_latest=True, length_mode=SHORTS) == (
            "Locked · Latest · Shorts")

    def test_says_when_fun_time_has_narrowed_to_f_mode(self):
        """Between the lock and the length, where each satellite puts it: F-mode
        cuts the whole library to the funscripted videos and the length mode then
        narrows what is left, so the coarser filter is named first."""
        assert _line(f_mode=True) == "Locked · Shuffle · F-Mode"
        assert _line(length_mode=SHORTS, f_mode=True) == (
            "Locked · Shuffle · F-Mode · Shorts")


class TestCompilationLabel:
    def test_keeps_only_the_volume(self):
        assert compilation_label(
            "various - Ultimate Example Studio Alpha Collection - Volume 6 (v1)"
        ) == "Volume 6"

    def test_an_undashed_title_survives_whole(self):
        assert compilation_label("Scene Five 3") == "Scene Five 3"


class TestPainter:
    def test_a_tooltip_longer_than_the_panel_is_wide_stays_on_the_panel(self):
        """The lock button's tooltip wants 354px of box on a 238px console, so it
        used to be drawn straight off the right edge and lose its tail.  Fitting it
        is player_core's job — this guards that the console hands it the panel's own
        bounds, since passing anything wider puts the box back over the edge."""
        painter = ConsolePainter()
        hud = ConsoleHud(console=ConsoleModel(mode="nau", locked=False))
        plain = _rgb(painter.bgra(hud))  # also lays the buttons out, so one can be hovered
        tiny = load_font(8)
        (x, y, w, h), _button = max(
            ((rect, button) for rect, button in painter.buttons if button.tooltip),
            key=lambda pair: text_width(tiny, pair[1].tooltip))
        tipped = _rgb(ConsolePainter().bgra(hud, hover=(x + w // 2, y + h // 2)))

        def edge_ink(rgb) -> int:
            return int((rgb[:, -2:] > 200).all(axis=2).sum())

        assert not np.array_equal(plain, tipped)  # it drew something
        assert edge_ink(tipped) == edge_ink(plain) == 0

    def test_the_top_line_sits_tight_to_the_top(self):
        """The old console left a tall empty band above its first line; the status
        line now heads the console within a body line-height of the slab's top, the
        way each satellite's does."""
        painter = ConsolePainter()
        bgra = painter.bgra(ConsoleHud(modes=ModeHud(length_mode=FULL)))
        rgb = _rgb(bgra)

        # There is ink (the status text) within the first line-height below the pad.
        line_h = sum(load_font(11).getmetrics())
        band = rgb[PAD:PAD + line_h, :, :]
        assert (band > 200).any()

    def test_the_status_leads_and_the_file_name_is_the_muted_line_under_it(self):
        """The satellites lead with what they are showing, not with a file name, so
        the main player does too: the length mode or compilation in the body face, the
        file beneath it in the muted one."""
        painter = ConsolePainter()
        bgra = painter.bgra(ConsoleHud(modes=ModeHud(
            video="Some Video Name", length_mode=MIXED)))
        rgb = _rgb(bgra)

        body_h = sum(load_font(11).getmetrics())
        bright_rows = np.nonzero((rgb > 200).any(axis=(1, 2)))[0]
        muted = (rgb[:, :, 0] > 100) & (rgb[:, :, 0] < 160)
        muted_rows = np.nonzero(muted.any(axis=1))[0]

        assert bright_rows.min() < PAD + body_h          # the status is on top …
        assert muted_rows.max() > bright_rows.min()      # … the file name below it

    def test_a_longer_file_name_widens_the_panel(self):
        """It is drawn, not truncated, so the slab grows to hold it.

        Both names have to outrun the button row for this to be measuring the
        name at all: the panel is the widest of its parts, so a name shorter than
        the buttons is held by the buttons and every such name gives one width.
        """
        narrow = ConsolePainter().bgra(ConsoleHud(modes=ModeHud(
            video="A Much Much Longer Video Name Indeed")))
        wide = ConsolePainter().bgra(ConsoleHud(modes=ModeHud(
            video="A Much Much Longer Video Name Indeed, And Then Some More Of It")))

        assert wide.shape[1] > narrow.shape[1]

    def test_hybrid_grows_the_panel_for_the_readout(self):
        painter = ConsolePainter()
        plain = painter.bgra(ConsoleHud(console=ConsoleModel(mode="nau"))).shape[0]
        driving = ConsolePainter().bgra(
            ConsoleHud(console=ConsoleModel(mode="hybrid"), drive=_drive())).shape[0]

        assert driving > plain

    def test_the_dot_lights_only_while_the_main_has_the_floor(self):
        def dot(active: bool):
            bgra = ConsolePainter().bgra(
                ConsoleHud(console=ConsoleModel(mode="nau", active=active)))
            body = sum(load_font(11).getmetrics())
            cx, cy = PAD + 5, PAD + body // 2  # the dot's own centre
            return tuple(int(v) for v in _rgb(bgra)[cy, cx])

        assert np.allclose(dot(True), WHITE, atol=45)
        assert np.allclose(dot(False), TEXT_MUTED, atol=45)

    def test_the_dot_does_not_shift_the_words_around(self):
        """The dot is always in the same place and the same size — active only
        recolours it — so the line beside it cannot jump when the floor moves to
        another player."""
        painter = ConsolePainter()

        lit = painter.bgra(ConsoleHud(console=ConsoleModel(mode="nau", active=True)))
        idle = ConsolePainter().bgra(ConsoleHud(console=ConsoleModel(mode="nau", active=False)))

        assert lit.shape == idle.shape

    def test_an_unchanged_hud_is_not_repainted(self):
        painter = ConsolePainter()
        hud = ConsoleHud(console=ConsoleModel(mode="nau"))

        assert painter.bgra(hud) is painter.bgra(ConsoleHud(console=ConsoleModel(mode="nau")))

    def test_the_readouts_arrows_are_hit_targets_even_though_it_draws_them(self):
        """The readout paints its own amplitude/centre/speed arrows; the console
        adds them to its hit targets so a press on the trace's controls posts what
        is drawn there."""
        painter = ConsolePainter()
        painter.bgra(ConsoleHud(console=ConsoleModel(mode="hybrid"), drive=_drive()))

        actions = {b.action for _rect, b in painter.buttons}
        for action in ("genau_amplitude_up", "genau_center_down", "genau_speed_up"):
            assert action in actions

    def test_the_osr2_state_is_shown(self):
        """A boxed word, lower in the HUD — a read-out of what has the device, not
        a line jammed in with the mode."""
        painter = ConsolePainter()
        bgra = painter.bgra(ConsoleHud(
            console=ConsoleModel(mode="nau", osr2="funscript", broker=True)))
        rgb = _rgb(bgra)
        # FunScript is drawn green; there is green ink somewhere below the top line.
        green = (rgb[:, :, 1] > 130) & (rgb[:, :, 0] < 110) & (rgb[:, :, 2] < 110)
        assert green.any()

    def test_a_control_that_is_on_lights_the_active_ground_not_green(self):
        """Green means the favorites and the funscripts everywhere in this
        family — the OSR2 pill says FunScript in it, and that is the only thing on
        the console entitled to it.  The mode you are in is not one of them.

        Nor is it white, which is what this filled before: the family's ACTIVE
        ground is one step up from the resting one, the step Origenerator's
        checked buttons take, and the console taking a different one is what made
        it read as a different app from the windows beside it."""
        from shared_ui.colors import BG_BUTTON, BG_BUTTON_ACTIVE

        painter = ConsolePainter()
        rgb = _rgb(painter.bgra(ConsoleHud(console=ConsoleModel(mode="hybrid"))))
        (bx, by, bw, bh), _b = next(
            (rect, b) for rect, b in painter.buttons if b.action == "hybrid_activate")
        box = rgb[by:by + bh, bx:bx + bw].astype(int)

        shades, counts = np.unique(box.reshape(-1, 3), axis=0, return_counts=True)
        active = (BG_BUTTON_ACTIVE.red(), BG_BUTTON_ACTIVE.green(), BG_BUTTON_ACTIVE.blue())
        assert tuple(shades[counts.argmax()]) == active
        # And it is visibly a step up from a control at rest, or "on" says nothing.
        assert active != (BG_BUTTON.red(), BG_BUTTON.green(), BG_BUTTON.blue())
        green = (box[:, :, 1] > 130) & (box[:, :, 0] < 110) & (box[:, :, 2] < 110)
        assert not green.any()

    def test_a_control_at_rest_still_carries_the_familys_thin_edge(self):
        """The edge used to be the resting fill's own color, which is no edge at
        all — the satellite HUDs beside this one draw theirs in the muted gray the
        rest of the chrome uses, and the console read as borderless slabs."""
        from shared_ui.colors import TEXT_MUTED

        painter = ConsolePainter()
        rgb = _rgb(painter.bgra(ConsoleHud(console=ConsoleModel(mode="hybrid"))))
        (bx, by, bw, bh), _b = next(
            (rect, b) for rect, b in painter.buttons
            if b.action and b.action != "hybrid_activate")
        box = rgb[by:by + bh, bx:bx + bw].astype(int)
        muted = (TEXT_MUTED.red(), TEXT_MUTED.green(), TEXT_MUTED.blue())

        # Along the top edge, between the rounded corners.
        edge = box[0, 4:bw - 4]
        assert (abs(edge - np.array(muted)).max(axis=1) <= 2).any()

    def test_the_broker_wears_the_face_it_had_on_the_dashboard(self):
        """Its own pink mark on blue while the service is up and red while it is
        down — the broker acts on the room's own service rather than on a player,
        so it does not take the on/off colors the controls beside it use."""
        for broker, fill in ((True, (48, 128, 224)), (False, (255, 60, 60))):
            box = self._broker_box(broker)

            assert tuple(box[box.shape[0] // 2, 2]) == fill
            assert (box == np.array((200, 80, 160), dtype=box.dtype)).all(axis=2).any()

    def test_a_control_that_stands_for_an_app_wears_that_apps_mark(self):
        """`broker_icon.ico` and `fmode_icon.ico` are five-by-five letters, and one
        set in the body face is a thin thing beside them.  What has to hold is the
        shape: the grid the .ico carries, in its pink, whatever the button is
        doing underneath it."""
        for action, grid in (("broker_panel", ICON_GRIDS["B"]),
                             ("main_fmode", ICON_GRIDS["F"])):
            box = self._button_box(action, ConsoleModel(
                mode="nau", broker=True, f_mode=True))
            pink = (box == np.array((200, 80, 160), dtype=box.dtype)).all(axis=2)
            ys, xs = np.nonzero(pink)
            cell = (xs.max() - xs.min() + 1) / 5
            drawn = [
                "".join("#" if pink[int(ys.min() + (r + 0.5) * cell),
                                    int(xs.min() + (c + 0.5) * cell)] else "."
                        for c in range(5))
                for r in range(5)
            ]

            assert drawn == list(grid), action

    def test_the_typed_glyphs_all_come_out_of_the_face_that_has_them(self):
        """Segoe UI Bold carries none of these marks and Pillow draws a ".notdef"
        box for what a face lacks, so every glyph the console types has to be in
        the symbol face — the reset arrow, the newest of them, included."""
        from PIL import ImageFont

        from player_core.console import _GLYPHS
        from player_core.console_hud import SYMBOL_FONT

        glyph_font: ImageFont.FreeTypeFont = load_font(11, SYMBOL_FONT)
        notdef = glyph_font.getmask("").getbbox()

        for name, glyph in _GLYPHS.items():
            assert glyph_font.getmask(glyph).getbbox() != notdef, name

    def test_reset_is_a_thing_done_so_nothing_ever_lights_it(self):
        """The lock and F-mode fill their boxes while they are on; a reset is over
        the moment it lands, and it is what turns those two back off — a lit reset
        would read as a third state the player was sitting in."""
        for model in (ConsoleModel(mode="nau"),
                      ConsoleModel(mode="nau", locked=True, f_mode=True)):
            box = self._button_box("main_reset", model)
            filled = (box > 100).all(axis=2).sum()

            assert filled < box.shape[0] * box.shape[1] // 2

    def test_minimize_is_drawn_as_a_bar_rather_than_left_to_a_font(self):
        """Windows' minimize mark lives in Segoe MDL2 Assets, which this HUD does
        not load, and Pillow draws a ".notdef" box for what a face lacks.  So the
        painter draws it: a run of ink across the middle of the button, wider than
        it is tall, which is the mark every Windows title bar uses."""
        box = self._button_box("main_minimize", ConsoleModel(mode="nau"))
        # The button's own rounded outline is its border, so only the interior
        # holds the mark -- and the interior is the button's ground now, which is
        # itself gray, so the mark is what is BRIGHTER than that ground.
        inside = box[2:-2, 2:-2]
        ys, xs = np.nonzero((inside > 150).all(axis=2))

        assert len(ys), "the minimize button drew no mark at all"
        assert xs.max() - xs.min() > ys.max() - ys.min()

    @staticmethod
    def _button_box(action: str, model: ConsoleModel) -> np.ndarray:
        painter = ConsolePainter()
        rgb = _rgb(painter.bgra(ConsoleHud(console=model)))
        (bx, by, bw, bh), _b = next(
            (rect, b) for rect, b in painter.buttons if b.action == action)
        return rgb[by:by + bh, bx:bx + bw]

    def _broker_box(self, broker: bool) -> np.ndarray:
        return self._button_box("broker_panel", ConsoleModel(mode="nau", broker=broker))

    def test_f_mode_is_the_one_lit_control_that_stays_green(self):
        """It narrows the playlist to the videos that have a funscript, and green
        is what the funscripts and the favorites own."""
        box = self._button_box("main_fmode",
                               ConsoleModel(mode="nau", f_mode=True)).astype(int)

        shades, counts = np.unique(box.reshape(-1, 3), axis=0, return_counts=True)
        assert tuple(shades[counts.argmax()]) == (48, 160, 48)

    def test_the_enhanced_filter_wears_yellow_off_and_on(self):
        """An enhanced picture wears a yellow plus in its corner, so the switch
        that keeps only those is yellow wherever you find it: the mark at rest,
        and the whole button once it is on."""
        amber = (255, 200, 120)
        off = self._button_box("genau_filter_enhanced",
                               ConsoleModel(mode="genau", enhanced_filter=False))
        on = self._button_box("genau_filter_enhanced",
                              ConsoleModel(mode="genau", enhanced_filter=True))

        assert (np.abs(off.astype(int) - amber).sum(axis=2) < 30).any()  # the mark
        shades, counts = np.unique(on.astype(int).reshape(-1, 3), axis=0,
                                   return_counts=True)
        assert tuple(shades[counts.argmax()]) == amber                  # the fill

    def test_the_slab_is_the_canvas_grey_unless_a_host_asks_for_another(self):
        """Floating over a video the panel reads against the picture behind it,
        so it is the canvas colour. A host drawing it on its own chrome has no
        picture behind it — on a window painted that very grey the slab is
        invisible and only its border shows — so it says which grey it wants."""
        from player_core.hud_panel import BG_PRIMARY

        default = _rgb(ConsolePainter().bgra(
            ConsoleHud(console=ConsoleModel(mode="genau"))))
        asked = _rgb(ConsolePainter().bgra(
            ConsoleHud(console=ConsoleModel(mode="genau"), ground=(40, 40, 40))))

        # A pixel of bare slab: just inside the border, clear of every control.
        assert tuple(default[3, 3]) == BG_PRIMARY
        assert tuple(asked[3, 3]) != BG_PRIMARY
        assert asked[3, 3].min() > default[3, 3].min()

    def test_the_ground_is_part_of_what_the_repaint_cache_compares(self):
        """Everything else on this panel is; a ground that slipped past it would
        leave the old slab on screen until something else moved."""
        painter = ConsolePainter()
        first = _rgb(painter.bgra(ConsoleHud(console=ConsoleModel(mode="genau"))))[3, 3]
        second = _rgb(painter.bgra(ConsoleHud(console=ConsoleModel(mode="genau"),
                                              ground=(40, 40, 40))))[3, 3]

        assert tuple(first) != tuple(second)

    def test_a_lit_marks_ink_stays_white_over_a_colored_fill(self):
        """The Dash's mic keeps its white glyph while the panel under it goes
        blue.  A record button whose circle went dark while it recorded read as a
        different button rather than as the same one recording."""
        painter = ConsolePainter()
        rgb = _rgb(painter.bgra(
            ConsoleHud(console=ConsoleModel(mode="nau", record="recording"))))
        (bx, by, bw, bh), _b = next(
            (rect, b) for rect, b in painter.buttons if b.action == "nau_record_tap")
        box = rgb[by:by + bh, bx:bx + bw].astype(int)

        assert tuple(box[bh // 2, 2]) == (255, 60, 60)   # the fill went red …
        assert (box > 240).all(axis=2).any()             # … and the circle did not


class TestPresses:
    @staticmethod
    def _painted(mode: str = "nau") -> ConsolePainter:
        painter = ConsolePainter()
        painter.bgra(ConsoleHud(console=ConsoleModel(mode=mode)))
        return painter

    @staticmethod
    def _over(painter: ConsolePainter, action: str) -> tuple[int, int]:
        (bx, by, bw, bh), _b = next(
            (rect, b) for rect, b in painter.buttons if b.action == action)
        left, top = hud_xy()
        return left + bx + bw // 2, top + by + bh // 2

    def test_a_press_on_a_button_carries_that_buttons_command(self):
        painter = self._painted()

        assert painter.press_at(*self._over(painter, "main_next")) == "main_next"

    def test_a_press_that_missed_every_button_carries_nothing(self):
        assert self._painted().press_at(2000, 2000) == ""

    def test_the_panels_own_corner_is_not_read_as_the_windows(self):
        painter = self._painted()
        (bx, by, _bw, _bh), _b = next(
            (rect, b) for rect, b in painter.buttons if b.action == "main_prev")

        assert painter.press_at(bx, by) == ""

    def test_a_readouts_arrow_press_reaches_genau(self):
        painter = ConsolePainter()
        painter.bgra(ConsoleHud(
            console=ConsoleModel(mode="hybrid", osr2="genau"), drive=_drive()))

        assert painter.press_at(*self._over(painter, "genau_amplitude_up")) == "genau_amplitude_up"

    def test_the_readouts_controls_are_dead_while_a_funscript_has_the_device(self):
        """Genau is paused through a funscript's stretch, so a stroke it is not
        sending cannot be adjusted — pressing one woke Genau onto a device the
        funscript was already driving, and the two fought over it."""
        painter = ConsolePainter()
        painter.bgra(ConsoleHud(
            console=ConsoleModel(mode="hybrid", osr2="funscript"), drive=_drive()))

        over = self._over(painter, "genau_amplitude_up")
        assert painter.press_at(*over) == ""
        assert all(b.dim for _rect, b in painter.buttons if b.action.startswith("genau_amplitude"))

    def test_the_cursor_over_a_button_is_reported_in_panel_coordinates(self):
        painter = self._painted()
        mx, my = self._over(painter, "main_next")
        left, top = hud_xy()

        assert painter.hover_at(mx, my) == (mx - left, my - top)


class TestDrags:
    """The readout's bars are set by pressing in them and dragging along them, so
    a level is reached in one gesture rather than by walking a mark to it."""

    @staticmethod
    def _painted(osr2: str = "genau") -> ConsolePainter:
        painter = ConsolePainter()
        painter.bgra(ConsoleHud(
            console=ConsoleModel(mode="hybrid", osr2=osr2), drive=_drive()))
        return painter

    @staticmethod
    def _band(painter: ConsolePainter, axis: str):
        return next(track for track in painter.tracks if track.axis == axis)

    @staticmethod
    def _at(track, along: float) -> tuple[int, int]:
        """A window point that fraction of the way up (or along) *track*.

        Only speed runs left to right; the trace and the amplitude bar are both
        read as heights, the trace despite being the wider of the two.
        """
        x, y, w, h = track.rect
        left, top = hud_xy()
        if track.axis == SPEED:
            return left + x + round(along * (w - 1)), top + y + h // 2
        return left + x + w // 2, top + y + round((1 - along) * (h - 1))

    def test_a_press_along_the_speed_bar_sets_the_speed(self):
        painter = self._painted()

        point = self._at(self._band(painter, SPEED), 1.0)
        assert painter.press_at(*point) == "genau_speed_100"

    def test_a_press_in_the_trace_moves_the_stroke_s_center(self):
        painter = self._painted()

        point = self._at(self._band(painter, CENTER), 1.0)
        assert painter.press_at(*point) == "genau_center_100"

    def test_a_press_up_the_amplitude_bar_sets_how_far_the_stroke_reaches(self):
        painter = self._painted()

        point = self._at(self._band(painter, AMPLITUDE), 1.0)
        assert painter.press_at(*point) == "genau_amp_100"

    def test_the_bar_a_press_took_hold_of_keeps_the_drag(self):
        """A press latches its bar, so a drag that wanders off it — past its end,
        or out over another one — goes on setting the level it started on."""
        painter = self._painted()
        speed = self._band(painter, SPEED)
        painter.press_at(*self._at(speed, 1.0))

        assert painter.holding is True
        left, _top = hud_xy()
        assert painter.drag_to(left + speed.rect[0] - 500, 0) == "genau_speed_0"
        assert painter.drag_to(*self._at(speed, 1.0)) == "genau_speed_100"

    def test_a_drag_says_nothing_while_the_level_under_it_has_not_moved(self):
        """Every mouse motion fires, and each one that repeats the level is a line
        in the command file for Fun Time to route to where Genau already is."""
        painter = self._painted()
        speed = self._band(painter, SPEED)
        painter.press_at(*self._at(speed, 1.0))

        assert painter.drag_to(*self._at(speed, 1.0)) == ""

    def test_letting_go_ends_the_drag(self):
        painter = self._painted()
        painter.press_at(*self._at(self._band(painter, SPEED), 0.0))

        painter.release()

        assert painter.holding is False
        assert painter.drag_to(*self._at(self._band(painter, SPEED), 1.0)) == ""

    def test_a_press_on_a_button_leaves_no_bar_latched_behind_it(self):
        """Otherwise the bar a previous press held would keep taking the pointer
        long after the gesture that grabbed it was over."""
        painter = self._painted()
        painter.press_at(*self._at(self._band(painter, SPEED), 0.0))
        (bx, by, bw, bh), _b = next(
            (rect, b) for rect, b in painter.buttons if b.action == "main_next")
        left, top = hud_xy()

        painter.press_at(left + bx + bw // 2, top + by + bh // 2)

        assert painter.holding is False

    def test_the_bars_are_dead_while_a_funscript_has_the_device(self):
        """The whole readout is dimmed through a funscript's stretch — a stroke
        Genau is not sending cannot be dragged any more than it can be stepped."""
        painter = self._painted(osr2="funscript")

        point = self._at(self._band(painter, SPEED), 1.0)
        assert painter.press_at(*point) == ""
        assert painter.holding is False

    def test_there_are_no_bars_at_all_where_nothing_is_driving(self):
        """In nau mode the readout is not drawn, so its bands must not linger as
        targets over whatever the console puts in that space instead."""
        painter = ConsolePainter()
        painter.bgra(ConsoleHud(console=ConsoleModel(mode="nau")))

        assert painter.tracks == []

    def test_each_bar_names_what_it_sets_on_hover(self):
        """Nothing else on a HUD drawn into the video says a bar can be dragged."""
        painter = self._painted()
        left, top = hud_xy()

        for axis in (SPEED, CENTER, AMPLITUDE):
            x, y, w, h = self._band(painter, axis).rect
            assert painter.hover_at(left + x + w // 2, top + y + h // 2) is not None


class TestPlaybackSpeed:
    def test_the_drawing_player_folds_in_its_own_rate(self):
        """Fun Time does not publish Nau's video rate — Nau knows it and adds it
        at draw time, so the console shows the rate the video is really playing."""
        console = with_playback_speed(ConsoleModel(mode="nau"), 1.75)

        assert console.playback_speed == 1.75


class TestPlacement:
    def test_the_panel_sits_in_the_top_left_corner(self):
        assert hud_xy() == (8, 8)


def _rgb(bgra: np.ndarray) -> np.ndarray:
    return bgra[:, :, [2, 1, 0]]


class TestTraceSources:
    """The trace is on the console in every mode, because in every mode something
    may be driving the device — and what it is a picture of is whoever that is."""

    @staticmethod
    def _painted(mode: str, osr2: str, drive: DriveHud | None = None) -> ConsolePainter:
        painter = ConsolePainter()
        painter.bgra(ConsoleHud(
            console=ConsoleModel(mode=mode, osr2=osr2), drive=drive or _drive()))
        return painter

    def test_genau_driving_leaves_the_readout_pressable(self):
        painter = self._painted("hybrid", "genau")

        assert [t.dim for t in painter.tracks] == [False, False, False]

    def test_a_funscript_driving_dims_every_control_but_keeps_the_trace(self):
        """A stroke Genau is not sending cannot be adjusted; the picture of the
        one that *is* being sent is still worth drawing."""
        painter = self._painted("hybrid", "funscript")

        assert all(t.dim for t in painter.tracks)
        assert painter.tracks

    def test_the_panel_keeps_its_size_whoever_has_the_device(self):
        """The controls dim for a funscript's turn rather than leave: removing
        them resized the panel, so the trace shifted at every handoff and the
        position marker jumped with it."""
        genau_turn = self._painted("hybrid", "genau")
        funscript_turn = self._painted("hybrid", "funscript")

        assert genau_turn._image.size == funscript_turn._image.size

    def test_nau_shows_the_trace_alone(self):
        """No Genau behind that screen: its amplitude, centre and speed describe a
        stroke nothing is making, and no control on them could reach one."""
        painter = self._painted("nau", "funscript")

        assert painter.tracks == []
        # The readout's own marks, not the mode row's Genau button beside them.
        assert not [b for _rect, b in painter.buttons
                    if b.action in _DRIVE_TIPS]

    def test_a_trace_only_readout_costs_the_panel_less_room(self):
        tall = self._painted("hybrid", "genau")
        short = self._painted("nau", "funscript")

        assert short._image.size[1] < tall._image.size[1]


class TestEveryConsolePaints:
    """One paint per (mode x driver) with a composed trace on the panel.

    The pill's Buffer state shipped referencing a name this module never
    imported, and no test painted a hybrid console with a composed drive — so
    every suite was green while the real Nau crashed on its first console
    frame and the session came up with no main player at all.  A paint smoke
    over the whole grid makes that class of crash impossible to ship quietly.
    """

    def test_every_mode_and_driver_combination_paints(self):
        wave = tuple(0.5 for _ in range(len(DriveHud().waveform) or 80))
        segments = ((0, "genau"), (30, "neutral"), (50, "funscript"))
        for mode in ("nau", "hybrid", "genau"):
            for driven in ("genau", "funscript", "neutral", "nothing"):
                hud = ConsoleHud(
                    modes=ModeHud(video="clip one"),
                    console=ConsoleModel(mode=mode, osr2="genau"),
                    drive=DriveHud(waveform=wave, driven=driven,
                                   segments=segments))
                ConsolePainter().rgba(hud)

    def test_the_buffer_pill_is_wider_than_nothing(self):
        """The Buffer word really reaches the pill: its width is computed from
        the same state the paint will draw."""
        wave = tuple(0.5 for _ in range(80))
        painter = ConsolePainter()
        hud = ConsoleHud(
            modes=ModeHud(video="clip one"),
            console=ConsoleModel(mode="hybrid", osr2="genau"),
            drive=DriveHud(waveform=wave, driven="neutral",
                           segments=((0, "genau"), (30, "neutral"))))
        painter.rgba(hud)

        assert painter._osr2_state(hud.console) == "buffer"


class TestNothingDriving:
    """With the OSR2 off there is nothing being sent, so there is no motion to
    trace — and a trace scrolling on in the middle of a readout whose every
    control is dead is the one part still claiming to be live.

    Genau's own mode, where the readout is a picture of one waveform and
    nothing else.  Hybrid is the exception, below: there the readout is a
    picture of a handoff, and the gaps are part of what it draws.
    """

    @staticmethod
    def _scroll(painter: ConsolePainter, offset: float) -> None:
        painter.bgra(ConsoleHud(
            console=ConsoleModel(mode="genau", osr2="off"),
            drive=_drive(offset)))

    def test_the_trace_stops_where_it_was_when_the_device_went_quiet(self):
        painter = ConsolePainter()
        self._scroll(painter, 0.0)
        first = painter.bgra(ConsoleHud(
            console=ConsoleModel(mode="genau", osr2="off"), drive=_drive(0.0))).copy()

        self._scroll(painter, 3.0)

        assert np.array_equal(painter.bgra(ConsoleHud(
            console=ConsoleModel(mode="genau", osr2="off"),
            drive=_drive(3.0))), first)

    def test_it_moves_again_the_moment_something_is_driving(self):
        painter = ConsolePainter()
        self._scroll(painter, 0.0)
        still = painter.bgra(ConsoleHud(
            console=ConsoleModel(mode="genau", osr2="off"), drive=_drive(0.0))).copy()

        moving = painter.bgra(ConsoleHud(
            console=ConsoleModel(mode="genau", osr2="genau"), drive=_drive(3.0)))

        assert not np.array_equal(moving, still)


class TestTheHandoffKeepsMoving:
    """In hybrid the readout draws the device changing hands, and between the
    two drivers is a gap where nothing is being sent at all — the OSR2 stops
    answering on the wire and reads "off" for a moment.  Held still there, the
    whole trace froze into one flat grey at every handoff and came back only
    once something was driving again, which is what he kept watching happen as
    the funscript's turn came up."""

    def test_the_trace_goes_on_sliding_through_the_gap(self):
        painter = ConsolePainter()
        first = painter.bgra(ConsoleHud(
            console=ConsoleModel(mode="hybrid", osr2="off"), drive=_drive(0.0))).copy()

        later = painter.bgra(ConsoleHud(
            console=ConsoleModel(mode="hybrid", osr2="off"), drive=_drive(3.0)))

        assert not np.array_equal(later, first)

    def test_the_line_keeps_the_colors_the_model_gave_it(self):
        """Blanked segments fall back to one flat colour for the whole line —
        the grey he saw.  The model says where the device changes hands, and
        that has to survive the gap."""
        painter = ConsolePainter()
        hud = ConsoleHud(
            console=ConsoleModel(mode="hybrid", osr2="off"),
            drive=replace(_drive(0.0), segments=((0, "genau"), (40, "neutral"))))

        assert painter._resolve(hud).drive.segments == ((0, "genau"), (40, "neutral"))
