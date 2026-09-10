"""Independent analytic expectations; no Inventor holdout is used here."""
from dataclasses import replace
import math
import unittest

from cq_acis import (
    AcisMetadata, AcisModel, BodyEntity, LumpEntity, ShellEntity, FaceEntity,
    ConeSurfaceEntity, SphereSurfaceEntity, TorusSurfaceEntity, BSplineSurfaceEntity,
    EntityRef, NULL_REF, RawEntity, Vec3, ParameterRange, TransformEntity,
    CadQueryConverter, CadQueryConversionError, parse_sat_model, convert_model,
)
from cq_acis.cadquery import _Placement


def raw(i, name):
    return RawEntity(i, name, NULL_REF, None)


def single_surface(surface):
    return AcisModel(AcisMetadata(units_mm=1, resabs=1e-7), (
        BodyEntity(raw(0,'body'), NULL_REF, EntityRef(1), NULL_REF, NULL_REF),
        LumpEntity(raw(1,'lump'), NULL_REF, NULL_REF, EntityRef(2), EntityRef(0)),
        ShellEntity(raw(2,'shell'), NULL_REF, NULL_REF, NULL_REF, EntityRef(3), NULL_REF, EntityRef(1)),
        FaceEntity(raw(3,'face'), NULL_REF, NULL_REF, NULL_REF, EntityRef(2), NULL_REF, EntityRef(4), False, False, None),
        replace(surface, raw=raw(4,surface.raw.type_name)),
    ))


def sphere(radius=2):
    return SphereSurfaceEntity(raw(0,'sphere-surface'), NULL_REF, Vec3(1,2,3), radius,
                               Vec3(0,0,1), Vec3(1,0,0), False, None, None)


def torus(minor=1):
    return TorusSurfaceEntity(raw(0,'torus-surface'), NULL_REF, Vec3(0,0,0), Vec3(0,0,1),
                              4, minor, Vec3(1,0,0), False, None, None)


def cone(**changes):
    return replace(ConeSurfaceEntity(raw(0,'cone-surface'), NULL_REF, Vec3(0,0,0), Vec3(0,0,1),
                                     Vec3(4,0,0), 1, None, .6, .8, 4, 13, False, None, None), **changes)


def sat(record):
    return parse_sat_model('700 0 0 0\n@4 test @4 test @4 test\n1 1e-7 1e-10\n'+record+'\nEnd-of-ACIS-data\n')


def spline_record(rational=False):
    # A bilinear patch with hand-computable rational interpolation.
    points = [(0,0,0,1),(2,0,0,2),(0,3,0,1),(2,3,4,2)]
    poles = ' '.join(' '.join(map(str,p if rational else p[:3])) for p in points)
    return ('spline-surface $-1 -1 $-1 forward { exactsur '+('nurbs' if rational else 'nubs')+
            ' 1 1 open open none none 2 2 0 1 1 1 0 1 1 1 '+poles+' 0 } I I I I #')


