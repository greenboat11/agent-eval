"""Enforces the one-directional package boundary from ADR 001:
agenteval/core must never import from agenteval/experiments, so the
infrastructure layer stays extractable on its own later.
"""

import ast
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent / "agenteval" / "core"


def _imported_module_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0] + "." + alias.name.split(".")[1]
                           if "." in alias.name else alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            roots.add(".".join(parts[:2]) if len(parts) > 1 else parts[0])
    return roots


def test_core_does_not_import_experiments():
    offenders = []
    for path in CORE_DIR.rglob("*.py"):
        imported = _imported_module_roots(path.read_text())
        if "agenteval.experiments" in imported:
            offenders.append(str(path))
    assert not offenders, f"agenteval/core must not import agenteval/experiments: {offenders}"
