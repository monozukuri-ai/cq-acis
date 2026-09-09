from __future__ import annotations

from dataclasses import replace
import importlib.util
import math
from typing import get_type_hints
import unittest

from cq_acis import (
    AcisContainer,
    AcisDiagnostic,
    AcisMetadata,
    AcisModel,
    AcisModelError,
    BodyEntity,
    CadQueryConversionError,
    CadQueryConverter,
    CoedgeEntity,
    EdgeEntity,
    EntityRef,
    FaceEntity,
    LoopEntity,
    LumpEntity,
    NULL_REF,
    PlaneSurfaceEntity,
    PointEntity,
    RawEntity,
    SatGraphError,
    SatModel,
    ShellEntity,
    SourceSpan,
    StraightCurveEntity,
    Vec3,
    VertexEntity,
    convert_model,
    convert_sat_model,
    parse_sat_model,
    to_cadquery,
)


def tetrahedron_model(units_mm: float = 1.0) -> AcisModel:
    """Synthetic decoded geometry, built without SAT records or a SAT parser.

    Four outward-oriented triangles bound a unit tetrahedron. The raw producer
    IDs differ from model indices to exercise the adapter's identity boundary.
    This fixture does not claim that any ASM bytes have been decoded.
    """
    points = (Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(0, 0, 1))
    faces = ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))
    pairs = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    pair_indices = {pair: i for i, pair in enumerate(pairs)}
    coedges_by_edge: dict[int, list[int]] = {i: [] for i in range(6)}
    for f, vertices in enumerate(faces):
        for j, start in enumerate(vertices):
            end = vertices[(j + 1) % 3]
            coedges_by_edge[pair_indices[tuple(sorted((start, end)))]].append(
                35 + f * 3 + j
            )

    def raw(index: int, kind: str) -> RawEntity:
        return RawEntity(index, kind, NULL_REF, 1000 + index)

    entities = [
        BodyEntity(raw(0, "body"), NULL_REF, EntityRef(1), NULL_REF, NULL_REF),
        LumpEntity(raw(1, "lump"), NULL_REF, NULL_REF, EntityRef(2), EntityRef(0)),
        ShellEntity(
            raw(2, "shell"), NULL_REF, NULL_REF, NULL_REF,
            EntityRef(11), NULL_REF, EntityRef(1),
        ),
    ]
    for i, point in enumerate(points):
        entities.append(PointEntity(raw(3 + i, "point"), NULL_REF, point))
    for i in range(4):
        edge = next(j for j, pair in enumerate(pairs) if i in pair)
        entities.append(VertexEntity(
            raw(7 + i, "vertex"), NULL_REF, EntityRef(23 + edge), EntityRef(3 + i)
        ))
    for f in range(4):
        entities.append(FaceEntity(
            raw(11 + f, "face"), NULL_REF,
            EntityRef(12 + f) if f < 3 else NULL_REF,
            EntityRef(15 + f), EntityRef(2), NULL_REF, EntityRef(19 + f),
            False, False, None,
        ))
    for f in range(4):
        entities.append(LoopEntity(
            raw(15 + f, "loop"), NULL_REF, NULL_REF,
            EntityRef(35 + f * 3), EntityRef(11 + f),
        ))
    for f, (a, b, c) in enumerate(faces):
        u = (points[b] - points[a]).normalized()
        normal = u.cross(points[c] - points[a]).normalized()
        entities.append(PlaneSurfaceEntity(
            raw(19 + f, "plane-surface"), NULL_REF,
            points[a], normal, u, False, None, None,
        ))
    for i, (a, b) in enumerate(pairs):
        entities.append(EdgeEntity(
            raw(23 + i, "edge"), NULL_REF,
            EntityRef(7 + a), None, EntityRef(7 + b), None,
            EntityRef(coedges_by_edge[i][0]), EntityRef(29 + i), False, None,
        ))
    for i, (a, b) in enumerate(pairs):
        entities.append(StraightCurveEntity(
            raw(29 + i, "straight-curve"), NULL_REF,
            points[a], (points[b] - points[a]).normalized(), None,
        ))
    for f, vertices in enumerate(faces):
        for j, start in enumerate(vertices):
            end = vertices[(j + 1) % 3]
            edge = pair_indices[tuple(sorted((start, end)))]
            index = 35 + f * 3 + j
            partner = next(k for k in coedges_by_edge[edge] if k != index)
            entities.append(CoedgeEntity(
                raw(index, "coedge"), NULL_REF,
                EntityRef(35 + f * 3 + (j + 1) % 3),
                EntityRef(35 + f * 3 + (j - 1) % 3),
                EntityRef(partner), EntityRef(23 + edge), start > end,
                EntityRef(15 + f), NULL_REF,
            ))
    return AcisModel(
        metadata=AcisMetadata(
            units_mm=units_mm, resabs=1e-7, resnor=1e-10,
            product_id="Synthetic external adapter",
        ),
        entities=tuple(entities),
    )


