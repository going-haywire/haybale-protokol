"""Argument pins that follow the Arg shape, shared by OSC Receive and OSC Send.

The Arg shape text is the source of truth. Each named token has a pin with a stable id
(``arg_<n>``, numbers never reused, because an edge's id contains its port's id); the node
store keeps the ids in shape order. The pin edits a user makes rewrite the text:

- connecting the empty ``ADD`` slot appends the edge type's token (undo takes it back);
- deleting the edge that grew a pin removes the pin and its token (typed pins stay);
- reordering pins reorders the tokens; ``_`` skips stay where they are.

Every rewrite goes through the ``arg_shape`` port, whose ``on_change`` rebuilds the pins,
inside the user's one action, so each edit is one undo step.
"""

from __future__ import annotations

import re
from typing import Any

from haywire.api import ADD, PortOrigin

from haybale_protokol_osc.shape import ShapeError, Token, parse_shape, token_for_type

ARG_ID = re.compile(r"arg_(\d+)")


class ArgPins:
    """Mixin for a ``BaseNode`` with an ``arg_shape`` config port and ``arg_<n>`` pins."""

    #: True for Receive (outlets, ``_`` allowed), False for Send (inlets).
    receive: bool = False

    # Provided by BaseNode (the mixin comes first in the bases, so it defines no stubs).
    ports: dict[str, Any]
    store: Any
    value: Any
    add: Any
    post_value: Any

    # -- the node supplies --------------------------------------------------------

    def _arg_spec(self, port_id: str, type_cls: Any, origin: PortOrigin, label: str) -> Any:
        """The inlet or outlet spec of one argument pin."""
        raise NotImplementedError

    # -- reading ------------------------------------------------------------------

    def _tokens(self) -> list[Token]:
        """The current Arg shape; raises ``ShapeError`` when the text is invalid."""
        return parse_shape(str(self.value("arg_shape") or ""), receive=self.receive)

    def _arg_ids(self) -> list[str]:
        return list(getattr(self.store, "arg_ids", []))

    def _slot_id(self) -> str:
        return str(getattr(self.store, "arg_slot", "arg_1"))

    def _arg_ports(self) -> list[Any]:
        """The typed argument pins, in shape order."""
        return [self.ports[port_id] for port_id in self._arg_ids() if port_id in self.ports]

    def _pins_mismatch(self) -> str | None:
        """Why the argument pins no longer match the Arg shape (a pin removed from its menu), or ``None``."""
        try:
            named = [token for token in self._tokens() if token.haywire_type is not None]
        except ShapeError as exc:
            return f"Arg shape: {exc}"
        if len(self._arg_ports()) != len(named):
            return "pins and Arg shape differ: retype the Arg shape"
        return None

    # -- building -----------------------------------------------------------------

    def _add_arg_ports(self, tokens: list[Token]) -> None:
        """Add one pin per named token, then the empty slot. Call inside the node's ``rejig``."""
        import haywire.api as builtin

        from haybale_core.types.specs import BYTES

        named = [token for token in tokens if token.haywire_type is not None]
        ids = self._arg_ids()[: len(named)]
        slot = self._slot_id()
        while len(ids) < len(named):
            # The empty slot holds no edge (connecting grows it), so its id is free to take.
            ids.append(slot if slot not in ids else self._new_arg_id(ids))
        if slot in ids:
            slot = self._new_arg_id(ids)
        self.store.arg_ids = ids
        self.store.arg_slot = slot
        grown = getattr(self.store, "arg_grown", [])
        self.store.arg_grown = [port_id for port_id in grown if port_id in ids]
        for position, (port_id, token) in enumerate(zip(ids, named, strict=True), start=1):
            name = str(token.haywire_type)
            type_cls = BYTES if name == "BYTES" else getattr(builtin, name)
            self.add(self._arg_spec(port_id, type_cls, PortOrigin.RESOLVED, f"{position}: {token.text}"))
        self.add(self._arg_spec(slot, ADD, PortOrigin.DECLARED, "+"))

    def _move_slot_last(self) -> None:
        """Put the empty slot after every other port, so it is the last pin of its side."""
        slot = self.ports.get(self._slot_id())
        if slot is None:
            return
        others = [port.order for port in self.ports.values() if port is not slot]
        if others and slot.order <= max(others):
            slot.order = max(others) + 1
            wrapper = getattr(self, "wrapper", None)
            if wrapper is not None:
                wrapper.mark_layout_changed()

    def _new_arg_id(self, taken: list[str]) -> str:
        used = [int(m.group(1)) for port_id in (*self.ports, *taken) if (m := ARG_ID.fullmatch(port_id))]
        floor = int(getattr(self.store, "arg_next", 1))
        number = max([floor - 1, *used]) + 1
        self.store.arg_next = number + 1
        return f"arg_{number}"

    def _accept_text(self) -> None:
        """Remember the current config texts as the last ones that applied."""
        for port_id in ("address", "arg_shape"):
            if port_id in self.ports:
                setattr(self.store, f"good_{port_id}", str(self.value(port_id) or ""))

    def _reject_text(self, port: Any, error: Exception) -> None:
        """Put ``port`` back to its last applied text and say why the new one was refused."""
        self._report(f"not applied: {error}")
        good = str(getattr(self.store, f"good_{getattr(port, 'id', '')}", ""))
        if getattr(port, "id", None) in ("address", "arg_shape") and self.value(port.id) != good:
            port.set_value(good)

    def _write_shape(self, tokens: list[Token]) -> None:
        """Set the Arg shape text; its ``on_change`` rebuilds the pins."""
        self.ports["arg_shape"].set_value(" ".join(token.text for token in tokens))

    # -- pin edits ------------------------------------------------------------------

    def hb_grow(self, port: Any, edge_wrapper: Any) -> None:
        """An edge on the empty slot becomes an argument of the edge's type."""

        if port.type_cls is None or not issubclass(port.type_cls, ADD) or port.id != self._slot_id():
            return
        other = edge_wrapper._outlet_port if port.is_inlet() else edge_wrapper._inlet_port
        if other is None:
            return
        type_name = getattr(other.stored_type, "__name__", "")
        text = token_for_type(type_name)
        if text is None:
            self._report(f"OSC cannot carry {type_name}")
            return
        try:
            tokens = self._tokens()
        except ShapeError as exc:
            self._report(f"not applied: {exc}")
            return
        self.store.arg_ids = [*self._arg_ids(), port.id]
        self.store.arg_grown = [*getattr(self.store, "arg_grown", []), port.id]
        self.store.arg_slot = self._new_arg_id(self._arg_ids())
        self._write_shape([*tokens, *parse_shape(text, receive=self.receive)])

    def release_pins(self, port_ids: list[str]) -> list[str]:
        """Remove the grown argument pins whose edge is gone, with their tokens."""
        grown = list(getattr(self.store, "arg_grown", []))
        candidates = [
            port_id
            for port_id in port_ids
            if port_id in grown and port_id in self.ports and not self.ports[port_id].is_linked()
        ]
        if not candidates:
            return []
        try:
            tokens = self._tokens()
        except ShapeError:
            return []
        ids = self._arg_ids()
        stash = dict(getattr(self.store, "arg_released", {}))
        for port_id in candidates:
            index = ids.index(port_id)
            position = _named_positions(tokens)[index]
            stash[port_id] = [index, position, tokens[position].text]
            del tokens[position]
            del ids[index]
            grown.remove(port_id)
        self.store.arg_released = stash
        self.store.arg_ids = ids
        self.store.arg_grown = grown
        self._write_shape(tokens)
        return candidates

    def restore_pins(self, port_ids: list[str]) -> None:
        """Bring back pins ``release_pins`` removed, at their places in the shape."""
        stash = dict(getattr(self.store, "arg_released", {}))
        try:
            tokens = self._tokens()
        except ShapeError:
            return
        ids = self._arg_ids()
        grown = list(getattr(self.store, "arg_grown", []))
        for port_id in reversed(port_ids):
            if port_id not in stash:
                continue
            index, position, text = stash.pop(port_id)
            tokens.insert(position, *parse_shape(text, receive=self.receive))
            ids.insert(index, port_id)
            grown.append(port_id)
        self.store.arg_released = stash
        self.store.arg_ids = ids
        self.store.arg_grown = grown
        self._write_shape(tokens)

    def reorder_ports(self, ordered_ids: list[str]) -> None:
        """Reorder pins as the base does, then reorder the Arg shape to match."""
        super().reorder_ports(ordered_ids)  # type: ignore[misc]
        try:
            self._reorder_tokens()
        finally:
            self._move_slot_last()

    def _reorder_tokens(self) -> None:
        ids = self._arg_ids()
        if any(port_id not in self.ports for port_id in ids):
            return  # a pin was removed from its menu; the status guard reports it
        new_ids = sorted(ids, key=lambda port_id: self.ports[port_id].order)
        if new_ids == ids:
            return
        try:
            tokens = self._tokens()
        except ShapeError:
            return
        positions = _named_positions(tokens)
        named = {port_id: tokens[position] for port_id, position in zip(ids, positions, strict=True)}
        for position, port_id in zip(positions, new_ids, strict=True):
            tokens[position] = named[port_id]
        self.store.arg_ids = new_ids
        self._write_shape(tokens)

    def _report(self, text: str) -> None:
        """Show ``text`` on the node's status outlet."""
        self.post_value("status", text)


def _named_positions(tokens: list[Token]) -> list[int]:
    return [position for position, token in enumerate(tokens) if token.haywire_type is not None]
