"""The main console: the controls whichever player holds the slot draws."""
from __future__ import annotations

from pathlib import Path

from player_core.console import (
    BROKER_ICON,
    BUTTON,
    GAP,
    GROUP_GAP,
    MINIMIZE_ICON,
    ConsoleModel,
    ModeHud,
    console_rows,
    hit_test,
    main_player_displays,
    osr2_row,
    place_rows,
    read_console,
    shape_label,
    tooltip_at,
)


def _actions(model: ConsoleModel) -> list[str]:
    return [b.action for row in console_rows(model) for b in row if b.action]


def _button(model: ConsoleModel, action: str):
    return next(b for row in console_rows(model) for b in row if b.action == action)


def _osr2_button(model: ConsoleModel, action: str):
    return next(b for b in osr2_row(model) if b.action == action)


class TestShapeLabel:
    """The control that cycles the waveform names it on hover, so the name lives
    with the console rather than with the readout that no longer prints it."""

    def test_names_the_waveform_instead_of_leaving_it_to_the_curve(self):
        assert shape_label("sine") == "Sine"
        assert shape_label("rounded_square") == "Square"
        assert shape_label("sawtooth") == "Sawtooth"

    def test_an_unknown_shape_is_titled_rather_than_dropped(self):
        assert shape_label("half_moon") == "Half Moon"


class TestOsr2Row:
    """The device's own control: the broker that talks to the OSR2 at all."""

    def test_the_broker_is_a_control_and_says_which_way_a_press_goes(self):
        running = _osr2_button(ConsoleModel(broker=True), "broker_panel")
        down = _osr2_button(ConsoleModel(broker=False), "broker_panel")

        assert running.lit is True and "stop" in running.tooltip
        assert down.warn is True and "start" in down.tooltip

    def test_the_broker_is_the_only_control_on_that_line(self):
        """The takeover switch shared it until its one trigger — the OSR2's own
        free mode — turned out to be unreachable from here."""
        assert [b.action for b in osr2_row(ConsoleModel())] == ["broker_panel"]

    def test_the_broker_asks_for_its_own_icon_rather_than_the_word(self):
        """It is the room's own service, not one of the players' controls, and it
        had a mark of its own on the dashboard: the painter draws that rather than
        giving it the on/off colors everything else here takes."""
        broker = _osr2_button(ConsoleModel(), "broker_panel")

        assert broker.glyph == BROKER_ICON
        assert broker.width == BUTTON


class TestTransport:
    """Prev/next step the main player's video where the main player is on screen, Genau's clips where it
    is — with the actions that only make sense for each."""

    def test_video_mode_steps_the_video_and_acts_on_it(self):
        actions = _actions(ConsoleModel(mode="video"))
        for action in ("main_prev", "main_next", "main_nudge_prev",
                       "main_nudge_next", "main_fmode", "browse_library",
                       "clipper_save", "main_player_record_tap"):
            assert action in actions, action

    def test_f_mode_is_the_main_players_own_and_lights_while_it_is_on(self):
        """Fun Time's dashboard carried one F-mode switch for the room; every
        player carries its own now, and this is the main player's — its playlist
        narrowed to the videos that have a funscript."""
        off = _button(ConsoleModel(mode="video"), "main_fmode")
        on = _button(ConsoleModel(mode="video", f_mode=True), "main_fmode")

        assert off.lit is False
        assert on.lit is True

    def test_f_mode_is_not_offered_where_there_is_no_main_player_playlist(self):
        """In genau mode the main slot is Genau's, and the playlist F-mode
        narrows is not what is playing — the same reason nudge and record go."""
        assert "main_fmode" not in _actions(ConsoleModel(mode="genau"))

    def test_genau_steps_its_own_clips_and_can_mark_one_weird(self):
        actions = _actions(ConsoleModel(mode="genau"))

        assert "genau_prev_clip" in actions
        assert "genau_next_clip" in actions
        assert "genau_weird_clip" in actions  # the mark-weird the readout lacked

    def test_genau_offers_no_video_only_actions(self):
        """Nudge, open, clip and record act on a video; Genau's clips are not one."""
        actions = _actions(ConsoleModel(mode="genau"))

        for action in ("main_nudge_prev", "browse_library", "clipper_save",
                       "main_player_record_tap", "main_fmode"):
            assert action not in actions


