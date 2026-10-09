"""General Gmsh/OpenCASCADE provider: canonical geometry -> tagged mesh + entity map + receipt.

Pipeline::

    GeometryModel (Forge identity)
        -> OCC entities (rectangle/disk/box/cylinder/imported, placed in the root frame)
        -> cutouts (boolean difference with declared void tool bodies)
        -> fragment of every meshed body (conformal interfaces; overlaps refused)
        -> canonical feature matching (geometric containment, never tag order)
        -> physical groups (regions / boundaries / interfaces)
        -> mesh -> SpatialMesh
        -> ProviderEntityMap + MeshBinding + GeometryReceipt

Gmsh tags are translation details.  Every canonical feature is located by a
geometric statement about the body it belongs to (``xmin`` of a box is the face
on the plane local x = 0 within the box's extents), checked on sample points of
each provider entity.  An entity that matches nothing a declaration needs is
simply not grouped; a declared feature that matches no entity is a refusal.

Gmsh is a TOOL.  Its output is a numerical discretization of the declared
geometry; nothing here is evidence about the physical object.  When Gmsh cannot
run, :class:`~engcore.numerical.core.ProviderUnavailable` is raised -- a mesh is
never synthesized.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import os
import re
import tempfile
from typing import Any, Mapping

import numpy as np

from ..numerical.core import ProviderUnavailable
from ..scientific.fields import CellType
from ..scientific.units.quantity import Quantity
from .geometry import (
    Body, EntityMapping, FeatureRef, GeometryModel, GeometryReceipt, GeometryRefusal, MeshBinding, ProviderEntityMap,
    ShapeKind, Transform,
)
from .mesh import CoordinateFrame, GroupKind, MeshProvenance, PhysicalGroup, SpatialMesh
from .providers import gmsh_available

PROVIDER_ID = "gmsh"
ADAPTER_VERSION = "1"

#: Gmsh element type codes this adapter accepts: (cell, facet) per dimension.
_ELEMENT_TYPES = {2: (2, 1), 3: (4, 2)}   # 2D: 3-node triangle / 2-node line; 3D: 4-node tetra / 3-node triangle


@dataclass(frozen=True)
class GmshMeshRequest:
    """Meshing options.  Every option enters the receipt; none is chosen silently.

    ``size`` is the target element size (a length Quantity).  ``body_sizes``
    optionally refines individual bodies.  ``files`` maps an imported shape's
    sha256 to the local path holding those bytes (verified before import).
    """

    size: Quantity
    frame_id: str
    body_sizes: Mapping[str, Quantity] = field(default_factory=dict)
    algorithm_2d: int = 6
    algorithm_3d: int = 1
    files: Mapping[str, str] = field(default_factory=dict)

    def options(self) -> dict[str, Any]:
        from .geometry import length_m

        return {"size_m": length_m(self.size, "mesh size", positive=True),
                "body_sizes_m": {k: length_m(v, f"body size {k}", positive=True) for k, v in sorted(self.body_sizes.items())},
                "Mesh.Algorithm": int(self.algorithm_2d), "Mesh.Algorithm3D": int(self.algorithm_3d), "General.NumThreads": 1,
                "Mesh.ElementOrder": 1, "adapter_version": ADAPTER_VERSION}


@dataclass(frozen=True)
class GeometryMeshResult:
    model: GeometryModel
    mesh: SpatialMesh
    entity_map: ProviderEntityMap
    binding: MeshBinding
    receipt: GeometryReceipt

    def to_dict(self) -> dict[str, Any]:
        return {"geometry_digest": self.model.digest, "mesh_digest": self.mesh.digest, "entity_map": self.entity_map.to_dict(),
                "binding": self.binding.to_dict(), "receipt": self.receipt.to_dict()}


# --------------------------------------------------------------------------
# Feature predicates (body-local coordinates, metres)
# --------------------------------------------------------------------------


def _on_feature(body: Body, feature: str, p: tuple[float, float, float], tol: float) -> bool:
    x, y, z = p
    d = body.shape.dimensions_m
    k = body.shape.kind
    within = lambda v, hi: -tol <= v <= hi + tol  # noqa: E731
    if k is ShapeKind.RECTANGLE:
        L, W = d["length"], d["width"]
        return {"xmin": abs(x) <= tol and within(y, W), "xmax": abs(x - L) <= tol and within(y, W),
                "ymin": abs(y) <= tol and within(x, L), "ymax": abs(y - W) <= tol and within(x, L)}[feature]
    if k is ShapeKind.DISK:
        return abs(math.hypot(x, y) - d["radius"]) <= tol
    if k is ShapeKind.BOX:
        L, W, H = d["length"], d["width"], d["height"]
        return {"xmin": abs(x) <= tol and within(y, W) and within(z, H), "xmax": abs(x - L) <= tol and within(y, W) and within(z, H),
                "ymin": abs(y) <= tol and within(x, L) and within(z, H), "ymax": abs(y - W) <= tol and within(x, L) and within(z, H),
                "zmin": abs(z) <= tol and within(x, L) and within(y, W), "zmax": abs(z - H) <= tol and within(x, L) and within(y, W)}[feature]
    if k is ShapeKind.CYLINDER:
        r, H = d["radius"], d["height"]
        rho = math.hypot(x, y)
        return {"side": abs(rho - r) <= tol and within(z, H), "bottom": abs(z) <= tol and rho <= r + tol,
                "top": abs(z - H) <= tol and rho <= r + tol}[feature]
    if k is ShapeKind.IMPORTED:
        sel = next(s for s in body.shape.selectors if s.name == feature)
        return all(lo - tol <= v <= hi + tol for v, lo, hi in zip(p, sel.lower_m, sel.upper_m))
    raise GeometryRefusal(f"no feature predicate for {k.value}")


# --------------------------------------------------------------------------
# STEP unit header
# --------------------------------------------------------------------------

_SI_PREFIX = {"$": "m", ".MILLI.": "mm", ".CENTI.": "cm", ".DECI.": "dm", ".KILO.": "km", ".MICRO.": "um"}


def step_length_unit(data: bytes) -> str | None:
    """The length unit a STEP file declares, if exactly one is readable; None when absent or ambiguous."""
    text = data.decode("latin-1", "replace").upper()
    found = set()
    for m in re.finditer(r"SI_UNIT\s*\(\s*(\$|\.[A-Z]+\.)\s*,\s*\.METRE\.\s*\)", text):
        found.add(_SI_PREFIX.get(m.group(1), "?" + m.group(1)))
    for m in re.finditer(r"CONVERSION_BASED_UNIT\s*\(\s*'([A-Z]+)'", text):
        name = m.group(1)
        if name in ("INCH", "FOOT"):
            found.add(name.lower())
    if len(found) != 1:
        return None
    unit = found.pop()
    return None if unit.startswith("?") else unit


# --------------------------------------------------------------------------
# The adapter
# --------------------------------------------------------------------------


def _affine(t: Transform) -> list[float]:
    r, tr = t.rotation, t.translation_m
    return [r[0][0], r[0][1], r[0][2], tr[0], r[1][0], r[1][1], r[1][2], tr[1], r[2][0], r[2][1], r[2][2], tr[2]]


def _sha_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class GmshGeometryProvider:
    """Stateless adapter; one :meth:`mesh` call owns one Gmsh session from initialize to finalize."""

    provider_id = PROVIDER_ID

    @staticmethod
    def probe() -> tuple[bool, str]:
        return gmsh_available()

    def mesh(self, model: GeometryModel, request: GmshMeshRequest) -> GeometryMeshResult:
        ok, detail = gmsh_available()
        if not ok:
            raise ProviderUnavailable(f"Gmsh cannot run here: {detail}")
        if not isinstance(model, GeometryModel) or not isinstance(request, GmshMeshRequest):
            raise GeometryRefusal("mesh() needs a GeometryModel and a GmshMeshRequest")
        options = request.options()
        dim = model.dimension
        meshed = model.meshed_bodies()
        region_of: dict[str, str] = {}
        for r in model.regions:
            for b in r.bodies:
                if b in region_of:
                    raise GeometryRefusal(f"body {b!r} lies in regions {region_of[b]!r} and {r.name!r}; a mesh cell carries one "
                                          "region tag, so overlapping regions cannot be meshed")
                region_of[b] = r.name
        untagged = sorted(b.body_id for b in meshed if b.body_id not in region_of)
        if untagged:
            raise GeometryRefusal(f"meshed bodies {untagged} belong to no region; their cells would carry no identity")
        unknown_sizes = sorted(set(request.body_sizes) - {b.body_id for b in meshed})
        if unknown_sizes:
            raise GeometryRefusal(f"body sizes name unknown or void bodies {unknown_sizes}")
        file_digests = {}
        for b in model.bodies:
            if b.shape.kind is ShapeKind.IMPORTED:
                path = request.files.get(b.shape.source.file_digest)
                if path is None:
                    raise GeometryRefusal(f"no file supplied for imported body {b.body_id!r}")
                if _sha_file(path) != b.shape.source.file_digest:
                    raise GeometryRefusal(f"file for {b.body_id!r} does not have the declared sha256; refusing foreign bytes")
                file_digests[f"file:{b.body_id}"] = b.shape.source.file_digest

        import gmsh

        gmsh.initialize(readConfigFiles=False)
        try:
            version = gmsh.__version__
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.option.setNumber("General.NumThreads", 1)
            gmsh.option.setNumber("Mesh.Algorithm", int(request.algorithm_2d))
            gmsh.option.setNumber("Mesh.Algorithm3D", int(request.algorithm_3d))
            gmsh.option.setNumber("Mesh.ElementOrder", 1)
            gmsh.option.setNumber("Mesh.MeshSizeMin", 0.0)
            gmsh.option.setNumber("Mesh.MeshSizeMax", options["size_m"])
            gmsh.model.add("forge")
            occ = gmsh.model.occ
            tags = {b.body_id: self._create(gmsh, b, model, request) for b in model.bodies}
            # cutouts
            for b in meshed:
                if b.cutouts:
                    tools = [dt for c in b.cutouts for dt in tags[c]]
                    out, _ = occ.cut(tags[b.body_id], tools, removeObject=True, removeTool=False)
                    if not out:
                        raise GeometryRefusal(f"cutouts remove all of body {b.body_id!r}")
                    tags[b.body_id] = [tuple(x) for x in out]
            voids = [dt for b in model.bodies if b.void for dt in tags[b.body_id]]
            if voids:
                occ.remove(voids, recursive=True)
            # fragment: conformal interfaces between all meshed bodies
            order = [b.body_id for b in meshed]
            flat = [dt for bid in order for dt in tags[bid]]
            if len(flat) > 1:
                _, fmap = occ.fragment(flat, [])
                pieces: dict[str, list] = {bid: [] for bid in order}
                owner: dict[tuple[int, int], str] = {}
                i = 0
                for bid in order:
                    for _ in tags[bid]:
                        for piece in fmap[i]:
                            piece = tuple(piece)
                            if piece[0] != dim:
                                continue
                            if piece in owner and owner[piece] != bid:
                                raise GeometryRefusal(f"bodies {owner[piece]!r} and {bid!r} overlap; one cell cannot belong to two bodies")
                            owner[piece] = bid
                            pieces[bid].append(piece)
                        i += 1
                tags = {bid: sorted(set(v)) for bid, v in pieces.items()}
            occ.synchronize()
            for bid in order:
                if not tags[bid]:
                    raise GeometryRefusal(f"body {bid!r} produced no {dim}D entity")
            leftovers = {dt for dt in gmsh.model.getEntities(dim)} - {dt for bid in order for dt in tags[bid]}
            if leftovers:
                raise GeometryRefusal(f"provider produced {dim}D entities {sorted(leftovers)} that belong to no declared body")

            char = self._characteristic_length(gmsh)
            tol = max(1e-6 * char, 1e-12)
            boundary_entities = sorted({tuple(e) for e in gmsh.model.getEntities(dim - 1)})
            feature_hits = self._match_features(gmsh, model, boundary_entities, tol)
            body_boundary = {bid: sorted({(abs(d), abs(t)) for d, t in gmsh.model.getBoundary(tags[bid], combined=False, oriented=False)})
                             for bid in order}

            mappings: list[EntityMapping] = []
            for bid in sorted(tags):
                if tags[bid]:
                    mappings.append(EntityMapping(f"body:{bid}", tuple(tags[bid])))
            for fref, ents in sorted(feature_hits.items()):
                if ents:
                    mappings.append(EntityMapping(fref.entity_id, tuple(ents)))

            cell_groups: list[tuple[str, int, list]] = []
            for i, r in enumerate(model.regions, start=1):
                ents = sorted({dt for b in r.bodies for dt in tags[b]})
                cell_groups.append((r.name, i, ents))
                mappings.append(EntityMapping(r.entity_id, tuple(ents)))
            facet_groups: list[tuple[str, int, list]] = []
            claimed: dict[tuple[int, int], str] = {}
            tag = 1
            for bd in model.boundaries:
                ents: set = set()
                for f in bd.features:
                    hit = feature_hits.get(f, [])
                    if not hit:
                        raise GeometryRefusal(f"boundary {bd.name!r}: feature {f.body_id}/{f.feature} matches no provider entity "
                                              "(consumed by a boolean, or not where declared)")
                    ents.update(hit)
                facet_groups.append((bd.name, tag, sorted(ents)))
                tag += 1
            for itf in model.interfaces:
                shared = sorted(set(body_boundary[itf.body_a]) & set(body_boundary[itf.body_b]))
                if not shared:
                    raise GeometryRefusal(f"interface {itf.name!r}: bodies {itf.body_a!r} and {itf.body_b!r} share no face")
                facet_groups.append((itf.name, tag, shared))
                tag += 1
            for name, _, ents in facet_groups:
                for e in ents:
                    if e in claimed:
                        raise GeometryRefusal(f"provider entity {e} belongs to both {claimed[e]!r} and {name!r}; one facet carries one tag")
                    claimed[e] = name
                kind = "boundary" if any(b.name == name for b in model.boundaries) else "interface"
                mappings.append(EntityMapping(f"{kind}:{name}", tuple(ents)))

            for name, t, ents in cell_groups:
                gmsh.model.addPhysicalGroup(dim, [e[1] for e in ents], t, name)
            for name, t, ents in facet_groups:
                gmsh.model.addPhysicalGroup(dim - 1, [e[1] for e in ents], t, name)

            for bid, q in sorted(request.body_sizes.items()):
                pts = gmsh.model.getBoundary(tags[bid], combined=False, oriented=False, recursive=True)
                gmsh.model.mesh.setSize([(0, abs(p[1])) for p in pts if p[0] == 0], options["body_sizes_m"][bid])
            gmsh.model.mesh.generate(dim)

            node_tags, coords, _ = gmsh.model.mesh.getNodes()
            node_tags = np.asarray(node_tags, dtype=np.int64)
            xyz_all = np.asarray(coords, dtype=float).reshape(-1, 3)
            order_idx = np.argsort(node_tags)
            node_tags, xyz_all = node_tags[order_idx], xyz_all[order_idx]
            cell_type, facet_type = _ELEMENT_TYPES[dim]
            cells, cell_tags = [], []
            for _, t, ents in cell_groups:
                for _, e in ents:
                    types, _, conn = gmsh.model.mesh.getElements(dim, e)
                    for ty, cn in zip(types, conn):
                        if int(ty) != cell_type:
                            raise GeometryRefusal(f"Gmsh produced element type {ty}; only linear simplices were requested")
                        rows = np.asarray(cn, dtype=np.int64).reshape(-1, dim + 1)
                        cells.append(rows)
                        cell_tags.append(np.full(len(rows), t, dtype=np.int64))
            facets, facet_tags = [], []
            for _, t, ents in facet_groups:
                for _, e in ents:
                    types, _, conn = gmsh.model.mesh.getElements(dim - 1, e)
                    for ty, cn in zip(types, conn):
                        if int(ty) != facet_type:
                            raise GeometryRefusal(f"Gmsh produced facet type {ty}; only linear simplices were requested")
                        rows = np.asarray(cn, dtype=np.int64).reshape(-1, dim)
                        facets.append(rows)
                        facet_tags.append(np.full(len(rows), t, dtype=np.int64))
        finally:
            gmsh.finalize()

        cells_a = np.concatenate(cells)
        used = np.unique(cells_a)
        position = {int(t): i for i, t in enumerate(node_tags)}
        keep = np.array([position[int(t)] for t in used], dtype=np.int64)
        remap = {int(t): i for i, t in enumerate(used)}
        xyz = xyz_all[keep]
        if dim == 2:
            if np.any(np.abs(xyz[:, 2]) > tol):
                raise GeometryRefusal("a 2D mesh has nodes off the z = 0 plane")
            xyz = xyz[:, :2]
        cells_l = np.vectorize(remap.__getitem__)(cells_a)
        facets_l = None
        ftags = None
        if facets:
            fa = np.concatenate(facets)
            if not np.all(np.isin(fa, used)):
                raise GeometryRefusal("a tagged facet uses a node no cell uses")
            facets_l = np.vectorize(remap.__getitem__)(fa)
            ftags = np.concatenate(facet_tags)
        groups = tuple(PhysicalGroup(n, GroupKind.CELLS, t) for n, t, _ in cell_groups) + \
            tuple(PhysicalGroup(n, GroupKind.FACETS, t) for n, t, _ in facet_groups)
        provenance_options = dict(options, geometry_digest=model.digest)
        mesh = SpatialMesh(coordinates=xyz, cells=cells_l, cell_type=CellType.TRIANGLE if dim == 2 else CellType.TETRAHEDRON,
                           frame=CoordinateFrame(request.frame_id, dim), cell_tags=np.concatenate(cell_tags), facets=facets_l,
                           facet_tags=ftags, groups=groups, provenance=MeshProvenance(PROVIDER_ID, version, provenance_options))
        entity_map = ProviderEntityMap(PROVIDER_ID, version, model.digest, tuple(mappings))
        receipt = GeometryReceipt(PROVIDER_ID, version, "mesh_generation",
                                  {"geometry": model.digest, "shape": model.shape_digest, **file_digests},
                                  {"mesh": mesh.digest, "entity_map": entity_map.digest}, options)
        names = {r.entity_id: r.name for r in model.regions}
        names.update({b.entity_id: b.name for b in model.boundaries})
        names.update({i.entity_id: i.name for i in model.interfaces})
        binding = MeshBinding(model.digest, mesh.digest, names, entity_map.digest, receipt.digest).validate(model, mesh)
        return GeometryMeshResult(model, mesh, entity_map, binding, receipt)

    # ---- construction --------------------------------------------------------
    def _create(self, gmsh, body: Body, model: GeometryModel, request: GmshMeshRequest) -> list[tuple[int, int]]:
        occ = gmsh.model.occ
        d = body.shape.dimensions_m
        k = body.shape.kind
        if k is ShapeKind.RECTANGLE:
            dts = [(2, occ.addRectangle(0, 0, 0, d["length"], d["width"]))]
        elif k is ShapeKind.DISK:
            dts = [(2, occ.addDisk(0, 0, 0, d["radius"], d["radius"]))]
        elif k is ShapeKind.BOX:
            dts = [(3, occ.addBox(0, 0, 0, d["length"], d["width"], d["height"]))]
        elif k is ShapeKind.CYLINDER:
            dts = [(3, occ.addCylinder(0, 0, 0, 0, 0, d["height"], d["radius"]))]
        elif k is ShapeKind.IMPORTED:
            src = body.shape.source
            path = request.files[src.file_digest]
            with open(path, "rb") as fh:
                data = fh.read()
            scale = src.scale_to_m
            if src.format == "step":
                declared = Quantity(1.0, src.declared_length_unit).magnitude_in("m")
                header = step_length_unit(data)
                if header is None:
                    raise GeometryRefusal(f"STEP file of {body.body_id!r} states no single readable length unit; units are never guessed")
                if abs(Quantity(1.0, header).magnitude_in("m") - declared) > 1e-12 * declared:
                    raise GeometryRefusal(f"STEP file of {body.body_id!r} is in {header}; the declaration says {src.declared_length_unit}")
                # OpenCASCADE converts the file's declared unit to metres; no second scale is applied
                gmsh.option.setString("Geometry.OCCTargetUnit", "M")
                scale = 1.0
            suffix = ".step" if src.format == "step" else ".brep"
            with tempfile.TemporaryDirectory(prefix="forge-gmsh-") as tmp:
                local = os.path.join(tmp, "import" + suffix)
                with open(local, "wb") as fh:
                    fh.write(data)
                imported = occ.importShapes(local, highestDimOnly=True)
            dts = [tuple(x) for x in imported if x[0] == src.dimension]
            if not dts:
                raise GeometryRefusal(f"imported file of {body.body_id!r} contains no {src.dimension}D entity")
            if scale != 1.0:
                occ.dilate(dts, 0, 0, 0, scale, scale, scale)
        else:  # pragma: no cover - ShapeKind is closed
            raise GeometryRefusal(f"unsupported shape {k}")
        place = model.body_to_root(body.body_id)
        if not place.is_identity:
            occ.affineTransform(dts, _affine(place))
        return dts

    @staticmethod
    def _characteristic_length(gmsh) -> float:
        x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(-1, -1)
        return max(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), 1e-9)

    def _samples(self, gmsh, dim: int, tag: int) -> list[tuple[float, float, float]]:
        pts = [tuple(gmsh.model.getValue(0, abs(p[1]), [])) for p in
               gmsh.model.getBoundary([(dim, tag)], combined=False, oriented=False, recursive=True) if p[0] == 0]
        lo, hi = gmsh.model.getParametrizationBounds(dim, tag)
        lo, hi = list(lo), list(hi)
        fr = (0.2, 0.35, 0.5, 0.65, 0.8)
        cand = [[lo[0] + f * (hi[0] - lo[0])] for f in fr] if dim == 1 else \
            [[lo[0] + f * (hi[0] - lo[0]), lo[1] + g * (hi[1] - lo[1])] for f in fr for g in fr]
        for uv in cand:
            xyz = list(gmsh.model.getValue(dim, tag, uv))
            if dim == 1 or gmsh.model.isInside(dim, tag, xyz):
                pts.append(tuple(xyz))
        return pts

    def _match_features(self, gmsh, model: GeometryModel, entities, tol: float) -> dict[FeatureRef, list[tuple[int, int]]]:
        hits: dict[FeatureRef, list[tuple[int, int]]] = {}
        inverse = {b.body_id: model.body_to_root(b.body_id).inverse() for b in model.bodies}
        for dim, tag in entities:
            samples = self._samples(gmsh, dim, tag)
            if not samples:
                continue
            for b in model.bodies:
                local = [inverse[b.body_id].apply(p) for p in samples]
                for feat in b.shape.features:
                    if all(_on_feature(b, feat, p, tol) for p in local):
                        hits.setdefault(FeatureRef(b.body_id, feat), []).append((dim, tag))
        return hits


def mesh_geometry(model: GeometryModel, request: GmshMeshRequest) -> GeometryMeshResult:
    return GmshGeometryProvider().mesh(model, request)


def mesh_measure(mesh: SpatialMesh, cells: np.ndarray | None = None) -> float:
    """Total area (2D) or volume (3D) of the mesh cells -- a discretization statement, not a measurement."""
    x = mesh.coordinates
    c = mesh.cells if cells is None else mesh.cells[cells]
    if mesh.cell_type is CellType.TRIANGLE:
        a, b, d = x[c[:, 0]], x[c[:, 1]], x[c[:, 2]]
        return float(np.sum(0.5 * np.abs((b[:, 0] - a[:, 0]) * (d[:, 1] - a[:, 1]) - (d[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))))
    if mesh.cell_type is CellType.TETRAHEDRON:
        a, b, d, e = (x[c[:, i]] for i in range(4))
        return float(np.sum(np.abs(np.einsum("ij,ij->i", b - a, np.cross(d - a, e - a))) / 6.0))
    raise GeometryRefusal(f"mesh measure is implemented for simplices, not {mesh.cell_type.value}")


def facet_measure(mesh: SpatialMesh, facet_indices: np.ndarray) -> float:
    """Total length (2D) or area (3D) of the given tagged facets."""
    x = mesh.coordinates
    f = mesh.facets[facet_indices]
    if mesh.cell_type is CellType.TRIANGLE:
        return float(np.sum(np.linalg.norm(x[f[:, 1]] - x[f[:, 0]], axis=1)))
    if mesh.cell_type is CellType.TETRAHEDRON:
        return float(np.sum(0.5 * np.linalg.norm(np.cross(x[f[:, 1]] - x[f[:, 0]], x[f[:, 2]] - x[f[:, 0]]), axis=1)))
    raise GeometryRefusal(f"facet measure is implemented for simplices, not {mesh.cell_type.value}")
