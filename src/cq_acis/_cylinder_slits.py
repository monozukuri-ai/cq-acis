"""Cylindrical bands with paired source edges on one interior generator."""
from __future__ import annotations

import math
from dataclasses import replace


def cylinder_slit_face(c, face, surface, loops, placement, geometry):
    from .cadquery import CadQueryConversionError
    try:
        return _cylinder_slit_face(c, face, surface, loops, placement, geometry)
    except CadQueryConversionError:
        raise
    except Exception as error:
        raise CadQueryConversionError(f'face ${face.index}: cylinder slit construction failed: {error}',
                                      code='geometry.cylinder_slit_mismatch') from error


def _cylinder_slit_face(c, face, surface, loops, placement, geometry):
    """Represent zero-area paired loops as retained segments of the chart seam.

    Two complete circular rims and disjoint, ordinary straight double uses on
    one generator are qualified. No loop is discarded or exported as an
    INTERNAL edge (STEP can silently omit those). Every saved edge and vertex
    remains in the boundary of a single face; only connecting chart seams and
    circle subdivisions are added. Saved finite charts/pcurves are excluded.
    """
    from .cadquery import CadQueryConversionError
    from .model import EdgeEntity, EllipseCurveEntity, StraightCurveEntity, VertexEntity, Vec3
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
    from OCP.BRepTools import BRepTools_ReShape
    from OCP.ElCLib import ElCLib
    from OCP.Geom2d import Geom2d_Line
    from OCP.TopAbs import TopAbs_FORWARD
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Wire
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt, gp_Pnt2d, gp_Dir2d

    if (len(loops) < 3 or not surface.is_cylinder() or not surface.is_circular()
            or placement.orientation_sign < 0 or any(r is not None and
                (r.lower is not None or r.upper is not None) for r in (surface.profile_range, surface.u_range, surface.v_range))):
        return None
    tol = c.tolerance
    axis, center, radius = geometry.axis, geometry.center, geometry.radius
    rims, slits, saved_points = [], [], []

    def fail(message):
        raise CadQueryConversionError(f'face ${face.index}: {message}', code='geometry.cylinder_slit_mismatch')

    def vec(point):
        return Vec3(*point.Coord())

    for loop in loops:
        uses = c._coedges(loop)
        if any(co.raw.type_name != 'coedge' or not co.pcurve.is_null for co in uses):
            return None
        if len(uses) == 1:
            edge = c._require(uses[0].edge, EdgeEntity, context='cylinder slit rim')
            curve = c._resolve_geometry(edge.curve)
            if (not isinstance(curve, EllipseCurveEntity) or not curve.is_circle()
                    or edge.start_vertex != edge.end_vertex):
                return None
            kind = 'rim'
        elif len(uses) == 2 and uses[0].edge == uses[1].edge and uses[0].reversed != uses[1].reversed:
            edge = c._require(uses[0].edge, EdgeEntity, context='cylinder slit')
            curve = c._resolve_geometry(edge.curve)
            if not isinstance(curve, StraightCurveEntity):
                return None
            kind = 'slit'
        else:
            return None
        if edge.raw.type_name != 'edge' or any(
                not isinstance(c.model.resolve(v), VertexEntity) or c.model.resolve(v).raw.type_name != 'vertex'
                for v in (edge.start_vertex, edge.end_vertex)):
            return None
        points = [placement.point_vector(c._vertex_location(v, context='cylinder slit vertex'))
                  for v in (edge.start_vertex, edge.end_vertex)]
        saved_points.extend(points)
        if kind == 'rim':
            delta = placement.point_vector(curve.center) - center
            v = delta.dot(axis)
            major = placement.vector(curve.major_axis)
            normal = placement.oriented_direction(curve.normal * (1 if curve.ratio >= 0 else -1))
            if (edge.start_parameter is None or edge.end_parameter is None
                    or not math.isclose(abs(edge.end_parameter-edge.start_parameter), 2*math.pi, rel_tol=0., abs_tol=1e-10)
                    or (delta-axis*v).magnitude > tol or abs(major.magnitude-radius) > tol
                    or abs(major.dot(axis)) > tol
                    or abs(abs(normal.dot(axis))-1) > 1e-10):
                fail('rim is not a complete coaxial source circle')
            shape = c._edge(uses[0], placement)
            if any(not any(math.dist((p.x, p.y, p.z), vertex.toTuple()) <= tol
                           for vertex in shape.Vertices()) for p in points):
                fail('rim does not retain its saved vertex')
            sign = normal.dot(axis) * (1 if shape.wrapped.Orientation() == TopAbs_FORWARD else -1)
            rims.append(dict(loop=loop.index, edge=edge.index, v=v, point=points[0], sign=sign))
        else:
            # Construct the saved line/parameter interval, then check it against
            # BOTH saved vertices. Never replace a mismatching line by a chord.
            shape = c._straight_edge(edge, replace(uses[0], reversed=False), placement, curve)
            shape.wrapped.Orientation(TopAbs_FORWARD)
            native_curve = BRep_Tool.Curve_s(shape.wrapped, 0., 0.)
            first, last = BRep_Tool.Range_s(shape.wrapped)
            actual = [vec(native_curve.Value(t)) for t in (first, last)]
            if (not math.isfinite(first+last) or last <= first
                    or any(min((p-q).magnitude for q in actual) > tol for p in points)
                    or any(min((p-q).magnitude for p in points) > tol for q in actual)):
                fail('straight trim disagrees with saved source vertices')
            heights = [(p-center).dot(axis) for p in actual]
            direction = native_curve.Lin().Direction()
            slope = vec(direction).dot(axis)
            if abs(abs(slope)-1) > 1e-10:
                fail('paired edge is not a cylinder generator')
            radial = actual[0]-center-axis*heights[0]
            if abs(radial.magnitude-radius) > tol:
                fail('paired edge is off the cylinder')
            slits.append(dict(loop=loop.index, edge=edge.index, coedges=[u.index for u in uses], shape=shape,
                curve=native_curve, first=first, last=last, heights=heights, low=min(heights), high=max(heights),
                radial=radial, slope=1 if slope > 0 else -1))
    if len(rims) != 2 or not slits:
        return None
    rims.sort(key=lambda rim: rim['v'])
    lower, upper = (r['v'] for r in rims)
    if upper-lower <= tol or rims[0]['sign']*rims[1]['sign'] >= 0:
        fail('rim separation or orientation is inconsistent')
    slits.sort(key=lambda slit: slit['low'])
    radial = slits[0]['radial']
    cursor = lower
    for slit in slits:
        if ((slit['radial']-radial).magnitude > tol or slit['low']-cursor <= tol
                or upper-slit['high'] <= tol):
            fail('paired generator trims overlap, touch a rim, or use different generators')
        cursor = slit['high']

    # Rotate only the generated unbounded chart so its seam contains every
    # paired source edge. The circular cylinder's physical support is unchanged.
    support = geometry.surface.Copy()
    x = radial.normalized()
    support.SetPosition(gp_Ax3(gp_Pnt(center.x, center.y, center.z), gp_Dir(axis.x, axis.y, axis.z),
                              gp_Dir(x.x, x.y, x.z)))
    result = c.cq.Face(BRepBuilderAPI_MakeFace(support, 0., 2*math.pi, lower, upper, tol).Face())
    builder, reshape, location = BRep_Builder(), BRepTools_ReShape(), TopLoc_Location()
    seam = next(e for e in result.Edges() if BRep_Tool.IsClosed_s(e.wrapped, result.wrapped))
    seam.wrapped.Orientation(TopAbs_FORWARD)
    seam_curve = BRep_Tool.Curve_s(seam.wrapped, 0., 0.)
    cursor, vertex = lower, TopExp.FirstVertex_s(seam.wrapped)
    segments = []
    for slit in slits:
        source = slit['shape'].wrapped
        start, end = TopExp.FirstVertex_s(source), TopExp.LastVertex_s(source)
        if slit['slope'] < 0:
            start, end = end, start
        gap = BRepBuilderAPI_MakeEdge(seam_curve, vertex, start, cursor, slit['low']).Edge()
        segments.append((gap, 0., 1))
        offset = slit['heights'][0] - slit['slope']*slit['first']
        segments.append((source, offset, slit['slope']))
        cursor, vertex = slit['high'], end
    gap = BRepBuilderAPI_MakeEdge(seam_curve, vertex, TopExp.LastVertex_s(seam.wrapped), cursor, upper).Edge()
    segments.append((gap, 0., 1))
    wire = TopoDS_Wire()
    builder.MakeWire(wire)
    for edge, offset, slope in segments:
        forward_u, reverse_u = (2*math.pi, 0.) if slope > 0 else (0., 2*math.pi)
        pcs = [Geom2d_Line(gp_Pnt2d(u, offset), gp_Dir2d(0, slope)) for u in (forward_u, reverse_u)]
        builder.UpdateEdge(edge, *pcs, support, location, tol)
        first, last = BRep_Tool.Range_s(edge)
        builder.Range(edge, support, location, first, last)
        builder.SameRange(edge, True)
        builder.SameParameter(edge, True)
        builder.Add(wire, edge if slope > 0 else edge.Reversed())
    reshape.Replace(seam.wrapped, wire)

    # The generated seam need not pass through the stored rim vertices. Split
    # the exact isocircles at those vertices, without dropping or moving them.
    for edge in result.Edges():
        if BRep_Tool.IsClosed_s(edge.wrapped, result.wrapped):
            continue
        edge.wrapped.Orientation(TopAbs_FORWARD)
        curve = BRep_Tool.Curve_s(edge.wrapped, 0., 0.)
        v = (vec(curve.Location())-center).dot(axis)
        rim = min(rims, key=lambda r: abs(r['v']-v))
        point = rim['point']
        first, last = BRep_Tool.Range_s(edge.wrapped)
        t = first + (ElCLib.Parameter_s(curve.Circ(), gp_Pnt(point.x, point.y, point.z))-first) % (2*math.pi)
        if min(t-first, last-t)*radius <= tol:
            continue
        middle = BRepBuilderAPI_MakeVertex(curve.Value(t)).Vertex()
        pc = BRep_Tool.CurveOnSurface_s(edge.wrapped, result.wrapped, 0., 0.)
        wire = TopoDS_Wire()
        builder.MakeWire(wire)
        for a, b, va, vb in ((first, t, TopExp.FirstVertex_s(edge.wrapped), middle),
                              (t, last, middle, TopExp.LastVertex_s(edge.wrapped))):
            cut = BRepBuilderAPI_MakeEdge(curve, va, vb, a, b).Edge()
            builder.UpdateEdge(cut, pc, support, location, tol)
            builder.Range(cut, support, location, a, b)
            builder.Add(wire, cut)
        reshape.Replace(edge.wrapped, wire)
    result = c.cq.Face(reshape.Apply(result.wrapped))
    if rims[0]['sign'] < 0:
        result = c._reverse_face(result)
    proof = _verify_slit_face(c, result, support, slits, saved_points, lower, upper)
    c.cylinder_slit_faces.append(dict(face=face.index, surface=surface.index, loops=[l.index for l in loops],
        rims=[r['edge'] for r in rims], paired_edges=[dict(edge=s['edge'], loop=s['loop'], coedges=s['coedges'],
            parameter_range=(s['first'],s['last'])) for s in slits],
        method='unchanged cylinder with segmented chart seam; paired source edges and all vertices retained', **proof))
    return result


