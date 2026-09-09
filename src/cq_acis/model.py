"""Container-independent ACIS geometry and source information.

No parsing or CadQuery imports belong here. Rust owns validation and geometry
math. Adapters must decode the exact source dialect and remap references into
one model-local entity table before constructing an AcisModel. This module
does not decode SAB or Inventor data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterator, Protocol, TypeAlias, overload

from . import _native


class AcisContainer(str, Enum):
    """Source encoding; identifying an encoding does not decode it."""

    SAT = "sat"
    SAB = "sab"
    ASM_SAB = "asm_sab"


@dataclass(frozen=True, slots=True)
class SatRecord:
    """Legacy SAT source attachment, optional on shared model entities."""

    entity_type: str
    text: str
    sequence_number: int | None
    start_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class AcisMetadata:
    """Source facts; absent values remain None, not inferred defaults.

    units_mm is millimetres per source length unit. resabs is expressed in
    source length units; resnor is dimensionless. save_version belongs to the
    source dialect, not to the originating application's product year.
    """

    units_mm: float | None = None
    resabs: float | None = None
    resnor: float | None = None
    container: AcisContainer | None = None
    save_version: int | None = None
    product_id: str | None = None
    modeler_version: str | None = None
    creation_date: str | None = None
    dialect: str | None = None


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Half-open byte range in an explicitly named source domain.

    For compressed carriers, name the decompressed stream/domain. Its offsets
    must not be presented as offsets in the outer Inventor file.
    """

    source_id: str
    start_offset: int
    end_offset: int

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("source_id must identify the byte domain")
        if self.start_offset < 0 or self.end_offset < self.start_offset:
            raise ValueError("invalid source byte range")


@dataclass(frozen=True, slots=True)
class AcisDiagnostic:
    """Adapter-reported loss, limitation, or source observation."""

    code: str
    message: str
    entity_index: int | None = None
    source: SourceSpan | None = None


class AcisModelError(ValueError):
    """Raised when a shared model has invalid entity identities/references."""


@dataclass(frozen=True, slots=True)
class EntityRef:
    """A model-local, zero-based entity reference; index -1 is null."""

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


AcisValue: TypeAlias = EntityRef | CountedString | int | float | str | bytes


@dataclass(frozen=True, slots=True)
class RawEntity:
    """Identity and optional source data; no SAT record is required.

    ``index`` addresses this model, while ``entity_id`` retains a producer ID.
    ``record`` is the legacy SAT attachment; binary adapters can use
    ``source`` and ``raw_data`` instead. Bytes alone imply no decoded semantics.
    """

    index: int
    type_name: str
    attributes: EntityRef
    entity_id: int | None
    values: tuple[AcisValue, ...] = ()
    record: SatRecord | None = None
    source: SourceSpan | None = None
    raw_data: bytes | None = None

    def references(self, *, include_attributes: bool = True) -> Iterator[EntityRef]:
        if include_attributes:
            yield self.attributes
        for value in self.values:
            if isinstance(value, EntityRef):
                yield value


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float
    y: float
    z: float

    def cross(self, other: Vec3) -> Vec3:
        return Vec3(*_native.vector(
            "cross", (self.x, self.y, self.z), (other.x, other.y, other.z), 0.0
        ))

    def dot(self, other: Vec3) -> float:
        return _native.vector_scalar(
            "dot", (self.x, self.y, self.z), (other.x, other.y, other.z)
        )

    def __neg__(self) -> Vec3:
        return Vec3(*_native.vector(
            "neg", (self.x, self.y, self.z), (0.0, 0.0, 0.0), 0.0
        ))

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(*_native.vector(
            "add", (self.x, self.y, self.z), (other.x, other.y, other.z), 0.0
        ))

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(*_native.vector(
            "sub", (self.x, self.y, self.z), (other.x, other.y, other.z), 0.0
        ))

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(*_native.vector(
            "mul", (self.x, self.y, self.z), (0.0, 0.0, 0.0), scalar
        ))

    def __rmul__(self, scalar: float) -> Vec3:
        return self * scalar

    @property
    def magnitude(self) -> float:
        return _native.vector_scalar(
            "magnitude", (self.x, self.y, self.z), (0.0, 0.0, 0.0)
        )

    def normalized(self) -> Vec3:
        return Vec3(*_native.vector(
            "normalized", (self.x, self.y, self.z), (0.0, 0.0, 0.0), 0.0
        ))


