"""The old names a renamed module, function or class still answers to.

Every app on this machine runs out of one venv per app, and every open branch of
it runs out of that same venv, so a name this package renames is still spelled
the old way by every checkout from before the rename until it is rebased. These
keep those checkouts importing and running; nothing new may use them.
"""
from __future__ import annotations

import functools
import importlib
from collections.abc import Callable, Mapping
from typing import Any

__all__: list[str] = []


def old_name_getter(module: str, renamed: Mapping[str, str]) -> Callable[[str], Any]:
    def __getattr__(name: str) -> Any:
        if name not in renamed:
            raise AttributeError(f"module {module!r} has no attribute {name!r}")
        return getattr(importlib.import_module(module), renamed[name])
    return __getattr__


def answers_to_old_names(renamed: Mapping[str, str]) -> Callable[[type], type]:
    def wrap(cls: type) -> type:
        init = cls.__init__

        @functools.wraps(init)
        def __init__(self, *args, **kwargs) -> None:
            init(self, *args, **{renamed.get(key, key): value for key, value in kwargs.items()})

        cls.__init__ = __init__
        for old, new in renamed.items():
            setattr(cls, old, property(lambda self, new=new: getattr(self, new),
                                       lambda self, value, new=new: setattr(self, new, value)))
        return cls
    return wrap


def method_of(obj: object, name: str, *, old_name: str) -> Callable[..., Any]:
    """*obj*'s method *name*, or *old_name* on a collaborator from before the rename."""
    return getattr(obj, name, None) or getattr(obj, old_name)
