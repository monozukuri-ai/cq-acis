"""Independent stepped-cylinder area and actual shell-incidence regressions."""
from dataclasses import replace
import math
import unittest

import cq_acis as a
from cq_acis.cadquery import _Placement
from test_m4_geometry import raw, cone

N, R = a.NULL_REF, a.EntityRef


def stepped_cylinder(alpha=.2, beta=3., bottom=0., low=4., high=6.):
    """Radius two; upper rim has two horizontal arcs and two vertical steps."""
    surface = cone(major_axis=a.Vec3(2, 0, 0), reference_radius=2,
                   parameter_scale=2, sin_half_angle=0., cos_half_angle=1.)
    entries = [a.FaceEntity(raw(0, 'face'), N, N, R(2), N, N, R(1), False, False, None),
               replace(surface, raw=raw(1, 'cone-surface')), None, None]

    def ring(loop_index, vertices, specs, reverse):
        vertex_refs = []
        for xyz in vertices:
            i = len(entries)
            entries.extend([a.VertexEntity(raw(i, 'vertex'), N, N, R(i+1)),
                            a.PointEntity(raw(i+1, 'point'), N, xyz)])
            vertex_refs.append(R(i))
        coedges = []
        for j, (kind, first, last, z) in enumerate(specs):
            i = len(entries)
            start, end = vertices[j], vertices[(j+1) % len(vertices)]
            if kind == 'circle':
                curve = a.EllipseCurveEntity(raw(i+2, 'ellipse-curve'), N,
                    a.Vec3(0, 0, z), a.Vec3(0, 0, 1), a.Vec3(2, 0, 0), 1., None)
            else:
                curve = a.StraightCurveEntity(raw(i+2, 'straight-curve'), N,
                    start, (end-start).normalized(), None)
                first, last = 0., (end-start).magnitude
            entries.extend([None, a.EdgeEntity(raw(i+1, 'edge'), N,
                vertex_refs[j], first, vertex_refs[(j+1) % len(vertices)], last,
                R(i), R(i+2), False, None), curve])
            coedges.append(i)
        order = coedges[::-1] if reverse else coedges
        for j, i in enumerate(order):
            entries[i] = a.CoedgeEntity(raw(i, 'coedge'), N, R(order[(j+1) % len(order)]),
                R(order[j-1]), N, R(i+1), reverse, R(loop_index), N)
        entries[loop_index] = a.LoopEntity(raw(loop_index, 'loop'), N,
            R(3) if loop_index == 2 else N, R(order[0]), R(0))

    def point(u, z):
        return a.Vec3(2*math.cos(u), 2*math.sin(u), z)

    ring(2, [point(0., bottom)], [('circle', 0., 2*math.pi, bottom)], False)
    ring(3, [point(alpha, low), point(beta, low), point(beta, high), point(alpha, high)],
         [('circle', alpha, beta, low), ('line', 0., 0., 0.),
          ('circle', beta, alpha+2*math.pi, high), ('line', 0., 0., 0.)], True)
    return a.AcisModel(a.AcisMetadata(units_mm=1., resabs=1e-6), tuple(entries))


