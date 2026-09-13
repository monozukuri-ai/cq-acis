"""Bounded observed ASM endpoint envelopes, separate from curve tolerances."""

import math

from .extensions import TolerantVertex
from .model import BSplineCurveEntity, EdgeEntity, EllipseCurveEntity, RawEntity, StraightCurveEntity, Vec3


def endpoint_envelope(converter, reference, placement):
    """Qualify a saved envelope against the complete incident source-edge star.

    This is an observed ASM profile, not a general interpretation of TVERTEX
    scalars. The owner must be a checked, explicitly stored intersection fit.
    The two bounds must tightly enclose the measured star endpoint deviation.
    Neither the saved point nor any incident 3D curve is moved or refitted.
    """
    key = (reference.index, placement)
    if key in converter._vertex_envelopes:
        return converter._vertex_envelopes[key]
    if not placement.preserves_circles or not isinstance(converter.model.resolve(reference), RawEntity):
        return None
    vertex = converter._tolerant_view(reference, context="endpoint envelope")
    if not isinstance(vertex, TolerantVertex) or vertex.source_flag != 1 or vertex.saved_scalars[0] != -1:
        return None
    scale = placement.vector(Vec3(1, 0, 0)).magnitude
    inner, outer = (v * scale for v in vertex.saved_scalars[1:])
    resolution = converter.tolerance
    rounding = 128 * math.ulp(max(1., outer))
    if not (resolution < inner <= outer and outer - inner <= resolution + rounding):
        return None
    owner = converter._require(vertex.vertex.edge, EdgeEntity, context="endpoint envelope owner")
    owner_curve = converter._resolve_geometry(owner.curve)
    supported = converter._supported_curves.get(owner.curve.index)
    if (owner.raw.type_name != "edge" or supported is None or supported.kind != "int_int_cur"
            or reference not in (owner.start_vertex, owner.end_vertex)):
        return None
    from ._supported_curves import validate_fit
    if owner_curve.index not in converter._checked_supported_curves:
        converter.supported_curve_checks.append(validate_fit(converter, supported, placement))
        converter._checked_supported_curves.add(owner_curve.index)
    point = placement.point_vector(converter._vertex_location(reference, context="endpoint envelope point"))
    star = []
    for item in converter.model.entities:
        if isinstance(item, RawEntity) and item.type_name == "tedge-edge":
            item = converter._require(item.index, EdgeEntity, context="endpoint envelope incidence")
        if not isinstance(item, EdgeEntity) or reference not in (item.start_vertex, item.end_vertex):
            continue
        if item.start_vertex == item.end_vertex:
            return None
        curve = converter._resolve_geometry(item.curve)
        if not isinstance(curve, (StraightCurveEntity, EllipseCurveEntity, BSplineCurveEntity)):
            return None
        if isinstance(curve, BSplineCurveEntity) and curve.fit_tolerance > (converter.model.metadata.resabs or 1e-6):
            view = converter._supported_curves.get(curve.index)
            if view is None:
                return None
            converter.supported_curve_checks.append(validate_fit(converter, view, placement))
        parameters = (item.start_parameter, item.end_parameter)
        if any(t is None or not math.isfinite(t) for t in parameters) or parameters[0] >= parameters[1]:
            return None
        parameters = [(-1 if item.reversed else 1) * t for t in parameters]
        if curve.parameter_range is not None and any(
                (curve.parameter_range.lower is not None and t < curve.parameter_range.lower)
                or (curve.parameter_range.upper is not None and t > curve.parameter_range.upper)
                for t in parameters):
            return None
        points = [placement.point_vector(curve.origin + curve.direction * t
                  if isinstance(curve, StraightCurveEntity) else curve.evaluate(t)) for t in parameters]
        index = 0 if item.start_vertex == reference else 1
        deviation = (points[index] - point).magnitude
        opposite = item.end_vertex if index == 0 else item.start_vertex
        opposite_point = placement.point_vector(converter._vertex_location(opposite, context="endpoint envelope opposite"))
        # A vertex ball cannot consume an incident edge or the opposite point.
        if (not math.isfinite(deviation) or deviation > inner + rounding
                or min((points[1-index] - point).magnitude, (opposite_point - point).magnitude) <= 2 * outer):
            return None
        star.append(dict(edge=item.index, curve=curve.index, parameter=parameters[index], deviation_mm=deviation))
    if len(star) < 2:
        return None
    maximum = max(item["deviation_mm"] for item in star)
    if maximum <= resolution or inner - maximum > resolution or outer - maximum > resolution + rounding:
        return None
    result = dict(vertex=reference.index, owner_edge=owner.index, source_point_mm=list(placement.point(
        converter._vertex_location(reference, context="endpoint envelope point"))),
        saved_scalars_source_units=vertex.saved_scalars, incident_edges=star,
        profile="ASM 22700 / embedded 22601; flag 1, legacy -1, checked full int_int_cur owner",
        scale_to_mm=scale, model_resolution_mm=resolution,
        max_endpoint_deviation_mm=maximum, tolerance_mm=outer,
        method="observed ASM endpoint envelope; complete incident source star; unchanged saved point and curves")
    converter._vertex_envelopes[key] = result
    converter.tolerant_vertex_envelopes.append(result)
    return result
