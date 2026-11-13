"""The Arg shape: the argument tokens an OSC node expects or sends, e.g. ``vf3 vf3 i s``.

Tokens are OSC type tags plus Haywire groupings that map to vector and matrix types; on
Receive only, ``_`` / ``_n`` skip one or n arguments. ``T`` and ``F`` both mean "a bool".

======  ========  ===========================================
token   pin type  on the wire
======  ========  ===========================================
i h     INT       one ``i`` (32-bit) / ``h`` (64-bit)
f d     FLOAT     one ``f`` (32-bit) / ``d`` (64-bit)
s S c   STRING    one ``s`` / ``S`` / ``c``
b       BYTES     one blob
T F     BOOL      ``T`` or ``F``, by value
r       COLOR     one RGBA ``r`` (``#rrggbbaa``)
viN     VECNI     N ``i`` (N = 2..4)
vfN     VECNF     N ``f`` (N = 2..4)
m3 m4   MAT3/4    9 / 16 ``f``, row by row
======  ========  ===========================================
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from haywire.barn.builtin.types.color import ColorStr
from haywire.core.settings.types import Mat3, Mat4, Vec2f, Vec2i, Vec3f, Vec3i, Vec4f, Vec4i

INT32 = (-(2**31), 2**31 - 1)
INT64 = (-(2**63), 2**63 - 1)

_VECTORS: dict[str, type[list[Any]]] = {
    "vi2": Vec2i, "vi3": Vec3i, "vi4": Vec4i, "vf2": Vec2f, "vf3": Vec3f, "vf4": Vec4f,
}
_SINGLE = {
    "i": "INT", "h": "INT", "f": "FLOAT", "d": "FLOAT", "s": "STRING", "S": "STRING", "c": "STRING",
    "b": "BYTES", "T": "BOOL", "F": "BOOL", "r": "COLOR",
}
_SKIP = re.compile(r"_(\d*)")


class ShapeError(ValueError):
    """The Arg shape text, or the values given for it, do not fit."""


class ArgRangeError(ShapeError):
    """A value does not fit its wire type; the message names the argument (1-based)."""

    def __init__(self, index: int, value: Any, tag: str, hint: str) -> None:
        super().__init__(f"arg {index}: {value} does not fit {tag} ({hint})")
        self.index = index


@dataclass(frozen=True)
class Token:
    """One Arg shape token."""

    text: str
    width: int
    """How many OSC arguments it covers."""
    haywire_type: str | None
    """The builtin type name of its pin, ``None`` for a skip."""


def parse_shape(text: str, *, receive: bool) -> list[Token]:
    """Split ``text`` into tokens.

    Raises:
        ShapeError: An unknown token, or a skip on a Send node.
    """
    tokens: list[Token] = []
    for word in text.split():
        skip = _SKIP.fullmatch(word)
        if skip is not None:
            if not receive:
                raise ShapeError("'_' skips arguments on Receive only; a Send node sends every inlet")
            count = int(skip.group(1) or 1)
            if count < 1:
                raise ShapeError(f"unknown token {word!r}")
            tokens.append(Token(word, count, None))
        elif word in _SINGLE:
            tokens.append(Token(word, 1, _SINGLE[word]))
        elif word in _VECTORS:
            tokens.append(Token(word, int(word[2]), f"VEC{word[2]}{word[1].upper()}"))
        elif word in ("m3", "m4"):
            size = int(word[1])
            tokens.append(Token(word, size * size, f"MAT{size}"))
        else:
            raise ShapeError(f"unknown token {word!r}")
    return tokens


def decode(tokens: Sequence[Token], args: Sequence[Any]) -> list[Any] | None:
    """One value per non-skip token, or ``None`` when ``args`` are too few or a type does not fit.

    Arguments past the shape are ignored.
    """
    if sum(token.width for token in tokens) > len(args):
        return None
    values: list[Any] = []
    position = 0
    for token in tokens:
        chunk = args[position : position + token.width]
        position += token.width
        if token.haywire_type is None:
            continue
        value = _decode_one(token, chunk)
        if value is None:
            return None
        values.append(value)
    return values


def encode(tokens: Sequence[Token], values: Sequence[Any]) -> tuple[str, tuple[Any, ...]]:
    """The OSC type tags and flat arguments for ``values``, one per token.

    Raises:
        ShapeError: Value count or type does not fit the tokens.
        ArgRangeError: An int does not fit its tag (the message says which, and suggests ``h``).
    """
    if len(values) != len(tokens):
        raise ShapeError(f"{len(values)} values for {len(tokens)} tokens")
    tags: list[str] = []
    args: list[Any] = []
    for index, (token, value) in enumerate(zip(tokens, values, strict=True), start=1):
        token_tags, token_args = _encode_one(index, token, value)
        tags.append(token_tags)
        args.extend(token_args)
    return "".join(tags), tuple(args)


def infer_shape(values: Sequence[Any]) -> str:
    """The default Arg shape for ``values``: ``f`` / ``i`` for numbers, groupings for vectors."""
    words: list[str] = []
    for value in values:
        if isinstance(value, bool):
            words.append("T")
        elif isinstance(value, int):
            words.append("i")
        elif isinstance(value, float):
            words.append("f")
        elif isinstance(value, ColorStr):
            words.append("r")
        elif isinstance(value, str):
            words.append("s")
        elif isinstance(value, (bytes, bytearray)):
            words.append("b")
        elif isinstance(value, Mat3):
            words.append("m3")
        elif isinstance(value, Mat4):
            words.append("m4")
        else:
            word = next((w for w, cls in _VECTORS.items() if type(value) is cls), None)
            if word is None:
                raise ShapeError(f"cannot send a {type(value).__name__} over OSC")
            words.append(word)
    return " ".join(words)


def _decode_one(token: Token, chunk: Sequence[Any]) -> Any:
    kind = token.text
    if kind in ("i", "h"):
        value = chunk[0]
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    if kind in ("f", "d"):
        return _as_float(chunk[0])
    if kind in ("s", "S", "c"):
        return chunk[0] if isinstance(chunk[0], str) else None
    if kind == "b":
        return bytes(chunk[0]) if isinstance(chunk[0], (bytes, bytearray)) else None
    if kind in ("T", "F"):
        return chunk[0] if isinstance(chunk[0], bool) else None
    if kind == "r":
        value = chunk[0]
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        return ColorStr(f"#{value & 0xFFFFFFFF:08x}")
    if kind in _VECTORS:
        cls = _VECTORS[kind]
        if kind[1] == "i":
            if not all(isinstance(v, int) and not isinstance(v, bool) for v in chunk):
                return None
            return cls(chunk)
        floats = [_as_float(v) for v in chunk]
        return None if None in floats else cls(floats)
    size = int(kind[1])
    floats = [_as_float(v) for v in chunk]
    if None in floats:
        return None
    rows = [floats[r * size : (r + 1) * size] for r in range(size)]
    return Mat3(rows) if size == 3 else Mat4(rows)


def _encode_one(index: int, token: Token, value: Any) -> tuple[str, list[Any]]:
    kind = token.text
    if kind in ("i", "h"):
        _check_int(index, value, kind)
        return kind, [int(value)]
    if kind in ("f", "d"):
        return kind, [_require_float(index, value)]
    if kind in ("s", "S", "c"):
        return kind, [str(value)]
    if kind == "b":
        if not isinstance(value, (bytes, bytearray)):
            raise ShapeError(f"arg {index}: blob needs bytes, not {type(value).__name__}")
        return "b", [bytes(value)]
    if kind in ("T", "F"):
        flag = bool(value)
        return ("T" if flag else "F"), [flag]
    if kind == "r":
        text = str(value).lstrip("#")
        rgba = text if len(text) == 8 else text[:6] + "ff"
        try:
            return "r", [int(rgba, 16)]
        except ValueError:
            raise ShapeError(f"arg {index}: {value!r} is not a colour") from None
    if kind in _VECTORS:
        items = list(value)
        if len(items) != token.width:
            raise ShapeError(f"arg {index}: {kind} needs {token.width} values")
        tag = kind[1]
        if tag == "i":
            for item in items:
                _check_int(index, item, "i")
            return "i" * token.width, [int(item) for item in items]
        return "f" * token.width, [_require_float(index, item) for item in items]
    size = int(kind[1])
    rows = [list(row) for row in value]
    if len(rows) != size or any(len(row) != size for row in rows):
        raise ShapeError(f"arg {index}: {kind} needs {size}x{size} values")
    return "f" * token.width, [_require_float(index, item) for row in rows for item in row]


def _check_int(index: int, value: Any, tag: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        else:
            raise ShapeError(f"arg {index}: {tag} needs an int, not {type(value).__name__}")
    low, high = INT32 if tag == "i" else INT64
    if not low <= value <= high:
        raise ArgRangeError(index, value, tag, "use h" if tag == "i" else "out of 64-bit range")


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _require_float(index: int, value: Any) -> float:
    result = _as_float(value)
    if result is None:
        raise ShapeError(f"arg {index}: needs a number, not {type(value).__name__}")
    return result


_TYPE_TOKENS = {
    "INT": "i", "FLOAT": "f", "STRING": "s", "BYTES": "b",
    "BOOL": "T", "COLOR": "r", "MAT3": "m3", "MAT4": "m4",
}


def token_for_type(type_name: str) -> str | None:
    """The default token for a pin of builtin type ``type_name``, ``None`` if OSC cannot carry it."""
    if type_name in _TYPE_TOKENS:
        return _TYPE_TOKENS[type_name]
    vector = re.fullmatch(r"VEC([234])([IF])", type_name)
    if vector is not None:
        return f"v{vector.group(2).lower()}{vector.group(1)}"
    return None
