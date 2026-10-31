"""Local mesh adaptation in one dimension: indicators, marking, bisection, and an adaptation loop.

Adaptive mesh control, slice 2 (active-epic exception EXC-1, amendment A1).
Pure numerics: it computes, and holds no authority.  It refines a NON-UNIFORM
1D grid where a piecewise-linear (P1) solution's estimated interpolation error
is largest; no domain solver is changed, and no Core mesh record is.

Indicator
    For a cell of width ``h`` the P1 interpolation error is bounded by
    ``h**2 / 8 * max|u''|`` over the cell.  ``u''`` at an interior node is the
    non-uniform three-point estimate (exact for quadratics); a boundary node
    takes its neighbour's.  The cell indicator is ``h**2 / 8`` times the larger
    of its two nodal estimates.  It is an a-posteriori ESTIMATE that assumes a
    smooth solution: never a bound, and never validation.

Marking and refinement
    Doerfler (bulk) marking: the fewest cells, largest indicators first, whose
    indicators sum to at least ``theta`` times the total.  Marked cells are
    bisected, never below ``minimum_cell``.  Gradation control then bisects any
    cell more than ``max_ratio`` times larger than a neighbour, so the grid
    stays graded.

Loop
    :func:`adapt_grid` evaluates the caller's solution on the current grid
    (fresh values every cycle, never interpolated), and stops when the largest
    indicator is within the declared tolerance (an ESTIMATE), or when the cycle
    budget, node budget or resolution floor ends it.  Every cycle is recorded.

Provenance and validity (Phase 3 BR16, defect and stabilization fixes)
    Every grid version has a content digest; each cycle records the digest of
    the grid it evaluated, the cells it marked and the largest neighbour-size
    ratio, so the whole refinement history is reconstructible.  Only the final
    grid's values are reported: every earlier grid's values are superseded and
    their digests are listed as such.  A bisection whose midpoint is not
    strictly inside its cell in float64 is not performed (resolution floor),
    rather than producing a non-increasing grid.

Legacy adapt_grid scope
    require_supported_adaptation retains its original refusal of transient and
    multidimensional execution. Geometry-only refine/adapt_grid creates no trusted
    ancestry. The opt-in M1A MeshLineage1D and interval_transfer.AdaptiveMesh1D add
    recorded reversible bisections and managed state transfer under OD-6, not a
    transient solver or multidimensional/coupled adaptation capability.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Sequence

import numpy as np

from ..scenarios.timeline import canonical_digest
from ..scientific.units.quantity import Quantity, normalize_unit, require_spread_unit
from ..scientific.units.quantity import dimensionality, is_ratio_scale
from .core import NumericalRefusal

#: Legacy adapt_grid combinations; M1A requires the separate explicit lineage manager.
SUPPORTED_ADAPTATION = (
    {"dimension": 1, "transient": False, "operation": "bisection refinement with gradation",
     "status": "supported (EXC-1 A1)"},
)
REFUSED_ADAPTATION = (
    {"case": "coarsening", "reason": "not in EXC-1 A1; needs an owner-approved amendment"},
    {"case": "transient / time-adaptive state on an adapted grid",
     "reason": "no conservative state transfer between 1D grids is defined; EXC-1 A2 prohibits a transient solver"},
    {"case": "2D triangle or 3D tetrahedron refinement", "reason": "not in EXC-1; a new mesh-control slice"},
    {"case": "coupled field transfer between changing meshes",
     "reason": "the coupling runtime registers its supports at construction and refuses an unregistered one"},
)


def require_supported_adaptation(*, spatial_dimension: int, transient: bool) -> None:
    """Refuse every adaptation combination outside :data:`SUPPORTED_ADAPTATION`."""
    if spatial_dimension != 1:
        raise NumericalRefusal(f"local mesh adaptation is implemented in 1D only; {spatial_dimension}D is refused "
                               f"(owner decision: an EXC-1 amendment for triangle/tetrahedron refinement)")
    if transient:
        raise NumericalRefusal("adaptation of a transient problem is refused: no conservative state transfer between "
                               "adapted grids is defined (owner decision: EXC-1 amendment)")


@dataclass(frozen=True)
class Grid1D:
    """Strictly increasing node positions in one declared length unit."""

    nodes: tuple[float, ...]
    unit: str

    def __post_init__(self) -> None:
        nodes = tuple(float(x) for x in self.nodes)
        if len(nodes) < 3:
            raise NumericalRefusal("a 1D adaptive grid needs at least three nodes (two cells)")
        if not all(math.isfinite(x) for x in nodes) or any(b <= a for a, b in zip(nodes, nodes[1:])):
            raise NumericalRefusal("grid nodes must be finite and strictly increasing")
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "unit", normalize_unit(self.unit))

    @property
    def cell_widths(self) -> np.ndarray:
        return np.diff(np.asarray(self.nodes, dtype=float))

    @property
    def digest(self) -> str:
        """Phase 3 BR16: the content identity of this grid version (nodes and unit)."""
        return canonical_digest({"nodes": [float(x).hex() for x in self.nodes], "unit": self.unit})

    @property
    def max_neighbour_ratio(self) -> float:
        widths = self.cell_widths
        return float(np.max(np.maximum(widths[1:] / widths[:-1], widths[:-1] / widths[1:])))

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": list(self.nodes), "unit": self.unit}


def second_derivative_estimates(grid: Grid1D, values: Sequence[float]) -> np.ndarray:
    """Nodal ``u''`` estimates (non-uniform three-point; boundary nodes copy their neighbour)."""
    x = np.asarray(grid.nodes, dtype=float)
    u = np.asarray(values, dtype=float)
    if u.shape != x.shape or not np.all(np.isfinite(u)):
        raise NumericalRefusal("solution values must be finite, one per grid node")
    h = np.diff(x)
    left, right = h[:-1], h[1:]
    interior = 2.0 * ((u[2:] - u[1:-1]) / right - (u[1:-1] - u[:-2]) / left) / (left + right)
    return np.concatenate(([interior[0]], interior, [interior[-1]]))


def cell_indicators(grid: Grid1D, values: Sequence[float]) -> np.ndarray:
    """Per-cell estimated P1 interpolation error: ``h**2 / 8 * max(|u''|)`` at the cell's two nodes."""
    curvature = np.abs(second_derivative_estimates(grid, values))
    widths = grid.cell_widths
    return widths ** 2 / 8.0 * np.maximum(curvature[:-1], curvature[1:])


