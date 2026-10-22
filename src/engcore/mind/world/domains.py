"""Allowed-value domains, guards and declared constraints, and the one membership rule they share.

Continuous, integer, categorical and boolean domains ARE ``ScientificVariable`` records (kind, unit, bounds,
categories), reused unchanged.  The one missing form is :class:`DiscreteLevels`: a finite set of unit-bearing levels
such as the current levels a protocol offers.  ``VariableKind`` is frozen, so it is not extended; the new form lives
here.

Membership is decided per kind.  A range (continuous, or integer wrapped as a quantity as ``DesignSpace`` does) is
decided by its owner, ``ScientificVariable.require_within_bounds``: inclusive, unit-converted, never clamped.  The kind
rules the owner leaves to its consumers (an integer is an ``IntegerValue``, a category is one of the declared
categories, a boolean has no bounds; ``tests/test_core_semantic_invariants.py`` records that a second consumer
inherits no refusal) are applied here, with the design layer's dimensionless test (``dimensionality``).  An integer,
categorical or boolean domain is stated in its variable's own unit, so an integer means the same count to the check
and to whoever executes it.  Only :class:`DiscreteLevels`, which has no owner, compares at comparison precision in the
base unit (see :mod:`.base`), so a spelling of a level matches that level.  Compatibility is always the unit owner's
conversion (:func:`.base.converts`), never a shared dimension: a temperature difference is not a temperature.

Identity is the raw owner payload (``to_dict``): two domains that any check could tell apart are two identities.
Nothing is ever clamped, rounded to a level or projected: a value is a member or it is refused with the reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from engcore.design.grammar import ConstraintStatus
from engcore.mind.repsem.roles import RoleSource
from engcore.scientific import (
    ConstraintDefinition, ConstraintOperator, Quantity, ScientificCoreError, ScientificVariable, VariableKind,
    dimensionality,
)
from engcore.scientific.ir.values import BooleanValue, CategoricalValue, IntegerValue

from .base import (
    WorldRefused, converts, expect_schema, magnitude_key, names, require_value, same_value, schema, text, unit,
    value_from, value_key, value_payload,
)

LEVELS_SCHEMA = schema("discrete_levels")
GUARD_SCHEMA = schema("guard")
CONSTRAINT_SCHEMA = schema("declared_constraint")
DIMENSIONLESS = dimensionality("dimensionless")
#: ``DeclaredConstraint.applies_to`` entry meaning every action of the world.
ALL_ACTIONS = "*"


@dataclass(frozen=True)
class DiscreteLevels:
    """A finite set of unit-bearing levels.  Order is the declared order; identity ignores it."""

    unit: str
    levels: tuple[Quantity, ...]

    def __post_init__(self) -> None:
        u = unit(self.unit, "discrete levels unit")
        object.__setattr__(self, "unit", u)
        levels = tuple(self.levels)
        if not levels:
            raise WorldRefused("a discrete domain declares at least one level")
        for level in levels:
            if not converts(level, u):
                raise WorldRefused(f"level {level!r} is not a quantity the unit owner converts into {u!r}")
        keys = [magnitude_key(level) for level in levels]
        if len(set(keys)) != len(keys):
            raise WorldRefused(f"discrete levels repeat a value: {keys}")
        object.__setattr__(self, "levels", levels)

    def keys(self) -> tuple[float, ...]:
        return tuple(sorted(magnitude_key(level) for level in self.levels))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": LEVELS_SCHEMA, "unit": self.unit, "levels": [level.to_dict() for level in self.levels]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DiscreteLevels":
        expect_schema(payload.get("schema"), LEVELS_SCHEMA)
        return cls(payload["unit"], tuple(Quantity.from_dict(x) for x in payload["levels"]))


Domain = ScientificVariable | DiscreteLevels


def domain_kind(domain: Domain) -> str:
    """A report label: 'discrete' for levels, else the frozen ``VariableKind`` value.  Not a new vocabulary."""
    return "discrete" if isinstance(domain, DiscreteLevels) else domain.kind.value


def is_finite(domain: Domain) -> bool:
    return isinstance(domain, DiscreteLevels) or domain.kind in (
        VariableKind.CATEGORICAL, VariableKind.BOOLEAN, VariableKind.INTEGER)


def domain_problem(domain: Any, name: str, declared_unit: str) -> str | None:
    """Why ``domain`` cannot serve variable ``name`` declared in ``declared_unit``, or None.

    Applies the design-layer searchability rules (a range states both bounds; an integer range is dimensionless with
    integer-valued bounds; a category or a boolean is dimensionless and unbounded).  A range or level set must be
    convertible into the variable's unit by the unit owner; an integer, categorical or boolean domain is stated in
    exactly the variable's unit (a count in percent and the same count in dimensionless are different numbers)."""
    if isinstance(domain, DiscreteLevels):
        if not converts(Quantity(1.0, domain.unit), declared_unit):
            return f"discrete levels in {domain.unit!r} do not convert into the variable unit {declared_unit!r}"
        return None
    if not isinstance(domain, ScientificVariable):
        return f"a domain is a ScientificVariable or DiscreteLevels, not {type(domain).__name__}"
    if domain.name != name:
        return f"the domain is declared for {domain.name!r}, not {name!r}"
    if not converts(Quantity(1.0, domain.unit), declared_unit):
        return f"domain unit {domain.unit!r} does not convert into the variable unit {declared_unit!r}"
    kind = domain.kind
    if kind is not VariableKind.CONTINUOUS and unit(domain.unit, "domain unit") != unit(declared_unit, "variable unit"):
        return (f"a {kind.value} domain is stated in its variable's own unit {declared_unit!r}, not {domain.unit!r} "
                "(its values are not converted)")
    if kind in (VariableKind.CATEGORICAL, VariableKind.BOOLEAN):
        if dimensionality(domain.unit) != DIMENSIONLESS or domain.lower is not None or domain.upper is not None:
            return f"a {kind.value} domain is dimensionless and unbounded"
        return None
    if domain.lower is None or domain.upper is None:
        return f"a {kind.value} domain states both bounds (an unbounded range is not a declared domain)"
    if kind is VariableKind.INTEGER:
        if dimensionality(domain.unit) != DIMENSIONLESS:
            return "an integer domain is dimensionless (a count)"
        if not (float(domain.lower.magnitude).is_integer() and float(domain.upper.magnitude).is_integer()):
            return f"an integer domain has integer-valued bounds, not [{domain.lower.magnitude}, {domain.upper.magnitude}]"
    return None


