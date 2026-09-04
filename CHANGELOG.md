# Changelog

Dated notes on work that changes what is in this package rather than what it
does. Behaviour-preserving changes are recorded here when they remove a public
name, when they move a number the family is measured by, and when they turn up a
defect that is being left alone rather than fixed.

The comment ratio below is `(radon raw Comments + Multi) / SLOC` over
`player_core/` and `tools/`, the measure `audit/findings/player_core.md` set its
baseline with: **0.7692** over 3,661 SLOC, with 28 of 29 files above 0.25.

## 2026-09-04 — Genau's engine moves in, for the headset

Everything Genau does that is not its pygame window now lives here, so Fun
Time's VR player can run the same clip player in-process for its genau mode
and GenauVR, a second copy of most of it, can go. Twenty-one modules and their
tests came over from `../genau`; nothing already here changed but `robot_hand`,
which took the hand's control limits. The names moved with the responsibility:

| was, in `genau/` | is, here |
| --- | --- |
| `engine` (`PlaybackEngine`, `update_engine`), `refresh_logic.Beat` | `robot_hand_beat` (`BeatEngine`, `advance_beat`, `Beat`) |
| `tcode` (`RateLimitedTCodeSender`), `device_handoff` | `robot_hand_driver` (`RobotHandTCodeDriver`, `DeviceHandoff`) |
| `limits` | `robot_hand` (`ControlLimits`, `control_limits`) |
| `state` (`SharedState`), `refresh_logic.read_shared_state_snapshot` | `broker_feed` (`BrokerFeed`, `BrokerSnapshot`, `snapshot`) |
| `controls`, `runtime_commands` | `genau_controls` (registry, `VERBS`, `KEYS`, `apply_runtime_command`) |
| `refresh_controller` | `genau_refresh` |
| `drive_readout` (`DriveReadout`) | `genau_readout` (`GenauReadout`) |
| `status_writer` | `genau_status` (with the status file's name) |
| `notifier` | `genau_notifier` |
| `video`, `weird` | `clip_folder` (the scan, and the piles beside the folder) and `clip_decode` (ffmpeg, and the frame cache) |
| `frame_cache` | `clip_decode`, reading WebP through Pillow rather than cv2 |
| `clip_runtime`, `cache_utils` | `clip_cache` |
| `refresh_logic.display_index_for_phase` | `clip_renderer` |
| `first_clip` | `clip_preload` |
| `control_registry`, `flags`, `tick_failures` | `control_registry`, `flag`, `tick_failures` |
| `clip_advance`, `clip_sequence`, `clip_selection`, `clip_loader`, `clip_renderer` | the same names |

The two class renames say what the things are beside what was already here:
the engine is the beat the hand strokes to, not playback, and its sender is the
Robot Hand's T-Code driver, the mirror of the funscript's.

**Two dependencies moved with it.** cv2 did not come: `.rhcache` frames are
WebP and Pillow reads them, so the one reader that needed OpenCV is gone from
the family's shared code. `app_support` now is imported at run time, for the
first time here — `clip_decode` launches ffmpeg through its hidden-subprocess
kwargs — where before only the test plugin reached it; every consumer's venv
already has it, and the merge gate already installs it.

**The consumer gate carries 61 waiting names.** Nothing imports the engine from
here until genau's window switches to it and Fun Time's VR player takes it up;
both are the next landings on this branch line, and each takes its lines out
of `tests/no_consumer_imports.txt` as it does.

**The comment ratio falls because the denominator grew: 0.7704 → 0.6416** over
`player_core/` and `tools/`, SLOC 3,310 → 4,897, files 29 → 50. The engine
arrives at the density genau kept it at, and nothing measured before this
changed.

## 2026-08-31 — the sanitize toolchain leaves `tools/` (item 44 stage 2)

`tools/sanitize_guard.py` and `tools/__init__.py` are gone; the guard is
`app_support.sanitize`, installed with the package, and `tools/githooks/` holds
the two shims that run it. `tests/test_sanitize_guard.py` is gone too -- its
fifty-nine unit cases live in app_support now, and the one case whose subject is
this checkout arrives from `app_support.sanitize.pytest_plugin`, named once in
`pyproject.toml`. The merge gate installs app_support for that line; nothing
under `player_core/` imports it.

**The comment ratio moves because its denominator did: 0.7447 → 0.7532** over
`player_core/` and `tools/`, SLOC 3,415 → 3,270, files 31 → 29. Not a comment
was added or removed here; the two files that left were the least-commented in
the measured set. The 0.7692/3,661 in this file's header is the audit's baseline
and predates both this and the harvester's removal.

**One behaviour change, in the hooks.** The `[ -n "$python" ] || exit 0` escape
is gone. While the guard was a file in this repo it ran off any interpreter, so
"cannot run" meant "no python at all"; as an installed package it means "not
installed in the interpreter this hook found", which is a checkout that has
silently stopped being guarded. Measured through a real `git commit`: with no
python on PATH the old hooks committed a blocked term (exit 0), these refuse it.
The four cases that matter -- a staged term, a term in the message, a clean
commit, a checkout with no blocklist -- behave exactly as before.

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
| An unreachable fallback return, an empty `pass` branch and two function-local `numpy` imports | −6 | 0.7656 → 0.7669 |

Net: 3,661 → 3,616 SLOC, 0.7692 → 0.7669. Two helpers the audit called
unadopted were adopted rather than deleted, which is why the line count moves
less than the deletion list suggests.

`tools/` was untouched throughout the item itself: `sanitize_guard.py` and
`githooks/install.py` are maintained byte-identical across eleven checkouts, so
their stale `noqa` and their comment ratios (0.55 / 0.31) belong to the
cross-repo consolidation rather than to this repo on its own. The third file
there, `harvest_blocklist.py`, was deleted afterwards on the owner's
instruction — see below.

**Comments.** Worked file by file against the retained-comments list in
`audit/findings/player_core.md`, which is the floor: every range it marks *keep*
is still there, whole. Nothing was stripped off opaque code — each cut either
corrected a statement that was false, deleted a second copy of a rule stated
elsewhere, replaced a section-heading comment with a function of that name, or
kept the invariant a war story was protecting and dropped the story.

| what changed | comment ratio |
|---|---|
| Stale docs: `mpv_player` "not unit-tested", "three applications", the README's six-of-27 module list | 0.7669 → 0.7658 |
| Six comments describing things that are not there (see the commit for each) | 0.7658 → 0.7630 |
| The symbol face named once in `hud_panel` instead of three times, and the glyph notes that named the wrong glyphs | 0.7630 → 0.7590 |
| `funscript`'s three bounds explained by the incident that set them | 0.7590 → 0.7579 |
| `HudRenderer.render`'s section headings became `_draw_status_band` and `_draw_mode_row` | 0.7579 → 0.7528 |
| `ConsolePainter._paint`'s top block became `_draw_top_block` (CC 18 → 15) | 0.7528 → 0.7525 |
| The console's eight histories cut to the rules they guarded | 0.7525 → 0.7439 |
| The drive readout's five attempts, and `drive_layout`'s and `tcode`'s | 0.7439 → 0.7403 |
| The satellite explaining itself by the dashboard it replaced, thirteen times | 0.7403 → 0.7364 |
| Seventeen more across nine files with one war story each | 0.7364 → 0.7267 |

**Where it ended: 0.7692 → 0.7267 over 3,626 SLOC.** The audit counted 21 "used
to" lines across seven modules; four remain, and three of those are on the
retained list or state a live fact about Qt rather than about this code.

Every rendered panel is byte-identical to `bb4c790`, the commit the audit
measured: 22 of them — three console modes with and without hover, both
satellite sides across the mode row and the subtitle, and both empty shells.
Every comment-only commit was checked by parsing the file before and after and
comparing the syntax trees with docstrings stripped, so no expression, constant
or branch moved in any of them.

**The floor held, with four deliberate exceptions.** Of the 278 retained ranges,
269 are word-for-word what they were. Four were reworded because a *different*
finding in the same bundle required it, and each keeps its mechanism:

- `drive_layout.py:11-15` — "kept apart from the painters" is singular now, and
  "both toolkits' panels" is gone, because `dead/011` established there is one
  painter. The reason the layout is kept apart — a wrong hit target still looks
  right — is untouched.
- `drive_layout.py:182-189` — the `prefix` paragraph went with the parameter
  (`dead/008`); the rest of the docstring stands.
- `direct_control.py:33` — the "A T-Code stroke position" note moved to
  `tcode.py` with `POSITION_MAX` itself (`design/010`).
- `wave_stack.py:142-147` — the reference to `player_core`'s own
  `_recompute_center` from inside `player_core` went (`dead/013`); what it
  described, the centre giving way as the amplitude opens past it, stays.

The other five the checker flags are boundary artifacts: a range that begins
mid-sentence in a narrative the audit separately asked to delete, or one whose
note already said *first sentence* or *minus the genau reference*.

### The blocklist harvester, removed

`tools/harvest_blocklist.py` and `tests/test_harvest_blocklist.py` are gone, on
the owner's instruction and outside the scope of item 13.

The blocklist is a curated list of domain terms, written by hand to keep the
nature of this suite out of a public repo. The harvester learned terms off the
media library instead and merged them in, which is how the machine-generated
list now sitting in these checkouts came to exist — and that list is why
publication is frozen. A tool that rewrites a hand-curated secret is not a tool
whose first-run crash wants fixing.

That crash was `player_core/all/dead/025`, filed in the audit's bugs register
and recorded here as found-and-not-fixed while the item ran. It is moot: the
file is gone. The finding should be closed as withdrawn rather than carried into
the cross-repo consolidation, and item 44's plan to publish `tools/` from
`app_support` should drop `app_support/app_support/sanitize/harvest.py` with it.

`tools/sanitize_guard.py` is untouched and unweakened. It never referenced the
harvester: it reads the blocklist and refuses a staged term, which is the half
that does the protecting.

### Still open from this item

The ratio is reported here, not gated, and `player_core` still has no dead-code
scan, by design. What this arc did not take from the bundle: the test-suite
findings beyond the seven mutation survivors — the private names asserted on
across seven files, the near-duplicate tests, the missing `tests/conftest.py`,
and the two guard tests coupled to the real checkout. Those are the suite's
shape rather than its trustworthiness; the seven probes that could not fail
now do.
