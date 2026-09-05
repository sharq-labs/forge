"""SRIA campaign loop and versioned persistence surfaces.

The M5 campaign loop remains the bounded sequential orchestration path. Core
V0.3 adds an incremental persistence successor without changing the scientific,
decision, assurance, stopping, or certification semantics of that loop.
"""

from __future__ import annotations

from .budget import BudgetCharge, BudgetExhausted, BudgetLedger
from .certification import CertificationRequirement, RequirementStatus
from .checkpoint import (
    CampaignCheckpoint,
    CheckpointStore,
    EffectLedger,
    IterationPlan,
    ResumeViolation,
)
from .events import (
    CampaignEvent,
    CampaignEventLog,
    CampaignEventType,
    ChainBroken,
)
from .executor import (
    ExecutionRecord,
    MemberExecution,
    SimulationExecutor,
    aggregate_member_cost,
    require_simulation,
)
from .liveness import (
    LIVENESS_POLICY_ID,
    LivenessRuling,
    LivenessStatus,
    ValidationLivenessPolicy,
    ValidationTarget,
    validation_targets,
)
from .persistence import (
    BudgetDeclaration,
    BudgetJournalEntry,
    CampaignCheckpointV3,
    CompactRunState,
    EffectJournalEntry,
    IncrementalCheckpointStore,
    IterationJournalEntry,
    PersistenceIntegrityError,
)
from .persistence_runner import IncrementalCampaignRunner
from .runner import (
    AssessmentBundle,
    CampaignHarness,
    CampaignRunner,
    deterministic_clock,
)
from .state import (
    RESEARCH_MODE_VOCABULARY,
    TERMINAL_STATES,
    CampaignRun,
    ExecutionState,
    IterationRecord,
    PauseReason,
)
from .stopping import (
    STOPPING_REVIEW_VERSION,
    ArbiterStoppingReview,
    StopProposal,
    StopReview,
    StopReviewOutcome,
    StoppingCriterion,
    StoppingCriterionEvaluator,
)

#: Frozen M5 campaign-loop identity. Kept for compatibility.
SRIA_CAMPAIGN_VERSION = "0.1.0-m5-campaign-loop"
#: Versioned persistence successor introduced by Core V0.3.
SRIA_CAMPAIGN_PERSISTENCE_VERSION = "0.3.0"

__all__ = [
    "SRIA_CAMPAIGN_VERSION",
    "SRIA_CAMPAIGN_PERSISTENCE_VERSION",
    # state
    "CampaignRun",
    "ExecutionState",
    "IterationRecord",
    "PauseReason",
    "TERMINAL_STATES",
    "RESEARCH_MODE_VOCABULARY",
    # events
    "CampaignEvent",
    "CampaignEventLog",
    "CampaignEventType",
    "ChainBroken",
    # budget
    "BudgetLedger",
    "CertificationRequirement",
    "RequirementStatus",
    "BudgetCharge",
    "BudgetExhausted",
    # legacy checkpoint compatibility
    "CampaignCheckpoint",
    "CheckpointStore",
    "EffectLedger",
    "IterationPlan",
    "ResumeViolation",
    # Core V0.3 persistence
    "IncrementalCheckpointStore",
    "CampaignCheckpointV3",
    "CompactRunState",
    "BudgetDeclaration",
    "BudgetJournalEntry",
    "EffectJournalEntry",
    "IterationJournalEntry",
    "PersistenceIntegrityError",
    # executor
    "SimulationExecutor",
    "ExecutionRecord",
    "MemberExecution",
    "require_simulation",
    "aggregate_member_cost",
    # validation liveness
    "ValidationLivenessPolicy",
    "LivenessRuling",
    "LivenessStatus",
    "ValidationTarget",
    "validation_targets",
    "LIVENESS_POLICY_ID",
    # stopping
    "StopProposal",
    "StopReview",
    "StopReviewOutcome",
    "ArbiterStoppingReview",
    "StoppingCriterion",
    "StoppingCriterionEvaluator",
    "STOPPING_REVIEW_VERSION",
    # runners
    "CampaignRunner",
    "IncrementalCampaignRunner",
    "CampaignHarness",
    "AssessmentBundle",
    "deterministic_clock",
]
