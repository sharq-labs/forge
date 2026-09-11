"""Two manufactured solutions, and the problems that should reproduce them.

The method of manufactured solutions in the only form that is worth anything
here: pick a smooth ``T``, put it into the operator to get the source and the
boundary data it implies, then ask the solver to recover ``T`` from those. A
discretisation that is subtly wrong cannot pass this by construction, which is
why the convergence study is measured against these rather than against a
second run of the same code.

Both are chosen so that every boundary value this model can express is a
constant on its edge, which is what the record carries. That constraint is real
and is reported as one: a boundary condition that varies along an edge is not
representable by :class:`FieldBoundaryCondition` as it stands.

``SINE_PLATE``
    ``T = T0 + A sin(pi x/Lx) sin(pi y/Ly)``, Dirichlet on all four edges.
    Genuinely two-dimensional: both second derivatives are non-zero and the
    error is not dominated by either axis.

``COSINE_COLUMN``
    ``T = T0 + A cos(pi y / 2Ly)``, Dirichlet below, a **non-zero** constant
    flux above, zero flux at the sides. This is the case that discriminates the
    Neumann treatment: a one-sided first-order flux condition reproduces the
    plate case and this one's interior perfectly well, and loses an order here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from engcore.domains.thermal_models.conduction2d import (
    SOURCE_UNIT,
    SteadyConductionProblem,
    node_grid,
    plate_problem,
)
from engcore.scientific.fields import BoundaryEdge, FieldDefinition, StructuredMesh
from engcore.scientific.ir.conditions import BoundaryKind
from engcore.data.field import FieldValue
from engcore.scientific.units.quantity import Quantity

CONDUCTIVITY = Quantity(12.5, "watt/meter/kelvin")
OFFSET = 300.0
AMPLITUDE = 40.0


@dataclass(frozen=True)
class Manufactured:
    """A closed-form field, and the problem whose solution it must be."""

    name: str
    exact: Callable[[np.ndarray, np.ndarray], np.ndarray]
    build: Callable[[StructuredMesh, str], SteadyConductionProblem]

    def problem(self, mesh: StructuredMesh, problem_id: str = "") -> SteadyConductionProblem:
        return self.build(mesh, problem_id or f"{self.name}:{mesh.nodes_x}x{mesh.nodes_y}")

    def exact_on(self, mesh: StructuredMesh) -> np.ndarray:
        x, y = node_grid(mesh)
        return self.exact(x, y)


def square(nodes: int, mesh_id: str = "plate", length: float = 1.0) -> StructuredMesh:
    return StructuredMesh(
        mesh_id, Quantity(length, "meter"), Quantity(length, "meter"), nodes, nodes
    )


def _source_field(mesh: StructuredMesh, values: np.ndarray) -> FieldValue:
    return FieldValue(
        definition=FieldDefinition("q", SOURCE_UNIT, mesh.mesh_id),
        mesh=mesh,
        values=values,
    )


# ---- T = T0 + A sin(pi x / Lx) sin(pi y / Ly) ---------------------------------------
def _sine_exact(x: np.ndarray, y: np.ndarray, lx: float = 1.0, ly: float = 1.0) -> np.ndarray:
    return OFFSET + AMPLITUDE * np.sin(math.pi * x / lx) * np.sin(math.pi * y / ly)


def _sine_problem(mesh: StructuredMesh, problem_id: str) -> SteadyConductionProblem:
    lx = mesh.length_x.magnitude_in("meter")
    ly = mesh.length_y.magnitude_in("meter")
    k = CONDUCTIVITY.magnitude_in("watt/meter/kelvin")
    x, y = node_grid(mesh)
    # -k laplacian(T) = k (pi^2/Lx^2 + pi^2/Ly^2) (T - T0)
    factor = (math.pi / lx) ** 2 + (math.pi / ly) ** 2
    source = k * factor * (_sine_exact(x, y, lx, ly) - OFFSET)
    return plate_problem(
        problem_id=problem_id,
        mesh=mesh,
        conductivity=CONDUCTIVITY,
        edge_values={edge: Quantity(OFFSET, "kelvin") for edge in BoundaryEdge},
        source=_source_field(mesh, source),
        description="manufactured sine plate",
    )


SINE_PLATE = Manufactured("sine_plate", _sine_exact, _sine_problem)


# ---- T = T0 + A cos(pi y / 2 Ly) -----------------------------------------------------
def _cosine_exact(x: np.ndarray, y: np.ndarray, ly: float = 1.0) -> np.ndarray:
    return OFFSET + AMPLITUDE * np.cos(math.pi * y / (2.0 * ly))


def _cosine_problem(mesh: StructuredMesh, problem_id: str) -> SteadyConductionProblem:
    ly = mesh.length_y.magnitude_in("meter")
    k = CONDUCTIVITY.magnitude_in("watt/meter/kelvin")
    x, y = node_grid(mesh)
    wavenumber = math.pi / (2.0 * ly)
    source = k * wavenumber**2 * AMPLITUDE * np.cos(wavenumber * y)
    # Outward normal +y at the top: -k dT/dy = +k A w sin(w Ly) = k A w.
    top_flux = k * AMPLITUDE * wavenumber * math.sin(wavenumber * ly)
    return plate_problem(
        problem_id=problem_id,
        mesh=mesh,
        conductivity=CONDUCTIVITY,
        edge_values={
            BoundaryEdge.BOTTOM: Quantity(OFFSET + AMPLITUDE, "kelvin"),
            BoundaryEdge.TOP: Quantity(top_flux, "watt/meter**2"),
            BoundaryEdge.LEFT: Quantity(0.0, "watt/meter**2"),
            BoundaryEdge.RIGHT: Quantity(0.0, "watt/meter**2"),
        },
        edge_kinds={
            BoundaryEdge.TOP: BoundaryKind.NEUMANN,
            BoundaryEdge.LEFT: BoundaryKind.NEUMANN,
            BoundaryEdge.RIGHT: BoundaryKind.NEUMANN,
        },
        source=_source_field(mesh, source),
        description="manufactured cosine column with a non-zero flux edge",
    )


COSINE_COLUMN = Manufactured("cosine_column", _cosine_exact, _cosine_problem)

MANUFACTURED = (SINE_PLATE, COSINE_COLUMN)
REFINEMENTS = (16, 32, 64, 128)


# ---- measuring --------------------------------------------------------------------
def errors(solved: np.ndarray, exact: np.ndarray) -> tuple[float, float]:
    """``(L2, Linf)`` of the nodal error, L2 as a mesh-independent RMS."""
    difference = np.asarray(solved, dtype=np.float64) - np.asarray(exact, dtype=np.float64)
    return (
        float(math.sqrt(float(np.mean(difference**2)))),
        float(np.max(np.abs(difference))),
    )


def observed_order(coarse: tuple[float, float], fine: tuple[float, float]) -> float:
    """``log(e_coarse/e_fine) / log(h_coarse/h_fine)`` for ``(h, error)`` pairs."""
    (h_coarse, e_coarse), (h_fine, e_fine) = coarse, fine
    if e_fine <= 0.0 or e_coarse <= 0.0:
        return float("nan")
    return math.log(e_coarse / e_fine) / math.log(h_coarse / h_fine)


def spacing_of(mesh: StructuredMesh) -> float:
    return mesh.spacing_x.magnitude_in("meter")
