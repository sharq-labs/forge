"""The ScientificWorld: a read-only, content-addressed reasoning view over declared and authoritative records.

A world is a VIEW.  It holds the problem's declared variables (each carrying its reused repsem role declaration and,
if it has a current value, the owner record the value is bound to), the protocol's declared actions, constraints and
observation channels, the model records whose applicability gates model execution, verbatim provider status and
health reports, the budget as its owner records state it, and typed references to the records it summarizes.  It
authors no state, evidence, applicability verdict, hypothesis status or uncertainty: it computes no value, it fills
no gap, and every missing item stays missing.

Identity.  ``content_digest`` covers the material fields only (CORE_FREEZE_POLICY §6: labels and descriptions are not
material).  ``revision_id`` binds that content to its lineage (revision number, parent revision, changed fields).  The
narrative ``reason`` of a revision is recorded but is not identity, as ``TwinRevision`` excludes its change note.
A world is frozen; a material change is a new revision made by :meth:`ScientificWorld.derive`, which computes the
changed fields itself and refuses a revision that changes nothing.  :func:`verify_lineage` re-derives a chain.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from engcore.execution.orchestration.resources import ResourceBudget, ResourceUsage
from engcore.mind.repsem.roles import RoleRefused, RoleSource, RoleTable, VariableRole
from engcore.providers.catalog import Availability
from engcore.providers.health import ProviderHealth
from engcore.providers.identity import content_digest
from engcore.scientific import ExperimentBudget, Quantity, ScientificModelDefinition
from engcore.scientific.ir.values import as_context_value
from engcore.scientific.results.immutable import detach, freeze
from engcore.sria.decision.recommendation import BudgetPlan

from .actions import ActionSpec
from .base import (
    HEX64, SOFTWARE_VERSION, RecordRef, WorldRefused, digest, expect_schema, schema, text,
)
from .domains import ALL_ACTIONS, DeclaredConstraint, declared_source, membership
from .variables import (
    CHANNEL_ROLES, CONTROLLABILITY_BY_ROLE, Controllability, Entity, Observability, ObservationChannel, ValueOrigin,
    WorldVariable,
)

WORLD_SCHEMA = schema("scientific_world")
APPLICABILITY_SCHEMA = schema("applicability_binding")
PROVIDER_SCHEMA = schema("provider_snapshot")
BUDGET_SCHEMA = schema("budget")
LINEAGE_SCHEMA = schema("lineage")
HEALTH_SCHEMA = "engcore.providers.health/1"

#: The fields a revision may change; each is material.  ``world_id`` names the world and never changes.
MATERIAL_FIELDS = ("actions", "applicability", "basis", "budget", "channels", "constraints", "declared_by", "entities",
                   "providers", "references", "variables")

#: ``ProviderHealthReport.executable``: AVAILABLE, UNQUALIFIED and QUALIFIED may run ("running is not trusting").
#: A report dict cannot call the property, so the set is restated here and pinned equal to the property by test.
EXECUTABLE_HEALTH = frozenset({ProviderHealth.AVAILABLE, ProviderHealth.UNQUALIFIED, ProviderHealth.QUALIFIED})

#: Roles whose current value may enter a model-applicability context.  A latent parameter, a measurement or a derived
#: quantity is never a caller-declared fact about where a model is applied (Gen1 repsem refuses the same roles).
APPLICABILITY_CONTEXT_ROLES = frozenset({VariableRole.CONTROLLED_INPUT, VariableRole.FIXED_PROTOCOL_CONDITION,
                                         VariableRole.STATE_VARIABLE, VariableRole.NUISANCE_VARIABLE})
#: Roles a declared constraint may read: what an action sets or holds, the state, and the passive environment.
CONSTRAINT_ROLES = APPLICABILITY_CONTEXT_ROLES

BUDGET_DIMENSIONS = ("cost", "experiments", "solver_calls", "wall_time")


# ---- model applicability (the core owner, consulted, never re-implemented) ------------------------------------------------
@dataclass(frozen=True)
class ApplicabilityBinding:
    """A model record whose validity domain gates the actions that execute it.

    Evaluated only by ``ScientificModelDefinition.assess_validity(declared=..., record_values=True)``, so the verdict
    carries the model id and version.  The world does not author the domain: it carries the model record it was
    handed.  It gates MODEL_EXECUTION actions; for a SYSTEM_QUERY it is an annotation only."""

    model: ScientificModelDefinition

    def __post_init__(self) -> None:
        if not isinstance(self.model, ScientificModelDefinition):
            raise WorldRefused("an applicability binding carries the ScientificModelDefinition that owns the domain")

    @property
    def binding_id(self) -> str:
        return f"{self.model.model_id}@{self.model.version}"

    @property
    def reads(self) -> frozenset[str]:
        validity = self.model.validity
        return frozenset(validity.context_keys) - frozenset(validity.derived_quantities)

    def assess(self, declared: Mapping[str, Any]):
        values = {k: as_context_value(v) for k, v in sorted(declared.items()) if k in self.reads}
        return self.model.assess_validity(declared=values, record_values=True)

    def identity(self) -> dict[str, Any]:
        return {"binding_id": self.binding_id, "model_digest": digest(self.model.to_dict())}

    def to_dict(self) -> dict[str, Any]:
        return {"schema": APPLICABILITY_SCHEMA, "model": self.model.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ApplicabilityBinding":
        expect_schema(payload.get("schema"), APPLICABILITY_SCHEMA)
        return cls(ScientificModelDefinition.from_dict(payload["model"]))


# ---- provider snapshots: the providers' own records, verbatim ---------------------------------------------------------------
@dataclass(frozen=True)
class ProviderSnapshot:
    """A provider's ``ProviderStatus.to_dict()`` and ``ProviderHealthReport.to_dict()``, embedded verbatim.

    Replayable where a live probe is not.  Construction re-derives the report's status digest by the owner's rule
    (``content_digest`` of the status minus its location) and refuses a pair that does not belong together."""

    status: Mapping[str, Any]
    report: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.status, Mapping) or not isinstance(self.report, Mapping):
            raise WorldRefused("a provider snapshot embeds the status and health report records")
        if self.report.get("schema") != HEALTH_SCHEMA:
            raise WorldRefused(f"not a provider health report: {self.report.get('schema')!r}")
        try:
            pid = self.status["capability"]["provider_id"]
            Availability(self.status["availability"])
            ProviderHealth(self.report["health"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WorldRefused(f"malformed provider status or report: {exc}") from None
        if self.report.get("provider_id") != pid:
            raise WorldRefused(f"the health report is for {self.report.get('provider_id')!r}, the status for {pid!r}")
        expected = content_digest({k: v for k, v in detach(self.status).items() if k != "location"})
        if self.report.get("status_digest") != expected:
            raise WorldRefused(f"provider {pid!r}: the report's status digest does not match this status")
        object.__setattr__(self, "status", freeze(detach(self.status)))
        object.__setattr__(self, "report", freeze(detach(self.report)))

    @classmethod
    def from_status(cls, status: Any, report: Any) -> "ProviderSnapshot":
        return cls(status.to_dict(), report.to_dict())

    @property
    def provider_id(self) -> str:
        return self.status["capability"]["provider_id"]

    @property
    def version(self) -> str:
        return self.status.get("version", "")

    @property
    def build_digest(self) -> str:
        return self.status.get("digest", "")

    @property
    def availability(self) -> Availability:
        return Availability(self.status["availability"])

    @property
    def health(self) -> ProviderHealth:
        return ProviderHealth(self.report["health"])

    @property
    def reason(self) -> str:
        return self.report.get("reason", "")

    @property
    def executable(self) -> bool:
        return self.availability is Availability.AVAILABLE and self.health in EXECUTABLE_HEALTH

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROVIDER_SCHEMA, "status": detach(self.status), "report": detach(self.report)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProviderSnapshot":
        expect_schema(payload.get("schema"), PROVIDER_SCHEMA)
        return cls(payload["status"], payload["report"])


# ---- budget: owner records, every dimension declared ---------------------------------------------------------------------------
def _count(value: Any, field_name: str, *, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise WorldRefused(f"{field_name} must be an int >= {minimum} (no bool, no float, no coercion), got {value!r}")
    return value


def _seconds(value: Any, field_name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise WorldRefused(f"{field_name} must be a finite non-negative number of seconds, got {value!r}")
    return float(value)


def _resource_payload(budget: ResourceBudget) -> dict[str, Any]:
    return {"max_wall_seconds": budget.max_wall_seconds, "max_function_evaluations": budget.max_function_evaluations}


@dataclass(frozen=True)
class WorldBudget:
    """The budget as its owner records state it.  Every dimension is LIMITED by a record or declared UNBOUNDED with a
    basis; a dimension that is neither is undeclared, and an action then cannot be shown affordable.

    * experiments: an ``ExperimentBudget`` (observations; its silent coercion is pre-checked, attempt caps are not
      tracked in BR1 and are refused) with the observations already spent;
    * solver_calls and wall_time: an execution ``ResourceBudget`` (``max_function_evaluations`` is the solver-call
      limit, ``max_wall_seconds`` the wall-time limit) with its ``ResourceUsage``;
    * cost: a ``BudgetPlan`` (its validation-pool fence is called, never copied) in a stated cost unit.

    The spent amounts are the owner records' statements (``authority``); the Mind never counts them."""

    experiments: ExperimentBudget | None = None
    observations_spent: int | None = None
    compute: ResourceBudget | None = None
    compute_used: ResourceUsage | None = None
    cost: BudgetPlan | None = None
    cost_unit: str = ""
    unbounded: Any = ()
    authority: RecordRef | None = None

    def __post_init__(self) -> None:
        if self.experiments is not None:
            if not isinstance(self.experiments, ExperimentBudget):
                raise WorldRefused("experiments must be an ExperimentBudget")
            _count(self.experiments.max_observations, "max_observations", minimum=1)
            if self.experiments.max_attempts is not None:
                raise WorldRefused("an attempt cap is not tracked in BR1; declare observations only")
            _count(self.observations_spent, "observations_spent", minimum=0)
        elif self.observations_spent is not None:
            raise WorldRefused("observations_spent without an experiment budget")
        if self.compute is not None:
            if not isinstance(self.compute, ResourceBudget) or not isinstance(self.compute_used, ResourceUsage):
                raise WorldRefused("a compute budget is a ResourceBudget with its ResourceUsage")
            if self.compute.max_cpu_seconds is not None or self.compute.max_peak_memory_bytes is not None:
                raise WorldRefused("only solver calls and wall time are BR1 budget dimensions")
            if self.compute.max_function_evaluations is not None:
                _count(self.compute.max_function_evaluations, "max_function_evaluations", minimum=1)
                _count(self.compute_used.function_evaluations, "function_evaluations used", minimum=0)
            if self.compute.max_wall_seconds is not None:
                _seconds(self.compute.max_wall_seconds, "max_wall_seconds")
                _seconds(self.compute_used.wall_seconds, "wall_seconds used")
            if self.compute.max_function_evaluations is None and self.compute.max_wall_seconds is None:
                raise WorldRefused("a compute budget limits solver calls or wall time")
        elif self.compute_used is not None:
            raise WorldRefused("compute usage without a compute budget")
        if self.cost is not None:
            if not isinstance(self.cost, BudgetPlan):
                raise WorldRefused("cost must be a BudgetPlan")
            text(self.cost_unit, "cost_unit (the cost budget states its unit)")
        elif self.cost_unit:
            raise WorldRefused("cost_unit without a cost budget")
        pairs = tuple(sorted(dict(self.unbounded).items())) if not isinstance(self.unbounded, tuple) else tuple(
            sorted(self.unbounded))
        for dim, basis in pairs:
            if dim not in BUDGET_DIMENSIONS:
                raise WorldRefused(f"{dim!r} is not a budget dimension {BUDGET_DIMENSIONS}")
            text(basis, f"unbounded {dim!r} basis")
        object.__setattr__(self, "unbounded", pairs)
        both = set(self._limited()) & {d for d, _ in pairs}
        if both:
            raise WorldRefused(f"dimensions {sorted(both)} are both limited and unbounded")
        if self._limited() and not isinstance(self.authority, RecordRef):
            raise WorldRefused("a limited budget cites the record that states what was spent (authority RecordRef)")

    def _limited(self) -> tuple[str, ...]:
        out = []
        if self.experiments is not None:
            out.append("experiments")
        if self.compute is not None and self.compute.max_function_evaluations is not None:
            out.append("solver_calls")
        if self.compute is not None and self.compute.max_wall_seconds is not None:
            out.append("wall_time")
        if self.cost is not None:
            out.append("cost")
        return tuple(sorted(out))

    def status(self, dimension: str) -> str:
        """'limited', 'unbounded' (declared, with a basis) or 'undeclared'."""
        if dimension in self._limited():
            return "limited"
        if dimension in {d for d, _ in self.unbounded}:
            return "unbounded"
        return "undeclared"

    def remaining(self, dimension: str) -> Any:
        """Signed remaining amount of a limited dimension (an overrun stays negative; nothing is clamped)."""
        if self.status(dimension) != "limited":
            return None
        if dimension == "experiments":
            return self.experiments.max_observations - self.observations_spent
        if dimension == "solver_calls":
            return self.compute.max_function_evaluations - self.compute_used.function_evaluations
        if dimension == "wall_time":
            return float(self.compute.max_wall_seconds) - float(self.compute_used.wall_seconds)
        return self.cost.general_pool

    def identity(self) -> dict[str, Any]:
        return self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": BUDGET_SCHEMA,
                "experiments": None if self.experiments is None else self.experiments.to_dict(),
                "observations_spent": self.observations_spent,
                "compute": None if self.compute is None else _resource_payload(self.compute),
                "compute_used": None if self.compute_used is None else {
                    "wall_seconds": self.compute_used.wall_seconds,
                    "function_evaluations": self.compute_used.function_evaluations},
                "cost": None if self.cost is None else self.cost.to_dict(), "cost_unit": self.cost_unit,
                "unbounded": [list(p) for p in self.unbounded],
                "authority": None if self.authority is None else self.authority.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorldBudget":
        expect_schema(payload.get("schema"), BUDGET_SCHEMA)
        cost = payload.get("cost")
        if cost is not None and not {"spent_general", "spent_validation"} <= set(cost):
            raise WorldRefused("a cost budget states what was spent; a missing spent amount is never zero")
        compute = payload.get("compute")
        used = payload.get("compute_used")
        return cls(None if payload.get("experiments") is None else ExperimentBudget.from_dict(payload["experiments"]),
                   payload.get("observations_spent"),
                   None if compute is None else ResourceBudget(**compute),
                   None if used is None else ResourceUsage(wall_seconds=used["wall_seconds"],
                                                           function_evaluations=used["function_evaluations"]),
                   None if cost is None else BudgetPlan.from_dict(cost), payload.get("cost_unit", ""),
                   tuple((d, b) for d, b in payload.get("unbounded", ())),
                   None if payload.get("authority") is None else RecordRef.from_dict(payload["authority"]))


