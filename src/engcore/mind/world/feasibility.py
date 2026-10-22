"""The FeasibleActionSpace and its check: may this proposal be executed as declared, here, now?

This is pre-execution ADMISSIBILITY of an action, nothing more.  Its outcome is classified
``action_feasibility_not_scientific_support``: it is not evidence, not a hypothesis status, not a validation, not a
physical-infeasibility claim, never a ``RunOutcome`` or an ``AttributedCause.INFEASIBLE`` (those describe executed
runs), and never an evidence admission (``sria.admission``).  It is computed only from what the world states.

Statuses (the brief's seven plus one): FEASIBLE; INFEASIBLE_DOMAIN (a value outside its declared domain, a wrong
kind or dimension, or a variable the action does not offer); INFEASIBLE_PROTOCOL (outside a limit the protocol
metadata declares: a level, a fixed condition, a protocol constraint); INFEASIBLE_STATE (the state forbids it, or it
would set a state directly); INFEASIBLE_APPLICABILITY (a model execution outside its model's validity domain, as the
core ``ScientificModelDefinition.assess_validity`` decides: the core status travels verbatim); INFEASIBLE_PROVIDER
(the provider authority's snapshot does not allow it); INFEASIBLE_BUDGET (more than the budget owner says remains);
MISSING_INFORMATION (something needed to decide is absent or undecidable: never a default, never FEASIBLE).

Every check family runs on every proposal and records itself; reasons are collected, not short-circuited; the status
is the first by a fixed precedence (a definite infeasibility outranks missing information).  A decision cannot be
FEASIBLE unless all nine families ran and none left a reason.  Reason codes and annotation keys are a closed set
(:data:`REASON_CODES`, :data:`ANNOTATION_KEYS`): a record cannot carry a verdict word the check never produces.  No
clock, randomness or environment is read.

Monotonicity.  Removing information about the system (a value, an uncertainty, a provider or budget statement)
never turns a refusal FEASIBLE: every family that needs a value reports its absence.  A declaration is the question
itself, not information about the system: withdrawing a declared domain, constraint or precondition changes what is
asked.  The state-domain check therefore reads only what the decision uses (precondition metrics, the metrics of
constraints in force, gating applicability inputs), where an absent value is already MISSING_INFORMATION.

A FEASIBLE decision produces a :class:`ClearedAction`: an admitted-action record for the existing execution system.
Nothing here dispatches, reserves budget or invokes a provider; that is the execution owner's (see the BR1 README).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from engcore.mind.repsem.roles import RoleSource, VariableRole
from engcore.design.grammar import ConstraintStatus
from engcore.execution.orchestration.resources import ResourceUsage
from engcore.mind.repsem import canonical_bytes
from engcore.scientific import Quantity, ScientificCoreError, ScientificProblem, ValidityStatus
from engcore.scientific.models.definition import UnknownReason
from engcore.scientific.results.requirements import unmet_uncertainty_requirements
from engcore.scientific.results.uncertainty import UncertaintyKind
from engcore.scientific.results.immutable import detach, freeze
from engcore.sria.actions import FeasibilityVerdict
from engcore.sria.decision.replay import ReplayMode, ReplayOutcome, ReplayResult

from .actions import ActionMode, ActionSpec, ExecutionKind, ProposedAction, proposed_action_from_suggestion
from .base import (
    ProposalRefused, StaleProposal, WorldRefused, converts, digest, expect_schema, same_value, schema, value_payload,
)
from .declaration import coverage_demand
from .domains import check_at_edges, edges_in_domain, finite_members, is_finite, membership
from .variables import SET_BY_DECLARATION, ValueOrigin
from .world import APPLICABILITY_CONTEXT_ROLES, BUDGET_DIMENSIONS, ScientificWorld

DECISION_SCHEMA = schema("feasibility_decision")
SPACE_SCHEMA = schema("feasible_action_space")
CLASSIFICATION = "action_feasibility_not_scientific_support"
#: The decision rule a value known only within a stated interval is decided under, when the declaration's core
#: uncertainty demand names it and the record meets that demand.  Probabilistic, never a guarantee.
COVERAGE_BAND = "coverage_band_at_declared_level_not_a_guarantee"


class FeasibilityStatus(str, Enum):
    FEASIBLE = "FEASIBLE"
    INFEASIBLE_DOMAIN = "INFEASIBLE_DOMAIN"
    INFEASIBLE_PROTOCOL = "INFEASIBLE_PROTOCOL"
    INFEASIBLE_STATE = "INFEASIBLE_STATE"
    INFEASIBLE_APPLICABILITY = "INFEASIBLE_APPLICABILITY"
    INFEASIBLE_PROVIDER = "INFEASIBLE_PROVIDER"
    INFEASIBLE_BUDGET = "INFEASIBLE_BUDGET"
    MISSING_INFORMATION = "MISSING_INFORMATION"


F = FeasibilityStatus
#: A definite infeasibility outranks missing information; among infeasibilities, the most fundamental first.
PRECEDENCE = (F.INFEASIBLE_DOMAIN, F.INFEASIBLE_PROTOCOL, F.INFEASIBLE_STATE, F.INFEASIBLE_APPLICABILITY,
              F.INFEASIBLE_PROVIDER, F.INFEASIBLE_BUDGET, F.MISSING_INFORMATION)

#: Who declared a limit decides under which status its violation is reported.  Exhaustive over the declarable sources
#: (the legacy adapter default is refused at construction and never reaches a check).
STATUS_BY_SOURCE: Mapping[RoleSource, FeasibilityStatus] = {
    RoleSource.PROTOCOL_METADATA: F.INFEASIBLE_PROTOCOL,
    RoleSource.PROBLEM_SPECIFICATION: F.INFEASIBLE_DOMAIN,
}


class CheckFamily(str, Enum):
    ACTION = "action"
    ROLE = "role"
    DOMAIN = "domain"
    OBSERVE = "observe"
    PROTOCOL = "protocol"
    STATE = "state"
    APPLICABILITY = "applicability"
    PROVIDER = "provider"
    BUDGET = "budget"
    AUTHORITY = "authority"          # admission only: a binding its owner no longer states (never run by check)


#: The families a check runs; AUTHORITY is verified by admission against the owners, before any check.
CHECKED_FAMILIES = tuple(f for f in CheckFamily if f is not CheckFamily.AUTHORITY)
#: Why a value known only within its uncertainty cannot decide: no declared coverage demand names it (a coverage
#: below 1 is never an enclosure), the record does not meet the core demand, or it states no interval.
UNDECIDABLE_WHY = ("ENCLOSURE_REQUIRED", "COVERAGE_REQUIREMENT_UNMET", "COVERAGE_BAND_NOT_STATED")


_MEMBERSHIP_CODES = ("VALUE_KIND_MISMATCH", "UNIT_INCOMPATIBLE", "LEVEL_NOT_DECLARED", "OUTSIDE_RANGE",
                     "CATEGORY_NOT_DECLARED")
#: Every reason code a family emits.  Closed: a record with any other code is refused.
REASON_CODES: Mapping[CheckFamily, frozenset[str]] = {
    CheckFamily.ACTION: frozenset({"UNDECLARED_ACTION"}),
    CheckFamily.ROLE: frozenset({"UNDECLARED_VARIABLE", "FIXED_CONDITION_CHANGED", "STATE_NOT_DIRECTLY_SETTABLE",
                                 "PROTOCOL_CONDITION_NOT_SELECTABLE", "CONTROL_NOT_OFFERED_BY_ACTION",
                                 "ROLE_NOT_CONTROLLABLE"}),
    CheckFamily.DOMAIN: frozenset({"GUARD_UNRESOLVED", "CONTROL_INACTIVE", "CONTROL_NOT_SUPPLIED",
                                   *_MEMBERSHIP_CODES}),
    CheckFamily.OBSERVE: frozenset({"OBSERVE_TARGETS_NOT_SUPPLIED", "UNDECLARED_VARIABLE", "LATENT_NOT_OBSERVABLE",
                                    "DERIVED_NOT_OBSERVABLE", "NO_OBSERVATION_CHANNEL",
                                    "OBSERVABLE_NOT_OFFERED_BY_ACTION"}),
    CheckFamily.PROTOCOL: frozenset({"GUARD_UNRESOLVED", "CONSTRAINT_UNRESOLVED", "CONSTRAINT_UNDECIDABLE",
                                     "CONSTRAINT_VIOLATED", "CONSTRAINT_UNDECIDED", "CONSTRAINT_UNRESOLVABLE",
                                     *(f"CONSTRAINT_{w}" for w in UNDECIDABLE_WHY)}),
    CheckFamily.STATE: frozenset({"PRECONDITION_UNRESOLVED", "PRECONDITION_UNCERTAINTY_UNKNOWN",
                                  "PRECONDITION_VIOLATED", "PRECONDITION_UNDECIDED", "PRECONDITION_UNRESOLVABLE",
                                  "STATE_DOMAIN_UNDECIDABLE", "STATE_OUTSIDE_DECLARED_DOMAIN",
                                  "STATE_DOMAIN_UNDECIDED", *(f"PRECONDITION_{w}" for w in UNDECIDABLE_WHY),
                                  *(f"STATE_DOMAIN_{w}" for w in UNDECIDABLE_WHY)}),
    CheckFamily.APPLICABILITY: frozenset({"OUTSIDE_VALIDATED_DOMAIN", "APPLICABILITY_INPUT_NOT_EXACT",
                                          "APPLICABILITY_NOT_SUPPLIED", "APPLICABILITY_UNKNOWN",
                                          "APPLICABILITY_NOT_ASSESSABLE"}),
    CheckFamily.PROVIDER: frozenset({"PROVIDER_UNAVAILABLE", "PROVIDER_VERSION_MISMATCH", "PROVIDER_DIGEST_MISMATCH"}),
    CheckFamily.BUDGET: frozenset({"BUDGET_DIMENSION_UNDECLARED", "COST_NOT_DECLARED", "OVER_BUDGET"}),
    CheckFamily.AUTHORITY: frozenset({"AUTHORITY_STALE", "AUTHORITY_MISSING", "AUTHORITY_MISMATCH",
                                      "AUTHORITY_UNVERIFIABLE", "AUTHORITY_OWNER_UNAVAILABLE"}),
}
#: Every annotation key a decision may carry.  ``core_status`` is the core's status as it is (exact inputs only);
#: ``decided_under_coverage`` names every value decided under a declared coverage band (probabilistic, never a
#: guarantee).
ANNOTATION_KEYS = frozenset({"binding_id", "gating", "withheld", "not_exact_inputs", "assessments",
                             "assessment_digests", "error", "core_status", "relied_on_bound_values",
                             "decided_under_coverage", "model_digest"})


def _frozen(detail: Mapping[str, Any]) -> Any:
    return freeze(detach(dict(detail)))


@dataclass(frozen=True)
class FeasibilityReason:
    status: FeasibilityStatus
    code: str
    family: CheckFamily
    subject: str
    message: str
    detail: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", FeasibilityStatus(self.status))
        object.__setattr__(self, "family", CheckFamily(self.family))
        if self.status is F.FEASIBLE:
            raise WorldRefused("a reason explains a non-FEASIBLE outcome")
        if self.code not in REASON_CODES[self.family]:
            raise WorldRefused(f"{self.code!r} is not a {self.family.value} reason code (the set is closed)")
        object.__setattr__(self, "detail", _frozen(self.detail or {}))

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "code": self.code, "family": self.family.value, "subject": self.subject,
                "message": self.message, "detail": detach(self.detail)}


@dataclass(frozen=True)
class FamilyRecord:
    family: CheckFamily
    evaluated: int
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", CheckFamily(self.family))

    def to_dict(self) -> dict[str, Any]:
        return {"family": self.family.value, "evaluated": self.evaluated, "note": self.note}


def _derive_status(reasons: tuple[FeasibilityReason, ...]) -> FeasibilityStatus:
    if not reasons:
        return F.FEASIBLE
    present = {r.status for r in reasons}
    return next(s for s in PRECEDENCE if s in present)


@dataclass(frozen=True)
class FeasibilityDecision:
    status: FeasibilityStatus
    reasons: tuple[FeasibilityReason, ...]
    checked: tuple[FamilyRecord, ...]
    action_id: str
    world_revision: str
    space_id: str
    proposal_digest: str
    annotations: Any = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", FeasibilityStatus(self.status))
        reasons = tuple(sorted(self.reasons, key=lambda r: (PRECEDENCE.index(r.status), r.family.value, r.code,
                                                             r.subject)))
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "checked", tuple(sorted(self.checked, key=lambda c: list(CheckFamily).index(c.family))))
        if self.status is not _derive_status(reasons):
            raise WorldRefused(f"a decision's status {self.status.value} disagrees with its reasons")
        if self.status is F.FEASIBLE and {c.family for c in self.checked} != set(CHECKED_FAMILIES):
            raise WorldRefused("FEASIBLE needs every check family to have run (an unchecked family is not a pass)")
        for item in self.annotations:
            if not isinstance(item, Mapping) or set(item) - ANNOTATION_KEYS:
                raise WorldRefused(f"annotation keys are a closed set {sorted(ANNOTATION_KEYS)}")
        object.__setattr__(self, "annotations", _frozen({"items": list(self.annotations)})["items"])

    @property
    def feasible(self) -> bool:
        return self.status is F.FEASIBLE

    def codes(self) -> tuple[str, ...]:
        return tuple(sorted({r.code for r in self.reasons}))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": DECISION_SCHEMA, "classification": CLASSIFICATION, "status": self.status.value,
                "action_id": self.action_id, "world_revision": self.world_revision, "space_id": self.space_id,
                "proposal_digest": self.proposal_digest, "reasons": [r.to_dict() for r in self.reasons],
                "checked": [c.to_dict() for c in self.checked], "annotations": detach(self.annotations)}

    @property
    def digest(self) -> str:
        return digest(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FeasibilityDecision":
        expect_schema(payload.get("schema"), DECISION_SCHEMA)
        if payload.get("classification") != CLASSIFICATION:
            raise WorldRefused("not a feasibility decision record")
        return cls(FeasibilityStatus(payload["status"]),
                   tuple(FeasibilityReason(r["status"], r["code"], r["family"], r["subject"], r["message"], r["detail"])
                         for r in payload["reasons"]),
                   tuple(FamilyRecord(c["family"], c["evaluated"], c.get("note", "")) for c in payload["checked"]),
                   payload["action_id"], payload["world_revision"], payload["space_id"], payload["proposal_digest"],
                   tuple(payload.get("annotations", ())))

    def feasibility_verdicts(self) -> tuple[FeasibilityVerdict, ...]:
        """Definite infeasibilities only, as SRIA ``FeasibilityVerdict`` records for reporting into its hard gate.

        MISSING_INFORMATION is never exported as a negative verdict, nothing is ever exported as a positive one, and a
        refusal decided under a declared coverage band is a probabilistic refusal, not a definite one: not exported."""
        return tuple(FeasibilityVerdict(f"forge.mind.world:{r.family.value}:{r.code}:{r.subject}", False,
                                        f"{r.status.value}: {r.message}")
                     for r in self.reasons if r.status is not F.MISSING_INFORMATION
                     and r.detail.get("decision_rule") != COVERAGE_BAND)


# ---- value resolution ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _Resolved:
    value: Any
    source: str                    # proposal | fixed_condition | world_declared | world_bound
    edges: tuple[Any, ...] | None  # None: present but undecidable (``why`` says why)
    rule: str = "exact"            # exact | coverage band (COVERAGE_BAND) | undecidable
    why: str = ""                  # UNCERTAINTY_UNKNOWN or one of UNDECIDABLE_WHY
    coverage: float | None = None


def _world_basis(world: ScientificWorld, name: str) -> _Resolved | None:
    """What the world's current value of ``name`` can decide, never more than its uncertainty states.

    * A DECLARED set point (a controlled input or protocol condition) that states no quantified uncertainty is the
      declaration itself: exact as declared.  One that states an uncertainty is decided like any other value.
    * Any other value holds only within its uncertainty.  UNKNOWN decides nothing.  A probabilistic interval
      (every core INTERVAL: its coverage is below 1 or unstated) is never an enclosure; it decides only when the
      declaration's core ``UncertaintySpecification`` demands this variable QUANTIFIED at a confidence level and the
      record meets that demand by the core rule (``unmet_uncertainty_requirements``), and then only as a coverage
      band at that declared level, labelled as such.  Everything else is undecidable, never a default."""
    if not world.declares(name):
        return None
    var = world.variable(name)
    if var.value is None:
        return None
    u = var.uncertainty
    if var.origin is ValueOrigin.DECLARED and var.role in SET_BY_DECLARATION and not u.is_quantified:
        return _Resolved(var.value, "world_declared", (var.value,))
    source = "world_declared" if var.origin is ValueOrigin.DECLARED else "world_bound"
    if not u.is_quantified:
        return _Resolved(var.value, source, None, "undecidable", "UNCERTAINTY_UNKNOWN")
    demand = coverage_demand(world.uncertainty, name)
    if demand is None:
        return _Resolved(var.value, source, None, "undecidable", "ENCLOSURE_REQUIRED")
    problem = ScientificProblem(f"{world.world_id}.uncertainty-demand", uncertainty=world.uncertainty)
    if name in unmet_uncertainty_requirements(problem, {name: u}):
        return _Resolved(var.value, source, None, "undecidable", "COVERAGE_REQUIREMENT_UNMET", demand)
    if u.kind is not UncertaintyKind.INTERVAL:
        return _Resolved(var.value, source, None, "undecidable", "COVERAGE_BAND_NOT_STATED", demand)
    return _Resolved(var.value, source, (u.lower, u.upper), COVERAGE_BAND, "", demand)


def _resolve(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction | None, name: str,
             *, include_proposal: bool = True) -> _Resolved | None:
    """Precedence: the proposal's assignment, then the action's fixed condition, then the world's current value."""
    if include_proposal and proposal is not None:
        v = proposal.value(name)
        if v is not None:
            return _Resolved(v, "proposal", (v,))
    f = spec.fixed(name)
    if f is not None:
        return _Resolved(f.value, "fixed_condition", (f.value,))
    return _world_basis(world, name)


