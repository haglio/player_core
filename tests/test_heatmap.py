from __future__ import annotations

from player_core.funscript import Funscript
from player_core.heatmap import ScriptColors, _speed_to_color, bin_speeds, build_heatmap


class TestSpeedToColor:
    def test_gradient_anchors_run_from_near_black_through_blue_cyan_green_and_yellow_to_red(self):
        assert _speed_to_color(0) == (10, 14, 30)
        assert _speed_to_color(100) == (30, 70, 230)
        assert _speed_to_color(200) == (20, 210, 210)
        assert _speed_to_color(300) == (40, 220, 50)
        assert _speed_to_color(400) == (235, 220, 40)
        assert _speed_to_color(500) == (240, 40, 30)

    def test_interpolates_linearly_between_anchors(self):
        assert _speed_to_color(50) == (20, 42, 130)
        assert _speed_to_color(150) == (25, 140, 220)

    def test_clamps_above_top_anchor_to_red(self):
        assert _speed_to_color(501) == (240, 40, 30)
        assert _speed_to_color(10_000) == (240, 40, 30)


class TestTheStripIsThePaletteOverTheArithmetic:
    def test_each_bin_is_its_own_speed_as_a_color(self):
        fs = Funscript(actions=[(1000, 0), (1500, 100), (2000, 0)])

        colors = build_heatmap(fs, 4, start_ms=0, end_ms=4000)

        assert colors == [
            _speed_to_color(speed)
            for speed in bin_speeds(fs, 4, start_ms=0, end_ms=4000)
        ]

    def test_an_empty_window_draws_nothing(self):
        fs = Funscript(actions=[(0, 0), (1000, 100)])

        assert build_heatmap(fs, 10, start_ms=0, end_ms=0) == []


class TestHowMuchTravelLandsInEachBin:
    def test_an_empty_window_has_no_bins(self):
        fs = Funscript(actions=[(0, 0), (1000, 100)])

        assert bin_speeds(fs, 10, start_ms=0, end_ms=0) == []

    def test_a_script_with_nothing_to_move_between_is_idle_throughout(self):
        assert bin_speeds(Funscript(actions=[]), 4, start_ms=0, end_ms=10_000) == [0] * 4
        assert bin_speeds(
            Funscript(actions=[(500, 80)]), 4, start_ms=0, end_ms=10_000) == [0] * 4

    def test_full_travel_per_bin_reads_as_100_units_per_second(self):
        fs = Funscript(actions=[(0, 0), (1000, 100), (2000, 0), (3000, 100), (4000, 0)])

        assert bin_speeds(fs, 4, start_ms=0, end_ms=4000) == [100] * 4

    def test_a_segment_spanning_bins_splits_its_travel_by_overlap(self):
        fs = Funscript(actions=[(0, 0), (2000, 100)])

        assert bin_speeds(fs, 2, start_ms=0, end_ms=2000) == [50, 50]

    def test_bins_before_the_first_action_and_after_the_last_are_idle(self):
        fs = Funscript(actions=[(1000, 0), (1500, 100), (2000, 0)])

        assert bin_speeds(fs, 4, start_ms=0, end_ms=4000) == [0, 200, 0, 0]

    def test_an_instantaneous_jump_between_duplicate_timestamps_is_ignored(self):
        fs = Funscript(actions=[(0, 0), (1000, 100), (1000, 20), (2000, 120)])

        assert bin_speeds(fs, 2, start_ms=0, end_ms=2000) == [100, 100]

    def test_one_bin_averages_the_whole_video(self):
        fs = Funscript(actions=[(0, 0), (1000, 100)])

        assert bin_speeds(fs, 1, start_ms=0, end_ms=2000) == [50]

    def test_travel_past_the_video_end_does_not_count(self):
        fs = Funscript(actions=[(0, 0), (2000, 100)])

        assert bin_speeds(fs, 1, start_ms=0, end_ms=1000) == [50]


class TestAWindowInsideTheVideo:
    def test_its_bins_see_only_their_own_window(self):
        fs = Funscript(actions=[(0, 0), (1000, 100), (2000, 0), (3000, 100), (4000, 0)])

        assert bin_speeds(fs, 2, start_ms=1000, end_ms=3000) == [100, 100]

    def test_activity_entirely_before_it_is_excluded(self):
        fs = Funscript(actions=[(0, 0), (1000, 100)])

        assert bin_speeds(fs, 2, start_ms=2000, end_ms=4000) == [0, 0]

    def test_a_segment_straddling_its_start_counts_only_the_overlap(self):
        fs = Funscript(actions=[(500, 0), (1500, 100)])

        assert bin_speeds(fs, 1, start_ms=1000, end_ms=2000) == [50]


class TestTheColorsAcrossTheTrack:
    def _script(self):
        return Funscript(actions=[(0, 0), (1000, 100), (2000, 0)])

    def test_are_the_scripts_colors_over_the_whole_length_at_the_tracks_width(self):
        colors = ScriptColors()

        across = colors.across("v0", self._script(), 2000, 100)

        assert across == build_heatmap(self._script(), 100, start_ms=0, end_ms=2000)

    def test_are_nothing_for_an_unscripted_item(self):
        assert ScriptColors().across("v0", None, 2000, 100) == []

    def test_are_built_once_while_the_item_its_length_and_the_width_hold_still(self):
        colors = ScriptColors()
        script = self._script()

        first = colors.across("v0", script, 2000, 100)
        again = colors.across("v0", script, 2000, 100)

        assert again is first

    def test_are_rebuilt_when_the_item_the_length_or_the_width_changes(self):
        colors = ScriptColors()
        script = self._script()
        first = colors.across("v0", script, 2000, 100)

        assert colors.across("v1", script, 2000, 100) is not first
        assert colors.across("v1", script, 3000, 100) is not colors.across("v1", script, 2000, 100)
        assert len(colors.across("v1", script, 3000, 50)) == 50
