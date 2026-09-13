"""Additive Rust-decoded views; raw entities and model API 2 stay unchanged.

Saved tolerant scalars have incomplete semantics. Conversion uses the observed
TEDGE bound only with a qualified same-support saved UV curve; other extension
scalars remain uninterpreted. Subtype extents index RawEntity.values, not bytes.
"""
from __future__ import annotations
from dataclasses import dataclass
from .model import CoedgeEntity, EdgeEntity, VertexEntity, ModelEntity, RawEntity, BSplineCurveEntity, ParameterRange
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
    inline_curve: SupportedCurve | None = None


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


@dataclass(frozen=True, slots=True)
class SplineSurfacePcurve:
    """Saved UV poles/knots; reversed means C(-t), support sense keeps UV."""
    raw: RawEntity
    degree: int
    knots: tuple[float, ...]
    multiplicities: tuple[int, ...]
    poles: tuple[tuple[float, float], ...]
    reversed: bool
    parameter_interval: tuple[float, float]
    fit_tolerance: float
    support_reversed: bool
    support: SubtypeDefinition


@dataclass(frozen=True, slots=True)
class UvSpline:
    degree: int
    knots: tuple[float, ...]
    multiplicities: tuple[int, ...]
    poles: tuple[tuple[float, float], ...]
    weights: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SupportedCurve:
    curve: BSplineCurveEntity
    kind: str
    support: ModelEntity
    secondary_support: ModelEntity | None
    support_definition: SubtypeDefinition | None
    pcurve: UvSpline
    value_start: int
    value_end: int
    support_range: ParameterRange | None
    saved_lists: tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]
