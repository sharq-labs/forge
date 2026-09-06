"""Two computational realizations of ONE scientific model.

MODEL0-R DIFFERENTIAL PROOF. This module exists to answer one question with
executed evidence: does :class:`ModelRealizationDefinition` carry information
that has no correct home on the model, on the solver, or in runtime settings?

The model
---------
Exactly one: ``thermal.conduction1d.linear_diffusion`` v0.1.0, the frozen
``DIFFUSION_MODEL``. No second model is created, and none is edited. The
physics, assumptions, validity domain and units are the frozen model's.

The two realizations
--------------------
Both pose the same PDE and both discretize space the same way. They differ in
the *time* discretization, and that difference is a theorem rather than a
label:

``R1`` backward Euler   ``(I - rT) u_new = u_old``   unconditionally stable
``R2`` forward Euler    ``u_new = (I + rT) u_old``   stable iff ``r <= 1/2``

with ``r = alpha dt / dx^2``. The bound on ``R2`` follows from von Neumann
analysis of the FTCS scheme: the amplification factor of the mode with
wavenumber ``k`` is ``1 - 4 r sin^2(k dx / 2)``, whose magnitude exceeds one
for the highest representable mode as soon as ``r > 1/2``. Every correct
implementation of the scheme has this bound and no implementation can remove
it. That is why it is a property of the *realization* and not of any
particular solver.

``formulation`` is deliberately ``PDE`` on both. If the enum were carrying the
distinction, the proof would be about the enum rather than about the record.

Why this lives outside ``domains/thermal/``
-------------------------------------------
That tree is byte-pinned by three frozen experiments (T1/T2/T3), which assert
both a digest map and set-equality over its ``*.py`` files. Editing it or
adding to it would spend evidence this milestone has no authority to spend, so
the new path is a module beside it that drives the frozen public API only —
the same shape ``conduction1d_bulk.py`` uses.

What this module is not
-----------------------
Not a planner. :func:`admissible_realizations` is a deterministic filter over
declared facts that records its reasons; it does not rank, score or choose.
Not a generic scheme framework, not an equation IR, not a discretization IR.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import numpy as np
import scipy.linalg as sla
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ...scientific.capabilities import ScientificCapability
from ...scientific.ir.fingerprints import require_matching_fingerprint
from ...scientific.ir.problem import ModelReference, ScientificProblem
from ...scientific.models.definition import (
    RangeCondition,
    ValidityAssessment,
    ValidityDomain,
    ValidityStatus,
)
from ...scientific.realizations.definition import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
)
from ...scientific.realizations.registry import RealizationRegistry
from ...scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from ...scientific.results.result import ScientificResult
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from ...scientific.solvers.capability import (
    CoreCapabilities,
    SolverCapability,
    SolverCapabilityId,
)
from ...scientific.solvers.protocol import (
    DeclaredSupport,
    ConvergenceState,
    PreparedSolve,
    RawSolverOutput,
    SolverIdentity,
    SolverSettings,
)
from ...scientific.units.quantity import Quantity
from ..thermal.conduction1d.errors import SlabConfigurationError
from ..thermal.conduction1d.problem import (
    DIFFUSION_MODEL,
    FIELD_UNIT,
    LEFT_METRIC,
    MAX_METRIC,
    MIDPOINT_METRIC,
    RIGHT_METRIC,
    THERMAL_CONDUCTION_1D,
    ConductionSlab,
    build_conduction_problem,
    verify_problem_matches_slab,
)

__all__ = [
    "CONDUCTION_1D_TRANSIENT",
    "CORE_LINEAR_SOLVE",
    "EXPLICIT_REALIZATION",
    "IMPLICIT_REALIZATION",
    "SchemeSolver",
    "banded_scheme_solver",
    "sparse_scheme_solver",
    "conduction_realizations",
    "admissible_realizations",
    "fourier_number_of",
    "solve_with_realization",
]


# =====================================================================
# Capabilities
# =====================================================================

#: What science these realizations claim to provide. Declared here, in the
#: domain, exactly as the core intends: no capability is defined in the core.
CONDUCTION_1D_TRANSIENT = ScientificCapability.parse(
    "thermal:transient_conduction_1d"
)

#: The computational operation an implicit scheme needs a backend to perform.
#: This is a *solver* capability — a statement about software — and it is what
#: separates the two realizations' requirements. The explicit scheme needs no
#: linear solve at all; its update is a matrix-vector product.
#:
#: It is the **core-owned** capability, not a new name. Capability identity is
#: exact string equality with no registry, so minting ``core:linear_solve``
#: beside the existing ``core:linear_system`` would have created two names for
#: one operation, and a realization requiring one would silently miss a solver
#: providing the other.
CORE_LINEAR_SOLVE = CoreCapabilities.LINEAR_SYSTEM


# =====================================================================
# The two realization records
# =====================================================================

_MODEL = ModelReference(DIFFUSION_MODEL.model_id, DIFFUSION_MODEL.version)

#: Stability threshold of the FTCS scheme. Not a tunable: it is the value at
#: which the amplification factor of the highest representable mode reaches
#: magnitude one.
FTCS_STABILITY_LIMIT = 0.5

IMPLICIT_REALIZATION = ModelRealizationDefinition(
    realization_id="thermal.conduction1d.implicit_backward_euler",
    version="0.1.0",
    model=_MODEL,
    formulation=ModelFormulation.PDE,
    name="Backward Euler in time, 2nd-order central in space",
    description=(
        "Implicit time integration of the 1D diffusion equation. Each step "
        "solves (I - r T) u_new = u_old for the interior nodes."
    ),
    provided_capabilities=frozenset({CONDUCTION_1D_TRANSIENT}),
    required_solver_capabilities=frozenset(
        {
            SolverCapabilityId.coerce(THERMAL_CONDUCTION_1D),
            SolverCapabilityId.coerce(CORE_LINEAR_SOLVE),
        }
    ),
    assumptions=(
        "backward Euler in time; first-order accurate in dt",
        "second-order central differences in space",
        "unconditionally stable: no restriction on alpha dt / dx^2",
        "a square linear system is solved once per step",
    ),
    implementation=ImplementationReference(
        implementation_id="engcore.domains.thermal_models.conduction1d_schemes",
        version="0.1.0",
        reference="backward Euler; see module docstring",
    ),
)

EXPLICIT_REALIZATION = ModelRealizationDefinition(
    realization_id="thermal.conduction1d.explicit_forward_euler",
    version="0.1.0",
    model=_MODEL,
    formulation=ModelFormulation.PDE,
    name="Forward Euler in time (FTCS), 2nd-order central in space",
    description=(
        "Explicit time integration of the 1D diffusion equation. Each step "
        "is the matrix-vector product u_new = (I + r T) u_old; no linear "
        "system is solved."
    ),
    provided_capabilities=frozenset({CONDUCTION_1D_TRANSIENT}),
    required_solver_capabilities=frozenset(
        {SolverCapabilityId.coerce(THERMAL_CONDUCTION_1D)}
    ),
    assumptions=(
        "forward Euler in time; first-order accurate in dt",
        "second-order central differences in space",
        "conditionally stable: requires alpha dt / dx^2 <= 1/2",
        "no linear system is solved; each step is a matrix-vector product",
    ),
    implementation=ImplementationReference(
        implementation_id="engcore.domains.thermal_models.conduction1d_schemes",
        version="0.1.0",
        reference="FTCS; see module docstring",
    ),
)


def _require_slab_fingerprint(problem, slab) -> None:
    """The strict pairing check, in front of the permissive frozen one.

    ``conduction1d.verify_problem_matches_slab`` compares
    ``if declared and declared != actual``, so a problem carrying no
    ``slab_fingerprint`` at all passes it. That function lives in a byte-pinned
    file (``experiments/thermal_t1/t1_config.py`` digests it) and this round may
    not edit it -- but this module is not frozen, and the paths through *here*
    can be closed. See ``NEEDS.md`` G6.1 for what closing the frozen path costs.

    Called before the frozen verifier rather than instead of it: that one also
    checks things this does not, and running both means this module's behaviour
    is the frozen check plus a refusal of absence, rather than a reimplementation
    that could drift from it.
    """
    require_matching_fingerprint(
        problem=problem,
        key="slab_fingerprint",
        actual=slab.fingerprint(),
        error=SlabConfigurationError,
        subject="slab",
    )
    verify_problem_matches_slab(problem, slab)


def conduction_realizations() -> RealizationRegistry:
    """A fresh registry holding both realizations. No global singleton."""
    return RealizationRegistry((IMPLICIT_REALIZATION, EXPLICIT_REALIZATION))


# =====================================================================
# Admissibility — the part the record cannot currently express
# =====================================================================

def fourier_number_of(slab: ConductionSlab) -> float:
    """``alpha dt / dx^2`` for a slab. Read from the frozen declaration."""
    return float(slab.fourier_number)


#: MODEL0-R FINDING, recorded in code because it is the milestone's result.
#:
#: This table is a **side-table keyed by realization identity**. It exists
#: because ``ModelRealizationDefinition`` has no typed applicability envelope:
#: the stability bound is expressible on the record only as free text in
#: ``assumptions``, which a selector cannot evaluate without parsing prose.
#:
#: The envelope itself is built from ``ValidityDomain`` / ``RangeCondition``,
#: which already exist in the core and already carry exactly these semantics
#: at the model layer. Nothing new was invented; the type is simply not
#: reachable from a realization record, so the domain has to hold it beside
#: the record instead of on it. See ``docs/milestones/model0r-differential-evidence.md``.
_APPLICABILITY: dict[tuple[str, str], ValidityDomain] = {
    IMPLICIT_REALIZATION.key: ValidityDomain(
        description=(
            "Backward Euler is A-stable; no restriction on the Fourier number."
        ),
    ),
    EXPLICIT_REALIZATION.key: ValidityDomain(
        conditions=(
            RangeCondition(
                name="fourier_number",
                maximum=Quantity(FTCS_STABILITY_LIMIT, "dimensionless"),
                maximum_inclusive=True,
                description=(
                    "von Neumann stability of FTCS: the amplification factor "
                    "of the highest representable mode is 1 - 4r, so |g| > 1 "
                    "once r exceeds 1/2 and round-off content is amplified "
                    "every step."
                ),
            ),
        ),
        description="Conditionally stable explicit scheme.",
    ),
}


def realization_applicability(
    realization: ModelRealizationDefinition,
) -> ValidityDomain:
    """The realization's own applicability envelope.

    Looked up by realization identity because the record cannot carry it.
    An unregistered realization gets an empty domain, which
    :meth:`ValidityDomain.assess` reports as ``UNKNOWN`` rather than valid —
    absence of declared limits is not evidence of unlimited applicability.
    """
    return _APPLICABILITY.get(realization.key, ValidityDomain())


def assess_realization(
    realization: ModelRealizationDefinition, slab: ConductionSlab
) -> ValidityAssessment:
    """Is this realization applicable to this discretization? No execution."""
    return realization_applicability(realization).assess(
        {"fourier_number": Quantity(fourier_number_of(slab), "dimensionless")}
    )


def admissible_realizations(
    slab: ConductionSlab,
    *,
    registry: RealizationRegistry | None = None,
    available_solver_capabilities: Iterable[
        SolverCapabilityId | SolverCapability | str
    ] = (),
) -> tuple[
    tuple[ModelRealizationDefinition, ValidityAssessment, frozenset], ...
]:
    """Every realization of the model, with its verdict and its reasons.

    Returns each realization paired with its applicability assessment and its
    solver-capability gap. It **selects nothing**: a caller sees every
    candidate and every reason, in registry order, and decides. Ranking a
    cheap realization above an accurate one is a scientific judgement this
    function has no basis for making.
    """
    registry = registry if registry is not None else conduction_realizations()
    available = tuple(available_solver_capabilities)
    return tuple(
        (
            realization,
            assess_realization(realization, slab),
            realization.solver_capability_gap(available),
        )
        for realization in registry.for_model(
            DIFFUSION_MODEL.model_id, DIFFUSION_MODEL.version
        )
    )


# =====================================================================
# One solver, two schemes, two linear-algebra backends
# =====================================================================

@dataclass(frozen=True)
class PreparedScheme:
    """Grid, operator and the scheme this solve will run."""

    slab: ConductionSlab
    realization: ModelRealizationDefinition
    x_nodes: np.ndarray
    initial_interior: np.ndarray
    r: float

    @property
    def n_interior(self) -> int:
        return int(self.initial_interior.size)

    @property
    def midpoint_index(self) -> int:
        return self.slab.discretization.n_cells // 2

    @property
    def is_implicit(self) -> bool:
        return self.realization.key == IMPLICIT_REALIZATION.key


def _grid(slab: ConductionSlab) -> tuple[np.ndarray, np.ndarray, float]:
    n_cells = slab.discretization.n_cells
    x_nodes = np.linspace(0.0, slab.length_m, n_cells + 1)
    interior = x_nodes[1:-1]
    r = slab.alpha_m2_s * slab.dt_s / (slab.dx_m**2)
    initial = np.sin(np.pi * interior / slab.length_m)
    return x_nodes, initial, float(r)


class _Backend:
    """A linear-algebra strategy. Two exist; both must agree."""

    name: str

    def implicit_stepper(self, n: int, r: float):
        raise NotImplementedError

    def explicit_stepper(self, n: int, r: float):
        raise NotImplementedError


class _SparseBackend(_Backend):
    """SciPy sparse: LU factorization reused across steps."""

    name = "scipy.sparse.linalg.splu"

    @staticmethod
    def _operator(n: int, r: float, sign: float):
        main = (1.0 + sign * 2.0 * r) * np.ones(n)
        off = -sign * r * np.ones(max(n - 1, 0))
        return sp.diags([off, main, off], [-1, 0, 1], shape=(n, n), format="csc")

    def implicit_stepper(self, n: int, r: float):
        factorization = spla.splu(self._operator(n, r, 1.0))
        return factorization.solve

    def explicit_stepper(self, n: int, r: float):
        operator = self._operator(n, r, -1.0)
        return lambda u: operator @ u


class _BandedBackend(_Backend):
    """SciPy dense-banded: a different factorization path, same scheme."""

    name = "scipy.linalg.solve_banded"

    def implicit_stepper(self, n: int, r: float):
        ab = np.zeros((3, n))
        ab[0, 1:] = -r
        ab[1, :] = 1.0 + 2.0 * r
        ab[2, :-1] = -r
        return lambda u: sla.solve_banded((1, 1), ab, u)

    def explicit_stepper(self, n: int, r: float):
        def step(u: np.ndarray) -> np.ndarray:
            out = (1.0 - 2.0 * r) * u
            out[:-1] += r * u[1:]
            out[1:] += r * u[:-1]
            return out

        return step


@dataclass
class SchemeSolver(DeclaredSupport):
    """A ``ScientificSolver`` that executes whichever scheme it is handed.

    The scheme is **not** a property of this solver. It arrives on the
    ``ModelRealizationDefinition`` bound to the problem, which is the whole
    point: one solver identity covers both realizations, so solver identity
    cannot be what distinguishes them.
    """

    backend: _Backend = field(default_factory=_SparseBackend)
    solver_id: str = "thermal.conduction1d.scheme_solver"
    version: str = "0.1.0"
    _bound: dict[str, tuple[ConductionSlab, ModelRealizationDefinition]] = field(
        default_factory=dict, repr=False
    )

    # ---- identity / capability -----------------------------------------
    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity(self.solver_id, self.version, backend=self.backend.name)

    @property
    def capabilities(self) -> frozenset[SolverCapability]:
        return frozenset({THERMAL_CONDUCTION_1D, CORE_LINEAR_SOLVE})

    @property
    def solver_settings(self) -> SolverSettings:
        return SolverSettings(
            tolerances={"boundary_atol": 1e-14},
            options={"backend": self.backend.name},
        )

    # ---- binding ---------------------------------------------------------
    def bind(
        self,
        problem_id: str,
        slab: ConductionSlab,
        realization: ModelRealizationDefinition,
    ) -> None:
        """Bind the geometry *and the realization* to a problem id.

        The universal IR carries neither. The realization is bound rather than
        configured because it is a scientific choice about how to compute the
        claim, not a numerical setting of this backend.
        """
        if realization.model_key != _MODEL.key:
            raise ValueError(
                f"realization {realization.realization_id!r} implements "
                f"{realization.model_key}, not {_MODEL.key}"
            )
        key = str(problem_id)
        existing = self._bound.get(key)
        if existing is not None and existing[0].fingerprint() != slab.fingerprint():
            # Same discipline as the frozen ``bind_slab``, and the same
            # scope: what may not change under one problem id is the
            # *physics*. Rebinding a different **realization** is explicitly
            # allowed — one problem computed two ways is the whole point, and
            # which one ran is read back from the prepared solve rather than
            # from this binding.
            raise ValueError(
                f"problem {key!r} is already bound to slab "
                f"{existing[0].fingerprint()[:12]}…; rebinding to different "
                f"physics is refused — use a distinct problem id"
            )
        self._bound[key] = (slab, realization)

    # ---- lifecycle -------------------------------------------------------
    #: What this solver is for, and what it implements. The core compares.
    #:
    #: ``serves_capabilities`` is this domain's transient conduction capability
    #: rather than nothing: the subset test alone answers True for a problem
    #: that requires no capability at all, because the empty set is a subset of
    #: everything, and this adapter used to inherit that hole from writing the
    #: comparison by hand.
    serves_capabilities = frozenset({THERMAL_CONDUCTION_1D.name})
    served_models = (DIFFUSION_MODEL,)

    def prepare(self, problem: ScientificProblem) -> PreparedSolve:
        bound = self._bound.get(problem.problem_id)
        if bound is None:
            raise ValueError(
                f"nothing bound for problem {problem.problem_id!r}; call "
                f"bind() with a slab and a realization first"
            )
        slab, realization = bound
        if not self.supports(problem):
            raise ValueError(
                f"problem {problem.problem_id!r} is not 1D transient conduction"
            )
        _require_slab_fingerprint(problem, slab)
        x_nodes, initial, r = _grid(slab)
        return PreparedSolve(
            problem=problem,
            solver=self.identity,
            settings=self.solver_settings,
            payload=PreparedScheme(
                slab=slab,
                realization=realization,
                x_nodes=x_nodes,
                initial_interior=initial,
                r=r,
            ),
            notes=(
                f"{realization.realization_id}@{realization.version} on "
                f"{slab.discretization.n_cells} cells x "
                f"{slab.discretization.n_steps} steps, r={r:.6g}",
            ),
        )

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        system: PreparedScheme = prepared.payload
        d = system.slab.discretization
        started = time.perf_counter()
        n = system.n_interior
        if n == 0:
            return RawSolverOutput(
                convergence=ConvergenceState.FAILED,
                warnings=("slab has no interior unknowns to solve for",),
                wall_seconds=time.perf_counter() - started,
            )

        step = (
            self.backend.implicit_stepper(n, system.r)
            if system.is_implicit
            else self.backend.explicit_stepper(n, system.r)
        )

        u = system.initial_interior.copy()
        for _ in range(d.n_steps):
            u = np.asarray(step(u), dtype=np.float64)
            if not np.all(np.isfinite(u)):
                # An explicit scheme run past its stability bound reaches this.
                # DIVERGED, not FAILED: the machinery worked and the scheme
                # was inapplicable, and those are different statements.
                return RawSolverOutput(
                    convergence=ConvergenceState.DIVERGED,
                    warnings=("time march produced non-finite values",),
                    diagnostics={
                        "n_cells": d.n_cells,
                        "n_steps": d.n_steps,
                        "fourier_number": system.r,
                        "realization_id": system.realization.realization_id,
                    },
                    wall_seconds=time.perf_counter() - started,
                )

        full = np.concatenate(([0.0], u, [0.0]))
        return RawSolverOutput(
            convergence=ConvergenceState.CONVERGED,
            values={
                MIDPOINT_METRIC: float(full[system.midpoint_index]),
                MAX_METRIC: float(np.max(np.abs(full))),
                LEFT_METRIC: float(full[0]),
                RIGHT_METRIC: float(full[-1]),
            },
            iterations=d.n_steps,
            wall_seconds=time.perf_counter() - started,
            diagnostics={
                "n_cells": d.n_cells,
                "n_steps": d.n_steps,
                "n_interior": n,
                "dx_m": system.slab.dx_m,
                "dt_s": system.slab.dt_s,
                "fourier_number": system.r,
                "field": [float(v) for v in full],
            },
        )

    def extract_metrics(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> dict[str, Quantity]:
        """Restore units. The field is DIMENSIONLESS, never kelvin."""
        if not raw.succeeded:
            return {}
        return {name: Quantity(v, FIELD_UNIT) for name, v in raw.values.items()}

    def validate(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationReport:
        """Checks that do not know which scheme ran.

        The maximum-principle check is the one that matters here: diffusion
        cannot amplify, so ``max|u|`` may never exceed the initial amplitude
        of 1. It is a property of the *equation*, so it can catch a scheme
        used outside its stability envelope without being told about schemes.
        """
        system: PreparedScheme = prepared.payload
        checks: list[ValidationCheck] = []

        if not raw.succeeded:
            checks.append(
                ValidationCheck(
                    name="time_march_finite",
                    outcome=ValidationOutcome.FAIL,
                    detail="the time march did not produce a finite field",
                )
            )
            return ValidationReport(checks=tuple(checks))

        max_abs = float(raw.values[MAX_METRIC])
        checks.append(
            ValidationCheck(
                name="field_finite",
                outcome=(
                    ValidationOutcome.PASS
                    if math.isfinite(max_abs)
                    else ValidationOutcome.FAIL
                ),
                detail=f"max|u| = {max_abs:.6g}",
            )
        )
        checks.append(
            ValidationCheck(
                name="amplitude_decay",
                outcome=(
                    ValidationOutcome.PASS
                    if max_abs <= 1.0 + 1e-9
                    else ValidationOutcome.FAIL
                ),
                detail=(
                    f"discrete maximum principle: max|u| = {max_abs:.6g} "
                    f"against an initial amplitude of 1"
                ),
                residual=max_abs,
                tolerance=1.0,
            )
        )
        boundary = max(
            abs(float(raw.values[LEFT_METRIC])),
            abs(float(raw.values[RIGHT_METRIC])),
        )
        checks.append(
            ValidationCheck(
                name="boundary_conditions_held",
                outcome=(
                    ValidationOutcome.PASS
                    if boundary <= 1e-14
                    else ValidationOutcome.FAIL
                ),
                residual=boundary,
                tolerance=1e-14,
            )
        )
        # An unconditional PASS carrying DIMENSIONALLY_VALID and a sentence
        # about what the units were. Nothing was compared: the sentence was
        # true, and it was still a claimed level. It compares now, against the
        # unit each `ModelOutputSpec` on the model record declares -- a
        # reference outside the arithmetic, which is what makes the level
        # earned. The values themselves are checked by the three checks above.
        declared = {
            spec.metric: spec.unit_exemplar
            for spec in DIFFUSION_MODEL.outputs
        }
        produced = self.extract_metrics(prepared, raw)
        mismatched = sorted(
            f"{name} is {value.units!r}, {declared[name.split(':', 1)[0]]!r} "
            f"declared"
            for name, value in produced.items()
            if name.split(":", 1)[0] in declared
            and not value.is_compatible_with(declared[name.split(":", 1)[0]])
        )
        unchecked = sorted(
            name
            for name in produced
            if name.split(":", 1)[0] not in declared
        )
        compared = len(produced) - len(unchecked)
        checks.append(
            ValidationCheck(
                name="dimensional_consistency",
                outcome=(
                    ValidationOutcome.PASS
                    if compared and not mismatched
                    else ValidationOutcome.FAIL
                    if mismatched
                    else ValidationOutcome.NOT_RUN
                ),
                detail=(
                    f"{compared} produced metric(s) checked against the "
                    f"dimensions {DIFFUSION_MODEL.model_id} declares"
                    + (f"; mismatched: {mismatched}" if mismatched else "")
                    + (
                        f"; not a declared model output and not checked: "
                        f"{unchecked}"
                        if unchecked
                        else ""
                    )
                ),
                establishes=(
                    ValidationLevel.DIMENSIONALLY_VALID
                    if compared and not mismatched
                    else None
                ),
                evidence=tuple(
                    f"{DIFFUSION_MODEL.model_id}@"
                    f"{DIFFUSION_MODEL.version}:{metric}={unit}"
                    for metric, unit in sorted(declared.items())
                ),
            )
        )
        checks.append(
            ValidationCheck(
                name="discretization_convergence",
                outcome=ValidationOutcome.NOT_RUN,
                detail=(
                    "convergence under refinement is a claim about a sequence "
                    "of solves and cannot be established by one"
                ),
            )
        )
        return ValidationReport(
            checks=tuple(checks),
            notes=(
                f"r = {system.r:.6g}; scheme applicability is assessed before "
                f"execution, not here"
            ),
        )


# =====================================================================
# The null hypothesis, built rather than argued (prereg 5)
# =====================================================================

@dataclass
class ReducedSchemeSolver(SchemeSolver):
    """The realization-free steel-man of H0. Deliberately kept working.

    Identical numerics to :class:`SchemeSolver`, with one difference: the
    scheme arrives as a **string in** ``SolverSettings.options`` instead of as
    a typed realization record. This is exactly how the frozen production
    solver already advertises its scheme
    (``options={"time_integration": "backward_euler", ...}``), so the null
    hypothesis is given the strongest form the repository actually supports.

    It exists to be measured, not to be dismissed, and it is used by the
    reduction test to decide the preregistered stopping condition. If it
    turned out to lose nothing, MODEL0-R's realization boundary would be
    reported as weakened.
    """

    time_integration: str = "backward_euler"
    solver_id: str = "thermal.conduction1d.reduced_scheme_solver"

    @property
    def solver_settings(self) -> SolverSettings:
        return SolverSettings(
            tolerances={"boundary_atol": 1e-14},
            options={
                "backend": self.backend.name,
                "time_integration": self.time_integration,
                "space_discretization": "central_difference_2nd_order",
            },
        )

    def bind_reduced(self, problem_id: str, slab: ConductionSlab) -> None:
        """Bind geometry only. There is no realization in this world."""
        realization = (
            IMPLICIT_REALIZATION
            if self.time_integration == "backward_euler"
            else EXPLICIT_REALIZATION
        )
        # The mapping above is the magic-string branch the reduction needs in
        # order to run at all. It is the thing being measured.
        self._bound[str(problem_id)] = (slab, realization)


def sparse_scheme_solver() -> SchemeSolver:
    """Scheme solver over SciPy sparse LU."""
    return SchemeSolver(backend=_SparseBackend())


def banded_scheme_solver() -> SchemeSolver:
    """Scheme solver over SciPy dense-banded factorization.

    A materially different linear-algebra path for the same scheme. Used to
    show that swapping it changes ``SolverIdentity`` and changes nothing about
    the realization's scientific identity.
    """
    return SchemeSolver(
        backend=_BandedBackend(),
        solver_id="thermal.conduction1d.scheme_solver_banded",
    )


# =====================================================================
# Orchestration
# =====================================================================

def solve_with_realization(
    slab: ConductionSlab,
    realization: ModelRealizationDefinition,
    *,
    run_id: str,
    solver: SchemeSolver | None = None,
    problem: ScientificProblem | None = None,
    software_version: str = "engcore.domains.thermal_models.conduction1d_schemes/0.1.0",
    require_admissible: bool = False,
) -> ScientificResult:
    """Run one realization of the model and return a scientific result.

    ``require_admissible`` refuses to execute a realization outside its
    applicability envelope. It defaults to ``False`` **on purpose**: this
    milestone has to be able to run the inadmissible case and observe what
    actually happens, rather than assert the bound and never test it.
    """
    solver = solver or sparse_scheme_solver()
    problem = problem or build_conduction_problem(slab)
    _require_slab_fingerprint(problem, slab)

    if require_admissible:
        assessment = assess_realization(realization, slab)
        if assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
            raise ValueError(
                f"realization {realization.realization_id!r} is outside its "
                f"applicability envelope for this discretization "
                f"(r = {fourier_number_of(slab):.6g}): "
                f"{', '.join(assessment.violated)}"
            )

    solver.bind(problem.problem_id, slab, realization)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    report = solver.validate(prepared, raw)

    # Read back what actually executed rather than trusting this function's
    # own argument. Provenance must attribute the computation that ran.
    executed: ModelRealizationDefinition = prepared.payload.realization

    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version=software_version,
        # One binding, stating the whole relation structurally: this model,
        # computed by this realization, executed by this solver. The
        # participant sets are derived from it.
        bindings=(
            ExecutionBinding(
                model=_MODEL,
                realization=executed.reference(),
                solver=solver.identity,
            ),
        ),
        inputs={
            "alpha": slab.diffusivity,
            "length": slab.length,
            "end_time": slab.end_time,
        },
        # The MODEL's assumptions and the REALIZATION's assumptions are
        # different claims and are kept apart: the first is about the physics,
        # the second about the scheme that computed it.
        assumptions=DIFFUSION_MODEL.assumptions + executed.assumptions,
        tolerances=dict(solver.solver_settings.tolerances),
        metadata={
            "slab_id": slab.slab_id,
            "slab_fingerprint": slab.fingerprint(),
            "fourier_number": slab.fourier_number,
        },
    )

    return ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        models=((DIFFUSION_MODEL.model_id, DIFFUSION_MODEL.version),),
        solver=solver.identity,
        convergence=raw.convergence,
        validation=report,
        uncertainty={
            name: Uncertainty.unknown(
                "no uncertainty quantification performed; discretization "
                "error is established by refinement, not by one solve"
            )
            for name in metrics
        },
        assumptions=DIFFUSION_MODEL.assumptions + executed.assumptions,
        warnings=raw.warnings,
        provenance=provenance,
        metadata={
            "slab_id": slab.slab_id,
            "fourier_number": slab.fourier_number,
            "numerics": {
                k: v for k, v in raw.diagnostics.items() if k != "field"
            },
        },
    )


def raw_field(raw: RawSolverOutput) -> np.ndarray:
    """The solved field from a raw output, for in-process consumers only."""
    return np.asarray(raw.diagnostics["field"], dtype=np.float64)
