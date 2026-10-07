//! Source-free authoring for the bounded ASM 23200 metric box profile.
//!
//! This is a generated-model API, not an editor for parsed entities. No source
//! records, opaque payloads, attributes, transforms, or general history enter it.
use crate::*;
use std::{
    collections::{BTreeMap, BTreeSet},
    error::Error,
    fmt,
};

pub const BOX_ENTITY_COUNT: usize = 86;
pub const UNITS_MM: f64 = 10.0;
pub const RESABS: f64 = 1e-6;
pub const RESNOR: f64 = 1e-10;
pub const ASM_VERSION: &str = "232.6.0.65535";
const MAX_MM: f64 = 1e6;
const MIN_LENGTH_MM: f64 = 32.0 * RESABS * UNITS_MM;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuthoringError {
    pub entity_index: Option<usize>,
    pub message: &'static str,
}
impl fmt::Display for AuthoringError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.message)?;
        if let Some(i) = self.entity_index {
            write!(f, " (entity {i})")?;
        }
        Ok(())
    }
}
impl Error for AuthoringError {}
fn fail(message: &'static str) -> AuthoringError {
    AuthoringError {
        entity_index: None,
        message,
    }
}
fn ensure(ok: bool, message: &'static str) -> Result<(), AuthoringError> {
    if ok {
        Ok(())
    } else {
        Err(fail(message))
    }
}
fn finite(v: Vec3) -> bool {
    v.x.is_finite() && v.y.is_finite() && v.z.is_finite()
}
fn components(v: Vec3) -> [f64; 3] {
    [v.x, v.y, v.z]
}
fn near(a: Vec3, b: Vec3) -> bool {
    (a - b).magnitude() <= RESABS
}
fn reference(i: usize) -> EntityRef {
    EntityRef(i as i64)
}
fn raw(i: usize, name: &str, id: i32) -> RawEntity {
    let mut r = RawEntity::new(i, name);
    r.entity_id = Some(id.into());
    r
}
fn bounded_range(upper: f64) -> Option<ParameterRange> {
    Some(ParameterRange {
        lower: Some(0.0),
        upper: Some(upper),
    })
}

/// Axis-aligned box. Sizes and minimum corner are explicitly in millimetres.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BoxSpec {
    pub size_mm: Vec3,
    pub origin_mm: Vec3,
}
impl BoxSpec {
    pub fn new(size_mm: Vec3, origin_mm: Vec3) -> Self {
        Self { size_mm, origin_mm }
    }

