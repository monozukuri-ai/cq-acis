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

## Additional data candidates (P1)

The current P0 corpus contains 1,896 `ellipse-curve` entities, all with ratio
1.0, and 908 `cone-surface` entities, all with ratio 1.0 and
`sin_half_angle=0`. It is therefore sufficient for circular-edge and
cylindrical-surface coverage, but lacks real-data coverage for non-circular
ellipses and cones. Until suitable real files are added, generated fixtures
are used to test analytic curve and surface construction.

- The UMD CIM educational [cube with the cylindrical hole SAT example](https://isr.umd.edu/Labs/CIM/vm/xlator/acis.html)
  is a small, readable SAT 105 cylindrical-hole model. Its public page does
  not state redistribution terms, so the example is recorded as a URL only
  and is not vendored here.
- The `acadrust` [`SatDocument` builder](https://docs.rs/acadrust/latest/acadrust/entities/acis/types/struct.SatDocument.html)
  provides `add_ellipse_curve` and `add_cone_surface` under the MPL-2.0
  project license. It can generate minimal reproducible fixtures, but is not
  a replacement for real CAD exports.
- Public ACIS 7.0 format excerpts and ellipse/cone record examples are
  available in [Paul Bourke's SAT notes](https://paulbourke.net/dataformats/sat/sat.pdf).
  These notes are used for format research only; their redistribution terms
  should be checked before copying data into this repository.

When vendoring a P1 artifact, add its URL, retrieval date, SHA-256, license,
and the entity distribution proving that it contains a real ellipse or cone
to `sources.lock.json` and `manifest.jsonl`.

## Operating rules

- Fetch pinned commits from `sources.lock.json`, never an upstream branch tip.
- Verify the upstream Git blob SHA-1 before storing a downloaded file.
- Verify manifest SHA-256 values and sizes in CI.
- Do not vendor external samples with unclear redistribution terms; record the
  URL and local hash separately until licensing is resolved.
- Build corruption fixtures from redistributable or self-generated data.
