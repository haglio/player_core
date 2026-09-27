from __future__ import annotations

from enum import StrEnum

__all__: list[str] = []

_SIDES = {"left": False, "right": True}
_ENDS = {"up": False, "down": True}


class HudCorner(StrEnum):
    UPPER_LEFT = "upper_left"
    UPPER_RIGHT = "upper_right"
    LOWER_RIGHT = "lower_right"
    LOWER_LEFT = "lower_left"

    @property
    def right(self) -> bool:
        return self in (HudCorner.UPPER_RIGHT, HudCorner.LOWER_RIGHT)

    @property
    def lower(self) -> bool:
        return self in (HudCorner.LOWER_RIGHT, HudCorner.LOWER_LEFT)

    def toward(self, direction: str) -> HudCorner:
        if direction in _SIDES:
            return _corner(right=_SIDES[direction], lower=self.lower)
        if direction in _ENDS:
            return _corner(right=self.right, lower=_ENDS[direction])
        return self

    def turned(self, *, clockwise: bool) -> HudCorner:
        return _next_round(_CORNERS_ROUND, self, clockwise=clockwise)


class HudEdge(StrEnum):
    UPPER = "upper"
    RIGHT = "right"
    LOWER = "lower"
    LEFT = "left"

    def toward(self, direction: str) -> HudEdge:
        return _EDGE_TOWARD.get(direction, self)

    def turned(self, *, clockwise: bool) -> HudEdge:
        return _next_round(tuple(HudEdge), self, clockwise=clockwise)


_EDGE_TOWARD = {"up": HudEdge.UPPER, "down": HudEdge.LOWER,
                "left": HudEdge.LEFT, "right": HudEdge.RIGHT}


def _corner(*, right: bool, lower: bool) -> HudCorner:
    if lower:
        return HudCorner.LOWER_RIGHT if right else HudCorner.LOWER_LEFT
    return HudCorner.UPPER_RIGHT if right else HudCorner.UPPER_LEFT


_CORNERS_ROUND = (HudCorner.UPPER_LEFT, HudCorner.UPPER_RIGHT,
                  HudCorner.LOWER_RIGHT, HudCorner.LOWER_LEFT)


def _next_round(ring, place, *, clockwise: bool):
    order = ring if clockwise else ring[::-1]
    return order[(order.index(place) + 1) % len(order)]


def block_x(corner: HudCorner, *, panel_width: int, extent: int, pad: int) -> int:
    if not corner.right:
        return pad
    return max(pad, panel_width - pad - extent)


def hud_origin(corner: HudCorner, *, panel: tuple[int, int], window: tuple[int, int],
               margin: int, lower_edge: int = 0) -> tuple[int, int]:
    panel_w, panel_h = panel
    win_w, win_h = window
    x = win_w - margin - panel_w if corner.right else margin
    y = win_h - lower_edge - margin - panel_h if corner.lower else margin
    return max(0, x), max(0, y)
