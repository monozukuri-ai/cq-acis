"""Analytic oracles for bounded UV trims and saved tolerant boundaries."""
from dataclasses import replace
import math
import unittest

import cq_acis as a
from cq_acis.cadquery import _Placement
from test_m4_topology import model, raw

N = a.NULL_REF
R = a.EntityRef


def surface_values():
    return (N, b"\x0b", b"\x0f", "exact_spl_sur", 22601, 0, "nubs", 1, 1, 0, 0, 0, 0, 2, 2,
            0., 1, 1., 1, 0., 1, 1., 1,
            0., 0., 0., 2., 0., 0., 0., 3., 0., 2., 3., 0.,
            0., 0, 0, 0, 0, 0, 0, b"\x0b", b"\x0a", 1., b"\x0a", 0.,
            b"\x0a", 1., b"\x0a", 0., 0, b"\x10", b"\x0b", b"\x0b", b"\x0b", b"\x0b")


def pcurve_values(start=(.2, .2), end=(.8, .2)):
    return (N, 0, b"\x0b", b"\x0f", "exp_par_cur", "nubs", 1, 0, 2, 0., 1, 1., 1,
            *start, *end, 0., "spline", b"\x0b", b"\x0f", "ref", 0, b"\x10",
            b"\x0b", b"\x0b", b"\x0b", b"\x0b", b"\x10", 0., 0.)


def boundary(spline=False, edge_reversed=False, coedge_reversed=False):
    if spline:
        curve = a.BSplineCurveEntity(raw(0, "intcurve-curve"), N, 2, (0., 1.), (3, 3),
            (a.Vec3(1, 0, 0), a.Vec3(1, 1, 0), a.Vec3(0, 1, 0)),
            (1., math.sqrt(.5), 1.), None, 0.)
        first, last = .2, .8
    else:
        curve = a.EllipseCurveEntity(raw(0, "ellipse-curve"), N, a.Vec3(0, 0, 0),
            a.Vec3(0, 0, 1), a.Vec3(2, 0, 0), 1., None)
        first, last = 0., math.pi / 2
    parameters = (-last, -first) if edge_reversed else (first, last)
    sign = -1 if edge_reversed else 1
    points = [curve.evaluate(sign * t) for t in parameters]
    interval = tuple(sorted((-1 if coedge_reversed else 1) * t for t in parameters))
    return model([
        curve,
        raw(1, "tedge-edge", (N, R(2), parameters[0], R(4), parameters[1], R(6), R(0),
                               b"\x0a" if edge_reversed else b"\x0b", "tangent", 100., 22601, 0)),
        raw(2, "tvertex-vertex", (N, R(1), 1, R(3), -1., 100., 200., 0)),
        a.PointEntity(raw(3, "point"), N, points[0]),
        raw(4, "tvertex-vertex", (N, R(1), 1, R(5), -1., 100., 200., 0)),
        a.PointEntity(raw(5, "point"), N, points[1]),
        raw(6, "tcoedge-coedge", (N, R(6), R(6), N, R(1),
            b"\x0a" if coedge_reversed else b"\x0b", R(7), 0, N, *interval, N, 0, "null_curve", 0)),
        a.LoopEntity(raw(7, "loop"), N, N, R(6), N),
    ])


def polygon_face(uv=((.2, .2), (.8, .2), (.8, .8), (.2, .8)), bounds=(.1, .9, .1, .9)):
    surface = a.BSplineSurfaceEntity(raw(1, "spline-surface"), N, 1, 1,
        (0., 1.), (0., 1.), (2, 2), (2, 2), 2, 2,
        (a.Vec3(0, 0, 0), a.Vec3(2, 0, 0), a.Vec3(0, 3, 0), a.Vec3(2, 3, 0)),
        (1., 1., 1., 1.), False, a.ParameterRange(*bounds[:2]), a.ParameterRange(*bounds[2:]), 0.)
    face = a.FaceEntity(raw(0, "face"), N, N, R(2), N, N, R(1), False, False, None)
    entries = [face, surface, a.LoopEntity(raw(2, "loop"), N, N, R(3), R(0))]
    for i, (u, v) in enumerate(uv):
        j = (i + 1) % len(uv)
        prev = (i - 1) % len(uv)
        base, following = 3 + 5 * i, 3 + 5 * j
        point = a.Vec3(2 * u, 3 * v, 0)
        end = a.Vec3(2 * uv[j][0], 3 * uv[j][1], 0)
        entries.extend([
            a.CoedgeEntity(raw(base, "coedge"), N, R(following), R(3 + 5 * prev), N,
                           R(base + 1), False, R(2), N),
            a.EdgeEntity(raw(base + 1, "edge"), N, R(base + 2), 0., R(following + 2), 1.,
                         R(base), R(base + 4), False, None),
            a.VertexEntity(raw(base + 2, "vertex"), N, R(base + 1), R(base + 3)),
            a.PointEntity(raw(base + 3, "point"), N, point),
            a.StraightCurveEntity(raw(base + 4, "straight-curve"), N, point, end - point, None),
        ])
    return model(entries)