def _rule_detail(r: _Resolved) -> dict[str, Any]:
    return {"decision_rule": COVERAGE_BAND, "coverage": r.coverage} if r.rule == COVERAGE_BAND else {}


class _Collector:
    def __init__(self) -> None:
        self.reasons: list[FeasibilityReason] = []
        self.checked: list[FamilyRecord] = []
        self.annotations: list[dict[str, Any]] = []
        self.bound: set[tuple[str, str, str, str]] = set()
        self.coverage: set[tuple[str, float]] = set()

    def add(self, status: FeasibilityStatus, code: str, family: CheckFamily, subject: str, message: str,
            **detail: Any) -> None:
        self.reasons.append(FeasibilityReason(status, code, family, subject, message, detail))

    def ran(self, family: CheckFamily, evaluated: int, note: str = "") -> None:
        self.checked.append(FamilyRecord(family, evaluated, note))


def canonical(proposal: ProposedAction) -> ProposedAction:
    """The one proposal every family, the digest and any admission are derived from: exactly a ``ProposedAction``,
    rebuilt from its own payload with exact builtin names and typed values, so a subclass, a ``str`` subclass or a
    lazy container cannot show one view to one check and another view to the next."""
    if type(proposal) is not ProposedAction:
        raise WorldRefused("only an exact ProposedAction is checked (a subclass could answer differently per call)")
    return ProposedAction.from_dict(proposal.to_dict())


