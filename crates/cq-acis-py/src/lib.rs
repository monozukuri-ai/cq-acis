//! PyO3 boundary for acis-core. Python/CadQuery objects never enter the core crate.
use acis_core::{
    entities::*, AcisContainer, AcisDiagnostic, AcisMetadata, AcisModel, AcisValue, CountedString,
    EntityRef, RawEntity, SatRecord, SourceSpan, Vec3,
};
#[cfg(feature = "python-module")]
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::{
    prelude::*,
    types::{PyBytes, PyFloat, PyInt, PyString, PyTuple},
    IntoPyObjectExt,
};
use std::sync::Arc;
mod entities;
use entities::*;

pyo3::import_exception!(cq_acis.model, AcisModelError);
fn model_error(message: impl ToString) -> PyErr {
    AcisModelError::new_err(message.to_string())
}
#[cfg(feature = "python-module")]
fn geometry_error(error: acis_core::GeometryError) -> PyErr {
    PyValueError::new_err(error.to_string())
}

fn exact_int(value: &Bound<'_, PyAny>) -> PyResult<()> {
    if !value.get_type().is(value.py().get_type::<PyInt>()) {
        return Err(model_error("entity index must be an integer"));
    }
    Ok(())
}
fn index(value: &Bound<'_, PyAny>) -> PyResult<usize> {
    exact_int(value)?;
    value
        .extract()
        .map_err(|_| model_error("entity index is outside the native address range"))
}
fn reference(value: &Bound<'_, PyAny>) -> PyResult<EntityRef> {
    let value = value.getattr("index")?;
    exact_int(&value)?;
    value
        .extract()
        .map(EntityRef)
        .map_err(|_| model_error("entity reference is outside the native index range"))
}
fn reference_argument(value: &Bound<'_, PyAny>) -> PyResult<EntityRef> {
    if value.is_instance(&value.py().import("cq_acis.model")?.getattr("EntityRef")?)? {
        reference(value)
    } else {
        exact_int(value)?;
        value
            .extract()
            .map(EntityRef)
            .map_err(|_| model_error("entity reference is outside the native index range"))
    }
}
fn optional<T>(
    value: &Bound<'_, PyAny>,
    read: impl FnOnce(&Bound<'_, PyAny>) -> PyResult<T>,
) -> PyResult<Option<T>> {
    if value.is_none() {
        Ok(None)
    } else {
        read(value).map(Some)
    }
}
fn vec3(value: &Bound<'_, PyAny>) -> PyResult<Vec3> {
    Ok(Vec3 {
        x: value.getattr("x")?.extract()?,
        y: value.getattr("y")?.extract()?,
        z: value.getattr("z")?.extract()?,
    })
}
fn range(value: &Bound<'_, PyAny>) -> PyResult<ParameterRange> {
    Ok(ParameterRange {
        lower: value.getattr("lower")?.extract()?,
        upper: value.getattr("upper")?.extract()?,
    })
}
fn source(value: &Bound<'_, PyAny>) -> PyResult<SourceSpan> {
    let source = SourceSpan {
        source_id: value.getattr("source_id")?.extract()?,
        start_offset: index(&value.getattr("start_offset")?)?,
        end_offset: index(&value.getattr("end_offset")?)?,
    };
    source.validate().map_err(model_error)?;
    Ok(source)
}
fn sat_record(value: &Bound<'_, PyAny>) -> PyResult<SatRecord> {
    Ok(SatRecord {
        entity_type: value.getattr("entity_type")?.extract()?,
        text: value.getattr("text")?.extract()?,
        sequence_number: value.getattr("sequence_number")?.extract()?,
        start_offset: index(&value.getattr("start_offset")?)?,
        end_offset: index(&value.getattr("end_offset")?)?,
    })
}
fn acis_value(value: &Bound<'_, PyAny>) -> PyResult<AcisValue> {
    let py = value.py();
    let module = py.import("cq_acis.model")?;
    if value.is_instance(&module.getattr("EntityRef")?)? {
        return reference(value).map(AcisValue::Reference);
    }
    if value.is_instance(&module.getattr("CountedString")?)? {
        return Ok(AcisValue::CountedString(CountedString {
            value: value.getattr("value")?.extract()?,
            declared_length: index(&value.getattr("declared_length")?)?,
        }));
    }
    if value.get_type().is(py.get_type::<PyInt>()) {
        return value.extract().map(AcisValue::Integer);
    }
    if value.is_instance_of::<PyFloat>() {
        return value.extract().map(AcisValue::Float);
    }
    if value.is_instance_of::<PyString>() {
        return value.extract().map(AcisValue::String);
    }
    if value.is_instance_of::<PyBytes>() {
        return value.extract().map(AcisValue::Bytes);
    }
    Err(model_error(
        "value is not an AcisValue; unsupported data must be retained as bytes",
    ))
}
fn raw_entity(value: &Bound<'_, PyAny>) -> PyResult<RawEntity> {
    Ok(RawEntity {
        index: index(&value.getattr("index")?)?,
        type_name: value.getattr("type_name")?.extract()?,
        attributes: reference(&value.getattr("attributes")?)?,
        entity_id: value.getattr("entity_id")?.extract()?,
        values: value
            .getattr("values")?
            .try_iter()?
            .map(|v| acis_value(&v?))
            .collect::<PyResult<_>>()?,
        record: optional(&value.getattr("record")?, sat_record)?,
        source: optional(&value.getattr("source")?, source)?,
        raw_data: optional(&value.getattr("raw_data")?, |v| {
            Ok(v.cast::<PyBytes>()?.as_bytes().to_vec())
        })?,
    })
}
fn metadata(value: &Bound<'_, PyAny>) -> PyResult<AcisMetadata> {
    let container = value.getattr("container")?;
    let container = if container.is_none() {
        None
    } else {
        Some(
            match container.getattr("value")?.extract::<String>()?.as_str() {
                "sat" => AcisContainer::Sat,
                "sab" => AcisContainer::Sab,
                "asm_sab" => AcisContainer::AsmSab,
                _ => return Err(model_error("unrecognized ACIS container")),
            },
        )
    };
    Ok(AcisMetadata {
        container,
        units_mm: value.getattr("units_mm")?.extract()?,
        resabs: value.getattr("resabs")?.extract()?,
        resnor: value.getattr("resnor")?.extract()?,
        save_version: value.getattr("save_version")?.extract()?,
        product_id: value.getattr("product_id")?.extract()?,
        modeler_version: value.getattr("modeler_version")?.extract()?,
        creation_date: value.getattr("creation_date")?.extract()?,
        dialect: value.getattr("dialect")?.extract()?,
    })
}
fn diagnostic(value: &Bound<'_, PyAny>) -> PyResult<AcisDiagnostic> {
    Ok(AcisDiagnostic {
        code: value.getattr("code")?.extract()?,
        message: value.getattr("message")?.extract()?,
        entity_index: optional(&value.getattr("entity_index")?, index)?,
        source: optional(&value.getattr("source")?, source)?,
    })
}
fn read_model(value: &Bound<'_, PyAny>) -> PyResult<AcisModel> {
    let metadata = metadata(&value.getattr("metadata")?)?;
    let entities = value
        .getattr("entities")?
        .try_iter()?
        .map(|v| read_entity(&v?))
        .collect::<PyResult<Vec<_>>>()?;
    let diagnostics = value
        .getattr("diagnostics")?
        .try_iter()?
        .map(|v| diagnostic(&v?))
        .collect::<PyResult<Vec<_>>>()?;
    value
        .py()
        .detach(move || AcisModel::new(metadata, entities, diagnostics))
        .map_err(model_error)
}

fn construct<'py>(
    py: Python<'py>,
    name: &str,
    args: Vec<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    py.import("cq_acis.model")?
        .getattr(name)?
        .call1(PyTuple::new(py, args)?)
}
fn optional_to_py<'py, T>(
    py: Python<'py>,
    value: Option<&T>,
    write: impl FnOnce(Python<'py>, &T) -> PyResult<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    match value {
        Some(value) => write(py, value),
        None => Ok(py.None().into_bound(py)),
    }
}
fn reference_to_py(py: Python<'_>, value: EntityRef) -> PyResult<Bound<'_, PyAny>> {
    construct(py, "EntityRef", vec![value.0.into_bound_py_any(py)?])
}
fn vec3_to_py(py: Python<'_>, value: Vec3) -> PyResult<Bound<'_, PyAny>> {
    py.import("cq_acis.model")?
        .getattr("Vec3")?
        .call1((value.x, value.y, value.z))
}
fn range_to_py<'py>(py: Python<'py>, value: &ParameterRange) -> PyResult<Bound<'py, PyAny>> {
    py.import("cq_acis.model")?
        .getattr("ParameterRange")?
        .call1((value.lower, value.upper))
}
fn source_to_py<'py>(py: Python<'py>, value: &SourceSpan) -> PyResult<Bound<'py, PyAny>> {
    py.import("cq_acis.model")?.getattr("SourceSpan")?.call1((
        &value.source_id,
        value.start_offset,
        value.end_offset,
    ))
}
fn record_to_py<'py>(py: Python<'py>, value: &SatRecord) -> PyResult<Bound<'py, PyAny>> {
    py.import("cq_acis.model")?.getattr("SatRecord")?.call1((
        &value.entity_type,
        &value.text,
        value.sequence_number.clone(),
        value.start_offset,
        value.end_offset,
    ))
}
fn value_to_py<'py>(py: Python<'py>, value: &AcisValue) -> PyResult<Bound<'py, PyAny>> {
    match value {
        AcisValue::Reference(v) => reference_to_py(py, *v),
        AcisValue::CountedString(v) => py
            .import("cq_acis.model")?
            .getattr("CountedString")?
            .call1((&v.value, v.declared_length)),
        AcisValue::Integer(v) => v.clone().into_bound_py_any(py),
        AcisValue::Float(v) => v.into_bound_py_any(py),
        AcisValue::String(v) => v.into_bound_py_any(py),
        AcisValue::Bytes(v) => Ok(PyBytes::new(py, v).into_any()),
    }
}
fn raw_to_py<'py>(py: Python<'py>, raw: &RawEntity) -> PyResult<Bound<'py, PyAny>> {
    let values = raw
        .values
        .iter()
        .map(|v| value_to_py(py, v))
        .collect::<PyResult<Vec<_>>>()?;
    construct(
        py,
        "RawEntity",
        vec![
            raw.index.into_bound_py_any(py)?,
            raw.type_name.clone().into_bound_py_any(py)?,
            reference_to_py(py, raw.attributes)?,
            raw.entity_id.clone().into_bound_py_any(py)?,
            PyTuple::new(py, values)?.into_any(),
            optional_to_py(py, raw.record.as_ref(), record_to_py)?,
            optional_to_py(py, raw.source.as_ref(), source_to_py)?,
            optional_to_py(py, raw.raw_data.as_ref(), |py, v| {
                Ok(PyBytes::new(py, v).into_any())
            })?,
        ],
    )
}
fn metadata_to_py<'py>(py: Python<'py>, value: &AcisMetadata) -> PyResult<Bound<'py, PyAny>> {
    let container = match value.container {
        None => py.None().into_bound(py),
        Some(container) => py
            .import("cq_acis.model")?
            .getattr("AcisContainer")?
            .call1((match container {
                AcisContainer::Sat => "sat",
                AcisContainer::Sab => "sab",
                AcisContainer::AsmSab => "asm_sab",
            },))?,
    };
    construct(
        py,
        "AcisMetadata",
        vec![
            value.units_mm.into_bound_py_any(py)?,
            value.resabs.into_bound_py_any(py)?,
            value.resnor.into_bound_py_any(py)?,
            container,
            value.save_version.clone().into_bound_py_any(py)?,
            value.product_id.clone().into_bound_py_any(py)?,
            value.modeler_version.clone().into_bound_py_any(py)?,
            value.creation_date.clone().into_bound_py_any(py)?,
            value.dialect.clone().into_bound_py_any(py)?,
        ],
    )
}
fn diagnostic_to_py<'py>(py: Python<'py>, value: &AcisDiagnostic) -> PyResult<Bound<'py, PyAny>> {
    construct(
        py,
        "AcisDiagnostic",
        vec![
            value.code.clone().into_bound_py_any(py)?,
            value.message.clone().into_bound_py_any(py)?,
            value.entity_index.into_bound_py_any(py)?,
            optional_to_py(py, value.source.as_ref(), source_to_py)?,
        ],
    )
}

