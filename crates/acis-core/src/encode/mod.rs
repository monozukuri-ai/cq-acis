//! Exact-profile SAB encoding of generated models. Parsed/raw entities cannot
//! enter this API; opaque records and opaque history are never copied.
use crate::{
    authoring::{validate_box, AuthoredBox, AuthoringError, BOX_ENTITY_COUNT},
    Entity, EntityRef, ParameterRange, Vec3,
};
use std::{error::Error, fmt};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SabWriteProfile {
    Asm23200MetricBox,
    /// Metric box targeting ASM 23100 (Inventor 2026).
    Asm23100MetricBox,
    /// Analytic B-rep candidate; native kernel pcurve derivation is unqualified.
    Asm23200AnalyticExperimental,
    /// Analytic geometry targeting ASM 23100; bounded kernel profile.
    Asm23100AnalyticExperimental,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HistoryMode {
    /// DC source geometry: no history and outer document state zero.
    None,
    /// Final BRep: one insertion state, paired with RSe state-one helpers in M3.
    InsertionOnlyStateOne,
}
#[derive(Debug, Clone, Copy)]
pub struct SabWriteLimits {
    pub max_bytes: usize,
    pub max_entities: usize,
}
impl Default for SabWriteLimits {
    fn default() -> Self {
        Self {
            max_bytes: 64 * 1024,
            max_entities: BOX_ENTITY_COUNT,
        }
    }
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EncodeError {
    InvalidModel(AuthoringError),
    BudgetExceeded,
    InvalidField,
}
impl fmt::Display for EncodeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidModel(e) => write!(f, "{e}"),
            Self::BudgetExceeded => write!(f, "SAB write budget exceeded"),
            Self::InvalidField => write!(f, "field outside the selected ASM write profile"),
        }
    }
}
impl Error for EncodeError {}

