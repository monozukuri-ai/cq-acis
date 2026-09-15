"""Qualified chart seams for cylindrical faces with two winding boundaries."""
from __future__ import annotations

import math


def cylinder_seam_face(converter, face, loops, wires, geometry, original, placement, *, elliptic_sections=False):
    """Add a chart seam, retaining every oriented source curve and trim interval.

    Ordinary circular/linear boundaries use generated linear UV curves. Two
    complete elliptic plane sections additionally require an analytic support
    and separation proof. Both paths require opposite single windings; saved
    UV curves and general face healing are outside this operation.
    """
    from OCP.BRep import BRep_Tool
    from OCP.Geom import Geom_Circle, Geom_Line, Geom_Ellipse
    from OCP.Geom2d import Geom2d_Line
    from OCP.ShapeFix import ShapeFix_Face
    from OCP.TopAbs import TopAbs_REVERSED
    from .cadquery import CadQueryConversionError
    from .model import EdgeEntity, VertexEntity

    if len(loops) != 2 or len(wires) != 2:
        return None
    source_surface = converter._resolve_geometry(face.surface)
    saved_ranges = (source_surface.u_range, source_surface.v_range)
    if elliptic_sections:
        saved_ranges += (source_surface.profile_range,)
    if any(r is not None and (r.lower is not None or r.upper is not None)
           for r in saved_ranges):
        return None
    coedges = [co for loop in loops for co in converter._coedges(loop)]
    if any(co.raw.type_name != 'coedge' or not co.pcurve.is_null for co in coedges):
        return None
    source_edges = [converter.model.resolve(co.edge) for co in coedges]
    if any(not isinstance(e, EdgeEntity) or e.raw.type_name != 'edge' for e in source_edges):
        return None
    if elliptic_sections:
        _check_elliptic_sections(converter, loops, geometry, placement)
    for source_edge in source_edges:
        vertices = [converter.model.resolve(v) for v in (source_edge.start_vertex, source_edge.end_vertex)]
        if any(not isinstance(v, VertexEntity) or v.raw.type_name != 'vertex' for v in vertices):
            return None
    boundary_points = [v.toTuple() for wire in wires for v in wire.Vertices()]
    for source_edge in source_edges:
        for vertex in (source_edge.start_vertex, source_edge.end_vertex):
            point = placement.point(converter._vertex_location(vertex, context='cylinder seam source vertex'))
            if not any(math.dist(point, actual) <= converter.tolerance for actual in boundary_points):
                raise CadQueryConversionError('cylinder trim does not retain a saved source vertex',
                                              code='geometry.analytic_trim_mismatch')
    boundaries = []
    winding = []
    for wire in wires:
        delta = [0., 0.]
        for edge in wire.Edges():
            curve = BRep_Tool.Curve_s(edge.wrapped, 0., 0.)
            pc = BRep_Tool.CurveOnSurface_s(edge.wrapped, original.wrapped, 0., 0.)
            if (not isinstance(curve, (Geom_Circle, Geom_Ellipse) if elliptic_sections else (Geom_Circle, Geom_Line))
                    or pc is None or (not elliptic_sections and not isinstance(pc, Geom2d_Line))):
                return None
            first, last = BRep_Tool.Range_s(edge.wrapped)
            start, end = pc.Value(first), pc.Value(last)
            sign = -1 if edge.wrapped.Orientation() == TopAbs_REVERSED else 1
            delta[0] += sign * (end.X() - start.X())
            delta[1] += sign * (end.Y() - start.Y())
            boundaries.append((edge, curve, first, last))
        if abs(abs(delta[0]) - 2 * math.pi) > 1e-10 or abs(delta[1]) > converter.tolerance:
            return None
        winding.append(delta[0])
    if abs(sum(winding)) > 1e-10:
        raise CadQueryConversionError('cylinder boundary windings have inconsistent senses',
                                      code='geometry.boundary_orientation')
    fixer = ShapeFix_Face(original.wrapped)
    fixer.SetPrecision(converter.tolerance)
    fixer.SetMaxTolerance(converter.tolerance)
    if not fixer.FixMissingSeam():
        return None
    result = converter.cq.Face(fixer.Face())
    # FixMissingSeam may reverse every wire to give the chart its natural
    # orientation. Restore the source's whole-face sense before checking each
    # physical use; a mixture of changed senses is never accepted.
    restored = False
    if placement.orientation_sign > 0:
        senses = []
        for edge in result.Edges():
            if BRep_Tool.IsClosed_s(edge.wrapped, result.wrapped):
                continue
            curve = BRep_Tool.Curve_s(edge.wrapped, 0., 0.)
            matches = [source for source, saved, _, _ in boundaries if curve == saved]
            if len(matches) == 1:
                senses.append(edge.wrapped.Orientation() != matches[0].wrapped.Orientation())
        if senses and all(senses):
            result = converter._reverse_face(result)
            restored = True
    try:
        proof = _check_seam_boundaries(converter, result, geometry.surface, boundaries)
    except CadQueryConversionError:
        raise
    except Exception as error:
        raise CadQueryConversionError(f'face ${face.index}: cylinder seam verification failed: {error}',
                                      code='geometry.analytic_trim_mismatch') from error
    converter.periodic_seam_faces.append(dict(face=face.index,
        loops=[loop.index for loop in loops], edges=[co.edge.index for co in coedges],
        method='cylinder chart seam; unchanged oriented 3D curves and complete trim intervals',
        elliptic_sections=elliptic_sections, source_sense_restored=restored, **proof))
    return result