class M4AnalyticTests(unittest.TestCase):
    def assertVector(self, actual, expected, places=9):
        for a,b in zip((actual.x,actual.y,actual.z),expected):
            self.assertAlmostEqual(a,b,places=places)

    def test_saved_cone_scale_is_not_radius(self):
        record = 'cone-surface $-1 -1 $-1 0 0 0 0 0 1 4 0 0 1 I I .6 -.8 13 forward I I I I #'
        c = sat(record).entities[0]
        self.assertEqual((c.reference_radius, c.parameter_scale), (4,13))
        self.assertVector(c.evaluate(0,5),(7,0,-4))
        self.assertVector(c.apex,(0,0,16/3))
        self.assertEqual(c, sat(record).as_acis_model().to_native().entities[0])

    def test_positive_and_negative_cone_cosine_map_full_chart(self):
        converter = CadQueryConverter(AcisModel(AcisMetadata(units_mm=1,resabs=1e-7),()))
        face = single_surface(sphere()).entities[3]
        for cosine in [.8,-.8]:
            c = cone(cos_half_angle=cosine)
            geometry = converter._cone_geometry(face,c,_Placement(None,2))
            for u,v in [(.31,.2),(-2.9,4),(3.13,-1),(-3.13,8)]:
                p = _Placement(None,2).point_vector(c.evaluate(u,v))
                uv = geometry.uv(p)
                actual = geometry.surface.Value(*uv)
                self.assertVector(Vec3(actual.X(),actual.Y(),actual.Z()),(p.x,p.y,p.z))

    def test_ellipse_parameter_divides_by_radii(self):
        from cq_acis import EllipseCurveEntity
        e=EllipseCurveEntity(raw(0,'ellipse-curve'),NULL_REF,Vec3(0,0,0),Vec3(0,0,1),Vec3(4,0,0),.5,None)
        converter=CadQueryConverter(AcisModel(AcisMetadata(),()))
        for t in [.3,1.2,-2.7]:
            self.assertAlmostEqual(converter._ellipse_parameter(e,e.evaluate(t)),t)

    def test_closed_sphere_area_volume_bbox_and_poles(self):
        s = sphere()
        for invalid in (sphere(0),sphere(math.nan),replace(s,u_direction=Vec3(1,0,1))):
            with self.assertRaises(ValueError):invalid.evaluate(0,0)
        self.assertVector(s.evaluate(0,0),(3,2,3))
        self.assertVector(s.evaluate(.7,math.pi/2),(1,2,5))
        self.assertVector(s.evaluate(.7,-math.pi/2),(1,2,1))
        for model in (single_surface(s),single_surface(s).to_native()):
            shape=convert_model(model)[0]
            self.assertTrue(shape.isValid())
            self.assertAlmostEqual(shape.Area(),16*math.pi,places=7)
            self.assertAlmostEqual(shape.Volume(),32*math.pi/3,places=7)
            b=shape.BoundingBox()
            for actual,expected in zip((b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax),(-1,0,1,3,4,5)):
                self.assertAlmostEqual(actual,expected,places=6)

    def test_closed_torus_area_volume_and_both_periods(self):
        t=torus()
        self.assertVector(t.evaluate(0,0),(5,0,0))
        self.assertVector(t.evaluate(0,math.pi),(3,0,0))
        self.assertVector(t.evaluate(2*math.pi,2*math.pi),(5,0,0))
        shape=convert_model(single_surface(t))[0]
        self.assertTrue(shape.isValid())
        self.assertAlmostEqual(shape.Area(),16*math.pi**2,places=6)
        self.assertAlmostEqual(shape.Volume(),8*math.pi**2,places=6)
        b=shape.BoundingBox()
        for actual,expected in zip((b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax),(-5,-5,-1,5,5,1)):
            self.assertAlmostEqual(actual,expected,places=6)
        normal,point=shape.Faces()[0].normalAt(0,0)
        self.assertGreater(normal.x, .999999)

    def test_finite_loopless_ranges_and_singular_tori_fail(self):
        for surface in [replace(sphere(),u_range=ParameterRange(0,1)), torus(4),torus(5)]:
            with self.assertRaises(CadQueryConversionError):
                convert_model(single_surface(surface))

    def test_false_similarity_flag_does_not_permit_anisotropic_placement(self):
        transform=TransformEntity(raw(0,'transform'),(2,0,0,0,1,0,0,0,1,0,0,0),1,False,False,False)
        self.assertFalse(_Placement(transform,1).preserves_circles)

    def test_sat_sphere_torus_field_order_and_signed_radius(self):
        s=sat('sphere-surface $-1 -1 $-1 1 2 3 -2 1 0 0 0 0 1 forward_v I I I I #').entities[0]
        self.assertEqual((s.pole,s.u_direction,s.radius),(Vec3(0,0,1),Vec3(1,0,0),-2))
        t=sat('torus-surface $-1 -1 $-1 0 0 0 0 0 1 4 -1 1 0 0 reverse_v I I I I #').entities[0]
        self.assertTrue(t.reversed)
        self.assertEqual(t.minor_radius,-1)

    def test_sat_exactsur_evaluation_and_occt_agree_with_bilinear_formula(self):
        for rational in [False,True]:
            s=sat(spline_record(rational)).entities[0]
            self.assertIsInstance(s,BSplineSurfaceEntity)
            s.validate()
            converter=CadQueryConverter(AcisModel(AcisMetadata(),()))
            ocp=converter._bspline_geometry(s,_Placement(None,1))
            for u,v in [(0,0),(1,1),(.23,.71),(.5,.5),(1,0)]:
                weighted_u = 2*u/(1+u) if rational else u
                expected=(2*weighted_u,3*v,4*weighted_u*v)
                self.assertVector(s.evaluate(u,v),expected)
                p=ocp.Value(u,v)
                self.assertVector(Vec3(p.X(),p.Y(),p.Z()),expected)
            self.assertEqual(s,sat(spline_record(rational)).as_acis_model().to_native().entities[0])

    def test_spline_rejects_bad_weights_knots_and_domains(self):
        s=sat(spline_record()).entities[0]
        for bad in [replace(s,weights=(1,0,1,1)),replace(s,u_knots=(0,0)),
                    replace(s,u_multiplicities=(1,1)),replace(s,u_count=1000001)]:
            with self.assertRaises(ValueError):bad.validate()
        for u,v in [(-.1,.5),(.5,1.1),(math.nan,0)]:
            with self.assertRaises(ValueError):s.evaluate(u,v)
        for marker in ['periodic','closed']:
            self.assertIsInstance(sat(spline_record().replace('open open',marker+' open')).entities[0],RawEntity)
        self.assertIsInstance(sat(spline_record().replace('exactsur','sweep_sur')).entities[0],RawEntity)
        with self.assertRaises(ValueError):sat(spline_record().replace('0 }','0 12 }'))


if __name__=='__main__':unittest.main()

class M4SplineTrimTests(unittest.TestCase):
    def test_planar_nurbs_patch_trims_the_public_cube_without_changing_volume(self):
        from pathlib import Path
        from cq_acis import PlaneSurfaceEntity
        model = parse_sat_model((Path(__file__).parents[1]/'corpus/data/ezdxf/cube_sat_700.sat').read_bytes()).as_acis_model()
        plane = next(e for e in model.entities if isinstance(e,PlaneSurfaceEntity))
        # Synthetic representation change of one face, not an independent native NURBS file.
        poles = tuple(plane.origin + plane.u_direction*u + plane.v_direction*v
                      for v in [-1000,1000] for u in [-1000,1000])
        patch = BSplineSurfaceEntity(plane.raw,plane.pattern,1,1,(-1000,1000),(-1000,1000),(2,2),(2,2),2,2,poles,(1,1,1,1),False,None,None,0)
        changed = AcisModel(model.metadata,tuple(patch if e.index==plane.index else e for e in model.entities))
        converter=CadQueryConverter(changed)
        shape=converter.convert()[0]
        self.assertTrue(shape.isValid())
        self.assertAlmostEqual(shape.Volume(),777**3,places=5)
        self.assertGreaterEqual(converter.pcurve_count,4)
        self.assertLessEqual(converter.pcurve_max_deviation,converter.tolerance)
