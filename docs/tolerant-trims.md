# Tolerant boundaries and finite spline trims

English | [日本語](tolerant-trims.ja.md)

These features are available from 0.3.3 for the observed ASM 22700 / embedded
22601 profile. Rust integrations must use matching core, bridge, and Python
package versions; see the [model API](model-api.md).

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
- A forward, two-knot, degree-1 `exp_par_cur` can supply its saved UV line when
  it references the same explicit spline definition as the supporting surface.
  Embedded support bounds must be unbounded and chart shifts zero. Other pcurve
  profiles use checked projection where supported.

## Pcurve views and diagnostics

`NativeModel.linear_surface_pcurve(pcurve_ref, surface_ref)` returns a
`LinearSurfacePcurve` view, or `None` for another profile. Malformed admitted
profiles and mismatched support definitions raise `AcisModelError`. The view
retains the raw pcurve, interval, two UV points, saved fit tolerance, and
source definition provenance.

Used 2D curves on their supporting surface must agree with the unchanged 3D
edge at the original model tolerance. Neither tolerant scalars nor saved fit
tolerances enlarge that tolerance. Inline coedge curves and inferred local
healing rules remain unsupported.

The converter's `tolerant_boundaries`, `saved_pcurves`, and
`bounded_surface_faces` describe component checks. Readable views or valid
individual faces do not guarantee a complete solid; conversion still fails
when another boundary, surface, or shell is unsupported or invalid. These
features do not establish agreement with Inventor's current Model State.

See [geometry limitations](geometry-support.md), [binary history limitations](sab-support.md),
and [error handling](usage.md#errors-and-diagnostics).
