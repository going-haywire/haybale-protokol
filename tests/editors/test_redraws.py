"""Change signals refresh parts of an editor; a full redraw would destroy an open dialog."""

import pytest

from haybale_protokol.editors.gates_editor import GatesEditor
from haybale_protokol.editors.monitor_editor import MonitorEditor
from haybale_protokol.signals import ProtokolChanged
from haywire.core.session import handlers


def _signals(cls: type, attr: str) -> set[object]:
    found: set[object] = set()
    for member in vars(cls).values():
        found.update(getattr(member, attr, ()))
    return found


@pytest.mark.parametrize("cls", [GatesEditor, MonitorEditor])
def test_protokol_changes_never_redraw_the_whole_editor(cls: type) -> None:
    assert ProtokolChanged not in _signals(cls, handlers._REDRAW_ON_ATTR)
    assert ProtokolChanged in _signals(cls, handlers._REACT_ON_ATTR)
