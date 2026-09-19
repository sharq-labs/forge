"""CORE-3 -- what a registered capability can answer, declared rather than inferred.

The public execution surface was a list of systems (``engcore.mcp.systems``):
a caller had to know that "electrothermal" is the thing that reports a body's
final temperature. Routing a *claim* needs the inverse question -- *which
registered capability produces this quantity, in this dimension, exercising
these declared scientific capabilities?* -- and it must be answered from
declarations, never from words in a prompt.

A :class:`CapabilityDeclaration` is that declaration. It states:

* the :class:`~engcore.scientific.capabilities.ScientificCapability` identifiers
  it provides, each with the record that makes it true (a realization that
  declares it, or a stated basis);
* every input it accepts -- path, kind, dimension, required or not, the model
  input it feeds, the validity conditions it unlocks and its role (parameter,
  initial or boundary condition, operating condition, applicability evidence,
  numerics, identity);
* every quantity it produces, with its dimension and, for a quantity reported
  once per element, the qualifier that selects the element;
* the registered models it runs (id, version, assumptions, exclusions, the
  names of their validity conditions) and when each is active;
* the solvers, the claim shapes it can decide, the evidentiary levels it can
  attain and through which check, the uncertainty it quantifies, and its
  execution routes.

What a declaration does NOT do
------------------------------
It does not choose, rank or execute anything. Selection is
:mod:`engcore.claims.selection`; execution is the plan's job. A declaration
also never *raises* a level: ``attainable_levels`` is an upper bound the
compiler may use to predict a gap, and the report the run actually produces is
the only thing that attains one.

Facts are derived where a record exists to derive them from (the production
declarations read ``CaseDescription`` and the model registries), and the tests
pin every hand-written fact against a real run, so a declaration that drifts
from its system fails rather than routing a claim to a capability that no
longer does what it says.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

from ..scientific.capabilities import ScientificCapability
from ..scientific.errors import ScientificCoreError
from ..scientific.results.immutable import freeze
from ..scientific.results.validation import ValidationLevel
from ..scientific.serialization import require_schema_any, schema_string
from ..scientific.units.quantity import dimensionality, is_delta_unit, normalize_unit
from ..sria.uncertainty import UncertaintyChannel
from ..scientific.units.quantity import Quantity
from ._records import (
    quantity_text,
    require_bool,
    require_identifier,
    require_keys,
    require_list,
    require_mapping,
    require_path,
    require_schema_exact,
    require_text,
    tagged_digest,
)
from .contract import ClaimKind
from .errors import CapabilityDeclarationError, CapabilityInputError, CapabilityRegistryError

CAPABILITY_SCHEMA = schema_string("capability_declaration")
INPUT_SCHEMA = schema_string("capability_input")
PRODUCED_SCHEMA = schema_string("capability_produced_quantity")
MODEL_USE_SCHEMA = schema_string("capability_model_use")
SOLVER_USE_SCHEMA = schema_string("capability_solver_use")
PROVIDED_SCHEMA = schema_string("capability_provided")
LEVEL_SCHEMA = schema_string("capability_attainable_level")
LEVEL_SCHEMA_SCOPED = schema_string("capability_attainable_level", 2)
ROUTE_SCHEMA = schema_string("capability_route")
UNCERTAINTY_SCHEMA = schema_string("capability_uncertainty")
UNASSESSABLE_SCHEMA = schema_string("capability_unassessable_condition")
REFINEMENT_SCHEMA = schema_string("capability_refinement_study")
PERTURBABLE_SCHEMA = schema_string("capability_perturbable_input")
REGISTRY_SCHEMA = schema_string("capability_registry")

_DECLARATION_TAG = "crafty.claims.capability/1"
_REGISTRY_TAG = "crafty.claims.capability_registry/1"

#: Dotted lowercase identifier: ``system.electrothermal``.
_DOTTED = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


def _err(message: str) -> CapabilityDeclarationError:
    return CapabilityDeclarationError(message)


def _text(value: Any, name: str) -> str:
    return require_text(value, field=name, error=CapabilityDeclarationError)


def _dotted(value: Any, name: str) -> str:
    text = _text(value, name)
    if not _DOTTED.match(text):
        raise _err(f"{name} {text!r} must be dotted lowercase identifiers")
    return text


def _texts(values: Iterable[Any], name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise _err(f"{name} must be a collection of strings, not one string")
    return tuple(_text(item, f"{name} item") for item in values)


def declared_path(path: str) -> str:
    """``stages[3].body.duration`` -> ``stages[].body.duration``: the declared form of a claim path."""
    return re.sub(r"\[\d+\]", "[]", path)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class InputKind(str, Enum):
    """How an input is written. Mirrors the MCP payload readers' closed set, plus FLAG."""

    QUANTITY = "quantity"
    #: A bare dimensionless policy number (a derating share). A claim states it
    #: as ``Quantity(x, "dimensionless")``; the case builder writes the number.
    FRACTION = "fraction"
    IDENTIFIER = "identifier"
    CATEGORY = "category"
    COUNT = "count"
    FLAG = "flag"


class InputRole(str, Enum):
    """What an input *is* scientifically. Read by the planner and the explanation."""

    PARAMETER = "parameter"
    INITIAL_CONDITION = "initial_condition"
    BOUNDARY_CONDITION = "boundary_condition"
    OPERATING_CONDITION = "operating_condition"
    #: Evidence for a validity condition only; the solve does not read it.
    APPLICABILITY = "applicability"
    NUMERICS = "numerics"
    IDENTITY = "identity"


@dataclass(frozen=True)
class InputDeclaration:
    """One input a capability accepts, in the capability's own path vocabulary."""

    path: str
    kind: InputKind
    role: InputRole
    required: bool
    unit_exemplar: str | None = None
    model_id: str | None = None
    model_input: str | None = None
    unlocks_conditions: tuple[str, ...] = ()
    alternative_to: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", require_path(self.path, field="input.path", error=CapabilityDeclarationError))
        object.__setattr__(self, "kind", InputKind(self.kind))
        object.__setattr__(self, "role", InputRole(self.role))
        require_bool(self.required, field=f"input {self.path}.required", error=CapabilityDeclarationError)
        if self.kind is InputKind.QUANTITY:
            if self.unit_exemplar is None:
                raise _err(f"quantity input {self.path} must declare a unit exemplar")
            try:
                unit = normalize_unit(self.unit_exemplar)
                dimensionality(unit)
            except ScientificCoreError as exc:
                raise _err(f"input {self.path}: unit exemplar {self.unit_exemplar!r}: {exc}") from exc
            object.__setattr__(self, "unit_exemplar", unit)
        elif self.unit_exemplar is not None and self.kind is not InputKind.FRACTION:
            raise _err(f"{self.kind.value} input {self.path} carries no unit")
        if (self.model_id is None) != (self.model_input is None):
            raise _err(f"input {self.path}: model_id and model_input are given together or not at all")
        object.__setattr__(self, "unlocks_conditions", tuple(sorted(set(_texts(self.unlocks_conditions, "unlocks")))))
        object.__setattr__(
            self,
            "alternative_to",
            tuple(sorted(set(require_path(p, field="alternative_to", error=CapabilityDeclarationError) for p in self.alternative_to))),
        )
        object.__setattr__(self, "description", str(self.description))

    @property
    def dimension(self) -> str | None:
        if self.kind is InputKind.QUANTITY:
            return dimensionality(self.unit_exemplar)
        if self.kind is InputKind.FRACTION:
            return "dimensionless"
        return None

    @property
    def is_span(self) -> bool:
        """Whether the input is a difference on an offset scale (a delta temperature)."""
        return self.kind is InputKind.QUANTITY and is_delta_unit(self.unit_exemplar)

    @property
    def array_section(self) -> str | None:
        """``stages[]`` for ``stages[].body.duration``; ``None`` for a global input."""
        head, sep, _ = self.path.partition("[]")
        return f"{head}[]" if sep else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": INPUT_SCHEMA,
            "path": self.path,
            "kind": self.kind.value,
            "role": self.role.value,
            "required": self.required,
            "unit_exemplar": self.unit_exemplar,
            "dimension": self.dimension,
            "model_id": self.model_id,
            "model_input": self.model_input,
            "unlocks_conditions": list(self.unlocks_conditions),
            "alternative_to": list(self.alternative_to),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InputDeclaration":
        payload = require_mapping(payload, field="input", error=CapabilityDeclarationError)
        require_keys(
            payload,
            required=(
                "schema", "path", "kind", "role", "required", "unit_exemplar", "dimension",
                "model_id", "model_input", "unlocks_conditions", "alternative_to", "description",
            ),
            record="input",
            error=CapabilityDeclarationError,
        )
        require_schema_exact(payload, INPUT_SCHEMA, record="input", error=CapabilityDeclarationError)
        made = cls(
            path=payload["path"],
            kind=InputKind(payload["kind"]),
            role=InputRole(payload["role"]),
            required=payload["required"],
            unit_exemplar=payload["unit_exemplar"],
            model_id=payload["model_id"],
            model_input=payload["model_input"],
            unlocks_conditions=tuple(payload["unlocks_conditions"]),
            alternative_to=tuple(payload["alternative_to"]),
            description=payload["description"],
        )
        if made.dimension != payload["dimension"]:
            raise _err(f"input {made.path}: serialized dimension disagrees with its unit exemplar")
        return made


