"""Signals published by haybale-protokol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from haywire.core.signals import Signal


@dataclass(frozen=True)
class ProtokolChanged(Signal):
    """Gates, drivers or Lines changed. Cross-session, payload-free.

    Subscribers re-read ``ProtokolState.gates()`` and ``ProtokolState.lines()``.
    """

    cross_session: ClassVar[bool] = True
