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
FEASIBLE unless all nine families ran and none left a reason.  No clock, randomness or environment is read.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from engcore.mind.repsem.roles import RoleSource, VariableRole
from engcore.design.grammar import ConstraintStatus
from engcore.scientific import Quantity, RangeCondition, ScientificCoreError, ValidityStatus
from engcore.scientific.models.definition import UnknownReason
from engcore.scientific.results.immutable import detach, freeze
from engcore.sria.actions import FeasibilityVerdict
from engcore.sria.decision.replay import ReplayMode, ReplayOutcome, ReplayResult

from .actions import ActionMode, ActionSpec, ExecutionKind, ProposedAction
from .base import (
    StaleProposal, WorldRefused, digest, expect_schema, magnitude_key, same_value, schema, value_payload,
)
from .domains import check_at_edges, finite_members, is_finite, membership
from .variables import ValueOrigin
from .world import APPLICABILITY_CONTEXT_ROLES, BUDGET_DIMENSIONS, ScientificWorld

DECISION_SCHEMA = schema("feasibility_decision")
SPACE_SCHEMA = schema("feasible_action_space")
CLASSIFICATION = "action_feasibility_not_scientific_support"
MAX_UNCERTAIN_CORNERS = 256


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
        if self.status is F.FEASIBLE and {c.family for c in self.checked} != set(CheckFamily):
            raise WorldRefused("FEASIBLE needs every check family to have run (an unchecked family is not a pass)")
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

        MISSING_INFORMATION is never exported as a negative verdict, and nothing is ever exported as a positive one."""
        return tuple(FeasibilityVerdict(f"forge.mind.world:{r.family.value}:{r.code}:{r.subject}", False,
                                        f"{r.status.value}: {r.message}")
                     for r in self.reasons if r.status is not F.MISSING_INFORMATION)


# ---- value resolution ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _Resolved:
    value: Any
    source: str                    # proposal | fixed_condition | world_declared | world_bound
    edges: tuple[Any, ...] | None  # None: present but undecidable under its uncertainty


def _resolve(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction, name: str,
             *, include_proposal: bool = True) -> _Resolved | None:
    """Precedence: the proposal's assignment, then the action's fixed condition, then the world's current value."""
    if include_proposal:
        v = proposal.value(name)
        if v is not None:
            return _Resolved(v, "proposal", (v,))
    f = spec.fixed(name)
    if f is not None:
        return _Resolved(f.value, "fixed_condition", (f.value,))
    if not world.declares(name):
        return None
    var = world.variable(name)
    if var.value is None:
        return None
    if var.origin is ValueOrigin.DECLARED:
        return _Resolved(var.value, "world_declared", (var.value,))
    return _Resolved(var.value, "world_bound", var.edges())


class _Collector:
    def __init__(self) -> None:
        self.reasons: list[FeasibilityReason] = []
        self.checked: list[FamilyRecord] = []
        self.annotations: list[dict[str, Any]] = []
        self.bound: set[tuple[str, str, str, str]] = set()

    def add(self, status: FeasibilityStatus, code: str, family: CheckFamily, subject: str, message: str,
            **detail: Any) -> None:
        self.reasons.append(FeasibilityReason(status, code, family, subject, message, detail))

    def ran(self, family: CheckFamily, evaluated: int, note: str = "") -> None:
        self.checked.append(FamilyRecord(family, evaluated, note))


def canonical(proposal: ProposedAction) -> ProposedAction:
    """The one proposal every family, the digest and any clearance are derived from: exactly a ``ProposedAction``,
    rebuilt from its own payload (plain tuples, typed values), so a subclass or a lazy container cannot show one
    view to one check and another view to the next."""
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
        return FeasibilityDecision(_derive_status(reasons), reasons, tuple(c.checked), proposal.action_id,
                                   self.world.revision_id, self.space_id, proposal.digest,
                                   tuple(c.annotations) + tuple(relied))

    def clear(self, proposal: ProposedAction):
        """(decision, ClearedAction or None).  Only a FEASIBLE decision clears."""
        from .gate import ClearedAction

        decision = self.check(proposal)
        if not decision.feasible:
            return decision, None
        return decision, ClearedAction.of(self, proposal, decision)

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


def _guard_value(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction, name: str) -> _Resolved | None:
    r = _resolve(world, spec, proposal, name)
    if r is None or r.source == "world_bound":
        return None   # a guard decides on a stated value, never on a bound reading of unknown uncertainty
    return r


