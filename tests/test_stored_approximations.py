"""Stored B-spline fits of procedural ASM curves are used as derived geometry."""

from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import unittest

from cq_acis import (
    NULL_REF,
    BSplineCurveEntity,
    CadQueryConversionError,
    CadQueryConverter,
    EdgeEntity,
    NativeModel,
    RawEntity,
    StraightCurveEntity,
    parse_sab_model,
)

ROOT = Path(__file__).resolve().parents[1]
CUBE = ROOT / "corpus" / "data" / "ezdxf" / "cube_asm_sab_22300.sab"
OCP_AVAILABLE = importlib.util.find_spec("OCP") is not None
FIT_TOLERANCE = 1e-3


def cube_with_fitted_edge(*, stored: bool = True, sense: bytes = b"\x0b"):
    """Replace one straight edge curve of the cube by an `int_int_cur` record.

    The record carries a cubic fit of the same segment in the edge's own
    parameter, as ASM stores beside a procedural intersection curve. With
    ``stored=False`` the fit is absent (`nullbs`), as helical curves are saved.
    """
    model = parse_sab_model(CUBE.read_bytes(), source_id=CUBE.name)
    edge = next(
        e for e in model.entities
        if isinstance(e, EdgeEntity) and not e.reversed
        and isinstance(model.resolve(e.curve), StraightCurveEntity)
        and e.start_parameter is not None and e.start_parameter < e.end_parameter
    )
    line = model.resolve(edge.curve)
    start, end = edge.start_parameter, edge.end_parameter
    if sense == b"\x0a":
        # A reversed record stores the fit in the negated parameter.
        knots = (-end, -start)
        fractions = (1.0, 2 / 3, 1 / 3, 0.0)
    else:
        knots = (start, end)
        fractions = (0.0, 1 / 3, 2 / 3, 1.0)
    poles = []
    for fraction in fractions:
        point = line.origin + line.direction * (start + (end - start) * fraction)
        poles.extend((point.x, point.y, point.z))
    fit = (
        ("nubs", 3, 0, 2, knots[0], 3, knots[1], 3, *poles, FIT_TOLERANCE)
        if stored else ("nullbs",)
    )
    values = (
        NULL_REF, sense, b"\x0f", "int_int_cur", 22220, 0, *fit,
        "null_surface", "null_surface", "nullbs", "nullbs", b"\x10", b"\x0b", b"\x0b",
    )
    fitted = RawEntity(line.index, "intcurve-curve", NULL_REF, None, values)
    entities = tuple(fitted if e.index == line.index else e for e in model.entities)
    return replace(model, entities=entities), edge, fitted


@unittest.skipUnless(CUBE.exists(), "Populate the ezdxf corpus to run stored-fit checks")
class TestStoredApproximationView(unittest.TestCase):
    def test_native_view_returns_the_fit_and_its_provenance(self) -> None:
        model, edge, fitted = cube_with_fitted_edge()
        stored = NativeModel.from_model(model).stored_approximation(edge.curve)
        geometry, kind, fit_tolerance, definition_entity, closure = stored
        self.assertIsInstance(geometry, BSplineCurveEntity)
        self.assertEqual((kind, fit_tolerance, definition_entity, closure),
                         ("int_int_cur", FIT_TOLERANCE, None, (0, 0)))
        self.assertEqual(geometry.raw, fitted)
        self.assertEqual(geometry.knots, (edge.start_parameter, edge.end_parameter))
        self.assertEqual(geometry.multiplicities, (4, 4))
        self.assertEqual(geometry.fit_tolerance, FIT_TOLERANCE)
        # The parsed model is unchanged: the record itself stays raw.
        self.assertIsInstance(model.resolve(edge.curve), RawEntity)

    def test_reversed_record_runs_the_fit_backwards(self) -> None:
        model, edge, _ = cube_with_fitted_edge(sense=b"\x0a")
        geometry, *_ = NativeModel.from_model(model).stored_approximation(edge.curve)
        self.assertEqual(geometry.knots, (edge.start_parameter, edge.end_parameter))
        line = parse_sab_model(CUBE.read_bytes()).resolve(edge.curve)
        for parameter in (edge.start_parameter, edge.end_parameter):
            expected = line.origin + line.direction * parameter
            actual = geometry.evaluate(parameter)
            self.assertAlmostEqual((actual - expected).magnitude, 0.0, places=9)

    def test_record_without_a_stored_fit_has_no_view(self) -> None:
        model, edge, _ = cube_with_fitted_edge(stored=False)
        native = NativeModel.from_model(model)
        self.assertIsNone(native.stored_approximation(edge.curve))
        self.assertIsNone(native.stored_approximation(edge.start_vertex))


@unittest.skipUnless(CUBE.exists() and OCP_AVAILABLE, "needs the ezdxf corpus and OCP")
class TestStoredApproximationConversion(unittest.TestCase):
    def test_fitted_edge_converts_and_is_reported_as_an_approximation(self) -> None:
        for sense in (b"\x0b", b"\x0a"):
            with self.subTest(sense=sense):
                model, edge, _ = cube_with_fitted_edge(sense=sense)
                converter = CadQueryConverter(model, backend="occt")
                (solid,) = converter.convert()
                self.assertTrue(solid.isValid())
                self.assertAlmostEqual(solid.Volume(), 777.0**3, places=3)
                self.assertEqual((len(solid.Faces()), len(solid.Edges()), len(solid.Vertices())),
                                 (6, 12, 8))
                unit = model.metadata.units_mm or 1.0
                self.assertEqual(converter.approximations, [{
                    "entity": edge.curve.index, "type": "intcurve-curve", "subtype": "int_int_cur",
                    "fit_tolerance_source_units": FIT_TOLERANCE,
                    "fit_tolerance_mm": FIT_TOLERANCE * unit,
                    "definition_entity": None,
                    "code": "geometry.approximated_from_stored_spline",
                }])
                self.assertEqual(converter.approximation_failures, {})

    def test_exact_model_reports_no_approximation(self) -> None:
        model = parse_sab_model(CUBE.read_bytes(), source_id=CUBE.name)
        converter = CadQueryConverter(model, backend="occt")
        converter.convert()
        self.assertEqual(converter.approximations, [])

    def test_missing_fit_stays_an_unsupported_curve(self) -> None:
        model, _, _ = cube_with_fitted_edge(stored=False)
        with self.assertRaises(CadQueryConversionError) as raised:
            CadQueryConverter(model, backend="occt").convert()
        self.assertEqual(raised.exception.code, "geometry.curve_unsupported")


if __name__ == "__main__":
    unittest.main()
