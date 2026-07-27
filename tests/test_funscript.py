from __future__ import annotations

import json

from player_core.funscript import Funscript, load, snap_loop


class TestLoad:
    def test_parses_actions(self, tmp_path):
        data = {
            "actions": [
                {"at": 1000, "pos": 0},
                {"at": 2000, "pos": 100},
                {"at": 500, "pos": 50},
            ]
        }
        path = tmp_path / "test.funscript"
        path.write_text(json.dumps(data))

        fs = load(path)

        assert fs.actions == [(500, 50), (1000, 0), (2000, 100)]


class TestFirstRealEventMs:
    def test_dense_from_start_has_no_lead_in(self):
        fs = Funscript(actions=[(0, 0), (300, 100), (600, 0), (900, 100)])

        assert fs.first_real_event_ms is None

    def test_action_starting_late_reports_onset(self):
        fs = Funscript(actions=[(60000, 0), (60300, 100), (60600, 0)])

        assert fs.first_real_event_ms == 60000

    def test_isolated_leading_blip_is_skipped(self):
        # A stray blip at t=0, a long quiet gap, then dense action at 34s.
        fs = Funscript(actions=[
            (0, 50), (34000, 0), (34300, 100), (34600, 0), (34900, 100),
        ])

        assert fs.first_real_event_ms == 34000

    def test_sparse_throughout_has_no_onset(self):
        # Every action is isolated (10s apart): there is no dense onset to
        # rest up to, so drive normally rather than park the whole video.
        fs = Funscript(actions=[(0, 0), (10000, 100), (20000, 0), (30000, 100)])

        assert fs.first_real_event_ms is None

    def test_short_lead_in_is_not_worth_parking(self):
        # Dense action begins at 4s — under the "a long time" threshold, so no
        # parking (a momentary rest at the very start is not worth it).
        fs = Funscript(actions=[(4000, 0), (4300, 100), (4600, 0), (4900, 100)])

        assert fs.first_real_event_ms is None


class TestIsRestingAt:
    def test_on_a_dense_cluster_is_not_resting(self):
        fs = Funscript(actions=[(10000, 0), (10300, 100), (10600, 0), (10900, 100)])

        assert fs.is_resting_at(10300) is False

    def test_deep_gap_between_clusters_is_resting(self):
        fs = Funscript(actions=[
            (10000, 0), (10300, 100), (10600, 0),   # cluster A
            (40000, 0), (40300, 100), (40600, 0),   # cluster B
        ])

        assert fs.is_resting_at(25000) is True  # midway in the 30s gap

    def test_buffer_before_a_cluster_is_not_resting(self):
        # The funscript reclaims a _QUIET_LEAD_IN_MS buffer ahead of its action,
        # so the OSR2 settles onto the script before it fires.
        fs = Funscript(actions=[(40000, 0), (40300, 100), (40600, 0)])

        assert fs.is_resting_at(37000) is False  # 3s before -> inside the buffer
        assert fs.is_resting_at(34000) is True   # 6s before -> still the gap

    def test_quiet_lead_in_is_resting(self):
        fs = Funscript(actions=[(60000, 0), (60300, 100), (60600, 0)])

        assert fs.is_resting_at(0) is True

    def test_isolated_blip_does_not_anchor_driving(self):
        # A stray blip with no dense neighbour must not pull the OSR2 off Genau.
        fs = Funscript(actions=[(20000, 50), (60000, 0), (60300, 100), (60600, 0)])

        assert fs.is_resting_at(20000) is True

    def test_sparse_funscript_is_all_resting(self):
        # Every action isolated (10s apart): no dense scripting, Genau drives.
        fs = Funscript(actions=[(0, 0), (10000, 100), (20000, 0), (30000, 100)])

        assert fs.is_resting_at(15000) is True