@dataclass(frozen=True, slots=True)
class ParameterRange:
    """A parameter range where ``None`` represents an infinite bound."""

    lower: float | None
    upper: float | None


@dataclass(frozen=True, slots=True)
class DecodedEntity:
    raw: RawEntity

    @property
    def index(self) -> int:
        return self.raw.index

    @property
    def attributes(self) -> EntityRef:
        return self.raw.attributes

    @property
    def entity_id(self) -> int | None:
        return self.raw.entity_id


@dataclass(frozen=True, slots=True)
class BodyEntity(DecodedEntity):
    pattern: EntityRef
    lump: EntityRef
    wire: EntityRef
    transform: EntityRef


@dataclass(frozen=True, slots=True)
class LumpEntity(DecodedEntity):
    pattern: EntityRef
    next_lump: EntityRef
    shell: EntityRef
    body: EntityRef


@dataclass(frozen=True, slots=True)
class ShellEntity(DecodedEntity):
    pattern: EntityRef
    next_shell: EntityRef
    subshell: EntityRef
    face: EntityRef
    wire: EntityRef
    lump: EntityRef


@dataclass(frozen=True, slots=True)
class FaceEntity(DecodedEntity):
    pattern: EntityRef
    next_face: EntityRef
    loop: EntityRef
    shell: EntityRef
    subshell: EntityRef
    surface: EntityRef
    reversed: bool
    double_sided: bool
    containment_in: bool | None


@dataclass(frozen=True, slots=True)
class LoopEntity(DecodedEntity):
    pattern: EntityRef
    next_loop: EntityRef
    coedge: EntityRef
    face: EntityRef


@dataclass(frozen=True, slots=True)
class CoedgeEntity(DecodedEntity):
    pattern: EntityRef
    next_coedge: EntityRef
    previous_coedge: EntityRef
    partner_coedge: EntityRef
    edge: EntityRef
    reversed: bool
    loop: EntityRef
    pcurve: EntityRef


@dataclass(frozen=True, slots=True)
class EdgeEntity(DecodedEntity):
    pattern: EntityRef
    start_vertex: EntityRef
    start_parameter: float | None
    end_vertex: EntityRef
    end_parameter: float | None
    coedge: EntityRef
    curve: EntityRef
    reversed: bool
    convexity: str | None


@dataclass(frozen=True, slots=True)
class VertexEntity(DecodedEntity):
    pattern: EntityRef
    edge: EntityRef
    point: EntityRef


@dataclass(frozen=True, slots=True)
class PointEntity(DecodedEntity):
    pattern: EntityRef
    location: Vec3


@dataclass(frozen=True, slots=True)
class StraightCurveEntity(DecodedEntity):
    pattern: EntityRef
    origin: Vec3
    direction: Vec3
    parameter_range: ParameterRange | None


@dataclass(frozen=True, slots=True)
class EllipseCurveEntity(DecodedEntity):
    pattern: EntityRef
    center: Vec3
    normal: Vec3
    major_axis: Vec3
    ratio: float
    parameter_range: ParameterRange | None

    @property
    def major_radius(self) -> float:
        return _native.geometry(self, "major_radius", ())

    @property
    def minor_radius(self) -> float:
        return _native.geometry(self, "minor_radius", ())

    @property
    def minor_axis(self) -> Vec3:
        return _native.geometry(self, "minor_axis", ())

    def is_circle(self, tolerance: float = 1e-12) -> bool:
        return _native.geometry(self, "is_circle", (tolerance,))

    def evaluate(self, parameter: float) -> Vec3:
        return _native.geometry(self, "evaluate", (parameter,))


@dataclass(frozen=True, slots=True)
class PlaneSurfaceEntity(DecodedEntity):
    pattern: EntityRef
    origin: Vec3
    normal: Vec3
    u_direction: Vec3
    reverse_v: bool
    u_range: ParameterRange | None
    v_range: ParameterRange | None

    @property
    def v_direction(self) -> Vec3:
        return _native.geometry(self, "v_direction", ())


