//! Stored B-spline approximations of procedural ASM curves and surfaces.
//!
//! ASM saves a fitted `bs3` curve or surface, with its fit tolerance, next to
//! the procedural definition of most intersection curves (`int_int_cur`,
//! `blend_int_cur`, `par_int_cur`, `offset_int_cur`, ...) and spline surfaces
//! (`rb_blend_spl_sur`, `rot_spl_sur`, `sweep_sur`, `cl_loft_spl_sur`, ...).
//! This module reads only that stored fit. It never evaluates the procedural
//! definition, and a record without a stored fit (`nullbs`, as helical
//! geometry writes) yields `None`. The result is derived geometry: it differs
//! from the source by up to the saved fit tolerance, and the caller must
//! report it as an approximation.
//!
//! Subtype references (`ref N`) are resolved through a lenient index that
//! numbers every non-reference scope in the order it opens. The strict
//! [`crate::subtypes`] table keeps its qualified vocabulary and is unchanged.
use crate::{
    asm_nurbs::Reader, AcisModel, AcisValue, BSplineCurveEntity, BSplineSurfaceEntity, Entity,
    EntityRef, ParameterRange,
};

/// One subtype scope (`{ kind ... }`) in opening order across the whole model.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ApproximationScope {
    pub index: usize,
    pub kind: String,
    pub entity_index: usize,
    pub value_start: usize,
    /// One past the closing tag.
    pub value_end: usize,
}

/// Opening-order numbering of every subtype scope; references allocate nothing.
#[derive(Debug, Clone, Default)]
pub struct ApproximationIndex {
    scopes: Vec<ApproximationScope>,
    /// Entity at which the brace structure stopped being well formed.
    broken_at: Option<usize>,
}

/// A stored fit and where it came from.
#[derive(Debug, Clone, PartialEq)]
pub struct StoredApproximation {
    pub geometry: Entity,
    /// The procedural subtype the fit stands for, such as `int_int_cur`.
    pub kind: String,
    pub fit_tolerance: f64,
    /// Saved closure of the fit per direction (a curve uses the first):
    /// 0 open, 1 closed, 2 periodic. The knots are clamped in every case.
    pub closure: [u8; 2],
    /// The scope a `ref` record was expanded from.
    pub definition: Option<ApproximationScope>,
}

fn tag(value: &AcisValue, expected: u8) -> bool {
    matches!(value, AcisValue::Bytes(bytes) if bytes == &[expected])
}

fn word(value: Option<&AcisValue>) -> Option<&str> {
    match value {
        Some(AcisValue::String(text)) => Some(text),
        _ => None,
    }
}

impl ApproximationIndex {
    pub fn new(model: &AcisModel) -> Self {
        let mut index = Self::default();
        for entity in model.entities() {
            let raw = entity.raw();
            let mut stack: Vec<Option<usize>> = Vec::new();
            for (position, value) in raw.values.iter().enumerate() {
                if tag(value, 15) {
                    match word(raw.values.get(position + 1)) {
                        Some("ref") => stack.push(None),
                        Some(kind) => {
                            let slot = index.scopes.len();
                            index.scopes.push(ApproximationScope {
                                index: slot,
                                kind: kind.into(),
                                entity_index: raw.index,
                                value_start: position,
                                value_end: 0,
                            });
                            stack.push(Some(slot));
                        }
                        None => {
                            // An unnamed scope has no observed numbering rule.
                            index.broken_at.get_or_insert(raw.index);
                            stack.push(None);
                        }
                    }
                } else if tag(value, 16) {
                    match stack.pop() {
                        Some(Some(slot)) => index.scopes[slot].value_end = position + 1,
                        Some(None) => (),
                        None => {
                            index.broken_at.get_or_insert(raw.index);
                        }
                    }
                }
            }
            if !stack.is_empty() {
                index.broken_at.get_or_insert(raw.index);
            }
        }
        index
    }

    pub fn scopes(&self) -> &[ApproximationScope] {
        &self.scopes
    }

    fn definition(&self, user: usize, target: usize) -> Result<&ApproximationScope, String> {
        if self.broken_at.is_some_and(|broken| user >= broken) {
            return Err("subtype numbering is unqualified after a malformed scope".into());
        }
        self.scopes
            .get(target)
            .filter(|scope| scope.value_end != 0 && scope.entity_index <= user)
            .ok_or_else(|| "unresolved subtype reference".into())
    }
}

