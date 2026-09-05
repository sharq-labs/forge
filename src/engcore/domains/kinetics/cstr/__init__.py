"""Non-isothermal CSTR — a stiff nonlinear ODE domain on the frozen contracts.

The third scientific domain. It exists to answer one question: can a genuinely
stiff, nonlinear, failure-prone kinetics solver satisfy the existing
``ScientificSolver`` contract, report its failures honestly through the existing
result and validation vocabulary, and earn a defensible verification result —
without changing the Scientific Core?

    dC_A/dt = (q/V)(C_Af - C_A) - k(T) C_A
    dT/dt   = (q/V)(T_f  - T  ) + beta k(T) C_A - gamma (T - T_c)
    k(T)    = k0 exp(-E/(R T))

Every quantity carries a real physical unit. Temperature is an absolute
thermodynamic temperature in kelvin, because it appears inside an exponential
where a relative scale would be meaningless.

WHAT THIS DOMAIN ADDS THAT THE EARLIER TWO COULD NOT
-----------------------------------------------------
Electrical DC is a direct linear solve whose numerical error sits at round-off,
so convergence was NOT_APPLICABLE and nothing could fail. Thermal conduction is
linear and unconditionally stable, so its cheap rung degrades in accuracy
rather than breaking, and a solve essentially cannot fail either.

Here the governing equations are nonlinear, the Arrhenius coupling makes the
system genuinely stiff, and solves can and do fail — at a computational limit,
by step-size collapse, or by completing successfully and landing outside the
model's validity envelope. That last case is the one this domain exists to
exercise: it is the difference between "the integration worked" and "the answer
is usable", and no earlier domain could produce it.

Module roles:

    problem.py     chemistry, operation and integration declarations, the model
                   with its validity envelope, the domain capability, and the
                   universal problem statement
    reference.py   the independent references — an algebraic steady state by
                   Brent bracketing, and the exact reaction-free invariant.
                   Verification side only; it never imports the solver
    solver.py      CSTRSolver (the five-stage lifecycle) and the solve_reactor
                   wrapper
    validation.py  per-solve checks, and separately the verification gate that
                   is the only thing allowed to award NUMERICALLY_CONVERGED,
                   ANALYTICALLY_VERIFIED or CROSS_SOLVER_VALIDATED

THE PUBLIC SURFACE IS DELIBERATELY SMALL
-----------------------------------------
``__all__`` is what a *consumer of this domain* needs: declare a reactor, build
a problem, solve it, read the metrics, run the verification gate, measure
stiffness, catch the errors. The assembled system, the assembly routine, the
per-solve report builder, the problem/run integrity check and the internal
resampling helpers stay reachable from their own modules for white-box tests
and are not compatibility promises.
"""

from __future__ import annotations

from .errors import (
    IntegrationBudgetExceeded,
    KineticsCSTRError,
    ReactorBindingError,
    ReactorConfigurationError,
)
from .problem import (
    CA_FINAL_METRIC,
    CONCENTRATION_UNIT,
    CONVERSION_METRIC,
    CSTR_MODEL,
    CSTR_MODELS,
    DENSITY_UNIT,
    DIMENSIONLESS,
    FLOW_UNIT,
    HEAT_CAPACITY_UNIT,
    KINETICS_CSTR_NONISOTHERMAL,
    MAX_VALID_TEMPERATURE_K,
    METRIC_UNITS,
    MIN_VALID_TEMPERATURE_K,
    MOLAR_ENERGY_UNIT,
    MOLAR_GAS_CONSTANT,
    RATE_CONSTANT_UNIT,
    T_AT_MAX_METRIC,
    T_FINAL_METRIC,
    T_MAX_METRIC,
    TEMPERATURE_UNIT,
    TIME_UNIT,
    UA_UNIT,
    VOLUME_UNIT,
    IntegrationSettings,
    ReactorChemistry,
    ReactorOperation,
    ReactorRun,
    build_cstr_problem,
)
from .reference import (
    INVARIANT_EXPRESSION,
    INVARIANT_REFERENCE_ID,
    STEADY_STATE_EXPRESSION,
    STEADY_STATE_REFERENCE_ID,
    SteadyState,
    adiabatic_invariant_exact,
    arrhenius_rate_constant,
    invariant_is_exact,
    invariant_value,
    steady_state_residual,
    steady_states,
)
from .solver import (
    BACKEND,
    SOLVER_ID,
    SOLVER_VERSION,
    CSTRSolver,
    TransientTrajectorySample,
    VerificationSolveBundle,
    solve_reactor,
    solve_reactor_bundle,
)
from .validation import (
    CONVERGENCE_QOIS,
    INVARIANT_REL_TOL,
    MIN_RUNGS,
    STATIONARITY_REL_TOL,
    STEADY_STATE_REL_TOL,
    TOLERANCE_LADDER,
    TOLERANCE_REL_TOL,
    CSTRValidationSettings,
    CSTRVerificationReport,
    StiffnessMeasurement,
    ToleranceRung,
    measure_stiffness,
    run_verification_gate,
)

__all__ = [
    # declarations
    "ReactorChemistry",
    "ReactorOperation",
    "IntegrationSettings",
    "ReactorRun",
    # problem statement
    "build_cstr_problem",
    "CSTR_MODEL",
    "CSTR_MODELS",
    "KINETICS_CSTR_NONISOTHERMAL",
    # solving
    "CSTRSolver",
    "solve_reactor",
    "solve_reactor_bundle",
    "VerificationSolveBundle",
    "TransientTrajectorySample",
    "SOLVER_ID",
    "SOLVER_VERSION",
    "BACKEND",
    # the independent references
    "steady_states",
    "steady_state_residual",
    "SteadyState",
    "arrhenius_rate_constant",
    "adiabatic_invariant_exact",
    "invariant_value",
    "invariant_is_exact",
    "STEADY_STATE_REFERENCE_ID",
    "STEADY_STATE_EXPRESSION",
    "INVARIANT_REFERENCE_ID",
    "INVARIANT_EXPRESSION",
    # verification
    "run_verification_gate",
    "CSTRVerificationReport",
    "ToleranceRung",
    "TOLERANCE_LADDER",
    "TOLERANCE_REL_TOL",
    "INVARIANT_REL_TOL",
    "STEADY_STATE_REL_TOL",
    "STATIONARITY_REL_TOL",
    "CONVERGENCE_QOIS",
    "MIN_RUNGS",
    "CSTRValidationSettings",
    # stiffness
    "measure_stiffness",
    "StiffnessMeasurement",
    # metric names and units
    "CA_FINAL_METRIC",
    "T_FINAL_METRIC",
    "T_MAX_METRIC",
    "T_AT_MAX_METRIC",
    "CONVERSION_METRIC",
    "METRIC_UNITS",
    "CONCENTRATION_UNIT",
    "TEMPERATURE_UNIT",
    "TIME_UNIT",
    "VOLUME_UNIT",
    "FLOW_UNIT",
    "RATE_CONSTANT_UNIT",
    "MOLAR_ENERGY_UNIT",
    "DENSITY_UNIT",
    "HEAT_CAPACITY_UNIT",
    "UA_UNIT",
    "DIMENSIONLESS",
    "MOLAR_GAS_CONSTANT",
    "MIN_VALID_TEMPERATURE_K",
    "MAX_VALID_TEMPERATURE_K",
    # errors
    "KineticsCSTRError",
    "ReactorConfigurationError",
    "ReactorBindingError",
    "IntegrationBudgetExceeded",
]