def _check_elliptic_sections(converter, loops, geometry, placement):
    """Prove two disjoint plane sections of the same circular cylinder.

    The projected major/minor axes must form a radius-R circle. Each section
    is then a single-valued height c + a*cos(U) + b*sin(U); its full separation
    from the other section has an analytic minimum, without sample fitting.
    """
    from .cadquery import CadQueryConversionError
    from .model import EdgeEntity, EllipseCurveEntity
    sections = []
    tol, radius = converter.tolerance, geometry.radius
    for loop in loops:
        coedges = converter._coedges(loop)
        if len(coedges) != 1:
            raise CadQueryConversionError('elliptic cylinder section must be a complete rim')
        edge = converter._require(coedges[0].edge, EdgeEntity,
                                  context='elliptic cylinder section')
        curve = converter._resolve_geometry(edge.curve)
        if not isinstance(curve, EllipseCurveEntity) or edge.start_vertex != edge.end_vertex:
            raise CadQueryConversionError('elliptic cylinder section must be a closed ellipse')
        if (edge.start_parameter is None or edge.end_parameter is None
                or not math.isfinite(edge.start_parameter + edge.end_parameter)
                or not math.isclose(abs(edge.end_parameter-edge.start_parameter), 2*math.pi,
                                    rel_tol=0., abs_tol=1e-10)):
            raise CadQueryConversionError('elliptic cylinder section does not retain a complete saved interval',
                                          code='geometry.analytic_trim_mismatch')
        delta = placement.point_vector(curve.center) - geometry.center
        major = placement.vector(curve.major_axis)
        normal = placement.oriented_direction(curve.normal).normalized()
        minor = normal.cross(major) * abs(curve.ratio)
        axial = normal.dot(geometry.axis)
        radial_center = delta - geometry.axis * delta.dot(geometry.axis)
        projected = [v - geometry.axis * v.dot(geometry.axis) for v in (major, minor)]
        if (radial_center.magnitude > tol or abs(axial) < 1e-8 or abs(normal.dot(major)) > tol
                or any(abs(v.magnitude-radius) > tol for v in projected)
                or abs(projected[0].dot(projected[1])) > tol*radius):
            raise CadQueryConversionError('ellipse is not a section of the source cylinder',
                                          code='geometry.analytic_trim_mismatch')
        sections.append((delta.dot(geometry.axis), -radius*normal.dot(geometry.x_direction)/axial,
                         -radius*normal.dot(geometry.y_direction)/axial))
    dc, da, db = (b-a for a, b in zip(*sections))
    if abs(dc) - math.hypot(da, db) <= tol:
        raise CadQueryConversionError('cylinder section boundaries intersect or touch',
                                      code='geometry.analytic_trim_mismatch')


