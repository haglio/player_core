# player_core — Project-Specific Instructions

Shared rules are in the global `~/.claude/CLAUDE.md`. This file contains only
player_core-specific overrides.

**Keep this file short.** No redundancy with the global CLAUDE.md. One bullet
per rule. If editing this file, remove or consolidate — never just append.

## Running tests

This repo has no venv of its own. Use a consumer's — both have this package
installed editable:

```bash
"C:/path/to/genau/.venv/Scripts/python.exe" -m pytest tests/
```

## Installing

Always `--config-settings editable_mode=compat`; the README says why, and
`tests/test_install.py` goes red if a venv is ever reinstalled without it.

## Worktrees lack the DLL

`vendor/libmpv-2.dll` is fetched, not tracked, so a fresh worktree has no
`vendor/` and anything importing `MpvPlayer` through that worktree — a consumer
suite pointed at it, or a fun_time verification session naming it in
`genau_project_dirs` — dies on load. Copy the DLL in from the primary's
`vendor/` first.

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
- **No vulture scan here, on purpose — the gate reads the consumers instead.**
  Every caller of this package lives in another repo, so vulture flags the entire
  public API and the whitelist needed to silence it would just restate that API:
  a guard that can never fail. Don't add one back.
  `tests/test_consumer_imports.py` asks the question the consumers can answer —
  every public name must be imported by some sibling checkout, with
  `tests/no_consumer_imports.txt` holding the ones that are not yet. It needs
  those checkouts on disk and skips rather than passes without them, so a public
  clone and CI both skip it and this machine is where it bites.

## libmpv changes: mandatory pre-flight

`MpvPlayer` is the one place this family touches libmpv. Before modifying any
mpv property or command, state the mechanism (why the approach works, citing the
specific mpv behavior), verify it rather than guessing, and name which of the
three apps' run loops the change touches. If you cannot, stop and say so — do
not submit a speculative fix.

## Test fixtures must be fabricated, never copied from the real library

Every fixture value that stands in for library data — a video title, a filename,
a performer or studio name, prompt text — must be **invented**. Never paste a
real one out of the media library to make a test feel realistic.

This is not a style note. It is the single thing that has actually leaked private
data into these repos: an agent writing a test reached for a real filename or
performer name because it was handy, and it rode into a public commit. Nothing in
the app's *design* pulls library text into source — the library lives outside
every repo, read at runtime through the git-ignored overlays — so this habit is
the only remaining path for a real name to get committed, and the only thing
stopping it is you following this rule.

Do not lean on the sanitize guard to catch it. `app_support.sanitize` fails
the suite when a **known** blocked term appears in the tracked tree, but a brand-
new performer name it has never seen passes every check and lands. The guard is a
backstop for names already known; it cannot see the next one.

So fabricate fully. Use `Jane Doe`, `Example Studio`, `scene one`, the
`alpha`/`beta`/`gamma` act placeholders the committed `content.example.json`
already uses. The near miss that still counts: taking a real filename and
changing a character or two — it is still that clip, still that performer. Make
it up from scratch, don't lightly edit a real one.

## Landing — GitHub merge queue, not local ff-merge

This repo is public at `github.com/haglio/player_core` with a merge-queue ruleset on
`main`, so the global "ff-merge into the primary checkout under
`.git/agent-merge.lock`" flow does NOT apply here:

- **Land through a pull request.** From your worktree: commit, `git fetch origin
  && git rebase origin/main`, `git push -u origin <branch>`, then
  `gh pr create --fill`. Auto-merge arms itself; the queue rebases your PR onto
  `main`, runs the required check, and merges it when green. Don't ff-merge into
  the primary checkout, don't push `main` directly, and never force-push `main`.
- **The `.git/agent-merge.lock` is retired here** — the GitHub queue serializes.
- **Sync local checkouts by pulling.** `main` advances only on origin (via the
  queue), so the primary checkout and worktrees update with
  `git pull --ff-only origin main`; the running app self-updates the same way.
  The primary is only ever fast-forwarded — never reset or merged-into.
- **A red required check** (`.github/workflows/merge-gate.yml`) can't land.

Everything else in the global CLAUDE.md — work in a worktree, green tests before
you push, clean handoff — still applies.
