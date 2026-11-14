"""A node's gate setting names one or more gates, separated by commas: ``"desk, tablets"``."""

from __future__ import annotations

from collections.abc import Iterable


def gate_names(text: str | None) -> list[str]:
    """The gate names in ``text``, in order, without blanks or repeats."""
    names: list[str] = []
    for part in (text or "").split(","):
        name = part.strip()
        if name and name not in names:
            names.append(name)
    return names


def join_gate_names(names: Iterable[str]) -> str:
    """``names`` as one setting value, ``"a, b"``."""
    return ", ".join(gate_names(",".join(names)))


def named_status(gate: str, status: str) -> str:
    """``status`` prefixed with the gate it is about, unless it already names it."""
    return status if f"'{gate}'" in status or f" {gate}" in status else f"{gate}: {status}"
