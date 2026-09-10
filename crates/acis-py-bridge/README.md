# acis-py-bridge

Shared Rust-to-Python conversion for the `cq_acis.model` dataclasses. The crate
has no `PyInit` entry point and exports no Python type, so multiple extensions
can use it without registering duplicate native classes. `acis-core` remains
independent of Python. This crate depends on crates.io `acis-core =0.2.1`.

`model_from_python` and `model_to_python` validate the model API version (`1`)
and retain source spans, unknown bytes, arbitrary precision integers, and
diagnostics without a SAT or JSON intermediate. Python `cq-acis>=0.2,<0.3`
with `cq_acis.model.MODEL_API_VERSION == 1` must be installed at runtime.

The shared bridge must be published before downstream registry-only builds.
Run `cargo publish --dry-run -p acis-py-bridge --locked` to verify the package;
this command does not publish it. Development overrides belong in an explicit
Cargo `--config` file, not in a downstream release manifest.

The additive extension-view writers in 0.2.1 require cq-acis >=0.3.1,<0.4.
Existing model API 2 dataclass layouts are unchanged; ordinary model conversion
retains its cq-acis >=0.3.0,<0.4 contract.
