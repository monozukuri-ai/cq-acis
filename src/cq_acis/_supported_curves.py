"""Source-associated curve construction and independent OCCT checks.

This module never substitutes a fitted curve for a shared source edge.
"""

from dataclasses import fields
from types import SimpleNamespace
import math

from .model import (
    PlaneSurfaceEntity,
    SphereSurfaceEntity,
    TorusSurfaceEntity,
    BSplineSurfaceEntity,
    Vec3,
)


def array(values, cls):
    result = cls(1, len(values))
    for i, value in enumerate(values, 1):
        result.SetValue(i, value)
    return result


def spline3d(source, placement):
    from OCP.Geom import Geom_BSplineCurve
    from OCP.TColgp import TColgp_Array1OfPnt
    from OCP.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
    from OCP.gp import gp_Pnt

    source.validate()
    return Geom_BSplineCurve(
        array([gp_Pnt(*placement.point(p)) for p in source.poles], TColgp_Array1OfPnt),
        array(source.weights, TColStd_Array1OfReal),
        array(source.knots, TColStd_Array1OfReal),
        array(source.multiplicities, TColStd_Array1OfInteger),
        source.degree,
        False,
    )


def spline2d(source, first, last, reverse=False, scale=(1.0, 1.0), swap=False):
    from OCP.Geom2d import Geom2d_BSplineCurve
    from OCP.TColgp import TColgp_Array1OfPnt2d
    from OCP.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
    from OCP.gp import gp_Pnt2d

    knots = tuple(-k for k in source.knots[::-1]) if reverse else source.knots
    poles = source.poles[::-1] if reverse else source.poles
    if swap:
        poles = tuple((p[1], p[0]) for p in poles)
    weights = source.weights[::-1] if reverse else source.weights
    mults = source.multiplicities[::-1] if reverse else source.multiplicities
    target = [
        first + (k - knots[0]) / (knots[-1] - knots[0]) * (last - first) for k in knots
    ]
    return Geom2d_BSplineCurve(
        array(
            [gp_Pnt2d(p[0] * scale[0], p[1] * scale[1]) for p in poles],
            TColgp_Array1OfPnt2d,
        ),
        array(weights, TColStd_Array1OfReal),
        array(target, TColStd_Array1OfReal),
        array(mults, TColStd_Array1OfInteger),
        source.degree,
        False,
    )


def support_geometry(converter, source, placement):
    from .cadquery import CadQueryConversionError
    from OCP.Geom import Geom_Plane
    from OCP.gp import gp_Ax3, gp_Pnt, gp_Dir

    if not placement.preserves_circles:
        raise CadQueryConversionError(
            "associated support requires a similarity placement",
            code="geometry.tolerant_transform_unsupported",
        )
    uv_scale = (1.0, 1.0)
    if isinstance(source, PlaneSurfaceEntity):
        u = placement.vector(source.u_direction)
        normal = placement.oriented_direction(source.normal)
        if u.magnitude <= 0 or abs(normal.dot(u.normalized())) > 1e-9:
            raise CadQueryConversionError(
                "invalid plane support frame", code="geometry.supported_curve_support"
            )
        surface = Geom_Plane(
            gp_Ax3(
                gp_Pnt(*placement.point(source.origin)),
                gp_Dir(normal.x, normal.y, normal.z),
                gp_Dir(u.x, u.y, u.z),
            )
        )
        uv_scale = (u.magnitude, u.magnitude * (-1 if source.reverse_v else 1))
        radius = 1.0
    elif isinstance(source, (SphereSurfaceEntity, TorusSurfaceEntity)):
        geometry = converter._closed_analytic_geometry(None, source, placement)
        surface, radius = geometry.surface, geometry.radius
    elif isinstance(source, BSplineSurfaceEntity):
        surface = converter._bspline_geometry(source, placement)
        radius = 1.0
    else:
        raise CadQueryConversionError(
            "unsupported associated surface", code="geometry.supported_curve_support"
        )
    return SimpleNamespace(
        surface=surface,
        radius=radius,
        tolerance=converter.tolerance,
        source_surface=source.index,
        source_geometry=source,
        uv_scale=uv_scale,
        uv_swap=isinstance(source, (SphereSurfaceEntity, TorusSurfaceEntity)),
    )


def same_support(saved, face):
    # Raw provenance differs for an embedded definition. Compare the saved chart
    # frame/shape exactly; finite ranges belong to the face and are checked there.
    if type(saved) is not type(face):
        return False
    ignored = {"raw", "pattern", "u_range", "v_range"}
    return all(
        getattr(saved, f.name) == getattr(face, f.name)
        for f in fields(saved)
        if f.name not in ignored
    )


