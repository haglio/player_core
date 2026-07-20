"""The chrome the players' in-video HUDs are drawn on.

Every player in this family paints its HUD into the video as a BGRA bitmap mpv
composites, rather than into a window of its own: an mpv overlay has no z-order,
so it can neither fall behind the video nor float above the desktop — the two
failure modes a separate always-on-top window kept oscillating between.

What the HUDs share is the look, not the contents: a rounded translucent slab,
the Segoe UI face sized the way Qt sized it, and the RGBA -> BGRA hand-off mpv
wants.  What each one *says* is its own business — the satellite draws a map of
clips, Nau a couple of mode lines — so this owns the chrome and stops there.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Segoe UI Bold — every label on these HUDs is bold, because they are read at a
# glance over moving video.  A caller wanting another face passes its filename.
UI_FONT = "segoeuib.ttf"

# Palette, matching the shared_ui tokens the Qt HUDs drew with (RGB).  Mirrored
# rather than imported: shared_ui is Qt, so its tokens are QColors and these HUDs
# are Pillow.  Carried whole rather than trimmed to today's callers — the point of
# one palette is that the HUDs look alike, and a player reaching for its own blue
# is back to the ad-hoc literals this replaced.
BG_PRIMARY = (24, 24, 24)
BORDER_PANEL = (112, 119, 128)
BLUE = (48, 128, 224)
GREEN = (48, 160, 48)
RED = (255, 60, 60)
AMBER = (255, 200, 120)
TEXT_MUTED = (120, 120, 120)
TEXT_PRIMARY = (240, 240, 240)
WHITE = (255, 255, 255)

# Translucent enough to read the video through, opaque enough to read the text.
PANEL_ALPHA = 224
CORNER_RADIUS = 8


def px(points: int) -> int:
    """A Qt point size as pixels, at the standard 96 dpi Windows reports.

    These HUDs were laid out in Qt, which sizes type in points; Pillow sizes it
    in pixels, so every point size crosses this on its way to a font.
    """
    return round(points * 4 / 3)


def load_font(points: int, family: str = UI_FONT) -> ImageFont.FreeTypeFont:
    """*family* at *points*, or Pillow's own face when the machine lacks it.

    The HUD is redrawn while the video plays, so a missing face has to degrade to
    an ugly panel rather than raise into the run loop.
    """
    try:
        return ImageFont.truetype(family, px(points))
    except OSError:
        return ImageFont.load_default(px(points))


def text_width(font: ImageFont.FreeTypeFont, text: str) -> int:
    """How wide *text* draws in *font* — what a panel sizes itself against."""
    return int(font.getlength(text))


def to_bgra(image: Image.Image) -> np.ndarray:
    """An RGBA Pillow image as the contiguous BGRA array mpv's overlays take."""
    rgba = np.asarray(image, dtype=np.uint8)
    return np.ascontiguousarray(rgba[:, :, [2, 1, 0, 3]], dtype=np.uint8)


class HudPanel:
    """A rounded translucent slab to draw a HUD onto, and hand to mpv.

    Callers draw through :attr:`draw` and :attr:`image` — the panel is a surface,
    not a layout — and finish with :meth:`to_bgra`.
    """

    def __init__(self, width: int, height: int, *, alpha: int = PANEL_ALPHA) -> None:
        self.image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.draw.rounded_rectangle(
            [0, 0, width - 1, height - 1], radius=CORNER_RADIUS,
            fill=(*BG_PRIMARY, alpha), outline=(*BORDER_PANEL, 255), width=1,
        )

    def to_bgra(self) -> np.ndarray:
        return to_bgra(self.image)
