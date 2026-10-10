"""A checkout from before Genau's clips became flicks still imports and runs.

Every open branch of an app runs out of that app's one venv, so these are the
names those branches spell until they are rebased. Each test is one thing such a
checkout does; when no checkout does it any more, the test goes with the name.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from funestra_core import flick_folder, playhead
from funestra_core.cruise_control import CruiseControlState
from funestra_core.flag import Flag
from funestra_core.flick_cache import FlickCacheStore
from funestra_core.flick_renderer import FlickRenderController
from funestra_core.genau_controls import GenauControls, apply_runtime_command
from funestra_core.genau_notifier import GenauNotifier
from funestra_core.genau_status import build_status_text
from funestra_core.renamed import method_of
from funestra_core.robot_hand import RobotHandState
from funestra_core.robot_hand_beat import BeatEngine


def test_an_old_module_path_gives_the_renamed_function():
    from funestra_core.clip_folder import flat_clips_in  # noqa: PLC0415

    assert flat_clips_in is flick_folder.flat_flicks_in


def test_an_old_module_path_refuses_a_name_it_never_had():
    with pytest.raises(ImportError):
        from funestra_core.clip_folder import a_name_funestra_core_never_had  # noqa: F401, PLC0415


def test_a_function_renamed_in_place_answers_to_its_old_name():
    assert playhead.clip_playhead is playhead.flick_playhead


def test_a_class_takes_its_old_keyword_names_and_answers_to_its_old_attribute_names():
    store = FlickCacheStore(limit=1)
    renderer = FlickRenderController(clip_store=store, blit_frame=lambda _frame: None)

    renderer.set_current_flick_path(Path("C:/flicks/alpha.mp4"))

    assert renderer.flick_store is store
    assert renderer.current_clip_path == Path("C:/flicks/alpha.mp4")


def test_genaus_controls_take_the_collaborators_an_old_orchestrator_names():
    stepped = []
    controls = GenauControls(engine=BeatEngine(last_tick=0.0), paused=Flag(), step_clip=stepped.append)

    controls.step_flick(1)

    assert stepped == [1]


def test_an_old_seconds_verb_still_sets_the_pace():
    from funestra_core.flick_advance import FlickAdvanceState  # noqa: PLC0415

    controls = GenauControls(engine=BeatEngine(last_tick=0.0), paused=Flag(), step_flick=lambda _step: None,
                             flick_advance_state=FlickAdvanceState())

    apply_runtime_command("CLIP_SECONDS 30", controls)

    assert controls.flick_advance_state.interval == 30


def test_the_status_says_the_flick_under_both_keys():
    text = build_status_text(RobotHandState(), CruiseControlState(), flick=Path("C:/flicks/alpha.mp4"))

    assert {line.split("=", 1)[0] for line in text.splitlines()} >= {"flick", "clip"}


def test_a_collaborator_from_before_the_rename_is_asked_by_its_old_method_name():
    heard = []

    class OldNotifier:
        def notify_clip(self, path):
            heard.append(path)

    method_of(OldNotifier(), "notify_flick", old_name="notify_clip")(Path("alpha.mp4"))

    assert heard == [Path("alpha.mp4")]


def test_the_notifier_answers_to_its_old_method_name():
    class Socket:
        def __init__(self):
            self.sent = []

        def sendto(self, data, _address):
            self.sent.append(data)

    sock = Socket()
    GenauNotifier("127.0.0.1", 9999, sock=sock).notify_clip(Path("alpha.mp4"))

    assert sock.sent == [b"FLICK alpha", b"CLIP alpha"]
