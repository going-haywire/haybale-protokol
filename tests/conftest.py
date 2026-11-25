"""Fixtures for this repo's own suite.

Mirrors the haywire monorepo's ``library_system`` fixture: the installed haywire libraries
load through their entry points, this repo's haybales from ``barn/``. HOME points at a temp
dir, so no test reads or writes the real ``~/.haywire``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    """The repo root (the directory holding ``barn/``)."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session", autouse=True)
def _isolated_home(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Point HOME at a temp dir so library enables never write into the real ``~/.haywire``."""
    home = tmp_path_factory.mktemp("home")
    previous = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    yield home
    if previous is not None:
        os.environ["HOME"] = previous


@pytest.fixture(scope="session", autouse=True)
def _no_real_sdl() -> Iterator[None]:
    """Keep the real SDL out of the suite: the gamepad driver sees no pad unless a test plugs one.

    The device watch and the refresh button list every device protocol, so without this a test
    run on a machine with a pad would see it. The hardware tests put the real SDL back.
    """
    import haybale_protokol_gamepad.driver as gamepad_driver
    from tests.gamepad.fake_sdl import FakeBackend

    saved = gamepad_driver.backend_factory
    gamepad_driver.backend_factory = FakeBackend
    yield
    gamepad_driver.stop_pump()
    gamepad_driver.backend_factory = saved


@pytest.fixture(scope="session")
def library_system(project_root: Path, _isolated_home: Path) -> Iterator[Any]:
    """A fully initialised library system with this repo's haybales loaded."""
    from haywire.core.di.config import set_global_injector, set_library_system
    from haywire.core.di.test_config import create_test_library_system

    service = create_test_library_system(
        workspace_root=str(project_root),
        library_paths=[str(project_root / "barn")],
        load_libraries=True,
        enable_file_watching=False,
    )
    set_library_system(service)
    set_global_injector(service.injector)

    yield service

    lib_registry = service.get_library_registry()
    if hasattr(lib_registry, "stop_file_watching"):
        lib_registry.stop_file_watching()
    set_library_system(None)
    set_global_injector(None)


@pytest.fixture
def graph(library_system: Any) -> Any:
    """An empty graph on the library system, validating inline."""
    from haywire.core.graph.base import BaseGraph
    from haywire.core.graph.scheduler import SyncScheduler

    return BaseGraph(filestem="Protokol Test Graph", validation_scheduler=SyncScheduler())
