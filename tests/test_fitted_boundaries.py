"""Boundary handling that faces on stored fits rely on: singular points,
full-turn pcurves, and the direction of inner loops on a reversed face."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from cq_acis import CadQueryConverter, parse_sab_model

ROOT = Path(__file__).resolve().parents[1]
CUBE = ROOT / "corpus" / "data" / "ezdxf" / "cube_asm_sab_22300.sab"
OCP_AVAILABLE = importlib.util.find_spec("OCP") is not None


def converter() -> CadQueryConverter:
    return CadQueryConverter(parse_sab_model(CUBE.read_bytes(), source_id=CUBE.name))


@unittest.skipUnless(OCP_AVAILABLE, "needs OCP")
class TestSingularBoundaries(unittest.TestCase):
    def test_pole_segment_is_singular_and_a_regular_segment_is_not(self) -> None:
        from OCP.Geom import Geom_SphericalSurface
        from OCP.gp import gp_Ax3

        sphere = Geom_SphericalSurface(gp_Ax3(), 5.0)
        pole = math.pi / 2
        self.assertTrue(CadQueryConverter._singular_segment(sphere, (0.0, pole), (1.0, pole), 1e-6))
        self.assertFalse(CadQueryConverter._singular_segment(sphere, (0.0, 0.0), (1.0, 0.0), 1e-6))
        # A short regular segment is a gap, not a singular point.
        self.assertFalse(CadQueryConverter._singular_segment(sphere, (0.0, 0.0), (1e-9, 0.0), 1e-6))

    def test_degenerated_edge_carries_only_a_pcurve(self) -> None:
        from OCP.BRep import BRep_Tool
        from OCP.Geom import Geom_SphericalSurface
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Ax3, gp_Pnt

        sphere = Geom_SphericalSurface(gp_Ax3(), 5.0)
        pole = math.pi / 2
        edge = converter()._degenerated_edge(sphere, (0.0, pole), (1.0, pole), gp_Pnt(0, 0, 5), 1e-6).wrapped
        self.assertTrue(BRep_Tool.Degenerated_s(edge))
        self.assertIsNone(BRep_Tool.Curve_s(edge, 0.0, 0.0))
        first, last = BRep_Tool.Range_s(edge)
        pcurve = BRep_Tool.CurveOnSurface_s(edge, sphere, TopLoc_Location(), 0.0, 0.0)
        start, end = pcurve.Value(first), pcurve.Value(last)
        self.assertAlmostEqual(start.X(), 0.0)
        self.assertAlmostEqual(end.X(), 1.0)
        self.assertAlmostEqual(start.Y(), pole)
        self.assertAlmostEqual(end.Y(), pole)


@unittest.skipUnless(OCP_AVAILABLE, "needs OCP")
class TestSampledPcurve(unittest.TestCase):
    def test_full_turn_on_a_periodic_support_covers_the_whole_edge_range(self) -> None:
        from OCP.Geom import Geom_Ellipse, Geom_SurfaceOfLinearExtrusion
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

        ellipse = Geom_Ellipse(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 8.0, 3.0)
        surface = Geom_SurfaceOfLinearExtrusion(ellipse, gp_Dir(0, 0, 1))
        first, last = math.pi, 3 * math.pi  # One full turn that starts off the seam.
        pcurve = CadQueryConverter._sampled_pcurve(
            ellipse, surface, first, last, (2 * math.pi, None), 1e-6)
        self.assertIsNotNone(pcurve)
        self.assertLessEqual(pcurve.FirstParameter(), first)
        self.assertGreaterEqual(pcurve.LastParameter(), last)
        self.assertAlmostEqual(abs(pcurve.Value(last).X() - pcurve.Value(first).X()), 2 * math.pi, places=6)
        for i in range(33):
            t = first + (last - first) * i / 32
            uv = pcurve.Value(t)
            self.assertLess(surface.Value(uv.X(), uv.Y()).Distance(ellipse.Value(t)), 1e-6)


@unittest.skipUnless(OCP_AVAILABLE, "needs OCP")
class TestInnerLoopsOfReversedSplineFace(unittest.TestCase):
    @staticmethod
    def _square_wire(surface, corners):
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex, BRepBuilderAPI_MakeWire
        from OCP.Geom2d import Geom2d_Line
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Dir2d, gp_Pnt, gp_Pnt2d

        vertices = [BRepBuilderAPI_MakeVertex(gp_Pnt(x, y, 0)).Vertex() for x, y in corners]
        wire = BRepBuilderAPI_MakeWire()
        for i, (x0, y0) in enumerate(corners):
            x1, y1 = corners[(i + 1) % len(corners)]
            length = math.hypot(x1 - x0, y1 - y0)
            edge = BRepBuilderAPI_MakeEdge(vertices[i], vertices[(i + 1) % len(corners)]).Edge()
            line = Geom2d_Line(gp_Pnt2d(x0, y0), gp_Dir2d((x1 - x0) / length, (y1 - y0) / length))
            BRep_Builder().UpdateEdge(edge, line, surface, TopLoc_Location(), 1e-7)
            wire.Add(edge)
        return wire.Wire()

    def _face(self, *, reversed_face: bool):
        from OCP.Geom import Geom_BSplineSurface
        from OCP.TColgp import TColgp_Array2OfPnt
        from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
        from OCP.gp import gp_Pnt

        poles = TColgp_Array2OfPnt(1, 2, 1, 2)
        for i, x in enumerate((-10.0, 10.0), 1):
            for j, y in enumerate((-10.0, 10.0), 1):
                poles.SetValue(i, j, gp_Pnt(x, y, 0))
        knots = TColStd_Array1OfReal(1, 2)
        knots.SetValue(1, -10.0)
        knots.SetValue(2, 10.0)
        multiplicities = TColStd_Array1OfInteger(1, 2)
        multiplicities.SetValue(1, 2)
        multiplicities.SetValue(2, 2)
        patch = Geom_BSplineSurface(poles, knots, knots, multiplicities, multiplicities, 1, 1)

        outer = [(-5, -5), (5, -5), (5, 5), (-5, 5)]
        hole = [(-1, -1), (-1, 1), (1, 1), (1, -1)]
        if reversed_face:
            # Source loops of a face reversed against its surface run the other way.
            outer, hole = outer[::-1], hole[::-1]
        conv = converter()
        wires = {1: self._square_wire(patch, outer), 2: self._square_wire(patch, hole)}
        conv._bspline_geometry = lambda surface, placement: patch
        conv._wire = lambda loop, placement, geometry=None: conv.cq.Wire(wires[loop.index])
        surface = SimpleNamespace(index=10**6, reversed=False, u_range=None, v_range=None,
                                  u_knots=(-10.0, 10.0), v_knots=(-10.0, 10.0))
        face = SimpleNamespace(index=1, reversed=reversed_face)
        loops = (SimpleNamespace(index=1), SimpleNamespace(index=2))
        return conv._bspline_face(face, surface, loops, None)

    def test_hole_follows_the_outer_loop_on_a_reversed_face(self) -> None:
        for reversed_face in (False, True):
            with self.subTest(reversed_face=reversed_face):
                result = self._face(reversed_face=reversed_face)
                self.assertTrue(result.isValid())
                self.assertAlmostEqual(result.Area(), 100.0 - 4.0, places=6)


if __name__ == "__main__":
    unittest.main()
