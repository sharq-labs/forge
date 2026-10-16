"""Minimal next-action layer.

This package is not a scientific authority. It does not assess claims,
applicability, uncertainty, validation, or physical feasibility. Those
verdicts stay with the authorities that already issued them. The only
decision here is which typed action to take next, or whether to stop.
"""

from .transition import (
    ActionResult,
    ActionType,
    BoundaryRequest,
    CandidateAction,
    Dependency,
    DependencyKind,
    DependencyStatus,
    HypothesisStatus,
    InformationGain,
    LlmActionProposal,
    MindProblem,
    MindHypothesis,
    MindRefusal,
    MindState,
    ProposalRecord,
    ResultKind,
    Selection,
    SOFTWARE_VERSION,
    apply_result,
    review_proposal,
    select_next_action,
)

__all__ = [
    "SOFTWARE_VERSION",
    "ActionResult",
    "ActionType",
    "BoundaryRequest",
    "CandidateAction",
    "Dependency",
    "DependencyKind",
    "DependencyStatus",
    "HypothesisStatus",
    "InformationGain",
    "LlmActionProposal",
    "MindHypothesis",
    "MindProblem",
    "MindRefusal",
    "MindState",
    "ProposalRecord",
    "ResultKind",
    "Selection",
    "apply_result",
    "review_proposal",
    "select_next_action",
]