    pub fn build(self) -> Result<AuthoredBox, AuthoringError> {
        ensure(
            finite(self.size_mm) && finite(self.origin_mm),
            "non-finite box input",
        )?;
        ensure(
            components(self.size_mm)
                .iter()
                .all(|&x| (MIN_LENGTH_MM..=MAX_MM).contains(&x)),
            "box size outside tolerance/coordinate budget",
        )?;
        let maximum = self.origin_mm + self.size_mm;
        ensure(
            components(self.origin_mm)
                .into_iter()
                .chain(components(maximum))
                .all(|x| x.abs() <= MAX_MM),
            "box placement outside coordinate budget",
        )?;
        let o = self.origin_mm * (1.0 / UNITS_MM);
        let d = self.size_mm * (1.0 / UNITS_MM);
        let p: [Vec3; 8] = [
            (0.0, 0.0, 0.0),
            (d.x, 0.0, 0.0),
            (d.x, d.y, 0.0),
            (0.0, d.y, 0.0),
            (0.0, 0.0, d.z),
            (d.x, 0.0, d.z),
            (d.x, d.y, d.z),
            (0.0, d.y, d.z),
        ]
        .map(|v| o + Vec3::from(v));
        // Counter-clockwise walks when viewed from outside the solid.
        let walks = [
            [0, 3, 2, 1],
            [4, 5, 6, 7],
            [0, 4, 7, 3],
            [1, 2, 6, 5],
            [0, 1, 5, 4],
            [3, 7, 6, 2],
        ];
        let mut uses: BTreeMap<(usize, usize), Vec<usize>> = BTreeMap::new();
        for (f, walk) in walks.iter().enumerate() {
            for j in 0..4 {
                let (a, b) = (walk[j], walk[(j + 1) % 4]);
                uses.entry((a.min(b), a.max(b)))
                    .or_default()
                    .push(16 + f * 4 + j);
            }
        }
        let edges: Vec<_> = uses.keys().copied().collect();
        let mut e = Vec::with_capacity(BOX_ENTITY_COUNT);
        let mut h = raw(0, "asmheader", -1);
        h.values = vec![AcisValue::String(ASM_VERSION.into())];
        e.push(Entity::Raw(h));
        e.push(Entity::Body(BodyEntity {
            raw: raw(1, "body", 0),
            pattern: NULL_REF,
            lump: reference(2),
            wire: NULL_REF,
            transform: NULL_REF,
        }));
        e.push(Entity::Lump(LumpEntity {
            raw: raw(2, "lump", -1),
            pattern: NULL_REF,
            next_lump: NULL_REF,
            shell: reference(3),
            body: reference(1),
        }));
        e.push(Entity::Shell(ShellEntity {
            raw: raw(3, "shell", -1),
            pattern: NULL_REF,
            next_shell: NULL_REF,
            subshell: NULL_REF,
            face: reference(4),
            wire: NULL_REF,
            lump: reference(2),
        }));
        for f in 0..6 {
            e.push(Entity::Face(FaceEntity {
                raw: raw(e.len(), "face", f + 1),
                pattern: NULL_REF,
                next_face: if f == 5 {
                    NULL_REF
                } else {
                    reference(5 + f as usize)
                },
                loop_ref: reference(10 + f as usize),
                shell: reference(3),
                subshell: NULL_REF,
                surface: reference(68 + f as usize),
                reversed: false,
                double_sided: false,
                containment_in: None,
            }));
        }
        for f in 0..6 {
            e.push(Entity::Loop(LoopEntity {
                raw: raw(e.len(), "loop", -1),
                pattern: NULL_REF,
                next_loop: NULL_REF,
                coedge: reference(16 + f * 4),
                face: reference(4 + f),
            }));
        }
        for (f, walk) in walks.iter().enumerate() {
            for j in 0..4 {
                let (a, b) = (walk[j], walk[(j + 1) % 4]);
                let key = (a.min(b), a.max(b));
                let edge = edges
                    .iter()
                    .position(|&v| v == key)
                    .expect("generated edge");
                let i = 16 + f * 4 + j;
                let partner = uses[&key]
                    .iter()
                    .copied()
                    .find(|&v| v != i)
                    .expect("paired generated edge");
                e.push(Entity::Coedge(CoedgeEntity {
                    raw: raw(i, "coedge", -1),
                    pattern: NULL_REF,
                    next_coedge: reference(16 + f * 4 + (j + 1) % 4),
                    previous_coedge: reference(16 + f * 4 + (j + 3) % 4),
                    partner_coedge: reference(partner),
                    edge: reference(40 + edge),
                    reversed: a != key.0,
                    loop_ref: reference(10 + f),
                    pcurve: NULL_REF,
                }));
            }
        }
        for (k, &(a, b)) in edges.iter().enumerate() {
            let length_mm = (p[b] - p[a]).magnitude() * UNITS_MM;
            e.push(Entity::Edge(EdgeEntity {
                raw: raw(e.len(), "edge", 7 + k as i32),
                pattern: NULL_REF,
                start_vertex: reference(52 + a),
                start_parameter: Some(0.0),
                end_vertex: reference(52 + b),
                end_parameter: Some(length_mm),
                coedge: reference(uses[&(a, b)][0]),
                curve: reference(74 + k),
                reversed: false,
                convexity: Some("unknown".into()),
            }));
        }
        for v in 0..8 {
            let edge = edges
                .iter()
                .position(|&(a, b)| a == v || b == v)
                .expect("incident generated edge");
            e.push(Entity::Vertex(VertexEntity {
                raw: raw(e.len(), "vertex", -1),
                pattern: NULL_REF,
                edge: reference(40 + edge),
                point: reference(60 + v),
            }));
        }
        for point in p {
            e.push(Entity::Point(PointEntity {
                raw: raw(e.len(), "point", -1),
                pattern: NULL_REF,
                location: point,
            }));
        }
        for walk in walks {
            let u = p[walk[1]] - p[walk[0]];
            let v = p[walk[3]] - p[walk[0]];
            let normal = u
                .cross(v)
                .normalized()
                .map_err(|_| fail("degenerate face"))?;
            e.push(Entity::PlaneSurface(PlaneSurfaceEntity {
                raw: raw(e.len(), "plane-surface", -1),
                pattern: NULL_REF,
                origin: p[walk[0]],
                normal,
                u_direction: u * (1.0 / (u.magnitude() * UNITS_MM)),
                reverse_v: false,
                u_range: bounded_range(u.magnitude() * UNITS_MM),
                v_range: bounded_range(v.magnitude() * UNITS_MM),
            }));
        }
        for &(a, b) in &edges {
            let delta = p[b] - p[a];
            let length_mm = delta.magnitude() * UNITS_MM;
            e.push(Entity::StraightCurve(StraightCurveEntity {
                raw: raw(e.len(), "straight-curve", -1),
                pattern: NULL_REF,
                origin: p[a],
                direction: delta * (1.0 / length_mm),
                parameter_range: bounded_range(length_mm),
            }));
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
            dialect: Some("authored-asm23200-metric-box".into()),
        };
        let model = AcisModel::new(metadata, e, Vec::new())
            .map_err(|_| fail("generated reference closure failed"))?;
        let validation = validate_box(&model)?;
        Ok(AuthoredBox {
            spec: self,
            model,
            validation,
        })
    }
}

