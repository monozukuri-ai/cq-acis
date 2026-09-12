# Python releases

[`.github/workflows/release.yml`](../.github/workflows/release.yml) builds and
publishes the **Python `cq-acis` distribution**. From 0.3.2, the Python package and
all Rust crates use `[workspace.package].version` in the root `Cargo.toml`.
Every crate inherits that version, and `pyproject.toml` uses
[`dynamic = ["version"]`](https://www.maturin.rs/metadata.html#dynamic-metadata)
so maturin reads the Rust version. Release checks reject independent package
versions and stale workspace dependency pins.

Python builds use the matching workspace `acis-core` and `acis-py-bridge`.
Both sources are included in the sdist, so Python source installs need no sibling
checkout or prior Rust crate publication. Rust consumers using crates.io require
`acis-core` to be published first, followed by `acis-py-bridge` at the same version.
The Python release workflow does not publish Rust crates.

Run release checks in a clean checkout without local `[patch.crates-io]`
overrides. Refresh `Cargo.lock` after changing versions and retain `--locked`
in builds. The workspace path dependencies keep the core tested by Rust and the
core linked into Python identical, including before publication.

## Triggers and artifacts

- Publishing a GitHub Release starts validation, builds, and PyPI publication.
  Its tag must be exactly `v<workspace.package.version>` from `Cargo.toml`.
- Pushing a tag alone does not publish. The workflow must be present in the
  tagged commit when the GitHub Release is published.
- **Run workflow** (`workflow_dispatch`) performs the same build and verification
  jobs and stores artifacts, but never publishes to PyPI. To use this button,
  first merge the workflow into the default branch.

The workflow produces ABI3 wheels for Linux x86-64 (manylinux2014), Windows
x86-64, macOS Apple Silicon, and macOS Intel, plus one source archive. The native
extension uses the CPython 3.10 stable ABI (`cp310-abi3`), but the package requires
Python 3.11 or newer to match [CadQuery 2.8](https://pypi.org/project/cadquery/2.8.0/).
Rust 1.93.0 and maturin 1.11.5 are pinned. This is a release toolchain, not an MSRV
compatibility test. Each wheel is installed with its dependencies in fresh Python
3.11 and 3.12 environments. Native import, SAT/SAB decoding, model round trips,
and a valid CadQuery cube are checked outside the source checkout. The sdist is
also rebuilt and installed in an isolated environment. The source regression
suite and Rust checks must pass before packaging starts.

The clean installs require binary wheels for all dependencies. This lets pip
select a compatible Numba/llvmlite release on Intel macOS, where newer releases
no longer provide wheels, without requiring an LLVM development installation.
Resolved dependency versions are logged. A smoke test succeeds only after its
child interpreter exits normally; passing the CAD assertions alone is not enough.

On Windows the package metadata pins `casadi==3.7.2` and `nlopt==2.11.0` to keep
their SWIG runtime tables separate. Other combinations can corrupt the heap at
interpreter shutdown after `import cadquery`, even when geometry checks pass
([CasADi issue #4403](https://github.com/casadi/casadi/issues/4403),
[CadQuery issue #1564](https://github.com/CadQuery/cadquery/issues/1564)). These
constraints apply to end-user installs as well as CI. Revisit them when fixed
upstream Windows wheels are available and verify a normal process exit on both
Python 3.11 and 3.12 before removing them.

Only verified files are collected in the final `publish` job. That job alone
has `id-token: write`. It uses PyPI Trusted Publishing; no long-lived API token
or Rust publication token is needed. Third-party notices and licenses are checked
inside both distribution formats; the public corpus stays out of the packages.

## One-time PyPI configuration

For the existing `cq-acis` project, configure (or verify) this Trusted Publisher
under the project's **Publishing** settings:

| Field | Value |
| --- | --- |
| Owner | `monozukuri-ai` |
| Repository | `cq-acis` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

The GitHub job uses environment `pypi`; its name must match the PyPI registration.
No approval requirement is added by this workflow. Any existing environment
protections still apply. See [PyPI's setup instructions](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

## Cutting the next release

Choose a new shared version unused on both crates.io and PyPI. The version
prepared in this checkout is `v0.3.3`.

1. In the root `Cargo.toml`, update `[workspace.package].version` and the two
   exact version pins under `[workspace.dependencies]` to the same number.
   Run `cargo generate-lockfile` and `uv lock`, then
   `python scripts/check_python_release.py --tag v0.3.3` using the new version.
   No Python version field needs editing. The uv cache keys include the Cargo
   manifests so Rust version changes invalidate cached Python build metadata.
2. Commit the version/lockfile and workflow changes. Run **Python release**
   manually to review artifacts before publishing.
3. For a coordinated Rust release, publish `acis-core` and then `acis-py-bridge`
   at the new version. Downstream Rust projects must update their exact pins
   after these packages are available on crates.io.
4. Create the matching tag, then publish a GitHub Release for that tag. For example,
   workspace version `0.3.3` uses tag `v0.3.3`.
5. Check the final **Publish verified distributions to PyPI** job. A successful
   build or manual workflow run alone does not mean a package was published.

Before any upload, the workflow compares existing PyPI filenames and SHA-256
hashes with the complete local artifact set. Existing artifacts must be an
identical subset. Different bytes or an old wheel flavor fail before upload.
After a transient upload failure, **Re-run failed jobs** reuses the successful
build artifacts; identical uploads can be skipped. If the digest check fails,
choose a new version rather than replacing an existing release.

## Local checks

Using Python 3.11 (latest patch) or newer for the release helpers, run:

```sh
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
python -m unittest discover -s scripts/tests -v
python scripts/check_python_release.py --tag v0.3.3  # use the checkout's version
maturin build --release --locked --out wheel-check
maturin sdist --out sdist-check
python scripts/check_python_release.py --dist wheel-check
python scripts/check_python_release.py --dist sdist-check --wheels 0 --sdists 1
python scripts/smoke_python_release.py --dist wheel-check --python python3.11 --python python3.12
python scripts/smoke_python_release.py --dist sdist-check --sdist
```

The smoke commands create temporary virtual environments, install CadQuery and
its dependencies, and require network access or a populated package cache. The
sdist rebuild also requires Rust and maturin on the invoking Python interpreter.
`maturin sdist` does not accept `--locked`; the subsequent Rust build does.

Reference: [maturin distribution documentation](https://www.maturin.rs/distribution.html).
