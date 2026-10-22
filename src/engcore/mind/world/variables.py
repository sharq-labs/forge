"""World variables: one declared role (Gen1 repsem), plus unit, domain, bound value, uncertainty and time semantics.

The role is the :class:`~engcore.mind.repsem.roles.RoleDeclaration` itself, reused unchanged: a role is a fact about
the experiment, declared by the problem specification or the protocol metadata and never inferred from a name.  What
this module adds is what a reasoning view needs around that declaration, each piece reused or justified:

* the unit, validated through the sealed unit registry (Gen1 leaves ``RoleDeclaration.unit`` unvalidated);
* an optional physical meaning (:class:`~engcore.scientific.semantics.QuantitySemantics`; ``None`` is undeclared);
* an optional admissible domain (a ``ScientificVariable`` or :class:`~.domains.DiscreteLevels`; ``None`` is UNKNOWN,
  never unbounded);
* an optional current value.  The world never produces a value: a value is either DECLARED by the problem or the
  protocol (with its basis), or a PROJECTION of the owner record it came from.  A projection carries an
  :class:`~.authority.AuthorityBinding` (owner, record identity, revision, the owner's own digest, and the digest of
  exactly the value and uncertainty projected), so the copy can never differ from its binding and a binding can be
  re-checked against its owner; a contract fixture may still cite a :class:`~.base.RecordRef`, which no owner can
  verify and which therefore never supports admission.  Its ``Uncertainty`` defaults to UNKNOWN and is never zero;
* a declared :class:`TemporalSemantics` tag, checked against the role.

Observability and controllability are derived views, never stored flags that could disagree with the role.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from engcore.mind.repsem.roles import RoleDeclaration, RoleSource, VariableRole
from engcore.scientific import Quantity, ScientificCoreError, ScientificVariable, Uncertainty
from engcore.scientific.results.uncertainty import UncertaintyKind
from engcore.scientific.semantics import QuantitySemantics

from .authority import BINDING_SCHEMA, AuthorityBinding, OwnerKind, projection_digest
from .base import (
    RecordKind, RecordRef, WorldRefused, converts, expect_schema, is_value, names, schema, text, unit, value_from,
    value_payload,
)
from .domains import DiscreteLevels, domain_from, domain_identity, domain_problem, membership

VARIABLE_SCHEMA = schema("variable")
ENTITY_SCHEMA = schema("entity")
CHANNEL_SCHEMA = schema("observation_channel")


class TemporalSemantics(str, Enum):
    """How a variable's value is indexed in time.  Declared per variable; checked against the role, never guessed."""

    TIME_INVARIANT = "time_invariant"        # one value for the system (a parameter)
    CONSTANT_PER_RUN = "constant_per_run"    # held for a whole run
    PER_SEGMENT = "per_segment"              # held per protocol segment
    TIME_SERIES = "time_series"              # recorded or imposed as a function of time
    STATE_EVOLVING = "state_evolving"        # evolves under declared dynamics (driven_by)


class ValueOrigin(str, Enum):
    """How a current value reached the world.  DECLARED cites its basis; every other origin cites its owner record.

    No existing vocabulary spans these: ``ParameterProvenance`` covers parameters, ``DatumOrigin`` material data."""

    DECLARED = "declared"      # stated by the problem specification or protocol metadata
    OBSERVED = "observed"      # read through an observation channel
    ESTIMATED = "estimated"    # inferred (fit, reconstruction, belief)
    COMPUTED = "computed"      # computed from declared sources (a derived quantity, a provider run)


class Observability(str, Enum):
    """Derived from the role and the declared observation channels; never a free flag."""

    OBSERVED_CHANNEL = "observed_channel"    # a declared channel records it
    NO_CHANNEL = "no_channel"                # observable in kind, but no declared channel records it here
    DERIVED_ONLY = "derived_only"            # computed from declared sources; never an independent observation
    NOT_OBSERVABLE = "not_observable"        # a latent parameter: estimated, never observed


