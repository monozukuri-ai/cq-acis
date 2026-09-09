from __future__ import annotations

from dataclasses import asdict, fields, replace
import importlib.machinery
import importlib.util
import json
import math
from pathlib import Path
import pickle
import struct
import unittest

from cq_acis import (
    AcisContainer, AcisDiagnostic, AcisMetadata, AcisModel, AcisModelError,
    CountedString, EllipseCurveEntity, EntityRef, NativeModel, NULL_REF, RawEntity, SourceSpan, Vec3,
    convert_model, parse_sat_model,
)
from cq_acis import _native
from test_model import tetrahedron_model

ROOT = Path(__file__).resolve().parents[1]


class TestNativeModel(unittest.TestCase):
    def test_native_extension_is_loaded_and_snapshot_owns_its_data(self):
        self.assertTrue(any(_native.__file__.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES))
        model = tetrahedron_model()
        native = model.to_native()
        self.assertIsInstance(native, NativeModel)
        self.assertEqual(native.to_model(), model)
        self.assertEqual(native.resolve(EntityRef(1)), model.resolve(1))
        self.assertEqual(native.bodies(), model.bodies())
        self.assertIsNone(native.resolve(NULL_REF))
        self.assertEqual(len(native), len(model))
        self.assertIn(0, {e.index for e in native.referenced_by(EntityRef(1))})
        # Deliberately bypass frozen dataclasses: native data must not alias PyObjects.
        object.__setattr__(model.entities[0].raw, "entity_id", 99999)
        self.assertEqual(native.resolve(0).entity_id, 1000)
        with self.assertRaises(AttributeError):
            native.entities = ()

    def test_binary_tokens_big_integers_and_absent_metadata_round_trip(self):
        span = SourceSpan("part.ipt/segment/inflated", 64, 69)
        metadata = AcisMetadata(container=AcisContainer.ASM_SAB, save_version=2**130, dialect="synthetic")
        raw = RawEntity(
            0, "vendor-unknown", NULL_REF, -(2**200),
            values=(EntityRef(0), CountedString("#\x00é", 3), 2**256, -2**256,
                    1, 1.0, -0.0, "word", b"\x00\xff"),
            source=span, raw_data=b"\x00\xff\x00\x01\x02",
        )
        diagnostic = AcisDiagnostic("unsupported", "Unknown synthetic record", 0, span)
        model = AcisModel(metadata, (raw,), (diagnostic,))
        restored = model.to_native().to_model()
        self.assertEqual(restored, model)
        self.assertIsNone(restored.metadata.units_mm)
        self.assertIsNone(restored.entities[0].record)
        self.assertIs(type(restored.entities[0].values[4]), int)
        self.assertIs(type(restored.entities[0].values[5]), float)
        self.assertEqual(struct.pack("d", restored.entities[0].values[6]), struct.pack("d", -0.0))

    def test_nonfinite_raw_values_are_preserved_without_json_coercion(self):
        model = AcisModel(AcisMetadata(), (RawEntity(
            0, "opaque", NULL_REF, None, (float("nan"), float("inf"), -float("inf"))
        ),))
        values = model.to_native().entities[0].values
        self.assertTrue(math.isnan(values[0]))
        self.assertEqual(values[1:], (float("inf"), -float("inf")))

    def test_geometry_error_and_tolerance_behavior_matches_python_math(self):
        ellipse = EllipseCurveEntity(RawEntity(0, "ellipse-curve", NULL_REF, None),
                                     NULL_REF, Vec3(0, 0, 0), Vec3(0, 0, 1),
                                     Vec3(2, 0, 0), 1.0, None)
        with self.assertRaises(ValueError):
            ellipse.evaluate(float("inf"))
        with self.assertRaises(ValueError):
            ellipse.is_circle(-1)
        for ratio in (0.5, 1.0, 1.0 + 1e-10, float("inf"), float("nan")):
            for tolerance in (0.0, 1e-12, float("inf"), float("nan")):
                self.assertEqual(replace(ellipse, ratio=ratio).is_circle(tolerance),
                                 math.isclose(abs(ratio), 1.0, rel_tol=0.0, abs_tol=tolerance))

    def test_python_dataclass_contract_is_preserved(self):
        model = tetrahedron_model()
        self.assertEqual([f.name for f in fields(model)], ["metadata", "entities", "diagnostics"])
        self.assertEqual(pickle.loads(pickle.dumps(model)), model)
        self.assertEqual(asdict(model), asdict(model.to_native().to_model()))
        self.assertIs(replace(model).entities, model.entities)
        self.assertIs(model.resolve(0), model.entities[0])

    def test_native_boundary_rejects_invalid_references_and_lost_fields(self):
        native = tetrahedron_model().to_native()
        for bad in (-2, len(native), 2**200, True, 1.5):
            with self.subTest(bad=bad), self.assertRaises(AcisModelError):
                native.resolve(bad)
        model = tetrahedron_model()
        for entity in (
            replace(model.entities[0], lump=EntityRef(len(model))),
            RawEntity(0, "unknown", NULL_REF, None, (object(),)),
        ):
            with self.subTest(entity=entity), self.assertRaises(AcisModelError):
                replace(model, entities=(entity,) + model.entities[1:])
        with self.assertRaises(AcisModelError):
            replace(model, diagnostics=(AcisDiagnostic("bad", "Dangling diagnostic", len(model)),))

    def test_every_corpus_entity_round_trips_through_rust(self):
        count = 0
        kinds = set()
        for line in (ROOT / "corpus/manifest.jsonl").read_text().splitlines():
            record = json.loads(line)
            if record["format"] != "sat":
                continue
            with self.subTest(record=record["id"]):
                model = parse_sat_model((ROOT / record["path"]).read_bytes()).as_acis_model()
                restored = model.to_native().to_model()
                self.assertEqual(restored, model)
                for before, after in zip(model.entities, restored.entities):
                    self.assertIs(type(before), type(after))
                    kinds.add(type(after).__name__)
                count += len(model)
        self.assertEqual(count, 62530)
        self.assertEqual(len(kinds), 15)  # 14 decoded types and RawEntity.


@unittest.skipUnless(importlib.util.find_spec("cadquery"), "CadQuery is not installed")
class TestNativeCadQuery(unittest.TestCase):
    def test_rust_owned_model_converts_without_sat_and_preserves_units(self):
        shape, = convert_model(tetrahedron_model(25.4).to_native())
        self.assertTrue(shape.isValid())
        self.assertAlmostEqual(shape.Volume(), 25.4**3 / 6, places=7)
        self.assertEqual((len(shape.Faces()), len(shape.Edges())), (4, 6))


if __name__ == "__main__":
    unittest.main()