def _shown(value: Any) -> Any:
    return value_payload(value) if type(value) in (Quantity, IntegerValue, BooleanValue, CategoricalValue) else repr(value)


def membership(domain: Domain, value: Any) -> tuple[str, str, dict[str, Any]] | None:
    """None when ``value`` is a member; otherwise (code, message, detail).  Never clamps, never rounds to a level."""
    shown = _shown(value)
    if isinstance(domain, DiscreteLevels):
        if not isinstance(value, Quantity):
            return "VALUE_KIND_MISMATCH", f"expected a quantity in {domain.unit!r}", {"proposed": shown}
        if not converts(value, domain.unit):
            return ("UNIT_INCOMPATIBLE", f"the unit owner does not convert {value} into {domain.unit!r}",
                    {"proposed": shown, "expected_unit": domain.unit})
        key = magnitude_key(value)
        if key in domain.keys():
            return None
        return ("LEVEL_NOT_DECLARED", f"{value} is not one of the declared levels",
                {"proposed": shown, "declared_levels": [lv.to_dict() for lv in domain.levels]})
    kind = domain.kind
    if kind is VariableKind.CONTINUOUS:
        if not isinstance(value, Quantity):
            return "VALUE_KIND_MISMATCH", f"expected a quantity in {domain.unit!r}", {"proposed": shown}
        if not converts(value, domain.unit):
            return ("UNIT_INCOMPATIBLE", f"the unit owner does not convert {value} into {domain.unit!r}",
                    {"proposed": shown, "expected_unit": domain.unit})
        return _owner_bounds(domain, value, shown)
    if kind is VariableKind.INTEGER:
        if type(value) is not IntegerValue:
            return "VALUE_KIND_MISMATCH", "expected an IntegerValue", {"proposed": shown}
        try:
            wrapped = Quantity(value.value, domain.unit)   # as DesignSpace wraps an integer, in the variable's unit
        except (OverflowError, ScientificCoreError) as exc:
            return "OUTSIDE_RANGE", f"{value.value} is not representable as a magnitude: {exc}", {"proposed": shown}
        return _owner_bounds(domain, wrapped, shown)
    if kind is VariableKind.CATEGORICAL:
        if type(value) is not CategoricalValue:
            return "VALUE_KIND_MISMATCH", "expected a CategoricalValue", {"proposed": shown}
        if value.value in domain.categories:
            return None
        return ("CATEGORY_NOT_DECLARED", f"{value.value!r} is not a declared category",
                {"proposed": shown, "declared_categories": list(domain.categories)})
    if kind is VariableKind.BOOLEAN:
        if type(value) is not BooleanValue:
            return "VALUE_KIND_MISMATCH", "expected a BooleanValue", {"proposed": shown}
        return None
    return "VALUE_KIND_MISMATCH", f"unsupported domain kind {kind!r}", {"proposed": shown}