class TolerantBoundaryTests(unittest.TestCase):
    def convert(self, source):
        converter = a.CadQueryConverter(source)
        coedge, = converter._coedges(source.entities[7])
        return converter, converter._edge(coedge, _Placement(None, 1.))

    def test_circle_and_rational_spline_keep_all_four_orientations(self):
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.TopAbs import TopAbs_REVERSED
        for spline in (False, True):
            for edge_reversed in (False, True):
                for coedge_reversed in (False, True):
                    with self.subTest(spline=spline, edge=edge_reversed, coedge=coedge_reversed):
                        source = boundary(spline, edge_reversed, coedge_reversed)
                        converter, shape = self.convert(source)
                        self.assertTrue(shape.isValid())
                        self.assertEqual(shape.wrapped.Orientation() == TopAbs_REVERSED,
                                         edge_reversed ^ coedge_reversed)
                        adaptor = BRepAdaptor_Curve(shape.wrapped)
                        for fraction in (0., .25, .5, .75, 1.):
                            t = adaptor.FirstParameter() + fraction * (adaptor.LastParameter() - adaptor.FirstParameter())
                            p = adaptor.Value(t)
                            self.assertAlmostEqual(math.hypot(p.X(), p.Y()), 1. if spline else 2., places=12)
                        if not spline:
                            self.assertAlmostEqual(shape.Length(), math.pi, places=12)
                        self.assertEqual(len(converter.tolerant_boundaries), 1)
                        self.assertLessEqual(converter.tolerant_boundaries[0]["max_endpoint_deviation_mm"], 1e-6)
                        self.assertIsInstance(source.entities[1], a.RawEntity)

    def test_saved_scalars_never_expand_model_precision(self):
        source = boundary()
        point = replace(source.entities[3], location=a.Vec3(2.001, 0, 0))
        changed = replace(source, entities=tuple(point if e.index == 3 else e for e in source.entities))
        with self.assertRaises(a.CadQueryConversionError) as caught:
            self.convert(changed)
        self.assertEqual(caught.exception.code, "geometry.tolerant_endpoint_mismatch")

    def test_tolerant_line_uses_saved_curve_instead_of_fitting_the_vertex_chord(self):
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        for reversed_edge in (False, True):
            source = boundary(edge_reversed=reversed_edge)
            curve = a.StraightCurveEntity(raw(0, "straight-curve"), N,
                                         a.Vec3(4, 5, 6), a.Vec3(2, 0, 0), None)
            params = source.entities[1].values[2], source.entities[1].values[4]
            sign = -1 if reversed_edge else 1
            entries = list(source.entities)
            entries[0] = curve
            entries[3] = replace(entries[3], location=curve.origin+curve.direction*(sign*params[0]))
            entries[5] = replace(entries[5], location=curve.origin+curve.direction*(sign*params[1]))
            source = replace(source, entities=tuple(entries))
            _, shape = self.convert(source)
            self.assertAlmostEqual(shape.Length(), math.pi, places=12)
            adaptor = BRepAdaptor_Curve(shape.wrapped)
            point = adaptor.Value((adaptor.FirstParameter()+adaptor.LastParameter())/2)
            self.assertAlmostEqual(point.X(), 4+math.pi/2, places=12)
            self.assertAlmostEqual(point.Y(), 5., places=12)
            self.assertAlmostEqual(point.Z(), 6., places=12)
            changed = replace(curve, origin=a.Vec3(4.01, 5, 6))
            with self.assertRaises(a.CadQueryConversionError):
                self.convert(replace(source, entities=(changed, *source.entities[1:])))

    def test_extra_turn_wrong_interval_and_broken_topology_are_rejected(self):
        for position, value in [(9, -2 * math.pi), (10, 0.1), (2, N), (12, 1), (13, "intcurve")]:
            source = boundary()
            values = list(source.entities[6].values)
            values[position] = value
            changed = replace(source.entities[6], values=tuple(values))
            with self.subTest(position=position), self.assertRaises(a.CadQueryConversionError):
                self.convert(replace(source, entities=tuple(changed if e.index == 6 else e for e in source.entities)))


