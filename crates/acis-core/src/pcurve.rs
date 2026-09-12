//! Observed forward linear exp_par_cur charts on the same explicit spline.
//! This is a partial view, not a general pcurve or procedural surface decoder.
use crate::{
    subtypes::{SubtypeDefinition, SubtypeTable},
    AcisModel, AcisValue, RawEntity,
};

#[derive(Debug, Clone, PartialEq)]
pub struct LinearSurfacePcurve {
    pub raw: RawEntity,
    pub parameter_interval: [f64; 2],
    pub uv_endpoints: [[f64; 2]; 2],
    /// Saved bound, never used to enlarge the consuming model's tolerance.
    pub fit_tolerance: f64,
    pub support: SubtypeDefinition,
}

fn tag(values: &[AcisValue], i: usize, byte: u8) -> bool {
    matches!(values.get(i), Some(AcisValue::Bytes(b)) if b == &[byte])
}
fn word(values: &[AcisValue], i: usize, expected: &str) -> bool {
    matches!(values.get(i), Some(AcisValue::String(s)) if s == expected)
}
fn integer(values: &[AcisValue], i: usize, expected: i64) -> bool {
    matches!(values.get(i), Some(AcisValue::Integer(n)) if *n == expected.into())
}
fn number(values: &[AcisValue], i: usize) -> Result<f64, String> {
    match values.get(i) {
        Some(AcisValue::Float(f)) if f.is_finite() => Ok(*f),
        _ => Err("linear pcurve requires a finite saved double".into()),
    }
}

fn definition(table: &SubtypeTable, entity: usize, start: usize) -> Option<&SubtypeDefinition> {
    table
        .definitions
        .iter()
        .find(|d| d.entity_index == entity && d.value_start == start)
        .or_else(|| {
            table
                .references
                .iter()
                .find(|r| r.entity_index == entity && r.value_start == start)
                .and_then(|r| r.target)
                .and_then(|i| table.definitions.get(i))
        })
}

pub(crate) fn decode(
    model: &AcisModel,
    table: &SubtypeTable,
    index: usize,
    surface: usize,
) -> Result<Option<LinearSurfacePcurve>, String> {
    if model
        .metadata()
        .save_version
        .as_ref()
        .map(ToString::to_string)
        .as_deref()
        != Some("22700")
    {
        return Ok(None);
    }
    let raw = model.entities().get(index).ok_or("missing pcurve")?.raw();
    let target = model
        .entities()
        .get(surface)
        .ok_or("missing pcurve surface")?
        .raw();
    let v = &raw.values;
    if raw.type_name != "pcurve"
        || target.type_name != "spline-surface"
        || !tag(v, 2, 11)
        || !word(v, 4, "exp_par_cur")
        || !word(v, 5, "nubs")
        || !integer(v, 6, 1)
        || !integer(v, 7, 0)
        || !integer(v, 8, 2)
        || !word(v, 18, "spline")
        || !tag(v, 19, 11)
    {
        return Ok(None);
    }
    if !matches!(v.first(), Some(AcisValue::Reference(_)))
        || !integer(v, 1, 0)
        || !tag(v, 3, 15)
        || !integer(v, 10, 1)
        || !integer(v, 12, 1)
        || !tag(v, 20, 15)
    {
        return Err("unqualified linear pcurve envelope".into());
    }
    let support = definition(table, index, 20).ok_or("unresolved pcurve support")?;
    let face_support = definition(table, surface, 2).ok_or("unresolved face spline support")?;
    if support.kind != "exact_spl_sur" || support != face_support {
        return Err("pcurve references a different spline support".into());
    }
    let end = if word(v, 21, "ref") {
        if !tag(v, 23, 16) {
            return Err("invalid pcurve support reference".into());
        }
        24
    } else if word(v, 21, "exact_spl_sur") {
        support.value_end
    } else {
        return Err("unsupported pcurve support profile".into());
    };
    // Only an unchanged chart, unbounded embedded support and zero UV shift.
    if v.len() != end + 7
        || !(0..4).all(|i| tag(v, end + i, 11))
        || !tag(v, end + 4, 16)
        || number(v, end + 5)? != 0.
        || number(v, end + 6)? != 0.
    {
        return Err("unqualified pcurve support ranges or chart shift".into());
    }
    let parameter_interval = [number(v, 9)?, number(v, 11)?];
    let uv_endpoints = [
        [number(v, 13)?, number(v, 14)?],
        [number(v, 15)?, number(v, 16)?],
    ];
    let fit_tolerance = number(v, 17)?;
    if parameter_interval[0] >= parameter_interval[1]
        || !(parameter_interval[1] - parameter_interval[0]).is_finite()
        || uv_endpoints[0] == uv_endpoints[1]
        || fit_tolerance < 0.
    {
        return Err("invalid linear pcurve interval, poles or tolerance".into());
    }
    Ok(Some(LinearSurfacePcurve {
        raw: raw.clone(),
        parameter_interval,
        uv_endpoints,
        fit_tolerance,
        support: support.clone(),
    }))
}
