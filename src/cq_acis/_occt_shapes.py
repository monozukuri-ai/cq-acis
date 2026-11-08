"""OCCT-only shape wrappers: the subset of CadQuery's ``Shape`` API the converter uses.

The converter builds B-reps through a small set of CadQuery wrapper
constructors and accessors. This module provides the same names over bare
``OCP`` (``cadquery-ocp`` or ``cadquery-ocp-novtk``) so that conversion works
without the ``cadquery`` package. Every method mirrors the CadQuery
implementation of the same name; nothing here extends the geometry that the
converter accepts.

Wrapped shapes are downcast to their concrete ``TopoDS`` type on
construction, as CadQuery does, because OCCT builders require the exact type.
"""

from __future__ import annotations

from collections.abc import Iterable

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeSolid,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Sewing,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass3d import BRepClass3d
from OCP.BRepGProp import BRepGProp
from OCP.BRepLib import BRepLib_FindSurface
from OCP.gp import gp_Pnt
from OCP.GProp import GProp_GProps
from OCP.ShapeFix import ShapeFix_Face, ShapeFix_Shape, ShapeFix_Solid
from OCP.TopAbs import (
    TopAbs_COMPOUND,
    TopAbs_COMPSOLID,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
    TopAbs_WIRE,
)
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.TopTools import TopTools_IndexedMapOfShape, TopTools_ListOfShape

__all__ = [
    "BoundBox",
    "Compound",
    "CompSolid",
    "Edge",
    "Face",
    "Shape",
    "Shell",
    "Solid",
    "Vector",
    "Vertex",
    "Wire",
    "downcast",
    "shapetype",
]

_TYPE_NAMES = {
    TopAbs_VERTEX: "Vertex",
    TopAbs_EDGE: "Edge",
    TopAbs_WIRE: "Wire",
    TopAbs_FACE: "Face",
    TopAbs_SHELL: "Shell",
    TopAbs_SOLID: "Solid",
    TopAbs_COMPSOLID: "CompSolid",
    TopAbs_COMPOUND: "Compound",
}
_INVERSE_TYPE_NAMES = {name: kind for kind, name in _TYPE_NAMES.items()}
_DOWNCASTS = {
    TopAbs_VERTEX: TopoDS.Vertex_s,
    TopAbs_EDGE: TopoDS.Edge_s,
    TopAbs_WIRE: TopoDS.Wire_s,
    TopAbs_FACE: TopoDS.Face_s,
    TopAbs_SHELL: TopoDS.Shell_s,
    TopAbs_SOLID: TopoDS.Solid_s,
    TopAbs_COMPSOLID: TopoDS.CompSolid_s,
    TopAbs_COMPOUND: TopoDS.Compound_s,
}
# CadQuery's mass functions per shape kind; vertices have no mass properties.
_MASS_PROPERTIES = {
    TopAbs_EDGE: BRepGProp.LinearProperties_s,
    TopAbs_WIRE: BRepGProp.LinearProperties_s,
    TopAbs_FACE: BRepGProp.SurfaceProperties_s,
    TopAbs_SHELL: BRepGProp.SurfaceProperties_s,
    TopAbs_SOLID: BRepGProp.VolumeProperties_s,
    TopAbs_COMPSOLID: BRepGProp.VolumeProperties_s,
    TopAbs_COMPOUND: BRepGProp.VolumeProperties_s,
}


def shapetype(obj: TopoDS_Shape):
    if obj.IsNull():
        raise ValueError("Null TopoDS_Shape object")
    return obj.ShapeType()


def downcast(obj: TopoDS_Shape) -> TopoDS_Shape:
    """Downcast a ``TopoDS_Shape`` to its concrete ``TopoDS`` type."""
    return _DOWNCASTS[shapetype(obj)](obj)


class Vector:
    """A point or vector with the tuple accessors the converter reads."""

    __slots__ = ("x", "y", "z")

    def __init__(self, *args):
        if len(args) == 1:
            value = args[0]
            if isinstance(value, Vector):
                coordinates = (value.x, value.y, value.z)
            elif isinstance(value, gp_Pnt):
                coordinates = (value.X(), value.Y(), value.Z())
            else:
                coordinates = tuple(value)
        elif len(args) == 0:
            coordinates = (0.0, 0.0, 0.0)
        else:
            coordinates = args
        if len(coordinates) != 3:
            raise TypeError("Vector expects three coordinates")
        self.x, self.y, self.z = (float(c) for c in coordinates)

    def toTuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def toPnt(self) -> gp_Pnt:
        return gp_Pnt(self.x, self.y, self.z)

    def __repr__(self) -> str:
        return f"Vector({self.x}, {self.y}, {self.z})"

    def __eq__(self, other) -> bool:
        return isinstance(other, Vector) and self.toTuple() == other.toTuple()

    def __hash__(self) -> int:
        return hash(self.toTuple())


