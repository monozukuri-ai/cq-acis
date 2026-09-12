# acis-core

Rust-owned ACIS models, reference validation, analytic geometry helpers, and
a bounded SAB/ASM reader. This crate has no dependency on Python, PyO3,
CadQuery, or an external file parser.

For a Rust consumer using the 0.3.3 API:

```toml
[dependencies]
acis-core = "=0.3.3"
```

```rust
use acis_core::{AcisMetadata, AcisModel, Entity, EntityRef, RawEntity, SourceSpan};

let mut raw = RawEntity::new(0, "vendor-unknown");
raw.raw_data = Some(vec![0, 255, 1]);
raw.source = Some(SourceSpan {
    source_id: "part.ipt/segment/inflated".into(),
    start_offset: 64,
    end_offset: 67,
});
let model = AcisModel::new(AcisMetadata::default(), vec![Entity::Raw(raw)], vec![])?;
assert_eq!(model.resolve(EntityRef(0))?.unwrap().index(), 0);
# Ok::<(), acis_core::ModelError>(())
```

`Entity` includes typed topology and geometry used by cq-acis and a `Raw`
variant. Its fields retain topology links, analytic parameters, source records,
byte ranges, and optional uninterpreted bytes. `AcisModel` validates contiguous
indices, closure of raw and typed references, source ranges, and diagnostic
targets at construction.

Model references use signed 64-bit indices (`-1` is null). Source IDs and integer
tokens use arbitrary precision integers; offsets and model lengths use `usize`.
Adapters must remap foreign references explicitly. An unsupported entity must
remain raw, with a diagnostic when appropriate. Retained bytes do not establish
decoded geometry or active-state ownership.

`geometry` implements vectors, ellipse and cone evaluation, plane directions,
and the ACIS row-vector transform convention. It does not construct OCCT solids.
Use Python `cq-acis` for conversion to supported CadQuery B-reps.

`sab::parse_sab` accepts the supported binary profiles and returns this model;
see [SAB/ASM support](https://github.com/monozukuri-ai/cq-acis/blob/main/docs/sab-support.md)
for version and history limitations. Inventor containers must be extracted
separately before passing SAB bytes to the parser.

Explicit clamped NURBS curves/surfaces, sphere and torus entities, and partial
tolerant topology/subtype views are available within the
[documented geometry scope](https://github.com/monozukuri-ai/cq-acis/blob/main/docs/geometry-support.md).
Views retain the source raw records and do not guarantee complete geometry.
Use `acis-py-bridge` when exchanging this model with Python `cq-acis`.
