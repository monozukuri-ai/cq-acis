# acis-core

Rust-owned ACIS models, reference validation, analytic geometry helpers, and
a bounded SAB/ASM reader. This crate has no dependency on Python, PyO3,
CadQuery, or an external file parser. The
only runtime dependency is `num-bigint`, used to preserve source integers.

From a sibling `inventor-kit` checkout, an unpublished local dependency can be:

```toml
[dependencies]
acis-core = { path = "../cq-acis/crates/acis-core" }
```

For a manifest nested under `crates/`, adjust the relative path to that manifest.
No crates.io publication is implied by this example.

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

`Entity` includes all 14 decoded entity types used by cq-acis and a `Raw`
variant. Its fields retain topology links, analytic parameters, source records,
byte ranges, and optional uninterpreted bytes. `AcisModel` validates contiguous
indices, closure of raw and typed references, source ranges, and diagnostic
targets. Private model fields keep these checks valid after construction.

Model references use signed 64-bit indices (`-1` is null). Source IDs and integer
tokens use arbitrary precision integers; offsets and model lengths use `usize`.
Adapters must remap foreign references explicitly. An unsupported entity must
remain raw, with a diagnostic when appropriate. Retained bytes do not establish
decoded geometry or active-state ownership.

`geometry` implements vectors, ellipse and cone evaluation, plane directions,
and the ACIS row-vector transform convention. It does not construct OCCT solids.
`cq-acis-py` provides the separate Python boundary and the existing Python
CadQuery adapter constructs the supported B-reps.

SAT framing/schema decoding is currently Python. `sab::parse_sab` decodes the
explicitly admitted binary profiles directly into this model; see
`docs/sab-support.md` in the repository for exact gates and history limitations.
Inventor container parsing is implemented in the separate `inventor-kit` crate.

```sh
cargo test -p acis-core --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
```

M4 development version 0.2.0 adds signed sphere/torus records, a separate cone
parameter scale, and bounded explicit clamped NURBS surface evaluation / SAT 700
`exactsur` decoding. Canonical evaluator coordinates are documented separately
from saved ACIS charts. Explicit clamped curves and the experimental ASM 22700 /
embedded 22601 forward direct NURBS profile are also supported, only with the
qualified default trailers. Other procedural ASM spline records remain opaque.
