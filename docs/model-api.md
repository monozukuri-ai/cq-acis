# Shared model API

English | [日本語](model-api.ja.md)

## Constructing a model

`cq_acis.model` provides `AcisModel`, `AcisMetadata`, and the geometry/entity
types independently of SAT framing. External decoders can construct
`AcisModel(metadata=..., entities=...)` directly; a `SatHeader`, `SatEntityGraph`,
or text `SatRecord` is not required. The same `to_cadquery()` and
`convert_model()` functions accept both this model and the existing `SatModel`.

For existing SAT callers:

```python
from pathlib import Path
from cq_acis import convert_model, parse_sat_model

sat_model = parse_sat_model(Path("model.sat").read_bytes())
model = sat_model.as_acis_model()
shapes = convert_model(model)

assert model.metadata == sat_model.metadata
assert model.entities is sat_model.entities
# Existing access to sat_model.graph and raw.record still works.
```

Adapter contracts:

- Use contiguous, zero-based model indices for `EntityRef`; `-1` is null.
  Keep source record IDs in `RawEntity.entity_id`. Construction validates
  indices and reference closure, not geometry or source-format compatibility.
- Put length units and tolerances in `AcisMetadata`: `units_mm` is millimetres
  per source unit, `resabs` uses source length units, and `resnor` is
  dimensionless. Missing source values remain `None`. For compatibility, the
  converter still defaults missing units to 1 mm and missing absolute tolerance
  to 1e-6 source units; external decoders should supply known values explicitly.
- Preserve source encoding, save version, producer and dialect in metadata.
  The application year and kernel save version are separate values.
- A `RawEntity` can omit `record` and instead retain binary `raw_data` and a
  `SourceSpan(source_id, start_offset, end_offset)`. Spans are half-open byte
  ranges in the named domain, including decompressed streams where applicable.
- Keep unknown entities as `RawEntity` and adapter reports in
  `AcisModel.diagnostics` (`AcisDiagnostic`). Unsupported geometry referenced
  by a converted body raises `CadQueryConversionError`; an undecoded raw body
  is also rejected. Other retained records and diagnostics are not proof of
  complete conversion and should be inspected by callers.

## Native models and compatibility

Existing public entity imports and `SatModel(graph, entities)` remain available.
Python entities support their dataclass constructors, equality, and
`dataclasses.replace`.

```python
native = model.to_native()  # Immutable snapshot of the model's values.
assert native.to_model() == model
shapes = convert_model(native)
```

`NativeModel` accepts the same conversion operations as `AcisModel`. Its
properties and `to_model()` return Python values without preserving the original
Python object identities. Source bytes and arbitrary-precision source integers
are retained. Model references fit signed 64-bit indices (`-1` is null); offsets
and lengths must fit the native address range. Invalid source spans and dangling
diagnostic targets are rejected. Represent unsupported classes or values with
`RawEntity` and bytes.

The shared dataclass contract is identified by
`cq_acis.model.MODEL_API_VERSION == 2`. This is separate from the package release
number. Rust extensions should use matching `acis-core`, `acis-py-bridge`, and
Python `cq-acis` versions. See the [bridge API](../crates/acis-py-bridge/README.md).

Additional views expose qualified raw geometry through
`NativeModel.tolerant_topology(reference)`, `subtype_table`,
`resolve_subtype(reference)`, and `linear_surface_pcurve(pcurve_ref, surface_ref)`.
The source entities remain raw. A view or subtype index does not establish
complete geometry support; see [geometry support](geometry-support.md) and
[tolerant trims](tolerant-trims.md).

Since 0.3.4: `NativeModel.spline_surface_pcurve(pcurve_ref, surface_ref)` returns the bounded `SplineSurfacePcurve` view described in [tolerant trims](tolerant-trims.md).

Unreleased: `TolerantCoedge.inline_curve` and `NativeModel.supported_curve()` retain full associated curves and their source support/UV provenance. See [tolerant trims](tolerant-trims.md).
