//! Experimental bounded analytic B-rep authoring, independent of parsed records.
//!
//! Coordinates are millimetres; line parameters are millimetres and ellipse
//! parameters radians. Surface charts follow OCCT (length UV for planes,
//! angular U and length V for cylinders). Pcurves are deliberately absent in
//! this experimental profile; native kernel derivation is NOT yet qualified.
use super::*;

pub const MAX_TOPOLOGY: usize = 4096;
#[derive(Debug, Clone)]
pub enum CurveSpec {
    Line {
        origin: Vec3,
        direction: Vec3,
    },
    Ellipse {
        center: Vec3,
        normal: Vec3,
        major_axis: Vec3,
        ratio: f64,
    },
}
#[derive(Debug, Clone)]
pub enum SurfaceSpec {
    Plane {
        origin: Vec3,
        normal: Vec3,
        u_direction: Vec3,
    },
    Cylinder {
        center: Vec3,
        axis: Vec3,
        x_direction: Vec3,
        radius: f64,
    },
}
#[derive(Debug, Clone)]
pub struct EdgeSpec {
    pub vertices: [usize; 2],
    pub parameters: [f64; 2],
    pub curve: CurveSpec,
}
#[derive(Debug, Clone, Copy)]
pub struct EdgeUse {
    pub edge: usize,
    pub reversed: bool,
}
#[derive(Debug, Clone)]
pub struct FaceSpec {
    pub surface: SurfaceSpec,
    pub reversed: bool,
    /// Outer loop first. Walks follow the supporting surface, before face reversal.
    pub loops: Vec<Vec<EdgeUse>>,
}
#[derive(Debug, Clone)]
pub struct BrepSpec {
    pub vertices_mm: Vec<Vec3>,
    pub edges: Vec<EdgeSpec>,
    pub faces: Vec<FaceSpec>,
    pub tolerance_mm: f64,
}
/// Only the semantic builder can create this immutable model. This is not a
/// general model rewriter and cannot carry native attributes/history/raw bytes.
#[derive(Debug, Clone)]
pub struct AuthoredBrep {
    model: AcisModel,
}
impl AuthoredBrep {
    pub fn model(&self) -> &AcisModel {
        &self.model
    }
}
fn frame(a: Vec3, b: Vec3) -> bool {
    finite(a)
        && finite(b)
        && (a.magnitude() - 1.0).abs() < 1e-9
        && (b.magnitude() - 1.0).abs() < 1e-9
        && a.dot(b).abs() < 1e-9
}
fn coord(p: Vec3) -> bool {
    finite(p) && components(p).iter().all(|x| x.abs() <= MAX_MM)
}
fn unbounded() -> Option<ParameterRange> {
    Some(ParameterRange {
        lower: None,
        upper: None,
    })
}
impl CurveSpec {
    fn validate(&self) -> Result<(), AuthoringError> {
        ensure(
            match *self {
                Self::Line { origin, direction } => {
                    coord(origin) && finite(direction) && (direction.magnitude() - 1.0).abs() < 1e-9
                }
                Self::Ellipse {
                    center,
                    normal,
                    major_axis,
                    ratio,
                } => {
                    coord(center)
                        && finite(major_axis)
                        && (MIN_LENGTH_MM..=MAX_MM).contains(&major_axis.magnitude())
                        && frame(normal, major_axis * (1.0 / major_axis.magnitude()))
                        && ratio.is_finite()
                        && ratio > 0.0
                        && ratio <= 1.0
                        && major_axis.magnitude() * ratio >= MIN_LENGTH_MM
                }
            },
            "invalid analytic curve frame/radius/coordinate",
        )
    }
    fn point(&self, t: f64) -> Vec3 {
        match *self {
            Self::Line { origin, direction } => origin + direction * t,
            Self::Ellipse {
                center,
                normal,
                major_axis,
                ratio,
            } => center + major_axis * t.cos() + normal.cross(major_axis) * (ratio * t.sin()),
        }
    }
}
impl SurfaceSpec {
    fn validate(&self) -> Result<(), AuthoringError> {
        ensure(
            match *self {
                Self::Plane {
                    origin,
                    normal,
                    u_direction,
                } => coord(origin) && frame(normal, u_direction),
                Self::Cylinder {
                    center,
                    axis,
                    x_direction,
                    radius,
                } => {
                    coord(center)
                        && frame(axis, x_direction)
                        && radius.is_finite()
                        && (MIN_LENGTH_MM..=MAX_MM).contains(&radius)
                }
            },
            "invalid analytic surface frame/radius/coordinate",
        )
    }
    fn distance(&self, p: Vec3) -> f64 {
        match *self {
            Self::Plane { origin, normal, .. } => (p - origin).dot(normal).abs(),
            Self::Cylinder {
                center,
                axis,
                radius,
                ..
            } => {
                let v = p - center;
                ((v - axis * v.dot(axis)).magnitude() - radius).abs()
            }
        }
    }
}
impl BrepSpec {
    pub fn build(&self) -> Result<AuthoredBrep, AuthoringError> {
        let nv = self.vertices_mm.len();
        let ne = self.edges.len();
        let nf = self.faces.len();
        ensure(
            nv > 0
                && ne > 0
                && nf > 0
                && nv <= MAX_TOPOLOGY
                && ne <= MAX_TOPOLOGY
                && nf <= MAX_TOPOLOGY,
            "analytic topology budget exceeded or empty",
        )?;
        ensure(
            self.tolerance_mm.is_finite()
                && self.tolerance_mm > 0.0
                && self.tolerance_mm <= RESABS * UNITS_MM,
            "source tolerance exceeds analytic profile",
        )?;
        ensure(
            self.vertices_mm.iter().copied().all(coord),
            "invalid vertex coordinate",
        )?;
        let tol = RESABS * UNITS_MM;
        let mut incident = vec![None; nv];
        for (i, e) in self.edges.iter().enumerate() {
            ensure(
                e.vertices.iter().all(|&v| v < nv),
                "edge vertex outside table",
            )?;
            e.curve.validate()?;
            let [a, b] = e.parameters;
            ensure(
                a.is_finite() && b.is_finite() && b > a && a.abs() <= 1e8 && b.abs() <= 1e8,
                "invalid analytic edge parameter interval",
            )?;
            if matches!(e.curve, CurveSpec::Ellipse { .. }) {
                ensure(
                    b - a <= std::f64::consts::TAU + 1e-9,
                    "ellipse interval exceeds one turn",
                )?;
            }
            for (j, t) in [a, b].into_iter().enumerate() {
                ensure(
                    (e.curve.point(t) - self.vertices_mm[e.vertices[j]]).magnitude() <= tol,
                    "edge parameter does not meet vertex",
                )?;
                incident[e.vertices[j]] = Some(i);
            }
            ensure(
                (e.vertices[0] != e.vertices[1])
                    || matches!(e.curve, CurveSpec::Ellipse { .. })
                        && (b - a - std::f64::consts::TAU).abs() <= 1e-9,
                "closed edge is not a full ellipse",
            )?;
        }
        ensure(incident.iter().all(Option::is_some), "unused vertex")?;
        let mut loops = Vec::new();
        let mut coedges = Vec::new();
        let mut uses = vec![Vec::new(); ne];
        let mut face_loops = Vec::new();
        for (fi, f) in self.faces.iter().enumerate() {
            f.surface.validate()?;
            ensure(
                !f.loops.is_empty() && f.loops.len() <= MAX_TOPOLOGY,
                "empty face or loop budget exceeded",
            )?;
            face_loops.push(loops.len());
            for walk in &f.loops {
                ensure(
                    !walk.is_empty() && coedges.len() + walk.len() <= MAX_TOPOLOGY * 2,
                    "empty loop or coedge budget exceeded",
                )?;
                let li = loops.len();
                let first = coedges.len();
                loops.push((fi, first, walk.len()));
                for (j, u) in walk.iter().enumerate() {
                    ensure(u.edge < ne, "coedge edge outside table")?;
                    let e = &self.edges[u.edge];
                    let next = walk[(j + 1) % walk.len()];
                    ensure(next.edge < ne, "coedge edge outside table")?;
                    ensure(
                        e.vertices[usize::from(!u.reversed)]
                            == self.edges[next.edge].vertices[usize::from(next.reversed)],
                        "loop walk is disconnected",
                    )?;
                    for k in 0..=32 {
                        let t = e.parameters[0]
                            + (e.parameters[1] - e.parameters[0]) * (k as f64 / 32.0);
                        let p = e.curve.point(t);
                        ensure(
                            coord(p) && f.surface.distance(p) <= tol,
                            "edge leaves supporting surface/coordinate budget",
                        )?;
                    }
                    uses[u.edge].push((coedges.len(), fi, u.reversed ^ f.reversed));
                    coedges.push((
                        li,
                        first + (j + 1) % walk.len(),
                        first + (j + walk.len() - 1) % walk.len(),
                        *u,
                    ));
                }
            }
        }
        ensure(
            uses.iter().all(|u| u.len() == 2 && u[0].2 != u[1].2),
            "edge must have two oppositely oriented uses",
        )?;
        // A single shell must be connected through its shared edges.
        let mut reached = BTreeSet::from([0]);
        loop {
            let before = reached.len();
            for u in &uses {
                if reached.contains(&u[0].1) || reached.contains(&u[1].1) {
                    reached.insert(u[0].1);
                    reached.insert(u[1].1);
                }
            }
            if before == reached.len() {
                break;
            }
        }
        ensure(reached.len() == nf, "disconnected shell")?;
        let fs = 4;
        let ls = fs + nf;
        let cs = ls + loops.len();
        let es = cs + coedges.len();
        let vs = es + ne;
        let ps = vs + nv;
        let ss = ps + nv;
        let gs = ss + nf;
        let mut out = Vec::with_capacity(gs + ne);
        let mut h = raw(0, "asmheader", -1);
        h.values = vec![AcisValue::String(ASM_VERSION.into())];
        out.push(Entity::Raw(h));
        out.push(Entity::Body(BodyEntity {
            raw: raw(1, "body", 0),
            pattern: NULL_REF,
            lump: reference(2),
            wire: NULL_REF,
            transform: NULL_REF,
        }));
        out.push(Entity::Lump(LumpEntity {
            raw: raw(2, "lump", -1),
            pattern: NULL_REF,
            next_lump: NULL_REF,
            shell: reference(3),
            body: reference(1),
        }));
        out.push(Entity::Shell(ShellEntity {
            raw: raw(3, "shell", -1),
            pattern: NULL_REF,
            next_shell: NULL_REF,
            subshell: NULL_REF,
            face: reference(fs),
            wire: NULL_REF,
            lump: reference(2),
        }));
        for (i, f) in self.faces.iter().enumerate() {
            out.push(Entity::Face(FaceEntity {
                raw: raw(out.len(), "face", (i + 1) as i32),
                pattern: NULL_REF,
                next_face: if i + 1 < nf {
                    reference(fs + i + 1)
                } else {
                    NULL_REF
                },
                loop_ref: reference(ls + face_loops[i]),
                shell: reference(3),
                subshell: NULL_REF,
                surface: reference(ss + i),
                reversed: f.reversed,
                double_sided: false,
                containment_in: None,
            }));
        }
        for (i, &(fi, first, _)) in loops.iter().enumerate() {
            out.push(Entity::Loop(LoopEntity {
                raw: raw(out.len(), "loop", -1),
                pattern: NULL_REF,
                next_loop: if loops.get(i + 1).is_some_and(|x| x.0 == fi) {
                    reference(ls + i + 1)
                } else {
                    NULL_REF
                },
                coedge: reference(cs + first),
                face: reference(fs + fi),
            }));
        }
        for (i, &(li, next, prev, u)) in coedges.iter().enumerate() {
            let pair = &uses[u.edge];
            let partner = if pair[0].0 == i { pair[1].0 } else { pair[0].0 };
            // Semantic input walks follow the supporting surface. ACIS walks
            // follow the oriented face: reversing a face reverses both the
            // cyclic order and every edge use. Keeping only the face flag can
            // produce a readable body with invalid native mass properties.
            let reversed_face = self.faces[loops[li].0].reversed;
            out.push(Entity::Coedge(CoedgeEntity {
                raw: raw(out.len(), "coedge", -1),
                pattern: NULL_REF,
                next_coedge: reference(cs + if reversed_face { prev } else { next }),
                previous_coedge: reference(cs + if reversed_face { next } else { prev }),
                partner_coedge: reference(cs + partner),
                edge: reference(es + u.edge),
                reversed: u.reversed ^ reversed_face,
                loop_ref: reference(ls + li),
                pcurve: NULL_REF,
            }));
        }
        for (i, e) in self.edges.iter().enumerate() {
            out.push(Entity::Edge(EdgeEntity {
                raw: raw(out.len(), "edge", (nf + 1 + i) as i32),
                pattern: NULL_REF,
                start_vertex: reference(vs + e.vertices[0]),
                end_vertex: reference(vs + e.vertices[1]),
                start_parameter: Some(e.parameters[0]),
                end_parameter: Some(e.parameters[1]),
                coedge: reference(cs + uses[i][0].0),
                curve: reference(gs + i),
                reversed: false,
                convexity: Some("unknown".into()),
            }));
        }
        for (i, edge) in incident.iter().enumerate() {
            out.push(Entity::Vertex(VertexEntity {
                raw: raw(out.len(), "vertex", -1),
                pattern: NULL_REF,
                edge: reference(es + edge.unwrap()),
                point: reference(ps + i),
            }));
        }
        for &p in &self.vertices_mm {
            out.push(Entity::Point(PointEntity {
                raw: raw(out.len(), "point", -1),
                pattern: NULL_REF,
                location: p * (1.0 / UNITS_MM),
            }));
        }
        for f in &self.faces {
            out.push(match f.surface {
                SurfaceSpec::Plane {
                    origin,
                    normal,
                    u_direction,
                } => Entity::PlaneSurface(PlaneSurfaceEntity {
                    raw: raw(out.len(), "plane-surface", -1),
                    pattern: NULL_REF,
                    origin: origin * (1.0 / UNITS_MM),
                    normal,
                    u_direction: u_direction * (1.0 / UNITS_MM),
                    reverse_v: false,
                    u_range: unbounded(),
                    v_range: unbounded(),
                }),
                SurfaceSpec::Cylinder {
                    center,
                    axis,
                    x_direction,
                    radius,
                } => Entity::ConeSurface(ConeSurfaceEntity {
                    raw: raw(out.len(), "cone-surface", -1),
                    pattern: NULL_REF,
                    center: center * (1.0 / UNITS_MM),
                    axis,
                    major_axis: x_direction * (radius / UNITS_MM),
                    ratio: 1.0,
                    profile_range: unbounded(),
                    sin_half_angle: 0.0,
                    cos_half_angle: 1.0,
                    reference_radius: radius / UNITS_MM,
                    parameter_scale: radius / UNITS_MM,
                    reversed: false,
                    u_range: unbounded(),
                    v_range: unbounded(),
                }),
            });
        }
        for e in &self.edges {
            out.push(match e.curve {
                CurveSpec::Line { origin, direction } => {
                    Entity::StraightCurve(StraightCurveEntity {
                        raw: raw(out.len(), "straight-curve", -1),
                        pattern: NULL_REF,
                        origin: origin * (1.0 / UNITS_MM),
                        direction: direction * (1.0 / UNITS_MM),
                        parameter_range: unbounded(),
                    })
                }
                CurveSpec::Ellipse {
                    center,
                    normal,
                    major_axis,
                    ratio,
                } => Entity::EllipseCurve(EllipseCurveEntity {
                    raw: raw(out.len(), "ellipse-curve", -1),
                    pattern: NULL_REF,
                    center: center * (1.0 / UNITS_MM),
                    normal,
                    major_axis: major_axis * (1.0 / UNITS_MM),
                    ratio,
                    parameter_range: unbounded(),
                }),
            });
        }
        let metadata = AcisMetadata {
            units_mm: Some(UNITS_MM),
            resabs: Some(RESABS),
            resnor: Some(RESNOR),
            container: Some(AcisContainer::AsmSab),
            save_version: Some(23200.into()),
            product_id: Some("cq-acis".into()),
            modeler_version: Some(format!("ASM {ASM_VERSION} NT")),
            creation_date: Some(String::new()),
            dialect: Some("authored-asm23200-analytic-experimental".into()),
        };
        let model = AcisModel::new(metadata, out, Vec::new())
            .map_err(|_| fail("analytic generated reference closure failed"))?;
        Ok(AuthoredBrep { model })
    }
}
