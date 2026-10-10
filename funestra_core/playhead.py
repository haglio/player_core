"""The readout at the left end of every Funestra's timeline row: where the video is, and how long it runs."""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from PIL import Image, ImageDraw
from shared_ui.palette import TEXT_PRIMARY

from .hud_panel import KeptBitmap, ink_center_offset, load_font, text_width
from .hud_status import SEPARATOR
from .renamed import old_name_getter
from .volume import CHIP_H, MARGIN, chip_xy

__all__: list[str] = []

_RENAMED = {"clip_playhead": "flick_playhead"}

__getattr__ = old_name_getter(__name__, _RENAMED)

_TEXT_PT = 8


@dataclass(frozen=True)
class PlayheadHud:
    text: str
    widest: str


def _clock(ms: float, length_ms: float) -> str:
    length_s = int(length_ms // 1000)
    minutes, seconds = divmod(int(ms // 1000), 60)
    if length_s < 3600:
        return f"{minutes:0{len(str(length_s // 60))}d}:{seconds:02d}"
    hours, minutes = divmod(minutes, 60)
    return f"{hours:0{len(str(length_s // 3600))}d}:{minutes:02d}:{seconds:02d}"


def _video_text(position_ms: float, duration_ms: float, frame_rate: float) -> str:
    text = f"{_clock(position_ms, duration_ms)} / {_clock(duration_ms, duration_ms)}"
    if frame_rate > 0:
        text += f"{SEPARATOR}frame {round(position_ms / 1000 * frame_rate)}"
    return text


def video_playhead(position_ms: float, duration_ms: float, frame_rate: float) -> PlayheadHud | None:
    if duration_ms <= 0:
        return None
    return PlayheadHud(text=_video_text(position_ms, duration_ms, frame_rate),
                       widest=_video_text(duration_ms, duration_ms, frame_rate))


def flick_playhead(frame: int, frame_count: int) -> PlayheadHud | None:
    if frame_count <= 0:
        return None
    return PlayheadHud(text=f"frame {frame} / {frame_count}",
                       widest=f"frame {frame_count} / {frame_count}")


# The three below are what the Fun Time on main still imports of the row's old
# placement, kept only until its next lands -- which lays the row out through
# funestra_core.hud_row.row_layout and reaches none of them.
def lower_edge_height(win_w: int, *, timeline_h: int) -> int:
    return timeline_h


def readout_xy(readout_w: int, *, win_w: int, win_h: int, timeline_h: int) -> tuple[int, int]:
    return MARGIN, chip_xy(win_w=win_w, win_h=win_h, timeline_h=timeline_h)[1]


def on_readout(x: int, y: int, *, win_w: int, win_h: int, timeline_h: int) -> bool:
    return y >= win_h - timeline_h and x < MARGIN


@cache
def _font():
    return load_font(_TEXT_PT)


def readout_width(hud: PlayheadHud) -> int:
    """The room the readout takes on the row: its widest words' worth."""
    return text_width(_font(), hud.widest)


class PlayheadHudPainter(KeptBitmap):
    """The words alone, as tall as the chip and centered on the digits' ink."""

    def __init__(self) -> None:
        super().__init__()
        self._top = (CHIP_H - 1) / 2 - ink_center_offset(_font(), "0")[1]

    def _paint(self, hud: PlayheadHud) -> Image.Image:
        image = Image.new("RGBA", (readout_width(hud), CHIP_H), (0, 0, 0, 0))
        ImageDraw.Draw(image).text((0, self._top), hud.text, font=_font(),
                                   fill=(*TEXT_PRIMARY, 255))
        return image
