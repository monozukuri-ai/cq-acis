from __future__ import annotations

import unittest

from cq_acis import (
    AcisContainer,
    SatParseError,
    detect_container,
    parse_sat,
    parse_sat_header,
)


class TestContainerDetection(unittest.TestCase):
    def test_detect_sat(self) -> None:
        self.assertEqual(detect_container("105 1 1 0\nbody $-1 #"), AcisContainer.SAT)

    def test_detect_sab_preambles(self) -> None:
        self.assertEqual(
            detect_container(b"ACIS BinaryFile\x00\x01"), AcisContainer.SAB
        )
        self.assertEqual(
            detect_container(b"ASM BinaryFile\x00\x01"), AcisContainer.ASM_SAB
        )

    def test_reject_unknown_data(self) -> None:
        with self.assertRaises(SatParseError):
            detect_container(b"not an ACIS file")


class TestSatHeader(unittest.TestCase):
    def test_parse_legacy_one_line_header(self) -> None:
        header = parse_sat_header("105 128 1 0\nbody $-1 #")
        self.assertEqual(header.save_version, 105)
        self.assertEqual(header.declared_record_count, 128)
        self.assertEqual(header.declared_entity_count, 1)
        self.assertEqual(header.line_count, 1)
        self.assertIsNone(header.product_id)

    def test_parse_at_counted_three_line_header(self) -> None:
        data = (
            "700 0 1 0\r\n"
            "@4 Tool @8 ACIS 7.0 @24 Sat Apr 23 14:32:04 2022\r\n"
            "1 1e-6 1e-10\r\n"
            "body $-1 #\r\n"
            "End-of-ACIS-data\r\n"
        )
        header = parse_sat_header(data)
        self.assertEqual(header.product_id, "Tool")
        self.assertEqual(header.modeler_version, "ACIS 7.0")
        self.assertEqual(header.creation_date, "Sat Apr 23 14:32:04 2022")
        self.assertEqual(header.units_mm, 1.0)
        self.assertEqual(header.resabs, 1e-6)
        self.assertEqual(header.resnor, 1e-10)
        self.assertEqual(header.line_count, 3)

    def test_parse_plain_counted_three_line_header(self) -> None:
        data = (
            "400 0 1 0\n"
            "4 Tool 8 ACIS 7.0 24 Sat Apr 23 14:32:04 2022\n"
            "25.4 1e-6 1e-10\n"
            "body $-1 #\n"
        )
        header = parse_sat_header(data)
        self.assertEqual(header.product_id, "Tool")
        self.assertEqual(header.units_mm, 25.4)

    def test_reject_truncated_modern_header(self) -> None:
        with self.assertRaisesRegex(SatParseError, "three-line"):
            parse_sat_header("700 0 1 0\n")


class TestSatRecords(unittest.TestCase):
    HEADER = (
        "700 0 1 0\n"
        "@4 Tool @8 ACIS 7.0 @24 Sat Apr 23 14:32:04 2022\n"
        "1 1e-6 1e-10\n"
    )

    def test_frame_records_and_end_marker(self) -> None:
        document = parse_sat(
            self.HEADER
            + "body $-1 @5 a#b c value #\n"
            + "-12 point $-1 0 0 0 #\n"
            + "End-of-ACIS-data\n"
        )
        self.assertTrue(document.has_end_marker)
        self.assertEqual([record.entity_type for record in document.records], ["body", "point"])
        self.assertIsNone(document.records[0].sequence_number)
        self.assertEqual(document.records[1].sequence_number, 12)
        self.assertIn("a#b c", document.records[0].text)

    def test_end_marker_is_optional_for_legacy_files(self) -> None:
        document = parse_sat("105 1 1 0\nbody $-1 #\n")
        self.assertFalse(document.has_end_marker)
        self.assertEqual(len(document.records), 1)

    def test_reject_unterminated_record(self) -> None:
        with self.assertRaisesRegex(SatParseError, "unterminated"):
            parse_sat(self.HEADER + "body $-1\n")

    def test_reject_sat_parser_for_sab(self) -> None:
        with self.assertRaisesRegex(SatParseError, "binary SAB"):
            parse_sat(b"ACIS BinaryFile\x00\x01")


if __name__ == "__main__":
    unittest.main()