# ---------------------------------------------------------------------------
# Outputs, models, solvers, provided capabilities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProducedQuantity:
    """A quantity the capability reports.

    ``instance_key`` is the qualifier a claim uses to select one element when
    the quantity is reported once per element; ``instance_path`` is the input
    whose values name the elements. Both are set or neither.
    """

    name: str
    unit_exemplar: str
    model_id: str | None = None
    instance_key: str | None = None
    instance_path: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_identifier(self.name, field="produced.name", error=CapabilityDeclarationError))
        try:
            unit = normalize_unit(self.unit_exemplar)
            dimensionality(unit)
        except ScientificCoreError as exc:
            raise _err(f"produced {self.name}: unit exemplar: {exc}") from exc
        object.__setattr__(self, "unit_exemplar", unit)
        if (self.instance_key is None) != (self.instance_path is None):
            raise _err(f"produced {self.name}: instance_key and instance_path are given together")
        if self.instance_key is not None:
            require_identifier(self.instance_key, field="produced.instance_key", error=CapabilityDeclarationError)
            require_path(self.instance_path, field="produced.instance_path", error=CapabilityDeclarationError)
        object.__setattr__(self, "description", str(self.description))

    @property
    def dimension(self) -> str:
        return dimensionality(self.unit_exemplar)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PRODUCED_SCHEMA,
            "name": self.name,
            "unit_exemplar": self.unit_exemplar,
            "dimension": self.dimension,
            "model_id": self.model_id,
            "instance_key": self.instance_key,
            "instance_path": self.instance_path,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProducedQuantity":
        payload = require_mapping(payload, field="produced", error=CapabilityDeclarationError)
        require_keys(
            payload,
            required=("schema", "name", "unit_exemplar", "dimension", "model_id", "instance_key", "instance_path", "description"),
            record="produced",
            error=CapabilityDeclarationError,
        )
        require_schema_exact(payload, PRODUCED_SCHEMA, record="produced", error=CapabilityDeclarationError)
        made = cls(
            name=payload["name"],
            unit_exemplar=payload["unit_exemplar"],
            model_id=payload["model_id"],
            instance_key=payload["instance_key"],
            instance_path=payload["instance_path"],
            description=payload["description"],
        )
        if made.dimension != payload["dimension"]:
            raise _err(f"produced {made.name}: serialized dimension disagrees with its unit")
        return made


@dataclass(frozen=True)
class ModelUse:
    """A registered model the capability runs, and when it runs.

    ``activation`` lists input-path prefixes: the model takes part in a run
    exactly when an input under one of them is supplied. Empty means every
    run. ``instance_section`` names the array whose elements each carry their
    own instance of the model (``stages[]``), or ``None`` for one instance.

    ``definition`` is the live :class:`ScientificModelDefinition`; it is what
    selection assesses validity with, and it is never serialized -- a
    serialized declaration describes a capability, it does not re-arm one.
    """

    model_id: str
    version: str
    model_type: str
    assumptions: tuple[str, ...]
    exclusions: tuple[str, ...]
    validity_conditions: tuple[str, ...]
    derived_quantities: tuple[str, ...]
    activation: tuple[str, ...] = ()
    instance_section: str | None = None
    definition: Any = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _dotted(self.model_id, "model.model_id"))
        object.__setattr__(self, "version", _text(self.version, "model.version"))
        object.__setattr__(self, "model_type", _text(self.model_type, "model.model_type"))
        object.__setattr__(self, "assumptions", _texts(self.assumptions, "model.assumptions"))
        object.__setattr__(self, "exclusions", _texts(self.exclusions, "model.exclusions"))
        object.__setattr__(self, "validity_conditions", tuple(sorted(_texts(self.validity_conditions, "model.validity_conditions"))))
        object.__setattr__(self, "derived_quantities", tuple(sorted(_texts(self.derived_quantities, "model.derived_quantities"))))
        object.__setattr__(
            self,
            "activation",
            tuple(sorted(require_path(p, field="model.activation", error=CapabilityDeclarationError) for p in self.activation)),
        )
        if self.instance_section is not None and not self.instance_section.endswith("[]"):
            raise _err(f"model {self.model_id}: instance_section must name an array section like 'stages[]'")
        if self.definition is not None:
            if getattr(self.definition, "model_id", None) != self.model_id or getattr(self.definition, "version", None) != self.version:
                raise _err(
                    f"model {self.model_id}@{self.version}: the attached definition is "
                    f"{getattr(self.definition, 'model_id', None)}@{getattr(self.definition, 'version', None)}"
                )

    @classmethod
    def of(cls, definition: Any, *, activation: Iterable[str] = (), instance_section: str | None = None) -> "ModelUse":
        """Derive every field from a live model definition."""
        return cls(
            model_id=definition.model_id,
            version=definition.version,
            model_type=getattr(definition.model_type, "value", str(definition.model_type)),
            assumptions=tuple(definition.assumptions),
            exclusions=tuple(definition.exclusions),
            validity_conditions=tuple(c.name for c in definition.validity.conditions),
            derived_quantities=tuple(definition.validity.derived_quantities),
            activation=tuple(activation),
            instance_section=instance_section,
            definition=definition,
        )

    @property
    def key(self) -> tuple[str, str]:
        return (self.model_id, self.version)

    @property
    def always_active(self) -> bool:
        return not self.activation

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MODEL_USE_SCHEMA,
            "model_id": self.model_id,
            "version": self.version,
            "model_type": self.model_type,
            "assumptions": list(self.assumptions),
            "exclusions": list(self.exclusions),
            "validity_conditions": list(self.validity_conditions),
            "derived_quantities": list(self.derived_quantities),
            "activation": list(self.activation),
            "instance_section": self.instance_section,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelUse":
        payload = require_mapping(payload, field="model", error=CapabilityDeclarationError)
        require_keys(
            payload,
            required=(
                "schema", "model_id", "version", "model_type", "assumptions", "exclusions",
                "validity_conditions", "derived_quantities", "activation", "instance_section",
            ),
            record="model",
            error=CapabilityDeclarationError,
        )
        require_schema_exact(payload, MODEL_USE_SCHEMA, record="model", error=CapabilityDeclarationError)
        return cls(
            model_id=payload["model_id"],
            version=payload["version"],
            model_type=payload["model_type"],
            assumptions=tuple(payload["assumptions"]),
            exclusions=tuple(payload["exclusions"]),
            validity_conditions=tuple(payload["validity_conditions"]),
            derived_quantities=tuple(payload["derived_quantities"]),
            activation=tuple(payload["activation"]),
            instance_section=payload["instance_section"],
        )