def doerfler_mark(indicators: Sequence[float], theta: float) -> list[int]:
    """The fewest cells (largest first) whose indicators sum to at least ``theta`` times the total."""
    eta = np.asarray(indicators, dtype=float)
    if not 0.0 < theta <= 1.0:
        raise NumericalRefusal("Doerfler theta must lie in (0, 1]")
    total = float(eta.sum())
    if total <= 0.0:
        return []
    order = sorted(range(eta.size), key=lambda i: (-eta[i], i))  # ties broken by position: deterministic
    marked, running = [], 0.0
    for index in order:
        marked.append(index)
        running += float(eta[index])
        if running >= theta * total:
            break
    return sorted(marked)


def refine(grid: Grid1D, marked: Sequence[int], *, minimum_cell: float, max_ratio: float) -> Grid1D:
    """Bisect the marked cells (never below ``minimum_cell``), then enforce neighbour size ratio <= ``max_ratio``."""
    nodes = list(grid.nodes)

    def bisectable(a: float, b: float) -> bool:
        # Phase 3 BR16: a midpoint that rounds onto an end would make the grid non-increasing
        middle = 0.5 * (a + b)
        return (b - a) / 2.0 >= minimum_cell and a < middle < b

    for index in sorted(set(marked), reverse=True):
        if not 0 <= index < len(nodes) - 1:
            raise NumericalRefusal(f"marked cell {index} does not exist on a grid of {len(nodes) - 1} cells")
        a, b = nodes[index], nodes[index + 1]
        if bisectable(a, b):
            nodes.insert(index + 1, 0.5 * (a + b))
    changed = True
    while changed:  # gradation: terminates because every bisection halves a cell and minimum_cell bounds it
        changed = False
        widths = np.diff(np.asarray(nodes, dtype=float))
        for i in range(widths.size - 1):
            big = i if widths[i] > max_ratio * widths[i + 1] else i + 1 if widths[i + 1] > max_ratio * widths[i] else None
            if big is not None and bisectable(nodes[big], nodes[big + 1]):
                nodes.insert(big + 1, 0.5 * (nodes[big] + nodes[big + 1]))
                changed = True
                break
    return Grid1D(tuple(nodes), grid.unit)


