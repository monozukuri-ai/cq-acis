from pathlib import Path
import unittest
from cq_acis import RawEntity, parse_sab_model, to_cadquery

ROOT = Path(__file__).resolve().parents[1]


class TestSab(unittest.TestCase):
    def test_public_cubes_geometry_and_exact_source_spans(self):
        for version in (21800, 22300):
            path = ROOT / f'corpus/data/ezdxf/cube_asm_sab_{version}.sab'
            if not path.exists():
                self.skipTest('Populate the ezdxf corpus to run public SAB checks')
            data = path.read_bytes()
            model = parse_sab_model(data, source_id=path.name)
            self.assertEqual(len(model), 115)
            self.assertEqual(len(model.bodies()), 1)
            self.assertEqual(model.metadata.save_version, version)
            self.assertFalse(any(d.code == 'sab.entity_schema_unsupported' for d in model.diagnostics))
            for e in model.entities:
                raw = e if isinstance(e, RawEntity) else e.raw
                self.assertIsNone(raw.record)
                self.assertEqual(raw.source.source_id, path.name)
                self.assertEqual(raw.raw_data, data[raw.source.start_offset:raw.source.end_offset])
            shape = to_cadquery(model).val()
            self.assertTrue(shape.isValid())
            self.assertEqual((len(shape.Faces()), len(shape.Edges()), len(shape.Vertices())), (6, 12, 8))
            self.assertAlmostEqual(shape.Volume(), 777**3, places=4)
            bounds = shape.BoundingBox()
            for v in (bounds.xlen, bounds.ylen, bounds.zlen):
                self.assertAlmostEqual(v, 777, places=7)

    def test_binary_boundary_errors_are_python_exceptions(self):
        with self.assertRaisesRegex(ValueError, 'signature'):
            parse_sab_model(b'not a SAB')
        with self.assertRaises(TypeError):
            parse_sab_model('not bytes')
        with self.assertRaises(ValueError):
            parse_sab_model(b'', source_id='')
