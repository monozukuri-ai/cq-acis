//! Shared dataclass conversion for the cq-acis Python model API.
//! This rlib exports no Python module or pyclass; acis-core stays Python-free.
use acis_core::{
    entities::*, AcisContainer, AcisDiagnostic, AcisMetadata, AcisModel, AcisValue, CountedString,
    EntityRef, RawEntity, SatRecord, SourceSpan, Vec3,
};
use pyo3::{
    prelude::*,
    types::{PyBytes, PyFloat, PyInt, PyString, PyTuple},
    IntoPyObjectExt,
};
mod entities;
mod extensions;
use entities::*;
pub use entities::{read_entity as entity_from_python, write_entity as entity_to_python};
pub use extensions::{
    linear_surface_pcurve_to_python, resolved_subtype_to_python, subtype_table_to_python,
    tolerant_to_python,
};

/// Version of the Python dataclass layout, independent of crate/package versions.
pub const MODEL_API_VERSION: u32 = 2;
pyo3::import_exception!(cq_acis.model, AcisModelError);
fn model_error(message: impl ToString) -> PyErr {
    AcisModelError::new_err(message.to_string())
}

/// Reject incompatible Python models before constructing any compatibility objects.
pub fn ensure_python_model_api(py: Python<'_>) -> PyResult<()> {
    let version = py
        .import("cq_acis.model")
        .and_then(|m| m.getattr("MODEL_API_VERSION"))
        .and_then(|v| v.extract::<u32>());
    if version.ok() != Some(MODEL_API_VERSION) {
        return Err(pyo3::exceptions::PyImportError::new_err(
            "acis-py-bridge requires cq-acis Python model API 2 (cq-acis >=0.3.0,<0.4); install a compatible native wheel"));
    }
    Ok(())
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
pub fn reference_from_python(value: &Bound<'_, PyAny>) -> PyResult<EntityRef> {
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
pub fn model_from_python(value: &Bound<'_, PyAny>) -> PyResult<AcisModel> {
    ensure_python_model_api(value.py())?;
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
pub fn vector_to_python(py: Python<'_>, value: Vec3) -> PyResult<Bound<'_, PyAny>> {
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
pub fn metadata_to_python<'py>(
    py: Python<'py>,
    value: &AcisMetadata,
) -> PyResult<Bound<'py, PyAny>> {
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
pub fn diagnostic_to_python<'py>(
    py: Python<'py>,
    value: &AcisDiagnostic,
) -> PyResult<Bound<'py, PyAny>> {
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

/// Convert a validated owned Rust model without SAT/JSON intermediates.
pub fn model_to_python<'py>(py: Python<'py>, model: AcisModel) -> PyResult<Bound<'py, PyAny>> {
    model_ref_to_python(py, &model)
}

/// Borrow a validated model without cloning its stored records.
pub fn model_ref_to_python<'py>(py: Python<'py>, model: &AcisModel) -> PyResult<Bound<'py, PyAny>> {
    ensure_python_model_api(py)?;
    let entities = PyTuple::new(
        py,
        model
            .entities()
            .iter()
            .map(|e| write_entity(py, e))
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    let diagnostics = PyTuple::new(
        py,
        model
            .diagnostics()
            .iter()
            .map(|d| diagnostic_to_python(py, d))
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    construct(
        py,
        "AcisModel",
        vec![
            metadata_to_python(py, model.metadata())?,
            entities.into_any(),
            diagnostics.into_any(),
        ],
    )
}