class BoundBox:
    """Axis-aligned bounds of a shape, as CadQuery's ``BoundBox`` exposes them."""

    __slots__ = ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")

    def __init__(self, box: Bnd_Box):
        self.xmin, self.ymin, self.zmin, self.xmax, self.ymax, self.zmax = box.Get()

    @property
    def xlen(self) -> float:
        return self.xmax - self.xmin

    @property
    def ylen(self) -> float:
        return self.ymax - self.ymin

    @property
    def zlen(self) -> float:
        return self.zmax - self.zmin

    @property
    def center(self) -> Vector:
        return Vector(
            (self.xmin + self.xmax) / 2,
            (self.ymin + self.ymax) / 2,
            (self.zmin + self.zmax) / 2,
        )

    @property
    def DiagonalLength(self) -> float:
        return (self.xlen**2 + self.ylen**2 + self.zlen**2) ** 0.5

    def __repr__(self) -> str:
        return (
            f"BoundBox(xmin={self.xmin}, xmax={self.xmax}, ymin={self.ymin}, "
            f"ymax={self.ymax}, zmin={self.zmin}, zmax={self.zmax})"
        )


class Shape:
    """A ``TopoDS_Shape`` with CadQuery-style topology and property accessors."""

    __slots__ = ("wrapped", "forConstruction", "label")

    def __init__(self, obj: TopoDS_Shape):
        self.wrapped = downcast(obj)
        self.forConstruction = False
        self.label = ""

    @classmethod
    def cast(cls, obj: TopoDS_Shape, forConstruction: bool = False) -> Shape:
        """Return the wrapper class matching the shape's topological type."""
        shape = _CONSTRUCTORS[shapetype(obj)](obj)
        shape.forConstruction = forConstruction
        return shape

    def __repr__(self) -> str:
        kind = "Null" if self.wrapped.IsNull() else self.ShapeType()
        return f"<cq_acis OCCT {kind} at {id(self):#x}>"

    def __hash__(self) -> int:
        return hash(self.wrapped)

    def __eq__(self, other) -> bool:
        return self.isSame(other) if isinstance(other, Shape) else False

    def ShapeType(self) -> str:
        return _TYPE_NAMES[shapetype(self.wrapped)]

    def isNull(self) -> bool:
        return self.wrapped.IsNull()

    def isSame(self, other: Shape) -> bool:
        return self.wrapped.IsSame(other.wrapped)

    def isEqual(self, other: Shape) -> bool:
        return self.wrapped.IsEqual(other.wrapped)

    def isValid(self) -> bool:
        return BRepCheck_Analyzer(self.wrapped).IsValid()

    def Closed(self) -> bool:
        """The OCCT closedness flag of the shape, not a geometric check."""
        return self.wrapped.Closed()

    def _entities(self, kind) -> list[Shape]:
        found = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(self.wrapped, kind, found)
        return [Shape.cast(found.FindKey(index)) for index in range(1, found.Extent() + 1)]

    def Vertices(self) -> list[Vertex]:
        return self._entities(TopAbs_VERTEX)

    def Edges(self) -> list[Edge]:
        """Edges with a 3D curve; like CadQuery, degenerated edges are left out."""
        return [
            edge for edge in self._entities(TopAbs_EDGE) if not BRep_Tool.Degenerated_s(edge.wrapped)
        ]

    def Wires(self) -> list[Wire]:
        return self._entities(TopAbs_WIRE)

    def Faces(self) -> list[Face]:
        return self._entities(TopAbs_FACE)

    def Shells(self) -> list[Shell]:
        return self._entities(TopAbs_SHELL)

    def Solids(self) -> list[Solid]:
        return self._entities(TopAbs_SOLID)

    def CompSolids(self) -> list[CompSolid]:
        return self._entities(TopAbs_COMPSOLID)

    def Compounds(self) -> list[Compound]:
        return self._entities(TopAbs_COMPOUND)

    def _mass_properties(self) -> GProp_GProps:
        calculate = _MASS_PROPERTIES.get(shapetype(self.wrapped))
        if calculate is None:
            raise ValueError("vertices have no mass properties")
        properties = GProp_GProps()
        calculate(self.wrapped, properties)
        return properties

    def Area(self) -> float:
        """The surface area of all faces in this shape."""
        properties = GProp_GProps()
        BRepGProp.SurfaceProperties_s(self.wrapped, properties)
        return properties.Mass()

    def Volume(self) -> float:
        """The volume of this shape (CadQuery's mass with unit density)."""
        return self._mass_properties().Mass()

    def Center(self) -> Vector:
        """The centre of mass of this shape."""
        return Vector(self._mass_properties().CentreOfMass())

    def BoundingBox(self, tolerance: float | None = None) -> BoundBox:
        del tolerance  # CadQuery's optimal bounds do not use it either.
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(self.wrapped, box)
        return BoundBox(box)


