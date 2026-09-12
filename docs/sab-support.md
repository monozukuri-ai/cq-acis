# SAB / ASM support

`parse_sab_model(data, source_id=...)` accepts binary bytes and returns an
`AcisModel`. Use `convert_model()` or `to_cadquery()` on the result to attempt
shape conversion; see [usage](usage.md).

## Accepted profiles

| Container | Accepted save versions | Coverage limitation |
| --- | --- | --- |
| ACIS BinaryFile, 4-byte words | 21800 | Limited native fixture coverage |
| ASM BinaryFile4 | 22000, 22300, 22600, 22700, 22900, 23200 | Version acceptance does not imply support for all geometry layouts |
| ASM BinaryFile8 | Same ASM versions as above | Synthetic framing coverage only; no native eight-byte fixture validated |

These are exact save-format numbers, not Inventor product release ranges.
Every input must also satisfy the supported record grammar and reference
requirements. Other signatures or save versions raise `ValueError`.

Typed records include body, lump, shell, face, loop, coedge, edge, vertex,
point, straight, ellipse, plane, cone/cylinder, sphere, torus, and transform.
Names with `-curve` and `-surface` suffixes are accepted. Unknown entities,
attributes, and unfamiliar layouts remain `RawEntity`; schema limitations are
reported with `sab.entity_schema_unsupported`. See [geometry support](geometry-support.md)
for conversion and explicit NURBS profiles.

## Source data and history

A binary `RawEntity` retains its exact record bytes in `raw_data` and a
`SourceSpan` in the byte domain named by `source_id`. Its `record` is `None`.
All source references in the active table must resolve within that table.

History beginning at a reserved history marker is retained as an opaque
`__opaque_sab_history__` attachment. Active references cannot resolve to that
attachment. Its contents and terminal framing are not validated or replayed,
so corruption confined to the history suffix is not detected. Parsing describes
only the stored table; it does not establish the current Inventor feature,
history, or Model State result. Retained bytes alone do not prove decoded
geometry or complete conversion.

Inventor `.ipt` and other container files must be extracted separately before
passing SAT/SAB data to this API. This package does not implement Inventor
container extraction.

## Parser limits and errors

Default limits are 64 MiB of input, 500,000 records including a history
attachment, 4,000,000 tokens, 4 MiB strings, and subtype depth 64.
Unknown tags, truncated active records, invalid references, unbalanced subtypes,
and limit violations raise errors. Inspect model diagnostics even when parsing
succeeds, then handle conversion failures as described in [usage](usage.md).

For Rust integrations, use [acis-core](../crates/acis-core/README.md) and the
[Python bridge](../crates/acis-py-bridge/README.md).
See [third-party notices](../THIRD_PARTY_NOTICES.md) for attribution.