def _verify_slit_face(c, result, support, slits, saved_points, lower, upper):
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from ._supported_curves import deviation
    from .cadquery import CadQueryConversionError

    def require(condition, message):
        if not condition:
            raise CadQueryConversionError('cylinder slit verification: '+message, code='geometry.cylinder_slit_mismatch')

    require(result.isValid() and len(result.Wires()) == 1, 'expected one valid face wire')
    require(math.isclose(result.Area(), 2*math.pi*support.Radius()*(upper-lower), rel_tol=1e-10, abs_tol=1e-7),
            'cylindrical band area changed')
    maximum = 0.
    edges = result.Edges()
    require(len([e for e in edges if BRep_Tool.IsClosed_s(e.wrapped, result.wrapped)]) == 2*len(slits)+1,
            'incomplete seam segmentation')
    for slit in slits:
        matches = [e for e in edges if BRep_Tool.Curve_s(e.wrapped, 0., 0.) == slit['curve']]
        require(len(matches) == 1 and BRep_Tool.Range_s(matches[0].wrapped) == (slit['first'],slit['last']),
                'source paired trim was removed or changed')
    for edge in edges:
        require(BRep_Tool.Tolerance_s(edge.wrapped) <= math.nextafter(c.tolerance, math.inf), 'edge tolerance enlarged')
        seam = BRep_Tool.IsClosed_s(edge.wrapped, result.wrapped)
        uses = [edge.wrapped]
        if seam:
            uses.append(TopoDS.Edge_s(edge.wrapped.Reversed()))
            explorer = TopExp_Explorer(result.wrapped, TopAbs_EDGE)
            senses = []
            while explorer.More():
                use = explorer.Current()
                if use.IsSame(edge.wrapped):
                    senses.append(use.Orientation())
                explorer.Next()
            require(len(senses) == 2 and senses[0] != senses[1], 'seam must retain two opposite uses')
        curve = BRep_Tool.Curve_s(edge.wrapped, 0., 0.)
        first, last = BRep_Tool.Range_s(edge.wrapped)
        for use in uses:
            pc = BRep_Tool.CurveOnSurface_s(use, result.wrapped, 0., 0.)
            require(pc is not None and BRep_Tool.Range_s(use, result.wrapped) == (first, last), 'missing or mistimed UV')
            error = deviation(curve, pc, support, first, last)
            require(math.isfinite(error) and error <= c.tolerance, 'curve left source cylinder')
            maximum = max(maximum, error)
    vertices = result.Vertices()
    for p in saved_points:
        require(any(math.dist((p.x,p.y,p.z),v.toTuple()) <= c.tolerance for v in vertices), 'saved vertex lost or moved')
    require(all(BRep_Tool.Tolerance_s(v.wrapped) <= math.nextafter(c.tolerance, math.inf) for v in vertices),
            'vertex tolerance enlarged')
    return dict(source_paired_edges=len(slits), seam_segments=2*len(slits)+1,
                max_deviation_mm=maximum, tolerance_mm=c.tolerance)
