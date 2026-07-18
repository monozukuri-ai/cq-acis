from __future__ import annotations

import math
import unittest

from cq_acis import (
    BodyEntity,
    ConeSurfaceEntity,
    CountedString,
    EntityRef,
    EllipseCurveEntity,
    LumpEntity,
    ParameterRange,
    PlaneSurfaceEntity,
    SatGraphError,
    SatParseError,
    TransformEntity,
    Vec3,
    parse_sat_graph,
    parse_sat_model,
    tokenize_record,
)


MODERN_HEADER = (
    "700 0 1 0\n"
    "@4 Test @8 ACIS 7.0 @24 Sat Apr 23 14:32:04 2022\n"
    "1 1e-6 1e-10\n"
)
V400_HEADER = (
    "400 0 1 0\n"
    "4 Test 8 ACIS 4.0 24 Sat Apr 23 14:32:04 2022\n"
    "1 1e-6 1e-10\n"
)
V600_HEADER = (
    "600 0 1 0\n"
    "4 Test 8 ACIS 6.0 24 Sat Apr 23 14:32:04 2022\n"
    "1 1e-6 1e-10\n"
)


class TestRecordTokenizer(unittest.TestCase):
    def test_classify_values_and_preserve_counted_string(self) -> None:
        tokens = tokenize_record("edge $2 -7 1.25 -2e-3 @5 a#b c")
        self.assertEqual(tokens[:5], ("edge", EntityRef(2), -7, 1.25, -0.002))
        self.assertEqual(tokens[5], CountedString("a#b c", 5))

    def test_reject_invalid_negative_reference(self) -> None:
        with self.assertRaisesRegex(SatParseError, "negative SAT reference"):
            parse_sat_graph("105 1 1 0\nbody $-1 $-2 $-1 $-1 #\n")


class TestEntityGraph(unittest.TestCase):
    DATA = (
        MODERN_HEADER
        + "-0 body $-1 42 $-1 $1 $-1 $-1 #\n"
        + "-1 lump $-1 43 $-1 $-1 $-1 $0 #\n"
        + "End-of-ACIS-data\n"
    )

    def test_build_graph_and_resolve_forward_and_back_references(self) -> None:
        graph = parse_sat_graph(self.DATA)
        self.assertEqual(len(graph), 2)
        self.assertEqual(graph.entities[0].entity_id, 42)
        self.assertEqual(graph.entities[0].record.sequence_number, 0)
        self.assertEqual(graph.entities[1].record.sequence_number, 1)
        self.assertEqual(graph.resolve(EntityRef(1)).type_name, "lump")
        self.assertIsNone(graph.resolve(EntityRef(-1)))
        self.assertEqual(graph.referenced_by(1), (graph.entities[0],))

    def test_decode_supported_entities(self) -> None:
        model = parse_sat_model(self.DATA)
        body = model.resolve(0)
        lump = model.resolve(1)
        self.assertIsInstance(body, BodyEntity)
        self.assertIsInstance(lump, LumpEntity)
        assert isinstance(body, BodyEntity)
        assert isinstance(lump, LumpEntity)
        self.assertIs(model.resolve(body.lump), lump)
        self.assertIs(model.resolve(lump.body), body)
        self.assertEqual(model.bodies(), (body,))

    def test_reject_dangling_reference(self) -> None:
        with self.assertRaisesRegex(SatGraphError, "outside"):
            parse_sat_graph("105 1 1 0\nbody $-1 $9 $-1 $-1 #\n")

    def test_reject_non_contiguous_explicit_sequence(self) -> None:
        data = MODERN_HEADER + "-1 body $-1 42 $-1 $-1 $-1 $-1 #\n"
        with self.assertRaisesRegex(SatGraphError, "declares sequence 1"):
            parse_sat_graph(data)


