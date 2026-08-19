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

from shared_ui.icons_pil import paste_glyph

# Segoe UI Bold — every label on these HUDs is bold, because they are read at a
# glance over moving video.  A caller wanting another face passes its filename.
UI_FONT = "segoeuib.ttf"

# Palette, matching the shared_ui tokens the Qt HUDs drew with (RGB).  Mirrored
# rather than imported: shared_ui is Qt, so its tokens are QColors and these HUDs
# are Pillow.  Carried whole rather than trimmed to today's callers — the point of
# one palette is that the HUDs look alike, and a player reaching for its own blue
# is back to the ad-hoc literals this replaced.
BG_PRIMARY = (24, 24, 24)
BG_BUTTON = (62, 62, 62)         # a control at rest
BG_BUTTON_ACTIVE = (92, 92, 92)  # a control that is on
BORDER_PANEL = (120, 120, 120)
BLUE = (48, 128, 224)
GREEN = (48, 160, 48)
RED = (255, 60, 60)
AMBER = (255, 200, 120)
PINK = (200, 80, 160)
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


# Where each glyph's ink sits relative to the origin ``draw.text`` draws from,
# measured once per face+size+glyph.  A HUD uses a dozen glyphs and repaints them
# for the life of the session, so the probe below runs a handful of times.
_INK_OFFSETS: dict[tuple[str, int, str], tuple[float, float] | None] = {}


def _ink_center_offset(font: ImageFont.FreeTypeFont, glyph: str) -> tuple[float, float] | None:
    """The centre of *glyph*'s ink, offset from where ``draw.text`` starts it.

    Measured by drawing it, because nothing reported is the ink box:
    ``textbbox`` gives the layout box, whose bottom is the face's descender line
    however short the glyph — a minus sign reports nine pixels of empty space
    under it.  None when the glyph leaves no ink at all.
    """
    key = (str(getattr(font, "path", "")), int(getattr(font, "size", 0)), glyph)
    if key not in _INK_OFFSETS:
        pad = 8
        box = font.getbbox(glyph)
        probe = Image.new("L", (int(box[2]) + 2 * pad, int(box[3]) + 2 * pad), 0)
        ImageDraw.Draw(probe).text((pad, pad), glyph, font=font, fill=255)
        ink = probe.getbbox()
        _INK_OFFSETS[key] = None if ink is None else (
            (ink[0] + ink[2] - 1) / 2 - pad, (ink[1] + ink[3] - 1) / 2 - pad,
        )
    return _INK_OFFSETS[key]


def draw_glyph(draw: ImageDraw.ImageDraw, cx: float, cy: float, glyph: str,
               font: ImageFont.FreeTypeFont, fill) -> None:
    """Draw *glyph* centred on its own ink at ``(cx, cy)``.

    Pillow's ``anchor="mm"`` centres the font's ascent/descent box, not the mark
    inside it — and on the symbol faces these HUDs use, the mark sits high in a
    box that runs down to the descender.  Every icon button was therefore drawing
    its glyph two to six pixels low.  Centring the ink puts it where the eye
    expects it, whatever the glyph.
    """
    offset = _ink_center_offset(font, glyph)
    if offset is None:
        return
    draw.text((cx - offset[0], cy - offset[1]), glyph, font=font, fill=fill)


# How much room a mark leaves inside its button, so it does not run into the
# rounded border the button draws around it.
MARK_INSET = 2


def draw_mark(image: Image.Image, name: str, rect: tuple[int, int, int, int],
              fill) -> None:
    """One of the family's marks, centred in *rect*.

    The same drawing the apps' Qt chrome paints -- shared_ui holds the geometry
    and each side renders it -- so a trash can on a HUD is the trash can on
    Origenerator's toolbar rather than whatever character a symbol font had.
    Before this, a HUD mark was a typed glyph or a hand-drawn one, and the two
    sides drifted apart exactly as you would expect.

    Takes the panel's IMAGE rather than its pen, the way the drive readout does:
    the mark is supersampled and composited back, which a pen cannot carry.
    """
    x, y, w, h = rect
    paste_glyph(image, name,
                (x + MARK_INSET, y + MARK_INSET, w - 2 * MARK_INSET,
                 h - 2 * MARK_INSET),
                fill)


# The dot at the head of every HUD's status line, saying whether a bare, unaddressed
# command lands on this player.  Same size and same corner on all three, because a
# reader glancing across two screens is looking for one mark in one place.
ACTIVE_DOT = 10


def draw_active_dot(draw: ImageDraw.ImageDraw, x: int, y: int, active: bool) -> None:
    """The active-player dot, its top-left at ``(x, y)``.

    White while a bare command would land on this player, the palette's gray
    otherwise — and always drawn, never hidden.  An absent dot and an idle dot look
    the same, and then only the player that *has* the floor says anything, which is
    half an answer to a question asked of the room.
    """
    draw.ellipse([x, y, x + ACTIVE_DOT, y + ACTIVE_DOT],
                 fill=(*(WHITE if active else TEXT_MUTED), 255))


