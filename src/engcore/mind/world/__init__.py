"""GEN2-BR1: ScientificWorld + FeasibleActionSpace v1, the first Generation-2 Mind capability (research layer).

A :class:`ScientificWorld` is a read-only, content-addressed reasoning VIEW over declared and authoritative records:
variables (each with its reused Gen1 role declaration), the protocol's actions, constraints and channels, the model
records whose applicability gates model execution, verbatim provider status, the budget as its owner records state
it, and typed references to what it summarizes.  A :class:`FeasibleActionSpace` checks whether a
:class:`ProposedAction` may be executed as declared, with a structured :class:`FeasibilityDecision`.

Neither issues SUPPORTED, REFUSED, a scientific truth, a hypothesis status or an evidence admission; a feasibility
decision is pre-execution admissibility only (``action_feasibility_not_scientific_support``).  The Mind reads and
proposes through a :class:`MindWorldPort`, which reaches no executor.  A FEASIBLE decision yields a
:class:`ClearedAction`, the admitted-action record handed to the existing execution system; nothing here dispatches,
reserves a budget or invokes a provider (that stays the execution owner's).

Imported by its own path, ``engcore.mind.world``: it is not re-exported from ``engcore.mind`` or from the Gen1
packages (both byte-pinned by the sealed Gen1 reference), and nothing certified imports it.
"""

from .actions import (
    ActionMode, ActionSpec, ControlSpec, ExecutionKind, FORBIDDEN_PROPOSAL_KEYS, IntakeCode, IntakeRefusal,
    ProposedAction, proposed_action_from_suggestion, suggestion_from_dict,
)
from .base import ProposalRefused, RecordKind, RecordRef, SOFTWARE_VERSION, StaleProposal, WorldRefused
from .domains import ALL_ACTIONS, DeclaredConstraint, DiscreteLevels, Guard
from .feasibility import (
    ANNOTATION_KEYS, CLASSIFICATION, REASON_CODES, CheckFamily, ClearedAction, FeasibilityDecision, FeasibilityReason,
    FeasibilityStatus, FeasibleActionSpace, replay_decision,
)
from .port import MindWorldPort
from .variables import (
    Controllability, Entity, Observability, ObservationChannel, TemporalSemantics, ValueOrigin, WorldVariable,
)
from .world import (
    ApplicabilityBinding, Lineage, ProviderSnapshot, ScientificWorld, WorldBudget, restatement_problem, verify_lineage,
)

__all__ = [
    "ALL_ACTIONS", "ANNOTATION_KEYS", "ActionMode", "ActionSpec", "ApplicabilityBinding", "CLASSIFICATION",
    "CheckFamily", "ClearedAction", "ControlSpec", "Controllability", "DeclaredConstraint", "DiscreteLevels", "Entity",
    "ExecutionKind", "FORBIDDEN_PROPOSAL_KEYS", "FeasibilityDecision", "FeasibilityReason", "FeasibilityStatus",
    "FeasibleActionSpace", "Guard", "IntakeCode", "IntakeRefusal", "Lineage", "MindWorldPort", "Observability",
    "ObservationChannel", "ProposalRefused", "ProposedAction", "ProviderSnapshot", "REASON_CODES", "RecordKind",
    "RecordRef", "SOFTWARE_VERSION", "ScientificWorld", "StaleProposal", "TemporalSemantics", "ValueOrigin",
    "WorldBudget", "WorldRefused", "WorldVariable", "proposed_action_from_suggestion", "replay_decision",
    "restatement_problem", "suggestion_from_dict", "verify_lineage",
]
