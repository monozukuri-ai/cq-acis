# Binary format references

The new SAB reader in `crates/acis-core/src/sab.rs` was written for cq-acis.
Its bounded token grammar and entity layouts were informed by:

- The cadmpeg project, commit `faa73bfdaa29a7b4fb5c6998c1bdedfec8fac9d7`:
  [ASM format notes](https://github.com/cadmpeg/cadmpeg/blob/faa73bfdaa29a7b4fb5c6998c1bdedfec8fac9d7/docs/formats/asm.md)
  licensed CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/).
  Attribution: the cadmpeg project. The implementation and support document here
  are adaptations to a smaller shared model: exact version gates, opaque history,
  source spans, and rejection of unsupported analytic charts. They do not imply
  endorsement or implement the complete cadmpeg format model.
  Its Apache-2.0 Rust reference source was also consulted; a copy of the license
  is included at `licenses/cadmpeg-Apache-2.0.txt`.
- ezdxf by Manfred Moitzi: https://github.com/mozman/ezdxf, MIT.
  SAB tag grammar and the two public cube fixtures provide an independent
  framing/geometry regression. License: `licenses/ezdxf-MIT.txt`.

Existing corpus files retain their separate upstream notices in `corpus/` and
are excluded from distribution artifacts. InventorLoader source is not used.
