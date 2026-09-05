"""SRIA V0.1 — Scientific Research Intelligence Architecture, milestone M1.

M1 is the trust foundation and nothing else. It exists so that simulations,
literature, measurements, benchmarks, Domain Packs, Critics, an Arbiter and
cost/failure/fidelity learning can all be added later *without rewriting the
core* — and, more importantly, without any of them acquiring the ability to
write scientific belief on their own.

The one invariant that must survive every future milestone:

    NO SOURCE WRITES SCIENTIFIC BELIEF DIRECTLY.

    Candidate Evidence -> Critics/Assessments -> Arbiter admission
                       -> Belief Update Gateway -> Scientific Belief

The enforcement mechanisms here are **architectural capability boundaries**:
they prevent belief writes that are accidental, incidental, or attempted
through any supported API, and they make deliberate circumvention visible in
an audit log. They are not security isolation — Python cannot provide that —
and the import scanner is a CI guardrail, not a sandbox.

Failing admission is procedural, never epistemic: a refused, unsigned or
mis-bound admission leaves belief unchanged *and* leaves the evidence's
scientific standing unchanged. ``INVALID`` is reserved for an explicit
scientific judgement.

What M1 deliberately does **not** contain: research strategy, a Strategist, a
Digger, a Digital Twin, reinforcement learning, a UI, evidence fusion, utility
ranking, a learned cost or failure model, and any LLM anywhere near the
scientific path. Several of those have reserved fields and enum members so the
storage format will not have to change when they arrive; reaching a reserved
capability at runtime raises :class:`ReservedNotImplemented` rather than
quietly doing something approximate.

Layering: SRIA imports the Scientific Core. The Scientific Core never imports
SRIA, and neither imports an LLM provider — enforced by
:mod:`engcore.sria.trust`.
"""

from __future__ import annotations

from .admission import (
    AdmissionAttempt,
    AdmissionAuthority,
    AdmissionAuthorityRegistry,
    AdmissionDeclaration,
    AdmissionOutcome,
)
from .actions import (
    ExecutorType,
    FeasibilityVerdict,
    HardConstraint,
    HardFeasibilityGate,
    IMPLEMENTED_EXECUTORS,
    ResearchAction,
    require_executable,
)
from .charter import (
    AcceptanceCriterion,
    CampaignCharter,
    CampaignType,
    CharterAmendment,
    ConfidenceRequirement,
    IMPLEMENTED_CAMPAIGN_TYPES,
    TerminalDecision,
    require_implemented_campaign_type,
)
from .domain_pack import (
    DomainCriticHook,
    DomainPack,
    FORBIDDEN_PACK_ATTRIBUTES,
    FidelityLevel,
    REQUIRED_PACK_METHODS,
    guard_from_packs,
    validate_domain_pack,
)
from .errors import (
    ActionContractError,
    AdmissionAuthorityError,
    AdmissionError,
    BeliefWriteViolation,
    CalibrationKeyContamination,
    CharterError,
    DomainPackContractError,
    EvidenceError,
    FeasibilityViolation,
    LifecycleViolation,
    OutcomeContractError,
    ReservedNotImplemented,
    SRIAError,
    SignatureError,
    TrustBoundaryViolation,
    UncertaintyContractError,
)
from .evidence import (
    ALLOWED_TRANSITIONS,
    Assessment,
    AssessmentVerdict,
    BELIEF_BEARING_STATUS,
    ClaimBinding,
    ClaimType,
    Evidence,
    EvidenceStatus,
    IMPLEMENTED_SOURCE_CLASSES,
    LifecycleEvent,
    SourceClass,
    require_implemented_source,
)
from .gateway import BeliefEntry, BeliefUpdateGateway, ScientificBelief
from .outcomes import (
    AttributedCause,
    BlameAssignment,
    CensoringType,
    DetectedBy,
    Disposition,
    Retryability,
    RunOutcome,
)
from .provenance import (
    AssessmentProvenance,
    DecisionProvenance,
    EvidenceProvenance,
)
from .signatures import (
    CALIBRATION_KEY_VERSION,
    CalibrationKey,
    EnvironmentSignature,
    SemanticGuard,
    StructureComponent,
    StructureSignature,
    build_calibration_key,
)
from .uncertainty import (
    DiscrepancyKind,
    ModelDiscrepancy,
    SubjectModel,
    UncertaintyChannel,
    UncertaintyDeclaration,
)

SRIA_VERSION = "0.1.0-m1-contracts"

__all__ = [
    "SRIA_VERSION",
    # errors
    "SRIAError",
    "CharterError",
    "EvidenceError",
    "LifecycleViolation",
    "AdmissionError",
    "AdmissionAuthorityError",
    "BeliefWriteViolation",
    "UncertaintyContractError",
    "OutcomeContractError",
    "ActionContractError",
    "FeasibilityViolation",
    "SignatureError",
    "CalibrationKeyContamination",
    "DomainPackContractError",
    "ReservedNotImplemented",
    "TrustBoundaryViolation",
    # charter
    "CampaignCharter",
    "CampaignType",
    "TerminalDecision",
    "ConfidenceRequirement",
    "AcceptanceCriterion",
    "CharterAmendment",
    "IMPLEMENTED_CAMPAIGN_TYPES",
    "require_implemented_campaign_type",
    # evidence
    "Evidence",
    "EvidenceStatus",
    "SourceClass",
    "ClaimType",
    "ClaimBinding",
    "Assessment",
    "AssessmentVerdict",
    "LifecycleEvent",
    # admission authority
    "AdmissionDeclaration",
    "AdmissionAttempt",
    "AdmissionAuthority",
    "AdmissionAuthorityRegistry",
    "AdmissionOutcome",
    "ALLOWED_TRANSITIONS",
    "BELIEF_BEARING_STATUS",
    "IMPLEMENTED_SOURCE_CLASSES",
    "require_implemented_source",
    # gateway
    "BeliefUpdateGateway",
    "ScientificBelief",
    "BeliefEntry",
    # uncertainty
    "UncertaintyChannel",
    "SubjectModel",
    "DiscrepancyKind",
    "ModelDiscrepancy",
    "UncertaintyDeclaration",
    # actions
    "ResearchAction",
    "ExecutorType",
    "FeasibilityVerdict",
    "HardConstraint",
    "HardFeasibilityGate",
    "IMPLEMENTED_EXECUTORS",
    "require_executable",
    # outcomes
    "RunOutcome",
    "Disposition",
    "AttributedCause",
    "BlameAssignment",
    "CensoringType",
    "Retryability",
    "DetectedBy",
    # provenance
    "EvidenceProvenance",
    "AssessmentProvenance",
    "DecisionProvenance",
    # signatures
    "StructureSignature",
    "StructureComponent",
    "EnvironmentSignature",
    "CalibrationKey",
    "SemanticGuard",
    "build_calibration_key",
    "CALIBRATION_KEY_VERSION",
    # domain packs
    "DomainPack",
    "DomainCriticHook",
    "FidelityLevel",
    "validate_domain_pack",
    "guard_from_packs",
    "REQUIRED_PACK_METHODS",
    "FORBIDDEN_PACK_ATTRIBUTES",
]
