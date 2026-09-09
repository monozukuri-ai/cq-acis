//! Analytic helpers. No kernel approximation or tessellation is performed here.
use crate::{ConeSurfaceEntity, EllipseCurveEntity, PlaneSurfaceEntity, TransformEntity};
use std::{
    error::Error,
    fmt,
    ops::{Add, Mul, Neg, Sub},
};

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Vec3 {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}
impl From<(f64, f64, f64)> for Vec3 {
    fn from(v: (f64, f64, f64)) -> Self {
        Self {
            x: v.0,
            y: v.1,
            z: v.2,
        }
    }
}
impl From<Vec3> for (f64, f64, f64) {
    fn from(v: Vec3) -> Self {
        (v.x, v.y, v.z)
    }
}
impl Add for Vec3 {
    type Output = Self;
    fn add(self, b: Self) -> Self {
        (self.x + b.x, self.y + b.y, self.z + b.z).into()
    }
}
impl Sub for Vec3 {
    type Output = Self;
    fn sub(self, b: Self) -> Self {
        (self.x - b.x, self.y - b.y, self.z - b.z).into()
    }
}
impl Neg for Vec3 {
    type Output = Self;
    fn neg(self) -> Self {
        (-self.x, -self.y, -self.z).into()
    }
}
impl Mul<f64> for Vec3 {
    type Output = Self;
    fn mul(self, b: f64) -> Self {
        (self.x * b, self.y * b, self.z * b).into()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GeometryError {
    ZeroVector,
    NegativeTolerance,
    InfiniteParameter,
}
impl fmt::Display for GeometryError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ZeroVector => write!(f, "cannot normalize a zero-length vector"),
            Self::NegativeTolerance => write!(f, "tolerances must be non-negative"),
            Self::InfiniteParameter => {
                write!(f, "math domain error: infinite trigonometric parameter")
            }
        }
    }
}
impl Error for GeometryError {}

impl Vec3 {
    pub fn cross(self, b: Self) -> Self {
        (
            self.y * b.z - self.z * b.y,
            self.z * b.x - self.x * b.z,
            self.x * b.y - self.y * b.x,
        )
            .into()
    }
    pub fn dot(self, b: Self) -> f64 {
        self.x * b.x + self.y * b.y + self.z * b.z
    }
    pub fn magnitude(self) -> f64 {
        self.dot(self).sqrt()
    }
    pub fn normalized(self) -> Result<Self, GeometryError> {
        let magnitude = self.magnitude();
        if magnitude == 0.0 {
            return Err(GeometryError::ZeroVector);
        }
        Ok(self * (1.0 / magnitude))
    }
}

impl EllipseCurveEntity {
    pub fn major_radius(&self) -> f64 {
        self.major_axis.magnitude()
    }
    pub fn minor_radius(&self) -> f64 {
        self.major_radius() * self.ratio.abs()
    }
    pub fn minor_axis(&self) -> Result<Vec3, GeometryError> {
        Ok(self.normal.normalized()?.cross(self.major_axis) * self.ratio)
    }
    pub fn is_circle(&self, tolerance: f64) -> Result<bool, GeometryError> {
        is_close(self.ratio.abs(), 1.0, 0.0, tolerance)
    }
    pub fn evaluate(&self, parameter: f64) -> Result<Vec3, GeometryError> {
        if parameter.is_infinite() {
            return Err(GeometryError::InfiniteParameter);
        }
        Ok(self.center + self.major_axis * parameter.cos() + self.minor_axis()? * parameter.sin())
    }
}

impl PlaneSurfaceEntity {
    pub fn v_direction(&self) -> Vec3 {
        let direction = self.normal.cross(self.u_direction);
        if self.reverse_v {
            -direction
        } else {
            direction
        }
    }
}

impl ConeSurfaceEntity {
    pub fn major_direction(&self) -> Result<Vec3, GeometryError> {
        self.major_axis.normalized()
    }
    pub fn minor_direction(&self) -> Result<Vec3, GeometryError> {
        Ok(self.axis.normalized()?.cross(self.major_direction()?))
    }
    pub fn minor_radius(&self) -> f64 {
        self.reference_radius * self.ratio.abs()
    }
    pub fn is_cylinder(&self, tolerance: f64) -> Result<bool, GeometryError> {
        is_close(self.sin_half_angle, 0.0, 1e-9, tolerance)
    }
    pub fn is_circular(&self, tolerance: f64) -> Result<bool, GeometryError> {
        is_close(self.ratio.abs(), 1.0, 0.0, tolerance)
    }
    pub fn radius_at(&self, v: f64) -> f64 {
        self.reference_radius + v * self.sin_half_angle
    }
    pub fn apex(&self) -> Result<Option<Vec3>, GeometryError> {
        if self.is_cylinder(1e-12)? {
            return Ok(None);
        }
        let axial_offset = self.reference_radius * self.cos_half_angle / self.sin_half_angle;
        Ok(Some(self.center - self.axis.normalized()? * axial_offset))
    }
    pub fn evaluate(&self, u: f64, v: f64) -> Result<Vec3, GeometryError> {
        if u.is_infinite() {
            return Err(GeometryError::InfiniteParameter);
        }
        let axis = self.axis.normalized()?;
        let radial =
            self.major_direction()? * u.cos() + self.minor_direction()? * (self.ratio * u.sin());
        Ok(self.center + axis * (v * self.cos_half_angle) + radial * self.radius_at(v))
    }
}

// Preserve Python math.isclose behavior, including negative/NaN/infinite tolerances.
fn is_close(a: f64, b: f64, relative: f64, absolute: f64) -> Result<bool, GeometryError> {
    if relative < 0.0 || absolute < 0.0 {
        return Err(GeometryError::NegativeTolerance);
    }
    if a == b {
        return Ok(true);
    }
    if a.is_infinite() || b.is_infinite() {
        return Ok(false);
    }
    let difference = (a - b).abs();
    Ok(difference <= (relative * b).abs()
        || difference <= (relative * a).abs()
        || difference <= absolute)
}

impl TransformEntity {
    pub fn linear_determinant(&self) -> f64 {
        let v = self.matrix_values;
        let determinant = v[0] * (v[4] * v[8] - v[5] * v[7]) - v[1] * (v[3] * v[8] - v[5] * v[6])
            + v[2] * (v[3] * v[7] - v[4] * v[6]);
        self.scale.powi(3) * determinant
    }
    /// ACIS row-vector placement: scale * (vector * matrix).
    pub fn transform_vector(&self, vector: Vec3) -> Vec3 {
        let v = self.matrix_values;
        (
            self.scale * (vector.x * v[0] + vector.y * v[3] + vector.z * v[6]),
            self.scale * (vector.x * v[1] + vector.y * v[4] + vector.z * v[7]),
            self.scale * (vector.x * v[2] + vector.y * v[5] + vector.z * v[8]),
        )
            .into()
    }
    pub fn transform_point(&self, point: Vec3) -> Vec3 {
        self.transform_vector(point)
            + Vec3::from((
                self.matrix_values[9],
                self.matrix_values[10],
                self.matrix_values[11],
            ))
    }
}
