# Usage

Install `cq-acis` as described in the [README](../README.md#installation).

## Parse and convert

`parse_sat_model(data)` accepts SAT text or bytes and returns a `SatModel`.
`parse_sab_model(data, source_id=...)` accepts binary bytes and returns an
`AcisModel`. Both models expose `bodies()`, `resolve()`, metadata, and entities.

```python
from pathlib import Path
from cq_acis import convert_model, parse_sat_model, to_cadquery

model = parse_sat_model(Path("model.sat").read_bytes())
shapes = convert_model(model)  # Tuple of CadQuery shapes, one per source body.
result = to_cadquery(model)    # CadQuery Workplane containing those shapes.
```

For a SAT file, `import_sat_file(path)` combines parsing and conversion.
`import_sat_data(data)` does the same for SAT text or bytes. Binary input uses
`parse_sab_model()` followed by `convert_model()` or `to_cadquery()`; see
[SAB/ASM support](sab-support.md).

## Errors and diagnostics

Unsupported records are retained as `RawEntity`. A successful parse is not a
guarantee that the model can form a complete shape. Inspect
`AcisModel.diagnostics` and retained raw records when assessing completeness.

```python
from cq_acis import CadQueryConversionError, convert_model

try:
    shapes = convert_model(model)
except CadQueryConversionError as error:
    print(error.code, str(error))
```

`CadQueryConversionError.code` identifies failures such as unsupported geometry,
trim mismatch, invalid faces, and open shells. A partially converted body is
not returned as a successful solid. See [geometry limits](geometry-support.md)
and the [model API](model-api.md) for raw data and diagnostic handling.

## Export and visual inspection

Use CadQuery's exporters on a converted shape:

```python
import cadquery as cq
from cq_acis import import_sat_file

shape = import_sat_file("model.sat").val()
assert shape.isValid()
cq.exporters.export(shape, "model.step", "STEP")
cq.exporters.export(shape, "model.stl", "STL")
cq.exporters.export(shape, "model.svg", "SVG")
```

Open STEP or STL files in a CAD viewer. For a model with multiple bodies, export
each shape returned by `convert_model()` to retain every body.

The repository includes [`examples/parse_sat.py`](../examples/parse_sat.py),
which prints body statistics and exports each body's STEP, STL, and SVG files.
After installing the source checkout, run these commands from its root:

```bash
python examples/parse_sat.py
python examples/parse_sat.py path/to/model.sat --output-dir /tmp/cq-acis-output
```

The default input is the repository's SAT cube fixture. The example and test
corpus are not included in the Python distributions. If the optional
`ocp_vscode` viewer is installed, use `python examples/parse_sat.py --show` for
interactive viewing.
