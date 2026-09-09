# Python releases

[`.github/workflows/release.yml`](../.github/workflows/release.yml) builds and
publishes the **Python `cq-acis` distribution**. The `acis-core` Rust crate has
its own publication lifecycle. Python builds use the checked-out workspace core;
its source is included in the sdist, so source installs need no sibling checkout.

## Triggers and artifacts

- Publishing a GitHub Release starts validation, builds, and PyPI publication.
  Its tag must be exactly `v<project.version>` from `pyproject.toml`.
- Pushing a tag alone does not publish. The workflow must be present in the
  tagged commit when the GitHub Release is published.
- **Run workflow** (`workflow_dispatch`) performs the same build and verification
  jobs and stores artifacts, but never publishes to PyPI. To use this button,
  first merge the workflow into the default branch.

The workflow produces Python 3.10 ABI3 wheels for Linux x86-64 (manylinux2014),
Windows x86-64, macOS Apple Silicon, and macOS Intel, plus one source archive.
Rust 1.93.0 and maturin 1.11.5 are pinned. This is a release toolchain, not an MSRV
compatibility test. Each wheel is installed with its dependencies in fresh Python
3.10 and 3.11 environments. Native import, SAT/SAB decoding, model round trips,
and a valid CadQuery cube are checked outside the source checkout. The sdist is
also rebuilt and installed in an isolated environment. The source regression
suite and Rust checks must pass before packaging starts.

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

At implementation time (2026-09-09), [PyPI `cq-acis` 0.1.0](https://pypi.org/project/cq-acis/0.1.0/)
already contains the earlier pure Python wheel and source archive. Select a **new
Python version** for the Rust-backed release; do not reuse `v0.1.0`.

1. Update `[project].version` in `pyproject.toml` and refresh `uv.lock` with
   `uv lock`. The Python release version does not need to match the Rust workspace
   version: publishing a new Python binding does not require republishing an
   unchanged `acis-core` crate.
2. Commit the version/lockfile and workflow changes. Run **Python release**
   manually to review artifacts before publishing.
3. Create the matching tag, then publish a GitHub Release for that tag. For example,
   Python version `0.1.1` uses tag `v0.1.1`.
4. Check the final **Publish verified distributions to PyPI** job. A successful
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
python -m unittest discover -s scripts/tests -v
python scripts/check_python_release.py --tag v0.1.0  # use the checkout's version
maturin build --release --locked --out wheel-check
maturin sdist --out sdist-check
python scripts/check_python_release.py --dist wheel-check
python scripts/check_python_release.py --dist sdist-check --wheels 0 --sdists 1
python scripts/smoke_python_release.py --dist wheel-check --python python3.10 --python python3.11
python scripts/smoke_python_release.py --dist sdist-check --sdist
```

The smoke commands create temporary virtual environments, install CadQuery and
its dependencies, and require network access or a populated package cache. The
sdist rebuild also requires Rust and maturin on the invoking Python interpreter.
`maturin sdist` does not accept `--locked`; the subsequent Rust build does.

Reference: [maturin distribution documentation](https://www.maturin.rs/distribution.html).