class _AuditOnlyRecord:
    @classmethod
    def from_dict(cls, payload):
        raise NumericalRefusal("serialized mesh audit data cannot establish issuance; trusted durable import is unsupported")


class _IssuedRecords:
    """Local issuance plus canonical snapshot, not scientific evidence or durable authority."""
    def __init__(self):
        self._records = {}

    @staticmethod
    def snapshot(record):
        try:
            return canonical_digest(record.to_dict())
        except Exception as exc:
            raise NumericalRefusal("invalid or tampered issued mesh record") from exc

    def issue(self, record):
        key, snapshot = record.record_id, self.snapshot(record)
        if key in self._records:
            previous, expected = self._records[key]
            self.require(previous)
            if snapshot != expected:
                raise NumericalRefusal("conflicting mesh record identity")
            return previous
        self._records[key] = (record, snapshot)
        return record

    def require(self, record):
        try:
            entry = self._records.get(record.record_id)
            if entry is None or entry[0] is not record or self.snapshot(record) != entry[1]:
                raise NumericalRefusal("unissued, substituted or tampered mesh record")
        except (AttributeError, TypeError, ValueError) as exc:
            raise NumericalRefusal("missing or malformed mesh issuance") from exc

    def verify(self):
        for key, (record, _) in tuple(self._records.items()):
            if record.record_id != key:
                raise NumericalRefusal("conflicting issued mesh registry key")
            self.require(record)

    def lookup(self, key, record_type):
        entry = self._records.get(key)
        if entry is None or not isinstance(entry[0], record_type) or entry[0].record_id != key:
            raise NumericalRefusal("missing authoritative mesh ancestry record")
        self.require(entry[0])
        return entry[0]


@dataclass(frozen=True)
class LineageCell1D(_AuditOnlyRecord):
    root_id: str
    parent_id: str | None
    left: float
    right: float

    def __post_init__(self):
        if not all(math.isfinite(x) for x in (self.left, self.right)) or not self.left < self.right:
            raise NumericalRefusal("lineage cell requires a positive finite interval")

    @property
    def cell_id(self):
        return canonical_digest({"schema": "lineage_cell_1d/1", "root": self.root_id, "parent": self.parent_id,
                                 "left": float(self.left).hex(), "right": float(self.right).hex()})

    @property
    def record_id(self):
        return self.cell_id

    def to_dict(self):
        return {"schema": "lineage_cell_1d/1", "cell_id": self.cell_id, "root_id": self.root_id,
                "parent_id": self.parent_id, "left": float(self.left).hex(), "right": float(self.right).hex()}


@dataclass(frozen=True)
class Bisection1D(_AuditOnlyRecord):
    parent: LineageCell1D
    children: tuple[LineageCell1D, LineageCell1D]

    def __post_init__(self):
        middle = .5*self.parent.left + .5*self.parent.right
        if (len(self.children) != 2 or not self.parent.left < middle < self.parent.right
                or any(c.parent_id != self.parent.cell_id or c.root_id != self.parent.root_id for c in self.children)
                or (self.children[0].left, self.children[0].right, self.children[1].left, self.children[1].right)
                   != (self.parent.left, middle, middle, self.parent.right)):
            raise NumericalRefusal("invalid exact parent/child bisection geometry or ancestry")

    @property
    def record_id(self):
        return canonical_digest({"schema": "bisection_1d/1", "parent": self.parent.to_dict(),
                                 "children": [c.to_dict() for c in self.children]})

    def to_dict(self):
        return {"schema": "bisection_1d/1", "bisection_id": self.record_id, "parent": self.parent.to_dict(),
                "children": [c.to_dict() for c in self.children]}


