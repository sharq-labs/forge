"""Minimal next-action layer.

This package is not a scientific authority. ``transition`` selects a typed
action or stop. ``handlers`` dispatches an already selected action to an
existing FORGE authority and returns that authority's typed result.
"""

from .transition import (
    SOFTWARE_VERSION,
    POLICY_VERSION,
    ActionResult,
    ActionType,
    BoundaryRequest,
    CandidateAction,
    DecisionValue,
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
    apply_result,
    review_proposal,
    select_next_action,
)

__all__ = [
    "POLICY_VERSION",
    "SOFTWARE_VERSION",
    "DecisionValue",
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