class TestSharedModel(unittest.TestCase):
    def test_binary_source_and_unsupported_entity_survive_without_sat_objects(self):
        span = SourceSpan("part.ipt:RSeStorage/segment:inflated", 64, 68)
        raw = RawEntity(
            0, "vendor-curve", NULL_REF, 725,
            source=span, raw_data=b"\x00\xff\x01\x02",
        )
        diagnostic = AcisDiagnostic(
            "geometry.unsupported", "Unsupported vendor curve", 0, span
        )
        metadata = AcisMetadata(
            container=AcisContainer.ASM_SAB, save_version=23200,
            product_id="Test producer", dialect="unverified-test-dialect",
        )
        model = AcisModel(metadata, (raw,), (diagnostic,))
        self.assertIs(model.resolve(EntityRef(0)), raw)
        self.assertIsNone(raw.record)
        self.assertEqual(raw.raw_data, b"\x00\xff\x01\x02")
        self.assertEqual(raw.entity_id, 725)
        self.assertIs(raw.source, span)
        self.assertIsNone(model.metadata.units_mm)
        self.assertEqual(model.diagnostics, (diagnostic,))
        self.assertFalse(hasattr(model, "graph"))
        self.assertIsNone(model.resolve(NULL_REF))

    def test_legacy_sat_constructor_graph_and_missing_metadata_are_preserved(self):
        parsed = parse_sat_model("105 1 0 0\npoint $-1 1 2 3 #\n")
        model = SatModel(parsed.graph, parsed.entities)
        self.assertIsInstance(model, SatModel)
        self.assertIs(model.graph, parsed.graph)
        self.assertIs(replace(model, entities=parsed.entities).graph, parsed.graph)
        shared = model.as_acis_model()
        self.assertIsInstance(shared, AcisModel)
        self.assertIs(shared.entities, parsed.entities)
        self.assertIs(shared.resolve(0).raw.record, parsed.graph.entities[0].record)
        self.assertEqual(shared.metadata.save_version, 105)
        self.assertEqual(shared.metadata.container, AcisContainer.SAT)
        self.assertIsNone(shared.metadata.units_mm)
        self.assertIsNone(shared.metadata.resabs)
        with self.assertRaises(SatGraphError):
            model.resolve(99)

    def test_shared_view_preserves_sat_header_source_facts(self):
        model = parse_sat_model(
            "700 0 0 0\n@4 Test @8 ACIS 7.0 @4 date\n25.4 1e-7 1e-10\n"
        )
        shared = model.as_acis_model()
        self.assertEqual(shared.metadata, AcisMetadata(
            units_mm=25.4, resabs=1e-7, resnor=1e-10,
            container=AcisContainer.SAT, save_version=700,
            product_id="Test", modeler_version="ACIS 7.0", creation_date="date",
        ))

    def test_old_module_imports_refer_to_the_same_shared_types(self):
        from cq_acis import entities, graph, model, sat, tokens

        self.assertIs(entities.BodyEntity, model.BodyEntity)
        self.assertIs(graph.RawEntity, model.RawEntity)
        self.assertIs(tokens.EntityRef, model.EntityRef)
        self.assertIs(sat.AcisContainer, model.AcisContainer)
        self.assertIs(sat.SatRecord, model.SatRecord)
        self.assertEqual(get_type_hints(RawEntity)["record"], sat.SatRecord | None)

    def test_adapter_must_remap_sparse_source_ids_and_close_references(self):
        metadata = AcisMetadata()
        examples = (
            (RawEntity(7, "unknown", NULL_REF, 7),),
            (RawEntity(0, "unknown", EntityRef(1), 7),),
            (RawEntity(0, "unknown", NULL_REF, 7, (EntityRef(1),)),),
            (BodyEntity(
                RawEntity(0, "body", NULL_REF, 7), NULL_REF,
                EntityRef(1), NULL_REF, NULL_REF,
            ),),
        )
        for entities in examples:
            with self.subTest(entities=entities), self.assertRaises(AcisModelError):
                AcisModel(metadata, entities)
        model = tetrahedron_model()
        for index in (-2, len(model), True, 1.5):
            with self.subTest(index=index), self.assertRaises(AcisModelError):
                model.resolve(index)

    def test_source_span_requires_a_domain_and_ordered_bounds(self):
        for args in (("", 0, 1), ("inflated", -1, 2), ("inflated", 4, 2)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                SourceSpan(*args)


@unittest.skipUnless(importlib.util.find_spec("cadquery"), "CadQuery is not installed")
class TestSharedModelConversion(unittest.TestCase):
    def test_undecoded_body_cannot_silently_become_an_empty_result(self):
        model = AcisModel(
            AcisMetadata(units_mm=1.0, resabs=1e-6),
            (RawEntity(0, "body", NULL_REF, 321, raw_data=b"\xff"),),
        )
        with self.assertRaisesRegex(CadQueryConversionError, "not been decoded"):
            convert_model(model)

    def test_record_free_tetrahedron_has_expected_geometry_and_units(self):
        for scale in (1.0, 25.4):
            with self.subTest(scale=scale):
                model = tetrahedron_model(scale)
                self.assertTrue(all(e.raw.record is None for e in model.entities))
                self.assertFalse(hasattr(model, "graph"))
                converter = CadQueryConverter(model)
                self.assertAlmostEqual(converter.tolerance, 1e-7 * scale)
                for shapes in (
                    converter.convert(), convert_model(model),
                    convert_sat_model(model), tuple(to_cadquery(model).vals()),
                ):
                    self.assertEqual(len(shapes), 1)
                    shape = shapes[0]
                    self.assertTrue(shape.isValid())
                    self.assertEqual(len(shape.Faces()), 4)
                    self.assertEqual(len(shape.Edges()), 6)
                    self.assertEqual(len(shape.Vertices()), 4)
                    self.assertAlmostEqual(shape.Volume(), scale**3 / 6, places=7)
                    self.assertAlmostEqual(
                        shape.Area(), (3 + math.sqrt(3)) * scale**2 / 2, places=7
                    )
                    bounds = shape.BoundingBox()
                    for length in (bounds.xlen, bounds.ylen, bounds.zlen):
                        self.assertAlmostEqual(length, scale)

    def test_unsupported_surface_is_retained_and_blocks_exact_conversion(self):
        model = tetrahedron_model()
        entities = list(model.entities)
        original = entities[19].raw
        unsupported = replace(original, type_name="vendor-surface", raw_data=b"\xff")
        entities[19] = unsupported
        diagnostic = AcisDiagnostic("geometry.unsupported", "Unknown surface", 19)
        model = replace(model, entities=tuple(entities), diagnostics=(diagnostic,))
        with self.assertRaisesRegex(CadQueryConversionError, "vendor-surface"):
            convert_model(model)
        self.assertIs(model.resolve(19), unsupported)
        self.assertEqual(model.diagnostics, (diagnostic,))


if __name__ == "__main__":
    unittest.main()
