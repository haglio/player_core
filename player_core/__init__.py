"""The name this package went by until the Player became the Funestra.

Branches written before the rename still import ``player_core.<module>``; each
such import reaches the very module :mod:`funestra_core` holds, so a patch made
through either name lands on both.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys

__all__: list[str] = []

NEW_PACKAGE = "funestra_core"


def new_module_name(old: str) -> str:
    return f"{NEW_PACKAGE}.{old.partition('.')[2]}"


class _OldNames(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(f"{__name__}."):
            return None
        if importlib.util.find_spec(new_module_name(fullname)) is None:
            return None
        return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        module = importlib.import_module(new_module_name(spec.name))
        spec.loader_state = module.__spec__
        return module

    def exec_module(self, module):
        module.__spec__ = module.__spec__.loader_state


def __getattr__(name: str):
    if name.startswith("__"):
        raise AttributeError(name)
    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as missing:
        raise AttributeError(name) from missing


if not any(isinstance(finder, _OldNames) for finder in sys.meta_path):
    sys.meta_path.insert(0, _OldNames())
