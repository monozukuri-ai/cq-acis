"""Experimental analytic OCCT -> ACIS authoring (no native API or template).

The generated profile uses kernel-derived pcurves and is not native-qualified.
Original UV curves are retained in the audit, including both seam branches; they
are not serialized by this candidate encoder. This API does not write IPT files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import json

from . import _native


class AuthoringError(ValueError):
    """Input is outside the bounded analytic authoring profile."""


@dataclass(frozen=True)
class UvCurve:
    face: int
    loop: int
    use: int
    edge: int
    seam: bool
    kind: str
    parameters: tuple[float, float]
    # Exact OCCT definition in its original chart (not a sampled polyline).
    definition: tuple


@dataclass(frozen=True)
class SurfaceChart:
    face: int
    kind: str
    origin: tuple[float, float, float]
    x_direction: tuple[float, float, float]
    y_direction: tuple[float, float, float]
    axis: tuple[float, float, float]
    uv_bounds: tuple[float, float, float, float]
    # U is unchanged; reflected cylindrical charts map V -> -V and reverse
    # each generated loop. UvCurve.use retains the original OCCT walk index.
    generated_v_sign: int


@dataclass(frozen=True)
class AuthoredShape:
    """Immutable generated model plus the source UV definitions for qualification."""
    _generated: object
    pcurves: tuple[UvCurve, ...]
    charts: tuple[SurfaceChart, ...]
    tolerance_mm: float
    _semantic_json: str = field(default='', repr=False)
    profile: str = field(default='asm23200-analytic-kernel-derived-experimental', init=False)
    native_qualified: bool = field(default=False, init=False)

    @property
    def model(self):
        return self._generated.model

    def to_sab(self, *, history: bool = False) -> bytes:
        """Encode a SAB candidate; native acceptance is a separate gate."""
        return self._generated.to_sab(history=history)

    def to_spec(self) -> dict:
        """Return a detached millimetre semantic specification, without SAB data.

        Only values produced by ``from_cadquery`` retain this specification.
        Mutating the returned dictionary never changes this authored value.
        The result, including after a JSON round trip, can be passed to
        ``_native.author_analytic`` to rebuild the generated model.
        """
        if not self._semantic_json:
            raise AuthoringError('semantic specification unavailable')
        return json.loads(self._semantic_json)


def _xyz(v):
    return (v.X(), v.Y(), v.Z())


def _xy(v):
    return (v.X(), v.Y())


def _same_index(table, shape):
    for i, item in enumerate(table):
        if item.IsSame(shape):
            return i
    raise AuthoringError('topology references a shape outside its shared table')


def _uv_definition(curve):
    from OCP.Geom2d import Geom2d_TrimmedCurve
    from OCP.Geom2dAdaptor import Geom2dAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle, GeomAbs_Ellipse, GeomAbs_BSplineCurve
    while isinstance(curve, Geom2d_TrimmedCurve):
        curve = curve.BasisCurve()
    a = Geom2dAdaptor_Curve(curve)
    kind = a.GetType()
    if kind == GeomAbs_Line:
        c = a.Line()
        return 'line', (_xy(c.Location()), _xy(c.Direction()))
    if kind in (GeomAbs_Circle, GeomAbs_Ellipse):
        c = a.Circle() if kind == GeomAbs_Circle else a.Ellipse()
        major = c.Radius() if kind == GeomAbs_Circle else c.MajorRadius()
        minor = major if kind == GeomAbs_Circle else c.MinorRadius()
        return 'ellipse', (_xy(c.Location()), _xy(c.XAxis().Direction()), _xy(c.YAxis().Direction()), major, minor)
    if kind == GeomAbs_BSplineCurve:
        c = a.BSpline()
        if c.NbPoles() > 4096 or c.NbKnots() > 4096:
            raise AuthoringError('UV B-spline budget exceeded')
        return 'bspline', (c.Degree(), c.IsPeriodic(),
            tuple(_xy(c.Pole(i)) for i in range(1, c.NbPoles()+1)),
            tuple(c.Weight(i) for i in range(1, c.NbPoles()+1)),
            tuple(c.Knot(i) for i in range(1, c.NbKnots()+1)),
            tuple(c.Multiplicity(i) for i in range(1, c.NbKnots()+1)))
    raise AuthoringError(f'unsupported UV curve: {kind}')


def from_cadquery(shape) -> AuthoredShape:
    """Create an experimental analytic model from exactly one valid OCCT solid.

    Supports planes/circular cylinders and lines/circles/ellipses. Shared topology,
    face senses, full circles, hole loops and the two seam occurrences are kept.
    OCCT locations are applied by its adaptors once; no mesh or STEP export is used.
    """
    import cadquery as cq
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
    from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle, GeomAbs_Ellipse, GeomAbs_Plane, GeomAbs_Cylinder
    from OCP.TopAbs import TopAbs_FORWARD, TopAbs_REVERSED
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    if isinstance(shape, cq.Workplane):
        values = shape.vals()
        if len(values) != 1:
            raise AuthoringError('expected one solid, not a workplane with multiple objects')
        shape = values[0]
    if not isinstance(shape, cq.Solid):
        raise AuthoringError('expected one cadquery.Solid (extract compounds explicitly)')
    if not shape.isValid() or len(shape.Shells()) != 1 or not shape.Shells()[0].wrapped.Closed() or shape.Volume() <= 0:
        raise AuthoringError('expected a valid, closed, positive-volume solid with one shell')
    vertices = [v.wrapped for v in shape.Vertices()]
    edges = [TopoDS.Edge_s(e.wrapped.Oriented(TopAbs_FORWARD)) for e in shape.Edges()]
    faces = shape.Faces()
    if not all(0 < len(items) <= 4096 for items in (vertices, edges, faces)):
        raise AuthoringError('analytic topology budget exceeded')
    tolerance = max(BRep_Tool.Tolerance_s(s) for s in [*vertices, *edges, *(f.wrapped for f in faces)])
    if not math.isfinite(tolerance) or tolerance > 1e-5:
        raise AuthoringError(f'source tolerance {tolerance} mm exceeds 1e-5 mm profile')
    spec = dict(vertices_mm=[_xyz(BRep_Tool.Pnt_s(v)) for v in vertices], edges=[], faces=[], tolerance_mm=tolerance)
    for i, e in enumerate(edges):
        if BRep_Tool.Degenerated_s(e):
            raise AuthoringError(f'edge {i}: degenerate edges are unsupported')
        a = BRepAdaptor_Curve(e)
        kind = a.GetType()
        if kind == GeomAbs_Line:
            c = a.Line()
            curve = dict(kind='line', origin=_xyz(c.Location()), direction=_xyz(c.Direction()))
        elif kind in (GeomAbs_Circle, GeomAbs_Ellipse):
            c = a.Circle() if kind == GeomAbs_Circle else a.Ellipse()
            radius = c.Radius() if kind == GeomAbs_Circle else c.MajorRadius()
            minor = radius if kind == GeomAbs_Circle else c.MinorRadius()
            curve = dict(kind='ellipse', center=_xyz(c.Location()), normal=_xyz(c.Axis().Direction()),
                major_axis=tuple(x*radius for x in _xyz(c.XAxis().Direction())), ratio=minor/radius)
        else:
            raise AuthoringError(f'edge {i}: unsupported 3D curve {kind}')
        spec['edges'].append(dict(vertices=[_same_index(vertices, TopExp.FirstVertex_s(e)),
            _same_index(vertices, TopExp.LastVertex_s(e))], parameters=[a.FirstParameter(), a.LastParameter()], curve=curve))
    uv_curves = []
    charts = []
    for fi, original in enumerate(faces):
        if original.wrapped.Orientation() not in (TopAbs_FORWARD, TopAbs_REVERSED):
            raise AuthoringError(f'face {fi}: unsupported face orientation')
        f = TopoDS.Face_s(original.wrapped.Oriented(TopAbs_FORWARD))
        a = BRepAdaptor_Surface(f, False)
        reverse_chart = False
        if a.GetType() == GeomAbs_Plane:
            c = a.Plane()
            normal = c.XAxis().Direction().Crossed(c.YAxis().Direction())
            surface = dict(kind='plane', origin=_xyz(c.Location()), normal=_xyz(normal), u_direction=_xyz(c.XAxis().Direction()))
        elif a.GetType() == GeomAbs_Cylinder:
            c = a.Cylinder()
            reverse_chart = not c.Position().Direct()
            axis = c.XAxis().Direction().Crossed(c.YAxis().Direction())
            surface = dict(kind='cylinder', center=_xyz(c.Location()), axis=_xyz(axis), x_direction=_xyz(c.XAxis().Direction()), radius=c.Radius())
        else:
            raise AuthoringError(f'face {fi}: unsupported surface {a.GetType()}')
        charts.append(SurfaceChart(fi, surface['kind'], _xyz(c.Location()),
            _xyz(c.XAxis().Direction()), _xyz(c.YAxis().Direction()), _xyz(c.Axis().Direction()),
            tuple(BRepTools.UVBounds_s(f)), -1 if reverse_chart else 1))
        outer = BRepTools.OuterWire_s(f)
        wires = cq.Face(f).Wires()
        if outer.IsNull() or sum(w.wrapped.IsSame(outer) for w in wires) != 1:
            raise AuthoringError(f'face {fi}: outer wire is ambiguous')
        wires.sort(key=lambda w: not w.wrapped.IsSame(outer))
        loops = []
        for li, w in enumerate(wires):
            walk = []
            explorer = BRepTools_WireExplorer(w.wrapped, f)
            while explorer.More():
                e = explorer.Current()
                if e.Orientation() not in (TopAbs_FORWARD, TopAbs_REVERSED):
                    raise AuthoringError(f'face {fi}: unsupported coedge orientation')
                ei = _same_index(edges, e)
                walk.append((ei, e.Orientation() == TopAbs_REVERSED))
                params = BRep_Tool.Range_s(e, f)
                pc = BRep_Tool.CurveOnSurface_s(e, f, *params)
                if pc is None:
                    raise AuthoringError(f'face {fi} edge {ei}: no UV curve')
                kind, definition = _uv_definition(pc)
                uv_curves.append(UvCurve(fi, li, len(walk)-1, ei, BRep_Tool.IsClosed_s(e,f), kind, tuple(params), definition))
                explorer.Next()
            # Count occurrences, not unique edges: a seam must appear twice.
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE
            count = 0
            ex = TopExp_Explorer(w.wrapped, TopAbs_EDGE)
            while ex.More():
                count += 1
                ex.Next()
            if len(walk) != count or not walk:
                raise AuthoringError(f'face {fi}: wire traversal omitted edges')
            loops.append([(e, not r) for e, r in reversed(walk)] if reverse_chart else walk)
        spec['faces'].append(dict(surface=surface, reversed=(original.wrapped.Orientation()==TopAbs_REVERSED)^reverse_chart, loops=loops))
    try:
        generated = _native.author_analytic(spec)
    except ValueError as e:
        raise AuthoringError(str(e)) from e
    return AuthoredShape(generated, tuple(uv_curves), tuple(charts), tolerance,
                         json.dumps(spec, allow_nan=False, separators=(',', ':')))
