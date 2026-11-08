"""The OCCT backend: conversion without CadQuery and the bare-OCP shape wrappers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

from cq_acis import (
    BACKENDS,
    CadQueryConverter,
    CadQueryDependencyError,
    convert_model,
    convert_model_occt,
    parse_sab_model,
    parse_sat_model,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "corpus" / "data" / "ezdxf"
OCP_AVAILABLE = importlib.util.find_spec("OCP") is not None
CADQUERY_AVAILABLE = importlib.util.find_spec("cadquery") is not None

if OCP_AVAILABLE:
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeSphere
    from OCP.gp import gp_Pnt
    from OCP.TopoDS import TopoDS_Compound, TopoDS_Shape, TopoDS_Solid

    from cq_acis import _occt_shapes as occt


def cube_models():
    """The public cube fixtures as (name, model) pairs: SAT 700 and ASM 22300."""
    yield "cube_sat_700.sat", parse_sat_model((DATA / "cube_sat_700.sat").read_bytes())
    yield (
        "cube_asm_sab_22300.sab",
        parse_sab_model((DATA / "cube_asm_sab_22300.sab").read_bytes(), source_id="cube.sab"),
    )


class TestBackendSelection(unittest.TestCase):
    def test_unknown_backend_is_rejected_before_any_import(self) -> None:
        _, model = next(cube_models())
        with self.assertRaises(ValueError):
            CadQueryConverter(model, backend="bogus")
        self.assertEqual(BACKENDS, ("auto", "cadquery", "occt"))

    @unittest.skipUnless(OCP_AVAILABLE, "OCP is not installed")
    def test_auto_backend_falls_back_to_occt_when_cadquery_is_missing(self) -> None:
        # Blocking the cadquery import in a child process simulates cq-acis[occt].
        code = (
            "import sys; sys.modules['cadquery'] = None\n"
            "from pathlib import Path\n"
            "from cq_acis import CadQueryConverter, CadQueryDependencyError, convert_model, "
            "parse_sat_model, to_cadquery\n"
            f"model = parse_sat_model(Path({str(DATA / 'cube_sat_700.sat')!r}).read_bytes())\n"
            "converter = CadQueryConverter(model)\n"
            "assert converter.backend == 'occt', converter.backend\n"
            "shapes = convert_model(model)\n"
            "assert len(shapes) == 1 and type(shapes[0]).__module__ == 'cq_acis._occt_shapes'\n"
            "assert shapes[0].wrapped.__class__.__name__ == 'TopoDS_Solid'\n"
            "try:\n"
            "    to_cadquery(model)\n"
            "except CadQueryDependencyError as error:\n"
            "    assert 'cq-acis[cadquery]' in str(error), error\n"
            "else:\n"
            "    raise AssertionError('to_cadquery must require CadQuery')\n"
            "print('fallback ok')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, check=False, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fallback ok", result.stdout)


@unittest.skipUnless(OCP_AVAILABLE, "OCP is not installed")
class TestOcctConversion(unittest.TestCase):
    def test_public_cubes_become_valid_topods_solids(self) -> None:
        for name, model in cube_models():
            with self.subTest(name=name):
                shapes = convert_model_occt(model)
                self.assertEqual(len(shapes), 1)
                self.assertIsInstance(shapes[0], TopoDS_Solid)
                self.assertTrue(BRepCheck_Analyzer(shapes[0]).IsValid())
                solid = occt.Shape.cast(shapes[0])
                self.assertIsInstance(solid, occt.Solid)
                counts = (len(solid.Solids()), len(solid.Faces()), len(solid.Edges()), len(solid.Vertices()))
                self.assertEqual(counts, (1, 6, 12, 8))
                self.assertAlmostEqual(solid.Volume(), 777.0**3, places=3)
                self.assertAlmostEqual(solid.Area(), 6 * 777.0**2, places=3)
                bounds = solid.BoundingBox()
                for length in (bounds.xlen, bounds.ylen, bounds.zlen):
                    self.assertAlmostEqual(length, 777.0, places=6)

    def test_converter_exposes_wrapped_shapes_and_refuses_a_workplane(self) -> None:
        _, model = next(cube_models())
        converter = CadQueryConverter(model, backend="occt")
        self.assertEqual(converter.backend, "occt")
        shapes = converter.convert()
        self.assertEqual(len(shapes), 1)
        self.assertIsInstance(shapes[0], occt.Solid)
        self.assertIsInstance(shapes[0].wrapped, TopoDS_Shape)
        self.assertTrue(shapes[0].isValid())
        with self.assertRaises(CadQueryDependencyError):
            converter.workplane()
        self.assertEqual(convert_model(model, backend="occt")[0].Volume(), shapes[0].Volume())

    @unittest.skipUnless(CADQUERY_AVAILABLE, "CadQuery is not installed")
    def test_occt_and_cadquery_backends_agree(self) -> None:
        for name, model in cube_models():
            with self.subTest(name=name):
                (occt_solid,) = convert_model(model, backend="occt")
                (cq_solid,) = convert_model(model, backend="cadquery")
                self.assertEqual(type(cq_solid).__module__.split(".")[0], "cadquery")
                self.assertAlmostEqual(occt_solid.Volume(), cq_solid.Volume(), places=6)
                self.assertAlmostEqual(occt_solid.Area(), cq_solid.Area(), places=6)
                for accessor in ("Faces", "Edges", "Vertices"):
                    self.assertEqual(
                        len(getattr(occt_solid, accessor)()), len(getattr(cq_solid, accessor)())
                    )
                occt_bounds, cq_bounds = occt_solid.BoundingBox(), cq_solid.BoundingBox()
                for axis in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"):
                    self.assertAlmostEqual(getattr(occt_bounds, axis), getattr(cq_bounds, axis), places=6)
                self.assertEqual(occt_solid.isValid(), cq_solid.isValid())
                # The same OCCT object can be re-wrapped by either backend.
                self.assertIsInstance(occt.Shape.cast(cq_solid.wrapped), occt.Solid)


@unittest.skipUnless(OCP_AVAILABLE, "OCP is not installed")
class TestOcctShapeWrappers(unittest.TestCase):
    """The wrappers mirror the CadQuery methods the converter relies on."""

    def box(self, x: float = 10.0, y: float = 20.0, z: float = 30.0, origin=(0.0, 0.0, 0.0)):
        return occt.Shape.cast(BRepPrimAPI_MakeBox(gp_Pnt(*origin), x, y, z).Shape())

    def test_cast_downcasts_and_reports_the_shape_type(self) -> None:
        box = self.box()
        self.assertIsInstance(box, occt.Solid)
        self.assertIsInstance(box.wrapped, TopoDS_Solid)
        self.assertEqual(box.ShapeType(), "Solid")
        self.assertEqual([face.ShapeType() for face in box.Faces()], ["Face"] * 6)
        self.assertEqual(len(box.Edges()), 12)
        self.assertEqual(len(box.Vertices()), 8)
        self.assertEqual(len(box.Wires()), 6)
        self.assertEqual(len(box.Shells()), 1)
        self.assertEqual(len(box.Solids()), 1)
        self.assertFalse(box.isNull())
        with self.assertRaises(ValueError):
            occt.Shape.cast(TopoDS_Shape())

    def test_edges_leave_out_degenerated_edges_like_cadquery(self) -> None:
        # A full sphere carries one seam edge plus two degenerated pole edges.
        sphere = occt.Shape.cast(BRepPrimAPI_MakeSphere(5.0).Shape())
        self.assertEqual(len(sphere.Faces()), 1)
        self.assertEqual(len(sphere.Faces()[0].Edges()), 1)
        self.assertEqual(len(sphere.Vertices()), 2)
        if CADQUERY_AVAILABLE:
            import cadquery as cq

            self.assertEqual(len(cq.Shape.cast(sphere.wrapped).Edges()), 1)

    def test_mass_properties_bounds_and_vertex_points(self) -> None:
        box = self.box()
        self.assertTrue(box.isValid())
        self.assertAlmostEqual(box.Volume(), 6000.0, places=9)
        self.assertAlmostEqual(box.Area(), 2200.0, places=9)
        self.assertEqual(box.Center().toTuple(), (5.0, 10.0, 15.0))
        bounds = box.BoundingBox()
        self.assertEqual(
            (bounds.xmin, bounds.ymin, bounds.zmin, bounds.xmax, bounds.ymax, bounds.zmax),
            (0.0, 0.0, 0.0, 10.0, 20.0, 30.0),
        )
        self.assertEqual((bounds.xlen, bounds.ylen, bounds.zlen), (10.0, 20.0, 30.0))
        self.assertEqual(bounds.center.toTuple(), (5.0, 10.0, 15.0))
        corners = {vertex.toTuple() for vertex in box.Vertices()}
        self.assertIn((10.0, 20.0, 30.0), corners)
        vertex = box.Vertices()[0]
        self.assertEqual(vertex.Center().toTuple(), vertex.toTuple())
        self.assertIsInstance(box.Faces()[0].Area(), float)
        self.assertIsInstance(box.Shells()[0].Closed(), bool)

    def test_identity_follows_the_underlying_shape(self) -> None:
        box = self.box()
        first, again = box.Faces()[0], occt.Shape.cast(box.wrapped).Faces()[0]
        self.assertEqual(first, again)
        self.assertTrue(first.isSame(again))
        self.assertEqual(hash(first), hash(again))
        self.assertNotEqual(first, box.Faces()[1])
        self.assertNotEqual(first, "not a shape")

    def test_edges_wires_and_planar_faces(self) -> None:
        def square(size: float, origin=(0.0, 0.0)):
            x0, y0 = origin
            points = [(x0, y0, 0.0), (x0 + size, y0, 0.0), (x0 + size, y0 + size, 0.0), (x0, y0 + size, 0.0)]
            edges = [occt.Edge.makeLine(points[i], points[(i + 1) % 4]) for i in range(4)]
            return occt.Wire.assembleEdges(edges)

        edge = occt.Edge.makeLine((0.0, 0.0, 0.0), (3.0, 4.0, 0.0))
        self.assertIsInstance(edge, occt.Edge)
        self.assertFalse(edge.IsClosed())
        outer = square(2.0)
        self.assertIsInstance(outer, occt.Wire)
        self.assertTrue(outer.IsClosed())
        self.assertTrue(outer.isValid())
        face = occt.Face.makeFromWires(outer)
        self.assertIsInstance(face, occt.Face)
        self.assertAlmostEqual(face.Area(), 4.0, places=9)
        holed = occt.Face.makeFromWires(outer, [square(1.0, (0.5, 0.5))])
        self.assertAlmostEqual(holed.Area(), 3.0, places=9)
        self.assertEqual(len(holed.Wires()), 2)
        self.assertTrue(holed.isValid())
        with self.assertRaises(ValueError):
            occt.Wire.assembleEdges([edge, occt.Edge.makeLine((9.0, 9.0, 9.0), (9.0, 9.0, 10.0))])
        skew = occt.Wire.assembleEdges(
            [
                occt.Edge.makeLine((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
                occt.Edge.makeLine((1.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
                occt.Edge.makeLine((1.0, 1.0, 1.0), (0.0, 1.0, 0.0)),
                occt.Edge.makeLine((0.0, 1.0, 0.0), (0.0, 0.0, 0.0)),
            ]
        )
        with self.assertRaises(ValueError):
            occt.Face.makeFromWires(skew)

    def test_shells_solids_cavities_and_compounds(self) -> None:
        box = self.box()
        shell = occt.Shell.makeShell(face for face in box.Faces())
        self.assertEqual(len(shell.Shells()), 1)
        self.assertTrue(shell.isValid())
        solid = occt.Solid.makeSolid(shell.Shells()[0])
        self.assertIsInstance(solid, occt.Solid)
        self.assertTrue(solid.isValid())
        self.assertAlmostEqual(solid.Volume(), 6000.0, places=6)
        self.assertEqual(solid.outerShell().ShapeType(), "Shell")
        hollow = solid.addCavity(self.box(2.0, 2.0, 2.0, origin=(4.0, 9.0, 14.0)))
        self.assertTrue(hollow.isValid())
        self.assertAlmostEqual(hollow.Volume(), 6000.0 - 8.0, places=6)
        self.assertEqual(len(hollow.Shells()), 2)
        compound = occt.Compound.makeCompound([solid, self.box(1.0, 1.0, 1.0, origin=(50.0, 0.0, 0.0))])
        self.assertIsInstance(compound, occt.Compound)
        self.assertIsInstance(compound.wrapped, TopoDS_Compound)
        self.assertEqual(len(compound.Solids()), 2)
        self.assertAlmostEqual(compound.Volume(), 6001.0, places=6)
        self.assertTrue(compound.isValid())


if __name__ == "__main__":
    unittest.main()
