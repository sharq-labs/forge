"""Generic multiphysics execution runtime."""

from .admission import (
    MultiphysicsExecutionAdmission,
    admit_multiphysics_execution,
)
from .convergence import ResidualCalculator
from .error import CouplingErrorBudget, CouplingErrorContribution
from .external import (
    ExternalProviderIdentity,
    ExternalSnapshot,
    ExternalSolverParticipant,
    ExternalSolverSession,
)
from .factory import (
    ParticipantFactory,
    ParticipantFactoryCoverage,
    ParticipantFactoryDeclaration,
    ParticipantFactoryRegistry,
)
from .mapping import FieldMapper, FieldMappingResult, StructuredFieldMapper
from .participant import (
    AdvanceRequest,
    AdvanceResult,
    CallbackParticipant,
    CouplingValue,
    ExecutableParticipant,
    InitializationResult,
    ParticipantEvent,
    RuntimeCheckpoint,
    validate_inputs,
    validate_outputs,
    validate_port_value,
    validate_uncertainty,
)
from .relaxation import RelaxationController, relax_uncertainty
from .runtime import MultiphysicsExecutionError, MultiphysicsRuntime
from .transfer import (
    FrameTransform,
    TransferEngine,
    TransferResult,
    combine_fan_in_uncertainty,
)

__all__ = [
    "AdvanceRequest",
    "AdvanceResult",
    "CallbackParticipant",
    "CouplingErrorBudget",
    "CouplingErrorContribution",
    "CouplingValue",
    "ExecutableParticipant",
    "ExternalProviderIdentity",
    "ExternalSnapshot",
    "ExternalSolverParticipant",
    "ExternalSolverSession",
    "FieldMapper",
    "FieldMappingResult",
    "FrameTransform",
    "InitializationResult",
    "MultiphysicsExecutionAdmission",
    "MultiphysicsExecutionError",
    "MultiphysicsRuntime",
    "ParticipantEvent",
    "ParticipantFactory",
    "ParticipantFactoryCoverage",
    "ParticipantFactoryDeclaration",
    "ParticipantFactoryRegistry",
    "RelaxationController",
    "ResidualCalculator",
    "RuntimeCheckpoint",
    "StructuredFieldMapper",
    "TransferEngine",
    "TransferResult",
    "admit_multiphysics_execution",
    "combine_fan_in_uncertainty",
    "relax_uncertainty",
    "validate_inputs",
    "validate_outputs",
    "validate_port_value",
    "validate_uncertainty",
]
