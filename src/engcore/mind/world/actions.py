"""Declared actions (what may be done) and proposals (what someone asks to do).

An :class:`ActionSpec` is declared by the problem specification or the protocol metadata, never by a proposer.  Its
family is the canonical planning label (``sria.decision.ActionFamily``).  Two fields are new, both declared:

* ``mode``: OBSERVE reads declared channels and sets nothing; INTERVENE sets the declared controls.  A recorded
  variable is not thereby settable.
* ``execution``: MODEL_EXECUTION runs a model through a provider as evidence-bearing work, so model applicability
  gates it and it must name the model(s) whose applicability applies; SYSTEM_QUERY observes or intervenes on the
  system itself (a rig, a recorded pool, an escrow), where model applicability is an annotation, never a gate.
  Neither is ``sria.actions.ExecutorType`` (who executes).

Role semantics are enforced when an action is bound to a world (:meth:`ActionSpec.bind`):

=========================  ==============================================================================================
CONTROLLED_INPUT           may be a control
FIXED_PROTOCOL_CONDITION   a control only over a finite domain the protocol metadata declares (selection among the
                           protocol's levels); otherwise a fixed condition of the action
STATE_VARIABLE             a control only of a separate explicit state-intervention action (every control of that
                           action is a state intervention, each with its basis)
MEASUREMENT / DERIVED /    never a control
LATENT / NUISANCE
LATENT / DERIVED           never an expected observable either
=========================  ==============================================================================================

A :class:`ProposedAction` is the brief's "ActionProposal" (renamed: ``sria.decision.ActionProposal`` already exists
and means something else).  It is bound to one world revision, sets typed scientific values only, and names its
proposer.  Every proposer meets the same check.  A language-model proposal enters only as a certified
``ExternalSuggestion`` (:func:`proposed_action_from_suggestion`) and carries that suggestion as its ``source``; the
check re-derives the proposal from the source against its own world, so its provenance, revision and family are
verified, never taken from the proposal.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from engcore.mind.repsem.roles import RoleSource, VariableRole
from engcore.scientific import (
    ConstraintDefinition, Quantity, ScientificParameter, ScientificVariable, VariableKind,
)
from engcore.scientific import VariableRole as StudyRole
from engcore.scientific.ir.values import BooleanValue, CategoricalValue, IntegerValue
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.external import AUTHORITY_KEYS, EXTERNAL_SUGGESTION_SCHEMA, ExternalSuggestion
from engcore.sria.decision.hypotheses import ProposalProvenance, ProposerKind
from engcore.system_runtime.request import ProviderBinding

from .base import (
    HEX64, WorldRefused, as_unit, converts, digest, exact_text, expect_schema, names, require_plain_value,
    require_value, schema, text, value_from, value_payload,
)
from .domains import (
    DeclaredConstraint, DiscreteLevels, Guard, contained, declared_source, domain_from, domain_identity,
    domain_problem, is_finite, membership,
)
from .variables import TemporalSemantics

CONTROL_SCHEMA = schema("control")
ACTION_SCHEMA = schema("action_spec")
PROPOSAL_SCHEMA = schema("proposed_action")
INTAKE_REFUSAL_SCHEMA = schema("intake_refusal")

#: Budget dimensions an action may declare a cost in.  Duration is declared separately (``estimated_duration``) and is
#: what the wall-time budget is checked against.
COST_DIMENSIONS = ("cost", "experiments", "solver_calls")

#: Gen1's belief-shaped keys a proposal may never carry (``engcore.mind.minimal.structures._FORBIDDEN_PROPOSAL_KEYS``,
#: copied because that name is private to a byte-pinned Gen1 module; a test pins this as a superset of it).
GEN1_FORBIDDEN_KEYS = frozenset({"weight", "prior", "posterior", "probability", "confidence", "score", "credit",
                                 "threshold", "stop", "outcome"})

#: Keys an external proposal may never carry, at any depth: the certified suggestion boundary's authority keys, Gen1's
#: belief keys, and the assertions a proposer could otherwise smuggle into feasibility.
FORBIDDEN_PROPOSAL_KEYS = frozenset(AUTHORITY_KEYS) | GEN1_FORBIDDEN_KEYS | frozenset({
    "admissible", "allowed_values", "bounds", "budget", "clamp", "constraint", "constraints", "cost", "default",
    "domain", "feasibility", "feasible", "infeasible", "levels", "nearest", "override", "precondition",
    "preconditions", "remaining", "verified",
    # GEN2-BR1.1: admission and authority-binding fields; a proposer never states them
    "admission", "admitted", "admitted_action", "authority", "authorities", "authority_binding", "authorization",
    "authorized", "binding", "bindings", "capability", "declaration", "dispatch", "owner", "projection",
    "record_digest", "revision", "verification", "world",
})

#: The only keys a suggestion's ``point`` may carry: assignments are a list of {variable, value} pairs, so a variable's
#: NAME is never a key and can never collide with a forbidden key.
SUGGESTION_POINT_KEYS = frozenset({"assignments", "observe"})


class ActionMode(str, Enum):
    """OBSERVE(variable) reads; INTERVENE(variable=value) sets."""

    OBSERVE = "observe"
    INTERVENE = "intervene"


class ExecutionKind(str, Enum):
    """Whether executing the action is evidence-bearing model execution (gated by model applicability)."""

    MODEL_EXECUTION = "model_execution"
    SYSTEM_QUERY = "system_query"


@dataclass(frozen=True)
class ControlSpec:
    """One variable an INTERVENE action sets, its allowed values, and who declared them."""

    variable: str
    domain: ScientificVariable | DiscreteLevels
    declared_by: RoleSource
    basis: str
    active_when: Guard | None = None
    state_intervention: bool = False

    def __post_init__(self) -> None:
        text(self.variable, "control variable")
        if isinstance(self.domain, ScientificVariable):
            if self.domain.name != self.variable:
                raise WorldRefused(f"control {self.variable!r}: its domain is declared for {self.domain.name!r}")
            if self.domain.role is not StudyRole.CONTROL:
                raise WorldRefused(f"control {self.variable!r}: an action-control domain has the study role CONTROL")
        elif not isinstance(self.domain, DiscreteLevels):
            raise WorldRefused(f"control {self.variable!r}: a domain is a ScientificVariable or DiscreteLevels")
        object.__setattr__(self, "declared_by", declared_source(self.declared_by, f"control {self.variable!r}"))
        text(self.basis, f"control {self.variable!r} basis")
        if self.active_when is not None and not isinstance(self.active_when, Guard):
            raise WorldRefused(f"control {self.variable!r}: active_when is a Guard or None")
        if type(self.state_intervention) is not bool:
            raise WorldRefused(f"control {self.variable!r}: state_intervention is a bool")

    def identity(self) -> dict[str, Any]:
        return {"variable": self.variable, "domain": domain_identity(self.domain),
                "declared_by": self.declared_by.value, "basis": self.basis,
                "active_when": None if self.active_when is None else self.active_when.identity(),
                "state_intervention": self.state_intervention}

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CONTROL_SCHEMA, "variable": self.variable, "domain": self.domain.to_dict(),
                "declared_by": self.declared_by.value, "basis": self.basis,
                "active_when": None if self.active_when is None else self.active_when.to_dict(),
                "state_intervention": self.state_intervention}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ControlSpec":
        expect_schema(payload.get("schema"), CONTROL_SCHEMA)
        return cls(payload["variable"], domain_from(payload["domain"]), RoleSource(payload["declared_by"]),
                   payload["basis"], None if payload.get("active_when") is None else Guard.from_dict(payload["active_when"]),
                   payload.get("state_intervention", False))


def _costs(value: Any, action_id: str) -> tuple[tuple[str, Any], ...]:
    if isinstance(value, tuple):
        value = dict(value)
    if not isinstance(value, Mapping):
        raise WorldRefused(f"action {action_id!r}: estimated_cost maps a budget dimension to a typed value")
    out = []
    for dim, amount in sorted(value.items()):
        if dim not in COST_DIMENSIONS:
            raise WorldRefused(f"action {action_id!r}: {dim!r} is not a cost dimension {COST_DIMENSIONS}")
        require_value(amount, f"action {action_id!r} cost {dim!r}")
        if dim in ("experiments", "solver_calls"):
            if type(amount) is not IntegerValue or amount.value < 0:
                raise WorldRefused(f"action {action_id!r}: a {dim} cost is a non-negative IntegerValue")
        elif not (isinstance(amount, Quantity) and amount.units == "dimensionless" and amount.magnitude >= 0):
            raise WorldRefused(f"action {action_id!r}: a cost is a non-negative plain dimensionless quantity in the "
                               "budget's cost units (no percent or other scaled spelling)")
        out.append((dim, amount))
    return tuple(out)


def _domain_states_kind(domain: Any, value: Any) -> bool:
    """Whether a variable's own declared domain states the kind of a typed (non-quantity) value."""
    kinds = {IntegerValue: VariableKind.INTEGER, CategoricalValue: VariableKind.CATEGORICAL,
             BooleanValue: VariableKind.BOOLEAN}
    return isinstance(domain, ScientificVariable) and domain.kind is kinds.get(type(value))