@dataclass(frozen=True)
class MeshVersion1D(_AuditOnlyRecord):
    root_id: str
    parent_version_id: str | None
    grid: Grid1D
    cells: tuple[LineageCell1D, ...]
    operation: str
    coordinate_frame: str
    root_context: str
    bisection_ids: tuple[str, ...] = ()
    policy: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if (len(self.cells) != len(self.grid.nodes)-1 or len({c.cell_id for c in self.cells}) != len(self.cells)
                or any(c.root_id != self.root_id or (c.left, c.right) != pair
                       for c, pair in zip(self.cells, zip(self.grid.nodes[:-1], self.grid.nodes[1:])))):
            raise NumericalRefusal("mesh version cells do not partition its exact grid")

    def _material(self):
        return {"schema": "mesh_version_1d/1", "root_id": self.root_id, "parent_version_id": self.parent_version_id,
                "grid": self.grid.to_dict(), "grid_digest": self.grid.digest, "cells": [c.to_dict() for c in self.cells],
                "operation": self.operation, "coordinate_frame": self.coordinate_frame,
                "root_context": self.root_context,
                "bisection_ids": list(self.bisection_ids), "policy": dict(self.policy)}

    @property
    def version_id(self):
        return canonical_digest(self._material())

    @property
    def record_id(self):
        return self.version_id

    def to_dict(self):
        # Reuse only this call's material; later reads still rebuild it so the
        # issuer can detect mutation. Custom representations keep their reads.
        if not _plain_mesh_material(self):
            return {**self._material(), "version_id": self.version_id}
        material = self._material()
        return {**material, "version_id": canonical_digest(material)}


def _plain_grid_material(grid):
    """Non-converting shape check for serialization reuse, never admission."""
    try:
        return (type(grid) is Grid1D and type(grid.nodes) is tuple and type(grid.unit) is str
                and all(type(x) is float for x in grid.nodes))
    except AttributeError:
        return False


def _plain_mesh_material(mesh):
    """Only builtin values have side-effect-free repeated material reads.

    A custom iterable or numeric conversion may mutate or raise on a later
    read. Inspect exact containers before traversing, and retain the original
    serialization path for anything else, including malformed records.
    """
    try:
        return (type(mesh) is MeshVersion1D and _plain_grid_material(mesh.grid)
                and type(mesh.root_id) is str
                and (mesh.parent_version_id is None or type(mesh.parent_version_id) is str)
                and type(mesh.operation) is str and type(mesh.coordinate_frame) is str
                and type(mesh.root_context) is str and type(mesh.cells) is tuple
                and all(type(cell) is LineageCell1D and type(cell.root_id) is str
                        and (cell.parent_id is None or type(cell.parent_id) is str)
                        and type(cell.left) is float and type(cell.right) is float for cell in mesh.cells)
                and type(mesh.bisection_ids) is tuple and all(type(x) is str for x in mesh.bisection_ids)
                and type(mesh.policy) is tuple
                and all(type(pair) is tuple and len(pair) == 2
                        and type(pair[0]) is str and type(pair[1]) is str for pair in mesh.policy))
    except AttributeError:
        return False


@dataclass(frozen=True)
class MeshChange1D(_AuditOnlyRecord):
    before: MeshVersion1D
    after: MeshVersion1D
    operation: str
    bisections: tuple[Bisection1D, ...]

    @property
    def record_id(self):
        return canonical_digest({"schema": "mesh_change_1d/1", "before": self.before.version_id,
                                 "after": self.after.version_id, "operation": self.operation,
                                 "bisections": [b.record_id for b in self.bisections]})

    def to_dict(self):
        return {"schema": "mesh_change_1d/1", "change_id": self.record_id,
                "before": self.before.to_dict(), "after": self.after.to_dict(), "operation": self.operation,
                "bisections": [b.to_dict() for b in self.bisections]}


