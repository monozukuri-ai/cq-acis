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
    """Raised when a decoded SAT model cannot be converted without approximation."""


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
        return self.transform is None or not self.transform.sheared

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
        return u_parameter, v_parameter


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

    def _require(
        self,
        reference: EntityRef | int,
        expected_type: type[EntityT],
        *,
        context: str,
    ) -> EntityT:
        entity = self.model.resolve(reference)
        if not isinstance(entity, expected_type):
            if entity is None:
                actual = "null"
            elif isinstance(entity, RawEntity):
                actual = entity.type_name
            else:
                actual = entity.raw.type_name
            raise CadQueryConversionError(
                f"{context}: expected {expected_type.__name__}, got {actual}"
            )
        return entity

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
        vertex = self._require(reference, VertexEntity, context=context)
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
        self, edge: EdgeEntity, coedge: CoedgeEntity, placement: _Placement
    ):
        if edge.start_vertex.is_null or edge.end_vertex.is_null:
            raise CadQueryConversionError(
                f"edge ${edge.index}: straight edge requires two vertices"
            )
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
            relative.dot(minor_direction), relative.dot(major_direction)
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
        edge = self._require(
            coedge.edge, EdgeEntity, context=f"coedge ${coedge.index}"
        )
        curve = self.model.resolve(edge.curve)
        if isinstance(curve, StraightCurveEntity):
            return self._straight_edge(edge, coedge, placement)
        if isinstance(curve, EllipseCurveEntity):
            return self._ellipse_edge(edge, coedge, curve, placement)
        if curve is None:
            actual = "null"
        elif isinstance(curve, RawEntity):
            actual = curve.type_name
        else:
            actual = curve.raw.type_name
        raise CadQueryConversionError(
            f"edge ${edge.index} curve: unsupported geometry {actual}"
        )

    def _attach_surface_pcurves(
        self, edges: tuple, geometry: _CylinderGeometry, *, loop_index: int
    ) -> None:
        from OCP.BRep import BRep_Builder
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.Geom2d import Geom2d_Line
        from OCP.TopAbs import TopAbs_REVERSED
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Dir2d, gp_Pnt2d

        previous_end: tuple[float, float] | None = None
        loop_start: tuple[float, float] | None = None
        location = TopLoc_Location()
        parameter_tolerance = geometry.tolerance / max(geometry.radius, 1.0)

        for edge in edges:
            adaptor = BRepAdaptor_Curve(edge.wrapped)
            first = adaptor.FirstParameter()
            last = adaptor.LastParameter()
            if not math.isfinite(first) or not math.isfinite(last) or last <= first:
                raise CadQueryConversionError(
                    f"loop ${loop_index}: invalid edge parameter range"
                )

            samples: list[tuple[float, float, float]] = []
            for sample_index in range(9):
                parameter = first + (last - first) * sample_index / 8.0
                point = adaptor.Value(parameter)
                u_parameter, v_parameter = geometry.uv(
                    Vec3(point.X(), point.Y(), point.Z())
                )
                if samples:
                    previous_u = samples[-1][1]
                    u_parameter = previous_u + (
                        (u_parameter - previous_u + math.pi) % (2.0 * math.pi)
                        - math.pi
                    )
                samples.append((parameter, u_parameter, v_parameter))

            parameter_span = last - first
            du = (samples[-1][1] - samples[0][1]) / parameter_span
            dv = (samples[-1][2] - samples[0][2]) / parameter_span
            derivative_length = math.hypot(du, dv)
            if not math.isclose(
                derivative_length, 1.0, abs_tol=1e-6, rel_tol=1e-6
            ):
                raise CadQueryConversionError(
                    f"loop ${loop_index}: boundary is not an isoparametric "
                    "cylinder curve"
                )
            du /= derivative_length
            dv /= derivative_length

            for parameter, actual_u, actual_v in samples:
                offset = parameter - first
                expected_u = samples[0][1] + du * offset
                expected_v = samples[0][2] + dv * offset
                if (
                    abs(actual_u - expected_u) > parameter_tolerance * 10.0
                    or abs(actual_v - expected_v) > geometry.tolerance * 10.0
                ):
                    raise CadQueryConversionError(
                        f"loop ${loop_index}: cylinder pcurve is not linear"
                    )

            reversed_edge = edge.wrapped.Orientation() == TopAbs_REVERSED
            oriented_start = samples[-1][1:3] if reversed_edge else samples[0][1:3]
            oriented_end = samples[0][1:3] if reversed_edge else samples[-1][1:3]
            shift = 0.0
            if previous_end is not None:
                shift = round(
                    (previous_end[0] - oriented_start[0]) / (2.0 * math.pi)
                ) * (2.0 * math.pi)
                if abs(previous_end[1] - oriented_start[1]) > geometry.tolerance * 10.0:
                    raise CadQueryConversionError(
                        f"loop ${loop_index}: cylinder pcurves do not connect"
                    )

            origin_u = samples[0][1] + shift - du * first
            origin_v = samples[0][2] - dv * first
            pcurve = Geom2d_Line(
                gp_Pnt2d(origin_u, origin_v), gp_Dir2d(du, dv)
            )
            builder = BRep_Builder()
            builder.UpdateEdge(
                edge.wrapped,
                pcurve,
                geometry.surface,
                location,
                geometry.tolerance,
            )
            builder.Range(edge.wrapped, geometry.surface, location, first, last)
            builder.SameRange(edge.wrapped, True)
            builder.SameParameter(edge.wrapped, True)

            oriented_start = (oriented_start[0] + shift, oriented_start[1])
            oriented_end = (oriented_end[0] + shift, oriented_end[1])
            if loop_start is None:
                loop_start = oriented_start
            previous_end = oriented_end

        assert loop_start is not None and previous_end is not None
        closing_u = (
            (previous_end[0] - loop_start[0] + math.pi) % (2.0 * math.pi)
            - math.pi
        )
        if (
            abs(closing_u) > parameter_tolerance * 10.0
            or abs(previous_end[1] - loop_start[1]) > geometry.tolerance * 10.0
        ):
            raise CadQueryConversionError(
                f"loop ${loop_index}: cylinder pcurves do not close"
            )

    def _wire(
        self,
        loop: LoopEntity,
        placement: _Placement,
        surface_geometry: _CylinderGeometry | None = None,
    ):
        edges = tuple(self._edge(coedge, placement) for coedge in self._coedges(loop))
        if surface_geometry is not None:
            self._attach_surface_pcurves(
                edges, surface_geometry, loop_index=loop.index
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
        if not surface.is_circular():
            raise CadQueryConversionError(
                f"face ${face.index}: elliptical cylinders are not supported"
            )
        if not placement.preserves_circles:
            raise CadQueryConversionError(
                f"face ${face.index}: sheared cylinder/cone placement is not supported"
            )

        from OCP.Geom import Geom_ConicalSurface, Geom_CylindricalSurface
        from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt

        center = placement.point_vector(surface.center)
        axial_direction = surface.axis * surface.cos_half_angle
        axis = placement.oriented_direction(axial_direction)
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
            if surface.is_cylinder():
                ocp_surface = Geom_CylindricalSurface(axis_system, radius)
            else:
                semi_angle = math.atan2(
                    surface.sin_half_angle, surface.cos_half_angle
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
            surface.cos_half_angle,
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
            curve = self.model.resolve(edge.curve)
            if (
                not isinstance(curve, EllipseCurveEntity)
                or not curve.is_circle()
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

        geometry = self._cone_geometry(face, surface, placement)
        try:
            if self._is_full_revolution_face(loops):
                wires = tuple(self._wire(loop, placement) for loop in loops)
                v_parameters: list[float] = []
                for wire in wires:
                    for edge in wire.Edges():
                        adaptor = BRepAdaptor_Curve(edge.wrapped)
                        point = adaptor.Value(adaptor.FirstParameter())
                        _, v_parameter = geometry.uv(
                            Vec3(point.X(), point.Y(), point.Z())
                        )
                        v_parameters.append(v_parameter)
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

    def _face(self, face: FaceEntity, placement: _Placement):
        surface = self.model.resolve(face.surface)
        if not isinstance(surface, (PlaneSurfaceEntity, ConeSurfaceEntity)):
            if surface is None:
                actual = "null"
            elif isinstance(surface, RawEntity):
                actual = surface.type_name
            else:
                actual = surface.raw.type_name
            raise CadQueryConversionError(
                f"face ${face.index} surface: unsupported geometry {actual}"
            )
        loops = self._linked_entities(
            face.loop,
            LoopEntity,
            "next_loop",
            context=f"face ${face.index} loops",
        )
        if not loops:
            raise CadQueryConversionError(f"face ${face.index} has no loop")
        for loop in loops:
            if loop.face.index != face.index:
                raise CadQueryConversionError(
                    f"loop ${loop.index} belongs to face ${loop.face.index}, "
                    f"not ${face.index}"
                )
        if isinstance(surface, PlaneSurfaceEntity):
            result = self._plane_face(face, loops, placement)
        else:
            result = self._cone_face(face, surface, loops, placement)
        if not result.isValid():
            raise CadQueryConversionError(f"face ${face.index}: face is invalid")
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
        if not components:
            raise CadQueryConversionError(
                f"shell ${shell.index}: sewing produced no shell"
            )
        for component_index, component in enumerate(components):
            if not component.isValid():
                raise CadQueryConversionError(
                    f"shell ${shell.index}: component {component_index} is invalid"
                )
            if not component.Closed():
                raise CadQueryConversionError(
                    f"shell ${shell.index}: component {component_index} is not closed"
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