class BoundedSurfaceTests(unittest.TestCase):
    def test_bounded_nurbs_face_keeps_public_cube_solid_and_volume(self):
        from pathlib import Path
        source = a.parse_sat_model((Path(__file__).parents[1] / 'corpus/data/ezdxf/cube_sat_700.sat').read_bytes()).as_acis_model()
        plane = next(e for e in source.entities if isinstance(e, a.PlaneSurfaceEntity))
        poles = tuple(plane.origin + plane.u_direction*u + plane.v_direction*v
                      for v in (-1000, 1000) for u in (-1000, 1000))
        surface = a.BSplineSurfaceEntity(plane.raw, plane.pattern, 1, 1, (-1000, 1000), (-1000, 1000),
            (2, 2), (2, 2), 2, 2, poles, (1., 1., 1., 1.), False,
            a.ParameterRange(-900., 900.), a.ParameterRange(-900., 900.), 0.)
        changed = replace(source, entities=tuple(surface if e.index == plane.index else e for e in source.entities))
        converter = a.CadQueryConverter(changed)
        shape, = converter.convert()
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids()), 1)
        self.assertAlmostEqual(shape.Volume(), 777**3, delta=1e-5)
        self.assertEqual(len(converter.bounded_surface_faces), 1)

    def test_rectangular_and_diagonal_trims_keep_area_and_orientation(self):
        for uv, area in [(((.2, .2), (.8, .2), (.8, .8), (.2, .8)), 2.16),
                         (((.2, .2), (.8, .2), (.5, .8)), 1.08)]:
            for reverse in (False, True):
                source = polygon_face(uv)
                face = replace(source.entities[0], reversed=reverse)
                converter = a.CadQueryConverter(source)
                shape = converter._face(face, _Placement(None, 1.))
                self.assertTrue(shape.isValid())
                self.assertAlmostEqual(shape.Area(), area, places=9)
                self.assertAlmostEqual(shape.normalAt().z, -1. if reverse else 1., places=9)
                self.assertEqual(len(shape.Edges()), len(uv))
                self.assertEqual(converter.bounded_surface_faces[0]["uv_bounds"], (.1, .9, .1, .9))
                self.assertLessEqual(converter.pcurve_max_deviation, converter.tolerance)

    def test_finite_chart_survives_native_bridge_and_source_ranges(self):
        source = polygon_face()
        self.assertEqual(source.to_native().to_model(), source)
        for bounds in [(None, .9, .1, None), (0., 1., 0., 1.)]:
            source = polygon_face(bounds=bounds)
            shape = a.CadQueryConverter(source)._face(source.entities[0], _Placement(None, 1.))
            self.assertAlmostEqual(shape.Area(), 2.16, places=9)

    def test_face_trims_outside_saved_uv_are_not_clipped(self):
        source = polygon_face(bounds=(.3, .9, .1, .9))
        with self.assertRaises(a.CadQueryConversionError):
            a.CadQueryConverter(source)._face(source.entities[0], _Placement(None, 1.))

    def test_interior_excursion_cannot_pass_endpoint_only_validation(self):
        from OCP.Geom2d import Geom2d_BezierCurve
        from OCP.TColgp import TColgp_Array1OfPnt2d
        from OCP.gp import gp_Pnt2d
        poles = TColgp_Array1OfPnt2d(1, 3)
        for i, point in enumerate(((.2, .2), (2., .5), (.2, .8)), 1):
            poles.SetValue(i, gp_Pnt2d(*point))
        curve = Geom2d_BezierCurve(poles)
        self.assertGreater(curve.Value(.5).X(), 1.)
        with self.assertRaises(a.CadQueryConversionError) as caught:
            a.CadQueryConverter._check_uv_trim(curve, 0., 1., (0., 1., 0., 1.), 7)
        self.assertEqual(caught.exception.code, "geometry.spline_trim_outside_domain")

    def test_invalid_ranges_are_rejected_in_both_directions(self):
        surface = polygon_face().entities[1]
        for lower, upper in [(-.01, 1.), (0., 1.01), (.5, .5), (.8, .2), (math.nan, 1.), (0., math.inf)]:
            for direction in ("u_range", "v_range"):
                with self.subTest(direction=direction, bounds=(lower, upper)), self.assertRaises(ValueError):
                    replace(surface, **{direction: a.ParameterRange(lower, upper)}).validate()