/// `open`, `closed` and `periodic` fits share the clamped knot convention.
fn closure(r: &mut Reader<'_>) -> Result<u8, String> {
    let text = match r.take()? {
        AcisValue::Integer(v) => v.to_string(),
        AcisValue::String(s) => s.clone(),
        _ => return Err("unqualified stored spline closure".into()),
    };
    match text.as_str() {
        "0" | "open" => Ok(0),
        "1" | "closed" => Ok(1),
        "2" | "periodic" => Ok(2),
        _ => Err("unqualified stored spline closure".into()),
    }
}

/// A saved range that leaves the fit's knot domain (a periodic fit is saved
/// with ranges beyond one period) is dropped rather than misapplied.
fn range_in(range: Option<ParameterRange>, lower: f64, upper: f64) -> Option<ParameterRange> {
    let range = range?;
    let inside = [range.lower, range.upper]
        .into_iter()
        .flatten()
        .all(|t| t.is_finite() && t >= lower && t <= upper)
        && !matches!((range.lower, range.upper), (Some(a), Some(b)) if a > b);
    Some(if inside {
        range
    } else {
        ParameterRange {
            lower: None,
            upper: None,
        }
    })
}

fn singularity(r: &mut Reader<'_>) -> Result<(), String> {
    match r.take()? {
        AcisValue::Integer(v) if matches!(v.to_string().as_str(), "0" | "1" | "2" | "3") => Ok(()),
        AcisValue::String(s) if matches!(s.as_str(), "none" | "low" | "high" | "both") => Ok(()),
        _ => Err("unqualified stored spline singularity".into()),
    }
}

fn rational(value: Option<&AcisValue>) -> Option<bool> {
    match word(value) {
        Some("nubs") => Some(false),
        Some("nurbs") => Some(true),
        _ => None,
    }
}

struct Envelope<'a> {
    values: &'a [AcisValue],
    pattern: EntityRef,
    reversed: bool,
    /// Index of the tag that closes the top-level scope.
    close: usize,
}

fn curve(
    e: &Envelope<'_>,
    raw: &crate::RawEntity,
) -> Result<Option<(Entity, f64, [u8; 2])>, String> {
    let values = e.values;
    // name, embedded version, representation flag, then the fitted curve.
    if !matches!(values.get(4), Some(AcisValue::Integer(_)))
        || !matches!(values.get(5), Some(AcisValue::Integer(_)))
    {
        return Ok(None);
    }
    let Some(rational) = rational(values.get(6)) else {
        return Ok(None);
    };
    let mut r = Reader { values, pos: 7 };
    let degree = r.integer()?;
    let closed = closure(&mut r)?;
    let count = r.integer()?;
    let (mut knots, mut multiplicities, poles) = r.knots(degree, count)?;
    let (mut poles, mut weights) = r.poles(poles, rational)?;
    let fit_tolerance = r.number()?;
    if fit_tolerance < 0. || r.pos > e.close {
        return Err("invalid stored curve fit".into());
    }
    let mut tail = Reader {
        values,
        pos: e.close + 1,
    };
    let saved_range = tail.range()?;
    if tail.pos != values.len() {
        return Err("unconsumed fields after the stored curve".into());
    }
    if e.reversed {
        // A reversed intcurve runs the fit backwards: C'(t) = C(-t).
        knots = knots.iter().rev().map(|k| -k).collect();
        multiplicities.reverse();
        poles.reverse();
        weights.reverse();
    }
    let parameter_range = range_in(saved_range, knots[0], knots[knots.len() - 1]);
    let curve = BSplineCurveEntity {
        raw: raw.clone(),
        pattern: e.pattern,
        degree,
        knots,
        multiplicities,
        poles,
        weights,
        parameter_range,
        fit_tolerance,
    };
    curve.validate()?;
    Ok(Some((
        Entity::BSplineCurve(curve),
        fit_tolerance,
        [closed, 0],
    )))
}

