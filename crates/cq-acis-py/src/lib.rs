//! cq-acis native class and module; shared conversion lives in acis-py-bridge.
use acis_core::{entities::*, AcisModel, Vec3};
use acis_py_bridge::{
    diagnostic_to_python, entity_from_python, entity_to_python, metadata_to_python,
    model_from_python, reference_from_python, vector_to_python,
};
#[cfg(feature = "python-module")]
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::{
    prelude::*,
    types::{PyBytes, PyTuple},
    IntoPyObjectExt,
};
use std::sync::{Arc, OnceLock};
pyo3::import_exception!(cq_acis.model, AcisModelError);
fn model_error(message: impl ToString) -> PyErr {
    AcisModelError::new_err(message.to_string())
}
#[cfg(feature = "python-module")]
fn geometry_error(error: acis_core::GeometryError) -> PyErr {
    PyValueError::new_err(error.to_string())
}
fn optional_to_py<'py, T>(
    py: Python<'py>,
    value: Option<&T>,
    write: impl FnOnce(Python<'py>, &T) -> PyResult<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    match value {
        Some(v) => write(py, v),
        None => Ok(py.None().into_bound(py)),
    }
}

/// Immutable Rust-owned snapshot. Python properties create compatibility dataclasses.
#[pyclass(frozen, module = "cq_acis._native")]
pub struct NativeModel {
    inner: Arc<AcisModel>,
    subtypes: OnceLock<acis_core::subtypes::SubtypeResolver>,
}

// Kept as a Rust re-export for existing downstream source users.
pub use acis_py_bridge::model_to_python;

#[cfg(feature = "python-module")]
#[pyfunction]
#[pyo3(signature = (data, source_id="sab-input"))]
fn parse_sab_model(data: &Bound<'_, PyBytes>, source_id: &str) -> PyResult<NativeModel> {
    let limits = acis_core::sab::SabLimits::default();
    if data.as_bytes().len() > limits.max_bytes {
        return Err(PyValueError::new_err("SAB input exceeds byte limit"));
    }
    let bytes = data.as_bytes().to_vec();
    let result = data
        .py()
        .detach(|| acis_core::sab::parse_sab(&bytes, source_id, &limits))
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(NativeModel {
        inner: Arc::new(result.model),
        subtypes: OnceLock::new(),
    })
}

#[cfg(feature = "python-module")]
#[pyfunction]
fn decode_sat_exactsur<'py>(
    raw: &Bound<'py, PyAny>,
    save_version: u32,
) -> PyResult<Bound<'py, PyAny>> {
    let entity = entity_from_python(raw)?;
    let decoded = acis_core::nurbs::decode_sat_exactsur(entity.raw(), save_version)
        .map_err(PyValueError::new_err)?;
    match decoded {
        Some(surface) => entity_to_python(raw.py(), &Entity::BSplineSurface(surface)),
        None => Ok(raw.clone()),
    }
}

