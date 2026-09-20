"""Typed engineering intent: the user problem a scientific planner may trust.

An LLM may draft this record but it cannot place model, realization, solver,
graph, validation verdict or result authority in it. Missing information is
derived downstream by deterministic validation/planning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Mapping

from ..claims._records import tagged_digest
from ..scientific.capabilities import ScientificCapability, scientific_capabilities
from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.constraints import ConstraintDefinition
from ..scientific.ir.values import ScientificValue, decode_value, encode_value, require_scientific_value
from ..scientific.results.immutable import freeze
from ..scientific.results.validation import ValidationLevel
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity, dimensionality
from ..sria.uncertainty import UncertaintyChannel

ENGINEERING_INTENT_SCHEMA = schema_string("engineering_intent")
CONTEXT_SCHEMA = schema_string("engineering_context_of_use")
COMPONENT_SCHEMA = schema_string("engineering_component")
INTERFACE_SCHEMA = schema_string("engineering_interface")
EXCHANGE_SCHEMA = schema_string("engineering_interface_exchange")
FACT_SCHEMA = schema_string("engineering_intent_fact")
QOI_SCHEMA = schema_string("engineering_intent_qoi")
QOI_CONSTRAINT_SCHEMA = schema_string("engineering_qoi_constraint")
OBJECTIVE_SCHEMA = schema_string("engineering_objective")
FIDELITY_REQUEST_SCHEMA = schema_string("engineering_fidelity_request")
COMPUTE_BUDGET_SCHEMA = schema_string("engineering_compute_budget")

_IDENTITY_TAG = "forge.engineering_intent.identity/1"
_RECORD_TAG = "forge.engineering_intent.record/1"
_IDENTIFIER = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.:-]*$")
_PATH_SEGMENT = r"[a-zA-Z_][a-zA-Z0-9_]*(?:\[\d+\])?"
_PATH = re.compile(rf"^{_PATH_SEGMENT}(?:\.{_PATH_SEGMENT})*$")


def _text(value: Any, label: str) -> str:
    value = str(value).strip()
    if not value:
        raise InvalidScientificProblem(f"{label} must be non-empty")
    return value


def _id(value: Any, label: str) -> str:
    value = _text(value, label)
    if not _IDENTIFIER.match(value):
        raise InvalidScientificProblem(f"{label} {value!r} is not a stable identifier")
    return value


def _path(value: Any, label: str) -> str:
    value = _text(value, label)
    if not _PATH.match(value):
        raise InvalidScientificProblem(
            f"{label} {value!r} must be a dotted concrete path; arrays use numeric indices"
        )
    return value


def _reject_unknown_keys(
    payload: Mapping[str, Any],
    allowed: frozenset[str],
    label: str,
) -> None:
    extra = sorted(set(payload) - allowed)
    if extra:
        raise InvalidScientificProblem(
            f"{label} contains unknown fields {extra}; canonical contracts "
            "refuse undeclared data rather than silently ignoring it"
        )


def _unit(value: Any, label: str) -> str:
    value = _text(value, label)
    try:
        dimensionality(value)
    except Exception as exc:
        raise InvalidScientificProblem(f"{label} {value!r} is not a valid unit") from exc
    return value


def _identity_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _identity_payload(child)
            for key, child in sorted(value.items())
            if key not in {"description", "statement"}
        }
    if isinstance(value, list):
        return [_identity_payload(child) for child in value]
    return value


class FactRole(str, Enum):
    PARAMETER = "parameter"
    INITIAL_CONDITION = "initial_condition"
    BOUNDARY_CONDITION = "boundary_condition"
    OPERATING_CONDITION = "operating_condition"
    GEOMETRY = "geometry"
    MATERIAL = "material"
    APPLICABILITY = "applicability"
    IDENTITY = "identity"


class ObjectiveKind(str, Enum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"
    TARGET = "target"


@dataclass(frozen=True)
class ContextOfUse:
    decision: str
    application: str
    consequence_if_wrong: str
    required_levels: tuple[ValidationLevel, ...] = ()
    required_uncertainty: tuple[UncertaintyChannel, ...] = ()
    required_capabilities: frozenset[ScientificCapability] = frozenset()
    require_independent_verification: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", _text(self.decision, "context.decision"))
        object.__setattr__(self, "application", _text(self.application, "context.application"))
        object.__setattr__(self, "consequence_if_wrong", _text(self.consequence_if_wrong, "context.consequence_if_wrong"))
        levels = tuple(ValidationLevel(x) for x in self.required_levels)
        channels = tuple(UncertaintyChannel(x) for x in self.required_uncertainty)
        if len(levels) != len(set(levels)) or len(channels) != len(set(channels)):
            raise InvalidScientificProblem("context evidence/uncertainty requirements must be unique")
        if not isinstance(self.require_independent_verification, bool):
            raise InvalidScientificProblem("require_independent_verification must be boolean")
        object.__setattr__(self, "required_levels", tuple(sorted(levels, key=lambda x: x.value)))
        object.__setattr__(self, "required_uncertainty", tuple(sorted(channels, key=lambda x: x.value)))
        object.__setattr__(self, "required_capabilities", scientific_capabilities(self.required_capabilities))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONTEXT_SCHEMA,
            "decision": self.decision,
            "application": self.application,
            "consequence_if_wrong": self.consequence_if_wrong,
            "required_levels": [x.value for x in self.required_levels],
            "required_uncertainty": [x.value for x in self.required_uncertainty],
            "required_capabilities": sorted(x.identifier for x in self.required_capabilities),
            "require_independent_verification": self.require_independent_verification,
        }

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "ContextOfUse":
        require_schema(p, CONTEXT_SCHEMA)
        _reject_unknown_keys(
            p,
            frozenset({
                "schema", "decision", "application", "consequence_if_wrong",
                "required_levels", "required_uncertainty",
                "required_capabilities", "require_independent_verification",
            }),
            "engineering context",
        )
        return cls(
            p["decision"], p["application"], p["consequence_if_wrong"],
            tuple(p.get("required_levels", ())),
            tuple(p.get("required_uncertainty", ())),
            frozenset(p.get("required_capabilities", ())),
            p.get("require_independent_verification", False),
        )


@dataclass(frozen=True)
class EngineeringComponent:
    component_id: str
    kind: str
    required_capabilities: frozenset[ScientificCapability] = frozenset()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _id(self.component_id, "component_id"))
        object.__setattr__(self, "kind", _id(self.kind, f"component {self.component_id}.kind"))
        object.__setattr__(self, "required_capabilities", scientific_capabilities(self.required_capabilities))
        object.__setattr__(self, "description", str(self.description).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COMPONENT_SCHEMA,
            "component_id": self.component_id,
            "kind": self.kind,
            "required_capabilities": sorted(x.identifier for x in self.required_capabilities),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "EngineeringComponent":
        require_schema(p, COMPONENT_SCHEMA)
        _reject_unknown_keys(
            p,
            frozenset({
                "schema", "component_id", "kind",
                "required_capabilities", "description",
            }),
            "engineering component",
        )
        return cls(p["component_id"], p["kind"], frozenset(p.get("required_capabilities", ())), p.get("description", ""))


@dataclass(frozen=True)
class InterfaceExchange:
    quantity: str
    unit_exemplar: str
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", _id(self.quantity, "exchange.quantity"))
        object.__setattr__(self, "unit_exemplar", _unit(self.unit_exemplar, "exchange.unit_exemplar"))
        object.__setattr__(self, "description", str(self.description).strip())

    @property
    def dimension(self) -> str:
        return dimensionality(self.unit_exemplar)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXCHANGE_SCHEMA,
            "quantity": self.quantity,
            "unit_exemplar": self.unit_exemplar,
            "dimension": self.dimension,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "InterfaceExchange":
        require_schema(p, EXCHANGE_SCHEMA)
        _reject_unknown_keys(
            p,
            frozenset({
                "schema", "quantity", "unit_exemplar",
                "dimension", "description",
            }),
            "engineering interface exchange",
        )
        made = cls(p["quantity"], p["unit_exemplar"], p.get("description", ""))
        if p.get("dimension", made.dimension) != made.dimension:
            raise InvalidScientificProblem("serialized exchange dimension disagrees with its unit")
        return made


@dataclass(frozen=True)
class EngineeringInterface:
    interface_id: str
    source_component: str
    target_component: str
    exchanges: tuple[InterfaceExchange, ...]
    bidirectional: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "interface_id", _id(self.interface_id, "interface_id"))
        object.__setattr__(self, "source_component", _id(self.source_component, "interface.source_component"))
        object.__setattr__(self, "target_component", _id(self.target_component, "interface.target_component"))
        if self.source_component == self.target_component:
            raise InvalidScientificProblem("engineering interface must connect distinct components")
        items = tuple(self.exchanges)
        if not items or any(not isinstance(x, InterfaceExchange) for x in items):
            raise InvalidScientificProblem("engineering interface requires typed exchanges")
        if not isinstance(self.bidirectional, bool):
            raise InvalidScientificProblem("interface.bidirectional must be boolean")
        object.__setattr__(self, "exchanges", tuple(sorted(items, key=lambda x: (x.quantity, x.unit_exemplar))))
        object.__setattr__(self, "description", str(self.description).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": INTERFACE_SCHEMA,
            "interface_id": self.interface_id,
            "source_component": self.source_component,
            "target_component": self.target_component,
            "exchanges": [x.to_dict() for x in self.exchanges],
            "bidirectional": self.bidirectional,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "EngineeringInterface":
        require_schema(p, INTERFACE_SCHEMA)
        _reject_unknown_keys(
            p,
            frozenset({
                "schema", "interface_id", "source_component",
                "target_component", "exchanges", "bidirectional",
                "description",
            }),
            "engineering interface",
        )
        return cls(
            p["interface_id"], p["source_component"], p["target_component"],
            tuple(InterfaceExchange.from_dict(x) for x in p["exchanges"]),
            p.get("bidirectional", False), p.get("description", ""),
        )


@dataclass(frozen=True)
class IntentFact:
    path: str
    role: FactRole
    value: ScientificValue
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _path(self.path, "fact.path"))
        object.__setattr__(self, "role", FactRole(self.role))
        require_scientific_value(self.value, context=f"intent fact {self.path}")
        object.__setattr__(self, "description", str(self.description).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FACT_SCHEMA,
            "path": self.path,
            "role": self.role.value,
            "value": encode_value(self.value),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "IntentFact":
        require_schema(p, FACT_SCHEMA)
        _reject_unknown_keys(
            p,
            frozenset({"schema", "path", "role", "value", "description"}),
            "engineering intent fact",
        )
        return cls(p["path"], FactRole(p["role"]), decode_value(p["value"]), p.get("description", ""))


@dataclass(frozen=True)
class IntentQuantityOfInterest:
    qoi_id: str
    name: str
    unit: str
    subject: str | None = None
    qualifiers: Mapping[str, str] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "qoi_id", _id(self.qoi_id, "qoi_id"))
        object.__setattr__(self, "name", _id(self.name, f"qoi {self.qoi_id}.name"))
        object.__setattr__(self, "unit", _unit(self.unit, f"qoi {self.qoi_id}.unit"))
        if self.subject is not None:
            object.__setattr__(self, "subject", _id(self.subject, f"qoi {self.qoi_id}.subject"))
        clean = {_id(k, "qoi qualifier"): _text(v, f"qoi qualifier {k}") for k, v in dict(self.qualifiers).items()}
        object.__setattr__(self, "qualifiers", freeze(clean))
        object.__setattr__(self, "description", str(self.description).strip())

    @property
    def dimension(self) -> str:
        return dimensionality(self.unit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": QOI_SCHEMA,
            "qoi_id": self.qoi_id,
            "name": self.name,
            "unit": self.unit,
            "dimension": self.dimension,
            "subject": self.subject,
            "qualifiers": dict(sorted(self.qualifiers.items())),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "IntentQuantityOfInterest":
        require_schema(p, QOI_SCHEMA)
        _reject_unknown_keys(
            p,
            frozenset({
                "schema", "qoi_id", "name", "unit", "dimension",
                "subject", "qualifiers", "description",
            }),
            "engineering quantity of interest",
        )
        made = cls(p["qoi_id"], p["name"], p["unit"], p.get("subject"), dict(p.get("qualifiers", {})), p.get("description", ""))
        if p.get("dimension", made.dimension) != made.dimension:
            raise InvalidScientificProblem(f"qoi {made.qoi_id!r} dimension disagrees with its unit")
        return made


@dataclass(frozen=True)
class QOIConstraint:
    qoi_id: str
    constraint: ConstraintDefinition

    def __post_init__(self) -> None:
        object.__setattr__(self, "qoi_id", _id(self.qoi_id, "constraint.qoi_id"))
        if not isinstance(self.constraint, ConstraintDefinition):
            raise InvalidScientificProblem("QOIConstraint requires ConstraintDefinition")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": QOI_CONSTRAINT_SCHEMA, "qoi_id": self.qoi_id, "constraint": self.constraint.to_dict()}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "QOIConstraint":
        require_schema(p, QOI_CONSTRAINT_SCHEMA)
        _reject_unknown_keys(
            p,
            frozenset({"schema", "qoi_id", "constraint"}),
            "engineering qoi constraint",
        )
        return cls(p["qoi_id"], ConstraintDefinition.from_dict(p["constraint"]))


@dataclass(frozen=True)
class EngineeringObjective:
    objective_id: str
    qoi_id: str
    kind: ObjectiveKind
    target: Quantity | None = None
    weight: float = 1.0
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "objective_id", _id(self.objective_id, "objective_id"))
        object.__setattr__(self, "qoi_id", _id(self.qoi_id, "objective.qoi_id"))
        object.__setattr__(self, "kind", ObjectiveKind(self.kind))
        if self.kind is ObjectiveKind.TARGET and not isinstance(self.target, Quantity):
            raise InvalidScientificProblem("target objective requires a Quantity target")
        if self.kind is not ObjectiveKind.TARGET and self.target is not None:
            raise InvalidScientificProblem("only target objectives may carry a target")
        weight = float(self.weight)
        if not 0.0 < weight < float("inf"):
            raise InvalidScientificProblem("objective weight must be finite and positive")
        object.__setattr__(self, "weight", weight)
        object.__setattr__(self, "description", str(self.description).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": OBJECTIVE_SCHEMA,
            "objective_id": self.objective_id,
            "qoi_id": self.qoi_id,
            "kind": self.kind.value,
            "target": None if self.target is None else self.target.to_dict(),
            "weight": self.weight,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "EngineeringObjective":
        require_schema(p, OBJECTIVE_SCHEMA)
        _reject_unknown_keys(
            p,
            frozenset({
                "schema", "objective_id", "qoi_id", "kind",
                "target", "weight", "description",
            }),
            "engineering objective",
        )
        target = p.get("target")
        return cls(p["objective_id"], p["qoi_id"], ObjectiveKind(p["kind"]), None if target is None else Quantity.from_dict(target), p.get("weight", 1.0), p.get("description", ""))


@dataclass(frozen=True)
class FidelityRequest:
    ladder_id: str
    ladder_version: str
    minimum_rung: str | None = None
    preferred_rung: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ladder_id", _id(self.ladder_id, "fidelity.ladder_id"))
        object.__setattr__(self, "ladder_version", _text(self.ladder_version, "fidelity.ladder_version"))
        for label in ("minimum_rung", "preferred_rung"):
            value = getattr(self, label)
            if value is not None:
                object.__setattr__(self, label, _id(value, f"fidelity.{label}"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIDELITY_REQUEST_SCHEMA,
            "ladder_id": self.ladder_id,
            "ladder_version": self.ladder_version,
            "minimum_rung": self.minimum_rung,
            "preferred_rung": self.preferred_rung,
        }

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "FidelityRequest":
        require_schema(p, FIDELITY_REQUEST_SCHEMA)
        _reject_unknown_keys(
            p,
            frozenset({
                "schema", "ladder_id", "ladder_version",
                "minimum_rung", "preferred_rung",
            }),
            "engineering fidelity request",
        )
        return cls(p["ladder_id"], p["ladder_version"], p.get("minimum_rung"), p.get("preferred_rung"))


@dataclass(frozen=True)
class ComputeBudget:
    max_wall_time: Quantity | None = None
    max_solver_calls: int | None = None

    def __post_init__(self) -> None:
        if self.max_wall_time is not None:
            if not isinstance(self.max_wall_time, Quantity) or self.max_wall_time.dimensionality != dimensionality("second"):
                raise InvalidScientificProblem("compute max_wall_time must be a time Quantity")
            if self.max_wall_time.magnitude_in("second") <= 0.0:
                raise InvalidScientificProblem("compute max_wall_time must be positive")
            object.__setattr__(self, "max_wall_time", self.max_wall_time.to("second"))
        if self.max_solver_calls is not None and (
            isinstance(self.max_solver_calls, bool)
            or not isinstance(self.max_solver_calls, int)
            or self.max_solver_calls < 1
        ):
            raise InvalidScientificProblem("max_solver_calls must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COMPUTE_BUDGET_SCHEMA,
            "max_wall_time": None if self.max_wall_time is None else self.max_wall_time.to_dict(),
            "max_solver_calls": self.max_solver_calls,
        }

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "ComputeBudget":
        require_schema(p, COMPUTE_BUDGET_SCHEMA)
        _reject_unknown_keys(
            p,
            frozenset({"schema", "max_wall_time", "max_solver_calls"}),
            "engineering compute budget",
        )
        wall = p.get("max_wall_time")
        return cls(None if wall is None else Quantity.from_dict(wall), p.get("max_solver_calls"))


@dataclass(frozen=True)
class EngineeringIntent:
    statement: str
    context: ContextOfUse
    components: tuple[EngineeringComponent, ...]
    interfaces: tuple[EngineeringInterface, ...]
    facts: tuple[IntentFact, ...]
    qois: tuple[IntentQuantityOfInterest, ...]
    constraints: tuple[QOIConstraint, ...] = ()
    objectives: tuple[EngineeringObjective, ...] = ()
    required_capabilities: frozenset[ScientificCapability] = frozenset()
    fidelity: FidelityRequest | None = None
    compute_budget: ComputeBudget = ComputeBudget()

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", _text(self.statement, "intent.statement"))
        if not isinstance(self.context, ContextOfUse):
            raise InvalidScientificProblem("EngineeringIntent requires ContextOfUse")
        definitions = (
            ("components", EngineeringComponent, lambda x: x.component_id),
            ("interfaces", EngineeringInterface, lambda x: x.interface_id),
            ("facts", IntentFact, lambda x: x.path),
            ("qois", IntentQuantityOfInterest, lambda x: x.qoi_id),
            ("constraints", QOIConstraint, lambda x: x.constraint.name),
            ("objectives", EngineeringObjective, lambda x: x.objective_id),
        )
        for label, kind, key in definitions:
            values = tuple(getattr(self, label))
            if any(not isinstance(item, kind) for item in values):
                raise InvalidScientificProblem(f"intent {label} must be {kind.__name__} records")
            keys = [key(item) for item in values]
            if len(keys) != len(set(keys)):
                raise InvalidScientificProblem(f"intent {label} contains duplicate identities")
            object.__setattr__(self, label, tuple(sorted(values, key=key)))
        if not self.components or not self.qois:
            raise InvalidScientificProblem("engineering intent requires components and quantities of interest")

        component_ids = {x.component_id for x in self.components}
        for interface in self.interfaces:
            missing = {interface.source_component, interface.target_component} - component_ids
            if missing:
                raise InvalidScientificProblem(f"interface {interface.interface_id!r} references unknown components {sorted(missing)}")
        qois = {x.qoi_id: x for x in self.qois}
        for qoi in self.qois:
            if qoi.subject is not None and qoi.subject not in component_ids:
                raise InvalidScientificProblem(f"qoi {qoi.qoi_id!r} references unknown subject {qoi.subject!r}")
        for item in self.constraints:
            qoi = qois.get(item.qoi_id)
            if qoi is None:
                raise InvalidScientificProblem(f"constraint references unknown qoi {item.qoi_id!r}")
            if item.constraint.metric != qoi.name or item.constraint.bound.dimensionality != qoi.dimension:
                raise InvalidScientificProblem(f"constraint {item.constraint.name!r} disagrees with qoi {qoi.qoi_id!r}")
        for objective in self.objectives:
            qoi = qois.get(objective.qoi_id)
            if qoi is None:
                raise InvalidScientificProblem(f"objective references unknown qoi {objective.qoi_id!r}")
            if objective.target is not None and objective.target.dimensionality != qoi.dimension:
                raise InvalidScientificProblem(f"objective {objective.objective_id!r} target dimension differs from qoi")
        if self.fidelity is not None and not isinstance(self.fidelity, FidelityRequest):
            raise InvalidScientificProblem("intent fidelity must be FidelityRequest")
        if not isinstance(self.compute_budget, ComputeBudget):
            raise InvalidScientificProblem("intent compute_budget must be ComputeBudget")
        object.__setattr__(self, "required_capabilities", scientific_capabilities(self.required_capabilities))

    @property
    def fact_map(self) -> Mapping[str, ScientificValue]:
        return freeze({x.path: x.value for x in self.facts})

    def qoi(self, qoi_id: str) -> IntentQuantityOfInterest:
        for item in self.qois:
            if item.qoi_id == qoi_id:
                return item
        raise InvalidScientificProblem(f"intent has no qoi {qoi_id!r}")

    def component(self, component_id: str) -> EngineeringComponent:
        for item in self.components:
            if item.component_id == component_id:
                return item
        raise InvalidScientificProblem(f"intent has no component {component_id!r}")

    def required_for(self, qoi: IntentQuantityOfInterest) -> frozenset[ScientificCapability]:
        required = set(self.required_capabilities) | set(self.context.required_capabilities)
        if qoi.subject is not None:
            required |= set(self.component(qoi.subject).required_capabilities)
        return frozenset(required)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_INTENT_SCHEMA,
            "statement": self.statement,
            "context": self.context.to_dict(),
            "components": [x.to_dict() for x in self.components],
            "interfaces": [x.to_dict() for x in self.interfaces],
            "facts": [x.to_dict() for x in self.facts],
            "qois": [x.to_dict() for x in self.qois],
            "constraints": [x.to_dict() for x in self.constraints],
            "objectives": [x.to_dict() for x in self.objectives],
            "required_capabilities": sorted(x.identifier for x in self.required_capabilities),
            "fidelity": None if self.fidelity is None else self.fidelity.to_dict(),
            "compute_budget": self.compute_budget.to_dict(),
        }

    @property
    def identity_digest(self) -> str:
        return tagged_digest(_IDENTITY_TAG, _identity_payload(self.to_dict()))

    @property
    def record_digest(self) -> str:
        return tagged_digest(_RECORD_TAG, self.to_dict())

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "EngineeringIntent":
        require_schema(p, ENGINEERING_INTENT_SCHEMA)
        _reject_unknown_keys(
            p,
            frozenset({
                "schema", "statement", "context", "components", "interfaces",
                "facts", "qois", "constraints", "objectives",
                "required_capabilities", "fidelity", "compute_budget",
            }),
            "engineering intent",
        )
        fidelity = p.get("fidelity")
        return cls(
            statement=p["statement"],
            context=ContextOfUse.from_dict(p["context"]),
            components=tuple(EngineeringComponent.from_dict(x) for x in p["components"]),
            interfaces=tuple(EngineeringInterface.from_dict(x) for x in p.get("interfaces", ())),
            facts=tuple(IntentFact.from_dict(x) for x in p.get("facts", ())),
            qois=tuple(IntentQuantityOfInterest.from_dict(x) for x in p["qois"]),
            constraints=tuple(QOIConstraint.from_dict(x) for x in p.get("constraints", ())),
            objectives=tuple(EngineeringObjective.from_dict(x) for x in p.get("objectives", ())),
            required_capabilities=frozenset(p.get("required_capabilities", ())),
            fidelity=None if fidelity is None else FidelityRequest.from_dict(fidelity),
            compute_budget=ComputeBudget.from_dict(p.get("compute_budget", {"schema": COMPUTE_BUDGET_SCHEMA})),
        )


__all__ = [
    "COMPUTE_BUDGET_SCHEMA", "COMPONENT_SCHEMA", "CONTEXT_SCHEMA",
    "ENGINEERING_INTENT_SCHEMA", "EXCHANGE_SCHEMA", "FACT_SCHEMA",
    "FIDELITY_REQUEST_SCHEMA", "INTERFACE_SCHEMA", "OBJECTIVE_SCHEMA",
    "QOI_CONSTRAINT_SCHEMA", "QOI_SCHEMA", "ComputeBudget", "ContextOfUse",
    "EngineeringComponent", "EngineeringIntent", "EngineeringInterface",
    "EngineeringObjective", "FactRole", "FidelityRequest", "IntentFact",
    "IntentQuantityOfInterest", "InterfaceExchange", "ObjectiveKind",
    "QOIConstraint",
]
