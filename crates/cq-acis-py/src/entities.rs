//! Explicit Python dataclass conversion; no text/JSON intermediate representation.
use super::*;
pub fn read_body_entity(value: &Bound<'_, PyAny>) -> PyResult<BodyEntity> {
    Ok(BodyEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        lump: {
            let field = value.getattr("lump")?;
            reference(&field)?
        },
        wire: {
            let field = value.getattr("wire")?;
            reference(&field)?
        },
        transform: {
            let field = value.getattr("transform")?;
            reference(&field)?
        },
    })
}

pub fn write_body_entity<'py>(py: Python<'py>, entity: &BodyEntity) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        reference_to_py(py, entity.lump)?,
        reference_to_py(py, entity.wire)?,
        reference_to_py(py, entity.transform)?,
    ];
    construct(py, "BodyEntity", args)
}

pub fn read_lump_entity(value: &Bound<'_, PyAny>) -> PyResult<LumpEntity> {
    Ok(LumpEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        next_lump: {
            let field = value.getattr("next_lump")?;
            reference(&field)?
        },
        shell: {
            let field = value.getattr("shell")?;
            reference(&field)?
        },
        body: {
            let field = value.getattr("body")?;
            reference(&field)?
        },
    })
}

pub fn write_lump_entity<'py>(py: Python<'py>, entity: &LumpEntity) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        reference_to_py(py, entity.next_lump)?,
        reference_to_py(py, entity.shell)?,
        reference_to_py(py, entity.body)?,
    ];
    construct(py, "LumpEntity", args)
}

pub fn read_shell_entity(value: &Bound<'_, PyAny>) -> PyResult<ShellEntity> {
    Ok(ShellEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        next_shell: {
            let field = value.getattr("next_shell")?;
            reference(&field)?
        },
        subshell: {
            let field = value.getattr("subshell")?;
            reference(&field)?
        },
        face: {
            let field = value.getattr("face")?;
            reference(&field)?
        },
        wire: {
            let field = value.getattr("wire")?;
            reference(&field)?
        },
        lump: {
            let field = value.getattr("lump")?;
            reference(&field)?
        },
    })
}

pub fn write_shell_entity<'py>(
    py: Python<'py>,
    entity: &ShellEntity,
) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        reference_to_py(py, entity.next_shell)?,
        reference_to_py(py, entity.subshell)?,
        reference_to_py(py, entity.face)?,
        reference_to_py(py, entity.wire)?,
        reference_to_py(py, entity.lump)?,
    ];
    construct(py, "ShellEntity", args)
}

pub fn read_face_entity(value: &Bound<'_, PyAny>) -> PyResult<FaceEntity> {
    Ok(FaceEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        next_face: {
            let field = value.getattr("next_face")?;
            reference(&field)?
        },
        loop_ref: {
            let field = value.getattr("loop")?;
            reference(&field)?
        },
        shell: {
            let field = value.getattr("shell")?;
            reference(&field)?
        },
        subshell: {
            let field = value.getattr("subshell")?;
            reference(&field)?
        },
        surface: {
            let field = value.getattr("surface")?;
            reference(&field)?
        },
        reversed: {
            let field = value.getattr("reversed")?;
            field.extract()?
        },
        double_sided: {
            let field = value.getattr("double_sided")?;
            field.extract()?
        },
        containment_in: {
            let field = value.getattr("containment_in")?;
            field.extract()?
        },
    })
}

pub fn write_face_entity<'py>(py: Python<'py>, entity: &FaceEntity) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        reference_to_py(py, entity.next_face)?,
        reference_to_py(py, entity.loop_ref)?,
        reference_to_py(py, entity.shell)?,
        reference_to_py(py, entity.subshell)?,
        reference_to_py(py, entity.surface)?,
        entity.reversed.into_bound_py_any(py)?,
        entity.double_sided.into_bound_py_any(py)?,
        entity.containment_in.into_bound_py_any(py)?,
    ];
    construct(py, "FaceEntity", args)
}

pub fn read_loop_entity(value: &Bound<'_, PyAny>) -> PyResult<LoopEntity> {
    Ok(LoopEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        next_loop: {
            let field = value.getattr("next_loop")?;
            reference(&field)?
        },
        coedge: {
            let field = value.getattr("coedge")?;
            reference(&field)?
        },
        face: {
            let field = value.getattr("face")?;
            reference(&field)?
        },
    })
}

pub fn write_loop_entity<'py>(py: Python<'py>, entity: &LoopEntity) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        reference_to_py(py, entity.next_loop)?,
        reference_to_py(py, entity.coedge)?,
        reference_to_py(py, entity.face)?,
    ];
    construct(py, "LoopEntity", args)
}

