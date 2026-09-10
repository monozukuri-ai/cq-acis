//! Typed geometry shared by text and binary ACIS adapters.
use crate::geometry::Vec3;
use crate::{EntityRef, RawEntity};

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ParameterRange {
    pub lower: Option<f64>,
    pub upper: Option<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BodyEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub lump: EntityRef,
    pub wire: EntityRef,
    pub transform: EntityRef,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LumpEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub next_lump: EntityRef,
    pub shell: EntityRef,
    pub body: EntityRef,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ShellEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub next_shell: EntityRef,
    pub subshell: EntityRef,
    pub face: EntityRef,
    pub wire: EntityRef,
    pub lump: EntityRef,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FaceEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub next_face: EntityRef,
    pub loop_ref: EntityRef,
    pub shell: EntityRef,
    pub subshell: EntityRef,
    pub surface: EntityRef,
    pub reversed: bool,
    pub double_sided: bool,
    pub containment_in: Option<bool>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LoopEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub next_loop: EntityRef,
    pub coedge: EntityRef,
    pub face: EntityRef,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CoedgeEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub next_coedge: EntityRef,
    pub previous_coedge: EntityRef,
    pub partner_coedge: EntityRef,
    pub edge: EntityRef,
    pub reversed: bool,
    pub loop_ref: EntityRef,
    pub pcurve: EntityRef,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EdgeEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub start_vertex: EntityRef,
    pub start_parameter: Option<f64>,
    pub end_vertex: EntityRef,
    pub end_parameter: Option<f64>,
    pub coedge: EntityRef,
    pub curve: EntityRef,
    pub reversed: bool,
    pub convexity: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct VertexEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub edge: EntityRef,
    pub point: EntityRef,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PointEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub location: Vec3,
}

#[derive(Debug, Clone, PartialEq)]
pub struct StraightCurveEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub origin: Vec3,
    pub direction: Vec3,
    pub parameter_range: Option<ParameterRange>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EllipseCurveEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub center: Vec3,
    pub normal: Vec3,
    pub major_axis: Vec3,
    pub ratio: f64,
    pub parameter_range: Option<ParameterRange>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PlaneSurfaceEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub origin: Vec3,
    pub normal: Vec3,
    pub u_direction: Vec3,
    pub reverse_v: bool,
    pub u_range: Option<ParameterRange>,
    pub v_range: Option<ParameterRange>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ConeSurfaceEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub center: Vec3,
    pub axis: Vec3,
    pub major_axis: Vec3,
    pub ratio: f64,
    pub profile_range: Option<ParameterRange>,
    pub sin_half_angle: f64,
    pub cos_half_angle: f64,
    pub reference_radius: f64,
    /// Saved ACIS chart scale; not a geometric radius.
    pub parameter_scale: f64,
    pub reversed: bool,
    pub u_range: Option<ParameterRange>,
    pub v_range: Option<ParameterRange>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TransformEntity {
    pub raw: RawEntity,
    pub matrix_values: [f64; 12],
    pub scale: f64,
    pub rotated: bool,
    pub reflected: bool,
    pub sheared: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SphereSurfaceEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub center: Vec3,
    pub radius: f64,
    pub pole: Vec3,
    pub u_direction: Vec3,
    pub reversed: bool,
    pub u_range: Option<ParameterRange>,
    pub v_range: Option<ParameterRange>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TorusSurfaceEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub center: Vec3,
    pub axis: Vec3,
    pub major_radius: f64,
    pub minor_radius: f64,
    pub u_direction: Vec3,
    pub reversed: bool,
    pub u_range: Option<ParameterRange>,
    pub v_range: Option<ParameterRange>,
}

/// Explicit clamped, non-periodic rational B-spline curve in the saved parameter.
#[derive(Debug, Clone, PartialEq)]
pub struct BSplineCurveEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub degree: usize,
    pub knots: Vec<f64>,
    pub multiplicities: Vec<usize>,
    pub poles: Vec<Vec3>,
    pub weights: Vec<f64>,
    pub parameter_range: Option<ParameterRange>,
    pub fit_tolerance: f64,
}

/// Explicit, non-periodic, clamped tensor-product surface. Poles are V-major.
#[derive(Debug, Clone, PartialEq)]
pub struct BSplineSurfaceEntity {
    pub raw: RawEntity,
    pub pattern: EntityRef,
    pub u_degree: usize,
    pub v_degree: usize,
    pub u_knots: Vec<f64>,
    pub v_knots: Vec<f64>,
    pub u_multiplicities: Vec<usize>,
    pub v_multiplicities: Vec<usize>,
    pub u_count: usize,
    pub v_count: usize,
    pub poles: Vec<Vec3>,
    pub weights: Vec<f64>,
    pub reversed: bool,
    pub u_range: Option<ParameterRange>,
    pub v_range: Option<ParameterRange>,
    pub fit_tolerance: f64,
}