#[pymethods]
impl NativeModel {
    #[staticmethod]
    fn from_model(model: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Self {
            inner: Arc::new(model_from_python(model)?),
            subtypes: OnceLock::new(),
        })
    }
    fn __len__(&self) -> usize {
        self.inner.len()
    }
    /// Partial view; never changes the raw entity or the model tolerance.
    fn tolerant_topology<'py>(&self, reference: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        let py = reference.py();
        let Some(entity) = self
            .inner
            .resolve(reference_from_python(reference)?)
            .map_err(model_error)?
        else {
            return Ok(py.None().into_bound(py));
        };
        let version = self
            .inner
            .metadata()
            .save_version
            .as_ref()
            .and_then(|v| v.to_string().parse().ok())
            .unwrap_or(0);
        let view = acis_core::tolerant::decode(entity.raw(), version).map_err(model_error)?;
        optional_to_py(py, view.as_ref(), acis_py_bridge::tolerant_to_python)
    }
    #[getter]
    fn subtype_table<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let table = self
            .subtypes
            .get_or_init(|| acis_core::subtypes::SubtypeResolver::new(Arc::clone(&self.inner)));
        acis_py_bridge::subtype_table_to_python(py, table.table())
    }
    fn resolve_subtype<'py>(&self, reference: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        let py = reference.py();
        let Some(entity) = self
            .inner
            .resolve(reference_from_python(reference)?)
            .map_err(model_error)?
        else {
            return Ok(py.None().into_bound(py));
        };
        let resolver = self
            .subtypes
            .get_or_init(|| acis_core::subtypes::SubtypeResolver::new(Arc::clone(&self.inner)));
        let resolved = resolver.resolve(entity.index()).map_err(model_error)?;
        optional_to_py(
            py,
            resolved.as_ref(),
            acis_py_bridge::resolved_subtype_to_python,
        )
    }
    fn __repr__(&self) -> String {
        format!(
            "NativeModel(entities={}, bodies={})",
            self.inner.len(),
            self.inner.bodies().count()
        )
    }
    #[getter]
    fn metadata<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        metadata_to_python(py, self.inner.metadata())
    }
    #[getter]
    fn entities<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(
            py,
            self.inner
                .entities()
                .iter()
                .map(|e| entity_to_python(py, e))
                .collect::<PyResult<Vec<_>>>()?,
        )
    }
    #[getter]
    fn diagnostics<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(
            py,
            self.inner
                .diagnostics()
                .iter()
                .map(|d| diagnostic_to_python(py, d))
                .collect::<PyResult<Vec<_>>>()?,
        )
    }
    fn resolve<'py>(&self, reference: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        let py = reference.py();
        optional_to_py(
            py,
            self.inner
                .resolve(reference_from_python(reference)?)
                .map_err(model_error)?,
            entity_to_python,
        )
    }
    fn bodies<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(
            py,
            self.inner
                .bodies()
                .map(|body| entity_to_python(py, &Entity::Body(body.clone())))
                .collect::<PyResult<Vec<_>>>()?,
        )
    }
    fn referenced_by<'py>(&self, reference: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyTuple>> {
        let py = reference.py();
        let indices = self
            .inner
            .referenced_by(reference_from_python(reference)?)
            .map_err(model_error)?;
        PyTuple::new(
            py,
            indices
                .into_iter()
                .map(|i| entity_to_python(py, &self.inner.entities()[i]))
                .collect::<PyResult<Vec<_>>>()?,
        )
    }
    fn to_model<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        acis_py_bridge::model_ref_to_python(py, &self.inner)
    }
}

#[cfg(feature = "python-module")]
#[pyfunction]
fn validate_model(model: &Bound<'_, PyAny>) -> PyResult<()> {
    model_from_python(model).map(|_| ())
}
#[cfg(feature = "python-module")]
#[pyfunction]
fn resolve_index(reference: &Bound<'_, PyAny>, entity_count: usize) -> PyResult<Option<usize>> {
    acis_core::resolve_index(reference_from_python(reference)?, entity_count).map_err(model_error)
}

// Numeric helpers keep the existing Python value classes while using Rust math.
#[cfg(feature = "python-module")]
type Triple = (f64, f64, f64);
#[cfg(feature = "python-module")]
#[pyfunction]
fn vector(operation: &str, a: Triple, b: Triple, scalar: f64) -> PyResult<Triple> {
    let a = Vec3::from(a);
    let b = Vec3::from(b);
    let v = match operation {
        "cross" => a.cross(b),
        "add" => a + b,
        "sub" => a - b,
        "neg" => -a,
        "mul" => a * scalar,
        "normalized" => a.normalized().map_err(geometry_error)?,
        _ => return Err(PyValueError::new_err("unknown vector operation")),
    };
    Ok(v.into())
}
#[cfg(feature = "python-module")]
#[pyfunction]
fn vector_scalar(operation: &str, a: Triple, b: Triple) -> PyResult<f64> {
    let a = Vec3::from(a);
    let b = Vec3::from(b);
    match operation {
        "dot" => Ok(a.dot(b)),
        "magnitude" => Ok(a.magnitude()),
        _ => Err(PyValueError::new_err("unknown vector operation")),
    }
}

