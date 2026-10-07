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

## Experimental source-free SAB authoring

`authoring::BoxSpec` builds one axis-aligned solid from millimetre dimensions
and a minimum corner. `encode::SabEncoder` emits only the
`Asm23200MetricBox` profile: width 4, scale 10, resabs 1e-6 source units,
resnor 1e-10, planes, straight curves, and closed box topology. It does not
read a template, source SAB, raw entity payload, or Inventor API. This API
is experimental and has no whole-IPT or general ACIS editing contract.

```rust
use acis_core::authoring::BoxSpec;
use acis_core::encode::{HistoryMode, SabEncoder};

let generated = BoxSpec::new((20.0, 30.0, 40.0).into(), (5.0, -10.0, 0.0).into()).build()?;
let bytes = SabEncoder::default().encode(&generated, HistoryMode::None)?;
assert!(bytes.starts_with(b"ASM BinaryFile4"));
# Ok::<(), Box<dyn std::error::Error>>(())
```

Sizes must be at least 0.00032 mm (32 absolute tolerances) and at most
1,000,000 mm. Each minimum/maximum coordinate must be within +/-1,000,000 mm.
There are exactly 86 active entities. Topology/ownership, reciprocal partners,
loop closure and orientation, analytic charts, finite values, semantic IDs,
and output byte/entity budgets are checked before encoding.

The encoder accepts an immutable `AuthoredBox`, which only the builder can
construct. `validate_box` can separately check parsed geometry without granting
it encoder input rights. `HistoryMode::None` is intended for source geometry;
`InsertionOnlyStateOne` constructs a fresh insertion-only history for a final
BRep. The SAB reader retains history as opaque; its successful read alone is
not history or native-kernel qualification. Native acceptance and document
integration require separate oracle tests. Other versions, rotations, attributes,
and arbitrary source history have no write fallback.

The Rust-only `author_box` example takes an output filename, three sizes, three
minimum-corner coordinates, and `source` or `result`. It refuses to replace an
existing output file.
