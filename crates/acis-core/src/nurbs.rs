//! Bounded explicit clamped NURBS. Procedural and periodic data are not inferred.
use crate::{AcisValue, BSplineCurveEntity, BSplineSurfaceEntity, ParameterRange, RawEntity, Vec3};

const MAX_POLES: usize = 1_000_000;
pub(crate) fn knot_vector(
    degree: usize,
    knots: &[f64],
    mults: &[usize],
    count: usize,
) -> Result<Vec<f64>, String> {
    if !(1..=16).contains(&degree)
        || !(2..=4096).contains(&knots.len())
        || knots.len() != mults.len()
        || !knots.iter().all(|x| x.is_finite())
        || knots.windows(2).any(|w| w[0] >= w[1])
        || mults[0] != degree + 1
        || mults[mults.len() - 1] != degree + 1
        || mults[1..mults.len() - 1]
            .iter()
            .any(|m| *m == 0 || *m > degree)
    {
        return Err("invalid/non-clamped B-spline knots, degree or multiplicities".into());
    }
    let length = mults
        .iter()
        .try_fold(0usize, |a, b| a.checked_add(*b))
        .ok_or("knot size overflow")?;
    if length > 65536 || count.checked_add(degree + 1) != Some(length) {
        return Err("B-spline knot/pole count mismatch".into());
    }
    Ok(knots
        .iter()
        .zip(mults)
        .flat_map(|(k, m)| std::iter::repeat_n(*k, *m))
        .collect())
}
// Local Cox-de Boor basis. Endpoint convention is closed on the final span.
fn basis(knots: &[f64], degree: usize, count: usize, t: f64) -> Result<(usize, Vec<f64>), String> {
    if !t.is_finite() || t < knots[degree] || t > knots[count] {
        return Err("B-spline parameter outside domain".into());
    }
    let span = if t == knots[count] {
        count - 1
    } else {
        knots.partition_point(|k| *k <= t) - 1
    };
    let mut n = vec![0.; degree + 1];
    n[0] = 1.;
    let mut left = vec![0.; degree + 1];
    let mut right = vec![0.; degree + 1];
    for j in 1..=degree {
        left[j] = t - knots[span + 1 - j];
        right[j] = knots[span + j] - t;
        let mut saved = 0.;
        for r in 0..j {
            let denom = right[r + 1] + left[j - r];
            let term = if denom == 0. { 0. } else { n[r] / denom };
            n[r] = saved + right[r + 1] * term;
            saved = left[j - r] * term;
        }
        n[j] = saved;
    }
    Ok((span - degree, n))
}
impl BSplineCurveEntity {
    pub fn validate(&self) -> Result<(), String> {
        if self.poles.is_empty()
            || self.poles.len() > MAX_POLES
            || self.weights.len() != self.poles.len()
            || !self
                .poles
                .iter()
                .all(|p| p.x.is_finite() && p.y.is_finite() && p.z.is_finite())
            || !self.weights.iter().all(|w| w.is_finite() && *w > 0.)
            || !self.fit_tolerance.is_finite()
            || self.fit_tolerance < 0.
        {
            return Err("invalid B-spline curve poles, weights or tolerance".into());
        }
        knot_vector(
            self.degree,
            &self.knots,
            &self.multiplicities,
            self.poles.len(),
        )?;
        if let Some(range) = self.parameter_range {
            if [range.lower, range.upper].iter().flatten().any(|t| {
                !t.is_finite() || *t < self.knots[0] || *t > self.knots[self.knots.len() - 1]
            }) || matches!((range.lower,range.upper),(Some(a),Some(b)) if a>b)
            {
                return Err("B-spline curve range outside knot domain".into());
            }
        }
        Ok(())
    }
    pub fn evaluate(&self, t: f64) -> Result<Vec3, String> {
        self.validate()?;
        let knots = knot_vector(
            self.degree,
            &self.knots,
            &self.multiplicities,
            self.poles.len(),
        )?;
        let (start, values) = basis(&knots, self.degree, self.poles.len(), t)?;
        let mut point = Vec3::from((0., 0., 0.));
        let mut weight = 0.;
        // Normalize weights to avoid overflowing a valid rational quotient.
        let scale = self.weights[start..start + values.len()]
            .iter()
            .copied()
            .fold(0., f64::max);
        for (i, b) in values.iter().enumerate() {
            let w = b * (self.weights[start + i] / scale);
            point = point + self.poles[start + i] * w;
            weight += w;
        }
        point = point * (1. / weight);
        if !point.x.is_finite() || !point.y.is_finite() || !point.z.is_finite() {
            return Err("NURBS curve evaluation overflow".into());
        }
        Ok(point)
    }
}