def _contained_as_executed(inner: Any, outer: Any, unit_: str) -> bool:
    """Whether every member of an action's domain, AS EXECUTED (in the variable's unit by the unit owner), is a member
    of the variable's own domain: a declared level or bound is never checked in a spelling no executor receives."""
    if isinstance(inner, DiscreteLevels):
        return all(membership(outer, as_unit(level, unit_)) is None for level in inner.levels)
    if isinstance(inner, ScientificVariable) and inner.kind is VariableKind.CONTINUOUS and inner.lower is not None \
            and inner.upper is not None and converts(inner.lower, unit_):
        if not contained(inner, outer):
            return False
        return all(membership(outer, as_unit(edge, unit_)) is None for edge in (inner.lower, inner.upper))
    return contained(inner, outer)


@dataclass(frozen=True)
class ActionSpec:
    action_id: str
    family: ActionFamily
    mode: ActionMode
    execution: ExecutionKind = ExecutionKind.SYSTEM_QUERY
    controls: tuple[ControlSpec, ...] = ()
    preconditions: tuple[ConstraintDefinition, ...] = ()
    fixed_conditions: tuple[ScientificParameter, ...] = ()
    expected_observables: tuple[str, ...] = ()
    provider_requirements: tuple[ProviderBinding, ...] = ()
    estimated_cost: Any = field(default_factory=dict)
    estimated_duration: Quantity | None = None
    cost_basis: str = ""
    applicability: tuple[str, ...] = ()
    declared_by: RoleSource | None = None
    basis: str = ""
    description: str = ""                                   # non-material

    def __post_init__(self) -> None:
        aid = text(self.action_id, "action_id")
        try:
            object.__setattr__(self, "family", ActionFamily(self.family))
            object.__setattr__(self, "mode", ActionMode(self.mode))
            object.__setattr__(self, "execution", ExecutionKind(self.execution))
        except ValueError as exc:
            raise WorldRefused(f"action {aid!r}: {exc}") from None
        controls = tuple(self.controls)
        if any(not isinstance(c, ControlSpec) for c in controls):
            raise WorldRefused(f"action {aid!r}: controls are ControlSpec records")
        names([c.variable for c in controls], f"action {aid!r} controls")
        object.__setattr__(self, "controls", tuple(sorted(controls, key=lambda c: c.variable)))
        if self.mode is ActionMode.OBSERVE and controls:
            raise WorldRefused(f"action {aid!r}: an OBSERVE action sets nothing")
        if self.mode is ActionMode.INTERVENE and not controls:
            raise WorldRefused(f"action {aid!r}: an INTERVENE action declares what it sets")
        states = {c.state_intervention for c in controls}
        if len(states) > 1:
            raise WorldRefused(f"action {aid!r}: a state intervention is a separate action; it does not share an "
                               "action with ordinary controls")
        pre = tuple(self.preconditions)
        if any(not isinstance(p, ConstraintDefinition) for p in pre):
            raise WorldRefused(f"action {aid!r}: preconditions are ConstraintDefinition records")
        names([p.name for p in pre], f"action {aid!r} preconditions")
        object.__setattr__(self, "preconditions", tuple(sorted(pre, key=lambda p: p.name)))
        fixed = tuple(self.fixed_conditions)
        if any(not isinstance(f, ScientificParameter) for f in fixed):
            raise WorldRefused(f"action {aid!r}: fixed conditions are ScientificParameter records")
        names([f.name for f in fixed], f"action {aid!r} fixed conditions")
        if {f.name for f in fixed} & {c.variable for c in controls}:
            raise WorldRefused(f"action {aid!r}: a variable is either a control or a fixed condition, not both")
        object.__setattr__(self, "fixed_conditions", tuple(sorted(fixed, key=lambda f: f.name)))
        object.__setattr__(self, "expected_observables", names(self.expected_observables, f"action {aid!r} observables"))
        if self.mode is ActionMode.OBSERVE and not self.expected_observables:
            raise WorldRefused(f"action {aid!r}: an OBSERVE action names what it can observe")
        reqs = tuple(self.provider_requirements)
        if any(not isinstance(r, ProviderBinding) for r in reqs):
            raise WorldRefused(f"action {aid!r}: provider requirements are ProviderBinding records")
        names([r.provider_id for r in reqs], f"action {aid!r} providers")
        object.__setattr__(self, "provider_requirements", tuple(sorted(reqs, key=lambda r: r.provider_id)))
        object.__setattr__(self, "estimated_cost", _costs(self.estimated_cost, aid))
        if self.estimated_cost and not str(self.cost_basis).strip():
            raise WorldRefused(f"action {aid!r}: a declared cost cites its basis")
        if self.estimated_duration is not None and not (
                converts(self.estimated_duration, "second") and self.estimated_duration.magnitude_in("second") >= 0):
            raise WorldRefused(f"action {aid!r}: estimated_duration is a non-negative time quantity")
        object.__setattr__(self, "applicability", names(self.applicability, f"action {aid!r} applicability"))
        if self.execution is ExecutionKind.MODEL_EXECUTION and not (reqs and self.applicability):
            raise WorldRefused(f"action {aid!r}: a MODEL_EXECUTION names its provider and the model(s) whose "
                               "applicability gates it (model applicability precedes evidence-bearing execution)")
        if self.execution is ExecutionKind.SYSTEM_QUERY and reqs:
            raise WorldRefused(f"action {aid!r}: an action that runs a provider is a MODEL_EXECUTION; a SYSTEM_QUERY "
                               "cannot carry provider requirements (the applicability gate is not optional)")
        object.__setattr__(self, "declared_by", declared_source(self.declared_by, f"action {aid!r}"))
        text(self.basis, f"action {aid!r} basis")
        if not isinstance(self.description, str):
            raise WorldRefused(f"action {aid!r}: description is text")

    # ---- binding to a world: role semantics with behaviour ------------------------------------------------------------
    def bind(self, world: Any) -> "ActionSpec":
        aid = self.action_id
        for c in self.controls:
            if not world.declares(c.variable):
                raise WorldRefused(f"action {aid!r}: control {c.variable!r} is not a declared variable")
            var = world.variable(c.variable)
            role = var.role
            if role is VariableRole.CONTROLLED_INPUT:
                if c.state_intervention:
                    raise WorldRefused(f"action {aid!r}: {c.variable!r} is a CONTROLLED_INPUT, not a state intervention")
                if var.temporal is TemporalSemantics.TIME_SERIES:
                    raise WorldRefused(f"action {aid!r}: {c.variable!r} is a TIME_SERIES input; a scalar control would "
                                       "silently mean a constant profile (time-series controls are an open decision)")
            elif role is VariableRole.FIXED_PROTOCOL_CONDITION:
                if c.declared_by is not RoleSource.PROTOCOL_METADATA or not is_finite(c.domain):
                    raise WorldRefused(f"action {aid!r}: {c.variable!r} is a FIXED_PROTOCOL_CONDITION; it may only be "
                                       "selected among a finite set of levels the protocol metadata declares")
                if c.state_intervention:
                    raise WorldRefused(f"action {aid!r}: {c.variable!r} is not a state")
            elif role is VariableRole.STATE_VARIABLE:
                if not c.state_intervention:
                    raise WorldRefused(f"action {aid!r}: {c.variable!r} is a STATE_VARIABLE; only an explicit state "
                                       "intervention (state_intervention=True, with its basis) may set a state")
            else:
                raise WorldRefused(f"action {aid!r}: {c.variable!r} is a {role.value} and is never a control")
            problem = domain_problem(c.domain, c.variable, var.unit)
            if problem:
                raise WorldRefused(f"action {aid!r} control {c.variable!r}: {problem}")
            if var.domain is not None and not _contained_as_executed(c.domain, var.domain, var.unit):
                rule = ("the unit owner's level identity rule (a level is matched only by a value the owner calls that "
                        "level)" if isinstance(var.domain, DiscreteLevels) else "the owner's bound rule")
                raise WorldRefused(f"action {aid!r} control {c.variable!r}: a member or edge of the action domain, as "
                                   "executed in the variable's unit, is outside the variable's declared domain by "
                                   f"{rule} (an action restricts, never widens; conversion noise counts: state the "
                                   "domain in the variable's own unit to avoid it)")
            if c.active_when is not None:
                if c.active_when.variable == c.variable:
                    raise WorldRefused(f"action {aid!r}: control {c.variable!r} cannot guard itself")
                world._check_guard(c.active_when, f"action {aid!r} control {c.variable!r}")
        for f in self.fixed_conditions:
            if not world.declares(f.name):
                raise WorldRefused(f"action {aid!r}: fixed condition {f.name!r} is not a declared variable")
            var = world.variable(f.name)
            if var.role not in (VariableRole.FIXED_PROTOCOL_CONDITION, VariableRole.CONTROLLED_INPUT):
                raise WorldRefused(f"action {aid!r}: {f.name!r} is a {var.role.value}; only a protocol condition or a "
                                   "controlled input is held fixed by an action")
            if var.temporal is TemporalSemantics.TIME_SERIES:
                raise WorldRefused(f"action {aid!r}: {f.name!r} is a TIME_SERIES input; a scalar fixed condition would "
                                   "silently mean a constant profile (time-series conditions are an open decision)")
            if isinstance(f.value, Quantity) and not converts(f.value, var.unit):
                raise WorldRefused(f"action {aid!r}: the unit owner does not convert fixed {f.name!r} = {f.value} into "
                                   f"{var.unit!r}")
            if not isinstance(f.value, Quantity) and var.unit != "dimensionless" and not _domain_states_kind(
                    var.domain, f.value):
                raise WorldRefused(f"action {aid!r}: fixed {f.name!r} is a {type(f.value).__name__} but the variable is "
                                   f"declared in {var.unit!r}: only a quantity the unit owner converts is executed in a "
                                   "unit-bearing variable (a typed value needs exactly 'dimensionless' or a declared "
                                   "domain of its kind)")
            if var.domain is not None and membership(var.domain, as_unit(f.value, var.unit)) is not None:
                raise WorldRefused(f"action {aid!r}: fixed {f.name!r} = {f.value!r} is outside its declared domain "
                                   "(as executed, in the variable's unit)")
        for name in self.expected_observables:
            if not world.declares(name):
                raise WorldRefused(f"action {aid!r}: observable {name!r} is not a declared variable")
            role = world.role(name)
            if role in (VariableRole.LATENT_PARAMETER, VariableRole.DERIVED_QUANTITY):
                raise WorldRefused(f"action {aid!r}: {name!r} is a {role.value}, never an observable")
            if not world.has_channel(name):
                raise WorldRefused(f"action {aid!r}: observable {name!r} has no declared observation channel")
        for p in self.preconditions:
            if not world.declares(p.metric):
                raise WorldRefused(f"action {aid!r}: precondition {p.name!r} reads undeclared {p.metric!r}")
            if not converts(p.bound, world.variable(p.metric).unit):
                raise WorldRefused(f"action {aid!r}: the unit owner does not convert precondition {p.name!r}'s bound "
                                   f"into {p.metric!r}'s unit")
        for binding_id in self.applicability:
            if world.applicability_binding(binding_id) is None:
                raise WorldRefused(f"action {aid!r}: applicability binding {binding_id!r} is not declared")
        return self

    # ---- views --------------------------------------------------------------------------------------------------------
    def control(self, name: str) -> ControlSpec | None:
        for c in self.controls:
            if c.variable == name:
                return c
        return None

    def fixed(self, name: str) -> ScientificParameter | None:
        for f in self.fixed_conditions:
            if f.name == name:
                return f
        return None

    def cost(self, dimension: str) -> Any:
        for dim, amount in self.estimated_cost:
            if dim == dimension:
                return amount
        return None

    # ---- serialization ------------------------------------------------------------------------------------------------
    def identity(self) -> dict[str, Any]:
        return {"action_id": self.action_id, "family": self.family.value, "mode": self.mode.value,
                "execution": self.execution.value, "controls": [c.identity() for c in self.controls],
                "preconditions": [p.to_dict() for p in self.preconditions],
                "fixed_conditions": [[f.name, value_payload(f.value)] for f in self.fixed_conditions],
                "expected_observables": list(self.expected_observables),
                "provider_requirements": [r.to_dict() for r in self.provider_requirements],
                "estimated_cost": [[d, value_payload(a)] for d, a in self.estimated_cost],
                "estimated_duration": None if self.estimated_duration is None else self.estimated_duration.to_dict(),
                "cost_basis": self.cost_basis, "applicability": list(self.applicability),
                "declared_by": self.declared_by.value, "basis": self.basis}

    @property
    def digest(self) -> str:
        return digest(self.identity())

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ACTION_SCHEMA, "action_id": self.action_id, "family": self.family.value,
                "mode": self.mode.value, "execution": self.execution.value,
                "controls": [c.to_dict() for c in self.controls],
                "preconditions": [p.to_dict() for p in self.preconditions],
                "fixed_conditions": [f.to_dict() for f in self.fixed_conditions],
                "expected_observables": list(self.expected_observables),
                "provider_requirements": [r.to_dict() for r in self.provider_requirements],
                "estimated_cost": [[d, value_payload(a)] for d, a in self.estimated_cost],
                "estimated_duration": None if self.estimated_duration is None else self.estimated_duration.to_dict(),
                "cost_basis": self.cost_basis, "applicability": list(self.applicability),
                "declared_by": self.declared_by.value, "basis": self.basis, "description": self.description}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ActionSpec":
        expect_schema(payload.get("schema"), ACTION_SCHEMA)
        return cls(payload["action_id"], ActionFamily(payload["family"]), ActionMode(payload["mode"]),
                   ExecutionKind(payload["execution"]), tuple(ControlSpec.from_dict(c) for c in payload["controls"]),
                   tuple(ConstraintDefinition.from_dict(p) for p in payload["preconditions"]),
                   tuple(ScientificParameter.from_dict(f) for f in payload["fixed_conditions"]),
                   tuple(payload["expected_observables"]),
                   tuple(ProviderBinding.from_dict(r) for r in payload["provider_requirements"]),
                   {d: value_from(a) for d, a in payload["estimated_cost"]},
                   None if payload.get("estimated_duration") is None else Quantity.from_dict(payload["estimated_duration"]),
                   payload.get("cost_basis", ""), tuple(payload.get("applicability", ())),
                   RoleSource(payload["declared_by"]), payload["basis"], payload.get("description", ""))


