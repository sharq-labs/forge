"""The problem / protocol declaration a world is projected from.

A :class:`ProtocolDeclaration` is what the problem specification and the protocol metadata state: each variable's
reused repsem role declaration, unit, time semantics, domain and any DECLARED set point; the declared actions,
constraints, observation channels and entities; WHERE every other current value comes from (:class:`ValueSource`,
a state owner and variable of the governing run); which model records gate model execution, which providers the
actions need, and which owner account states each budget dimension (:class:`BudgetSource`; one account states one
dimension).  It states no uncertainty policy: no FORGE owner states a decision-coverage policy, so a current value
never decides a containment (``feasibility``).

It is content-addressed (``digest``) and revisioned like a protocol document cited by ``protocol_digest`` elsewhere in
FORGE.  The world never authors it and never edits it: the execution side holds the declaration in force
(:class:`~.owners.DeclarationReader`), a world binds to it by identity, and admission checks that the world is
exactly its projection.  A changed domain, level or constraint is a new declaration revision, never a world edit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from engcore.mind.repsem.roles import RoleRefused, RoleSource, RoleTable
from engcore.scientific import Quantity, ScientificCoreError
from engcore.scientific.units.quantity import is_ratio_scale

from .actions import ActionSpec
from .base import RecordRef, WorldRefused, digest, expect_schema, schema, text
from .domains import DeclaredConstraint, declared_source
from .owners import record_key
from .variables import ORIGIN_BY_ROLE, Entity, ObservationChannel, ValueOrigin, WorldVariable

DECLARATION_SCHEMA = schema("protocol_declaration")
SOURCE_SCHEMA = schema("value_source")
BUDGET_SOURCE_SCHEMA = schema("budget_source")
BUDGET_DIMENSIONS = ("cost", "experiments", "solver_calls", "wall_time")
#: Which budget owner may state which dimension: observations are a ScientificExperiment's accounting; the others
#: are BudgetLedger accounts in the dimension's unit.
BUDGET_OWNERS = {"experiments": ("experiment",), "cost": ("ledger",), "solver_calls": ("ledger",),
                 "wall_time": ("ledger",)}


@dataclass(frozen=True)
class ValueSource:
    """``variable``'s current value is the governing run's head-state value of ``variable_id`` held by state owner
    ``owner_id``, with the declared ``origin``.  The world never states the value itself."""

    variable: str
    owner_id: str
    origin: ValueOrigin
    variable_id: str = ""

    def __post_init__(self) -> None:
        text(self.variable, "value source variable")
        text(self.owner_id, "value source state owner")
        try:
            object.__setattr__(self, "origin", ValueOrigin(self.origin))
        except ValueError:
            raise WorldRefused(f"value source {self.variable!r}: unknown origin {self.origin!r}") from None
        if self.origin is ValueOrigin.DECLARED:
            raise WorldRefused(f"value source {self.variable!r}: a DECLARED value is part of the declaration, "
                               "never read from an owner")
        if self.variable_id and type(self.variable_id) is not str:
            raise WorldRefused("variable_id is text")

    @property
    def record_id(self) -> str:
        return record_key(self.owner_id, self.variable_id or self.variable)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SOURCE_SCHEMA, "variable": self.variable, "owner_id": self.owner_id,
                "origin": self.origin.value, "variable_id": self.variable_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValueSource":
        expect_schema(payload.get("schema"), SOURCE_SCHEMA)
        return cls(payload["variable"], payload["owner_id"], ValueOrigin(payload["origin"]),
                   payload.get("variable_id", ""))


@dataclass(frozen=True)
class BudgetSource:
    """One budget dimension: stated by an owner record (``ledger`` / ``experiment`` id), or declared unbounded with
    a basis.  A dimension the declaration names neither way is undeclared, never unlimited.

    A ``cost`` ledger states the UNIT the declaration's cost amounts are in (``unit``, a unit the unit owner knows): an
    action's cost is a plain number in that unit, and the unit owner converts it into the ledger's own unit, so an
    equal budget spelled in another unit decides the same way and an amount is never read in whatever unit the ledger
    happens to use.  Solver calls (a count) and wall time (a duration) carry their own units."""

    dimension: str
    kind: str
    ref: str
    unit: str = ""

    def __post_init__(self) -> None:
        if self.dimension not in BUDGET_DIMENSIONS:
            raise WorldRefused(f"{self.dimension!r} is not a budget dimension {BUDGET_DIMENSIONS}")
        if self.kind not in ("ledger", "experiment", "unbounded"):
            raise WorldRefused(f"budget source kind {self.kind!r} is not ledger, experiment or unbounded")
        if self.kind != "unbounded" and self.kind not in BUDGET_OWNERS[self.dimension]:
            raise WorldRefused(f"{self.dimension!r} is stated by {BUDGET_OWNERS[self.dimension]}, not {self.kind!r}")
        text(self.ref, f"budget source {self.dimension!r} {'basis' if self.kind == 'unbounded' else 'owner record'}")
        if type(self.unit) is not str:
            raise WorldRefused("a budget source's unit is text")
        if (self.dimension, self.kind) == ("cost", "ledger"):
            text(self.unit, "the unit a cost ledger's amounts are declared in")
            try:
                ratio = is_ratio_scale(Quantity(1.0, self.unit).units)
            except ScientificCoreError:
                raise WorldRefused(f"cost unit {self.unit!r} is not a unit the unit owner knows") from None
            if not ratio:
                raise WorldRefused(f"cost unit {self.unit!r} is an offset scale: a cost amount's zero is never a "
                                   "convention (the unit owner's is_ratio_scale)")
        elif self.unit:
            raise WorldRefused(f"only a cost ledger states a declared unit; {self.dimension!r} amounts carry their own")

    @classmethod
    def ledger(cls, dimension: str, ledger_id: str, unit: str = "") -> "BudgetSource":
        return cls(dimension, "ledger", ledger_id, unit)

    @classmethod
    def experiment(cls, dimension: str, experiment_id: str) -> "BudgetSource":
        return cls(dimension, "experiment", experiment_id)

    @classmethod
    def unbounded(cls, dimension: str, basis: str) -> "BudgetSource":
        return cls(dimension, "unbounded", basis)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": BUDGET_SOURCE_SCHEMA, "dimension": self.dimension, "kind": self.kind, "ref": self.ref,
                **({"unit": self.unit} if self.unit else {})}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BudgetSource":
        expect_schema(payload.get("schema"), BUDGET_SOURCE_SCHEMA)
        return cls(payload["dimension"], payload["kind"], payload["ref"], payload.get("unit", ""))


def _unique(items: Any, kind: type, key: Any, what: str) -> tuple[Any, ...]:
    items = tuple(items)
    if any(type(i) is not kind for i in items):
        raise WorldRefused(f"{what} are exactly {kind.__name__} records")
    keys = [key(i) for i in items]
    if len(set(keys)) != len(keys):
        raise WorldRefused(f"{what} repeat an id")
    return tuple(sorted(items, key=key))


@dataclass(frozen=True)
class ProtocolDeclaration:
    declaration_id: str
    revision: int
    world_id: str
    declared_by: RoleSource
    basis: str
    variables: tuple[WorldVariable, ...]
    entities: tuple[Entity, ...] = ()
    constraints: tuple[DeclaredConstraint, ...] = ()
    actions: tuple[ActionSpec, ...] = ()
    channels: tuple[ObservationChannel, ...] = ()
    references: tuple[RecordRef, ...] = ()
    values: tuple[ValueSource, ...] = ()
    models: tuple[tuple[str, str], ...] = ()
    providers: tuple[str, ...] = ()
    budget: tuple[BudgetSource, ...] = ()
    description: str = ""                                                  # non-material

    def __post_init__(self) -> None:
        for name in ("declaration_id", "world_id", "basis"):
            if type(getattr(self, name)) is not str:
                raise WorldRefused(f"declaration {name} is exactly a str")
            text(getattr(self, name), f"declaration {name}")
        if type(self.revision) is not int or self.revision < 1:
            raise WorldRefused("a declaration revision is an int >= 1")
        object.__setattr__(self, "declared_by", declared_source(self.declared_by, f"declaration {self.declaration_id!r}"))
        variables = _unique(self.variables, WorldVariable, lambda v: v.name, "declared variables")
        try:
            RoleTable(tuple(v.declaration for v in variables))
        except RoleRefused as exc:
            raise WorldRefused(f"declaration role table: {exc}") from None
        for v in variables:
            if v.source is not None or (v.value is not None and v.origin is not ValueOrigin.DECLARED):
                raise WorldRefused(f"{v.name!r}: a declaration states only DECLARED values; any other current value "
                                   "is read from its owner through a ValueSource")
        object.__setattr__(self, "variables", variables)
        object.__setattr__(self, "entities", _unique(self.entities, Entity, lambda e: e.entity_id, "entities"))
        object.__setattr__(self, "constraints", _unique(self.constraints, DeclaredConstraint, lambda c: c.constraint_id,
                                                        "constraints"))
        object.__setattr__(self, "actions", _unique(self.actions, ActionSpec, lambda a: a.action_id, "actions"))
        object.__setattr__(self, "channels", _unique(self.channels, ObservationChannel, lambda c: c.variable,
                                                     "channels"))
        refs = tuple(self.references)
        if any(type(r) is not RecordRef for r in refs) or len(set(refs)) != len(refs):
            raise WorldRefused("declaration references are unique RecordRef records")
        object.__setattr__(self, "references", tuple(sorted(refs)))
        by_name = {v.name: v for v in variables}
        values = _unique(self.values, ValueSource, lambda s: s.variable, "value sources")
        for s in values:
            v = by_name.get(s.variable)
            if v is None:
                raise WorldRefused(f"value source {s.variable!r} names no declared variable")
            if v.value is not None:
                raise WorldRefused(f"{s.variable!r} has a DECLARED value and an owner source")
            if s.origin not in ORIGIN_BY_ROLE[v.role]:
                raise WorldRefused(f"{s.variable!r}: a {v.role.value} value cannot be {s.origin.value}")
        object.__setattr__(self, "values", values)
        models = tuple(tuple(m) for m in self.models)
        if any(len(m) != 2 or any(type(x) is not str or not x for x in m) for m in models) or \
                len(set(models)) != len(models):
            raise WorldRefused("declared models are distinct (model_id, version) pairs")
        object.__setattr__(self, "models", tuple(sorted(models)))
        providers = tuple(self.providers)
        if any(type(p) is not str or not p for p in providers) or len(set(providers)) != len(providers):
            raise WorldRefused("declared providers are distinct provider ids")
        object.__setattr__(self, "providers", tuple(sorted(providers)))
        object.__setattr__(self, "budget", _unique(self.budget, BudgetSource, lambda b: b.dimension, "budget sources"))
        accounts = [(b.kind, b.ref) for b in self.budget if b.kind != "unbounded"]
        if len(set(accounts)) != len(accounts):
            raise WorldRefused("one budget account states one dimension (its owner decides on one pool; two dimensions "
                               "drawn from it would each be checked against the whole of it)")
        if type(self.description) is not str:
            raise WorldRefused("description is text")

    # ---- identity ------------------------------------------------------------------------------------------------------
    def _material(self) -> dict[str, Any]:
        return {"schema": DECLARATION_SCHEMA, "declaration_id": self.declaration_id, "revision": self.revision,
                "world_id": self.world_id, "declared_by": self.declared_by.value, "basis": self.basis,
                "roles": RoleTable(tuple(v.declaration for v in self.variables)).to_dict(),
                "variables": [v.to_dict() for v in self.variables],
                "entities": [e.to_dict() for e in self.entities],
                "constraints": [c.to_dict() for c in self.constraints],
                "actions": [a.to_dict() for a in self.actions], "channels": [c.to_dict() for c in self.channels],
                "references": [r.to_dict() for r in self.references], "values": [s.to_dict() for s in self.values],
                "models": [list(m) for m in self.models], "providers": list(self.providers),
                "budget": [b.to_dict() for b in self.budget]}

    @property
    def digest(self) -> str:
        return digest(self._material())

    def to_dict(self) -> dict[str, Any]:
        return {**self._material(), "description": self.description}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProtocolDeclaration":
        expect_schema(payload.get("schema"), DECLARATION_SCHEMA)
        try:
            roles = RoleTable.from_dict(payload["roles"])
        except RoleRefused as exc:
            raise WorldRefused(f"declaration role table: {exc}") from None
        decls = {d.name: d for d in roles.declarations}
        variables = []
        for v in payload["variables"]:
            if v.get("name") not in decls:
                raise WorldRefused(f"declared variable {v.get('name')!r} has no role declaration")
            variables.append(WorldVariable.from_dict(v, decls[v["name"]]))
        if len(variables) != len(decls):
            raise WorldRefused("the role table declares variables the declaration does not carry")
        return cls(payload["declaration_id"], payload["revision"], payload["world_id"],
                   RoleSource(payload["declared_by"]), payload["basis"], tuple(variables),
                   tuple(Entity.from_dict(e) for e in payload["entities"]),
                   tuple(DeclaredConstraint.from_dict(c) for c in payload["constraints"]),
                   tuple(ActionSpec.from_dict(a) for a in payload["actions"]),
                   tuple(ObservationChannel.from_dict(c) for c in payload["channels"]),
                   tuple(RecordRef.from_dict(r) for r in payload["references"]),
                   tuple(ValueSource.from_dict(s) for s in payload["values"]),
                   tuple(tuple(m) for m in payload["models"]), tuple(payload["providers"]),
                   tuple(BudgetSource.from_dict(b) for b in payload["budget"]), payload.get("description", ""))


__all__ = ["BUDGET_DIMENSIONS", "BudgetSource", "ProtocolDeclaration", "ValueSource"]
