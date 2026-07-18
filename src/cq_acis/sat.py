"""Container detection and lossless record framing for ASCII ACIS SAT files.

This module deliberately stops before decoding entity-specific fields.  It keeps
the framing layer independent from the later ACIS-to-OpenCascade translation
layer and preserves unknown entity records verbatim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterator


class SatParseError(ValueError):
    """Raised when SAT container framing is malformed or incomplete."""


class AcisContainer(str, Enum):
    """Container kind detectable without interpreting entity schemas."""

    SAT = "sat"
    SAB = "sab"
    ASM_SAB = "asm_sab"


@dataclass(frozen=True, slots=True)
class SatHeader:
    save_version: int
    declared_record_count: int
    declared_entity_count: int
    history_flag: int
    product_id: str | None
    modeler_version: str | None
    creation_date: str | None
    units_mm: float | None
    resabs: float | None
    resnor: float | None
    line_count: int
    data_offset: int


@dataclass(frozen=True, slots=True)
class SatRecord:
    entity_type: str
    text: str
    sequence_number: int | None
    start_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class SatDocument:
    header: SatHeader
    records: tuple[SatRecord, ...]
    has_end_marker: bool


_HEADER_RE = re.compile(
    r"^\s*(?P<version>\d+)\s+"
    r"(?P<records>-?\d+)\s+"
    r"(?P<entities>-?\d+)\s+"
    r"(?P<history>-?\d+)(?:\s|$)"
)
_SEQUENCE_TOKEN_RE = re.compile(r"^-\d+$")
_SAT_PREFIX_RE = re.compile(rb"^\s*\d+\s+-?\d+\s+-?\d+\s+-?\d+(?:\s|$)")
_END_MARKER = "End-of-ACIS-data"


def _as_text(data: str | bytes) -> str:
    if isinstance(data, str):
        return data
    if data.startswith((b"ACIS BinaryFile", b"ASM BinaryFile")):
        raise SatParseError("binary SAB data cannot be parsed as ASCII SAT")
    # latin-1 preserves a one-to-one mapping between byte and character offsets.
    return data.decode("latin-1")


def detect_container(data: str | bytes) -> AcisContainer:
    """Detect ASCII SAT, ACIS-prefixed SAB, or ASM-prefixed SAB data."""

    if isinstance(data, str):
        prefix = data[:256].encode("latin-1", errors="replace")
    else:
        prefix = data[:256]
    if prefix.startswith(b"ACIS BinaryFile"):
        return AcisContainer.SAB
    if prefix.startswith(b"ASM BinaryFile"):
        return AcisContainer.ASM_SAB
    if _SAT_PREFIX_RE.match(prefix):
        return AcisContainer.SAT
    raise SatParseError("data does not start with a recognized SAT/SAB header")


def _parse_counted_strings(line: str, count: int) -> tuple[str, ...]:
    values: list[str] = []
    position = 0
    length = len(line)

    for _ in range(count):
        while position < length and line[position].isspace():
            position += 1
        if position < length and line[position] == "@":
            position += 1

        digits_start = position
        while position < length and line[position].isdigit():
            position += 1
        if digits_start == position:
            raise SatParseError("expected a counted string length in SAT header")
        string_length = int(line[digits_start:position])

        if position >= length or not line[position].isspace():
            raise SatParseError("missing separator before a counted SAT header string")
        position += 1
        value_end = position + string_length
        if value_end > length:
            raise SatParseError("counted SAT header string exceeds its input line")
        values.append(line[position:value_end])
        position = value_end

    if line[position:].strip():
        raise SatParseError("unexpected data after SAT header strings")
    return tuple(values)


def parse_sat_header(data: str | bytes) -> SatHeader:
    """Parse legacy one-line and modern three-line SAT headers."""

    if detect_container(data) is not AcisContainer.SAT:
        raise SatParseError("expected an ASCII SAT container")
    text = _as_text(data)
    lines = text.splitlines(keepends=True)
    if not lines:
        raise SatParseError("empty SAT input")

    first_line = lines[0].rstrip("\r\n")
    match = _HEADER_RE.match(first_line)
    if match is None:
        raise SatParseError("invalid SAT header line")
    save_version = int(match.group("version"))
    declared_record_count = int(match.group("records"))
    declared_entity_count = int(match.group("entities"))
    history_flag = int(match.group("history"))

    product_id: str | None = None
    modeler_version: str | None = None
    creation_date: str | None = None
    units_mm: float | None = None
    resabs: float | None = None
    resnor: float | None = None
    line_count = 1

    # The public legacy v1.05 fixtures have a one-line header.  The supported
    # v400+ fixtures use the documented three-line form.
    if save_version >= 400:
        if len(lines) < 3:
            raise SatParseError("three-line SAT header is truncated")
        second_line = lines[1].rstrip("\r\n")
        product_id, modeler_version, creation_date = _parse_counted_strings(
            second_line, 3
        )
        third_line = lines[2].strip()
        numeric_fields = third_line.split()
        if len(numeric_fields) != 3:
            raise SatParseError("SAT tolerance header must contain three numbers")
        try:
            units_mm, resabs, resnor = map(float, numeric_fields)
        except ValueError as error:
            raise SatParseError("invalid number in SAT tolerance header") from error
        line_count = 3

    data_offset = sum(len(line) for line in lines[:line_count])
    return SatHeader(
        save_version=save_version,
        declared_record_count=declared_record_count,
        declared_entity_count=declared_entity_count,
        history_flag=history_flag,
        product_id=product_id,
        modeler_version=modeler_version,
        creation_date=creation_date,
        units_mm=units_mm,
        resabs=resabs,
        resnor=resnor,
        line_count=line_count,
        data_offset=data_offset,
    )


def _record_identity(text: str) -> tuple[str, int | None]:
    tokens = text.split(None, 2)
    if not tokens:
        raise SatParseError("empty SAT record")
    if _SEQUENCE_TOKEN_RE.match(tokens[0]):
        if len(tokens) < 2:
            raise SatParseError("SAT sequence number is not followed by an entity type")
        return tokens[1], -int(tokens[0])
    return tokens[0], None


def _scan_document(text: str, header: SatHeader) -> tuple[list[SatRecord], bool]:
    records: list[SatRecord] = []
    position = header.data_offset
    text_length = len(text)

    while True:
        while position < text_length and text[position].isspace():
            position += 1
        if position >= text_length:
            return records, False
        if text.startswith(_END_MARKER, position):
            remainder = text[position + len(_END_MARKER) :]
            if remainder.strip():
                raise SatParseError("unexpected data after End-of-ACIS-data marker")
            return records, True

        record_start = position
        while position < text_length:
            character = text[position]
            if character == "@":
                digits_start = position + 1
                digits_end = digits_start
                while digits_end < text_length and text[digits_end].isdigit():
                    digits_end += 1
                if digits_end > digits_start:
                    if digits_end >= text_length or not text[digits_end].isspace():
                        raise SatParseError(
                            f"missing separator after counted string at offset {position}"
                        )
                    string_length = int(text[digits_start:digits_end])
                    string_start = digits_end + 1
                    string_end = string_start + string_length
                    if string_end > text_length:
                        raise SatParseError(
                            f"counted string at offset {position} exceeds SAT input"
                        )
                    position = string_end
                    continue
            if character == "#":
                record_text = text[record_start:position].strip()
                if not record_text:
                    raise SatParseError(f"empty SAT record at offset {record_start}")
                entity_type, sequence_number = _record_identity(record_text)
                records.append(
                    SatRecord(
                        entity_type=entity_type,
                        text=record_text,
                        sequence_number=sequence_number,
                        start_offset=record_start,
                        end_offset=position + 1,
                    )
                )
                position += 1
                break
            position += 1
        else:
            raise SatParseError(f"unterminated SAT record at offset {record_start}")


def parse_sat(data: str | bytes) -> SatDocument:
    """Parse the SAT header and frame all records without decoding fields."""

    text = _as_text(data)
    header = parse_sat_header(data)
    records, has_end_marker = _scan_document(text, header)
    return SatDocument(
        header=header,
        records=tuple(records),
        has_end_marker=has_end_marker,
    )


def iter_sat_records(data: str | bytes) -> Iterator[SatRecord]:
    """Iterate framed SAT records.

    The initial implementation protects unambiguous ``@<length>`` strings from
    embedded ``#`` characters.  Older schema-dependent counted strings are kept
    verbatim but are not yet interpreted.
    """

    yield from parse_sat(data).records