class TestFavoritesFilter:
    """The other narrowing switch a genau-mode host can have: its favorites."""

    def test_no_button_where_the_host_has_no_such_filter(self):
        """Genau's own clips are not a set anybody has bookmarked, and F-mode in
        the main player branch is Fun Time's own — this is the genau branch's, and it
        appears only where a host folded one in."""
        assert "main_fmode" not in _actions(ConsoleModel(mode="genau"))

    def test_the_button_appears_once_a_host_says_it_has_one(self):
        assert "main_fmode" in _actions(
            ConsoleModel(mode="genau", favorites_filter=False))

    def test_it_lights_while_the_filter_is_on(self):
        off = _button(ConsoleModel(mode="genau", favorites_filter=False), "main_fmode")
        on = _button(ConsoleModel(mode="genau", favorites_filter=True), "main_fmode")

        assert (off.lit, on.lit) == (False, True)
        assert on.favorite is True   # green: the favorites own it across the family

    def test_it_leads_the_switches_where_it_leads_them_in_the_other_branch(self):
        """F holds one place on this console whichever branch drew it, and the
        rest of the narrowing switches group after it."""
        row = next(row for row in console_rows(
            ConsoleModel(mode="genau", favorites_filter=False, enhanced_filter=False))
            if any(b.action == "main_fmode" for b in row))
        actions = [b.action for b in row if b.action]

        assert actions.index("main_fmode") == actions.index("main_lock") + 1
        assert actions.index("genau_filter_enhanced") == actions.index("main_fmode") + 1

    def test_the_main_player_branchs_f_mode_is_untouched_by_it(self):
        """Fun Time publishes that one for a playlist it owns; this field is the
        genau branch's and must not reach across."""
        assert "main_fmode" in _actions(ConsoleModel(mode="video"))
        assert _button(ConsoleModel(mode="video", f_mode=True), "main_fmode").lit is True


class TestEnhancedFilter:
    """Origenerator's own narrowing switch: keep only the pictures it enhanced."""

    def test_no_button_where_the_host_has_no_such_filter(self):
        """An enhancement is a thing Origenerator makes, so no other player here
        has a set to narrow — and a dead button nobody can explain is worse than
        no button.  Genau's own console is the one this would otherwise grow."""
        assert "genau_filter_enhanced" not in _actions(ConsoleModel(mode="genau"))
        assert "genau_filter_enhanced" not in _actions(ConsoleModel(mode="video"))

    def test_the_button_appears_once_a_host_says_it_has_one(self):
        assert "genau_filter_enhanced" in _actions(
            ConsoleModel(mode="genau", enhanced_filter=False))

    def test_it_lights_while_the_filter_is_on(self):
        off = _button(ConsoleModel(mode="genau", enhanced_filter=False),
                      "genau_filter_enhanced")
        on = _button(ConsoleModel(mode="genau", enhanced_filter=True),
                     "genau_filter_enhanced")

        assert (off.lit, on.lit) == (False, True)

    def test_it_says_which_way_the_press_goes(self):
        """A toggle whose tooltip reads the same either way makes you press it to
        find out what it was — which is the one thing a filter must not do."""
        off = _button(ConsoleModel(mode="genau", enhanced_filter=False),
                      "genau_filter_enhanced")
        on = _button(ConsoleModel(mode="genau", enhanced_filter=True),
                     "genau_filter_enhanced")

        assert "Show only" in off.tooltip
        assert "press for all of them" in on.tooltip

    def test_it_keeps_the_yellow_an_enhancement_is_marked_with(self):
        """Green is spoken for by the funscripts and the favorites; an enhanced
        picture wears yellow, so the switch that keeps only those does too."""
        button = _button(ConsoleModel(mode="genau", enhanced_filter=True),
                         "genau_filter_enhanced")

        assert button.enhanced is True
        assert button.favorite is False

    def test_it_sits_with_the_switches_after_the_lock(self):
        """The narrowing switches ride straight after the padlock, as they do in
        the other branch: all of them say what there is to step through rather
        than acting on what is on screen. Alone, with no favorites filter
        beside it, it takes that first place itself."""
        row = next(row for row in console_rows(
            ConsoleModel(mode="genau", enhanced_filter=False))
            if any(b.action == "genau_filter_enhanced" for b in row))
        actions = [b.action for b in row if b.action]

        assert actions.index("genau_filter_enhanced") == actions.index("main_lock") + 1

    def test_a_published_panel_leaves_it_alone(self, tmp_path: Path):
        """The host owns this filter the way it owns the pace, so a console panel
        read off Fun Time's file must leave it unset rather than answer False —
        which would draw the button, unlit, on every player in the room."""
        import json
        path = tmp_path / "main_player_console.json"
        path.write_text(json.dumps({"mode": "genau"}), encoding="utf-8")

        assert read_console(path).enhanced_filter is None
        assert read_console(path).favorites_filter is None
        assert ConsoleModel().enhanced_filter is None
        assert ConsoleModel().favorites_filter is None