# ---- the space ------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SpaceEntry:
    action_id: str
    spec_digest: str
    standing: tuple[FeasibilityReason, ...]   # value-independent reasons (provider, budget, state preconditions)

    @property
    def open(self) -> bool:
        return not self.standing

    def to_dict(self) -> dict[str, Any]:
        return {"action_id": self.action_id, "spec_digest": self.spec_digest,
                "standing": [r.to_dict() for r in self.standing]}


@dataclass(frozen=True)
class FeasibleActionSpace:
    """The world's declared actions with their value-independent standing, content-addressed to one world revision.

    Built only from the world (protocol, providers, applicability bindings, budget all live there).  It ranks
    nothing, selects nothing, samples nothing: it checks proposals and enumerates declared finite alternatives."""

    world: ScientificWorld
    entries: tuple[SpaceEntry, ...]
    space_id: str

    @classmethod
    def build(cls, world: ScientificWorld) -> "FeasibleActionSpace":
        if not isinstance(world, ScientificWorld):
            raise WorldRefused("an action space is derived from a ScientificWorld")
        entries = []
        for spec in world.actions:
            c = _Collector()
            _check_state(world, spec, None, c)
            _check_provider(world, spec, c)
            _check_budget(world, spec, c)
            entries.append(SpaceEntry(spec.action_id, spec.digest, tuple(sorted(
                c.reasons, key=lambda r: (PRECEDENCE.index(r.status), r.family.value, r.code, r.subject)))))
        entries = tuple(entries)
        space_id = digest({"schema": SPACE_SCHEMA, "world_revision": world.revision_id,
                           "entries": [e.to_dict() for e in entries]})
        return cls(world, entries, space_id)

    def entry(self, action_id: str) -> SpaceEntry | None:
        for e in self.entries:
            if e.action_id == action_id:
                return e
        return None

    def open_actions(self) -> tuple[str, ...]:
        return tuple(e.action_id for e in self.entries if e.open)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SPACE_SCHEMA, "world_revision": self.world.revision_id, "space_id": self.space_id,
                "entries": [e.to_dict() for e in self.entries]}

    # ---- the check ------------------------------------------------------------------------------------------------------
    def check(self, proposal: ProposedAction) -> FeasibilityDecision:
        proposal = canonical(proposal)
        world = self.world
        if proposal.world_revision != world.revision_id:
            raise StaleProposal(f"the proposal was made for world revision {proposal.world_revision[:12]}, not "
                                f"{world.revision_id[:12]}; a decision stays bound to the world it was made in")
        if proposal.source is not None:
            again = proposed_action_from_suggestion(proposal.source, world=world)
            if not isinstance(again, ProposedAction):
                raise ProposalRefused(f"the proposal's source suggestion is refused at intake here: {again.code.value} "
                                      f"({again.message})")
            if canonical_bytes(again.to_dict()) != canonical_bytes(proposal.to_dict()):
                raise ProposalRefused("the proposal is not what its source suggestion yields in this world")
        c = _Collector()
        spec = world.action(proposal.action_id)
        if spec is None:
            c.add(F.MISSING_INFORMATION, "UNDECLARED_ACTION", CheckFamily.ACTION, proposal.action_id,
                  "the world declares no such action (never inferred from a name)")
            c.ran(CheckFamily.ACTION, 1)
            return self._decision(proposal, c)
        c.ran(CheckFamily.ACTION, 1)
        _check_roles(world, spec, proposal, c)
        _check_domains(world, spec, proposal, c)
        _check_observe(world, spec, proposal, c)
        _check_protocol(world, spec, proposal, c)
        _check_state(world, spec, proposal, c)
        _check_applicability(world, spec, proposal, c)
        _check_provider(world, spec, c)
        _check_budget(world, spec, c)
        return self._decision(proposal, c)

    def _decision(self, proposal: ProposedAction, c: _Collector) -> FeasibilityDecision:
        reasons = tuple(c.reasons)
        relied = [{"relied_on_bound_values": [{"variable": n, "kind": k, "ref": r, "used_for": u}
                                              for n, k, r, u in sorted(c.bound)]}]
        if c.coverage:
            relied.append({"decided_under_coverage": [{"variable": n, "coverage": cov, "rule": COVERAGE_BAND}
                                                      for n, cov in sorted(c.coverage)]})
        return FeasibilityDecision(_derive_status(reasons), reasons, tuple(c.checked), proposal.action_id,
                                   self.world.revision_id, self.space_id, proposal.digest,
                                   tuple(c.annotations) + tuple(relied))

    def alternatives(self, proposal: ProposedAction, variable: str) -> dict[str, Any]:
        """The declared values of one control that would make this proposal FEASIBLE, the rest held as proposed.

        Admissible options, not recommendations: order is the declared order, never a distance to what was asked,
        and nothing is projected.  A continuous control is reported as its declared range, never sampled."""
        proposal = canonical(proposal)
        spec = self.world.action(proposal.action_id)
        control = None if spec is None else spec.control(variable)
        if control is None:
            raise WorldRefused(f"{variable!r} is not a control of action {proposal.action_id!r}")
        label = "admissible options under the declared world, not recommendations"
        if not is_finite(control.domain):
            return {"variable": variable, "kind": "declared_range", "label": label,
                    "range": [control.domain.lower.to_dict(), control.domain.upper.to_dict()]}
        options = []
        for member in finite_members(control.domain):
            trial = ProposedAction(proposal.action_id, proposal.world_revision,
                                   {**dict(proposal.assignments), variable: member}, proposal.observe,
                                   proposal.proposer, proposal.rationale)
            if self.check(trial).feasible:
                options.append(member)
        return {"variable": variable, "kind": "declared_members", "label": label, "options": options}