/// Unknown entities remain raw; bytes do not imply decoded semantics.
#[derive(Debug, Clone, PartialEq)]
pub enum Entity {
    Raw(RawEntity),
    Body(BodyEntity),
    Lump(LumpEntity),
    Shell(ShellEntity),
    Face(FaceEntity),
    Loop(LoopEntity),
    Coedge(CoedgeEntity),
    Edge(EdgeEntity),
    Vertex(VertexEntity),
    Point(PointEntity),
    StraightCurve(StraightCurveEntity),
    EllipseCurve(EllipseCurveEntity),
    PlaneSurface(PlaneSurfaceEntity),
    ConeSurface(ConeSurfaceEntity),
    SphereSurface(SphereSurfaceEntity),
    TorusSurface(TorusSurfaceEntity),
    BSplineSurface(BSplineSurfaceEntity),
    BSplineCurve(BSplineCurveEntity),
    Transform(TransformEntity),
}

impl Entity {
    pub fn raw(&self) -> &RawEntity {
        match self {
            Self::Raw(raw) => raw,
            Self::Body(entity) => &entity.raw,
            Self::Lump(entity) => &entity.raw,
            Self::Shell(entity) => &entity.raw,
            Self::Face(entity) => &entity.raw,
            Self::Loop(entity) => &entity.raw,
            Self::Coedge(entity) => &entity.raw,
            Self::Edge(entity) => &entity.raw,
            Self::Vertex(entity) => &entity.raw,
            Self::Point(entity) => &entity.raw,
            Self::StraightCurve(entity) => &entity.raw,
            Self::EllipseCurve(entity) => &entity.raw,
            Self::PlaneSurface(entity) => &entity.raw,
            Self::ConeSurface(entity) => &entity.raw,
            Self::SphereSurface(entity) => &entity.raw,
            Self::TorusSurface(entity) => &entity.raw,
            Self::BSplineSurface(entity) => &entity.raw,
            Self::BSplineCurve(entity) => &entity.raw,
            Self::Transform(entity) => &entity.raw,
        }
    }
    pub fn index(&self) -> usize {
        self.raw().index
    }
    pub fn references(&self) -> Vec<EntityRef> {
        let mut refs = self.raw().references();
        match self {
            Self::Raw(_) => {}
            Self::Body(entity) => {
                refs.extend([entity.pattern, entity.lump, entity.wire, entity.transform])
            }
            Self::Lump(entity) => {
                refs.extend([entity.pattern, entity.next_lump, entity.shell, entity.body])
            }
            Self::Shell(entity) => refs.extend([
                entity.pattern,
                entity.next_shell,
                entity.subshell,
                entity.face,
                entity.wire,
                entity.lump,
            ]),
            Self::Face(entity) => refs.extend([
                entity.pattern,
                entity.next_face,
                entity.loop_ref,
                entity.shell,
                entity.subshell,
                entity.surface,
            ]),
            Self::Loop(entity) => {
                refs.extend([entity.pattern, entity.next_loop, entity.coedge, entity.face])
            }
            Self::Coedge(entity) => refs.extend([
                entity.pattern,
                entity.next_coedge,
                entity.previous_coedge,
                entity.partner_coedge,
                entity.edge,
                entity.loop_ref,
                entity.pcurve,
            ]),
            Self::Edge(entity) => refs.extend([
                entity.pattern,
                entity.start_vertex,
                entity.end_vertex,
                entity.coedge,
                entity.curve,
            ]),
            Self::Vertex(entity) => refs.extend([entity.pattern, entity.edge, entity.point]),
            Self::Point(entity) => refs.extend([entity.pattern]),
            Self::StraightCurve(entity) => refs.extend([entity.pattern]),
            Self::EllipseCurve(entity) => refs.extend([entity.pattern]),
            Self::PlaneSurface(entity) => refs.extend([entity.pattern]),
            Self::ConeSurface(entity) => refs.extend([entity.pattern]),
            Self::SphereSurface(entity) => refs.extend([entity.pattern]),
            Self::TorusSurface(entity) => refs.extend([entity.pattern]),
            Self::BSplineSurface(entity) => refs.extend([entity.pattern]),
            Self::BSplineCurve(entity) => refs.extend([entity.pattern]),
            Self::Transform(_) => {}
        }
        refs
    }
}
