"""SRIA V0.1 M2 — computational calibration.

M2 is the first genuinely learning part of SRIA. It predicts *computational*
behaviour — how long a run will take, whether it will fail, how configurations
relate — and it deliberately decides nothing. Choosing what experiment to run,
whether to explore or optimize, when to stop, and what is scientifically valid
all belong to later milestones.

The boundary that makes this safe: nothing here consumes the legacy
``EvaluationStatus``. Every legacy outcome enters through
:mod:`~engcore.sria.calibration.outcome_bridge`, which refuses to guess a cause
that historical records do not contain and marks such rows ineligible for
supervised failure learning. That gate is enforced by test, not convention.

Calibration is keyed by structure × environment, never by scientific domain
name — the property M1 established and M2 relies on for any transfer between
domains that share a computational shape.
"""

from __future__ import annotations

from .cost_model import (
    COST_MODEL_VERSION,
    CostEvaluation,
    CostModel,
    CostPrediction,
    cost_baselines,
    evaluate_cost,
)
from .critic import (
    CalibrationCritic,
    CalibrationReport,
    CalibrationVerdict,
    Diagnostic,
    NotDecisionGrade,
)
from .dataset import (
    GroupedSplit,
    LeakageError,
    assert_group_key_not_a_feature,
    assert_no_group_leakage,
    group_counts,
    grouped_folds,
    grouped_split,
)
from .failure_model import (
    FAILURE_MODEL_VERSION,
    feasibility_records,
    FailureEvaluation,
    FailureModel,
    FailurePrediction,
    InsufficientFailureData,
    base_rate_baseline,
    eligible_records,
    evaluate_failure,
)
from .fidelity import (
    FidelityDataStatus,
    FidelityOwnership,
    FidelityRung,
    FidelitySemanticError,
    KNOWN_STRATEGY_IDENTITIES,
    ModelFidelityRelationship,
    assert_not_a_strategy_identity,
    fidelity_corpus_status,
)
from .strategy_relationships import (
    RelationshipKind,
    StrategyCostRelationship,
    learn_strategy_cost_ratios,
    strategy_success_rates,
)
from .ingest import (
    CAMPAIGN_ENVIRONMENT,
    corpus_summary,
    load_corpus,
    load_runs_csv,
    structure_for,
)
from .learning_record import (
    ComputationalLearningRecord,
    LearningRecordError,
    record_from_bridged_outcome,
)
from .memory import (
    CalibrationMemory,
    CalibrationMemoryEntry,
    Consumer,
    MemoryKind,
)
from .outcome_bridge import (
    BridgedOutcome,
    CENSORING_EVIDENCE,
    FAILURE_KIND_EVIDENCE,
    LEGACY_MAPPING_TABLE,
    MappingConfidence,
    bridge_evaluation,
    bridge_evaluation_status,
    mapping_table_rows,
)

__all__ = [
    # M2A bridge
    "BridgedOutcome",
    "MappingConfidence",
    "bridge_evaluation",
    "bridge_evaluation_status",
    "mapping_table_rows",
    "LEGACY_MAPPING_TABLE",
    "FAILURE_KIND_EVIDENCE",
    "CENSORING_EVIDENCE",
    # learning record
    "ComputationalLearningRecord",
    "LearningRecordError",
    "record_from_bridged_outcome",
    # dataset / leakage
    "GroupedSplit",
    "LeakageError",
    "grouped_split",
    "grouped_folds",
    "group_counts",
    "assert_no_group_leakage",
    "assert_group_key_not_a_feature",
    # cost
    "CostModel",
    "CostPrediction",
    "CostEvaluation",
    "cost_baselines",
    "evaluate_cost",
    "COST_MODEL_VERSION",
    # failure
    "FailureModel",
    "FailurePrediction",
    "FailureEvaluation",
    "InsufficientFailureData",
    "eligible_records",
    "feasibility_records",
    "evaluate_failure",
    "base_rate_baseline",
    "FAILURE_MODEL_VERSION",
    # strategy / algorithm relationships (NOT fidelity)
    "StrategyCostRelationship",
    "RelationshipKind",
    "learn_strategy_cost_ratios",
    "strategy_success_rates",
    # model fidelity (contract only in M2)
    "FidelityRung",
    "ModelFidelityRelationship",
    "FidelityOwnership",
    "FidelityDataStatus",
    "FidelitySemanticError",
    "assert_not_a_strategy_identity",
    "fidelity_corpus_status",
    "KNOWN_STRATEGY_IDENTITIES",
    # memory
    "CalibrationMemory",
    "CalibrationMemoryEntry",
    "MemoryKind",
    "Consumer",
    # critic
    "CalibrationCritic",
    "CalibrationReport",
    "CalibrationVerdict",
    "Diagnostic",
    "NotDecisionGrade",
    # ingest
    "load_runs_csv",
    "load_corpus",
    "corpus_summary",
    "structure_for",
    "CAMPAIGN_ENVIRONMENT",
]