def _owner_bounds(domain: ScientificVariable, value: Quantity, shown: Any) -> tuple[str, str, dict[str, Any]] | None:
    """The owner's inclusive bound rule, ``ScientificVariable.require_within_bounds`` (rejects, never clamps)."""
    try:
        domain.require_within_bounds(value)
    except ScientificCoreError as exc:
        return ("OUTSIDE_RANGE", str(exc),
                {"proposed": shown, "lower": domain.lower.to_dict(), "upper": domain.upper.to_dict()})
    return None


def contained(inner: Domain, outer: Domain) -> bool:
    """Whether every member of ``inner`` is a member of ``outer``: an action may restrict a variable, never widen it."""
    if isinstance(inner, DiscreteLevels):
        return all(membership(outer, level) is None for level in inner.levels)
    if isinstance(outer, DiscreteLevels) or inner.kind is not outer.kind:
        return False
    if inner.kind is not VariableKind.CONTINUOUS and unit(inner.unit, "inner unit") != unit(outer.unit, "outer unit"):
        return False                               # an integer is never reinterpreted across units
    if inner.kind is VariableKind.CONTINUOUS:
        return membership(outer, inner.lower) is None and membership(outer, inner.upper) is None
    if inner.kind is VariableKind.INTEGER:
        return (membership(outer, IntegerValue(int(inner.lower.magnitude))) is None
                and membership(outer, IntegerValue(int(inner.upper.magnitude))) is None)
    if inner.kind is VariableKind.CATEGORICAL:
        return set(inner.categories) <= set(outer.categories)
    return True


def finite_members(domain: Domain, limit: int = 1000) -> tuple[Any, ...]:
    """Members of a finite domain in declared order (levels, categories, booleans, integers up to ``limit``)."""
    if isinstance(domain, DiscreteLevels):
        return tuple(domain.levels)
    if domain.kind is VariableKind.CATEGORICAL:
        return tuple(CategoricalValue(c) for c in domain.categories)
    if domain.kind is VariableKind.BOOLEAN:
        return (BooleanValue(False), BooleanValue(True))
    if domain.kind is VariableKind.INTEGER:
        lo, hi = int(domain.lower.magnitude), int(domain.upper.magnitude)
        if hi - lo + 1 > limit:
            raise WorldRefused(f"an integer domain of {hi - lo + 1} values exceeds the enumeration limit {limit}")
        return tuple(IntegerValue(i) for i in range(lo, hi + 1))
    raise WorldRefused("a continuous domain is not enumerable; it is checked, never sampled or projected here")


def domain_identity(domain: Domain) -> dict[str, Any]:
    """Identity payload of a domain: the owner record's own payload, raw (declared unit, raw magnitudes, declared
    order).  The owner decides membership on raw values, so identity must distinguish whatever it can."""
    return domain.to_dict()


