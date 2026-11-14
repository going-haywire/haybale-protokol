"""Hot-reload follows a helper only when it is imported by its full module path.

haywire-core's dependency graph records ``from a.b import c`` as a dependency on ``a.b``, never
on the submodule ``a.b.c``, so an edit to ``c`` would not reload the modules using it.
Import helpers as ``from a.b.c import name`` or ``import a.b.c``.
"""

import ast
import importlib.util
from pathlib import Path

import pytest

BARN = Path(__file__).parent.parent / "barn"
SOURCES = sorted(p for p in BARN.glob("*/haybale_protokol*/**/*.py") if "__pycache__" not in p.parts)


def _submodule_imports(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if not node.module.startswith("haybale_protokol"):
                continue
            for alias in node.names:
                name = f"{node.module}.{alias.name}"
                if importlib.util.find_spec(node.module) is not None and _is_module(name):
                    found.append(f"from {node.module} import {alias.name}")
    return found


def _is_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(BARN)))
def test_helpers_are_imported_by_full_module_path(path: Path) -> None:
    assert _submodule_imports(path) == []
