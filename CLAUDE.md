# player_core — Project-Specific Instructions

Shared rules are in the global `~/.claude/CLAUDE.md`. This file contains only
player_core-specific overrides.

**Keep this file short.** No redundancy with the global CLAUDE.md. One bullet
per rule. If editing this file, remove or consolidate — never just append.

## Running tests

This repo has no venv of its own. Use a consumer's — both have this package
installed editable:

```bash
"C:/path/to/suite-root/projects/genau/.venv/Scripts/python.exe" -m pytest tests/
```

## Installing

Always `--config-settings editable_mode=compat`; the README says why, and
`tests/test_install.py` goes red if a venv is ever reinstalled without it.

## What belongs here

- **Only what a second repo needs.** A module earns a place here once both
  `../genau` and `../fun_time` import it. Until then it stays with the app that
  owns it — a "core" that accumulates one app's code is the coupling this repo
  exists to undo.
- **No app knows another app exists.** Nothing here may import `nau`, `genau`,
  `satellite` or `fun_time`, and nothing here may be shaped around one caller's
  needs. `StatusWriter` takes a `fields` callable rather than hardcoding either
  player's keys for exactly this reason.

## Changing this repo changes three apps

- A change here lands in `../genau` and `../fun_time` the moment it is saved —
  they install this editable, so there is no version to bump and no release to
  cut, and equally no buffer against a mistake.
- **Run all three suites before merging**: this one, genau's unit suite, and
  fun_time's unit *and* hidden-desktop integration suites (the last is what
  actually launches `MpvPlayer` against the real DLL).
- **No dead-code scan here, on purpose.** Every caller of this package lives in
  another repo, so vulture flags the entire public API and the whitelist needed
  to silence it would just restate that API — a guard that can never fail.
  "Is this still used?" is answered by the consumers' own scans; don't add one
  back.

## libmpv changes: mandatory pre-flight

`MpvPlayer` is the one place this family touches libmpv. Before modifying any
mpv property or command, state the mechanism (why the approach works, citing the
specific mpv behavior), verify it rather than guessing, and name which of the
three apps' run loops the change touches. If you cannot, stop and say so — do
not submit a speculative fix.