@dataclass(frozen=True)
class SolverUse:
    """A solver the capability runs and the solver capabilities it declares."""

    solver_id: str
    version: str
    solver_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "solver_id", _text(self.solver_id, "solver.solver_id"))
        object.__setattr__(self, "version", _text(self.version, "solver.version"))
        object.__setattr__(self, "solver_capabilities", tuple(sorted(set(_texts(self.solver_capabilities, "solver.capabilities")))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SOLVER_USE_SCHEMA,
            "solver_id": self.solver_id,
            "version": self.version,
            "solver_capabilities": list(self.solver_capabilities),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SolverUse":
        payload = require_mapping(payload, field="solver", error=CapabilityDeclarationError)
        require_keys(payload, required=("schema", "solver_id", "version", "solver_capabilities"), record="solver", error=CapabilityDeclarationError)
        require_schema_exact(payload, SOLVER_USE_SCHEMA, record="solver", error=CapabilityDeclarationError)
        return cls(payload["solver_id"], payload["version"], tuple(payload["solver_capabilities"]))


@dataclass(frozen=True)
class ProvidedCapability:
    """A scientific capability the declaration provides, and what makes it true.

    ``basis`` names the record: ``realization:<id>@<version>`` when a
    registered realization declares the capability, or a stated reason when no
    realization exists (the declaration then owns the claim, and says so).
    """

    capability: ScientificCapability
    basis: str

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "capability", ScientificCapability.coerce(self.capability))
        except ScientificCoreError as exc:
            raise _err(f"provided capability: {exc}") from exc
        object.__setattr__(self, "basis", _text(self.basis, "provided.basis"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROVIDED_SCHEMA, "capability": self.capability.identifier, "basis": self.basis}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProvidedCapability":
        payload = require_mapping(payload, field="provided", error=CapabilityDeclarationError)
        require_keys(payload, required=("schema", "capability", "basis"), record="provided", error=CapabilityDeclarationError)
        require_schema_exact(payload, PROVIDED_SCHEMA, record="provided", error=CapabilityDeclarationError)
        return cls(capability=payload["capability"], basis=payload["basis"])


# ---------------------------------------------------------------------------
# Routes and levels
# ---------------------------------------------------------------------------


class RouteKind(str, Enum):
    """What a route IS. Whether two solver routes are independent is never declared.

    ``SOLVER_ROUTE`` is any further numerical route to the same quantity. The
    relation between it and the primary -- the same implementation under
    another name, a different numerical method in the same implementation, or
    a verifiably independent route -- is *computed* from the pinned component
    identities (:mod:`engcore.claims.routes`), because a declared independence
    is the thing :class:`~engcore.scientific.consensus.CrossSolverConsensus`
    refuses to believe.
    """

    PRIMARY_SIMULATION = "primary_simulation"
    SOLVER_ROUTE = "solver_route"
    ANALYTIC_REFERENCE = "analytic_reference"
    BENCHMARK = "benchmark"
    EXPERIMENTAL = "experimental"


@dataclass(frozen=True)
class RouteDeclaration:
    """One execution or evidence route of a capability.

    ``pinned_route`` keys ``engcore.domains.SCIENTIFIC_ROUTE_DECLARATIONS``;
    ``analytic_reference`` keys ``SCIENTIFIC_ANALYTIC_REFERENCE_DECLARATIONS``;
    ``oracle`` is the ``(oracle_id, version)`` of a trusted oracle pin, and
    ``oracle_provider`` returns the domain's
    :class:`~engcore.scientific.oracles.OracleEvidenceSet` for it. Each is
    checked against its registry when the declaration is built: a route naming
    a pin that does not exist, or an oracle whose content is not the trusted
    content, is refused rather than carried. ``check_name`` is the validation
    check in the credibility report that carries the route's outcome.
    ``activation`` names the input that requests the route (empty: every run
    requests it).
    """

    route_id: str
    kind: RouteKind
    description: str
    check_name: str | None = None
    pinned_route: str | None = None
    analytic_reference: str | None = None
    oracle: tuple[str, str] | None = None
    activation: tuple[str, ...] = ()
    oracle_provider: Callable[[], Any] | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_id", _text(self.route_id, "route.route_id"))
        object.__setattr__(self, "kind", RouteKind(self.kind))
        object.__setattr__(self, "description", _text(self.description, f"route {self.route_id}.description"))
        if self.oracle is not None:
            oracle = tuple(self.oracle)
            if len(oracle) != 2:
                raise _err(f"route {self.route_id}: oracle is (oracle_id, version)")
            object.__setattr__(self, "oracle", (_text(oracle[0], "oracle id"), _text(oracle[1], "oracle version")))
        object.__setattr__(
            self,
            "activation",
            tuple(sorted(require_path(p, field="route.activation", error=CapabilityDeclarationError) for p in self.activation)),
        )
        needs = {
            RouteKind.ANALYTIC_REFERENCE: ("analytic_reference", self.analytic_reference),
            RouteKind.BENCHMARK: ("oracle", self.oracle),
            RouteKind.EXPERIMENTAL: ("oracle", self.oracle),
            RouteKind.SOLVER_ROUTE: ("pinned_route", self.pinned_route),
        }
        if self.kind in needs:
            name, value = needs[self.kind]
            if value is None:
                raise _err(f"a {self.kind.value} route must name its {name}; route {self.route_id} does not")
        if self.kind is not RouteKind.PRIMARY_SIMULATION and self.check_name is None:
            raise _err(f"route {self.route_id}: an evidence route names the check that carries its outcome")
        if self.oracle_provider is not None:
            if self.oracle is None:
                raise _err(f"route {self.route_id}: an oracle provider without an oracle identity")
            if not callable(self.oracle_provider):
                raise _err(f"route {self.route_id}: oracle_provider must be callable")

    def verify_references(self) -> None:
        """Refuse a route whose pin, reference or oracle is not the registered one."""
        from .. import domains  # the registries live beside the domains that pin them

        if self.pinned_route is not None and self.pinned_route not in domains.SCIENTIFIC_ROUTE_DECLARATIONS:
            raise _err(f"route {self.route_id}: {self.pinned_route!r} is not a pinned solve route")
        if (
            self.analytic_reference is not None
            and self.analytic_reference not in domains.SCIENTIFIC_ANALYTIC_REFERENCE_DECLARATIONS
        ):
            raise _err(f"route {self.route_id}: {self.analytic_reference!r} is not a pinned analytic reference")
        if self.oracle is not None:
            if self.oracle_provider is None:
                raise _err(f"route {self.route_id}: oracle {self.oracle} has no provider to verify it against")
            evidence = self.oracle_provider()
            identity = getattr(evidence, "identity", None)
            if identity is None or tuple(identity.key) != tuple(self.oracle):
                raise _err(f"route {self.route_id}: the provider returns {getattr(identity, 'key', None)}, not {self.oracle}")
            if not evidence.is_trusted:
                raise _err(
                    f"route {self.route_id}: oracle {self.oracle} is not trusted: "
                    f"{identity.authority_gap}"
                )
            expected = {RouteKind.BENCHMARK: ValidationLevel.BENCHMARK_VALIDATED,
                        RouteKind.EXPERIMENTAL: ValidationLevel.EXPERIMENTALLY_VALIDATED}.get(self.kind)
            if expected is not None and identity.establishes is not expected:
                raise _err(
                    f"route {self.route_id}: a {self.kind.value} route must name an oracle that "
                    f"establishes {expected.value}; {self.oracle} establishes {identity.establishes.value}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ROUTE_SCHEMA,
            "route_id": self.route_id,
            "kind": self.kind.value,
            "description": self.description,
            "check_name": self.check_name,
            "pinned_route": self.pinned_route,
            "analytic_reference": self.analytic_reference,
            "oracle": None if self.oracle is None else list(self.oracle),
            "activation": list(self.activation),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RouteDeclaration":
        payload = require_mapping(payload, field="route", error=CapabilityDeclarationError)
        require_keys(
            payload,
            required=("schema", "route_id", "kind", "description", "check_name", "pinned_route", "analytic_reference", "oracle", "activation"),
            record="route",
            error=CapabilityDeclarationError,
        )
        require_schema_exact(payload, ROUTE_SCHEMA, record="route", error=CapabilityDeclarationError)
        oracle = payload["oracle"]
        return cls(
            route_id=payload["route_id"],
            kind=RouteKind(payload["kind"]),
            description=payload["description"],
            check_name=payload["check_name"],
            pinned_route=payload["pinned_route"],
            analytic_reference=payload["analytic_reference"],
            oracle=None if oracle is None else tuple(oracle),
            activation=tuple(payload["activation"]),
        )


@dataclass(frozen=True)
class AttainableLevel:
    """An evidentiary level the capability CAN attain, the check that earns it, and when.

    ``quantities`` scopes the declaration to the produced QoIs the check
    actually establishes. An empty tuple preserves the historical
    capability-wide declaration for checks that genuinely cover every output.

    An upper bound for prediction, never an award: the credibility report the
    run produces is the only thing that attains a level.
    """

    level: ValidationLevel
    check_name: str
    route_id: str | None
    condition: str
    quantities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", ValidationLevel(self.level))
        if self.level is ValidationLevel.UNVERIFIED:
            raise _err("UNVERIFIED is not an attainable level")
        object.__setattr__(self, "check_name", _text(self.check_name, "level.check_name"))
        object.__setattr__(self, "condition", _text(self.condition, "level.condition"))
        quantities = tuple(
            require_identifier(
                item,
                field="level.quantities",
                error=CapabilityDeclarationError,
            )
            for item in self.quantities
        )
        if len(quantities) != len(set(quantities)):
            raise _err("level.quantities contains duplicate produced quantities")
        object.__setattr__(self, "quantities", tuple(sorted(quantities)))

    def applies_to(self, quantity: str) -> bool:
        return not self.quantities or quantity in self.quantities

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LEVEL_SCHEMA_SCOPED if self.quantities else LEVEL_SCHEMA,
            "level": self.level.value,
            "check_name": self.check_name,
            "route_id": self.route_id,
            "condition": self.condition,
            **({"quantities": list(self.quantities)} if self.quantities else {}),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AttainableLevel":
        payload = require_mapping(payload, field="level", error=CapabilityDeclarationError)
        schema = require_schema_any(payload, (LEVEL_SCHEMA, LEVEL_SCHEMA_SCOPED))
        required = ("schema", "level", "check_name", "route_id", "condition")
        if schema == LEVEL_SCHEMA_SCOPED:
            required = required + ("quantities",)
        require_keys(
            payload,
            required=required,
            record="level",
            error=CapabilityDeclarationError,
        )
        quantities = (
            tuple(
                require_list(
                    payload["quantities"],
                    field="level.quantities",
                    error=CapabilityDeclarationError,
                )
            )
            if schema == LEVEL_SCHEMA_SCOPED
            else ()
        )
        return cls(
            ValidationLevel(payload["level"]),
            payload["check_name"],
            payload["route_id"],
            payload["condition"],
            quantities,
        )


@dataclass(frozen=True)
class UncertaintyCapability:
    """Which uncertainty channels the capability quantifies, per produced quantity.

    A quantity absent from ``quantified`` has every channel UNKNOWN. That is
    the state of every production system today, and declaring it is what lets
    the compiler say *before running anything* that a claim demanding a
    quantified channel cannot be supported by this capability.
    """

    quantified: Mapping[str, frozenset[UncertaintyChannel]]
    basis: str

    def __post_init__(self) -> None:
        quantified = {}
        for name, channels in require_mapping(self.quantified, field="uncertainty.quantified", error=CapabilityDeclarationError).items():
            quantified[require_identifier(name, field="uncertainty quantity", error=CapabilityDeclarationError)] = frozenset(
                UncertaintyChannel(c) for c in channels
            )
        object.__setattr__(self, "quantified", freeze(quantified))
        object.__setattr__(self, "basis", _text(self.basis, "uncertainty.basis"))

    def channels_for(self, quantity: str) -> frozenset[UncertaintyChannel]:
        return frozenset(self.quantified.get(quantity, frozenset()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNCERTAINTY_SCHEMA,
            "quantified": {
                name: sorted(c.value for c in self.quantified[name]) for name in sorted(self.quantified)
            },
            "basis": self.basis,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UncertaintyCapability":
        payload = require_mapping(payload, field="uncertainty", error=CapabilityDeclarationError)
        require_keys(payload, required=("schema", "quantified", "basis"), record="uncertainty", error=CapabilityDeclarationError)
        require_schema_exact(payload, UNCERTAINTY_SCHEMA, record="uncertainty", error=CapabilityDeclarationError)
        return cls(quantified={k: tuple(v) for k, v in payload["quantified"].items()}, basis=payload["basis"])


@dataclass(frozen=True)
class UnassessableCondition:
    """A validity condition this capability can never assess, and why.

    Some systems run a model without assembling the context one of its
    conditions reads -- the battery boundary runs the lumped thermal body but
    accepts no body-applicability declaration, so the body's Biot number is
    never computed. No input a caller could supply changes that. Declaring it
    lets selection see, before anything runs, that the model's applicability
    cannot be established here; a test pins the declaration against the
    conditions a real run leaves UNKNOWN.
    """

    model_id: str
    condition: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _dotted(self.model_id, "unassessable.model_id"))
        object.__setattr__(self, "condition", _text(self.condition, "unassessable.condition"))
        object.__setattr__(self, "reason", _text(self.reason, "unassessable.reason"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNASSESSABLE_SCHEMA,
            "model_id": self.model_id,
            "condition": self.condition,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UnassessableCondition":
        payload = require_mapping(payload, field="unassessable", error=CapabilityDeclarationError)
        require_keys(payload, required=("schema", "model_id", "condition", "reason"), record="unassessable", error=CapabilityDeclarationError)
        require_schema_exact(payload, UNASSESSABLE_SCHEMA, record="unassessable", error=CapabilityDeclarationError)
        return cls(payload["model_id"], payload["condition"], payload["reason"])


@dataclass(frozen=True)
class RefinementStudy:
    """How the capability's numerical uncertainty can be measured: a declared refinement ladder.

    ``refined_inputs`` are NUMERICS count inputs and the finest (baseline) value
    each takes when a claim states none -- exactly the executor's own default,
    so level 0 of the study *is* the reported run. Level ``k`` divides every
    refined input by ``ratio**k``; the scheme's ``formal_order`` and the
    ``order_tolerance`` that decides the asymptotic range are the capability's
    declaration, never inferred from the numbers.
    """

    quantities: frozenset[str]
    refined_inputs: Mapping[str, int]
    ratio: int
    levels: int
    formal_order: float
    order_tolerance: float
    basis: str
    #: Checks that judge accuracy *at the run's own resolution*; a coarse level is
    #: expected to fail them, and the study measures exactly that. Any other FAIL
    #: disqualifies a level.
    accuracy_checks: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "accuracy_checks", frozenset(_text(c, "refinement.accuracy_check") for c in self.accuracy_checks))
        object.__setattr__(self, "quantities", frozenset(require_identifier(q, field="refinement.quantity", error=CapabilityDeclarationError) for q in self.quantities))
        refined = {}
        for path, value in require_mapping(self.refined_inputs, field="refinement.refined_inputs", error=CapabilityDeclarationError).items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise _err(f"refinement baseline for {path} must be a positive integer")
            refined[_text(path, "refinement.path")] = value
        if not self.quantities or not refined:
            raise _err("a refinement study names at least one quantity and one refined input")
        object.__setattr__(self, "refined_inputs", freeze(refined))
        for label in ("ratio", "levels"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int):
                raise _err(f"refinement.{label} must be an integer")
        if self.ratio < 2:
            raise _err("refinement.ratio must be at least 2")
        if self.levels < 3:
            raise _err("refinement.levels must be at least 3: an observed order needs three solutions")
        for label in ("formal_order", "order_tolerance"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
                raise _err(f"refinement.{label} must be positive")
            object.__setattr__(self, label, float(value))
        object.__setattr__(self, "basis", _text(self.basis, "refinement.basis"))

    def ladder(self, baseline: Mapping[str, int]) -> tuple[dict[str, int], ...] | str:
        """The resolution of every level, finest first, or why this baseline admits no ladder."""
        out = []
        for k in range(self.levels):
            level = {}
            for path, value in sorted(baseline.items()):
                divisor = self.ratio ** k
                if value % divisor:
                    return f"{path}={value} is not divisible by {self.ratio}**{k}; level {k} would not be a refinement"
                level[path] = value // divisor
            out.append(level)
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REFINEMENT_SCHEMA,
            "quantities": sorted(self.quantities),
            "refined_inputs": {k: self.refined_inputs[k] for k in sorted(self.refined_inputs)},
            "ratio": self.ratio,
            "levels": self.levels,
            "formal_order": self.formal_order,
            "order_tolerance": self.order_tolerance,
            "basis": self.basis,
            "accuracy_checks": sorted(self.accuracy_checks),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RefinementStudy":
        payload = require_mapping(payload, field="refinement", error=CapabilityDeclarationError)
        require_keys(payload, required=("schema", "quantities", "refined_inputs", "ratio", "levels", "formal_order", "order_tolerance", "basis", "accuracy_checks"), record="refinement", error=CapabilityDeclarationError)
        require_schema_exact(payload, REFINEMENT_SCHEMA, record="refinement", error=CapabilityDeclarationError)
        return cls(frozenset(payload["quantities"]), payload["refined_inputs"], payload["ratio"], payload["levels"], payload["formal_order"], payload["order_tolerance"], payload["basis"], frozenset(payload["accuracy_checks"]))


@dataclass(frozen=True)
class PerturbableInput:
    """An input the capability may be re-run at another value of, for propagation or sensitivity.

    Declaring it says only that the system accepts other values there; whether a
    perturbed run stays inside its models' validated domains is decided per run
    by the run's own validity records.
    """

    path: str
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _text(self.path, "perturbable.path"))
        object.__setattr__(self, "rationale", _text(self.rationale, "perturbable.rationale"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PERTURBABLE_SCHEMA, "path": self.path, "rationale": self.rationale}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PerturbableInput":
        payload = require_mapping(payload, field="perturbable", error=CapabilityDeclarationError)
        require_keys(payload, required=("schema", "path", "rationale"), record="perturbable", error=CapabilityDeclarationError)
        require_schema_exact(payload, PERTURBABLE_SCHEMA, record="perturbable", error=CapabilityDeclarationError)
        return cls(payload["path"], payload["rationale"])


# ---------------------------------------------------------------------------
# The declaration
# ---------------------------------------------------------------------------

#: ``executor(case, *, run_id) -> CapabilityRun``. Kept off the serialized form.
Executor = Callable[..., Any]
CaseBuilder = Callable[[Mapping[str, Any]], dict]


@dataclass(frozen=True)
class CapabilityDeclaration:
    """Everything the Core may know about one executable capability, before running it."""

    capability_id: str
    version: str
    domain: str
    summary: str
    provides: tuple[ProvidedCapability, ...]
    inputs: tuple[InputDeclaration, ...]
    produces: tuple[ProducedQuantity, ...]
    models: tuple[ModelUse, ...]
    solvers: tuple[SolverUse, ...]
    claim_shapes: frozenset[ClaimKind]
    attainable_levels: tuple[AttainableLevel, ...]
    uncertainty: UncertaintyCapability
    routes: tuple[RouteDeclaration, ...]
    unassessable_conditions: tuple[UnassessableCondition, ...] = ()
    #: Phase 2: how NUMERICAL uncertainty is measured (``None``: it is not).
    refinement: RefinementStudy | None = None
    #: Phase 2/7: inputs the system may be re-run at other values of.
    perturbable: tuple[PerturbableInput, ...] = ()
    executor: Executor | None = field(default=None, compare=False, repr=False)
    case_builder: CaseBuilder | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_id", _dotted(self.capability_id, "capability_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(self, "domain", _dotted(self.domain, "domain"))
        object.__setattr__(self, "summary", _text(self.summary, "summary"))
        for label, kind in (
            ("provides", ProvidedCapability),
            ("inputs", InputDeclaration),
            ("produces", ProducedQuantity),
            ("models", ModelUse),
            ("solvers", SolverUse),
            ("attainable_levels", AttainableLevel),
            ("routes", RouteDeclaration),
            ("unassessable_conditions", UnassessableCondition),
        ):
            items = tuple(getattr(self, label))
            if any(not isinstance(item, kind) for item in items):
                raise _err(f"{self.capability_id}: {label} must be {kind.__name__} records")
            object.__setattr__(self, label, items)
        if not isinstance(self.uncertainty, UncertaintyCapability):
            raise _err(f"{self.capability_id}: uncertainty must be an UncertaintyCapability")
        if self.refinement is not None and not isinstance(self.refinement, RefinementStudy):
            raise _err(f"{self.capability_id}: refinement must be a RefinementStudy")
        perturbable = tuple(self.perturbable)
        if any(not isinstance(p, PerturbableInput) for p in perturbable):
            raise _err(f"{self.capability_id}: perturbable must be PerturbableInput records")
        object.__setattr__(self, "perturbable", tuple(sorted(perturbable, key=lambda p: p.path)))
        object.__setattr__(self, "claim_shapes", frozenset(ClaimKind(k) for k in self.claim_shapes))
        if not self.claim_shapes:
            raise _err(f"{self.capability_id}: declares no claim shape it can decide")
        if not self.produces:
            raise _err(f"{self.capability_id}: produces nothing")

        self._unique("provides", [p.capability.identifier for p in self.provides])
        self._unique("inputs", [i.path for i in self.inputs])
        self._unique("produces", [q.name for q in self.produces])
        self._unique("models", [m.model_id for m in self.models])
        self._unique("routes", [r.route_id for r in self.routes])

        # Canonical order, so the digest cannot depend on declaration order.
        object.__setattr__(self, "provides", tuple(sorted(self.provides, key=lambda p: p.capability.identifier)))
        object.__setattr__(self, "inputs", tuple(sorted(self.inputs, key=lambda i: i.path)))
        object.__setattr__(self, "produces", tuple(sorted(self.produces, key=lambda q: q.name)))
        object.__setattr__(self, "models", tuple(sorted(self.models, key=lambda m: m.model_id)))
        object.__setattr__(self, "solvers", tuple(sorted(self.solvers, key=lambda s: (s.solver_id, s.version))))
        object.__setattr__(
            self,
            "attainable_levels",
            tuple(sorted(self.attainable_levels, key=lambda a: (list(ValidationLevel).index(a.level), a.check_name))),
        )
        object.__setattr__(self, "routes", tuple(sorted(self.routes, key=lambda r: r.route_id)))
        self._unique(
            "unassessable_conditions",
            [f"{u.model_id}#{u.condition}" for u in self.unassessable_conditions],
        )
        object.__setattr__(
            self,
            "unassessable_conditions",
            tuple(sorted(self.unassessable_conditions, key=lambda u: (u.model_id, u.condition))),
        )

        self._check_references()
        if self.executor is not None and not callable(self.executor):
            raise _err(f"{self.capability_id}: executor must be callable")
        if self.case_builder is not None and not callable(self.case_builder):
            raise _err(f"{self.capability_id}: case_builder must be callable")

    def _unique(self, label: str, keys: list[str]) -> None:
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        if duplicates:
            raise _err(f"{self.capability_id}: duplicate {label} {duplicates}")

    def _check_references(self) -> None:
        paths = {i.path for i in self.inputs}
        models = {m.model_id for m in self.models}
        for item in self.inputs:
            if item.model_id is not None and item.model_id not in models:
                raise _err(f"{self.capability_id}: input {item.path} feeds model {item.model_id}, which is not declared")
            for other in item.alternative_to:
                if other not in paths:
                    raise _err(f"{self.capability_id}: input {item.path} is an alternative to undeclared {other}")
        for quantity in self.produces:
            if quantity.model_id is not None and quantity.model_id not in models:
                raise _err(f"{self.capability_id}: {quantity.name} is produced by undeclared model {quantity.model_id}")
            if quantity.instance_path is not None and quantity.instance_path not in paths:
                raise _err(f"{self.capability_id}: {quantity.name} instances are named by undeclared input {quantity.instance_path}")
        for model in self.models:
            for prefix in model.activation:
                if not any(p == prefix or p.startswith(prefix + ".") for p in paths):
                    raise _err(f"{self.capability_id}: model {model.model_id} activates on {prefix}, under which nothing is declared")
        routes = {r.route_id: r for r in self.routes}
        primaries = [r for r in self.routes if r.kind is RouteKind.PRIMARY_SIMULATION]
        if len(primaries) != 1:
            raise _err(f"{self.capability_id}: exactly one PRIMARY_SIMULATION route is required, found {len(primaries)}")
        for route in self.routes:
            for path in route.activation:
                if path not in paths:
                    raise _err(f"{self.capability_id}: route {route.route_id} is activated by undeclared input {path}")
        for level in self.attainable_levels:
            if level.route_id is not None and level.route_id not in routes:
                raise _err(f"{self.capability_id}: level {level.level.value} names undeclared route {level.route_id}")
        if self.executor is not None:
            # A live declaration must point at real pins; a description read
            # back from JSON is checked by digest instead (it has no providers).
            for route in self.routes:
                route.verify_references()
        by_model = {m.model_id: m for m in self.models}
        for item in self.unassessable_conditions:
            model = by_model.get(item.model_id)
            if model is None:
                raise _err(f"{self.capability_id}: unassessable condition names undeclared model {item.model_id}")
            if item.condition not in model.validity_conditions:
                raise _err(
                    f"{self.capability_id}: {item.model_id} has no validity condition {item.condition!r}"
                )
        produced = {q.name for q in self.produces}
        for level in self.attainable_levels:
            unknown_quantities = sorted(set(level.quantities) - produced)
            if unknown_quantities:
                raise _err(
                    f"{self.capability_id}: level {level.level.value} scopes to "
                    f"unproduced quantities {unknown_quantities}"
                )
        for quantity in produced:
            applicable = [level for level in self.attainable_levels if level.applies_to(quantity)]
            seen: set[ValidationLevel] = set()
            for level in applicable:
                if level.level in seen:
                    raise _err(
                        f"{self.capability_id}: {quantity} has more than one "
                        f"attainable declaration for {level.level.value}"
                    )
                seen.add(level.level)
        for name in self.uncertainty.quantified:
            if name not in produced:
                raise _err(f"{self.capability_id}: uncertainty declared for {name}, which is not produced")
        self._unique("perturbable", [p.path for p in self.perturbable])
        by_path = {i.path: i for i in self.inputs}
        for item in self.perturbable:
            declared = by_path.get(item.path)
            if declared is None or declared.kind is not InputKind.QUANTITY:
                raise _err(f"{self.capability_id}: perturbable input {item.path} is not a declared quantity input")
        if self.refinement is not None:
            for name in self.refinement.quantities:
                if name not in produced:
                    raise _err(f"{self.capability_id}: refinement names {name}, which is not produced")
            for path in self.refinement.refined_inputs:
                declared = by_path.get(path)
                if declared is None or declared.kind is not InputKind.COUNT or declared.role is not InputRole.NUMERICS:
                    raise _err(f"{self.capability_id}: refined input {path} is not a declared NUMERICS count")
            ladder = self.refinement.ladder(self.refinement.refined_inputs)
            if isinstance(ladder, str):
                raise _err(f"{self.capability_id}: the declared baseline admits no ladder: {ladder}")
        # A channel may be declared quantifiable only where a declared study can quantify it.
        for name, channels in self.uncertainty.quantified.items():
            if UncertaintyChannel.NUMERICAL in channels and (self.refinement is None or name not in self.refinement.quantities):
                raise _err(f"{self.capability_id}: NUMERICAL is declared for {name} with no refinement study behind it")
            if UncertaintyChannel.EPISTEMIC_PARAMETER in channels and not self.perturbable:
                raise _err(f"{self.capability_id}: EPISTEMIC_PARAMETER is declared for {name} with no perturbable input")

    # ---- views ----------------------------------------------------------------

    @property
    def provided_capabilities(self) -> frozenset[ScientificCapability]:
        return frozenset(p.capability for p in self.provides)

    @property
    def primary_route(self) -> RouteDeclaration:
        return next(r for r in self.routes if r.kind is RouteKind.PRIMARY_SIMULATION)

    def input(self, path: str) -> InputDeclaration | None:
        """The declaration for a claim path (indexed or declared form), or ``None``."""
        wanted = declared_path(path)
        return next((i for i in self.inputs if i.path == wanted), None)

    def produced(self, name: str) -> ProducedQuantity | None:
        return next((q for q in self.produces if q.name == name), None)

    def model(self, model_id: str) -> ModelUse | None:
        return next((m for m in self.models if m.model_id == model_id), None)

    def route(self, route_id: str) -> RouteDeclaration | None:
        return next((r for r in self.routes if r.route_id == route_id), None)

    @property
    def required_inputs(self) -> tuple[InputDeclaration, ...]:
        return tuple(i for i in self.inputs if i.required)

    def attainable(self, quantity: str | None = None) -> frozenset[ValidationLevel]:
        """Levels this capability can establish, optionally for one produced QoI."""
        if quantity is None:
            return frozenset(a.level for a in self.attainable_levels)
        if self.produced(quantity) is None:
            raise _err(f"{self.capability_id}: {quantity!r} is not a produced quantity")
        return frozenset(
            a.level for a in self.attainable_levels if a.applies_to(quantity)
        )

    def unassessable(self, model_id: str) -> Mapping[str, str]:
        """Condition name -> reason, for the conditions of ``model_id`` never assessable here."""
        return {u.condition: u.reason for u in self.unassessable_conditions if u.model_id == model_id}

    @property
    def executable(self) -> bool:
        return self.executor is not None

    # ---- identity ---------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CAPABILITY_SCHEMA,
            "capability_id": self.capability_id,
            "version": self.version,
            "domain": self.domain,
            "summary": self.summary,
            "provides": [p.to_dict() for p in self.provides],
            "inputs": [i.to_dict() for i in self.inputs],
            "produces": [q.to_dict() for q in self.produces],
            "models": [m.to_dict() for m in self.models],
            "solvers": [s.to_dict() for s in self.solvers],
            "claim_shapes": sorted(k.value for k in self.claim_shapes),
            "attainable_levels": [a.to_dict() for a in self.attainable_levels],
            "uncertainty": self.uncertainty.to_dict(),
            "routes": [r.to_dict() for r in self.routes],
            "unassessable_conditions": [u.to_dict() for u in self.unassessable_conditions],
            # Written only when declared, so a capability that declares neither keeps its identity.
            **({"refinement": self.refinement.to_dict()} if self.refinement is not None else {}),
            **({"perturbable": [p.to_dict() for p in self.perturbable]} if self.perturbable else {}),
        }

    @property
    def digest(self) -> str:
        """Identity of what the capability declares. Executors are not part of it."""
        return tagged_digest(_DECLARATION_TAG, self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CapabilityDeclaration":
        """A description only: the result has no executor and no model definitions."""
        payload = require_mapping(payload, field="capability", error=CapabilityDeclarationError)
        require_keys(
            payload,
            required=(
                "schema", "capability_id", "version", "domain", "summary", "provides", "inputs",
                "produces", "models", "solvers", "claim_shapes", "attainable_levels", "uncertainty", "routes",
                "unassessable_conditions",
            ),
            optional=("refinement", "perturbable"),
            record="capability",
            error=CapabilityDeclarationError,
        )
        require_schema_exact(payload, CAPABILITY_SCHEMA, record="capability", error=CapabilityDeclarationError)

        def many(key: str, reader: Callable[[Any], Any]) -> tuple:
            return tuple(reader(item) for item in require_list(payload[key], field=key, error=CapabilityDeclarationError))

        return cls(
            capability_id=payload["capability_id"],
            version=payload["version"],
            domain=payload["domain"],
            summary=payload["summary"],
            provides=many("provides", ProvidedCapability.from_dict),
            inputs=many("inputs", InputDeclaration.from_dict),
            produces=many("produces", ProducedQuantity.from_dict),
            models=many("models", ModelUse.from_dict),
            solvers=many("solvers", SolverUse.from_dict),
            claim_shapes=frozenset(ClaimKind(k) for k in require_list(payload["claim_shapes"], field="claim_shapes", error=CapabilityDeclarationError)),
            attainable_levels=many("attainable_levels", AttainableLevel.from_dict),
            uncertainty=UncertaintyCapability.from_dict(payload["uncertainty"]),
            routes=many("routes", RouteDeclaration.from_dict),
            unassessable_conditions=many("unassessable_conditions", UnassessableCondition.from_dict),
            refinement=None if payload.get("refinement") is None else RefinementStudy.from_dict(payload["refinement"]),
            perturbable=many("perturbable", PerturbableInput.from_dict) if "perturbable" in payload else (),
        )


# ---------------------------------------------------------------------------
# What an executor returns
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InstanceReport:
    """One credibility report and the element it describes (``None``: the whole case)."""

    instance: str | None
    report: Any

    def __post_init__(self) -> None:
        from ..credibility.evidence import CredibilityEvidenceReport

        if not isinstance(self.report, CredibilityEvidenceReport):
            raise _err("an executor returns CredibilityEvidenceReport records, nothing else")
        if self.instance is not None:
            object.__setattr__(self, "instance", _text(self.instance, "instance"))


@dataclass(frozen=True)
class CapabilityRun:
    """Everything an executor hands back. ``native`` is the system's own run object.

    ``condition_repairs`` carries the serialized
    :class:`~engcore.domains.repair.ConditionRepair` records the system already
    computed, per instance, so a repair shown to a caller is the domain's exact
    inversion and never a sentence written here.
    """

    reports: tuple[InstanceReport, ...]
    condition_repairs: tuple[tuple[str | None, Mapping[str, Any]], ...] = ()
    native: Any = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        reports = tuple(self.reports)
        if not reports or any(not isinstance(r, InstanceReport) for r in reports):
            raise _err("a capability run carries at least one InstanceReport")
        instances = [r.instance for r in reports]
        if len(set(instances)) != len(instances):
            raise _err(f"a capability run reports one instance once; got {instances}")
        object.__setattr__(self, "reports", reports)
        object.__setattr__(self, "condition_repairs", tuple((i, freeze(dict(r))) for i, r in self.condition_repairs))


# ---------------------------------------------------------------------------
# Inputs -> a case
# ---------------------------------------------------------------------------

_INDEX = re.compile(r"\[(\d*)\]")


def input_problem(declaration: InputDeclaration, path: str, value: Any) -> str | None:
    """Why ``value`` cannot be supplied as ``path``, or ``None`` when it can.

    One rule for the compiler (which reports the problem) and the case builder
    (which refuses on it), so the two cannot disagree about what is accepted.
    """
    wanted_indexed = declaration.array_section is not None
    indices = _INDEX.findall(path)
    if wanted_indexed and (not indices or any(i == "" for i in indices)):
        return f"{path} belongs to the array {declaration.array_section} and must name an element, e.g. {declaration.path.replace('[]', '[0]')}"
    if not wanted_indexed and indices:
        return f"{path} is not an array element; the declared input is {declaration.path}"
    kind = declaration.kind
    if kind is InputKind.QUANTITY:
        if not isinstance(value, Quantity):
            return f"{path} must be a Quantity of [{declaration.dimension}] (e.g. 1 {declaration.unit_exemplar}), got {type(value).__name__}"
        if dimensionality(value.units) != declaration.dimension:
            return f"{path} is [{dimensionality(value.units)}], the capability requires [{declaration.dimension}] (e.g. 1 {declaration.unit_exemplar})"
        if is_delta_unit(value.units) != declaration.is_span:
            wanted = "a difference" if declaration.is_span else "an absolute value"
            return f"{path} must be {wanted} on the temperature scale; {value} is not"
        return None
    if kind is InputKind.FRACTION:
        if not isinstance(value, Quantity) or dimensionality(value.units) != "dimensionless":
            return f"{path} is a dimensionless share, stated as Quantity(x, 'dimensionless')"
        return None
    if kind in (InputKind.IDENTIFIER, InputKind.CATEGORY):
        if not isinstance(value, str) or isinstance(value, bool):
            return f"{path} is {kind.value} text, got {type(value).__name__}"
        return None
    if kind is InputKind.COUNT:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return f"{path} is a positive integer count, got {value!r}"
        return None
    if kind is InputKind.FLAG:
        if not isinstance(value, bool):
            return f"{path} is a boolean flag, got {value!r}"
        return None
    return f"{path}: unhandled input kind {kind.value}"  # pragma: no cover - closed enum


def _payload_value(declaration: InputDeclaration, value: Any) -> Any:
    if declaration.kind is InputKind.QUANTITY:
        return quantity_text(value)
    if declaration.kind is InputKind.FRACTION:
        return float(value.magnitude_in("dimensionless"))
    return value


def _insert(tree: dict, path: str, value: Any) -> None:
    segments = path.split(".")
    node: Any = tree
    for position, segment in enumerate(segments):
        last = position == len(segments) - 1
        match = _INDEX.search(segment)
        name = segment[: match.start()] if match else segment
        if match:
            index = int(match.group(1))
            items = node.setdefault(name, [])
            if not isinstance(items, list):
                raise CapabilityInputError(f"{path}: {name} is both an element array and a value")
            while len(items) <= index:
                items.append(None)
            if last:
                items[index] = value
                return
            if items[index] is None:
                items[index] = {}
            node = items[index]
        else:
            if last:
                if name in node:
                    raise CapabilityInputError(f"{path} is supplied twice")
                node[name] = value
                return
            child = node.setdefault(name, {})
            if not isinstance(child, dict):
                raise CapabilityInputError(f"{path}: {name} is both a section and a value")
            node = child


def _holes(node: Any, where: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, child in node.items():
            found += _holes(child, f"{where}.{key}" if where else key)
    elif isinstance(node, list):
        for index, child in enumerate(node):
            if child is None:
                found.append(f"{where}[{index}]")
            else:
                found += _holes(child, f"{where}[{index}]")
    return found


def build_case(declaration: CapabilityDeclaration, inputs: Mapping[str, Any]) -> dict:
    """Write supplied inputs into the nested case the capability's executor reads.

    Purely mechanical: every path must be declared, every value must pass
    :func:`input_problem`, and array elements must be dense from index 0. Nothing
    is defaulted, reordered by meaning or inferred -- an input the claim did not
    state is absent from the case, and the system decides what that means.
    """
    tree: dict = {}
    for path in sorted(inputs):
        found = declaration.input(path)
        if found is None:
            raise CapabilityInputError(f"{declaration.capability_id} declares no input {path!r}")
        problem = input_problem(found, path, inputs[path])
        if problem is not None:
            raise CapabilityInputError(problem)
        _insert(tree, path, _payload_value(found, inputs[path]))
    holes = _holes(tree)
    if holes:
        raise CapabilityInputError(
            f"array elements {holes} are not described; elements are numbered from 0 without gaps"
        )
    return tree


def inputs_from_case(declaration: CapabilityDeclaration, case: Mapping[str, Any]) -> dict[str, Any]:
    """The claim-input form of an existing case payload: the inverse of :func:`build_case`.

    Every leaf must be a declared input and every value is read as its declared
    kind: a quantity text through :meth:`Quantity.parse`, a fraction into a
    dimensionless Quantity. Nothing is dropped and nothing is added, and
    ``build_case(declaration, inputs_from_case(declaration, case))`` writes the
    same case back (up to the canonical spelling of units).
    """
    out: dict[str, Any] = {}

    def walk(node: Any, where: str) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                walk(child, f"{where}.{key}" if where else str(key))
            return
        if isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, f"{where}[{index}]")
            return
        item = declaration.input(where)
        if item is None:
            raise CapabilityInputError(f"{declaration.capability_id} declares no input {where!r}")
        if item.kind is InputKind.QUANTITY:
            if not isinstance(node, str):
                raise CapabilityInputError(f"{where} must be quantity text, got {node!r}")
            try:
                value: Any = Quantity.parse(node)
            except ScientificCoreError as exc:
                raise CapabilityInputError(f"{where}: {exc}") from exc
        elif item.kind is InputKind.FRACTION:
            if isinstance(node, bool) or not isinstance(node, (int, float)):
                raise CapabilityInputError(f"{where} must be a bare fraction, got {node!r}")
            value = Quantity(float(node), "dimensionless")
        else:
            value = node
        problem = input_problem(item, where, value)
        if problem is not None:
            raise CapabilityInputError(problem)
        out[where] = value

    walk(case, "")
    return out


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


class MismatchReason(str, Enum):
    """Why a declaration is not a candidate for a requested quantity. Each is a fact."""

    QUANTITY_NOT_PRODUCED = "quantity_not_produced"
    DIMENSION_MISMATCH = "dimension_mismatch"
    CAPABILITY_NOT_PROVIDED = "capability_not_provided"
    CLAIM_SHAPE_UNSUPPORTED = "claim_shape_unsupported"
    NOT_EXECUTABLE = "not_executable"


@dataclass(frozen=True)
class CapabilityMatch:
    """How one declaration relates to one structured requirement. Never a ranking."""

    capability_id: str
    matched: bool
    reasons: tuple[tuple[MismatchReason, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "matched": self.matched,
            "reasons": [{"reason": r.value, "detail": d} for r, d in self.reasons],
        }


def match_declaration(
    declaration: CapabilityDeclaration,
    *,
    quantity: str,
    dimension: str,
    required: frozenset[ScientificCapability],
    claim_kind: ClaimKind,
) -> CapabilityMatch:
    """Compare declared facts with structured requirements. Exact identifiers only."""
    reasons: list[tuple[MismatchReason, str]] = []
    produced = declaration.produced(quantity)
    if produced is None:
        reasons.append(
            (
                MismatchReason.QUANTITY_NOT_PRODUCED,
                f"{declaration.capability_id} produces {[q.name for q in declaration.produces]}, not {quantity!r}",
            )
        )
    elif produced.dimension != dimension:
        reasons.append(
            (
                MismatchReason.DIMENSION_MISMATCH,
                f"{declaration.capability_id} reports {quantity!r} as [{produced.dimension}], the claim needs [{dimension}]",
            )
        )
    missing = sorted(c.identifier for c in required - declaration.provided_capabilities)
    if missing:
        reasons.append(
            (
                MismatchReason.CAPABILITY_NOT_PROVIDED,
                f"{declaration.capability_id} does not provide {missing}",
            )
        )
    if claim_kind not in declaration.claim_shapes:
        reasons.append(
            (
                MismatchReason.CLAIM_SHAPE_UNSUPPORTED,
                f"{declaration.capability_id} decides {sorted(k.value for k in declaration.claim_shapes)}, not {claim_kind.value}",
            )
        )
    if not declaration.executable:
        reasons.append((MismatchReason.NOT_EXECUTABLE, f"{declaration.capability_id} has no executor in this registry"))
    return CapabilityMatch(declaration.capability_id, not reasons, tuple(reasons))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class CapabilityRegistry:
    """An immutable, indexed set of capability declarations.

    Instance-based, like the Core's model and realization registries: there is
    no module-level singleton, so a test, a campaign or a second product can
    hold its own. Built once from a tuple of declarations; queries are dict
    lookups, so routing never walks or imports the repository per request.
    """

    def __init__(self, declarations: Iterable[CapabilityDeclaration]) -> None:
        items = tuple(declarations)
        for item in items:
            if not isinstance(item, CapabilityDeclaration):
                raise CapabilityRegistryError(f"registry entries must be CapabilityDeclaration, got {type(item).__name__}")
        ids = [d.capability_id for d in items]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise CapabilityRegistryError(f"duplicate capability ids {duplicates}; one id names one capability")
        self._declarations = tuple(sorted(items, key=lambda d: d.capability_id))
        self._by_id = {d.capability_id: d for d in self._declarations}
        by_quantity: dict[str, list[CapabilityDeclaration]] = {}
        by_capability: dict[ScientificCapability, list[CapabilityDeclaration]] = {}
        for declaration in self._declarations:
            for quantity in declaration.produces:
                by_quantity.setdefault(quantity.name, []).append(declaration)
            for capability in declaration.provided_capabilities:
                by_capability.setdefault(capability, []).append(declaration)
        self._by_quantity = {k: tuple(v) for k, v in by_quantity.items()}
        self._by_capability = {k: tuple(v) for k, v in by_capability.items()}
        self._digest = tagged_digest(_REGISTRY_TAG, [(d.capability_id, d.digest) for d in self._declarations])

    def __len__(self) -> int:
        return len(self._declarations)

    def __iter__(self):
        return iter(self._declarations)

    def __contains__(self, capability_id: object) -> bool:
        return capability_id in self._by_id

    @property
    def declarations(self) -> tuple[CapabilityDeclaration, ...]:
        return self._declarations

    @property
    def digest(self) -> str:
        return self._digest

    def get(self, capability_id: str) -> CapabilityDeclaration:
        try:
            return self._by_id[capability_id]
        except KeyError:
            raise CapabilityRegistryError(
                f"no capability {capability_id!r}; registered: {sorted(self._by_id)}"
            ) from None

    def producing(self, quantity: str) -> tuple[CapabilityDeclaration, ...]:
        return self._by_quantity.get(quantity, ())

    def providing(self, capability: ScientificCapability | str) -> tuple[CapabilityDeclaration, ...]:
        return self._by_capability.get(ScientificCapability.coerce(capability), ())

    def provided_capabilities(self) -> frozenset[ScientificCapability]:
        return frozenset(self._by_capability)

    def produced_quantities(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_quantity))

    def match(
        self,
        *,
        quantity: str,
        dimension: str,
        required: Iterable[ScientificCapability | str] = (),
        claim_kind: ClaimKind,
    ) -> tuple[CapabilityMatch, ...]:
        """Every declaration, matched or not, with the reasons -- in id order."""
        wanted = frozenset(ScientificCapability.coerce(c) for c in required)
        return tuple(
            match_declaration(d, quantity=quantity, dimension=dimension, required=wanted, claim_kind=claim_kind)
            for d in self._declarations
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REGISTRY_SCHEMA,
            "digest": self._digest,
            "capabilities": [d.to_dict() for d in self._declarations],
        }


__all__ = [
    "CAPABILITY_SCHEMA",
    "AttainableLevel",
    "CapabilityDeclaration",
    "CapabilityMatch",
    "CapabilityRegistry",
    "CapabilityRun",
    "InputDeclaration",
    "InstanceReport",
    "InputKind",
    "InputRole",
    "MismatchReason",
    "ModelUse",
    "PerturbableInput",
    "RefinementStudy",
    "ProducedQuantity",
    "ProvidedCapability",
    "RouteDeclaration",
    "RouteKind",
    "SolverUse",
    "UnassessableCondition",
    "UncertaintyCapability",
    "build_case",
    "declared_path",
    "input_problem",
    "inputs_from_case",
    "match_declaration",
]