class TestVersionAwareGeometry(unittest.TestCase):
    def test_transform_uses_acis_row_vector_placement(self) -> None:
        model = parse_sat_model(
            "105 1 1 0\n"
            "transform $-1 0 1 0 -1 0 0 0 0 1 10 20 30 2 1 0 0 #\n"
        )
        transform = model.resolve(0)
        self.assertIsInstance(transform, TransformEntity)
        assert isinstance(transform, TransformEntity)
        self.assertEqual(
            transform.transform_vector(Vec3(1.0, 2.0, 3.0)),
            Vec3(-4.0, 2.0, 6.0),
        )
        self.assertEqual(
            transform.transform_point(Vec3(1.0, 2.0, 3.0)),
            Vec3(6.0, 22.0, 36.0),
        )
        self.assertEqual(transform.linear_determinant, 8.0)

    def test_decode_legacy_plane_without_parameter_ranges(self) -> None:
        model = parse_sat_model(
            "105 1 1 0\nplane-surface $-1 0 0 0 0 0 1 1 0 0 0 #\n"
        )
        plane = model.resolve(0)
        self.assertIsInstance(plane, PlaneSurfaceEntity)
        assert isinstance(plane, PlaneSurfaceEntity)
        self.assertEqual(plane.origin, Vec3(0.0, 0.0, 0.0))
        self.assertEqual(plane.v_direction, Vec3(0.0, 1.0, 0.0))
        self.assertIsNone(plane.u_range)
        self.assertIsNone(plane.v_range)

    def test_decode_modern_plane_with_finite_and_infinite_ranges(self) -> None:
        data = (
            MODERN_HEADER
            + "plane-surface $-1 7 $-1 0 0 0 0 0 1 1 0 0 "
            + "forward_v F -1 F 1 I I #\n"
            + "End-of-ACIS-data\n"
        )
        plane = parse_sat_model(data).resolve(0)
        self.assertIsInstance(plane, PlaneSurfaceEntity)
        assert isinstance(plane, PlaneSurfaceEntity)
        self.assertEqual(plane.u_range, ParameterRange(-1.0, 1.0))
        self.assertEqual(plane.v_range, ParameterRange(None, None))

    def test_decode_and_evaluate_legacy_ellipse(self) -> None:
        data = (
            "105 1 1 0\n"
            "ellipse-curve $-1 1 2 3 0 0 1 2 0 0 0.5 #\n"
        )
        ellipse = parse_sat_model(data).resolve(0)
        self.assertIsInstance(ellipse, EllipseCurveEntity)
        assert isinstance(ellipse, EllipseCurveEntity)
        self.assertEqual(ellipse.major_radius, 2.0)
        self.assertEqual(ellipse.minor_radius, 1.0)
        self.assertFalse(ellipse.is_circle())
        self.assertIsNone(ellipse.parameter_range)
        self.assertEqual(ellipse.evaluate(0.0), Vec3(3.0, 2.0, 3.0))
        at_quarter = ellipse.evaluate(math.pi / 2.0)
        self.assertAlmostEqual(at_quarter.x, 1.0)
        self.assertAlmostEqual(at_quarter.y, 3.0)
        self.assertAlmostEqual(at_quarter.z, 3.0)

    def test_decode_legacy_cylinder(self) -> None:
        data = (
            "105 1 1 0\n"
            "cone-surface $-1 0 0 0 0 0 1 2 0 0 1 0 1 0 #\n"
        )
        cylinder = parse_sat_model(data).resolve(0)
        self.assertIsInstance(cylinder, ConeSurfaceEntity)
        assert isinstance(cylinder, ConeSurfaceEntity)
        self.assertTrue(cylinder.is_cylinder())
        self.assertTrue(cylinder.is_circular())
        self.assertEqual(cylinder.reference_radius, 2.0)
        self.assertIsNone(cylinder.apex)
        self.assertEqual(cylinder.evaluate(0.0, 3.0), Vec3(2.0, 0.0, 3.0))

    def test_v400_cone_can_derive_omitted_reference_radius(self) -> None:
        data = (
            V400_HEADER
            + "cone-surface $-1 0 0 0 0 0 1 2 0 0 1 "
            + "I I 0 1 forward I I I I #\n"
            + "End-of-ACIS-data\n"
        )
        cylinder = parse_sat_model(data).resolve(0)
        self.assertIsInstance(cylinder, ConeSurfaceEntity)
        assert isinstance(cylinder, ConeSurfaceEntity)
        self.assertEqual(cylinder.reference_radius, 2.0)
        self.assertEqual(cylinder.profile_range, ParameterRange(None, None))
        self.assertEqual(cylinder.u_range, ParameterRange(None, None))
        self.assertEqual(cylinder.v_range, ParameterRange(None, None))

    def test_decode_and_evaluate_modern_cone(self) -> None:
        data = (
            V600_HEADER
            + "cone-surface $-1 0 0 0 0 0 1 2 0 0 1 "
            + "I I 0.6 0.8 2 forward I I I I #\n"
            + "End-of-ACIS-data\n"
        )
        cone = parse_sat_model(data).resolve(0)
        self.assertIsInstance(cone, ConeSurfaceEntity)
        assert isinstance(cone, ConeSurfaceEntity)
        self.assertFalse(cone.is_cylinder())
        self.assertEqual(cone.radius_at(1.0), 2.6)
        point = cone.evaluate(0.0, 1.0)
        self.assertAlmostEqual(point.x, 2.6)
        self.assertAlmostEqual(point.y, 0.0)
        self.assertAlmostEqual(point.z, 0.8)
        assert cone.apex is not None
        self.assertAlmostEqual(cone.apex.x, 0.0)
        self.assertAlmostEqual(cone.apex.y, 0.0)
        self.assertAlmostEqual(cone.apex.z, -8.0 / 3.0)


if __name__ == "__main__":
    unittest.main()
