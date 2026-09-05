"""Two verification concepts, kept apart on purpose.

PER-SOLVE VALIDATION establishes what one run can establish: the linear system
was solved, the field is finite, the boundaries held, the amplitude decayed,
the metrics carry units. That is the whole list. It awards
``DIMENSIONALLY_VALID`` and nothing stronger.

It specifically does NOT award ``NUMERICALLY_CONVERGED``. The linear residual
of a direct sparse factorization sits at round-off in every run, coarse or
fine, so treating it as convergence would certify the 8-cell solve exactly as
confidently as the 512-cell one. Discretization accuracy is invisible to a
single solve — the run has nothing to compare itself against — and the honest
record of that is an explicit NOT_RUN check rather than silence.

THE REFINEMENT GATE establishes the two claims that need a *sequence*:

    NUMERICALLY_CONVERGED   successive QoI differences contract across a
                            declared ladder, and analytic errors fall
                            monotonically
    ANALYTICALLY_VERIFIED   the finest rung agrees with the independent
                            closed form inside a declared tolerance

PROVENANCE OF THE THRESHOLDS — READ THIS BEFORE QUOTING THEM
-------------------------------------------------------------
``CONVERGENCE_MIN_CONTRACTION`` and ``ANALYTIC_REL_TOL`` are a **declared
verification gate set after exploratory feasibility analysis**. They are NOT
preregistered, and calling them so would overstate what they are.

An exploratory calculation on this benchmark had already observed a finest
analytic error near 4e-4 and successive contractions near 2.0-2.3 before these
values were written down. The thresholds were then chosen — 1e-3 and 1.5 —
comfortably outside those observations rather than tightly around them, and
they were fixed before any scored test ran. But the numbers were informed by
having seen roughly where the method lands, and a reader deciding how much
weight the gate carries needs to know that.

What that costs, stated plainly: passing this gate on the benchmark it was
declared for is weaker evidence than passing a genuinely preregistered gate
would be. The remedy is a predeclared confirmatory stress case the thresholds
were not chosen from, and the strength of the claim rests on that rather than
on the original run.

That stress case is verification methodology, not a runtime capability, so it
lives under ``tests/domains/thermal/holdout_declaration.py`` and this package
has no dependency on it. It raises the diffusivity by 50%, which is the
direction that stresses a fixed ladder, and it clears these same untouched
thresholds. Nothing in it is independent physical validation: it is the same
computational benchmark at a different parameter.

The second requires the first. A result that happened to land near the
reference without a convergent sequence behind it has not been verified; it
has been lucky, and the gate refuses to call that verification.

WHAT THE COUPLED LADDER CAN AND CANNOT SAY
------------------------------------------
The ladder refines cells and steps together. Backward Euler is first order in
time and the central difference is second order in space, so a coupled
refinement measures their combination and nothing finer. The permitted claim is
that the sequence converges toward the analytic solution with behaviour
consistent with first-order temporal error dominating. Separating the two
orders would need a spatial-only and a temporal-only sweep, which this
milestone does not perform, so no independent spatial order is claimed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import numpy as np

from ....scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from .errors import SlabConfigurationError
from .reference import REFERENCE_EXPRESSION, REFERENCE_ID, exact_midpoint

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .problem import ConductionSlab
    from .solver import PreparedConductionSystem


# =====================================================================
# Per-solve settings and report
# =====================================================================

@dataclass(frozen=True)
class ConductionValidationSettings:
    """Tolerances for the checks a single solve can actually make."""

    #: ||A u_new - u_old|| for the final step. Direct factorization, so this
    #: is a round-off-scale check that the solve is self-consistent.
    residual_atol: float = 1.0e-10
    #: Dirichlet ends are excluded from the unknowns, so they should be
    #: identically zero; the tolerance guards against assembly corruption.
    boundary_atol: float = 1.0e-14

    def as_mapping(self) -> dict[str, float]:
        return {
            "residual_atol": float(self.residual_atol),
            "boundary_atol": float(self.boundary_atol),
        }


def build_validation_report(
    system: "PreparedConductionSystem",
    raw,
    settings: ConductionValidationSettings,
) -> ValidationReport:
    """Checks one solve can support, and an explicit note about what it cannot."""
    if not raw.succeeded:
        return ValidationReport(
            checks=(
                ValidationCheck(
                    name="linear_system_residual",
                    outcome=ValidationOutcome.FAIL,
                    detail="; ".join(raw.warnings) or "solve did not succeed",
                ),
            ),
            notes="no solution to validate",
        )

    checks: list[ValidationCheck] = []
    field_values = np.asarray(raw.diagnostics["field"], dtype=np.float64)

    residual = float(raw.residuals.get("final_step_linear_system", float("nan")))
    residual_ok = math.isfinite(residual) and residual <= settings.residual_atol
    checks.append(
        ValidationCheck(
            name="linear_system_residual",
            outcome=(
                ValidationOutcome.PASS if residual_ok else ValidationOutcome.FAIL
            ),
            residual=residual,
            tolerance=settings.residual_atol,
            detail=(
                "||A u_new - u_old|| for the final backward-Euler step. This "
                "is linear-algebra self-consistency and says nothing about "
                "discretization accuracy"
            ),
            # Deliberately establishes nothing. See the module docstring.
            establishes=None,
        )
    )

    finite = bool(np.all(np.isfinite(field_values)))
    checks.append(
        ValidationCheck(
            name="field_finite",
            outcome=ValidationOutcome.PASS if finite else ValidationOutcome.FAIL,
            detail="every node value is finite",
            establishes=None,
        )
    )

    boundary_error = float(max(abs(field_values[0]), abs(field_values[-1])))
    boundary_ok = boundary_error <= settings.boundary_atol
    checks.append(
        ValidationCheck(
            name="boundary_conditions_held",
            outcome=(
                ValidationOutcome.PASS if boundary_ok else ValidationOutcome.FAIL
            ),
            residual=boundary_error,
            tolerance=settings.boundary_atol,
            detail="u(0,t) and u(L,t) held at zero",
            establishes=None,
        )
    )

    initial_max = float(raw.diagnostics.get("initial_max_abs", 1.0))
    final_max = float(np.max(np.abs(field_values)))
    decayed = final_max <= initial_max + settings.boundary_atol
    checks.append(
        ValidationCheck(
            name="amplitude_decay",
            outcome=ValidationOutcome.PASS if decayed else ValidationOutcome.FAIL,
            residual=final_max,
            tolerance=initial_max,
            detail=(
                f"max|u| fell from {initial_max:.6g} to {final_max:.6g}; "
                f"homogeneous Dirichlet diffusion cannot amplify"
            ),
            establishes=None,
        )
    )

    checks.append(
        ValidationCheck(
            name="dimensional_consistency",
            outcome=ValidationOutcome.PASS,
            detail=(
                "all metrics carry the dimensionless field unit; u is a "
                "normalized field and is not reported as a temperature"
            ),
            establishes=ValidationLevel.DIMENSIONALLY_VALID,
        )
    )

    checks.append(
        ValidationCheck(
            name="discretization_convergence",
            outcome=ValidationOutcome.NOT_RUN,
            detail=(
                "a single solve cannot establish discretization convergence: "
                "it has nothing to compare itself against. Run the refinement "
                "gate (run_verification_gate) over a ladder of resolutions"
            ),
            establishes=None,
        )
    )

    checks.append(
        ValidationCheck(
            name="analytic_reference_agreement",
            outcome=ValidationOutcome.NOT_RUN,
            detail=(
                "comparison against the closed-form reference is performed by "
                "the verification gate, which requires a converged finest rung "
                "before it will award ANALYTICALLY_VERIFIED"
            ),
            establishes=None,
        )
    )

    return ValidationReport(
        checks=tuple(checks),
        notes=(
            "single-solve validation; the strongest level available here is "
            "DIMENSIONALLY_VALID"
        ),
    )


# =====================================================================
# The refinement gate
# =====================================================================

@dataclass(frozen=True)
class RefinementRung:
    n_cells: int
    n_steps: int

    @property
    def work_proxy(self) -> int:
        return self.n_cells * self.n_steps


#: The declared ladder. A domain-local sequence; it is NOT wired into any SRIA
#: fidelity strategy and nothing here selects a rung.
VERIFICATION_LADDER: tuple[RefinementRung, ...] = (
    RefinementRung(8, 10),
    RefinementRung(16, 20),
    RefinementRung(32, 40),
    RefinementRung(64, 80),
    RefinementRung(128, 160),
    RefinementRung(256, 320),
    RefinementRung(512, 640),
)

#: Successive |Δ QoI| must contract by at least this factor at every step.
#: First-order-in-Δt behaviour on this coupled ladder predicts ~2, so 1.5 is a
#: floor the sequence must clear. DECLARED AFTER EXPLORATORY ANALYSIS that had
#: already seen contractions near 2.0-2.3 — see the module docstring.
CONVERGENCE_MIN_CONTRACTION = 1.5

#: The finest rung must agree with the closed form to this relative tolerance.
#: A conventional engineering verification level. DECLARED AFTER EXPLORATORY
#: ANALYSIS that had already seen a finest error near 4e-4 — see the module
#: docstring. Frozen from that point: not retuned for the holdout, and not to
#: be retuned if a future case fails it.
ANALYTIC_REL_TOL = 1.0e-3

#: A ladder shorter than this cannot show a trend worth calling convergence.
MIN_RUNGS = 4


@dataclass(frozen=True)
class RungResult:
    n_cells: int
    n_steps: int
    dx_m: float
    dt_s: float
    qoi: float
    analytic: float
    abs_error: float
    rel_error: float
    work_proxy: int
    wall_seconds_telemetry: float | None
    successive_delta: float | None = None
    error_ratio: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_cells": self.n_cells,
            "n_steps": self.n_steps,
            "dx_m": self.dx_m,
            "dt_s": self.dt_s,
            "qoi": self.qoi,
            "analytic": self.analytic,
            "abs_error": self.abs_error,
            "rel_error": self.rel_error,
            "work_proxy": self.work_proxy,
            "wall_seconds_telemetry": self.wall_seconds_telemetry,
            "successive_delta": self.successive_delta,
            "error_ratio": self.error_ratio,
        }


@dataclass(frozen=True)
class VerificationReport:
    """The outcome of a refinement study, and the levels it earns."""

    rungs: tuple[RungResult, ...]
    numerically_converged: bool
    analytically_verified: bool
    convergence_detail: str
    analytic_detail: str
    min_contraction_required: float
    analytic_rel_tol: float
    reference_id: str = REFERENCE_ID
    reference_expression: str = REFERENCE_EXPRESSION

    @property
    def levels_earned(self) -> tuple[ValidationLevel, ...]:
        earned: list[ValidationLevel] = []
        if self.numerically_converged:
            earned.append(ValidationLevel.NUMERICALLY_CONVERGED)
        if self.analytically_verified:
            earned.append(ValidationLevel.ANALYTICALLY_VERIFIED)
        return tuple(earned)

    @property
    def claim(self) -> str:
        if not self.numerically_converged:
            return "no convergence claim is supported by this sequence"
        return (
            "the coupled refinement sequence converges toward the analytic "
            "solution with behaviour consistent with first-order temporal "
            "error dominating the combined refinement; spatial and temporal "
            "orders are NOT separately identified by this test"
        )

    def to_report(self) -> ValidationReport:
        """The gate expressed in the universal validation vocabulary."""
        checks = (
            ValidationCheck(
                name="discretization_convergence",
                outcome=(
                    ValidationOutcome.PASS
                    if self.numerically_converged
                    else ValidationOutcome.FAIL
                ),
                detail=self.convergence_detail,
                tolerance=self.min_contraction_required,
                establishes=(
                    ValidationLevel.NUMERICALLY_CONVERGED
                    if self.numerically_converged
                    else None
                ),
                evidence=tuple(
                    f"{r.n_cells}c/{r.n_steps}s err={r.abs_error:.6e}"
                    for r in self.rungs
                ),
            ),
            ValidationCheck(
                name="analytic_reference_agreement",
                outcome=(
                    ValidationOutcome.PASS
                    if self.analytically_verified
                    else ValidationOutcome.FAIL
                ),
                detail=self.analytic_detail,
                residual=self.rungs[-1].rel_error if self.rungs else None,
                tolerance=self.analytic_rel_tol,
                establishes=(
                    ValidationLevel.ANALYTICALLY_VERIFIED
                    if self.analytically_verified
                    else None
                ),
                evidence=(f"{self.reference_id}: {self.reference_expression}",),
            ),
        )
        return ValidationReport(checks=checks, notes=self.claim)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rungs": [r.to_dict() for r in self.rungs],
            "numerically_converged": self.numerically_converged,
            "analytically_verified": self.analytically_verified,
            "convergence_detail": self.convergence_detail,
            "analytic_detail": self.analytic_detail,
            "min_contraction_required": self.min_contraction_required,
            "analytic_rel_tol": self.analytic_rel_tol,
            "levels_earned": [level.value for level in self.levels_earned],
            "claim": self.claim,
            "reference_id": self.reference_id,
            "reference_expression": self.reference_expression,
        }


def run_verification_gate(
    slab: "ConductionSlab",
    *,
    ladder: Sequence[RefinementRung] = VERIFICATION_LADDER,
    run_id_prefix: str = "thermal-verify",
    min_contraction: float = CONVERGENCE_MIN_CONTRACTION,
    analytic_rel_tol: float = ANALYTIC_REL_TOL,
) -> VerificationReport:
    """Solve the same physical slab at every rung and judge the sequence.

    The slab's own discretization is ignored: every rung supplies its own, and
    the physics is held identical via ``with_discretization`` so that any
    difference between rungs is numerical by construction.
    """
    from .problem import MIDPOINT_METRIC, SlabDiscretization, build_conduction_problem
    from .solver import Conduction1DSolver, solve_slab

    if len(ladder) < 2:
        raise SlabConfigurationError(
            "a refinement gate needs at least two rungs to compare"
        )

    analytic = exact_midpoint(
        length_m=slab.length_m,
        alpha_m2_s=slab.alpha_m2_s,
        time_s=slab.end_time_s,
    )

    rows: list[RungResult] = []
    previous_qoi: float | None = None
    previous_error: float | None = None
    for index, rung in enumerate(ladder):
        refined = slab.with_discretization(
            SlabDiscretization(rung.n_cells, rung.n_steps)
        )
        # A fresh solver per rung: binding is keyed by problem id, and every
        # rung is the same physics, so one solver would refuse nothing — but a
        # fresh one makes each rung independently reproducible.
        problem = build_conduction_problem(
            refined, problem_id=f"{run_id_prefix}-{index}"
        )
        result = solve_slab(
            refined,
            run_id=f"{run_id_prefix}-{index}",
            solver=Conduction1DSolver(),
            problem=problem,
        )
        qoi = result.values[MIDPOINT_METRIC].magnitude_in("dimensionless")
        abs_error = abs(qoi - analytic)
        rows.append(
            RungResult(
                n_cells=rung.n_cells,
                n_steps=rung.n_steps,
                dx_m=refined.dx_m,
                dt_s=refined.dt_s,
                qoi=qoi,
                analytic=analytic,
                abs_error=abs_error,
                rel_error=abs_error / abs(analytic) if analytic else float("inf"),
                work_proxy=rung.work_proxy,
                wall_seconds_telemetry=result.metadata.get(
                    "wall_seconds_telemetry"
                ),
                successive_delta=(
                    None if previous_qoi is None else abs(qoi - previous_qoi)
                ),
                error_ratio=(
                    None
                    if previous_error is None or abs_error == 0.0
                    else previous_error / abs_error
                ),
            )
        )
        previous_qoi = qoi
        previous_error = abs_error

    # --- convergence gate -------------------------------------------------
    reasons: list[str] = []
    if len(rows) < MIN_RUNGS:
        reasons.append(
            f"only {len(rows)} rungs; at least {MIN_RUNGS} are required"
        )
    errors = [r.abs_error for r in rows]
    if not all(b < a for a, b in zip(errors, errors[1:])):
        reasons.append("analytic error did not fall monotonically")
    deltas = [r.successive_delta for r in rows if r.successive_delta is not None]
    contractions = [
        (a / b) for a, b in zip(deltas, deltas[1:]) if b > 0.0
    ]
    if len(contractions) != max(len(deltas) - 1, 0):
        reasons.append("a successive difference was zero; contraction undefined")
    elif any(c < min_contraction for c in contractions):
        worst = min(contractions)
        reasons.append(
            f"successive QoI differences contracted by only {worst:.3f} at the "
            f"weakest step, below the required {min_contraction}"
        )
    numerically_converged = not reasons

    if numerically_converged:
        convergence_detail = (
            f"{len(rows)} rungs from {rows[0].n_cells}c/{rows[0].n_steps}s to "
            f"{rows[-1].n_cells}c/{rows[-1].n_steps}s; analytic error fell "
            f"{errors[0]:.6e} -> {errors[-1]:.6e}; successive QoI differences "
            f"contracted by at least {min(contractions):.3f} at every step "
            f"(required {min_contraction})"
        )
    else:
        convergence_detail = "; ".join(reasons)

    # --- analytic gate ----------------------------------------------------
    finest = rows[-1]
    within_tolerance = finest.rel_error <= analytic_rel_tol
    analytically_verified = bool(numerically_converged and within_tolerance)
    if analytically_verified:
        analytic_detail = (
            f"finest rung {finest.n_cells}c/{finest.n_steps}s gives "
            f"{finest.qoi:.12g} against the closed form {finest.analytic:.12g}; "
            f"relative error {finest.rel_error:.6e} within {analytic_rel_tol}"
        )
    elif not numerically_converged:
        analytic_detail = (
            f"relative error at the finest rung is {finest.rel_error:.6e}, but "
            f"ANALYTICALLY_VERIFIED is withheld because the sequence is not "
            f"numerically converged: agreement without a convergent sequence "
            f"behind it is not verification"
        )
    else:
        analytic_detail = (
            f"finest rung relative error {finest.rel_error:.6e} exceeds the "
            f"declared tolerance {analytic_rel_tol}"
        )

    return VerificationReport(
        rungs=tuple(rows),
        numerically_converged=numerically_converged,
        analytically_verified=analytically_verified,
        convergence_detail=convergence_detail,
        analytic_detail=analytic_detail,
        min_contraction_required=min_contraction,
        analytic_rel_tol=analytic_rel_tol,
    )
