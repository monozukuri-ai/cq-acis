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
- SAB and Autodesk ShapeManager SAB preamble detection
- Entity-reference graph validation for `$n` pointers
- Typed decoding for SAT save versions 105, 400, 600, and 700
- Typed topology and analytic geometry entities:
  `body`, `lump`, `shell`, `face`, `loop`, `coedge`, `edge`, `vertex`,
  `point`, `straight-curve`, `ellipse-curve`, `plane-surface`,
  `cone-surface`, and `transform`
- Exact CadQuery conversion for line, circular/elliptical edge, plane,
  cylindrical, and circular-conical geometry
- Splitting of non-manifold ACIS shells into valid CadQuery solids and
  compounds
- Preservation of unsupported records as `RawEntity`

Elliptical cones, elliptical cylinders, sheared placements, and unsupported
surface/curve types are rejected rather than approximated.

## Installation

The CadQuery converter is installed with the default dependencies:

```bash
python -m pip install cq-acis
```

For a source checkout:

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

Run the full test suite from a source checkout:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The pinned corpus currently covers 25 artifacts, including 23 SAT files and 2
SAB files. CadQuery regression tests convert 23 SAT artifacts and 147 bodies.

## Project status

The package is under active development. The public API and supported SAT
subset may change while broader producer/version coverage is added.

## License

The project code is licensed under the [MIT License](LICENSE). Third-party
corpus files have separate notices under [`corpus/licenses/`](corpus/licenses/);
consult those notices before redistribution.
