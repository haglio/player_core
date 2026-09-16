"""Locate the libmpv DLL so ``import mpv`` can find it.

python-mpv resolves libmpv through the Windows DLL search path (``%PATH%``),
not ``os.add_dll_directory``, so the directory holding ``libmpv-2.dll`` must be
on PATH before ``import mpv``.  The DLL is ~117 MB and is NOT committed; it is
fetched once (see the README).

Two places are looked in, in order.  A checkout's own ``vendor/`` comes first,
so a worktree that fetched a copy keeps it.  The machine-wide copy under
``%LOCALAPPDATA%\\haglio\\libmpv`` comes after, and it is the one that matters
now: an app pins a version of this package, so its venv holds a copy of the
package beside no ``vendor/`` at all, and every such copy finds the one DLL
there.
"""
from __future__ import annotations

import os
from pathlib import Path

__all__: list[str] = []  # package-internal: no sibling reaches anything here


def machine_libmpv_dir() -> Path:
    """The one machine-wide home of ``libmpv-2.dll``, shared by every install."""
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "haglio" / "libmpv"


def libmpv_dirs() -> list[Path]:
    """Where ``libmpv-2.dll`` is looked for, first match winning."""
    return [Path(__file__).resolve().parent.parent / "vendor", machine_libmpv_dir()]


def add_libmpv_to_path() -> None:
    """Put the DLL's directories at the front of ``%PATH%``, once, in order."""
    wanted = [str(d) for d in libmpv_dirs()]
    rest = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p not in wanted]
    os.environ["PATH"] = os.pathsep.join([*wanted, *rest])