fn surface_at(
    e: &Envelope<'_>,
    raw: &crate::RawEntity,
    start: usize,
) -> Result<(BSplineSurfaceEntity, f64, [u8; 2]), String> {
    let values = e.values;
    let rational = rational(values.get(start)).ok_or("missing stored surface")?;
    let mut r = Reader {
        values,
        pos: start + 1,
    };
    let u_degree = r.integer()?;
    let v_degree = r.integer()?;
    // Rational fits name the rational directions before the closure fields.
    if matches!(word(values.get(r.pos)), Some("both" | "u" | "v" | "none")) {
        r.pos += 1;
    }
    let closed = [closure(&mut r)?, closure(&mut r)?];
    singularity(&mut r)?;
    singularity(&mut r)?;
    let u_knot_count = r.integer()?;
    let v_knot_count = r.integer()?;
    let (u_knots, u_multiplicities, u_count) = r.knots(u_degree, u_knot_count)?;
    let (v_knots, v_multiplicities, v_count) = r.knots(v_degree, v_knot_count)?;
    let count = u_count
        .checked_mul(v_count)
        .ok_or("surface pole overflow")?;
    let (poles, weights) = r.poles(count, rational)?;
    let fit_tolerance = r.number()?;
    if fit_tolerance < 0. || r.pos > e.close {
        return Err("invalid stored surface fit".into());
    }
    let mut tail = Reader {
        values,
        pos: e.close + 1,
    };
    let u_range = range_in(tail.range()?, u_knots[0], u_knots[u_knots.len() - 1]);
    let v_range = range_in(tail.range()?, v_knots[0], v_knots[v_knots.len() - 1]);
    if tail.pos != values.len() {
        return Err("unconsumed fields after the stored surface".into());
    }
    let surface = BSplineSurfaceEntity {
        raw: raw.clone(),
        pattern: e.pattern,
        u_degree,
        v_degree,
        u_knots,
        v_knots,
        u_multiplicities,
        v_multiplicities,
        u_count,
        v_count,
        poles,
        weights,
        reversed: e.reversed,
        u_range,
        v_range,
        fit_tolerance,
    };
    surface.validate()?;
    Ok((surface, fit_tolerance, closed))
}

fn surface(
    e: &Envelope<'_>,
    raw: &crate::RawEntity,
) -> Result<Option<(Entity, f64, [u8; 2])>, String> {
    // The fit follows the subtype's own data, which may nest curve subtypes
    // with fits of their own: take the last block directly inside the scope.
    let mut depth = 0usize;
    let mut candidates = Vec::new();
    for (position, value) in e.values.iter().enumerate().take(e.close).skip(2) {
        if tag(value, 15) {
            depth += 1;
        } else if tag(value, 16) {
            depth = depth.saturating_sub(1);
        } else if depth == 1 && rational(Some(value)).is_some() {
            candidates.push(position);
        }
    }
    let mut failure = None;
    for start in candidates.into_iter().rev() {
        match surface_at(e, raw, start) {
            Ok((surface, fit, closed)) => {
                return Ok(Some((Entity::BSplineSurface(surface), fit, closed)))
            }
            Err(error) => failure = failure.or(Some(error)),
        }
    }
    match failure {
        Some(error) => Err(error),
        None => Ok(None),
    }
}

