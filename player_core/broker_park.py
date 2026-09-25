from __future__ import annotations

from dataclasses import dataclass

from .funscript import PARK_SETTLE_MS

__all__: list[str] = []

BROKER_PARK_DELAY_MS = 1000


@dataclass(frozen=True)
class BrokerPark:
    from_height: float
    asked_at: float

    def height_at(self, now: float) -> float:
        gliding_s = max(0.0, now - self.asked_at - BROKER_PARK_DELAY_MS / 1000)
        return self.from_height * max(0.0, 1.0 - gliding_s / (PARK_SETTLE_MS / 1000))
