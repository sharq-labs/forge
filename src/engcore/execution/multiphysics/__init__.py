"""Generic multiphysics execution runtime."""

from .convergence import ResidualCalculator
from .error import CouplingErrorBudget, CouplingErrorContribution
from .external import (
    ExternalProviderIdentity,
    ExternalSnapshot,
    ExternalSolverParticipant,
    ExternalSolverSession,
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
    "MultiphysicsExecutionError",
    "MultiphysicsRuntime",
    "ParticipantEvent",
    "RelaxationController",
    "ResidualCalculator",
    "RuntimeCheckpoint",
    "StructuredFieldMapper",
    "TransferEngine",
    "TransferResult",
    "combine_fan_in_uncertainty",
    "relax_uncertainty",
    "validate_inputs",
    "validate_outputs",
    "validate_port_value",
    "validate_uncertainty",
]
