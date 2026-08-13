from __future__ import annotations

import bisect
import time

from .tcode import HandoffGlide, TCodeSink, format_tcode_command

from .funscript import Funscript

_RESEND_INTERVAL = 0.1
# Glide to the parked position over this long, matching the broker's own park.
_PARK_INTERVAL_MS = 500
# Sentinel "segment" for the parked state, distinct from -1 ("nothing sent yet").
_PARK_SEGMENT = -2


class FunscriptTCodeDriver:
    def __init__(self, sink: TCodeSink) -> None:
        self._sink = sink
        self._last_send_time: float = -1.0
        self._last_segment: int = -1
        # The device is wherever the other driver left it when this one takes
        # over, so its first waypoints glide rather than snap.  Armed by
        # :meth:`reset`, which is what a takeover already calls, and armed here
        # too: the first waypoint of a session starts from the broker's park.
        self._glide = HandoffGlide()
        self._glide.begin()

    def update(
        self, position_ms: int, fs: Funscript, *, now: float | None = None, speed: float = 1.0
    ) -> None:
        if now is None:
            now = time.monotonic()

        if fs.is_parked_at(position_ms):
            # The plan through every quiet stretch — the lead-in, interior gaps,
            # the tail past the last action — is the parked position: the
            # device's neutral is its rest, not wherever the last action left it
            # and not a drift toward one still seconds away.  The rise back out
            # is the waypoint below, which the plan arms a beat ahead of each
            # cluster so the device meets its opening action as it fires.
            self.park(now=now)
            return

        next_index = bisect.bisect_right(fs._times, position_ms)
        if self._should_send(next_index, now):
            self._send_waypoint(fs, next_index, position_ms, speed, now)
            self._mark_sent(next_index, now)

    def park(self, *, now: float | None = None) -> None:
        """Rest the OSR2 at its closest position (the same place the broker parks
        it on pause), holding there.

        Drives the OSR2 when there is nothing to script from — an unscripted
        video, or a funscript's quiet lead-in.  Edge-gated like a waypoint: sent
        once on entry, then refreshed on the resend interval against packet loss.
        """
        if now is None:
            now = time.monotonic()
        if self._should_send(_PARK_SEGMENT, now):
            # Already a glide, and a long one, so a takeover needs nothing extra.
            self._sink.send(format_tcode_command("L0", 0, _PARK_INTERVAL_MS))
            self._mark_sent(_PARK_SEGMENT, now)

    def _should_send(self, segment: int, now: float) -> bool:
        new_segment = segment != self._last_segment
        stale = (
            self._last_send_time >= 0
            and now - self._last_send_time >= _RESEND_INTERVAL
        )
        return new_segment or stale

    def _mark_sent(self, segment: int, now: float) -> None:
        self._last_segment = segment
        self._last_send_time = now

    def _send_waypoint(
        self, fs: Funscript, next_index: int, position_ms: int, speed: float, now: float
    ) -> None:
        """Aim at ``fs.actions[next_index]``, the first action still ahead.

        Ahead of the whole script that is the opening action itself, so a
        playhead approaching the script's start glides to where the script
        begins rather than skipping to where its first stroke ends.
        """
        if next_index < len(fs.actions):
            next_t, next_pos = fs.actions[next_index]
            # ``next_t - position_ms`` is the gap to the waypoint in *media* time;
            # the OSR2 executes its move in wall-clock time, so at playback rate
            # ``speed`` the move must finish in that many wall-milliseconds.
            remaining = max(1, round((next_t - position_ms) / speed))
            tcode_pos = round(next_pos * 9999 / 100)
            self._send(tcode_pos, remaining, now)
        else:
            _, pos = fs.actions[-1]
            tcode_pos = round(pos * 9999 / 100)
            self._send(tcode_pos, 100, now)

    def _send(self, position: int, interval_ms: int, now: float) -> None:
        """One waypoint, given the handoff's glide while one is running.

        The script's own timing runs a beat late for that stretch — the
        alternative is arriving on time by snapping there from wherever Genau's
        stroke had the device, which is the jolt this exists to remove.
        """
        self._sink.send(format_tcode_command(
            "L0", position, self._glide.interval_ms(interval_ms, now)))

    def reset(self) -> None:
        """Forget what was sent, and glide onto whatever comes next.

        A reset is what a takeover, a seek and a new video all do, and each of
        them leaves the device somewhere this script did not put it.
        """
        self._last_segment = -1
        self._last_send_time = -1.0
        self._glide.begin()

    def close(self) -> None:
        self._sink.close()
