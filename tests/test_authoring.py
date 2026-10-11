"""Analytic authoring: independent OCCT geometry and malformed semantic inputs."""
import copy
import math
import unittest
from unittest.mock import patch

import cadquery as cq
import cq_acis as a
from cq_acis import _native


class AnalyticAuthoringTests(unittest.TestCase):
    def roundtrip(self, source):
        authored = a.from_cadquery(source)
        self.assertFalse(authored.native_qualified)
        for history in (False, True):
            model = a.parse_sab_model(authored.to_sab(history=history))
            rebuilt = a.to_cadquery(model).val()
            self.assertTrue(rebuilt.isValid())
            self.assertEqual(len(rebuilt.Solids()), 1)
            self.assertEqual(len(source.Faces()), len(rebuilt.Faces()))
            self.assertEqual(len(source.Edges()), len(rebuilt.Edges()))
            self.assertEqual(len(source.Vertices()), len(rebuilt.Vertices()))
            self.assertAlmostEqual(source.Volume(), rebuilt.Volume(), delta=source.Volume()*1e-6)
            self.assertAlmostEqual(source.Area(), rebuilt.Area(), delta=source.Area()*1e-6)
            self.assertLessEqual(source.cut(rebuilt).Volume()+rebuilt.cut(source).Volume(), source.Volume()*1e-7)
            x,y=source.BoundingBox(),rebuilt.BoundingBox()
            for attr in ('xmin','ymin','zmin','xmax','ymax','zmax'):
                self.assertAlmostEqual(getattr(x,attr),getattr(y,attr),delta=1e-5)
            # Edge references remain shared; paired seam occurrences are not merged.
            coedges=[e for e in model.entities if isinstance(e,a.CoedgeEntity)]
            for c in coedges:
                partner=model.resolve(c.partner_coedge)
                self.assertEqual(partner.edge,c.edge)
                # The two uses of a shared edge run in opposite directions
                # in the outward-oriented shell, including reversed faces.
                self.assertNotEqual(partner.reversed,c.reversed)
                self.assertEqual(model.resolve(partner.partner_coedge).index,c.index)
                self.assertEqual(model.resolve(c.next_coedge).previous_coedge.index,c.index)
        return authored

    def test_planar_face_walk_has_outward_winding(self):
        model=a.from_cadquery(cq.Solid.makeBox(13,17,23)).model
        for face in (e for e in model.entities if isinstance(e,a.FaceEntity)):
            normal=model.resolve(face.surface).normal
            loop=model.resolve(face.loop)
            start=loop.coedge
            current=start
            area=cq.Vector()
            while True:
                use=model.resolve(current)
                edge=model.resolve(use.edge)
                refs=[edge.start_vertex,edge.end_vertex]
                if use.reversed:refs.reverse()
                points=[model.resolve(model.resolve(v).point).location for v in refs]
                p,q=[cq.Vector(v.x,v.y,v.z) for v in points]
                area+=p.cross(q)
                current=use.next_coedge
                if current==start:break
            signed=area.dot(cq.Vector(normal.x,normal.y,normal.z))
            self.assertGreater(signed*(-1 if face.reversed else 1),0)

    def test_box_and_rigid_location(self):
        source=cq.Solid.makeBox(13,17,23)
        self.roundtrip(source)
        location=cq.Location(cq.Vector(17,-23,41),cq.Vector(1,2,3),37)
        self.roundtrip(source.moved(location))

    def test_full_circles_and_both_seam_branches(self):
        source=cq.Workplane('XY').circle(7).extrude(19).val()
        authored=self.roundtrip(source)
        seams=[p for p in authored.pcurves if p.seam]
        self.assertEqual(len(seams),2)
        self.assertEqual(seams[0].edge,seams[1].edge)
        self.assertNotEqual(seams[0].definition,seams[1].definition)
        self.assertEqual(sum(isinstance(e,a.EllipseCurveEntity) for e in authored.model.entities),2)
        self.roundtrip(source.rotate((0,0,0),(1,1,0),31).translate((103,-57,13)))

    def test_hole_and_counterbore_inner_loops(self):
        hole=cq.Workplane('XY').box(40,30,12).faces('>Z').workplane().hole(7).solids().val()
        bore=cq.Workplane('XY').box(40,30,12).faces('>Z').workplane().cboreHole(7,13,4).solids().val()
        for s in (hole,bore):
            authored=self.roundtrip(s)
            self.assertGreater(sum(isinstance(e,a.LoopEntity) for e in authored.model.entities),len(s.Faces()))

    def test_partial_arcs(self):
        tube=cq.Solid.makeCylinder(10,18).cut(cq.Solid.makeCylinder(7,18))
        slit=cq.Solid.makeBox(20,5,18,cq.Vector(0,-2.5,0))
        self.roundtrip(tube.cut(slit).Solids()[0])

    def test_ellipse_boundary_and_original_uv_spline(self):
        cylinder=cq.Solid.makeCylinder(10,30)
        tool=cq.Solid.makeBox(80,80,40,cq.Vector(-40,-40,18)).rotate((0,0,18),(0,1,18),25)
        source=cylinder.cut(tool).Solids()[0]
        authored=self.roundtrip(source)
        self.assertTrue(any(isinstance(e,a.EllipseCurveEntity) and e.ratio<.999 for e in authored.model.entities))
        self.assertTrue(any(p.kind=='bspline' for p in authored.pcurves))

    def test_unsupported_shapes_fail_specifically(self):
        for shape,reason in [(cq.Solid.makeSphere(5),'unsupported'),(cq.Solid.makeTorus(10,2),'unsupported'),
                             (cq.Compound.makeCompound([cq.Solid.makeBox(1,2,3)]),'one cadquery.Solid'),
                             (cq.Workplane('XY').newObject([cq.Solid.makeBox(1,2,3),cq.Solid.makeBox(2,3,4)]),'multiple')]:
            with self.subTest(reason=reason),self.assertRaisesRegex(a.AuthoringError,reason):a.from_cadquery(shape)

    def test_rust_semantic_boundary_rejects_corruption(self):
        captured=[]
        builder=_native.author_analytic
        def save(spec):captured.append(copy.deepcopy(spec));return builder(spec)
        with patch.object(_native,'author_analytic',save):
            a.from_cadquery(cq.Solid.makeBox(10,20,30))
        original=captured[0]
        changes=[
            lambda s:s['vertices_mm'].__setitem__(0,(math.nan,0,0)),
            lambda s:s.update(tolerance_mm=.001),
            lambda s:s['edges'][0].update(vertices=[999,0]),
            lambda s:s['edges'][0].update(parameters=[0,0]),
            lambda s:s['edges'][0]['curve'].update(direction=(0,0,0)),
            lambda s:s['faces'][0].update(loops=[]),
            lambda s:s['faces'][0].update(reversed=not s['faces'][0]['reversed']),
            lambda s:s['faces'][0]['loops'][0].pop(),
            lambda s:s['faces'][0]['surface'].update(origin=(300,400,500)),
            lambda s:s['edges'][0]['curve'].update(kind='opaque-native-record'),
        ]
        for mutate in changes:
            spec=copy.deepcopy(original);mutate(spec)
            with self.subTest(change=changes.index(mutate)),self.assertRaises(ValueError):builder(spec)


if __name__=='__main__':unittest.main()