class TestReset:
    """The way back out: drop everything narrowing what the main player plays."""

    def test_the_main_player_can_be_reset_wherever_main_player_is_on_screen(self):
        """Each satellite's HUD carries this button; the main player's console had
        no way to say "put it back" at all, so the length mode and F-mode could
        only be lifted one at a time and only by name."""
        assert "main_reset" in _actions(ConsoleModel(mode="video"))

    def test_it_is_not_offered_where_there_is_no_main_player_playlist(self):
        """In genau mode neither of the things it drops is narrowing what is on
        screen — the same reason F-mode itself is not offered there."""
        assert "main_reset" not in _actions(ConsoleModel(mode="genau"))

    def test_it_is_a_thing_done_rather_than_a_state_held(self):
        """Nothing lights it: the lock and F-mode are conditions the player sits
        in, and a reset is over the moment it lands."""
        for f_mode in (False, True):
            button = _button(ConsoleModel(mode="video", f_mode=f_mode), "main_reset")
            assert button.lit is False
            assert button.favorite is False

    def test_it_stands_clear_of_the_switches_it_turns_off(self):
        """It shares the transport's command prefix and would otherwise rejoin
        that run and read as another step through the video — and it must not read
        as a third switch either, since it is what takes the other two back off."""
        placed = place_rows(console_rows(ConsoleModel(mode="video")), x=0, y=0)
        by_action = {b.action: rect for rect, b in placed}
        fmode, reset = by_action["main_fmode"], by_action["main_reset"]

        assert reset[0] - (fmode[0] + fmode[2]) == GROUP_GAP


class TestBrowseOrder:
    """Shuffle and Latest: which way round what plays was put in order."""

    def test_both_players_can_be_reordered_from_the_console(self):
        """The order was a spoken command and a status word with no control at
        all.  It is one question in both modes — video reorders the playlist Fun
        Time built for the main player, genau tells Genau to rescan the other way round."""
        for mode in ("video", "genau"):
            actions = _actions(ConsoleModel(mode=mode, latest=False))
            assert "main_shuffle" in actions and "main_latest" in actions

    def test_exactly_one_of_the_pair_is_lit(self):
        """Neither is ever off — the player is in one order or the other — so the
        light says which one you are in rather than "this is engaged"."""
        shuffled = ConsoleModel(mode="video", latest=False)
        newest = ConsoleModel(mode="video", latest=True)

        assert _button(shuffled, "main_shuffle").lit is True
        assert _button(shuffled, "main_latest").lit is False
        assert _button(newest, "main_shuffle").lit is False
        assert _button(newest, "main_latest").lit is True

    def test_neither_of_the_pair_wears_a_color_of_its_own(self):
        """A lit control fills the family's blue, and these are lit controls —
        neither of them is the favorites' green or an enhanced picture's amber."""
        for action in ("main_shuffle", "main_latest"):
            button = _button(ConsoleModel(mode="video", latest=False), action)
            assert button.favorite is False and button.enhanced is False

    def test_the_pair_is_its_own_group_after_the_reset(self):
        """The two are one control asked twice, so they sit together — and apart
        from reset, which is what puts the order back rather than a third way of
        setting it."""
        placed = place_rows(console_rows(ConsoleModel(mode="video", latest=False)),
                            x=0, y=0)
        by_action = {b.action: rect for rect, b in placed}
        reset = by_action["main_reset"]
        shuffle, latest = by_action["main_shuffle"], by_action["main_latest"]

        assert shuffle[0] - (reset[0] + reset[2]) == GROUP_GAP
        assert latest[0] - (shuffle[0] + shuffle[2]) == GAP

    def test_a_host_with_no_browse_order_is_offered_neither(self):
        """Origenerator's motion panel draws this console over a show's own set,
        which is not a browse at all — two buttons nothing there answers would be
        two dead buttons."""
        actions = _actions(ConsoleModel(mode="genau"))

        assert "main_shuffle" not in actions and "main_latest" not in actions
        assert ConsoleModel().latest is None

    def test_a_published_panel_says_which_order_it_is_in(self, tmp_path: Path):
        """Fun Time publishes the flag every tick, so its own consoles always draw
        the pair; a file that says nothing about it is not one of them."""
        import json
        path = tmp_path / "main_player_console.json"
        path.write_text(json.dumps({"mode": "video", "latest": True}), encoding="utf-8")
        assert read_console(path).latest is True

        path.write_text(json.dumps({"mode": "video"}), encoding="utf-8")
        assert read_console(path).latest is None


