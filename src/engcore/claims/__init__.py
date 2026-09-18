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
(:mod:`.repair`), the compiler that decides whether a claim can execute
(:mod:`.compiler`), route classification from pinned identities
(:mod:`.routes`), the deterministic experiment plan (:mod:`.planning`),
execution bound to the plan (:mod:`.execution`), the claim-level verdict
(:mod:`.verdict`), the structured explanation (:mod:`.explanation`), the
end-to-end runtime (:mod:`.assessment`), uncertainty transport
(:mod:`.uncertainty`), context-of-use binding (:mod:`.context`), evidence-source
adapters (:mod:`.sources`) and trusted-oracle discovery (:mod:`.oracles`) --
routing one to the other without a caller naming a system.

Nothing here parses natural language and nothing here imports an AI provider.
"""

from .assessment import (
    ASSESSMENT_SCHEMA,
    AssessmentForgeryError,
    ClaimAssessment,
    assemble_evidence,
    assess_claim,
    assure,
    verify_assessment,
)
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
    PerturbableInput,
    ProducedQuantity,
    ProvidedCapability,
    RefinementStudy,
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
from .context import ContextBindingError, context_problems, require_context
from .execution import ExecutionOutcome, PlanExecution, binding_problems, execute_plan
from .oracles import OracleApplicability, OracleMatch, discover_oracles
from .sources import SOURCE_ADAPTERS, EvidenceSourceAdapter, SourceOutcome, SourceStatus, gather_evidence
from .uncertainty import (
    TransportState,
    TransportedRecord,
    UncertaintyTransport,
    UncertaintyTransportError,
    classify_record,
    report_transport,
    transport,
)
from .explanation import ExplanationItem, ExplanationKind, explain, resolve
from .planning import (
    ExperimentPlan,
    PlanningError,
    PlanStep,
    StepAvailability,
    StepKind,
    charter_for,
    execution_order,
    plan_experiment,
    verify_plan,
)
from .repair import RepairAction, RepairKind, merge_repairs
from .routes import RouteAssessment, RouteClass, assess_routes, classify_dependencies, pinned_dependencies
from .verdict import (
    ClaimComparison,
    ClaimVerdict,
    ComparisonOutcome,
    DecisionRule,
    VerdictBasis,
    admissible,
    compare,
    derive_claim_verdict,
)
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

from .numerical_uq import (
    EstimateStatus,
    NumericalUQError,
    NumericalUncertaintyEstimate,
    RefinementLevel,
    estimate_numerical_uncertainty,
)

from .parameter_uq import (
    DistributionKind,
    InputDistribution,
    InputUncertainty,
    ParameterUQError,
    ParameterUncertaintyEstimate,
    PropagatedRun,
    draw_samples,
    estimate_parameter_uncertainty,
    wilks_confidence,
)

from .uq_studies import (
    StudyOutcome,
    UncertaintyStudyError,
    planned_studies,
    run_uncertainty_studies,
    study_spec,
    verify_study_records,
)

from .policy import (
    BUILTIN_PROFILES,
    DecisionConsequence,
    DecisionContext,
    DerivedEvidenceRequirement,
    EvidencePolicy,
    EvidencePolicyProfile,
    ModelInfluence,
    RiskClass,
    apply_policy,
    builtin_context,
    derive_requirement,
    policy_findings,
)

from .external_evidence import (
    ExternalEvidenceAssessment,
    ExternalStanding,
    LiteratureRecord,
    MeasurementRecord,
    PRODUCTION_EXTERNAL_REGISTRY,
    TrustedExternalRegistry,
    TrustedPin,
    assess_benchmark,
    assess_literature,
    assess_measurement,
    compare_with_simulation,
    read_external_record,
)

from .gaps import (
    EvidenceGap,
    EvidenceGapAnalysis,
    GapClass,
    analyze_gaps,
)

from .next_experiment import (
    ExperimentAction,
    ExperimentRecommendation,
    NextExperimentPlan,
    recommend_next,
)

from .sensitivity import (
    BoundaryKind,
    EnvelopeSide,
    ParameterSensitivity,
    RobustnessEnvelope,
    SensitivityError,
    SensitivityReport,
    robustness_envelope,
    sensitivity_study,
)

from .challenge import (
    Challenge,
    ChallengeKind,
    ChallengeReport,
    ChallengeResult,
    challenge_claim,
)

from .impact import (
    AssessmentSummary,
    Change,
    ChangeKind,
    DecisionGraph,
    ImpactReport,
    NodeKind,
    detect_changes,
    impact_of,
    record_digest,
)


__all__ = [
    "ASSESSMENT_SCHEMA",
    "AssessmentForgeryError",
    "AssessmentSummary",
    "AttainableLevel",
    "BUILTIN_PROFILES",
    "BoundaryKind",
    "CallerAssumption",
    "CandidateAssessment",
    "CandidateStatus",
    "CapabilityDeclaration",
    "CapabilityDeclarationError",
    "CapabilityExecutionRefused",
    "CapabilityInputError",
    "CapabilityMatch",
    "CapabilityRegistry",
    "CapabilityRegistryError",
    "CapabilityRun",
    "Challenge",
    "ChallengeKind",
    "ChallengeReport",
    "ChallengeResult",
    "Change",
    "ChangeKind",
    "ClaimAssessment",
    "ClaimComparison",
    "ClaimContractError",
    "ClaimKind",
    "ClaimLayerError",
    "ClaimTarget",
    "ClaimVerdict",
    "ComparisonOutcome",
    "CompilationStatus",
    "CompiledClaim",
    "ConditionStatus",
    "ContextBindingError",
    "DecisionBinding",
    "DecisionConsequence",
    "DecisionContext",
    "DecisionGraph",
    "DecisionRule",
    "DerivedEvidenceRequirement",
    "DistributionKind",
    "EnvelopeSide",
    "EstimateStatus",
    "EvidenceGap",
    "EvidenceGapAnalysis",
    "EvidencePolicy",
    "EvidencePolicyProfile",
    "EvidenceRequirement",
    "EvidenceSourceAdapter",
    "ExecutionOutcome",
    "ExperimentAction",
    "ExperimentPlan",
    "ExperimentRecommendation",
    "ExplanationItem",
    "ExplanationKind",
    "ExternalEvidenceAssessment",
    "ExternalStanding",
    "GapClass",
    "GapKind",
    "ImpactReport",
    "InputDeclaration",
    "InputDistribution",
    "InputKind",
    "InputRole",
    "InputUncertainty",
    "InstanceReport",
    "LiteratureRecord",
    "MeasurementRecord",
    "MismatchReason",
    "ModelApplicability",
    "ModelInfluence",
    "ModelSelection",
    "ModelUse",
    "NextExperimentPlan",
    "NodeKind",
    "NumericalUQError",
    "NumericalUncertaintyEstimate",
    "OracleApplicability",
    "OracleMatch",
    "PRODUCTION_EXTERNAL_REGISTRY",
    "ParameterSensitivity",
    "ParameterUQError",
    "ParameterUncertaintyEstimate",
    "PerturbableInput",
    "PlanExecution",
    "PlanStep",
    "PlanningError",
    "PredictedGap",
    "ProducedQuantity",
    "PropagatedRun",
    "ProvidedCapability",
    "QuantityOfInterest",
    "READINESS_ORDER",
    "RefinementLevel",
    "RefinementStudy",
    "RejectionReason",
    "RepairAction",
    "RepairKind",
    "RequestedOutput",
    "RiskClass",
    "RobustnessEnvelope",
    "RouteAssessment",
    "RouteClass",
    "RouteDeclaration",
    "RouteKind",
    "SOURCE_ADAPTERS",
    "ScientificClaim",
    "SensitivityError",
    "SensitivityReport",
    "SolverUse",
    "SourceOutcome",
    "SourceStatus",
    "StepAvailability",
    "StepKind",
    "StudyOutcome",
    "TransportState",
    "TransportedRecord",
    "TrustedExternalRegistry",
    "TrustedPin",
    "UnassessableCondition",
    "UncertaintyCapability",
    "UncertaintyDemand",
    "UncertaintyStudyError",
    "UncertaintyTransport",
    "UncertaintyTransportError",
    "UnknownBasis",
    "VerdictBasis",
    "admissible",
    "analyze_gaps",
    "apply_policy",
    "assemble_evidence",
    "assess_benchmark",
    "assess_claim",
    "assess_literature",
    "assess_measurement",
    "assess_routes",
    "assure",
    "binding_problems",
    "build_case",
    "builtin_context",
    "challenge_claim",
    "charter_for",
    "classify_dependencies",
    "classify_record",
    "compare",
    "compare_with_simulation",
    "compile_claim",
    "context_problems",
    "declared_path",
    "derive_claim_verdict",
    "derive_requirement",
    "detect_changes",
    "discover_oracles",
    "draw_samples",
    "estimate_numerical_uncertainty",
    "estimate_parameter_uncertainty",
    "execute_plan",
    "execution_order",
    "explain",
    "gather_evidence",
    "impact_of",
    "input_problem",
    "inputs_from_case",
    "match_declaration",
    "merge_repairs",
    "pinned_dependencies",
    "plan_experiment",
    "planned_studies",
    "policy_findings",
    "read_external_record",
    "readiness_rank",
    "recommend_next",
    "record_digest",
    "report_transport",
    "require_context",
    "resolve",
    "robustness_envelope",
    "run_uncertainty_studies",
    "select_capability",
    "sensitivity_study",
    "study_spec",
    "transport",
    "verify_assessment",
    "verify_plan",
    "verify_study_records",
    "wilks_confidence",
]