class Controllability(str, Enum):
    """Derived from the role alone."""

    INTERVENABLE = "intervenable"                        # CONTROLLED_INPUT: set through a declared action control
    PROTOCOL_SELECTABLE = "protocol_selectable"          # FIXED_PROTOCOL_CONDITION: selected among protocol levels
    STATE_INTERVENTION_ONLY = "state_intervention_only"  # STATE_VARIABLE: only an explicit state-intervention action
    NOT_CONTROLLABLE = "not_controllable"                # measurement, derived, latent, nuisance


R = VariableRole
#: Which time indexing each role admits.  A state evolves; a latent parameter is a constant of the system (or of a run).
TEMPORAL_BY_ROLE: Mapping[VariableRole, frozenset[TemporalSemantics]] = {
    R.CONTROLLED_INPUT: frozenset({TemporalSemantics.CONSTANT_PER_RUN, TemporalSemantics.PER_SEGMENT,
                                   TemporalSemantics.TIME_SERIES}),
    R.FIXED_PROTOCOL_CONDITION: frozenset({TemporalSemantics.CONSTANT_PER_RUN, TemporalSemantics.PER_SEGMENT}),
    R.STATE_VARIABLE: frozenset({TemporalSemantics.STATE_EVOLVING}),
    R.MEASUREMENT: frozenset({TemporalSemantics.TIME_SERIES, TemporalSemantics.CONSTANT_PER_RUN,
                              TemporalSemantics.PER_SEGMENT}),
    R.DERIVED_QUANTITY: frozenset({TemporalSemantics.TIME_SERIES, TemporalSemantics.CONSTANT_PER_RUN,
                                   TemporalSemantics.PER_SEGMENT, TemporalSemantics.TIME_INVARIANT}),
    R.LATENT_PARAMETER: frozenset({TemporalSemantics.TIME_INVARIANT, TemporalSemantics.CONSTANT_PER_RUN}),
    R.NUISANCE_VARIABLE: frozenset({TemporalSemantics.TIME_SERIES, TemporalSemantics.CONSTANT_PER_RUN,
                                    TemporalSemantics.PER_SEGMENT}),
}

#: Which value origins each role admits.  A latent parameter is never observed; a derived quantity is only computed;
#: a measurement or a nuisance is only observed; a state is never merely declared (it comes from its owner record:
#: a system state, an observation, an estimate) -- the world must not become a second state authority.
ORIGIN_BY_ROLE: Mapping[VariableRole, frozenset[ValueOrigin]] = {
    R.CONTROLLED_INPUT: frozenset({ValueOrigin.DECLARED, ValueOrigin.OBSERVED}),
    R.FIXED_PROTOCOL_CONDITION: frozenset({ValueOrigin.DECLARED, ValueOrigin.OBSERVED}),
    R.STATE_VARIABLE: frozenset({ValueOrigin.OBSERVED, ValueOrigin.ESTIMATED, ValueOrigin.COMPUTED}),
    R.MEASUREMENT: frozenset({ValueOrigin.OBSERVED}),
    R.DERIVED_QUANTITY: frozenset({ValueOrigin.COMPUTED}),
    R.LATENT_PARAMETER: frozenset({ValueOrigin.DECLARED, ValueOrigin.ESTIMATED}),
    R.NUISANCE_VARIABLE: frozenset({ValueOrigin.OBSERVED}),
}

