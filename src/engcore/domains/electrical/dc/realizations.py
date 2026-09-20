"""Model realization for the linear DC network MNA subsystem."""

from __future__ import annotations

from ....scientific.capabilities import ScientificCapability
from ....scientific.ir.problem import ModelReference
from ....scientific.realizations.definition import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
)
from ....scientific.realizations.registry import RealizationRegistry
from ....scientific.solvers.capability import (
    CoreCapabilities,
    SolverCapabilityId,
)
from .models import ELECTRICAL_DC_LINEAR, KCL_MODEL

DC_NETWORK_STATE = ScientificCapability(
    "electrical",
    "dc_network_state",
)

MNA_NETWORK_REALIZATION = ModelRealizationDefinition(
    realization_id="electrical.dc.network.mna",
    version="0.1.0",
    model=ModelReference(
        KCL_MODEL.model_id,
        KCL_MODEL.version,
    ),
    formulation=ModelFormulation.ALGEBRAIC,
    name="Modified nodal analysis of a linear DC network",
    description=(
        "Realizes the network-level KCL system together with the active "
        "component models declared by the participant model assembly. "
        "The primary model identity is KCL; resistor/source constitutive "
        "models remain explicit members of the participant assembly."
    ),
    provided_capabilities=frozenset({DC_NETWORK_STATE}),
    required_capabilities=frozenset(),
    required_solver_capabilities=frozenset(
        {
            SolverCapabilityId.coerce(ELECTRICAL_DC_LINEAR),
            SolverCapabilityId.coerce(CoreCapabilities.LINEAR_SYSTEM),
        }
    ),
    assumptions=(
        "the active participant model assembly is a linear resistive DC network",
        "component values are fixed over one coupling window",
        "network topology is fixed over one coupling window",
    ),
    implementation=ImplementationReference(
        implementation_id="engcore.domains.electrical.dc.solver",
        version="0.1.0",
        reference="modified nodal analysis; exact active models are carried by ParticipantSpec.models",
    ),
)


def dc_realizations() -> RealizationRegistry:
    return RealizationRegistry((MNA_NETWORK_REALIZATION,))


__all__ = [
    "DC_NETWORK_STATE",
    "MNA_NETWORK_REALIZATION",
    "dc_realizations",
]
