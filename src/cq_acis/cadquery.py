"""Conversion of the supported analytic ACIS subset into CadQuery shapes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from ._native import NativeModel
from .model import (
    AcisModelView,
    BodyEntity,
    ConeSurfaceEntity,
    BSplineSurfaceEntity,
    BSplineCurveEntity,
    TorusSurfaceEntity,
    SphereSurfaceEntity,
    CoedgeEntity,
    DecodedEntity,
    EdgeEntity,
    EntityRef,
    EllipseCurveEntity,
    FaceEntity,
    LoopEntity,
    LumpEntity,
    PlaneSurfaceEntity,
    PointEntity,
    RawEntity,
    ShellEntity,
    StraightCurveEntity,
    TransformEntity,
    Vec3,
    VertexEntity,
)

if TYPE_CHECKING:
    import cadquery as cq


class CadQueryDependencyError(ImportError):
    """Raised when the optional CadQuery conversion dependency is unavailable."""


class CadQueryConversionError(RuntimeError):
    """A classified conversion failure; unsupported geometry is never dropped."""

    def __init__(self, message: str, *, code: str = "geometry.conversion_failed"):
        super().__init__(message)
        self.code = code


EntityT = TypeVar("EntityT", bound=DecodedEntity)


@dataclass(frozen=True, slots=True)
class _Placement:
    transform: TransformEntity | None
    unit_scale: float

    @property
    def orientation_sign(self) -> float:
        if self.transform is None or self.transform.linear_determinant > 0.0:
            return 1.0
        return -1.0

    @property
    def preserves_circles(self) -> bool:
        if self.transform is None:
            return True
        if self.transform.sheared:
            return False
        basis = [self.transform.transform_vector(v) for v in
                 (Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1))]
        size = basis[0].magnitude
        return size > 0 and all(math.isclose(v.magnitude, size, rel_tol=1e-9)
                                for v in basis) and all(
            abs(basis[i].dot(basis[j])) <= 1e-9 * size * size
            for i in range(3) for j in range(i))

    def vector(self, vector: Vec3) -> Vec3:
        transformed = (
            self.transform.transform_vector(vector) if self.transform else vector
        )
        return transformed * self.unit_scale

    def oriented_direction(self, vector: Vec3) -> Vec3:
        return self.vector(vector).normalized() * self.orientation_sign

    def point_vector(self, point: Vec3) -> Vec3:
        transformed = self.transform.transform_point(point) if self.transform else point
        return transformed * self.unit_scale

    def point(self, point: Vec3) -> tuple[float, float, float]:
        transformed = self.point_vector(point)
        return transformed.x, transformed.y, transformed.z


@dataclass(frozen=True, slots=True)
class _CylinderGeometry:
    surface: object
    center: Vec3
    axis: Vec3
    x_direction: Vec3
    y_direction: Vec3
    radius: float
    tolerance: float

    def uv(self, point: Vec3) -> tuple[float, float]:
        relative = point - self.center
        u_parameter = math.atan2(
            relative.dot(self.y_direction), relative.dot(self.x_direction)
        )
        v_parameter = relative.dot(self.axis)
        radial = relative - self.axis * v_parameter
        if not math.isclose(
            radial.magnitude,
            self.radius,
            abs_tol=self.tolerance * 10.0,
            rel_tol=1e-9,
        ):
            raise CadQueryConversionError(
                "cylinder boundary point is not on the decoded surface"
            )
        return u_parameter, v_parameter


@dataclass(frozen=True, slots=True)
class _ConeGeometry(_CylinderGeometry):
    sin_half_angle: float
    cos_half_angle: float
    reference_radius: float

    def uv(self, point: Vec3) -> tuple[float, float]:
        relative = point - self.center
        if abs(self.cos_half_angle) <= 1e-12:
            raise CadQueryConversionError("cone surface has no axial parameter")
        v_parameter = relative.dot(self.axis)
        radial = relative - self.axis * v_parameter
        slope = self.sin_half_angle / self.cos_half_angle
        expected_radius = self.reference_radius + v_parameter * slope
        if expected_radius <= self.tolerance:
            raise CadQueryConversionError("cone boundary radius is not positive")
        if not math.isclose(
            radial.magnitude,
            expected_radius,
            abs_tol=self.tolerance * 10.0,
            rel_tol=1e-9,
        ):
            raise CadQueryConversionError(
                "cone boundary point is not on the decoded surface"
            )
        u_parameter = math.atan2(
            radial.dot(self.y_direction), radial.dot(self.x_direction)
        )
        return u_parameter, v_parameter / self.cos_half_angle


@dataclass(frozen=True, slots=True)
class _EllipseCylinderGeometry(_CylinderGeometry):
    minor_radius: float

    def uv(self, point: Vec3) -> tuple[float, float]:
        relative = point - self.center
        x = relative.dot(self.x_direction) / self.radius
        y = relative.dot(self.y_direction) / self.minor_radius
        u, v = math.atan2(y, x), relative.dot(self.axis)
        actual = self.surface.Value(u, v)
        if (Vec3(actual.X(), actual.Y(), actual.Z()) - point).magnitude > 10 * self.tolerance:
            raise CadQueryConversionError("elliptical cylinder boundary is off surface", code="geometry.pcurve_mismatch")
        return u, v


@dataclass(frozen=True, slots=True)
class _SphereGeometry(_CylinderGeometry):
    def uv(self, point: Vec3) -> tuple[float, float]:
        relative = point - self.center
        if abs(relative.magnitude - self.radius) > self.tolerance * 10:
            raise CadQueryConversionError("sphere boundary is off surface", code="geometry.pcurve_mismatch")
        x, y, z = (relative.dot(d) for d in (self.x_direction, self.y_direction, self.axis))
        if math.hypot(x, y) <= self.tolerance:
            raise CadQueryConversionError("sphere pole requires a degenerate pcurve", code="geometry.singular_pcurve_unsupported")
        return math.atan2(y, x), math.atan2(z, math.hypot(x, y))


@dataclass(frozen=True, slots=True)
class _TorusGeometry(_CylinderGeometry):
    minor_radius: float

    def uv(self, point: Vec3) -> tuple[float, float]:
        relative = point - self.center
        x, y, z = (relative.dot(d) for d in (self.x_direction, self.y_direction, self.axis))
        radial = math.hypot(x, y) - self.radius
        if abs(math.hypot(radial, z) - self.minor_radius) > self.tolerance * 10:
            raise CadQueryConversionError("torus boundary is off surface", code="geometry.pcurve_mismatch")
        return math.atan2(y, x), math.atan2(z, radial)


def _load_cadquery():
    try:
        import cadquery as cq
    except ImportError as error:
        raise CadQueryDependencyError(
            "CadQuery conversion requires the optional dependency; "
            "install cq-acis[cadquery]"
        ) from error
    return cq


class CadQueryConverter:
    """Build exact analytic CadQuery B-reps from a shared ACIS model."""

    def __init__(self, model: AcisModelView):
        # CadQuery walks the same references repeatedly. Materialize the Python
        # view once instead of copying native entity fields on every lookup.
        if isinstance(model, NativeModel):
            model = model.to_model()
        self.model = model
        self.cq = _load_cadquery()
        unit_scale = model.metadata.units_mm or 1.0
        self.tolerance = (model.metadata.resabs or 1e-6) * unit_scale
        self.pcurve_max_deviation = 0.0
        self.pcurve_checks: list[dict] = []
        self.degenerate_edges: list[dict] = []
        self.analytic_trim_faces: list[dict] = []
        self.tolerant_endpoints: list[dict] = []
        self.tolerant_boundaries: list[dict] = []
        self.bounded_surface_faces: list[dict] = []
        self.saved_pcurves: list[dict] = []
        self.source_edge_tolerances: list[dict] = []
        self.supported_curve_checks: list[dict] = []
        self.spline_endpoint_failures: list[dict] = []
        self.associated_pcurves: list[dict] = []
        self.plane_wire_orientations: list[dict] = []
        self.inline_pcurves: list[dict] = []
        self.inline_reparameterizations: list[dict] = []
        self.tolerant_line_trims: list[dict] = []
        self.tolerant_pcurve_joins: list[dict] = []
        self._supported_curves = {}
        self._checked_supported_curves = set()
        self.resolved_subtypes: list[dict] = []
        self.subtype_failures: dict[int, str] = {}
        self._extension_native = None
        self._geometry_cache = {}
        self._topology_views = {}
        self.pcurve_count = 0

    def _native_extensions(self):
        if self._extension_native is None:
            self._extension_native = NativeModel.from_model(self.model)
        return self._extension_native

    def _resolve_geometry(self, reference):
        entity = self.model.resolve(reference)
        if not isinstance(entity, RawEntity):
            return entity
        if entity.index not in self._geometry_cache:
            from .model import AcisModelError
            resolved = None
            try:
                resolved = self._native_extensions().resolve_subtype(reference)
            except AcisModelError as error:
                self.subtype_failures[entity.index] = str(error)
            supported = None
            if resolved is None:
                try:
                    supported = self._native_extensions().supported_curve(reference)
                except AcisModelError as error:
                    raise CadQueryConversionError(str(error), code='geometry.supported_curve_unsupported') from error
            if supported is not None:
                self._supported_curves[entity.index] = supported
            self._geometry_cache[entity.index] = resolved.geometry if resolved else supported.curve if supported else entity
            if resolved:
                definition = resolved.definition
                self.resolved_subtypes.append({
                    'entity': entity.index, 'subtype': definition.index,
                    'definition_entity': definition.entity_index,
                    'definition_value_start': definition.value_start,
                    'definition_value_end': definition.value_end,
                })
        return self._geometry_cache[entity.index]

    def _require(
        self,
        reference: EntityRef | int,
        expected_type: type[EntityT],
        *,
        context: str,
    ) -> EntityT:
        entity = self.model.resolve(reference)
        if isinstance(entity, RawEntity) and expected_type in (EdgeEntity, CoedgeEntity):
            from .extensions import TolerantEdge, TolerantCoedge
            view = self._tolerant_view(entity.index, context=context)
            if expected_type is EdgeEntity and isinstance(view, TolerantEdge):
                entity = view.edge
            elif expected_type is CoedgeEntity and isinstance(view, TolerantCoedge):
                entity = view.coedge
        if not isinstance(entity, expected_type):
            if entity is None:
                actual = "null"
            elif isinstance(entity, RawEntity):
                actual = entity.type_name
            else:
                actual = entity.raw.type_name
            raise CadQueryConversionError(
                f"{context}: expected {expected_type.__name__}, got {actual}",
                code="geometry.tolerant_topology_unsupported" if actual in
                ("tvertex-vertex", "tedge-edge", "tcoedge-coedge", "tolerant-vertex", "tolerant-edge", "tolerant-coedge")
                else "geometry.conversion_failed"
            )
        return entity

    def _tolerant_view(self, reference, *, context):
        from .model import AcisModelError
        index = reference.index if isinstance(reference, EntityRef) else reference
        if index not in self._topology_views:
            try:
                self._topology_views[index] = self._native_extensions().tolerant_topology(index)
            except AcisModelError as error:
                raise CadQueryConversionError(
                    f"{context}: {error}", code="geometry.tolerant_topology_unsupported"
                ) from error
        return self._topology_views[index]

    def _linked_entities(
        self,
        start: EntityRef,
        expected_type: type[EntityT],
        next_attribute: str,
        *,
        context: str,
    ) -> tuple[EntityT, ...]:
        entities: list[EntityT] = []
        seen: set[int] = set()
        current = start
        while not current.is_null:
            if current.index in seen:
                raise CadQueryConversionError(
                    f"{context}: linked list cycles at ${current.index}"
                )
            seen.add(current.index)
            entity = self._require(current, expected_type, context=context)
            entities.append(entity)
            next_reference = getattr(entity, next_attribute)
            if not isinstance(next_reference, EntityRef):
                raise CadQueryConversionError(
                    f"{context}: {next_attribute} is not an entity reference"
                )
            current = next_reference
        return tuple(entities)

    def _coedges(self, loop: LoopEntity) -> tuple[CoedgeEntity, ...]:
        if loop.coedge.is_null:
            raise CadQueryConversionError(f"loop ${loop.index} has no coedge")

        coedges: list[CoedgeEntity] = []
        seen: set[int] = set()
        current = loop.coedge
        while True:
            if current.is_null:
                raise CadQueryConversionError(
                    f"loop ${loop.index} coedge chain ends before closing"
                )
            if current.index in seen:
                if current.index == loop.coedge.index:
                    break
                raise CadQueryConversionError(
                    f"loop ${loop.index} coedge chain cycles at ${current.index}"
                )
            seen.add(current.index)
            coedge = self._require(
                current, CoedgeEntity, context=f"loop ${loop.index}"
            )
            if coedge.loop.index != loop.index:
                raise CadQueryConversionError(
                    f"coedge ${coedge.index} belongs to loop ${coedge.loop.index}, "
                    f"not ${loop.index}"
                )
            coedges.append(coedge)
            current = coedge.next_coedge
        if any(c.index in self._topology_views for c in coedges):
            for previous, coedge in zip(coedges[-1:] + coedges[:-1], coedges):
                if coedge.previous_coedge.index != previous.index:
                    raise CadQueryConversionError(
                        f"loop ${loop.index}: inconsistent previous coedge",
                        code="geometry.tolerant_topology_mismatch")
        return tuple(coedges)

    def _body_placement(self, body: BodyEntity) -> _Placement:
        transform = None
        if not body.transform.is_null:
            transform = self._require(
                body.transform,
                TransformEntity,
                context=f"body ${body.index} transform",
            )
            if math.isclose(transform.linear_determinant, 0.0, abs_tol=1e-15):
                raise CadQueryConversionError(
                    f"body ${body.index}: transform is singular"
                )
        unit_scale = self.model.metadata.units_mm
        if unit_scale is None:
            unit_scale = 1.0
        if unit_scale <= 0.0:
            raise CadQueryConversionError(
                f"body ${body.index}: invalid millimetre unit scale {unit_scale}"
            )
        return _Placement(transform, unit_scale)

    def _vertex_location(self, reference: EntityRef, *, context: str) -> Vec3:
        from .extensions import TolerantVertex
        entity = self.model.resolve(reference)
        view = self._tolerant_view(reference, context=context) if isinstance(entity, RawEntity) else None
        vertex = view.vertex if isinstance(view, TolerantVertex) else self._require(reference, VertexEntity, context=context)
        point = self._require(
            vertex.point, PointEntity, context=f"vertex ${vertex.index}"
        )
        return point.location

    def _vertex_point(
        self, reference: EntityRef, placement: _Placement, *, context: str
    ) -> tuple[float, float, float]:
        return placement.point(self._vertex_location(reference, context=context))

    def _reverse_edge(self, edge):
        from OCP.TopoDS import TopoDS

        return self.cq.Edge(TopoDS.Edge_s(edge.wrapped.Reversed()))

    def _straight_edge(
        self, edge: EdgeEntity, coedge: CoedgeEntity, placement: _Placement, curve=None
    ):
        if edge.start_vertex.is_null or edge.end_vertex.is_null:
            raise CadQueryConversionError(
                f"edge ${edge.index}: straight edge requires two vertices"
            )
        if curve is not None:
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
            from OCP.Geom import Geom_Line
            from OCP.gp import gp_Dir, gp_Pnt
            direction = placement.vector(curve.direction)
            if direction.magnitude <= 0 or not math.isfinite(direction.magnitude):
                raise CadQueryConversionError("invalid tolerant line direction",
                                              code="geometry.tolerant_parameter_mismatch")
            origin = placement.point(curve.origin)
            line = Geom_Line(gp_Pnt(*origin), gp_Dir(direction.x, direction.y, direction.z))
            sign = -1 if edge.reversed else 1
            parameters = [sign * t * direction.magnitude for t in (edge.start_parameter, edge.end_parameter)]
            builder = BRepBuilderAPI_MakeEdge(line, min(parameters), max(parameters))
            if not builder.IsDone():
                raise CadQueryConversionError("tolerant source line construction failed")
            result = self.cq.Edge(builder.Edge())
            return self._reverse_edge(result) if edge.reversed ^ coedge.reversed else result
        start = self._vertex_point(
            edge.start_vertex, placement, context=f"edge ${edge.index} start"
        )
        end = self._vertex_point(
            edge.end_vertex, placement, context=f"edge ${edge.index} end"
        )
        try:
            result = self.cq.Edge.makeLine(start, end)
        except Exception as error:
            raise CadQueryConversionError(
                f"edge ${edge.index}: CadQuery could not build the line"
            ) from error
        return self._reverse_edge(result) if coedge.reversed else result

    def _ellipse_parameter(self, curve: EllipseCurveEntity, point: Vec3) -> float:
        major_direction = curve.major_axis.normalized()
        minor_direction = (
            curve.normal.normalized().cross(major_direction)
            * (1.0 if curve.ratio >= 0.0 else -1.0)
        )
        relative = point - curve.center
        return math.atan2(
            relative.dot(minor_direction) / curve.minor_radius,
            relative.dot(major_direction) / curve.major_radius
        )

    def _ellipse_edge_parameters(
        self, edge: EdgeEntity, curve: EllipseCurveEntity
    ) -> tuple[float, float, bool]:
        if edge.start_vertex.is_null or edge.end_vertex.is_null:
            raise CadQueryConversionError(
                f"edge ${edge.index}: ellipse edge requires two vertices"
            )
        if edge.start_parameter is not None and edge.end_parameter is not None:
            direction = -1.0 if edge.reversed else 1.0
            start = direction * edge.start_parameter
            end = direction * edge.end_parameter
        else:
            start_location = self._vertex_location(
                edge.start_vertex, context=f"edge ${edge.index} start"
            )
            end_location = self._vertex_location(
                edge.end_vertex, context=f"edge ${edge.index} end"
            )
            start = self._ellipse_parameter(curve, start_location)
            end = self._ellipse_parameter(curve, end_location)

        full_circle = edge.start_vertex.index == edge.end_vertex.index
        if edge.reversed:
            if full_circle:
                end = start - 2.0 * math.pi
            while end >= start:
                end -= 2.0 * math.pi
            return end, start, True
        if full_circle:
            end = start + 2.0 * math.pi
        while end <= start:
            end += 2.0 * math.pi
        return start, end, False

    def _ellipse_edge(
        self,
        edge: EdgeEntity,
        coedge: CoedgeEntity,
        curve: EllipseCurveEntity,
        placement: _Placement,
    ):
        if not placement.preserves_circles:
            raise CadQueryConversionError(
                f"edge ${edge.index}: sheared ellipse placement is not supported"
            )

        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        from OCP.Geom import Geom_Circle, Geom_Ellipse
        from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Elips, gp_Pnt

        center = placement.point_vector(curve.center)
        normal = placement.oriented_direction(
            curve.normal * (1.0 if curve.ratio >= 0.0 else -1.0)
        )
        major_axis = placement.vector(curve.major_axis)
        radius = major_axis.magnitude
        if radius <= self.tolerance:
            raise CadQueryConversionError(
                f"edge ${edge.index}: circle radius is too small"
            )
        x_direction = major_axis.normalized()
        minor_radius = radius * abs(curve.ratio)
        if minor_radius <= self.tolerance:
            raise CadQueryConversionError(
                f"edge ${edge.index}: ellipse minor radius is too small"
            )
        first, last, reverse_for_edge = self._ellipse_edge_parameters(edge, curve)
        try:
            axis = gp_Ax2(
                gp_Pnt(center.x, center.y, center.z),
                gp_Dir(normal.x, normal.y, normal.z),
                gp_Dir(x_direction.x, x_direction.y, x_direction.z),
            )
            if curve.is_circle():
                analytic_curve = Geom_Circle(gp_Circ(axis, radius))
            else:
                if abs(curve.ratio) > 1.0:
                    raise ValueError(
                        "ellipse ratio greater than one requires axis swapping"
                    )
                ellipse_axis = gp_Ax2(
                    gp_Pnt(center.x, center.y, center.z),
                    gp_Dir(normal.x, normal.y, normal.z),
                    gp_Dir(x_direction.x, x_direction.y, x_direction.z),
                )
                analytic_curve = Geom_Ellipse(
                    gp_Elips(ellipse_axis, radius, minor_radius)
                )
            builder = BRepBuilderAPI_MakeEdge(analytic_curve, first, last)
            if not builder.IsDone():
                raise ValueError("OCP circle edge builder did not complete")
            result = self.cq.Edge(builder.Edge())
        except Exception as error:
            raise CadQueryConversionError(
                f"edge ${edge.index}: CadQuery could not build the circle arc"
            ) from error
        if reverse_for_edge:
            result = self._reverse_edge(result)
        if coedge.reversed:
            result = self._reverse_edge(result)
        return result

    def _edge(self, coedge: CoedgeEntity, placement: _Placement):
        if coedge.raw.type_name == "tcoedge-coedge":
            self._tolerant_view(coedge.index, context="tolerant coedge")
        edge = self._require(
            coedge.edge, EdgeEntity, context=f"coedge ${coedge.index}"
        )
        curve = self._resolve_geometry(edge.curve)
        tolerant = (edge.index in self._topology_views or coedge.index in self._topology_views
                or (isinstance(curve, (EllipseCurveEntity, StraightCurveEntity))
                    and any(isinstance(self.model.resolve(v), RawEntity)
                            for v in (edge.start_vertex, edge.end_vertex))))
        if curve is not None and curve.index in self._supported_curves:
            from ._supported_curves import validate_fit
            self.supported_curve_checks.append(validate_fit(self, self._supported_curves[curve.index], placement))
            self._checked_supported_curves.add(curve.index)
        if isinstance(curve, StraightCurveEntity):
            edge = self._tolerant_line_interval(edge, coedge, curve, placement)
            result = self._straight_edge(edge, coedge, placement, curve if tolerant else None)
        elif isinstance(curve, EllipseCurveEntity):
            result = self._ellipse_edge(edge, coedge, curve, placement)
        elif isinstance(curve, BSplineCurveEntity):
            result = self._bspline_edge(edge, coedge, curve, placement)
        else:
            result = None
        if result is not None:
            inline = self._inline_curve(coedge)
            endpoint_bound = self._validate_inline_use(coedge, result, placement) if inline else None
            if tolerant:
                try:
                    self._check_tolerant_boundary(edge, coedge, curve, placement)
                except CadQueryConversionError as error:
                    if error.code != 'geometry.tolerant_endpoint_mismatch':
                        raise
                    if endpoint_bound is None and not coedge.partner_coedge.is_null:
                        partner = self._require(coedge.partner_coedge, CoedgeEntity, context='tolerant endpoint partner')
                        if partner.partner_coedge.index == coedge.index and partner.edge == coedge.edge and self._inline_curve(partner):
                            endpoint_bound = self._validate_inline_use(partner, result, placement)
                    if endpoint_bound is None:
                        raise
                    from .extensions import TolerantVertex
                    if not all(isinstance(self._tolerant_view(v, context='tolerant endpoint'), TolerantVertex)
                               for v in (edge.start_vertex, edge.end_vertex)):
                        raise
                    self._check_tolerant_boundary(edge, coedge, curve, placement, endpoint_bound)
                    self._restore_tolerant_vertices(result, edge, placement, endpoint_bound)
            return result
        if curve is None:
            start = self._vertex_location(edge.start_vertex, context=f"edge ${edge.index} start")
            end = self._vertex_location(edge.end_vertex, context=f"edge ${edge.index} end")
            collapsed = (placement.point_vector(start) - placement.point_vector(end)).magnitude <= self.tolerance
            raise CadQueryConversionError(
                f"edge ${edge.index}: null curve with {'coincident' if collapsed else 'distinct'} vertices; "
                "a singular surface and its pcurve must establish degeneracy",
                code="geometry.null_curve_coincident" if collapsed else "geometry.null_curve_distinct")
        elif isinstance(curve, RawEntity):
            actual = curve.type_name
        else:
            actual = curve.raw.type_name
        raise CadQueryConversionError(
            f"edge ${edge.index} curve: unsupported geometry {actual}", code="geometry.curve_unsupported"
        )

    def _check_tolerant_boundary(self, edge, coedge, curve, placement, endpoint_bound=None):
        """Check the saved curve, source endpoints and oriented intervals.

        Model resabs applies by default. A local endpoint bound requires an
        independently checked inline representation and its shared TEDGE.
        Face-support UV checks remain separate.
        """
        from .extensions import TolerantCoedge
        tolerance = self.tolerance if endpoint_bound is None else endpoint_bound
        if not isinstance(curve, (StraightCurveEntity, EllipseCurveEntity, BSplineCurveEntity)):
            raise CadQueryConversionError(
                f"edge ${edge.index}: tolerant boundary needs an explicit line, ellipse or spline",
                code="geometry.tolerant_topology_unsupported")
        parameters = (edge.start_parameter, edge.end_parameter)
        if (any(t is None or not math.isfinite(t) for t in parameters)
                or parameters[0] >= parameters[1]):
            raise CadQueryConversionError("invalid tolerant edge interval",
                                          code="geometry.tolerant_parameter_mismatch")
        if (isinstance(curve, EllipseCurveEntity)
                and parameters[1] - parameters[0] > 2 * math.pi + 64 * math.ulp(2 * math.pi)):
            raise CadQueryConversionError("multiple-turn tolerant ellipse is not qualified",
                                          code="geometry.tolerant_parameter_mismatch")
        if (isinstance(curve, EllipseCurveEntity) and edge.start_vertex == edge.end_vertex
                and abs(parameters[1] - parameters[0] - 2 * math.pi) > 1e-10):
            raise CadQueryConversionError("closed tolerant ellipse lacks a full saved turn",
                                          code="geometry.tolerant_parameter_mismatch")
        sign = -1 if edge.reversed else 1
        vertices = (edge.start_vertex, edge.end_vertex)
        expected = [placement.point_vector(self._vertex_location(v, context="tolerant boundary"))
                    for v in vertices]
        deviations = []

        def check(parameter, point):
            try:
                if curve.parameter_range is not None:
                    domain = curve.parameter_range
                    if ((domain.lower is not None and parameter < domain.lower)
                            or (domain.upper is not None and parameter > domain.upper)):
                        raise ValueError("tolerant trim outside saved curve domain")
                source_point = (curve.origin + curve.direction * parameter
                                if isinstance(curve, StraightCurveEntity) else curve.evaluate(parameter))
                actual = placement.point_vector(source_point)
            except (ValueError, OverflowError) as error:
                raise CadQueryConversionError(str(error), code="geometry.tolerant_parameter_mismatch") from error
            deviation = (actual - point).magnitude
            if not math.isfinite(deviation) or deviation > tolerance:
                raise CadQueryConversionError(
                    f"edge ${edge.index}: tolerant boundary disagrees with saved vertex "
                    f"({deviation:.9g} mm; model tolerance {self.tolerance:.9g} mm)",
                    code="geometry.tolerant_endpoint_mismatch")
            deviations.append(deviation)

        for parameter, point in zip(parameters, expected):
            check(sign * parameter, point)
        view = self._topology_views.get(coedge.index)
        if isinstance(view, TolerantCoedge):
            if view.parameter_interval[0] >= view.parameter_interval[1]:
                raise CadQueryConversionError("empty tolerant coedge interval",
                                              code="geometry.tolerant_parameter_mismatch")
            direction = -1 if coedge.reversed else 1
            interval = sorted(direction * t for t in parameters)
            # The observed saved intervals are independently rounded (up to
            # 6.1e-12). Also check actual 3D endpoints below at model precision.
            if any(abs(a - b) > 1e-10 for a, b in zip(interval, view.parameter_interval)):
                raise CadQueryConversionError("coedge interval differs from its saved edge",
                                              code="geometry.tolerant_parameter_mismatch")
            if coedge.reversed:
                expected.reverse()
                sign *= -1
            for parameter, point in zip(view.parameter_interval, expected):
                check(sign * parameter, point)
        self.tolerant_boundaries.append({
            "edge": edge.index, "coedge": coedge.index, "curve": curve.index,
            "max_endpoint_deviation_mm": max(deviations), "tolerance_mm": tolerance,
            "method": "saved 3D curve and oriented endpoints" if endpoint_bound is None else "validated inline support and source TEDGE endpoint bound",
        })

    def _bspline_edge(self, edge, coedge, curve, placement):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        from OCP.Geom import Geom_BSplineCurve
        from OCP.TColgp import TColgp_Array1OfPnt
        from OCP.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
        from OCP.gp import gp_Pnt
        curve.validate()
        if curve.fit_tolerance > (self.model.metadata.resabs or 1e-6) and curve.index not in self._checked_supported_curves:
            raise CadQueryConversionError("B-spline fit tolerance exceeds model precision",
                                          code="geometry.spline_fit_tolerance")
        if edge.start_parameter is None or edge.end_parameter is None:
            raise CadQueryConversionError("B-spline edge needs saved endpoint parameters",
                                          code="geometry.spline_parameter_unsupported")
        sign = -1 if edge.reversed else 1
        start, end = sign * edge.start_parameter, sign * edge.end_parameter
        if not math.isfinite(start + end) or sign * (end - start) <= 0:
            raise CadQueryConversionError("invalid B-spline edge interval",
                                          code="geometry.spline_parameter_unsupported")
        for parameter, vertex in ((start, edge.start_vertex), (end, edge.end_vertex)):
            if (parameter < curve.knots[0] or parameter > curve.knots[-1]
                    or (curve.parameter_range is not None and (
                        (curve.parameter_range.lower is not None and parameter < curve.parameter_range.lower)
                        or (curve.parameter_range.upper is not None and parameter > curve.parameter_range.upper)))):
                raise CadQueryConversionError("B-spline trim outside saved domain",
                                              code="geometry.spline_parameter_unsupported")
            point = placement.point_vector(curve.evaluate(parameter))
            from .extensions import TolerantVertex
            from .model import AcisModelError
            tolerant = None
            if isinstance(self.model.resolve(vertex), RawEntity):
                try:
                    tolerant = self._native_extensions().tolerant_topology(vertex)
                except AcisModelError as error:
                    raise CadQueryConversionError(str(error), code="geometry.tolerant_topology_unsupported") from error
            if isinstance(tolerant, TolerantVertex):
                source_point = self._require(tolerant.vertex.point, PointEntity, context="tolerant vertex point")
                location = source_point.location
            else:
                location = self._vertex_location(vertex, context="B-spline endpoint")
            expected = placement.point_vector(location)
            deviation = (point - expected).magnitude
            if not math.isfinite(deviation) or deviation > self.tolerance:
                self.spline_endpoint_failures.append(dict(edge=edge.index, coedge=coedge.index,
                    curve=curve.index, vertex=vertex.index, parameter=parameter,
                    deviation_mm=deviation, tolerance_mm=self.tolerance,
                    saved_vertex_scalars=tolerant.saved_scalars if isinstance(tolerant, TolerantVertex) else None))
                raise CadQueryConversionError(f"edge ${edge.index}: spline endpoint differs from source vertex "
                                              f"${vertex.index} by {deviation:.12g} mm (allowed {self.tolerance:.9g} mm)",
                                              code="geometry.spline_endpoint_mismatch")
            if isinstance(tolerant, TolerantVertex):
                self.tolerant_endpoints.append({
                    'vertex': vertex.index, 'edge': edge.index, 'coedge': coedge.index,
                    'curve': curve.index, 'parameter': parameter,
                    'deviation_mm': deviation, 'tolerance_mm': self.tolerance,
                    'saved_scalars_source_units': tolerant.saved_scalars,
                    'method': 'saved spline endpoint matches saved point within model resabs',
                })
        def array(values, cls):
            result = cls(1, len(values))
            for i, value in enumerate(values, 1):
                result.SetValue(i, value)
            return result
        try:
            ocp = Geom_BSplineCurve(
                array([gp_Pnt(*placement.point(p)) for p in curve.poles], TColgp_Array1OfPnt),
                array(curve.weights, TColStd_Array1OfReal), array(curve.knots, TColStd_Array1OfReal),
                array(curve.multiplicities, TColStd_Array1OfInteger), curve.degree, False)
            builder = BRepBuilderAPI_MakeEdge(ocp, min(start, end), max(start, end))
            if not builder.IsDone():
                raise ValueError("B-spline edge construction failed")
            result = self.cq.Edge(builder.Edge())
        except Exception as error:
            raise CadQueryConversionError("OCCT B-spline edge construction failed") from error
        return self._reverse_edge(result) if edge.reversed ^ coedge.reversed else result

    def _tolerant_line_interval(self, edge, coedge, curve, placement):
        """Ordinary lines may trim to saved tolerant points on the same locus.

        Both points must remain inside the saved edge/curve bounds. TEDGE and
        TCOEDGE parameter contracts are not reinterpreted by this path.
        """
        from dataclasses import replace
        from .extensions import TolerantVertex
        if edge.raw.type_name != 'edge' or coedge.raw.type_name != 'coedge':
            return edge
        vertices = (edge.start_vertex, edge.end_vertex)
        if not any(isinstance(self.model.resolve(v),RawEntity) and
                   isinstance(self._tolerant_view(v,context='line endpoint'),TolerantVertex) for v in vertices):
            return edge
        if edge.start_parameter is None or edge.end_parameter is None or curve.direction.magnitude <= 0:
            return edge
        sign = -1 if edge.reversed else 1
        original = (edge.start_parameter,edge.end_parameter)
        parameters=[]
        for vertex, old in zip(vertices,original):
            point = self._vertex_location(vertex,context='source line point')
            parameter = (point-curve.origin).dot(curve.direction)/curve.direction.dot(curve.direction)
            nearest = curve.origin + curve.direction*parameter
            if (placement.point_vector(nearest)-placement.point_vector(point)).magnitude > self.tolerance:
                return edge
            mapped=sign*parameter
            roundoff=64*math.ulp(max(1.,abs(mapped),*(abs(t) for t in original)))
            if not min(original)-roundoff <= mapped <= max(original)+roundoff:
                return edge
            mapped=min(max(mapped,min(original)),max(original))
            parameter=sign*mapped
            if curve.parameter_range is not None and (
                (curve.parameter_range.lower is not None and parameter < curve.parameter_range.lower-roundoff) or
                (curve.parameter_range.upper is not None and parameter > curve.parameter_range.upper+roundoff)):
                return edge
            if not isinstance(self.model.resolve(vertex),RawEntity) and abs(mapped-old)*placement.vector(curve.direction).magnitude > self.tolerance:
                return edge
            parameters.append(mapped)
        if parameters[0] >= parameters[1] or all(abs(a-b)*placement.vector(curve.direction).magnitude <= self.tolerance for a,b in zip(parameters,original)):
            return edge
        self.tolerant_line_trims.append(dict(edge=edge.index,coedge=coedge.index,
            saved_interval=original,vertex_interval=tuple(parameters),method='unchanged source line; saved points inside source intervals'))
        return replace(edge,start_parameter=parameters[0],end_parameter=parameters[1])

    def _inline_curve(self, coedge):
        if coedge is None or coedge.raw.type_name != 'tcoedge-coedge':
            return None
        view = self._tolerant_view(coedge.index, context='inline coedge')
        return view.inline_curve if view else None

    def _validate_inline_use(self, coedge, shape, placement):
        from ._supported_curves import validate_fit, support_geometry, inline_pcurve, deviation
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from types import SimpleNamespace
        view = self._inline_curve(coedge)
        fit = validate_fit(self, view, placement)
        edge = self._require(coedge.edge, EdgeEntity, context='inline shared edge')
        parameters = (edge.start_parameter, edge.end_parameter)
        if any(t is None or not math.isfinite(t) for t in parameters) or parameters[0] >= parameters[1]:
            raise CadQueryConversionError('invalid inline shared edge interval', code='geometry.tolerant_parameter_mismatch')
        interval = sorted((-1 if coedge.reversed else 1)*t for t in parameters)
        if any(abs(a-b) > 1e-10 for a,b in zip(interval,(view.curve.knots[0],view.curve.knots[-1]))):
            raise CadQueryConversionError('inline curve interval differs from shared edge',code='geometry.tolerant_parameter_mismatch')
        geometry = support_geometry(self, view.support, placement)
        adaptor = BRepAdaptor_Curve(shape.wrapped)
        first, last = adaptor.FirstParameter(), adaptor.LastParameter()
        curve = BRep_Tool.Curve_s(shape.wrapped, first, last)
        pc = inline_pcurve(self, view, curve, geometry, first, last, edge.reversed ^ coedge.reversed)
        maximum = deviation(curve, pc, geometry.surface, first, last)
        limit, source_bound = self._saved_pcurve_tolerance(coedge, SimpleNamespace(raw=view.curve.raw), placement)
        if source_bound is None or maximum > limit:
            raise CadQueryConversionError(f'inline UV and shared edge exceed saved edge bound ({maximum} > {limit} mm)',
                                          code='geometry.inline_edge_mismatch')
        self.supported_curve_checks.append(dict(fit, coedge=coedge.index, edge=edge.index,
            shared_edge_max_deviation_mm=maximum, shared_edge_tolerance_mm=limit))
        return limit

    def _restore_tolerant_vertices(self, shape, edge, placement, limit):
        from OCP.BRep import BRep_Builder
        from OCP.gp import gp_Pnt
        expected = [placement.point_vector(self._vertex_location(v, context='tolerant source vertex'))
                    for v in (edge.start_vertex, edge.end_vertex)]
        vertices = shape.Vertices()
        if len(vertices) != 2 or (expected[0]-expected[1]).magnitude <= 2*limit:
            raise CadQueryConversionError('ambiguous tolerant endpoint pairing',code='geometry.tolerant_endpoint_mismatch')
        builder = BRep_Builder()
        for vertex in vertices:
            point = Vec3(*vertex.Center().toTuple())
            target = min(expected, key=lambda p:(p-point).magnitude)
            if (target-point).magnitude > limit:
                raise CadQueryConversionError('tolerant endpoint exceeds checked bound',code='geometry.tolerant_endpoint_mismatch')
            builder.UpdateVertex(vertex.wrapped, gp_Pnt(target.x,target.y,target.z), limit)
        builder.UpdateEdge(shape.wrapped, limit)

    def _saved_surface_pcurve(self, coedge, geometry, first, last, reverse_3d):
        from .model import AcisModelError
        from OCP.Geom2d import Geom2d_BSplineCurve
        from OCP.TColgp import TColgp_Array1OfPnt2d
        from OCP.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
        from OCP.gp import gp_Pnt2d
        if coedge is None or coedge.pcurve.is_null or not hasattr(geometry, "source_surface"):
            return None, None
        try:
            view = self._native_extensions().spline_surface_pcurve(coedge.pcurve, geometry.source_surface)
        except AcisModelError as error:
            raise CadQueryConversionError(str(error), code="geometry.saved_pcurve_unsupported") from error
        if view is None:
            return None, None
        edge = self._require(coedge.edge, EdgeEntity, context="saved pcurve")
        sign = -1 if coedge.reversed else 1
        if edge.start_parameter is None or edge.end_parameter is None:
            raise CadQueryConversionError("saved pcurve needs source edge parameters",
                                          code="geometry.saved_pcurve_parameter_mismatch")
        mapped = sorted(sign * t for t in (edge.start_parameter, edge.end_parameter))
        if max(abs(a - b) for a, b in zip(mapped, view.parameter_interval)) > 1e-10:
            raise CadQueryConversionError("saved pcurve and edge intervals differ",
                                          code="geometry.saved_pcurve_parameter_mismatch")
        poles = TColgp_Array1OfPnt2d(1, len(view.poles))
        knots = TColStd_Array1OfReal(1, len(view.knots))
        mults = TColStd_Array1OfInteger(1, len(view.multiplicities))
        # Affine reparameterization preserves every saved pole and the UV locus.
        # Curve sense C(-t) and OCCT edge direction are independent reversals.
        reverse = view.reversed ^ reverse_3d
        points = view.poles[::-1] if reverse else view.poles
        source_knots = tuple(-k for k in view.knots[::-1]) if reverse else view.knots
        source_mults = view.multiplicities[::-1] if reverse else view.multiplicities
        for i, uv in enumerate(points, 1):
            poles.SetValue(i, gp_Pnt2d(*uv))
        for i, (k, mult) in enumerate(zip(source_knots, source_mults), 1):
            t = first + (k-source_knots[0]) / (source_knots[-1]-source_knots[0]) * (last-first)
            knots.SetValue(i, t)
            mults.SetValue(i, mult)
        return Geom2d_BSplineCurve(poles, knots, mults, view.degree, False), view

    def _saved_pcurve_tolerance(self, coedge, saved, placement):
        """Observed ASM 22700 TEDGE allowance, scoped to a checked saved pcurve.

        The edge's stored deviation and one original resabs form the bound;
        pcurve fit tolerances and vertex extension scalars are not substituted.
        Geometry, chart bounds and the converter's model resolution stay fixed.
        """
        from .extensions import TolerantCoedge, TolerantEdge
        if coedge is None or saved is None or placement is None:
            return self.tolerance, None
        use = self._tolerant_view(coedge.index, context="saved pcurve tolerance")
        edge = self._tolerant_view(coedge.edge, context="saved pcurve tolerance")
        if not isinstance(use, TolerantCoedge) or not isinstance(edge, TolerantEdge):
            return self.tolerance, None
        if not placement.preserves_circles:
            raise CadQueryConversionError("saved edge tolerance requires a similarity placement",
                                          code="geometry.tolerant_transform_unsupported")
        scale = placement.vector(Vec3(1., 0., 0.)).magnitude
        allowance = edge.saved_scalar * scale
        limit = allowance + self.tolerance
        if not math.isfinite(limit) or allowance < 0:
            raise CadQueryConversionError("invalid saved edge tolerance",
                                          code="geometry.tolerant_tolerance_invalid")
        return limit, {"edge": edge.edge.index, "coedge": coedge.index,
                       "pcurve": saved.raw.index, "saved_scalar_source_units": edge.saved_scalar,
                       "scale_to_mm": scale, "saved_deviation_mm": allowance,
                       "model_resolution_mm": self.tolerance, "limit_mm": limit,
                       "profile": "ASM 22700 / embedded 22601; null-inline tcoedge and same-support saved UV",
                       "method": "observed TEDGE bound plus original model resolution; geometry unchanged"}

    def _check_tolerant_join(self, previous, current, previous_coedge, current_coedge, geometry, placement, limit, loop_index):
        from .extensions import TolerantVertex
        if placement is None or limit <= self.tolerance or previous_coedge is None or current_coedge is None:
            raise CadQueryConversionError(f'loop ${loop_index}: pcurves do not connect',code='geometry.pcurve_connection')
        before=self._require(previous_coedge.edge,EdgeEntity,context='UV join')
        after=self._require(current_coedge.edge,EdgeEntity,context='UV join')
        end=before.start_vertex if previous_coedge.reversed else before.end_vertex
        start=after.end_vertex if current_coedge.reversed else after.start_vertex
        if end!=start or not isinstance(self._tolerant_view(end,context='UV join'),TolerantVertex):
            raise CadQueryConversionError('UV gap lacks a shared tolerant source vertex',code='geometry.pcurve_connection')
        expected=placement.point_vector(self._vertex_location(end,context='UV join'))
        points=[geometry.surface.Value(*uv) for uv in (previous,current)]
        deviations=[(Vec3(p.X(),p.Y(),p.Z())-expected).magnitude for p in points]
        gap=points[0].Distance(points[1])
        if not all(math.isfinite(d) and d<=limit for d in (*deviations,gap)):
            raise CadQueryConversionError('UV gap exceeds the checked source edge bound',code='geometry.pcurve_connection')
        self.tolerant_pcurve_joins.append(dict(vertex=end.index,previous_coedge=previous_coedge.index,
            coedge=current_coedge.index,gap_mm=gap,deviations_to_source_mm=deviations,tolerance_mm=limit))

    def _attach_surface_pcurves(self, edges: tuple, geometry, *, loop_index: int, coedges=None, placement=None) -> None:
        """Check saved/projected UV against unchanged 3D curves and source bounds."""
        from OCP.Adaptor3d import Adaptor3d_CurveOnSurface
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.Geom2dAdaptor import Geom2dAdaptor_Curve
        from OCP.GeomAdaptor import GeomAdaptor_Curve, GeomAdaptor_Surface
        from OCP.GeomLib import GeomLib_CheckCurveOnSurface
        from OCP.GeomProjLib import GeomProjLib
        from OCP.TopAbs import TopAbs_REVERSED
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Vec2d

        surface = geometry.surface
        periods = (surface.UPeriod() if surface.IsUPeriodic() else None,
                   surface.VPeriod() if surface.IsVPeriodic() else None)
        previous_end = None
        loop_start = None
        previous_limit = first_limit = self.tolerance
        location = TopLoc_Location()
        parameter_tolerance = self.tolerance / max(geometry.radius, 1.0)
        for i, edge in enumerate(edges):
            adaptor = BRepAdaptor_Curve(edge.wrapped)
            first, last = adaptor.FirstParameter(), adaptor.LastParameter()
            if not math.isfinite(first + last) or last <= first:
                raise CadQueryConversionError("invalid boundary parameter range")
            curve = BRep_Tool.Curve_s(edge.wrapped, first, last)
            try:
                coedge = coedges[i] if coedges is not None else None
                inline = self._inline_curve(coedge)
                if inline:
                    from ._supported_curves import same_support, inline_pcurve
                    if not hasattr(geometry, 'source_geometry') or not same_support(inline.support, geometry.source_geometry):
                        raise CadQueryConversionError('inline UV references another support chart', code='geometry.inline_support_mismatch')
                    pcurve = inline_pcurve(self, inline, curve, geometry, first, last,
                                           edge.wrapped.Orientation() == TopAbs_REVERSED)
                    saved = None
                else:
                    pcurve, saved = self._saved_surface_pcurve(
                        coedge, geometry, first, last, edge.wrapped.Orientation() == TopAbs_REVERSED)
                associated = None
                associated_limit = None
                if coedge is not None:
                    source_edge = self._require(coedge.edge, EdgeEntity, context='associated curve')
                    associated = self._supported_curves.get(source_edge.curve.index)
                if associated is not None:
                    from ._supported_curves import same_support, project_supported_curve
                    face_support = getattr(geometry, 'source_geometry', None)
                    if not any(s is not None and same_support(s, face_support)
                               for s in (associated.support, associated.secondary_support)):
                        raise CadQueryConversionError('associated curve belongs to another support',
                                                      code='geometry.supported_curve_support')
                    associated_limit = (associated.curve.fit_tolerance *
                                        placement.vector(Vec3(1., 0., 0.)).magnitude + self.tolerance)
                    if pcurve is None:
                        pcurve = project_supported_curve(curve, geometry, first, last, associated_limit)
                if pcurve is None:
                    pcurve = GeomProjLib.Curve2d_s(curve, first, last, surface, self.tolerance * 0.1)
                if pcurve is None:
                    raise ValueError("projection returned no curve")
                start, end = pcurve.Value(first), pcurve.Value(last)
                uv_start, uv_end = [start.X(), start.Y()], [end.X(), end.Y()]
                if edge.wrapped.Orientation() == TopAbs_REVERSED:
                    uv_start, uv_end = uv_end, uv_start
                shift = [0., 0.]
                if previous_end is not None:
                    for d, period in enumerate(periods):
                        if period is not None:
                            shift[d] = round((previous_end[d] - uv_start[d]) / period) * period
                pcurve.Translate(gp_Vec2d(*shift))
                if getattr(geometry, "uv_bounds", None) is not None:
                    self._check_uv_trim(pcurve, first, last, geometry.uv_bounds, loop_index)
                # OCCT's projector can return an approximation and its output
                # tolerance is not exposed by the Python binding. Independently
                # bound same-parameter deviation before attaching that curve.
                check = GeomLib_CheckCurveOnSurface(GeomAdaptor_Curve(curve, first, last))
                check.Perform(Adaptor3d_CurveOnSurface(
                    Geom2dAdaptor_Curve(pcurve, first, last), GeomAdaptor_Surface(surface)))
                limit, source_limit = associated_limit or self.tolerance, None
                # An inline use can need its checked TEDGE bound at a source
                # endpoint even when its reparameterized pcurve is exact.
                if check.IsDone() and math.isfinite(check.MaxDistance()) and (inline is not None or check.MaxDistance() > limit):
                    from types import SimpleNamespace
                    source = SimpleNamespace(raw=inline.curve.raw) if inline else saved
                    limit, source_limit = self._saved_pcurve_tolerance(coedge, source, placement)
                    if inline and source_limit is not None:
                        source_limit.update(pcurve=None, inline_coedge=coedge.index,
                            value_start=inline.value_start, value_end=inline.value_end,
                            profile='ASM 22700 / 22601; checked inline support and shared TEDGE')
                if not check.IsDone() or not math.isfinite(check.MaxDistance()) or check.MaxDistance() > limit:
                    raise CadQueryConversionError(
                        f"loop ${loop_index}: {'saved' if saved is not None else 'projected'} 2D/3D "
                        f"trim exceeds source tolerance ({check.MaxDistance() if check.IsDone() else 'unchecked'} "
                        f"mm; allowed {limit:.9g} mm; model tolerance {self.tolerance:.9g} mm)",
                        code="geometry.pcurve_mismatch")
                if previous_end is not None and any(abs(previous_end[d]-uv_start[d]-shift[d])>parameter_tolerance*10 for d in range(2)):
                    self._check_tolerant_join(previous_end,[uv_start[d]+shift[d] for d in range(2)],
                        coedges[i-1] if coedges else None,coedge,geometry,placement,max(previous_limit,limit),loop_index)
                self.pcurve_max_deviation = max(self.pcurve_max_deviation, check.MaxDistance())
                self.pcurve_count += 1
                self.pcurve_checks.append({"loop": loop_index,
                    "coedge": coedge.index if coedge is not None else None,
                    "pcurve": saved.raw.index if saved is not None else None,
                    "max_deviation_mm": check.MaxDistance(), "tolerance_mm": limit,
                    "source_edge_bound": source_limit})
                if associated:
                    self.associated_pcurves.append(dict(curve=associated.curve.index,
                        coedge=coedge.index, surface=geometry.source_surface,
                        max_deviation_mm=check.MaxDistance(), tolerance_mm=limit,
                        method='saved 3D fit projected only onto its checked associated support'))
                if inline:
                    self.inline_pcurves.append(dict(coedge=coedge.index, edge=coedge.edge.index,
                        surface=geometry.source_surface, value_start=inline.value_start, value_end=inline.value_end,
                        max_deviation_mm=check.MaxDistance(), tolerance_mm=limit))
                if saved is not None:
                    self.saved_pcurves.append({"pcurve": saved.raw.index, "coedge": coedge.index,
                        "surface": geometry.source_surface, "support_subtype": saved.support.index,
                        "max_deviation_mm": check.MaxDistance(), "tolerance_mm": limit,
                        "saved_fit_tolerance_source_units": saved.fit_tolerance,
                        "degree": saved.degree, "reversed": saved.reversed,
                        "support_reversed": saved.support_reversed,
                        "method": "saved spline UV curve; same spline support and 3D deviation checked"})
                builder = BRep_Builder()
                builder.UpdateEdge(edge.wrapped, pcurve, surface, location, limit)
                if source_limit is not None or associated is not None:
                    for vertex in edge.Vertices():
                        builder.UpdateVertex(vertex.wrapped, limit)
                    if source_limit is not None:
                        self.source_edge_tolerances.append({**source_limit, "max_deviation_mm": check.MaxDistance()})
                builder.Range(edge.wrapped, surface, location, first, last)
                builder.SameRange(edge.wrapped, True)
                builder.SameParameter(edge.wrapped, True)
                uv_start = [uv_start[d] + shift[d] for d in range(2)]
                uv_end = [uv_end[d] + shift[d] for d in range(2)]
                if loop_start is None:
                    loop_start = uv_start
                    first_limit = limit
                previous_end = uv_end
                previous_limit = limit
            except CadQueryConversionError:
                raise
            except Exception as error:
                raise CadQueryConversionError(
                    f"loop ${loop_index}: boundary projection failed", code="geometry.pcurve_projection") from error
        if previous_end is None or loop_start is None:
            raise CadQueryConversionError("empty boundary")
        for d, period in enumerate(periods):
            delta = previous_end[d] - loop_start[d]
            if period is not None:
                delta = (delta + period / 2) % period - period / 2
            if abs(delta) > parameter_tolerance * 10:
                self._check_tolerant_join(previous_end,loop_start,coedges[-1] if coedges else None,
                    coedges[0] if coedges else None,geometry,placement,max(previous_limit,first_limit),loop_index)
                break

    @staticmethod
    def _check_uv_trim(pcurve, first, last, bounds, loop_index):
        from OCP.Bnd import Bnd_Box2d
        from OCP.BndLib import BndLib_Add2dCurve
        from OCP.Geom2dAdaptor import Geom2dAdaptor_Curve
        from OCP.GeomAbs import (GeomAbs_Line, GeomAbs_Circle, GeomAbs_Ellipse,
                                 GeomAbs_Parabola, GeomAbs_Hyperbola,
                                 GeomAbs_BezierCurve, GeomAbs_BSplineCurve)
        if Geom2dAdaptor_Curve(pcurve).GetType() not in (
                GeomAbs_Line, GeomAbs_Circle, GeomAbs_Ellipse, GeomAbs_Parabola,
                GeomAbs_Hyperbola, GeomAbs_BezierCurve, GeomAbs_BSplineCurve):
            raise CadQueryConversionError("unqualified spline trim bound representation",
                                          code="geometry.spline_trim_outside_domain")
        # A conservative bound, including spline control points, checks the
        # whole trim. Endpoint-only checks miss curves leaving the saved UV box.
        box = Bnd_Box2d()
        BndLib_Add2dCurve.Add_s(pcurve, first, last, 0., box)
        box.SetGap(0.)
        xmin, ymin, xmax, ymax = box.Get()
        for lower, upper, allowed_lower, allowed_upper in (
                (xmin, xmax, bounds[0], bounds[1]),
                (ymin, ymax, bounds[2], bounds[3])):
            roundoff = max(1e-10, 64 * math.ulp(max(1., abs(allowed_lower), abs(allowed_upper))))
            if (not math.isfinite(lower + upper)
                    or lower < allowed_lower - roundoff or upper > allowed_upper + roundoff):
                raise CadQueryConversionError(
                    f"loop ${loop_index}: complete trim is not inside saved spline UV bounds",
                    code="geometry.spline_trim_outside_domain")

    def _wire(
        self,
        loop: LoopEntity,
        placement: _Placement,
        surface_geometry: _CylinderGeometry | None = None,
    ):
        coedges = self._coedges(loop)
        edges = tuple(self._edge(coedge, placement) for coedge in coedges)
        if surface_geometry is not None:
            self._attach_surface_pcurves(
                edges, surface_geometry, loop_index=loop.index, coedges=coedges, placement=placement
            )
        try:
            wire = self.cq.Wire.assembleEdges(edges)
        except Exception as error:
            raise CadQueryConversionError(
                f"loop ${loop.index}: CadQuery could not assemble the wire"
            ) from error
        if not wire.IsClosed():
            raise CadQueryConversionError(f"loop ${loop.index}: wire is not closed")
        if not wire.isValid():
            raise CadQueryConversionError(f"loop ${loop.index}: wire is invalid")
        return wire

    def _plane_face(
        self, face: FaceEntity, loops: tuple[LoopEntity, ...], placement: _Placement
    ):
        if any(self._inline_curve(coedge) for loop in loops for coedge in self._coedges(loop)):
            from ._supported_curves import support_geometry
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
            geometry = support_geometry(self, self._resolve_geometry(face.surface), placement)
            wires = tuple(self._wire(loop, placement, geometry) for loop in loops)
            builder = BRepBuilderAPI_MakeFace(geometry.surface, wires[0].wrapped, True)
            for wire in wires[1:]:
                builder.Add(wire.wrapped)
            if not builder.IsDone():
                raise CadQueryConversionError('tolerant planar face failed',code='geometry.face_invalid')
            result = self.cq.Face(builder.Face())
            if len(wires) > 1:
                from OCP.ShapeFix import ShapeFix_Face
                orienter = ShapeFix_Face(result.wrapped)
                if orienter.FixOrientation():
                    oriented = self.cq.Face(orienter.Face())
                    # Plane wires may only reverse: no new/deleted geometry.
                    if (len(oriented.Wires()) != len(wires)
                            or len(oriented.Edges()) != len(result.Edges()) or any(
                                not any(e.wrapped.IsSame(v.wrapped) for v in oriented.Edges())
                                for e in result.Edges())):
                        raise CadQueryConversionError('planar wire orientation changed topology',
                                                      code='geometry.face_invalid')
                    self.plane_wire_orientations.append(dict(face=face.index, loops=[l.index for l in loops]))
                    result = oriented
            return self._reverse_face(result) if face.reversed else result
        wires = tuple(self._wire(loop, placement) for loop in loops)
        try:
            return self.cq.Face.makeFromWires(wires[0], list(wires[1:]))
        except Exception as error:
            raise CadQueryConversionError(
                f"face ${face.index}: CadQuery could not build the planar face"
            ) from error

    def _cone_geometry(
        self, face: FaceEntity, surface: ConeSurfaceEntity, placement: _Placement
    ) -> _ConeGeometry:
        if not surface.is_circular() and not surface.is_cylinder():
            raise CadQueryConversionError(
                f"face ${face.index}: elliptical cones require a qualified rational surface",
                code="geometry.elliptical_cone_unsupported")
        if (surface.parameter_scale <= 0 or surface.reference_radius <= 0
            or not math.isclose(surface.sin_half_angle**2 + surface.cos_half_angle**2, 1, abs_tol=1e-9)
            or abs(surface.cos_half_angle) <= 1e-12):
            raise CadQueryConversionError(f"face ${face.index}: invalid cone scale/angle")
        if not placement.preserves_circles:
            raise CadQueryConversionError(
                f"face ${face.index}: sheared cylinder/cone placement is not supported"
            )

        from OCP.Geom import Geom_ConicalSurface, Geom_CylindricalSurface, Geom_Ellipse, Geom_SurfaceOfLinearExtrusion
        from OCP.gp import gp_Ax2, gp_Ax3, gp_Dir, gp_Pnt

        center = placement.point_vector(surface.center)
        axial_direction = surface.axis * surface.cos_half_angle
        axis = placement.vector(axial_direction).normalized()
        major_axis = placement.vector(surface.major_axis)
        radius = major_axis.magnitude
        x_direction = major_axis.normalized()
        if not math.isclose(
            axis.dot(x_direction), 0.0, abs_tol=1e-9, rel_tol=0.0
        ):
            raise CadQueryConversionError(
                f"face ${face.index}: cylinder/cone axes are not perpendicular"
            )
        y_direction = axis.cross(x_direction).normalized()
        try:
            axis_system = gp_Ax3(
                gp_Pnt(center.x, center.y, center.z),
                gp_Dir(axis.x, axis.y, axis.z),
                gp_Dir(x_direction.x, x_direction.y, x_direction.z),
            )
            if not surface.is_circular():
                if not 0 < abs(surface.ratio) <= 1:
                    raise CadQueryConversionError("elliptical cylinder ratio outside (0, 1]")
                ellipse = Geom_Ellipse(gp_Ax2(axis_system.Location(), axis_system.Direction(), axis_system.XDirection()),
                                       radius, radius * abs(surface.ratio))
                ocp_surface = Geom_SurfaceOfLinearExtrusion(ellipse, axis_system.Direction())
                return _EllipseCylinderGeometry(ocp_surface, center, axis, x_direction, y_direction,
                                                radius, self.tolerance, radius * abs(surface.ratio))
            elif surface.is_cylinder():
                ocp_surface = Geom_CylindricalSurface(axis_system, radius)
            else:
                semi_angle = math.atan2(
                    surface.sin_half_angle, abs(surface.cos_half_angle)
                )
                ocp_surface = Geom_ConicalSurface(
                    axis_system, semi_angle, radius
                )
        except Exception as error:
            raise CadQueryConversionError(
                f"face ${face.index}: CadQuery could not build the cylinder/cone"
            ) from error
        return _ConeGeometry(
            ocp_surface,
            center,
            axis,
            x_direction,
            y_direction,
            radius,
            self.tolerance,
            surface.sin_half_angle,
            abs(surface.cos_half_angle),
            radius,
        )

    def _is_full_revolution_face(self, loops: tuple[LoopEntity, ...]) -> bool:
        if len(loops) != 2:
            return False
        for loop in loops:
            coedges = self._coedges(loop)
            if len(coedges) != 1:
                return False
            edge = self._require(
                coedges[0].edge, EdgeEntity, context=f"loop ${loop.index}"
            )
            curve = self._resolve_geometry(edge.curve)
            if (
                not isinstance(curve, EllipseCurveEntity)
                or edge.start_vertex.index != edge.end_vertex.index
            ):
                return False
        return True

    def _reverse_face(self, face):
        from OCP.TopoDS import TopoDS

        return self.cq.Face(TopoDS.Face_s(face.wrapped.Reversed()))

    def _cone_face(
        self,
        face: FaceEntity,
        surface: ConeSurfaceEntity,
        loops: tuple[LoopEntity, ...],
        placement: _Placement,
    ):
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace

        if not surface.is_circular() and not surface.is_cylinder():
            return self._elliptical_cone_face(face, surface, loops, placement)
        geometry = self._cone_geometry(face, surface, placement)
        apex_face = self._cone_apex_face(face, surface, loops, placement, geometry)
        if apex_face is not None:
            return apex_face
        try:
            if self._is_full_revolution_face(loops):
                wires = tuple(self._wire(loop, placement) for loop in loops)
                v_parameters: list[float] = []
                for wire in wires:
                    for edge in wire.Edges():
                        adaptor = BRepAdaptor_Curve(edge.wrapped)
                        values = []
                        for fraction in (0, .125, .25, .375, .5, .625, .75, .875, 1):
                            point = adaptor.Value(adaptor.FirstParameter() + fraction *
                                                  (adaptor.LastParameter() - adaptor.FirstParameter()))
                            _, v_parameter = geometry.uv(Vec3(point.X(), point.Y(), point.Z()))
                            values.append(v_parameter)
                        if max(values) - min(values) > geometry.tolerance * 10:
                            raise CadQueryConversionError("full revolution boundary is not an isocurve")
                        v_parameters.append(values[0])
                lower_v = min(v_parameters)
                upper_v = max(v_parameters)
                builder = BRepBuilderAPI_MakeFace(
                    geometry.surface,
                    0.0,
                    2.0 * math.pi,
                    lower_v,
                    upper_v,
                    geometry.tolerance,
                )
            else:
                wires = tuple(
                    self._wire(loop, placement, geometry) for loop in loops
                )
                builder = BRepBuilderAPI_MakeFace(
                    geometry.surface, wires[0].wrapped, True
                )
                for wire in wires[1:]:
                    builder.Add(wire.wrapped)
                builder.Build()
            if not builder.IsDone():
                raise ValueError(f"OCP face builder error {builder.Error()}")
            result = self.cq.Face(builder.Face())
        except CadQueryConversionError:
            raise
        except Exception as error:
            raise CadQueryConversionError(
                f"face ${face.index}: CadQuery could not trim the cylinder/cone surface"
            ) from error
        if face.reversed != surface.reversed:
            result = self._reverse_face(result)
        return result

    def _elliptical_cone_face(self, face, surface, loops, placement):
        """Two coaxial complete elliptic sections of one positive cone nappe."""
        from dataclasses import replace
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_GTransform
        from OCP.gp import gp_GTrsf, gp_Mat, gp_XYZ
        if not self._is_full_revolution_face(loops) or not 0 < abs(surface.ratio) < 1:
            raise CadQueryConversionError("elliptical cone needs two complete coaxial elliptical sections",
                                          code="geometry.elliptical_cone_unsupported")
        geometry = self._cone_geometry(face, replace(surface, ratio=1.), placement)
        values = []
        for loop in loops:
            coedge = self._coedges(loop)[0]
            edge = self._require(coedge.edge, EdgeEntity, context="elliptical cone")
            curve = self._resolve_geometry(edge.curve)
            center = placement.point_vector(curve.center)
            delta = center - geometry.center
            axial = delta.dot(geometry.axis)
            v = axial / geometry.cos_half_angle
            expected_radius = geometry.reference_radius + v * geometry.sin_half_angle
            major = placement.vector(curve.major_axis)
            normal = placement.vector(curve.normal).normalized()
            if (expected_radius <= self.tolerance
                    or (delta - geometry.axis * axial).magnitude > self.tolerance
                    or abs(abs(normal.dot(geometry.axis)) - 1.) > 1e-10
                    or abs(abs(major.normalized().dot(geometry.x_direction)) - 1.) > 1e-10
                    or abs(major.magnitude - expected_radius) > self.tolerance
                    or abs(abs(curve.ratio) * major.magnitude - abs(surface.ratio) * expected_radius) > self.tolerance):
                raise CadQueryConversionError("elliptical cone boundary is not a source isosection",
                                              code="geometry.elliptical_cone_unsupported")
            self._edge(coedge, placement)
            values.append(v)
        if abs(values[1] - values[0]) <= self.tolerance:
            raise CadQueryConversionError("elliptical cone has an empty section interval")
        circular = BRepBuilderAPI_MakeFace(geometry.surface, 0., 2 * math.pi,
                                          min(values), max(values), self.tolerance)
        # An affine transform of rational conics is exact: OCCT transforms the
        # homogeneous spline representation, without fitting sampled points.
        y = geometry.y_direction
        components = (y.x, y.y, y.z)
        factor = abs(surface.ratio) - 1.
        matrix = [(1. if i == j else 0.) + factor * components[i] * components[j]
                  for i in range(3) for j in range(3)]
        translation = y * (-factor * geometry.center.dot(y))
        transform = gp_GTrsf(gp_Mat(*matrix), gp_XYZ(translation.x, translation.y, translation.z))
        builder = BRepBuilderAPI_GTransform(circular.Face(), transform, True)
        if not builder.IsDone():
            raise CadQueryConversionError("elliptical cone affine construction failed")
        faces = self.cq.Shape.cast(builder.Shape()).Faces()
        if len(faces) != 1 or not faces[0].isValid():
            raise CadQueryConversionError("elliptical cone affine face is invalid", code="geometry.face_invalid")
        self.analytic_trim_faces.append({"face": face.index,
            "method": "elliptical_cone_affine_isosections", "loops": [l.index for l in loops]})
        return self._reverse_face(faces[0]) if face.reversed ^ surface.reversed else faces[0]

    def _cone_apex_face(self, face, surface, loops, placement, geometry):
        """A complete circular rim and one source null loop at a proven apex.

        OCCT creates an explicit degenerate edge and a seam in its own chart.
        The source edge's arbitrary null-curve parameters are not used as UV.
        """
        from OCP.BRep import BRep_Tool
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        if surface.is_cylinder() or not surface.is_circular() or len(loops) != 2:
            return None
        rings, nulls = [], []
        for loop in loops:
            coedges = self._coedges(loop)
            if len(coedges) != 1:
                return None
            coedge = coedges[0]
            edge = self._require(coedge.edge, EdgeEntity, context=f"loop ${loop.index}")
            if edge.start_vertex != edge.end_vertex:
                return None
            curve = self._resolve_geometry(edge.curve)
            if curve is None:
                nulls.append((coedge, edge))
            elif isinstance(curve, EllipseCurveEntity) and curve.is_circle():
                rings.append((coedge, edge, curve))
            else:
                return None
        if len(rings) != 1 or len(nulls) != 1:
            return None
        coedge, edge = nulls[0]
        apex = placement.point_vector(surface.apex)
        point = placement.point_vector(self._vertex_location(edge.start_vertex, context="cone apex"))
        if (apex - point).magnitude > self.tolerance:
            raise CadQueryConversionError(f"edge ${edge.index}: null loop is not at the cone apex",
                                          code="geometry.degeneracy_unproven")
        ring_coedge, _, curve = rings[0]
        center = placement.point_vector(curve.center)
        delta = center - geometry.center
        axial = delta.dot(geometry.axis)
        normal = placement.oriented_direction(curve.normal * (1 if curve.ratio > 0 else -1))
        radius = placement.vector(curve.major_axis).magnitude
        v = axial / geometry.cos_half_angle
        apex_v = -geometry.reference_radius / geometry.sin_half_angle
        if ((delta - geometry.axis * axial).magnitude > self.tolerance
                or abs(abs(normal.dot(geometry.axis)) - 1) > 1e-10
                or abs(radius - (geometry.reference_radius + v * geometry.sin_half_angle)) > self.tolerance
                or abs(v - apex_v) <= self.tolerance):
            return None
        self._edge(ring_coedge, placement)  # Validate the source rim and its trim.
        # The explicit apex loop selects the unique finite side of the rim.
        flip = face.reversed ^ surface.reversed
        builder = BRepBuilderAPI_MakeFace(geometry.surface, 0., 2 * math.pi,
                                         min(v, apex_v), max(v, apex_v), self.tolerance)
        if not builder.IsDone():
            raise CadQueryConversionError("cone apex face construction failed")
        result = self.cq.Face(builder.Face())
        # CadQuery.Edges() deliberately filters degenerate edges. Inspect the
        # OCCT topology directly when proving preservation of a source null edge.
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopoDS import TopoDS
        explorer = TopExp_Explorer(result.wrapped, TopAbs_EDGE)
        degenerate = []
        while explorer.More():
            candidate = TopoDS.Edge_s(explorer.Current())
            if BRep_Tool.Degenerated_s(candidate):
                degenerate.append(self.cq.Edge(candidate))
            explorer.Next()
        if len(degenerate) != 1 or any(
                math.dist(vertex.toTuple(), (point.x, point.y, point.z)) > self.tolerance
                for vertex in degenerate[0].Vertices()):
            raise CadQueryConversionError(f"constructed cone lost its source apex: {len(degenerate)} degenerate edges",
                                          code="geometry.degeneracy_unproven")
        self.degenerate_edges.append({"face": face.index, "edge": edge.index,
                                      "coedge": coedge.index, "method": "analytic_cone_apex"})
        return self._reverse_face(result) if flip else result

    def _closed_analytic_geometry(self, face, surface, placement):
        from OCP.Geom import Geom_SphericalSurface, Geom_ToroidalSurface
        from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt
        if not placement.preserves_circles:
            raise CadQueryConversionError("sphere/torus requires a similarity placement")
        center = placement.point_vector(surface.center)
        axis = placement.vector(surface.pole if isinstance(surface, SphereSurfaceEntity) else surface.axis).normalized()
        x = placement.vector(surface.u_direction).normalized()
        if abs(axis.dot(x)) > 1e-9:
            raise CadQueryConversionError("sphere/torus frame is not orthogonal")
        y = axis.cross(x)
        frame = gp_Ax3(gp_Pnt(center.x, center.y, center.z), gp_Dir(axis.x, axis.y, axis.z), gp_Dir(x.x, x.y, x.z))
        scale = placement.vector(Vec3(1, 0, 0)).magnitude
        if isinstance(surface, SphereSurfaceEntity):
            radius = abs(surface.radius) * scale
            if not math.isfinite(radius) or radius <= self.tolerance:
                raise CadQueryConversionError("invalid sphere radius")
            return _SphereGeometry(Geom_SphericalSurface(frame, radius), center, axis, x, y, radius, self.tolerance)
        major, minor = surface.major_radius * scale, abs(surface.minor_radius) * scale
        if not math.isfinite(major + minor) or not major > minor > self.tolerance:
            raise CadQueryConversionError("only regular ring tori are qualified", code="geometry.singular_torus_unsupported")
        return _TorusGeometry(Geom_ToroidalSurface(frame, major, minor), center, axis, x, y, major, self.tolerance, minor)

    def _periodic_band(self, face, surface, loops, placement, geometry):
        """Recognize two complete analytic isocircles and preserve their senses."""
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from OCP.TopAbs import TopAbs_REVERSED
        if not self._is_full_revolution_face(loops):
            return None
        boundaries = []
        signed_radius = surface.radius if isinstance(surface, SphereSurfaceEntity) else surface.minor_radius
        flip = face.reversed ^ surface.reversed ^ (signed_radius < 0)
        for loop in loops:
            coedge = self._coedges(loop)[0]
            edge = self._edge(coedge, placement)
            curve = BRepAdaptor_Curve(edge.wrapped)
            samples = []
            for i in range(33):
                t = curve.FirstParameter() + i / 32 * (curve.LastParameter() - curve.FirstParameter())
                p = curve.Value(t)
                uv = list(geometry.uv(Vec3(p.X(), p.Y(), p.Z())))
                if samples:
                    for d, periodic in enumerate((geometry.surface.IsUPeriodic(), geometry.surface.IsVPeriodic())):
                        if periodic:
                            uv[d] = samples[-1][d] + ((uv[d] - samples[-1][d] + math.pi) % (2 * math.pi) - math.pi)
                samples.append(uv)
            spans = [max(p[d] for p in samples) - min(p[d] for p in samples) for d in range(2)]
            constant = 0 if spans[0] < spans[1] else 1
            varying = 1 - constant
            if spans[constant] > self.tolerance / max(geometry.radius, 1) * 10:
                return None
            if not math.isclose(spans[varying], 2 * math.pi, abs_tol=1e-8):
                return None
            direction = samples[-1][varying] - samples[0][varying]
            if edge.wrapped.Orientation() == TopAbs_REVERSED:
                direction = -direction
            # For an outward UV chart the lower V boundary runs +U, and the
            # lower U boundary runs -V. Signed radii carry surface sense.
            lower = (direction * (-1 if flip else 1) * (1 if constant == 1 else -1)) > 0
            boundaries.append((constant, samples[0][constant], lower))
        if boundaries[0][0] != boundaries[1][0] or boundaries[0][2] == boundaries[1][2]:
            raise CadQueryConversionError("periodic band has inconsistent boundary senses", code="geometry.boundary_orientation")
        constant = boundaries[0][0]
        lower = next(p[1] for p in boundaries if p[2])
        upper = next(p[1] for p in boundaries if not p[2])
        periodic = geometry.surface.IsUPeriodic() if constant == 0 else geometry.surface.IsVPeriodic()
        if periodic:
            upper = lower + (upper - lower) % (2 * math.pi)
        if upper <= lower + 1e-12:
            raise CadQueryConversionError("periodic band has an empty or ambiguous domain")
        bounds = (lower, upper, 0., 2 * math.pi) if constant == 0 else (0., 2 * math.pi, lower, upper)
        maker = BRepBuilderAPI_MakeFace(geometry.surface, *bounds, self.tolerance)
        if not maker.IsDone():
            raise CadQueryConversionError("periodic band construction failed")
        result = self.cq.Face(maker.Face())
        return self._reverse_face(result) if flip else result

    def _closed_analytic_face(self, face, surface, loops, placement):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        has_inline = any(self._inline_curve(coedge) for loop in loops for coedge in self._coedges(loop))
        if has_inline:
            from ._supported_curves import support_geometry
            geometry = support_geometry(self, surface, placement)
        else:
            geometry = self._closed_analytic_geometry(face, surface, placement)
        band = None if has_inline else self._periodic_band(face, surface, loops, placement, geometry)
        if band is not None:
            return band
        if isinstance(surface, SphereSurfaceEntity) and loops and not has_inline:
            circular = self._sphere_circular_trims(face, surface, loops, placement, geometry)
            if circular is not None:
                return circular
        if not loops:
            # A loopless closed surface has no trim boundary. Finite saved subset
            # ranges require chart interpretation and must not imply a full face.
            if any(r is not None and (r.lower is not None or r.upper is not None)
                   for r in (surface.u_range, surface.v_range)):
                raise CadQueryConversionError("loopless surface has finite saved ranges", code="geometry.source_chart_unsupported")
            builder = BRepBuilderAPI_MakeFace(geometry.surface, geometry.tolerance)
        else:
            wires = tuple(self._wire(loop, placement, geometry) for loop in loops)
            builder = BRepBuilderAPI_MakeFace(geometry.surface, wires[0].wrapped, True)
            for wire in wires[1:]:
                builder.Add(wire.wrapped)
            builder.Build()
        if not builder.IsDone():
            raise CadQueryConversionError(f"face ${face.index}: analytic trim failed")
        result = self.cq.Face(builder.Face())
        signed_radius = surface.radius if isinstance(surface, SphereSurfaceEntity) else surface.minor_radius
        if face.reversed ^ surface.reversed ^ (signed_radius < 0):
            result = self._reverse_face(result)
        return result

    def _sphere_circular_trims(self, face, surface, loops, placement, geometry):
        """Trim a sphere by disjoint complete source circles, including seams.

        An oriented circle selects a plane half-space. The intersection builds
        OCCT seam/pole topology; every resulting physical boundary must still
        cover a whole source circle, with matching analytic geometry.
        """
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
        from OCP.GeomAbs import GeomAbs_Circle
        from OCP.TopAbs import TopAbs_REVERSED
        from OCP.gp import gp_Pln, gp_Pnt, gp_Dir
        circles = []
        flip = face.reversed ^ surface.reversed ^ (surface.radius < 0)
        for loop in loops:
            coedges = self._coedges(loop)
            if len(coedges) != 1:
                return None
            coedge = coedges[0]
            edge = self._require(coedge.edge, EdgeEntity, context="sphere boundary")
            curve = self._resolve_geometry(edge.curve)
            if (not isinstance(curve, EllipseCurveEntity) or not curve.is_circle()
                    or edge.start_vertex != edge.end_vertex):
                return None
            center = placement.point_vector(curve.center)
            normal = placement.oriented_direction(curve.normal * (1 if curve.ratio > 0 else -1))
            radius = placement.vector(curve.major_axis).magnitude
            offset = center - geometry.center
            if ((offset - normal * offset.dot(normal)).magnitude > self.tolerance
                    or abs(math.hypot(offset.magnitude, radius) - geometry.radius) > self.tolerance):
                raise CadQueryConversionError("sphere boundary is not a circle on the source sphere",
                                              code="geometry.pcurve_mismatch")
            converted = self._edge(coedge, placement)
            sense = -1 if converted.wrapped.Orientation() == TopAbs_REVERSED else 1
            # A mirror reverses the ambient orientation of the source traversal.
            keep = normal * (sense * (-1 if flip else 1) * placement.orientation_sign)
            circles.append((edge.index, center, normal, radius, keep))
        result = BRepBuilderAPI_MakeFace(geometry.surface, self.tolerance).Face()
        try:
            for _, center, _, _, keep in circles:
                plane = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(center.x, center.y, center.z),
                                                     gp_Dir(keep.x, keep.y, keep.z))).Face()
                outside = center - keep * max(geometry.radius, 1.)
                half = BRepPrimAPI_MakeHalfSpace(plane, gp_Pnt(outside.x, outside.y, outside.z)).Solid()
                cut = BRepAlgoAPI_Cut(result, half)
                cut.Build()
                if not cut.IsDone():
                    raise ValueError("sphere half-space intersection failed")
                result = cut.Shape()
            faces = self.cq.Shape.cast(result).Faces()
            if len(faces) != 1 or not faces[0].isValid():
                raise CadQueryConversionError("circular sphere trims do not form one valid face",
                                              code="geometry.face_invalid")
            result = faces[0]
            spans = [0.] * len(circles)
            for converted in result.Edges():
                if BRep_Tool.IsClosed_s(converted.wrapped, result.wrapped):
                    continue  # An OCCT chart seam is not a physical trim.
                adaptor = BRepAdaptor_Curve(converted.wrapped)
                if adaptor.GetType() != GeomAbs_Circle:
                    raise ValueError("sphere cut introduced a non-circular boundary")
                circle = adaptor.Circle()
                p, n = circle.Location(), circle.Axis().Direction()
                center, normal = Vec3(p.X(), p.Y(), p.Z()), Vec3(n.X(), n.Y(), n.Z())
                matches = [i for i, (_, c, axis, radius, _) in enumerate(circles)
                           if (center - c).magnitude <= self.tolerance
                           and abs(circle.Radius() - radius) <= self.tolerance
                           and abs(abs(normal.dot(axis)) - 1) <= 1e-10]
                if len(matches) != 1:
                    raise ValueError("sphere cut has ambiguous or changed source boundary")
                spans[matches[0]] += adaptor.LastParameter() - adaptor.FirstParameter()
            if any(abs(span - 2 * math.pi) * circles[i][3] > self.tolerance for i, span in enumerate(spans)):
                raise ValueError("sphere cut removed or changed a source circle")
        except CadQueryConversionError:
            raise
        except Exception as error:
            raise CadQueryConversionError("circular sphere trim verification failed",
                                          code="geometry.analytic_trim_mismatch") from error
        self.analytic_trim_faces.append({"face": face.index, "edges": [c[0] for c in circles],
                                        "method": "sphere_oriented_circle_halfspaces"})
        return self._reverse_face(result) if flip else result

    def _bspline_geometry(self, surface: BSplineSurfaceEntity, placement):
        from OCP.Geom import Geom_BSplineSurface
        from OCP.TColgp import TColgp_Array2OfPnt
        from OCP.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger, TColStd_Array2OfReal
        from OCP.gp import gp_Pnt
        surface.validate()
        if surface.fit_tolerance > (self.model.metadata.resabs or 1e-6):
            raise CadQueryConversionError("B-spline fit tolerance exceeds model precision", code="geometry.spline_fit_tolerance")
        def array(values, cls):
            result = cls(1, len(values))
            for i, value in enumerate(values, 1):
                result.SetValue(i, value)
            return result
        poles = TColgp_Array2OfPnt(1, surface.u_count, 1, surface.v_count)
        weights = TColStd_Array2OfReal(1, surface.u_count, 1, surface.v_count)
        for v in range(surface.v_count):
            for u in range(surface.u_count):
                index = v * surface.u_count + u
                poles.SetValue(u+1, v+1, gp_Pnt(*placement.point(surface.poles[index])))
                weights.SetValue(u+1, v+1, surface.weights[index])
        return Geom_BSplineSurface(poles, weights,
            array(surface.u_knots, TColStd_Array1OfReal), array(surface.v_knots, TColStd_Array1OfReal),
            array(surface.u_multiplicities, TColStd_Array1OfInteger), array(surface.v_multiplicities, TColStd_Array1OfInteger),
            surface.u_degree, surface.v_degree, False, False)

    def _bspline_face(self, face, surface, loops, placement):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from OCP.Geom import Geom_RectangularTrimmedSurface
        from types import SimpleNamespace
        ocp_surface = self._bspline_geometry(surface, placement)
        bounds = tuple(bound if bound is not None else knot
                       for domain, knots in ((surface.u_range, surface.u_knots),
                                             (surface.v_range, surface.v_knots))
                       for bound, knot in zip((domain.lower, domain.upper) if domain else (None, None),
                                               (knots[0], knots[-1])))
        bounded = any(r is not None and (r.lower is not None or r.upper is not None)
                      for r in (surface.u_range, surface.v_range))
        if bounded:
            ocp_surface = Geom_RectangularTrimmedSurface(ocp_surface, *bounds)
        geometry = SimpleNamespace(surface=ocp_surface, radius=1., tolerance=self.tolerance,
                                   uv_bounds=bounds if bounded else None, source_surface=surface.index, source_geometry=surface)
        wires = tuple(self._wire(loop, placement, geometry) for loop in loops)
        builder = BRepBuilderAPI_MakeFace(ocp_surface, wires[0].wrapped, True)
        for wire in wires[1:]:
            builder.Add(wire.wrapped)
        builder.Build()
        if not builder.IsDone():
            raise CadQueryConversionError("B-spline face trim failed")
        result = self.cq.Face(builder.Face())
        if bounded:
            self.bounded_surface_faces.append({"face": face.index, "surface": surface.index,
                "uv_bounds": bounds, "loops": [loop.index for loop in loops],
                "method": "unchanged spline chart; complete projected trim bounds checked"})
        return self._reverse_face(result) if face.reversed != surface.reversed else result

    def _face(self, face: FaceEntity, placement: _Placement):
        surface = self._resolve_geometry(face.surface)
        if not isinstance(surface, (PlaneSurfaceEntity, ConeSurfaceEntity, SphereSurfaceEntity, TorusSurfaceEntity, BSplineSurfaceEntity)):
            if surface is None:
                actual = "null"
            elif isinstance(surface, RawEntity):
                actual = surface.type_name
            else:
                actual = surface.raw.type_name
            raise CadQueryConversionError(
                f"face ${face.index} surface: unsupported geometry {actual}", code="geometry.surface_unsupported"
            )
        loops = self._linked_entities(
            face.loop,
            LoopEntity,
            "next_loop",
            context=f"face ${face.index} loops",
        )
        if not loops and not isinstance(surface, (SphereSurfaceEntity, TorusSurfaceEntity)):
            raise CadQueryConversionError(f"face ${face.index} has no loop")
        for loop in loops:
            if loop.face.index != face.index:
                raise CadQueryConversionError(
                    f"loop ${loop.index} belongs to face ${loop.face.index}, "
                    f"not ${face.index}"
                )
        if isinstance(surface, PlaneSurfaceEntity):
            result = self._plane_face(face, loops, placement)
        elif isinstance(surface, BSplineSurfaceEntity):
            result = self._bspline_face(face, surface, loops, placement)
        elif isinstance(surface, ConeSurfaceEntity):
            result = self._cone_face(face, surface, loops, placement)
        else:
            result = self._closed_analytic_face(face, surface, loops, placement)
        if not result.isValid():
            raise CadQueryConversionError(f"face ${face.index}: face is invalid", code="geometry.face_invalid")
        return result

    def _shell(
        self, shell: ShellEntity, placement: _Placement
    ) -> tuple[cq.Shell, ...]:
        faces = self._linked_entities(
            shell.face,
            FaceEntity,
            "next_face",
            context=f"shell ${shell.index} faces",
        )
        if not faces:
            raise CadQueryConversionError(f"shell ${shell.index} has no face")
        for face in faces:
            if face.shell.index != shell.index:
                raise CadQueryConversionError(
                    f"face ${face.index} belongs to shell ${face.shell.index}, "
                    f"not ${shell.index}"
                )
        try:
            result = self.cq.Shell.makeShell(
                self._face(face, placement) for face in faces
            )
        except CadQueryConversionError:
            raise
        except Exception as error:
            raise CadQueryConversionError(
                f"shell ${shell.index}: CadQuery could not sew the faces"
            ) from error
        if not result.isValid():
            raise CadQueryConversionError(f"shell ${shell.index}: shell is invalid")

        # An ACIS shell can be non-manifold at an edge. OCP sewing represents
        # such a result as a Compound of independently closed Shells rather
        # than one non-manifold Shell, so retain every closed component.
        components = tuple(result.Shells())
        if not components and len(faces) == 1 and faces[0].loop.is_null and isinstance(
                self.model.resolve(faces[0].surface), (SphereSurfaceEntity, TorusSurfaceEntity)):
            # Sewing returns a Face for a single closed surface. Retain that
            # face in an explicit shell; closure/validity are still checked.
            from OCP.BRep import BRep_Builder, BRep_Tool
            from OCP.BRepCheck import BRepCheck_Shell, BRepCheck_NoError
            from OCP.TopoDS import TopoDS_Shell
            wrapped = TopoDS_Shell()
            builder = BRep_Builder()
            builder.MakeShell(wrapped)
            for converted_face in result.Faces():
                builder.Add(wrapped, converted_face.wrapped)
            if BRep_Tool.IsClosed_s(wrapped) and BRepCheck_Shell(wrapped).Closed() == BRepCheck_NoError:
                wrapped.Closed(True)
            components = (self.cq.Shell(wrapped),)
        if not components:
            raise CadQueryConversionError(
                f"shell ${shell.index}: sewing produced no shell", code="geometry.sewing_no_shell"
            )
        for component_index, component in enumerate(components):
            if not component.isValid():
                raise CadQueryConversionError(
                    f"shell ${shell.index}: component {component_index} is invalid"
                )
            if not component.Closed():
                raise CadQueryConversionError(
                    f"shell ${shell.index}: component {component_index} is not closed", code="geometry.shell_open"
                )
        return components

    def _lump(self, lump: LumpEntity, placement: _Placement):
        shells = self._linked_entities(
            lump.shell,
            ShellEntity,
            "next_shell",
            context=f"lump ${lump.index} shells",
        )
        if not shells:
            raise CadQueryConversionError(f"lump ${lump.index} has no shell")
        for shell in shells:
            if shell.lump.index != lump.index:
                raise CadQueryConversionError(
                    f"shell ${shell.index} belongs to lump ${shell.lump.index}, "
                    f"not ${lump.index}"
                )
        converted = tuple(self._shell(shell, placement) for shell in shells)
        outer_shells = converted[0]
        cavity_shells = tuple(
            component for group in converted[1:] for component in group
        )
        if len(outer_shells) > 1 and cavity_shells:
            raise CadQueryConversionError(
                f"lump ${lump.index}: cavities in a split non-manifold shell "
                "are not supported"
            )
        try:
            if len(outer_shells) == 1:
                result = self.cq.Solid.makeSolid(outer_shells[0])
                if cavity_shells:
                    result = result.addCavity(*cavity_shells)
            else:
                solids = tuple(
                    self.cq.Solid.makeSolid(component)
                    for component in outer_shells
                )
                result = self.cq.Compound.makeCompound(solids)
        except Exception as error:
            raise CadQueryConversionError(
                f"lump ${lump.index}: CadQuery could not build the solid"
            ) from error
        if not result.isValid():
            raise CadQueryConversionError(f"lump ${lump.index}: solid is invalid")
        return result

    def convert_body(self, body: BodyEntity):
        """Convert one decoded body to a Solid or a Compound of its lumps."""

        if not body.wire.is_null:
            raise CadQueryConversionError(
                f"body ${body.index}: wire bodies are not supported yet"
            )
        lumps = self._linked_entities(
            body.lump,
            LumpEntity,
            "next_lump",
            context=f"body ${body.index} lumps",
        )
        if not lumps:
            raise CadQueryConversionError(f"body ${body.index} has no lump")
        for lump in lumps:
            if lump.body.index != body.index:
                raise CadQueryConversionError(
                    f"lump ${lump.index} belongs to body ${lump.body.index}, "
                    f"not ${body.index}"
                )
        placement = self._body_placement(body)
        solids = tuple(self._lump(lump, placement) for lump in lumps)
        if len(solids) == 1:
            return solids[0]
        result = self.cq.Compound.makeCompound(solids)
        if not result.isValid():
            raise CadQueryConversionError(f"body ${body.index}: compound is invalid")
        return result

    def convert(self) -> tuple[cq.Shape, ...]:
        """Convert every decoded body, preserving one result per body."""

        for entity in self.model.entities:
            if isinstance(entity, RawEntity) and entity.type_name == "body":
                raise CadQueryConversionError(
                    f"body ${entity.index}: body has not been decoded"
                )
        return tuple(self.convert_body(body) for body in self.model.bodies())

    def workplane(self) -> cq.Workplane:
        """Return converted body shapes on a CadQuery Workplane stack."""

        return self.cq.Workplane("XY").newObject(self.convert())


def convert_model(model: AcisModelView) -> tuple[cq.Shape, ...]:
    """Convert the supported bodies in any shared ACIS model to CadQuery shapes."""

    return CadQueryConverter(model).convert()


def convert_sat_model(model: AcisModelView) -> tuple[cq.Shape, ...]:
    """Backward-compatible entrypoint; accepts SatModel and AcisModel."""

    return convert_model(model)


def to_cadquery(model: AcisModelView) -> cq.Workplane:
    """Convert an AcisModel or legacy SatModel to a CadQuery Workplane."""

    return CadQueryConverter(model).workplane()


def import_sat_data(data: str | bytes) -> cq.Workplane:
    """Parse SAT text or bytes and return its bodies on a Workplane."""

    from .entities import parse_sat_model

    return to_cadquery(parse_sat_model(data))


def import_sat_file(path: str | PathLike[str]) -> cq.Workplane:
    """Read an ASCII SAT file and return its bodies on a Workplane."""

    return import_sat_data(Path(path).read_bytes())