#: Which owner records may carry a value of each origin.  A synthetic fixture may stand in for any (never evidence).
RECORDS_BY_ORIGIN: Mapping[ValueOrigin, frozenset[RecordKind]] = {
    ValueOrigin.OBSERVED: frozenset({RecordKind.MEASUREMENT_OBSERVATION, RecordKind.DATASET_OBSERVATION,
                                     RecordKind.EVIDENCE_ITEM, RecordKind.SYSTEM_STATE, RecordKind.SYNTHETIC_FIXTURE}),
    ValueOrigin.ESTIMATED: frozenset({RecordKind.BELIEF_SNAPSHOT, RecordKind.TWIN_REVISION, RecordKind.SYSTEM_STATE,
                                      RecordKind.SYNTHETIC_FIXTURE}),
    ValueOrigin.COMPUTED: frozenset({RecordKind.PROVIDER_RECORD, RecordKind.SYSTEM_STATE,
                                     RecordKind.SYNTHETIC_FIXTURE}),
}

#: The one owner a projected current value is read from today: the governing run's committed head state.
OWNERS_BY_ORIGIN: Mapping[ValueOrigin, frozenset[OwnerKind]] = {
    ValueOrigin.OBSERVED: frozenset({OwnerKind.SYSTEM_STATE}),
    ValueOrigin.ESTIMATED: frozenset({OwnerKind.SYSTEM_STATE}),
    ValueOrigin.COMPUTED: frozenset({OwnerKind.SYSTEM_STATE}),
}
#: The fields a value projection carries.
VALUE_FIELDS = ("uncertainty", "value")


def value_projection(value: Any, uncertainty: Uncertainty) -> dict[str, Any]:
    """What a value binding projects: the value and its uncertainty, as their owner records serialize them."""
    return {"value": value_payload(value), "uncertainty": uncertainty.to_dict()}


CONTROLLABILITY_BY_ROLE: Mapping[VariableRole, Controllability] = {
    R.CONTROLLED_INPUT: Controllability.INTERVENABLE,
    R.FIXED_PROTOCOL_CONDITION: Controllability.PROTOCOL_SELECTABLE,
    R.STATE_VARIABLE: Controllability.STATE_INTERVENTION_ONLY,
    R.MEASUREMENT: Controllability.NOT_CONTROLLABLE,
    R.DERIVED_QUANTITY: Controllability.NOT_CONTROLLABLE,
    R.LATENT_PARAMETER: Controllability.NOT_CONTROLLABLE,
    R.NUISANCE_VARIABLE: Controllability.NOT_CONTROLLABLE,
}

#: Roles whose DECLARED value is exact by declaration: a set point the problem or protocol imposes.  Any other value,
#: even a declared one (a nominal latent parameter), is only as exact as its uncertainty says.
SET_BY_DECLARATION = frozenset({R.CONTROLLED_INPUT, R.FIXED_PROTOCOL_CONDITION})

#: Roles a declared observation channel may record.  Never a latent parameter (estimated) or a derived quantity
#: (computed: it is never independent evidence).
CHANNEL_ROLES = frozenset({R.CONTROLLED_INPUT, R.FIXED_PROTOCOL_CONDITION, R.STATE_VARIABLE, R.MEASUREMENT,
                           R.NUISANCE_VARIABLE})


def _source_identity(source: Any) -> Any:
    if source is None:
        return None
    if type(source) is AuthorityBinding:
        return {"schema": BINDING_SCHEMA, **source.identity()}     # bound_at is metadata, not identity
    return source.to_dict()


def _source_from(payload: Any) -> Any:
    if payload is None:
        return None
    if payload.get("schema") == BINDING_SCHEMA:
        return AuthorityBinding.from_dict(payload)
    return RecordRef.from_dict(payload)


