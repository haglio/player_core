"""Funscript parsing and the timing questions every scripted player asks of one.

A funscript is a JSON list of (time, position) actions authored against one
video.  Beyond parsing, this answers where sustained action begins (so the OSR2
rests through a long quiet lead-in instead of drifting toward it), whether a
given playhead sits in a quiet stretch (``is_resting_at`` — what the hybrid
handoff hands to Genau), where the action next picks up (``next_active_ms`` —
where a jump-to-the-action lands), plus loop-boundary snapping for A-B loops.
"""
from __future__ import annotations

import bisect
import json
from dataclasses import dataclass
from pathlib import Path


_BASE_THRESHOLD = 95
_MIN_LOOP_MS = 500

# How far a marked loop boundary may travel to land on a stroke base.  Snapping
# exists so the seam falls at the foot of a stroke rather than mid-stroke, and a
# stroke runs a few hundred milliseconds to about a second — so a base further
# out than this belongs to some other action, not to the stroke the mark landed
# in, and honoring the mark beats looping something nobody marked.
_SNAP_TOLERANCE_MS = 1000

# A funscript whose sustained action does not begin until at least this far in
# has a long enough quiet lead-in that the OSR2 should rest at its parked
# position rather than drift toward a still-distant action.  The same value
# doubles as the gap that marks a leading action as an isolated stray blip:
# real action is densely sampled, so the first action closely followed by
# another (gap below this) is where it truly begins.
_QUIET_LEAD_IN_MS = 5000

# The same number, public: it is also how far ahead of a cluster the hybrid
# handoff gives the device to the script (resting ends this far before the
# onset), so a drawer reconstructing where a handoff fell reads it from here
# rather than growing a second copy of the buffer.
QUIET_LEAD_IN_MS = _QUIET_LEAD_IN_MS

# How long the device takes to rise from its parked rest to a cluster's opening
# action: long enough to read as a deliberate approach rather than a twitch,
# short enough that it rests through nearly all of a long quiet stretch.
_RISE_MS = 1000

# How long the device takes to settle onto its park when whoever was driving
# lets go — the interval the waypoint driver's park command carries (and the
# broker's own park matches).  Public because the drive trace draws this glide:
# a plan that dropped to park in one sample was a cliff the device then took
# half a second to walk down.
PARK_SETTLE_MS = 500

# How long the device takes to walk between one driver's last position and the
# next one's first, at a hybrid handoff.  A couple of seconds: long enough to
# read as a hand-over rather than a jump, short enough to leave the device
# resting for most of the buffer.  Both directions use it — down onto the park
# when the script takes over, up to the stroke's floor when Genau does — so the
# two ramps are the same shape mirrored, which is what the buffer looks like.
HANDOFF_RAMP_MS = 2000

# How long the arbiter will wait, past a turn boundary, for a stroke whose
# floor rests ON the park to come down and touch it — the one case where the
# handoff needs no ramp at all: the blue swings on to its touch-down and the
# grey runs flat from there, so the device is set down exactly where the line
# ends.  Long enough for a slow stroke's whole cycle, short enough that a
# stroke that never comes down cannot stall the script.  Shared with the trace,
# which scans the same span for the same touch it draws the blue ending on.
PARK_TOUCH_WAIT_CAP_MS = 2500

# When the script gives the device back, relative to its cluster's last action.
# Not the same as the lead-in: the lead-in is long because the device needs a
# run-up to the opening action, while at this end the script is done and only
# has to be out of the way in time for the other driver's climb.  Sized so the
# climb lands exactly at the far end of the quiet, where the stroke has always
# resumed — the buffer keeps its shape (glide down, rest, climb) instead of
# either being spent on nothing or eaten whole by the ramp.
QUIET_LEAD_OUT_MS = QUIET_LEAD_IN_MS - HANDOFF_RAMP_MS

# Past any real playhead, so a turn's start alone orders it against a position
# in :meth:`Funscript.turn_bounds_at`'s bisect.
_MS_MAX = 1 << 62


