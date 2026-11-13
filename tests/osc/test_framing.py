"""OSC over TCP framing: OSC 1.0 length prefix and OSC 1.1 SLIP."""

import struct

import pytest

from haybale_protokol_osc.framing import FrameError, FrameReader, encode_frame

PACKETS = [b"/a\x00\x00,i\x00\x00\x00\x00\x00\x01", b"\xc0\xdb middle \xc0", b"x" * 300]


@pytest.mark.parametrize("framing", ["1.0", "1.1"])
def test_round_trip(framing: str) -> None:
    reader = FrameReader(framing)  # type: ignore[arg-type]
    assert reader.feed(b"".join(encode_frame(p, framing) for p in PACKETS)) == PACKETS  # type: ignore[arg-type]


def test_length_prefix_layout() -> None:
    assert encode_frame(b"abcd", "1.0") == struct.pack(">I", 4) + b"abcd"


def test_slip_round_trip_with_escaped_bytes() -> None:
    frame = encode_frame(b"\xc0\xdb", "1.1")
    assert frame.count(b"\xc0") == 2, "only the two END bytes remain unescaped"
    assert FrameReader("1.1").feed(frame) == [b"\xc0\xdb"]


@pytest.mark.parametrize("framing", ["1.0", "1.1"])
def test_reader_reassembles_split_and_joined_frames(framing: str) -> None:
    stream = b"".join(encode_frame(p, framing) for p in PACKETS)  # type: ignore[arg-type]
    reader = FrameReader(framing)  # type: ignore[arg-type]
    out: list[bytes] = []
    for i in range(len(stream)):
        out.extend(reader.feed(stream[i : i + 1]))
    assert out == PACKETS


def test_oversized_length_is_rejected() -> None:
    with pytest.raises(FrameError, match="length"):
        FrameReader("1.0", max_frame=100).feed(struct.pack(">I", 101))


def test_slip_without_end_over_limit_is_rejected() -> None:
    reader = FrameReader("1.1", max_frame=100)
    reader.feed(b"\xc0" + b"x" * 60)
    with pytest.raises(FrameError, match="END"):
        reader.feed(b"x" * 60)


def test_empty_slip_frames_are_skipped() -> None:
    assert FrameReader("1.1").feed(b"\xc0\xc0\xc0abc\xc0") == [b"abc"]


def test_unknown_framing_raises() -> None:
    with pytest.raises(ValueError, match="framing"):
        FrameReader("2.0")  # type: ignore[arg-type]


def test_invalid_slip_escape_is_a_frame_error() -> None:
    with pytest.raises(FrameError, match="SLIP"):
        FrameReader("1.1").feed(b"\xc0\xdb\x00\xc0")