# The app marks, cell by cell.  Every icon in this family is a pink letter laid
# out on a five-by-five grid — the shape each app's own .ico carries — and a HUD
# that wants one draws it from the grid rather than loading the file: the .ico
# files live in the apps' own repos, and no app here may reach into another's.
# A letter set in the body face is not the same mark: it is a thin letterform
# where the icon is a chunky one, and it reads as a caption rather than a badge.
ICON_GRIDS = {
    "B": ("#####", "#...#", "#####", "#...#", "#####"),  # the OSR2 broker
    "F": ("#####", "#....", "#####", "#....", "#...."),  # F-mode
}


def draw_icon(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int],
              letter: str, fill=PINK) -> None:
    """Draw the app mark for *letter*, centred in *rect* and sized to fill it.

    The grid's blank cells are left alone rather than painted, so whatever is
    behind shows through the letter's counters — exactly as the .ico's own
    transparent cells let the panel under it through.
    """
    x, y, w, h = rect
    cell = max(1, min(w, h) // 7)
    left, top = x + (w - 5 * cell) / 2, y + (h - 5 * cell) / 2
    for row, line in enumerate(ICON_GRIDS[letter]):
        for column, painted in enumerate(line):
            if painted != "#":
                continue
            cx, cy = left + column * cell, top + row * cell
            draw.rectangle([cx, cy, cx + cell - 1, cy + cell - 1], fill=(*fill, 255))


# The tooltip box: the room around its words, how round its corner is, and how
# solid it sits over the slab it covers.
TOOLTIP_PAD = 5
TOOLTIP_RADIUS = 4
TOOLTIP_ALPHA = 240
_TOOLTIP_EDGE = 2           # the gap it keeps from the panel's own edge
_TOOLTIP_OFFSET = (14, 16)  # right of and below the cursor, clear of the pointer


def _wrap(font: ImageFont.FreeTypeFont, text: str, available: int) -> list[str]:
    """*text* broken on spaces into lines of at most *available* px.

    A word wider than *available* keeps its own line and overhangs — breaking
    mid-word would read as two words, and nothing named on these HUDs has one
    that long.
    """
    lines: list[str] = []
    for word in text.split():
        if lines and text_width(font, f"{lines[-1]} {word}") <= available:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def draw_tooltip(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, text: str,
                 pos: tuple[int, int], bounds: tuple[int, int]) -> tuple[int, int, int, int]:
    """Name a control in a box near *pos*, inside a panel *bounds* big, and return
    the box it drew.

    These HUDs are painted into the video, so there is no native tooltip to fall
    back on and every glyph on them is cryptic on purpose — this box *is* how a
    control says what it is.  Being part of the panel's own bitmap is also why it
    wraps rather than running on: whatever crosses the slab's edge is never drawn,
    so an over-wide tooltip loses its tail with nothing to say it had one.  The box
    is then nudged back inside the slab, so a control near an edge names itself
    inward instead of off it.
    """
    room = max(1, bounds[0] - 2 * (_TOOLTIP_EDGE + TOOLTIP_PAD))
    lines = _wrap(font, text, room)
    if not lines:
        return (0, 0, 0, 0)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    w = max(text_width(font, line) for line in lines) + 2 * TOOLTIP_PAD
    h = line_h * len(lines) + 2 * TOOLTIP_PAD
    x = max(_TOOLTIP_EDGE, min(pos[0] + _TOOLTIP_OFFSET[0], bounds[0] - w - _TOOLTIP_EDGE))
    y = max(_TOOLTIP_EDGE, min(pos[1] + _TOOLTIP_OFFSET[1], bounds[1] - h - _TOOLTIP_EDGE))
    draw.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=TOOLTIP_RADIUS,
                           fill=(*BG_PRIMARY, TOOLTIP_ALPHA),
                           outline=(*BORDER_PANEL, 255), width=1)
    for index, line in enumerate(lines):
        draw.text((x + w / 2, y + TOOLTIP_PAD + index * line_h + ascent), line,
                  font=font, anchor="ms", fill=(*TEXT_PRIMARY, 255))
    return (x, y, w, h)


def to_bgra(image: Image.Image) -> np.ndarray:
    """An RGBA Pillow image as the contiguous BGRA array mpv's overlays take."""
    rgba = np.asarray(image, dtype=np.uint8)
    return np.ascontiguousarray(rgba[:, :, [2, 1, 0, 3]], dtype=np.uint8)


class HudPanel:
    """A rounded translucent slab to draw a HUD onto, and hand to mpv.

    Callers draw through :attr:`draw` and :attr:`image` — the panel is a surface,
    not a layout — and finish with :meth:`to_bgra`.

    *ground* is the grey the slab is made of.  It defaults to the canvas colour,
    which is right where the panel floats over a video: the picture behind it is
    what it reads against, and a HUD the colour of a dark frame still reads as a
    panel over one.  A host that draws this on its own chrome instead has no
    picture behind it, and on a window painted that very grey the slab vanishes
    and leaves its one-pixel border outlining nothing — so it says which grey it
    wants, and gets a panel that sits on that window the way the window's own
    panels do.
    """

    def __init__(self, width: int, height: int, *, alpha: int = PANEL_ALPHA,
                 ground: tuple[int, int, int] = BG_PRIMARY) -> None:
        self.image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.draw.rounded_rectangle(
            [0, 0, width - 1, height - 1], radius=CORNER_RADIUS,
            fill=(*ground, alpha), outline=(*BORDER_PANEL, 255), width=1,
        )

    def to_bgra(self) -> np.ndarray:
        return to_bgra(self.image)
