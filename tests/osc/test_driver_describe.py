"""The OSC driver describes its gate options and parses test messages for the editors."""

from typing import Any

import pytest

from haybale_protokol.drivers import gate_fields, message_parser, uses_devices
from haybale_protokol.gates import Gate
from haybale_protokol_osc.driver import OscDriver


def _shown(values: dict[str, Any]) -> list[str]:
    fields = gate_fields(OscDriver())
    defaults = {f.key: f.default for f in fields}
    return [f.key for f in fields if f.applies_to(values, defaults)]


def test_gate_fields_cover_every_option() -> None:
    driver = OscDriver()
    fields = {f.key: f for f in gate_fields(driver)}
    assert set(fields) == {"transport", "role", "host", "port", "bind", "framing"}
    options = {"transport": "tcp", "role": "client", "host": "h", "port": 1, "framing": "1.0"}
    driver.line_key(Gate("g", "osc", "two-way", options=options), None)
    assert fields["transport"].choices == ("udp", "tcp")
    assert fields["framing"].default == "1.1"
    assert not uses_devices(driver)


@pytest.mark.parametrize(
    ("values", "shown"),
    [
        ({"direction": "in"}, ["transport", "port", "bind"]),
        ({"direction": "out"}, ["transport", "host", "port"]),
        ({"direction": "two-way", "transport": "tcp"}, ["transport", "role", "host", "port", "framing"]),
        (
            {"direction": "in", "transport": "tcp", "role": "server"},
            ["transport", "role", "port", "bind", "framing"],
        ),
    ],
)
def test_fields_apply_by_transport_and_role(values: dict[str, Any], shown: list[str]) -> None:
    assert _shown(values) == shown


def test_parse_test_message_types() -> None:
    parse = message_parser(OscDriver())
    assert parse is not None
    message = parse("/fader/1 0.5 3 hello T F")
    assert message.address == "/fader/1"
    assert message.args == (0.5, 3, "hello", True, False)
    assert message.extra["types"] == "fisTF"


def test_parse_quoted_string() -> None:
    parse = message_parser(OscDriver())
    assert parse is not None
    message = parse('/label "two words" "3"')
    assert message.args == ("two words", "3")
    assert message.extra["types"] == "ss"


@pytest.mark.parametrize("text", ["", "fader 1", "/a\"unclosed", "/ok \"open"])
def test_parse_rejects_bad_input(text: str) -> None:
    parse = message_parser(OscDriver())
    assert parse is not None
    with pytest.raises(ValueError, match="address|quote"):
        parse(text)