# ---- proposals --------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ProposedAction:
    """INTERVENE(variable=value, ...) and/or OBSERVE(variable, ...) on one declared action of one world revision."""

    action_id: str
    world_revision: str
    assignments: Any
    observe: tuple[str, ...] = ()
    proposer: ProposalProvenance | None = None
    rationale: str = ""                                    # recorded for audit, never parsed, not identity
    source: ExternalSuggestion | None = None               # the certified suggestion an external proposal came from

    def __post_init__(self) -> None:
        exact_text(self.action_id, "proposal action_id")
        if type(self.world_revision) is not str or not HEX64.match(self.world_revision):
            raise WorldRefused("a proposal names the 64-hex world revision it was made for")
        raw = list(self.assignments.items()) if isinstance(self.assignments, Mapping) else [
            tuple(p) for p in self.assignments]
        for pair in raw:
            if len(pair) != 2:
                raise WorldRefused("an assignment is a (variable, value) pair")
            exact_text(pair[0], "assigned variable")
        out = [(n, require_plain_value(v, f"proposed {n!r}")) for n, v in sorted(raw, key=lambda p: p[0])]
        if len({n for n, _ in out}) != len(out):
            raise WorldRefused("a proposal assigns each variable once")
        object.__setattr__(self, "assignments", tuple(out))
        for o in (() if isinstance(self.observe, (str, bytes)) else tuple(self.observe)):
            exact_text(o, "observe target")
        object.__setattr__(self, "observe", names(self.observe, "observe targets"))
        if not isinstance(self.proposer, ProposalProvenance):
            raise WorldRefused("a proposal names its proposer (ProposalProvenance)")
        if self.source is None:
            if self.proposer.proposer_kind is ProposerKind.LANGUAGE_MODEL:
                raise WorldRefused("a language-model proposal enters only as an ExternalSuggestion, which it carries as "
                                   "its source")
        else:
            src = self.source
            if type(src) is not ExternalSuggestion:
                raise WorldRefused("a proposal's source is exactly a certified ExternalSuggestion")
            if (self.proposer.proposer_kind is not src.engine_kind or self.proposer.proposal_digest != src.digest
                    or self.proposer.proposer_id != f"{src.engine_id}@{src.engine_version}"
                    or self.action_id != src.target_ref):
                raise WorldRefused("a proposal's provenance and action are its source suggestion's, exactly")
        if not isinstance(self.rationale, str):
            raise WorldRefused("rationale is text")

    def value(self, name: str) -> Any:
        for n, v in self.assignments:
            if n == name:
                return v
        return None

    def identity(self) -> dict[str, Any]:
        p = self.proposer
        return {"action_id": self.action_id, "world_revision": self.world_revision,
                "assignments": [{"variable": n, "value": value_payload(v)} for n, v in self.assignments],
                "observe": list(self.observe),
                "proposer": {"kind": p.proposer_kind.value, "id": p.proposer_id, "suggestion": p.proposal_digest}}

    @property
    def digest(self) -> str:
        return digest(self.identity())

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROPOSAL_SCHEMA, "action_id": self.action_id, "world_revision": self.world_revision,
                "assignments": [{"variable": n, "value": value_payload(v)} for n, v in self.assignments],
                "observe": list(self.observe), "proposer": self.proposer.to_dict(), "rationale": self.rationale,
                "source": None if self.source is None else self.source.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProposedAction":
        expect_schema(payload.get("schema"), PROPOSAL_SCHEMA)
        return cls(payload["action_id"], payload["world_revision"],
                   tuple((a["variable"], value_from(a["value"])) for a in payload["assignments"]),
                   tuple(payload["observe"]), ProposalProvenance.from_dict(payload["proposer"]),
                   payload.get("rationale", ""),
                   None if payload.get("source") is None else suggestion_from_dict(payload["source"]))


