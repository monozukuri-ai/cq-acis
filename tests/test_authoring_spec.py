"""Semantic specifications can be reused without mutating the authored model."""
import copy
import json
import unittest

import cadquery as cq

from cq_acis import _native
from cq_acis.authoring import from_cadquery


class SemanticSpecification(unittest.TestCase):
    def test_exported_spec_rebuilds_identical_sab(self):
        shapes = {
            "box": cq.Solid.makeBox(13, 17, 23),
            "cylinder": cq.Workplane("XY").circle(3).extrude(5).val(),
        }
        for name, shape in shapes.items():
            authored = from_cadquery(shape)
            spec = authored.to_spec()
            for transport, restored in (
                ("direct", spec),
                ("json", json.loads(json.dumps(spec))),
            ):
                with self.subTest(shape=name, transport=transport):
                    rebuilt = _native.author_analytic(restored)
                    for history in (False, True):
                        self.assertEqual(
                            rebuilt.to_sab(history=history),
                            authored.to_sab(history=history),
                        )

    def test_spec_sequences_keep_arity_and_element_type_checks(self):
        original = from_cadquery(cq.Solid.makeBox(13, 17, 23)).to_spec()
        cases = (
            ("vertices_mm", [0], [0.0, 0.0], ValueError),
            ("vertices_mm", [0], [0.0, 0.0, 0.0, 0.0], ValueError),
            ("vertices_mm", [0], [0.0, "invalid", 0.0], TypeError),
            ("edges", [0, "curve", "origin"], [0.0, 0.0], ValueError),
            ("faces", [0, "loops", 0, 0], [0], ValueError),
            ("faces", [0, "loops", 0, 0], [0, False, False], ValueError),
            ("faces", [0, "loops", 0, 0], [0, "false"], TypeError),
            ("faces", [0, "loops", 0, 0], ["invalid", False], TypeError),
        )
        for table, path, value, error in cases:
            with self.subTest(table=table, path=path, value=value):
                spec = copy.deepcopy(original)
                item = spec[table]
                for key in path[:-1]:
                    item = item[key]
                item[path[-1]] = value
                with self.assertRaises(error):
                    _native.author_analytic(spec)

    def test_detached_spec_does_not_modify_generated_model(self):
        authored=from_cadquery(cq.Workplane('XY').circle(3).extrude(5).val())
        before=authored.to_sab(history=False)
        spec=authored.to_spec()
        original=spec['vertices_mm'][0][0]
        spec['vertices_mm'][0][0]=123456.
        self.assertEqual(authored.to_spec()['vertices_mm'][0][0],original)
        self.assertEqual(authored.to_sab(history=False),before)
        self.assertEqual(set(authored.to_spec()),{'vertices_mm','edges','faces','tolerance_mm'})

if __name__=='__main__':unittest.main()
