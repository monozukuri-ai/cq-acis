# Experimental analytic authoring

Version 0.3.10 provides `from_cadquery` for one closed CadQuery solid.
It constructs an immutable semantic ACIS model and an experimental ASM 23200
SAB candidate without an Inventor API, native file, or template. Native kernel qualification is outside this API's scope. It does not write IPT.

```python
import cadquery as cq
from cq_acis import from_cadquery, parse_sab_model, to_cadquery

solid = cq.Workplane("XY").circle(7).extrude(19).val()
authored = from_cadquery(solid)
assert not authored.native_qualified
sab = authored.to_sab()
rebuilt = to_cadquery(parse_sab_model(sab)).val()
assert rebuilt.isValid()
```

Supported input consists of planes and circular cylinders bounded by straight
lines, circles and ellipses. The adapter keeps shared edges and vertices, inner
loops, full circles, both seam occurrences, face senses and edge parameters.
OCCT locations are applied once by its geometry adaptors. No mesh conversion or
STEP export occurs. A `Workplane` must contain exactly one `Solid`; explicitly
extract the desired solid from a compound before calling this function.

Input coordinates are millimetres. SAB coordinates use 10 mm per source unit;
line parameters retain millimetres and ellipse parameters retain radians.
The profile requires source tolerances no larger than 1e-5 mm. Each topology
table is limited to 4096 entries, coordinates to +/-1,000,000 mm, and uses to
8192. General splines in 3D, other surfaces, degenerate edges, multiple shells,
unconnected loops, unpaired edges and invalid frames are rejected. The Rust
builder checks reference ownership and analytic boundary consistency; it is
not a replacement for a general geometric self-intersection kernel.

Rust `FaceSpec` loops follow the supporting surface before applying the face
sense. Generated ACIS coedge walks follow the oriented face: reversed faces
reverse both the cyclic order and every edge-use sense. Shared partner uses
therefore run in opposite directions. A successful OCCT reconstruction alone
does not validate this convention; reconstruction can repair wire orientation.

`authored.pcurves` retains exact original OCCT UV line/ellipse/B-spline definitions
for qualification, including separate seam branches. `authored.charts` retains
source coordinate frames, UV bounds and the mapping of reflected cylindrical
charts to the generated chart. These UV curves are **not serialized** in the
current candidate SAB. Native kernel derivation remains an unqualified route;
local reconstruction does not prove that Inventor accepts it. Callers must not
use this candidate as a qualified native-file writer.

`to_sab(history=True)` adds an insertion-only state-one history candidate. This
is a geometry-layer history and does not initialize an Inventor document graph.
The existing `BoxSpec`/default Rust encoder remains a separate bounded profile.

## Semantic specification

`authored.to_spec()` returns a detached, JSON-compatible millimetre specification
of shared vertices, edges, supporting surfaces and face loops. It is suitable
for a downstream document writer; it contains no serialized native file or SAB
payload. Mutating the returned value does not change the authored shape. The
shared model API remains version 2.
