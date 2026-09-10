# cq-acis

Parse ACIS SAT/SAB data and convert the supported analytic B-rep subset to
CadQuery/OpenCascade shapes.

日本語版: [README.ja.md](README.ja.md)

> This project is experimental. ACIS SAT versions and producer-specific
> records vary, so unsupported entities are preserved as raw records and
> conversion fails explicitly when an exact shape cannot be built.

## Features

- SAT container detection and ASCII record framing
- Legacy one-line and modern three-line SAT headers
- Counted `@<length>` strings used by SAT 7 and later
- SAB and Autodesk ShapeManager SAB parsing for explicitly admitted profiles
- Entity-reference graph validation for `$n` pointers
- Typed decoding for SAT save versions 105, 400, 600, and 700
- Typed topology and analytic geometry entities:
  `body`, `lump`, `shell`, `face`, `loop`, `coedge`, `edge`, `vertex`,
  `point`, `straight-curve`, `ellipse-curve`, `plane-surface`,
  `cone-surface`, `sphere-surface`, `torus-surface`, and `transform`
- Exact CadQuery conversion for line, circular/elliptical edge, plane,
  cylindrical (including elliptical), circular-conical and qualified sphere/torus geometry
- Splitting of non-manifold ACIS shells into valid CadQuery solids and
  compounds
- Preservation of unsupported records as `RawEntity`
- Reusable Rust `acis-core` models, reference validation, and analytic helpers,
  with a PyO3 binding and the existing Python dataclass API

M4 adds an experimental explicit SAT 700 `exactsur` NURBS surface adapter.
It also admits an experimental ASM 22700 / embedded 22601 direct explicit
NURBS profile, proved cone-apex degeneracies, circular sphere holes, and
elliptical-cone isosections. Other native spline profiles and non-similarity
placements remain unsupported. Projected 2D trims are numerically checked against unchanged 3D
curves at source precision. See [M4 scope and validation](docs/m4-geometry.md).
The 0.3.1 development version adds partial tolerant topology and nested subtype
views while keeping model API 2, and requires core/bridge 0.2.1;
registry-only releases require their separate publication first.

## Installation

The CadQuery converter is installed with the default dependencies:

```bash
python -m pip install cq-acis
```

For a source checkout, install Rust (1.83 or newer) and a C linker first.
The native extension is built by maturin:

```bash
python -m pip install -e .
```

## Quick start

Parse SAT records and resolve topology references:

```python
from cq_acis import BodyEntity, parse_sat_model

with open("model.sat", "rb") as source:
    model = parse_sat_model(source.read())

for body in model.bodies():
    assert isinstance(body, BodyEntity)
    lump = model.resolve(body.lump)
    print(body.index, lump.index if lump else None)
```

Convert the bodies to a CadQuery `Workplane`:

```python
from cq_acis import import_sat_file

result = import_sat_file("model.sat")
shape = result.val()
assert shape.isValid()
print(shape.Volume())
```

## Shared model for external decoders

`cq_acis.model` provides `AcisModel`, `AcisMetadata`, and the geometry/entity
types independently of SAT framing. External decoders can construct
`AcisModel(metadata=..., entities=...)` directly; a `SatHeader`, `SatEntityGraph`,
or text `SatRecord` is not required. The same `to_cadquery()` and new
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

All existing public entity imports and the `SatModel(graph, entities)`
constructor remain available. SAT framing and schema decoding are still Python;
SAB/ASM binary decoding now runs in Rust; Inventor CFB/RSe extraction is implemented
in the separate `inventor-kit` project. See [binary support](docs/sab-support.md).

## Rust core and Python boundary

[`crates/acis-core`](crates/acis-core) owns all 14 typed entity variants, raw
values, metadata, diagnostics, reference validation/resolution, vector math,
ellipse/cone evaluation, and transform calculations. It can be a direct Cargo
dependency of an Inventor decoder without Python or CadQuery. See its
[README](crates/acis-core/README.md) for a local dependency example.

