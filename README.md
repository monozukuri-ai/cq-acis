# cq-acis

Parse ACIS SAT/SAB data and convert supported B-rep geometry to
CadQuery/OpenCascade shapes.

日本語版: [README.ja.md](README.ja.md)

> This project is experimental. Supported geometry depends on the save version
> and producer. Unsupported entities remain available as raw records; conversion
> raises an error when it cannot build the requested shape within source
> precision. Projected 2D trims are checked against the unchanged 3D curves.

## Features

- Read legacy and modern SAT headers, counted strings, and entity references.
- Decode SAT save versions 105, 400, 600, and 700, plus selected SAB and
  Autodesk ShapeManager binary profiles.
- Convert supported lines, circles, ellipses, planes, cylinders, cones,
  spheres, and tori, with experimental support for explicit NURBS and
  selected tolerant boundaries.
- Inspect topology, metadata, diagnostics, and the source data of unknown records.
- Use a shared model API to connect external decoders to the CadQuery converter.

See [geometry support and limitations](docs/geometry-support.md) and
[SAB/ASM support](docs/sab-support.md) for the accepted profiles.

## Installation

Requires **Python 3.11 or newer**. CadQuery 2.8 or later is installed as a dependency.

```bash
python -m pip install cq-acis
```

Installing a prebuilt wheel does not require Rust. To install from a source
checkout, install Rust 1.83 or newer and a C linker first, then run:

```bash
python -m pip install -e .
```

CadQuery's platform requirements also apply.

## Quick start

Parse SAT records and follow topology references:

```python
from pathlib import Path
from cq_acis import parse_sat_model

model = parse_sat_model(Path("model.sat").read_bytes())
for body in model.bodies():
    lump = model.resolve(body.lump)
    print(body.index, lump.index if lump else None)
```

Import a SAT file as a CadQuery `Workplane`:

```python
from cq_acis import import_sat_file

result = import_sat_file("model.sat")
shape = result.val()
assert shape.isValid()
print(shape.Volume())
```

For binary SAB/ASM input:

```python
from pathlib import Path
from cq_acis import parse_sab_model, to_cadquery

model = parse_sab_model(Path("model.sab").read_bytes(), source_id="model.sab")
print(model.diagnostics)
result = to_cadquery(model)
```

Parsing a file does not guarantee that all its geometry can be converted.
See [usage and error handling](docs/usage.md).

## Documentation

- [Documentation index](docs/README.md)
- [Usage, export, and visual inspection](docs/usage.md)
- [Shared model API](docs/model-api.md)
- [Geometry support and limitations](docs/geometry-support.md)
- [SAB/ASM support and history limitations](docs/sab-support.md)
- [Tolerant boundaries and finite UV trims](docs/tolerant-trims.md)
- Rust APIs: [acis-core](crates/acis-core/README.md),
  [acis-py-bridge](crates/acis-py-bridge/README.md)

The public API and supported format subset may change as coverage expands.

## License

The project code is licensed under the [MIT License](LICENSE). See
[third-party notices](THIRD_PARTY_NOTICES.md) for dependency attribution.
The repository's [test corpus](corpus/README.md) is excluded from the Python
distributions and has separate [license notices](corpus/licenses/).
