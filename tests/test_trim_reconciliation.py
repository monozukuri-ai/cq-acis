"""Independent locus, endpoint-star, and rejection checks for trim clocks."""
from dataclasses import replace
import math
from types import SimpleNamespace
import unittest

import cq_acis as a
from cq_acis.cadquery import _Placement
from cq_acis._supported_curves import deviation, reparameterize_saved_pcurve, spline2d
from cq_acis._tolerant_vertices import endpoint_envelope
from test_m4_topology import raw
from test_tolerant_trims import polygon_face, surface_values
import test_supported_curves as fixtures

N, R = a.NULL_REF, a.EntityRef


def endpoint_source():
    source = polygon_face()
    entries = list(source.entities)
    entries[1] = raw(1, 'spline-surface', surface_values())
    record = fixtures.IntersectionCurveTests().source().entities[1]
    entries[7] = replace(record, index=7)
    entries[5] = raw(5, 'tvertex-vertex', (N, R(4), 1, R(6), -1., .0004000001, .000401, 0))
    entries[6] = replace(entries[6], location=entries[6].location + a.Vec3(0, .0004, 0))
    return replace(source, entities=tuple(entries))


class SavedClockTests(unittest.TestCase):
    def arc(self):
        from OCP.Geom import Geom_Circle, Geom_Plane
        from OCP.gp import gp_Ax2, gp_Ax3, gp_Pnt, gp_Dir, gp_Circ
        source = SimpleNamespace(knots=(0., 1.), poles=((1., 0.), (1., 1.), (0., 1.)),
            weights=(1., math.sqrt(.5), 1.), multiplicities=(3, 3), degree=2)
        pc = spline2d(source, 0., math.pi / 2)
        curve = Geom_Circle(gp_Circ(gp_Ax2(gp_Pnt(), gp_Dir(0, 0, 1)), 1.))
        surface = Geom_Plane(gp_Ax3(gp_Pnt(), gp_Dir(0, 0, 1)))
        return pc, curve, surface

    def test_exact_rational_locus_and_endpoints_survive_new_clock(self):
        pc, curve, surface = self.arc()
        limit = .0001
        self.assertGreater(deviation(curve, pc, surface, 0., math.pi/2), 100*limit)
        result, proof = reparameterize_saved_pcurve(pc, curve, surface, 0., math.pi/2, limit)
        self.assertIsNotNone(proof)
        self.assertLessEqual(proof['max_deviation_mm'], limit)
        self.assertLessEqual(deviation(curve, result, surface, 0., math.pi/2), limit)
        self.assertEqual(pc.NbPoles(), 3)
        old, new = proof['source_knots'], proof['edge_knots']
        for a0, b0, a1, b1 in zip(old, old[1:], new, new[1:]):
            self.assertLess(a1, b1)
            for f in (0., .173, .51, .819, 1.):
                original, actual = pc.Value(a0 + f*(b0-a0)), result.Value(a1 + f*(b1-a1))
                self.assertLess(original.Distance(actual), 1e-13)
                self.assertAlmostEqual(actual.X()**2 + actual.Y()**2, 1., places=12)
                self.assertGreaterEqual(actual.X(), -1e-14)
                self.assertGreaterEqual(actual.Y(), -1e-14)
        for t in (0., math.pi/2):
            self.assertLess(pc.Value(t).Distance(result.Value(t)), 1e-14)

    def test_reparameterization_does_not_admit_wrong_locus_or_backtracking(self):
        from OCP.gp import gp_Vec2d
        pc, curve, surface = self.arc()
        shifted = pc.Copy()
        shifted.Translate(gp_Vec2d(.02, .02))
        for source in (shifted, pc.Reversed()):
            unchanged, proof = reparameterize_saved_pcurve(source, curve, surface, 0., math.pi/2, .0001)
            self.assertIsNone(proof)
            self.assertIs(unchanged, source)


