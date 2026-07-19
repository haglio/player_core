"""The chrome the players' in-video HUDs are drawn on."""
from __future__ import annotations

import numpy as np

from player_core.hud_panel import BG_PRIMARY, PANEL_ALPHA, HudPanel, load_font, px, text_width


def test_panel_is_a_translucent_rounded_slab_of_the_asked_size():
    panel = HudPanel(60, 40)

    bgra = panel.to_bgra()

    assert bgra.shape == (40, 60, 4)
    middle = bgra[20, 30]
    assert tuple(middle) == (BG_PRIMARY[2], BG_PRIMARY[1], BG_PRIMARY[0], PANEL_ALPHA)
    assert bgra[0, 0, 3] == 0  # the rounded corner leaves the very corner clear
    assert np.asarray(bgra).dtype == np.uint8


def test_point_sizes_become_pixels_at_96_dpi():
    """Qt sized these HUDs' fonts in points and Pillow sizes in pixels, so the
    panels keep their old proportions only if the conversion does."""
    assert px(9) == 12
    assert px(11) == 15


def test_a_missing_face_falls_back_instead_of_raising():
    """A font the machine does not have must not take the player down mid-render:
    the HUD is drawn every frame, so an OSError here is a crash, not a blank."""
    assert load_font(11, "no-such-face.ttf") is not None


def test_text_width_measures_the_drawn_string():
    font = load_font(11)

    assert text_width(font, "") == 0
    assert text_width(font, "Volume 6") > text_width(font, "Vol")