class CylinderSeamTests(unittest.TestCase):
    def test_step_area_and_all_source_vertices_survive_chart_seam(self):
        from OCP.BRep import BRep_Tool
        for alpha, beta in ((.2, 3.), (-.3, 2.1)):
            source = stepped_cylinder(alpha, beta)
            c = a.CadQueryConverter(source)
            face = c._face(source.entities[0], _Placement(None, 1.))
            expected = 2 * (4*(beta-alpha) + 6*(2*math.pi-beta+alpha))
            self.assertTrue(face.isValid())
            self.assertAlmostEqual(face.Area(), expected, delta=1e-6)
            self.assertEqual(len(c.periodic_seam_faces), 1)
            self.assertEqual(c.periodic_seam_faces[0]['source_edges'], 5)
            self.assertEqual(c.periodic_seam_faces[0]['seam_edges'], 1)
            self.assertEqual(source, source.to_native().to_model())
            for entry in source.entities:
                if isinstance(entry, a.PointEntity):
                    self.assertTrue(any(math.dist(v.toTuple(), (entry.location.x, entry.location.y,
                        entry.location.z)) < c.tolerance for v in face.Vertices()))
            self.assertTrue(all(BRep_Tool.Tolerance_s(e.wrapped) <= math.nextafter(c.tolerance, math.inf)
                                for e in face.Edges()))

    def test_translation_scale_and_loop_order_do_not_change_the_trim(self):
        source = stepped_cylinder()
        entries = list(source.entities)
        entries[0] = replace(entries[0], loop=R(3))
        entries[2] = replace(entries[2], next_loop=N)
        entries[3] = replace(entries[3], next_loop=R(2))
        transform = a.TransformEntity(raw(0, 'transform'),
            (1, 0, 0, 0, 1, 0, 0, 0, 1, 3, 4, 5), 1, False, False, False)
        for model in (source, replace(source, entities=tuple(entries))):
            c = a.CadQueryConverter(model)
            face = c._face(model.entities[0], _Placement(transform, 2.))
            self.assertTrue(face.isValid())
            self.assertAlmostEqual(face.Area(), 8 * (4*2.8 + 6*(2*math.pi-2.8)), delta=1e-6)

    def test_verifier_rejects_changed_trim_orientation_and_support(self):
        from OCP.BRep import BRep_Tool
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeEdge
        from OCP.Geom import Geom_CylindricalSurface
        from cq_acis._analytic_seams import cylinder_seam_face, _check_seam_boundaries
        source = stepped_cylinder()
        c = a.CadQueryConverter(source)
        p = _Placement(None, 1.)
        loops = tuple(source.entities[i] for i in (2, 3))
        geometry = c._cone_geometry(source.entities[0], source.entities[1], p)
        wires = [c._wire(loop, p, geometry) for loop in loops]
        boundaries = [(edge, BRep_Tool.Curve_s(edge.wrapped, 0., 0.),
                       *BRep_Tool.Range_s(edge.wrapped)) for wire in wires for edge in wire.Edges()]
        builder = BRepBuilderAPI_MakeFace(geometry.surface, wires[0].wrapped, True)
        builder.Add(wires[1].wrapped)
        result = cylinder_seam_face(c, source.entities[0], loops, wires, geometry, c.cq.Face(builder.Face()), p)
        edge, curve, first, last = boundaries[0]
        for lo, hi in ((first+.01, last), (first, last-.01)):
            trimmed = c.cq.Edge(BRepBuilderAPI_MakeEdge(curve, lo, hi).Edge())
            trimmed.wrapped.Orientation(edge.wrapped.Orientation())
            with self.assertRaisesRegex(ValueError, 'trim'):
                _check_seam_boundaries(c, result, geometry.surface, [(trimmed, curve, lo, hi), *boundaries[1:]])
        reversed_edge = c.cq.Edge(edge.wrapped.Reversed())
        with self.assertRaisesRegex(ValueError, 'reversed physical boundary'):
            _check_seam_boundaries(c, result, geometry.surface, [(reversed_edge, curve, first, last), *boundaries[1:]])
        wrong_surface = Geom_CylindricalSurface(geometry.surface.Position(), 2.01)
        with self.assertRaisesRegex(ValueError, 'support was changed'):
            _check_seam_boundaries(c, result, wrong_surface, boundaries)

    def test_off_surface_or_same_sense_boundaries_are_rejected(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from cq_acis._analytic_seams import cylinder_seam_face
        source = stepped_cylinder()
        c = a.CadQueryConverter(source)
        p = _Placement(None, 1.)
        loops = tuple(source.entities[i] for i in (2, 3))
        geometry = c._cone_geometry(source.entities[0], source.entities[1], p)
        wires = [c._wire(loop, p, geometry) for loop in loops]
        wires[1] = c.cq.Wire(wires[1].wrapped.Reversed())
        builder = BRepBuilderAPI_MakeFace(geometry.surface, wires[0].wrapped, True)
        builder.Add(wires[1].wrapped)
        with self.assertRaises(a.CadQueryConversionError) as caught:
            cylinder_seam_face(c, source.entities[0], loops, wires, geometry, c.cq.Face(builder.Face()), p)
        self.assertEqual(caught.exception.code, 'geometry.boundary_orientation')
        entries = list(source.entities)
        curve = next(e for e in entries if isinstance(e, a.EllipseCurveEntity))
        entries[curve.index] = replace(curve, center=curve.center+a.Vec3(.01, 0, 0))
        with self.assertRaises(a.CadQueryConversionError):
            a.CadQueryConverter(replace(source, entities=tuple(entries)))._face(entries[0], p)
        entries = list(source.entities)
        point = next(e for e in entries if isinstance(e, a.PointEntity))
        entries[point.index] = replace(point, location=point.location+a.Vec3(.01, 0, 0))
        with self.assertRaises(a.CadQueryConversionError) as caught:
            a.CadQueryConverter(replace(source, entities=tuple(entries)))._face(entries[0], p)
        self.assertEqual(caught.exception.code, 'geometry.analytic_trim_mismatch')

    def test_unqualified_saved_chart_and_mirrored_traversal_are_rejected(self):
        source = stepped_cylinder()
        entries = list(source.entities)
        entries[1] = replace(entries[1], u_range=a.ParameterRange(0., 1.))
        with self.assertRaises(a.CadQueryConversionError):
            a.CadQueryConverter(replace(source, entities=tuple(entries)))._face(entries[0], _Placement(None, 1.))
        mirror = a.TransformEntity(raw(0, 'transform'),
            (-1, 0, 0, 0, 1, 0, 0, 0, 1, 3, 4, 5), 1, False, True, False)
        with self.assertRaises(a.CadQueryConversionError) as caught:
            a.CadQueryConverter(source)._face(source.entities[0], _Placement(mirror, 2.))
        self.assertEqual(caught.exception.code, 'geometry.analytic_trim_mismatch')


class ShellClosureTests(unittest.TestCase):
    def converter(self):
        return a.CadQueryConverter(a.AcisModel(a.AcisMetadata(), ()))

    def test_closed_incidence_restores_flag_without_changing_geometry(self):
        c = self.converter()
        box = c.cq.Solid.makeBox(2, 3, 4)
        shell = box.Shells()[0]
        shell.wrapped.Closed(False)
        c._check_shell_closure(shell, 7, 0)
        self.assertTrue(shell.Closed())
        actual = c.cq.Solid.makeSolid(shell)
        self.assertTrue(actual.isValid())
        self.assertAlmostEqual(actual.Volume(), 24.)
        self.assertEqual(len(actual.Faces()), 6)
        self.assertFalse(c.shell_closure_checks[0]['flag_was_closed'])

    def test_open_shell_cannot_be_accepted_even_with_a_true_flag(self):
        c = self.converter()
        box = c.cq.Solid.makeBox(2, 3, 4)
        shell = c.cq.Shell.makeShell(box.Faces()[:-1])
        for flag in (False, True):
            shell.wrapped.Closed(flag)
            with self.assertRaises(a.CadQueryConversionError) as caught:
                c._check_shell_closure(shell, 7, 0)
            self.assertEqual(caught.exception.code, 'geometry.shell_open')
        self.assertEqual(c.shell_closure_checks, [])

    def test_reversed_face_is_rejected_despite_closed_edge_incidence(self):
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Shell
        c = self.converter()
        box = c.cq.Solid.makeBox(2, 3, 4)
        shell = TopoDS_Shell()
        builder = BRep_Builder()
        builder.MakeShell(shell)
        for i, face in enumerate(box.Faces()):
            builder.Add(shell, face.wrapped.Reversed() if i == 0 else face.wrapped)
        with self.assertRaises(a.CadQueryConversionError) as caught:
            c._check_shell_closure(c.cq.Shell(shell), 7, 0)
        self.assertEqual(caught.exception.code, 'geometry.shell_orientation')


if __name__ == '__main__':
    unittest.main()
