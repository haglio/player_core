"""Offscreen twin of MpvPlayer: the same engine rendered into a caller's FBO.

``MpvPlayer`` paints into a window mpv owns (``wid``); some hosts have no
window per video — a VR compositor draws several players into one scene — so
this variant drives libmpv's render API instead: mpv decodes exactly as
before, but each frame is drawn on demand into whatever OpenGL framebuffer the
caller passes, for the host to composite wherever it likes.  libmpv renders
the OSD into that frame too, so overlays pushed through ``overlay_add`` (the
players' in-video HUDs) carry over unchanged.

The caller owns the GL context and must have it current on the calling thread
for construction, for every ``render`` and for ``close`` (which frees the
render context); *get_proc_address* resolves GL entry points by name (e.g.
wrapping ``glfw.get_proc_address``), because libmpv binds its own GL functions
through it.

The control surface is ``_MpvControl`` — MpvPlayer's own — so a session class
drives either player without knowing which rendering path is backing it.  Not
unit-tested for MpvPlayer's reason: it needs the libmpv DLL and a live GL
context.
"""
from __future__ import annotations

from collections.abc import Callable

from .mpv_gate import mpv_call
from .mpv_player import _import_mpv, _MpvControl, _shared_options

__all__ = [
    "MpvRenderPlayer",
]

class MpvRenderPlayer(_MpvControl):
    def __init__(
        self,
        get_proc_address: Callable[[str], int | None],
        *,
        muted: bool = False,
        loop_file: bool = True,
        prefetch: bool = False,
        audio: bool = True,
    ) -> None:
        super().__init__()
        mpv = _import_mpv()
        options = _shared_options(muted=muted, loop_file=loop_file, prefetch=prefetch)
        # No window to own: libmpv renders on demand into the caller's FBO.
        options["vo"] = "libmpv"
        if not audio:
            # No audio track at all — stronger than muted.  mpv's default
            # clock follows audio, so a muted player still stalls its VIDEO
            # the moment its output device stops draining (a VR headset's
            # sink parks whenever the headset isn't worn, and every player
            # in the process opens some device).  A host whose player is
            # silent by design opts out of audio selection entirely, and the
            # clock runs on video timing, immune to any device's state.
            options["aid"] = "no"
        self._adopt(mpv.MPV(**options))

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
    @mpv_call(False)
    def has_new_frame(self) -> bool:
        """Whether mpv holds a frame newer than the last one rendered."""
        return bool(self._render_context.update())

    @mpv_call()
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

    def _release(self) -> None:
        """The render context first, then the core it was created against.

        That order is libmpv's: a render context outstanding when the core is
        destroyed is undefined behavior.  Both frees reach here only once, and
        only once :meth:`close` has established that no thread is inside a
        ``render``, an ``update`` or a property read — python-mpv's
        ``MpvRenderContext.free`` is a bare ``mpv_render_context_free`` with no
        guard of its own, and a second one would free a freed context.
        """
        try:
            self._render_context.free()
        except Exception:
            pass
        super()._release()