def _check_domains(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction, c: _Collector) -> None:
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
        found = membership(control.domain, assigned)
        if found is not None:
            code, message, detail = found
            status = F.INFEASIBLE_DOMAIN if code in ("VALUE_KIND_MISMATCH", "UNIT_INCOMPATIBLE") else \
                STATUS_BY_SOURCE[control.declared_by]
            c.add(status, code, CheckFamily.DOMAIN, name, message, declared_by=control.declared_by.value, **detail)
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


def _edges_for(r: _Resolved) -> tuple[Any, ...] | None:
    return r.edges if r.edges is not None and all(isinstance(e, Quantity) for e in r.edges) else None


def _note_bound(world: ScientificWorld, c: _Collector, name: str, used_for: str) -> None:
    var = world.variable(name)
    if var.source is not None:
        c.bound.add((name, var.source.kind.value, var.source.ref, used_for))


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
            _note_bound(world, c, metric, f"constraint {cid}")
        edges = _edges_for(r)
        if edges is None:
            c.add(F.MISSING_INFORMATION, "CONSTRAINT_UNDECIDABLE", CheckFamily.PROTOCOL, cid,
                  "the constrained value's uncertainty does not allow a decision", metric=metric, source=r.source)
            continue
        outcome, detail = check_at_edges(constraint.consequence, edges)
        if outcome is ConstraintStatus.VIOLATED:
            c.add(status, "CONSTRAINT_VIOLATED", CheckFamily.PROTOCOL, cid, f"violates {constraint.basis}",
                  metric=metric, source=r.source, **detail)
        elif outcome is ConstraintStatus.UNKNOWN:
            c.add(F.MISSING_INFORMATION, f"CONSTRAINT_{detail['why'].upper()}", CheckFamily.PROTOCOL, cid,
                  "the constraint cannot be decided on the stated value", metric=metric, source=r.source, **detail)
    c.ran(CheckFamily.PROTOCOL, n)


def _check_state(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction | None, c: _Collector) -> None:
    n = 0
    for pre in spec.preconditions:
        n += 1
        var = world.variable(pre.metric)
        if var.value is None:
            c.add(F.MISSING_INFORMATION, "PRECONDITION_UNRESOLVED", CheckFamily.STATE, pre.name,
                  "the state this precondition reads has no current value", metric=pre.metric)
            continue
        _note_bound(world, c, pre.metric, f"precondition {pre.name}")
        edges = var.edges()
        if edges is None or not all(isinstance(e, Quantity) for e in edges):
            c.add(F.MISSING_INFORMATION, "PRECONDITION_UNCERTAINTY_UNKNOWN", CheckFamily.STATE, pre.name,
                  "the current value's uncertainty is not an interval, so the precondition cannot be decided (a point "
                  "value is never treated as exact)", metric=pre.metric, uncertainty=var.uncertainty.kind.value)
            continue
        outcome, detail = check_at_edges(pre, edges)
        if outcome is ConstraintStatus.VIOLATED:
            c.add(F.INFEASIBLE_STATE, "PRECONDITION_VIOLATED", CheckFamily.STATE, pre.name,
                  "the current state does not meet the action's precondition", metric=pre.metric, **detail)
        elif outcome is ConstraintStatus.UNKNOWN:
            c.add(F.MISSING_INFORMATION, f"PRECONDITION_{detail['why'].upper()}", CheckFamily.STATE, pre.name,
                  "the precondition cannot be decided on the current value", metric=pre.metric, **detail)
    for name in sorted(_reads(world, spec)):
        var = world.variable(name)
        if var.value is None or var.domain is None or var.edges() == (var.value,) and var.source is None:
            continue
        if proposal is not None and (proposal.value(name) is not None or spec.fixed(name) is not None):
            continue
        n += 1
        edges = var.edges()
        if edges is None:
            c.add(F.MISSING_INFORMATION, "STATE_DOMAIN_UNDECIDABLE", CheckFamily.STATE, name,
                  "whether the current value lies in its declared domain depends on an uncertainty that is not an "
                  "interval", uncertainty=var.uncertainty.kind.value)
            continue
        outside = [membership(var.domain, e) is not None for e in edges]
        if all(outside):
            c.add(F.INFEASIBLE_STATE, "STATE_OUTSIDE_DECLARED_DOMAIN", CheckFamily.STATE, name,
                  "the system's current value lies outside the variable's declared domain at every edge of its "
                  "uncertainty", edges=[value_payload(e) for e in edges])
        elif any(outside):
            c.add(F.MISSING_INFORMATION, "STATE_DOMAIN_UNDECIDED", CheckFamily.STATE, name,
                  "the current value's uncertainty straddles its declared domain", edges=[value_payload(e) for e in edges])
    c.ran(CheckFamily.STATE, n)


