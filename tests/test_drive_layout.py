"""drive_layout — the readout's rects, and what a press on one asks for.

The layout can be wrong and still look right: a hit target that has drifted from
the mark drawn over it shows up only when a press lands on the wrong control. So
these press the rects the geometry hands out, rather than trusting them.
"""

from player_core import drive_layout as layout
from player_core.geometry import contains


def _by_action(controls):
    return {c.action: c for c in controls}


def test_the_block_is_as_big_as_the_parts_it_places():
    g = layout.geometry(0, 0, 0.5)
    for rect in (g.wave, g.speed_bar, g.amp_bar, g.speed_up, g.center_down):
        x, y, w, h = rect
        assert 0 <= x and x + w <= layout.SECTION_W
        assert 0 <= y and y + h <= layout.SECTION_H
    assert layout.section_size() == (layout.SECTION_W, layout.SECTION_H)
    assert layout.section_size(trace_only=True) == layout.TRACE_ONLY_SIZE


def test_the_centre_marks_ride_the_line_they_move_and_stay_on_the_block():
    # The dotted centre line moves with the value, and its marks travel with it —
    # but a centre at either extreme must not push one off the trace's band.
    for center in (0, 25, 50, 75, 100):
        g = layout.geometry(0, 0, layout.fraction(center))
        wave_x, wave_y, _w, wave_h = g.wave
        for rect in (g.center_up, g.center_down):
            assert wave_y <= rect[1]
            assert rect[1] + rect[3] <= wave_y + wave_h
    high = layout.geometry(0, 0, 1.0).center_up[1]
    low = layout.geometry(0, 0, 0.0).center_up[1]
    assert high < low  # a higher centre sits higher up the block


def test_a_press_reads_the_value_drawn_under_it():
    tracks = {t.axis: t for t in layout.tracks(0, 0, 50)}
    speed = tracks[layout.SPEED]
    x, y, w, h = speed.rect
    assert layout.track_value(speed, x, y) == 0
    assert layout.track_value(speed, x + w - 1, y) == 100
    assert layout.track_value(speed, x + (w - 1) // 2, y) == 50

    trace = tracks[layout.CENTER]
    x, y, w, h = trace.rect
    assert layout.track_value(trace, x, y) == 100          # the top is centre 100
    assert layout.track_value(trace, x, y + h - 1) == 0

    # Amplitude is drawn out from the centre both ways, so a press is the reach
    # needed to arrive there: half the band above a centred stroke is amp 100.
    amp = tracks[layout.AMPLITUDE]
    x, y, w, h = amp.rect
    assert layout.track_value(amp, x, y) == 100
    assert layout.track_value(amp, x, y + (h - 1) // 2) <= 2  # no reach at all


def test_a_press_off_the_end_of_a_band_reads_as_its_nearer_end():
    # A drag that wanders off the bar goes on setting it rather than stopping.
    speed = {t.axis: t for t in layout.tracks(0, 0, 50)}[layout.SPEED]
    x, y, w, _h = speed.rect
    assert layout.track_value(speed, x - 500, y) == 0
    assert layout.track_value(speed, x + w + 500, y) == 100


def test_every_mark_is_hit_by_a_press_in_its_own_middle_and_by_no_other():
    marks = layout.controls(0, 0, 50, layout.Limits())
    for mark in marks:
        x, y, w, h = mark.rect
        px, py = x + w // 2, y + h // 2
        assert [m.action for m in marks
                if contains(m.rect, px, py)] == [mark.action]


def test_a_mark_at_the_end_of_its_range_is_dimmed_and_only_that_one():
    marks = _by_action(layout.controls(0, 0, 50, layout.Limits(amp_at_max=True)))
    assert marks["genau_amplitude_up"].dim
    assert not marks["genau_amplitude_down"].dim
    assert not any(m.dim for a, m in marks.items()
                   if not a.startswith("genau_amplitude"))


def test_nothing_driving_dims_every_mark_and_every_band():
    marks = layout.controls(0, 0, 50, layout.Limits(), dim=True)
    assert all(mark.dim for mark in marks)
    assert all(track.dim for track in layout.tracks(0, 0, 50, dim=True))


def test_every_mark_posts_the_command_fun_time_routes_to_genau():
    # The verbs are the wire, so they are written out here rather than composed:
    # a rename has to be findable from the dispatch end as well as this one.
    posted = _by_action(layout.controls(0, 0, 50, layout.Limits()))
    assert set(posted) == {
        "genau_speed_down", "genau_speed_up",
        "genau_amplitude_down", "genau_amplitude_up",
        "genau_center_down", "genau_center_up",
    }


def test_the_trace_alone_has_nothing_to_press():
    # In Nau there is no engine behind the screen for a mark to reach.
    assert layout.controls(0, 0, 50, layout.Limits(), trace_only=True) == []
    assert layout.tracks(0, 0, 50, trace_only=True) == []
