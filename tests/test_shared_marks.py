"""The HUD wears the family's marks, not lookalikes of them.

A HUD is painted into the video frame with Pillow and there is no Qt in a player
process, so for a long time every mark here was whatever a symbol font happened
to carry, or something hand-drawn on the spot.  The bin on this console had
nothing to do with the bin on Origenerator's toolbar.  Both sides now render one
list of geometry out of shared_ui, and these hold the console to using it.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from player_core.console import WAVE_ICON, _GLYPHS
from player_core.hud_marks import SHARED_MARK, shared_mark, shared_mark_name
from player_core.hud_panel import MARK_INSET, draw_mark
from shared_ui.icon_geometry import glyph_names


def _named_marks() -> dict[str, str]:
    """Every control face that names a shared mark, by the mark it names."""
    faces = {key: value for key, value in _GLYPHS.items()} | {"wave": WAVE_ICON}
    return {
        key: shared_mark_name(face)
        for key, face in faces.items()
        if face.startswith(SHARED_MARK)
    }


class TestNamingTheMarks:
    def test_a_marker_round_trips_through_the_name_it_carries(self):
        assert shared_mark_name(shared_mark("trash")) == "trash"

    def test_the_console_names_marks_rather_than_drawing_them(self):
        # The console is a model the painter reads; it holds no colors and no
        # Pillow, and it stayed that way by naming what it wants drawn.
        assert _named_marks(), "no control names a shared mark any more"

    def test_the_bin_and_the_reset_and_the_waveform_are_family_marks(self):
        # The three the console used to spell for itself: two characters out of
        # Segoe UI Symbol and one curve drawn by hand in the painter.
        named = _named_marks()
        assert named["trash"] == "trash"
        assert named["reset"] == "reset"
        assert named["wave"] == "wave"

    def test_every_mark_a_control_names_actually_exists(self):
        # A typo here would be a KeyError raised deep inside a video pipeline,
        # while a player is on screen -- so it is caught in the suite instead.
        missing = {
            key: name for key, name in _named_marks().items()
            if name not in glyph_names()
        }
        assert not missing, f"controls naming marks shared_ui does not have: {missing}"


class TestDrawingThem:
    def test_a_mark_lands_inside_the_button_it_was_given(self):
        # HUD buttons draw their own rounded border, so a mark filling the whole
        # rect runs into it. The inset is what keeps the two apart.
        panel = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
        draw_mark(panel, "trash", (0, 0, 18, 18), (255, 255, 255, 255))
        ink = np.asarray(panel)[:, :, 0] > 128

        assert ink.any(), "the mark did not draw"
        assert not ink[:MARK_INSET, :].any()
        assert not ink[-MARK_INSET:, :].any()

    def test_a_mark_is_laid_over_what_the_button_already_painted(self):
        # It composites onto the button's fill rather than stamping a
        # transparent square over it, which would cut a hole in the panel.
        panel = Image.new("RGBA", (18, 18), (0, 90, 0, 255))
        draw_mark(panel, "reset", (0, 0, 18, 18), (255, 255, 255, 255))
        pixels = np.asarray(panel)

        assert (pixels[:, :, 3] == 255).all(), "the mark punched through the panel"
        assert (pixels[:, :, 0] > 128).any(), "the mark did not draw"
        assert (pixels[:, :, 1] == 90).any(), "the fill is gone"

    def test_two_marks_are_two_different_drawings(self):
        # The point of naming them: a control that names the wrong one shows the
        # wrong one, and only a difference here would ever reveal that.
        def drawn(name: str) -> bytes:
            panel = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
            draw_mark(panel, name, (0, 0, 18, 18), (255, 255, 255, 255))
            return panel.tobytes()

        assert drawn("trash") != drawn("reset")
        assert drawn("reset") != drawn("wave")