class Vertex(Shape):
    __slots__ = ()

    def toTuple(self) -> tuple[float, float, float]:
        point = BRep_Tool.Pnt_s(self.wrapped)
        return (point.X(), point.Y(), point.Z())

    def Center(self) -> Vector:
        """The centre of a vertex is itself."""
        return Vector(self.toTuple())


class _Mixin1D(Shape):
    __slots__ = ()

    def IsClosed(self) -> bool:
        return BRep_Tool.IsClosed_s(self.wrapped)


class Edge(_Mixin1D):
    __slots__ = ()

    @classmethod
    def makeLine(cls, v1, v2) -> Edge:
        """Create a linear edge between two points."""
        return cls(BRepBuilderAPI_MakeEdge(Vector(v1).toPnt(), Vector(v2).toPnt()).Edge())


class Wire(_Mixin1D):
    __slots__ = ()

    @classmethod
    def assembleEdges(cls, listOfEdges: Iterable[Edge]) -> Wire:
        """Build one wire from edges in any order; disconnected edges are rejected."""
        builder = BRepBuilderAPI_MakeWire()
        edges = TopTools_ListOfShape()
        for edge in listOfEdges:
            edges.Append(edge.wrapped)
        builder.Add(edges)
        builder.Build()
        if not builder.IsDone():
            raise ValueError(f"Cannot build wire: {builder.Error()}")
        return cls(builder.Wire())


class Face(Shape):
    __slots__ = ()

    @classmethod
    def makeFromWires(cls, outerWire: Wire, innerWires: Iterable[Wire] = ()) -> Face:
        """Make a planar face from a closed outer wire and optional inner wires."""
        inner = list(innerWires)
        if inner and not outerWire.IsClosed():
            raise ValueError("Cannot build face(s): outer wire is not closed")
        wires = Compound.makeCompound([outerWire, *inner])
        if not BRepLib_FindSurface(wires.wrapped, OnlyPlane=True).Found():
            raise ValueError("Cannot build face(s): wires not planar")
        fixer = ShapeFix_Shape(outerWire.wrapped)
        fixer.Perform()
        builder = BRepBuilderAPI_MakeFace(TopoDS.Wire_s(fixer.Shape()), True)
        for wire in inner:
            if not wire.IsClosed():
                raise ValueError("Cannot build face(s): inner wire is not closed")
            builder.Add(wire.wrapped)
        builder.Build()
        if not builder.IsDone():
            raise ValueError(f"Cannot build face(s): {builder.Error()}")
        face_fixer = ShapeFix_Face(builder.Face())
        face_fixer.FixOrientation()
        face_fixer.Perform()
        return cls(face_fixer.Result())


class Shell(Shape):
    __slots__ = ()

    @classmethod
    def makeShell(cls, listOfFaces: Iterable[Face]) -> Shell:
        """Sew faces; like CadQuery, the sewn result may wrap a compound of shells."""
        sewing = BRepBuilderAPI_Sewing()
        for face in listOfFaces:
            sewing.Add(face.wrapped)
        sewing.Perform()
        return cls(sewing.SewedShape())


class _Mixin3D(Shape):
    __slots__ = ()

    def outerShell(self) -> Shell:
        return Shell(BRepClass3d.OuterShell_s(self.wrapped))


class Solid(_Mixin3D):
    __slots__ = ()

    @classmethod
    def makeSolid(cls, shell: Shell) -> Solid:
        """Make a solid from a single shell, fixing its orientation."""
        return cls(ShapeFix_Solid().SolidFromShell(shell.wrapped))

    def addCavity(self, *shells: Shell | Solid) -> Solid:
        """Return a copy of this solid with the given shells as internal voids."""
        builder = BRepBuilderAPI_MakeSolid(self.wrapped)
        for shell in shells:
            builder.Add(
                shell.wrapped if isinstance(shell, Shell) else shell.outerShell().wrapped
            )
        fixer = ShapeFix_Solid(builder.Solid())
        fixer.Perform()
        return self.__class__(fixer.Solid())


class CompSolid(_Mixin3D):
    __slots__ = ()


class Compound(_Mixin3D):
    __slots__ = ()

    @classmethod
    def makeCompound(cls, listOfShapes: Iterable[Shape]) -> Compound:
        """Collect shapes into one compound."""
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        for shape in listOfShapes:
            builder.Add(compound, shape.wrapped)
        return cls(compound)


_CONSTRUCTORS = {
    TopAbs_VERTEX: Vertex,
    TopAbs_EDGE: Edge,
    TopAbs_WIRE: Wire,
    TopAbs_FACE: Face,
    TopAbs_SHELL: Shell,
    TopAbs_SOLID: Solid,
    TopAbs_COMPSOLID: CompSolid,
    TopAbs_COMPOUND: Compound,
}
