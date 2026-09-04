from __future__ import annotations

from pathlib import Path

from player_core.clip_cache import ClipCacheStore
from player_core.clip_renderer import ClipRenderController, display_index_for_phase


def _make_controller():
    clip_store = ClipCacheStore(limit=2)
    display_calls: list[object] = []

    controller = ClipRenderController(
        clip_store=clip_store,
        blit_frame=display_calls.append,
    )
    return controller, clip_store, display_calls


def test_prepare_active_clip_displays_first_frame():
    controller, clip_store, display_calls = _make_controller()
    path = Path("demo.mp4")
    clip_store.clip_cache[path] = {"frames": ["f0", "f1"]}
    controller.set_current_clip_path(path)

    controller.prepare_active_clip_for_current_size()

    assert controller.current_frame_index == 0
    assert display_calls == ["f0"]


def test_show_frame_at_blits_that_frame():
    controller, clip_store, display_calls = _make_controller()
    path = Path("demo.mp4")
    clip_store.clip_cache[path] = {"frames": ["f0", "f1", "f2"]}
    controller.set_current_clip_path(path)

    shown = controller.show_frame_at(1)

    assert shown is True
    assert controller.current_frame_index == 1
    assert display_calls == ["f1"]


def test_show_frame_at_skips_when_the_index_has_not_moved():
    controller, clip_store, display_calls = _make_controller()
    path = Path("demo.mp4")
    clip_store.clip_cache[path] = {"frames": ["f0", "f1"]}
    controller.set_current_clip_path(path)

    controller.show_frame_at(0)
    controller.show_frame_at(0)

    assert display_calls == ["f0"]


def test_show_frame_at_returns_false_when_no_active_clip_is_loaded():
    controller, _clip_store, display_calls = _make_controller()

    assert controller.show_frame_at(0) is False
    assert display_calls == []


def test_display_index_for_phase_reverses_phase_position():
    assert display_index_for_phase(
        phase=0.25,
        frame_count=8,
        auto_active=True,
        current_frame_index=None,
    ) == 5


def test_display_index_for_phase_clamps_past_end():
    assert display_index_for_phase(
        phase=1.0,
        frame_count=8,
        auto_active=True,
        current_frame_index=None,
    ) == 0


def test_display_index_for_phase_uses_current_frame_when_not_auto_active():
    assert display_index_for_phase(
        phase=0.25,
        frame_count=8,
        auto_active=False,
        current_frame_index=3,
    ) == 3