class TestProjectionPair:
    """VR and flat, as the two shapes of video each button includes."""

    def _pair(self, plays_vr, plays_flat, **over):
        rows = console_rows(
            ConsoleModel(mode="video", latest=False,
                         plays_vr=plays_vr, plays_flat=plays_flat),
            main_player=ModeHud(length_mode="mixed", **over))
        return [b for row in rows for b in row
                if b.action.startswith("main_projection")]

    def test_both_shapes_is_both_of_them_lit(self):
        assert [b.lit for b in self._pair(True, True)] == [True, True]

    def test_dropping_one_from_both_asks_for_the_other_alone(self):
        assert [b.action for b in self._pair(True, True)] == [
            "main_projection_flat", "main_projection_vr"]

    def test_putting_the_dark_one_back_asks_for_both(self):
        pair = self._pair(True, False)

        assert [b.lit for b in pair] == [True, False]
        assert pair[1].action == "main_projection_both"

    def test_the_last_lit_one_can_still_be_turned_off(self):
        """Neither shape is a browse with nothing in it -- degenerate, but a real
        answer, and unlike the lengths nothing here refuses the press."""
        pair = self._pair(False, True)

        assert [b.dim for b in pair] == [False, False]
        assert pair[1].action == "main_projection_none"

    def test_neither_lit_offers_each_shape_back(self):
        assert [b.action for b in self._pair(False, False)] == [
            "main_projection_vr", "main_projection_flat"]

    def test_no_pair_at_all_where_the_library_holds_one_shape(self):
        """Every session outside the headset: the VR masters are not in its
        library, so a filter over them would be two dead buttons."""
        assert self._pair(None, None) == []
        assert ConsoleModel().plays_vr is None

    def test_inside_a_compilation_the_shapes_read_as_held(self):
        pair = self._pair(True, True, compilation="Volume 6")

        assert all(b.remembered and not b.lit for b in pair)

    def test_a_published_panel_says_which_shapes_it_is_playing(self, tmp_path: Path):
        import json
        path = tmp_path / "main_player_console.json"
        path.write_text(json.dumps({"mode": "video", "plays_vr": True,
                                    "plays_flat": False}), encoding="utf-8")
        panel = read_console(path)
        assert (panel.plays_vr, panel.plays_flat) == (True, False)

        path.write_text(json.dumps({"mode": "video"}), encoding="utf-8")
        assert read_console(path).plays_vr is None


class TestLengthPair:
    """Full length and shorts, as the two lengths each button includes."""

    def _pair(self, length_mode: str, **over):
        rows = console_rows(ConsoleModel(mode="video", latest=False),
                            main_player=ModeHud(length_mode=length_mode, **over))
        buttons = {b.action: b for row in rows for b in row if b.action}
        by_icon = [b for row in rows for b in row
                   if b.action.startswith("main_player_length")]
        return by_icon, buttons

    def test_mixed_is_both_of_them_lit(self):
        """Every length there is, which is what Mixed means — and why it needs no
        button of its own."""
        pair, _ = self._pair("mixed")

        assert [b.lit for b in pair] == [True, True]

    def test_one_length_is_that_one_lit_and_the_other_dark(self):
        full, _ = self._pair("full")
        shorts, _ = self._pair("shorts")

        assert [b.lit for b in full] == [True, False]
        assert [b.lit for b in shorts] == [False, True]

    def test_dropping_one_from_mixed_asks_for_the_other_alone(self):
        pair, _ = self._pair("mixed")

        assert [b.action for b in pair] == ["main_player_length_shorts", "main_player_length_full"]

    def test_putting_the_dark_one_back_asks_for_mixed(self):
        pair, _ = self._pair("full")

        assert pair[1].action == "main_player_length_mixed"

    def test_the_last_lit_one_can_still_be_turned_off(self):
        """Neither length is a browse with nothing in it -- degenerate, but a
        real answer, and the same one the shapes pair beside it allows.  Refusing
        it is what left a lit button wearing a gray mark for an unsayable reason."""
        pair, _ = self._pair("full")

        assert [b.dim for b in pair] == [False, False]
        assert pair[0].action == "main_player_length_none"

    def test_neither_lit_offers_each_length_back(self):
        pair, _ = self._pair("none")

        assert [b.lit for b in pair] == [False, False]
        assert [b.action for b in pair] == ["main_player_length_full", "main_player_length_shorts"]

    def test_no_pair_at_all_without_a_library_to_filter(self):
        _pair, buttons = self._pair("")

        assert not [a for a in buttons if a.startswith("main_player_length")]


