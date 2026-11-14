"""Fixtures for editor tests: NiceGUI's simulated user, a ProtokolState on a temp project, a stub context."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User
from nicegui.testing.user_simulation import user_simulation

from haybale_protokol.drivers import GateField, LineKey, Message
from haybale_protokol.gates import Gate
from haybale_protokol.states.protokol_selection import ProtokolSelection
from haybale_protokol.states.protokol_state import ProtokolState
from tests.fakes import FakeDriver


class FormDriver(FakeDriver):
    """FakeDriver with a gate form, test-send and a device list."""

    def __init__(self, devices: tuple[tuple[str, str], ...] = ()) -> None:
        super().__init__()
        self._devices = devices

    def gate_fields(self) -> tuple[GateField, ...]:
        return (
            GateField("port", "Port", "int"),
            GateField("host", "Host", "text", applies=({"direction": ("out", "two-way")},)),
        )

    def line_key(self, gate: Gate, device: Any) -> LineKey:
        if not isinstance(gate.options.get("port"), int):
            raise ValueError("needs a port")
        return LineKey("fake", f"{gate.direction} {gate.options['port']}")

    def parse_test_message(self, text: str) -> Message:
        if not text.startswith("/"):
            raise ValueError("needs an address")
        return Message(text.split()[0], tuple(text.split()[1:]), 0.0)

    def list_devices(self) -> tuple[tuple[str, str], ...]:
        return self._devices


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def user() -> AsyncGenerator[User, None]:
    async with user_simulation() as u:
        yield u


@pytest.fixture
def driver() -> FormDriver:
    return FormDriver()


@pytest.fixture
def protokol(tmp_path: Path, driver: FormDriver) -> Iterator[ProtokolState]:
    state = ProtokolState()
    state.project_root = tmp_path
    state.grace_s = lambda: 0.0
    state.register_driver(driver)
    yield state
    state.on_disable()


@pytest.fixture
def selection() -> ProtokolSelection:
    chosen = ProtokolSelection()
    chosen.session = lambda: None  # type: ignore[assignment]
    return chosen


def make_context(
    protokol: ProtokolState, selection: ProtokolSelection, *, edit: bool = True, admin: bool = False
) -> MagicMock:
    context = MagicMock()
    context.app_data = {ProtokolState: protokol}
    context.data = {ProtokolSelection: selection}
    context.can_view.return_value = True
    context.can_edit.return_value = edit or admin
    context.can_admin.return_value = admin
    return context


async def open_editor(user: User, editor_cls: type, context: MagicMock) -> Any:
    """Draw ``editor_cls`` on a page and open it; returns the editor."""
    holder: dict[str, Any] = {}

    @ui.page("/")
    def page() -> None:
        editor = editor_cls(MagicMock())
        holder["editor"] = editor
        editor.draw(context, ui.column())

    await user.open("/")
    return holder["editor"]


def one(user: User, marker: str) -> Any:
    elements = user.find(marker=marker).elements
    assert len(elements) == 1, f"{marker}: {len(elements)} elements"
    return next(iter(elements))


def set_value(user: User, marker: str, value: Any) -> None:
    one(user, marker).set_value(value)


Make = Callable[..., MagicMock]
