# Geometry support and limitations

Parsing and conversion have different scopes. A record can be retained or
decoded without being convertible to a CadQuery shape. Unsupported referenced
geometry raises `CadQueryConversionError`; it is not silently replaced with a
sampled surface or returned as a partially successful solid.

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
| Tolerant topology and finite UV trims | Selected ASM profiles described in [tolerant trims](tolerant-trims.md) |

Placements must be similarity transforms; general nonuniform scale and shear
are unsupported. Loopless sphere/torus faces with finite saved ranges are
rejected. General null-curve edges and multi-edge null loops are unsupported.

## Explicit NURBS profiles

- **SAT 700:** direct `exactsur` surfaces with `nubs` or `nurbs`, open clamped
  U/V directions, and no extra fields. Other SAT spline profiles stay raw.
- **ASM 22700 / embedded 22601:** forward explicit `exact_int_cur` curves and
  `exact_spl_sur` surfaces, including qualified subtype references. The admitted
  profile requires open clamped splines, no singularities, zero fit tolerance,
  and the supported default record fields. Unknown extensions remain raw.
  Curves require saved edge parameters and null support surfaces/pcurves.
  Surface bounds may be unbounded or a supported [finite UV domain](tolerant-trims.md).

Spline weights must be positive. The supported degree range is 1–16, with at
most 4,096 knot entries per direction, 65,536 expanded knots per direction, and
one million surface poles. Reversed or periodic spline profiles, sweeps, blends,
and other procedural geometry remain unsupported.

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