def _check_seam_boundaries(converter, result, surface, boundaries):
    from OCP.BRep import BRep_Tool
    from OCP.BRepLib import BRepLib
    from OCP.Geom import Geom_CylindricalSurface, Geom_RectangularTrimmedSurface
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from ._supported_curves import deviation

    support = BRep_Tool.Surface_s(result.wrapped)
    if isinstance(support, Geom_RectangularTrimmedSurface):
        support = support.BasisSurface()
    def frame(s):
        return (s.Radius(), s.Location().Coord(), s.Position().XDirection().Coord(),
                s.Position().YDirection().Coord(), s.Axis().Direction().Coord())
    if not isinstance(support, Geom_CylindricalSurface) or frame(support) != frame(surface):
        raise ValueError('cylinder support was changed')
    # The seam tool creates a new edge at its default tolerance and may split
    # circles with unset parameter flags. Recompute generated UV clocks and
    # their tolerances, then independently qualify every 3D curve below.
    # This path has no saved pcurves to refit.
    BRepLib.SameParameter_s(result.wrapped, converter.tolerance, True)
    spans = [[] for _ in boundaries]
    maximum = 0.
    seams = []
    # OCCT may round the scaled source precision (e.g. 1e-6 * 10) by one ulp.
    tolerance_limit = math.nextafter(converter.tolerance, math.inf)
    for edge in result.Edges():
        curve = BRep_Tool.Curve_s(edge.wrapped, 0., 0.)
        first, last = BRep_Tool.Range_s(edge.wrapped)
        seam = BRep_Tool.IsClosed_s(edge.wrapped, result.wrapped)
        if seam:
            seams.append(edge)
        else:
            matches = [i for i, (source, saved, _, _) in enumerate(boundaries)
                       if curve == saved and edge.wrapped.Orientation() == source.wrapped.Orientation()]
            if len(matches) != 1:
                raise ValueError('changed, ambiguous or reversed physical boundary')
            spans[matches[0]].append((first, last))
        uses = (edge.wrapped, TopoDS.Edge_s(edge.wrapped.Reversed())) if seam else (edge.wrapped,)
        for use in uses:
            pc = BRep_Tool.CurveOnSurface_s(use, result.wrapped, 0., 0.)
            if pc is None or BRep_Tool.Range_s(use, result.wrapped) != (first, last):
                raise ValueError('missing pcurve or inconsistent trim clock')
            distance = deviation(curve, pc, surface, first, last)
            if not math.isfinite(distance) or distance > converter.tolerance:
                raise ValueError('seam pcurve exceeds source precision')
            maximum = max(maximum, distance)
        if BRep_Tool.Tolerance_s(edge.wrapped) > tolerance_limit:
            raise ValueError('edge tolerance was enlarged')
    if len(seams) != 1 or len(result.Wires()) != 1:
        raise ValueError('expected one chart seam in one wire')
    explorer = TopExp_Explorer(result.wrapped, TopAbs_EDGE)
    senses = []
    while explorer.More():
        use = explorer.Current()
        if use.IsSame(seams[0].wrapped):
            senses.append(use.Orientation())
        explorer.Next()
    if len(senses) != 2 or senses[0] == senses[1]:
        raise ValueError('chart seam must have two opposite uses')
    for (_, curve, first, last), intervals in zip(boundaries, spans):
        epsilon = max(1e-12, 64 * math.ulp(max(1., abs(first), abs(last))))
        if curve.IsPeriodic():
            period = curve.Period()
            normalized = []
            for start, end in intervals:
                length = end - start
                if length <= 0 or length > period + epsilon:
                    raise ValueError('invalid periodic trim length')
                start = first + (start - first) % period
                if first + period - start <= epsilon:
                    start = first
                end = start + length
                if end > first + period + epsilon:
                    normalized.extend(((start, first + period), (first, end - period)))
                else:
                    normalized.append((start, min(end, first + period)))
            intervals = normalized
        cursor = first
        for start, end in sorted(intervals):
            if abs(start - cursor) > epsilon or end <= start:
                raise ValueError('source trim was omitted, overlapped or extended')
            cursor = end
        if not intervals or abs(cursor - last) > epsilon:
            raise ValueError('incomplete source trim coverage')
    vertices = result.Vertices()
    for source, _, _, _ in boundaries:
        for vertex in source.Vertices():
            if not any(math.dist(vertex.toTuple(), other.toTuple()) <= converter.tolerance for other in vertices):
                raise ValueError('source vertex was removed or moved')
    if any(BRep_Tool.Tolerance_s(v.wrapped) > tolerance_limit for v in vertices):
        raise ValueError('vertex tolerance was enlarged')
    if not result.isValid() or not math.isfinite(result.Area()) or result.Area() <= 0:
        raise ValueError('cylinder seam did not produce a valid bounded face')
    return dict(source_edges=len(boundaries), physical_edges=sum(map(len, spans)),
                seam_edges=len(seams), max_deviation_mm=maximum, tolerance_mm=converter.tolerance)