#[cfg(feature = "python-module")]
#[pyfunction]
fn geometry<'py>(
    value: &Bound<'py, PyAny>,
    operation: &str,
    parameters: Vec<f64>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = value.py();
    let parameter = |index| {
        parameters
            .get(index)
            .copied()
            .ok_or_else(|| PyTypeError::new_err("missing geometry parameter"))
    };
    match entity_from_python(value)? {
        Entity::EllipseCurve(e) => match operation {
            "major_radius" => e.major_radius().into_bound_py_any(py),
            "minor_radius" => e.minor_radius().into_bound_py_any(py),
            "minor_axis" => vector_to_python(py, e.minor_axis().map_err(geometry_error)?),
            "is_circle" => e
                .is_circle(parameter(0)?)
                .map_err(geometry_error)?
                .into_bound_py_any(py),
            "evaluate" => vector_to_python(py, e.evaluate(parameter(0)?).map_err(geometry_error)?),
            _ => Err(PyValueError::new_err("unknown ellipse operation")),
        },
        Entity::PlaneSurface(e) if operation == "v_direction" => {
            vector_to_python(py, e.v_direction())
        }
        Entity::ConeSurface(e) => match operation {
            "major_direction" => vector_to_python(py, e.major_direction().map_err(geometry_error)?),
            "minor_direction" => vector_to_python(py, e.minor_direction().map_err(geometry_error)?),
            "minor_radius" => e.minor_radius().into_bound_py_any(py),
            "is_cylinder" => e
                .is_cylinder(parameter(0)?)
                .map_err(geometry_error)?
                .into_bound_py_any(py),
            "is_circular" => e
                .is_circular(parameter(0)?)
                .map_err(geometry_error)?
                .into_bound_py_any(py),
            "radius_at" => e.radius_at(parameter(0)?).into_bound_py_any(py),
            "apex" => match e.apex().map_err(geometry_error)? {
                Some(v) => vector_to_python(py, v),
                None => Ok(py.None().into_bound(py)),
            },
            "evaluate" => vector_to_python(
                py,
                e.evaluate(parameter(0)?, parameter(1)?)
                    .map_err(geometry_error)?,
            ),
            _ => Err(PyValueError::new_err("unknown cone operation")),
        },
        Entity::SphereSurface(e) if operation == "evaluate" => vector_to_python(
            py,
            e.evaluate(parameter(0)?, parameter(1)?)
                .map_err(geometry_error)?,
        ),
        Entity::TorusSurface(e) if operation == "evaluate" => vector_to_python(
            py,
            e.evaluate(parameter(0)?, parameter(1)?)
                .map_err(geometry_error)?,
        ),
        Entity::BSplineCurve(e) => match operation {
            "evaluate" => vector_to_python(
                py,
                e.evaluate(parameter(0)?).map_err(PyValueError::new_err)?,
            ),
            "validate" => {
                e.validate().map_err(PyValueError::new_err)?;
                Ok(py.None().into_bound(py))
            }
            _ => Err(PyValueError::new_err("unknown B-spline operation")),
        },
        Entity::BSplineSurface(e) => match operation {
            "evaluate" => vector_to_python(
                py,
                e.evaluate(parameter(0)?, parameter(1)?)
                    .map_err(PyValueError::new_err)?,
            ),
            "validate" => {
                e.validate().map_err(PyValueError::new_err)?;
                Ok(py.None().into_bound(py))
            }
            _ => Err(PyValueError::new_err("unknown B-spline operation")),
        },
        Entity::Transform(e) => match operation {
            "linear_determinant" => e.linear_determinant().into_bound_py_any(py),
            "transform_vector" => vector_to_python(
                py,
                e.transform_vector((parameter(0)?, parameter(1)?, parameter(2)?).into()),
            ),
            "transform_point" => vector_to_python(
                py,
                e.transform_point((parameter(0)?, parameter(1)?, parameter(2)?).into()),
            ),
            _ => Err(PyValueError::new_err("unknown transform operation")),
        },
        _ => Err(PyValueError::new_err("unsupported geometry operation")),
    }
}

#[cfg(feature = "python-module")]
#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_sab_model, module)?)?;
    module.add_function(wrap_pyfunction!(decode_sat_exactsur, module)?)?;
    module.add_class::<NativeModel>()?;
    module.add_function(wrap_pyfunction!(validate_model, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_index, module)?)?;
    module.add_function(wrap_pyfunction!(vector, module)?)?;
    module.add_function(wrap_pyfunction!(vector_scalar, module)?)?;
    module.add_function(wrap_pyfunction!(geometry, module)?)?;
    module.add("CORE_VERSION", "0.2.1")?;
    module.add("MODEL_API_VERSION", acis_py_bridge::MODEL_API_VERSION)?;
    Ok(())
}