def suggestion_from_dict(payload: Mapping[str, Any]) -> ExternalSuggestion:
    """Rebuild a stored certified ``ExternalSuggestion`` (its own constructor re-applies the authority-key refusal)."""
    if payload.get("schema") != EXTERNAL_SUGGESTION_SCHEMA:
        raise WorldRefused(f"not an external suggestion record: {payload.get('schema')!r}")
    return ExternalSuggestion(ProposerKind(payload["engine_kind"]), payload["engine_id"], payload["engine_version"],
                              ActionFamily(payload["family"]), payload["target_ref"], payload["point"],
                              payload["rationale"], payload.get("acquisition_value"), payload.get("extra", {}))


# ---- external intake ------------------------------------------------------------------------------------------------------
class IntakeCode(str, Enum):
    AUTHORITY_KEY = "AUTHORITY_KEY"
    UNKNOWN_KEY = "UNKNOWN_KEY"
    NOT_A_TYPED_VALUE = "NOT_A_TYPED_VALUE"
    MALFORMED = "MALFORMED"
    STALE_REVISION = "STALE_REVISION"
    FAMILY_MISMATCH = "FAMILY_MISMATCH"
    NOT_THROUGH_INTAKE = "NOT_THROUGH_INTAKE"


@dataclass(frozen=True)
class IntakeRefusal:
    """A structured refusal of an external proposal before any feasibility check (it never reaches one)."""

    code: IntakeCode
    subject: str
    message: str
    suggestion_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", IntakeCode(self.code))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": INTAKE_REFUSAL_SCHEMA, "code": self.code.value, "subject": self.subject,
                "message": self.message, "suggestion_digest": self.suggestion_digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IntakeRefusal":
        expect_schema(payload.get("schema"), INTAKE_REFUSAL_SCHEMA)
        return cls(IntakeCode(payload["code"]), payload["subject"], payload["message"], payload["suggestion_digest"])


