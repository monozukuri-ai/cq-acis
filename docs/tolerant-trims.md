# Tolerant boundaries and finite spline trims

English | [日本語](tolerant-trims.ja.md)

Version 0.3.3 introduced bounded tolerant boundaries, finite UV domains and
forward linear pcurve views for ASM 22700 / embedded 22601. The additional
spline pcurve view and local edge-bound conversion shipped in **0.3.4**.
The inline and associated curve additions below are **unreleased** and require
matching core, bridge and Python sources. Model API 2 and the existing views
remain unchanged. See the [model API](model-api.md).

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
extension scalars never supply additional allowance. Underreported bounds and unsupported charts remain errors.


## Unreleased inline and associated curves

`TolerantCoedge.inline_curve` exposes the observed full `par_int_cur` envelope
on a plane, sphere or torus. It retains the original raw coedge, value extent,
cubic 3D fit, support frame, degree-3 non-rational or degree-2 rational UV,
knots, weights and trailer values. Unknown versions, supports, curve senses,
closure flags, interval mismatches and unconsumed fields reject the view.
Plane UV scale and the saved sphere/torus angle order are explicit.

Conversion checks the inline 3D fit against its saved support/UV within its
own fit tolerance plus original resolution. Independently, the **unchanged
shared source edge** must agree with the support UV within its TEDGE bound.
The inline fit tolerance never increases that shared-edge allowance. For a
single rational quadratic minor arc on a plane, Bernstein coefficient bounds
can certify the same conic, positive angular direction, half-plane containment
and matching endpoints. Only then may an analytic pcurve supply the shared
edge's parameterization. Raw UV poles remain saved; the certificate and derived
parameterization are recorded in `inline_reparameterizations`.

A checked inline edge or its reciprocal use can establish the local bound for
source tolerant endpoints. OCCT vertices then retain the original source point
coordinates. A UV join additionally needs the exact same source tolerant
vertex ID and bounded support-point distances; nearby unrelated vertices are
not merged by this rule. Ordinary lines with tolerant endpoints may narrow
their interval to saved points only when those points lie on the unchanged
line at model resolution and inside both original edge and curve intervals.
This does not reinterpret TEDGE/TCOEDGE intervals. Planar hole orientation uses
only OCCT `FixOrientation`, with all underlying edge identities retained.

`NativeModel.supported_curve(reference)` adds a `SupportedCurve` view for the
observed full `int_int_cur`: a cubic 3D fit associated with a file-local exact
spline subtype and a plane. The original curve, UV and support definition
provenance are retained. The converter projects the saved 3D fit onto its
primary support, checks the full curve at the declared fit bound, and checks
the secondary plane using the positive-weight convex hull. Saved UV stays a
parameter hint with its original same-parameter discrepancy reported; it is
not substituted for the 3D curve. Both saved and derived UV must stay inside
the support domain. Face attachment is limited to those same supports and
keeps finite face bounds. This verifies each support distance, not an exact
intersection or vendor equivalence. Source spline endpoints still require
original model precision; unknown TVERTEX scalars supply no allowance.

`supported_curve_checks`, `inline_pcurves`, `associated_pcurves`,
`tolerant_line_trims`, `tolerant_pcurve_joins`, `plane_wire_orientations` and
`spline_endpoint_failures` separate these checks and transformations. On the
pinned Inventor FTC07 2021 regression, all 10 inline views and all 206 tolerant
coedge boundaries pass. Valid individual faces increase from 245 to 254 of
258; finite-UV faces remain 5 of 8. Two saved pcurves still exceed their TEDGE
bounds. Two further faces share a spline endpoint that differs from its saved
vertex by 0.00652608345231 mm versus 0.00001 mm original resolution. Those faces
remain rejected; complete FTC07 conversion is still unavailable.

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
