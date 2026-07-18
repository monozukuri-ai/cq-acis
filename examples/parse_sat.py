"""Parse an ACIS SAT file and export its CadQuery bodies for inspection.

Run from the repository root after installing ``cq-acis[cadquery]``::

    python examples/parse_sat.py
    python examples/parse_sat.py path/to/model.sat --show

The script always writes STEP, STL, and SVG files.  ``--show`` additionally
tries to display the shapes in the optional ``ocp_vscode`` viewer.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cq_acis import import_sat_file


DEFAULT_SOURCE = Path("corpus/data/ezdxf/cube_sat_700.sat")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"SAT file to parse (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("examples/output"),
        help="directory for STEP, STL, and SVG exports",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="display the converted bodies with the optional ocp_vscode viewer",
    )
    return parser.parse_args()


def export_body(shape, output_stem: Path) -> None:
    from cadquery import exporters

    exporters.export(shape, str(output_stem.with_suffix(".step")), "STEP")
    exporters.export(shape, str(output_stem.with_suffix(".stl")), "STL")
    exporters.export(shape, str(output_stem.with_suffix(".svg")), "SVG")


def main() -> None:
    args = parse_args()
    if not args.source.is_file():
        raise SystemExit(f"SAT file not found: {args.source}")

    workplane = import_sat_file(args.source)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"source: {args.source}")
    print(f"bodies: {workplane.size()}")
    for index, shape in enumerate(workplane.vals()):
        output_stem = args.output_dir / f"{args.source.stem}_body{index}"
        export_body(shape, output_stem)
        bounds = shape.BoundingBox()
        print(
            f"body {index}: {type(shape).__name__}, "
            f"valid={shape.isValid()}, volume={shape.Volume():.12g}, "
            f"faces={len(shape.Faces())}, "
            f"bbox=({bounds.xmin:.6g}, {bounds.xmax:.6g}, "
            f"{bounds.ymin:.6g}, {bounds.ymax:.6g}, "
            f"{bounds.zmin:.6g}, {bounds.zmax:.6g})"
        )

    if args.show:
        try:
            from ocp_vscode import show
        except ImportError as error:
            raise SystemExit(
                "--show requires ocp_vscode; open the exported STL/STEP files "
                "in a 3D viewer instead"
            ) from error
        show(*workplane.vals())


if __name__ == "__main__":
    main()