/// Only the source-free builder can construct this value; its model is immutable.
#[derive(Debug, Clone)]
pub struct AuthoredBox {
    spec: BoxSpec,
    model: AcisModel,
    validation: BoxValidation,
}
impl AuthoredBox {
    pub fn spec(&self) -> BoxSpec {
        self.spec
    }
    pub fn model(&self) -> &AcisModel {
        &self.model
    }
    pub fn validation(&self) -> &BoxValidation {
        &self.validation
    }
}
#[derive(Debug, Clone, PartialEq)]
pub struct BoxValidation {
    pub minimum_mm: Vec3,
    pub maximum_mm: Vec3,
    pub volume_mm3: f64,
}

/// Independently checks the bounded topology, ownership, analytic geometry,
/// orientation, and units. This does not grant native-kernel qualification.
/// A parsed model can be checked, but cannot be passed to the encoder.
pub fn validate_box(model: &AcisModel) -> Result<BoxValidation, AuthoringError> {
    ensure(
        model.entities().len() == BOX_ENTITY_COUNT,
        "box entity budget/count differs",
    )?;
    let m = model.metadata();
    ensure(
        m.units_mm == Some(UNITS_MM)
            && m.resabs == Some(RESABS)
            && m.resnor == Some(RESNOR)
            && m.save_version == Some(23200.into())
            && m.container == Some(AcisContainer::AsmSab),
        "unsupported authoring profile",
    )?;
    let entities = model.entities();
    let mut counts = BTreeMap::new();
    let mut ids = BTreeSet::new();
    for (i, e) in entities.iter().enumerate() {
        ensure(e.index() == i, "non-dense entity identity")?;
        for r in e.references() {
            resolve_index(r, entities.len()).map_err(|_| fail("reference outside entity table"))?;
        }
        ensure(
            e.raw().attributes == NULL_REF,
            "attributes outside box profile",
        )?;
        let id = e
            .raw()
            .entity_id
            .as_ref()
            .ok_or_else(|| fail("missing semantic entity ID"))?;
        let has_id = matches!(e, Entity::Body(_) | Entity::Face(_) | Entity::Edge(_));
        ensure(
            if has_id {
                id >= &BigInt::from(0) && ids.insert(id.clone())
            } else {
                id == &BigInt::from(-1)
            },
            "invalid or duplicate semantic entity ID",
        )?;
        let (name, pattern) = match e {
            Entity::Raw(r)
                if i == 0
                    && r.type_name == "asmheader"
                    && r.values == [AcisValue::String(ASM_VERSION.into())] =>
            {
                ("asmheader", NULL_REF)
            }
            Entity::Body(x) => ("body", x.pattern),
            Entity::Lump(x) => ("lump", x.pattern),
            Entity::Shell(x) => ("shell", x.pattern),
            Entity::Face(x) => ("face", x.pattern),
            Entity::Loop(x) => ("loop", x.pattern),
            Entity::Coedge(x) => ("coedge", x.pattern),
            Entity::Edge(x) => ("edge", x.pattern),
            Entity::Vertex(x) => ("vertex", x.pattern),
            Entity::Point(x) => ("point", x.pattern),
            Entity::PlaneSurface(x) => ("plane-surface", x.pattern),
            Entity::StraightCurve(x) => ("straight-curve", x.pattern),
            _ => return Err(fail("entity outside box profile")),
        };
        ensure(
            pattern == NULL_REF && e.raw().type_name == name,
            "entity name/pattern outside profile",
        )?;
        *counts.entry(name).or_insert(0usize) += 1;
    }
    for (name, n) in [
        ("asmheader", 1),
        ("body", 1),
        ("lump", 1),
        ("shell", 1),
        ("face", 6),
        ("loop", 6),
        ("coedge", 24),
        ("edge", 12),
        ("vertex", 8),
        ("point", 8),
        ("plane-surface", 6),
        ("straight-curve", 12),
    ] {
        ensure(
            counts.get(name) == Some(&n),
            "box entity type counts differ",
        )?;
    }
    // All references are bounds checked above, including null. Type-specific
    // access never indexes using an unchecked reference.
    let get = |r: EntityRef| -> Result<&Entity, AuthoringError> {
        let i = resolve_index(r, entities.len())
            .map_err(|_| fail("invalid reference"))?
            .ok_or_else(|| fail("required reference is null"))?;
        Ok(&entities[i])
    };
    let point = |r: EntityRef| -> Result<Vec3, AuthoringError> {
        if let Entity::Vertex(v) = get(r)? {
            if let Entity::Point(p) = get(v.point)? {
                return Ok(p.location);
            }
        }
        Err(fail("vertex/point reference type differs"))
    };
    let mut min = Vec3::from((f64::INFINITY, f64::INFINITY, f64::INFINITY));
    let mut max = Vec3::from((f64::NEG_INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY));
    let mut point_owners = BTreeSet::new();
    let mut vertex_degrees = BTreeMap::new();
    for e in entities {
        if let Entity::Vertex(v) = e {
            ensure(
                point_owners.insert(v.point.0),
                "point shared by multiple vertices",
            )?;
            let p = point(reference(v.raw.index))?;
            ensure(
                finite(p) && components(p).iter().all(|x| x.abs() <= MAX_MM / UNITS_MM),
                "invalid point coordinate",
            )?;
            min = (min.x.min(p.x), min.y.min(p.y), min.z.min(p.z)).into();
            max = (max.x.max(p.x), max.y.max(p.y), max.z.max(p.z)).into();
            match get(v.edge)? {
                Entity::Edge(edge)
                    if [edge.start_vertex, edge.end_vertex].contains(&reference(v.raw.index)) => {}
                _ => return Err(fail("vertex incidence differs")),
            }
        }
    }
    let d = max - min;
    ensure(
        components(d).iter().all(|&x| {
            (MIN_LENGTH_MM / UNITS_MM - RESABS * 0.001..=MAX_MM / UNITS_MM + RESABS * 0.001)
                .contains(&x)
        }),
        "degenerate box bounds",
    )?;
    let mut corners = BTreeSet::new();
    for e in entities {
        if let Entity::Point(p) = e {
            let mut corner = 0;
            for (axis, (value, (lo, hi))) in components(p.location)
                .into_iter()
                .zip(components(min).into_iter().zip(components(max)))
                .enumerate()
            {
                if (value - hi).abs() <= RESABS {
                    corner |= 1 << axis;
                } else {
                    ensure((value - lo).abs() <= RESABS, "point is not a box corner")?;
                }
            }
            ensure(corners.insert(corner), "duplicate box corner")?;
        }
    }
    let body = entities
        .iter()
        .find_map(|e| {
            if let Entity::Body(x) = e {
                Some(x)
            } else {
                None
            }
        })
        .expect("counted body");
    ensure(
        body.wire == NULL_REF && body.transform == NULL_REF && body.raw.entity_id == Some(0.into()),
        "body outside single solid profile",
    )?;
    let Entity::Lump(lump) = get(body.lump)? else {
        return Err(fail("body/lump type differs"));
    };
    ensure(
        lump.body == reference(body.raw.index) && lump.next_lump == NULL_REF,
        "lump ownership differs",
    )?;
    let Entity::Shell(shell) = get(lump.shell)? else {
        return Err(fail("lump/shell type differs"));
    };
    ensure(
        shell.lump == body.lump
            && shell.next_shell == NULL_REF
            && shell.subshell == NULL_REF
            && shell.wire == NULL_REF,
        "shell ownership differs",
    )?;
    let mut faces = BTreeSet::new();
    let mut loops = BTreeSet::new();
    let mut coedges = BTreeSet::new();
    let mut surfaces = BTreeSet::new();
    let mut edge_uses: BTreeMap<i64, Vec<i64>> = BTreeMap::new();
    let mut face_ref = shell.face;
    let mut normals = BTreeSet::new();
    for _ in 0..6 {
        ensure(faces.insert(face_ref.0), "face chain cycle")?;
        let Entity::Face(f) = get(face_ref)? else {
            return Err(fail("face reference type differs"));
        };
        ensure(
            f.shell == lump.shell
                && f.subshell == NULL_REF
                && !f.reversed
                && !f.double_sided
                && f.containment_in.is_none(),
            "face ownership/sense differs",
        )?;
        ensure(
            loops.insert(f.loop_ref.0) && surfaces.insert(f.surface.0),
            "shared loop/surface",
        )?;
        let Entity::Loop(l) = get(f.loop_ref)? else {
            return Err(fail("loop reference type differs"));
        };
        let Entity::PlaneSurface(s) = get(f.surface)? else {
            return Err(fail("surface reference type differs"));
        };
        ensure(
            l.face == face_ref && l.next_loop == NULL_REF,
            "loop ownership differs",
        )?;
        ensure(
            finite(s.origin)
                && finite(s.normal)
                && finite(s.u_direction)
                && (s.normal.magnitude() - 1.0).abs() <= RESNOR
                && (s.u_direction.magnitude() - 1.0 / UNITS_MM).abs() <= RESNOR
                && s.normal.dot(s.u_direction).abs() <= RESNOR
                && !s.reverse_v,
            "invalid plane frame",
        )?;
        let axis = components(s.normal)
            .iter()
            .position(|v| (v.abs() - 1.0).abs() <= RESNOR)
            .ok_or_else(|| fail("non-axis-aligned box plane"))?;
        ensure(
            components(s.normal)
                .iter()
                .enumerate()
                .all(|(i, &v)| i == axis || v == 0.0)
                && normals.insert((axis, components(s.normal)[axis] > 0.0)),
            "duplicate/non-axis-aligned face normal",
        )?;
        for range in [s.u_range, s.v_range] {
            let Some(ParameterRange {
                lower: Some(lo),
                upper: Some(hi),
            }) = range
            else {
                return Err(fail("missing finite plane range"));
            };
            ensure(
                lo == 0.0
                    && hi.is_finite()
                    && (MIN_LENGTH_MM - RESABS * UNITS_MM * 0.001
                        ..=MAX_MM + RESABS * UNITS_MM * 0.001)
                        .contains(&hi),
                "invalid plane range",
            )?;
        }
        let mut current = l.coedge;
        let mut walk = Vec::new();
        for _ in 0..4 {
            ensure(coedges.insert(current.0), "shared/repeated coedge")?;
            let Entity::Coedge(c) = get(current)? else {
                return Err(fail("coedge reference type differs"));
            };
            let Entity::Coedge(next) = get(c.next_coedge)? else {
                return Err(fail("next coedge type differs"));
            };
            let Entity::Coedge(prev) = get(c.previous_coedge)? else {
                return Err(fail("previous coedge type differs"));
            };
            let Entity::Coedge(partner) = get(c.partner_coedge)? else {
                return Err(fail("partner coedge type differs"));
            };
            let Entity::Edge(edge) = get(c.edge)? else {
                return Err(fail("edge reference type differs"));
            };
            ensure(
                c.loop_ref == f.loop_ref
                    && c.pcurve == NULL_REF
                    && next.previous_coedge == current
                    && prev.next_coedge == current,
                "coedge ownership/links differ",
            )?;
            ensure(
                c.partner_coedge != current
                    && partner.partner_coedge == current
                    && partner.edge == c.edge
                    && partner.reversed != c.reversed
                    && partner.loop_ref != c.loop_ref,
                "coedge partner/sense differs",
            )?;
            let (a, b) = if c.reversed {
                (edge.end_vertex, edge.start_vertex)
            } else {
                (edge.start_vertex, edge.end_vertex)
            };
            let Entity::Edge(next_edge) = get(next.edge)? else {
                return Err(fail("next edge reference type differs"));
            };
            let next_a = if next.reversed {
                next_edge.end_vertex
            } else {
                next_edge.start_vertex
            };
            ensure(b == next_a, "open loop vertex walk")?;
            let p = point(a)?;
            ensure(
                (p - s.origin).dot(s.normal).abs() <= RESABS,
                "loop off face plane",
            )?;
            walk.push(p);
            edge_uses.entry(c.edge.0).or_default().push(current.0);
            current = c.next_coedge;
        }
        ensure(
            current == l.coedge,
            "loop does not close after four coedges",
        )?;
        ensure(
            (walk[1] - walk[0]).cross(walk[2] - walk[0]).dot(s.normal) > 0.0
                && (s.origin - (min + max) * 0.5).dot(s.normal) > RESABS,
            "inward or degenerate face",
        )?;
        // The plane chart agrees with both adjacent rectangle sides in mm.
        let u = s.u_direction;
        let v = s.v_direction();
        ensure(
            near(s.origin, walk[0])
                && near(s.origin + u * s.u_range.unwrap().upper.unwrap(), walk[1])
                && near(s.origin + v * s.v_range.unwrap().upper.unwrap(), walk[3]),
            "plane range/loop chart differs",
        )?;
        face_ref = f.next_face;
    }
    ensure(
        face_ref == NULL_REF && edge_uses.len() == 12,
        "face chain/edge coverage differs",
    )?;
    let mut curves = BTreeSet::new();
    for e in entities {
        if let Entity::Edge(edge) = e {
            let usage = edge_uses
                .get(&(edge.raw.index as i64))
                .ok_or_else(|| fail("unused edge"))?;
            ensure(
                usage.len() == 2
                    && usage.contains(&edge.coedge.0)
                    && !edge.reversed
                    && edge.convexity.as_deref() == Some("unknown"),
                "edge use/sense differs",
            )?;
            ensure(
                edge.start_vertex != edge.end_vertex && curves.insert(edge.curve.0),
                "degenerate edge/shared curve",
            )?;
            *vertex_degrees.entry(edge.start_vertex.0).or_insert(0) += 1;
            *vertex_degrees.entry(edge.end_vertex.0).or_insert(0) += 1;
            let Entity::StraightCurve(c) = get(edge.curve)? else {
                return Err(fail("curve reference type differs"));
            };
            let (Some(a), Some(b)) = (edge.start_parameter, edge.end_parameter) else {
                return Err(fail("missing edge parameters"));
            };
            ensure(
                a == 0.0
                    && b.is_finite()
                    && (MIN_LENGTH_MM - RESABS * UNITS_MM * 0.001
                        ..=MAX_MM + RESABS * UNITS_MM * 0.001)
                        .contains(&b)
                    && finite(c.origin)
                    && finite(c.direction)
                    && (c.direction.magnitude() - 1.0 / UNITS_MM).abs() <= RESNOR
                    && c.parameter_range == bounded_range(b),
                "invalid line/parameter range",
            )?;
            ensure(
                near(c.origin + c.direction * a, point(edge.start_vertex)?)
                    && near(c.origin + c.direction * b, point(edge.end_vertex)?),
                "line endpoints differ from vertices",
            )?;
        }
    }
    ensure(
        vertex_degrees.len() == 8 && vertex_degrees.values().all(|&n| n == 3),
        "box vertex degree differs",
    )?;
    Ok(BoxValidation {
        minimum_mm: min * UNITS_MM,
        maximum_mm: max * UNITS_MM,
        volume_mm3: d.x * d.y * d.z * UNITS_MM.powi(3),
    })
}