@dataclass
class Funscript:
    actions: list[tuple[int, int]]

    def __post_init__(self) -> None:
        self._times = [a[0] for a in self.actions]
        self._dense_times = self._compute_dense_times()
        self._onsets = self._compute_onsets()
        self._turns = self._compute_turns()
        # The device's plan sampled on a fixed grid, for
        # :meth:`planned_trace_window` to take windows of.
        self._planned_grid_step: float | None = None
        self._planned_grid_values: tuple[float, ...] = ()

    @property
    def first_real_event_ms(self) -> int | None:
        """Onset of sustained action past a long quiet lead-in, else None.

        Returns the time of the first action that is closely followed by
        another (i.e. where dense action begins), skipping any isolated stray
        blips at the very start.  Returns None when action begins promptly, so
        callers drive from the top; otherwise the OSR2 rests at its parked
        position until this time.
        """
        if not self._onsets:
            return None
        onset = self._onsets[0]
        return onset if onset >= _QUIET_LEAD_IN_MS else None

    def is_parked_at(self, position_ms: int) -> bool:
        """Whether the device's plan at *position_ms* is its parked position.

        The neutral pose through every stretch the script is not actively
        stroking — the quiet lead-in, interior gaps, the tail past the last
        action — is the park, not wherever the last action happened to leave
        the device: it drops to park as a cluster ends and rises again
        ``_RISE_MS`` ahead of the next one, timed to meet its opening action.
        Inside a cluster it is never parked, and isolated stray blips out in
        the quiet stretches are noise the device sits out.
        """
        if not self._dense_times:
            return True
        i = bisect.bisect_left(self._dense_times, position_ms)
        nxt = self._dense_times[i] if i < len(self._dense_times) else None
        prv = self._dense_times[i - 1] if i > 0 else None
        if nxt is not None and nxt - position_ms <= _RISE_MS:
            return False
        # Between two dense actions of one cluster the device is mid-stroke;
        # between clusters (or past the last) it rests.
        return not (
            prv is not None and nxt is not None and nxt - prv < _QUIET_LEAD_IN_MS
        )

    def planned_position_at(self, position_ms: int) -> float:
        """Where the device is *planned* to be at *position_ms*, 0-100.

        The script's own motion through each dense cluster, the parked position
        through the quiet stretches, and a straight climb between them — from
        park at the foot of the rise to the cluster's opening action as it
        fires.  This is the line the waypoint driver walks, so a trace drawn
        from it is the device's coming motion rather than a picture the device
        contradicts (:meth:`position_at` holds the last position across gaps
        the device spends parked).
        """
        i = bisect.bisect_left(self._dense_times, position_ms)
        nxt = self._dense_times[i] if i < len(self._dense_times) else None
        prv = self._dense_times[i - 1] if i > 0 else None
        if self.is_parked_at(position_ms):
            if prv is not None and position_ms - prv < PARK_SETTLE_MS:
                # The drop out of a cluster is the driver's own park glide,
                # drawn: a straight descent from the last action onto the rest.
                return self.position_at(prv) * (1 - (position_ms - prv) / PARK_SETTLE_MS)
            return 0.0
        rising = (
            nxt is not None and position_ms < nxt
            and (prv is None or nxt - prv >= _QUIET_LEAD_IN_MS)
        )
        if rising:
            return self.position_at(nxt) * (1 - (nxt - position_ms) / _RISE_MS)
        return self.position_at(position_ms)

    def planned_trace_window(self, start_ms: int, span_ms: int, count: int,
                             ) -> tuple[tuple[float, ...], float]:
        """The device's plan as a picture: *count* + 1 knot samples covering
        *span_ms* from the knot at or before *start_ms*, as 0-1 heights, and how
        far past that knot *start_ms* sits as a fraction of one.

        The plan rather than the script's own interpolated line — parked through
        the quiet stretches, rising to meet each cluster, the script's shape
        inside one — so a trace drawn from it is the device's coming motion
        rather than a picture the device contradicts.

        The values are the fixed grid's own, never resampled and never blended:
        the script does not change while it plays, so its picture is computed
        once and reread, and the fraction goes to the drawer, which shifts the
        whole polyline left by it.  Reading the grid *at* the shifted positions
        instead morphed the heights at fixed columns every frame, so the shape
        changed while it moved.  The extra trailing sample is the knot just past
        the span's far edge, so the shifted line still reaches the border.  Past
        the end of the script the device rests at its park, so the picture does
        too."""
        if count <= 0 or not self.actions:
            return (), 0.0
        step = span_ms / max(1, count - 1)
        samples = count + 1
        if step <= 0:
            return (0.0,) * samples, 0.0
        grid = self._planned_grid(step)
        whole, frac = divmod(start_ms / step, 1)
        first = int(whole)
        return tuple(
            grid[first + i] if 0 <= first + i < len(grid) else 0.0
            for i in range(samples)
        ), frac

    def _planned_grid(self, step_ms: float) -> tuple[float, ...]:
        """The whole plan at one sample every *step_ms*, from zero, memoized."""
        if self._planned_grid_step != step_ms:
            last = self.actions[-1][0]
            count = int(last / step_ms) + 2 if step_ms > 0 else 1
            self._planned_grid_step = step_ms
            self._planned_grid_values = tuple(
                self.planned_position_at(round(i * step_ms)) / 100
                for i in range(count))
        return self._planned_grid_values

    def position_at(self, position_ms: int) -> float:
        """Where the script has the device at *position_ms*, 0-100.

        Interpolated between the surrounding actions and held flat outside them,
        the same motion the waypoint driver asks the OSR2 for.
        """
        if not self.actions:
            return 0.0
        index = bisect.bisect_right(self._times, position_ms) - 1
        if index < 0:
            return float(self.actions[0][1])
        if index >= len(self.actions) - 1:
            return float(self.actions[-1][1])
        (t0, p0), (t1, p1) = self.actions[index], self.actions[index + 1]
        if t1 <= t0:
            return float(p1)
        return p0 + (p1 - p0) * (position_ms - t0) / (t1 - t0)

    def next_active_ms(self, position_ms: int) -> int | None:
        """Where scripted action next starts up after *position_ms*, else None.

        The answer is the first stroke of the next dense cluster, not the buffer
        :meth:`is_resting_at` allows ahead of it: this is where a seek asking for
        the action lands, and landing in the buffer would leave several seconds
        of nothing on the near side of it.  A position inside a cluster is
        carried past that cluster to the one after — "next" is always forward,
        never the run already playing — and None means nothing scripted remains.
        """
        i = bisect.bisect_right(self._onsets, position_ms)
        return self._onsets[i] if i < len(self._onsets) else None

    def _compute_onsets(self) -> list[int]:
        """The start of each dense cluster: a dense time with no dense
        predecessor inside _QUIET_LEAD_IN_MS, i.e. the far side of a quiet
        stretch.  The first is where the script begins in earnest, which is what
        first_real_event_ms reports once it is far enough in to be worth parking
        for; the rest are where it resumes after each interior gap.
        """
        onsets: list[int] = []
        previous: int | None = None
        for t in self._dense_times:
            if previous is None or t - previous >= _QUIET_LEAD_IN_MS:
                onsets.append(t)
            previous = t
        return onsets

    def _compute_dense_times(self) -> list[int]:
        """Times of actions that belong to a dense cluster — those with a
        neighbour within _QUIET_LEAD_IN_MS.  Isolated stray blips are excluded,
        the same standard first_real_event_ms uses to find where action begins.
        """
        dense: list[int] = []
        for k, (t, _p) in enumerate(self.actions):
            prev_close = k > 0 and t - self.actions[k - 1][0] < _QUIET_LEAD_IN_MS
            next_close = (
                k + 1 < len(self.actions)
                and self.actions[k + 1][0] - t < _QUIET_LEAD_IN_MS
            )
            if prev_close or next_close:
                dense.append(t)
        return dense

    def _compute_turns(self) -> list[tuple[int, int]]:
        """The stretches the script holds the device for, in order.

        One per dense cluster, opened _QUIET_LEAD_IN_MS before its first action
        and closed QUIET_LEAD_OUT_MS after its last — early enough that the next
        driver's climb out of the park lands where the stroke has always
        resumed.

        Two clusters merge when their _QUIET_LEAD_IN_MS neighbourhoods overlap,
        which is the old rule and stays the old rule: whether the script gives
        the device back between two clusters is about whether there is room for
        the other driver to do anything, and that has not changed because the
        lead-out shortened.  Measured on the short lead-out instead, a six-second
        gap would open a turn of a few hundred milliseconds — a handoff there and
        back before anything could happen.
        """
        turns: list[list[int]] = []
        for t in self._dense_times:
            low, high = t - _QUIET_LEAD_IN_MS, t + QUIET_LEAD_OUT_MS
            if turns and low <= turns[-1][1] + (_QUIET_LEAD_IN_MS - QUIET_LEAD_OUT_MS):
                turns[-1][1] = high
            else:
                turns.append([low, high])
        return [(low, high) for low, high in turns]

    def turn_bounds_at(self, position_ms: int) -> tuple[int | None, int | None]:
        """When the stretch holding *position_ms* begins and ends, in ms.

        Whose stretch it is, is :meth:`is_resting_at` — this says only where it
        starts and stops, and None at either end means it runs past the edge of
        the video.  Whoever draws the handoff needs the *boundary*, not the
        classification: a ramp that walks the device between the park and a
        stroke has to be anchored to the moment the device changed hands, and
        anchored to anything recomputed per frame it slides around under its
        own picture.
        """
        index = bisect.bisect_right(self._turns, (position_ms, _MS_MAX)) - 1
        if index >= 0 and position_ms <= self._turns[index][1]:
            return self._turns[index]
        before = self._turns[index][1] if index >= 0 else None
        after = self._turns[index + 1][0] if index + 1 < len(self._turns) else None
        return (before, after)

    def is_resting_at(self, position_ms: int) -> bool:
        """True when position_ms sits outside every stretch the script holds the
        device for — a funscript's lead-in, an interior gap, the tail.

        In Hybrid the orchestrator hands these stretches to Genau; inside a turn
        the funscript drives.  Read straight off :meth:`turn_bounds_at`'s own
        turns rather than measured again here, because the two answers have to
        be the same answer: the arbiter flips the device on this, and the trace
        anchors its ramps to those bounds, so a rule stated twice is a seam that
        can disagree with the handoff it is drawing.
        """
        if not self._turns:
            return True
        index = bisect.bisect_right(self._turns, (position_ms, _MS_MAX)) - 1
        return not (index >= 0 and position_ms <= self._turns[index][1])