def edges_in_domain(domain: Domain, edges: tuple[Any, ...]) -> str:
    """'inside', 'outside' or 'undecided' for a value known only by its edges (one edge: an exact value).

    Sound for every domain kind: a range is decided side by side (an interval wholly beyond one bound is outside;
    edges on both sides, or one inside, are undecided); a finite domain is never shown to contain a value known only
    as an interval, because points between its members are not members."""
    verdicts = [membership(domain, e) is None for e in edges]
    if len(edges) == 1:
        return "inside" if verdicts[0] else "outside"
    if isinstance(domain, ScientificVariable) and domain.kind is VariableKind.CONTINUOUS:
        if all(verdicts):
            return "inside"                                 # an interval of a convex set lies in it
        if any(verdicts) or not all(converts(e, domain.unit) for e in edges):
            return "undecided"
        below = [e.magnitude_in(domain.unit) < domain.lower.magnitude_in(domain.unit) for e in edges]
        return "outside" if all(below) or not any(below) else "undecided"
    return "undecided"


def domain_payload(domain: Domain) -> dict[str, Any]:
    return domain.to_dict()


def domain_from(payload: Mapping[str, Any]) -> Domain:
    if payload.get("schema") == LEVELS_SCHEMA:
        return DiscreteLevels.from_dict(payload)
    return ScientificVariable.from_dict(payload)


# ---- guards and declared constraints ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Guard:
    """``variable`` takes one of ``values``: the trigger of a conditional constraint or a conditional control.

    Guard values are categorical, boolean or integer.  A numeric threshold is a ``ConstraintDefinition`` (a constraint
    or a precondition), never a guard: set membership over a measured quantity would hide its uncertainty."""

    variable: str
    values: tuple[Any, ...]

    def __post_init__(self) -> None:
        text(self.variable, "guard variable")
        values = tuple(require_value(v, f"guard {self.variable!r} value") for v in self.values)
        if not values:
            raise WorldRefused(f"guard on {self.variable!r} names no value")
        if any(isinstance(v, Quantity) for v in values):
            raise WorldRefused(f"guard on {self.variable!r}: a guard is categorical, boolean or integer, never a quantity")
        if len({repr(value_key(v)) for v in values}) != len(values):
            raise WorldRefused(f"guard on {self.variable!r} repeats a value")
        object.__setattr__(self, "values", values)

    def holds(self, value: Any) -> bool:
        return any(same_value(value, v) for v in self.values)

    def identity(self) -> dict[str, Any]:
        return {"variable": self.variable, "values": sorted((value_key(v) for v in self.values), key=repr)}

    def to_dict(self) -> dict[str, Any]:
        return {"schema": GUARD_SCHEMA, "variable": self.variable, "values": [value_payload(v) for v in self.values]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Guard":
        expect_schema(payload.get("schema"), GUARD_SCHEMA)
        return cls(payload["variable"], tuple(value_from(v) for v in payload["values"]))


def declared_source(value: Any, where: str) -> RoleSource:
    """Who declared a limit: the problem specification or the protocol metadata (the repsem ``RoleSource`` values).

    The legacy adapter default is a reproduction aid for Gen1 ablations, never a declaration."""
    try:
        source = RoleSource(value)
    except ValueError:
        raise WorldRefused(f"{where}: declared_by must be problem_specification or protocol_metadata") from None
    if source is RoleSource.LEGACY_ADAPTER_DEFAULT:
        raise WorldRefused(f"{where}: the legacy adapter default is not a declaration")
    return source


@dataclass(frozen=True)
class DeclaredConstraint:
    """A typed constraint (reused ``ConstraintDefinition``) that applies, when its guard holds, to the actions it names.

    Scope is DECLARED (``applies_to``: action ids, or ``"*"`` for every action), never inferred from the variables an
    action happens to set.  ``declared_by`` names the authority that imposed it; a violation is reported under it
    (INFEASIBLE_PROTOCOL for protocol metadata, INFEASIBLE_DOMAIN for the problem specification)."""

    constraint_id: str
    consequence: ConstraintDefinition
    guard: Guard | None
    applies_to: tuple[str, ...]
    declared_by: RoleSource
    basis: str

    def __post_init__(self) -> None:
        text(self.constraint_id, "constraint_id")
        if not isinstance(self.consequence, ConstraintDefinition):
            raise WorldRefused(f"constraint {self.constraint_id!r}: the consequence is a ConstraintDefinition")
        if self.guard is not None and not isinstance(self.guard, Guard):
            raise WorldRefused(f"constraint {self.constraint_id!r}: the guard is a Guard or None")
        scope = names(self.applies_to, f"constraint {self.constraint_id!r} applies_to")
        if not scope or (ALL_ACTIONS in scope and len(scope) > 1):
            raise WorldRefused(f"constraint {self.constraint_id!r}: applies_to names its actions, or is exactly ('*',)")
        object.__setattr__(self, "applies_to", scope)
        object.__setattr__(self, "declared_by", declared_source(self.declared_by, f"constraint {self.constraint_id!r}"))
        text(self.basis, f"constraint {self.constraint_id!r} basis")

    def applies(self, action_id: str) -> bool:
        return self.applies_to == (ALL_ACTIONS,) or action_id in self.applies_to

    @property
    def reads(self) -> tuple[str, ...]:
        return tuple(sorted({self.consequence.metric} | ({self.guard.variable} if self.guard else set())))

    def identity(self) -> dict[str, Any]:
        return {"constraint_id": self.constraint_id, "consequence": self.consequence.to_dict(),
                "guard": None if self.guard is None else self.guard.identity(), "applies_to": list(self.applies_to),
                "declared_by": self.declared_by.value, "basis": self.basis}

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CONSTRAINT_SCHEMA, "constraint_id": self.constraint_id,
                "consequence": self.consequence.to_dict(), "guard": None if self.guard is None else self.guard.to_dict(),
                "applies_to": list(self.applies_to), "declared_by": self.declared_by.value, "basis": self.basis}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DeclaredConstraint":
        expect_schema(payload.get("schema"), CONSTRAINT_SCHEMA)
        return cls(payload["constraint_id"], ConstraintDefinition.from_dict(payload["consequence"]),
                   None if payload.get("guard") is None else Guard.from_dict(payload["guard"]),
                   tuple(payload["applies_to"]), RoleSource(payload["declared_by"]), payload["basis"])