class MeshLineage1D:
    """Explicit local issuer; existing geometry-only refinement grants no ancestry."""
    def __init__(self, grid: Grid1D, *, root_context: str, coordinate_frame: str):
        if not isinstance(root_context, str) or not root_context.strip():
            raise NumericalRefusal("root registration requires explicit context; it is not source evidence")
        if not isinstance(coordinate_frame, str) or not coordinate_frame.strip():
            raise NumericalRefusal("lineage requires explicit coordinate frame")
        if (not isinstance(grid, Grid1D) or not is_ratio_scale(grid.unit)
                or dimensionality(grid.unit) != dimensionality("m")
                or not np.all(np.isfinite(grid.cell_widths))):
            raise NumericalRefusal("lineage requires finite ratio-scale length geometry")
        self._issued = _IssuedRecords()
        self._changes_for_versions = {}
        root = canonical_digest({"schema": "mesh_root_1d/1", "grid": grid.digest, "context": root_context,
                                 "coordinate_frame": coordinate_frame})
        cells = tuple(LineageCell1D(root, None, a, b) for a, b in zip(grid.nodes[:-1], grid.nodes[1:]))
        self._current = self._issued.issue(MeshVersion1D(root, None, grid, cells, "root", coordinate_frame, root_context))

    @property
    def current(self):
        return self._current

    def verify(self):
        self._issued.verify()
        version, seen = self.current, set()
        while True:
            self._issued.require(version)
            if version.version_id in seen:
                raise NumericalRefusal("cyclic mesh version ancestry")
            seen.add(version.version_id)
            for key in version.bisection_ids:
                self._issued.lookup(key, Bisection1D)
            if version.parent_version_id is None:
                if version.operation != "root":
                    raise NumericalRefusal("missing declared root ancestry")
                break
            parent = self._issued.lookup(version.parent_version_id, MeshVersion1D)
            change = self._changes_for_versions.get(version.version_id)
            self._issued.require(change)
            if (change.before is not parent or change.after is not version
                    or (parent.root_id, parent.root_context, parent.coordinate_frame)
                       != (version.root_id, version.root_context, version.coordinate_frame)):
                raise NumericalRefusal("inconsistent mesh parent/change/root identity")
            version = parent

    def require(self, record):
        self.verify()
        self._issued.require(record)

    @staticmethod
    def _ratio(cells, max_ratio):
        if isinstance(max_ratio, bool) or not math.isfinite(max_ratio) or max_ratio < 1:
            raise NumericalRefusal("max_ratio must be explicit finite and >= 1")
        widths = [c.right-c.left for c in cells]
        if any(not math.isfinite(x) or x <= 0 for x in widths) or any(max(a/b, b/a) > max_ratio for a,b in zip(widths[:-1], widths[1:])):
            raise NumericalRefusal("mesh change violates finite widths or declared neighbour ratio")

    def _commit(self, cells, records, operation, max_ratio, minimum=None):
        self._ratio(cells, max_ratio)
        before = self.current
        grid = Grid1D((cells[0].left, *(c.right for c in cells)), before.grid.unit)
        records = tuple(self._issued.issue(r) for r in records)
        policy = (("max_ratio", float(max_ratio).hex()),) + (() if minimum is None else (("minimum_cell_in_grid_unit", float(minimum).hex()),))
        after = self._issued.issue(MeshVersion1D(before.root_id, before.version_id, grid, tuple(cells), operation, before.coordinate_frame, before.root_context,
                                                tuple(r.record_id for r in records), policy))
        change = self._issued.issue(MeshChange1D(before, after, operation, records))
        self._changes_for_versions[after.version_id] = change
        self._current = after
        return change

    def refine(self, cell_ids, *, minimum_cell: Quantity, max_ratio: float):
        self.verify()
        selected = tuple(cell_ids)
        active = {c.cell_id for c in self.current.cells}
        if not selected or len(set(selected)) != len(selected) or not set(selected).issubset(active):
            raise NumericalRefusal("refinement requires distinct active cell identities")
        if (not isinstance(minimum_cell, Quantity) or not is_ratio_scale(minimum_cell.units)
                or minimum_cell.dimensionality != dimensionality("m")):
            raise NumericalRefusal("minimum cell requires explicit ratio-scale length")
        minimum = minimum_cell.magnitude_in(self.current.grid.unit)
        if not math.isfinite(minimum) or minimum <= 0:
            raise NumericalRefusal("minimum cell must be positive finite")
        cells, records = [], []
        for cell in self.current.cells:
            if cell.cell_id not in selected:
                cells.append(cell)
                continue
            middle = .5*cell.left + .5*cell.right
            if not cell.left < middle < cell.right or min(middle-cell.left, cell.right-middle) < minimum:
                raise NumericalRefusal("bisection violates representability or declared minimum cell")
            children = (LineageCell1D(cell.root_id, cell.cell_id, cell.left, middle),
                        LineageCell1D(cell.root_id, cell.cell_id, middle, cell.right))
            records.append(Bisection1D(cell, children))
            cells.extend(children)
        return self._commit(cells, records, "refine", max_ratio, minimum)

    def coarsen(self, bisections, *, max_ratio: float):
        self.verify()
        records = tuple(bisections)
        if not records or any(not isinstance(r, Bisection1D) for r in records):
            raise NumericalRefusal("coarsening requires issued bisection records, never inferred neighbours")
        for record in records:
            self._issued.require(record)
        if len({r.record_id for r in records}) != len(records):
            raise NumericalRefusal("conflicting duplicate coarsening records")
        active = [c.cell_id for c in self.current.cells]
        replacements, removed = {}, set()
        for record in records:
            left, right = (c.cell_id for c in record.children)
            if left not in active or right not in active or active.index(right) != active.index(left)+1 or {left,right} & removed:
                raise NumericalRefusal("coarsening requires exact active adjacent siblings of the recorded parent")
            replacements[left] = record.parent
            removed.update((left,right))
        cells = [replacements[c.cell_id] if c.cell_id in replacements else c for c in self.current.cells
                 if c.cell_id not in removed or c.cell_id in replacements]
        return self._commit(cells, sorted(records, key=lambda r: r.parent.left), "coarsen", max_ratio)