@dataclass(frozen=True, slots=True)
class ConeSurfaceEntity(DecodedEntity):
    pattern: EntityRef
    center: Vec3
    axis: Vec3
    major_axis: Vec3
    ratio: float
    profile_range: ParameterRange | None
    sin_half_angle: float
    cos_half_angle: float
    reference_radius: float
    reversed: bool
    u_range: ParameterRange | None
    v_range: ParameterRange | None

    @property
    def major_direction(self) -> Vec3:
        return _native.geometry(self, "major_direction", ())

    @property
    def minor_direction(self) -> Vec3:
        return _native.geometry(self, "minor_direction", ())

    @property
    def minor_radius(self) -> float:
        return _native.geometry(self, "minor_radius", ())

    def is_cylinder(self, tolerance: float = 1e-12) -> bool:
        return _native.geometry(self, "is_cylinder", (tolerance,))

    def is_circular(self, tolerance: float = 1e-12) -> bool:
        return _native.geometry(self, "is_circular", (tolerance,))

    def radius_at(self, v_parameter: float) -> float:
        return _native.geometry(self, "radius_at", (v_parameter,))

    @property
    def apex(self) -> Vec3 | None:
        return _native.geometry(self, "apex", ())

    def evaluate(self, u_parameter: float, v_parameter: float) -> Vec3:
        return _native.geometry(self, "evaluate", (u_parameter, v_parameter))


@dataclass(frozen=True, slots=True)
class TransformEntity(DecodedEntity):
    matrix_values: tuple[float, ...]
    scale: float
    rotated: bool
    reflected: bool
    sheared: bool

    @property
    def linear_determinant(self) -> float:
        return _native.geometry(self, "linear_determinant", ())

    def transform_vector(self, vector: Vec3) -> Vec3:
        """Apply the linear part of the ACIS row-vector placement."""
        return _native.geometry(self, "transform_vector", (vector.x, vector.y, vector.z))

    def transform_point(self, point: Vec3) -> Vec3:
        """Apply ``world = scale * (point * matrix) + translation``."""
        return _native.geometry(self, "transform_point", (point.x, point.y, point.z))


SupportedEntity: TypeAlias = (
    BodyEntity
    | LumpEntity
    | ShellEntity
    | FaceEntity
    | LoopEntity
    | CoedgeEntity
    | EdgeEntity
    | VertexEntity
    | PointEntity
    | StraightCurveEntity
    | EllipseCurveEntity
    | PlaneSurfaceEntity
    | ConeSurfaceEntity
    | TransformEntity
)
ModelEntity: TypeAlias = SupportedEntity | RawEntity


class AcisModelView(Protocol):
    """Read interface shared by AcisModel and the legacy SatModel adapter."""

    @property
    def metadata(self) -> AcisMetadata: ...

    @property
    def entities(self) -> tuple[ModelEntity, ...]: ...

    def resolve(self, reference: EntityRef | int) -> ModelEntity | None: ...

    def bodies(self) -> tuple[BodyEntity, ...]: ...


@dataclass(frozen=True, slots=True)
class AcisModel:
    """Decoded entity table independent of its file encoding.

    Entities use contiguous zero-based indices. Foreign record identifiers
    remain in RawEntity.entity_id and SourceSpan; adapters remap all references.
    Construction checks identity and reference closure, not B-rep validity,
    source-dialect compatibility, or whether a carrier is active.
    """

    metadata: AcisMetadata
    entities: tuple[ModelEntity, ...]
    diagnostics: tuple[AcisDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entities", tuple(self.entities))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        _native.validate_model(self)

    def __len__(self) -> int:
        return len(self.entities)

    @overload
    def resolve(self, reference: EntityRef) -> ModelEntity | None: ...

    @overload
    def resolve(self, reference: int) -> ModelEntity | None: ...

    def resolve(self, reference: EntityRef | int) -> ModelEntity | None:
        index = _native.resolve_index(reference, len(self.entities))
        return None if index is None else self.entities[index]

    def to_native(self) -> _native.NativeModel:
        """Copy values into an immutable Rust-owned model, without SAT reparsing."""
        return _native.NativeModel.from_model(self)

    def bodies(self) -> tuple[BodyEntity, ...]:
        return tuple(
            entity for entity in self.entities if isinstance(entity, BodyEntity)
        )
