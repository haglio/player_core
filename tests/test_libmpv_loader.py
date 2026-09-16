from __future__ import annotations

import os
from pathlib import Path

from player_core import libmpv_loader
from player_core.libmpv_loader import add_libmpv_to_path, libmpv_dirs, machine_libmpv_dir


def test_a_checkouts_own_vendor_dir_is_looked_in_first():
    # A worktree or checkout that fetched its own copy keeps using it.
    import player_core

    assert libmpv_dirs()[0] == Path(player_core.__file__).resolve().parent.parent / "vendor"


def test_the_machine_wide_copy_is_looked_in_after_it(monkeypatch, tmp_path: Path):
    # An app that pins this package gets a copy of it in its own venv, beside no
    # vendor dir at all -- so the one DLL lives where every copy can find it.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert libmpv_dirs()[1] == tmp_path / "haglio" / "libmpv"


def test_the_machine_wide_copy_is_under_local_app_data(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert machine_libmpv_dir() == tmp_path / "haglio" / "libmpv"


def test_with_no_local_app_data_it_is_under_the_home_dirs_one(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(libmpv_loader.Path, "home", classmethod(lambda cls: tmp_path))

    assert machine_libmpv_dir() == tmp_path / "AppData" / "Local" / "haglio" / "libmpv"


def test_both_go_on_path_ahead_of_everything_in_that_order(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("PATH", r"C:\existing")

    add_libmpv_to_path()

    parts = os.environ["PATH"].split(os.pathsep)
    assert parts[:2] == [str(d) for d in libmpv_dirs()]
    assert r"C:\existing" in parts


def test_putting_them_on_path_twice_adds_nothing(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("PATH", r"C:\existing")

    add_libmpv_to_path()
    add_libmpv_to_path()

    parts = os.environ["PATH"].split(os.pathsep)
    assert all(parts.count(str(d)) == 1 for d in libmpv_dirs())