# ---- the families -----------------------------------------------------------------------------------------------------------------
def _check_roles(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction, c: _Collector) -> None:
    for name, value in proposal.assignments:
        if not world.declares(name):
            c.add(F.MISSING_INFORMATION, "UNDECLARED_VARIABLE", CheckFamily.ROLE, name,
                  "the world declares no such variable (a name is never mapped to a declared one)")
            continue
        if spec.control(name) is not None:
            continue
        fixed = spec.fixed(name)
        if fixed is not None:
            if not same_value(value, fixed.value):
                c.add(F.INFEASIBLE_PROTOCOL, "FIXED_CONDITION_CHANGED", CheckFamily.ROLE, name,
                      "the action holds this condition fixed; a proposal cannot change it",
                      declared=value_payload(fixed.value), proposed=value_payload(value))
            continue
        role = world.role(name)
        if role is VariableRole.STATE_VARIABLE:
            c.add(F.INFEASIBLE_STATE, "STATE_NOT_DIRECTLY_SETTABLE", CheckFamily.ROLE, name,
                  "a state evolves under its declared dynamics; only an explicit state-intervention action sets it")
        elif role is VariableRole.FIXED_PROTOCOL_CONDITION:
            c.add(F.INFEASIBLE_PROTOCOL, "PROTOCOL_CONDITION_NOT_SELECTABLE", CheckFamily.ROLE, name,
                  "this action does not offer a selection of this protocol condition")
        elif role is VariableRole.CONTROLLED_INPUT:
            c.add(F.INFEASIBLE_DOMAIN, "CONTROL_NOT_OFFERED_BY_ACTION", CheckFamily.ROLE, name,
                  "a controlled input changes only through an action that declares it as a control")
        else:
            c.add(F.INFEASIBLE_DOMAIN, "ROLE_NOT_CONTROLLABLE", CheckFamily.ROLE, name,
                  f"a {role.value} is never set by an action", role=role.value)
    c.ran(CheckFamily.ROLE, len(proposal.assignments))


