"""Conduction1DSolver — a ScientificSolver over backward-Euler finite differences.

The five lifecycle stages stay strictly separated, exactly as the Electrical
domain keeps them:

``supports`` (capability question, never executes)
→ ``prepare`` (assemble the tridiagonal system)
→ ``solve`` (SciPy sparse factorization and time march, raw floats)
→ ``extract_metrics`` (units restored)
→ ``validate`` (independent checks)

DISCRETIZATION
--------------
Second-order central differences in space, backward Euler in time. Each step
solves ``(I - r T) u_new = u_old`` with ``r = alpha dt / dx^2`` and ``T`` the
standard second-difference operator. The matrix is constant in time, so it is
factorized once and reused — that is why ``iterations`` reports the number of
back-substitutions rather than a count of nonlinear passes.

Backward Euler was chosen over an explicit scheme deliberately. It is
unconditionally stable, so a coarse rung degrades in *accuracy* rather than
blowing up. A fidelity ladder whose cheap rung diverges demonstrates a
stability limit; a ladder whose cheap rung is merely inaccurate demonstrates
discretization error, which is what this domain exists to expose.

WHAT THIS SOLVER DOES NOT CLAIM
-------------------------------
``validate`` never awards ``NUMERICALLY_CONVERGED``. A direct sparse
factorization has a linear residual at round-off, and reporting that as
numerical convergence would conflate linear-algebra accuracy with
discretization accuracy — two unrelated things that happen to share a word.
Discretization convergence can only be established by refining, which needs
more than one solve, so it lives in :mod:`validation` and is a claim about a
*sequence* of results. The per-solve report says so explicitly with a NOT_RUN
check rather than staying silent about it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ....scientific.ir.problem import ScientificProblem
from ....scientific.results.provenance import ProvenanceRecord
from ....scientific.results.result import ScientificResult
from ....scientific.results.uncertainty import Uncertainty
from ....scientific.results.validation import ValidationReport
from ....scientific.solvers.protocol import (
    ConvergenceState,
    PreparedSolve,
    RawSolverOutput,
    SolverIdentity,
    SolverSettings,
)
from ....scientific.units.quantity import Quantity
from .errors import SlabBindingError, ThermalConduction1DError
from .problem import (
    CONDUCTION_MODELS,
    FIELD_UNIT,
    LEFT_METRIC,
    MAX_METRIC,
    MIDPOINT_METRIC,
    RIGHT_METRIC,
    THERMAL_CONDUCTION_1D,
    ConductionSlab,
    conduction_solver_capabilities,
    verify_problem_matches_slab,
)
from .validation import ConductionValidationSettings, build_validation_report

SOLVER_ID = "thermal.conduction1d.backward_euler_fd"
SOLVER_VERSION = "0.1.0"
BACKEND = "scipy.sparse.linalg.splu"


@dataclass(frozen=True)
class PreparedConductionSystem:
    """The assembled system and the grid it lives on."""

    slab: ConductionSlab
    matrix: Any                    # scipy.sparse CSC, (n_interior, n_interior)
    x_nodes: np.ndarray            # all nodes, including both boundaries
    initial_interior: np.ndarray   # u(x, 0) at interior nodes
    r: float                       # alpha dt / dx^2

    @property
    def n_interior(self) -> int:
        return int(self.initial_interior.size)

    @property
    def midpoint_index(self) -> int:
        """Index of x = L/2 in the FULL node array. Exact for an even mesh."""
        return self.slab.discretization.n_cells // 2


def assemble(slab: ConductionSlab) -> PreparedConductionSystem:
    """Build ``(I - r T)`` for the interior nodes.

    Dirichlet ends are not unknowns: they are held at zero by construction and
    simply excluded from the system, which is why they contribute nothing to
    the right-hand side.
    """
    n_cells = slab.discretization.n_cells
    dx = slab.dx_m
    dt = slab.dt_s
    r = slab.alpha_m2_s * dt / (dx**2)

    x_nodes = np.linspace(0.0, slab.length_m, n_cells + 1)
    interior = x_nodes[1:-1]
    n = interior.size

    main = (1.0 + 2.0 * r) * np.ones(n)
    off = -r * np.ones(max(n - 1, 0))
    matrix = sp.diags(
        [off, main, off], [-1, 0, 1], shape=(n, n), format="csc"
    )
    initial = np.sin(np.pi * interior / slab.length_m)
    return PreparedConductionSystem(
        slab=slab,
        matrix=matrix,
        x_nodes=x_nodes,
        initial_interior=initial,
        r=float(r),
    )


@dataclass
class Conduction1DSolver:
    """1D transient diffusion solver satisfying the ScientificSolver protocol."""

    settings: ConductionValidationSettings = field(
        default_factory=ConductionValidationSettings
    )
    _slabs: dict[str, ConductionSlab] = field(default_factory=dict, repr=False)

    # ---- identity / capability -----------------------------------------
    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend=BACKEND)

    @property
    def capabilities(self):
        return conduction_solver_capabilities()

    @property
    def solver_settings(self) -> SolverSettings:
        return SolverSettings(
            tolerances=self.settings.as_mapping(),
            options={
                "time_integration": "backward_euler",
                "space_discretization": "central_difference_2nd_order",
                "backend": BACKEND,
            },
        )

    # ---- domain-local slab binding ---------------------------------------
    def bind_slab(self, slab: ConductionSlab, problem_id: str) -> None:
        """Associate a slab with the problem describing it.

        Rebinding the same physical slab at a different resolution is allowed —
        that is what a refinement study does. Rebinding *different physics* to
        the same problem id is refused, because two results would then claim
        one identity while describing different systems.
        """
        if not isinstance(slab, ConductionSlab):
            raise ThermalConduction1DError("bind_slab expects a ConductionSlab")
        key = str(problem_id)
        existing = self._slabs.get(key)
        if existing is not None and existing.fingerprint() != slab.fingerprint():
            raise SlabBindingError(
                f"problem {key!r} is already bound to a different slab "
                f"(bound {existing.fingerprint()[:12]}…, incoming "
                f"{slab.fingerprint()[:12]}…); rebinding to different physics "
                f"is refused — use a distinct problem id"
            )
        self._slabs[key] = slab

    def bound_slab(self, problem_id: str) -> ConductionSlab | None:
        return self._slabs.get(str(problem_id))

    # ---- lifecycle -------------------------------------------------------
    def supports(self, problem: ScientificProblem) -> bool:
        """Capability question only — never attempts a solve."""
        if not isinstance(problem, ScientificProblem):
            return False
        declared = {capability.name for capability in self.capabilities}
        if not set(problem.required_capabilities).issubset(declared):
            return False
        domain_models = {model.model_id for model in CONDUCTION_MODELS}
        referenced = {reference.model_id for reference in problem.models}
        if not referenced & domain_models:
            return False
        return THERMAL_CONDUCTION_1D.name in problem.required_capabilities

    def prepare(self, problem: ScientificProblem) -> PreparedSolve:
        slab = self.bound_slab(problem.problem_id)
        if slab is None:
            raise ThermalConduction1DError(
                f"no slab bound for problem {problem.problem_id!r}; call "
                f"bind_slab() first — the universal IR carries no geometry"
            )
        if not self.supports(problem):
            raise ThermalConduction1DError(
                f"problem {problem.problem_id!r} is not a 1D transient "
                f"conduction analysis"
            )
        verify_problem_matches_slab(problem, slab)
        system = assemble(slab)
        d = slab.discretization
        return PreparedSolve(
            problem=problem,
            solver=self.identity,
            settings=self.solver_settings,
            payload=system,
            notes=(
                f"tridiagonal system {system.n_interior}x{system.n_interior} "
                f"({d.n_cells} cells, {d.n_steps} steps, "
                f"dx={slab.dx_m:.6g} m, dt={slab.dt_s:.6g} s, "
                f"Fo={slab.fourier_number:.6g})",
            ),
        )

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        system: PreparedConductionSystem = prepared.payload
        slab = system.slab
        d = slab.discretization
        started = time.perf_counter()

        if system.n_interior == 0:
            return RawSolverOutput(
                convergence=ConvergenceState.FAILED,
                warnings=("slab has no interior unknowns to solve for",),
                wall_seconds=time.perf_counter() - started,
            )

        try:
            factorization = spla.splu(system.matrix)
        except (RuntimeError, ValueError) as exc:
            return RawSolverOutput(
                convergence=ConvergenceState.FAILED,
                warnings=("system matrix could not be factorized",),
                diagnostics={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "n_interior": system.n_interior,
                },
                wall_seconds=time.perf_counter() - started,
            )

        u = system.initial_interior.copy()
        final_residual = float("nan")
        for _ in range(d.n_steps):
            previous = u
            u = factorization.solve(previous)
            if not np.all(np.isfinite(u)):
                return RawSolverOutput(
                    convergence=ConvergenceState.DIVERGED,
                    warnings=("time march produced non-finite values",),
                    diagnostics={
                        "n_interior": system.n_interior,
                        "n_cells": d.n_cells,
                        "n_steps": d.n_steps,
                    },
                    wall_seconds=time.perf_counter() - started,
                )
            # Residual of the step actually taken: ||A u_new - u_old||.
            final_residual = float(
                np.linalg.norm(system.matrix @ u - previous)
            )

        full = np.concatenate(([0.0], u, [0.0]))
        wall = time.perf_counter() - started

        values = {
            MIDPOINT_METRIC: float(full[system.midpoint_index]),
            MAX_METRIC: float(np.max(np.abs(full))),
            LEFT_METRIC: float(full[0]),
            RIGHT_METRIC: float(full[-1]),
        }
        return RawSolverOutput(
            convergence=ConvergenceState.CONVERGED,
            values=values,
            residuals={"final_step_linear_system": final_residual},
            # Back-substitutions performed against one factorization; there is
            # no nonlinear iteration in this scheme and none is implied.
            iterations=d.n_steps,
            wall_seconds=wall,
            diagnostics={
                "n_cells": d.n_cells,
                "n_steps": d.n_steps,
                "n_interior": system.n_interior,
                "dx_m": slab.dx_m,
                "dt_s": slab.dt_s,
                "fourier_number": slab.fourier_number,
                "work_proxy": d.work_proxy,
                "r_coefficient": system.r,
                "factorization": "scipy.sparse.linalg.splu (reused each step)",
                "initial_max_abs": float(np.max(np.abs(system.initial_interior))),
                "field": [float(v) for v in full],
            },
        )

    def extract_metrics(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> dict[str, Quantity]:
        """Restore units. The field is DIMENSIONLESS, never kelvin."""
        if not raw.succeeded:
            return {}
        return {
            name: Quantity(value, FIELD_UNIT) for name, value in raw.values.items()
        }

    def validate(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationReport:
        system: PreparedConductionSystem = prepared.payload
        return build_validation_report(system, raw, self.settings)


# =====================================================================
# Public wrapper
# =====================================================================

def solve_slab(
    slab: ConductionSlab,
    *,
    run_id: str,
    solver: Conduction1DSolver | None = None,
    problem: ScientificProblem | None = None,
    software_version: str = "engcore.domains.thermal.conduction1d/0.1.0",
    git_commit: str | None = None,
    timestamp: str | None = None,
    environment: Mapping[str, str] | None = None,
    parent_run_id: str | None = None,
) -> ScientificResult:
    """Run the full contract lifecycle for one slab and return a result.

    Orchestration only: every stage goes through the protocol.

    **Diagnostics survive.** E1 recorded that the Electrical wrapper discards
    ``RawSolverOutput``, so residual norm and wall-seconds never reached the
    result and an experiment had to re-derive them with a second solve. Here
    the numerical diagnostics are carried into ``ScientificResult.metadata``
    on the existing result surface — no second result structure, no re-run.
    The field array is deliberately excluded: it is large, it is not a
    diagnostic, and the metrics already carry every value a caller needs.
    """
    from .problem import build_conduction_problem

    solver = solver or Conduction1DSolver()
    problem = problem or build_conduction_problem(slab)
    verify_problem_matches_slab(problem, slab)
    solver.bind_slab(slab, problem.problem_id)

    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    report = solver.validate(prepared, raw)

    model_identities = tuple((m.model_id, m.version) for m in CONDUCTION_MODELS)
    assumptions = CONDUCTION_MODELS[0].assumptions

    inputs = {
        "alpha": slab.diffusivity,
        "length": slab.length,
        "end_time": slab.end_time,
    }

    diagnostics = {
        key: value
        for key, value in raw.diagnostics.items()
        if key != "field"
    }
    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version=software_version,
        git_commit=git_commit,
        models=model_identities,
        solvers=((SOLVER_ID, SOLVER_VERSION),),
        inputs=inputs,
        assumptions=assumptions,
        tolerances=solver.settings.as_mapping(),
        environment=dict(environment or {}),
        timestamp=timestamp,
        parent_run_id=parent_run_id,
        metadata={
            "slab_id": slab.slab_id,
            "slab_fingerprint": slab.fingerprint(),
            "time_integration": "backward_euler",
            "space_discretization": "central_difference_2nd_order",
            "backend": BACKEND,
            "slab_canonical": slab.to_dict(),
        },
    )

    return ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        models=model_identities,
        solver=solver.identity,
        convergence=raw.convergence,
        validation=report,
        # No uncertainty quantification is performed here. The discretization
        # error is real and is quantified by the refinement gate, not by this
        # single solve, so claiming anything but UNKNOWN would be fabrication.
        uncertainty={
            name: Uncertainty.unknown(
                "no uncertainty quantification performed; discretization error "
                "is established by the refinement gate, not by one solve"
            )
            for name in metrics
        },
        assumptions=assumptions,
        warnings=raw.warnings,
        provenance=provenance,
        metadata={
            "slab_id": slab.slab_id,
            "slab_fingerprint": slab.fingerprint(),
            # Numerical diagnostics on the existing result surface.
            "numerics": diagnostics,
            "residuals": dict(raw.residuals),
            "iterations": raw.iterations,
            # Telemetry only. Never a scientific score in this milestone.
            "wall_seconds_telemetry": raw.wall_seconds,
        },
    )
