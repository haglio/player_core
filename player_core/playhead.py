"""The readout at the left end of every player's timeline row: where the video is, and how long it runs."""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image
from shared_ui.palette import TEXT_PRIMARY

from .hud_panel import KeptBitmap, ink_center_offset, load_font, pill, text_width
from .hud_status import SEPARATOR
from .volume import CHIP_H, PAD

__all__: list[str] = []

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


def clip_playhead(frame: int, frame_count: int) -> PlayheadHud | None:
    if frame_count <= 0:
        return None
    return PlayheadHud(text=f"frame {frame} / {frame_count}",
                       widest=f"frame {frame_count} / {frame_count}")


class PlayheadHudPainter(KeptBitmap):
    def __init__(self) -> None:
        super().__init__()
        self._font = load_font(_TEXT_PT)
        self._top = (CHIP_H - 1) / 2 - ink_center_offset(self._font, "0")[1]

    def _paint(self, hud: PlayheadHud) -> Image.Image:
        image, draw = pill(text_width(self._font, hud.widest) + 2 * PAD, CHIP_H)
        draw.text((PAD, self._top), hud.text, font=self._font, fill=(*TEXT_PRIMARY, 255))
        return image
