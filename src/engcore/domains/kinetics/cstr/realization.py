"""Production realization record for the non-isothermal CSTR domain."""

from __future__ import annotations

from ....scientific.capabilities import ScientificCapability
from ....scientific.ir.problem import ModelReference
from ....scientific.realizations.definition import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
)
from ....scientific.solvers.capability import SolverCapabilityId
from .problem import (
    CSTR_MODEL,
    KINETICS_CSTR_NONISOTHERMAL,
    cstr_solver_capabilities,
)

REALIZATION_ID = "kinetics.cstr.nonisothermal_first_order.scipy_implicit"
REALIZATION_VERSION = "0.1.0"

CSTR_TRANSIENT_SCIENCE = ScientificCapability.parse(
    "kinetics:cstr_nonisothermal_transient"
)

CSTR_REALIZATION = ModelRealizationDefinition(
    realization_id=REALIZATION_ID,
    version=REALIZATION_VERSION,
    model=ModelReference(CSTR_MODEL.model_id, CSTR_MODEL.version),
    formulation=ModelFormulation.ODE,
    name="Non-isothermal CSTR implicit-IVP realization",
    description=(
        "The declared coupled species/energy balances assembled as a two-state "
        "initial-value ODE and integrated by the domain's implicit SciPy solver."
    ),
    provided_capabilities=frozenset({CSTR_TRANSIENT_SCIENCE}),
    required_capabilities=frozenset(),
    required_solver_capabilities=frozenset(
        SolverCapabilityId.coerce(item) for item in cstr_solver_capabilities()
    ),
    assumptions=(
        "the numerical realization implements exactly the CSTR model's declared balances",
        "the analytic Jacobian is the derivative of the same assembled right-hand side",
        "integration settings are execution choices and do not change realization identity",
    ),
    implementation=ImplementationReference(
        implementation_id="engcore.domains.kinetics.cstr.solver",
        version=REALIZATION_VERSION,
        reference=(
            "SciPy solve_ivp implicit integration of the CSTR species and energy balances"
        ),
    ),
)

__all__ = [
    "CSTR_REALIZATION",
    "CSTR_TRANSIENT_SCIENCE",
    "REALIZATION_ID",
    "REALIZATION_VERSION",
]
