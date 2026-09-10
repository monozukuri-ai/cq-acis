"""Closed-form geometry expectations and fail-closed boundary checks."""
from dataclasses import replace
import math
import unittest

from cq_acis import (
    AcisMetadata, AcisModel, BSplineCurveEntity, CadQueryConverter, CadQueryConversionError,
    CoedgeEntity, EdgeEntity, EllipseCurveEntity, EntityRef, FaceEntity, LoopEntity,
    NULL_REF, PointEntity, RawEntity, Vec3, VertexEntity,
)
from cq_acis.cadquery import _Placement
from test_m4_geometry import cone, sphere, raw


def bounded_face(surface, rims, apex=None):
    """One face, complete analytic rims and optionally one source null loop."""
    count = len(rims) + (apex is not None)
    face = FaceEntity(raw(0, 'face'), NULL_REF, NULL_REF, EntityRef(2), NULL_REF,
                      NULL_REF, EntityRef(1), False, False, None)
    entities = [face, replace(surface, raw=raw(1, surface.raw.type_name))]
    for i in range(count):
        base = 2 + 6*i
        curve = rims[i] if i < len(rims) else None
        curve_ref = EntityRef(base+5) if curve is not None else NULL_REF
        entities.extend([
            LoopEntity(raw(base, 'loop'), NULL_REF, EntityRef(base+6) if i+1<count else NULL_REF,
                       EntityRef(base+1), EntityRef(0)),
            CoedgeEntity(raw(base+1, 'coedge'), NULL_REF, EntityRef(base+1), EntityRef(base+1),
                         NULL_REF, EntityRef(base+2), False, EntityRef(base), NULL_REF),
            EdgeEntity(raw(base+2, 'edge'), NULL_REF, EntityRef(base+3), 0., EntityRef(base+3),
                       2*math.pi if curve else 1., EntityRef(base+1), curve_ref, False, None),
            VertexEntity(raw(base+3, 'vertex'), NULL_REF, EntityRef(base+2), EntityRef(base+4)),
            PointEntity(raw(base+4, 'point'), NULL_REF, curve.evaluate(0) if curve else apex),
            replace(curve, raw=raw(base+5, 'ellipse-curve')) if curve else raw(base+5, 'unused'),
        ])
    return AcisModel(AcisMetadata(units_mm=1., resabs=1e-6), tuple(entities))


def ellipse(center, normal, radius, ratio=1., major=None):
    if major is None:
        major = Vec3(1,0,0) if abs(normal.x) < .9 else Vec3(0,1,0)
    return EllipseCurveEntity(raw(0,'ellipse-curve'),NULL_REF,center,normal,major*radius,ratio,None)


