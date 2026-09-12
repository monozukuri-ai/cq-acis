"""Additive Rust-decoded views; raw entities and model API 2 stay unchanged.

Saved tolerant scalars have incomplete semantics. They are not effective OCCT
tolerances. Subtype extents are indices into RawEntity.values, not byte offsets.
"""
from dataclasses import dataclass
from .model import CoedgeEntity, EdgeEntity, VertexEntity, ModelEntity, RawEntity
from .tokens import EntityRef


@dataclass(frozen=True, slots=True)
class TolerantVertex:
    vertex: VertexEntity
    source_flag: int
    saved_scalars: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class TolerantEdge:
    edge: EdgeEntity
    saved_scalar: float
    embedded_version: int


@dataclass(frozen=True, slots=True)
class TolerantCoedge:
    coedge: CoedgeEntity
    parameter_interval: tuple[float, float]
    attachment: EntityRef


@dataclass(frozen=True, slots=True)
class SubtypeDefinition:
    index: int
    kind: str
    entity_index: int
    value_start: int
    value_end: int
    parent: int | None


@dataclass(frozen=True, slots=True)
class SubtypeReference:
    entity_index: int
    value_start: int
    target: int | None


@dataclass(frozen=True, slots=True)
class SubtypeTable:
    definitions: tuple[SubtypeDefinition, ...]
    references: tuple[SubtypeReference, ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolvedSubtype:
    geometry: ModelEntity
    definition: SubtypeDefinition


@dataclass(frozen=True, slots=True)
class LinearSurfacePcurve:
    raw: RawEntity
    parameter_interval: tuple[float, float]
    uv_endpoints: tuple[tuple[float, float], tuple[float, float]]
    fit_tolerance: float
    support: SubtypeDefinition
