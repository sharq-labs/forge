"""Experiments: studies over problems, and the optimizer boundary."""

from .evaluation import EvaluationStatus, ScientificEvaluation
from .experiment import (
    ExperimentBudget,
    ScientificExperiment,
    candidate_from_parameters,
)
from .optimizer_adapter import (
    CandidateCodec,
    NumericSearchBackend,
    ObjectiveEncoder,
    OptimizerAdapter,
)

__all__ = [
    "EvaluationStatus",
    "ScientificEvaluation",
    "ExperimentBudget",
    "ScientificExperiment",
    "candidate_from_parameters",
    "CandidateCodec",
    "NumericSearchBackend",
    "ObjectiveEncoder",
    "OptimizerAdapter",
]
