"""Which application a player's windows belong to, as far as the taskbar knows.

Windows groups taskbar buttons by AppUserModelID, and takes the icon and name
from whichever pinned shortcut carries the same one.  A process that never sets
its own is given an identity derived from its executable — which for these
players is a shared python interpreter, so they land under whatever unrelated
app registered that path first, wearing its icon and its name.

Every player in this family therefore claims one explicitly, and *which* one is
the launcher's to say rather than the player's: run on its own, a player is its
own application; run by an orchestrator, its windows belong to that orchestrator
along with everything else it opened.  This is the one call behind both.
"""
from __future__ import annotations

import ctypes

_shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]


def set_app_user_model_id(app_id: str) -> None:
    """Claim *app_id* as this process's taskbar identity.

    Must run before any window exists: Windows reads the identity as a window is
    created, so a call afterwards leaves the windows already on the bar where
    they were.

    Raises OSError on failure — the callers treat that as cosmetic and carry on,
    because an icon is never worth failing to start over.
    """
    hr = _shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    if hr < 0:  # the FAILED() macro
        raise OSError(f"SetCurrentProcessExplicitAppUserModelID failed: HRESULT 0x{hr:08x}")