def _guard_value(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction | None, name: str
                 ) -> _Resolved | None:
    r = _resolve(world, spec, proposal, name)
    if r is None or r.source == "world_bound" or r.edges is None or len(r.edges) != 1:
        return None   # a guard decides on a stated value, never on a reading known only within its uncertainty
    return r


def _check_domains(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction, c: _Collector) -> None:
    """Each active control: the value in the variable's own declared unit (the unit owner's conversion with its
    point/difference flag), a member of the action's declared domain, and a member of the variable's own declared
    domain by the owner's pointwise rule at every check (containment at binding is never a substitute)."""
    for control in spec.controls:
        name = control.variable
        assigned = proposal.value(name)
        if control.active_when is not None:
            g = _guard_value(world, spec, proposal, control.active_when.variable)
            if g is None:
                c.add(F.MISSING_INFORMATION, "GUARD_UNRESOLVED", CheckFamily.DOMAIN, name,
                      "whether this control is active depends on a value that is not stated",
                      guard_variable=control.active_when.variable)
                continue
            if not control.active_when.holds(g.value):
                if assigned is not None:
                    c.add(STATUS_BY_SOURCE[control.declared_by], "CONTROL_INACTIVE", CheckFamily.DOMAIN, name,
                          "this control is not available under the stated condition",
                          guard_variable=control.active_when.variable)
                continue
        if assigned is None:
            c.add(F.MISSING_INFORMATION, "CONTROL_NOT_SUPPLIED", CheckFamily.DOMAIN, name,
                  "an active control of the action has no proposed value (never defaulted)")
            continue
        var = world.variable(name)
        if isinstance(assigned, Quantity) and not converts(assigned, var.unit):
            c.add(F.INFEASIBLE_DOMAIN, "UNIT_INCOMPATIBLE", CheckFamily.DOMAIN, name,
                  f"the unit owner does not convert {assigned} into the variable's declared unit {var.unit!r}",
                  declared_by=control.declared_by.value, proposed=value_payload(assigned), expected_unit=var.unit)
            continue
        found = membership(control.domain, assigned)
        if found is None and var.domain is not None:
            found = membership(var.domain, assigned)
            source = var.declaration.source
        else:
            source = control.declared_by
        if found is not None:
            code, message, detail = found
            status = F.INFEASIBLE_DOMAIN if code in ("VALUE_KIND_MISMATCH", "UNIT_INCOMPATIBLE") else \
                STATUS_BY_SOURCE[source]
            c.add(status, code, CheckFamily.DOMAIN, name, message, declared_by=source.value, **detail)
    c.ran(CheckFamily.DOMAIN, len(spec.controls))


def _check_observe(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction, c: _Collector) -> None:
    if spec.mode is ActionMode.OBSERVE and not proposal.observe:
        c.add(F.MISSING_INFORMATION, "OBSERVE_TARGETS_NOT_SUPPLIED", CheckFamily.OBSERVE, spec.action_id,
              "an OBSERVE proposal names what it observes (never defaulted to everything)")
    for name in proposal.observe:
        if not world.declares(name):
            c.add(F.MISSING_INFORMATION, "UNDECLARED_VARIABLE", CheckFamily.OBSERVE, name,
                  "the world declares no such variable")
            continue
        role = world.role(name)
        if role is VariableRole.LATENT_PARAMETER:
            c.add(F.INFEASIBLE_DOMAIN, "LATENT_NOT_OBSERVABLE", CheckFamily.OBSERVE, name,
                  "a latent parameter is estimated, never observed")
        elif role is VariableRole.DERIVED_QUANTITY:
            c.add(F.INFEASIBLE_DOMAIN, "DERIVED_NOT_OBSERVABLE", CheckFamily.OBSERVE, name,
                  "a derived quantity is computed from declared sources, never an independent observation")
        elif not world.has_channel(name):
            c.add(F.INFEASIBLE_DOMAIN, "NO_OBSERVATION_CHANNEL", CheckFamily.OBSERVE, name,
                  "no declared channel records this variable")
        elif name not in spec.expected_observables:
            c.add(F.INFEASIBLE_DOMAIN, "OBSERVABLE_NOT_OFFERED_BY_ACTION", CheckFamily.OBSERVE, name,
                  "this action does not record this observable")
    c.ran(CheckFamily.OBSERVE, len(proposal.observe))