class AdaptationStatus(str, Enum):
    #: the largest indicator is within the tolerance -- an ESTIMATE, not a bound
    TOLERANCE_MET_ESTIMATED = "tolerance_met_estimated"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NODE_BUDGET = "node_budget"
    RESOLUTION_FLOOR = "resolution_floor"


@dataclass(frozen=True)
class AdaptationPolicy:
    theta: float
    tolerance: Quantity          # a spread in the solution's unit
    minimum_cell: Quantity       # a length
    max_cycles: int
    max_nodes: int
    max_ratio: float = 2.0

    def __post_init__(self) -> None:
        if isinstance(self.theta, bool) or not 0.0 < float(self.theta) <= 1.0:
            raise NumericalRefusal("theta must lie in (0, 1]")
        object.__setattr__(self, "theta", float(self.theta))
        require_spread_unit(str(self.tolerance.units), context="adaptation tolerance")
        if not self.tolerance.magnitude > 0:
            raise NumericalRefusal("adaptation tolerance must be positive")
        if not self.minimum_cell.magnitude > 0:
            raise NumericalRefusal("minimum_cell must be a positive length")
        for label, low, high in (("max_cycles", 1, 50), ("max_nodes", 4, 1_000_000)):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise NumericalRefusal(f"{label} must be an int in [{low}, {high}]")
        if isinstance(self.max_ratio, bool) or not math.isfinite(float(self.max_ratio)) or float(self.max_ratio) < 1.5:
            raise NumericalRefusal("max_ratio must be >= 1.5 (bisection gradation)")
        object.__setattr__(self, "max_ratio", float(self.max_ratio))

    def to_dict(self) -> dict[str, Any]:
        return {"theta": self.theta, "tolerance": self.tolerance.to_dict(), "minimum_cell": self.minimum_cell.to_dict(),
                "max_cycles": self.max_cycles, "max_nodes": self.max_nodes, "max_ratio": self.max_ratio}


@dataclass(frozen=True)
class AdaptationCycle:
    cycle: int
    node_count: int
    max_indicator: float
    total_indicator: float
    marked_cells: int
    #: Phase 3 BR16 provenance: the grid version this cycle evaluated, the cells it marked on it,
    #: and that grid's largest neighbour-size ratio
    grid_digest: str = ""
    marked: tuple[int, ...] = ()
    max_neighbour_ratio: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"cycle": self.cycle, "node_count": self.node_count, "max_indicator": self.max_indicator,
                "total_indicator": self.total_indicator, "marked_cells": self.marked_cells,
                "grid_digest": self.grid_digest, "marked": list(self.marked),
                "max_neighbour_ratio": self.max_neighbour_ratio}


