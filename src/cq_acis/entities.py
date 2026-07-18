"""Version-aware decoding of the first supported ACIS entity schemas."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, TypeAlias, overload

from .graph import RawEntity, SatEntityGraph, SatGraphError, parse_sat_graph
from .tokens import CountedString, EntityRef, NULL_REF, SatToken


class EntityDecodeError(SatGraphError):
    """Raised when a supported entity does not match its expected SAT schema."""


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float
    y: float
    z: float

    def cross(self, other: Vec3) -> Vec3:
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def dot(self, other: Vec3) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def __neg__(self) -> Vec3:
        return Vec3(-self.x, -self.y, -self.z)

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Vec3:
        return self * scalar

    @property
    def magnitude(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> Vec3:
        magnitude = self.magnitude
        if magnitude == 0.0:
            raise ValueError("cannot normalize a zero-length vector")
        return self * (1.0 / magnitude)


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
        return self.major_axis.magnitude

    @property
    def minor_radius(self) -> float:
        return self.major_radius * abs(self.ratio)

    @property
    def minor_axis(self) -> Vec3:
        return self.normal.normalized().cross(self.major_axis) * self.ratio

    def is_circle(self, tolerance: float = 1e-12) -> bool:
        return math.isclose(abs(self.ratio), 1.0, abs_tol=tolerance, rel_tol=0.0)

    def evaluate(self, parameter: float) -> Vec3:
        return (
            self.center
            + self.major_axis * math.cos(parameter)
            + self.minor_axis * math.sin(parameter)
        )


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
        direction = self.normal.cross(self.u_direction)
        return -direction if self.reverse_v else direction


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
        return self.major_axis.normalized()

    @property
    def minor_direction(self) -> Vec3:
        return self.axis.normalized().cross(self.major_direction)

    @property
    def minor_radius(self) -> float:
        return self.reference_radius * abs(self.ratio)

    def is_cylinder(self, tolerance: float = 1e-12) -> bool:
        return math.isclose(self.sin_half_angle, 0.0, abs_tol=tolerance)

    def is_circular(self, tolerance: float = 1e-12) -> bool:
        return math.isclose(abs(self.ratio), 1.0, abs_tol=tolerance, rel_tol=0.0)

    def radius_at(self, v_parameter: float) -> float:
        return self.reference_radius + v_parameter * self.sin_half_angle

    @property
    def apex(self) -> Vec3 | None:
        if self.is_cylinder():
            return None
        axial_offset = (
            self.reference_radius * self.cos_half_angle / self.sin_half_angle
        )
        return self.center - self.axis.normalized() * axial_offset

    def evaluate(self, u_parameter: float, v_parameter: float) -> Vec3:
        axis = self.axis.normalized()
        radial = (
            self.major_direction * math.cos(u_parameter)
            + self.minor_direction * (self.ratio * math.sin(u_parameter))
        )
        return (
            self.center
            + axis * (v_parameter * self.cos_half_angle)
            + radial * self.radius_at(v_parameter)
        )


@dataclass(frozen=True, slots=True)
class TransformEntity(DecodedEntity):
    matrix_values: tuple[float, ...]
    scale: float
    rotated: bool
    reflected: bool
    sheared: bool

    @property
    def linear_determinant(self) -> float:
        values = self.matrix_values
        determinant = (
            values[0] * (values[4] * values[8] - values[5] * values[7])
            - values[1] * (values[3] * values[8] - values[5] * values[6])
            + values[2] * (values[3] * values[7] - values[4] * values[6])
        )
        return self.scale**3 * determinant

    def transform_vector(self, vector: Vec3) -> Vec3:
        """Apply the linear part of the ACIS row-vector placement."""

        values = self.matrix_values
        return Vec3(
            self.scale
            * (vector.x * values[0] + vector.y * values[3] + vector.z * values[6]),
            self.scale
            * (vector.x * values[1] + vector.y * values[4] + vector.z * values[7]),
            self.scale
            * (vector.x * values[2] + vector.y * values[5] + vector.z * values[8]),
        )

    def transform_point(self, point: Vec3) -> Vec3:
        """Apply ``world = scale * (point * matrix) + translation``."""

        transformed = self.transform_vector(point)
        values = self.matrix_values
        return transformed + Vec3(values[9], values[10], values[11])


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


class _EntityReader:
    def __init__(self, graph: SatEntityGraph, raw: RawEntity):
        self.graph = graph
        self.raw = raw
        self.version = graph.header.save_version
        self.values = raw.values
        self.position = 0

    def _error(self, message: str) -> EntityDecodeError:
        return EntityDecodeError(
            f"record {self.raw.index} ({self.raw.type_name}) token "
            f"{self.position}: {message}"
        )

    def _take(self) -> SatToken:
        if self.position >= len(self.values):
            raise self._error("unexpected end of entity data")
        value = self.values[self.position]
        self.position += 1
        return value

    def peek(self) -> SatToken:
        if self.position >= len(self.values):
            raise self._error("unexpected end of entity data")
        return self.values[self.position]

    def next_is_number(self) -> bool:
        return type(self.peek()) in {int, float}

    def read_ref(self, expected_type: str | None = None) -> EntityRef:
        value = self._take()
        if not isinstance(value, EntityRef):
            raise self._error(f"expected entity reference, got {value!r}")
        target = self.graph.resolve(value)
        if target is not None and expected_type is not None:
            if expected_type in {"curve", "surface", "attrib"}:
                matches = target.type_name == expected_type or target.type_name.endswith(
                    f"-{expected_type}"
                )
            else:
                matches = target.type_name == expected_type
            if not matches:
                raise self._error(
                    f"expected {expected_type!r} reference, got "
                    f"{target.type_name!r} at ${target.index}"
                )
        return value

    def read_int(self) -> int:
        value = self._take()
        if type(value) is not int:
            raise self._error(f"expected integer, got {value!r}")
        return value

    def read_float(self) -> float:
        value = self._take()
        if type(value) not in {int, float}:
            raise self._error(f"expected number, got {value!r}")
        return float(value)

    def read_vec3(self) -> Vec3:
        return Vec3(self.read_float(), self.read_float(), self.read_float())

    def read_word(self) -> str:
        value = self._take()
        if isinstance(value, CountedString):
            return value.value
        if not isinstance(value, str):
            raise self._error(f"expected word, got {value!r}")
        return value

    def read_string(self) -> str:
        value = self._take()
        if isinstance(value, CountedString):
            return value.value
        if self.version >= 700:
            raise self._error(f"expected @-counted string, got {value!r}")
        if type(value) is not int:
            raise self._error(f"expected string length, got {value!r}")
        string_length = value
        word = self._take()
        if not isinstance(word, str):
            raise self._error(f"expected string value, got {word!r}")
        if len(word) != string_length:
            raise self._error(
                f"string length mismatch: declared {string_length}, got {len(word)}"
            )
        return word

    def read_bool(
        self, true_word: str, false_word: str, *, allow_numeric: bool = False
    ) -> bool:
        value = self._take()
        if allow_numeric and type(value) is int and value in {0, 1}:
            return bool(value)
        if isinstance(value, CountedString):
            value = value.value
        if value == true_word:
            return True
        if value == false_word:
            return False
        raise self._error(
            f"expected {true_word!r}/{false_word!r}, got {value!r}"
        )

    def read_bound(self) -> float | None:
        marker = self.read_word()
        if marker == "I":
            return None
        if marker == "F":
            return self.read_float()
        raise self._error(f"expected interval marker 'I' or 'F', got {marker!r}")

    def read_range(self) -> ParameterRange:
        return ParameterRange(self.read_bound(), self.read_bound())

    def finish(self) -> None:
        if self.position != len(self.values):
            remaining = self.values[self.position :]
            raise self._error(f"unconsumed entity data: {remaining!r}")


def _read_pattern(reader: _EntityReader) -> EntityRef:
    if reader.version >= 700:
        return reader.read_ref("pattern")
    return NULL_REF


def _read_orientation(reader: _EntityReader) -> bool:
    return reader.read_bool(
        "reversed", "forward", allow_numeric=reader.version < 400
    )


def _decode_body(reader: _EntityReader) -> BodyEntity:
    result = BodyEntity(
        reader.raw,
        _read_pattern(reader),
        reader.read_ref("lump"),
        reader.read_ref("wire"),
        reader.read_ref("transform"),
    )
    reader.finish()
    return result


def _decode_lump(reader: _EntityReader) -> LumpEntity:
    result = LumpEntity(
        reader.raw,
        _read_pattern(reader),
        reader.read_ref("lump"),
        reader.read_ref("shell"),
        reader.read_ref("body"),
    )
    reader.finish()
    return result


def _decode_shell(reader: _EntityReader) -> ShellEntity:
    pattern = _read_pattern(reader)
    next_shell = reader.read_ref("shell")
    subshell = reader.read_ref("subshell")
    face = reader.read_ref("face")
    wire = reader.read_ref("wire") if reader.version >= 400 else NULL_REF
    lump = reader.read_ref("lump")
    reader.finish()
    return ShellEntity(reader.raw, pattern, next_shell, subshell, face, wire, lump)


def _decode_face(reader: _EntityReader) -> FaceEntity:
    pattern = _read_pattern(reader)
    next_face = reader.read_ref("face")
    loop = reader.read_ref("loop")
    shell = reader.read_ref("shell")
    subshell = reader.read_ref("subshell")
    surface = reader.read_ref("surface")
    reversed_ = reader.read_bool("reversed", "forward")
    double_sided = reader.read_bool("double", "single")
    containment = reader.read_bool("in", "out") if double_sided else None
    reader.finish()
    return FaceEntity(
        reader.raw,
        pattern,
        next_face,
        loop,
        shell,
        subshell,
        surface,
        reversed_,
        double_sided,
        containment,
    )


def _decode_loop(reader: _EntityReader) -> LoopEntity:
    result = LoopEntity(
        reader.raw,
        _read_pattern(reader),
        reader.read_ref("loop"),
        reader.read_ref("coedge"),
        reader.read_ref("face"),
    )
    reader.finish()
    return result


def _decode_coedge(reader: _EntityReader) -> CoedgeEntity:
    pattern = _read_pattern(reader)
    next_coedge = reader.read_ref("coedge")
    previous_coedge = reader.read_ref("coedge")
    partner_coedge = reader.read_ref("coedge")
    edge = reader.read_ref("edge")
    reversed_ = _read_orientation(reader)
    loop = reader.read_ref("loop")
    pcurve = reader.read_ref("pcurve")
    reader.finish()
    return CoedgeEntity(
        reader.raw,
        pattern,
        next_coedge,
        previous_coedge,
        partner_coedge,
        edge,
        reversed_,
        loop,
        pcurve,
    )


def _decode_edge(reader: _EntityReader) -> EdgeEntity:
    pattern = _read_pattern(reader)
    start_vertex = reader.read_ref("vertex")
    start_parameter = reader.read_float() if reader.version >= 500 else None
    end_vertex = reader.read_ref("vertex")
    end_parameter = reader.read_float() if reader.version >= 500 else None
    coedge = reader.read_ref("coedge")
    curve = reader.read_ref("curve")
    reversed_ = _read_orientation(reader)
    convexity = reader.read_string() if reader.version >= 500 else None
    reader.finish()
    return EdgeEntity(
        reader.raw,
        pattern,
        start_vertex,
        start_parameter,
        end_vertex,
        end_parameter,
        coedge,
        curve,
        reversed_,
        convexity,
    )


def _decode_vertex(reader: _EntityReader) -> VertexEntity:
    result = VertexEntity(
        reader.raw,
        _read_pattern(reader),
        reader.read_ref("edge"),
        reader.read_ref("point"),
    )
    reader.finish()
    return result


def _decode_point(reader: _EntityReader) -> PointEntity:
    result = PointEntity(reader.raw, _read_pattern(reader), reader.read_vec3())
    reader.finish()
    return result


def _decode_straight_curve(reader: _EntityReader) -> StraightCurveEntity:
    pattern = _read_pattern(reader)
    origin = reader.read_vec3()
    direction = reader.read_vec3()
    parameter_range = reader.read_range() if reader.version >= 400 else None
    reader.finish()
    return StraightCurveEntity(
        reader.raw, pattern, origin, direction, parameter_range
    )


def _decode_ellipse_curve(reader: _EntityReader) -> EllipseCurveEntity:
    pattern = _read_pattern(reader)
    center = reader.read_vec3()
    normal = reader.read_vec3()
    major_axis = reader.read_vec3()
    ratio = reader.read_float()
    parameter_range = reader.read_range() if reader.version >= 400 else None
    reader.finish()
    return EllipseCurveEntity(
        reader.raw,
        pattern,
        center,
        normal,
        major_axis,
        ratio,
        parameter_range,
    )


def _decode_plane_surface(reader: _EntityReader) -> PlaneSurfaceEntity:
    pattern = _read_pattern(reader)
    origin = reader.read_vec3()
    normal = reader.read_vec3()
    u_direction = reader.read_vec3()
    reverse_v = reader.read_bool(
        "reverse_v", "forward_v", allow_numeric=reader.version < 400
    )
    if reader.version >= 400:
        u_range = reader.read_range()
        v_range = reader.read_range()
    else:
        u_range = None
        v_range = None
    reader.finish()
    return PlaneSurfaceEntity(
        reader.raw,
        pattern,
        origin,
        normal,
        u_direction,
        reverse_v,
        u_range,
        v_range,
    )


def _decode_cone_surface(reader: _EntityReader) -> ConeSurfaceEntity:
    pattern = _read_pattern(reader)
    center = reader.read_vec3()
    axis = reader.read_vec3()
    major_axis = reader.read_vec3()
    ratio = reader.read_float()
    profile_range = reader.read_range() if reader.version >= 400 else None
    sin_half_angle = reader.read_float()
    cos_half_angle = reader.read_float()

    # Some v400 writers omit this scaling field; the magnitude of major_axis
    # is the equivalent reference radius. It is present in the corpus at v600+.
    if reader.version >= 400 and reader.next_is_number():
        reference_radius = reader.read_float()
    else:
        reference_radius = major_axis.magnitude

    reversed_ = reader.read_bool(
        "reversed", "forward", allow_numeric=reader.version < 400
    )
    if reader.version >= 400:
        u_range = reader.read_range()
        v_range = reader.read_range()
    else:
        u_range = None
        v_range = None
    reader.finish()
    return ConeSurfaceEntity(
        reader.raw,
        pattern,
        center,
        axis,
        major_axis,
        ratio,
        profile_range,
        sin_half_angle,
        cos_half_angle,
        reference_radius,
        reversed_,
        u_range,
        v_range,
    )


def _decode_transform(reader: _EntityReader) -> TransformEntity:
    matrix_values = tuple(reader.read_float() for _ in range(12))
    scale = reader.read_float()
    rotated = reader.read_bool("rotate", "no_rotate", allow_numeric=True)
    reflected = reader.read_bool("reflect", "no_reflect", allow_numeric=True)
    sheared = reader.read_bool("shear", "no_shear", allow_numeric=True)
    reader.finish()
    return TransformEntity(
        reader.raw, matrix_values, scale, rotated, reflected, sheared
    )


Decoder: TypeAlias = Callable[[_EntityReader], SupportedEntity]
_DECODERS: dict[str, Decoder] = {
    "body": _decode_body,
    "lump": _decode_lump,
    "shell": _decode_shell,
    "face": _decode_face,
    "loop": _decode_loop,
    "coedge": _decode_coedge,
    "edge": _decode_edge,
    "vertex": _decode_vertex,
    "point": _decode_point,
    "straight-curve": _decode_straight_curve,
    "ellipse-curve": _decode_ellipse_curve,
    "plane-surface": _decode_plane_surface,
    "cone-surface": _decode_cone_surface,
    "transform": _decode_transform,
}
SUPPORTED_ENTITY_TYPES = frozenset(_DECODERS)


def decode_entity(graph: SatEntityGraph, raw: RawEntity) -> ModelEntity:
    """Decode a supported entity, preserving unsupported records as-is."""

    decoder = _DECODERS.get(raw.type_name)
    if decoder is None:
        return raw
    return decoder(_EntityReader(graph, raw))


@dataclass(frozen=True, slots=True)
class SatModel:
    graph: SatEntityGraph
    entities: tuple[ModelEntity, ...]

    def __len__(self) -> int:
        return len(self.entities)

    @overload
    def resolve(self, reference: EntityRef) -> ModelEntity | None: ...

    @overload
    def resolve(self, reference: int) -> ModelEntity: ...

    def resolve(self, reference: EntityRef | int) -> ModelEntity | None:
        index = reference.index if isinstance(reference, EntityRef) else reference
        if index == -1:
            return None
        self.graph.resolve(index)
        return self.entities[index]

    def bodies(self) -> tuple[BodyEntity, ...]:
        return tuple(
            entity for entity in self.entities if isinstance(entity, BodyEntity)
        )


def decode_sat_model(graph: SatEntityGraph) -> SatModel:
    """Decode all currently supported entities in a validated graph."""

    return SatModel(
        graph,
        tuple(decode_entity(graph, entity) for entity in graph.entities),
    )


def parse_sat_model(data: str | bytes) -> SatModel:
    """Parse SAT data through framing, graph validation, and typed decoding."""

    return decode_sat_model(parse_sat_graph(data))