class SavedPcurveTests(unittest.TestCase):
    def source(self):
        alias = (N, b"\x0b", b"\x0f", "ref", 0, b"\x10", b"\x0b", b"\x0b", b"\x0b", b"\x0b")
        return model([raw(0, "spline-surface", surface_values()),
                      raw(1, "pcurve", pcurve_values()), raw(2, "spline-surface", alias)])

    def test_view_is_bound_to_its_source_surface_and_keeps_raw_record(self):
        source = self.source()
        native = source.to_native()
        view = native.linear_surface_pcurve(1, 2)
        self.assertEqual(view.raw, source.entities[1])
        self.assertEqual(view.support.index, 0)
        self.assertEqual(view.uv_endpoints, ((.2, .2), (.8, .2)))
        self.assertIsInstance(native.resolve_subtype(2).geometry, a.BSplineSurfaceEntity)
        alias = replace(source.entities[2], index=3, values=(N, b"\x0b", b"\x0f", "ref", 2,
                        b"\x10", b"\x0b", b"\x0b", b"\x0b", b"\x0b"))
        wrong = model([*source.entities[:2], raw(2, "spline-surface", surface_values()), alias])
        with self.assertRaisesRegex(a.AcisModelError, "different spline"):
            wrong.to_native().linear_surface_pcurve(1, 3)
        self.assertIsNone(model(source.entities, 22600).to_native().linear_surface_pcurve(1, 2))

    def test_incomplete_extended_and_nonfinite_charts_never_return_a_view(self):
        source = self.source()
        values = source.entities[1].values
        variants = [values[:n] for n in range(len(values))]
        variants.append((*values, 0))
        for position, value in [(9, 1.), (10, 2), (13, math.nan), (17, -1.), (29, .1)]:
            changed = list(values)
            changed[position] = value
            variants.append(tuple(changed))
        for changed in variants:
            entries = (source.entities[0], replace(source.entities[1], values=changed), source.entities[2])
            try:
                view = model(entries).to_native().linear_surface_pcurve(1, 2)
            except a.AcisModelError:
                continue
            self.assertIsNone(view)

    def face_with_saved_pcurves(self):
        source = polygon_face()
        entries = list(source.entities)
        entries[1] = replace(entries[1], raw=raw(1, "spline-surface", surface_values()))
        for coedge in [e for e in entries if isinstance(e, a.CoedgeEntity)]:
            edge = entries[coedge.edge.index]
            curve = entries[edge.curve.index]
            entries[curve.index] = a.BSplineCurveEntity(curve.raw, N, 1, (0., 1.), (2, 2),
                (curve.origin, curve.origin + curve.direction), (1., 1.), None, 0.)
            entries[coedge.index] = replace(coedge, pcurve=R(len(entries)))
            start = (curve.origin.x / 2, curve.origin.y / 3)
            end = ((curve.origin.x + curve.direction.x) / 2, (curve.origin.y + curve.direction.y) / 3)
            entries.append(raw(len(entries), "pcurve", pcurve_values(start, end)))
        return replace(source, entities=tuple(entries))

    def test_saved_trims_construct_the_face_without_projecting_and_detect_wrong_uv(self):
        from unittest.mock import patch
        source = self.face_with_saved_pcurves()
        converter = a.CadQueryConverter(source)
        with patch("OCP.GeomProjLib.GeomProjLib.Curve2d_s", side_effect=AssertionError("unexpected projection")):
            shape = converter._face(source.entities[0], _Placement(None, 1.))
        self.assertTrue(shape.isValid())
        self.assertAlmostEqual(shape.Area(), 2.16, places=9)
        self.assertEqual(len(converter.saved_pcurves), 4)
        self.assertTrue(all(p["max_deviation_mm"] <= p["tolerance_mm"] for p in converter.saved_pcurves))
        bad = list(source.entities[-1].values)
        bad[13] += .01
        changed = replace(source, entities=(*source.entities[:-1], replace(source.entities[-1], values=tuple(bad))))
        with self.assertRaises(a.CadQueryConversionError):
            a.CadQueryConverter(changed)._face(changed.entities[0], _Placement(None, 1.))


if __name__ == "__main__":
    unittest.main()
