"""OSC TCP gates: options, Line keys and validation."""

from typing import Any

import pytest

from haybale_protokol.drivers import LineKey
from haybale_protokol.gates import Gate
from haybale_protokol_osc.driver import OscDriver


def _gate(direction: str = "two-way", **options: Any) -> Gate:
    return Gate("g", "osc", direction, options={"transport": "tcp", **options})  # type: ignore[arg-type]


def test_tcp_line_keys() -> None:
    driver = OscDriver()
    client = _gate(host="10.0.0.5", port=3032)
    assert driver.line_key(client, None) == LineKey("osc", "tcp-client 10.0.0.5:3032")
    server = _gate(role="server", port=9000)
    assert driver.line_key(server, None) == LineKey("osc", "tcp-server 0.0.0.0:9000")
    bound = _gate(role="server", port=9000, bind="127.0.0.1")
    assert driver.line_key(bound, None) == LineKey("osc", "tcp-server 127.0.0.1:9000")


def test_two_way_tcp_is_allowed() -> None:
    for direction in ("in", "out", "two-way"):
        OscDriver().line_key(_gate(direction, host="h", port=1), None)


@pytest.mark.parametrize(
    ("options", "text"),
    [
        ({"host": "h", "port": 1, "role": "peer"}, "role"),
        ({"host": "h", "port": 1, "framing": "2.0"}, "framing"),
        ({"port": 1}, "host"),
        ({"host": 5, "port": 1}, "host"),
        ({"role": "server", "port": 1, "bind": 0}, "bind"),
        ({"role": "server"}, "port"),
    ],
)
def test_tcp_bad_options_raise(options: dict[str, Any], text: str) -> None:
    with pytest.raises(ValueError, match=text):
        OscDriver().line_key(_gate(**options), None)


def test_udp_bind_must_be_text() -> None:
    gate = Gate("g", "osc", "in", options={"port": 1, "bind": 0})
    with pytest.raises(ValueError, match="bind"):
        OscDriver().line_key(gate, None)


def test_line_options_name_the_framing() -> None:
    driver = OscDriver()
    assert driver.line_options(_gate(host="h", port=1)) == {"framing": "1.1"}
    assert driver.line_options(_gate(host="h", port=1, framing="1.0")) == {"framing": "1.0"}
    assert driver.line_options(Gate("u", "osc", "in", options={"port": 1})) == {}