def _reads(world: ScientificWorld, spec: ActionSpec) -> set[str]:
    names = {p.metric for p in spec.preconditions}
    for constraint in world.constraints:
        if constraint.applies(spec.action_id):
            names |= set(constraint.reads)
    for binding_id in spec.applicability:
        names |= set(world.applicability_binding(binding_id).reads)
    return {n for n in names if world.declares(n)}


def _one_sided(condition: RangeCondition, side: str) -> RangeCondition:
    """The lower or upper half of a range condition, as a core record (so the core evaluates it)."""
    if side == "lower":
        return RangeCondition(condition.name, minimum=condition.minimum,
                              minimum_inclusive=condition.minimum_inclusive)
    return RangeCondition(condition.name, maximum=condition.maximum, maximum_inclusive=condition.maximum_inclusive)


def _interval_violates(condition: RangeCondition, edges: tuple[Any, ...]) -> bool:
    """Every point of [a, b] violates a range condition iff both edges violate the SAME side of it.  Each side is a
    half-line (convex), and both judgments are the core evaluator's."""
    for side, bound in (("lower", condition.minimum), ("upper", condition.maximum)):
        if bound is None:
            continue
        half = _one_sided(condition, side)
        if all(half.evaluate(e) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN for e in edges):
            return True
    return False


