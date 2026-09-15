"""Analytic oblique sections and source-preserving paired generator trims."""
from dataclasses import replace
import math
from pathlib import Path
import tempfile
import unittest

import cq_acis as a
from cq_acis.cadquery import _Placement
from test_m4_geometry import raw, cone
from test_m4_followup import bounded_face, ellipse

N, R = a.NULL_REF, a.EntityRef


def cylinder():
    return cone(major_axis=a.Vec3(2,0,0), reference_radius=2, parameter_scale=2,
                sin_half_angle=0., cos_half_angle=1.)


def oblique_band(height=5., tilt=.1):
    upper = ellipse(a.Vec3(0,0,height), a.Vec3(tilt,0,-1).normalized(),
                    2*math.sqrt(1+tilt*tilt), 1/math.sqrt(1+tilt*tilt),
                    a.Vec3(1,0,tilt).normalized())
    return bounded_face(cylinder(), [ellipse(a.Vec3(0,0,0),a.Vec3(0,0,1),2), upper])


def slit_band(intervals=((2.,3.),(5.,6.),(7.,8.)), phases=None):
    m = bounded_face(cylinder(), [ellipse(a.Vec3(0,0,0),a.Vec3(0,0,1),2),
                                 ellipse(a.Vec3(0,0,10),a.Vec3(0,0,-1),2)])
    entries = list(m.entities)
    previous = 8  # Second circular loop in bounded_face().
    for i,(start,end) in enumerate(intervals):
        phi = phases[i] if phases else 1.1
        p,q = (a.Vec3(2*math.cos(phi),2*math.sin(phi),z) for z in (start,end))
        base = len(entries)
        entries[previous] = replace(entries[previous],next_loop=R(base))
        entries.extend([
            a.LoopEntity(raw(base,'loop'),N,N,R(base+1),R(0)),
            a.CoedgeEntity(raw(base+1,'coedge'),N,R(base+2),R(base+2),R(base+2),R(base+3),False,R(base),N),
            a.CoedgeEntity(raw(base+2,'coedge'),N,R(base+1),R(base+1),R(base+1),R(base+3),True,R(base),N),
            a.EdgeEntity(raw(base+3,'edge'),N,R(base+4),0.,R(base+6),(q-p).magnitude,R(base+1),R(base+8),False,None),
            a.VertexEntity(raw(base+4,'vertex'),N,R(base+3),R(base+5)),
            a.PointEntity(raw(base+5,'point'),N,p),
            a.VertexEntity(raw(base+6,'vertex'),N,R(base+3),R(base+7)),
            a.PointEntity(raw(base+7,'point'),N,q),
            a.StraightCurveEntity(raw(base+8,'straight-curve'),N,p,(q-p).normalized(),None),
        ])
        previous = base
    return replace(m,entities=tuple(entries))