def check_at_edges(constraint: ConstraintDefinition, edges: tuple[Quantity, ...]) -> tuple[ConstraintStatus, dict[str, Any]]:
    """Evaluate a constraint at every edge of a value, in the design layer's three-valued vocabulary.

    SATISFIED only if every edge satisfies it; VIOLATED only if every edge violates it on the same side (for a one-sided
    operator every violation is on its one side; an EQUAL band can be missed above and below while an interior point
    meets it); otherwise UNKNOWN, with ``why`` 'undecided' (the edges disagree) or 'unresolvable' (a dimension or
    conversion error).  An exact value has one edge.  Uncertainty can only make an answer less decided, never more."""
    results = []
    try:
        for edge in edges:
            results.append(constraint.check(edge))
        sides = {edge.to(constraint.bound.units).magnitude > constraint.bound.magnitude for edge in edges}
    except ScientificCoreError as exc:
        return ConstraintStatus.UNKNOWN, {"why": "unresolvable", "error": str(exc)}
    detail: dict[str, Any] = {"checks": [r.to_dict() for r in results]}
    if all(r.satisfied for r in results):
        return ConstraintStatus.SATISFIED, detail
    if not any(r.satisfied for r in results) and (constraint.operator is not ConstraintOperator.EQUAL or len(sides) == 1):
        return ConstraintStatus.VIOLATED, detail
    return ConstraintStatus.UNKNOWN, {**detail, "why": "undecided"}


__all__ = [
    "ALL_ACTIONS", "DeclaredConstraint", "DiscreteLevels", "Domain", "Guard", "check_at_edges", "contained",
    "declared_source", "domain_identity", "domain_kind", "domain_problem", "edges_in_domain", "finite_members",
    "is_finite", "membership",
]
