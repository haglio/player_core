from __future__ import annotations

from player_core.ken_burns import Move, pan, zoom_in

DRIFT = pan(1.0, -1.0)
CREEP = zoom_in(0.5, 0.5)


class OneMove:
    def __init__(self, move: Move = DRIFT, *, from_rest: Move = CREEP) -> None:
        self.move = move
        self.rest_move = from_rest
        self.dealt = 0

    def deal(self) -> Move:
        self.dealt += 1
        return self.move

    def from_rest(self) -> Move:
        return self.rest_move