/// The stored fit of an `intcurve-curve` or `spline-surface` record, if any.
///
/// `Ok(None)` means the record is not a procedural subtype with a stored fit.
/// An error means a fit seems to be present but its layout is not understood.
pub fn resolve(
    model: &AcisModel,
    index: &ApproximationIndex,
    entity_index: usize,
) -> Result<Option<StoredApproximation>, String> {
    let Some(entity) = model.entities().get(entity_index) else {
        return Err("missing approximation owner".into());
    };
    let raw = entity.raw();
    let is_curve = match raw.type_name.as_str() {
        "intcurve-curve" => true,
        "spline-surface" => false,
        _ => return Ok(None),
    };
    let values = &raw.values;
    let (Some(AcisValue::Reference(pattern)), Some(sense), Some(open), Some(name)) = (
        values.first(),
        values.get(1),
        values.get(2),
        word(values.get(3)),
    ) else {
        return Ok(None);
    };
    if !(tag(sense, 10) || tag(sense, 11)) || !tag(open, 15) {
        return Ok(None);
    }
    let reversed = tag(sense, 10);
    let (expanded, kind, definition);
    if name == "ref" {
        let target = match values.get(4) {
            Some(AcisValue::Integer(n)) => n
                .to_string()
                .parse::<usize>()
                .map_err(|_| "invalid subtype reference")?,
            _ => return Err("invalid subtype reference".into()),
        };
        if !values.get(5).is_some_and(|v| tag(v, 16)) {
            return Err("invalid geometry alias envelope".into());
        }
        let scope = index.definition(raw.index, target)?;
        let owner = model
            .entities()
            .get(scope.entity_index)
            .ok_or("missing subtype owner")?
            .raw();
        let body = owner
            .values
            .get(scope.value_start..scope.value_end)
            .ok_or("invalid subtype extent")?;
        expanded = values[..2]
            .iter()
            .chain(body)
            .chain(&values[6..])
            .cloned()
            .collect::<Vec<_>>();
        kind = scope.kind.clone();
        definition = Some(scope.clone());
    } else {
        expanded = values.clone();
        kind = name.to_string();
        definition = None;
    }
    let mut depth = 0usize;
    let mut close = None;
    for (position, value) in expanded.iter().enumerate().skip(2) {
        if tag(value, 15) {
            depth += 1;
        } else if tag(value, 16) {
            depth = depth.checked_sub(1).ok_or("unmatched subtype close")?;
            if depth == 0 {
                close = Some(position);
                break;
            }
        }
    }
    let envelope = Envelope {
        values: &expanded,
        pattern: *pattern,
        reversed,
        close: close.ok_or("unclosed subtype")?,
    };
    let decoded = if is_curve {
        curve(&envelope, raw)?
    } else {
        surface(&envelope, raw)?
    };
    Ok(
        decoded.map(|(geometry, fit_tolerance, closure)| StoredApproximation {
            geometry,
            kind,
            fit_tolerance,
            closure,
            definition,
        }),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{AcisMetadata, RawEntity, NULL_REF};
    use AcisValue::{Bytes as B, Float as F, Integer as I, Reference as R, String as S};

    fn int(n: i64) -> AcisValue {
        I(n.into())
    }
    fn raw(index: usize, kind: &str, values: Vec<AcisValue>) -> Entity {
        Entity::Raw(RawEntity {
            values,
            ..RawEntity::new(index, kind)
        })
    }
    /// A cubic fit on one span from (0,0,0) to (3,0,0) with a subtype trailer.
    fn curve_values(sense: u8, kind: &str) -> Vec<AcisValue> {
        let mut values = vec![
            R(NULL_REF),
            B(vec![sense]),
            B(vec![15]),
            S(kind.into()),
            int(22220),
            int(0),
            S("nubs".into()),
            int(3),
            int(0),
            int(2),
            F(1.),
            int(3),
            F(2.),
            int(3),
        ];
        for x in [0., 1., 2., 3.] {
            values.extend([F(x), F(0.), F(0.)]);
        }
        values.push(F(0.001));
        // Procedural data the fit stands for, including a nested scope.
        values.extend([
            S("spline".into()),
            B(vec![11]),
            B(vec![15]),
            S("ref".into()),
            int(0),
            B(vec![16]),
            S("nullbs".into()),
        ]);
        values.extend([B(vec![16]), B(vec![10]), F(1.25), B(vec![11])]);
        values
    }
    fn surface_values() -> Vec<AcisValue> {
        let mut values = vec![
            R(NULL_REF),
            B(vec![11]),
            B(vec![15]),
            S("rot_spl_sur".into()),
            int(22000),
            S("intcurve".into()),
            B(vec![11]),
        ];
        // A nested curve subtype with its own fit must not be taken for the surface.
        values.extend(curve_values(11, "offset_int_cur")[2..27].iter().cloned());
        values.extend([S("nullbs".into()), B(vec![16])]);
        values.extend([
            S("nubs".into()),
            int(1),
            int(1),
            int(0),
            int(0),
            int(0),
            int(0),
            int(2),
            int(2),
        ]);
        for _ in 0..2 {
            values.extend([F(0.), int(1), F(1.), int(1)]);
        }
        for (x, y, z) in [(0., 0., 0.), (2., 0., 0.), (0., 3., 0.), (2., 3., 4.)] {
            values.extend([F(x), F(y), F(z)]);
        }
        values.push(F(0.002));
        values.extend((0..6).map(|_| int(0)));
        values.extend([B(vec![11]), B(vec![16])]);
        values.extend((0..4).map(|_| B(vec![11])));
        values
    }
    fn model(entities: Vec<Entity>) -> AcisModel {
        AcisModel::new(AcisMetadata::default(), entities, vec![]).unwrap()
    }

    #[test]
    fn curve_fit_is_read_and_a_reversed_record_runs_backwards() {
        let m = model(vec![
            raw(0, "intcurve-curve", curve_values(11, "int_int_cur")),
            raw(1, "intcurve-curve", curve_values(10, "blend_int_cur")),
        ]);
        let index = ApproximationIndex::new(&m);
        let forward = resolve(&m, &index, 0).unwrap().unwrap();
        assert_eq!(
            (forward.kind.as_str(), forward.fit_tolerance),
            ("int_int_cur", 0.001)
        );
        let Entity::BSplineCurve(curve) = &forward.geometry else {
            panic!()
        };
        assert_eq!(curve.knots, vec![1., 2.]);
        assert_eq!(curve.multiplicities, vec![4, 4]);
        assert_eq!(curve.parameter_range.unwrap().lower, Some(1.25));
        assert_eq!(curve.evaluate(1.).unwrap().x, 0.);
        assert_eq!(curve.evaluate(2.).unwrap().x, 3.);
        // A saved range outside the reversed knot domain is dropped, not misapplied.
        let reversed = resolve(&m, &index, 1).unwrap().unwrap();
        assert_eq!(reversed.closure, [0, 0]);
        let Entity::BSplineCurve(curve) = &reversed.geometry else {
            panic!()
        };
        assert_eq!(curve.knots, vec![-2., -1.]);
        assert!(curve.parameter_range.unwrap().lower.is_none());
        assert_eq!(curve.evaluate(-1.).unwrap().x, 0.);
        assert_eq!(curve.evaluate(-2.).unwrap().x, 3.);
    }

    #[test]
    fn records_without_a_stored_fit_or_with_other_types_yield_none() {
        let mut helix = curve_values(11, "helix_int_cur");
        helix[5] = B(vec![10]);
        let mut null = curve_values(11, "int_int_cur");
        null[6] = S("nullbs".into());
        let m = model(vec![
            raw(0, "intcurve-curve", helix),
            raw(1, "intcurve-curve", null),
            raw(2, "plane-surface", curve_values(11, "int_int_cur")),
        ]);
        let index = ApproximationIndex::new(&m);
        for entity in 0..3 {
            assert_eq!(resolve(&m, &index, entity).unwrap(), None);
        }
        // A truncated fit is an error, not an absent fit.
        let mut cut = curve_values(11, "int_int_cur");
        cut.drain(20..24);
        let m = model(vec![raw(0, "intcurve-curve", cut)]);
        assert!(resolve(&m, &ApproximationIndex::new(&m), 0).is_err());
    }

    #[test]
    fn surface_fit_is_the_last_block_of_the_scope_and_references_expand() {
        let alias = vec![
            R(NULL_REF),
            B(vec![10]),
            B(vec![15]),
            S("ref".into()),
            int(0),
            B(vec![16]),
            B(vec![11]),
            B(vec![11]),
            B(vec![11]),
            B(vec![11]),
        ];
        let m = model(vec![
            raw(0, "spline-surface", surface_values()),
            raw(1, "spline-surface", alias.clone()),
        ]);
        let index = ApproximationIndex::new(&m);
        // The surface scope opens first; its nested curve scope is numbered next.
        assert_eq!(
            index
                .scopes()
                .iter()
                .map(|s| s.kind.as_str())
                .collect::<Vec<_>>(),
            ["rot_spl_sur", "offset_int_cur"]
        );
        let direct = resolve(&m, &index, 0).unwrap().unwrap();
        let Entity::BSplineSurface(surface) = &direct.geometry else {
            panic!()
        };
        assert_eq!(
            (surface.u_count, surface.v_count, surface.reversed),
            (2, 2, false)
        );
        assert_eq!(direct.fit_tolerance, 0.002);
        let p = surface.evaluate(1., 1.).unwrap();
        assert_eq!((p.x, p.y, p.z), (2., 3., 4.));
        let aliased = resolve(&m, &index, 1).unwrap().unwrap();
        assert_eq!(aliased.kind, "rot_spl_sur");
        assert_eq!(aliased.definition.as_ref().unwrap().entity_index, 0);
        let Entity::BSplineSurface(surface) = &aliased.geometry else {
            panic!()
        };
        assert!(surface.reversed);
        assert_eq!(surface.raw.index, 1);
        // A reference cannot point forward or past the numbered scopes.
        let mut forward = alias;
        forward[4] = int(7);
        let m = model(vec![raw(0, "spline-surface", forward)]);
        assert!(resolve(&m, &ApproximationIndex::new(&m), 0).is_err());
    }
}