class TestCompilationAndJumps:
    """The set a video belongs to, the scene it came from, and its other cuts."""

    def _button_for(self, action: str, **over):
        rows = console_rows(ConsoleModel(mode="video", latest=False),
                            main_player=ModeHud(length_mode="mixed", **over))
        return next(b for row in rows for b in row if b.action == action)

    def test_the_compilation_button_enters_and_the_lit_one_leaves(self):
        """One button for both halves: there is no second control for "end", and
        the light is what says which of the two a press will do."""
        outside = self._button_for("main_player_compilation", has_compilation=True)
        inside = self._button_for("main_player_end_compilation", compilation="Volume 6")

        assert outside.lit is False and outside.dim is False
        assert inside.lit is True

    def test_a_video_in_no_compilation_cannot_be_pressed_into_one(self):
        assert self._button_for("main_player_compilation").dim is True

    def test_inside_a_compilation_the_order_and_length_read_as_held(self):
        """A compilation replaces both while it plays and gives them back on the
        way out, so they are set-but-not-in-force rather than off."""
        rows = console_rows(ConsoleModel(mode="video", latest=False),
                            main_player=ModeHud(length_mode="mixed", compilation="Volume 6"))
        held = {b.action: b for row in rows for b in row
                if b.action in ("main_shuffle", "main_player_length_shorts")}

        assert all(b.remembered and not b.lit for b in held.values())

    def test_the_clip_jump_says_which_way_it_would_go(self):
        to_scene = self._button_for("main_player_full_vid", jump_to="scene")
        to_clip = self._button_for("main_player_clip_jump", jump_to="clip")

        assert to_scene.glyph != to_clip.glyph
        assert to_scene.dim is False and to_clip.dim is False

    def test_a_video_with_nothing_on_the_other_end_is_dim(self):
        """Most clips' source scenes are not in the library at all."""
        assert self._button_for("main_player_clip_jump").dim is True

    def test_the_version_step_is_dim_without_another_version(self):
        assert self._button_for("main_player_cycle_version").dim is True
        assert self._button_for("main_player_cycle_version", has_other_versions=True).dim is False


class TestLock:
    """The padlock: whether the video repeats or plays on into the playlist."""

    def test_the_video_can_be_held_wherever_main_player_is_on_screen(self):
        assert "main_lock" in _actions(ConsoleModel(mode="video"))

    def test_it_is_lit_while_the_video_is_held(self):
        assert _button(ConsoleModel(mode="video", locked=True), "main_lock").lit is True
        assert _button(ConsoleModel(mode="video", locked=False), "main_lock").lit is False

    def test_it_says_which_way_a_press_goes(self):
        held = _button(ConsoleModel(mode="video", locked=True), "main_lock")
        loose = _button(ConsoleModel(mode="video", locked=False), "main_lock")

        assert held.tooltip.startswith("Locked") and "play on" in held.tooltip
        assert loose.tooltip.startswith("Unlocked") and "hold this video" in loose.tooltip

    def test_it_pairs_with_f_mode_and_stands_apart_from_everything_else(self):
        """The two switches are the states the player sits in — this video held,
        the playlist narrowed — where the four marks each move the video now and
        the browser opens a file.  So they sit together, and clear of both.  The
        lock also shares the transport's command prefix, which would otherwise
        have made it read as a fifth step."""
        placed = place_rows(console_rows(ConsoleModel(mode="video")), x=0, y=0)
        by_action = {b.action: rect for rect, b in placed}
        step, lock = by_action["main_next"], by_action["main_lock"]
        fmode, reset = by_action["main_fmode"], by_action["main_reset"]

        assert lock[0] - (step[0] + step[2]) == GROUP_GAP
        assert fmode[0] - (lock[0] + lock[2]) == GAP        # the pair runs together
        assert reset[0] - (fmode[0] + fmode[2]) == GROUP_GAP


class TestPlaybackSpeed:
    def test_the_video_rate_has_controls_where_main_player_is_on_screen(self):
        actions = _actions(ConsoleModel(mode="video"))
        assert "main_player_speed_down" in actions and "main_player_speed_up" in actions

    def test_genau_has_no_video_rate(self):
        """Genau's clips play at the motion's rate, so there is no video rate to
        set — that Speed is the motion's, on the readout."""
        actions = _actions(ConsoleModel(mode="genau"))

        assert "main_player_speed_down" not in actions

    def test_the_rate_is_shown_as_a_read_out_between_the_arrows(self):
        rows = console_rows(with_speed(ConsoleModel(mode="video"), 1.5))
        readouts = [b.glyph for row in rows for b in row if not b.action]

        assert "1.5×" in readouts