@dataclass(frozen=True)
class WorldVariable:
    declaration: RoleDeclaration
    temporal: TemporalSemantics
    label: str = ""                                   # human name: non-material, never part of identity
    quantity: QuantitySemantics | None = None
    domain: ScientificVariable | DiscreteLevels | None = None
    value: Any = None
    origin: ValueOrigin | None = None
    source: RecordRef | AuthorityBinding | None = None  # the owner record a non-declared value is bound to
    value_basis: str = ""                             # the basis of a DECLARED value
    uncertainty: Uncertainty = field(default_factory=lambda: Uncertainty.unknown("not declared"))

    def __post_init__(self) -> None:
        if not isinstance(self.declaration, RoleDeclaration):
            raise WorldRefused("a world variable carries its role declaration (repsem RoleDeclaration)")
        d = self.declaration
        text(d.name, "variable name")
        if d.source is RoleSource.LEGACY_ADAPTER_DEFAULT:
            raise WorldRefused(f"{d.name!r}: the legacy adapter default is not a role declaration (roles are declared)")
        try:
            object.__setattr__(self, "temporal", TemporalSemantics(self.temporal))
        except ValueError:
            raise WorldRefused(f"{d.name!r}: temporal semantics must be declared, got {self.temporal!r}") from None
        if self.temporal not in TEMPORAL_BY_ROLE[d.role]:
            raise WorldRefused(f"{d.name!r}: a {d.role.value} cannot be {self.temporal.value}; allowed "
                               f"{sorted(t.value for t in TEMPORAL_BY_ROLE[d.role])}")
        u = unit(d.unit, f"{d.name!r} unit")
        if not isinstance(self.label, str):
            raise WorldRefused(f"{d.name!r}: label must be text")
        if self.quantity is not None:
            if not isinstance(self.quantity, QuantitySemantics):
                raise WorldRefused(f"{d.name!r}: quantity must be a QuantitySemantics declaration or None")
            if not converts(Quantity(1.0, self.quantity.unit), u):
                raise WorldRefused(f"{d.name!r}: declared quantity {self.quantity.meaning_id!r} is in "
                                   f"{self.quantity.unit!r}, not compatible with {u!r}")
        if self.domain is not None:
            problem = domain_problem(self.domain, d.name, u)
            if problem:
                raise WorldRefused(f"{d.name!r}: {problem}")
        self._check_value(d, u)
        self._check_uncertainty(d, u)
        if type(self.source) is AuthorityBinding and \
                projection_digest(value_projection(self.value, self.uncertainty)) != self.source.projection:
            raise WorldRefused(f"{d.name!r}: the value and uncertainty differ from what their authority binding "
                               "projected; a projected value changes only with a new owner record and binding")

    def _check_value(self, d: RoleDeclaration, u: str) -> None:
        if self.value is None:
            if self.origin is not None or self.source is not None or self.value_basis:
                raise WorldRefused(f"{d.name!r}: an origin, source or basis without a value")
            return
        if not is_value(self.value):
            raise WorldRefused(f"{d.name!r}: a value is a typed scientific value, not {type(self.value).__name__}")
        if isinstance(self.value, Quantity) and not converts(self.value, u):
            raise WorldRefused(f"{d.name!r}: the unit owner does not convert value {self.value} into {u!r}")
        try:
            object.__setattr__(self, "origin", ValueOrigin(self.origin))
        except ValueError:
            raise WorldRefused(f"{d.name!r}: a value states its origin") from None
        if self.origin not in ORIGIN_BY_ROLE[d.role]:
            raise WorldRefused(f"{d.name!r}: a {d.role.value} value cannot be {self.origin.value}; allowed "
                               f"{sorted(o.value for o in ORIGIN_BY_ROLE[d.role])}")
        if self.origin is ValueOrigin.DECLARED:
            if self.source is not None:
                raise WorldRefused(f"{d.name!r}: a DECLARED value cites its basis, not an owner record")
            text(self.value_basis, f"{d.name!r} declared value basis")
            if self.domain is not None:
                found = membership(self.domain, self.value)
                if found is not None:
                    raise WorldRefused(f"{d.name!r}: declared value is outside its own declared domain: {found[1]}")
        else:
            if type(self.source) is AuthorityBinding:
                if self.source.owner_kind not in OWNERS_BY_ORIGIN[self.origin]:
                    raise WorldRefused(f"{d.name!r}: a {self.source.owner_kind.value} owner cannot carry an "
                                       f"{self.origin.value} value")
                if self.source.fields != VALUE_FIELDS:
                    raise WorldRefused(f"{d.name!r}: a value binding projects exactly {VALUE_FIELDS}")
            elif type(self.source) is RecordRef:
                if self.source.kind not in RECORDS_BY_ORIGIN[self.origin]:
                    raise WorldRefused(f"{d.name!r}: a {self.source.kind.value} record cannot carry an "
                                       f"{self.origin.value} value")
            else:
                raise WorldRefused(f"{d.name!r}: an {self.origin.value} value is bound to the owner record it came "
                                   "from (an AuthorityBinding, or a RecordRef no owner verifies)")
            if self.value_basis:
                raise WorldRefused(f"{d.name!r}: a bound value's basis is its record, not free text")

    def _check_uncertainty(self, d: RoleDeclaration, u: str) -> None:
        if not isinstance(self.uncertainty, Uncertainty):
            raise WorldRefused(f"{d.name!r}: uncertainty must be an Uncertainty record (UNKNOWN by default)")
        if not self.uncertainty.is_quantified:
            return
        if not isinstance(self.value, Quantity):
            raise WorldRefused(f"{d.name!r}: a quantified uncertainty needs a quantity value; an absent or "
                               "non-quantity value has UNKNOWN uncertainty")
        try:
            spread = self.uncertainty.standard_uncertainty            # a spread: a difference, never a point
            if spread is not None and not spread.is_compatible_with(u):
                raise WorldRefused(f"{d.name!r}: uncertainty {spread} is not compatible with {u!r}")
            for edge in (self.uncertainty.lower, self.uncertainty.upper):   # interval edges are points of the value
                if edge is not None and not converts(edge, u):
                    raise WorldRefused(f"{d.name!r}: the unit owner does not convert interval edge {edge} into {u!r}")
        except ScientificCoreError as exc:
            raise WorldRefused(f"{d.name!r}: {exc}") from None
        if self.uncertainty.kind is UncertaintyKind.INTERVAL:
            lo, x, hi = (q.magnitude_in(u) for q in (self.uncertainty.lower, self.value, self.uncertainty.upper))
            if not lo <= x <= hi:
                raise WorldRefused(f"{d.name!r}: the uncertainty interval does not contain its value")

    # ---- views ------------------------------------------------------------------------------------------------------
    @property
    def name(self) -> str:
        return self.declaration.name

    @property
    def role(self) -> VariableRole:
        return self.declaration.role

    @property
    def unit(self) -> str:
        return unit(self.declaration.unit, f"{self.name!r} unit")

    @property
    def controllability(self) -> Controllability:
        return CONTROLLABILITY_BY_ROLE[self.role]

    def edges(self) -> tuple[Any, ...] | None:
        """The values a check must hold at for this current value, or None when that cannot be decided.

        A DECLARED set point (a controlled input or protocol condition) is exact by declaration.  Every other value is
        exact only within its uncertainty: an INTERVAL gives its two edges; an UNKNOWN or a STANDARD uncertainty (no
        coverage is assumed) gives None, so missing uncertainty never becomes zero."""
        if self.value is None:
            return None
        if self.origin is ValueOrigin.DECLARED and self.role in SET_BY_DECLARATION:
            return (self.value,)
        if self.uncertainty.kind is UncertaintyKind.INTERVAL:
            return (self.uncertainty.lower, self.uncertainty.upper)
        return None

    # ---- serialization ------------------------------------------------------------------------------------------------
    def identity(self) -> dict[str, Any]:
        """Identity payload: everything but the human label, as the raw owner payloads (a value in another
        spelling is another identity: identity must distinguish whatever a check or an execution can see)."""
        return {"name": self.name, "unit": self.unit, "temporal": self.temporal.value,
                "quantity": None if self.quantity is None else self.quantity.to_dict(),
                "domain": None if self.domain is None else domain_identity(self.domain),
                "value": None if self.value is None else value_payload(self.value),
                "origin": None if self.origin is None else self.origin.value,
                "source": _source_identity(self.source), "value_basis": self.value_basis,
                "uncertainty": self.uncertainty.to_dict()}

    def to_dict(self) -> dict[str, Any]:
        """The variable's own fields; its role declaration travels in the world's role table (see ScientificWorld)."""
        return {"schema": VARIABLE_SCHEMA, "name": self.name, "label": self.label, "temporal": self.temporal.value,
                "quantity": None if self.quantity is None else self.quantity.to_dict(),
                "domain": None if self.domain is None else self.domain.to_dict(),
                "value": None if self.value is None else value_payload(self.value),
                "origin": None if self.origin is None else self.origin.value,
                "source": None if self.source is None else self.source.to_dict(), "value_basis": self.value_basis,
                "uncertainty": self.uncertainty.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], declaration: RoleDeclaration) -> "WorldVariable":
        expect_schema(payload.get("schema"), VARIABLE_SCHEMA)
        if payload.get("name") != declaration.name:
            raise WorldRefused(f"variable {payload.get('name')!r} does not match its role declaration")
        return cls(declaration, payload["temporal"], payload.get("label", ""),
                   None if payload.get("quantity") is None else QuantitySemantics.from_dict(payload["quantity"]),
                   None if payload.get("domain") is None else domain_from(payload["domain"]),
                   None if payload.get("value") is None else value_from(payload["value"]),
                   None if payload.get("origin") is None else ValueOrigin(payload["origin"]),
                   _source_from(payload.get("source")), payload.get("value_basis", ""),
                   Uncertainty.from_dict(payload["uncertainty"]))


