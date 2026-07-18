from __future__ import annotations

import os
from pathlib import Path

from player_core.libmpv_loader import add_libmpv_to_path, libmpv_dir


def test_libmpv_dir_is_vendor_beside_the_installed_package():
    # Every app resolves the DLL through this one location, so it is anchored to
    # the installed package rather than to any consuming repo's layout.
    import player_core

    d = libmpv_dir()
    assert d.name == "vendor"
    assert d.parent == Path(player_core.__file__).resolve().parent.parent


def test_add_libmpv_to_path_prepends_vendor(monkeypatch):
    monkeypatch.setenv("PATH", r"C:\existing")
    add_libmpv_to_path()
    parts = os.environ["PATH"].split(os.pathsep)
    assert parts[0] == str(libmpv_dir())
    assert r"C:\existing" in parts


def test_add_libmpv_to_path_is_idempotent(monkeypatch):
    monkeypatch.setenv("PATH", r"C:\existing")
    add_libmpv_to_path()
    add_libmpv_to_path()
    assert os.environ["PATH"].split(os.pathsep).count(str(libmpv_dir())) == 1
