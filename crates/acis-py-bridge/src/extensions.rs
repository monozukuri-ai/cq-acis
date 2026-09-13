//! Additive partial views; existing model dataclass layouts are unchanged.
use super::*;
use acis_core::{subtypes::*, tolerant::*};

fn extension<'py>(
    py: Python<'py>,
    name: &str,
    args: Vec<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    ensure_python_model_api(py)?;
    py.import("cq_acis.extensions")?
        .getattr(name)?
        .call1(PyTuple::new(py, args)?)
}

pub fn tolerant_to_python<'py>(
    py: Python<'py>,
    view: &TolerantTopology,
) -> PyResult<Bound<'py, PyAny>> {
    let (name, args) = match view {
        TolerantTopology::Vertex(v) => (
            "TolerantVertex",
            vec![
                entity_to_python(py, &Entity::Vertex(v.vertex.clone()))?,
                v.source_flag.into_bound_py_any(py)?,
                PyTuple::new(py, v.saved_scalars)?.into_any(),
            ],
        ),
        TolerantTopology::Edge(v) => (
            "TolerantEdge",
            vec![
                entity_to_python(py, &Entity::Edge(v.edge.clone()))?,
                v.saved_scalar.into_bound_py_any(py)?,
                v.embedded_version.into_bound_py_any(py)?,
            ],
        ),
        TolerantTopology::Coedge(v) => (
            "TolerantCoedge",
            vec![
                entity_to_python(py, &Entity::Coedge(v.coedge.clone()))?,
                PyTuple::new(py, v.parameter_interval)?.into_any(),
                reference_to_py(py, v.attachment)?,
            ],
        ),
    };
    extension(py, name, args)
}

fn definition_to_python<'py>(
    py: Python<'py>,
    d: &SubtypeDefinition,
) -> PyResult<Bound<'py, PyAny>> {
    extension(
        py,
        "SubtypeDefinition",
        vec![
            d.index.into_bound_py_any(py)?,
            d.kind.clone().into_bound_py_any(py)?,
            d.entity_index.into_bound_py_any(py)?,
            d.value_start.into_bound_py_any(py)?,
            d.value_end.into_bound_py_any(py)?,
            d.parent.into_bound_py_any(py)?,
        ],
    )
}

pub fn linear_surface_pcurve_to_python<'py>(
    py: Python<'py>,
    view: &acis_core::pcurve::LinearSurfacePcurve,
) -> PyResult<Bound<'py, PyAny>> {
    extension(
        py,
        "LinearSurfacePcurve",
        vec![
            entity_to_python(py, &Entity::Raw(view.raw.clone()))?,
            PyTuple::new(py, view.parameter_interval)?.into_any(),
            PyTuple::new(py, view.uv_endpoints.iter().map(|p| (p[0], p[1])))?.into_any(),
            view.fit_tolerance.into_bound_py_any(py)?,
            definition_to_python(py, &view.support)?,
        ],
    )
}

pub fn spline_surface_pcurve_to_python<'py>(
    py: Python<'py>,
    view: &acis_core::pcurve::SplineSurfacePcurve,
) -> PyResult<Bound<'py, PyAny>> {
    extension(
        py,
        "SplineSurfacePcurve",
        vec![
            entity_to_python(py, &Entity::Raw(view.raw.clone()))?,
            view.degree.into_bound_py_any(py)?,
            PyTuple::new(py, &view.knots)?.into_any(),
            PyTuple::new(py, &view.multiplicities)?.into_any(),
            PyTuple::new(py, view.poles.iter().map(|p| (p[0], p[1])))?.into_any(),
            view.reversed.into_bound_py_any(py)?,
            PyTuple::new(py, view.parameter_interval)?.into_any(),
            view.fit_tolerance.into_bound_py_any(py)?,
            view.support_reversed.into_bound_py_any(py)?,
            definition_to_python(py, &view.support)?,
        ],
    )
}

pub fn subtype_table_to_python<'py>(
    py: Python<'py>,
    table: &SubtypeTable,
) -> PyResult<Bound<'py, PyAny>> {
    let definitions = table
        .definitions
        .iter()
        .map(|d| definition_to_python(py, d))
        .collect::<PyResult<Vec<_>>>()?;
    let references = table
        .references
        .iter()
        .map(|r| {
            extension(
                py,
                "SubtypeReference",
                vec![
                    r.entity_index.into_bound_py_any(py)?,
                    r.value_start.into_bound_py_any(py)?,
                    r.target.into_bound_py_any(py)?,
                ],
            )
        })
        .collect::<PyResult<Vec<_>>>()?;
    extension(
        py,
        "SubtypeTable",
        vec![
            PyTuple::new(py, definitions)?.into_any(),
            PyTuple::new(py, references)?.into_any(),
            PyTuple::new(py, &table.diagnostics)?.into_any(),
        ],
    )
}

pub fn resolved_subtype_to_python<'py>(
    py: Python<'py>,
    resolved: &ResolvedSubtype,
) -> PyResult<Bound<'py, PyAny>> {
    extension(
        py,
        "ResolvedSubtype",
        vec![
            entity_to_python(py, &resolved.geometry)?,
            definition_to_python(py, &resolved.definition)?,
        ],
    )
}