class FollowupGeometryTests(unittest.TestCase):
    def convert_face(self, model, placement=_Placement(None,1)):
        converter = CadQueryConverter(model)
        return converter, converter._face(model.entities[0],placement)

    def test_explicit_cone_apex_retains_a_degenerate_edge(self):
        from OCP.BRep import BRep_Tool
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopoDS import TopoDS
        s=cone()
        m=bounded_face(s,[ellipse(s.center,Vec3(0,0,-1),4)],s.apex)
        converter,face=self.convert_face(m)
        self.assertTrue(face.isValid())
        self.assertAlmostEqual(face.Area(),math.pi*4*(4/.6),places=7)
        self.assertEqual(len(converter.degenerate_edges),1)
        explorer=TopExp_Explorer(face.wrapped,TopAbs_EDGE);count=0
        while explorer.More():
            count+=BRep_Tool.Degenerated_s(TopoDS.Edge_s(explorer.Current()))
            explorer.Next()
        self.assertEqual(count,1)
        wrong=bounded_face(s,[ellipse(s.center,Vec3(0,0,-1),4)],s.apex+Vec3(0,0,.001))
        with self.assertRaises(CadQueryConversionError) as caught:self.convert_face(wrong)
        self.assertEqual(caught.exception.code,'geometry.degeneracy_unproven')

    def test_elliptical_cone_frustum_has_closed_form_volume(self):
        import cadquery as cq
        s=cone(ratio=.5)
        rims=[ellipse(Vec3(0,0,z),Vec3(0,0,1),r,.5) for z,r in [(0,4),(4,7)]]
        m=bounded_face(s,rims)
        converter,side=self.convert_face(m)
        caps=[cq.Face.makeFromWires(converter._wire(m.entities[2+6*i],_Placement(None,1))) for i in range(2)]
        solid=cq.Solid.makeSolid(cq.Shell.makeShell([side,*caps]))
        self.assertTrue(solid.isValid())
        # CadQuery's default volume integration is too coarse for a rational
        # cone. Use OCCT's adaptive integral against the independent formula.
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        props=GProp_GProps()
        BRepGProp.VolumeProperties_s(solid.wrapped,props,1e-12)
        self.assertAlmostEqual(abs(props.Mass()), math.pi*.5*4/3*(16+28+49),delta=1e-6)
        self.assertEqual(len(converter.analytic_trim_faces),1)
        bad=bounded_face(s,[rims[0],replace(rims[1],center=Vec3(.01,0,4))])
        with self.assertRaises(CadQueryConversionError):self.convert_face(bad)

    def test_six_sphere_holes_cross_seams_and_poles(self):
        s=replace(sphere(3.25),center=Vec3(0,0,0))
        height=2.5;radius=math.sqrt(s.radius**2-height**2)
        axes=[Vec3(1,0,0),Vec3(-1,0,0),Vec3(0,1,0),Vec3(0,-1,0),Vec3(0,0,1),Vec3(0,0,-1)]
        rims=[ellipse(n*height,n*-1,radius) for n in axes]
        expected=4*math.pi*s.radius**2 - 6*2*math.pi*s.radius*(s.radius-height)
        converter,face=self.convert_face(bounded_face(s,rims))
        self.assertAlmostEqual(face.Area(),expected,delta=1e-4)
        self.assertEqual(len(converter.analytic_trim_faces),1)
        self.assertEqual(len(converter.analytic_trim_faces[0]['edges']),6)
        # Circle geometry must be on the sphere; no projection repairs it.
        bad=[replace(rims[0],center=rims[0].center+Vec3(.001,0,0)),*rims[1:]]
        with self.assertRaises(CadQueryConversionError):self.convert_face(bounded_face(s,bad))

    def test_sphere_cap_keeps_the_oriented_side(self):
        s=replace(sphere(2),center=Vec3(0,0,0))
        radius=math.sqrt(3)
        for normal,area in [(Vec3(0,0,1),4*math.pi),(Vec3(0,0,-1),12*math.pi)]:
            _,face=self.convert_face(bounded_face(s,[ellipse(Vec3(0,0,1),normal,radius)]))
            self.assertAlmostEqual(face.Area(),area,places=6)

    def test_sphere_trim_translation_scale_and_reflection(self):
        from cq_acis import TransformEntity
        s=replace(sphere(2),center=Vec3(0,0,0))
        rim=ellipse(Vec3(0,0,1),Vec3(0,0,1),math.sqrt(3))
        mirror=TransformEntity(raw(0,'transform'),(-1,0,0,0,1,0,0,0,1,3,4,5),1,False,True,False)
        placement=_Placement(mirror,2)
        _,face=self.convert_face(bounded_face(s,[rim]),placement)
        self.assertAlmostEqual(face.Area(),16*math.pi,places=5)
        center=face.Center()
        self.assertAlmostEqual(center.x,6,places=6)
        self.assertAlmostEqual(center.y,8,places=6)
        self.assertAlmostEqual(center.z,13,places=6)

    def test_overlapping_sphere_holes_cannot_erase_source_boundaries(self):
        s=replace(sphere(2),center=Vec3(0,0,0))
        rims=[ellipse(Vec3(0,0,1),Vec3(0,0,-1),math.sqrt(3)),
              ellipse(Vec3(1,0,0),Vec3(-1,0,0),math.sqrt(3))]
        with self.assertRaises(CadQueryConversionError):self.convert_face(bounded_face(s,rims))

    def test_rational_curve_evaluation_and_trim_match_a_quarter_circle(self):
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        curve=BSplineCurveEntity(raw(0,'intcurve-curve'),NULL_REF,2,(0.,1.),(3,3),
            (Vec3(1,0,0),Vec3(1,1,0),Vec3(0,1,0)),(1.,math.sqrt(.5),1.),None,0.)
        p=curve.evaluate(.5)
        self.assertAlmostEqual(p.x,math.sqrt(.5));self.assertAlmostEqual(p.y,math.sqrt(.5))
        self.assertEqual(curve,AcisModel(AcisMetadata(),(curve,)).to_native().entities[0])
        for reversed in (False,True):
            params=(.2,.8) if not reversed else (-.8,-.2)
            points=[curve.evaluate(abs(t)) for t in params]
            edge=EdgeEntity(raw(1,'edge'),NULL_REF,EntityRef(2),params[0],EntityRef(4),params[1],NULL_REF,EntityRef(0),reversed,None)
            ce=CoedgeEntity(raw(6,'coedge'),NULL_REF,NULL_REF,NULL_REF,NULL_REF,EntityRef(1),False,NULL_REF,NULL_REF)
            entities=(curve,edge,VertexEntity(raw(2,'vertex'),NULL_REF,EntityRef(1),EntityRef(3)),PointEntity(raw(3,'point'),NULL_REF,points[0]),
                      VertexEntity(raw(4,'vertex'),NULL_REF,EntityRef(1),EntityRef(5)),PointEntity(raw(5,'point'),NULL_REF,points[1]),ce)
            converter=CadQueryConverter(AcisModel(AcisMetadata(units_mm=1,resabs=1e-7),entities))
            result=converter._edge(ce,_Placement(None,1))
            adaptor=BRepAdaptor_Curve(result.wrapped)
            for t in [.2,.4,.5,.7,.8]:
                p=adaptor.Value(t);expected=curve.evaluate(t)
                self.assertLess(math.dist((p.X(),p.Y(),p.Z()),(expected.x,expected.y,expected.z)),1e-12)
                self.assertAlmostEqual(math.hypot(p.X(),p.Y()),1.)
            wrong=replace(entities[3],location=Vec3(2,2,2))
            changed=AcisModel(converter.model.metadata,tuple(wrong if e.index==3 else e for e in entities))
            with self.assertRaises(CadQueryConversionError) as caught:CadQueryConverter(changed)._edge(ce,_Placement(None,1))
            self.assertEqual(caught.exception.code,'geometry.spline_endpoint_mismatch')
        for bad in [replace(curve,weights=(1.,-1.,1.)),replace(curve,knots=(0.,0.)),replace(curve,degree=1000000)]:
            with self.assertRaises(ValueError):bad.validate()


if __name__=='__main__': unittest.main()
