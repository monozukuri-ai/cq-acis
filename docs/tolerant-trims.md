# Tolerant boundaries and finite spline trims

English | [日本語](tolerant-trims.ja.md)

Version 0.3.3 extends the observed ASM 22700 / embedded 22601 profile.
These additions are not present in 0.3.2. Use the matching 0.3.3 core,
bridge, Python extension and converter together.

## Admitted geometry

- `tedge-edge` and null-inline `tcoedge-coedge` can participate in conversion
  when their line, ellipse or explicit spline already agrees with the saved vertices
  at the model's original `resabs`. Edge/coedge directions, saved parameter
  intervals and reciprocal loop links are checked. Source entities stay raw.
- Forward explicit spline surfaces and their qualified subtype references may
  retain finite U/V bounds. Bounds must define a nonempty subset of the clamped
  knot domain. Reversed charts, periodic splines and unknown trailers remain
  unsupported. NURBS evaluation describes the unchanged supporting surface.
- Face conversion retains the finite support domain and checks the complete
  trim, using analytic bounds or conservative spline control-point bounds.
  An excursion outside that domain rejects the face; it is not clipped away.
  Saved charts and intervals admit at most `1e-10` parameter roundoff (or
  64 ULP for larger UV coordinates), separately from geometric precision.
- A forward, two-knot, degree-1 `exp_par_cur` on an explicitly identified
  instance of the same spline definition can supply its saved UV line. The
  immutable file-local subtype table binds the pcurve and its support.
  Embedded support bounds must be unbounded; chart shifts must be zero.
  Other pcurve profiles continue to use the existing checked projection path.

`NativeModel.linear_surface_pcurve(pcurve_ref, surface_ref)` returns an additive
`LinearSurfacePcurve` view, or `None` for another profile. Malformed admitted
profiles and mismatched support definitions raise `AcisModelError`. The view
retains the complete raw pcurve, interval, two UV points, saved fit tolerance
and definition provenance. Model API 2 and the existing entity layouts remain
unchanged.

The converter compares every used 2D curve on its support with the unchanged
3D edge using OCCT's same-parameter curve-on-surface check. Neither tolerant
scalars nor a pcurve's saved fit tolerance increase the accepted model
tolerance. No inline coedge curve or local healing rule is inferred.
`tolerant_boundaries`, `saved_pcurves` and `bounded_surface_faces` record which
checks passed; they are component diagnostics, not proof of a complete solid.

## Validation and remaining limits

Tests use circle/rational quarter-circle equations, polygon areas and normals,
and a bounded NURBS representation of a known cube. They reject wrong
endpoints, extra turns, invalid bounds, trims that leave the UV box between
their endpoints, wrong support references, truncated records and chart shifts.

In the pinned Inventor FTC07 2021 regression, 195 tolerant coedges construct
valid edges, 10 retain unsupported inline curves, and one fails the original
endpoint tolerance. Eight finite surfaces and 153 linear pcurve views can be
read with source provenance. Individual valid faces increase from 112 to 192
out of 258. The part still fails complete conversion because remaining
curve-on-surface deviations exceed the model tolerance. None of the eight
finite native faces is yet fully converted. This is local component evidence,
not Inventor or current Model State qualification.

The public Inventor corpus remains at 10 valid-solid conversions out of 33
inputs (including five non-IPT documents). The holdouts are not used for fitting.
Reproduction is provided by inventor-kit's `scripts/validate_tolerant_trims.py`.

OCCT references: [curve projection](https://dev.opencascade.org/doc/refman/html/class_geom_proj_lib.html),
[curve-on-surface verification](https://dev.opencascade.org/doc/refman/html/class_geom_lib___check_curve_on_surface.html),
[2D curve bounds](https://dev.opencascade.org/doc/refman/html/class_bnd_lib___add2d_curve.html).
