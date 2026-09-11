"""Steady conduction on a rectangular plate, as a field problem end to end.

The vertical slice this spike exists to answer: a field-valued problem that is
declared, solved, validated, referenced and serialized through the platform's
own contracts, with nothing scientific hidden in metadata, an array or a label.

    -div(k grad T) = q          on a rectangular plate
    T = T0                      on a Dirichlet edge
    -k grad(T) . n = qn         on a Neumann edge

What is declared, and where it lives
------------------------------------
* the support, the field, the regions and the conditions are
  ``scientific.fields`` records — typed, unit-bearing and serializable;
* the values are a ``FieldValue`` in the runtime plane and reach the record as
  a content-addressed reference, never inline;
* the scalar evidence a reader acts on — extrema, the mean, the residual, the
  worst boundary error — are ``Quantity`` values on an ordinary
  ``ScientificResult``;
* what this model may be asked is stated in :data:`APPLICABILITY` and refused
  explicitly, rather than being whatever the assembly happens to tolerate.

Why this module is here rather than in ``domains/thermal``
----------------------------------------------------------
That tree is byte-pinned by three frozen experiments and its file set is
asserted, so nothing may be added to it. This package is where thermal work
that post-dates those freezes lives, and its own docstring says so.

Scope, stated so it is not mistaken for a solver framework: one equation, one
support type, constant isotropic conductivity, two boundary families, one
discretisation, one direct sparse solve. Anisotropy, temperature dependence,
three dimensions, unstructured supports and every transient term are refused by
:func:`require_applicable` rather than approximated.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ...data.field import FieldValue
from ...data.store import BulkDataStore, InMemoryBulkStore
from ...scientific.errors import InvalidScientificProblem
from ...scientific.fields import (
    BoundaryEdge,
    FieldBoundaryCondition,
    FieldDefinition,
    FieldLocation,
    FieldRecord,
    MeshRegion,
    StructuredMesh,
    boundary_regions,
    require_complete_boundary,
)
from ...scientific.ir.conditions import BoundaryKind
from ...scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from ...scientific.results.result import ScientificResult
from ...scientific.results.thresholds import VerificationThresholds
from ...scientific.results.validation import (
    ValidationCheck,
    ValidationOutcome,
    ValidationReport,
)
from ...scientific.solvers.protocol import ConvergenceState, SolverIdentity
from ...scientific.units.quantity import Quantity

SOLVER_ID = "thermal_models.conduction2d.finite_difference"
SOLVER_VERSION = "0.1.0"
BACKEND = "scipy.sparse.linalg.spsolve"

#: The dimension each declared input must carry. Checked by dimension and never
#: by unit string, so a plate in millimetres and a source in kW/m^3 are fine.
CONDUCTIVITY_UNIT = "watt/meter/kelvin"
SOURCE_UNIT = "watt/meter**3"
FLUX_UNIT = "watt/meter**2"
TEMPERATURE_UNIT = "kelvin"

#: What this model is for, in the terms a refusal is written in. Not prose: the
#: refusals below are generated from these statements, so the envelope a reader
#: sees is the envelope the code enforces.
APPLICABILITY = (
    "a rectangular Cartesian plate discretised by a structured rectilinear support",
    "one scalar field at the nodes, in a unit of temperature",
    "constant isotropic conductivity, strictly positive",
    "a volumetric source that is uniform or a field on the same support",
    "Dirichlet and Neumann boundary conditions only",
    "at least one Dirichlet condition, or the steady problem has no unique solution",
    "the steady equation only: no time term, and no temperature-dependent property",
)


#: Relative residual of the assembled linear system, below which the direct
#: solve is taken to have solved the system it was handed. A direct sparse
#: factorisation on a well-conditioned Laplacian lands many orders below this;
#: the number is here to catch a system that was *not* solved, not to grade one
#: that was.
RESIDUAL_REL_TOL = 1e-10

#: How far a node on a Dirichlet edge may sit from the value that was
#: prescribed there. Those rows are pinned by an identity row, so anything
#: above round-off means the boundary data did not reach the matrix.
BOUNDARY_ABS_TOL = 1e-9

#: The numbers this model judges against, as a record rather than as arguments.
#:
#: Sprint 1's lesson, applied before it could become a defect: a caller who can
#: pass the tolerance has defeated the verification, because the report that
#: comes back reads — in every field a consumer looks at — exactly like one
#: judged against the declared number. ``solve_steady_conduction`` therefore
#: takes a ``VerificationThresholds``, and a derived set still runs every
#: comparison and still reports every residual.
#:
#: **This gate awards no level, and is deliberately not registered in**
#: ``engcore.domains.SCIENTIFIC_THRESHOLD_DECLARATIONS``. The temptation is to
#: hand ``NUMERICALLY_CONVERGED`` to the residual check, the way the DC domain
#: does. This repository has already ruled on that, in the frozen conduction
#: validation and again in ``docs/domains/evidentiary-levels.md``: the linear
#: residual of a direct sparse factorisation sits at round-off in every run,
#: coarse or fine, so treating it as convergence would certify the 16 x 16
#: solve exactly as confidently as the 128 x 128 one. It is the same solver
#: kind and the same argument, so it gets the same answer.
#:
#: Convergence here is a claim about a *sequence* of solves, and the
#: manufactured-solution study is what establishes it. Registering this set
#: would claim an authority it does not exercise.
CONDUCTION2D_GATE_THRESHOLDS = VerificationThresholds(
    gate_id="thermal_models.conduction2d.verification_gate",
    version="0.1.0",
    values={
        "residual_rel_tol": RESIDUAL_REL_TOL,
        "boundary_abs_tol": BOUNDARY_ABS_TOL,
    },
    basis=(
        "declared for this architecture spike against the behaviour of a direct "
        "sparse factorisation on a five-point Laplacian, which lands several "
        "orders below both numbers. Neither is an accuracy claim about the "
        "discretisation, and neither awards a level: they separate a system "
        "that was solved from one that was not"
    ),
)


class Conduction2DError(InvalidScientificProblem):
    """A request this model does not serve, refused rather than approximated."""


@dataclass(frozen=True)
class SteadyConductionProblem:
    """One declared steady-conduction problem on one support."""

    problem_id: str
    mesh: StructuredMesh
    field: FieldDefinition
    conductivity: Quantity
    conditions: tuple[FieldBoundaryCondition, ...]
    source: Quantity | FieldValue | None = None
    regions: tuple[MeshRegion, ...] = ()
    description: str = ""
    metadata: Mapping[str, Any] = dataclass_field(default_factory=dict)

    def __post_init__(self) -> None:
        problem_id = str(self.problem_id).strip()
        if not problem_id:
            raise Conduction2DError("a conduction problem requires a problem_id")
        object.__setattr__(self, "problem_id", problem_id)
        object.__setattr__(self, "conditions", tuple(self.conditions))
        object.__setattr__(
            self, "regions", tuple(self.regions) or boundary_regions(self.mesh)
        )
        from ...scientific.results.immutable import freeze

        object.__setattr__(self, "metadata", freeze(dict(self.metadata)))
        require_applicable(self)

    @property
    def edges(self) -> Mapping[BoundaryEdge, FieldBoundaryCondition]:
        """The condition on each edge, by edge rather than by region id."""
        by_region = {region.region_id: region for region in self.regions}
        return {
            by_region[condition.region_id].edge: condition
            for condition in self.conditions
            if condition.field_id == self.field.field_id
        }


def require_applicable(problem: SteadyConductionProblem) -> None:
    """Refuse every request outside :data:`APPLICABILITY`, by name.

    Each refusal names the statement it violates, so a caller is told which
    part of the envelope they left rather than being handed a numerical
    symptom of it.
    """
    mesh, field = problem.mesh, problem.field
    if not isinstance(mesh, StructuredMesh):
        raise Conduction2DError(
            f"{problem.problem_id!r}: this model solves on a structured "
            f"rectilinear support, got {type(mesh).__name__}"
        )
    if mesh.dimensionality != 2:
        raise Conduction2DError(
            f"{problem.problem_id!r}: this model is two-dimensional and the "
            f"support is {mesh.dimensionality}-dimensional"
        )
    field.require_support(mesh)
    if field.location is not FieldLocation.NODE:
        raise Conduction2DError(
            f"{problem.problem_id!r}: this discretisation places unknowns at "
            f"nodes, and the field is declared at {field.location.value}s"
        )
    if field.components != 1:
        raise Conduction2DError(
            f"{problem.problem_id!r}: this model solves one scalar field, and "
            f"the field declares {field.components} components"
        )
    _require_dimension(field.unit, TEMPERATURE_UNIT, what=f"field {field.field_id!r}")

    conductivity = problem.conductivity
    if isinstance(conductivity, (tuple, list, np.ndarray)):
        raise Conduction2DError(
            f"{problem.problem_id!r}: conductivity is isotropic in this model "
            f"and was given {type(conductivity).__name__}; an anisotropic "
            f"conductivity is a different equation, not a different number"
        )
    if callable(conductivity):
        raise Conduction2DError(
            f"{problem.problem_id!r}: conductivity is constant in this model "
            f"and was given a callable; a temperature-dependent property makes "
            f"this equation nonlinear"
        )
    if not isinstance(conductivity, Quantity):
        raise Conduction2DError(
            f"{problem.problem_id!r}: conductivity must be a Quantity, got "
            f"{type(conductivity).__name__}"
        )
    _require_dimension(conductivity.units, CONDUCTIVITY_UNIT, what="conductivity")
    magnitude = conductivity.magnitude_in(CONDUCTIVITY_UNIT)
    if not math.isfinite(magnitude) or magnitude <= 0.0:
        raise Conduction2DError(
            f"{problem.problem_id!r}: conductivity must be finite and strictly "
            f"positive, got {conductivity}"
        )

    source = problem.source
    if source is not None:
        if isinstance(source, FieldValue):
            if source.mesh.fingerprint() != mesh.fingerprint():
                raise Conduction2DError(
                    f"{problem.problem_id!r}: the source field is on support "
                    f"{source.mesh.fingerprint()[:12]}… and the problem is on "
                    f"{mesh.fingerprint()[:12]}…"
                )
            _require_dimension(source.unit, SOURCE_UNIT, what="source field")
        elif isinstance(source, Quantity):
            _require_dimension(source.units, SOURCE_UNIT, what="source")
        else:
            raise Conduction2DError(
                f"{problem.problem_id!r}: a source is a uniform Quantity or a "
                f"FieldValue on this support, got {type(source).__name__}"
            )

    for condition in problem.conditions:
        if condition.kind not in (BoundaryKind.DIRICHLET, BoundaryKind.NEUMANN):
            raise Conduction2DError(
                f"{problem.problem_id!r}: condition {condition.name!r} is "
                f"{condition.kind.value!r}; this model serves dirichlet and "
                f"neumann only. A robin condition is representable in the core "
                f"records and is not served here"
            )
        if condition.kind is BoundaryKind.NEUMANN:
            _require_dimension(
                condition.value.units, FLUX_UNIT, what=f"condition {condition.name!r}"
            )
    require_complete_boundary(field, mesh, problem.regions, problem.conditions)
    if not any(c.kind is BoundaryKind.DIRICHLET for c in problem.conditions):
        raise Conduction2DError(
            f"{problem.problem_id!r}: every edge carries a flux condition, so "
            f"the steady temperature is determined only up to a constant and "
            f"the system is singular. Fix the level somewhere"
        )


def _require_dimension(unit: str, exemplar: str, *, what: str) -> None:
    from ...scientific.units.quantity import dimensionality

    if dimensionality(unit) != dimensionality(exemplar):
        raise Conduction2DError(
            f"{what} is measured in {unit!r}, and this model needs the "
            f"dimension of {exemplar!r}"
        )


# ---------------------------------------------------------------------------
# assembly and solve
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SteadyConductionSolution:
    """What a field solve produces: scalar evidence, and the field itself.

    Two records rather than one, deliberately. ``result`` is an ordinary
    ``ScientificResult`` — the same record every scalar domain produces, with
    ``Quantity`` values, provenance, a validation report and a typed reference
    to the field's bytes. ``field`` is the field-aware half, and ``store`` is a
    runtime fact the caller now owns.
    """

    result: ScientificResult
    field: FieldRecord
    values: FieldValue
    store: BulkDataStore

    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend=BACKEND)


def _source_array(problem: SteadyConductionProblem) -> np.ndarray:
    shape = problem.field.expected_shape(problem.mesh)
    if problem.source is None:
        return np.zeros(shape, dtype=np.float64)
    if isinstance(problem.source, FieldValue):
        return problem.source.to_unit(SOURCE_UNIT).values
    return np.full(shape, problem.source.magnitude_in(SOURCE_UNIT), dtype=np.float64)


def assemble(problem: SteadyConductionProblem) -> tuple[sp.csr_matrix, np.ndarray]:
    """The five-point operator for ``-k laplacian(T) = q`` and its right-hand side.

    Dirichlet nodes are pinned by an identity row rather than eliminated, which
    keeps the unknown numbering equal to the node numbering: a row of the
    solution is a row of the support, and no consumer has to invert a map.

    A Neumann edge is imposed by ghost-node elimination — the mirror of the
    first interior node, offset by the prescribed flux — which keeps the
    boundary truncation error second order and therefore does not flatten the
    convergence rate the whole study measures.
    """
    mesh, field = problem.mesh, problem.field
    nx, ny = mesh.nodes_x, mesh.nodes_y
    dx = mesh.spacing_x.magnitude_in("meter")
    dy = mesh.spacing_y.magnitude_in("meter")
    k = problem.conductivity.magnitude_in(CONDUCTIVITY_UNIT)
    q = _source_array(problem)
    edges = problem.edges

    n = nx * ny
    matrix = sp.lil_matrix((n, n), dtype=np.float64)
    rhs = np.zeros(n, dtype=np.float64)

    def index(i: int, j: int) -> int:
        return j * nx + i

    dirichlet: dict[int, float] = {}
    for edge, condition in edges.items():
        if condition.kind is not BoundaryKind.DIRICHLET:
            continue
        value = condition.value.magnitude_in(field.unit)
        region = next(r for r in problem.regions if r.edge is edge)
        for node in region.node_indices(mesh):
            dirichlet[node] = value

    for j in range(ny):
        for i in range(nx):
            row = index(i, j)
            if row in dirichlet:
                matrix[row, row] = 1.0
                rhs[row] = dirichlet[row]
                continue

            # -k * (d2T/dx2 + d2T/dy2) = q, five-point, with ghost nodes on
            # flux edges. A ghost node is eliminated against the interior
            # neighbour it mirrors, which doubles that neighbour's coefficient
            # and moves the flux into the right-hand side.
            centre = 2.0 * k / dx**2 + 2.0 * k / dy**2
            rhs[row] = q[j, i]

            for di, dj, spacing, edge_here in (
                (-1, 0, dx, BoundaryEdge.LEFT),
                (1, 0, dx, BoundaryEdge.RIGHT),
                (0, -1, dy, BoundaryEdge.BOTTOM),
                (0, 1, dy, BoundaryEdge.TOP),
            ):
                coefficient = -k / spacing**2
                ii, jj = i + di, j + dj
                inside = 0 <= ii < nx and 0 <= jj < ny
                if inside:
                    matrix[row, index(ii, jj)] += coefficient
                    continue
                # Off the support: this node is on `edge_here`, which carries a
                # flux condition (a Dirichlet edge would have been pinned).
                condition = edges[edge_here]
                flux = condition.value.magnitude_in(FLUX_UNIT)
                mirror_i, mirror_j = i - di, j - dj
                matrix[row, index(mirror_i, mirror_j)] += coefficient
                # T_ghost = T_mirror - 2 h qn / k, for -k dT/dn = qn on an
                # outward normal. Substituting leaves `coefficient * T_mirror`
                # on the left — hence the doubled neighbour above — and a
                # constant `-coefficient * 2 h qn / k`, which crosses to the
                # right-hand side with the sign it changes on the way.
                rhs[row] += coefficient * 2.0 * spacing * flux / k

            matrix[row, row] += centre

    return matrix.tocsr(), rhs


def solve_steady_conduction(
    problem: SteadyConductionProblem,
    *,
    run_id: str,
    store: BulkDataStore | None = None,
    software_version: str = f"{SOLVER_ID}/{SOLVER_VERSION}",
    git_commit: str | None = None,
    timestamp: str | None = None,
    thresholds: VerificationThresholds = CONDUCTION2D_GATE_THRESHOLDS,
) -> SteadyConductionSolution:
    """Solve one declared problem and return its scalar evidence and its field.

    ``thresholds`` is a record, not two numbers: a set derived from the declared
    one is still compared against, reported in full, and awards no level.
    """
    residual_rel_tol = thresholds["residual_rel_tol"]
    boundary_abs_tol = thresholds["boundary_abs_tol"]
    store = store if store is not None else InMemoryBulkStore()
    started = time.perf_counter()
    matrix, rhs = assemble(problem)
    solution = spla.spsolve(matrix.tocsc(), rhs)
    wall = time.perf_counter() - started

    mesh, field = problem.mesh, problem.field
    values = np.asarray(solution, dtype=np.float64).reshape(
        field.expected_shape(mesh)
    )
    finite = bool(np.all(np.isfinite(values)))

    checks: list[ValidationCheck] = []
    if not finite:
        checks.append(
            ValidationCheck(
                name="field_finite",
                outcome=ValidationOutcome.FAIL,
                detail="the linear solve did not produce a finite field",
            )
        )
        report = ValidationReport(checks=tuple(checks))
        raise Conduction2DError(
            f"{problem.problem_id!r}: the solve produced a non-finite field; "
            f"{report.checks[0].detail}"
        )

    solved = FieldValue(definition=field, mesh=mesh, values=values)
    record, reference = solved.store(store, name=f"{field.field_id}:field")

    residual = float(np.max(np.abs(matrix @ solution - rhs)))
    scale = float(np.max(np.abs(rhs))) or 1.0
    relative_residual = residual / scale
    checks.append(
        ValidationCheck(
            name="field_finite",
            outcome=ValidationOutcome.PASS,
            detail=f"all {solved.count} node values are finite",
        )
    )
    system_solved = relative_residual <= residual_rel_tol
    checks.append(
        ValidationCheck(
            name="field_linear_system_residual",
            outcome=(
                ValidationOutcome.PASS if system_solved else ValidationOutcome.FAIL
            ),
            detail=(
                f"max|A T - b| / max|b| = {relative_residual:.3e} against "
                f"{residual_rel_tol:.3e}; the factorisation solved the system "
                f"it was handed, which is not a statement about the equation"
            ),
            # Establishes nothing, on purpose. A direct sparse factorisation
            # sits at round-off whatever the resolution, so a level awarded
            # from this number would certify the coarsest solve exactly as
            # confidently as the finest. Convergence is a claim about a
            # sequence of solves; see CONDUCTION2D_GATE_THRESHOLDS.
            establishes=None,
            residual=relative_residual,
            tolerance=residual_rel_tol,
            evidence=thresholds.evidence(),
        )
    )

    worst_boundary = _worst_dirichlet_error(problem, solved)
    checks.append(
        ValidationCheck(
            # The name the scheme-carrying 1-D solver beside this one already
            # uses for the same claim, and which the evidentiary-level audit
            # has already ruled on: the scheme imposing its own constraint and
            # reading it back is not an independently obtained solution.
            name="boundary_conditions_held",
            outcome=(
                ValidationOutcome.PASS
                if worst_boundary <= boundary_abs_tol
                else ValidationOutcome.FAIL
            ),
            detail=(
                f"worst prescribed-value error on a dirichlet edge is "
                f"{worst_boundary:.3e} {field.unit}"
            ),
            establishes=None,
            residual=worst_boundary,
            tolerance=boundary_abs_tol,
            evidence=thresholds.evidence(),
        )
    )

    summary = solved.summary()
    result = ScientificResult(
        result_id=f"{run_id}:{problem.problem_id}",
        values={
            f"{field.field_id}:min": summary.minimum,
            f"{field.field_id}:max": summary.maximum,
            f"{field.field_id}:mean": summary.mean,
            f"{field.field_id}:l2_norm": summary.l2_norm,
        },
        provenance=ProvenanceRecord(
            run_id=run_id,
            software_version=software_version,
            git_commit=git_commit,
            timestamp=timestamp,
            solvers=((SOLVER_ID, SOLVER_VERSION),),
            inputs={
                "conductivity": problem.conductivity,
                "nodes_x": Quantity(float(mesh.nodes_x), "dimensionless"),
                "nodes_y": Quantity(float(mesh.nodes_y), "dimensionless"),
                "length_x": mesh.length_x,
                "length_y": mesh.length_y,
            },
            assumptions=APPLICABILITY,
            tolerances=dict(thresholds.values),
            metadata={
                "mesh_fingerprint": mesh.fingerprint(),
                "support": f"{mesh.nodes_x}x{mesh.nodes_y}",
                # Which set the numbers above came from, so a reader can tell a
                # declared judgement from an explored one without re-deriving it.
                "thresholds": thresholds.identity,
                "thresholds_digest": thresholds.threshold_digest,
            },
        ),
        problem_id=problem.problem_id,
        solver=SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend=BACKEND),
        # A direct sparse factorisation neither converges nor fails to, and
        # ``ConvergenceState`` says in as many words that the two must not be
        # conflated. The residual check below is what stands in for the claim
        # an iterative solver's CONVERGED would have made.
        convergence=ConvergenceState.NOT_APPLICABLE,
        validation=ValidationReport(checks=tuple(checks)),
        data_references=(reference,),
        metadata={"wall_seconds": wall},
    )
    return SteadyConductionSolution(
        result=result, field=record, values=solved, store=store
    )


def _worst_dirichlet_error(
    problem: SteadyConductionProblem, solved: FieldValue
) -> float:
    flat = solved.values.reshape(-1)
    worst = 0.0
    for edge, condition in problem.edges.items():
        if condition.kind is not BoundaryKind.DIRICHLET:
            continue
        prescribed = condition.value.magnitude_in(problem.field.unit)
        region = next(r for r in problem.regions if r.edge is edge)
        for node in region.node_indices(problem.mesh):
            worst = max(worst, abs(float(flat[node]) - prescribed))
    return worst


# ---------------------------------------------------------------------------
# declaring one
# ---------------------------------------------------------------------------
def plate_problem(
    *,
    problem_id: str,
    mesh: StructuredMesh,
    conductivity: Quantity,
    edge_values: Mapping[BoundaryEdge, Quantity],
    field_id: str = "T",
    field_unit: str = TEMPERATURE_UNIT,
    source: Quantity | FieldValue | None = None,
    edge_kinds: Mapping[BoundaryEdge, BoundaryKind] | None = None,
    description: str = "",
) -> SteadyConductionProblem:
    """A plate with one condition per edge, declared rather than assembled by hand.

    ``edge_values`` carries a temperature for a Dirichlet edge and a flux for a
    Neumann one; ``edge_kinds`` says which is which and defaults to Dirichlet
    everywhere.
    """
    kinds = dict(edge_kinds or {})
    regions = boundary_regions(mesh)
    field = FieldDefinition(
        field_id=field_id, unit=field_unit, mesh_id=mesh.mesh_id,
        description=description or "the solved field",
    )
    conditions: list[FieldBoundaryCondition] = []
    for region in regions:
        if region.edge not in edge_values:
            continue
        kind = kinds.get(region.edge, BoundaryKind.DIRICHLET)
        conditions.append(
            FieldBoundaryCondition(
                name=f"{field_id}-{region.edge.value}",
                field_id=field_id,
                region_id=region.region_id,
                kind=kind,
                value=edge_values[region.edge],
            )
        )
    return SteadyConductionProblem(
        problem_id=problem_id,
        mesh=mesh,
        field=field,
        conductivity=conductivity,
        conditions=tuple(conditions),
        source=source,
        regions=regions,
        description=description,
    )


def uniform_source(
    mesh: StructuredMesh, field_id: str, values: Sequence[Sequence[float]] | np.ndarray
) -> FieldValue:
    """A source field on ``mesh``, for a manufactured or measured distribution."""
    definition = FieldDefinition(
        field_id=f"{field_id}:source", unit=SOURCE_UNIT, mesh_id=mesh.mesh_id
    )
    return FieldValue(definition=definition, mesh=mesh, values=np.asarray(values, dtype=np.float64))


def node_grid(mesh: StructuredMesh) -> tuple[np.ndarray, np.ndarray]:
    """``(X, Y)`` node coordinates in metres, shaped like a node field."""
    x, y = mesh.axis_coordinates()
    return np.meshgrid(np.asarray(x), np.asarray(y))


def bindings_for(models: Iterable[tuple[str, str]]) -> tuple[ExecutionBinding, ...]:
    """Execution bindings for a caller that declares models. None are required."""
    identity = SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend=BACKEND)
    return tuple(
        ExecutionBinding(model=model, version=version, solver=identity)
        for model, version in models
    )
