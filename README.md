# player_core

The shared playback core backing the video players in this project family.

Six players and hosts across three repos read it. Four of them embed a video
player and are driven by an orchestrator through files on disk; the other two
take the HUDs and the motion without the player.

| Consumer | Repo | What it takes |
| --- | --- | --- |
| Genau | `../genau` | the clip player's whole engine, under its pygame window |
| Fun Time's main player | `../fun_time` | the player, the console, the drive readout, the T-Code driver |
| Fun Time's satellites | `../fun_time` | the player, the satellite HUD |
| Fun Time's VR player | `../fun_time` | the offscreen player, the T-Code driver, and the clip player's engine for its genau mode |
| Fun Time itself | `../fun_time` | the file channel, the playlist, the status line |
| Origenerator | `../origenerator` | the console and the drive readout, over its slideshows |

Everything they had to agree on lives here, so none of them has to import
another application's internals to get it. By what it is:

- **the engine** — `mpv_player`, its offscreen twin `render_player`, the
  `libmpv_loader` that puts the vendored DLL on `%PATH%` first, which is the
  only way python-mpv finds it on Windows, and `audio_outputs`, which says
  which of the machine's outputs a session means by the device name it
  configures.
- **the player contract** — what a content source hands a player and what
  it gets back, each format written and read in one module; see below.
  `session_quit` is beside them (a close on one window of a session asks the
  session).
- **the device** — `tcode` and `tcode_driver` for the wire, `funscript` for a
  script and the questions asked of one, and for a motion of this family's own:
  `robot_hand` (the waveform), `robot_hand_beat` (the phase it runs at),
  `robot_hand_driver` (the motion on the wire, and the device changing hands),
  `wave_stack` / `cruise_control` (the motion varying itself), `broker_feed`
  (the beat the OSR2 broker publishes when it has the room).
- **the clip player** — Genau, wherever it is drawn: `clip_folder`,
  `clip_decode`, `clip_cache`, `clip_loader`, `clip_preload`, `clip_sequence`,
  `clip_selection`, `clip_advance`, `clip_renderer` and `clip_scrub` get a clip
  from a folder to the frame the motion is at, and `genau_controls`,
  `genau_refresh`, `genau_readout`, `genau_status` and `genau_notifier` are its
  verbs, its tick, and what it publishes. A shell — Genau's pygame window, Fun
  Time's headset — supplies the surface, the loop and the keys.