pub fn read_coedge_entity(value: &Bound<'_, PyAny>) -> PyResult<CoedgeEntity> {
    Ok(CoedgeEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        next_coedge: {
            let field = value.getattr("next_coedge")?;
            reference(&field)?
        },
        previous_coedge: {
            let field = value.getattr("previous_coedge")?;
            reference(&field)?
        },
        partner_coedge: {
            let field = value.getattr("partner_coedge")?;
            reference(&field)?
        },
        edge: {
            let field = value.getattr("edge")?;
            reference(&field)?
        },
        reversed: {
            let field = value.getattr("reversed")?;
            field.extract()?
        },
        loop_ref: {
            let field = value.getattr("loop")?;
            reference(&field)?
        },
        pcurve: {
            let field = value.getattr("pcurve")?;
            reference(&field)?
        },
    })
}

pub fn write_coedge_entity<'py>(
    py: Python<'py>,
    entity: &CoedgeEntity,
) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        reference_to_py(py, entity.next_coedge)?,
        reference_to_py(py, entity.previous_coedge)?,
        reference_to_py(py, entity.partner_coedge)?,
        reference_to_py(py, entity.edge)?,
        entity.reversed.into_bound_py_any(py)?,
        reference_to_py(py, entity.loop_ref)?,
        reference_to_py(py, entity.pcurve)?,
    ];
    construct(py, "CoedgeEntity", args)
}

pub fn read_edge_entity(value: &Bound<'_, PyAny>) -> PyResult<EdgeEntity> {
    Ok(EdgeEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        start_vertex: {
            let field = value.getattr("start_vertex")?;
            reference(&field)?
        },
        start_parameter: {
            let field = value.getattr("start_parameter")?;
            field.extract()?
        },
        end_vertex: {
            let field = value.getattr("end_vertex")?;
            reference(&field)?
        },
        end_parameter: {
            let field = value.getattr("end_parameter")?;
            field.extract()?
        },
        coedge: {
            let field = value.getattr("coedge")?;
            reference(&field)?
        },
        curve: {
            let field = value.getattr("curve")?;
            reference(&field)?
        },
        reversed: {
            let field = value.getattr("reversed")?;
            field.extract()?
        },
        convexity: {
            let field = value.getattr("convexity")?;
            field.extract()?
        },
    })
}

pub fn write_edge_entity<'py>(py: Python<'py>, entity: &EdgeEntity) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        reference_to_py(py, entity.start_vertex)?,
        entity.start_parameter.into_bound_py_any(py)?,
        reference_to_py(py, entity.end_vertex)?,
        entity.end_parameter.into_bound_py_any(py)?,
        reference_to_py(py, entity.coedge)?,
        reference_to_py(py, entity.curve)?,
        entity.reversed.into_bound_py_any(py)?,
        entity.convexity.clone().into_bound_py_any(py)?,
    ];
    construct(py, "EdgeEntity", args)
}

pub fn read_vertex_entity(value: &Bound<'_, PyAny>) -> PyResult<VertexEntity> {
    Ok(VertexEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        edge: {
            let field = value.getattr("edge")?;
            reference(&field)?
        },
        point: {
            let field = value.getattr("point")?;
            reference(&field)?
        },
    })
}

pub fn write_vertex_entity<'py>(
    py: Python<'py>,
    entity: &VertexEntity,
) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        reference_to_py(py, entity.edge)?,
        reference_to_py(py, entity.point)?,
    ];
    construct(py, "VertexEntity", args)
}

pub fn read_point_entity(value: &Bound<'_, PyAny>) -> PyResult<PointEntity> {
    Ok(PointEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        location: {
            let field = value.getattr("location")?;
            vec3(&field)?
        },
    })
}

pub fn write_point_entity<'py>(
    py: Python<'py>,
    entity: &PointEntity,
) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        vec3_to_py(py, entity.location)?,
    ];
    construct(py, "PointEntity", args)
}

pub fn read_straight_curve_entity(value: &Bound<'_, PyAny>) -> PyResult<StraightCurveEntity> {
    Ok(StraightCurveEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        origin: {
            let field = value.getattr("origin")?;
            vec3(&field)?
        },
        direction: {
            let field = value.getattr("direction")?;
            vec3(&field)?
        },
        parameter_range: {
            let field = value.getattr("parameter_range")?;
            optional(&field, range)?
        },
    })
}

pub fn write_straight_curve_entity<'py>(
    py: Python<'py>,
    entity: &StraightCurveEntity,
) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        vec3_to_py(py, entity.origin)?,
        vec3_to_py(py, entity.direction)?,
        optional_to_py(py, entity.parameter_range.as_ref(), range_to_py)?,
    ];
    construct(py, "StraightCurveEntity", args)
}

