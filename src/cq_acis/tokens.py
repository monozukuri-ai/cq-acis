"""Schema-independent tokenization of ACIS SAT entity records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeAlias

from .sat import SatParseError


@dataclass(frozen=True, slots=True)
class EntityRef:
    """A zero-based SAT record reference; ``$-1`` is the null reference."""

    index: int

    @property
    def is_null(self) -> bool:
        return self.index == -1

    def __str__(self) -> str:
        return f"${self.index}"


NULL_REF = EntityRef(-1)


@dataclass(frozen=True, slots=True)
class CountedString:
    """An unambiguous SAT ``@<length> <value>`` string token."""

    value: str
    declared_length: int


SatToken: TypeAlias = EntityRef | CountedString | int | float | str

_INTEGER_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(
    r"^[+-]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[eE][+-]?\d+)?$"
)
_REFERENCE_RE = re.compile(r"^\$(-?\d+)$")


def _classify_word(word: str, offset: int) -> SatToken:
    if word.startswith("$"):
        match = _REFERENCE_RE.match(word)
        if match is None:
            raise SatParseError(f"invalid SAT reference {word!r} at offset {offset}")
        index = int(match.group(1))
        if index < -1:
            raise SatParseError(f"invalid negative SAT reference {word!r} at offset {offset}")
        return EntityRef(index)
    if _INTEGER_RE.match(word):
        return int(word)
    if _FLOAT_RE.match(word):
        return float(word)
    return word


def tokenize_record(text: str) -> tuple[SatToken, ...]:
    """Tokenize one record body, preserving explicit counted strings.

    Pre-v700 strings have no lexical marker and remain an integer length token
    followed by ordinary word tokens. Entity-specific readers interpret those
    schema-dependent pairs later.
    """

    tokens: list[SatToken] = []
    position = 0
    text_length = len(text)

    while position < text_length:
        while position < text_length and text[position].isspace():
            position += 1
        if position >= text_length:
            break

        token_start = position
        if text[position] == "@":
            position += 1
            digits_start = position
            while position < text_length and text[position].isdigit():
                position += 1
            if digits_start == position:
                raise SatParseError(
                    f"missing counted string length at offset {token_start}"
                )
            if position >= text_length or not text[position].isspace():
                raise SatParseError(
                    f"missing counted string separator at offset {token_start}"
                )
            declared_length = int(text[digits_start:position])
            position += 1
            value_end = position + declared_length
            if value_end > text_length:
                raise SatParseError(
                    f"counted string at offset {token_start} exceeds its record"
                )
            tokens.append(CountedString(text[position:value_end], declared_length))
            position = value_end
            continue

        while position < text_length and not text[position].isspace():
            position += 1
        tokens.append(_classify_word(text[token_start:position], token_start))

    return tuple(tokens)