def _note_bound(world: ScientificWorld, c: _Collector, name: str, used_for: str, r: _Resolved | None = None) -> None:
    var = world.variable(name)
    if var.source is not None:
        kind = getattr(var.source, "kind", None) or var.source.owner_kind
        ref = getattr(var.source, "ref", None) or var.source.record_digest
        c.bound.add((name, kind.value, ref, used_for))
    if r is not None and r.rule == COVERAGE_BAND:
        c.coverage.add((name, r.coverage))


def _undecidable(prefix: str, r: _Resolved) -> str:
    return f"{prefix}_UNCERTAINTY_UNKNOWN" if r.why == "UNCERTAINTY_UNKNOWN" and prefix == "PRECONDITION" else \
        f"{prefix}_UNDECIDABLE" if r.why == "UNCERTAINTY_UNKNOWN" else f"{prefix}_{r.why}"


def _check_protocol(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction, c: _Collector) -> None:
    n = 0
    for constraint in world.constraints:
        if not constraint.applies(spec.action_id):
            continue
        n += 1
        cid = constraint.constraint_id
        status = STATUS_BY_SOURCE[constraint.declared_by]
        if constraint.guard is not None:
            g = _guard_value(world, spec, proposal, constraint.guard.variable)
            if g is None:
                c.add(F.MISSING_INFORMATION, "GUARD_UNRESOLVED", CheckFamily.PROTOCOL, cid,
                      "whether this constraint applies depends on a value that is not stated",
                      guard_variable=constraint.guard.variable)
                continue
            if not constraint.guard.holds(g.value):
                continue
        metric = constraint.consequence.metric
        r = _resolve(world, spec, proposal, metric)
        if r is None:
            c.add(F.MISSING_INFORMATION, "CONSTRAINT_UNRESOLVED", CheckFamily.PROTOCOL, cid,
                  "the constrained value is not stated", metric=metric)
            continue
        if r.source == "world_bound":
            _note_bound(world, c, metric, f"constraint {cid}", r)
        if r.edges is None or not all(isinstance(e, Quantity) for e in r.edges):
            c.add(F.MISSING_INFORMATION, _undecidable("CONSTRAINT", r) if r.edges is None else "CONSTRAINT_UNDECIDABLE",
                  CheckFamily.PROTOCOL, cid, "the constrained value's uncertainty does not allow a decision",
                  metric=metric, source=r.source, why=r.why or "not a quantity")
            continue
        outcome, detail = check_at_edges(constraint.consequence, r.edges)
        if outcome is ConstraintStatus.VIOLATED:
            c.add(status, "CONSTRAINT_VIOLATED", CheckFamily.PROTOCOL, cid, f"violates {constraint.basis}",
                  metric=metric, source=r.source, **detail, **_rule_detail(r))
        elif outcome is ConstraintStatus.UNKNOWN:
            c.add(F.MISSING_INFORMATION, f"CONSTRAINT_{detail['why'].upper()}", CheckFamily.PROTOCOL, cid,
                  "the constraint cannot be decided on the stated value", metric=metric, source=r.source, **detail,
                  **_rule_detail(r))
    c.ran(CheckFamily.PROTOCOL, n)


def _check_state(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction | None, c: _Collector) -> None:
    n = 0
    for pre in spec.preconditions:
        n += 1
        r = _world_basis(world, pre.metric)
        if r is None:
            c.add(F.MISSING_INFORMATION, "PRECONDITION_UNRESOLVED", CheckFamily.STATE, pre.name,
                  "the state this precondition reads has no current value", metric=pre.metric)
            continue
        _note_bound(world, c, pre.metric, f"precondition {pre.name}", r)
        if r.edges is None or not all(isinstance(e, Quantity) for e in r.edges):
            c.add(F.MISSING_INFORMATION, _undecidable("PRECONDITION", r) if r.edges is None
                  else "PRECONDITION_UNCERTAINTY_UNKNOWN", CheckFamily.STATE, pre.name,
                  "the current value's uncertainty does not allow a decision (a point value is never treated as "
                  "exact, and a coverage interval is never an enclosure)", metric=pre.metric,
                  uncertainty=world.variable(pre.metric).uncertainty.kind.value, why=r.why or "not a quantity")
            continue
        outcome, detail = check_at_edges(pre, r.edges)
        if outcome is ConstraintStatus.VIOLATED:
            c.add(F.INFEASIBLE_STATE, "PRECONDITION_VIOLATED", CheckFamily.STATE, pre.name,
                  "the current state does not meet the action's precondition", metric=pre.metric, **detail,
                  **_rule_detail(r))
        elif outcome is ConstraintStatus.UNKNOWN:
            c.add(F.MISSING_INFORMATION, f"PRECONDITION_{detail['why'].upper()}", CheckFamily.STATE, pre.name,
                  "the precondition cannot be decided on the current value", metric=pre.metric, **detail,
                  **_rule_detail(r))
    for name in sorted(_used_reads(world, spec, proposal)):
        var = world.variable(name)
        if var.value is None or var.domain is None:
            continue    # an absent value is reported by the family that uses it; no declared domain states no range
        if proposal is not None and (proposal.value(name) is not None or spec.fixed(name) is not None):
            continue
        r = _world_basis(world, name)
        if r is not None and r.source == "world_declared" and r.edges is not None and len(r.edges) == 1:
            continue    # an exact set point, checked against its own domain when the world was built
        n += 1
        if r is None or r.edges is None:
            c.add(F.MISSING_INFORMATION, "STATE_DOMAIN_UNDECIDABLE" if r is None else _undecidable("STATE_DOMAIN", r),
                  CheckFamily.STATE, name, "whether the current value lies in its declared domain cannot be decided "
                  "at its stated uncertainty", uncertainty=var.uncertainty.kind.value,
                  why="" if r is None else r.why)
            continue
        where = edges_in_domain(var.domain, r.edges)
        if where == "outside":
            c.add(F.INFEASIBLE_STATE, "STATE_OUTSIDE_DECLARED_DOMAIN", CheckFamily.STATE, name,
                  "the system's current value lies outside the variable's declared domain (a range: wholly beyond one "
                  "bound at every edge of its stated band)", edges=[value_payload(e) for e in r.edges],
                  **_rule_detail(r))
        elif where == "undecided":
            c.add(F.MISSING_INFORMATION, "STATE_DOMAIN_UNDECIDED", CheckFamily.STATE, name,
                  "whether the current value lies in its declared domain cannot be decided at its uncertainty",
                  edges=[value_payload(e) for e in r.edges], **_rule_detail(r))
        else:
            _note_bound(world, c, name, "state domain", r)
    c.ran(CheckFamily.STATE, n)


