"""Qualified chart seams for cylindrical faces with two winding boundaries."""
from __future__ import annotations

import math


def cylinder_seam_face(converter, face, loops, wires, geometry, original, placement):
    """Add a chart seam, retaining every oriented source curve and trim interval.

    Only ordinary circular/linear boundaries with generated linear UV curves
    and two opposite single windings are qualified. Saved/tolerant UV curves
    and general face healing are deliberately outside this operation.
    """
    from OCP.BRep import BRep_Tool
    from OCP.Geom import Geom_Circle, Geom_Line
    from OCP.Geom2d import Geom2d_Line
    from OCP.ShapeFix import ShapeFix_Face
    from OCP.TopAbs import TopAbs_REVERSED
    from .cadquery import CadQueryConversionError
    from .model import EdgeEntity, VertexEntity

    if len(loops) != 2 or len(wires) != 2:
        return None
    source_surface = converter._resolve_geometry(face.surface)
    if any(r is not None and (r.lower is not None or r.upper is not None)
           for r in (source_surface.u_range, source_surface.v_range)):
        return None
    coedges = [co for loop in loops for co in converter._coedges(loop)]
    if any(co.raw.type_name != 'coedge' or not co.pcurve.is_null for co in coedges):
        return None
    source_edges = [converter.model.resolve(co.edge) for co in coedges]
    if any(not isinstance(e, EdgeEntity) or e.raw.type_name != 'edge' for e in source_edges):
        return None
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
            if not isinstance(curve, (Geom_Circle, Geom_Line)) or not isinstance(pc, Geom2d_Line):
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
    try:
        proof = _check_seam_boundaries(converter, result, geometry.surface, boundaries)
    except CadQueryConversionError:
        raise
    except Exception as error:
        raise CadQueryConversionError(f'face ${face.index}: cylinder seam verification failed: {error}',
                                      code='geometry.analytic_trim_mismatch') from error
    converter.periodic_seam_faces.append(dict(face=face.index,
        loops=[loop.index for loop in loops], edges=[co.edge.index for co in coedges],
        method='cylinder chart seam; unchanged oriented 3D curves and complete trim intervals', **proof))
    return result


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