class TestClipSeconds:
    """How long an unlocked Genau leaves each clip up — the only thing left of
    what used to be the auto-advance switch."""

    def test_the_pace_has_arrows_where_genau_is_on_screen(self):
        actions = _actions(ConsoleModel(mode="genau"))
        assert "genau_clip_seconds_down" in actions and "genau_clip_seconds_up" in actions

    def test_video_mode_shows_the_video_rate_instead(self):
        """The row is about what the transport is stepping, and in video mode
        that is the main player's video, which has a playback rate rather than a pace."""
        actions = _actions(ConsoleModel(mode="video"))
        assert "genau_clip_seconds_down" not in actions
        assert "main_player_speed_down" in actions

    def test_the_seconds_are_shown_as_a_read_out_between_the_arrows(self):
        rows = console_rows(ConsoleModel(mode="genau", advance_interval=7))
        readouts = [b.glyph for row in rows for b in row if not b.action]

        assert "7s" in readouts
        assert "Clip seconds" in readouts


class TestDriveControls:
    """The amplitude/centre/speed arrows moved onto the readout, so they are not
    console buttons any more; the hands-free switches still are."""

    def test_the_switch_row_is_there_in_both_modes(self):
        """The Robot Hand is backing the screen in both: driving outright in
        genau mode, taking the funscript's gaps in video mode."""
        for mode in ("video", "genau"):
            actions = _actions(ConsoleModel(mode=mode))
            for action in ("robot_hand_toggle_cruise", "robot_hand_cycle_shape",
                           "quarter_button"):
                assert action in actions, (mode, action)

    def test_auto_advance_is_no_longer_a_switch_of_its_own(self):
        """Arming it and holding a clip against it were two controls that could
        disagree, and the padlock beside them was a second lock on a console that
        already had the main player's.  What is left is the pace, on its own row."""
        actions = _actions(ConsoleModel(mode="genau"))

        assert "genau_toggle_auto_advance" not in actions
        assert "genau_toggle_clip_lock" not in actions

    def test_the_axis_arrows_are_not_console_buttons(self):
        """They belong to the readout now, drawn on the bars themselves."""
        actions = _actions(ConsoleModel(mode="video"))

        for action in ("robot_hand_amplitude_up", "robot_hand_center_down",
                       "robot_hand_speed_up"):
            assert action not in actions


class TestLockAcrossModes:
    """One padlock on the console, whichever player is showing: it holds the main player's
    video in video mode, and Genau's clip in genau."""

    def test_every_mode_offers_exactly_one_padlock(self):
        for mode in ("video", "genau"):
            actions = _actions(ConsoleModel(mode=mode))
            assert actions.count("main_lock") == 1, mode

    def test_it_is_lit_while_whatever_is_showing_is_held(self):
        for mode in ("video", "genau"):
            assert _button(ConsoleModel(mode=mode, locked=True), "main_lock").lit is True
            assert _button(ConsoleModel(mode=mode, locked=False), "main_lock").lit is False

    def test_in_genau_it_says_what_the_clip_does_and_how_fast(self):
        held = _button(ConsoleModel(mode="genau", locked=True, advance_interval=7),
                       "main_lock")
        loose = _button(ConsoleModel(mode="genau", locked=False, advance_interval=7),
                        "main_lock")

        assert held.tooltip.startswith("Locked") and "every 7s" in held.tooltip
        assert loose.tooltip.startswith("Unlocked") and "every 7s" in loose.tooltip


class TestState:
    def test_the_mode_you_are_in_is_lit_and_the_others_are_not(self):
        model = ConsoleModel(mode="video")

        assert _button(model, "main_video_activate").lit is True
        assert _button(model, "genau_activate").lit is False

    def test_nothing_but_the_recording_and_its_loop_takes_a_color_of_its_own(self):
        """Every switch here lights in the same white; red and blue are left to the
        two halves of a recording, which is the one control that has to say which
        of two things it is doing."""
        model = ConsoleModel(mode="genau", cruise=True, locked=True)
        colored = [b.action for row in console_rows(model) for b in row
                   if b.warn or b.hold]

        assert colored == []

    def test_f_mode_keeps_the_green_the_other_switches_gave_up(self):
        """It narrows the playlist to what has a funscript, and green means the
        favorites and the funscripts — so it is the one lit control here that is
        not white."""
        assert _button(ConsoleModel(mode="video", f_mode=True), "main_fmode").favorite is True
        assert _button(ConsoleModel(mode="genau"), "robot_hand_toggle_cruise").favorite is False

    def test_the_record_button_tells_marking_from_looping(self):
        """One key does both halves, and they look identical otherwise: the mark
        is still open in one and the loop is running in the other.  Red while it
        is being recorded, blue once it repeats."""
        idle = _button(ConsoleModel(mode="video"), "main_player_record_tap")
        marking = _button(ConsoleModel(mode="video", record="recording"), "main_player_record_tap")
        looping = _button(ConsoleModel(mode="video", record="looping"), "main_player_record_tap")

        assert (idle.warn, idle.hold) == (False, False)
        assert (marking.warn, marking.hold) == (True, False)
        assert (looping.warn, looping.hold) == (False, True)

    def test_the_record_button_says_which_press_comes_next(self):
        for record, wanted in (("normal", "Record"), ("recording", "out point"),
                               ("looping", "drop the loop")):
            button = _button(ConsoleModel(mode="video", record=record), "main_player_record_tap")
            assert wanted in button.tooltip