def _in_force(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction | None) -> list[Any]:
    """The constraints in force for this proposal: in scope, and with a guard that holds on a stated value.  Without a
    proposal (the space's standing) only unguarded constraints are in force."""
    out = []
    for constraint in world.constraints:
        if not constraint.applies(spec.action_id):
            continue
        if constraint.guard is not None:
            if proposal is None:
                continue
            g = _guard_value(world, spec, proposal, constraint.guard.variable)
            if g is None or not constraint.guard.holds(g.value):
                continue
        out.append(constraint)
    return out


def _used_reads(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction | None) -> set[str]:
    """The current values this decision uses: precondition metrics, metrics of the constraints in force, and the
    inputs of applicability that gates (model execution)."""
    names = {p.metric for p in spec.preconditions}
    names |= {constraint.consequence.metric for constraint in _in_force(world, spec, proposal)}
    if spec.execution is ExecutionKind.MODEL_EXECUTION:
        for binding_id in spec.applicability:
            names |= set(world.applicability_binding(binding_id).reads)
    return {n for n in names if world.declares(n)}


def context_reads(world: ScientificWorld, spec: ActionSpec) -> set[str]:
    """Every variable a decision on this action may read besides its configuration: preconditions, every in-scope
    constraint's metric and guard, every applicability input, every control guard."""
    names = {p.metric for p in spec.preconditions}
    for constraint in world.constraints:
        if constraint.applies(spec.action_id):
            names |= set(constraint.reads)
    for binding_id in spec.applicability:
        names |= set(world.applicability_binding(binding_id).reads)
    names |= {c.active_when.variable for c in spec.controls if c.active_when is not None}
    return {n for n in names if world.declares(n)}


def _check_applicability(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction, c: _Collector) -> None:
    """Model applicability, decided by the core (``ScientificModelDefinition.assess_validity``) at an exact point only.

    The core assesses points; it has no interval form, and an interval is never an enclosure.  So every input the
    model reads must be exact (a proposed or fixed value, or a declared set point with no stated uncertainty); if any
    is not, a gating applicability is MISSING_INFORMATION (``APPLICABILITY_INPUT_NOT_EXACT``) and no world rule
    stands in.  With exact inputs the core status is used as it is."""
    gating = spec.execution is ExecutionKind.MODEL_EXECUTION
    for binding_id in spec.applicability:
        binding = world.applicability_binding(binding_id)
        exact: dict[str, Any] = {}
        withheld: list[str] = []
        not_exact: list[str] = []
        for name in sorted(binding.reads):
            if world.role(name) not in APPLICABILITY_CONTEXT_ROLES:
                withheld.append(name)
                continue
            r = _resolve(world, spec, proposal, name)
            if r is None:
                continue
            if r.source == "world_bound":
                _note_bound(world, c, name, f"applicability {binding_id}")
            if r.edges is not None and len(r.edges) == 1 and r.rule == "exact":
                exact[name] = r.edges[0]
            else:
                not_exact.append(name)
        annotation: dict[str, Any] = {"binding_id": binding_id, "gating": gating, "withheld": withheld,
                                      "not_exact_inputs": not_exact, "core_status": None, "assessments": [],
                                      "assessment_digests": [], "error": "",
                                      "model_digest": digest(binding.model.to_dict())}
        assessment = None
        if not not_exact:
            try:
                assessment = binding.assess(exact)
            except ScientificCoreError as exc:
                annotation["error"] = str(exc)
        if assessment is not None:
            recorded = assessment.to_dict()
            annotation.update({"core_status": assessment.status.value, "assessments": [recorded],
                               "assessment_digests": [digest(recorded)]})
        c.annotations.append(annotation)
        if not gating:
            continue
        if not_exact:
            c.add(F.MISSING_INFORMATION, "APPLICABILITY_INPUT_NOT_EXACT", CheckFamily.APPLICABILITY, binding_id,
                  "the model reads a value known only within its uncertainty; the core assesses exact points only, "
                  "so model execution is not admitted on it (no world rule stands in)", not_exact=not_exact)
        elif annotation["error"]:
            c.add(F.MISSING_INFORMATION, "APPLICABILITY_NOT_ASSESSABLE", CheckFamily.APPLICABILITY, binding_id,
                  "the core could not assess applicability on the stated values", error=annotation["error"])
        elif assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
            c.add(F.INFEASIBLE_APPLICABILITY, "OUTSIDE_VALIDATED_DOMAIN", CheckFamily.APPLICABILITY, binding_id,
                  "the model this action executes is not applicable at this point (the core's status as it is)",
                  validity_status=assessment.status.value, violated=sorted(assessment.violated),
                  assessment_digests=annotation["assessment_digests"])
        elif assessment.status is ValidityStatus.UNKNOWN:
            reasons = sorted({u.reason.value for u in assessment.unknown_reasons})
            not_supplied = reasons == [UnknownReason.NOT_SUPPLIED.value]
            c.add(F.MISSING_INFORMATION, "APPLICABILITY_NOT_SUPPLIED" if not_supplied else "APPLICABILITY_UNKNOWN",
                  CheckFamily.APPLICABILITY, binding_id,
                  "model applicability is UNKNOWN here; model execution is not admitted on an unknown applicability",
                  validity_status=ValidityStatus.UNKNOWN.value, unknown_reasons=reasons,
                  unknown=sorted(assessment.unknown), withheld=withheld)
    c.ran(CheckFamily.APPLICABILITY, len(spec.applicability),
          "gates model execution" if gating else "annotation only (not a model execution)")


