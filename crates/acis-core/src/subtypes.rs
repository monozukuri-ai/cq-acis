//! File-local subtype indexing for a bounded ASM 22700 vocabulary.
//! Definitions receive indices on opening, including nested definitions.
//! Unknown scopes stop reliable numbering; references never consume an index.
use crate::{AcisModel, AcisValue, Entity};
use std::{collections::BTreeMap, sync::Arc};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SubtypeDefinition {
    pub index: usize,
    pub kind: String,
    pub entity_index: usize,
    /// Half-open indices into RawEntity.values, including scope delimiters.
    pub value_start: usize,
    pub value_end: usize,
    pub parent: Option<usize>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SubtypeReference {
    pub entity_index: usize,
    pub value_start: usize,
    pub target: Option<usize>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct SubtypeTable {
    pub definitions: Vec<SubtypeDefinition>,
    pub references: Vec<SubtypeReference>,
    pub diagnostics: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ResolvedSubtype {
    /// A view with the referencing entity's original raw bytes and span.
    pub geometry: Entity,
    pub definition: SubtypeDefinition,
}

fn tag(v: &AcisValue, t: u8) -> bool {
    matches!(v, AcisValue::Bytes(b) if b == &[t])
}
fn word(v: Option<&AcisValue>) -> Option<&str> {
    match v {
        Some(AcisValue::String(s)) => Some(s),
        _ => None,
    }
}
fn vocabulary(s: &str) -> bool {
    matches!(
        s,
        "exact_spl_sur" | "exact_int_cur" | "exp_par_cur" | "par_int_cur" | "int_int_cur"
    )
}

fn root_scope(raw: &crate::RawEntity, start: usize, kind: Option<&str>) -> bool {
    let boolean = |i| raw.values.get(i).is_some_and(|v| tag(v, 10) || tag(v, 11));
    let integer =
        |i, n: i64| matches!(raw.values.get(i), Some(AcisValue::Integer(v)) if *v == n.into());
    let reference = |i| matches!(raw.values.get(i), Some(AcisValue::Reference(_)));
    if !reference(0) {
        return false;
    }
    match raw.type_name.as_str() {
        "spline-surface" => {
            start == 2 && boolean(1) && matches!(kind, Some("exact_spl_sur" | "ref"))
        }
        "intcurve-curve" => {
            start == 2
                && boolean(1)
                && matches!(
                    kind,
                    Some("exact_int_cur" | "par_int_cur" | "int_int_cur" | "ref")
                )
        }
        "pcurve" => {
            start == 3 && integer(1, 0) && boolean(2) && matches!(kind, Some("exp_par_cur" | "ref"))
        }
        "tcoedge-coedge" => {
            start == 15
                && reference(11)
                && integer(12, 1)
                && word(raw.values.get(13)) == Some("intcurve")
                && boolean(14)
                && matches!(
                    kind,
                    Some("exact_int_cur" | "par_int_cur" | "int_int_cur" | "ref")
                )
        }
        _ => false,
    }
}

/// Index only an observed subtype vocabulary, without interpreting procedural
/// geometry. Unknown braces may have different registration rules, so every
/// reference after the first unknown/malformed scope is left unresolved.
pub fn index(model: &AcisModel) -> SubtypeTable {
    let mut table = SubtypeTable::default();
    if model
        .metadata()
        .save_version
        .as_ref()
        .map(ToString::to_string)
        .as_deref()
        != Some("22700")
    {
        table
            .diagnostics
            .push("subtype table requires ASM save version 22700".into());
        return table;
    }
    let mut reliable = true;
    for entity in model.entities() {
        let raw = entity.raw();
        let mut stack: Vec<Option<usize>> = Vec::new();
        let mut root_seen = false;
        for (i, value) in raw.values.iter().enumerate() {
            if tag(value, 15) {
                let kind = word(raw.values.get(i + 1));
                if stack.is_empty() {
                    if reliable && (root_seen || !root_scope(raw, i, kind)) {
                        reliable = false;
                        table.diagnostics.push(format!(
                            "entity {} value {i}: unqualified subtype record envelope",
                            raw.index
                        ));
                    }
                    root_seen = true;
                }
                if kind == Some("ref") {
                    if !raw.values.get(i + 3).is_some_and(|v| tag(v, 16)) {
                        reliable = false;
                    }
                    let target = if reliable && raw.values.get(i + 3).is_some_and(|v| tag(v, 16)) {
                        match raw.values.get(i + 2) {
                            Some(AcisValue::Integer(n)) => {
                                n.to_string().parse::<usize>().ok().filter(|n| {
                                    table.definitions.get(*n).is_some_and(|d| d.value_end != 0)
                                })
                            }
                            _ => None,
                        }
                    } else {
                        None
                    };
                    if target.is_none() {
                        table.diagnostics.push(format!(
                            "entity {} value {i}: unresolved subtype reference",
                            raw.index
                        ));
                    }
                    table.references.push(SubtypeReference {
                        entity_index: raw.index,
                        value_start: i,
                        target,
                    });
                    stack.push(None);
                } else if reliable && kind.is_some_and(vocabulary) {
                    let slot = table.definitions.len();
                    table.definitions.push(SubtypeDefinition {
                        index: slot,
                        kind: kind.unwrap().into(),
                        entity_index: raw.index,
                        value_start: i,
                        value_end: 0,
                        parent: stack.iter().rev().flatten().next().copied(),
                    });
                    stack.push(Some(slot));
                } else {
                    if reliable {
                        table.diagnostics.push(format!("entity {} value {i}: unknown scope; subsequent subtype numbering is unqualified", raw.index));
                    }
                    reliable = false;
                    stack.push(None);
                }
            } else if tag(value, 16) {
                match stack.pop() {
                    Some(Some(slot)) => table.definitions[slot].value_end = i + 1,
                    Some(None) => (),
                    None => {
                        reliable = false;
                        table.diagnostics.push(format!(
                            "entity {} value {i}: unmatched subtype close",
                            raw.index
                        ));
                    }
                }
            }
        }
        if !stack.is_empty() {
            reliable = false;
            table
                .diagnostics
                .push(format!("entity {}: unclosed subtype", raw.index));
        }
    }
    table
}

/// An index bound to its immutable source model; indices cannot cross files.
/// Build once when resolving multiple aliases.
pub struct SubtypeResolver {
    model: Arc<AcisModel>,
    table: SubtypeTable,
    roots: BTreeMap<usize, usize>,
}
impl SubtypeResolver {
    pub fn new(model: Arc<AcisModel>) -> Self {
        let table = index(&model);
        let roots = table
            .references
            .iter()
            .enumerate()
            .filter(|(_, r)| r.value_start == 2)
            .map(|(i, r)| (r.entity_index, i))
            .collect();
        Self {
            model,
            table,
            roots,
        }
    }
    pub fn table(&self) -> &SubtypeTable {
        &self.table
    }
    pub fn resolve(&self, entity_index: usize) -> Result<Option<ResolvedSubtype>, String> {
        resolve(
            &self.model,
            &self.table,
            self.roots.get(&entity_index).copied(),
            entity_index,
        )
    }
    pub fn linear_surface_pcurve(
        &self,
        pcurve: usize,
        surface: usize,
    ) -> Result<Option<crate::pcurve::LinearSurfacePcurve>, String> {
        crate::pcurve::decode(&self.model, &self.table, pcurve, surface)
    }
}

/// Resolve a top-level geometry alias through the indexed definition. Nested
/// definitions are eligible, but only the existing fully validated explicit
/// spline grammar can produce geometry. Saved sense/ranges belong to the user
/// of the subtype, not to the record containing its definition.
fn resolve(
    model: &AcisModel,
    table: &SubtypeTable,
    reference_index: Option<usize>,
    entity_index: usize,
) -> Result<Option<ResolvedSubtype>, String> {
    let raw = model
        .entities()
        .get(entity_index)
        .ok_or("missing subtype reference owner")?
        .raw();
    let expected = match raw.type_name.as_str() {
        "spline-surface" => "exact_spl_sur",
        "intcurve-curve" => "exact_int_cur",
        _ => return Ok(None),
    };
    if word(raw.values.get(3)) != Some("ref") {
        return Ok(None);
    }
    let reference = reference_index
        .and_then(|i| table.references.get(i))
        .ok_or("missing qualified subtype reference")?;
    let definition = reference
        .target
        .and_then(|i| table.definitions.get(i))
        .ok_or("unresolved subtype index")?;
    if definition.kind != expected {
        return Err("subtype reference has an unsupported geometry kind".into());
    }
    let owner = model
        .entities()
        .get(definition.entity_index)
        .ok_or("missing subtype owner")?
        .raw();
    let scope = owner
        .values
        .get(definition.value_start..definition.value_end)
        .ok_or("invalid subtype extent")?;
    if raw.values.len() < 6 || !tag(&raw.values[2], 15) || !tag(&raw.values[5], 16) {
        return Err("invalid geometry alias envelope".into());
    }
    let mut expanded = raw.clone();
    expanded.values = raw.values[..2]
        .iter()
        .chain(scope)
        .chain(&raw.values[6..])
        .cloned()
        .collect();
    let mut geometry =
        crate::asm_nurbs::decode(&expanded, 22700)?.ok_or("subtype geometry not decoded")?;
    // Never label expanded bytes as original source bytes.
    match &mut geometry {
        Entity::BSplineSurface(s) => s.raw = raw.clone(),
        Entity::BSplineCurve(c) => c.raw = raw.clone(),
        _ => return Err("unexpected resolved geometry".into()),
    }
    Ok(Some(ResolvedSubtype {
        geometry,
        definition: definition.clone(),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{AcisMetadata, RawEntity};
    fn b(t: u8) -> AcisValue {
        AcisValue::Bytes(vec![t])
    }
    fn s(t: &str) -> AcisValue {
        AcisValue::String(t.into())
    }
    fn model(values: Vec<AcisValue>) -> AcisModel {
        let mut raw = RawEntity::new(0, "pcurve");
        raw.values = vec![
            AcisValue::Reference(crate::NULL_REF),
            AcisValue::Integer(0.into()),
            b(11),
        ];
        raw.values.extend(values);
        AcisModel::new(
            AcisMetadata {
                save_version: Some(22700.into()),
                ..Default::default()
            },
            vec![Entity::Raw(raw)],
            vec![],
        )
        .unwrap()
    }
    #[test]
    fn nested_definitions_use_preorder_and_refs_do_not_allocate() {
        let m = model(vec![
            b(15),
            s("exp_par_cur"),
            b(15),
            s("exact_spl_sur"),
            b(16),
            b(15),
            s("ref"),
            AcisValue::Integer(1.into()),
            b(16),
            b(16),
        ]);
        let t = index(&m);
        assert_eq!(t.definitions.len(), 2);
        assert_eq!(t.definitions[1].parent, Some(0));
        assert_eq!(t.definitions[1].value_start, 5);
        assert_eq!(t.references[0].target, Some(1));
        assert!(t.diagnostics.is_empty());
    }
    #[test]
    fn unknown_scopes_forward_and_recursive_refs_are_not_guessed() {
        for values in [
            vec![b(15), s("ref"), AcisValue::Integer(0.into()), b(16)],
            vec![
                b(15),
                s("exact_spl_sur"),
                b(15),
                s("ref"),
                AcisValue::Integer(0.into()),
                b(16),
                b(16),
            ],
            vec![
                b(15),
                s("unknown"),
                b(16),
                b(15),
                s("exact_spl_sur"),
                b(16),
                b(15),
                s("ref"),
                AcisValue::Integer(0.into()),
                b(16),
            ],
        ] {
            let t = index(&model(values));
            assert!(t.references.iter().all(|r| r.target.is_none()));
            assert!(!t.diagnostics.is_empty());
        }
    }
}