def deviation(curve, pcurve, surface, first, last):
    from .cadquery import CadQueryConversionError
    from OCP.Adaptor3d import Adaptor3d_CurveOnSurface
    from OCP.Geom2dAdaptor import Geom2dAdaptor_Curve
    from OCP.GeomAdaptor import GeomAdaptor_Curve, GeomAdaptor_Surface
    from OCP.GeomLib import GeomLib_CheckCurveOnSurface

    check = GeomLib_CheckCurveOnSurface(GeomAdaptor_Curve(curve, first, last))
    check.Perform(
        Adaptor3d_CurveOnSurface(
            Geom2dAdaptor_Curve(pcurve, first, last), GeomAdaptor_Surface(surface)
        )
    )
    if not check.IsDone() or not math.isfinite(check.MaxDistance()):
        raise CadQueryConversionError(
            "unchecked supported curve", code="geometry.supported_curve_mismatch"
        )
    return check.MaxDistance()


def rational_plane_parameterization(pcurve, curve, geometry, first, last, tolerance):
    """Certify a rational quadratic minor arc before using analytic parameters.

    Bernstein coefficients bound the conic residual and plane distance over
    the entire saved UV curve. Positive angular derivative and a separating
    half-plane exclude backtracking or another turn. No sampled fit is used.
    """
    from OCP.Geom import Geom_Circle, Geom_Ellipse, Geom_Plane
    from OCP.Geom2d import Geom2d_BSplineCurve, Geom2d_Circle, Geom2d_Ellipse
    from OCP.GeomProjLib import GeomProjLib

    if not (
        isinstance(geometry.surface, Geom_Plane)
        and isinstance(curve, (Geom_Circle, Geom_Ellipse))
        and isinstance(pcurve, Geom2d_BSplineCurve)
        and pcurve.Degree() == 2
        and pcurve.NbPoles() == 3
        and pcurve.NbKnots() == 2
        and 0 < last - first < math.pi
    ):
        return pcurve, None
    axes = curve.Position()
    center = axes.Location()
    directions = (axes.XDirection(), axes.YDirection(), axes.Direction())
    radii = (
        (curve.Radius(),) * 2
        if isinstance(curve, Geom_Circle)
        else (curve.MajorRadius(), curve.MinorRadius())
    )
    weights = [pcurve.Weight(i) for i in range(1, 4)]
    if min(weights) <= 0 or not all(math.isfinite(w) for w in weights):
        return pcurve, None
    points = [
        geometry.surface.Value(pcurve.Pole(i).X(), pcurve.Pole(i).Y())
        for i in range(1, 4)
    ]
    coordinates = []
    for point in points:
        offset = (
            point.X() - center.X(),
            point.Y() - center.Y(),
            point.Z() - center.Z(),
        )
        xyz = [
            sum(v * d for v, d in zip(offset, (axis.X(), axis.Y(), axis.Z())))
            for axis in directions
        ]
        coordinates.append((xyz[0] / radii[0], xyz[1] / radii[1], xyz[2]))
    midpoint = (first + last) / 2
    if any(
        x * math.cos(midpoint) + y * math.sin(midpoint) <= 0 for x, y, _ in coordinates
    ):
        return pcurve, None
    numerator = [(x * w, y * w, z * w) for (x, y, z), w in zip(coordinates, weights)]
    residual = [0.0] * 5
    for i in range(3):
        for j in range(3):
            residual[i + j] += (
                math.comb(2, i)
                * math.comb(2, j)
                / math.comb(4, i + j)
                * (
                    numerator[i][0] * numerator[j][0]
                    + numerator[i][1] * numerator[j][1]
                    - weights[i] * weights[j]
                )
            )
    coefficient_scale = max(
        1.0,
        *(abs(x * x) + abs(y * y) + w * w for (x, y, _), w in zip(numerator, weights)),
    )
    q_bound = (max(abs(v) for v in residual) + 64 * math.ulp(coefficient_scale)) / min(
        weights
    ) ** 2
    if not math.isfinite(q_bound) or q_bound >= 1:
        return pcurve, None
    radial_bound = max(radii) * q_bound / (1 + math.sqrt(1 - q_bound))
    plane_bound = max(abs(v[2]) for v in numerator) / min(weights)
    coordinate_scale = max(
        1.0, *(abs(v) for p in (*points, center) for v in (p.X(), p.Y(), p.Z()))
    )
    locus_bound = math.hypot(radial_bound, plane_bound) + 128 * math.ulp(
        coordinate_scale
    )
    angular = [0.0] * 4
    derivative = [
        (2 * (b[0] - a[0]), 2 * (b[1] - a[1])) for a, b in zip(numerator, numerator[1:])
    ]
    for i in range(3):
        for j in range(2):
            angular[i + j] += (
                math.comb(2, i)
                / math.comb(3, i + j)
                * (
                    numerator[i][0] * derivative[j][1]
                    - numerator[i][1] * derivative[j][0]
                )
            )
    endpoint_error = max(
        geometry.surface.Value(pcurve.Value(t).X(), pcurve.Value(t).Y()).Distance(
            curve.Value(t)
        )
        for t in (first, last)
    )
    if locus_bound > tolerance or min(angular) <= 0 or endpoint_error > tolerance:
        return pcurve, None
    projected = GeomProjLib.Curve2d_s(
        curve, first, last, geometry.surface, tolerance * 0.1
    )
    if not isinstance(projected, (Geom2d_Circle, Geom2d_Ellipse)):
        return pcurve, None
    return projected, dict(
        method="rational quadratic conic identity; monotone minor arc; analytic parameters",
        locus_bound_mm=locus_bound,
        endpoint_deviation_mm=endpoint_error,
        tolerance_mm=tolerance,
    )


