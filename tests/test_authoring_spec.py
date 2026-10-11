"""Fresh semantic export remains detached from the immutable authored model."""
import unittest
import cadquery as cq
from cq_acis.authoring import from_cadquery

class SemanticSpecification(unittest.TestCase):
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
