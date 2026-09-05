"""SRIA V0.1 M4 — research decision intelligence.

Answers one question: **given the current belief, the declared terminal
decision, the budget, the uncertainty and the calibration state, which
candidate research action is worth purchasing?**

It is not an autonomous research loop. It ranks one step, myopically, and
records why.

The architecture is a composition, deliberately:

    ActionFamilyGenerators -> HardFeasibilityGate -> UtilityEngine
                           -> CandidateEvaluator -> DecisionRecommendation

There is no ``MetaBrain``, no ``ScientificBrain``, no ``UniversalStrategist``.
The six action families are *labels on proposals*, not modes — no state
machine, no ``current_mode``, no family that gates another or owns budget.
Every candidate is scored by the same engine, and a family earns influence only
by proposing things that score well.

What M4 refuses to do is as important as what it does:

* without a terminal decision and utility it returns
  ``TERMINAL_OBJECTIVE_UNAVAILABLE`` rather than producing a plausible number;
* an unavailable score component makes a candidate ``NOT_SCORABLE`` rather than
  being replaced by a confident default;
* an undeclared composite outcome dependence is never assumed independent;
* infeasible candidates never reach ranking, so high VoI cannot rescue them;
* failure earns value only for declared, scientifically informative causes —
  infrastructure loss earns nothing;
* ``STOP_PROPOSAL`` means "nothing looks worth its cost", never "validated" or
  "safe to stop". Certification remains the Arbiter's, and this package emits
  no verdict that could be mistaken for one.

Not implemented: autonomous multi-step campaigns, deep planning, RL, automated
hypothesis generation, Digger, Digital Twin, physical experimentation,
universal scientific utility or ontology, final stopping, safety certification.
"""

from __future__ import annotations

from .actions import (
    ActionFamily,
    ActionProposal,
    AtomicAction,
    CandidateAction,
    CompositeAction,
    CostAggregation,
    ExecutionOrder,
    OutcomeDependence,
    candidate_actions,
)
from .belief_snapshot import (
    BeliefSnapshot,
    CalibrationState,
    FactorAvailability,
    snapshot_from_gateway,
)
from .families import (
    ActionFamilyGenerator,
    CharacterizeGenerator,
    DEFAULT_GENERATORS,
    DiscriminateGenerator,
    ExploreGenerator,
    GenerationContext,
    OptimizeGenerator,
    ReduceUncertaintyGenerator,
    ValidateGenerator,
    generate_candidates,
)
from .hypotheses import Hypothesis, HypothesisSet, PredictionDisagreement
from .suppliers import (
    ApplicabilitySupport,
    CalibrationCostSupplier,
    CalibrationFailureSupplier,
)
from .replay import (
    NON_DECISION_FIELDS,
    DependencyIdentity,
    DependencyKind,
    ExecutionDependencyManifest,
    ReplayMode,
    ReplayOutcome,
    ReplayResult,
    audit_replay,
    candidate_decision_identity,
    candidate_set_digest,
    canonical_digest,
    cost_model_state_digest,
    executable_replay,
)
from .coherence import (
    CONFLICT_STATUSES,
    PROVISIONAL_DECISION_MODE_RESERVED,
    REFUSING_STATUSES,
    CoherenceConflict,
    CoherenceReport,
    CoherenceStatus,
    calibration_state_for,
    check_state_coherence,
    pin_decision_basis,
)
from .recommendation import (
    BudgetPlan,
    CandidateEvaluator,
    DecisionRecommendation,
    RecommendationOutcome,
    information_only_ranking,
)
from .terminal import (
    TerminalObjective,
    TerminalObjectiveStatus,
    TerminalUtility,
    resolve_terminal_objective,
)
from .utility import (
    INFORMATIVE_COMPUTATIONAL_FAILURE_CAUSES,
    SCIENTIFIC_OUTCOME_CAUSES,
    UTILITY_ENGINE_VERSION,
    CandidateScore,
    ComponentStatus,
    CostSupplier,
    CostTradeoff,
    FailureSupplier,
    MisusedFailureChannel,
    OutcomeModel,
    ScoreComponent,
    ScoreStatus,
    UtilityEngine,
    UtilityPolicy,
    declared_failure_causes,
    excluded_failure_causes,
    informative_failure_causes,
    misdeclared_scientific_outcomes,
)

SRIA_DECISION_VERSION = "0.1.0-m4-voi"

__all__ = [
    "SRIA_DECISION_VERSION",
    # terminal objective
    "TerminalObjective",
    "TerminalObjectiveStatus",
    "TerminalUtility",
    "resolve_terminal_objective",
    # belief snapshot
    "BeliefSnapshot",
    "CalibrationState",
    "FactorAvailability",
    "snapshot_from_gateway",
    # hypotheses
    "Hypothesis",
    "HypothesisSet",
    "PredictionDisagreement",
    # actions
    "ActionFamily",
    "ActionProposal",
    "AtomicAction",
    "CompositeAction",
    "CandidateAction",
    "OutcomeDependence",
    "CostAggregation",
    "ExecutionOrder",
    "candidate_actions",
    # families
    "ActionFamilyGenerator",
    "GenerationContext",
    "ExploreGenerator",
    "CharacterizeGenerator",
    "DiscriminateGenerator",
    "OptimizeGenerator",
    "ReduceUncertaintyGenerator",
    "ValidateGenerator",
    "DEFAULT_GENERATORS",
    "generate_candidates",
    # utility
    "UtilityEngine",
    "UtilityPolicy",
    "CandidateScore",
    "ScoreComponent",
    "ScoreStatus",
    "ComponentStatus",
    "OutcomeModel",
    "CostSupplier",
    "FailureSupplier",
    "CostTradeoff",
    "MisusedFailureChannel",
    "INFORMATIVE_COMPUTATIONAL_FAILURE_CAUSES",
    "SCIENTIFIC_OUTCOME_CAUSES",
    "UTILITY_ENGINE_VERSION",
    "informative_failure_causes",
    "excluded_failure_causes",
    "declared_failure_causes",
    "misdeclared_scientific_outcomes",
    # calibration suppliers
    "CalibrationCostSupplier",
    "CalibrationFailureSupplier",
    "ApplicabilitySupport",
    # replay
    "DependencyIdentity",
    "DependencyKind",
    "ExecutionDependencyManifest",
    "ReplayMode",
    "ReplayOutcome",
    "ReplayResult",
    "audit_replay",
    "executable_replay",
    "candidate_set_digest",
    "candidate_decision_identity",
    "canonical_digest",
    "cost_model_state_digest",
    "NON_DECISION_FIELDS",
    # state coherence
    "CoherenceStatus",
    "CoherenceReport",
    "CoherenceConflict",
    "REFUSING_STATUSES",
    "CONFLICT_STATUSES",
    "PROVISIONAL_DECISION_MODE_RESERVED",
    "check_state_coherence",
    "calibration_state_for",
    "pin_decision_basis",
    # recommendation
    "CandidateEvaluator",
    "DecisionRecommendation",
    "RecommendationOutcome",
    "BudgetPlan",
    "information_only_ranking",
]