@dataclass(frozen=True)
class ObservationChannel:
    """A declared way the world records a variable: the variable (its unit is the variable's) and the instrument,
    dataset column or other record that provides it."""

    variable: str
    reference: RecordRef

    def __post_init__(self) -> None:
        text(self.variable, "channel variable")
        if not isinstance(self.reference, RecordRef):
            raise WorldRefused(f"channel {self.variable!r} cites its instrument or data record (RecordRef)")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CHANNEL_SCHEMA, "variable": self.variable, "reference": self.reference.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ObservationChannel":
        expect_schema(payload.get("schema"), CHANNEL_SCHEMA)
        return cls(payload["variable"], RecordRef.from_dict(payload["reference"]))


@dataclass(frozen=True)
class Entity:
    """A declared system part grouping variables: a bare declared id, or a pointer to a system-definition record."""

    entity_id: str
    variables: tuple[str, ...]
    reference: RecordRef | None = None

    def __post_init__(self) -> None:
        text(self.entity_id, "entity_id")
        object.__setattr__(self, "variables", names(self.variables, f"entity {self.entity_id!r} variables"))
        if not self.variables:
            raise WorldRefused(f"entity {self.entity_id!r} groups no variable")
        if self.reference is not None and not isinstance(self.reference, RecordRef):
            raise WorldRefused(f"entity {self.entity_id!r}: reference is a RecordRef or None")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ENTITY_SCHEMA, "entity_id": self.entity_id, "variables": list(self.variables),
                "reference": None if self.reference is None else self.reference.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Entity":
        expect_schema(payload.get("schema"), ENTITY_SCHEMA)
        return cls(payload["entity_id"], tuple(payload["variables"]),
                   None if payload.get("reference") is None else RecordRef.from_dict(payload["reference"]))


__all__ = [
    "OWNERS_BY_ORIGIN", "VALUE_FIELDS", "value_projection", "CHANNEL_ROLES", "CONTROLLABILITY_BY_ROLE", "Controllability", "Entity", "ORIGIN_BY_ROLE", "Observability",
    "ObservationChannel", "RECORDS_BY_ORIGIN", "SET_BY_DECLARATION", "TEMPORAL_BY_ROLE", "TemporalSemantics", "ValueOrigin", "WorldVariable",
]
