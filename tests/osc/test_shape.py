"""The Arg shape: parsing, decoding received arguments, encoding arguments to send."""

import pytest

from haybale_protokol_osc.shape import ArgRangeError, ShapeError, decode, encode, infer_shape, parse_shape
from haywire.barn.builtin.types.color import ColorStr
from haywire.core.settings.types import Mat3, Vec2i, Vec3f


def test_parse_known_tokens() -> None:
    tokens = parse_shape("i f d h s b T r vi2 vf3 m3 m4", receive=False)
    assert [t.haywire_type for t in tokens] == [
        "INT", "FLOAT", "FLOAT", "INT", "STRING", "BYTES", "BOOL", "COLOR", "VEC2I", "VEC3F", "MAT3", "MAT4",
    ]
    assert [t.width for t in tokens] == [1, 1, 1, 1, 1, 1, 1, 1, 2, 3, 9, 16]
    assert parse_shape("  ", receive=True) == []


def test_skip_only_on_receive() -> None:
    tokens = parse_shape("_ _3 f", receive=True)
    assert [(t.width, t.haywire_type) for t in tokens] == [(1, None), (3, None), (1, "FLOAT")]
    with pytest.raises(ShapeError, match="_"):
        parse_shape("_ f", receive=False)


@pytest.mark.parametrize("text", ["q", "vf5", "_0", "_x", "x1"])
def test_unknown_token_raises(text: str) -> None:
    with pytest.raises(ShapeError, match="token"):
        parse_shape(text, receive=True)


def test_decode_groups_vectors() -> None:
    tokens = parse_shape("vf3 i", receive=True)
    values = decode(tokens, (1.0, 2.0, 3.0, 7))
    assert values == [[1.0, 2.0, 3.0], 7]
    assert isinstance(values[0], Vec3f)


def test_decode_skips_and_ignores_extra() -> None:
    assert decode(parse_shape("_2 s", receive=True), (1, 2, "x", "extra")) == ["x"]


def test_decode_int_as_float_but_not_float_as_int() -> None:
    assert decode(parse_shape("f", receive=True), (3,)) == [3.0]
    assert decode(parse_shape("i", receive=True), (3.5,)) is None
    assert decode(parse_shape("i", receive=True), (True,)) is None


def test_decode_matrix_color_bool() -> None:
    tokens = parse_shape("m3 r T", receive=True)
    matrix, color, flag = decode(tokens, (*range(9), 0xFF000080, False))  # type: ignore[misc]
    assert isinstance(matrix, Mat3)
    assert matrix == [[0, 1, 2], [3, 4, 5], [6, 7, 8]]
    assert color == "#ff000080"
    assert isinstance(color, ColorStr)
    assert flag is False


def test_decode_short_message_returns_none() -> None:
    assert decode(parse_shape("vf3", receive=True), (1.0, 2.0)) is None


def test_decode_wrong_type_returns_none() -> None:
    assert decode(parse_shape("s", receive=True), (1,)) is None
    assert decode(parse_shape("b", receive=True), ("x",)) is None


def test_encode_vector_flattens() -> None:
    tags, args = encode(parse_shape("vf3 i", receive=False), [Vec3f([1.0, 2.0, 3.0]), 4])
    assert tags == "fffi"
    assert args == (1.0, 2.0, 3.0, 4)


def test_encode_64bit_tags() -> None:
    assert encode(parse_shape("d h", receive=False), [0.5, 2**40]) == ("dh", (0.5, 2**40))


def test_encode_bool_color_matrix() -> None:
    identity = Mat3([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    tokens = parse_shape("T T r m3", receive=False)
    tags, args = encode(tokens, [True, False, ColorStr("#ff000080"), identity])
    assert tags == "TFr" + "f" * 9
    assert args[:3] == (True, False, 0xFF000080)
    assert args[3:] == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def test_encode_out_of_range_int_raises() -> None:
    with pytest.raises(ArgRangeError) as caught:
        encode(parse_shape("f i", receive=False), [0.5, 3_000_000_000])
    assert caught.value.index == 2
    assert str(caught.value) == "arg 2: 3000000000 does not fit i (use h)"


def test_encode_wrong_count_raises() -> None:
    with pytest.raises(ShapeError, match="2 values"):
        encode(parse_shape("f", receive=False), [1.0, 2.0])


def test_infer_shape() -> None:
    vectors = [Vec2i([1, 2]), Vec3f([1.0, 2.0, 3.0]), Mat3([[0] * 3] * 3)]
    values = [0.5, 3, True, "s", b"b", ColorStr("#ffffff"), *vectors]
    assert infer_shape(values) == "f i T s b r vi2 vf3 m3"
