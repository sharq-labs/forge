"""Independent LSODA/ODEPACK verification route for the CSTR.

This module intentionally does *not* import or call cstr.solver.assemble, its
right-hand side, or its Jacobian.  It translates the ReactorRun directly into
an ODEPACK/LSODA problem through scipy.integrate.odeint.  The shared object is
the declared physical problem; preprocessing, numerical method,
implementation, and backend are all distinct from the production
solve_ivp/BDF route.

This is a verification implementation, not the production integrator and not a
replacement for the BDF tolerance ladder.
"""

from __future__ import annotations

import math
import time
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.integrate import ODEintWarning, odeint

from ....scientific.ir.problem import ScientificProblem
from ....scientific.results.validation import ValidationReport
from ....scientific.solvers.protocol import (
    ConvergenceState,
    DeclaredSupport,
    PreparedSolve,
    RawSolverOutput,
    SolverIdentity,
    SolverSettings,
)
from ....scientific.units.quantity import Quantity
from .errors import IntegrationBudgetExceeded, ReactorBindingError, ReactorConfigurationError
from .problem import (
    CA_FINAL_METRIC,
    CONVERSION_METRIC,
    CSTR_MODEL,
    CSTR_MODELS,
    GAS_CONSTANT_UNIT,
    KINETICS_CSTR_NONISOTHERMAL,
    METRIC_UNITS,
    MOLAR_GAS_CONSTANT,
    T_AT_MAX_METRIC,
    T_FINAL_METRIC,
    T_MAX_METRIC,
    ReactorRun,
    cstr_solver_capabilities,
    verify_problem_matches_run,
)
from .validation import CSTRValidationSettings, build_validation_report

SOLVER_ID = "kinetics.cstr.odepack_lsoda_independent"
SOLVER_VERSION = "0.1.0"
BACKEND = "scipy.integrate.odeint/odepack-lsoda"

_R = MOLAR_GAS_CONSTANT.magnitude_in(GAS_CONSTANT_UNIT)


@dataclass(frozen=True)
class IndependentParameters:
    dilution_rate_per_s: float
    feed_concentration_mol_per_m3: float
    feed_temperature_k: float
    coolant_temperature_k: float
    beta_m3_k_per_mol: float
    gamma_per_s: float
    k0_per_s: float
    activation_energy_j_per_mol: float
    initial_concentration_mol_per_m3: float
    initial_temperature_k: float
    end_time_s: float
    n_output_points: int
    rtol: float
    atol_concentration: float
    atol_temperature: float
    rhs_budget: int


def independent_parameters(run: ReactorRun) -> IndependentParameters:
    """Translate declarations independently of the production assembler."""
    if not isinstance(run, ReactorRun):
        raise ReactorConfigurationError("independent LSODA route expects a ReactorRun")
    return IndependentParameters(
        dilution_rate_per_s=run.operation.flow_rate.magnitude_in("meter**3/second")
        / run.operation.volume.magnitude_in("meter**3"),
        feed_concentration_mol_per_m3=run.operation.feed_concentration.magnitude_in(
            "mol/meter**3"
        ),
        feed_temperature_k=run.operation.feed_temperature.magnitude_in("kelvin"),
        coolant_temperature_k=run.operation.coolant_temperature.magnitude_in("kelvin"),
        beta_m3_k_per_mol=(
            -run.chemistry.heat_of_reaction.magnitude_in("joule/mol")
            / (
                run.chemistry.density.magnitude_in("kg/meter**3")
                * run.chemistry.heat_capacity.magnitude_in("joule/kg/kelvin")
            )
        ),
        gamma_per_s=(
            run.operation.ua.magnitude_in("watt/kelvin")
            / (
                run.chemistry.density.magnitude_in("kg/meter**3")
                * run.operation.volume.magnitude_in("meter**3")
                * run.chemistry.heat_capacity.magnitude_in("joule/kg/kelvin")
            )
        ),
        k0_per_s=run.chemistry.k0.magnitude_in("1/second"),
        activation_energy_j_per_mol=run.chemistry.activation_energy.magnitude_in(
            "joule/mol"
        ),
        initial_concentration_mol_per_m3=run.initial_concentration.magnitude_in(
            "mol/meter**3"
        ),
        initial_temperature_k=run.initial_temperature.magnitude_in("kelvin"),
        end_time_s=run.operation.end_time.magnitude_in("second"),
        n_output_points=int(run.integration.n_output_points),
        rtol=float(run.integration.rtol),
        atol_concentration=float(run.integration.atol_concentration),
        atol_temperature=float(run.integration.atol_temperature),
        rhs_budget=int(run.integration.max_rhs_evaluations),
    )


