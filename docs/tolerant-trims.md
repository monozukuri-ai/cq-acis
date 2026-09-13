# Tolerant boundaries and finite spline trims

English | [日本語](tolerant-trims.ja.md)

Version 0.3.3 introduced bounded tolerant boundaries, finite UV domains and
forward linear pcurve views for ASM 22700 / embedded 22601. The additional
spline pcurve view and local edge-bound conversion shipped in **0.3.4**.
The 0.3.5 sources include the inline and associated curve additions below.
The trim reconciliation additions described separately are **unreleased**. Model API 2 and the existing views
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
finite UV bounds do not change. Saved pcurve fit tolerances and vertex extension scalars never increase this
TEDGE allowance. The separate associated-fit and endpoint profiles below have
their own checks. Underreported bounds and unsupported charts remain errors.


## Inline and associated curves (0.3.5 sources)

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
intersection or vendor equivalence. Source spline endpoints require original model precision unless the bounded
endpoint profile below independently qualifies their complete incident star.

## Unreleased trim reconciliation

A saved UV spline with a different clock can be split by exact knot insertion
into rational Bezier spans. A strictly increasing, piecewise affine parameter
map assigns those unchanged spans to the shared 3D edge. Closest-point
projection chooses the knot times; OCCT checks the full 3D deviation on every
span and over the whole result. The complete original UV locus, traversal,
endpoints and finite chart bounds are retained. No fitted replacement UV or
clipped projection is used. Backtracking, unresolved error and unknown curve
profiles reject conversion. `saved_pcurve_reparameterizations` records both
knot clocks, original discrepancy and accepted per-span maximum.

TEDGE uses keep their original TEDGE bound. For a saved UV fit associated with
a qualified explicit `int_int_cur`, its own saved fit tolerance plus original
resolution bounds the UV/3D comparison. The unchanged 3D fit must independently
pass its own tighter fit bound against both declared supports. Neither fit
budget is increased by a vertex tolerance. `associated_pcurves` records which
representation supplied the bound; unknown supports remain unsupported.

The observed ASM 22700 / 22601 endpoint profile requires flag 1, legacy scalar
-1, and an ordinary owner edge with a checked full `int_int_cur`. The remaining
two scalars must tightly bound the maximum measured endpoint distance over
**all incident source edges**, differ by at most original resolution, and not
consume an incident edge or its opposite point. The outer saved bound applies
only to the OCCT vertex, whose position stays at the saved source point. No 3D
poles, global precision or edge/UV allowance changes. Underreported or loose
scalars, unknown incident curves, and ambiguous joins remain errors. This is a
bounded observed profile, not a vendor-qualified interpretation of all
TVERTEX fields. `tolerant_vertex_envelopes` records the source scalars, point,
owner, full incident star, scale, measured distances and effective bound.

The pinned Inventor FTC07 2021 regression now has 258/258 valid individual
faces, 8/8 finite-UV faces, and a valid closed single solid containing all 258
faces. The previously failing faces are 332, 1164, 2336 and 4351. All 206
tolerant coedge boundaries still pass. This is local source-consistency and
OCCT validity evidence; Inventor/current Model State and vendor equivalence
remain unverified.

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
