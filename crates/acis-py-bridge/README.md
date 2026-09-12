# acis-py-bridge

Convert between Rust `AcisModel` values and Python `cq_acis.model` dataclasses
in a Python extension. Use matching `acis-core`, `acis-py-bridge`, and Python
`cq-acis` versions.

`model_from_python` and `model_to_python` validate the model API version (`2`)
and retain source spans, unknown bytes, arbitrary precision integers, and
diagnostics. Install the matching Python
`cq-acis` release at runtime; `cq_acis.model.MODEL_API_VERSION` remains `2`.

The model API version describes dataclass layouts and is separate from the
release number.

For the 0.3.3 model bridge:

```toml
[dependencies]
acis-py-bridge = "=0.3.3"
```

See the [shared model API](https://github.com/monozukuri-ai/cq-acis/blob/main/docs/model-api.md)
for reference, metadata, and raw-data contracts.
