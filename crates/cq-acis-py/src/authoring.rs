//! Semantic authoring boundary. No raw ACIS records enter the builder.
use super::*;
use acis_core::authoring::brep::*;
use acis_core::encode::{HistoryMode, SabEncoder, SabWriteLimits, SabWriteProfile};
use pyo3::types::PyList;

fn coordinates(item: &Bound<'_, PyAny>) -> PyResult<Vec3> {
    // Fixed-size arrays accept both OCCT adapter tuples and JSON lists,
    // while retaining the coordinate count and numeric type checks.
    let [x, y, z] = item.extract::<[f64; 3]>()?;
    Ok((x, y, z).into())
}
fn vector(item: &Bound<'_, PyAny>, key: &str) -> PyResult<Vec3> {
    coordinates(&item.get_item(key)?)
}
fn bounded<'py>(item: Bound<'py, PyAny>, limit: usize) -> PyResult<Bound<'py, PyList>> {
    let list = item.cast_into::<PyList>()?;
    if list.len() > limit {
        return Err(PyValueError::new_err("analytic input budget exceeded"));
    }
    Ok(list)
}
#[pyclass(frozen, module = "cq_acis._native")]
pub struct AuthoredBrep {
    inner: acis_core::authoring::brep::AuthoredBrep,
}
#[pymethods]
impl AuthoredBrep {
    #[getter]
    fn model(&self) -> NativeModel {
        NativeModel {
            inner: Arc::new(self.inner.model().clone()),
            subtypes: OnceLock::new(),
        }
    }
    #[pyo3(signature=(history=false))]
    fn to_sab<'py>(&self, py: Python<'py>, history: bool) -> PyResult<Bound<'py, PyBytes>> {
        let data = py
            .detach(|| {
                SabEncoder::new(
                    SabWriteProfile::Asm23200AnalyticExperimental,
                    SabWriteLimits {
                        max_bytes: 16 * 1024 * 1024,
                        max_entities: 32768,
                    },
                )
                .encode_brep(
                    &self.inner,
                    if history {
                        HistoryMode::InsertionOnlyStateOne
                    } else {
                        HistoryMode::None
                    },
                )
            })
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(PyBytes::new(py, &data))
    }
}
#[pyfunction]
pub fn author_analytic(spec: &Bound<'_, PyAny>) -> PyResult<AuthoredBrep> {
    let vertices = bounded(spec.get_item("vertices_mm")?, MAX_TOPOLOGY)?;
    let edges = bounded(spec.get_item("edges")?, MAX_TOPOLOGY)?;
    let faces = bounded(spec.get_item("faces")?, MAX_TOPOLOGY)?;
    let mut input = BrepSpec {
        vertices_mm: Vec::new(),
        edges: Vec::new(),
        faces: Vec::new(),
        tolerance_mm: spec.get_item("tolerance_mm")?.extract()?,
    };
    for v in vertices {
        input.vertices_mm.push(coordinates(&v)?);
    }
    for e in edges {
        let c = e.get_item("curve")?;
        let curve = match c.get_item("kind")?.extract::<String>()?.as_str() {
            "line" => CurveSpec::Line {
                origin: vector(&c, "origin")?,
                direction: vector(&c, "direction")?,
            },
            "ellipse" => CurveSpec::Ellipse {
                center: vector(&c, "center")?,
                normal: vector(&c, "normal")?,
                major_axis: vector(&c, "major_axis")?,
                ratio: c.get_item("ratio")?.extract()?,
            },
            _ => return Err(PyValueError::new_err("unsupported analytic curve kind")),
        };
        input.edges.push(EdgeSpec {
            vertices: e.get_item("vertices")?.extract()?,
            parameters: e.get_item("parameters")?.extract()?,
            curve,
        });
    }
    let mut uses = 0usize;
    for f in faces {
        let s = f.get_item("surface")?;
        let surface = match s.get_item("kind")?.extract::<String>()?.as_str() {
            "plane" => SurfaceSpec::Plane {
                origin: vector(&s, "origin")?,
                normal: vector(&s, "normal")?,
                u_direction: vector(&s, "u_direction")?,
            },
            "cylinder" => SurfaceSpec::Cylinder {
                center: vector(&s, "center")?,
                axis: vector(&s, "axis")?,
                x_direction: vector(&s, "x_direction")?,
                radius: s.get_item("radius")?.extract()?,
            },
            _ => return Err(PyValueError::new_err("unsupported analytic surface kind")),
        };
        let mut loops = Vec::new();
        for w in bounded(f.get_item("loops")?, MAX_TOPOLOGY)? {
            let walk = bounded(w, MAX_TOPOLOGY * 2)?;
            uses += walk.len();
            if uses > MAX_TOPOLOGY * 2 {
                return Err(PyValueError::new_err("analytic coedge budget exceeded"));
            }
            let mut row = Vec::new();
            for u in walk {
                let [edge, reversed] = u.extract::<[Bound<'_, PyAny>; 2]>()?;
                row.push(EdgeUse {
                    edge: edge.extract()?,
                    reversed: reversed.extract()?,
                });
            }
            loops.push(row);
        }
        input.faces.push(FaceSpec {
            surface,
            reversed: f.get_item("reversed")?.extract()?,
            loops,
        });
    }
    let inner = spec
        .py()
        .detach(|| input.build())
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(AuthoredBrep { inner })
}