impl BSplineSurfaceEntity {
    pub fn validate(&self) -> Result<(), String> {
        let count = self
            .u_count
            .checked_mul(self.v_count)
            .ok_or("pole count overflow")?;
        if count == 0
            || count > MAX_POLES
            || self.poles.len() != count
            || self.weights.len() != count
            || !self
                .poles
                .iter()
                .all(|p| p.x.is_finite() && p.y.is_finite() && p.z.is_finite())
            || !self.weights.iter().all(|w| w.is_finite() && *w > 0.)
            || !self.fit_tolerance.is_finite()
            || self.fit_tolerance < 0.
        {
            return Err("invalid B-spline poles, positive weights or fit tolerance".into());
        }
        knot_vector(
            self.u_degree,
            &self.u_knots,
            &self.u_multiplicities,
            self.u_count,
        )?;
        knot_vector(
            self.v_degree,
            &self.v_knots,
            &self.v_multiplicities,
            self.v_count,
        )?;
        for (range, knots) in [(self.u_range, &self.u_knots), (self.v_range, &self.v_knots)] {
            if let Some(range) = range {
                let lower = range.lower.unwrap_or(knots[0]);
                let upper = range.upper.unwrap_or(knots[knots.len() - 1]);
                if !lower.is_finite()
                    || !upper.is_finite()
                    || lower < knots[0]
                    || upper > knots[knots.len() - 1]
                    || lower >= upper
                {
                    return Err("B-spline surface range outside knot domain or empty".into());
                }
            }
        }
        Ok(())
    }
    pub fn evaluate(&self, u: f64, v: f64) -> Result<Vec3, String> {
        self.validate()?;
        let uk = knot_vector(
            self.u_degree,
            &self.u_knots,
            &self.u_multiplicities,
            self.u_count,
        )?;
        let vk = knot_vector(
            self.v_degree,
            &self.v_knots,
            &self.v_multiplicities,
            self.v_count,
        )?;
        let (ui, ub) = basis(&uk, self.u_degree, self.u_count, u)?;
        let (vi, vb) = basis(&vk, self.v_degree, self.v_count, v)?;
        let mut sum: Vec3 = (0., 0., 0.).into();
        let mut weight = 0.;
        for (j, bv) in vb.iter().enumerate() {
            for (i, bu) in ub.iter().enumerate() {
                let k = (vi + j) * self.u_count + ui + i;
                let w = bu * bv * self.weights[k];
                sum = sum + self.poles[k] * w;
                weight += w;
            }
        }
        let p = sum * (1. / weight);
        if !p.x.is_finite() || !p.y.is_finite() || !p.z.is_finite() {
            return Err("NURBS evaluation overflow".into());
        }
        Ok(p)
    }
}

