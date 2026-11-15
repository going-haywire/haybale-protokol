"""MIDI bytes and protokol messages, both ways."""

from typing import Any

import pytest

from haybale_protokol_midi.midi_messages import decode, describe, encode, parse_test_message


@pytest.mark.parametrize(
    ("data", "address", "args", "kind", "channel"),
    [
        ([0x90, 60, 100], "note 1 60", (60, 100, True), "note", 1),
        ([0x80, 60, 40], "note 1 60", (60, 40, False), "note", 1),
        ([0x9F, 60, 0], "note 16 60", (60, 0, False), "note", 16),
        ([0xB0, 7, 64], "cc 1 7", (7, 64), "cc", 1),
        ([0xE0, 0x00, 0x40], "pitchbend 1", (0,), "pitchbend", 1),
        ([0xE1, 0x00, 0x00], "pitchbend 2", (-8192,), "pitchbend", 2),
        ([0xE0, 0x7F, 0x7F], "pitchbend 1", (8191,), "pitchbend", 1),
        ([0xD0, 64], "aftertouch 1", (64,), "aftertouch", 1),
        ([0xC2, 5], "program 3", (5,), "program", 3),
        ([0xF0, 0x7D, 1, 2, 0xF7], "sysex", (b"\x7d\x01\x02",), "sysex", None),
        ([0xF8], "transport", ("clock", 0), "transport", None),
        ([0xFA], "transport", ("start", 0), "transport", None),
        ([0xF2, 0x20, 0x00], "transport", ("songpos", 32), "transport", None),
        ([0xA0, 60, 30], "raw", (b"\xa0\x3c\x1e",), "raw", None),
    ],
)
def test_decode(
    data: list[int], address: str, args: tuple[Any, ...], kind: str, channel: int | None
) -> None:
    message = decode(data, 1.5)
    assert message is not None
    assert (message.address, message.args, message.time) == (address, args, 1.5)
    assert message.extra["kind"] == kind
    assert message.extra["channel"] == channel
    assert message.extra["bytes"] == bytes(data)


def test_decode_nothing_is_none() -> None:
    assert decode([], 0.0) is None


@pytest.mark.parametrize(
    ("kind", "channel", "number", "values", "data"),
    [
        ("note", 1, 60, {"velocity": 100, "on": True}, [0x90, 60, 100]),
        ("note", 16, None, {"note": 61, "velocity": 0, "on": False}, [0x8F, 61, 0]),
        ("cc", 1, None, {"controller": 7, "value": 64}, [0xB0, 7, 64]),
        ("pitchbend", 1, None, {"value": -8192}, [0xE0, 0, 0]),
        ("aftertouch", 2, None, {"value": 64}, [0xD1, 64]),
        ("program", 1, None, {"program": 5}, [0xC0, 5]),
        ("sysex", None, None, {"data": b"\x7d\x01"}, [0xF0, 0x7D, 1, 0xF7]),
        ("transport", None, None, {"event": "stop", "position": 0}, [0xFC]),
        ("transport", None, None, {"event": "songpos", "position": 32}, [0xF2, 0x20, 0x00]),
        ("raw", None, None, {"bytes": b"\xa0\x3c\x1e"}, [0xA0, 60, 30]),
    ],
)
def test_encode(
    kind: str, channel: int | None, number: int | None, values: dict[str, Any], data: list[int]
) -> None:
    assert encode(kind, channel, number, values) == bytes(data)


@pytest.mark.parametrize(
    ("kind", "channel", "values", "field"),
    [
        ("note", 1, {"note": 60, "velocity": 200, "on": True}, "velocity"),
        ("note", 17, {"note": 60, "velocity": 1, "on": True}, "channel"),
        ("cc", 1, {"controller": 128, "value": 1}, "controller"),
        ("pitchbend", 1, {"value": 9000}, "value"),
        ("sysex", None, {"data": b"\x80"}, "data"),
        ("transport", None, {"event": "rewind", "position": 0}, "event"),
    ],
)
def test_encode_out_of_range_names_field(
    kind: str, channel: int | None, values: dict[str, Any], field: str
) -> None:
    with pytest.raises(ValueError, match=field):
        encode(kind, channel, None, values)


def test_parse_test_message_keeps_the_field_name() -> None:
    with pytest.raises(ValueError, match="velocity"):
        parse_test_message("note 1 60 200")


@pytest.mark.parametrize(
    ("text", "data"),
    [
        ("note 1 60 100", [0x90, 60, 100]),
        ("note 1 60 off", [0x80, 60, 0]),
        ("cc 1 7 64", [0xB0, 7, 64]),
        ("pb 1 -200", [0xE0, 56, 62]),
        ("at 1 64", [0xD0, 64]),
        ("pc 1 5", [0xC0, 5]),
        ("sysex 7D 01 02", [0xF0, 0x7D, 1, 2, 0xF7]),
        ("clock", [0xF8]),
        ("start", [0xFA]),
        ("raw 90 3C 64", [0x90, 0x3C, 0x64]),
    ],
)
def test_parse_test_message_forms(text: str, data: list[int]) -> None:
    message = parse_test_message(text)
    assert message.extra["bytes"] == bytes(data)


@pytest.mark.parametrize("text", ["", "note", "note 1", "cc 1 7", "wiggle 1", "raw zz"])
def test_parse_test_message_rejects(text: str) -> None:
    with pytest.raises(ValueError, match="test message"):
        parse_test_message(text)


@pytest.mark.parametrize(
    ("data", "text"),
    [
        ([0x90, 60, 100], "note on ch1 60 vel 100"),
        ([0x80, 60, 0], "note off ch1 60"),
        ([0xB0, 7, 64], "cc ch1 7 = 64"),
        ([0xE0, 0, 0x40], "pitchbend ch1 0"),
        ([0xF0, 0x7D, 1, 0xF7], "sysex 7d 01"),
        ([0xF2, 0x20, 0x00], "songpos 32"),
        ([0xA0, 60, 30], "raw a0 3c 1e"),
    ],
)
def test_describe(data: list[int], text: str) -> None:
    message = decode(data, 0.0)
    assert message is not None
    assert describe(message) == text
