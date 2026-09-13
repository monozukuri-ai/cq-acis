"""Independent analytic and rejection oracles for associated ASM curves."""

from dataclasses import fields, replace
import math
import struct
import unittest

import cq_acis as a
from cq_acis.cadquery import _Placement
from cq_acis._supported_curves import (
    support_geometry,
    spline2d,
    validate_fit,
    rational_plane_parameterization,
    deviation,
)
from test_m4_topology import model, raw
from test_tolerant_trims import polygon_face, surface_values

N, R = a.NULL_REF, a.EntityRef
T, F, OPEN, CLOSE = b"\x0b", b"\x0a", b"\x0f", b"\x10"


def vector(tag, *xyz):
    return bytes([tag]) + struct.pack("<ddd", *xyz)


def plane(origin=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0), u=(2.54, 0.0, 0.0)):
    return (
        "plane",
        vector(19, *origin),
        vector(20, *normal),
        vector(20, *u),
        T,
        T,
        T,
        T,
        T,
    )


def linear_poles(start, end):
    return tuple(
        tuple(x + t * (y - x) for x, y in zip(start, end))
        for t in (0.0, 1 / 3, 2 / 3, 1.0)
    )


def uv_values(poles, degree=3, weights=None):
    return (
        "nurbs" if weights else "nubs",
        degree,
        0,
        2,
        0.0,
        degree,
        1.0,
        degree,
        *(x for i, p in enumerate(poles) for x in ((*p, weights[i]) if weights else p)),
    )


def curve_values(poles, uv, support, fit=0.0, secondary=None):
    kind = "int_int_cur" if secondary is not None else "par_int_cur"
    return (
        T,
        OPEN,
        kind,
        22601,
        0,
        "nubs",
        3,
        0,
        2,
        0.0,
        3,
        1.0,
        3,
        *(x for p in poles for x in p),
        fit,
        *support,
        *(secondary if secondary is not None else ("null_surface",)),
        *uv,
        "nullbs",
        T,
        T,
        0,
        0,
        0,
        0,
        *((F, T) if secondary is None else ()),
        CLOSE,
        T,
        T,
    )


def inline_raw(poles=None, uv=None, support=None, fit=0.0):
    poles = poles or linear_poles((0.4, 0.6, 0.0), (1.6, 0.6, 0.0))
    uv = uv or uv_values(
        linear_poles((0.4 / 2.54, 0.6 / 2.54), (1.6 / 2.54, 0.6 / 2.54))
    )
    return raw(
        3,
        "tcoedge-coedge",
        (
            N,
            R(8),
            R(18),
            N,
            R(4),
            T,
            R(2),
            0,
            N,
            0.0,
            1.0,
            N,
            1,
            "intcurve",
            *curve_values(poles, uv, support or plane(), fit),
            0,
        ),
    )


def standalone(record):
    return replace(
        record,
        index=0,
        values=tuple(N if isinstance(v, a.EntityRef) else v for v in record.values),
    )


def planar_face(*, shared_gap=0.0, fit=0.0, allowance=0.001):
    source = polygon_face()
    entries = list(source.entities)
    entries[1] = a.PlaneSurfaceEntity(
        raw(1, "plane-surface"),
        N,
        a.Vec3(0, 0, 0),
        a.Vec3(0, 0, 1),
        a.Vec3(2.54, 0, 0),
        False,
        None,
        None,
    )
    entries[3] = inline_raw(
        poles=linear_poles((0.4, 0.6, fit), (1.6, 0.6, fit)), fit=fit
    )
    e = entries[4]
    entries[4] = raw(
        4,
        "tedge-edge",
        (
            N,
            e.start_vertex,
            0.0,
            e.end_vertex,
            1.0,
            R(3),
            e.curve,
            T,
            "tangent",
            allowance,
            22601,
            0,
        ),
    )
    for i in (5, 10):
        v = entries[i]
        entries[i] = raw(
            i, "tvertex-vertex", (N, v.edge, 1, v.point, -1.0, 100.0, 200.0, 0)
        )
    # Translate the shared source line and its source vertices, independently
    # of the inline fit. Other edges remain their original saved curves.
    entries[7] = replace(
        entries[7], origin=entries[7].origin + a.Vec3(0, 0, shared_gap)
    )
    for i in (6, 11):
        entries[i] = replace(
            entries[i], location=entries[i].location + a.Vec3(0, 0, shared_gap)
        )
    return replace(source, entities=tuple(entries))