class EndpointEnvelopeTests(unittest.TestCase):
    def test_associated_saved_uv_fit_is_independent_of_3d_fit_and_vertex_envelope(self):
        from cq_acis._supported_curves import support_geometry
        original = polygon_face()
        for fit in (.0006, 0.):
            source = endpoint_source()
            entries = list(source.entities)
            entries[5:7] = original.entities[5:7]
            entries[3] = replace(entries[3], pcurve=R(23))
            entries.append(raw(23, 'pcurve', (
                N, 0, fixtures.T, fixtures.OPEN, 'exp_par_cur',
                *fixtures.uv_values(((.2, .2), (.3, .2002), (.7, .2002), (.8, .2))),
                fit, 'spline', fixtures.T, fixtures.OPEN, 'ref', 0, fixtures.CLOSE,
                fixtures.T, fixtures.T, fixtures.T, fixtures.T, fixtures.CLOSE, 0., 0.)))
            c = a.CadQueryConverter(replace(source, entities=tuple(entries)))
            p = _Placement(None, 1.)
            coedges = tuple(entries[i] for i in (3, 8, 13, 18))
            edges = tuple(c._edge(coedge, p) for coedge in coedges)
            geometry = support_geometry(c, c._supported_curves[7].support, p)
            geometry.source_surface = 1
            if fit:
                c._attach_surface_pcurves(edges, geometry, loop_index=2, coedges=coedges, placement=p)
                check, = c.associated_pcurves
                self.assertEqual(check['tolerance_mm'], fit + c.tolerance)
                self.assertLess(check['max_deviation_mm'], fit)
                self.assertEqual(check['source_3d_fit_tolerance_source_units'], .0001)
                self.assertTrue(c.saved_pcurve_reparameterizations)
            else:
                with self.assertRaises(a.CadQueryConversionError) as caught:
                    c._attach_surface_pcurves(edges, geometry, loop_index=2, coedges=coedges, placement=p)
                self.assertEqual(caught.exception.code, 'geometry.pcurve_mismatch')

    def test_source_point_and_curve_are_retained_with_vertex_only_tolerance(self):
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        source = endpoint_source()
        c = a.CadQueryConverter(source)
        # Negative topology lookups must not make an ordinary edge tolerant.
        c._tolerant_view(3, context='test')
        c._tolerant_view(4, context='test')
        shape = c._edge(source.entities[3], _Placement(None, 1.))
        curve = BRepAdaptor_Curve(shape.wrapped)
        self.assertAlmostEqual(curve.Value(0.).Y(), .6, places=13)
        self.assertAlmostEqual(curve.Value(1.).Y(), .6, places=13)
        positions = [tuple(v.Center().toTuple()) for v in shape.Vertices()]
        self.assertTrue(any(math.dist(p, (.4, .6004, 0.)) < 1e-13 for p in positions))
        self.assertLessEqual(BRep_Tool.Tolerance_s(shape.wrapped), c.tolerance)
        self.assertEqual(c.tolerance, 1e-6)
        check, = c.tolerant_vertex_envelopes
        self.assertEqual({e['edge'] for e in check['incident_edges']}, {4, 19})
        self.assertAlmostEqual(check['max_endpoint_deviation_mm'], .0004, places=13)
        self.assertEqual(check['tolerance_mm'], .000401)
        self.assertEqual(source.to_native().to_model(), source)
        self.assertEqual(c.spline_endpoint_failures, [])

    def test_unknown_loose_or_underreported_scalars_do_not_relax_endpoints(self):
        source = endpoint_source()
        for flag, inner, outer in ((0, .0004000001, .000401), (1, .0001, .000101),
                                  (1, .1, .100001), (1, .0004000001, .0005)):
            entries = list(source.entities)
            entries[5] = raw(5, 'tvertex-vertex', (N, R(4), flag, R(6), -1., inner, outer, 0))
            changed = replace(source, entities=tuple(entries))
            with self.subTest(flag=flag, inner=inner, outer=outer), self.assertRaises(a.CadQueryConversionError) as caught:
                a.CadQueryConverter(changed)._edge(changed.entities[3], _Placement(None, 1.))
            self.assertEqual(caught.exception.code, 'geometry.spline_endpoint_mismatch')

    def test_every_incident_edge_and_opposite_point_must_be_checked(self):
        source = endpoint_source()
        for other in (replace(source.entities[22], origin=source.entities[22].origin + a.Vec3(.001, 0, 0)),
                      replace(source.entities[21], location=a.Vec3(.4, .6005, 0))):
            entries = list(source.entities)
            entries[other.index] = other
            c = a.CadQueryConverter(replace(source, entities=tuple(entries)))
            self.assertIsNone(endpoint_envelope(c, R(5), _Placement(None, 1.)))

    def test_vertex_envelope_cannot_expand_curve_fit_or_unrelated_uv_join(self):
        source = endpoint_source()
        c = a.CadQueryConverter(source)
        p = _Placement(None, 1.)
        check = endpoint_envelope(c, R(5), p)
        self.assertIsNotNone(check)
        from cq_acis._supported_curves import support_geometry
        geometry = support_geometry(c, c._supported_curves[7].support, p)
        from cq_acis._supported_curves import validate_fit
        view = c._supported_curves[7]
        off_support = replace(view.curve, poles=tuple(v + a.Vec3(0, 0, .0003) for v in view.curve.poles))
        with self.assertRaises(a.CadQueryConversionError) as caught:
            validate_fit(c, replace(view, curve=off_support), p)
        self.assertEqual(caught.exception.code, 'geometry.supported_curve_fit_mismatch')
        before, after = source.entities[18], source.entities[3]
        c._check_tolerant_join((.2, .2), (.2, .6004/3), before, after, geometry, p, c.tolerance, 2)
        with self.assertRaises(a.CadQueryConversionError):
            c._check_tolerant_join((.2, .2), (.2, .602/3), before, after, geometry, p, c.tolerance, 2)
        with self.assertRaises(a.CadQueryConversionError):
            c._check_tolerant_join((.2, .2), (.2, .6004/3), source.entities[8], after, geometry, p, c.tolerance, 2)


if __name__ == '__main__':
    unittest.main()