class CylinderSectionTests(unittest.TestCase):
    def convert(self, model, placement=_Placement(None,1)):
        c = a.CadQueryConverter(model)
        return c, c._face(model.entities[0],placement)

    def test_oblique_sections_preserve_exact_cylinder_area_and_trim(self):
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder
        for tilt in (.03,.1,-.07):
            model = oblique_band(tilt=tilt)
            c, face = self.convert(model)
            self.assertTrue(face.isValid())
            self.assertEqual(BRepAdaptor_Surface(face.wrapped).GetType(),GeomAbs_Cylinder)
            self.assertAlmostEqual(face.Area(),20*math.pi,delta=1e-5)
            self.assertTrue(c.periodic_seam_faces[0]['elliptic_sections'])
            self.assertLessEqual(c.periodic_seam_faces[0]['max_deviation_mm'],c.tolerance)
            self.assertEqual(model,model.to_native().to_model())
            for p in (e.location for e in model.entities if isinstance(e,a.PointEntity)):
                self.assertTrue(any(math.dist((p.x,p.y,p.z),v.toTuple())<=c.tolerance for v in face.Vertices()))

    def test_full_face_sense_is_retained_when_chart_builder_reverses_wires(self):
        from OCP.TopAbs import TopAbs_REVERSED
        model = oblique_band()
        entries = tuple(replace(e,reversed=not e.reversed) if isinstance(e,a.CoedgeEntity) else e for e in model.entities)
        c, face = self.convert(replace(model,entities=entries))
        self.assertTrue(face.isValid())
        self.assertEqual(face.wrapped.Orientation(),TopAbs_REVERSED)
        self.assertAlmostEqual(face.Area(),20*math.pi,delta=1e-5)
        self.assertTrue(c.periodic_seam_faces[0]['source_sense_restored'])

    def test_closed_vertex_identity_does_not_override_a_partial_saved_interval(self):
        model = oblique_band()
        for end in (.5, None, float('nan')):
            entries = list(model.entities)
            edge = next(e for e in entries if isinstance(e,a.EdgeEntity))
            entries[edge.index] = replace(edge,end_parameter=end)
            with self.subTest(end=end),self.assertRaises(a.CadQueryConversionError):
                self.convert(replace(model,entities=tuple(entries)))

    def test_crossing_touching_and_off_surface_sections_are_rejected(self):
        for height in (.1,.2):
            with self.subTest(height=height),self.assertRaises(a.CadQueryConversionError):
                self.convert(oblique_band(height=height,tilt=.1))
        source = oblique_band()
        for changed_type in (a.EllipseCurveEntity,a.PointEntity):
            entries = list(source.entities)
            original = next(e for e in reversed(entries) if isinstance(e,changed_type))
            if changed_type is a.EllipseCurveEntity:
                changed = replace(original,center=original.center+a.Vec3(.01,0,0))
            else:
                changed = replace(original,location=original.location+a.Vec3(.01,0,0))
            entries[original.index] = changed
            with self.subTest(changed_type=changed_type),self.assertRaises(a.CadQueryConversionError):
                self.convert(replace(source,entities=tuple(entries)))

    def test_slits_survive_step_as_seam_segments_with_all_source_vertices(self):
        import cadquery as cq
        from OCP.BRep import BRep_Tool
        for intervals in (((2.,3.),(5.,6.),(7.,8.)),((8.,7.),(3.,2.),(6.,5.))):
            model = slit_band(intervals)
            c, face = self.convert(model)
            self.assertTrue(face.isValid())
            self.assertAlmostEqual(face.Area(),40*math.pi,delta=1e-7)
            self.assertEqual(c.cylinder_slit_faces[0]['source_paired_edges'],3)
            self.assertEqual(c.cylinder_slit_faces[0]['seam_segments'],7)
            self.assertEqual(len(face.Edges()),11)
            self.assertEqual(model,model.to_native().to_model())
            with tempfile.TemporaryDirectory() as temp:
                path = str(Path(temp)/'slits.step')
                cq.exporters.export(face,path)
                after = cq.importers.importStep(path).val().Faces()[0]
            self.assertTrue(after.isValid())
            self.assertEqual(len(after.Edges()),len(face.Edges()))
            self.assertEqual(sum(BRep_Tool.IsClosed_s(e.wrapped,after.wrapped) for e in after.Edges()),7)
            self.assertAlmostEqual(after.Area(),face.Area(),delta=1e-7)
            for point in (e.location for e in model.entities if isinstance(e,a.PointEntity)):
                for shape in (face,after):
                    self.assertTrue(any(math.dist((point.x,point.y,point.z),v.toTuple())<=c.tolerance for v in shape.Vertices()))

    def test_slit_chart_translation_rotation_and_scale(self):
        transform = a.TransformEntity(raw(0,'transform'),(0,1,0,-1,0,0,0,0,1,3,4,5),1,False,False,False)
        model = slit_band(phases=(0.,0.,0.))
        c,face = self.convert(model,_Placement(transform,2.))
        self.assertTrue(face.isValid())
        self.assertAlmostEqual(face.Area(),160*math.pi,delta=1e-6)
        self.assertEqual(c.cylinder_slit_faces[0]['source_paired_edges'],3)

    def test_slit_overlap_rim_contact_and_other_generator_are_rejected(self):
        for model in (slit_band(((2.,4.),(3.,5.))),slit_band(((0.,3.),)),
                      slit_band(phases=(1.1,1.2,1.1))):
            with self.assertRaisesRegex(a.CadQueryConversionError,'overlap|touch|generators'):
                self.convert(model)

    def test_slit_source_point_curve_clock_and_rim_sense_are_checked(self):
        model = slit_band()
        source_edge = next(e for e in model.entities if isinstance(e,a.EdgeEntity) and e.start_vertex!=e.end_vertex)
        point = model.resolve(model.resolve(source_edge.end_vertex).point)
        start_point = model.resolve(model.resolve(source_edge.start_vertex).point)
        rim_use = next(e for e in model.entities if isinstance(e,a.CoedgeEntity))
        rim_curve = model.resolve(model.resolve(rim_use.edge).curve)
        for original, changed in ((source_edge,replace(source_edge,end_parameter=source_edge.end_parameter+.01)),
                                  (point,replace(point,location=point.location+a.Vec3(.01,0,0))),
                                  (point,replace(point,location=start_point.location)),
                                  (rim_curve,replace(rim_curve,major_axis=a.Vec3(math.sqrt(4-.01**2),0,.01))),
                                  (rim_use,replace(rim_use,reversed=not rim_use.reversed))):
            entries = list(model.entities);entries[original.index]=changed
            with self.subTest(entity=original.index),self.assertRaises(a.CadQueryConversionError):
                self.convert(replace(model,entities=tuple(entries)))

    def test_saved_uv_and_mirrored_slit_chart_are_not_inferred(self):
        for source in (slit_band(),oblique_band()):
            for field in ('u_range','v_range','profile_range'):
                entries = list(source.entities)
                entries[1]=replace(entries[1],**{field:a.ParameterRange(0.,1.)})
                with self.subTest(field=field),self.assertRaises(a.CadQueryConversionError):
                    self.convert(replace(source,entities=tuple(entries)))
        source = slit_band()
        mirror=a.TransformEntity(raw(0,'transform'),(-1,0,0,0,1,0,0,0,1,0,0,0),1,False,True,False)
        with self.assertRaises(a.CadQueryConversionError):self.convert(source,_Placement(mirror,1.))


if __name__ == '__main__':
    unittest.main()
