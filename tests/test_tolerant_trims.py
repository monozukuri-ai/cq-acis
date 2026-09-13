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


def cubic_pcurve_values(start=(.2, .2), end=(.8, .2), reverse=False, support_reverse=False):
    # Two independent cubic Bezier segments with an asymmetric knot, both
    # representing UV(t) = start + t*(end-start). Endpoint-only tests cannot
    # establish correct internal knot remapping when the direction is reversed.
    fractions = (0., .1, .2, .3, .3+.7/3, .3+1.4/3, 1.)
    poles = tuple(tuple(a + t*(b-a) for a, b in zip(start, end)) for t in fractions)
    knots = (0., .3, 1.)
    if reverse:
        poles = poles[::-1]
        knots = tuple(-k for k in knots[::-1])
    return (N, 0, b"\x0a" if reverse else b"\x0b", b"\x0f", "exp_par_cur", "nubs", 3, 0, 3,
            *(value for k in knots for value in (k, 3)),
            *(value for p in poles for value in p), 0., "spline",
            b"\x0a" if support_reverse else b"\x0b", b"\x0f", "ref", 0, b"\x10",
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
        with self.assertRaisesRegex(a.AcisModelError, "different spline"):
            wrong.to_native().spline_surface_pcurve(1, 3)
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


class SplinePcurveTests(unittest.TestCase):
    def source(self, reverse=False, support_reverse=False):
        source = SavedPcurveTests().face_with_saved_pcurves()
        entries = list(source.entities)
        for pc in source.entities:
            if isinstance(pc, a.RawEntity) and pc.type_name == "pcurve":
                entries[pc.index] = replace(pc, values=cubic_pcurve_values(
                    pc.values[13:15], pc.values[15:17], reverse, support_reverse))
        return replace(source, entities=tuple(entries))

    def test_cubic_knots_and_independent_senses_keep_uv_and_face_area(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        for reverse in (False, True):
            for support_reverse in (False, True):
                with self.subTest(reverse=reverse, support=support_reverse):
                    source = self.source(reverse, support_reverse)
                    converter = a.CadQueryConverter(source)
                    coedge = source.entities[3]
                    view = source.to_native().spline_surface_pcurve(coedge.pcurve, 1)
                    self.assertEqual(view.raw, source.resolve(coedge.pcurve))
                    self.assertEqual(view.parameter_interval, (0., 1.))
                    self.assertEqual(view.multiplicities, (4, 3, 4))
                    self.assertEqual(view.reversed, reverse)
                    self.assertEqual(view.support_reversed, support_reverse)
                    self.assertIsNone(source.to_native().linear_surface_pcurve(coedge.pcurve, 1))
                    for reverse_3d in (False, True):
                        pc, _ = converter._saved_surface_pcurve(
                            coedge, SimpleNamespace(source_surface=1), 2., 7., reverse_3d)
                        for fraction in (0., .1, .3, .5, .7, .9, 1.):
                            uv = pc.Value(2+5*fraction)
                            self.assertAlmostEqual(uv.X(), .2+.6*(1-fraction if reverse_3d else fraction), places=12)
                            self.assertAlmostEqual(uv.Y(), .2, places=12)
                    with patch("OCP.GeomProjLib.GeomProjLib.Curve2d_s", side_effect=AssertionError("projection")):
                        shape = converter._face(source.entities[0], _Placement(None, 1.))
                    self.assertTrue(shape.isValid())
                    self.assertAlmostEqual(shape.Area(), 2.16, places=9)
                    self.assertEqual(len(converter.saved_pcurves), 4)

    def test_unqualified_and_truncated_splines_never_return_a_view(self):
        source = self.source(True, True)
        original = source.entities[-1]
        values = original.values
        variants = [values[:n] for n in range(len(values))] + [(*values, 0)]
        for pos, value in [(2, b"\x09"), (5, "nurbs"), (6, 2), (7, 1), (8, 10**100),
                           (9, math.nan), (10, 2), (11, 0.), (12, 4), (15, math.inf),
                           (29, -1.), (31, b"\x09"), (34, 99), (42, .1)]:
            changed = list(values)
            changed[pos] = value
            variants.append(tuple(changed))
        for changed in variants:
            with self.subTest(values=changed):
                native = replace(source, entities=(*source.entities[:-1], replace(original, values=changed))).to_native()
                try:
                    view = native.spline_surface_pcurve(original.index, 1)
                except a.AcisModelError:
                    continue
                self.assertIsNone(view)
        self.assertIsNone(replace(source, metadata=replace(source.metadata, save_version=22600))
                          .to_native().spline_surface_pcurve(original.index, 1))

    def test_cubic_interior_excursion_rejects_despite_valid_endpoints(self):
        from types import SimpleNamespace
        source = self.source()
        pc = source.entities[-1]
        values = list(pc.values)
        values[17] = 4.  # Interior U control point, endpoints remain in bounds.
        source = replace(source, entities=(*source.entities[:-1], replace(pc, values=tuple(values))))
        converter = a.CadQueryConverter(source)
        coedge = next(e for e in source.entities if isinstance(e, a.CoedgeEntity) and e.pcurve.index == pc.index)
        curve, _ = converter._saved_surface_pcurve(coedge, SimpleNamespace(source_surface=1), 0., 1., False)
        self.assertGreater(curve.Value(.1).X(), .9)
        with self.assertRaises(a.CadQueryConversionError) as caught:
            converter._check_uv_trim(curve, 0., 1., (.1, .9, .1, .9), 2)
        self.assertEqual(caught.exception.code, "geometry.spline_trim_outside_domain")

    def test_inconsistent_curve_sense_cannot_reuse_the_saved_interval(self):
        source = self.source()
        values = list(source.entities[23].values)
        values[2] = b"\x0a"
        source = replace(source, entities=tuple(replace(e, values=tuple(values)) if e.index == 23 else e
                                                for e in source.entities))
        with self.assertRaises(a.CadQueryConversionError) as caught:
            a.CadQueryConverter(source)._face(source.entities[0], _Placement(None, 1.))
        self.assertEqual(caught.exception.code, "geometry.saved_pcurve_parameter_mismatch")


class SavedEdgeToleranceTests(unittest.TestCase):
    def source(self, gap=.001, allowance=.001, units=1.):
        source = SavedPcurveTests().face_with_saved_pcurves()
        entries = list(source.entities)
        for entity in source.entities:
            if isinstance(entity, a.BSplineCurveEntity):
                entries[entity.index] = replace(entity, poles=tuple(p+a.Vec3(0, 0, gap) for p in entity.poles))
            elif isinstance(entity, a.PointEntity):
                entries[entity.index] = replace(entity, location=entity.location+a.Vec3(0, 0, gap))
            elif isinstance(entity, a.EdgeEntity):
                entries[entity.index] = raw(entity.index, "tedge-edge", (N, entity.start_vertex, 0.,
                    entity.end_vertex, 1., entity.coedge, entity.curve, b"\x0b", "tangent", allowance, 22601, 0))
            elif isinstance(entity, a.CoedgeEntity):
                entries[entity.index] = raw(entity.index, "tcoedge-coedge", (N, entity.next_coedge,
                    entity.previous_coedge, entity.partner_coedge, entity.edge, b"\x0b", entity.loop,
                    0, entity.pcurve, 0., 1., N, 0, "null_curve", 0))
        return replace(source, entities=tuple(entries), metadata=replace(source.metadata, units_mm=units))

    def test_local_bound_scales_but_source_curves_vertices_and_model_resolution_stay_fixed(self):
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.BRep import BRep_Tool
        for units in (1., 10.):
            source = self.source(units=units)
            original = source.to_native().to_model()
            converter = a.CadQueryConverter(source)
            shape = converter._face(source.entities[0], _Placement(None, units))
            self.assertTrue(shape.isValid())
            self.assertEqual(source, original)
            self.assertEqual(converter.tolerance, 1e-6*units)
            self.assertEqual(len(converter.source_edge_tolerances), 4)
            self.assertAlmostEqual(shape.Area(), 2.16*units**2, places=7)
            for row in converter.source_edge_tolerances:
                self.assertAlmostEqual(row['limit_mm'], .001001*units, places=12)
                self.assertAlmostEqual(row['max_deviation_mm'], .001*units, places=12)
            for edge in shape.Edges():
                curve = BRepAdaptor_Curve(edge.wrapped)
                for t in (0., .25, .5, .75, 1.):
                    self.assertAlmostEqual(curve.Value(t).Z(), .001*units, places=12)
                self.assertAlmostEqual(BRep_Tool.Tolerance_s(edge.wrapped), .001001*units, places=12)
            for vertex in shape.Vertices():
                self.assertAlmostEqual(vertex.Center().z, .001*units, places=12)

    def test_underreported_edge_bound_or_ordinary_topology_remains_rejected(self):
        ordinary = SavedPcurveTests().face_with_saved_pcurves()
        for variant in ('underreported', 'ordinary_coedge', 'ordinary_edge', 'projected', 'huge_fit'):
            source = self.source(allowance=.0001 if variant in ('underreported', 'huge_fit') else .001)
            entries = list(source.entities)
            if variant in ('ordinary_coedge', 'ordinary_edge'):
                index = 3 if variant == 'ordinary_coedge' else 4
                entries[index] = ordinary.entities[index]
            elif variant == 'projected':
                values = list(entries[3].values)
                values[8] = N
                entries[3] = replace(entries[3], values=tuple(values))
            elif variant == 'huge_fit':
                values = list(entries[23].values)
                values[17] = 100.
                entries[23] = replace(entries[23], values=tuple(values))
            source = replace(source, entities=tuple(entries))
            with self.subTest(variant=variant), self.assertRaises(a.CadQueryConversionError) as caught:
                a.CadQueryConverter(source)._face(source.entities[0], _Placement(None, 1.))
            self.assertEqual(caught.exception.code, 'geometry.pcurve_projection' if variant == 'projected'
                             else 'geometry.pcurve_mismatch')

    def test_large_edge_bound_cannot_expand_finite_uv_domain(self):
        source = self.source(allowance=100.)
        values = list(source.entities[23].values)
        values[13] = 1.1
        source = replace(source, entities=tuple(replace(e, values=tuple(values)) if e.index == 23 else e
                                                for e in source.entities))
        with self.assertRaises(a.CadQueryConversionError) as caught:
            a.CadQueryConverter(source)._face(source.entities[0], _Placement(None, 1.))
        self.assertEqual(caught.exception.code, 'geometry.spline_trim_outside_domain')

    def test_similarity_transform_scales_bound_and_shear_rejects_local_allowance(self):
        transform = a.TransformEntity(raw(27, 'transform'),
            (0., 1., 0., -1., 0., 0., 0., 0., 1., 10., 20., 30.), 3., True, False, False)
        source = self.source(units=10.)
        converter = a.CadQueryConverter(source)
        shape = converter._face(source.entities[0], _Placement(transform, 10.))
        self.assertTrue(shape.isValid())
        self.assertAlmostEqual(shape.Area(), 2.16*30**2, places=6)
        for row in converter.source_edge_tolerances:
            self.assertAlmostEqual(row['scale_to_mm'], 30.)
            self.assertAlmostEqual(row['saved_deviation_mm'], .03)
            self.assertAlmostEqual(row['limit_mm'], .03001)
        shear = replace(transform, matrix_values=(1., 0., 0., .1, 1., 0., 0., 0., 1., 0., 0., 0.), sheared=True)
        with self.assertRaises(a.CadQueryConversionError) as caught:
            a.CadQueryConverter(source)._face(source.entities[0], _Placement(shear, 10.))
        self.assertEqual(caught.exception.code, 'geometry.tolerant_transform_unsupported')

    def test_only_one_original_resolution_is_added_to_the_saved_bound(self):
        for gap, accepted in ((.0010005, True), (.001002, False)):
            source = self.source(gap=gap)
            converter = a.CadQueryConverter(source)
            if accepted:
                self.assertTrue(converter._face(source.entities[0], _Placement(None, 1.)).isValid())
            else:
                with self.assertRaises(a.CadQueryConversionError) as caught:
                    converter._face(source.entities[0], _Placement(None, 1.))
                self.assertEqual(caught.exception.code, 'geometry.pcurve_mismatch')


if __name__ == "__main__":
    unittest.main()