class TestModePredicates:
    def test_main_player_displays_covers_video_mode_alone(self):
        assert main_player_displays("video")
        assert not main_player_displays("genau")


class TestReadConsole:
    def test_it_reads_back_what_fun_time_published(self, tmp_path: Path):
        import json
        path = tmp_path / "main_player_console.json"
        path.write_text(json.dumps({
            "mode": "video", "active": True, "f_mode": True, "osr2": "robot_hand",
            "broker": True, "record": "looping", "locked": False, "cruise": True,
            "shape": "sawtooth",
        }), encoding="utf-8")

        model = read_console(path)

        assert model.mode == "video"
        assert model.active is True
        assert model.f_mode is True
        assert model.osr2 == "robot_hand"
        assert model.broker is True
        assert model.record == "looping"
        assert model.locked is False
        assert model.cruise is True
        assert model.shape == "sawtooth"

    def test_a_panel_that_says_nothing_about_the_lock_reads_as_locked(self, tmp_path: Path):
        """Which is where both players open, and what a Fun Time too old to
        publish the flag is still describing."""
        import json
        path = tmp_path / "main_player_console.json"
        path.write_text(json.dumps({"mode": "video"}), encoding="utf-8")

        assert read_console(path).locked is True
        assert ConsoleModel().locked is True

    def test_a_torn_or_missing_file_keeps_the_console_you_have(self, tmp_path: Path):
        path = tmp_path / "main_player_console.json"
        assert read_console(path) is None

        path.write_text('{"mode": "video"', encoding="utf-8")
        assert read_console(path) is None