pub fn read_ellipse_curve_entity(value: &Bound<'_, PyAny>) -> PyResult<EllipseCurveEntity> {
    Ok(EllipseCurveEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        center: {
            let field = value.getattr("center")?;
            vec3(&field)?
        },
        normal: {
            let field = value.getattr("normal")?;
            vec3(&field)?
        },
        major_axis: {
            let field = value.getattr("major_axis")?;
            vec3(&field)?
        },
        ratio: {
            let field = value.getattr("ratio")?;
            field.extract()?
        },
        parameter_range: {
            let field = value.getattr("parameter_range")?;
            optional(&field, range)?
        },
    })
}

pub fn write_ellipse_curve_entity<'py>(
    py: Python<'py>,
    entity: &EllipseCurveEntity,
) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        vec3_to_py(py, entity.center)?,
        vec3_to_py(py, entity.normal)?,
        vec3_to_py(py, entity.major_axis)?,
        entity.ratio.into_bound_py_any(py)?,
        optional_to_py(py, entity.parameter_range.as_ref(), range_to_py)?,
    ];
    construct(py, "EllipseCurveEntity", args)
}

pub fn read_plane_surface_entity(value: &Bound<'_, PyAny>) -> PyResult<PlaneSurfaceEntity> {
    Ok(PlaneSurfaceEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        origin: {
            let field = value.getattr("origin")?;
            vec3(&field)?
        },
        normal: {
            let field = value.getattr("normal")?;
            vec3(&field)?
        },
        u_direction: {
            let field = value.getattr("u_direction")?;
            vec3(&field)?
        },
        reverse_v: {
            let field = value.getattr("reverse_v")?;
            field.extract()?
        },
        u_range: {
            let field = value.getattr("u_range")?;
            optional(&field, range)?
        },
        v_range: {
            let field = value.getattr("v_range")?;
            optional(&field, range)?
        },
    })
}

pub fn write_plane_surface_entity<'py>(
    py: Python<'py>,
    entity: &PlaneSurfaceEntity,
) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        vec3_to_py(py, entity.origin)?,
        vec3_to_py(py, entity.normal)?,
        vec3_to_py(py, entity.u_direction)?,
        entity.reverse_v.into_bound_py_any(py)?,
        optional_to_py(py, entity.u_range.as_ref(), range_to_py)?,
        optional_to_py(py, entity.v_range.as_ref(), range_to_py)?,
    ];
    construct(py, "PlaneSurfaceEntity", args)
}

pub fn read_cone_surface_entity(value: &Bound<'_, PyAny>) -> PyResult<ConeSurfaceEntity> {
    Ok(ConeSurfaceEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        pattern: {
            let field = value.getattr("pattern")?;
            reference(&field)?
        },
        center: {
            let field = value.getattr("center")?;
            vec3(&field)?
        },
        axis: {
            let field = value.getattr("axis")?;
            vec3(&field)?
        },
        major_axis: {
            let field = value.getattr("major_axis")?;
            vec3(&field)?
        },
        ratio: {
            let field = value.getattr("ratio")?;
            field.extract()?
        },
        profile_range: {
            let field = value.getattr("profile_range")?;
            optional(&field, range)?
        },
        sin_half_angle: {
            let field = value.getattr("sin_half_angle")?;
            field.extract()?
        },
        cos_half_angle: {
            let field = value.getattr("cos_half_angle")?;
            field.extract()?
        },
        reference_radius: {
            let field = value.getattr("reference_radius")?;
            field.extract()?
        },
        reversed: {
            let field = value.getattr("reversed")?;
            field.extract()?
        },
        u_range: {
            let field = value.getattr("u_range")?;
            optional(&field, range)?
        },
        v_range: {
            let field = value.getattr("v_range")?;
            optional(&field, range)?
        },
    })
}

pub fn write_cone_surface_entity<'py>(
    py: Python<'py>,
    entity: &ConeSurfaceEntity,
) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        reference_to_py(py, entity.pattern)?,
        vec3_to_py(py, entity.center)?,
        vec3_to_py(py, entity.axis)?,
        vec3_to_py(py, entity.major_axis)?,
        entity.ratio.into_bound_py_any(py)?,
        optional_to_py(py, entity.profile_range.as_ref(), range_to_py)?,
        entity.sin_half_angle.into_bound_py_any(py)?,
        entity.cos_half_angle.into_bound_py_any(py)?,
        entity.reference_radius.into_bound_py_any(py)?,
        entity.reversed.into_bound_py_any(py)?,
        optional_to_py(py, entity.u_range.as_ref(), range_to_py)?,
        optional_to_py(py, entity.v_range.as_ref(), range_to_py)?,
    ];
    construct(py, "ConeSurfaceEntity", args)
}