/// Immutable Rust-owned snapshot. Python properties create compatibility dataclasses.
#[pyclass(frozen, module = "cq_acis._native")]
pub struct NativeModel {
    inner: Arc<AcisModel>,
}

/// Reuse the Python compatibility adapter from another Rust extension without
/// exporting a duplicate NativeModel Python type across extension modules.
pub fn model_to_python<'py>(py: Python<'py>, model: AcisModel) -> PyResult<Bound<'py, PyAny>> {
    NativeModel {
        inner: Arc::new(model),
    }
    .to_model(py)
}

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
    })
}

#[pymethods]
impl NativeModel {
    #[staticmethod]
    fn from_model(model: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Self {
            inner: Arc::new(read_model(model)?),
        })
    }
    fn __len__(&self) -> usize {
        self.inner.len()
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
        metadata_to_py(py, self.inner.metadata())
    }
    #[getter]
    fn entities<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(
            py,
            self.inner
                .entities()
                .iter()
                .map(|e| write_entity(py, e))
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
                .map(|d| diagnostic_to_py(py, d))
                .collect::<PyResult<Vec<_>>>()?,
        )
    }
    fn resolve<'py>(&self, reference: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        let py = reference.py();
        optional_to_py(
            py,
            self.inner
                .resolve(reference_argument(reference)?)
                .map_err(model_error)?,
            write_entity,
        )
    }
    fn bodies<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(
            py,
            self.inner
                .bodies()
                .map(|body| write_body_entity(py, body))
                .collect::<PyResult<Vec<_>>>()?,
        )
    }
    fn referenced_by<'py>(&self, reference: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyTuple>> {
        let py = reference.py();
        let indices = self
            .inner
            .referenced_by(reference_argument(reference)?)
            .map_err(model_error)?;
        PyTuple::new(
            py,
            indices
                .into_iter()
                .map(|i| write_entity(py, &self.inner.entities()[i]))
                .collect::<PyResult<Vec<_>>>()?,
        )
    }
    fn to_model<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        construct(
            py,
            "AcisModel",
            vec![
                self.metadata(py)?,
                self.entities(py)?.into_any(),
                self.diagnostics(py)?.into_any(),
            ],
        )
    }
}

