from __future__ import annotations

import logging
from pathlib import Path

from .clip_folder import flipped_record_for_clips_folder
from .file_channel import publish_whole

__all__: list[str] = []

logger = logging.getLogger(__name__)

HALF_A_LOOP = 0.5


def _record_of(clip: Path) -> Path:
    return flipped_record_for_clips_folder(clip.parent)


def _flipped_names(record: Path) -> set[str]:
    try:
        text = record.read_text(encoding="utf-8")
    except OSError:
        return set()
    return {line.strip() for line in text.splitlines() if line.strip()}


class ClipFlip:
    def __init__(self) -> None:
        self._clip: Path | None = None
        self.on = False

    def follow(self, clip: Path | None) -> None:
        if clip == self._clip:
            return
        self._clip = clip
        self.on = clip is not None and clip.name in _flipped_names(_record_of(clip))

    def applied_to(self, phase: float) -> float:
        return (phase + HALF_A_LOOP) % 1.0 if self.on else phase

    def toggle(self) -> None:
        if self._clip is None:
            return
        record = _record_of(self._clip)
        names = _flipped_names(record) ^ {self._clip.name}
        if not publish_whole(record, "".join(f"{name}\n" for name in sorted(names))):
            logger.warning("Could not save the flip of %s to %s", self._clip.name, record)
        self.on = self._clip.name in names
