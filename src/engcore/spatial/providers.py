"""Mesh providers: Gmsh (generation) and meshio (file I/O).  Tools, not authorities.

Every array a provider returns passes through :class:`SpatialMesh`, which
validates it and derives identity from content.  Provider version and options
are recorded as provenance; they are not part of mesh identity, so a tool
upgrade that yields identical arrays yields the identical mesh, and one that
does not is visibly a different mesh.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..numerical.core import ProviderUnavailable
from ..scientific.fields import CellType
from .mesh import CoordinateFrame, GroupKind, MeshProvenance, PhysicalGroup, SpatialMesh, SpatialRefusal


def gmsh_available() -> tuple[bool, str]:
    try:
        import gmsh  # noqa: F401
        gmsh.initialize(readConfigFiles=False)
        gmsh.finalize()
        return True, gmsh.__version__
    except Exception as exc:  # ImportError, or missing system GL libraries
        return False, f"{type(exc).__name__}: {exc}"


def gmsh_two_region_plate(*, length: float, height: float, split: float, size: float, frame_id: str = "plate-xy") -> SpatialMesh:
    """A rectangle [0,length]x[0,height] (metres) split at x=split into two cell regions.

    Physical groups: cells ``left_plate`` (1) / ``right_plate`` (2); facets
    ``left`` (11), ``right`` (12), ``bottom`` (13), ``top`` (14).  Generated
    with a fixed algorithm and a single thread so replay is meaningful; the
    options are recorded in provenance.
    """
    ok, detail = gmsh_available()
    if not ok:
        raise ProviderUnavailable(f"Gmsh cannot run here: {detail}")
    if not (0 < split < length and height > 0 and size > 0):
        raise SpatialRefusal("plate geometry requires 0 < split < length, height > 0, size > 0")
    import gmsh

    options = {"Mesh.Algorithm": 6, "General.NumThreads": 1, "Mesh.RandomFactor": 1e-9, "size": size,
               "length": length, "height": height, "split": split}
    gmsh.initialize(readConfigFiles=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.model.add("plate")
        occ = gmsh.model.occ
        r1 = occ.addRectangle(0, 0, 0, split, height)
        r2 = occ.addRectangle(split, 0, 0, length - split, height)
        occ.fragment([(2, r1)], [(2, r2)])
        occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMin", size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        surfaces = sorted(tag for _, tag in gmsh.model.getEntities(2))
        by_x = sorted(surfaces, key=lambda s: gmsh.model.occ.getCenterOfMass(2, s)[0])
        gmsh.model.addPhysicalGroup(2, [by_x[0]], 1, "left_plate")
        gmsh.model.addPhysicalGroup(2, [by_x[1]], 2, "right_plate")
        eps = 1e-5 * min(length, height)  # OCC pads bounding boxes (~1e-7)
        sides = {"left": [], "right": [], "bottom": [], "top": []}
        for _, c in gmsh.model.getEntities(1):
            x0, y0, _, x1, y1, _ = gmsh.model.getBoundingBox(1, c)
            if abs(x0) < eps and abs(x1) < eps:
                sides["left"].append(c)
            elif abs(x0 - length) < eps and abs(x1 - length) < eps:
                sides["right"].append(c)
            elif abs(y0) < eps and abs(y1) < eps:
                sides["bottom"].append(c)
            elif abs(y0 - height) < eps and abs(y1 - height) < eps:
                sides["top"].append(c)
        empty = [k for k, v in sides.items() if not v]
        if empty:
            raise SpatialRefusal(f"could not identify boundary curves {empty}; refusing to guess boundary tags")
        for tag, name in ((11, "left"), (12, "right"), (13, "bottom"), (14, "top")):
            gmsh.model.addPhysicalGroup(1, sides[name], tag, name)
        gmsh.model.mesh.generate(2)
        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        order = np.argsort(node_tags)
        index = {int(t): i for i, t in enumerate(np.asarray(node_tags)[order])}
        xyz = np.asarray(coords).reshape(-1, 3)[order][:, :2]
        cells, cell_tags = [], []
        for phys in (1, 2):
            for ent in gmsh.model.getEntitiesForPhysicalGroup(2, phys):
                types, _, conn = gmsh.model.mesh.getElements(2, ent)
                for t, cn in zip(types, conn):
                    if t != 2:
                        raise SpatialRefusal(f"Gmsh produced element type {t}; only 3-node triangles were requested")
                    tri = np.asarray(cn).reshape(-1, 3)
                    cells.extend([[index[int(v)] for v in row] for row in tri])
                    cell_tags.extend([phys] * len(tri))
        facets, facet_tags = [], []
        for phys in (11, 12, 13, 14):
            for ent in gmsh.model.getEntitiesForPhysicalGroup(1, phys):
                types, _, conn = gmsh.model.mesh.getElements(1, ent)
                for t, cn in zip(types, conn):
                    seg = np.asarray(cn).reshape(-1, 2)
                    facets.extend([[index[int(v)] for v in row] for row in seg])
                    facet_tags.extend([phys] * len(seg))
        version = gmsh.__version__
    finally:
        gmsh.finalize()
    used = sorted({v for row in cells for v in row})
    if used != list(range(len(xyz))):
        raise SpatialRefusal("Gmsh returned nodes that no cell uses; refusing an ambiguous node set")
    groups = (PhysicalGroup("left_plate", GroupKind.CELLS, 1), PhysicalGroup("right_plate", GroupKind.CELLS, 2),
              PhysicalGroup("left", GroupKind.FACETS, 11), PhysicalGroup("right", GroupKind.FACETS, 12),
              PhysicalGroup("bottom", GroupKind.FACETS, 13), PhysicalGroup("top", GroupKind.FACETS, 14))
    return SpatialMesh(coordinates=xyz, cells=cells, cell_type=CellType.TRIANGLE, frame=CoordinateFrame(frame_id, 2),
                       cell_tags=cell_tags, facets=facets, facet_tags=facet_tags, groups=groups,
                       provenance=MeshProvenance("gmsh", version, options))


# --------------------------------------------------------------------------
# meshio I/O
# --------------------------------------------------------------------------

_MESHIO_CELL = {CellType.TRIANGLE: "triangle", CellType.QUADRILATERAL: "quad", CellType.TETRAHEDRON: "tetra", CellType.HEXAHEDRON: "hexahedron"}
_FACET_BLOCK = {CellType.TRIANGLE: "line", CellType.QUADRILATERAL: "line", CellType.TETRAHEDRON: "triangle"}


def write_meshio(mesh: SpatialMesh, path: str, point_data: dict[str, Any] | None = None) -> None:
    """Write coordinates, cells, cell tags and tagged facets.  Groups travel as field_data."""
    import meshio

    dim = mesh.frame.dimension
    pts = mesh.coordinates if dim == 3 else np.column_stack([mesh.coordinates, np.zeros(mesh.node_count)])
    blocks = [(_MESHIO_CELL[mesh.cell_type], mesh.cells)]
    tags = [mesh.cell_tags]
    if len(mesh.facets):
        blocks.append((_FACET_BLOCK[mesh.cell_type], mesh.facets))
        tags.append(mesh.facet_tags)
    field_data = {g.name: np.array([g.tag, dim if g.kind is GroupKind.CELLS else dim - 1]) for g in mesh.groups}
    # Entity bookkeeping the Gmsh format requires; it carries no scientific content
    # (every node is attributed to the one surface/volume entity 1).
    pd = dict(point_data or {})
    meshio.write(path, meshio.Mesh(pts, blocks, point_data=pd, cell_data={"gmsh:physical": tags, "gmsh:geometrical": tags}, field_data=field_data),
                 file_format="gmsh22", binary=False)


def read_meshio(path: str, *, frame: CoordinateFrame) -> SpatialMesh:
    """Read a mesh file into an exact SpatialMesh.  Tags and groups must be present."""
    import meshio

    m = meshio.read(path)
    dim = frame.dimension
    cell_kind = {2: "triangle", 3: "tetra"}[dim]
    facet_kind = {2: "line", 3: "triangle"}[dim]
    phys = m.cell_data.get("gmsh:physical")
    if phys is None:
        raise SpatialRefusal("mesh file carries no physical tags; regions cannot be recovered and are not guessed")
    cells, ctags, facets, ftags = [], [], [], []
    for block, tag in zip(m.cells, phys):
        if block.type == cell_kind:
            cells.append(block.data); ctags.append(tag)
        elif block.type == facet_kind:
            facets.append(block.data); ftags.append(tag)
        elif block.type != "vertex":
            raise SpatialRefusal(f"unexpected cell block {block.type!r} in {path}")
    groups = tuple(PhysicalGroup(name, GroupKind.CELLS if int(v[1]) == dim else GroupKind.FACETS, int(v[0])) for name, v in m.field_data.items())
    return SpatialMesh(coordinates=m.points[:, :dim], cells=np.concatenate(cells), cell_type=CellType.TRIANGLE if dim == 2 else CellType.TETRAHEDRON,
                       frame=frame, cell_tags=np.concatenate(ctags), facets=np.concatenate(facets) if facets else None,
                       facet_tags=np.concatenate(ftags) if ftags else None, groups=groups,
                       provenance=MeshProvenance("meshio", meshio.__version__, {"path_basename": path.rsplit("/", 1)[-1]}))
