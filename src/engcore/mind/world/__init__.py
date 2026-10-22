"""GEN2-BR1: ScientificWorld + FeasibleActionSpace v1, the first Generation-2 Mind capability (research layer).

A :class:`ScientificWorld` is a read-only, content-addressed reasoning VIEW over declared and authoritative records:
variables (each with its reused Gen1 role declaration), the protocol's actions, constraints and channels, the model
records whose applicability gates model execution, verbatim provider status, the budget as its owner records state
it, and typed references to what it summarizes.  A :class:`FeasibleActionSpace` checks whether a
:class:`ProposedAction` may be executed as declared, with a structured :class:`FeasibilityDecision`.

Neither issues SUPPORTED, REFUSED, a scientific truth, a hypothesis status or an evidence admission; a feasibility
decision is pre-execution admissibility only (``action_feasibility_not_scientific_support``).  The Mind reads and
proposes through a :class:`MindWorldPort`, which reaches no executor.

GEN2-BR1.1: a world holding owner facts is a PROJECTION (:func:`project_world`) of a :class:`ProtocolDeclaration`
and the owner records it points at; every projected fact carries an :class:`AuthorityBinding`.  Only
:func:`admit`, run by the execution side with its own :class:`Authorities`, verifies the world against its owners
and mints an :class:`AdmittedAction`; only :func:`authorize_dispatch` (or an :class:`ExecutionDesk`) re-admits it
against the owners as they are at dispatch and hands an executor a :class:`DispatchAuthorization`.  Nothing here
dispatches, reserves a budget or invokes a provider (that stays the execution owner's).

Imported by its own path, ``engcore.mind.world``: it is not re-exported from ``engcore.mind`` or from the Gen1
packages (both byte-pinned by the sealed Gen1 reference), and nothing certified imports it.
"""

from .actions import (
    ActionMode, ActionSpec, ControlSpec, ExecutionKind, FORBIDDEN_PROPOSAL_KEYS, IntakeCode, IntakeRefusal,
    ProposedAction, proposed_action_from_suggestion, suggestion_from_dict,
)
from .admission import (
    AdmissionRecord, AdmissionResult, AdmittedAction, DispatchAuthorization, DispatchRefused, ExecutionDesk, admit,
    authorize_dispatch, replay_admission,
)
from .authority import Authorities, AuthorityBinding, AuthorityReport, BindingCheck, BindingStatus, OwnerKind
from .base import ProposalRefused, RecordKind, RecordRef, SOFTWARE_VERSION, StaleProposal, WorldRefused
from .declaration import BudgetSource, ProtocolDeclaration, ValueSource
from .domains import ALL_ACTIONS, DeclaredConstraint, DiscreteLevels, Guard
from .feasibility import (
    ANNOTATION_KEYS, CLASSIFICATION, COVERAGE_BAND, REASON_CODES, CheckFamily, FeasibilityDecision, FeasibilityReason,
    FeasibilityStatus, FeasibleActionSpace, replay_decision,
)
from .owners import (
    BudgetReader, DeclarationReader, ModelRegistryReader, ProviderRegistryReader, RunStateReader, UnitRegistryReader,
)
from .port import MindWorldPort
from .projection import project_world, verify_world
from .variables import (
    Controllability, Entity, Observability, ObservationChannel, TemporalSemantics, ValueOrigin, WorldVariable,
)
from .world import (
    ApplicabilityBinding, BudgetStatement, Lineage, ProviderSnapshot, ScientificWorld, WorldBudget,
    restatement_problem, verify_lineage,
)

__all__ = [
    "ALL_ACTIONS", "ANNOTATION_KEYS", "ActionMode", "ActionSpec", "AdmissionRecord", "AdmissionResult",
    "AdmittedAction", "ApplicabilityBinding", "Authorities", "AuthorityBinding", "AuthorityReport", "BindingCheck",
    "BindingStatus", "BudgetReader", "BudgetSource", "BudgetStatement", "CLASSIFICATION", "COVERAGE_BAND",
    "CheckFamily", "ControlSpec", "Controllability", "DeclarationReader", "DeclaredConstraint", "DiscreteLevels",
    "DispatchAuthorization", "DispatchRefused", "Entity", "ExecutionDesk", "ExecutionKind", "FORBIDDEN_PROPOSAL_KEYS",
    "FeasibilityDecision", "FeasibilityReason", "FeasibilityStatus", "FeasibleActionSpace", "Guard", "IntakeCode",
    "IntakeRefusal", "Lineage", "MindWorldPort", "ModelRegistryReader", "Observability", "ObservationChannel",
    "OwnerKind", "ProposalRefused", "ProposedAction", "ProtocolDeclaration", "ProviderRegistryReader",
    "ProviderSnapshot", "REASON_CODES", "RecordKind", "RecordRef", "RunStateReader", "SOFTWARE_VERSION",
    "ScientificWorld", "StaleProposal", "TemporalSemantics", "UnitRegistryReader", "ValueOrigin", "ValueSource",
    "WorldBudget", "WorldRefused", "WorldVariable", "admit", "authorize_dispatch", "project_world",
    "proposed_action_from_suggestion", "replay_admission", "replay_decision", "restatement_problem",
    "suggestion_from_dict", "verify_lineage", "verify_world",
]