- **the chrome and what is drawn on it** — `hud_panel`, `hud_marks`,
  `geometry`, `timeline`, `volume`, `hud_status`, and then a model and a
  painter per HUD: `console` / `console_hud`, `drive_layout` / `drive_readout`,
  `satellite_hud` / `satellite_hud_paint`.  Two of those are sections rather
  than panels — the drive readout and `hud_osr2`'s device line — because a host
  that both browses a set and drives the OSR2 (Origenerator's shows) says all of
  it on ONE panel rather than stacking a console under a lock HUD.
- **the window** — `sdl_hints`, the SDL facts every player here has to get
  right before it opens one (its taskbar identity it claims through
  `app_support.win32`, like every other process in the family).
- **the loop** — `control_registry` (how any player declares a control and the
  verb and key that move it), `flag` (a bit two parts of an app share, with its
  edge), `tick_failures` (a frame loop's fault, said once).

Nothing app-specific belongs here. A module earns a place only once a second
repo needs it; until then it stays with the app that owns it. Genau's engine is
here because two shells run it: Genau's own window, and Fun Time's VR player,
whose genau mode runs the same tick against a headset texture.

## The player contract

A player shows what a content source hands it and tells the source what it is
showing. Today the source is Fun Time and the players are its main player, its
two satellites and their headset twins; the contract is what lets a second
source drive the same players. Every part of it is a pair — a writer and a
reader in one module — so the two sides cannot spell a thing differently:

| The source hands the player… | …through | …and reads back |
| --- | --- | --- |
| a playlist: one `PlaylistItem` per line, a video and its funscript, or a picture | `playlist` (`write_playlist` / `read_playlist`; `item_line` / `item_from_line` is the line, and `PLAY_FILE`'s value) | |
| verbs on its command file, spelled in `player_verbs` | `file_channel` (`append_command` / `consume_command_file`); the player answers the ones it declares in a `control_registry` | |
| the pace a picture holds the screen for: `SET_PACE <seconds>`, 0 holding it | `player_verbs.pace_seconds` reads the value, `set_pace` hands it to mpv | |
| the paused flag | `app_support.file_channel.write_flag` / `file_channel.read_paused_state` | |
| its HUD: a `HudModel` for a satellite, a `ConsoleModel` for the main slot, each carrying the buttons the source declares — rows of `hud_button.Button`: the verb a press posts, the face, the tooltip, lit or dim, where a group starts | `satellite_hud` (`hud_text` / `parse_hud`), `console` (`console_text` / `parse_console`) | |
| | `status` (`status_fields` / `parse_status`, published by `StatusWriter`) | a `PlayerStatus`: the item on screen, the playhead, paused, locked, the rate it plays at, whether the item is a picture — and after those seven lines, whatever that player adds of its own |

A player answers the verbs it can (`TRASH` is a satellite's, `TOGGLE_LOCK` the
main slot's) and refuses the rest on its log. It draws the buttons its source
declared and nothing else, and posts each one's verb verbatim; a read-out
whose number only the drawing host knows (the video's rate, a clip's pace)
names it in `host_value` and the painter fills it in. A panel declaring no
buttons is drawn with none.

A picture is shown by libmpv itself: it holds the frame for the pace and then
ends the file the way a finished video ends, so a picture moves on, holds under
a lock and waits out a pause exactly as a video does, and a player opens at 4
seconds until a source sets a pace. Whether an item is a picture is mpv's to
say once the file is open (`showing_picture`), so a playlist line carries no
kind; the still a HUD map draws for one is its cell's `thumb`, as for a video.

`clip_decode` reaches `app_support.subprocess_utils` for the one Windows fact
about launching ffmpeg (no console window), so `../app_support` has to be
installed in any venv that imports this package — every consumer's already is.

## Install

Each consuming project names a tag of this repo in its own
`[project.dependencies]`, and pip fetches it:

```toml
"player-core @ git+https://github.com/haglio/player_core@v0.1.243",
```

Every landing here is tagged (`tag-the-landing`, called from this repo's
merge gate), and the version this package reports is that tag, read by
setuptools-scm. A consumer moves to a newer one in its own commit, with its
own suite to answer for it.

## Working across this repo and a consumer

A consumer names a tag of this repo, so a change here does not reach it until
that consumer moves its pin. To try a change here inside one, install this
checkout over the pin in that consumer's venv and put it back after:

```bash
# from the consumer
".venv/Scripts/python.exe" -m pip install -e ../player_core --config-settings editable_mode=compat
# ...and back to the tag the consumer names: reinstalling the consumer
# replaces the checkout with its pin
".venv/Scripts/python.exe" -m pip install -e . --config-settings editable_mode=compat
```

Landing is two commits, in this order: this repo's, which tags a new version,
then the consumer's, which moves its pin to that tag. Between them the consumer
is untouched -- which is the whole point.


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

`libmpv-2.dll` (~117 MB) is **not committed**. Fetch it once; it lands in
`%LOCALAPPDATA%\haglio\libmpv\`, and every install of this package finds it
there -- an app's pinned copy, an editable checkout and a fresh worktree alike.
`libmpv_loader` looks in a checkout's own `vendor/` first, so a copy fetched
there by hand still wins for that checkout.

```bash
python tools/fetch_libmpv.py
```

`tools/libmpv.lock` names the build: source repository, release tag, asset and
its SHA-256. The script verifies that digest and refuses a mismatch, so this
machine and the merge gate link the same DLL and both can say which one. Upstream
keeps about a month of releases; once the pinned tag is gone the script says so,
names the lock file and takes the newest build instead, which is what every run
did before the pin. Bumping the pin is one pull request, and it is where a
version change gets a reason written down.

## Tests

```bash
".venv/Scripts/python.exe" -m pytest tests/
```

There is no venv in this repo — run the suite with a consumer's venv, each of
which has this package installed. The half of `mpv_player` that drives an mpv
handle is unit-tested against a fake; what needs the DLL and a real window is
constructing an `MpvPlayer`, and that is exercised by Fun Time's hidden-desktop
integration suite, which launches the real player.