#[cfg(feature = "python-module")]
#[pyfunction]
fn validate_model(model: &Bound<'_, PyAny>) -> PyResult<()> {
    read_model(model).map(|_| ())
}
#[cfg(feature = "python-module")]
#[pyfunction]
fn resolve_index(reference: &Bound<'_, PyAny>, entity_count: usize) -> PyResult<Option<usize>> {
    acis_core::resolve_index(reference_argument(reference)?, entity_count).map_err(model_error)
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
    match read_entity(value)? {
        Entity::EllipseCurve(e) => match operation {
            "major_radius" => e.major_radius().into_bound_py_any(py),
            "minor_radius" => e.minor_radius().into_bound_py_any(py),
            "minor_axis" => vec3_to_py(py, e.minor_axis().map_err(geometry_error)?),
            "is_circle" => e
                .is_circle(parameter(0)?)
                .map_err(geometry_error)?
                .into_bound_py_any(py),
            "evaluate" => vec3_to_py(py, e.evaluate(parameter(0)?).map_err(geometry_error)?),
            _ => Err(PyValueError::new_err("unknown ellipse operation")),
        },
        Entity::PlaneSurface(e) if operation == "v_direction" => vec3_to_py(py, e.v_direction()),
        Entity::ConeSurface(e) => match operation {
            "major_direction" => vec3_to_py(py, e.major_direction().map_err(geometry_error)?),
            "minor_direction" => vec3_to_py(py, e.minor_direction().map_err(geometry_error)?),
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
                Some(v) => vec3_to_py(py, v),
                None => Ok(py.None().into_bound(py)),
            },
            "evaluate" => vec3_to_py(
                py,
                e.evaluate(parameter(0)?, parameter(1)?)
                    .map_err(geometry_error)?,
            ),
            _ => Err(PyValueError::new_err("unknown cone operation")),
        },
        Entity::Transform(e) => match operation {
            "linear_determinant" => e.linear_determinant().into_bound_py_any(py),
            "transform_vector" => vec3_to_py(
                py,
                e.transform_vector((parameter(0)?, parameter(1)?, parameter(2)?).into()),
            ),
            "transform_point" => vec3_to_py(
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
    module.add_class::<NativeModel>()?;
    module.add_function(wrap_pyfunction!(validate_model, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_index, module)?)?;
    module.add_function(wrap_pyfunction!(vector, module)?)?;
    module.add_function(wrap_pyfunction!(vector_scalar, module)?)?;
    module.add_function(wrap_pyfunction!(geometry, module)?)?;
    module.add("CORE_VERSION", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