/// Bounded encoder. Only explicitly supported output profiles are selectable.
///
/// The profile selects the SAB save version and both ASM version strings.
/// Authored models are immutable semantic input; their default metadata is not
/// mutated when selecting an older output target. Default output remains 23200.
pub struct SabEncoder {
    profile: SabWriteProfile,
    limits: SabWriteLimits,
}
impl Default for SabEncoder {
    fn default() -> Self {
        Self::new(
            SabWriteProfile::Asm23200MetricBox,
            SabWriteLimits::default(),
        )
    }
}
impl SabEncoder {
    pub fn new(profile: SabWriteProfile, limits: SabWriteLimits) -> Self {
        Self { profile, limits }
    }
    pub fn encode(
        &self,
        generated: &AuthoredBox,
        history: HistoryMode,
    ) -> Result<Vec<u8>, EncodeError> {
        if !matches!(
            self.profile,
            SabWriteProfile::Asm23200MetricBox | SabWriteProfile::Asm23100MetricBox
        ) {
            return Err(EncodeError::InvalidField);
        }
        validate_box(generated.model()).map_err(EncodeError::InvalidModel)?;
        self.encode_model(generated.model(), history)
    }
    /// Only a semantic BrepSpec builder can supply this immutable value.
    pub fn encode_brep(
        &self,
        generated: &crate::authoring::brep::AuthoredBrep,
        history: HistoryMode,
    ) -> Result<Vec<u8>, EncodeError> {
        if !matches!(
            self.profile,
            SabWriteProfile::Asm23200AnalyticExperimental
                | SabWriteProfile::Asm23100AnalyticExperimental
        ) {
            return Err(EncodeError::InvalidField);
        }
        self.encode_model(generated.model(), history)
    }
    fn encode_model(
        &self,
        model: &crate::AcisModel,
        history: HistoryMode,
    ) -> Result<Vec<u8>, EncodeError> {
        if model.entities().len() > self.limits.max_entities {
            return Err(EncodeError::BudgetExceeded);
        }
        let mut w = Writer {
            bytes: Vec::new(),
            limit: self.limits.max_bytes,
        };
        let (save_version, asm_version) =
            match self.profile {
                SabWriteProfile::Asm23100MetricBox
                | SabWriteProfile::Asm23100AnalyticExperimental => (23100, "231.6.4.65535"),
                SabWriteProfile::Asm23200MetricBox
                | SabWriteProfile::Asm23200AnalyticExperimental => (23200, "232.6.0.65535"),
            };
        w.append(b"ASM BinaryFile4")?;
        // Native framing: record count unspecified (zero); top-level entries
        // are asmheader and one body. Bit one is the native ASM profile flag.
        for value in [
            save_version,
            0,
            2,
            if history == HistoryMode::None { 2 } else { 3 },
        ] {
            w.append(&i32::to_le_bytes(value))?;
        }
        w.text("cq-acis")?;
        w.text(&format!("ASM {asm_version} NT"))?;
        w.text("")?;
        let metadata = model.metadata();
        for value in [metadata.units_mm, metadata.resabs, metadata.resnor] {
            w.number(value.ok_or(EncodeError::InvalidField)?)?;
        }
        for entity in model.entities() {
            w.name(&entity.raw().type_name)?;
            w.reference(entity.raw().attributes)?;
            let id: i32 = entity
                .raw()
                .entity_id
                .as_ref()
                .ok_or(EncodeError::InvalidField)?
                .try_into()
                .map_err(|_| EncodeError::InvalidField)?;
            w.integer(id)?;
            match entity {
                Entity::Raw(_) if entity.index() == 0 => w.text(asm_version)?,
                Entity::Body(x) => w.references(&[x.pattern, x.lump, x.wire, x.transform])?,
                Entity::Lump(x) => w.references(&[x.pattern, x.next_lump, x.shell, x.body])?,
                Entity::Shell(x) => {
                    w.references(&[x.pattern, x.next_shell, x.subshell, x.face, x.wire, x.lump])?
                }
                Entity::Face(x) => {
                    w.references(&[
                        x.pattern,
                        x.next_face,
                        x.loop_ref,
                        x.shell,
                        x.subshell,
                        x.surface,
                    ])?;
                    w.boolean(x.reversed)?;
                    w.boolean(x.double_sided)?;
                }
                Entity::Loop(x) => w.references(&[x.pattern, x.next_loop, x.coedge, x.face])?,
                Entity::Coedge(x) => {
                    w.references(&[
                        x.pattern,
                        x.next_coedge,
                        x.previous_coedge,
                        x.partner_coedge,
                        x.edge,
                    ])?;
                    w.boolean(x.reversed)?;
                    w.reference(x.loop_ref)?;
                    w.integer(0)?;
                    w.reference(x.pcurve)?;
                }
                Entity::Edge(x) => {
                    w.reference(x.pattern)?;
                    w.reference(x.start_vertex)?;
                    w.number(x.start_parameter.ok_or(EncodeError::InvalidField)?)?;
                    w.reference(x.end_vertex)?;
                    w.number(x.end_parameter.ok_or(EncodeError::InvalidField)?)?;
                    w.references(&[x.coedge, x.curve])?;
                    w.boolean(x.reversed)?;
                    w.text(x.convexity.as_deref().ok_or(EncodeError::InvalidField)?)?;
                }
                Entity::Vertex(x) => {
                    w.references(&[x.pattern, x.edge])?;
                    w.integer(0)?;
                    w.reference(x.point)?;
                }
                Entity::Point(x) => {
                    w.reference(x.pattern)?;
                    w.vector(19, x.location)?;
                }
                Entity::StraightCurve(x) => {
                    w.reference(x.pattern)?;
                    w.vector(19, x.origin)?;
                    w.vector(20, x.direction)?;
                    w.range(x.parameter_range)?;
                }
                Entity::PlaneSurface(x) => {
                    w.reference(x.pattern)?;
                    w.vector(19, x.origin)?;
                    w.vector(20, x.normal)?;
                    w.vector(20, x.u_direction)?;
                    w.boolean(x.reverse_v)?;
                    w.range(x.u_range)?;
                    w.range(x.v_range)?;
                }
                Entity::EllipseCurve(x) => {
                    w.reference(x.pattern)?;
                    w.vector(19, x.center)?;
                    w.vector(20, x.normal)?;
                    w.vector(20, x.major_axis)?;
                    w.number(x.ratio)?;
                    w.range(x.parameter_range)?;
                }
                Entity::ConeSurface(x) => {
                    w.reference(x.pattern)?;
                    w.vector(19, x.center)?;
                    w.vector(20, x.axis)?;
                    w.vector(20, x.major_axis)?;
                    w.number(x.ratio)?;
                    w.range(x.profile_range)?;
                    w.number(x.sin_half_angle)?;
                    w.number(x.cos_half_angle)?;
                    w.number(x.parameter_scale)?;
                    w.boolean(x.reversed)?;
                    w.range(x.u_range)?;
                    w.range(x.v_range)?;
                }
                _ => return Err(EncodeError::InvalidField),
            }
            w.append(&[17])?;
        }
        if history == HistoryMode::InsertionOnlyStateOne {
            w.insertion_history(model.entities().len())?;
        }
        // The native terminator is a lineage name, without a tag17 trailer.
        w.name("End-of-ASM-data")?;
        Ok(w.bytes)
    }
}
struct Writer {
    bytes: Vec<u8>,
    limit: usize,
}
impl Writer {
    fn append(&mut self, b: &[u8]) -> Result<(), EncodeError> {
        if self
            .bytes
            .len()
            .checked_add(b.len())
            .filter(|&n| n <= self.limit)
            .is_none()
        {
            return Err(EncodeError::BudgetExceeded);
        }
        self.bytes.extend_from_slice(b);
        Ok(())
    }
    fn name(&mut self, name: &str) -> Result<(), EncodeError> {
        let mut parts = name.split('-').peekable();
        while let Some(p) = parts.next() {
            if p.is_empty() || !p.is_ascii() {
                return Err(EncodeError::InvalidField);
            }
            let length = u8::try_from(p.len()).map_err(|_| EncodeError::InvalidField)?;
            self.append(&[if parts.peek().is_some() { 14 } else { 13 }, length])?;
            self.append(p.as_bytes())?;
        }
        Ok(())
    }
    fn text(&mut self, value: &str) -> Result<(), EncodeError> {
        self.append(&[
            7,
            u8::try_from(value.len()).map_err(|_| EncodeError::InvalidField)?,
        ])?;
        self.append(value.as_bytes())
    }
    fn word(&mut self, tag: u8, value: i32) -> Result<(), EncodeError> {
        self.append(&[tag])?;
        self.append(&value.to_le_bytes())
    }
    fn integer(&mut self, value: i32) -> Result<(), EncodeError> {
        self.word(4, value)
    }
    fn reference(&mut self, value: EntityRef) -> Result<(), EncodeError> {
        self.word(
            12,
            i32::try_from(value.0).map_err(|_| EncodeError::InvalidField)?,
        )
    }
    fn references(&mut self, refs: &[EntityRef]) -> Result<(), EncodeError> {
        for &r in refs {
            self.reference(r)?;
        }
        Ok(())
    }
    fn boolean(&mut self, value: bool) -> Result<(), EncodeError> {
        self.append(&[if value { 10 } else { 11 }])
    }
    fn number(&mut self, value: f64) -> Result<(), EncodeError> {
        if !value.is_finite() {
            return Err(EncodeError::InvalidField);
        }
        self.append(&[6])?;
        self.append(&value.to_le_bytes())
    }
    fn vector(&mut self, tag: u8, value: Vec3) -> Result<(), EncodeError> {
        self.append(&[tag])?;
        for x in [value.x, value.y, value.z] {
            if !x.is_finite() {
                return Err(EncodeError::InvalidField);
            }
            self.append(&x.to_le_bytes())?;
        }
        Ok(())
    }
    fn range(&mut self, range: Option<ParameterRange>) -> Result<(), EncodeError> {
        let r = range.ok_or(EncodeError::InvalidField)?;
        for x in [r.lower, r.upper] {
            self.boolean(x.is_some())?;
            if let Some(v) = x {
                self.number(v)?;
            }
        }
        Ok(())
    }
    fn insertion_history(&mut self, n: usize) -> Result<(), EncodeError> {
        // Explicit one-state constructor; no opaque bytes are read. The
        // framing defaults 19/2 and state one were accepted in the M1 oracle.
        self.name("Begin-of-ASM-History-Data")?;
        self.name("history_stream")?;
        for v in [1, 1, 0, 19] {
            self.integer(v)?;
        }
        for v in [-1, 0, 0, -1] {
            self.reference(EntityRef(v))?;
        }
        self.append(&[17])?;
        self.name("delta_state")?;
        for v in [1, 1, 0] {
            self.integer(v)?;
        }
        for v in [-1, -1, 0, -1, 0] {
            self.reference(EntityRef(v))?;
        }
        self.boolean(false)?;
        self.integer(1)?;
        self.reference(EntityRef(0))?;
        self.integer(2)?;
        for slot in 1..n {
            self.integer(1)?;
            self.reference(EntityRef(-1))?;
            self.reference(EntityRef(slot as i64))?;
        }
        for _ in 0..3 {
            self.integer(0)?;
        }
        self.append(&[17])?;
        self.name("End-of-ASM-History-Section")
    }
}
