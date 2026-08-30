"""This repo's dead-code gate: every public name must have a consumer.

**Not vulture, and deliberately so.** Every caller of this package lives in
another repo, so a scanner looking for callers here flags the entire public API
and the whitelist that quiets it just restates that API -- a gate that can never
fail. `CLAUDE.md` says not to add one back, and this is not it.

The answerable question is the one the consumers can answer. This reads the
sibling checkouts, collects every name they import out of `player_core`, and
fails on a public name none of them reaches. `no_consumer_imports.txt` holds the
ones that already had no consumer when the gate went in; the set has to match it
exactly, so a name that gains a consumer takes its line out of the file and a
new name with no consumer cannot be added quietly.

**What it costs.** The answer depends on the sibling checkouts as they sit on
disk, which is why the file is a snapshot and not a rule. One that is absent,
or one on a branch that has dropped an import, moves names into the unreferenced
set and turns this red -- with the checkouts it read named in the message, so
the cause is in front of whoever sees it. A tree with no consumer beside it at
all, which is what CI clones, has nothing to compare against and skips: the
gate's authority is the developer machine, where the siblings live and where
every suite in this family is run before it lands.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "player_core"
BASELINE = Path(__file__).resolve().parent / "no_consumer_imports.txt"

_NOT_SOURCE = {".venv", ".claude", "build", "__pycache__", "node_modules"}


def _primary_checkout(repo: Path) -> Path:
    """The checkout *repo* belongs to, given a worktree or the primary itself.

    Worktrees share one git directory whose parent is the primary. Anchoring on
    the primary matters: a worktree lives at `<primary>/.claude/worktrees/<name>`
    and its neighbours are other worktrees, not the sibling repos.
    """
    try:
        common = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return repo
    return (repo / common).resolve().parent


def _source_files(checkout: Path):
    for path in checkout.rglob("*.py"):
        if _NOT_SOURCE.isdisjoint(path.parts) and not any(
            part.endswith(".egg-info") for part in path.parts
        ):
            yield path


def _public_names() -> dict[str, list[str]]:
    """Every module-level name this package publishes, and where it is defined."""
    published: dict[str, list[str]] = {}
    for module in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            else:
                continue
            for name in names:
                if not name.startswith("_"):
                    published.setdefault(name, []).append(module.name)
    return published


def _names_reached_from(source: str) -> set[str]:
    """The names one consumer module takes out of `player_core`.

    Both spellings count: what a `from player_core.x import a` names directly,
    and what is read off a module bound by `from player_core import x` or
    `import player_core.x` -- the second is how most of the geometry and the
    format helpers are reached.
    """
    # Most of a consumer's tree has nothing to do with this package, and parsing
    # it all costs more than the whole rest of this suite.
    if "player_core" not in source:
        return set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    modules, names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("player_core"):
            if "." in node.module:
                names.update(alias.name for alias in node.names)
            else:
                modules.update((alias.asname or alias.name) for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("player_core."):
                    modules.add(alias.asname or alias.name.split(".")[-1])
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in modules:
                names.add(node.attr)
    return names


def _what_the_consumers_reach() -> tuple[set[str], list[str]]:
    """Every name the sibling checkouts import, and which ones import anything.

    The consumers are found rather than named: a sibling that imports this
    package is one, and nothing here has to know an application's name to say so
    -- which is the rule the package itself is held to.
    """
    primary = _primary_checkout(ROOT)
    reached: set[str] = set()
    consumers = []
    for sibling in sorted(primary.parent.iterdir()):
        if not sibling.is_dir() or sibling == primary:
            continue
        found: set[str] = set()
        for path in _source_files(sibling):
            found |= _names_reached_from(path.read_text(encoding="utf-8", errors="replace"))
        if found:
            reached |= found
            consumers.append(sibling.name)
    return reached, consumers


def _baseline() -> set[str]:
    lines = BASELINE.read_text(encoding="utf-8").splitlines()
    return {line.split("#")[0].strip() for line in lines if line.split("#")[0].strip()}


def test_every_public_name_has_a_consumer():
    reached, consumers = _what_the_consumers_reach()
    if not consumers:
        pytest.skip(
            "no sibling checkout beside this one imports player_core, so there is "
            "nothing to compare the public surface against -- this is what a "
            "public clone and a fresh CI checkout look like"
        )

    published = _public_names()
    without_a_consumer = {name for name in published if name not in reached}
    recorded = _baseline()

    unrecorded = sorted(without_a_consumer - recorded)
    assert not unrecorded, (
        f"public names no consumer imports (read from: {', '.join(consumers)}).\n"
        "Give each one a consumer, make it private, or -- if it is meant to sit "
        f"unused for now -- add it to {BASELINE.name} with the reason:\n"
        + "\n".join(f"  {name}  ({', '.join(published[name])})" for name in unrecorded)
    )

    settled = sorted(recorded - without_a_consumer)
    assert not settled, (
        f"{BASELINE.name} lists names that are no longer waiting for a consumer "
        f"(read from: {', '.join(consumers)}). Delete these lines -- the file is "
        "the list of what is still waiting, and a line that has stopped being "
        "true is what hides the next one:\n"
        + "\n".join(
            f"  {name}  -- "
            + ("a consumer imports it now" if name in published
               else "no longer published here")
            for name in settled
        )
    )
