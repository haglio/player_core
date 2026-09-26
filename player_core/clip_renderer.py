"""Which frame of the clip on screen is up, and putting a chosen one up.

The renderer knows the clip and the frame index; the surface it draws on is the
shell's, reached through the one ``blit_frame`` callable it is built with, so
the same renderer serves a pygame window and a headset texture.
"""
from __future__ import annotations

from pathlib import Path

__all__ = [
    "ClipRenderController",
]

def display_index_for_phase(phase: float, frame_count: int) -> int:
    logical_index = min(int(phase * frame_count), frame_count - 1)
    return (frame_count - 1) - logical_index


class ClipRenderController:
    def __init__(
        self,
        *,
        clip_store,
        blit_frame,
    ):
        self.clip_store = clip_store
        self.blit_frame = blit_frame
        self.current_clip_path: Path | None = None
        self.current_frame_index: int | None = None

    def set_current_clip_path(self, path: Path | None) -> None:
        self.current_clip_path = path
        self.current_frame_index = None

    def current_clip_entry(self):
        path = self.current_clip_path
        if path is None or path not in self.clip_store.clip_cache:
            return None
        return self.clip_store.clip_cache.get(path)

    @property
    def portrait(self) -> bool | None:
        entry = self.current_clip_entry()
        if entry is None or not entry["frames"]:
            return None
        height, width = entry["frames"][0].shape[:2]
        return height > width

    def prepare_active_clip_for_current_size(self) -> None:
        path = self.current_clip_path
        if path is None or path not in self.clip_store.clip_cache:
            return

        entry = self.clip_store.clip_entry_for(path)
        if entry["frames"]:
            self.show_frame_at(0)

    def show_frame_at(self, index: int) -> bool:
        """Put frame *index* of the clip on screen, or say there was none.

        Named for the choice rather than the drawing: the view's own
        ``blit_frame`` takes an image, and one name for both would leave a call
        site not saying which of the two it meant.
        """
        path = self.current_clip_path
        if path is None or path not in self.clip_store.clip_cache:
            return False

        entry = self.clip_store.clip_entry_for(path)
        frames = entry["frames"]
        if not frames or index < 0 or index >= len(frames):
            return False

        if self.current_frame_index != index:
            self.blit_frame(frames[index])
            self.current_frame_index = index
        return True