[`crates/cq-acis-py`](crates/cq-acis-py) provides the [PyO3](https://pyo3.rs/)
boundary. The Python dataclasses preserve constructors, imports, equality,
`dataclasses.replace`, and the identity of existing model entities. Their math
and `AcisModel` validation/resolution call Rust. No Python fallback silently
substitutes for a missing extension; build/install it before running from source.

For a model owned entirely by Rust:

```python
native = model.to_native()  # Immutable snapshot; no SAT serialization/reparsing.
assert native.to_model() == model
shapes = convert_model(native)
```

`NativeModel` implements the converter's model interface. Its properties and
`to_model()` create Python dataclasses with equal values, without retaining
Python entity objects or their identities. The CadQuery adapter materializes
this Python view once per converter, avoiding repeated field copies during
topology traversal. Conversion copies fields directly,
including bytes and arbitrary-precision source integers; it does not use JSON.
Model references fit signed 64-bit indices, with `-1` for null, while offsets
and lengths fit the native address range. Invalid source spans and dangling
diagnostic targets are also rejected. Unknown entity classes/values must be
represented by `RawEntity`/bytes instead of being silently dropped.

The [maturin](https://www.maturin.rs/project_layout.html) build creates a mixed
Python/Rust wheel using the CPython 3.10 stable ABI. The package requires
**Python 3.11 or newer** because it depends on CadQuery 2.8+. Wheel installation
does not need Rust; source installation does. CadQuery's platform requirements
still apply. An abi3 tag alone does not demonstrate testing on
every Python version or operating system.

## Example and visual inspection

[`examples/parse_sat.py`](examples/parse_sat.py) parses a SAT file, prints body
statistics, and exports STEP, STL, and SVG files.

```bash
PYTHONPATH=src python examples/parse_sat.py
PYTHONPATH=src python examples/parse_sat.py path/to/model.sat \
  --output-dir /tmp/cq-acis-output
```

Open the generated STL or STEP in any 3D CAD viewer. With the optional
`ocp_vscode` viewer installed, try:

```bash
PYTHONPATH=src python examples/parse_sat.py --show
```

## Supported entities and conversion scope

The parser currently has typed support for:

```text
body, lump, shell, face, loop, coedge, edge, vertex,
point, straight-curve, ellipse-curve,
plane-surface, cone-surface, transform
```

Typed support does not imply that every entity can already be converted to a
CadQuery shape. Conversion is exact-only and raises `CadQueryConversionError`
for unsupported geometry.

## Development corpus

The pinned development corpus is not included in the Python wheel. It is kept
in this repository for parser and conversion regression tests. Sources,
upstream commits, and SHA-1 values are recorded in
[`corpus/sources.lock.json`](corpus/sources.lock.json); downloaded file hashes
and SAT metadata are recorded in
[`corpus/manifest.jsonl`](corpus/manifest.jsonl).

```bash
python scripts/fetch_corpus.py
python scripts/fetch_corpus.py --check
```

Review [`corpus/README.md`](corpus/README.md) and `corpus/licenses/` before
redistributing third-party files.

## Testing

Run the full test suite from a source checkout, with its virtual environment active:

```bash
python -m pip install maturin
maturin develop
cargo test -p acis-core --locked
PYTHONPATH=src python -m unittest discover -s tests -v
```

The pinned corpus currently covers 25 artifacts, including 23 SAT files and 2
SAB files. CadQuery regression tests convert 23 SAT artifacts and 147 bodies.
Native tests round-trip all 62,530 entities through Rust and cover SAT-free
geometry, source bytes/integers, model validation, and Python API compatibility.

## Project status

The package is under active development. The public API and supported SAT
subset may change while broader producer/version coverage is added.

## License

The project code is licensed under the [MIT License](LICENSE). Third-party
corpus files have separate notices under [`corpus/licenses/`](corpus/licenses/);
consult those notices before redistribution.

## SAB / ASM (stage 3)

`parse_sab_model(data, source_id="model.sab")` decodes the admitted binary
profiles directly through Rust. See [bounded support and history limitations](docs/sab-support.md).

## Python release CI

Publishing a GitHub Release tagged `v<pyproject version>` builds and validates
Linux, Windows, macOS ARM64/Intel ABI3 wheels and an sdist, then publishes to PyPI
with Trusted Publishing. Manual workflow runs build and verify without uploading.
See [release setup, versioning, and retry instructions](docs/releasing.md).
