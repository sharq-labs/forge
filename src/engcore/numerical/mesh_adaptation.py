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

Scope (what is NOT supported, by policy: active-epic exception EXC-1 covers
this slice only; :func:`require_supported_adaptation` refuses the rest)
    coarsening; transient or time-adaptive problems on an adapted grid (no
    conservative state transfer between grids is defined here); any 2D or 3D
    mesh (triangle / tetrahedron refinement); coupled field transfer between
    changing meshes.  Each needs an owner-approved EXC-1 amendment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Sequence

import numpy as np

from ..scenarios.timeline import canonical_digest
from ..scientific.units.quantity import Quantity, normalize_unit, require_spread_unit
from .core import NumericalRefusal

#: Phase 3 BR16: the adaptation combinations this module admits, and why the others are refused
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
