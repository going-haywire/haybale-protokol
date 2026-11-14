"""The Protokol selection: one gate, Line or Device per session."""

from typing import Any

import pytest

from haybale_protokol.drivers import LineKey
from haybale_protokol.states.protokol_selection import ProtokolSelection


def detached_selection() -> ProtokolSelection:
    """A selection whose session has gone, so its signals are dropped."""
    selection = ProtokolSelection()
    selection.session = lambda: None  # type: ignore[assignment]
    return selection


def test_selecting_one_clears_others() -> None:
    selection = detached_selection()
    selection.select_gate("in")
    assert (selection.gate, selection.line, selection.device) == ("in", None, None)
    key = LineKey("osc", "udp-in 0.0.0.0:8000")
    selection.select_line(key)
    assert (selection.gate, selection.line, selection.device) == (None, key, None)
    selection.select_device("desk")
    assert (selection.gate, selection.line, selection.device) == (None, None, "desk")
    selection.clear()
    assert (selection.gate, selection.line, selection.device) == (None, None, None)


@pytest.mark.integration
def test_selection_is_registered_as_session_state(library_system: Any) -> None:
    from haywire.core.state import LibraryStateRegistry, SessionState

    registry = library_system.injector.get(LibraryStateRegistry)
    library = library_system.get_library_registry().get_library("haybale-protokol")
    classes = registry.get_classes_for_library(library.class_identity)
    sessions = [cls for cls in classes.values() if issubclass(cls, SessionState)]
    assert [cls.__name__ for cls in sessions] == ["ProtokolSelection"]
