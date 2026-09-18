"""The scientific claim layer: claims, capabilities, routing, planning, assessment.

**Status: EXPERIMENTAL.** Not part of any Core Freeze. It sits *above* the
Scientific Core, the domains, the MCP credibility layer and SRIA, and owns no
physics, no validation vocabulary and no decision engine of its own:

* a claim's comparison is the Core's ``ConstraintDefinition``;
* its evidence bar is ``ValidationLevel``;
* its uncertainty and discrepancy vocabulary is SRIA's;
* what a run supports is the ``CredibilityEvidenceReport`` verdict;
* what a decision may rely on is the SRIA ``Arbiter``'s.

What this package adds is the protocol between them -- a structured claim
(:mod:`.contract`), a declared capability (:mod:`.capabilities`), model
selection over declared applicability (:mod:`.selection`), structured repair
(:mod:`.repair`) and the compiler that decides whether a claim can execute
(:mod:`.compiler`) -- routing one to the other without a caller naming a system.

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
    inputs_from_case,
    match_declaration,
)
from .compiler import (
    READINESS_ORDER,
    CompilationStatus,
    CompiledClaim,
    GapKind,
    PredictedGap,
    compile_claim,
    readiness_rank,
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
from .repair import RepairAction, RepairKind, merge_repairs
from .selection import (
    CandidateAssessment,
    CandidateStatus,
    ConditionStatus,
    ModelApplicability,
    ModelSelection,
    RejectionReason,
    UnknownBasis,
    select_capability,
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
    "READINESS_ORDER",
    "AttainableLevel",
    "CandidateAssessment",
    "CandidateStatus",
    "CompilationStatus",
    "CompiledClaim",
    "ConditionStatus",
    "GapKind",
    "ModelApplicability",
    "ModelSelection",
    "PredictedGap",
    "RejectionReason",
    "RepairAction",
    "RepairKind",
    "UnknownBasis",
    "compile_claim",
    "merge_repairs",
    "readiness_rank",
    "select_capability",
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
    "inputs_from_case",
    "match_declaration",
]