@dataclass(frozen=True)
class AdaptationRecord:
    status: AdaptationStatus
    reason: str
    policy: AdaptationPolicy
    value_unit: str
    cycles: tuple[AdaptationCycle, ...]
    grid: Grid1D
    values: tuple[float, ...]

    @property
    def superseded_grids(self) -> tuple[str, ...]:
        """Digests of every grid version whose values this record no longer reports (Phase 3 BR16)."""
        return tuple(c.grid_digest for c in self.cycles if c.grid_digest != self.grid.digest)

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "numerical_mesh_adaptation_not_scientific_evidence", "status": self.status.value,
                "reason": self.reason, "policy": self.policy.to_dict(), "value_unit": self.value_unit,
                "cycles": [c.to_dict() for c in self.cycles], "grid": self.grid.to_dict(), "values": list(self.values),
                "grid_digest": self.grid.digest, "superseded_grid_digests": list(self.superseded_grids),
                "notice": ("indicators are a-posteriori estimates of piecewise-linear interpolation error assuming a "
                           "smooth solution; not a bound, not validation")}


def adapt_grid(
    evaluate: Callable[[Grid1D], Sequence[float]],
    initial: Grid1D,
    policy: AdaptationPolicy,
    *,
    value_unit: str,
) -> AdaptationRecord:
    """Refine ``initial`` where the estimated error of ``evaluate``'s solution is largest (see the module docstring)."""
    tolerance = policy.tolerance.magnitude_as_spread_in(value_unit)
    minimum_cell = policy.minimum_cell.magnitude_in(initial.unit)
    grid = initial
    cycles: list[AdaptationCycle] = []
    for cycle in range(policy.max_cycles + 1):
        values = tuple(float(v) for v in evaluate(grid))  # fresh values on THIS grid, never interpolated
        eta = cell_indicators(grid, values)
        if not np.all(np.isfinite(eta)):
            raise NumericalRefusal(f"cycle {cycle}: the error indicators are not finite on grid {grid.digest[:12]}")
        marked = doerfler_mark(eta, policy.theta)
        cycles.append(AdaptationCycle(cycle, len(grid.nodes), float(eta.max()), float(eta.sum()), len(marked),
                                      grid.digest, tuple(marked), grid.max_neighbour_ratio))

        def done(status: AdaptationStatus, reason: str) -> AdaptationRecord:
            return AdaptationRecord(status, reason, policy, normalize_unit(value_unit), tuple(cycles), grid, values)

        if float(eta.max()) <= tolerance:
            return done(AdaptationStatus.TOLERANCE_MET_ESTIMATED,
                        f"largest estimated cell error {float(eta.max()):.6g} <= tolerance {tolerance:.6g} {value_unit}")
        if cycle == policy.max_cycles:
            return done(AdaptationStatus.BUDGET_EXHAUSTED,
                        f"{policy.max_cycles} cycles spent; largest estimated cell error {float(eta.max()):.6g} {value_unit}")
        refined = refine(grid, marked, minimum_cell=minimum_cell, max_ratio=policy.max_ratio)
        if len(refined.nodes) == len(grid.nodes):
            return done(AdaptationStatus.RESOLUTION_FLOOR,
                        f"every marked cell is at the minimum cell size {minimum_cell:g} {initial.unit}")
        if len(refined.nodes) > policy.max_nodes:
            return done(AdaptationStatus.NODE_BUDGET,
                        f"the next grid would have {len(refined.nodes)} nodes > max_nodes {policy.max_nodes}")
        grid = refined
    raise AssertionError("unreachable: the loop returns at max_cycles")  # pragma: no cover


__all__ = [
    "AdaptationCycle",
    "AdaptationPolicy",
    "AdaptationRecord",
    "AdaptationStatus",
    "Grid1D",
    "adapt_grid",
    "cell_indicators",
    "doerfler_mark",
    "refine",
    "REFUSED_ADAPTATION",
    "require_supported_adaptation",
    "second_derivative_estimates",
    "SUPPORTED_ADAPTATION",
]
