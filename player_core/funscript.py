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


@dataclass
class Funscript:
    actions: list[tuple[int, int]]

    def __post_init__(self) -> None:
        self._times = [a[0] for a in self.actions]
        self._dense_times = self._compute_dense_times()
        self._onsets = self._compute_onsets()

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

    def is_resting_at(self, position_ms: int) -> bool:
        """True when position_ms sits in a quiet stretch — no dense action
        within _QUIET_LEAD_IN_MS on either side (a funscript's lead-in or an
        interior gap).  In Hybrid the orchestrator hands these stretches to
        Genau; scripted stretches (not resting) drive the OSR2 from the
        funscript, and the buffer lets the script reclaim control before its
        next action fires.
        """
        if not self._dense_times:
            return True
        i = bisect.bisect_left(self._dense_times, position_ms)
        nearest = min(
            abs(self._dense_times[j] - position_ms)
            for j in (i - 1, i)
            if 0 <= j < len(self._dense_times)
        )
        return nearest > _QUIET_LEAD_IN_MS


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