# ---- lineage --------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Lineage:
    revision: int = 0
    parent: str = ""
    reason: str = ""
    changed_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _count(self.revision, "revision", minimum=0)
        object.__setattr__(self, "changed_fields", tuple(sorted(self.changed_fields)))
        if not isinstance(self.reason, str):
            raise WorldRefused("reason is text")
        if self.revision == 0:
            if self.parent or self.changed_fields:
                raise WorldRefused("a root world has no parent and no changed fields")
        else:
            if not isinstance(self.parent, str) or not HEX64.match(self.parent):
                raise WorldRefused("a revision names its parent revision id")
            text(self.reason, "a revision states its reason")
            if not self.changed_fields or set(self.changed_fields) - set(MATERIAL_FIELDS):
                raise WorldRefused(f"changed_fields must be a non-empty subset of {MATERIAL_FIELDS}")

    def identity(self) -> dict[str, Any]:
        return {"revision": self.revision, "parent": self.parent, "changed_fields": list(self.changed_fields)}

    def to_dict(self) -> dict[str, Any]:
        return {"schema": LINEAGE_SCHEMA, **self.identity(), "reason": self.reason}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Lineage":
        expect_schema(payload.get("schema"), LINEAGE_SCHEMA)
        return cls(payload["revision"], payload["parent"], payload.get("reason", ""), tuple(payload["changed_fields"]))