def _check_applicability(world: ScientificWorld, spec: ActionSpec, proposal: ProposedAction, c: _Collector) -> None:
    """Model applicability, decided by the core per point.  With exact inputs the core status is used as it is.

    With interval inputs the world must not invent a status, so it uses only two sound rules over core judgments:
    the whole interval box is IN when every corner is IN and every condition reading an uncertain input is a single-
    variable range (a convex set); it is OUTSIDE when some range condition is violated on the same side at both edges
    of its input, or a condition over exact inputs is violated (it is then violated at every corner).  Anything else
    is undecided: MISSING_INFORMATION.  A condition type other than a range over an uncertain input is undecided."""
    gating = spec.execution is ExecutionKind.MODEL_EXECUTION
    for binding_id in spec.applicability:
        binding = world.applicability_binding(binding_id)
        exact: dict[str, Any] = {}
        uncertain: dict[str, tuple[Any, ...]] = {}
        withheld: list[str] = []
        for name in sorted(binding.reads):
            if world.role(name) not in APPLICABILITY_CONTEXT_ROLES:
                withheld.append(name)
                continue
            r = _resolve(world, spec, proposal, name)
            if r is None:
                continue
            if r.source == "world_bound":
                _note_bound(world, c, name, f"applicability {binding_id}")
            if r.edges is None:
                withheld.append(name)
            elif len(r.edges) == 1:
                exact[name] = r.edges[0]
            else:
                uncertain[name] = r.edges
        annotation: dict[str, Any] = {"binding_id": binding_id, "gating": gating, "withheld": withheld,
                                      "uncertain_inputs": sorted(uncertain)}
        assessments: list[Any] = []
        error = ""
        corners = 1
        for edges in uncertain.values():
            corners *= len(edges)
        if corners > MAX_UNCERTAIN_CORNERS:
            error = f"{corners} corners exceed {MAX_UNCERTAIN_CORNERS}"
        else:
            try:
                for combo in itertools.product(*uncertain.values()):
                    assessments.append(binding.assess({**exact, **dict(zip(uncertain, combo))}))
            except ScientificCoreError as exc:
                error, assessments = str(exc), []
        statuses = [a.status for a in assessments]
        recorded = [a.to_dict() for a in assessments]
        annotation.update({"core_statuses": [st.value for st in statuses], "assessments": recorded,
                           "assessment_digests": [digest(x) for x in recorded], "error": error})
        if error:
            outcome = "not_assessable"
        elif not uncertain:
            outcome = statuses[0].value                      # one exact assessment: the core status as it is
        else:
            readers = [cond for cond in binding.model.validity.conditions
                       if set(getattr(cond, "context_keys", ()) or ()) & set(uncertain)]
            ranges_only = all(isinstance(cond, RangeCondition) and len(cond.context_keys) == 1 for cond in readers)
            whole_out = any(isinstance(cond, RangeCondition) and _interval_violates(cond, uncertain[cond.name])
                            for cond in readers if cond.name in uncertain)
            exact_only = {cond.name for cond in binding.model.validity.conditions
                          if not set(getattr(cond, "context_keys", ()) or ()) & set(uncertain)}
            exact_violated = set.intersection(*(set(a.violated) for a in assessments)) & exact_only
            if ValidityStatus.UNKNOWN in statuses:
                outcome = "unknown"
            elif whole_out or exact_violated:
                outcome = "outside_whole_interval"
            elif ranges_only and set(statuses) == {ValidityStatus.IN_DOMAIN}:
                outcome = "in_domain_whole_interval"
            else:
                outcome = "undecided"
        annotation["outcome"] = outcome
        c.annotations.append(annotation)
        if not gating:
            continue
        if outcome == ValidityStatus.OUTSIDE_VALIDATED_DOMAIN.value:
            c.add(F.INFEASIBLE_APPLICABILITY, "OUTSIDE_VALIDATED_DOMAIN", CheckFamily.APPLICABILITY, binding_id,
                  "the model this action executes is not applicable at this point (the core's status as it is)",
                  validity_status=outcome, violated=sorted(assessments[0].violated),
                  assessment_digests=annotation["assessment_digests"])
        elif outcome == "outside_whole_interval":
            c.add(F.INFEASIBLE_APPLICABILITY, "OUTSIDE_VALIDATED_DOMAIN", CheckFamily.APPLICABILITY, binding_id,
                  "every point of the stated input interval is outside the model's validity domain (each edge judged "
                  "by the core; the interval rule is the world's, stated in its basis)",
                  basis="a range condition is violated on the same side at both edges of its input, or a condition "
                        "over exact inputs is violated at every corner",
                  core_statuses=annotation["core_statuses"], assessment_digests=annotation["assessment_digests"])
        elif outcome == ValidityStatus.UNKNOWN.value or outcome == "unknown":
            unknown = [a for a in assessments if a.status is ValidityStatus.UNKNOWN][0]
            reasons = sorted({u.reason.value for u in unknown.unknown_reasons})
            not_supplied = reasons == [UnknownReason.NOT_SUPPLIED.value]
            c.add(F.MISSING_INFORMATION, "APPLICABILITY_NOT_SUPPLIED" if not_supplied else "APPLICABILITY_UNKNOWN",
                  CheckFamily.APPLICABILITY, binding_id,
                  "model applicability is UNKNOWN here; model execution is not admitted on an unknown applicability",
                  validity_status=ValidityStatus.UNKNOWN.value, unknown_reasons=reasons, unknown=sorted(unknown.unknown),
                  withheld=withheld)
        elif outcome not in (ValidityStatus.IN_DOMAIN.value, "in_domain_whole_interval"):
            c.add(F.MISSING_INFORMATION, f"APPLICABILITY_{outcome.upper()}", CheckFamily.APPLICABILITY, binding_id,
                  "model applicability cannot be decided on the stated values", uncertain_inputs=sorted(uncertain),
                  error=error)
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
        remaining = budget.remaining(dim)
        if dim == "cost":
            requested = magnitude_key(amount)
            ok = budget.cost.affordable(requested, family=spec.family)
        elif dim == "wall_time":
            requested = magnitude_key(amount)
            ok = requested <= remaining
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
    recomputed = FeasibleActionSpace.build(world).check(proposal).to_dict()
    from engcore.mind.repsem import canonical_bytes

    if canonical_bytes(recomputed) == canonical_bytes(dict(record)):
        return ReplayResult(mode, ReplayOutcome.REPRODUCED, dict(record), recomputed)
    diff = tuple(sorted(k for k in set(recomputed) | set(record) if recomputed.get(k) != record.get(k)))
    return ReplayResult(mode, ReplayOutcome.NONDETERMINISM_DETECTED, dict(record), recomputed, diff,
                        "the recomputed decision differs from the stored one")


__all__ = [
    "CLASSIFICATION", "CheckFamily", "FamilyRecord", "FeasibilityDecision", "FeasibilityReason", "FeasibilityStatus",
    "FeasibleActionSpace", "PRECEDENCE", "STATUS_BY_SOURCE", "SpaceEntry", "replay_decision",
]
