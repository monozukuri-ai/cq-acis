# acis-py-bridge

Shared Rust-to-Python conversion for the `cq_acis.model` dataclasses. The crate
has no `PyInit` entry point and exports no Python type, so multiple extensions
can use it without registering duplicate native classes. `acis-core` remains
independent of Python. This crate uses the matching workspace `acis-core` during
development and the same exact version from crates.io after publication.

`model_from_python` and `model_to_python` validate the model API version (`2`)
and retain source spans, unknown bytes, arbitrary precision integers, and
diagnostics without a SAT or JSON intermediate. Install the matching Python
`cq-acis` release at runtime; `cq_acis.model.MODEL_API_VERSION` remains `2`.

Publish `acis-core` first, then this bridge, before downstream registry-only builds.
Run `cargo publish --dry-run -p acis-py-bridge --locked` to verify the package;
this command does not publish it. Development overrides belong in an explicit
Cargo `--config` file, not in a downstream release manifest.

From 0.3.2, Rust and Python packages share the workspace version. The model API
version describes dataclass layouts and is separate from the release number.
