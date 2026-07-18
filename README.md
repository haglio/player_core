# player_core

The shared playback core behind the video players in this project family.

Three standalone applications embed a video player and are driven by an
orchestrator through files on disk:

| App | Repo | Launched as |
| --- | --- | --- |
| Nau | `../genau` | `python -m nau` |
| Genau | `../genau` | `python -m genau` |
| Fun Time's satellites | `../fun_time` | `python -m satellite` |

Everything they had to agree on lives here, so none of them has to import
another application's internals to get it:

- **`mpv_player`** — `MpvPlayer`, the libmpv wrapper. GPU-decoded playback
  rendered into a window the caller owns (`wid`), plus the playlist lookahead,
  A/B looping and BGRA overlay compositing the players drive.
- **`libmpv_loader`** — puts the vendored `libmpv-2.dll` on `%PATH%` before
  `import mpv`, which is the only way python-mpv finds it on Windows.
- **`playlist`** — the playlist file format Fun Time writes and both players read.
- **`file_channel`** — the command file and paused flag file an orchestrator
  steers a player through.
- **`status`** — the throttled status file a player publishes back.

Nothing app-specific belongs here. A module earns a place only once a second
repo needs it; until then it stays with the app that owns it.

## Install

Each consuming project installs this editable into its own venv, from a local
path — this package is never published, so it must not appear in any project's
`[project.dependencies]`:

```bash
# from ../genau
".venv/Scripts/python.exe" -m pip install -e ../player_core --config-settings editable_mode=compat

# from ../fun_time
".venv/Scripts/python.exe" -m pip install -e ../player_core --config-settings editable_mode=compat
```

**`editable_mode=compat` is required, not cosmetic.** This repo's directory is
named `player_core`, the same as the package inside it, and the directory that
holds all these repos is itself on `sys.path` in fun_time's venv (via its
`shared_ui.pth`). Setuptools' *default* editable install resolves the top-level
name through a meta-path finder that `PathFinder` never reaches, so the repo
root wins as an implicit namespace package: submodules still import, but
`player_core/__init__.py` never runs. `compat` mode puts the repo root on
`sys.path` instead, where a real package beats a namespace portion.
`tests/test_install.py` fails loudly if this is ever reinstalled the other way.

## libmpv

`vendor/libmpv-2.dll` (~117 MB) is **not committed**. Fetch it once into
`vendor/`; every app resolves the DLL through this one copy, because
`libmpv_loader` looks beside the installed package rather than inside each
consuming repo.

Grab the libmpv dev build for Windows x86_64 and copy `libmpv-2.dll` out of it
into `vendor/`.

## Tests

```bash
".venv/Scripts/python.exe" -m pytest tests/
```

There is no venv in this repo — run the suite with either consumer's venv, both
of which have this package installed. `MpvPlayer` itself is not unit-tested: it
needs the DLL and a real window, and is exercised by Fun Time's hidden-desktop
integration suite, which launches the real player.
