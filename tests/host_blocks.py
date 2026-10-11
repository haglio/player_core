from __future__ import annotations

from collections.abc import Callable

RED_BAND = (200, 40, 30)


class Band:
    height = 18
    least_width = 120

    def __init__(self, color: tuple[int, int, int] = RED_BAND, *,
                 landed: Callable[[tuple], None] | None = None) -> None:
        self.color = color
        self._landed = landed

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Band) and other.color == self.color

    def __hash__(self) -> int:
        return hash(self.color)

    def draw(self, image, rect) -> None:
        if self._landed is not None:
            self._landed(rect)
        x, y, width, height = rect
        image.paste((*self.color, 255), (x, y, x + width, y + height))


class HostsBlock:
    def __init__(self) -> None:
        self.drawn_at: tuple | None = None
        self.presses: list[tuple[int, int, tuple | None]] = []
        self.drags: list[tuple[int, int, tuple | None]] = []
        self.holding = False

    def drawing(self) -> Band:
        return Band(landed=self._landed)

    def _landed(self, rect: tuple) -> None:
        self.drawn_at = rect

    def press(self, px: int, py: int, *, rect) -> bool:
        self.presses.append((px, py, rect))
        self.holding = rect is not None and (rect[0] <= px < rect[0] + rect[2]
                                             and rect[1] <= py < rect[1] + rect[3])
        return self.holding

    def drag_to(self, px: int, py: int, *, rect) -> bool:
        if self.holding:
            self.drags.append((px, py, rect))
        return self.holding

    def release(self) -> None:
        self.holding = False
