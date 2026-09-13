"""The readout at the left end of the timeline row: where the video is, and how long it runs."""
from __future__ import annotations

import numpy as np

from player_core.playhead import (
    PlayheadHudPainter,
    clip_playhead,
    readout_xy,
    video_playhead,
)
from player_core.timeline import TIMELINE_HEIGHT, bar_track_x
from player_core.volume import CHIP_H, MARGIN, PAD, chip_xy


class TestWhatAVideosReadoutSays:
    def test_where_it_is_of_how_long_it_runs(self):
        assert video_playhead(42_000.0, 195_000.0, 0.0).text == "0:42 / 3:15"

    def test_where_it_is_takes_the_shape_of_how_long_it_runs(self):
        """Every digit is as wide as every other in the face these are drawn in,
        so a clock with the length's own fields never moves along the row."""
        assert video_playhead(42_000.0, 2_715_000.0, 0.0).text == "00:42 / 45:15"

    def test_a_video_an_hour_long_counts_its_hours_on_both_sides(self):
        assert video_playhead(42_000.0, 6_315_000.0, 0.0).text == "0:00:42 / 1:45:15"

    def test_the_frame_is_the_one_mpv_counts_to(self):
        """libmpv's own estimated-frame-number, read off a 29.97fps test pattern
        paused on its last frame: 239.  The rate it reports is a float32, so
        truncating the product lands one frame short at 238."""
        playhead = video_playhead(7_974.633333333334, 8_008.0, 29.970029830932617)

        assert playhead.text == "0:07 / 0:08 · frame 239"

    def test_a_video_whose_length_mpv_has_not_said_yet_has_no_readout(self):
        assert video_playhead(0.0, 0.0, 0.0) is None

    def test_a_video_whose_frame_rate_mpv_has_not_said_reads_its_clock_alone(self):
        assert video_playhead(1_000.0, 5_000.0, 0.0).text == "0:01 / 0:05"

    def test_the_widest_it_gets_is_what_it_says_on_the_last_frame(self):
        """The pill is sized to this, so a frame count that gains a digit
        partway through the video never pushes the clock along the row."""
        playhead = video_playhead(42_000.0, 2_715_000.0, 60.0)

        assert playhead.widest == "45:15 / 45:15 · frame 162900"


class TestWhatAClipsReadoutSays:
    def test_a_clip_has_frames_and_no_clock(self):
        """Genau's clips are pictures the Robot Hand scrubs through, with no time in them."""
        playhead = clip_playhead(7, 20)

        assert (playhead.text, playhead.widest) == ("frame 7 / 20", "frame 20 / 20")

    def test_a_clip_still_decoding_has_no_readout(self):
        assert clip_playhead(0, 0) is None


class TestThePill:
    def test_it_is_as_tall_as_the_volume_chip_at_the_other_end_of_the_row(self):
        pill = PlayheadHudPainter().bgra(video_playhead(42_000.0, 195_000.0, 30.0))

        assert pill.shape[0] == CHIP_H

    def test_a_video_that_runs_for_hours_gets_a_wider_pill_than_a_short_one(self):
        short = PlayheadHudPainter().bgra(video_playhead(0.0, 195_000.0, 30.0))
        long = PlayheadHudPainter().bgra(video_playhead(0.0, 7_200_000.0, 60.0))

        assert long.shape[1] > short.shape[1]

    def test_it_shows_where_the_video_has_got_to_without_changing_size(self):
        painter = PlayheadHudPainter()

        early = painter.bgra(video_playhead(1_000.0, 195_000.0, 30.0)).copy()
        later = painter.bgra(video_playhead(100_000.0, 195_000.0, 30.0))

        assert early.shape == later.shape
        assert not np.array_equal(early, later)

    def test_a_readout_that_has_not_moved_is_not_repainted(self):
        """Asked for on every frame a player paints; a paused video's readout
        holds still for as long as the pause does."""
        painter = PlayheadHudPainter()
        hud = video_playhead(1_000.0, 195_000.0, 30.0)

        assert painter.bgra(hud) is painter.bgra(hud)

    def test_its_digits_sit_in_the_middle_of_the_pill(self):
        """Centered on the digits' own ink.  Pillow's middle anchor centers the
        face's whole line, descender included, which sits a digit low."""
        pill = PlayheadHudPainter().bgra(video_playhead(42_000.0, 195_000.0, 0.0))

        first_digit = pill[:, PAD:PAD + 6, :3].sum(axis=2) > 600
        rows = np.flatnonzero(first_digit.any(axis=1))

        assert abs((rows[0] + rows[-1]) / 2 - (CHIP_H - 1) / 2) <= 0.5


class TestWhereThePillGoes:
    def test_it_sits_against_the_start_of_the_track_level_with_the_chip(self):
        x, y = readout_xy(131, win_w=1000, win_h=600, timeline_h=TIMELINE_HEIGHT)

        assert x + 131 + MARGIN == bar_track_x(1000)[0]
        assert y == chip_xy(win_w=1000, win_h=600, timeline_h=TIMELINE_HEIGHT)[1]
