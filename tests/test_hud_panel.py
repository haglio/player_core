"""The chrome the players' in-video HUDs are drawn on."""
from __future__ import annotations

import numpy as np

from player_core.hud_panel import (
    BG_PRIMARY,
    ICON_GRIDS,
    PANEL_ALPHA,
    PINK,
    TEXT_MUTED,
    TOOLTIP_PAD,
    WHITE,
    HudPanel,
    draw_active_dot,
    draw_glyph,
    draw_icon,
    draw_tooltip,
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


def test_the_active_dot_is_lit_or_grey_but_never_absent():
    """An absent dot cannot be told from an idle one, so only the player holding the
    floor would say anything — and a reader would have to check every screen to
    learn what one mark should tell them."""
    def dot(active: bool) -> tuple[int, ...]:
        panel = HudPanel(40, 40)
        draw_active_dot(panel.draw, 10, 10, active)
        return tuple(np.asarray(panel.image)[15, 15][:3])

    assert dot(True) == WHITE
    assert dot(False) == TEXT_MUTED


def test_a_tooltip_wider_than_the_panel_wraps_rather_than_running_off_it():
    """A tooltip is drawn into the panel's own bitmap, so whatever crosses the edge
    is simply never drawn — the sentence loses its tail with nothing to say it had
    one.  It wraps to the room there is instead, and the box stays on the slab."""
    panel = HudPanel(150, 120)
    font = load_font(8)

    box = draw_tooltip(panel.draw, font, "Unfavorite it or mark weird when it is "
                       "not a favorite", (20, 20), panel.image.size)

    x, y, w, h = box
    assert (x, y) >= (0, 0) and (x + w, y + h) <= (150, 120)
    assert h > sum(font.getmetrics()) + 2 * TOOLTIP_PAD  # more than one line


def test_a_tooltip_that_fits_stays_on_one_line_beside_the_cursor():
    """Wrapping is what a tooltip does when it must, not what it does — one that
    fits keeps its single line and sits down and to the right of the pointer,
    clear of the arrow itself."""
    panel = HudPanel(300, 200)
    font = load_font(8)

    x, y, _w, h = draw_tooltip(panel.draw, font, "Next clip", (40, 60),
                               panel.image.size)

    assert h == sum(font.getmetrics()) + 2 * TOOLTIP_PAD
    assert (x, y) > (40, 60)


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


def _icon_cells(letter: str, size: int = 18) -> list[str]:
    """The mark *letter* draws, read back off the pixels as its own grid."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_icon(ImageDraw.Draw(image), (0, 0, size, size), letter)
    painted = np.asarray(image)[:, :, 3] > 0
    ys, xs = np.nonzero(painted)
    cell = (xs.max() - xs.min() + 1) / 5
    return [
        "".join(
            "#" if painted[int(ys.min() + (row + 0.5) * cell),
                           int(xs.min() + (column + 0.5) * cell)] else "."
            for column in range(5)
        )
        for row in range(5)
    ]


def test_an_app_mark_draws_the_grid_its_icon_carries():
    """The .ico files live in the apps' own repos, so a HUD in one of them draws
    the mark from the grid instead of loading another repo's file — which only
    works if what lands on the pixels is that grid."""
    for letter, grid in ICON_GRIDS.items():
        assert _icon_cells(letter) == list(grid), letter


def test_an_app_mark_leaves_its_counters_clear_for_the_fill_behind_it():
    """The .ico's blank cells are transparent, so the panel colour shows through
    the letter's counters; painting them would make the mark a solid block."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (18, 18), (0, 0, 0, 255))
    draw_icon(ImageDraw.Draw(image), (0, 0, 18, 18), "B")
    pixels = np.asarray(image)

    assert (pixels[:, :, :3] == PINK).all(axis=2).any()   # the letter is drawn …
    assert (pixels[:, :, :3] == 0).all(axis=2).any()      # … and its holes are not


def test_an_app_mark_fits_inside_the_button_it_is_centred_in():
    """It has to sit in the same 18px square every other control on these HUDs
    uses, with room left around it rather than running to the button's border."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
    draw_icon(ImageDraw.Draw(image), (0, 0, 18, 18), "F")
    ys, xs = np.nonzero(np.asarray(image)[:, :, 3])

    assert xs.min() >= 2 and xs.max() <= 15
    assert ys.min() >= 2 and ys.max() <= 15


def test_a_glyph_with_no_ink_draws_nothing_rather_than_raising():
    """A space has no ink to centre on; the HUD repaints every frame, so this must
    be a no-op and not an exception out of the run loop."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw_glyph(ImageDraw.Draw(image), 5, 5, " ", load_font(11), (255, 255, 255, 255))

    assert np.asarray(image)[:, :, 3].max() == 0
