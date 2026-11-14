"""One line on whether a gate can be used and how its Line is doing, for the editors."""

from __future__ import annotations

from haybale_protokol.devices import DeviceListError, device_list_path, load_devices
from haybale_protokol.gates import Gate
from haybale_protokol.states.protokol_state import ProtokolState


def gate_status(state: ProtokolState, gate: Gate) -> str:
    """One line on whether ``gate`` can be used and how its Line is doing."""
    if state.driver(gate.protocol) is None:
        return "protocol not installed"
    if gate.device is not None:
        try:
            known = gate.device in load_devices(device_list_path())
        except DeviceListError as exc:
            return f"device list: {exc}"
        if not known:
            return f"unbound gate: no device '{gate.device}' on this machine"
    line = state.line_of(gate)
    if line is None:
        return "closed"
    return f"{line.status} · {line.users} users"
