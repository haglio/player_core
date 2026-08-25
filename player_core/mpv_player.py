"""libmpv-backed playback engine, shared by every player in this family.

mpv hardware-decodes on the GPU end to end (d3d11va), owns audio and so gets A/V
sync for free, seeks precisely enough to click on a timeline, and loops A-B
natively.  ``MpvPlayer`` renders into a pygame window the caller owns (via
``wid``); its offscreen twin (:mod:`player_core.render_player`) renders into a
framebuffer the caller supplies.  Both drive the ``_MpvControl`` surface below,
and both put overlays on top through ``overlay_add``.

The interface is a superset of what any one player needs, because the two use it
differently: Nau opens one file at a time (``loop_file="inf"``) and navigates
explicitly, while a satellite opens letting end-of-file walk a prefetched
playlist.  Either can be told to behave like the other — that is what a lock is
on either — so a constructor option is a *default* and never a rule.

``_MpvControl`` is driven against a fake in ``tests/test_mpv_control.py``.  What
needs the DLL and a real window is constructing an ``MpvPlayer``, and Fun Time's
hidden-desktop integration suite is what exercises that.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .libmpv_loader import add_libmpv_to_path

logger = logging.getLogger(__name__)

# mpv's severities onto Python's.  Only warnings and worse are asked for below,
# so anything that arrives belongs in the host's log at face value.
_MPV_LEVELS = {"fatal": logging.CRITICAL, "error": logging.ERROR, "warn": logging.WARNING}


def _log_mpv(level: str, prefix: str, text: str) -> None:
    """Write one of mpv's own messages to the host player's log.

    Failures inside the engine are otherwise invisible from Python: a clip mpv
    cannot open, a codec it cannot initialize, a hardware decoder it cannot
    create — none of them raise, and playback carries on with an empty video
    output.  What the host is left with is a black window over a healthy process
    and nothing written down anywhere, which is the one state that cannot be
    diagnosed afterwards.  mpv says why at the moment it happens; this keeps the
    sentence, in the log file the player already writes.
    """
    logger.log(_MPV_LEVELS.get(level, logging.WARNING), "mpv %s: %s", prefix, text.strip())


def _import_mpv():
    add_libmpv_to_path()
    import mpv  # noqa: PLC0415 — must follow add_libmpv_to_path (DLL on %PATH%)

    return mpv


def _shared_options(*, muted: bool, loop_file: bool, prefetch: bool) -> dict:
    """The mpv options every player in this family shares, however it renders.

    The windowed player adds its ``wid``/``vo=gpu`` pair on top; the offscreen
    one (:mod:`player_core.render_player`) adds ``vo=libmpv`` instead.

    ``log_handler`` and ``loglevel`` are python-mpv's own constructor keywords
    rather than mpv options; they ride here because both players want them for
    the same reason (:func:`_log_mpv`) and both hand this dict straight to
    ``MPV()``.
    """
    options = dict(
        log_handler=_log_mpv,
        # Warnings and worse only.  At "info" mpv narrates every file it opens,
        # which for a satellite walking a playlist is a line every few seconds —
        # noise that would bury the one line that matters.
        loglevel="warn",
        hwdec="auto-safe",
        # loop-1: the current file repeats, so a video never ends on its own;
        # [ ] navigates.  Nau opens on this; a satellite constructs with
        # loop_file=False ("no") so end-of-file advances its playlist.  Both
        # toggle it at runtime (see set_loop_file).
        loop_file="inf" if loop_file else "no",
        keep_open="yes",
        mute="yes" if muted else "no",
        # An audio device that cannot be opened must never stop the video:
        # mpv's default clock follows audio, so a failed output would freeze
        # every frame while the file "plays".  Null-audio playback keeps the
        # clock running and the session alive (a headset sink that is not
        # accepting streams yet is the case that found this).
        audio_fallback_to_null="yes",
        osc=False,
        input_default_bindings=False,
    )
    if prefetch:
        # Open and demux the *next* playlist entry during the tail of the
        # current one, so a satellite's end-of-file auto-advance cuts to an
        # already-loaded clip instead of cold-opening it on screen.  Only
        # satellites pass this; Nau plays one file at a time (loop_file=inf,
        # explicit [ ] nav) and has no next entry to prefetch.
        options["prefetch_playlist"] = "yes"
    return options


class _MpvControl:
    """The control surface shared by the windowed and offscreen players.

    Subclasses construct ``self._mpv``; every method here only drives it, so
    the session classes (Nau's, a satellite's, fun_time_vr's roles) can hold
    either player without knowing which rendering path is behind it.
    """

    _mpv: object

    def load(self, path: Path) -> None:
        self._mpv.play(str(path))
        # Reset to just this file: drop any entry the previous clip had staged as
        # its prefetched next, so the caller stages a fresh one from a clean base.
        # A no-op for Nau (single-file playlist); the reset is what a satellite's
        # jump/discard/filter navigation needs.
        self._mpv.playlist_clear()

    # Everything below trims mpv's playlist down to the clip on screen, and each
    # does it with ``playlist-clear`` — "clear the playlist, except the currently
    # played file" — rather than by removing computed indices.
    #
    # Which entry is current is mpv's to know, and it changes underneath us: with
    # prefetch on, mpv rolls onto the staged entry by itself at end-of-file, so an
    # index read a moment earlier can already name the clip now playing.  Removing
    # by that index takes the playing entry out from under mpv, which leaves it on
    # an empty playlist — a black window for the rest of the session, with a
    # healthy process, a running loop and nothing raised anywhere.  There is no
    # window to lose here: ``playlist-clear`` resolves "current" inside mpv.

    def stage_next(self, path: Path) -> None:
        """Make *path* the single entry queued after the current clip.

        With ``prefetch-playlist`` on, mpv opens and demuxes this entry before the
        current clip ends, so the end-of-file auto-advance onto it is seamless.
        Any previously-staged entry is replaced.
        """
        self._mpv.playlist_clear()
        self._mpv.loadfile(str(path), "append")

    def clear_next(self) -> None:
        """Drop the staged next entry (used when a lock pins the current clip)."""
        self._mpv.playlist_clear()

    @property
    def advanced_to_next(self) -> bool:
        """True once mpv has reached end-of-file and auto-advanced off the current
        clip onto the staged next one (its playlist position moved past the head).

        -1 is mpv's "no entry playing", which is not past the head.
        """
        pos = self._mpv.playlist_pos
        return pos is not None and pos >= 1

    def drop_consumed(self) -> None:
        """Remove the played-out head sitting ahead of the clip now playing.

        After an auto-advance the spent clip still occupies index 0; clearing
        around the current entry shifts it back to the head (mpv keeps playing it
        uninterrupted), restoring the [current, next] window.
        """
        self._mpv.playlist_clear()

    @property
    def position_ms(self) -> float:
        return (self._mpv.time_pos or 0.0) * 1000.0

    @property
    def duration_ms(self) -> float:
        return (self._mpv.duration or 0.0) * 1000.0


    def set_paused(self, paused: bool) -> None:
        self._mpv.pause = paused

    def set_loop_file(self, loop: bool) -> None:
        """Toggle infinite single-file looping at runtime.

        This is what a lock is on every player here: unlocked plays through and
        lets end-of-file walk the playlist (``no``); locked, the file repeats
        seamlessly in place (``inf``).  Which end each opens on differs — a
        satellite starts unlocked, Nau starts locked — but the switch is the same
        one, so "locked" means the same thing wherever it is said.
        """
        self._mpv.loop_file = "inf" if loop else "no"

    def set_speed(self, speed: float) -> None:
        """Set the playback rate (1.0 = normal). mpv retimes video and audio,
        and its ``time_pos`` clock advances at this rate — so the session's
        funscript sync, which reads that clock, follows the new speed for free
        (the T-Code driver only rescales its move durations)."""
        self._mpv.speed = speed

    def set_volume(self, volume: int) -> None:
        """Set the audio volume (0-100, a percentage of the source's own level).

        ``volume`` and ``mute`` are independent mpv properties, so a player
        constructed muted (``--no-audio`` / ``FUN_TIME_MUTE_AUDIO``, which the
        hidden-desktop integration runs rely on) stays silent whatever is set here.
        """
        self._mpv.volume = volume

    def set_muted(self, muted: bool) -> None:
        """Silence or unsilence the player at runtime, leaving the volume alone
        (so unmuting restores whatever level was set — the mixer convention)."""
        self._mpv.mute = muted

    def set_audio_device_matching(self, substring: str) -> str | None:
        """Route audio to the first output device whose name or description
        contains *substring*, case-insensitively.

        Returns the picked device's description, or None — with the device
        untouched — when nothing matches, so a headset that is off falls back
        to the system default rather than to silence.
        """
        needle = substring.lower()
        for device in self._mpv.audio_device_list or []:
            label = f"{device.get('name', '')} {device.get('description', '')}"
            if needle in label.lower():
                self._mpv.audio_device = device["name"]
                return str(device.get("description") or device["name"])
        return None

    def seek_ms(self, ms: float) -> None:
        self._mpv.command("seek", max(0.0, ms) / 1000.0, "absolute", "exact")

    def set_ab_loop(self, in_ms: float, out_ms: float) -> None:
        self._mpv.ab_loop_a = in_ms / 1000.0
        self._mpv.ab_loop_b = out_ms / 1000.0

    def clear_ab_loop(self) -> None:
        self._mpv.ab_loop_a = "no"
        self._mpv.ab_loop_b = "no"

    @property
    def eof(self) -> bool:
        return bool(self._mpv.eof_reached)


    def screenshot_bgra(self, height: int = 64):
        """Current displayed frame, resized to *height*, as a BGRA array.

        Used to capture loop in/out thumbnails on demand (a few times per
        loop) without disturbing playback — mpv renders the video itself.
        Returns None if no frame is available yet.
        """
        img = self._mpv.screenshot_raw()  # PIL Image
        if img is None or img.height == 0:
            return None
        w = max(1, round(height * img.width / img.height))
        arr = np.asarray(img.convert("RGBA").resize((w, height)))
        return np.ascontiguousarray(arr[:, :, [2, 1, 0, 3]], dtype=np.uint8)

    def overlay(self, ident: int, x: int, y: int, rgba) -> None:
        """Composite an (H, W, 4) BGRA uint8 array at (x, y) over the video."""
        arr = np.ascontiguousarray(rgba, dtype=np.uint8)
        h, w = arr.shape[:2]
        self._mpv.overlay_add(
            ident, x, y, "&" + str(arr.ctypes.data), 0, "bgra", w, h, w * 4,
        )
        # hold a reference so the buffer isn't freed while mpv reads it
        self._overlays = getattr(self, "_overlays", {})
        self._overlays[ident] = arr

    def remove_overlay(self, ident: int) -> None:
        self._mpv.overlay_remove(ident)
        getattr(self, "_overlays", {}).pop(ident, None)

    def close(self) -> None:
        try:
            self._mpv.terminate()
        except Exception:
            pass


class MpvPlayer(_MpvControl):
    def __init__(
        self, wid: int, *, muted: bool = False, loop_file: bool = True, prefetch: bool = False
    ) -> None:
        mpv = _import_mpv()
        options = _shared_options(muted=muted, loop_file=loop_file, prefetch=prefetch)
        options.update(
            wid=str(int(wid)),
            vo="gpu",
            input_vo_keyboard=False,
        )
        self._mpv = mpv.MPV(**options)