def snap_loop(fs: Funscript | None, in_ms: int, out_ms: int) -> tuple[int, int]:
    """The marked range as a loop: ordered, at least _MIN_LOOP_MS long, and each
    end pulled outward onto a nearby stroke base so the seam is not mid-stroke.

    A boundary with no base within _SNAP_TOLERANCE_MS keeps the time it was marked
    at.  Snapping was unbounded once, walking to whatever base came next and
    falling back to the script's own first and last action when a script never
    reached _BASE_THRESHOLD at all — so a five-second mark came back as a
    minutes-long range on about a fifth of a real library, and a range that long
    plays as no loop at all.
    """
    lo, hi = min(in_ms, out_ms), max(in_ms, out_ms)
    # Widen before snapping: both snaps only ever move a boundary outward, so a
    # mark shorter than a loop is lengthened here and stays long afterwards.
    hi = max(hi, lo + _MIN_LOOP_MS)
    # No funscript is simply nothing to snap to — a plain clip loop keeps its mark.
    actions = fs.actions if fs is not None else []
    bases = [t for t, p in actions if p >= _BASE_THRESHOLD]
    return _snap_back(bases, lo), _snap_forward(bases, hi)


def _snap_back(bases: list[int], boundary_ms: int) -> int:
    """*boundary_ms* pulled back to the latest base close enough behind it."""
    i = bisect.bisect_right(bases, boundary_ms)
    if i and boundary_ms - bases[i - 1] <= _SNAP_TOLERANCE_MS:
        return bases[i - 1]
    return boundary_ms


def _snap_forward(bases: list[int], boundary_ms: int) -> int:
    """*boundary_ms* pushed on to the earliest base close enough ahead of it."""
    i = bisect.bisect_left(bases, boundary_ms)
    if i < len(bases) and bases[i] - boundary_ms <= _SNAP_TOLERANCE_MS:
        return bases[i]
    return boundary_ms


def load(path: Path) -> Funscript:
    data = json.loads(path.read_text())
    raw = data["actions"]
    actions = sorted(((a["at"], a["pos"]) for a in raw), key=lambda a: a[0])
    return Funscript(actions=actions)
