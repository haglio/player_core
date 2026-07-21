"""The chrome the players' in-video HUDs are drawn on."""
from __future__ import annotations

import numpy as np

from player_core.hud_panel import (
    BG_PRIMARY,
    PANEL_ALPHA,
    HudPanel,
    draw_glyph,
    load_font,
    px,
    text_width,
)


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


def _ink_center(size: int, paint) -> tuple[float, float]:
    """Where the ink *paint* leaves on a blank square actually sits."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    paint(ImageDraw.Draw(image))
    ys, xs = np.nonzero(np.asarray(image)[:, :, 3])
    return (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2


def test_a_glyph_is_centred_on_its_ink_not_on_the_fonts_box():
    """``anchor="mm"`` centres the font's box, whose bottom is the descender line
    however short the glyph — which is why every icon button drew its mark low.
    Centring the ink puts it in the middle of the button, for the transport
    arrows, the padlock and the bare minus sign alike."""
    font = load_font(20, "seguisym.ttf")

    for glyph in ("⏮", "\U0001F512", "−", "∿"):
        centred = _ink_center(60, lambda d, g=glyph: draw_glyph(
            d, 30, 30, g, font, (255, 255, 255, 255)))
        by_metrics = _ink_center(60, lambda d, g=glyph: d.text(
            (30, 30), g, font=font, anchor="mm", fill=(255, 255, 255, 255)))

        assert abs(centred[1] - 30) <= 0.5, glyph
        assert by_metrics[1] > centred[1], glyph  # the old way sat lower


def test_a_glyph_with_no_ink_draws_nothing_rather_than_raising():
    """A space has no ink to centre on; the HUD repaints every frame, so this must
    be a no-op and not an exception out of the run loop."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw_glyph(ImageDraw.Draw(image), 5, 5, " ", load_font(11), (255, 255, 255, 255))

    assert np.asarray(image)[:, :, 3].max() == 0
