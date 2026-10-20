"""The Minimal Mind (BR-MIND-01): the smallest closed scientific loop, built on the canonical owners.

    state view -> competing hypotheses -> pre-result predictions -> candidate experiments -> selection -> execution
    -> evidence release / sealed falsifier verdicts -> belief update -> stop / replan

Canonical owners reused, never duplicated: hypotheses are :class:`engcore.sria.decision.Hypothesis` records; their
statuses come only from :mod:`engcore.claims.falsification` (sealed falsifiers, an exposure authority's clock, verified
against the expected registry anchor); candidates carry :class:`engcore.sria.decision.ActionProposal` provenance with an
:class:`~engcore.sria.decision.ActionFamily`; outside suggestions enter only as
:class:`~engcore.sria.decision.ExternalSuggestion`; utility terms are :class:`~engcore.sria.decision.ScoreComponent`
records; the search's multiplicity is counted by :class:`engcore.claims.multiplicity.MultiplicityLedger`.

What is new here (no existing owner computes it): a posterior over rival structures from admitted evidence, a
hypothesis-conditioned outcome model, an expected-discrimination experiment selection, a falsifier role, a stopping
rule, and content-addressed step records with exact replay.  This layer issues no verdict, admits no evidence, sets
no uncertainty an authority did not derive, and promotes nothing: its conclusion is a proposal for the caller's
authority.
"""

from .competition import HypothesisCompetition, mixture_logscore, pure_error
from .experiments import ExperimentCandidate, Selection, from_suggestion
from .outcome_model import AdmittedObservation, OutcomeModel, OutcomeModelRefused, OutcomePrediction
from .problem import ExperimentalProblem, InputSpec, ProblemRefused
from .runner import (
    FULL, MIND_ID, MIND_VERSION, NO_ADAPTIVE_SELECTION, NO_BELIEF_UPDATE, NO_FALSIFIER, PRECISION, VARIANTS,
    ConclusionKind, FittedLaw, MindConclusion, MindConfig, MindRun, ObservationRefused, conclude, replay, run_mind,
)
from .stopping import StopDecision, StopKind
from .structures import Structure, StructureRefused
from .trace import ReplayRefused, verify_chain

__all__ = [
    "AdmittedObservation", "ConclusionKind", "ExperimentCandidate", "ExperimentalProblem", "FULL", "FittedLaw",
    "HypothesisCompetition", "InputSpec", "MIND_ID", "MIND_VERSION", "MindConclusion", "MindConfig", "MindRun",
    "NO_ADAPTIVE_SELECTION", "NO_BELIEF_UPDATE", "NO_FALSIFIER", "ObservationRefused", "OutcomeModel", "OutcomeModelRefused",
    "OutcomePrediction", "PRECISION", "ProblemRefused", "ReplayRefused", "Selection", "StopDecision", "StopKind", "Structure",
    "StructureRefused", "VARIANTS", "conclude", "from_suggestion", "mixture_logscore", "pure_error", "replay", "run_mind",
    "verify_chain",
]
