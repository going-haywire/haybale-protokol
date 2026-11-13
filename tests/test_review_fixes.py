"""Fixes from the final review: per-gate errors and restarting while a Line closes."""

import threading
import time
from pathlib import Path

from haybale_protokol.gates import gate_file_path
from haybale_protokol.states.protokol_state import LineUse, ProtokolState
from tests.fakes import FakeConnection, FakeDriver


def test_one_bad_gate_leaves_the_others_working(tmp_path: Path) -> None:
    path = gate_file_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        '[gates.good]\nprotocol = "fake"\ndirection = "in"\n'
        '[gates.bad]\nprotocol = "fake"\ndirection = "sideways"\n',
        encoding="utf-8",
    )
    state = ProtokolState()
    state.project_root = tmp_path
    state.grace_s = lambda: 0.0
    state.register_driver(FakeDriver())
    use = state.use("good", "in")
    assert isinstance(use, LineUse)
    bad = state.use("bad", "in")
    assert isinstance(bad, str)
    assert bad.startswith("gate 'bad': ")
    assert "sideways" in bad
    use.release()


class SlowClose(FakeConnection):
    def close(self) -> None:
        time.sleep(0.3)
        super().close()


class SlowDriver(FakeDriver):
    def open(self, key, gate, device):  # type: ignore[no-untyped-def]
        connection = SlowClose()
        self.connections.append(connection)
        return connection


def test_use_while_line_is_closing_gets_a_fresh_line(tmp_path: Path) -> None:
    from haybale_protokol.gates import Gate, save_gates

    save_gates(gate_file_path(tmp_path), [Gate("a", "fake", "in")])
    state = ProtokolState()
    state.project_root = tmp_path
    state.grace_s = lambda: 0.0
    driver = SlowDriver()
    state.register_driver(driver)
    first = state.use("a", "in")
    assert isinstance(first, LineUse)
    closer = threading.Thread(target=first.release)
    closer.start()
    time.sleep(0.05)
    again = state.use("a", "in")
    closer.join()
    assert isinstance(again, LineUse), again
    assert again.line is not first.line
    assert again.line.is_open
    again.release()
