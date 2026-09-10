# Stage 3: bounded SAB / ASM reader

`parse_sab_model(bytes, source_id=...)` calls `acis_core::sab::parse_sab` through
PyO3. It returns the existing `AcisModel`, with no intermediate SAT text or JSON.
`NativeModel` and the existing SAT / CadQuery APIs remain available.

## Profile gates

| Container | Accepted save versions | Evidence |
| --- | --- | --- |
| ACIS BinaryFile, 4-byte words | 21800 | ezdxf cube, 115 records, valid 777 mm cube |
| ASM BinaryFile4 | 22000, 22300, 22600, 22700, 22900, 23200 | 22300 ezdxf cube; other versions extracted structurally from 25 public Inventor parts |
| ASM BinaryFile8 | same ASM version gate | Synthetic framing/64-bit integer tests only; no native Inventor eight-byte fixture validated |

Every accepted version still has to pass its complete record grammar and
reference closure. These are exact save-format numbers, not an Inventor product
release range. Other save versions and signatures raise `ValueError`.

The currently typed entities are body, lump, shell, face, loop, coedge, edge,
vertex, point, straight, ellipse, plane, cone/cylinder, sphere, torus and transform. Names with
`-curve` / `-surface` suffixes are admitted. Each decoder must consume all fields;
an unfamiliar layout remains `RawEntity` with `sab.entity_schema_unsupported`.
M4 retains negative cone cosine and a separate `parameter_scale`; evaluation
uses a documented canonical chart. Raw source ranges are not treated as OCCT
coordinates. See [M4 geometry](m4-geometry.md) for conversion and NURBS limits. Unknown entities and attributes
remain raw. Tags 22 and 23 retain their payload bytes without interpreting them.

`raw_data` is the exact record slice; `SourceSpan` uses the supplied source byte
domain. `record` is `None`: binary input never gets a fabricated SAT attachment.
All source references in the active table must resolve within that table.
History beginning at a reserved history marker is retained as one explicitly
named `__opaque_sab_history__` raw attachment, outside the source index namespace.
Active references cannot resolve to that attachment. Its contents and terminal
framing are not validated or replayed. Corruption exclusively in that suffix is
therefore not detected by this reader. The returned geometry represents only the
stored table, not proof of the current Inventor feature/history state.

Default limits: 64 MiB input, 500,000 records including a history attachment,
4,000,000 tokens, 4 MiB strings, subtype depth 64. Unknown tags, truncated active
records, invalid references, unbalanced subtypes, and limit violations fail.

## Rust adapter reuse

`cq-acis-py` now also builds an rlib. A downstream PyO3 crate can depend on it
with `default-features = false` and call `model_to_python(py, model)` to create
existing cq-acis Python dataclasses. This feature setting omits cq-acis's module
entry point; it avoids duplicate `PyInit` exports. The Rust core remains free of
Python/CadQuery dependencies. Both Python packages must use this stage-3 checkout
until compatible releases are published; the old PyPI version is not sufficient.

## Verification boundary

Rust tests cover 4/8-byte framing, exact source values, every truncation of a
minimal stream without history, unsupported tags/versions, bad lengths, limits,
subtypes, schema extensions, and active-to-history reference rejection. Python
regressions build both public cubes and check topology, volume, bounds and raw
spans. Inventor's separate corpus report checks 25 active tables against ezdxf's
independent record parser. It does not certify all geometric field semantics.

References and license attribution: [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