def _sorted_unique(items: Iterable[Any], key: Any, what: str, kind: type) -> tuple[Any, ...]:
    items = tuple(items)
    for item in items:
        if not isinstance(item, kind):
            raise WorldRefused(f"{what} must be {kind.__name__} records, got {type(item).__name__}")
    keyf = key if callable(key) else (lambda i: getattr(i, key))
    ids = [keyf(i) for i in items]
    if len(set(ids)) != len(ids):
        raise WorldRefused(f"{what} repeat an id: {sorted({i for i in ids if ids.count(i) > 1})}")
    return tuple(sorted(items, key=keyf))


# ---- the world --------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ScientificWorld:
    world_id: str
    variables: tuple[WorldVariable, ...]
    entities: tuple[Entity, ...] = ()
    constraints: tuple[DeclaredConstraint, ...] = ()
    actions: tuple[ActionSpec, ...] = ()
    channels: tuple[ObservationChannel, ...] = ()
    applicability: tuple[ApplicabilityBinding, ...] = ()
    providers: tuple[ProviderSnapshot, ...] = ()
    budget: WorldBudget = field(default_factory=WorldBudget)
    references: tuple[RecordRef, ...] = ()
    declared_by: RoleSource | None = None
    basis: str = ""
    lineage: Lineage = field(default_factory=Lineage)
    description: str = ""                                   # non-material
    _roles: Any = field(init=False, repr=False, compare=False, default=None)
    _content: str = field(init=False, repr=False, compare=False, default="")
    _revision: str = field(init=False, repr=False, compare=False, default="")

    def __post_init__(self) -> None:
        text(self.world_id, "world_id")
        object.__setattr__(self, "declared_by", declared_source(self.declared_by, f"world {self.world_id!r}"))
        text(self.basis, f"world {self.world_id!r} basis")
        variables = _sorted_unique(self.variables, "name", "variables", WorldVariable)
        if not variables:
            raise WorldRefused("a world declares its variables")
        object.__setattr__(self, "variables", variables)
        try:
            roles = RoleTable(tuple(v.declaration for v in variables))
        except RoleRefused as exc:
            raise WorldRefused(f"role table: {exc}") from None
        if roles.is_legacy:
            raise WorldRefused("a world is never built on the legacy adapter's inferred roles")
        object.__setattr__(self, "_roles", roles)
        declared = {v.name for v in variables}

        object.__setattr__(self, "entities", _sorted_unique(self.entities, "entity_id", "entities", Entity))
        for e in self.entities:
            if set(e.variables) - declared:
                raise WorldRefused(f"entity {e.entity_id!r} groups undeclared variables {sorted(set(e.variables) - declared)}")

        object.__setattr__(self, "channels", _sorted_unique(self.channels, "variable", "channels", ObservationChannel))
        for c in self.channels:
            if c.variable not in declared:
                raise WorldRefused(f"observation channel {c.variable!r} is not a declared variable")
            role = roles.role(c.variable)
            if role not in CHANNEL_ROLES:
                what = "a latent parameter is estimated" if role is VariableRole.LATENT_PARAMETER else \
                    "a derived quantity is computed, never an independent observation"
                raise WorldRefused(f"channel {c.variable!r}: {what}, never observed through a channel")
        for v in variables:
            if v.origin is ValueOrigin.OBSERVED and not self.has_channel(v.name):
                raise WorldRefused(f"{v.name!r}: an OBSERVED value needs a declared observation channel")

        object.__setattr__(self, "applicability", _sorted_unique(
            self.applicability, lambda a: a.binding_id, "applicability bindings", ApplicabilityBinding))
        for a in self.applicability:
            for name in sorted(a.reads):
                if name not in declared:
                    raise WorldRefused(f"applicability {a.binding_id!r} reads {name!r}, which the world does not declare")
                spec = next((i for i in a.model.inputs if i.name == name), None)
                exemplar = getattr(spec, "unit_exemplar", None)
                var = self.variable(name)
                if exemplar and not Quantity(1.0, exemplar).is_compatible_with(var.unit):
                    raise WorldRefused(f"applicability {a.binding_id!r}: input {name!r} is in {exemplar!r}, the world "
                                       f"declares {var.unit!r}")

        object.__setattr__(self, "providers", _sorted_unique(self.providers, lambda p: p.provider_id, "providers",
                                                             ProviderSnapshot))
        if not isinstance(self.budget, WorldBudget):
            raise WorldRefused("budget must be a WorldBudget")
        refs = tuple(self.references)
        if any(not isinstance(r, RecordRef) for r in refs) or len(set(refs)) != len(refs):
            raise WorldRefused("references must be unique RecordRef records")
        object.__setattr__(self, "references", tuple(sorted(refs)))
        if not isinstance(self.lineage, Lineage):
            raise WorldRefused("lineage must be a Lineage record")
        if not isinstance(self.description, str):
            raise WorldRefused("description is text")

        object.__setattr__(self, "actions", _sorted_unique(self.actions, "action_id", "actions", ActionSpec))
        for a in self.actions:
            a.bind(self)
        action_ids = {a.action_id for a in self.actions}
        object.__setattr__(self, "constraints",
                           _sorted_unique(self.constraints, "constraint_id", "constraints", DeclaredConstraint))
        for c in self.constraints:
            self._check_constraint(c)
            unknown = set(c.applies_to) - action_ids - {ALL_ACTIONS}
            if unknown:
                raise WorldRefused(f"constraint {c.constraint_id!r} applies to undeclared actions {sorted(unknown)}")
        content = digest(self._material())
        object.__setattr__(self, "_content", content)
        object.__setattr__(self, "_revision", digest({"world_id": self.world_id, "content": content,
                                                      **self.lineage.identity()}))

    # ---- construction checks ------------------------------------------------------------------------------------------------
    def _check_constraint(self, c: DeclaredConstraint) -> None:
        for name in c.reads:
            if not self.declares(name):
                raise WorldRefused(f"constraint {c.constraint_id!r} reads undeclared variable {name!r}")
            if self.role(name) not in CONSTRAINT_ROLES:
                raise WorldRefused(f"constraint {c.constraint_id!r} reads {name!r}, a {self.role(name).value}: a "
                                   "constraint limits what is set, held, or the state and environment it acts in")
        metric = self.variable(c.consequence.metric)
        if not c.consequence.bound.is_compatible_with(metric.unit):
            raise WorldRefused(f"constraint {c.constraint_id!r}: bound {c.consequence.bound} is not compatible with "
                               f"{metric.name!r} in {metric.unit!r}")
        if c.guard is not None:
            self._check_guard(c.guard, f"constraint {c.constraint_id!r}")

    def _check_guard(self, guard: Any, where: str) -> None:
        if not self.declares(guard.variable):
            raise WorldRefused(f"{where}: guard reads undeclared variable {guard.variable!r}")
        var = self.variable(guard.variable)
        if var.domain is None:
            raise WorldRefused(f"{where}: guard variable {guard.variable!r} has no declared domain to check values in")
        for value in guard.values:
            if membership(var.domain, value) is not None:
                raise WorldRefused(f"{where}: guard value {value!r} is not in the declared domain of {guard.variable!r}")

    # ---- identity ----------------------------------------------------------------------------------------------------------
    def _sections(self) -> dict[str, Any]:
        return {
            "variables": {"roles": self._roles.to_dict(), "fields": [v.identity() for v in self.variables]},
            "entities": [e.to_dict() for e in self.entities],
            "constraints": [c.identity() for c in self.constraints],
            "actions": [a.identity() for a in self.actions],
            "channels": [c.to_dict() for c in self.channels],
            "applicability": [a.identity() for a in self.applicability],
            "providers": [p.to_dict() for p in self.providers],
            "budget": self.budget.identity(),
            "references": [r.to_dict() for r in self.references],
            "declared_by": self.declared_by.value,
            "basis": self.basis,
        }

    def _material(self) -> dict[str, Any]:
        return {"schema": WORLD_SCHEMA, "world_id": self.world_id, **self._sections()}

    @property
    def content_digest(self) -> str:
        return self._content

    @property
    def revision_id(self) -> str:
        return self._revision

    @property
    def revision(self) -> int:
        return self.lineage.revision

    def changed_from(self, other: "ScientificWorld") -> tuple[str, ...]:
        before, after = other._sections(), self._sections()
        return tuple(sorted(k for k in MATERIAL_FIELDS if digest(before[k]) != digest(after[k])))

    def derive(self, *, reason: str, **changes: Any) -> "ScientificWorld":
        """A new revision with these material changes.  The parent is this world; the changed fields are computed."""
        unknown = set(changes) - set(MATERIAL_FIELDS)
        if unknown:
            raise WorldRefused(f"a revision changes material fields only; not {sorted(unknown)}")
        text(reason, "a revision states its reason")
        candidate = dataclasses.replace(self, **changes)
        changed = candidate.changed_from(self)
        if not changed:
            raise WorldRefused("no material change: a revision must change what the world states")
        return dataclasses.replace(candidate, lineage=Lineage(self.lineage.revision + 1, self.revision_id, reason, changed))

    # ---- read-only views ------------------------------------------------------------------------------------------------------
    @property
    def roles(self) -> RoleTable:
        return self._roles

    def declares(self, name: str) -> bool:
        return any(v.name == name for v in self.variables)

    def variable(self, name: str) -> WorldVariable:
        for v in self.variables:
            if v.name == name:
                return v
        raise WorldRefused(f"variable {name!r} is not declared in world {self.world_id!r} (never inferred from a name)")

    def role(self, name: str) -> VariableRole:
        return self.variable(name).role

    def has_channel(self, name: str) -> bool:
        return any(c.variable == name for c in self.channels)

    def controllability(self, name: str) -> Controllability:
        return CONTROLLABILITY_BY_ROLE[self.role(name)]

    def observability(self, name: str) -> Observability:
        role = self.role(name)
        if role is VariableRole.LATENT_PARAMETER:
            return Observability.NOT_OBSERVABLE
        if role is VariableRole.DERIVED_QUANTITY:
            return Observability.DERIVED_ONLY
        return Observability.OBSERVED_CHANNEL if self.has_channel(name) else Observability.NO_CHANNEL

    def observables(self) -> tuple[str, ...]:
        return tuple(c.variable for c in self.channels)

    def latent_quantities(self) -> tuple[str, ...]:
        return self._roles.names(VariableRole.LATENT_PARAMETER)

    def relationships(self) -> tuple[tuple[str, str, str], ...]:
        """Derived, never declared separately: role-table driven_by / derived_from edges and entity membership."""
        out = []
        for d in self._roles.declarations:
            out += [("driven_by", d.name, src) for src in d.driven_by]
            out += [("derived_from", d.name, src) for src in d.derived_from]
        for e in self.entities:
            out += [("member_of", n, e.entity_id) for n in e.variables]
        return tuple(sorted(out))

    def uncertainty_summary(self) -> dict[str, str]:
        """Per-variable uncertainty kind as the records state it ('unknown' unless quantified)."""
        return {v.name: v.uncertainty.kind.value for v in self.variables}

    def units(self) -> dict[str, str]:
        return {v.name: v.unit for v in self.variables}

    def action(self, action_id: str) -> ActionSpec | None:
        for a in self.actions:
            if a.action_id == action_id:
                return a
        return None

    def available_actions(self) -> tuple[str, ...]:
        return tuple(a.action_id for a in self.actions)

    def applicability_binding(self, binding_id: str) -> ApplicabilityBinding | None:
        for a in self.applicability:
            if a.binding_id == binding_id:
                return a
        return None

    def applicability_of(self, name: str) -> tuple[str, ...]:
        return tuple(a.binding_id for a in self.applicability if name in a.reads)

    def provider(self, provider_id: str) -> ProviderSnapshot | None:
        for p in self.providers:
            if p.provider_id == provider_id:
                return p
        return None

    # ---- serialization --------------------------------------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"schema": WORLD_SCHEMA, "software_version": SOFTWARE_VERSION, "world_id": self.world_id,
                "declared_by": self.declared_by.value, "basis": self.basis, "description": self.description,
                "roles": self._roles.to_dict(), "variables": [v.to_dict() for v in self.variables],
                "entities": [e.to_dict() for e in self.entities],
                "constraints": [c.to_dict() for c in self.constraints], "actions": [a.to_dict() for a in self.actions],
                "channels": [c.to_dict() for c in self.channels],
                "applicability": [a.to_dict() for a in self.applicability],
                "providers": [p.to_dict() for p in self.providers], "budget": self.budget.to_dict(),
                "references": [r.to_dict() for r in self.references], "lineage": self.lineage.to_dict(),
                "content_digest": self.content_digest, "revision_id": self.revision_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificWorld":
        expect_schema(payload.get("schema"), WORLD_SCHEMA)
        try:
            roles = RoleTable.from_dict(payload["roles"])
        except RoleRefused as exc:
            raise WorldRefused(f"role table: {exc}") from None
        decls = {d.name: d for d in roles.declarations}
        variables = []
        for v in payload["variables"]:
            if v.get("name") not in decls:
                raise WorldRefused(f"variable {v.get('name')!r} has no role declaration")
            variables.append(WorldVariable.from_dict(v, decls[v["name"]]))
        if len(variables) != len(decls):
            raise WorldRefused("the role table declares variables the world does not carry")
        world = cls(payload["world_id"], tuple(variables),
                    tuple(Entity.from_dict(e) for e in payload.get("entities", ())),
                    tuple(DeclaredConstraint.from_dict(c) for c in payload.get("constraints", ())),
                    tuple(ActionSpec.from_dict(a) for a in payload.get("actions", ())),
                    tuple(ObservationChannel.from_dict(c) for c in payload.get("channels", ())),
                    tuple(ApplicabilityBinding.from_dict(a) for a in payload.get("applicability", ())),
                    tuple(ProviderSnapshot.from_dict(p) for p in payload.get("providers", ())),
                    WorldBudget.from_dict(payload["budget"]),
                    tuple(RecordRef.from_dict(r) for r in payload.get("references", ())),
                    RoleSource(payload["declared_by"]), payload["basis"],
                    Lineage.from_dict(payload["lineage"]), payload.get("description", ""))
        for key, value in (("content_digest", world.content_digest), ("revision_id", world.revision_id)):
            if key in payload and payload[key] != value:
                raise WorldRefused(f"stored {key} {payload[key]!r} does not match the recomputed {value!r}")
        return world


