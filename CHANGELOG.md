# Changelog

Dated notes on work that changes what is in this package rather than what it
does. Behaviour-preserving changes are recorded here when they remove a public
name, when they move a number the family is measured by, and when they turn up a
defect that is being left alone rather than fixed.

The comment ratio below is `(radon raw Comments + Multi) / SLOC` over
`player_core/` and `tools/`, the measure `audit/findings/player_core.md` set its
baseline with: **0.7692** over 3,661 SLOC, with 28 of 29 files above 0.25.

## 2026-08-25 — the painters pinned, the unadopted helpers deleted

**Pins.** All seven mutation survivors the audit recorded against this suite are
now killed: the two tooltip-bounds tests, the satellite's reset button, the drive
readout's numbers, the funscript park glide and lead-in boundary, cruise
control's stalled-clock cap, and `adjust_center`'s low edge with `HudClicks`'
double-click window. Each was confirmed by re-running the audit's own mutation in
a throwaway worktree, first against the old test (green, as recorded) and then
against the new one (red).

The audit's suggested fix for the drive readout — asserting `TEXT_PRIMARY` is
absent from the section's set of colours — does not work and was not used: the
values are 8px text, so no pixel of a digit lands on the ink exactly and the
section's brightest pixel with the numbers forced white is 235. The test reads
the number's own pixels instead.

**Deletions.**

| what went | source lines | comment ratio |
|---|---:|---|
| `Funscript.trace` / `trace_window` / `_grid` / `planned_trace` | −60 | 0.7692 → 0.7663 |
| `Funscript._window` and its now-constant `tail`, left behind by the above | −7 | 0.7663 → 0.7656 |
| `console.shares_the_device`, with three imports ruff F401 flagged | −13 | 0.7656 → 0.7648 |
| `timeline.rgba_to_bgra`, a third copy of a swizzle with no reference at all | −4 | 0.7648 → 0.7654 |
| `drive_readout._LESS`/`_MORE`, five unread re-exports, a stale `noqa`, a seven-line blank hole | −16 | 0.7654 → 0.7659 |
| Four keyword parameters no caller varies: `HudPanel(alpha=)`, `draw_icon(fill=)`, `_value(left=, right=)` with `label_pair_x(right=)`, `drive_layout.controls(prefix=)` | −9 | 0.7659 → 0.7668 |
| `drive_layout.hit` and two of the three `Rect` declarations, **adopted** into a new `geometry` module that four inline point-in-rect tests now call | −2 | 0.7668 → 0.7678 |
| `console_hud.DOT` and both hand-drawn active dots, **adopted** into `hud_panel.draw_active_dot` | −8 | 0.7678 → 0.7658 |
| `hud_panel.BG_BUTTON_ACTIVE` — **kept**, and the whole mirrored palette pinned against `shared_ui.colors` instead | 0 | 0.7658 → 0.7658 |
| Three spellings of the T-Code position range, **adopted** into `tcode.POSITION_MAX` and `tcode.to_tcode_position` | +8 | 0.7658 → 0.7646 |
| Both hand-written BOM strips in `file_channel`, **adopted** into `_read_command_text` | +2 | 0.7646 → 0.7656 |