class TestNextActiveMs:
    def _two_clusters(self):
        return Funscript(actions=[
            (10000, 0), (10300, 100), (10600, 0),   # cluster A
            (40000, 0), (40300, 100), (40600, 0),   # cluster B
        ])

    def test_from_the_top_reaches_the_first_cluster(self):
        assert self._two_clusters().next_active_ms(0) == 10000

    def test_inside_a_gap_reaches_the_cluster_after_it(self):
        assert self._two_clusters().next_active_ms(25000) == 40000

    def test_lands_on_the_first_stroke_not_in_the_buffer_before_it(self):
        # is_resting_at hands the script back a _QUIET_LEAD_IN_MS buffer ahead of
        # a cluster so the OSR2 settles onto it; a jump that stopped there would
        # be five seconds of nothing, so it goes all the way to the stroke.
        fs = self._two_clusters()

        assert fs.is_resting_at(36000) is False   # inside the buffer
        assert fs.next_active_ms(25000) == 40000  # the jump still goes past it

    def test_inside_a_cluster_carries_on_to_the_next(self):
        """"Next" is forward: asked from the middle of a run, the answer is the
        run after it, not the one already playing."""
        assert self._two_clusters().next_active_ms(10300) == 40000

    def test_past_the_last_cluster_has_nowhere_to_go(self):
        assert self._two_clusters().next_active_ms(50000) is None

    def test_isolated_blips_are_not_somewhere_to_jump_to(self):
        # A lone action is not action; only densely-sampled runs count, the same
        # standard is_resting_at applies.
        fs = Funscript(actions=[
            (10000, 0), (10300, 100), (10600, 0),   # a real cluster
            (30000, 50),                            # a stray blip
        ])

        assert fs.next_active_ms(20000) is None

    def test_an_unscripted_stretch_of_a_scripted_video_still_answers(self):
        fs = Funscript(actions=[(60000, 0), (60300, 100), (60600, 0)])

        assert fs.next_active_ms(0) == 60000

    def test_a_script_with_no_dense_action_at_all_has_nowhere_to_go(self):
        fs = Funscript(actions=[(0, 0), (10000, 100), (20000, 0), (30000, 100)])

        assert fs.next_active_ms(0) is None


class TestSnapLoop:
    def _make_fs(self):
        return Funscript(actions=[
            (0, 100), (1000, 0), (2000, 100), (3000, 0),
            (4000, 100), (5000, 0), (6000, 100),
        ])

    def test_snaps_outward_to_base_positions(self):
        fs = self._make_fs()

        result = snap_loop(fs, 2500, 3500)

        assert result == (2000, 4000)

    def test_in_already_on_base(self):
        fs = self._make_fs()

        result = snap_loop(fs, 2000, 3500)

        assert result == (2000, 4000)

    def test_no_base_before_in_keeps_the_mark(self):
        # Nothing to pull the in point back onto — the first base is ahead of it —
        # so it stays where it was marked rather than jumping to the script's start.
        fs = Funscript(actions=[
            (1000, 0), (2000, 100), (3000, 0), (4000, 100),
        ])

        result = snap_loop(fs, 500, 2500)

        assert result == (500, 2500)

    def test_no_base_after_out_keeps_the_mark(self):
        # The last base is behind the out point, and snapping is outward only, so
        # the loop still ends where it was marked — never short of it.
        fs = Funscript(actions=[
            (0, 100), (1000, 0), (2000, 100), (3000, 0),
        ])

        result = snap_loop(fs, 2500, 3500)

        assert result == (2000, 3500)

    def test_zero_duration_extends(self):
        fs = self._make_fs()

        result = snap_loop(fs, 2050, 2050)

        assert result[1] - result[0] >= 500

    def test_a_distant_base_does_not_stretch_the_loop(self):
        # Full strokes for the first two seconds, then a long stretch of shallow
        # ones that never reach a base.  A mark inside that stretch has no base
        # near either end, and a loop stretched out to the far ones would run for
        # a minute instead of the five seconds that were marked.
        actions = [(0, 100), (500, 0), (1000, 100), (1500, 0), (2000, 100)]
        actions += [(t, 60 if (t // 500) % 2 else 20)
                    for t in range(2500, 60001, 500)]
        fs = Funscript(actions=actions)

        in_ms, out_ms = snap_loop(fs, 30000, 35000)

        assert (in_ms, out_ms) == (30000, 35000)

    def test_a_script_with_no_base_at_all_keeps_the_mark(self):
        # A script authored to a reduced range never reaches a base, so there is
        # nothing anywhere to snap to — which must not be read as "loop the file".
        fs = Funscript(actions=[(t, 80 if (t // 500) % 2 else 0)
                                for t in range(0, 60001, 500)])

        assert snap_loop(fs, 30000, 35000) == (30000, 35000)

    def test_no_funscript_keeps_the_mark(self):
        # An unscripted video loops too; there is simply nothing to snap to.
        assert snap_loop(None, 30000, 35000) == (30000, 35000)

    def test_no_funscript_still_widens_to_the_minimum(self):
        assert snap_loop(None, 30000, 30100) == (30000, 30500)