def _key_form(key: Any) -> str:
    """A key as a forbidden-key test reads it: NFKC-normalized, casefolded, with format characters (zero-width and
    similar, Unicode category Cf) removed and surrounding whitespace stripped, so a look-alike spelling is the key."""
    text_ = unicodedata.normalize("NFKC", str(key))
    text_ = "".join(ch for ch in text_ if unicodedata.category(ch) != "Cf")
    return text_.casefold().strip()


def _forbidden_key(node: Any, path: str) -> str | None:
    if isinstance(node, Mapping):
        for k, v in node.items():
            if _key_form(k) in FORBIDDEN_PROPOSAL_KEYS:
                return f"{path}.{k}"
            found = _forbidden_key(v, f"{path}.{k}")
            if found:
                return found
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            found = _forbidden_key(v, f"{path}[{i}]")
            if found:
                return found
    return None


def proposed_action_from_suggestion(suggestion: ExternalSuggestion, *, world: Any) -> ProposedAction | IntakeRefusal:
    """The one intake for external proposers (a language model, a search engine): a certified ExternalSuggestion.

    The suggestion already refused the certified authority keys at any depth.  Here its ``point`` must be exactly
    ``{"assignments": [{"variable": name, "value": <schema-tagged typed value>}, ...], "observe": [names]}``, its
    ``extra`` exactly ``{"world_revision": <64-hex>}`` naming the revision of ``world`` it was made for, and its family
    the declared action's family.  A bare number, an untyped string, an unknown key, a feasibility/budget/domain/belief
    assertion, another revision or another family is refused with a structured code.  Its acquisition value is never
    read.  ``target_ref`` names the action.  The proposal carries the suggestion as its ``source``, and the check
    re-runs this intake against its own world.  (Not the certified ``sria.decision.external.proposal_from_suggestion``,
    which builds an ``ActionProposal``.)"""
    if not isinstance(suggestion, ExternalSuggestion):
        raise TypeError("only an ExternalSuggestion is an external proposal")
    sdig = suggestion.digest
    world_revision = world.revision_id

    def refuse(code: IntakeCode, subject: str, message: str) -> IntakeRefusal:
        return IntakeRefusal(code, subject, message, sdig)

    for where, node in (("point", suggestion.point), ("extra", suggestion.extra)):
        found = _forbidden_key(node, where)
        if found:
            return refuse(IntakeCode.AUTHORITY_KEY, found, "a proposer has no authority over this key")
    unknown_extra = sorted(set(suggestion.extra) - {"world_revision"})
    if unknown_extra:
        return refuse(IntakeCode.UNKNOWN_KEY, ",".join(f"extra.{k}" for k in unknown_extra),
                      "a suggestion's extra is exactly {world_revision}; nothing else in it is read")
    made_for = dict(suggestion.extra).get("world_revision")
    if not isinstance(made_for, str) or not HEX64.match(made_for):
        return refuse(IntakeCode.MALFORMED, "extra.world_revision", "a suggestion names the world revision it was made for")
    if made_for != world_revision:
        return refuse(IntakeCode.STALE_REVISION, "extra.world_revision",
                      f"made for world revision {made_for[:12]}, not {world_revision[:12]}")
    point = dict(suggestion.point)
    extra_keys = set(point) - SUGGESTION_POINT_KEYS
    if extra_keys or "assignments" not in point:
        return refuse(IntakeCode.UNKNOWN_KEY, ",".join(sorted(extra_keys)) or "assignments",
                      "a suggestion point is exactly {assignments, observe}")
    pairs = []
    raw = point["assignments"]
    if not isinstance(raw, (list, tuple)):
        return refuse(IntakeCode.MALFORMED, "assignments", "assignments are a list of {variable, value} pairs")
    for i, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != {"variable", "value"}:
            return refuse(IntakeCode.MALFORMED, f"assignments[{i}]", "each assignment is exactly {variable, value}")
        encoded = item["value"]
        if not isinstance(encoded, Mapping) or "schema" not in encoded:
            return refuse(IntakeCode.NOT_A_TYPED_VALUE, str(item["variable"]),
                          "a value is a schema-tagged typed value; a bare number or string is never interpreted")
        try:
            value = value_from(encoded)
            canonical_payload = value_payload(value)
        except Exception as exc:  # noqa: BLE001 - any decode failure is a refusal, never a guess
            return refuse(IntakeCode.NOT_A_TYPED_VALUE, str(item["variable"]), str(exc))
        if dict(encoded) != canonical_payload:
            return refuse(IntakeCode.NOT_A_TYPED_VALUE, str(item["variable"]),
                          "a value payload is exactly its typed value's own encoding (no extra or altered key is "
                          "carried along)")
        pairs.append((item["variable"], value))
    spec = world.action(suggestion.target_ref)
    if spec is not None and spec.family is not suggestion.family:
        return refuse(IntakeCode.FAMILY_MISMATCH, suggestion.target_ref,
                      f"the suggestion is labelled {suggestion.family.value}, the declared action is {spec.family.value}")
    provenance = ProposalProvenance(suggestion.engine_kind, f"{suggestion.engine_id}@{suggestion.engine_version}",
                                    proposal_digest=sdig)
    try:
        return ProposedAction(suggestion.target_ref, world_revision, tuple(pairs), tuple(point.get("observe", ())),
                              provenance, suggestion.rationale, suggestion)
    except WorldRefused as exc:
        return refuse(IntakeCode.MALFORMED, "proposal", str(exc))


__all__ = [
    "ActionMode", "ActionSpec", "COST_DIMENSIONS", "ControlSpec", "ExecutionKind", "FORBIDDEN_PROPOSAL_KEYS",
    "GEN1_FORBIDDEN_KEYS", "IntakeCode", "IntakeRefusal", "ProposedAction", "SUGGESTION_POINT_KEYS",
    "proposed_action_from_suggestion", "suggestion_from_dict",
]
