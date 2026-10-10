"""What :mod:`funestra_core.flick_renderer` was called before Genau's clips became
flicks, kept for the checkouts that still import it."""
from __future__ import annotations

from .renamed import old_name_getter

__all__: list[str] = []

_RENAMED = {
    "ClipRenderController": "FlickRenderController",
    "display_index_for_phase": "display_index_for_phase",
}

__getattr__ = old_name_getter("funestra_core.flick_renderer", _RENAMED)
