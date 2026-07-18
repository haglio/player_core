"""Guard the one way this package can be installed wrong.

Sibling repos sit in a directory that is itself on ``sys.path`` (fun_time's venv
carries a ``shared_ui.pth`` naming ``projects/``), and this repo's directory is
called ``player_core`` — the same name as the package inside it. So
``import player_core`` has two candidates: the real package, and the repo root
as an implicit *namespace* package.

Setuptools' default editable install resolves the top-level name through a
meta-path finder that ``PathFinder`` never reaches, so the namespace shadow
wins: submodules still import (the finder rescues those), but
``player_core/__init__.py`` never executes and ``__file__`` is ``None``. That is
a landmine — it works today only because ``__init__.py`` holds nothing but a
docstring.

``pip install -e ... --config-settings editable_mode=compat`` puts the repo root
on ``sys.path`` instead, and a real package beats a namespace portion, so the
shadow cannot form. This test is what makes a wrong reinstall fail loudly rather
than years later.

The check runs in a subprocess with its working directory outside every repo,
because a run started *from* a repo root finds the package through the cwd and
would pass whatever the install did — which is exactly the false green this
guard exists to avoid.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile

_PROBE = """
import player_core
from player_core import libmpv_loader
print(player_core.__file__)
print(libmpv_loader.__file__)
"""


def _resolve_from_outside_any_repo() -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as neutral_cwd:
        result = subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=neutral_cwd, capture_output=True, text=True,
        )
    assert result.returncode == 0, (
        f"player_core is not importable from this interpreter:\n{result.stderr}"
    )
    package_file, submodule_file = result.stdout.strip().splitlines()
    return package_file, submodule_file


def test_the_installed_package_is_not_a_namespace_shadow_of_the_repo_root():
    package_file, _ = _resolve_from_outside_any_repo()

    assert package_file != "None", (
        "player_core resolved to a namespace package (the repo root), not the "
        "real package, so its __init__.py never runs. Reinstall with:\n"
        "  python -m pip install -e <path-to-player_core> "
        "--config-settings editable_mode=compat"
    )
    assert package_file.endswith("__init__.py")


def test_the_installed_packages_modules_come_from_that_same_package():
    # A namespace shadow can still serve submodules through the editable
    # finder, so proving __init__ resolved is not enough on its own: the
    # package and its modules must sit in one directory.
    package_file, submodule_file = _resolve_from_outside_any_repo()

    assert package_file != "None"
    package_dir = package_file.removesuffix("__init__.py")
    assert submodule_file.startswith(package_dir)
