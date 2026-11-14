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


#: Folders a registry claims (Library.register_components): every module in them must hold a component.
COMPONENT_FOLDERS = ("settings", "states", "themes", "types", "adapters", "widgets", "skins", "nodes",
                     "panels", "editors")


def _component_bases() -> tuple[type, ...]:
    from haywire.core.adapter.base import BaseAdapter
    from haywire.core.node.base import BaseNode
    from haywire.core.settings import LibrarySettings
    from haywire.core.state.base import LibraryState
    from haywire.ui.editor.base import BaseEditor

    return (BaseNode, BaseEditor, LibraryState, LibrarySettings, BaseAdapter)


@pytest.mark.parametrize(
    "path",
    [p for p in SOURCES if p.parent.name in COMPONENT_FOLDERS and p.name != "__init__.py"],
    ids=lambda p: str(p.relative_to(BARN)),
)
def test_component_folders_hold_only_component_modules(path: Path) -> None:
    """Core treats a module in a claimed folder as a component; a helper there does not reload as one."""
    import importlib

    package = path.parent.parent.name
    module = importlib.import_module(f"{package}.{path.parent.name}.{path.stem}")
    defined = [
        obj for obj in vars(module).values() if isinstance(obj, type) and obj.__module__ == module.__name__
    ]
    where = f"{path.parent.name}/"
    assert any(issubclass(obj, _component_bases()) for obj in defined), (
        f"{path.name} defines no component: move it out of {where} (a helper lives at the package root)"
    )