class TestLayout:
    def test_the_mode_row_leads_so_it_holds_its_place_across_modes(self):
        for mode in ("video", "genau"):
            first = console_rows(ConsoleModel(mode=mode))[0]
            assert [b.action for b in first][:3] == [
                "main_video_activate", "genau_activate", "main_minimize"]

    def test_the_file_actions_ride_the_mode_row_where_there_is_a_video(self):
        """Browsing for another video, recording a loop and saving what it caught
        are about files rather than about the video on screen — and the transport
        row had grown long enough that its own groups stopped reading as groups."""
        video = [b.action for b in console_rows(ConsoleModel(mode="video"))[0]]
        genau = [b.action for b in console_rows(ConsoleModel(mode="genau"))[0]]

        assert video[3:] == ["browse_library", "main_player_record_tap", "clipper_save"]
        # Nothing for them to act on in genau mode, so the row stops at minimize —
        # the same branch the transport row takes, one row down.
        assert genau[3:] == []

    def test_the_file_actions_stand_apart_from_minimize_and_from_each_other(self):
        """Three different things sharing one row: the window, the browser, and
        the two presses that make a clip."""
        placed = place_rows(console_rows(ConsoleModel(mode="video")), x=0, y=0)
        by_action = {b.action: rect for rect, b in placed}
        minimize, browse = by_action["main_minimize"], by_action["browse_library"]
        record, save = by_action["main_player_record_tap"], by_action["clipper_save"]

        assert browse[0] - (minimize[0] + minimize[2]) == GROUP_GAP
        assert record[0] - (browse[0] + browse[2]) == GROUP_GAP
        assert save[0] - (record[0] + record[2]) == GAP

    def test_minimize_rides_the_row_that_never_changes(self):
        """It parks the slot's window whatever is on it, so it must be in the row
        that is the same in every mode — the transport moves and resizes as the
        mode flips, which would put this button somewhere else each time."""
        for mode in ("video", "genau"):
            placed = place_rows(console_rows(ConsoleModel(mode=mode)), x=0, y=0)
            rect = next(r for r, b in placed if b.action == "main_minimize")
            assert rect == next(r for r, b in place_rows(
                console_rows(ConsoleModel(mode="video")), x=0, y=0)
                if b.action == "main_minimize"), mode

    def test_minimize_stands_apart_from_the_modes_it_sits_beside(self):
        """It is about the window, not about which app owns the slot, so it must
        not read as a fourth mode: the wider group gap separates it."""
        placed = place_rows(console_rows(ConsoleModel(mode="video")), x=0, y=0)
        by_action = {b.action: r for r, b in placed}
        genau, minimize = by_action["genau_activate"], by_action["main_minimize"]

        assert minimize[0] - (genau[0] + genau[2]) == GROUP_GAP

    def test_minimize_asks_for_a_drawn_bar_rather_than_a_font_glyph(self):
        """Windows' own minimize mark is in a face this HUD does not load, and
        Pillow draws tofu for what a face lacks — so the console names a marker and
        the painter draws it, the way the waveform does."""
        button = _button(ConsoleModel(mode="genau"), "main_minimize")

        assert button.glyph == MINIMIZE_ICON
        assert "taskbar" in button.tooltip

    def test_a_press_finds_the_button_under_it(self):
        placed = place_rows(console_rows(ConsoleModel(mode="video")), x=0, y=0)
        rect, _b = next((r, b) for r, b in placed if b.action == "main_next")

        assert hit_test(placed, rect[0] + 1, rect[1] + 1) == "main_next"
        assert tooltip_at(placed, rect[0] + 1, rect[1] + 1) == "Next video"

    def test_a_press_off_every_button_posts_nothing(self):
        placed = place_rows(console_rows(ConsoleModel(mode="video")), x=0, y=0)

        assert hit_test(placed, 5000, 5000) == ""

    def test_a_read_out_is_not_a_hit_target(self):
        placed = place_rows(console_rows(with_speed(ConsoleModel(mode="video"), 1.0)), x=0, y=0)
        rect = next(r for r, b in placed if not b.action and b.glyph.endswith("×"))

        assert hit_test(placed, rect[0] + 1, rect[1] + 1) == ""

    def test_the_buttons_are_the_declared_size(self):
        placed = place_rows(console_rows(ConsoleModel(mode="video")), x=0, y=0)

        assert all(rect[3] == BUTTON for rect, _b in placed)


def with_speed(model: ConsoleModel, speed: float) -> ConsoleModel:
    from dataclasses import replace
    return replace(model, playback_speed=speed)


def test_the_mode_row_can_be_left_off_and_takes_minimize_with_it():
    # A console drawn inside another app's window is not one of the three
    # players that row switches between, and has no borderless window of its own
    # to park. Everything below it still means what it means here — which is the
    # point of asking for this console rather than building a second one.
    from player_core.console import ConsoleModel, console_rows

    model = ConsoleModel(mode="genau")
    full = console_rows(model)
    trimmed = console_rows(model, modes=False)
    assert len(trimmed) == len(full) - 1
    assert trimmed == full[1:]
    actions = [b.action for row in trimmed for b in row]
    assert "main_minimize" not in actions
    assert not any(a.endswith("_activate") for a in actions)
    # ...and the rows that carry the motion are all still there.
    for kept in ("robot_hand_toggle_cruise", "robot_hand_cycle_shape", "main_lock",
                 "genau_clip_seconds_up", "genau_clip_seconds_down"):
        assert kept in actions


def test_the_published_verbs_are_exactly_what_the_buttons_post():
    """CONSOLE_VERBS is data a consumer holds its dispatch table to, so it has
    to be exactly the verbs the buttons post -- read off the source, so a button
    added with a new verb, or one renamed, fails here before it fails at a
    click."""
    import ast
    from pathlib import Path

    from player_core.console import CONSOLE_VERBS

    source = Path(__file__).resolve().parent.parent / "player_core" / "console.py"

    def literals(node):
        """Every string a verb slot can evaluate to.  Not only a bare one: a
        button whose verb depends on what it is showing picks among them there
        -- a lit length button asks for mixed, a dark one for its own length --
        and the projection pair, with four states to reach, nests the choice."""
        if isinstance(node, ast.IfExp):
            return literals(node.body) | literals(node.orelse)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
            return {node.value}
        return set()

    posted = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Button" and node.args:
            posted.update(literals(node.args[0]))
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_MODE_BUTTONS" for t in node.targets):
            posted.update(entry.elts[0].value for entry in node.value.elts)
    assert posted == CONSOLE_VERBS
