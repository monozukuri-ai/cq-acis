# ACIS test corpus

This directory contains the pinned data, provenance, licensing information,
and integrity metadata used for parser and CadQuery regression tests.

## Managed files

- `sources.lock.json`: upstream repositories, commits, Git blob hashes, and
  extraction instructions
- `manifest.jsonl`: SHA-256 hashes, sizes, SAT headers, and entity statistics
  generated after fetching the artifacts
- `licenses/`: license and redistribution notices copied from the pinned
  upstream revisions
- `data/`: downloaded SAT/SAB test artifacts

`manifest.jsonl` and `data/` can be regenerated deterministically with
`python scripts/fetch_corpus.py`.

## Included sources

### NIST Engineering Design Models

The corpus includes the ACIS SAT files under
`models/ACIS/NIST`. Several models are represented in raw, healed,
feature-added, and healed-plus-feature-added forms. These variants exercise
legacy SAT versions, producer-specific attributes, and healing differences.

The NIST notice is preserved in
[`licenses/NIST-engineering-design-models-LICENSE.md`](licenses/NIST-engineering-design-models-LICENSE.md).
The notice describes NIST-created material as generally public domain in the
United States, while warning that third-party material may be present. Check
the full notice and upstream history before redistribution.

### ezdxf

The ezdxf test sources provide these fixtures:

- SAT save version 400 cube
- SAT save version 700 cube
- SAT save version 700 prism
- Autodesk ShapeManager SAB version 21800 cube
- Autodesk ShapeManager SAB version 22300 cube

ezdxf is distributed under the MIT License. The notice is preserved in
[`licenses/ezdxf-LICENSE`](licenses/ezdxf-LICENSE).

## Operating rules

- Fetch pinned commits from `sources.lock.json`, never an upstream branch tip.
- Verify the upstream Git blob SHA-1 before storing a downloaded file.
- Verify manifest SHA-256 values and sizes in CI.
- Do not vendor external samples with unclear redistribution terms; record the
  URL and local hash separately until licensing is resolved.
- Build corruption fixtures from redistributable or self-generated data.
