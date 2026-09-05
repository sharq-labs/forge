"""CSTRSolver — a ScientificSolver over SciPy's stiff initial-value integrators.

The five lifecycle stages stay strictly separated, exactly as the Electrical and
Thermal domains keep them:

``supports`` (capability question, never executes)
→ ``prepare`` (build the right-hand side, the analytic Jacobian, and the
   declaration's validity assessment)
→ ``solve`` (SciPy adaptive implicit integration, raw floats)
→ ``extract_metrics`` (units restored)
→ ``validate`` (independent checks)

WHY BDF, AND WHY RADAU AS THE SECOND ARM
-----------------------------------------
The system is stiff: over the operating range ``dk/dT = k E/(R T**2)`` makes
the chemical mode orders of magnitude faster than the flow mode ``q/V`` during
ignition, while the horizon of interest is set by the slow mode. An explicit
method must resolve the fast mode for stability even where it is dynamically
irrelevant, so its cost is set by the stiffness ratio rather than by the
accuracy wanted. (The derivative rises steeply across the envelope but does not
grow without bound: ``k -> k0`` and ``dk/dT -> 0`` as ``T -> infinity``. See
:mod:`problem`.)

BDF is the production method. Variable-order (1-5) backward differentiation
with a quasi-Newton corrector and an analytic Jacobian: the standard choice for
stiff chemical kinetics, and cheap per step because it reuses factorizations
across steps.

Its stability property, stated accurately: BDF is **stiffly stable** in Gear's
sense — its stability region contains the whole negative real axis and a wedge
around it, so strongly damped modes are integrated at step sizes set by
accuracy rather than by stability. It is A-stable only at orders 1-2; at the
higher orders SciPy selects it is A(alpha)-stable with alpha shrinking as the
order rises. It is **not** L-stable at every order it uses, and this module
previously said it was.

Radau (5th-order Radau IIA, fully implicit Runge-Kutta) is the cross-method
arm. It is a genuinely different family — one-step rather than multistep, so
its error propagation and its startup behaviour have nothing structural in
common with BDF's — and it *is* both A-stable and L-stable. Damping rather than
oscillating on the fast chemical mode is what this problem requires, and it is
exactly what rules out the trapezoidal/Crank-Nicolson family, which is A-stable
but not L-stable and rings on stiff modes.

RK45 is admitted for one purpose only: as a measuring instrument. The ratio of
its right-hand-side evaluations to BDF's is how this domain evidences that a
regime is stiff, rather than asserting it. It is never a production method for
a stiff regime, and nothing here selects a method.

LSODA is deliberately excluded. It switches between stiff and non-stiff
internally, so a work count from it cannot be attributed to one method, and it
would corrupt the only stiffness measurement this domain has.

WHAT THIS SOLVER DOES NOT CLAIM
--------------------------------
``validate`` never awards ``NUMERICALLY_CONVERGED``. ``solve_ivp`` reporting
``status == 0`` means its local error estimate stayed under the tolerance it
was given — it is the integrator's opinion of its own step control, and it is
equally confident at rtol=1e-2 and rtol=1e-12. Numerical adequacy is a claim
about *tolerance independence*, which needs more than one solve, so it lives in
:mod:`validation` and is a claim about a sequence. The per-solve report says so
with an explicit NOT_RUN check rather than staying silent about it.

Nor does a successful integration mean a physically admissible one. A stiff
solve at loose tolerance can undershoot the concentration below zero and still
report success, and that result is executed-but-unusable rather than failed.
The per-solve report carries that as a FAILing state-admissibility check, which
is what makes ``ScientificResult.is_usable`` False while ``convergence``
correctly remains CONVERGED.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
from scipy.integrate import solve_ivp

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
from .errors import (
    IntegrationBudgetExceeded,
    ReactorBindingError,
    ReactorConfigurationError,
)
from .problem import (
    CA_FINAL_METRIC,
    CONVERSION_METRIC,
    CSTR_MODEL,
    CSTR_MODELS,
    KINETICS_CSTR_NONISOTHERMAL,
    METRIC_UNITS,
    T_AT_MAX_METRIC,
    T_FINAL_METRIC,
    T_MAX_METRIC,
    MOLAR_GAS_CONSTANT,
    GAS_CONSTANT_UNIT,
    ReactorRun,
    build_cstr_problem,
    cstr_solver_capabilities,
    verify_problem_matches_run,
)
from .validation import CSTRValidationSettings, build_validation_report

SOLVER_ID = "kinetics.cstr.scipy_implicit_ivp"
SOLVER_VERSION = "0.1.0"
BACKEND = "scipy.integrate.solve_ivp"

_R = MOLAR_GAS_CONSTANT.magnitude_in(GAS_CONSTANT_UNIT)


@dataclass
class _EvaluationCounter:
    """Right-hand-side evaluation count and the budget it must respect.

    ``completed`` counts evaluations the budget ADMITTED. The check happens
    before the count is incremented, so a budget of N admits exactly N
    evaluations and the (N+1)-th call is refused without being counted as work.

    The increment sits at admission rather than after the right-hand side
    returns because the body below cannot raise -- it returns finite values or
    NaN -- so "admitted" and "carried out" are the same set here.
    """

    budget: int
    completed: int = 0
    attempted: int = 0
    non_finite_events: int = 0
    non_positive_temperature_events: int = 0

    def charge(self, t: float) -> None:
        if self.completed >= self.budget:
            self.attempted = self.completed + 1
            raise IntegrationBudgetExceeded(
                f"right-hand-side evaluation budget of {self.budget} exhausted "
                f"at t = {t:.6g} s; the integration was still progressing when "
                f"it was stopped",
                completed=self.completed,
                attempted=self.attempted,
                budget=self.budget,
                t=t,
            )
        self.completed += 1
        self.attempted = self.completed


@dataclass(frozen=True)
class PreparedCSTRSystem:
    """The assembled right-hand side, its Jacobian, and the declaration."""

    run: ReactorRun
    rhs: Any                    # callable (t, y) -> ndarray
    jacobian: Any               # callable (t, y) -> ndarray
    counter: _EvaluationCounter
    output_grid: np.ndarray     # uniform reporting/checking grid on [0, t_end]

    @property
    def initial_state(self) -> np.ndarray:
        return np.array(
            [self.run.ca0_mol_per_m3, self.run.t0_k], dtype=np.float64
        )


def assemble(run: ReactorRun) -> PreparedCSTRSystem:
    """Build the right-hand side and analytic Jacobian for one run.

    Closures over plain floats: this is the numeric kernel, and it is the one
    place in the domain where unit-carrying quantities have been left behind on
    purpose. They come back in ``extract_metrics``.

    The Jacobian is supplied analytically rather than left to finite
    differences. For a stiff system the Newton corrector's convergence is
    governed by Jacobian quality, and a differenced Arrhenius derivative is
    exactly where that quality is worst.
    """
    chemistry = run.chemistry
    operation = run.operation

    a = operation.dilution_rate_per_s
    caf = operation.caf_mol_per_m3
    tf = operation.tf_k
    tc = operation.tc_k
    beta = chemistry.beta_m3_k_per_mol
    gamma = run.gamma_per_s
    k0 = chemistry.k0_per_s
    energy = chemistry.e_j_per_mol

    counter = _EvaluationCounter(budget=run.integration.max_rhs_evaluations)

    def rate_constant(temperature: float) -> float:
        # Outside the domain of the model the Arrhenius factor is not merely
        # inaccurate, it is undefined. Returning NaN lets the integrator reject
        # the step rather than continuing on a fabricated number.
        if not np.isfinite(temperature) or temperature <= 0.0:
            return float("nan")
        with np.errstate(over="ignore"):
            return float(k0 * np.exp(-energy / (_R * temperature)))

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        counter.charge(float(t))
        concentration = float(y[0])
        temperature = float(y[1])
        if temperature <= 0.0 or not np.isfinite(temperature):
            counter.non_positive_temperature_events += 1
        k = rate_constant(temperature)
        reaction = k * concentration
        d_concentration = a * (caf - concentration) - reaction
        d_temperature = (
            a * (tf - temperature) + beta * reaction - gamma * (temperature - tc)
        )
        out = np.array([d_concentration, d_temperature], dtype=np.float64)
        if not np.all(np.isfinite(out)):
            counter.non_finite_events += 1
        return out

    def jacobian(t: float, y: np.ndarray) -> np.ndarray:
        concentration = float(y[0])
        temperature = float(y[1])
        k = rate_constant(temperature)
        if not np.isfinite(k) or temperature <= 0.0:
            return np.full((2, 2), np.nan, dtype=np.float64)
        with np.errstate(over="ignore", invalid="ignore"):
            dk_dt = k * energy / (_R * temperature * temperature)
        return np.array(
            [
                [-(a + k), -concentration * dk_dt],
                [beta * k, -(a + gamma) + beta * concentration * dk_dt],
            ],
            dtype=np.float64,
        )

    grid = np.linspace(
        0.0, operation.end_time_s, int(run.integration.n_output_points)
    )
    return PreparedCSTRSystem(
        run=run, rhs=rhs, jacobian=jacobian, counter=counter, output_grid=grid
    )


@dataclass
class CSTRSolver:
    """Transient non-isothermal CSTR solver satisfying the ScientificSolver protocol."""

    settings: CSTRValidationSettings = field(default_factory=CSTRValidationSettings)
    _runs: dict[str, ReactorRun] = field(default_factory=dict, repr=False)

    # ---- identity / capability ------------------------------------------
    @property
    def identity(self) -> SolverIdentity:
        import scipy

        return SolverIdentity(
            SOLVER_ID, SOLVER_VERSION, backend=f"{BACKEND}/scipy-{scipy.__version__}"
        )

    @property
    def capabilities(self):
        return cstr_solver_capabilities()

    def solver_settings(self, run: ReactorRun) -> SolverSettings:
        """Numerical settings actually used, recorded for provenance."""
        return SolverSettings(
            tolerances=run.integration.as_tolerance_mapping(),
            options={
                "method": run.integration.method,
                "jacobian": "analytic",
                "n_output_points": run.integration.n_output_points,
                "dense_output": True,
                "backend": BACKEND,
            },
        )

    # ---- domain-local run binding ----------------------------------------
    def bind_run(self, run: ReactorRun, problem_id: str) -> None:
        """Associate a reactor run with the problem describing it.

        Rebinding the same physics at a different tolerance or method is
        allowed — that is what the tolerance ladder and the cross-method arm
        do. Rebinding *different physics* to the same problem id is refused,
        because two results would then claim one identity while describing
        different reactors.
        """
        if not isinstance(run, ReactorRun):
            raise ReactorConfigurationError("bind_run expects a ReactorRun")
        key = str(problem_id)
        existing = self._runs.get(key)
        if (
            existing is not None
            and existing.physics_fingerprint() != run.physics_fingerprint()
        ):
            raise ReactorBindingError(
                f"problem {key!r} is already bound to a different reactor "
                f"(bound {existing.physics_fingerprint()[:12]}…, incoming "
                f"{run.physics_fingerprint()[:12]}…); rebinding to different "
                f"physics is refused — use a distinct problem id"
            )
        self._runs[key] = run

    def bound_run(self, problem_id: str) -> ReactorRun | None:
        return self._runs.get(str(problem_id))

    # ---- lifecycle --------------------------------------------------------
    def supports(self, problem: ScientificProblem) -> bool:
        """Capability question only — never attempts a solve."""
        if not isinstance(problem, ScientificProblem):
            return False
        declared = {capability.name for capability in self.capabilities}
        if not set(problem.required_capabilities).issubset(declared):
            return False
        domain_models = {model.model_id for model in CSTR_MODELS}
        referenced = {reference.model_id for reference in problem.models}
        if not referenced & domain_models:
            return False
        return KINETICS_CSTR_NONISOTHERMAL.name in problem.required_capabilities

    def prepare(self, problem: ScientificProblem) -> PreparedSolve:
        run = self.bound_run(problem.problem_id)
        if run is None:
            raise ReactorConfigurationError(
                f"no reactor bound for problem {problem.problem_id!r}; call "
                f"bind_run() first — the universal IR carries no chemistry"
            )
        if not self.supports(problem):
            raise ReactorConfigurationError(
                f"problem {problem.problem_id!r} is not a transient "
                f"non-isothermal CSTR analysis"
            )
        verify_problem_matches_run(problem, run)

        # The declaration is assessed against the MODEL's own validity domain
        # here, before any integration. The constructors already refuse the
        # gross violations; this records the model's verdict as evidence rather
        # than relying on the constructors having been the only gate.
        assessment = CSTR_MODEL.assess_validity(run.validity_context())

        system = assemble(run)
        integration = run.integration
        return PreparedSolve(
            problem=problem,
            solver=self.identity,
            settings=self.solver_settings(run),
            payload=system,
            notes=(
                f"method={integration.method} rtol={integration.rtol:.3g} "
                f"atol=({integration.atol_concentration:.3g} mol/m**3, "
                f"{integration.atol_temperature:.3g} K) "
                f"budget={integration.max_rhs_evaluations} rhs evaluations",
                f"tau={run.operation.residence_time_s:.6g} s, "
                f"gamma={run.gamma_per_s:.6g} 1/s, "
                f"adiabatic_rise={run.adiabatic_rise_k:.6g} K, "
                f"Da(T_f)={run.damkohler_at_feed_temperature:.6g}",
                f"model validity assessment: {assessment.status.value}",
            ),
        )

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        """Integrate, and classify what actually happened.

        Five outcomes are kept distinct, because collapsing them is how the
        difference between "the reactor cannot be simulated" and "this run was
        given too small a budget" gets lost:

        MAX_ITERATIONS  the explicit evaluation budget was exhausted while the
                        integration was still progressing
        FAILED          the backend raised, or reported an input/step failure
        NOT_CONVERGED   the step size collapsed below what the arithmetic can
                        represent (SciPy status -1)
        DIVERGED        the trajectory went non-finite
        CONVERGED       the integrator finished the horizon under its tolerance
        """
        system: PreparedCSTRSystem = prepared.payload
        run = system.run
        integration = run.integration
        started = time.perf_counter()

        common: dict[str, Any] = {
            "method": integration.method,
            "rtol": integration.rtol,
            "atol_concentration": integration.atol_concentration,
            "atol_temperature": integration.atol_temperature,
            "rhs_budget": integration.max_rhs_evaluations,
            "residence_time_s": run.operation.residence_time_s,
            "end_time_s": run.operation.end_time_s,
            "gamma_per_s": run.gamma_per_s,
            "adiabatic": run.operation.is_adiabatic,
            "physics_fingerprint": run.physics_fingerprint(),
        }

        # An analytic Jacobian is only used by the implicit methods; passing it
        # to RK45 is an error in SciPy, and the probe must not be handed an
        # advantage the production method does not also have.
        kwargs: dict[str, Any] = {}
        if integration.is_stiff_method:
            kwargs["jac"] = system.jacobian

        try:
            solution = solve_ivp(
                system.rhs,
                (0.0, run.operation.end_time_s),
                system.initial_state,
                method=integration.method,
                rtol=integration.rtol,
                atol=np.array(integration.atol_vector, dtype=np.float64),
                dense_output=True,
                **kwargs,
            )
        except IntegrationBudgetExceeded as exc:
            return RawSolverOutput(
                convergence=ConvergenceState.MAX_ITERATIONS,
                warnings=(
                    f"right-hand-side evaluation budget of {exc.budget} "
                    f"exhausted at t = {exc.t:.6g} s of "
                    f"{run.operation.end_time_s:.6g} s",
                ),
                # The work the run actually rests on, never the refused call.
                iterations=exc.completed,
                wall_seconds=time.perf_counter() - started,
                diagnostics={
                    **common,
                    "outcome": "rhs_budget_exhausted",
                    "rhs_evaluations": exc.completed,
                    "rhs_evaluations_completed": exc.completed,
                    "rhs_evaluations_attempted": exc.attempted,
                    "abort_time_s": exc.t,
                    "fraction_of_horizon_completed": (
                        exc.t / run.operation.end_time_s
                        if run.operation.end_time_s
                        else 0.0
                    ),
                    "non_finite_rhs_events": system.counter.non_finite_events,
                    "non_positive_temperature_events":
                        system.counter.non_positive_temperature_events,
                },
            )
        except Exception as exc:  # backend raised for any other reason
            return RawSolverOutput(
                convergence=ConvergenceState.FAILED,
                warnings=(f"integrator raised {type(exc).__name__}",),
                iterations=system.counter.completed,
                wall_seconds=time.perf_counter() - started,
                diagnostics={
                    **common,
                    "outcome": "backend_exception",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "rhs_evaluations": system.counter.completed,
                    "rhs_evaluations_completed": system.counter.completed,
                    "rhs_evaluations_attempted": system.counter.attempted,
                    "non_finite_rhs_events": system.counter.non_finite_events,
                },
            )

        wall = time.perf_counter() - started
        times = np.asarray(solution.t, dtype=np.float64)
        states = np.asarray(solution.y, dtype=np.float64)
        finite_trajectory = bool(np.all(np.isfinite(states)))

        # SciPy's own accounting, kept alongside our budget counter. They
        # measure the same thing by different routes, and a disagreement is
        # itself worth seeing.
        work = {
            "rhs_evaluations": int(system.counter.completed),
            "rhs_evaluations_completed": int(system.counter.completed),
            "rhs_evaluations_attempted": int(system.counter.attempted),
            "scipy_nfev": int(getattr(solution, "nfev", 0)),
            "scipy_njev": int(getattr(solution, "njev", 0)),
            "scipy_nlu": int(getattr(solution, "nlu", 0)),
            "accepted_steps": int(times.size - 1) if times.size else 0,
            "non_finite_rhs_events": system.counter.non_finite_events,
            "non_positive_temperature_events":
                system.counter.non_positive_temperature_events,
        }

        if solution.status == -1 or not finite_trajectory:
            # A partial trajectory is real evidence and is preserved: this is
            # the one layer where non-finite values may be recorded honestly.
            convergence = (
                ConvergenceState.DIVERGED
                if not finite_trajectory
                else ConvergenceState.NOT_CONVERGED
            )
            reached = float(times[-1]) if times.size else 0.0
            return RawSolverOutput(
                convergence=convergence,
                warnings=(
                    f"{solution.message}"
                    if solution.status == -1
                    else "trajectory contains non-finite values",
                ),
                iterations=int(system.counter.completed),
                wall_seconds=wall,
                diagnostics={
                    **common,
                    **work,
                    "outcome": (
                        "step_size_collapse"
                        if solution.status == -1
                        else "non_finite_trajectory"
                    ),
                    "scipy_status": int(solution.status),
                    "scipy_message": str(solution.message),
                    "reached_time_s": reached,
                    "fraction_of_horizon_completed": (
                        reached / run.operation.end_time_s
                        if run.operation.end_time_s
                        else 0.0
                    ),
                    "trajectory_finite": finite_trajectory,
                    "partial_time_s": [float(v) for v in times],
                    "partial_concentration_mol_per_m3":
                        [float(v) for v in states[0]],
                    "partial_temperature_k": [float(v) for v in states[1]],
                },
            )

        if solution.status != 0:
            return RawSolverOutput(
                convergence=ConvergenceState.FAILED,
                warnings=(str(solution.message),),
                iterations=int(system.counter.completed),
                wall_seconds=wall,
                diagnostics={
                    **common,
                    **work,
                    "outcome": "unexpected_status",
                    "scipy_status": int(solution.status),
                    "scipy_message": str(solution.message),
                },
            )

        # --- completed horizon -------------------------------------------
        concentration = states[0]
        temperature = states[1]

        # The uniform grid is used for the invariant/conservation checks and
        # for cross-run comparison; it never influenced the integration path.
        grid = system.output_grid
        sampled = np.asarray(solution.sol(grid), dtype=np.float64)

        # THE ENVELOPE IS ASSESSED OVER BOTH SAMPLINGS, NOT JUST THE NODES.
        #
        # An adaptive integrator only guarantees its error estimate AT the
        # accepted nodes. Between two nodes the interpolant can carry the state
        # somewhere neither node shows — and for a stiff ignition the nodes can
        # straddle an excursion. Assessing physical admissibility from the
        # nodes alone would therefore let a trajectory leave the model's
        # validity envelope in between and be reported as never having left it.
        #
        # The dense output is already computed for the invariant check, so
        # unioning the two samplings is free. What this buys is a strictly
        # better *lower bound* on the true excursion.
        #
        # WHAT IS NOT CLAIMED: this is not the exact continuous extremum. No
        # interpolant-root-finding or Chebyshev bound is performed, so the
        # reported extrema remain a sampled minimum/maximum over
        # (accepted nodes union dense grid). A narrow enough excursion between
        # two adjacent dense samples would still be missed, and the diagnostic
        # names say "sampled" so a reader is not invited to over-read them.
        all_time = np.concatenate((times, grid))
        all_concentration = np.concatenate((concentration, sampled[0]))
        all_temperature = np.concatenate((temperature, sampled[1]))
        peak_index = int(np.argmax(all_temperature))

        caf = run.operation.caf_mol_per_m3
        final_concentration = float(concentration[-1])
        conversion = (
            (caf - final_concentration) / caf if caf > 0.0 else 0.0
        )

        values = {
            CA_FINAL_METRIC: final_concentration,
            T_FINAL_METRIC: float(temperature[-1]),
            # Maximum over the accepted steps AND the dense sample. The
            # accepted steps cluster where the solution moves fastest, so they
            # resolve a sharp ignition that a uniform grid alone would miss;
            # the dense sample covers the quiet stretches where the integrator
            # takes long steps. Neither sampling dominates the other, so the
            # peak is read from their union.
            T_MAX_METRIC: float(all_temperature[peak_index]),
            T_AT_MAX_METRIC: float(all_time[peak_index]),
            CONVERSION_METRIC: float(conversion),
        }

        return RawSolverOutput(
            convergence=ConvergenceState.CONVERGED,
            values=values,
            residuals={},
            iterations=int(system.counter.completed),
            wall_seconds=wall,
            diagnostics={
                **common,
                **work,
                "outcome": "completed_horizon",
                "scipy_status": int(solution.status),
                "scipy_message": str(solution.message),
                "trajectory_finite": True,
                "reached_time_s": float(times[-1]),
                "fraction_of_horizon_completed": 1.0,
                # Sampled extrema over accepted nodes UNION the dense grid.
                # A lower bound on the true continuous excursion, not the
                # exact extremum — see the comment above the union.
                "min_concentration_mol_per_m3": float(np.min(all_concentration)),
                "max_concentration_mol_per_m3": float(np.max(all_concentration)),
                "min_temperature_k": float(np.min(all_temperature)),
                "max_temperature_k": float(np.max(all_temperature)),
                "envelope_sampling": (
                    "accepted solver nodes union dense output on the uniform "
                    "grid; a sampled bound, not an exact continuous extremum"
                ),
                "envelope_sample_count": int(all_temperature.size),
                # The node-only extrema, kept so the contribution of dense
                # sampling is visible rather than merged away.
                "max_temperature_k_nodes_only": float(np.max(temperature)),
                "min_concentration_mol_per_m3_nodes_only": float(
                    np.min(concentration)
                ),
                "peak_time_s": float(all_time[peak_index]),
                "concentration_ceiling_mol_per_m3":
                    run.concentration_ceiling_mol_per_m3,
                # The uniform sample used by the conservation/invariant checks.
                "grid_time_s": [float(v) for v in grid],
                "grid_concentration_mol_per_m3": [float(v) for v in sampled[0]],
                "grid_temperature_k": [float(v) for v in sampled[1]],
            },
        )

    def extract_metrics(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> dict[str, Quantity]:
        """Restore units. This is the boundary back into the unit-aware world.

        A run that did not complete the horizon yields no metrics: a partial
        trajectory has no "final concentration", and inventing one from the
        last point reached would report a number for a question that was never
        answered. The partial trajectory itself survives in the raw
        diagnostics, where it belongs.
        """
        if not raw.succeeded:
            return {}
        return {
            name: Quantity(value, METRIC_UNITS[name])
            for name, value in raw.values.items()
        }

    def validate(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationReport:
        system: PreparedCSTRSystem = prepared.payload
        return build_validation_report(system.run, raw, self.settings)


# =====================================================================
# Public wrapper
# =====================================================================

@dataclass(frozen=True)
class TransientTrajectorySample:
    """The uniform dense sample of one solve. Domain-local and transient.

    This is the trajectory the verification checks read. It is deliberately NOT
    part of :class:`ScientificResult`: a record that carried thousands of points
    would make every serialized artifact unreadable, and the arrays are evidence
    for one gate rather than something a reader of the result needs.

    Empty when the solve did not complete the horizon — a partial trajectory is
    preserved in the raw diagnostics instead, where its incompleteness is
    explicit.
    """

    time_s: np.ndarray
    concentration_mol_per_m3: np.ndarray
    temperature_k: np.ndarray

    @classmethod
    def empty(cls) -> "TransientTrajectorySample":
        blank = np.array([], dtype=np.float64)
        return cls(
            time_s=blank,
            concentration_mol_per_m3=blank.copy(),
            temperature_k=blank.copy(),
        )

    @classmethod
    def from_diagnostics(
        cls, diagnostics: Mapping[str, Any]
    ) -> "TransientTrajectorySample":
        return cls(
            time_s=np.asarray(
                diagnostics.get("grid_time_s", ()), dtype=np.float64
            ),
            concentration_mol_per_m3=np.asarray(
                diagnostics.get("grid_concentration_mol_per_m3", ()),
                dtype=np.float64,
            ),
            temperature_k=np.asarray(
                diagnostics.get("grid_temperature_k", ()), dtype=np.float64
            ),
        )

    @property
    def is_empty(self) -> bool:
        return self.time_s.size == 0


@dataclass(frozen=True)
class VerificationSolveBundle:
    """One solve's public result plus the transient data a gate needs from it.

    WHY THIS TYPE EXISTS
    ---------------------
    The verification gate needs two things from the finest tolerance rung: the
    compact :class:`ScientificResult`, and the dense trajectory that the
    invariant and stationarity checks are computed over. The result deliberately
    discards the trajectory, so the gate used to recover it by integrating the
    same problem a second time — measured at 9.56 s of the 69.97 s a profiled
    gate spent, for an integration whose answer it already had.

    Carrying the arrays here instead keeps the duplication out without widening
    the universal result contract: the bundle is domain-local, never serialized,
    and is dropped as soon as the gate has read it.
    """

    result: ScientificResult
    trajectory: TransientTrajectorySample
    #: Right-hand-side evaluations the solve actually rested on.
    rhs_evaluations: int


def solve_reactor(
    run: ReactorRun,
    *,
    run_id: str,
    solver: CSTRSolver | None = None,
    problem: ScientificProblem | None = None,
    software_version: str = "engcore.domains.kinetics.cstr/0.1.0",
    source_commit: str | None = None,
    core_baseline_commit: str | None = None,
    timestamp: str | None = None,
    environment: Mapping[str, str] | None = None,
    parent_run_id: str | None = None,
) -> ScientificResult:
    """Run the full contract lifecycle for one reactor and return a result.

    Orchestration only: every stage goes through the protocol.

    TWO COMMIT IDENTITIES, AND THEY ARE NOT INTERCHANGEABLE
    --------------------------------------------------------
    ``source_commit``         the revision of THIS repository that actually
                              executed and produced the numbers. It is what
                              ``ProvenanceRecord.git_commit`` means: "to
                              re-derive this result, check out that revision".
    ``core_baseline_commit``  the frozen Core revision the domain was built
                              against. It is context, not execution identity,
                              and it lives in provenance metadata.

    Conflating them is not a cosmetic error. K1 originally passed the frozen
    Core V0.2 baseline into ``git_commit`` — a commit that predates this solver
    entirely, so the provenance record pointed at a revision where the code
    that produced the result did not yet exist. Anyone trying to reproduce it
    from that field would check out a tree with no kinetics domain in it.

    Both are caller-supplied. Neither is harvested from git here, and nothing
    in the Scientific Core harvests either: auto-collecting machine or repo
    state would be both a privacy problem and a determinism problem, which is
    the position ``ProvenanceRecord`` already takes.

    The large trajectory arrays are deliberately excluded from the result's
    metadata — they are evidence for the validation stage, not a diagnostic a
    reader of the result needs, and carrying thousands of points into every
    record would make the serialized artifacts unreadable. Everything scalar
    that describes how the solve went does survive, because E1 recorded that
    discarding it forces an experiment to re-derive it with a second solve.

    A caller that genuinely needs the trajectory — the verification gate — uses
    :func:`solve_reactor_bundle` rather than integrating the same problem twice.
    """
    return solve_reactor_bundle(
        run,
        run_id=run_id,
        solver=solver,
        problem=problem,
        software_version=software_version,
        source_commit=source_commit,
        core_baseline_commit=core_baseline_commit,
        timestamp=timestamp,
        environment=environment,
        parent_run_id=parent_run_id,
    ).result


def solve_reactor_bundle(
    run: ReactorRun,
    *,
    run_id: str,
    solver: CSTRSolver | None = None,
    problem: ScientificProblem | None = None,
    software_version: str = "engcore.domains.kinetics.cstr/0.1.0",
    source_commit: str | None = None,
    core_baseline_commit: str | None = None,
    timestamp: str | None = None,
    environment: Mapping[str, str] | None = None,
    parent_run_id: str | None = None,
) -> VerificationSolveBundle:
    """As :func:`solve_reactor`, but also hands back the transient trajectory.

    Identical lifecycle and an identical :class:`ScientificResult` — the only
    difference is that the dense sample this solve already computed is returned
    instead of being dropped, so a caller that needs it does not integrate the
    same problem a second time.
    """
    solver = solver or CSTRSolver()
    problem = problem or build_cstr_problem(run)
    verify_problem_matches_run(problem, run)
    solver.bind_run(run, problem.problem_id)

    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    report = solver.validate(prepared, raw)

    model_identities = tuple((m.model_id, m.version) for m in CSTR_MODELS)
    assumptions = CSTR_MODEL.assumptions

    inputs = {
        "k0": run.chemistry.k0,
        "activation_energy": run.chemistry.activation_energy,
        "heat_of_reaction": run.chemistry.heat_of_reaction,
        "density": run.chemistry.density,
        "heat_capacity": run.chemistry.heat_capacity,
        "volume": run.operation.volume,
        "flow_rate": run.operation.flow_rate,
        "feed_concentration": run.operation.feed_concentration,
        "feed_temperature": run.operation.feed_temperature,
        "coolant_temperature": run.operation.coolant_temperature,
        "ua": run.operation.ua,
        "end_time": run.operation.end_time,
        "initial_concentration": run.initial_concentration,
        "initial_temperature": run.initial_temperature,
        "molar_gas_constant": MOLAR_GAS_CONSTANT,
    }

    bulky = {
        "grid_time_s",
        "grid_concentration_mol_per_m3",
        "grid_temperature_k",
        "partial_time_s",
        "partial_concentration_mol_per_m3",
        "partial_temperature_k",
    }
    diagnostics = {k: v for k, v in raw.diagnostics.items() if k not in bulky}

    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version=software_version,
        # The EXECUTING revision. Never the Core baseline — see the docstring.
        git_commit=source_commit,
        models=model_identities,
        solvers=((SOLVER_ID, SOLVER_VERSION),),
        inputs=inputs,
        assumptions=assumptions,
        tolerances=run.integration.as_tolerance_mapping(),
        environment=dict(environment or {}),
        timestamp=timestamp,
        parent_run_id=parent_run_id,
        metadata={
            "run_label": run.run_label,
            "physics_fingerprint": run.physics_fingerprint(),
            "integration_method": run.integration.method,
            "jacobian": "analytic",
            "backend": BACKEND,
            "solver_backend_identity": solver.identity.backend,
            "run_canonical": run.to_dict(),
            # Context, not execution identity. Recorded under its own name so
            # it can never be mistaken for the revision that ran.
            "core_baseline_commit": core_baseline_commit,
            "commit_identity_semantics": (
                "git_commit is the source revision that produced this result; "
                "core_baseline_commit is the frozen Core revision the domain "
                "was built against. They are different questions and are never "
                "the same field"
            ),
        },
    )

    result = ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        models=model_identities,
        solver=solver.identity,
        convergence=raw.convergence,
        validation=report,
        # No uncertainty quantification is performed by a single solve. The
        # tolerance ladder quantifies the numerical component and nothing here
        # quantifies the model component, so anything but UNKNOWN would be
        # fabrication.
        uncertainty={
            name: Uncertainty.unknown(
                "no uncertainty quantification performed by this solve; the "
                "numerical component is estimated by the tolerance gate and "
                "the model-form component is not estimated at all"
            )
            for name in metrics
        },
        assumptions=assumptions,
        warnings=raw.warnings,
        provenance=provenance,
        metadata={
            "run_label": run.run_label,
            "physics_fingerprint": run.physics_fingerprint(),
            "numerics": diagnostics,
            "iterations": raw.iterations,
            # Telemetry only. Never a scientific score.
            "wall_seconds_telemetry": raw.wall_seconds,
        },
    )

    # The trajectory is read off the raw output this solve already produced. It
    # rides alongside the result rather than inside it, and the caller drops it.
    return VerificationSolveBundle(
        result=result,
        trajectory=(
            TransientTrajectorySample.from_diagnostics(raw.diagnostics)
            if raw.succeeded
            else TransientTrajectorySample.empty()
        ),
        rhs_evaluations=int(raw.iterations or 0),
    )
