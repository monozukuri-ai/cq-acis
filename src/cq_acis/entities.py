"""Version-aware decoding of the first supported ACIS entity schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeAlias, overload

from .model import (
    AcisContainer,
    AcisMetadata,
    AcisModel,
    BodyEntity,
    CoedgeEntity,
    ConeSurfaceEntity,
    DecodedEntity,
    EdgeEntity,
    EllipseCurveEntity,
    FaceEntity,
    LoopEntity,
    LumpEntity,
    ModelEntity,
    ParameterRange,
    PlaneSurfaceEntity,
    PointEntity,
    ShellEntity,
    StraightCurveEntity,
    SupportedEntity,
    TransformEntity,
    Vec3,
    VertexEntity,
)
from .graph import RawEntity, SatEntityGraph, SatGraphError, parse_sat_graph
from .tokens import CountedString, EntityRef, NULL_REF, SatToken


class EntityDecodeError(SatGraphError):
    """Raised when a supported entity does not match its expected SAT schema."""


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

    @property
    def metadata(self) -> AcisMetadata:
        """Expose source facts without requiring consumers to read SAT headers."""
        header = self.graph.header
        return AcisMetadata(
            units_mm=header.units_mm,
            resabs=header.resabs,
            resnor=header.resnor,
            container=AcisContainer.SAT,
            save_version=header.save_version,
            product_id=header.product_id,
            modeler_version=header.modeler_version,
            creation_date=header.creation_date,
        )

    def as_acis_model(self) -> AcisModel:
        """Share decoded entities and original record attachments without reparsing."""
        return AcisModel(self.metadata, self.entities)

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
