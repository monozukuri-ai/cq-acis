"""Low-level SAT entities and validated record-reference graphs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, overload

from .sat import SatDocument, SatHeader, SatParseError, SatRecord, parse_sat
from .tokens import EntityRef, SatToken, tokenize_record


class SatGraphError(SatParseError):
    """Raised when SAT records do not form a valid reference graph."""


@dataclass(frozen=True, slots=True)
class RawEntity:
    index: int
    type_name: str
    attributes: EntityRef
    entity_id: int | None
    values: tuple[SatToken, ...]
    record: SatRecord

    def references(self, *, include_attributes: bool = True) -> Iterator[EntityRef]:
        if include_attributes:
            yield self.attributes
        for value in self.values:
            if isinstance(value, EntityRef):
                yield value


@dataclass(frozen=True, slots=True)
class SatEntityGraph:
    header: SatHeader
    entities: tuple[RawEntity, ...]

    def __len__(self) -> int:
        return len(self.entities)

    @overload
    def resolve(self, reference: EntityRef) -> RawEntity | None: ...

    @overload
    def resolve(self, reference: int) -> RawEntity: ...

    def resolve(self, reference: EntityRef | int) -> RawEntity | None:
        index = reference.index if isinstance(reference, EntityRef) else reference
        if index == -1:
            return None
        if index < 0 or index >= len(self.entities):
            raise SatGraphError(
                f"SAT reference ${index} is outside 0..{len(self.entities) - 1}"
            )
        return self.entities[index]

    def bodies(self) -> tuple[RawEntity, ...]:
        return tuple(entity for entity in self.entities if entity.type_name == "body")

    def referenced_by(self, reference: EntityRef | int) -> tuple[RawEntity, ...]:
        target = reference.index if isinstance(reference, EntityRef) else reference
        return tuple(
            entity
            for entity in self.entities
            if any(item.index == target for item in entity.references())
        )


def _strip_sequence_token(
    tokens: tuple[SatToken, ...], record: SatRecord, record_index: int
) -> tuple[SatToken, ...]:
    if record.sequence_number is None:
        return tokens
    if record.sequence_number != record_index:
        raise SatGraphError(
            f"record {record_index} declares sequence {record.sequence_number}"
        )
    if not tokens or not isinstance(tokens[0], int):
        raise SatGraphError(f"record {record_index} has no sequence token")
    return tokens[1:]


def build_entity_graph(document: SatDocument) -> SatEntityGraph:
    """Build and validate the zero-based pointer graph of a parsed SAT file."""

    entities: list[RawEntity] = []
    has_entity_ids = document.header.save_version >= 700

    for index, record in enumerate(document.records):
        tokens = _strip_sequence_token(tokenize_record(record.text), record, index)
        if len(tokens) < 2:
            raise SatGraphError(f"record {index} is missing its attribute pointer")
        type_name = tokens[0]
        attributes = tokens[1]
        if not isinstance(type_name, str):
            raise SatGraphError(f"record {index} has a non-string entity type")
        if type_name != record.entity_type:
            raise SatGraphError(
                f"record {index} type mismatch: {type_name!r} != {record.entity_type!r}"
            )
        if not isinstance(attributes, EntityRef):
            raise SatGraphError(f"record {index} has no attribute reference")

        data_start = 2
        entity_id: int | None = None
        if has_entity_ids:
            if len(tokens) < 3 or not isinstance(tokens[2], int):
                raise SatGraphError(f"record {index} has no integer entity ID")
            entity_id = tokens[2]
            data_start = 3

        entities.append(
            RawEntity(
                index=index,
                type_name=type_name,
                attributes=attributes,
                entity_id=entity_id,
                values=tokens[data_start:],
                record=record,
            )
        )

    graph = SatEntityGraph(document.header, tuple(entities))
    for entity in graph.entities:
        for reference in entity.references():
            graph.resolve(reference)
    return graph


def parse_sat_graph(data: str | bytes) -> SatEntityGraph:
    """Parse SAT framing and return its validated raw entity graph."""

    return build_entity_graph(parse_sat(data))