@dataclass
class _IndependentCounter:
    budget: int
    completed: int = 0
    attempted: int = 0

    def charge(self, t: float) -> None:
        if self.completed >= self.budget:
            self.attempted = self.completed + 1
            raise IntegrationBudgetExceeded(
                f"independent LSODA RHS budget of {self.budget} exhausted at t={t:.6g}",
                completed=self.completed,
                attempted=self.attempted,
                budget=self.budget,
                t=t,
            )
        self.completed += 1
        self.attempted = self.completed


@dataclass(frozen=True)
class IndependentPreparedCSTR:
    run: ReactorRun
    parameters: IndependentParameters
    output_grid: np.ndarray


@dataclass
class IndependentLSODASolver(DeclaredSupport):
    """Second implementation of the CSTR equations using ODEPACK LSODA."""

    settings: CSTRValidationSettings = field(default_factory=CSTRValidationSettings)
    _runs: dict[str, ReactorRun] = field(default_factory=dict, repr=False)

    serves_capabilities = frozenset({KINETICS_CSTR_NONISOTHERMAL.name})
    served_models = CSTR_MODELS

    @property
    def identity(self) -> SolverIdentity:
        import scipy

        return SolverIdentity(
            SOLVER_ID,
            SOLVER_VERSION,
            backend=f"{BACKEND}/scipy-{scipy.__version__}",
        )

    @property
    def capabilities(self):
        return cstr_solver_capabilities()

    def bind_run(self, run: ReactorRun, problem_id: str) -> None:
        if not isinstance(run, ReactorRun):
            raise ReactorConfigurationError("bind_run expects ReactorRun")
        key = str(problem_id)
        existing = self._runs.get(key)
        if existing is not None and existing.physics_fingerprint() != run.physics_fingerprint():
            raise ReactorBindingError(
                f"problem {key!r} is already bound to different CSTR physics"
            )
        self._runs[key] = run

    def prepare(self, problem: ScientificProblem) -> PreparedSolve:
        run = self._runs.get(problem.problem_id)
        if run is None:
            raise ReactorConfigurationError(
                f"no reactor bound for problem {problem.problem_id!r}"
            )
        if not self.supports(problem):
            raise ReactorConfigurationError(
                f"problem {problem.problem_id!r} is not supported by the independent LSODA route"
            )
        verify_problem_matches_run(problem, run)
        params = independent_parameters(run)
        grid = np.linspace(0.0, params.end_time_s, params.n_output_points)
        return PreparedSolve(
            problem=problem,
            solver=self.identity,
            settings=SolverSettings(
                tolerances={
                    "rtol": params.rtol,
                    "atol_concentration": params.atol_concentration,
                    "atol_temperature": params.atol_temperature,
                },
                options={
                    "method": "LSODA",
                    "backend": BACKEND,
                    "jacobian": "ODEPACK internal finite difference",
                    "n_output_points": params.n_output_points,
                },
            ),
            payload=IndependentPreparedCSTR(run, params, grid),
            notes=(
                "independent verification route: separately translated RHS",
                "ODEPACK LSODA via scipy.integrate.odeint; no production assembler or Jacobian",
            ),
        )

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        payload: IndependentPreparedCSTR = prepared.payload
        run = payload.run
        p = payload.parameters
        counter = _IndependentCounter(p.rhs_budget)
        started = time.perf_counter()

        # Separate translation of the model equations. Do not replace this with
        # an import from solver.assemble: that would destroy the route's
        # preprocessing/implementation independence.
        def rhs(state, t):
            counter.charge(float(t))
            concentration = float(state[0])
            temperature = float(state[1])
            if not math.isfinite(temperature) or temperature <= 0.0:
                return [float("nan"), float("nan")]
            try:
                rate = p.k0_per_s * math.exp(
                    -p.activation_energy_j_per_mol / (_R * temperature)
                )
            except OverflowError:
                rate = float("inf")
            reaction = rate * concentration
            return [
                p.dilution_rate_per_s
                * (p.feed_concentration_mol_per_m3 - concentration)
                - reaction,
                p.dilution_rate_per_s * (p.feed_temperature_k - temperature)
                + p.beta_m3_k_per_mol * reaction
                - p.gamma_per_s * (temperature - p.coolant_temperature_k),
            ]

        initial = [
            p.initial_concentration_mol_per_m3,
            p.initial_temperature_k,
        ]
        caught: list[str] = []
        try:
            with warnings.catch_warnings(record=True) as records:
                warnings.simplefilter("always", ODEintWarning)
                states, info = odeint(
                    rhs,
                    initial,
                    payload.output_grid,
                    rtol=p.rtol,
                    atol=[p.atol_concentration, p.atol_temperature],
                    full_output=True,
                    mxstep=max(500, p.rhs_budget),
                    tfirst=False,
                )
                caught = [str(item.message) for item in records]
        except IntegrationBudgetExceeded as exc:
            return RawSolverOutput(
                convergence=ConvergenceState.MAX_ITERATIONS,
                iterations=exc.completed,
                wall_seconds=time.perf_counter() - started,
                warnings=(str(exc),),
                diagnostics={
                    "outcome": "rhs_budget_exhausted",
                    "integrator": "scipy.integrate.odeint",
                    "method": "LSODA",
                    "backend": BACKEND,
                    "jacobian": "ODEPACK internal finite difference",
                    "rhs_evaluations": exc.completed,
                    "rhs_evaluations_attempted": exc.attempted,
                },
            )
        except Exception as exc:
            return RawSolverOutput(
                convergence=ConvergenceState.FAILED,
                iterations=counter.completed,
                wall_seconds=time.perf_counter() - started,
                warnings=(f"odeint raised {type(exc).__name__}: {exc}",),
                diagnostics={
                    "outcome": "backend_exception",
                    "integrator": "scipy.integrate.odeint",
                    "method": "LSODA",
                    "backend": BACKEND,
                    "jacobian": "ODEPACK internal finite difference",
                    "rhs_evaluations": counter.completed,
                },
            )

        states = np.asarray(states, dtype=np.float64)
        message = str(info.get("message", ""))
        successful = (
            states.shape == (payload.output_grid.size, 2)
            and np.all(np.isfinite(states))
            and "successful" in message.lower()
            and not caught
        )
        if not successful:
            return RawSolverOutput(
                convergence=(
                    ConvergenceState.DIVERGED
                    if states.size and not np.all(np.isfinite(states))
                    else ConvergenceState.NOT_CONVERGED
                ),
                iterations=counter.completed,
                wall_seconds=time.perf_counter() - started,
                warnings=tuple(caught or (message or "LSODA did not report successful integration",)),
                diagnostics={
                    "outcome": "lsoda_not_successful",
                    "integrator": "scipy.integrate.odeint",
                    "method": "LSODA",
                    "backend": BACKEND,
                    "jacobian": "ODEPACK internal finite difference",
                    "rhs_evaluations": counter.completed,
                    "odeint_message": message,
                },
            )

        concentration = states[:, 0]
        temperature = states[:, 1]
        peak_index = int(np.argmax(temperature))
        caf = p.feed_concentration_mol_per_m3
        final_concentration = float(concentration[-1])
        conversion = (caf - final_concentration) / caf if caf > 0.0 else 0.0
        values = {
            CA_FINAL_METRIC: final_concentration,
            T_FINAL_METRIC: float(temperature[-1]),
            T_MAX_METRIC: float(temperature[peak_index]),
            T_AT_MAX_METRIC: float(payload.output_grid[peak_index]),
            CONVERSION_METRIC: float(conversion),
        }
        nfe = info.get("nfe")
        odepack_nfe = int(np.asarray(nfe).ravel()[-1]) if np.asarray(nfe).size else counter.completed
        return RawSolverOutput(
            convergence=ConvergenceState.CONVERGED,
            values=values,
            iterations=counter.completed,
            wall_seconds=time.perf_counter() - started,
            diagnostics={
                "outcome": "completed_horizon",
                "integrator": "scipy.integrate.odeint",
                "method": "LSODA",
                "backend": BACKEND,
                "jacobian": "ODEPACK internal finite difference",
                "rhs_evaluations": counter.completed,
                "odepack_nfe": odepack_nfe,
                "odeint_message": message,
                "trajectory_finite": True,
                "reached_time_s": float(payload.output_grid[-1]),
                "fraction_of_horizon_completed": 1.0,
                "min_concentration_mol_per_m3": float(np.min(concentration)),
                "max_concentration_mol_per_m3": float(np.max(concentration)),
                "min_temperature_k": float(np.min(temperature)),
                "max_temperature_k": float(np.max(temperature)),
                "envelope_sampling": (
                    "ODEPACK solution at the declared verification output grid; "
                    "a sampled bound, not an exact continuous extremum"
                ),
                "envelope_sample_count": int(temperature.size),
                "peak_time_s": float(payload.output_grid[peak_index]),
                "concentration_ceiling_mol_per_m3": run.concentration_ceiling_mol_per_m3,
                "grid_time_s": [float(v) for v in payload.output_grid],
                "grid_concentration_mol_per_m3": [float(v) for v in concentration],
                "grid_temperature_k": [float(v) for v in temperature],
            },
        )

    def extract_metrics(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> dict[str, Quantity]:
        if not raw.succeeded:
            return {}
        return {
            name: Quantity(value, METRIC_UNITS[name])
            for name, value in raw.values.items()
        }

    def validate(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationReport:
        payload: IndependentPreparedCSTR = prepared.payload
        return build_validation_report(payload.run, raw, self.settings)


__all__ = [
    "BACKEND",
    "IndependentLSODASolver",
    "IndependentParameters",
    "SOLVER_ID",
    "SOLVER_VERSION",
    "independent_parameters",
]
