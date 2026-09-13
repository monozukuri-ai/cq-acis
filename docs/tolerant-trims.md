# Tolerant boundaries and finite spline trims

English | [日本語](tolerant-trims.ja.md)

Version 0.3.3 introduced bounded tolerant boundaries, finite UV domains and
forward linear pcurve views for ASM 22700 / embedded 22601. The additional
spline pcurve view and local edge-bound conversion below are **unreleased**.
Use matching core, bridge and Python sources for these additions; model API 2
and the existing linear view remain unchanged. See the [model API](model-api.md).

## Supported boundaries and domains

- `tedge-edge` and `tcoedge-coedge` with no inline curve can participate in
  conversion when their line, ellipse, or explicit spline agrees with the saved
  vertices within the original model's `resabs`. Saved directions, parameter
  intervals, and reciprocal loop links must also agree. Source entities stay raw.
- Forward explicit spline surfaces and qualified subtype references can retain
  finite U/V bounds. Bounds must define a nonempty subset of the clamped knot
  domain. Reversed charts, periodic splines, and unknown trailing fields are
  unsupported. Evaluation describes the unchanged supporting surface.
- The complete face trim must remain inside the finite support domain.
  Out-of-domain trims reject the face; they are not clipped. Saved charts and
  intervals allow at most `1e-10` parameter roundoff (or 64 ULP for larger UV
  coordinates), separately from geometric precision.
- An open, non-rational, degree-1 or degree-3 `exp_par_cur` can supply its saved
  UV spline when it references the same explicit spline definition as the face.
  Curve sense `C(-t)` and the supporting surface's normal sense are retained
  independently. Reversing the normal does not reflect the UV chart. Clamped
  knots are remapped affinely to the 3D edge interval without changing UV poles
  or the curve locus. Embedded support bounds must be unbounded and chart
  shifts zero. Other pcurve profiles use checked projection where supported.

## Pcurve views and diagnostics

`NativeModel.linear_surface_pcurve(pcurve_ref, surface_ref)` returns a
`LinearSurfacePcurve` view, or `None` for another profile. Malformed admitted
profiles and mismatched support definitions raise `AcisModelError`. The view
retains the raw pcurve, interval, two UV points, saved fit tolerance, and
source definition provenance.

`NativeModel.spline_surface_pcurve(pcurve_ref, surface_ref)` adds a
`SplineSurfacePcurve` view with degree, saved-direction knots/poles, clamped
multiplicities, curve/support senses, effective parameter interval, fit
tolerance and the same raw/support provenance. It has the same `None`/error
contract as the linear view; unsupported rational/periodic UV splines and
unknown chart transforms are not decoded.

## Local edge bound

Projected trims and ordinary edges must agree with the unchanged 3D curve
within the original model resolution. A checked, same-support saved UV spline
on a qualified null-inline `tcoedge-coedge` / `tedge-edge` may instead use
`tedge.saved_scalar * placement_scale_to_mm + original_model_resolution_mm`.
This is an **observed interpretation** of the ASM 22700 / embedded 22601 TEDGE
field, not a vendor-qualified layout or a general tolerant-healing rule.

The independently measured same-parameter maximum must be finite and within
that bound. Only similarity placements qualify for the local allowance. The
converter records the source scalar, placement scale, resolution, effective
bound and measured deviation in `source_edge_tolerances`. It sets OCCT edge
and incident vertex tolerances to that bound; their coordinates and all 3D/UV
poles stay unchanged. `converter.tolerance`, strict source endpoint checks and
finite UV bounds do not change. Saved pcurve fit tolerances and unknown vertex
extension scalars never supply additional allowance. Underreported bounds,
inline coedge curves and unsupported charts remain errors.

`pcurve_checks` contains every accepted curve-on-surface check and its applicable
bound. `pcurve_max_deviation` is the maximum of these checks and can exceed the
model resolution when a recorded source edge bound applies. `saved_pcurves`,
`tolerant_boundaries` and `bounded_surface_faces` retain their component scope.
Readable views or valid individual faces do not guarantee a complete solid;
unsupported boundaries, invalid faces and open shells still fail conversion.
These features do not establish agreement with Inventor's current Model State.

OCCT's [curve-on-surface checker](https://dev.opencascade.org/doc/refman/html/class_geom_lib___check_curve_on_surface.html)
is used to measure the deviation. Spatial's [description of tolerant modeling](https://blog.spatial.com/3d-software-development-kits/subtleties-b-rep-translation-part-3-why-healing-matters)
explains why coincident topology can have differing geometric loci; it does
not specify the ASM field layout interpreted here.

See [geometry limitations](geometry-support.md), [binary history limitations](sab-support.md),
and [error handling](usage.md#errors-and-diagnostics).
