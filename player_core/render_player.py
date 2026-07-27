"""Offscreen twin of MpvPlayer: the same engine rendered into a caller's FBO.

``MpvPlayer`` paints into a window mpv owns (``wid``); some hosts have no
window per video — a VR compositor draws several players into one scene — so
this variant drives libmpv's render API instead: mpv decodes exactly as
before, but each frame is drawn on demand into whatever OpenGL framebuffer the
caller passes, for the host to composite wherever it likes.  libmpv renders
the OSD into that frame too, so overlays pushed through ``overlay_add`` (the
players' in-video HUDs) carry over unchanged.

The caller owns the GL context and must have it current on the calling thread
for construction and for every ``render``; *get_proc_address* resolves GL
entry points by name (e.g. wrapping ``glfw.get_proc_address``), because libmpv
binds its own GL functions through it.

The control surface is ``_MpvControl`` — MpvPlayer's own — so a session class
drives either player without knowing which rendering path is behind it.  Not
unit-tested for MpvPlayer's reason: it needs the libmpv DLL and a live GL
context.
"""
from __future__ import annotations

from typing import Callable

from .mpv_player import _MpvControl, _import_mpv, _shared_options


class MpvRenderPlayer(_MpvControl):
    def __init__(
        self,
        get_proc_address: Callable[[str], int | None],
        *,
        muted: bool = False,
        loop_file: bool = True,
        prefetch: bool = False,
    ) -> None:
        mpv = _import_mpv()
        options = _shared_options(muted=muted, loop_file=loop_file, prefetch=prefetch)
        # No window to own: libmpv renders on demand into the caller's FBO.
        options["vo"] = "libmpv"
        self._mpv = mpv.MPV(**options)

        def _resolve(_ctx, name: bytes):
            return get_proc_address(name.decode("utf-8"))

        # Held on self: libmpv calls this for the context's whole lifetime, and
        # a garbage-collected ctypes callback is a hard crash, not an error.
        self._get_proc_address = mpv.MpvGlGetProcAddressFn(_resolve)
        self._render_context = mpv.MpvRenderContext(
            self._mpv,
            "opengl",
            opengl_init_params={"get_proc_address": self._get_proc_address},
        )
        # Dimensions arrive by observation rather than being queried on
        # demand: a property read (mpv_get_property) takes the core's lock,
        # which a file being opened holds for long stretches — a frame loop
        # asking for dimensions mid-open measured hundreds of milliseconds
        # blocked on it.  The observer runs on python-mpv's event thread with
        # the new value in hand, so readers only ever touch a plain tuple.
        # video-out-params (not dwidth/dheight) so both numbers land in one
        # event and a reader can never see a half-updated size.
        self._video_dims = (0, 0)
        self._mpv.observe_property("video-out-params", self._note_video_dims)

    def _note_video_dims(self, _name: str, value) -> None:
        if isinstance(value, dict):
            self._video_dims = (int(value.get("dw") or 0), int(value.get("dh") or 0))
        else:
            self._video_dims = (0, 0)

    @property
    def has_new_frame(self) -> bool:
        """Whether mpv holds a frame newer than the last one rendered."""
        return bool(self._render_context.update())

    def render(self, fbo: int, width: int, height: int, *, flip_y: bool = False) -> None:
        """Draw the current frame (video + OSD overlays) into *fbo* at width x height.

        mpv scales to the target preserving aspect, so a target sized to the
        video's own aspect (see :attr:`video_dims`) fills edge to edge.

        Returns immediately: without block_for_target_time=False, libmpv holds
        the call until the frame's own display time — pacing the caller at the
        video's frame rate.  A host compositing several players on its own
        clock (a 90Hz VR frame loop over 30fps videos) must never inherit that
        pacing; presentation timing is the host's, and mpv just supplies its
        latest frame.
        """
        self._render_context.render(
            flip_y=flip_y,
            block_for_target_time=False,
            opengl_fbo={"fbo": int(fbo), "w": int(width), "h": int(height)},
        )

    @property
    def video_dims(self) -> tuple[int, int]:
        """The playing video's display size in pixels — (0, 0) until known.

        Served from the last video-out-params change event, never from a live
        core query (see the observer in __init__): safe to read at frame rate
        while another clip is opening.  Goes back to (0, 0) between files;
        callers keep their last-sized target through that window, which is
        what keeps the previous clip's final frame on screen during a
        transition instead of a teardown flicker.
        """
        return self._video_dims

    def close(self) -> None:
        try:
            self._render_context.free()
        except Exception:
            pass
        super().close()