def inline_pcurve(converter, view, curve, geometry, first, last, reverse):
    pc = spline2d(
        view.pcurve, first, last, reverse, geometry.uv_scale, geometry.uv_swap
    )
    pc, certificate = rational_plane_parameterization(
        pc, curve, geometry, first, last, converter.tolerance
    )
    if certificate is not None:
        converter.inline_reparameterizations.append(
            dict(coedge=view.curve.index, **certificate)
        )
    return pc


def project_supported_curve(curve, geometry, first, last, limit):
    from OCP.GeomProjLib import GeomProjLib
    from .cadquery import CadQueryConversionError

    pc = GeomProjLib.Curve2d_s(
        curve, first, last, geometry.surface, *geometry.surface.Bounds(), limit * 0.25
    )
    if pc is None:
        raise CadQueryConversionError(
            "associated curve projection failed",
            code="geometry.supported_curve_projection",
        )
    return pc


def validate_fit(converter, view, placement):
    from .cadquery import CadQueryConversionError

    curve = spline3d(view.curve, placement)
    first, last = view.curve.knots[0], view.curve.knots[-1]
    geometry = support_geometry(converter, view.support, placement)
    pc = spline2d(
        view.pcurve, first, last, scale=geometry.uv_scale, swap=geometry.uv_swap
    )
    maximum = deviation(curve, pc, geometry.surface, first, last)
    limit = (
        view.curve.fit_tolerance * placement.vector(Vec3(1, 0, 0)).magnitude
        + converter.tolerance
    )
    saved_uv_maximum = maximum
    method = "saved 3D fit versus saved support UV; full same-parameter check"
    if view.kind == "int_int_cur":
        # The full 3D fit is explicitly stored. Establish its distance to each
        # declared support independently; retain the saved UV as a diagnostic,
        # since it need not have the same parameterization as the 3D fit.
        converter._check_uv_trim(
            pc, first, last, geometry.surface.Bounds(), view.curve.index
        )
        pc = project_supported_curve(curve, geometry, first, last, limit)
        maximum = deviation(curve, pc, geometry.surface, first, last)
        converter._check_uv_trim(
            pc, first, last, geometry.surface.Bounds(), view.curve.index
        )
        method = "unchanged saved 3D fit; projected primary support and convex-hull plane checks"
    if not math.isfinite(limit) or maximum > limit:
        raise CadQueryConversionError(
            f"saved 3D fit exceeds associated support bound ({maximum} > {limit} mm)",
            code="geometry.supported_curve_fit_mismatch",
        )
    secondary_maximum = None
    if view.secondary_support is not None:
        plane = view.secondary_support
        if not isinstance(plane, PlaneSurfaceEntity):
            raise CadQueryConversionError(
                "unqualified second support", code="geometry.supported_curve_support"
            )
        normal = placement.vector(plane.normal).normalized()
        origin = placement.point_vector(plane.origin)
        # Positive B-spline weights give a convex-hull bound for signed plane
        # distance over the entire curve, including every knot span.
        secondary_maximum = max(
            abs((placement.point_vector(p) - origin).dot(normal))
            for p in view.curve.poles
        )
        if not math.isfinite(secondary_maximum) or secondary_maximum > limit:
            raise CadQueryConversionError(
                "stored curve exceeds second support bound",
                code="geometry.supported_curve_fit_mismatch",
            )
    return dict(
        entity=view.curve.index,
        kind=view.kind,
        value_start=view.value_start,
        value_end=view.value_end,
        fit_tolerance_source_units=view.curve.fit_tolerance,
        max_deviation_mm=maximum,
        tolerance_mm=limit,
        secondary_support_bound_mm=secondary_maximum,
        saved_uv_same_parameter_deviation_mm=saved_uv_maximum,
        method=method,
    )