pub fn read_transform_entity(value: &Bound<'_, PyAny>) -> PyResult<TransformEntity> {
    Ok(TransformEntity {
        raw: raw_entity(&value.getattr("raw")?)?,
        matrix_values: {
            let field = value.getattr("matrix_values")?;
            field.extract()?
        },
        scale: {
            let field = value.getattr("scale")?;
            field.extract()?
        },
        rotated: {
            let field = value.getattr("rotated")?;
            field.extract()?
        },
        reflected: {
            let field = value.getattr("reflected")?;
            field.extract()?
        },
        sheared: {
            let field = value.getattr("sheared")?;
            field.extract()?
        },
    })
}

pub fn write_transform_entity<'py>(
    py: Python<'py>,
    entity: &TransformEntity,
) -> PyResult<Bound<'py, PyAny>> {
    let args = vec![
        raw_to_py(py, &entity.raw)?,
        PyTuple::new(py, entity.matrix_values)?.into_any(),
        entity.scale.into_bound_py_any(py)?,
        entity.rotated.into_bound_py_any(py)?,
        entity.reflected.into_bound_py_any(py)?,
        entity.sheared.into_bound_py_any(py)?,
    ];
    construct(py, "TransformEntity", args)
}

pub fn read_entity(value: &Bound<'_, PyAny>) -> PyResult<Entity> {
    let py = value.py();
    let module = py.import("cq_acis.model")?;
    if value.get_type().is(&module.getattr("RawEntity")?) {
        return Ok(Entity::Raw(raw_entity(value)?));
    }
    if value.get_type().is(&module.getattr("BodyEntity")?) {
        return Ok(Entity::Body(read_body_entity(value)?));
    }
    if value.get_type().is(&module.getattr("LumpEntity")?) {
        return Ok(Entity::Lump(read_lump_entity(value)?));
    }
    if value.get_type().is(&module.getattr("ShellEntity")?) {
        return Ok(Entity::Shell(read_shell_entity(value)?));
    }
    if value.get_type().is(&module.getattr("FaceEntity")?) {
        return Ok(Entity::Face(read_face_entity(value)?));
    }
    if value.get_type().is(&module.getattr("LoopEntity")?) {
        return Ok(Entity::Loop(read_loop_entity(value)?));
    }
    if value.get_type().is(&module.getattr("CoedgeEntity")?) {
        return Ok(Entity::Coedge(read_coedge_entity(value)?));
    }
    if value.get_type().is(&module.getattr("EdgeEntity")?) {
        return Ok(Entity::Edge(read_edge_entity(value)?));
    }
    if value.get_type().is(&module.getattr("VertexEntity")?) {
        return Ok(Entity::Vertex(read_vertex_entity(value)?));
    }
    if value.get_type().is(&module.getattr("PointEntity")?) {
        return Ok(Entity::Point(read_point_entity(value)?));
    }
    if value.get_type().is(&module.getattr("StraightCurveEntity")?) {
        return Ok(Entity::StraightCurve(read_straight_curve_entity(value)?));
    }
    if value.get_type().is(&module.getattr("EllipseCurveEntity")?) {
        return Ok(Entity::EllipseCurve(read_ellipse_curve_entity(value)?));
    }
    if value.get_type().is(&module.getattr("PlaneSurfaceEntity")?) {
        return Ok(Entity::PlaneSurface(read_plane_surface_entity(value)?));
    }
    if value.get_type().is(&module.getattr("ConeSurfaceEntity")?) {
        return Ok(Entity::ConeSurface(read_cone_surface_entity(value)?));
    }
    if value.get_type().is(&module.getattr("TransformEntity")?) {
        return Ok(Entity::Transform(read_transform_entity(value)?));
    }
    Err(model_error(
        "unsupported Python entity class; retain unknown entities as RawEntity",
    ))
}

pub fn write_entity<'py>(py: Python<'py>, entity: &Entity) -> PyResult<Bound<'py, PyAny>> {
    match entity {
        Entity::Raw(raw) => raw_to_py(py, raw),
        Entity::Body(entity) => write_body_entity(py, entity),
        Entity::Lump(entity) => write_lump_entity(py, entity),
        Entity::Shell(entity) => write_shell_entity(py, entity),
        Entity::Face(entity) => write_face_entity(py, entity),
        Entity::Loop(entity) => write_loop_entity(py, entity),
        Entity::Coedge(entity) => write_coedge_entity(py, entity),
        Entity::Edge(entity) => write_edge_entity(py, entity),
        Entity::Vertex(entity) => write_vertex_entity(py, entity),
        Entity::Point(entity) => write_point_entity(py, entity),
        Entity::StraightCurve(entity) => write_straight_curve_entity(py, entity),
        Entity::EllipseCurve(entity) => write_ellipse_curve_entity(py, entity),
        Entity::PlaneSurface(entity) => write_plane_surface_entity(py, entity),
        Entity::ConeSurface(entity) => write_cone_surface_entity(py, entity),
        Entity::Transform(entity) => write_transform_entity(py, entity),
    }
}
