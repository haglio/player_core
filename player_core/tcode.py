"""The T-Code wire format and its UDP transport, shared by every OSR2 driver.

T-Code is the one-line command language the OSR2 broker's UDP inlet accepts
(``L0<pos>I<ms>``: move the linear axis to *pos* over *ms* milliseconds).  Both
driver styles in this family speak it — Genau's phase-driven stroke sender and
the funscript waypoint driver (:mod:`player_core.tcode_driver`) — so the format
and the datagram sink live here, beneath both.  What to send and when stays
with each driver; this module only says it correctly.
"""
from __future__ import annotations

import socket
from typing import Protocol


def format_tcode_command(axis: str, position: int, interval_ms: int) -> str:
    position = max(0, min(9999, position))
    interval_ms = max(0, interval_ms)
    return f"{axis}{position:04d}I{interval_ms}"


class TCodeSink(Protocol):
    def send(self, command: str) -> None: ...
    def close(self) -> None: ...


class UdpTCodeSink:
    def __init__(self, host: str = "127.0.0.1", port: int = 50557, *, sock=None) -> None:
        self._host = host
        self._port = port
        self._sock = sock if sock is not None else socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, command: str) -> None:
        self._sock.sendto((command + "\n").encode("ascii"), (self._host, self._port))

    def close(self) -> None:
        self._sock.close()
