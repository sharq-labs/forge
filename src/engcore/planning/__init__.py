"""Engineering intent and deterministic scientific planning.

The package sits above claims/capabilities and below product transports.  An
LLM may draft an EngineeringIntent; grounding and this planner decide what is
known, what must be clarified and which declared scientific execution is
admissible.  The package contains no domain-name branches and executes no
physics itself.
"""

from .blueprint import (
    BlueprintRegistry,
    ParticipantBinding,
    ParticipantBlueprint,
    PhysicsGraphBlueprint,
)
from .clarification import (
    ClarificationKind,
    ClarificationQuestion,
    clarification_questions,
)
from .intent import (
    ComputeBudget,
    ContextOfUse,
    EngineeringComponent,
    EngineeringIntent,
    EngineeringInterface,
    EngineeringObjective,
    FactRole,
    FidelityRequest,
    IntentFact,
    IntentQuantityOfInterest,
    InterfaceExchange,
    ObjectiveKind,
    QOIConstraint,
)
from .nl import (
    FORBIDDEN_PLANNER_AUTHORITY_FIELDS,
    IntentProposer,
    NaturalLanguageIntent,
    compile_natural_language_intent,
)
from .planner import (
    ExecutionMode,
    FidelityDecision,
    GapKind,
    GraphPlan,
    ModelExecutionChoice,
    PlanningGap,
    PlanningRegistries,
    PlanningStatus,
    QOIPlan,
    ResourceEstimate,
    ScientificPlanningRecord,
    plan_engineering_intent,
)
from .policy import PlannerPolicy
from .production import production_planning_registries
from .validation import (
    IntentReadiness,
    IntentValidation,
    IssueKind,
    PlanningIssue,
    QOICapabilityScreen,
    validate_intent,
)
from .verification import (
    VerificationPlanningOption,
    VerificationPlanningRegistry,
)

__all__ = [
    "BlueprintRegistry",
    "ClarificationKind",
    "ClarificationQuestion",
    "ComputeBudget",
    "ContextOfUse",
    "EngineeringComponent",
    "EngineeringIntent",
    "EngineeringInterface",
    "EngineeringObjective",
    "ExecutionMode",
    "FORBIDDEN_PLANNER_AUTHORITY_FIELDS",
    "FactRole",
    "FidelityDecision",
    "FidelityRequest",
    "GapKind",
    "GraphPlan",
    "IntentFact",
    "IntentProposer",
    "IntentQuantityOfInterest",
    "IntentReadiness",
    "IntentValidation",
    "InterfaceExchange",
    "IssueKind",
    "ModelExecutionChoice",
    "NaturalLanguageIntent",
    "ObjectiveKind",
    "ParticipantBinding",
    "ParticipantBlueprint",
    "PhysicsGraphBlueprint",
    "PlannerPolicy",
    "PlanningGap",
    "PlanningIssue",
    "PlanningRegistries",
    "PlanningStatus",
    "QOIConstraint",
    "QOICapabilityScreen",
    "QOIPlan",
    "ResourceEstimate",
    "ScientificPlanningRecord",
    "VerificationPlanningOption",
    "VerificationPlanningRegistry",
    "clarification_questions",
    "compile_natural_language_intent",
    "plan_engineering_intent",
    "production_planning_registries",
    "validate_intent",
]
