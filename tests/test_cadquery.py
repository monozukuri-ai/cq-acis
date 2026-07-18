from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest

from cq_acis import (
    CadQueryConverter,
    CoedgeEntity,
    ConeSurfaceEntity,
    EdgeEntity,
    EllipseCurveEntity,
    FaceEntity,
    convert_sat_model,
    import_sat_file,
    parse_sat_model,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "corpus" / "data"
CADQUERY_AVAILABLE = importlib.util.find_spec("cadquery") is not None

if CADQUERY_AVAILABLE:
    import cadquery as cq


class TestOptionalCadQueryDependency(unittest.TestCase):
    def test_core_import_is_lazy_and_missing_dependency_is_actionable(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        code = (
            "import sys, cq_acis; "
            "assert 'cadquery' not in sys.modules; "
            "\ntry: cq_acis.import_sat_data('105 0 0 0\\n')"
            "\nexcept cq_acis.CadQueryDependencyError as error: print(error)"
            "\nelse: raise AssertionError('expected CadQueryDependencyError')"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", code],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("install cq-acis[cadquery]", result.stdout)


@unittest.skipUnless(CADQUERY_AVAILABLE, "CadQuery is not installed")
class TestCadQueryConversion(unittest.TestCase):
    def test_cube_v400_and_v700_become_exact_valid_solids(self) -> None:
        for filename in ("cube_sat_400.sat", "cube_sat_700.sat"):
            with self.subTest(filename=filename):
                workplane = import_sat_file(DATA / "ezdxf" / filename)
                self.assertEqual(workplane.size(), 1)
                solid = workplane.val()
                self.assertIsInstance(solid, cq.Solid)
                self.assertTrue(solid.isValid())
                self.assertAlmostEqual(solid.Volume(), 777.0**3, places=6)
                self.assertEqual(len(solid.Faces()), 6)
                self.assertEqual(len(solid.Edges()), 12)
                self.assertEqual(len(solid.Vertices()), 8)
                bounds = solid.BoundingBox()
                self.assertEqual(
                    (
                        bounds.xmin,
                        bounds.xmax,
                        bounds.ymin,
                        bounds.ymax,
                        bounds.zmin,
                        bounds.zmax,
                    ),
                    (0.0, 777.0, 0.0, 777.0, 0.0, 777.0),
                )

    def test_prism_preserves_fixture_topology_and_volume(self) -> None:
        solid = import_sat_file(DATA / "ezdxf" / "prism_sat_700.sat").val()
        self.assertIsInstance(solid, cq.Solid)
        self.assertTrue(solid.isValid())
        self.assertAlmostEqual(solid.Volume(), 20.493389172734968, places=10)
        self.assertEqual(len(solid.Faces()), 10)
        self.assertEqual(len(solid.Edges()), 16)
        self.assertEqual(len(solid.Vertices()), 8)
        self.assertAlmostEqual(solid.BoundingBox().zlen, 2.0)

    def test_full_cylinder_becomes_an_exact_valid_solid(self) -> None:
        path = DATA / "nist" / "boeing_part" / "boeing_part.features.sat"
        model = parse_sat_model(path.read_bytes())
        body = model.resolve(6)
        solid = CadQueryConverter(model).convert_body(body)

        self.assertIsInstance(solid, cq.Solid)
        self.assertTrue(solid.isValid())
        self.assertAlmostEqual(solid.Volume(), math.pi * 0.375**2 * 0.25)
        self.assertEqual(len(solid.Faces()), 3)
        self.assertEqual(len(solid.Edges()), 3)
        self.assertEqual(len(solid.Vertices()), 2)

    def test_non_manifold_acis_shell_splits_into_valid_solids(self) -> None:
        path = DATA / "nist" / "boeing_part" / "boeing_part.features.sat"
        model = parse_sat_model(path.read_bytes())
        body = model.resolve(16)
        shape = CadQueryConverter(model).convert_body(body)

        self.assertIsInstance(shape, cq.Compound)
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids()), 2)
        self.assertEqual(len(shape.Faces()), 10)
        self.assertAlmostEqual(shape.Volume(), 98.44694251222256)
        self.assertTrue(all(solid.isValid() for solid in shape.Solids()))

    def test_every_supported_sat_corpus_body_converts(self) -> None:
        artifacts = 0
        bodies = 0
        manifest = ROOT / "corpus" / "manifest.jsonl"
        for line in manifest.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["format"] != "sat":
                continue
            counts = record["contents"]["entity_type_counts"]
            with self.subTest(record=record["id"]):
                model = parse_sat_model((ROOT / record["path"]).read_bytes())
                shapes = convert_sat_model(model)
                self.assertEqual(len(shapes), counts["body"])
                self.assertTrue(all(shape.isValid() for shape in shapes))
                self.assertTrue(all(shape.Volume() > 0.0 for shape in shapes))
                artifacts += 1
                bodies += len(shapes)
        self.assertEqual(artifacts, 23)
        self.assertEqual(bodies, 147)

    def test_true_ellipse_edge_and_cone_surface_use_analytic_ocp_geometry(self) -> None:
        path = DATA / "nist" / "boeing_part" / "boeing_part.features.sat"
        model = parse_sat_model(path.read_bytes())
        converter = CadQueryConverter(model)
        placement = converter._body_placement(model.bodies()[0])

        ellipse = next(
            entity
            for entity in model.entities
            if isinstance(entity, EllipseCurveEntity)
        )
        edge = next(
            entity
            for entity in model.entities
            if isinstance(entity, EdgeEntity) and entity.curve.index == ellipse.index
        )
        coedge = next(
            entity
            for entity in model.entities
            if isinstance(entity, CoedgeEntity) and entity.edge.index == edge.index
        )
        ellipse_edge = converter._ellipse_edge(
            edge, coedge, replace(ellipse, ratio=0.5), placement
        )
        self.assertTrue(ellipse_edge.isValid())

        cone = next(
            entity
            for entity in model.entities
            if isinstance(entity, ConeSurfaceEntity)
        )
        face = next(
            entity
            for entity in model.entities
            if isinstance(entity, FaceEntity) and entity.surface.index == cone.index
        )
        geometry = converter._cone_geometry(
            face,
            replace(cone, sin_half_angle=0.5, cos_half_angle=math.sqrt(0.75)),
            placement,
        )
        self.assertIsNotNone(geometry.surface)


if __name__ == "__main__":
    unittest.main()