def _check_provider(world: ScientificWorld, spec: ActionSpec, c: _Collector) -> None:
    for req in spec.provider_requirements:
        snap = world.provider(req.provider_id)
        pid = req.provider_id
        if snap is None:
            c.add(F.INFEASIBLE_PROVIDER, "PROVIDER_UNAVAILABLE", CheckFamily.PROVIDER, pid,
                  "the world holds no status for this provider; no substitute is chosen")
        elif not snap.executable:
            c.add(F.INFEASIBLE_PROVIDER, "PROVIDER_UNAVAILABLE", CheckFamily.PROVIDER, pid,
                  f"the provider is {snap.availability.value} / {snap.health.value}; no substitute is chosen",
                  availability=snap.availability.value, health=snap.health.value, reason=snap.reason)
        elif snap.version != req.provider_version:
            c.add(F.INFEASIBLE_PROVIDER, "PROVIDER_VERSION_MISMATCH", CheckFamily.PROVIDER, pid,
                  "the available build is another version", available=snap.version, required=req.provider_version)
        elif req.provider_digest and snap.build_digest != req.provider_digest:
            c.add(F.INFEASIBLE_PROVIDER, "PROVIDER_DIGEST_MISMATCH", CheckFamily.PROVIDER, pid,
                  "the available build differs from the pinned digest")
    c.ran(CheckFamily.PROVIDER, len(spec.provider_requirements))


def _check_budget(world: ScientificWorld, spec: ActionSpec, c: _Collector) -> None:
    budget = world.budget
    for dim in BUDGET_DIMENSIONS:
        state = budget.status(dim)
        if state == "undeclared":
            c.add(F.MISSING_INFORMATION, "BUDGET_DIMENSION_UNDECLARED", CheckFamily.BUDGET, dim,
                  "the world neither limits this budget dimension nor declares it unbounded")
            continue
        if state == "unbounded":
            continue
        amount = spec.estimated_duration if dim == "wall_time" else spec.cost(dim)
        if amount is None:
            c.add(F.MISSING_INFORMATION, "COST_NOT_DECLARED", CheckFamily.BUDGET, dim,
                  "the budget is limited and the action does not declare what it consumes (never assumed zero)")
            continue
        statement = budget.statement(dim)
        if statement is not None:                          # the owner record's own rule, on the raw amount
            requested = amount if dim == "wall_time" else (amount.magnitude if dim == "cost" else amount.value)
            ok, remaining = statement.decide(requested, spec.family)
            if isinstance(requested, Quantity):
                requested = requested.magnitude_in("second")
        else:
            remaining = budget.remaining(dim)
            if dim == "cost":                                   # the plan's own rule, on the raw amount
                requested = amount.magnitude
                ok = budget.cost.affordable(requested, family=spec.family)
            elif dim == "wall_time":                            # the execution owner's rule (ResourceUsage.exceeded)
                requested = amount.magnitude_in("second")
                ok = "wall_seconds" not in budget.compute_used.plus(ResourceUsage(wall_seconds=requested)).exceeded(
                    budget.compute)
            elif dim == "solver_calls":
                requested = amount.value
                ok = "function_evaluations" not in budget.compute_used.plus(
                    ResourceUsage(function_evaluations=requested)).exceeded(budget.compute)
            else:
                requested = amount.value
                ok = requested <= remaining
        if not ok:
            c.add(F.INFEASIBLE_BUDGET, "OVER_BUDGET", CheckFamily.BUDGET, dim,
                  "the action needs more than the budget owner says remains", requested=requested, remaining=remaining)
    c.ran(CheckFamily.BUDGET, len(BUDGET_DIMENSIONS))


# ---- replay -------------------------------------------------------------------------------------------------------------------------
def replay_decision(record: Mapping[str, Any], world_payload: Mapping[str, Any],
                    proposal_payload: Mapping[str, Any]) -> ReplayResult:
    """Re-execute a stored decision from its stored world and proposal (``sria.decision.replay`` vocabulary).

    The stored inputs are verified against the decision's bindings BEFORE anything is recomputed; a mismatch there is
    REPLAY_DEPENDENCY_UNAVAILABLE (and never REPRODUCED).  Then the decision is recomputed and compared byte for byte."""
    mode = ReplayMode.EXECUTABLE_REPLAY
    mismatches = []
    try:
        world = ScientificWorld.from_dict(world_payload)
    except (WorldRefused, ScientificCoreError, KeyError, TypeError, ValueError) as exc:
        return ReplayResult(mode, ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE, dict(record), mismatches=("world",),
                            detail=f"the stored world does not rebuild: {exc}")
    try:
        proposal = ProposedAction.from_dict(proposal_payload)
    except (WorldRefused, ScientificCoreError, KeyError, TypeError, ValueError) as exc:
        return ReplayResult(mode, ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE, dict(record), mismatches=("proposal",),
                            detail=f"the stored proposal does not rebuild: {exc}")
    if record.get("world_revision") != world.revision_id:
        mismatches.append("world_revision")
    if record.get("proposal_digest") != proposal.digest:
        mismatches.append("proposal_digest")
    if mismatches:
        return ReplayResult(mode, ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE, dict(record), mismatches=tuple(mismatches),
                            detail="the stored inputs are not the ones this decision was made for")
    try:
        recomputed = FeasibleActionSpace.build(world).check(proposal).to_dict()
    except WorldRefused as exc:
        return ReplayResult(mode, ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE, dict(record), mismatches=("proposal",),
                            detail=f"the stored proposal is refused by the check: {exc}")
    if canonical_bytes(recomputed) == canonical_bytes(dict(record)):
        return ReplayResult(mode, ReplayOutcome.REPRODUCED, dict(record), recomputed)
    diff = tuple(sorted(k for k in set(recomputed) | set(record) if recomputed.get(k) != record.get(k)))
    return ReplayResult(mode, ReplayOutcome.NONDETERMINISM_DETECTED, dict(record), recomputed, diff,
                        "the recomputed decision differs from the stored one")


__all__ = [
    "ANNOTATION_KEYS", "CHECKED_FAMILIES", "CLASSIFICATION", "COVERAGE_BAND", "CheckFamily", "FamilyRecord",
    "FeasibilityDecision", "FeasibilityReason", "FeasibilityStatus", "FeasibleActionSpace", "PRECEDENCE",
    "REASON_CODES", "STATUS_BY_SOURCE", "SpaceEntry", "canonical", "context_reads", "replay_decision",
]
