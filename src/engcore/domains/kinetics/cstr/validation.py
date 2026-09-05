"""Two verification concepts, kept apart on purpose.

PER-SOLVE VALIDATION establishes what one run can establish: the integrator
reported success, the trajectory is finite, the state stayed inside the model's
declared validity envelope, and the metrics carry the right units. That is the
whole list. It awards ``DIMENSIONALLY_VALID`` and nothing stronger.

It specifically does NOT award ``NUMERICALLY_CONVERGED``. ``solve_ivp``
returning ``status == 0`` means its local error estimate stayed under the
tolerance it was handed, and it says that with identical confidence at
rtol=1e-2 and at rtol=1e-12. Treating that as convergence would certify a
badly under-resolved ignition exactly as confidently as a converged one.
Numerical adequacy for an adaptive integrator is a statement about *tolerance
independence*, which is invisible to a single solve — the run has nothing to
compare itself against — and the honest record of that is an explicit NOT_RUN
check rather than silence.

THE VERIFICATION GATE establishes the claims that need more than one solve:

    NUMERICALLY_CONVERGED     the quantities of interest stop moving as the
                              tolerance is tightened down a declared ladder
    ANALYTICALLY_VERIFIED     the trajectory reproduces the exact reaction-free
                              invariant — available for an adiabatic reactor
                              only, where that invariant is a closed form
    CROSS_SOLVER_VALIDATED    the stationary end state agrees with a steady
                              state found by an independent algebraic solver

THE ORDERING IS NOT DECORATIVE
-------------------------------
Both reference comparisons require tolerance independence first. A result that
happened to land near a reference without a convergent sequence behind it has
not been verified; it has been lucky, and the gate refuses to call that
verification. This mirrors the rule the Thermal domain already established.

WHY BDF-vs-RADAU ESTABLISHES NOTHING
-------------------------------------
The gate also runs the same physics through both stiff integrators and reports
whether they agree. That check deliberately ``establishes=None``. The two
methods are genuinely different families, but they share this domain's
right-hand-side implementation, its analytic Jacobian, its unit conversions and
SciPy's step-control and error-norm infrastructure. A shared error in any of
those is invisible to the comparison. Reporting it as CROSS_SOLVER_VALIDATED
would be letting the solver grade itself with a second copy of its own
homework, so the comparison is recorded as evidence and awards no level.

The independent steady state is different in kind: different equations
(algebraic rather than differential), a different algorithm (Brent bracketing),
and an implementation in :mod:`reference` that shares no arithmetic with the
solve path. That one does award a level.

PROVENANCE OF THE THRESHOLDS — READ THIS BEFORE QUOTING THEM
-------------------------------------------------------------
``TOLERANCE_REL_TOL``, ``INVARIANT_REL_TOL``, ``STEADY_STATE_REL_TOL`` and
``STATIONARITY_REL_TOL`` are a **declared verification gate set after
exploratory feasibility analysis**. They are NOT preregistered, and calling
them so would overstate what they are.

An exploratory pass on the benchmark parameterization had already observed the
scale of each residual before these numbers were written down; each was then
set comfortably outside what exploration had seen rather than tightly around
it, and all were fixed before any scored run. A reader deciding how much weight
the gate carries needs to know that. The K1 preregistration records which
numbers exploration supplied and which it did not, and the confirmatory
evidence for the gate is that it clears untouched on regimes the thresholds
were not chosen from.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from ....scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from .problem import (
    MAX_VALID_TEMPERATURE_K,
    MIN_VALID_TEMPERATURE_K,
    CA_FINAL_METRIC,
    CONVERSION_METRIC,
    T_FINAL_METRIC,
    T_MAX_METRIC,
)
from .reference import (
    INVARIANT_EXPRESSION,
    INVARIANT_REFERENCE_ID,
    SEARCH_SEMANTICS,
    STEADY_STATE_EXPRESSION,
    STEADY_STATE_REFERENCE_ID,
    adiabatic_invariant_exact,
    invariant_is_exact,
    invariant_value,
    steady_states,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .problem import ReactorRun


# =====================================================================
# Per-solve settings and report
# =====================================================================

@dataclass(frozen=True)
class CSTRValidationSettings:
    """Tolerances for the checks a single solve can actually make."""

    #: How far below zero a concentration may drift before the state is called
    #: inadmissible. Not zero: an integrator working to a finite absolute
    #: tolerance will legitimately return values of that order on either side
    #: of an exact zero, and calling round-off a physical violation would make
    #: the check fire on correct answers. Set an order of magnitude above the
    #: tightest atol the tolerance ladder uses.
    concentration_floor_atol: float = 1.0e-9      # mol/m**3
    #: Slack on the upper concentration bound, same reasoning.
    concentration_ceiling_rtol: float = 1.0e-9
    #: The model's own declared temperature envelope, restated as a per-solve
    #: check so a trajectory that leaves it is caught even though the
    #: declaration that started it was inside.
    min_temperature_k: float = MIN_VALID_TEMPERATURE_K
    max_temperature_k: float = MAX_VALID_TEMPERATURE_K

    def as_mapping(self) -> dict[str, float]:
        return {
            "concentration_floor_atol": float(self.concentration_floor_atol),
            "concentration_ceiling_rtol": float(self.concentration_ceiling_rtol),
            "min_temperature_k": float(self.min_temperature_k),
            "max_temperature_k": float(self.max_temperature_k),
        }


def build_validation_report(
    run: "ReactorRun", raw, settings: CSTRValidationSettings
) -> ValidationReport:
    """Checks one solve can support, and explicit notes about what it cannot."""
    if not raw.succeeded:
        outcome_name = str(raw.diagnostics.get("outcome", "unknown"))
        return ValidationReport(
            checks=(
                ValidationCheck(
                    name="integration_reported_success",
                    outcome=ValidationOutcome.FAIL,
                    detail=(
                        f"integration did not complete the horizon "
                        f"({raw.convergence.value}, {outcome_name}): "
                        + ("; ".join(raw.warnings) or "no detail reported")
                    ),
                    establishes=None,
                ),
                ValidationCheck(
                    name="state_physically_admissible",
                    outcome=ValidationOutcome.NOT_RUN,
                    detail=(
                        "no completed trajectory to assess; the partial "
                        "trajectory is preserved in the raw diagnostics"
                    ),
                    establishes=None,
                ),
            ),
            notes=(
                f"no result to validate: the solve ended as "
                f"{raw.convergence.value}"
            ),
        )

    checks: list[ValidationCheck] = []

    checks.append(
        ValidationCheck(
            name="integration_reported_success",
            outcome=ValidationOutcome.PASS,
            detail=(
                f"solve_ivp completed the horizon with status 0 using "
                f"{run.integration.method} at rtol={run.integration.rtol:.3g}. "
                f"This is the integrator's opinion of its own local error "
                f"control and establishes nothing about accuracy"
            ),
            # Deliberately establishes nothing. See the module docstring.
            establishes=None,
        )
    )

    temperature = np.asarray(
        raw.diagnostics.get("grid_temperature_k", ()), dtype=np.float64
    )
    concentration = np.asarray(
        raw.diagnostics.get("grid_concentration_mol_per_m3", ()), dtype=np.float64
    )

    finite = bool(
        np.all(np.isfinite(temperature)) and np.all(np.isfinite(concentration))
    )
    checks.append(
        ValidationCheck(
            name="trajectory_finite",
            outcome=ValidationOutcome.PASS if finite else ValidationOutcome.FAIL,
            detail="every sampled state value is finite",
            establishes=None,
        )
    )

    # --- the physical envelope, over the whole trajectory ------------------
    min_concentration = float(raw.diagnostics.get(
        "min_concentration_mol_per_m3", float("nan")
    ))
    max_concentration = float(raw.diagnostics.get(
        "max_concentration_mol_per_m3", float("nan")
    ))
    min_temperature = float(raw.diagnostics.get("min_temperature_k", float("nan")))
    max_temperature = float(raw.diagnostics.get("max_temperature_k", float("nan")))
    ceiling = run.concentration_ceiling_mol_per_m3

    violations: list[str] = []
    if not math.isfinite(min_concentration) or (
        min_concentration < -settings.concentration_floor_atol
    ):
        violations.append(
            f"concentration reached {min_concentration:.6g} mol/m**3, below the "
            f"physical floor of zero by more than "
            f"{settings.concentration_floor_atol:.3g}"
        )
    if not math.isfinite(max_concentration) or (
        max_concentration
        > ceiling * (1.0 + settings.concentration_ceiling_rtol)
    ):
        violations.append(
            f"concentration reached {max_concentration:.6g} mol/m**3, above the "
            f"ceiling {ceiling:.6g} mol/m**3 that a consuming reaction fed at "
            f"C_Af cannot exceed"
        )
    if not math.isfinite(min_temperature) or (
        min_temperature < settings.min_temperature_k
    ):
        violations.append(
            f"temperature reached {min_temperature:.6g} K, below the model's "
            f"declared validity envelope [{settings.min_temperature_k}, "
            f"{settings.max_temperature_k}] K"
        )
    if not math.isfinite(max_temperature) or (
        max_temperature > settings.max_temperature_k
    ):
        violations.append(
            f"temperature reached {max_temperature:.6g} K, above the model's "
            f"declared validity envelope [{settings.min_temperature_k}, "
            f"{settings.max_temperature_k}] K; the constant-property "
            f"single-phase assumptions do not hold there"
        )

    checks.append(
        ValidationCheck(
            name="state_physically_admissible",
            outcome=(
                ValidationOutcome.PASS if not violations else ValidationOutcome.FAIL
            ),
            detail=(
                "; ".join(violations)
                if violations
                else (
                    f"C_A in [{min_concentration:.6g}, {max_concentration:.6g}] "
                    f"mol/m**3 within [0, {ceiling:.6g}]; T in "
                    f"[{min_temperature:.6g}, {max_temperature:.6g}] K within "
                    f"the declared envelope"
                )
            ),
            establishes=None,
        )
    )

    checks.append(
        ValidationCheck(
            name="dimensional_consistency",
            outcome=ValidationOutcome.PASS,
            detail=(
                "concentrations carry mol/m**3, temperatures carry kelvin as "
                "absolute thermodynamic temperatures, time carries seconds, "
                "and conversion is a genuine dimensionless concentration ratio"
            ),
            establishes=ValidationLevel.DIMENSIONALLY_VALID,
        )
    )

    checks.append(
        ValidationCheck(
            name="tolerance_independence",
            outcome=ValidationOutcome.NOT_RUN,
            detail=(
                "a single solve cannot establish numerical adequacy: it has "
                "nothing to compare itself against. Run the verification gate "
                "(run_verification_gate) over the declared tolerance ladder"
            ),
            establishes=None,
        )
    )

    checks.append(
        ValidationCheck(
            name="analytic_invariant_agreement",
            outcome=ValidationOutcome.NOT_RUN,
            detail=(
                "comparison against the exact reaction-free invariant is "
                "performed by the verification gate, which requires tolerance "
                "independence before it will award ANALYTICALLY_VERIFIED"
                + (
                    ""
                    if run.operation.is_adiabatic
                    else "; this reactor is cooled, so the invariant has no "
                    "closed form and the check is unavailable at any tolerance"
                )
            ),
            establishes=None,
        )
    )

    checks.append(
        ValidationCheck(
            name="independent_steady_state_agreement",
            outcome=ValidationOutcome.NOT_RUN,
            detail=(
                "comparison against the independently computed algebraic "
                "steady state is performed by the verification gate"
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
# The verification gate
# =====================================================================

@dataclass(frozen=True)
class ToleranceRung:
    """One rung of the tolerance ladder."""

    rtol: float
    atol_concentration: float
    atol_temperature: float

    @property
    def label(self) -> str:
        return f"rtol={self.rtol:.0e}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rtol": self.rtol,
            "atol_concentration": self.atol_concentration,
            "atol_temperature": self.atol_temperature,
        }


#: The declared ladder. Absolute tolerances fall with the relative one so that
#: no rung is silently floored by its atol: a ladder that tightened rtol alone
#: would stop improving as soon as atol dominated, and would then report a
#: false convergence plateau.
TOLERANCE_LADDER: tuple[ToleranceRung, ...] = (
    ToleranceRung(1.0e-6, 1.0e-6, 1.0e-6),
    ToleranceRung(1.0e-8, 1.0e-8, 1.0e-8),
    ToleranceRung(1.0e-10, 1.0e-10, 1.0e-10),
    ToleranceRung(1.0e-12, 1.0e-12, 1.0e-12),
)

#: The quantities whose tolerance independence is required. ``t:T_max`` is
#: excluded on purpose: on a monotone approach the peak sits at an endpoint and
#: its *time* is a plateau-valued quantity whose sampled argmax can jump
#: between nearly-equal values, which would be an artifact of reading an argmax
#: rather than a statement about accuracy.
CONVERGENCE_QOIS = (CA_FINAL_METRIC, T_FINAL_METRIC, T_MAX_METRIC, CONVERSION_METRIC)

#: Relative agreement required between the two tightest rungs, on every QoI.
#: DECLARED AFTER EXPLORATORY ANALYSIS — see the module docstring.
TOLERANCE_REL_TOL = 1.0e-6

#: Relative agreement required against the exact adiabatic invariant.
#: DECLARED AFTER EXPLORATORY ANALYSIS — see the module docstring. Exploration
#: observed errors near 1e-15 here, so a conventional 1e-6 engineering gate
#: would have been unfailable and therefore worthless as evidence. This is set
#: six orders above what was observed: loose enough that round-off and a
#: reasonable tolerance choice cannot trip it, tight enough that a genuine
#: breakdown of the two-state coupling would.
INVARIANT_REL_TOL = 1.0e-9

#: Relative agreement required against the independent algebraic steady state.
#: DECLARED AFTER EXPLORATORY ANALYSIS, on the same reasoning as the invariant
#: tolerance: exploration observed agreement at round-off, so the gate is set
#: six orders looser than the observation rather than six orders looser than
#: the physics would allow.
STEADY_STATE_REL_TOL = 1.0e-9

#: A trajectory counts as stationary when its states move by less than this,
#: relatively, over the final tenth of the horizon. Without it the steady-state
#: comparison would be applied to a trajectory that had not settled, and would
#: report disagreement that is about the horizon rather than about accuracy.
STATIONARITY_REL_TOL = 1.0e-6

#: A ladder shorter than this cannot show a trend worth calling convergence.
MIN_RUNGS = 3


@dataclass(frozen=True)
class ToleranceRungResult:
    """One rung's outcome.

    ``converged`` and ``usable`` are separate fields because K1 proved they are
    separate facts. A rung can complete the horizon, report CONVERGED and
    produce a full set of metrics while its trajectory sits outside the model's
    validity envelope — that is exactly regime R8. Treating "metrics were
    produced" as "this rung counts" would let such a rung carry a sequence to
    NUMERICALLY_CONVERGED, and the gate would then certify a ladder built on
    results the domain had already refused to call usable.
    """

    rung: ToleranceRung
    converged: bool
    usable: bool
    qois: dict[str, float]
    rhs_evaluations: int
    wall_seconds_telemetry: float | None
    unusable_reason: str = ""
    max_relative_change: float | None = None

    @property
    def counts_toward_verification(self) -> bool:
        """Only a converged AND usable rung is evidence about accuracy."""
        return self.converged and self.usable

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.rung.to_dict(),
            "converged": self.converged,
            "usable": self.usable,
            "counts_toward_verification": self.counts_toward_verification,
            "unusable_reason": self.unusable_reason,
            "qois": dict(self.qois),
            "rhs_evaluations": self.rhs_evaluations,
            "wall_seconds_telemetry": self.wall_seconds_telemetry,
            "max_relative_change": self.max_relative_change,
        }


@dataclass(frozen=True)
class CSTRVerificationReport:
    """The outcome of a verification study, and the levels it earns."""

    rungs: tuple[ToleranceRungResult, ...]
    tolerance_independent: bool
    tolerance_detail: str
    invariant_verified: bool
    invariant_detail: str
    invariant_max_rel_error: float | None
    steady_state_verified: bool
    steady_state_detail: str
    steady_state_rel_error: float | None
    steady_states_found: tuple[dict[str, Any], ...]
    cross_method_agrees: bool | None
    cross_method_detail: str
    cross_method_max_rel_difference: float | None
    tolerance_rel_tol: float = TOLERANCE_REL_TOL
    invariant_rel_tol: float = INVARIANT_REL_TOL
    steady_state_rel_tol: float = STEADY_STATE_REL_TOL

    @property
    def levels_earned(self) -> tuple[ValidationLevel, ...]:
        earned: list[ValidationLevel] = []
        if self.tolerance_independent:
            earned.append(ValidationLevel.NUMERICALLY_CONVERGED)
        if self.invariant_verified:
            earned.append(ValidationLevel.ANALYTICALLY_VERIFIED)
        if self.steady_state_verified:
            earned.append(ValidationLevel.CROSS_SOLVER_VALIDATED)
        return tuple(earned)

    @property
    def claim(self) -> str:
        if not self.tolerance_independent:
            return (
                "no numerical adequacy claim is supported by this tolerance "
                "sequence"
            )
        parts = [
            "the quantities of interest are independent of the integration "
            "tolerance down the declared ladder"
        ]
        if self.invariant_verified:
            parts.append(
                "and reproduce the exact reaction-free invariant of the "
                "nonlinear system"
            )
        if self.steady_state_verified:
            parts.append(
                "and the stationary end state agrees with an independently "
                "computed algebraic steady state"
            )
        return "; ".join(parts) + (
            ". No comparison against any physical measurement was performed"
        )

    def to_report(self) -> ValidationReport:
        """The gate expressed in the universal validation vocabulary."""
        checks = [
            ValidationCheck(
                name="tolerance_independence",
                outcome=(
                    ValidationOutcome.PASS
                    if self.tolerance_independent
                    else ValidationOutcome.FAIL
                ),
                detail=self.tolerance_detail,
                tolerance=self.tolerance_rel_tol,
                residual=(
                    self.rungs[-1].max_relative_change if self.rungs else None
                ),
                establishes=(
                    ValidationLevel.NUMERICALLY_CONVERGED
                    if self.tolerance_independent
                    else None
                ),
                evidence=tuple(
                    f"{r.rung.label} nfev={r.rhs_evaluations}" for r in self.rungs
                ),
            ),
            ValidationCheck(
                name="analytic_invariant_agreement",
                outcome=(
                    ValidationOutcome.PASS
                    if self.invariant_verified
                    else (
                        ValidationOutcome.NOT_RUN
                        if self.invariant_max_rel_error is None
                        else ValidationOutcome.FAIL
                    )
                ),
                detail=self.invariant_detail,
                residual=self.invariant_max_rel_error,
                tolerance=self.invariant_rel_tol,
                establishes=(
                    ValidationLevel.ANALYTICALLY_VERIFIED
                    if self.invariant_verified
                    else None
                ),
                evidence=(f"{INVARIANT_REFERENCE_ID}: {INVARIANT_EXPRESSION}",),
            ),
            ValidationCheck(
                name="independent_steady_state_agreement",
                outcome=(
                    ValidationOutcome.PASS
                    if self.steady_state_verified
                    else (
                        ValidationOutcome.NOT_RUN
                        if self.steady_state_rel_error is None
                        else ValidationOutcome.FAIL
                    )
                ),
                detail=self.steady_state_detail,
                residual=self.steady_state_rel_error,
                tolerance=self.steady_state_rel_tol,
                establishes=(
                    ValidationLevel.CROSS_SOLVER_VALIDATED
                    if self.steady_state_verified
                    else None
                ),
                evidence=(
                    f"{STEADY_STATE_REFERENCE_ID}: {STEADY_STATE_EXPRESSION}",
                    *(
                        f"steady state T={s['temperature_k']:.6f} K "
                        f"({s['stability']})"
                        for s in self.steady_states_found
                    ),
                ),
            ),
            ValidationCheck(
                name="cross_method_agreement",
                outcome=(
                    ValidationOutcome.NOT_RUN
                    if self.cross_method_agrees is None
                    else (
                        ValidationOutcome.PASS
                        if self.cross_method_agrees
                        else ValidationOutcome.WARNING
                    )
                ),
                detail=self.cross_method_detail,
                residual=self.cross_method_max_rel_difference,
                tolerance=self.tolerance_rel_tol,
                # Deliberately establishes nothing: the two methods share this
                # domain's right-hand side, Jacobian and SciPy's step control.
                # See the module docstring.
                establishes=None,
            ),
        ]
        return ValidationReport(checks=tuple(checks), notes=self.claim)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rungs": [r.to_dict() for r in self.rungs],
            "tolerance_independent": self.tolerance_independent,
            "tolerance_detail": self.tolerance_detail,
            "tolerance_rel_tol": self.tolerance_rel_tol,
            "invariant_verified": self.invariant_verified,
            "invariant_detail": self.invariant_detail,
            "invariant_max_rel_error": self.invariant_max_rel_error,
            "invariant_rel_tol": self.invariant_rel_tol,
            "steady_state_verified": self.steady_state_verified,
            "steady_state_detail": self.steady_state_detail,
            "steady_state_rel_error": self.steady_state_rel_error,
            "steady_state_rel_tol": self.steady_state_rel_tol,
            "steady_states_found": [dict(s) for s in self.steady_states_found],
            "steady_state_search_semantics": SEARCH_SEMANTICS,
            "cross_method_agrees": self.cross_method_agrees,
            "cross_method_detail": self.cross_method_detail,
            "cross_method_max_rel_difference":
                self.cross_method_max_rel_difference,
            "levels_earned": [level.value for level in self.levels_earned],
            "claim": self.claim,
            "reference_ids": [STEADY_STATE_REFERENCE_ID, INVARIANT_REFERENCE_ID],
        }


def _relative(a: float, b: float) -> float:
    """|a - b| / max(|b|, tiny). Symmetric enough for a convergence readout."""
    scale = max(abs(b), abs(a), 1e-300)
    return abs(a - b) / scale


def run_verification_gate(
    run: "ReactorRun",
    *,
    ladder: Sequence[ToleranceRung] = TOLERANCE_LADDER,
    run_id_prefix: str = "cstr-verify",
    tolerance_rel_tol: float = TOLERANCE_REL_TOL,
    invariant_rel_tol: float = INVARIANT_REL_TOL,
    steady_state_rel_tol: float = STEADY_STATE_REL_TOL,
    cross_method: str = "Radau",
) -> CSTRVerificationReport:
    """Solve the same physics down a tolerance ladder and judge the sequence.

    The run's own integration declaration supplies the method and the budget;
    every rung overrides only the tolerances, so any difference between rungs is
    numerical by construction.
    """
    from .problem import build_cstr_problem
    from .solver import CSTRSolver, TransientTrajectorySample, solve_reactor_bundle

    if len(ladder) < 2:
        raise ValueError("a tolerance gate needs at least two rungs to compare")

    rows: list[ToleranceRungResult] = []
    finest_result = None
    #: The finest rung's own trajectory sample, kept from the solve that
    #: produced it. This is the sample the invariant and stationarity checks
    #: read; it used to be recovered by integrating the finest rung a second
    #: time, which is the same arithmetic for the same answer.
    finest_rung_trajectory = TransientTrajectorySample.empty()

    for index, rung in enumerate(ladder):
        refined = run.with_integration(
            run.integration.with_tolerances(
                rtol=rung.rtol,
                atol_concentration=rung.atol_concentration,
                atol_temperature=rung.atol_temperature,
            )
        )
        problem = build_cstr_problem(refined, problem_id=f"{run_id_prefix}-{index}")
        bundle = solve_reactor_bundle(
            refined,
            run_id=f"{run_id_prefix}-{index}",
            solver=CSTRSolver(),
            problem=problem,
        )
        result = bundle.result
        # Keyed on the LAST rung of the ladder, not on the last *usable* one.
        # The re-solve this replaces was always performed at ladder[-1]'s
        # tolerances regardless of which rung became the reference, and changing
        # which trajectory the checks read would change what they report.
        if index == len(ladder) - 1:
            finest_rung_trajectory = bundle.trajectory
        converged = bool(result.values)
        # A completed solve is not automatically evidence about accuracy. If
        # the domain refused to call the result usable — an inadmissible state,
        # a trajectory outside the model's validity envelope — then it must not
        # contribute to any validation level, however well the integrator
        # behaved. Withheld, not downgraded to a failure: the solve really did
        # converge, and saying otherwise would be a different lie.
        usable = bool(converged and result.is_usable)
        unusable_reason = ""
        if converged and not usable:
            failing = "; ".join(
                f"{check.name}: {check.detail}"
                for check in result.validation.failures
            )
            unusable_reason = (
                f"the solve completed and reported "
                f"{result.convergence.value}, but the result is not usable "
                f"({failing or 'no detail recorded'})"
            )
        qois = {
            name: result.values[name].magnitude
            for name in CONVERGENCE_QOIS
            if name in result.values
        }
        numerics = dict(result.metadata.get("numerics", {}))
        rows.append(
            ToleranceRungResult(
                rung=rung,
                converged=converged,
                usable=usable,
                qois=qois,
                rhs_evaluations=int(numerics.get("rhs_evaluations", 0)),
                wall_seconds_telemetry=result.metadata.get(
                    "wall_seconds_telemetry"
                ),
                unusable_reason=unusable_reason,
            )
        )
        # Only a usable rung may become the reference the reference-comparisons
        # are taken against.
        if usable:
            finest_result = result

    # --- tolerance-independence gate --------------------------------------
    reasons: list[str] = []
    if len(rows) < MIN_RUNGS:
        reasons.append(f"only {len(rows)} rungs; at least {MIN_RUNGS} are required")
    incomplete = [r for r in rows if not r.converged]
    if incomplete:
        reasons.append(
            f"{len(incomplete)} of {len(rows)} rungs did not complete the horizon"
        )
    unusable = [r for r in rows if r.converged and not r.usable]
    if unusable:
        reasons.append(
            f"{len(unusable)} of {len(rows)} rungs completed but produced a "
            f"result the domain does not consider usable, so the sequence "
            f"cannot establish numerical adequacy: "
            + "; ".join(r.unusable_reason for r in unusable[:1])
        )
    failed = incomplete or unusable

    annotated: list[ToleranceRungResult] = list(rows)
    if not failed and len(rows) >= 2:
        annotated = [rows[0]]
        for previous, current in zip(rows, rows[1:]):
            changes = [
                _relative(current.qois[name], previous.qois[name])
                for name in CONVERGENCE_QOIS
                if name in current.qois and name in previous.qois
            ]
            worst = max(changes) if changes else float("nan")
            annotated.append(
                ToleranceRungResult(
                    rung=current.rung,
                    converged=current.converged,
                    usable=current.usable,
                    qois=current.qois,
                    rhs_evaluations=current.rhs_evaluations,
                    wall_seconds_telemetry=current.wall_seconds_telemetry,
                    unusable_reason=current.unusable_reason,
                    max_relative_change=worst,
                )
            )
        final_change = annotated[-1].max_relative_change
        if final_change is None or not math.isfinite(final_change):
            reasons.append("the finest tolerance comparison is not a finite number")
        elif final_change > tolerance_rel_tol:
            reasons.append(
                f"the two tightest rungs still disagree by {final_change:.3e}, "
                f"above the required {tolerance_rel_tol:.3e}: the quantities of "
                f"interest are still moving with the tolerance"
            )
    rows = tuple(annotated)  # type: ignore[assignment]
    tolerance_independent = not reasons

    if tolerance_independent:
        tolerance_detail = (
            f"{len(rows)} rungs from {rows[0].rung.label} to "
            f"{rows[-1].rung.label}; the largest relative change across the "
            f"two tightest rungs is {rows[-1].max_relative_change:.3e}, within "
            f"{tolerance_rel_tol:.3e}; right-hand-side evaluations rose "
            f"{rows[0].rhs_evaluations} -> {rows[-1].rhs_evaluations}"
        )
    else:
        tolerance_detail = "; ".join(reasons)

    # The trajectory sample is the one the finest rung already produced, kept
    # from that solve and shared by the invariant and stationarity checks. It is
    # NOT re-derived: the gate used to integrate the finest rung a second time
    # purely to recover arrays the result had discarded, which was the same
    # arithmetic reaching the same answer. The result contract is unchanged —
    # the sample rides beside it in a domain-local bundle, not inside it.
    if finest_result is not None:
        sample_times = finest_rung_trajectory.time_s
        sample_concentration = finest_rung_trajectory.concentration_mol_per_m3
        sample_temperature = finest_rung_trajectory.temperature_k
    else:
        sample_times = sample_concentration = sample_temperature = np.array([])

    # --- the exact adiabatic invariant ------------------------------------
    invariant_verified = False
    invariant_max_rel_error: float | None = None
    if not invariant_is_exact(run.gamma_per_s):
        invariant_detail = (
            f"the reactor is cooled (gamma = {run.gamma_per_s:.6g} 1/s), so the "
            f"reaction-free invariant has no closed form and no analytic "
            f"comparison is available at any tolerance"
        )
    elif finest_result is None:
        invariant_detail = (
            "no rung completed the horizon, so there is no trajectory to "
            "compare against the invariant"
        )
    else:
        beta = run.chemistry.beta_m3_k_per_mol
        times = sample_times
        numeric_z = invariant_value(
            sample_concentration, sample_temperature, beta_m3_k_per_mol=beta
        )
        exact_z = adiabatic_invariant_exact(
            times,
            dilution_rate_per_s=run.operation.dilution_rate_per_s,
            beta_m3_k_per_mol=beta,
            feed_concentration_mol_per_m3=run.operation.caf_mol_per_m3,
            feed_temperature_k=run.operation.tf_k,
            initial_concentration_mol_per_m3=run.ca0_mol_per_m3,
            initial_temperature_k=run.t0_k,
        )
        errors = np.abs(numeric_z - exact_z) / np.maximum(np.abs(exact_z), 1e-300)
        invariant_max_rel_error = float(np.max(errors))
        within = invariant_max_rel_error <= invariant_rel_tol
        invariant_verified = bool(tolerance_independent and within)
        if invariant_verified:
            invariant_detail = (
                f"the trajectory reproduces Z = T + beta C_A against the exact "
                f"closed form to a maximum relative error of "
                f"{invariant_max_rel_error:.3e} over {times.size} sample times, "
                f"within {invariant_rel_tol:.3e}. The reaction term cancels "
                f"exactly in Z, so this checks the coupling of the two states "
                f"through the stiff region without using the rate constant"
            )
        elif not tolerance_independent:
            invariant_detail = (
                f"maximum relative invariant error is "
                f"{invariant_max_rel_error:.3e}, but ANALYTICALLY_VERIFIED is "
                f"withheld because the sequence is not tolerance independent: "
                f"agreement without a convergent sequence behind it is not "
                f"verification"
            )
        else:
            invariant_detail = (
                f"maximum relative invariant error {invariant_max_rel_error:.3e} "
                f"exceeds the declared tolerance {invariant_rel_tol:.3e}"
            )

    # --- the independent algebraic steady state ---------------------------
    found = steady_states(
        dilution_rate_per_s=run.operation.dilution_rate_per_s,
        feed_concentration_mol_per_m3=run.operation.caf_mol_per_m3,
        feed_temperature_k=run.operation.tf_k,
        coolant_temperature_k=run.operation.tc_k,
        beta_m3_k_per_mol=run.chemistry.beta_m3_k_per_mol,
        gamma_per_s=run.gamma_per_s,
        k0_per_s=run.chemistry.k0_per_s,
        activation_energy_j_per_mol=run.chemistry.e_j_per_mol,
        search_min_k=MIN_VALID_TEMPERATURE_K,
        search_max_k=MAX_VALID_TEMPERATURE_K,
    )
    steady_states_found = tuple(s.to_dict() for s in found)

    steady_state_verified = False
    steady_state_rel_error: float | None = None
    if finest_result is None:
        steady_state_detail = (
            "no rung completed the horizon, so there is no end state to "
            "compare against a steady state"
        )
    elif not found:
        steady_state_detail = (
            f"the independent solver found no steady state inside "
            f"[{MIN_VALID_TEMPERATURE_K}, {MAX_VALID_TEMPERATURE_K}] K"
        )
    else:
        stationary, stationarity_detail = _is_stationary(
            sample_times, sample_concentration, sample_temperature
        )
        final_temperature = finest_result.values[T_FINAL_METRIC].magnitude
        nearest = min(
            found, key=lambda s: abs(s.temperature_k - final_temperature)
        )
        steady_state_rel_error = _relative(
            final_temperature, nearest.temperature_k
        )
        if not stationary:
            steady_state_detail = (
                f"the trajectory has not settled by the end of the horizon "
                f"({stationarity_detail}), so its end state is not a steady "
                f"state and comparing it to one would measure the horizon "
                f"rather than the accuracy. Nearest steady state is "
                f"{nearest.temperature_k:.6f} K ({nearest.stability}); the end "
                f"state is {final_temperature:.6f} K"
            )
            steady_state_rel_error = None
        else:
            within = steady_state_rel_error <= steady_state_rel_tol
            steady_state_verified = bool(tolerance_independent and within)
            if steady_state_verified:
                steady_state_detail = (
                    f"the stationary end state {final_temperature:.9f} K agrees "
                    f"with the independently computed steady state "
                    f"{nearest.temperature_k:.9f} K ({nearest.stability}) to a "
                    f"relative error of {steady_state_rel_error:.3e}, within "
                    f"{steady_state_rel_tol:.3e}. The reference solves the "
                    f"algebraic residual by Brent bracketing and shares no "
                    f"arithmetic with the integrator. "
                    f"{len(found)} transversal steady state(s) were found in "
                    f"the envelope ({SEARCH_SEMANTICS})"
                )
            elif not tolerance_independent:
                steady_state_detail = (
                    f"relative agreement with the independent steady state is "
                    f"{steady_state_rel_error:.3e}, but CROSS_SOLVER_VALIDATED "
                    f"is withheld because the sequence is not tolerance "
                    f"independent"
                )
            else:
                steady_state_detail = (
                    f"the end state {final_temperature:.9f} K differs from the "
                    f"nearest independent steady state "
                    f"{nearest.temperature_k:.9f} K by "
                    f"{steady_state_rel_error:.3e}, above the declared "
                    f"{steady_state_rel_tol:.3e}"
                )

    # --- the cross-method arm (establishes nothing) -----------------------
    cross_method_agrees: bool | None = None
    cross_method_max_rel_difference: float | None = None
    if finest_result is None or cross_method == run.integration.method:
        cross_method_detail = (
            "no completed reference rung to compare against"
            if finest_result is None
            else (
                f"the cross-method arm was asked for {cross_method!r}, which is "
                f"the production method; no independent comparison was made"
            )
        )
    else:
        from .problem import build_cstr_problem as _build
        from .solver import CSTRSolver as _Solver, solve_reactor as _solve

        alternative = run.with_integration(
            run.integration.with_method(cross_method).with_tolerances(
                rtol=ladder[-1].rtol,
                atol_concentration=ladder[-1].atol_concentration,
                atol_temperature=ladder[-1].atol_temperature,
            )
        )
        alt_problem = _build(alternative, problem_id=f"{run_id_prefix}-cross")
        alt_result = _solve(
            alternative,
            run_id=f"{run_id_prefix}-cross",
            solver=_Solver(),
            problem=alt_problem,
        )
        if not alt_result.values:
            cross_method_detail = (
                f"the {cross_method} arm did not complete the horizon "
                f"({alt_result.convergence.value}), so no comparison is possible"
            )
        else:
            differences = [
                _relative(
                    alt_result.values[name].magnitude,
                    finest_result.values[name].magnitude,
                )
                for name in CONVERGENCE_QOIS
                if name in alt_result.values and name in finest_result.values
            ]
            cross_method_max_rel_difference = max(differences) if differences else None
            cross_method_agrees = bool(
                cross_method_max_rel_difference is not None
                and cross_method_max_rel_difference <= tolerance_rel_tol
            )
            cross_method_detail = (
                f"{run.integration.method} and {cross_method} at "
                f"{ladder[-1].label} agree on every QoI to "
                f"{cross_method_max_rel_difference:.3e}. This establishes NO "
                f"validation level: both arms share this domain's right-hand "
                f"side, its analytic Jacobian and SciPy's step control, so a "
                f"shared error is invisible to the comparison"
            )

    return CSTRVerificationReport(
        rungs=tuple(rows),
        tolerance_independent=tolerance_independent,
        tolerance_detail=tolerance_detail,
        invariant_verified=invariant_verified,
        invariant_detail=invariant_detail,
        invariant_max_rel_error=invariant_max_rel_error,
        steady_state_verified=steady_state_verified,
        steady_state_detail=steady_state_detail,
        steady_state_rel_error=steady_state_rel_error,
        steady_states_found=steady_states_found,
        cross_method_agrees=cross_method_agrees,
        cross_method_detail=cross_method_detail,
        cross_method_max_rel_difference=cross_method_max_rel_difference,
        tolerance_rel_tol=tolerance_rel_tol,
        invariant_rel_tol=invariant_rel_tol,
        steady_state_rel_tol=steady_state_rel_tol,
    )


def _is_stationary(
    times: np.ndarray, concentration: np.ndarray, temperature: np.ndarray
) -> tuple[bool, str]:
    """Has the trajectory settled by the end of the horizon?

    Judged on the final tenth of the uniform sample: both states must move by
    less than ``STATIONARITY_REL_TOL`` relative over that window.
    """
    if times.size < 10:
        return False, "too few samples to judge stationarity"
    tail = max(int(times.size // 10), 2)
    window_t = temperature[-tail:]
    window_c = concentration[-tail:]
    temperature_drift = _relative(float(window_t[0]), float(window_t[-1]))
    concentration_drift = _relative(float(window_c[0]), float(window_c[-1]))
    worst = max(temperature_drift, concentration_drift)
    detail = (
        f"over the final {tail} of {times.size} samples the temperature moved "
        f"{temperature_drift:.3e} and the concentration {concentration_drift:.3e} "
        f"relatively; the stationarity threshold is {STATIONARITY_REL_TOL:.3e}"
    )
    return bool(worst <= STATIONARITY_REL_TOL), detail


# =====================================================================
# The stiffness measurement
# =====================================================================

@dataclass(frozen=True)
class StiffnessMeasurement:
    """How much more work an explicit method needs than a stiff one.

    Stiffness is *measured* rather than asserted. The ratio of right-hand-side
    evaluations between RK45 and the stiff production method is the operational
    definition: a problem is stiff exactly when an explicit method is forced to
    take steps far smaller than accuracy alone would require.

    The explicit arm is a measuring instrument and never a production method.
    It is given the same budget as the stiff arm, and exhausting that budget is
    itself a valid measurement — it means the ratio is at least the budget over
    the stiff arm's work.
    """

    stiff_method: str
    stiff_evaluations: int
    stiff_completed: bool
    explicit_method: str
    explicit_evaluations: int
    explicit_completed: bool
    explicit_outcome: str

    @property
    def work_ratio(self) -> float:
        if self.stiff_evaluations <= 0:
            return float("nan")
        return self.explicit_evaluations / self.stiff_evaluations

    @property
    def is_lower_bound(self) -> bool:
        """True when the explicit arm was stopped rather than finishing."""
        return not self.explicit_completed

    def to_dict(self) -> dict[str, Any]:
        return {
            "stiff_method": self.stiff_method,
            "stiff_evaluations": self.stiff_evaluations,
            "stiff_completed": self.stiff_completed,
            "explicit_method": self.explicit_method,
            "explicit_evaluations": self.explicit_evaluations,
            "explicit_completed": self.explicit_completed,
            "explicit_outcome": self.explicit_outcome,
            "work_ratio": self.work_ratio,
            "work_ratio_is_lower_bound": self.is_lower_bound,
        }


def measure_stiffness(
    run: "ReactorRun", *, explicit_method: str = "RK45", run_id_prefix: str = "cstr-stiff"
) -> StiffnessMeasurement:
    """Run the same physics through the stiff method and an explicit probe."""
    from .problem import build_cstr_problem
    from .solver import CSTRSolver, solve_reactor

    def work(method: str, label: str) -> tuple[int, bool, str]:
        variant = run.with_integration(run.integration.with_method(method))
        problem = build_cstr_problem(variant, problem_id=f"{run_id_prefix}-{label}")
        result = solve_reactor(
            variant,
            run_id=f"{run_id_prefix}-{label}",
            solver=CSTRSolver(),
            problem=problem,
        )
        numerics = dict(result.metadata.get("numerics", {}))
        return (
            int(numerics.get("rhs_evaluations", 0)),
            bool(result.values),
            str(numerics.get("outcome", "unknown")),
        )

    stiff_evaluations, stiff_completed, _ = work(run.integration.method, "stiff")
    explicit_evaluations, explicit_completed, explicit_outcome = work(
        explicit_method, "explicit"
    )
    return StiffnessMeasurement(
        stiff_method=run.integration.method,
        stiff_evaluations=stiff_evaluations,
        stiff_completed=stiff_completed,
        explicit_method=explicit_method,
        explicit_evaluations=explicit_evaluations,
        explicit_completed=explicit_completed,
        explicit_outcome=explicit_outcome,
    )