def verify_lineage(world: ScientificWorld, store: Mapping[str, ScientificWorld]) -> tuple[str, ...]:
    """Walk parents from ``store`` (revision id -> world) to the root; refuse a missing, tampered or forged link."""
    chain = [world]
    seen = {world.revision_id}
    while chain[-1].lineage.revision > 0:
        child = chain[-1]
        parent = store.get(child.lineage.parent)
        if parent is None:
            raise WorldRefused(f"revision {child.revision_id[:12]} names a parent the store does not hold")
        if parent.revision_id != child.lineage.parent or parent.revision_id in seen:
            raise WorldRefused("the lineage is tampered or cyclic")
        if parent.world_id != child.world_id or parent.lineage.revision + 1 != child.lineage.revision:
            raise WorldRefused("a revision continues another world or skips a revision number")
        changed = child.changed_from(parent)
        if changed != child.lineage.changed_fields:
            raise WorldRefused(f"stated changed fields {child.lineage.changed_fields} differ from the real change {changed}")
        seen.add(parent.revision_id)
        chain.append(parent)
    return tuple(w.revision_id for w in reversed(chain))


__all__ = [
    "APPLICABILITY_CONTEXT_ROLES", "ApplicabilityBinding", "BUDGET_DIMENSIONS", "EXECUTABLE_HEALTH", "Lineage",
    "MATERIAL_FIELDS", "ProviderSnapshot", "ScientificWorld", "WorldBudget", "verify_lineage",
]
