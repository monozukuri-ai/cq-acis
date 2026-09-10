"""Partial topology views and source-preserving subtype resolution."""
from dataclasses import replace
import math
import unittest

import cq_acis as a
from cq_acis.cadquery import _Placement

N = a.NULL_REF


def raw(index, name, values=()):
    return a.RawEntity(index, name, N, None, tuple(values), None, None, None)


def model(entities, version=22700):
    return a.AcisModel(a.AcisMetadata(save_version=version, units_mm=1., resabs=1e-6), tuple(entities))


def curve_values():
    # Rational quadratic unit quarter circle, with the qualified default trailer.
    return (N, b'\x0b', b'\x0f', 'exact_int_cur', 22601, 0, 'nurbs', 2, 0, 2,
            0., 2, 1., 2, 1.,0.,0.,1., 1.,1.,0.,math.sqrt(.5), 0.,1.,0.,1.,
            0., 'null_surface','null_surface','nullbs','nullbs',b'\x0b',b'\x0b',
            0,0,0,0,b'\x0a',1.,b'\x0a',0.,0,0,b'\x10',b'\x0a',0.,b'\x0a',1.)


class TopologyTests(unittest.TestCase):
    def test_views_keep_unknown_scalars_and_raw_entity_kinds(self):
        vertex = raw(0, 'tvertex-vertex', (N,N,1,N,-1.,.01,.02,0))
        edge = raw(1, 'tedge-edge', (N,N,0.,N,1.,N,N,b'\x0b','tangent',.01,22601,0))
        coedge = raw(2, 'tcoedge-coedge', (N,N,N,N,N,b'\x0b',N,0,N,0.,1.,N,0,'null_curve',0))
        native = model([vertex,edge,coedge]).to_native()
        v,e,c = (native.tolerant_topology(i) for i in range(3))
        self.assertEqual(v.saved_scalars, (-1.,.01,.02))
        self.assertEqual(v.vertex.raw, vertex)
        self.assertEqual(e.edge.raw, edge)
        self.assertEqual(c.coedge.raw, coedge)
        self.assertEqual(native.entities, (vertex,edge,coedge))
        self.assertIsNone(model([vertex],22600).to_native().tolerant_topology(0))
        for source in [vertex, edge, coedge]:
            for length in range(len(source.values)):
                bad = replace(source,index=0,values=source.values[:length])
                with self.assertRaises(a.AcisModelError):model([bad]).to_native().tolerant_topology(0)
            extra=replace(source,index=0,values=(*source.values,0))
            with self.assertRaises(a.AcisModelError):model([extra]).to_native().tolerant_topology(0)
        for pos, value in [(11,a.EntityRef(0)), (12,1), (13,'intcurve')]:
            values=list(coedge.values);values[pos]=value
            with self.assertRaises(a.AcisModelError):
                model([replace(coedge,index=0,values=tuple(values))]).to_native().tolerant_topology(0)

    def test_tolerant_point_is_accepted_only_at_original_precision(self):
        curve=a.BSplineCurveEntity(raw(0,'intcurve-curve'),N,2,(0.,1.),(3,3),
            (a.Vec3(1,0,0),a.Vec3(1,1,0),a.Vec3(0,1,0)),(1.,math.sqrt(.5),1.),None,0.)
        edge=a.EdgeEntity(raw(1,'edge'),N,a.EntityRef(2),0.,a.EntityRef(4),1.,a.EntityRef(6),a.EntityRef(0),False,None)
        tv=raw(2,'tvertex-vertex',(N,a.EntityRef(1),1,a.EntityRef(3),-1.,100.,200.,0))
        point=a.PointEntity(raw(3,'point'),N,a.Vec3(1,0,0))
        end=a.VertexEntity(raw(4,'vertex'),N,a.EntityRef(1),a.EntityRef(5))
        end_point=a.PointEntity(raw(5,'point'),N,a.Vec3(0,1,0))
        co=a.CoedgeEntity(raw(6,'coedge'),N,a.EntityRef(6),a.EntityRef(6),N,a.EntityRef(1),False,N,N)
        entities=[curve,edge,tv,point,end,end_point,co]
        converter=a.CadQueryConverter(model(entities))
        result=converter._edge(co,_Placement(None,1))
        self.assertTrue(result.isValid())
        self.assertAlmostEqual(result.Length(),math.pi/2,delta=1e-6)
        self.assertEqual(converter.tolerant_endpoints[0]['tolerance_mm'],1e-6)
        entities[3]=replace(point,location=a.Vec3(1.01,0,0))
        with self.assertRaises(a.CadQueryConversionError) as caught:
            a.CadQueryConverter(model(entities))._edge(co,_Placement(None,1))
        self.assertEqual(caught.exception.code,'geometry.spline_endpoint_mismatch')

    def test_nested_alias_preserves_both_source_owners(self):
        values=curve_values();close=values.index(b'\x10')+1
        owner=raw(0,'pcurve',(N,0,b'\x0b',b'\x0f','exp_par_cur',*values[2:close],b'\x10'))
        alias=raw(1,'intcurve-curve',(N,b'\x0b',b'\x0f','ref',1,b'\x10',b'\x0a',.2,b'\x0a',.8))
        native=model([owner,alias]).to_native()
        table=native.subtype_table
        self.assertEqual(len(table.definitions),2)
        self.assertEqual(table.definitions[1].parent,0)
        self.assertEqual(table.references[0].target,1)
        result=native.resolve_subtype(1)
        self.assertEqual(result.geometry.raw,alias)
        self.assertEqual(result.definition.entity_index,0)
        self.assertEqual(result.geometry.parameter_range,a.ParameterRange(.2,.8))
        self.assertAlmostEqual(result.geometry.evaluate(.5).x,math.sqrt(.5))
        self.assertEqual(native.entities[1],alias)
        converter=a.CadQueryConverter(native)
        self.assertEqual(converter._resolve_geometry(a.EntityRef(1)),result.geometry)
        self.assertEqual(converter.resolved_subtypes[0]['definition_entity'],0)

    def test_subtype_scope_uncertainty_and_file_local_indices(self):
        definition=raw(0,'intcurve-curve',curve_values())
        alias=raw(1,'intcurve-curve',(N,b'\x0b',b'\x0f','ref',0,b'\x10',b'\x0b',b'\x0b'))
        self.assertIsNotNone(model([definition,alias]).to_native().resolve_subtype(1))
        unknown=raw(0,'unknown',(b'\x0f','unknown_law',b'\x10'))
        for owner in [unknown,raw(0,'point'),replace(definition,type_name='unknown-attrib'),
                      raw(0,'pcurve',(b'\x0f','exp_par_cur',b'\x10'))]:
            native=model([owner,alias]).to_native()
            with self.assertRaises(a.AcisModelError):native.resolve_subtype(1)
        for index in [-1, 999, 2**100]:
            values=list(alias.values);values[4]=index
            native=model([definition,replace(alias,values=tuple(values))]).to_native()
            self.assertIsNone(native.subtype_table.references[0].target)
            with self.assertRaises(a.AcisModelError):native.resolve_subtype(1)
        reversed=replace(alias,values=(N,b'\x0a',*alias.values[2:]))
        with self.assertRaises(a.AcisModelError):model([definition,reversed]).to_native().resolve_subtype(1)


if __name__ == '__main__':
    unittest.main()
