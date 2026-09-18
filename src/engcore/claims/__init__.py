"""The scientific claim layer: claims, capabilities, routing, planning, assessment.

**Status: EXPERIMENTAL.** Not part of any Core Freeze. It sits *above* the
Scientific Core, the domains, the MCP credibility layer and SRIA, and owns no
physics, no validation vocabulary and no decision engine of its own:

* a claim's comparison is the Core's ``ConstraintDefinition``;
* its evidence bar is ``ValidationLevel``;
* its uncertainty and discrepancy vocabulary is SRIA's;
* what a run supports is the ``CredibilityEvidenceReport`` verdict;
* what a decision may rely on is the SRIA ``Arbiter``'s.

What this package adds is the protocol between them -- a structured claim, a
declared capability, and (in later modules) the compiler, selection, planning
and assessment that route one to the other without a caller naming a system.

Nothing here parses natural language and nothing here imports an AI provider.
"""

from .capabilities import (
    AttainableLevel,
    CapabilityDeclaration,
    CapabilityMatch,
    CapabilityRegistry,
    CapabilityRun,
    InputDeclaration,
    InputKind,
    InputRole,
    InstanceReport,
    MismatchReason,
    ModelUse,
    ProducedQuantity,
    ProvidedCapability,
    RouteDeclaration,
    RouteKind,
    SolverUse,
    UnassessableCondition,
    UncertaintyCapability,
    build_case,
    declared_path,
    input_problem,
    match_declaration,
)
from .contract import (
    CallerAssumption,
    ClaimKind,
    ClaimTarget,
    DecisionBinding,
    EvidenceRequirement,
    QuantityOfInterest,
    RequestedOutput,
    ScientificClaim,
    UncertaintyDemand,
)
from .errors import (
    CapabilityDeclarationError,
    CapabilityExecutionRefused,
    CapabilityInputError,
    CapabilityRegistryError,
    ClaimContractError,
    ClaimLayerError,
)

__all__ = [
    "AttainableLevel",
    "CallerAssumption",
    "CapabilityDeclaration",
    "CapabilityDeclarationError",
    "CapabilityExecutionRefused",
    "CapabilityInputError",
    "CapabilityMatch",
    "CapabilityRegistry",
    "CapabilityRegistryError",
    "CapabilityRun",
    "ClaimContractError",
    "ClaimKind",
    "ClaimLayerError",
    "ClaimTarget",
    "DecisionBinding",
    "EvidenceRequirement",
    "InputDeclaration",
    "InputKind",
    "InputRole",
    "InstanceReport",
    "MismatchReason",
    "ModelUse",
    "ProducedQuantity",
    "ProvidedCapability",
    "QuantityOfInterest",
    "RequestedOutput",
    "RouteDeclaration",
    "RouteKind",
    "ScientificClaim",
    "SolverUse",
    "UnassessableCondition",
    "UncertaintyCapability",
    "UncertaintyDemand",
    "build_case",
    "declared_path",
    "input_problem",
    "match_declaration",
]
