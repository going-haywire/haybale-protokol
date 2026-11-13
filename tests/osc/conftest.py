"""Fixtures for the OSC haybale's tests: free ports and a listening test socket."""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def udp_port() -> int:
    return free_udp_port()


@pytest.fixture
def listener() -> Iterator[socket.socket]:
    """A bound UDP socket on 127.0.0.1 with a 2 s timeout, standing in for a remote OSC peer."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    yield sock
    sock.close()
