"""OSC address patterns on Receive nodes: OSC syntax, one capture per wildcard.

``*`` and ``?`` match within one address part, never across ``/``; ``[0-9]`` / ``[!a-c]``
match one character of a set; ``{a,b}`` matches one of the words. Each of these becomes a
capture, numbered left to right (``match_1``, ``match_2``...). An empty pattern matches every
address and captures nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AddressPattern:
    """A compiled address pattern."""

    text: str
    captures: int
    _regex: re.Pattern[str] | None = field(default=None, repr=False, compare=False)

    @property
    def is_exact(self) -> bool:
        """True for a plain address, which a Line can look up instead of matching."""
        return bool(self.text) and self.captures == 0

    def match(self, address: str) -> tuple[str, ...] | None:
        """The captured strings when ``address`` matches, else ``None``."""
        if not self.text:
            return ()
        if self._regex is None:
            return () if address == self.text else None
        found = self._regex.fullmatch(address)
        return found.groups() if found else None


def compile_pattern(text: str) -> AddressPattern:
    """Compile ``text``.

    Raises:
        ValueError: Not an OSC address pattern; the message names the position.
    """
    if not text:
        return AddressPattern("", 0)
    if not text.startswith("/"):
        raise ValueError("an OSC address pattern must start with '/'")
    parts: list[str] = []
    captures = 0
    i = 0
    while i < len(text):
        char = text[i]
        if char == "*":
            parts.append("([^/]*)")
        elif char == "?":
            parts.append("([^/])")
        elif char == "[":
            end = text.find("]", i + 1)
            if end == -1:
                raise ValueError(f"unclosed '[' at position {i}")
            body = text[i + 1 : end]
            negate = body.startswith("!")
            body = body[1:] if negate else body
            escaped = "".join("-" if c == "-" else re.escape(c) for c in body)
            parts.append(f"([{'^' if negate else ''}{escaped}])")
            i = end
        elif char == "{":
            end = text.find("}", i + 1)
            if end == -1:
                raise ValueError(f"unclosed '{{' at position {i}")
            words = text[i + 1 : end].split(",")
            parts.append("(" + "|".join(re.escape(word) for word in words) + ")")
            i = end
        elif char in "]}":
            raise ValueError(f"unexpected '{char}' at position {i}")
        else:
            parts.append(re.escape(char))
            i += 1
            continue
        captures += 1
        i += 1
    if captures == 0:
        return AddressPattern(text, 0)
    try:
        regex = re.compile("".join(parts))
    except re.error as exc:
        raise ValueError(f"invalid pattern {text!r} at position {exc.pos}: {exc.msg}") from None
    return AddressPattern(text, captures, regex)
