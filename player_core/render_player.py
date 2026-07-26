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

    @property
    def has_new_frame(self) -> bool:
        """Whether mpv holds a frame newer than the last one rendered."""
        return bool(self._render_context.update())

    def render(self, fbo: int, width: int, height: int, *, flip_y: bool = False) -> None:
        """Draw the current frame (video + OSD overlays) into *fbo* at width x height.

        mpv scales to the target preserving aspect, so a target sized to the
        video's own aspect (see :attr:`video_dims`) fills edge to edge.
        """
        self._render_context.render(
            flip_y=flip_y,
            opengl_fbo={"fbo": int(fbo), "w": int(width), "h": int(height)},
        )

    @property
    def video_dims(self) -> tuple[int, int]:
        """The playing video's display size in pixels — (0, 0) until known."""
        return int(self._mpv.dwidth or 0), int(self._mpv.dheight or 0)

    def close(self) -> None:
        try:
            self._render_context.free()
        except Exception:
            pass
        super().close()