struct Reader<'a> {
    values: &'a [AcisValue],
    pos: usize,
}
impl Reader<'_> {
    fn take(&mut self) -> Result<&AcisValue, String> {
        let v = self.values.get(self.pos).ok_or("truncated exactsur")?;
        self.pos += 1;
        Ok(v)
    }
    fn word(&mut self, expected: &str) -> Result<(), String> {
        if matches!(self.take()?, AcisValue::String(s) if s == expected) {
            Ok(())
        } else {
            Err(format!("exactsur expected {expected}"))
        }
    }
    fn number(&mut self) -> Result<f64, String> {
        let value = match self.take()? {
            AcisValue::Float(v) => *v,
            AcisValue::Integer(v) => v.to_string().parse().map_err(|_| "invalid number")?,
            _ => return Err("expected number".into()),
        };
        if value.is_finite() {
            Ok(value)
        } else {
            Err("nonfinite exactsur number".into())
        }
    }
    fn integer(&mut self) -> Result<usize, String> {
        match self.take()? {
            AcisValue::Integer(v) => v
                .to_string()
                .parse()
                .map_err(|_| "invalid exactsur count".into()),
            _ => Err("expected exactsur integer".into()),
        }
    }
    fn bound(&mut self) -> Result<Option<f64>, String> {
        match self.take()? {
            AcisValue::String(s) if s == "I" => Ok(None),
            AcisValue::String(s) if s == "F" => self.number().map(Some),
            _ => Err("invalid exactsur bound".into()),
        }
    }
    fn range(&mut self) -> Result<Option<ParameterRange>, String> {
        Ok(Some(ParameterRange {
            lower: self.bound()?,
            upper: self.bound()?,
        }))
    }
    fn knots(
        &mut self,
        degree: usize,
        count: usize,
    ) -> Result<(Vec<f64>, Vec<usize>, usize), String> {
        if !(1..=16).contains(&degree) || !(2..=4096).contains(&count) {
            return Err("exactsur degree/knot limit".into());
        }
        let mut k = Vec::with_capacity(count);
        let mut m = Vec::with_capacity(count);
        for _ in 0..count {
            k.push(self.number()?);
            m.push(self.integer()?);
        }
        // This qualified open ACIS convention omits one copy at each endpoint.
        // Refuse other conventions, rather than repairing arbitrary knot arrays.
        if m[0] != degree || m[count - 1] != degree {
            return Err("unsupported ACIS endpoint multiplicities".into());
        }
        m[0] += 1;
        m[count - 1] += 1;
        let total = m
            .iter()
            .try_fold(0usize, |a, b| a.checked_add(*b))
            .ok_or("knot overflow")?;
        let poles = total.checked_sub(degree + 1).ok_or("invalid knot count")?;
        knot_vector(degree, &k, &m, poles)?;
        Ok((k, m, poles))
    }
}
/// SAT 7.0 direct `exactsur` only. Unknown subtypes/versions stay raw.
/// This does not reinterpret ASM `exact_spl_sur` trailers or subtype references.
pub fn decode_sat_exactsur(
    raw: &RawEntity,
    save_version: u32,
) -> Result<Option<BSplineSurfaceEntity>, String> {
    if save_version != 700
        || raw.type_name != "spline-surface"
        || !matches!(raw.values.get(3), Some(AcisValue::String(s)) if s=="exactsur")
    {
        return Ok(None);
    }
    let mut r = Reader {
        values: &raw.values,
        pos: 0,
    };
    let pattern = match r.take()? {
        AcisValue::Reference(v) => *v,
        _ => return Err("invalid exactsur pattern".into()),
    };
    let reversed = match r.take()? {
        AcisValue::String(v) if v == "forward" => false,
        AcisValue::String(v) if v == "reversed" => true,
        _ => return Err("invalid exactsur sense".into()),
    };
    r.word("{")?;
    r.word("exactsur")?;
    let rational = match r.take()? {
        AcisValue::String(s) if s == "nubs" => false,
        AcisValue::String(s) if s == "nurbs" => true,
        _ => return Ok(None),
    };
    let ud = r.integer()?;
    let vd = r.integer()?;
    // Unsupported periodic/singular data are retained, never made open.
    for expected in ["open", "open", "none", "none"] {
        if !matches!(r.take()?, AcisValue::String(s) if s==expected) {
            return Ok(None);
        }
    }
    let un = r.integer()?;
    let vn = r.integer()?;
    let (uk, um, uc) = r.knots(ud, un)?;
    let (vk, vm, vc) = r.knots(vd, vn)?;
    let count = uc
        .checked_mul(vc)
        .filter(|n| *n <= MAX_POLES)
        .ok_or("exactsur pole limit")?;
    let mut poles = Vec::with_capacity(count);
    let mut weights = Vec::with_capacity(count);
    for _ in 0..count {
        poles.push(Vec3::from((r.number()?, r.number()?, r.number()?)));
        weights.push(if rational { r.number()? } else { 1. });
    }
    let fit_tolerance = r.number()?;
    r.word("}")?;
    let u_range = r.range()?;
    let v_range = r.range()?;
    if r.pos != r.values.len() {
        return Err("unsupported exactsur trailing fields".into());
    }
    let surface = BSplineSurfaceEntity {
        raw: raw.clone(),
        pattern,
        u_degree: ud,
        v_degree: vd,
        u_knots: uk,
        v_knots: vk,
        u_multiplicities: um,
        v_multiplicities: vm,
        u_count: uc,
        v_count: vc,
        poles,
        weights,
        reversed,
        u_range,
        v_range,
        fit_tolerance,
    };
    surface.validate()?;
    Ok(Some(surface))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn surface() -> BSplineSurfaceEntity {
        BSplineSurfaceEntity {
            raw: RawEntity::new(0, "spline-surface"),
            pattern: crate::NULL_REF,
            u_degree: 1,
            v_degree: 1,
            u_knots: vec![0., 1.],
            v_knots: vec![0., 1.],
            u_multiplicities: vec![2, 2],
            v_multiplicities: vec![2, 2],
            u_count: 2,
            v_count: 2,
            poles: vec![
                (0., 0., 0.).into(),
                (2., 0., 0.).into(),
                (0., 3., 0.).into(),
                (2., 3., 4.).into(),
            ],
            weights: vec![1., 2., 1., 2.],
            reversed: false,
            u_range: None,
            v_range: None,
            fit_tolerance: 0.,
        }
    }
    #[test]
    fn rational_basis_and_endpoint_values_have_closed_form_expectations() {
        let s = surface();
        for (u, v) in [(0., 0.), (1., 1.), (0.25, 0.75), (0.5, 0.5)] {
            let p = s.evaluate(u, v).unwrap();
            let a = 2. * u / (1. + u);
            assert!((p.x - 2. * a).abs() < 1e-12);
            assert!((p.y - 3. * v).abs() < 1e-12);
            assert!((p.z - 4. * a * v).abs() < 1e-12);
        }
    }
    #[test]
    fn malformed_vectors_and_out_of_domain_parameters_never_panic() {
        for n in [0, 1, 3, usize::MAX] {
            let mut s = surface();
            s.u_count = n;
            assert!(s.validate().is_err());
        }
        for degree in [0, 17, usize::MAX] {
            let mut s = surface();
            s.u_degree = degree;
            assert!(s.validate().is_err());
        }
        for weight in [0., -1., f64::INFINITY, f64::NAN] {
            let mut s = surface();
            s.weights[0] = weight;
            assert!(s.validate().is_err());
        }
        let s = surface();
        for u in [-0.001, 1.001, f64::NAN, f64::INFINITY] {
            assert!(s.evaluate(u, 0.).is_err());
        }
    }

    #[test]
    fn saved_surface_ranges_are_nonempty_subdomains() {
        for range in [
            ParameterRange {
                lower: Some(0.2),
                upper: Some(0.8),
            },
            ParameterRange {
                lower: None,
                upper: Some(0.8),
            },
            ParameterRange {
                lower: Some(0.2),
                upper: None,
            },
        ] {
            let mut s = surface();
            s.u_range = Some(range);
            s.v_range = Some(range);
            s.validate().unwrap();
            // Evaluation still describes the unchanged supporting surface.
            assert_eq!(
                s.evaluate(0.5, 0.5).unwrap(),
                surface().evaluate(0.5, 0.5).unwrap()
            );
        }
        for (lower, upper) in [
            (-0.01, 0.8),
            (0.2, 1.01),
            (0.5, 0.5),
            (0.8, 0.2),
            (f64::NAN, 1.),
            (0., f64::INFINITY),
        ] {
            for u_direction in [false, true] {
                let mut s = surface();
                let range = Some(ParameterRange {
                    lower: Some(lower),
                    upper: Some(upper),
                });
                if u_direction {
                    s.u_range = range;
                } else {
                    s.v_range = range;
                }
                assert!(s.validate().is_err());
            }
        }
    }
}
