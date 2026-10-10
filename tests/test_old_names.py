from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_a_module_under_the_old_package_name_is_the_same_module():
    old = importlib.import_module("player_core.playlist")

    assert old is importlib.import_module("funestra_core.playlist")


def test_a_patch_through_the_old_name_reaches_the_module_itself(monkeypatch):
    import funestra_core.status  # noqa: PLC0415

    monkeypatch.setattr("player_core.status.stamp_the_playhead", lambda ms: (0, 0.0))

    assert funestra_core.status.stamp_the_playhead(5.0) == (0, 0.0)


def test_the_old_package_hands_its_modules_out_as_attributes():
    import funestra_core.pointer  # noqa: PLC0415
    import player_core  # noqa: PLC0415

    assert player_core.pointer is funestra_core.pointer


def test_a_module_reached_through_the_old_name_keeps_its_own_spec():
    module = importlib.import_module("player_core.flag")

    assert module.__spec__.name == "funestra_core.flag"
    assert module.__name__ == "funestra_core.flag"


def test_a_name_that_never_was_a_module_is_missing_under_either_name():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("player_core.no_such_module")
    import player_core  # noqa: PLC0415

    with pytest.raises(AttributeError):
        _ = player_core.no_such_module


def test_reaching_a_module_by_its_old_name_first_still_loads_it_once():
    probe = (
        "import player_core.heatmap as old, funestra_core.heatmap as new, sys;"
        "print(old is new, sys.modules['player_core.heatmap'] is sys.modules['funestra_core.heatmap'])"
    )
    result = subprocess.run([sys.executable, "-c", probe], cwd=ROOT,
                            capture_output=True, text=True, check=True)

    assert result.stdout.split() == ["True", "True"]
