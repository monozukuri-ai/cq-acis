# Geometry support and limitations

Parsing and conversion have different scopes. A record can be retained or
decoded without being convertible to a CadQuery shape. Unsupported referenced
geometry raises `CadQueryConversionError`; it is not silently replaced with a
sampled surface or returned as a partially successful solid. The one derived
representation is the B-spline fit that ASM itself saved beside a procedural
curve or surface; see [stored approximations](#stored-b-spline-approximations).

## Supported geometry

| Geometry | Conversion scope |
| --- | --- |
| Lines, circles, ellipses, and planes | Supported analytic boundaries and planar faces |
| Cylinders | Circular and elliptical cylinders |
| Circular cones | Supported trims, including a complete circular rim with a verifiable apex |
| Elliptical cones | Two complete coaxial elliptic sections on the positive nappe, with aligned axes and the same minor/major ratio in `(0, 1)` |
| Spheres | Closed loopless spheres, qualified periodic bands, and complete circular boundaries; intersecting holes and non-circular cuts are unsupported |
| Tori | Regular ring tori, including closed loopless faces and qualified periodic bands; horn and spindle tori are unsupported |
| Explicit NURBS | Experimental clamped, nonperiodic curves and surfaces in the profiles below |
| Procedural ASM curves and surfaces | The saved B-spline fit, as derived geometry within its saved fit tolerance |
| Tolerant topology and finite UV trims | Selected ASM profiles described in [tolerant trims](tolerant-trims.md) |

Placements must be similarity transforms; general nonuniform scale and shear
are unsupported. Loopless sphere/torus faces with finite saved ranges are
rejected. General null-curve edges and multi-edge null loops are unsupported.

## Qualified cylinder seams and shell closure (unreleased)

A circular cylinder with two oppositely winding boundaries may need an explicit
OCCT chart seam. The additional profile accepts ordinary circular/linear edges
with generated linear UV curves and no finite saved chart bounds. It verifies
the unchanged cylinder, every source 3D curve, oriented trim coverage (including
periodic splits), retained source vertices, both seam uses, and curve-on-surface
deviation at the original model precision. It does not apply general face healing
or reinterpret saved/tolerant pcurves. A kernel repair that reverses source
traversal, including the currently unqualified mirrored case, is rejected.
`periodic_seam_faces` records the source face, loops, edges and validation bounds.

Sewn shells are checked for actual edge incidence, closure and orientation before
the OCCT `Closed` flag is set. An unset flag alone no longer rejects a closed
shell; a genuinely open shell is rejected even if its flag is already true.
`shell_closure_checks` records the original flag and the checked component.
Open auxiliary bodies are not omitted or promoted to solids. A valid primary
body therefore does not by itself make complete-file conversion successful.

## Oblique cylinder sections and paired generator loops (unreleased)

Two disjoint, complete elliptic plane sections of a circular cylinder can bound
an oblique band. Projected ellipse axes must form the original radius circle;
the difference between the two sinusoidal height functions must be strictly
positive over the full period. Every source trim interval, curve, vertex and
orientation is checked after adding the chart seam. Generated UV curves are
checked at the source model precision. If the kernel reverses every physical
boundary together, the complete face sense is restored before verification;
individual reversals or changed curves are rejected.

A second profile accepts two complete coaxial circular rims and ordinary paired
straight-edge loops on one interior cylinder generator. The source edges become
segments of the chart seam, with two opposite uses each. Connecting seam segments
are added between them, and the circular rims are subdivided at their saved
vertices. This keeps all source 3D lines, intervals and vertices in the face and
through STEP roundtrips. The generated chart may rotate, but the physical
cylinder remains unchanged. `cylinder_slit_faces` records the original loop,
edge and coedge mapping, seam segments and measured errors.

Overlapping or touching trims, inconsistent rim senses, different generators,
mismatching saved endpoints/parameter clocks, finite saved charts, saved pcurves
and mirrored paired-loop placements are not admitted by this profile. No source
loop is dropped or converted into a STEP-invisible internal edge. These checks
qualify individual faces; other unsupported curves and surfaces can still stop
complete-part conversion.

## Explicit NURBS profiles

- **SAT 700:** direct `exactsur` surfaces with `nubs` or `nurbs`, open clamped
  U/V directions, and no extra fields. Other SAT spline profiles stay raw.
- **ASM (every accepted save version):** forward explicit `exact_int_cur`
  curves and `exact_spl_sur` surfaces, including qualified subtype references.
  The profile was observed on ASM 22700 records with embedded subtype version
  22601; since 0.4.0 it is admitted for every accepted save version, provided
  the embedded version does not exceed the container's save version
  (22000, 22220, 22502 and 22601 have been observed). The admitted profile
  requires open clamped splines, no singularities, zero fit tolerance, and the
  supported default record fields; a record that does not match stays raw.
  Curves require saved edge parameters and null support surfaces/pcurves.
  Surface bounds may be unbounded or a supported [finite UV domain](tolerant-trims.md).

Spline weights must be positive. The supported degree range is 1–16, with at
most 4,096 knot entries per direction, 65,536 expanded knots per direction, and
one million surface poles. Reversed or periodic exact spline profiles remain
unsupported. Sweeps, blends and other procedural geometry are never evaluated;
they convert only through their stored fit, described next.

## Stored B-spline approximations

ASM saves a fitted `bs3` curve or surface, with its fit tolerance, beside the
procedural definition of intersection curves (`int_int_cur`, `blend_int_cur`,
`par_int_cur`, `offset_int_cur`, ...) and spline surfaces (`rb_blend_spl_sur`,
`rot_spl_sur`, `sweep_sur`, `cl_loft_spl_sur`, ...). Since 0.4.1 the converter
uses that fit when a boundary curve or a face support is such a record, for
every accepted ASM save version, directly or through a subtype reference.

- The fit is **derived geometry**. It differs from the source by up to the saved
  fit tolerance, typically 10⁻³ to 10⁻² mm. Exact geometry is never replaced
  by a fit, and the parsed model is unchanged: the record stays a `RawEntity`.
- Every use is listed in `CadQueryConverter.approximations` with the entity,
  subtype, fit tolerance and the code `geometry.approximated_from_stored_spline`.
  A converted body that depends on a fit is not exact; report it as such.
- The fit tolerance widens only the checks of the edges and faces that depend on
  the fit: endpoint agreement with the source vertices, curve-on-surface
  deviation of the projected trims, and UV joins at a shared vertex. Edges on a
  fitted curve are built on the source vertex positions with that tolerance.
- A fit saved as periodic keeps its periodic chart, so trims may cross its seam.
  A fitted face support keeps its whole knot domain; its saved UV subdomain is
  not applied because the boundaries meet it only within the fit tolerance.
- A face on a periodic support whose two boundaries wind around it, at least
  one of them fitted, has no seam edge in the source. `ShapeFix_Face` adds the
  chart seam and splits the fitted boundary there; the result is accepted only
  as one valid face whose boundary pieces lie on the unchanged source curves,
  and is recorded in `approximated_face_repairs`.
- A record without a stored fit (`nullbs`, as helical thread curves and surfaces
  are saved) stays unsupported. A fit whose layout is not understood is recorded
  in `approximation_failures` and the record stays unsupported.

Known gaps: fitted faces that end in a singular point (a blend running out to a
point, a cone apex next to a fitted curve) need a degenerated edge that is not
generated yet, and a missing seam on a surface of linear extrusion is not
repaired. These faces fail with `geometry.face_invalid` or a null-curve error.

NURBS and elliptical-cone conversion are experimental. Independent native-file
coverage is limited; synthetic examples do not establish general producer
compatibility or correspondence with a vendor application's current model state.

## Precision and failure behavior

The converter preserves source 3D boundary curves. Projected 2D trims may be
numerical approximations, but their curve-on-surface deviation must stay within
the original model's `resabs`. Qualified saved UV splines may use the observed
[source edge bound](tolerant-trims.md#local-edge-bound) introduced in the 0.3.4
implementation, with explicit per-edge diagnostics and unchanged geometry.
Failed projection, disconnected trims, invalid faces and open shells remain
errors. Model resolution and finite UV bounds remain fixed. The unreleased
[associated-curve support](tolerant-trims.md#unreleased-inline-and-associated-curves)
adds independently checked local endpoint/fit rules; fit tolerances never
increase a shared TEDGE allowance.

Cone, sphere, and torus `evaluate()` methods use canonical coordinates; saved
ACIS UV ranges are not interchangeable with those coordinates. NURBS evaluation
uses the unchanged supporting geometry. Metadata units and defaults are
documented in the [model API](model-api.md).

For elliptical-cone volume measurements, CadQuery's default integration can be
too coarse. Use OCCT's adaptive
`BRepGProp.VolumeProperties_s(shape, props, 1e-12)` when accurate volume is needed.

Diagnostic counts and individual valid edges or faces do not establish complete
solid conversion. Binary history and current-state limitations also apply; see
[SAB/ASM support](sab-support.md).
