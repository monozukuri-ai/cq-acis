from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from cq_acis import (
    SUPPORTED_ENTITY_TYPES,
    AcisContainer,
    DecodedEntity,
    RawEntity,
    detect_container,
    parse_sat,
    parse_sat_model,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "corpus" / "manifest.jsonl"


def load_manifest() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestPinnedCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_manifest()

    def test_manifest_contains_expected_p0_artifacts(self) -> None:
        self.assertEqual(len(self.manifest), 25)
        self.assertEqual(
            sum(record["format"] == "sat" for record in self.manifest), 23
        )
        self.assertEqual(
            sum(record["format"] == "sab" for record in self.manifest), 2
        )

    def test_hashes_and_sizes_match_manifest(self) -> None:
        for record in self.manifest:
            with self.subTest(record=record["id"]):
                data = (ROOT / record["path"]).read_bytes()
                self.assertEqual(len(data), record["size_bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), record["sha256"])

    def test_all_sat_files_frame_without_schema_knowledge(self) -> None:
        entity_types: set[str] = set()
        for record in self.manifest:
            if record["format"] != "sat":
                continue
            with self.subTest(record=record["id"]):
                data = (ROOT / record["path"]).read_bytes()
                document = parse_sat(data)
                self.assertEqual(
                    document.header.save_version, record["save_version"]
                )
                self.assertTrue(any(item.entity_type == "body" for item in document.records))
                if document.header.declared_record_count > 0:
                    self.assertEqual(
                        len(document.records), document.header.declared_record_count
                    )
                if document.header.save_version >= 400:
                    self.assertTrue(document.has_end_marker)
                entity_types.update(item.entity_type for item in document.records)

        self.assertTrue(
            {
                "body",
                "lump",
                "shell",
                "face",
                "loop",
                "coedge",
                "edge",
                "vertex",
                "point",
            }.issubset(entity_types)
        )

    def test_sab_preambles_are_detected(self) -> None:
        detected: set[AcisContainer] = set()
        for record in self.manifest:
            if record["format"] != "sab":
                continue
            data = (ROOT / record["path"]).read_bytes()
            detected.add(detect_container(data))
        self.assertEqual(detected, {AcisContainer.SAB, AcisContainer.ASM_SAB})

    def test_all_sat_references_and_supported_schemas_decode(self) -> None:
        raw_count = 0
        typed_count = 0
        for record in self.manifest:
            if record["format"] != "sat":
                continue
            with self.subTest(record=record["id"]):
                data = (ROOT / record["path"]).read_bytes()
                model = parse_sat_model(data)
                raw_count += len(model.graph)
                typed_count += sum(
                    isinstance(entity, DecodedEntity) for entity in model.entities
                )
                for entity in model.entities:
                    if isinstance(entity, RawEntity):
                        self.assertNotIn(entity.type_name, SUPPORTED_ENTITY_TYPES)
                for body in model.bodies():
                    if not body.lump.is_null:
                        self.assertEqual(model.resolve(body.lump).raw.type_name, "lump")

        self.assertEqual(raw_count, 62530)
        self.assertEqual(typed_count, 36533)


if __name__ == "__main__":
    unittest.main()
