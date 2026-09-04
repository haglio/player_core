# player_core

The shared playback core behind the video players in this project family.

Six players and hosts across three repos read it. Four of them embed a video
player and are driven by an orchestrator through files on disk; the other two
take the HUDs and the stroke without the player.

| Consumer | Repo | What it takes |
| --- | --- | --- |
| Nau | `../genau` | the player, the console, the drive readout, the T-Code driver |
| Genau | `../genau` | the clip player's whole engine, under its pygame window |
| Fun Time's satellites | `../fun_time` | the player, the satellite HUD |
| Fun Time's VR player | `../fun_time` | the offscreen player, the T-Code driver, and the clip player's engine for its genau mode |
| Fun Time itself | `../fun_time` | the file channel, the playlist, the status line |
| Origenerator | `../origenerator` | the console and the drive readout, over its slideshows |

Everything they had to agree on lives here, so none of them has to import
another application's internals to get it. By what it is:

- **the engine** — `mpv_player`, its offscreen twin `render_player`, and the
  `libmpv_loader` that puts the vendored DLL on `%PATH%` first, which is the
  only way python-mpv finds it on Windows.
- **the files an orchestrator steers through** — `playlist`, `file_channel`
  (the command queue and the paused flag), `status` (what a player publishes
  back).
- **the device** — `tcode` and `tcode_driver` for the wire, `funscript` for a
  script and the questions asked of one, and for a stroke of this family's own:
  `robot_hand` (the waveform), `robot_hand_beat` (the phase it runs at),
  `robot_hand_driver` (the stroke on the wire, and the device changing hands),
  `wave_stack` / `cruise_control` (the stroke varying itself), `broker_feed`
  (the beat the OSR2 broker publishes when it has the room).
- **the clip player** — Genau, wherever it is drawn: `clip_folder`,
  `clip_decode`, `clip_cache`, `clip_loader`, `clip_preload`, `clip_sequence`,
  `clip_selection`, `clip_advance`, `clip_renderer` and `clip_scrub` get a clip
  from a folder to the frame the stroke is at, and `genau_controls`,
  `genau_refresh`, `genau_readout`, `genau_status` and `genau_notifier` are its
  verbs, its tick, and what it publishes. A shell — Genau's pygame window, Fun
  Time's headset — supplies the surface, the loop and the keys.
- **the chrome and what is drawn on it** — `hud_panel`, `hud_marks`,
  `geometry`, `timeline`, `volume`, `hud_status`, and then a model and a
  painter per HUD: `console` / `console_hud`, `drive_layout` / `drive_readout`,
  `satellite_hud` / `satellite_hud_paint`.
- **the window** — `sdl_hints` and `taskbar`, the two Win32 facts every player
  here has to get right before it opens one.
- **the loop** — `control_registry` (how any player declares a control and the
  verb and key that move it), `flag` (a bit two parts of an app share, with its
  edge), `tick_failures` (a frame loop's fault, said once).

Nothing app-specific belongs here. A module earns a place only once a second
repo needs it; until then it stays with the app that owns it. Genau's engine is
here because two shells run it: Genau's own window, and Fun Time's VR player,
whose genau mode runs the same tick against a headset texture.

`clip_decode` reaches `app_support.subprocess_utils` for the one Windows fact
about launching ffmpeg (no console window), so `../app_support` has to be
installed in any venv that imports this package — every consumer's already is.

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

There is no venv in this repo — run the suite with a consumer's venv, each of
which has this package installed. The half of `mpv_player` that drives an mpv
handle is unit-tested against a fake; what needs the DLL and a real window is
constructing an `MpvPlayer`, and that is exercised by Fun Time's hidden-desktop
integration suite, which launches the real player.