class InlineCurveTests(unittest.TestCase):
    def test_planar_hole_orientation_keeps_all_source_edges(self):
        source = planar_face()
        hole = polygon_face(uv=((0.3, 0.3), (0.4, 0.3), (0.4, 0.4), (0.3, 0.4)))

        def ref(r):
            return R(r.index + 23) if r.index >= 2 else r

        additional = []
        for entity in hole.entities[2:]:
            changes = {
                f.name: ref(getattr(entity, f.name))
                for f in fields(entity)
                if isinstance(getattr(entity, f.name), a.EntityRef)
            }
            changes["raw"] = replace(entity.raw, index=entity.index + 23)
            additional.append(replace(entity, **changes))
        entries = list(source.entities)
        entries[2] = replace(entries[2], next_loop=R(25))
        entries.extend((raw(23, "unused"), raw(24, "unused"), *additional))
        source = replace(source, entities=tuple(entries))
        c = a.CadQueryConverter(source)
        f = c._face(source.entities[0], _Placement(None, 1.0))
        self.assertTrue(f.isValid())
        self.assertEqual(len(f.Edges()), 8)
        self.assertEqual(len(f.Wires()), 2)
        self.assertAlmostEqual(f.Area(), 2.10, places=10)
        self.assertEqual(c.plane_wire_orientations, [dict(face=0, loops=[2, 25])])

    def test_planar_chart_scale_and_both_independent_error_bounds(self):
        source = planar_face(fit=0.0005)
        converter = a.CadQueryConverter(source)
        shape = converter._face(source.entities[0], _Placement(None, 1.0))
        self.assertTrue(shape.isValid())
        self.assertAlmostEqual(shape.Area(), 2.16, places=10)
        view = source.to_native().tolerant_topology(3).inline_curve
        self.assertEqual(view.curve.raw, source.entities[3])
        self.assertEqual(view.value_start, 14)
        self.assertEqual(view.value_end, len(source.entities[3].values) - 1)
        self.assertEqual(view.support.u_direction, a.Vec3(2.54, 0, 0))
        (check,) = converter.supported_curve_checks
        self.assertAlmostEqual(check["max_deviation_mm"], 0.0005, places=12)
        self.assertLess(check["shared_edge_max_deviation_mm"], 1e-12)
        self.assertEqual(converter.tolerance, 1e-6)
        self.assertEqual(source.to_native().to_model(), source)

    def test_inline_fit_never_replaces_shared_geometry_or_edge_allowance(self):
        from OCP.BRepAdaptor import BRepAdaptor_Curve

        source = planar_face(shared_gap=0.0004, fit=0.002, allowance=0.0005)
        converter = a.CadQueryConverter(source)
        co = converter._require(3, a.CoedgeEntity, context="test")
        shape = converter._edge(co, _Placement(None, 1.0))
        curve = BRepAdaptor_Curve(shape.wrapped)
        for t in (0.0, 0.13, 0.51, 1.0):
            self.assertAlmostEqual(
                curve.Value(
                    curve.FirstParameter()
                    + t * (curve.LastParameter() - curve.FirstParameter())
                ).Z(),
                0.0004,
                places=12,
            )
        bad = planar_face(shared_gap=0.0004, fit=0.1, allowance=0.0001)
        c = a.CadQueryConverter(bad)
        with self.assertRaises(a.CadQueryConversionError) as caught:
            c._edge(
                c._require(3, a.CoedgeEntity, context="test"), _Placement(None, 1.0)
            )
        self.assertEqual(caught.exception.code, "geometry.inline_edge_mismatch")

    def test_underreported_fit_and_wrong_support_are_rejected(self):
        source = planar_face(fit=0.0005)
        native = source.to_native()
        view = native.tolerant_topology(3).inline_curve
        c = a.CadQueryConverter(source)
        with self.assertRaises(a.CadQueryConversionError) as caught:
            validate_fit(
                c,
                replace(view, curve=replace(view.curve, fit_tolerance=0.0)),
                _Placement(None, 1.0),
            )
        self.assertEqual(caught.exception.code, "geometry.supported_curve_fit_mismatch")
        face_surface = replace(source.entities[1], u_direction=a.Vec3(1, 0, 0))
        source = replace(
            source, entities=(source.entities[0], face_surface, *source.entities[2:])
        )
        with self.assertRaises(a.CadQueryConversionError) as caught:
            a.CadQueryConverter(source)._face(source.entities[0], _Placement(None, 1.0))
        self.assertEqual(caught.exception.code, "geometry.inline_support_mismatch")

    def test_sphere_and_torus_saved_angle_order_has_trigonometric_oracle(self):
        k = 4 / 3 * math.tan(math.pi / 8)
        for torus in (False, True):
            radius = 3.0 if torus else 1.0
            support = (
                (
                    "torus",
                    vector(19, 0, 0, 0),
                    vector(20, 0, 0, 1),
                    2.0,
                    1.0,
                    vector(20, 1, 0, 0),
                )
                if torus
                else (
                    "sphere",
                    vector(19, 0, 0, 0),
                    1.0,
                    vector(20, 1, 0, 0),
                    vector(20, 0, 0, 1),
                )
            )
            poles = (
                (radius, 0.0, 0.0),
                (radius, k * radius, 0.0),
                (k * radius, radius, 0.0),
                (0.0, radius, 0.0),
            )
            record = standalone(
                inline_raw(
                    poles,
                    uv_values(linear_poles((0.0, 0.0), (0.0, math.pi / 2))),
                    (*support, T, T, T, T, T),
                    fit=0.01 * radius,
                )
            )
            source = model([record])
            c = a.CadQueryConverter(source)
            v = source.to_native().tolerant_topology(0).inline_curve
            geometry = support_geometry(c, v.support, _Placement(None, 1.0))
            pc = spline2d(
                v.pcurve, 0.0, 1.0, scale=geometry.uv_scale, swap=geometry.uv_swap
            )
            check = validate_fit(c, v, _Placement(None, 1.0))
            sampled = 0.0
            for t in (0.0, 0.17, 0.5, 0.83, 1.0):
                uv = pc.Value(t)
                point = geometry.surface.Value(uv.X(), uv.Y())
                expected = a.Vec3(
                    radius * math.cos(t * math.pi / 2),
                    radius * math.sin(t * math.pi / 2),
                    0.0,
                )
                self.assertLess(
                    (a.Vec3(point.X(), point.Y(), point.Z()) - expected).magnitude,
                    1e-12,
                )
                sampled = max(sampled, (v.curve.evaluate(t) - expected).magnitude)
            self.assertLessEqual(sampled, check["max_deviation_mm"] + 1e-10)

    def test_rational_saved_uv_retains_its_exact_circle(self):
        k = 4 / 3 * math.tan(math.pi / 8)
        poles = ((1.0, 0.0, 0.0), (1.0, k, 0.0), (k, 1.0, 0.0), (0.0, 1.0, 0.0))
        record = standalone(
            inline_raw(
                poles,
                uv_values(
                    ((1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), 2, (1.0, math.sqrt(0.5), 1.0)
                ),
                plane(u=(1.0, 0.0, 0.0)),
                fit=0.04,
            )
        )
        source = model([record])
        v = source.to_native().tolerant_topology(0).inline_curve
        pc = spline2d(v.pcurve, 0.0, 1.0)
        for t in (0.0, 0.19, 0.5, 0.71, 1.0):
            p = pc.Value(t)
            self.assertAlmostEqual(math.hypot(p.X(), p.Y()), 1.0, places=12)
        validate_fit(a.CadQueryConverter(source), v, _Placement(None, 1.0))

    def test_rational_conic_parameters_need_a_whole_curve_identity_certificate(self):
        from OCP.Geom import Geom_Ellipse
        from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir

        k = 4 / 3 * math.tan(math.pi / 8)
        record = standalone(
            inline_raw(
                ((2.0, 0.0, 0.0), (2.0, k, 0.0), (2 * k, 1.0, 0.0), (0.0, 1.0, 0.0)),
                uv_values(
                    ((2.0, 0.0), (2.0, 1.0), (0.0, 1.0)), 2, (1.0, math.sqrt(0.5), 1.0)
                ),
                plane(u=(1.0, 0.0, 0.0)),
                fit=0.1,
            )
        )
        source = model([record])
        v = source.to_native().tolerant_topology(0).inline_curve
        c = a.CadQueryConverter(source)
        g = support_geometry(c, v.support, _Placement(None, 1.0))
        curve = Geom_Ellipse(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 2.0, 1.0)
        pc = spline2d(v.pcurve, 0.0, math.pi / 2)
        self.assertGreater(deviation(curve, pc, g.surface, 0.0, math.pi / 2), 0.01)
        new, proof = rational_plane_parameterization(
            pc, curve, g, 0.0, math.pi / 2, c.tolerance
        )
        self.assertIsNotNone(proof)
        self.assertLess(proof["locus_bound_mm"], c.tolerance)
        self.assertLess(deviation(curve, new, g.surface, 0.0, math.pi / 2), 1e-12)
        # Matching endpoints alone cannot qualify the saved interior locus.
        wrong = replace(v.pcurve, poles=((2.0, 0.0), (2.01, 1.0), (0.0, 1.0)))
        for other in (
            spline2d(wrong, 0.0, math.pi / 2),
            spline2d(v.pcurve, 0.0, math.pi / 2, reverse=True),
        ):
            unchanged, proof = rational_plane_parameterization(
                other, curve, g, 0.0, math.pi / 2, c.tolerance
            )
            self.assertIsNone(proof)
            self.assertIs(unchanged, other)

    def test_truncation_unknown_profiles_and_interval_changes_fail_closed(self):
        record = standalone(inline_raw())
        for length in range(len(record.values)):
            with self.subTest(length=length), self.assertRaises(a.AcisModelError):
                model(
                    [replace(record, values=record.values[:length])]
                ).to_native().tolerant_topology(0)
        mutations = [
            (9, 0.1),
            (12, 2),
            (14, F),
            (16, "unknown_cur"),
            (17, 22600),
            (20, 2),
            (22, 2**63),
            (24, 4),
            (40, float("nan")),
        ]
        for position, value in mutations:
            values = list(record.values)
            values[position] = value
            with self.subTest(position=position), self.assertRaises(a.AcisModelError):
                model(
                    [replace(record, values=tuple(values))]
                ).to_native().tolerant_topology(0)
        with self.assertRaises(a.AcisModelError):
            model(
                [replace(record, values=(*record.values, 0))]
            ).to_native().tolerant_topology(0)
        self.assertIsNone(model([record], 22600).to_native().tolerant_topology(0))


class TolerantPointTests(unittest.TestCase):
    def line(self, end=a.Vec3(1.5, 0.6, 0.0)):
        source = polygon_face()
        entries = list(source.entities)
        vertex = entries[10]
        entries[10] = raw(
            10, "tvertex-vertex", (N, R(4), 1, vertex.point, -1.0, 100.0, 200.0, 0)
        )
        entries[11] = replace(entries[11], location=end)
        return replace(source, entities=tuple(entries))

    def test_line_trim_uses_source_points_inside_both_saved_intervals(self):
        from OCP.BRepAdaptor import BRepAdaptor_Curve

        source = self.line()
        c = a.CadQueryConverter(source)
        shape = c._edge(source.entities[3], _Placement(None, 1.0))
        ad = BRepAdaptor_Curve(shape.wrapped)
        self.assertAlmostEqual(shape.Length(), 1.1, places=12)
        self.assertAlmostEqual(ad.Value(ad.LastParameter()).X(), 1.5, places=12)
        self.assertEqual(source.entities[4].end_parameter, 1.0)
        self.assertEqual(c.tolerant_line_trims[0]["saved_interval"], (0.0, 1.0))
        self.assertAlmostEqual(
            c.tolerant_line_trims[0]["vertex_interval"][1], 11 / 12, places=12
        )

    def test_line_never_projects_off_locus_or_extrapolates_to_tolerant_point(self):
        for end in (a.Vec3(1.5, 0.601, 0.0), a.Vec3(1.7, 0.6, 0.0)):
            source = self.line(end)
            with self.assertRaises(a.CadQueryConversionError):
                a.CadQueryConverter(source)._edge(
                    source.entities[3], _Placement(None, 1.0)
                )
        source = self.line()
        curve = replace(source.entities[7], parameter_range=a.ParameterRange(0.0, 0.8))
        source = replace(
            source, entities=(*source.entities[:7], curve, *source.entities[8:])
        )
        with self.assertRaises(a.CadQueryConversionError):
            a.CadQueryConverter(source)._edge(source.entities[3], _Placement(None, 1.0))

    def test_uv_gap_requires_shared_source_vertex_and_checked_local_bound(self):
        source = planar_face()
        c = a.CadQueryConverter(source)
        p = _Placement(None, 1.0)
        g = support_geometry(c, source.entities[1], p)
        before = c._require(3, a.CoedgeEntity, context="test")
        after = source.entities[8]
        c._check_tolerant_join(
            (1.6004, 0.6), (1.6, 0.6), before, after, g, p, 0.0005, 2
        )
        self.assertEqual(c.tolerant_pcurve_joins[0]["vertex"], 10)
        for limit in (c.tolerance, 0.0002):
            with self.assertRaises(a.CadQueryConversionError):
                c._check_tolerant_join(
                    (1.6004, 0.6), (1.6, 0.6), before, after, g, p, limit, 2
                )
        with self.assertRaises(a.CadQueryConversionError):
            c._check_tolerant_join(
                (1.6004, 0.6), (1.6, 0.6), before, source.entities[13], g, p, 0.0005, 2
            )


class IntersectionCurveTests(unittest.TestCase):
    def test_full_intersection_envelope_rejects_truncation_and_wrong_support(self):
        source = self.source()
        owner, record = source.entities
        for length in range(4, len(record.values)):
            with self.subTest(length=length), self.assertRaises(a.AcisModelError):
                model(
                    [owner, replace(record, values=record.values[:length])]
                ).to_native().supported_curve(1)
        values = list(record.values)
        reference_position = values.index("ref") + 1
        for position, value in (
            (reference_position, 99),
            (4, 22600),
            (7, 4),
            (26, -1.0),
        ):
            changed = values.copy()
            changed[position] = value
            with self.subTest(position=position), self.assertRaises(a.AcisModelError):
                model(
                    [owner, replace(record, values=tuple(changed))]
                ).to_native().supported_curve(1)
        with self.assertRaises(a.AcisModelError):
            model(
                [owner, replace(record, values=(*record.values, 0))]
            ).to_native().supported_curve(1)
        self.assertIsNone(model(source.entities, 22600).to_native().supported_curve(1))

    def source(self, secondary_origin=(0.0, 0.6, 0.0)):
        support = ("spline", T, OPEN, "ref", 0, CLOSE, T, T, T, T)
        values = (
            N,
            *curve_values(
                linear_poles((0.4, 0.6, 0.0), (1.6, 0.6, 0.0)),
                uv_values(linear_poles((0.2, 0.2), (0.8, 0.2))),
                support,
                fit=0.0001,
                secondary=plane(secondary_origin, (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)),
            ),
        )
        return model(
            [
                raw(0, "spline-surface", surface_values()),
                raw(1, "intcurve-curve", values),
            ]
        )

    def test_both_supports_and_source_ownership_are_checked(self):
        source = self.source()
        native = source.to_native()
        view = native.supported_curve(1)
        self.assertEqual(view.support_definition.entity_index, 0)
        self.assertEqual(view.curve.raw, source.entities[1])
        self.assertEqual(view.support.raw, source.entities[1])
        self.assertEqual(native.entities, source.entities)
        check = validate_fit(a.CadQueryConverter(source), view, _Placement(None, 1.0))
        self.assertLess(check["max_deviation_mm"], 1e-12)
        self.assertEqual(check["secondary_support_bound_mm"], 0.0)
        changed = self.source((0.0, 0.61, 0.0))
        view = changed.to_native().supported_curve(1)
        with self.assertRaises(a.CadQueryConversionError) as caught:
            validate_fit(a.CadQueryConverter(changed), view, _Placement(None, 1.0))
        self.assertEqual(caught.exception.code, "geometry.supported_curve_fit_mismatch")

    def test_approximate_uv_is_retained_and_only_3d_support_fit_is_admitted(self):
        source = self.source()
        view = source.to_native().supported_curve(1)
        # An independently perturbed saved UV is not a reason to change the
        # stored 3D curve. Both support distances still need full checks.
        changed = replace(
            view,
            pcurve=replace(
                view.pcurve, poles=tuple((u + 0.01, v) for u, v in view.pcurve.poles)
            ),
        )
        check = validate_fit(
            a.CadQueryConverter(source), changed, _Placement(None, 1.0)
        )
        self.assertAlmostEqual(
            check["saved_uv_same_parameter_deviation_mm"], 0.02, places=12
        )
        self.assertLess(check["max_deviation_mm"], 1e-12)
        self.assertEqual(changed.curve, view.curve)
        outside = replace(
            changed,
            curve=replace(
                changed.curve,
                poles=tuple(p + a.Vec3(0, 0, 0.01) for p in changed.curve.poles),
            ),
        )
        with self.assertRaises(a.CadQueryConversionError):
            validate_fit(a.CadQueryConverter(source), outside, _Placement(None, 1.0))


if __name__ == "__main__":
    unittest.main()
