"""Generic hierarchical system topology bound to existing scientific authority.

ScientificTwin remains the authority for instance declarations. PhysicsGraph
remains the authority for executable ports and connection semantics. These
records add hierarchy and stable component identity without duplicating either.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics import PhysicsGraph, PortDefinition, PortRef
from ..scientific.ir.constraints import ConstraintDefinition
from ..scientific.serialization import require_schema, schema_string
from ..scientific.twins import ScientificTwin, TwinDatumRole, TwinReference
from ..scientific.units.quantity import Quantity

COMPONENT_DEFINITION_SCHEMA = schema_string("system_component_definition")
COMPONENT_INSTANCE_SCHEMA = schema_string("system_component_instance")
COMPONENT_CONNECTION_SCHEMA = schema_string("system_component_connection")
PARAMETER_BINDING_SCHEMA = schema_string("system_parameter_binding")
STATE_BINDING_SCHEMA = schema_string("system_state_binding")
CONSTRAINT_BINDING_SCHEMA = schema_string("system_constraint_binding")
SYSTEM_DEFINITION_SCHEMA = schema_string("system_definition")


def _text(value: object, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise InvalidScientificProblem(f"{label} must be non-empty")
    return text


@dataclass(frozen=True)
class ComponentDefinition:
    component_id: str
    version: str
    ports: tuple[PortDefinition, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        object.__setattr__(self, "version", _text(self.version, "component version"))
        ports = tuple(self.ports)
        if any(not isinstance(item, PortDefinition) for item in ports):
            raise InvalidScientificProblem("component ports must be PortDefinition records")
        if len({item.port_id for item in ports}) != len(ports):
            raise InvalidScientificProblem("component definition contains duplicate port ids")
        object.__setattr__(self, "ports", tuple(sorted(ports, key=lambda item: item.port_id)))
        object.__setattr__(self, "description", str(self.description).strip())

    @property
    def key(self) -> tuple[str, str]:
        return self.component_id, self.version

    def to_dict(self) -> dict[str, Any]:
        return {"schema": COMPONENT_DEFINITION_SCHEMA, "component_id": self.component_id, "version": self.version, "ports": [item.to_dict() for item in self.ports], "description": self.description}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ComponentDefinition":
        require_schema(payload, COMPONENT_DEFINITION_SCHEMA)
        return cls(payload["component_id"], payload["version"], tuple(PortDefinition.from_dict(item) for item in payload.get("ports", ())), payload.get("description", ""))


@dataclass(frozen=True, order=True)
class ComponentInstance:
    instance_id: str
    definition_id: str
    definition_version: str
    twin: TwinReference
    parent_id: str = ""
    participant_id: str = ""

    def __post_init__(self) -> None:
        for label in ("instance_id", "definition_id", "definition_version"):
            object.__setattr__(self, label, _text(getattr(self, label), label))
        if not isinstance(self.twin, TwinReference):
            raise InvalidScientificProblem("component instance requires TwinReference authority")
        object.__setattr__(self, "parent_id", str(self.parent_id).strip())
        object.__setattr__(self, "participant_id", str(self.participant_id).strip())
        if self.parent_id == self.instance_id:
            raise InvalidScientificProblem("component instance cannot parent itself")

    @property
    def definition_key(self) -> tuple[str, str]:
        return self.definition_id, self.definition_version

    def to_dict(self) -> dict[str, Any]:
        return {"schema": COMPONENT_INSTANCE_SCHEMA, "instance_id": self.instance_id, "definition_id": self.definition_id, "definition_version": self.definition_version, "twin": self.twin.to_dict(), "parent_id": self.parent_id, "participant_id": self.participant_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ComponentInstance":
        require_schema(payload, COMPONENT_INSTANCE_SCHEMA)
        return cls(payload["instance_id"], payload["definition_id"], payload["definition_version"], TwinReference.from_dict(payload["twin"]), payload.get("parent_id", ""), payload.get("participant_id", ""))


@dataclass(frozen=True, order=True)
class ComponentConnection:
    connection_id: str
    edge_id: str
    source_instance_id: str
    source_port_id: str
    target_instance_id: str
    target_port_id: str

    def __post_init__(self) -> None:
        for label in ("connection_id", "edge_id", "source_instance_id", "source_port_id", "target_instance_id", "target_port_id"):
            object.__setattr__(self, label, _text(getattr(self, label), label))
        if self.source_instance_id == self.target_instance_id:
            raise InvalidScientificProblem("component connection must cross instances")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": COMPONENT_CONNECTION_SCHEMA, **{name: getattr(self, name) for name in ("connection_id", "edge_id", "source_instance_id", "source_port_id", "target_instance_id", "target_port_id")}}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ComponentConnection":
        require_schema(payload, COMPONENT_CONNECTION_SCHEMA)
        return cls(*(payload[name] for name in ("connection_id", "edge_id", "source_instance_id", "source_port_id", "target_instance_id", "target_port_id")))


@dataclass(frozen=True, order=True)
class ParameterBinding:
    binding_id: str
    instance_id: str
    twin_datum: str
    target_path: str

    def __post_init__(self) -> None:
        for label in ("binding_id", "instance_id", "twin_datum", "target_path"):
            object.__setattr__(self, label, _text(getattr(self, label), label))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PARAMETER_BINDING_SCHEMA, "binding_id": self.binding_id, "instance_id": self.instance_id, "twin_datum": self.twin_datum, "target_path": self.target_path}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParameterBinding":
        require_schema(payload, PARAMETER_BINDING_SCHEMA)
        return cls(payload["binding_id"], payload["instance_id"], payload["twin_datum"], payload["target_path"])


@dataclass(frozen=True, order=True)
class StateBinding:
    binding_id: str
    instance_id: str
    twin_datum: str
    state_variable_id: str

    def __post_init__(self) -> None:
        for label in ("binding_id", "instance_id", "twin_datum", "state_variable_id"):
            object.__setattr__(self, label, _text(getattr(self, label), label))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": STATE_BINDING_SCHEMA, "binding_id": self.binding_id, "instance_id": self.instance_id, "twin_datum": self.twin_datum, "state_variable_id": self.state_variable_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StateBinding":
        require_schema(payload, STATE_BINDING_SCHEMA)
        return cls(payload["binding_id"], payload["instance_id"], payload["twin_datum"], payload["state_variable_id"])


@dataclass(frozen=True, order=True)
class ConstraintBinding:
    binding_id: str
    instance_id: str
    constraint_id: str

    def __post_init__(self) -> None:
        for label in ("binding_id", "instance_id", "constraint_id"):
            object.__setattr__(self, label, _text(getattr(self, label), label))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CONSTRAINT_BINDING_SCHEMA, "binding_id": self.binding_id, "instance_id": self.instance_id, "constraint_id": self.constraint_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConstraintBinding":
        require_schema(payload, CONSTRAINT_BINDING_SCHEMA)
        return cls(payload["binding_id"], payload["instance_id"], payload["constraint_id"])


@dataclass(frozen=True)
class SystemDefinition:
    system_id: str
    version: str
    definitions: tuple[ComponentDefinition, ...]
    instances: tuple[ComponentInstance, ...]
    connections: tuple[ComponentConnection, ...] = ()
    parameter_bindings: tuple[ParameterBinding, ...] = ()
    state_bindings: tuple[StateBinding, ...] = ()
    constraint_bindings: tuple[ConstraintBinding, ...] = ()
    constraints: tuple[ConstraintDefinition, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "system_id", _text(self.system_id, "system_id"))
        object.__setattr__(self, "version", _text(self.version, "system version"))
        definitions = tuple(self.definitions)
        instances = tuple(self.instances)
        if not definitions or len({item.key for item in definitions}) != len(definitions):
            raise InvalidScientificProblem("system requires unique component definitions")
        if not instances or len({item.instance_id for item in instances}) != len(instances):
            raise InvalidScientificProblem("system requires unique component instances")
        definition_keys = {item.key for item in definitions}
        instance_map = {item.instance_id: item for item in instances}
        for item in instances:
            if item.definition_key not in definition_keys:
                raise InvalidScientificProblem(f"instance {item.instance_id!r} references unknown definition")
            if item.parent_id and item.parent_id not in instance_map:
                raise InvalidScientificProblem(f"instance {item.instance_id!r} references unknown parent")
        for item in instances:
            seen = {item.instance_id}
            cursor = item
            while cursor.parent_id:
                if cursor.parent_id in seen:
                    raise InvalidScientificProblem("component hierarchy contains a cycle")
                seen.add(cursor.parent_id)
                cursor = instance_map[cursor.parent_id]
        self._set_unique("connections", self.connections, ComponentConnection, lambda item: item.connection_id)
        self._set_unique("parameter_bindings", self.parameter_bindings, ParameterBinding, lambda item: item.binding_id)
        self._set_unique("state_bindings", self.state_bindings, StateBinding, lambda item: item.binding_id)
        self._set_unique("constraint_bindings", self.constraint_bindings, ConstraintBinding, lambda item: item.binding_id)
        for connection in self.connections:
            if connection.source_instance_id not in instance_map or connection.target_instance_id not in instance_map:
                raise InvalidScientificProblem("component connection references unknown instance")
            source_instance = instance_map[connection.source_instance_id]
            target_instance = instance_map[connection.target_instance_id]
            source_definition = next(item for item in definitions if item.key == source_instance.definition_key)
            target_definition = next(item for item in definitions if item.key == target_instance.definition_key)
            source_ports = {item.port_id for item in source_definition.ports}
            target_ports = {item.port_id for item in target_definition.ports}
            if connection.source_port_id not in source_ports or connection.target_port_id not in target_ports:
                raise InvalidScientificProblem("component connection references undeclared component port")
        for binding in (*self.parameter_bindings, *self.state_bindings, *self.constraint_bindings):
            if binding.instance_id not in instance_map:
                raise InvalidScientificProblem("system binding references unknown instance")
        constraints = tuple(self.constraints)
        if any(not isinstance(item, ConstraintDefinition) for item in constraints) or len({item.name for item in constraints}) != len(constraints):
            raise InvalidScientificProblem("system constraints must contain unique ConstraintDefinition records")
        constraint_names = {item.name for item in constraints}
        if any(item.constraint_id not in constraint_names for item in self.constraint_bindings):
            raise InvalidScientificProblem("constraint binding references unknown ConstraintDefinition")
        object.__setattr__(self, "constraints", tuple(sorted(constraints, key=lambda item: item.name)))
        object.__setattr__(self, "definitions", tuple(sorted(definitions, key=lambda item: item.key)))
        object.__setattr__(self, "instances", tuple(sorted(instances)))

    def _set_unique(self, name, values, expected, identity) -> None:
        items = tuple(values)
        if any(not isinstance(item, expected) for item in items) or len({identity(item) for item in items}) != len(items):
            raise InvalidScientificProblem(f"{name} must contain unique typed records")
        object.__setattr__(self, name, tuple(sorted(items)))

    def validate_graph(self, graph: PhysicsGraph) -> None:
        if not isinstance(graph, PhysicsGraph):
            raise TypeError("system topology validation requires PhysicsGraph")
        definition_map = {item.key: item for item in self.definitions}
        participant_items = [item for item in self.instances if item.participant_id]
        if len({item.participant_id for item in participant_items}) != len(participant_items):
            raise InvalidScientificProblem("topology maps more than one instance to a PhysicsGraph participant")
        participant_instances = {item.participant_id: item for item in participant_items}
        if set(participant_instances) != {item.participant_id for item in graph.participants}:
            raise InvalidScientificProblem("topology participants must match PhysicsGraph exactly")
        for instance in self.instances:
            if not instance.participant_id:
                continue
            participant = graph.participant(instance.participant_id)
            definition = definition_map[instance.definition_key]
            if tuple(port.to_dict() for port in definition.ports) != tuple(port.to_dict() for port in participant.ports):
                raise InvalidScientificProblem(f"component {instance.instance_id!r} ports differ from PhysicsGraph participant")
        for connection in self.connections:
            edge = graph.edge(connection.edge_id)
            source = participant_instances.get(edge.source.participant_id)
            target = participant_instances.get(edge.target.participant_id)
            if source is None or target is None or (source.instance_id, edge.source.port_id, target.instance_id, edge.target.port_id) != (connection.source_instance_id, connection.source_port_id, connection.target_instance_id, connection.target_port_id):
                raise InvalidScientificProblem(f"connection {connection.connection_id!r} differs from PhysicsGraph edge")
        if len({item.edge_id for item in self.connections}) != len(self.connections):
            raise InvalidScientificProblem("topology maps more than one connection to a PhysicsGraph edge")
        if {item.edge_id for item in self.connections} != {item.edge_id for item in graph.edges}:
            raise InvalidScientificProblem("topology connections must cover PhysicsGraph edges exactly")

    @property
    def unsupported_execution_bindings(self) -> tuple[str, ...]:
        """Declared topology bindings no runtime consumes or enforces.

        Parameter and state bindings left this list in the World Runtime round:
        a parameter binding is delivered to a participant that declares the
        target parameter, and a state binding resolves to the scenario state
        variable a participant declares it initializes from.  Both refuse
        rather than assume when the participant does not declare support.

        Constraint bindings stay, and this is a statement about enforcement
        rather than about the records.  There is no authorized consumer that
        enforces an arbitrary system constraint during coupling, and a binding
        that looked supported would assert an enforcement nothing performs.
        """
        unsupported: list[str] = []
        if self.constraint_bindings or self.constraints:
            unsupported.append("constraint_enforcement")
        return tuple(unsupported)

    def parameter_values(
        self, twins: Mapping[tuple[str, str], ScientificTwin]
    ) -> dict[str, dict[str, Quantity]]:
        """Resolved parameter bindings, grouped by PhysicsGraph participant.

        One authority per target: two bindings naming the same participant
        parameter are refused rather than resolved by order.  An instance that
        maps to no participant cannot deliver a parameter to execution, which
        is also a refusal.
        """
        resolved: dict[str, dict[str, Quantity]] = {}
        instances = {item.instance_id: item for item in self.instances}
        for binding in self.parameter_bindings:
            instance = instances[binding.instance_id]
            if not instance.participant_id:
                raise InvalidScientificProblem(
                    f"parameter binding {binding.binding_id!r} targets instance "
                    f"{instance.instance_id!r}, which maps to no executable "
                    f"participant"
                )
            twin = twins.get(instance.twin.key)
            if twin is None or twin.reference != instance.twin:
                raise InvalidScientificProblem(
                    f"parameter binding {binding.binding_id!r} has no exact "
                    f"ScientificTwin authority"
                )
            datum = twin.declaration(binding.twin_datum)
            if datum.role is not TwinDatumRole.PARAMETER:
                raise InvalidScientificProblem(
                    f"parameter binding {binding.binding_id!r} requires a twin "
                    f"datum declared as a parameter"
                )
            if not isinstance(datum.value, Quantity):
                raise InvalidScientificProblem(
                    f"parameter binding {binding.binding_id!r} reads twin datum "
                    f"{binding.twin_datum!r}, which carries no unit-bearing value"
                )
            targets = resolved.setdefault(instance.participant_id, {})
            if binding.target_path in targets:
                raise InvalidScientificProblem(
                    f"participant {instance.participant_id!r} parameter "
                    f"{binding.target_path!r} is bound by more than one authority"
                )
            targets[binding.target_path] = datum.value
        return resolved

    def state_variable_owners(self) -> dict[str, str]:
        """Which PhysicsGraph participant each bound state variable belongs to.

        A state binding never infers participant support: it says which
        participant a scenario state variable is initialized on, and the
        participant's own declared state schema decides whether it accepts it.
        """
        owners: dict[str, str] = {}
        instances = {item.instance_id: item for item in self.instances}
        for binding in self.state_bindings:
            instance = instances[binding.instance_id]
            if not instance.participant_id:
                raise InvalidScientificProblem(
                    f"state binding {binding.binding_id!r} targets instance "
                    f"{instance.instance_id!r}, which maps to no executable "
                    f"participant"
                )
            existing = owners.get(binding.state_variable_id)
            if existing is not None and existing != instance.participant_id:
                raise InvalidScientificProblem(
                    f"state variable {binding.state_variable_id!r} is bound to "
                    f"both {existing!r} and {instance.participant_id!r}"
                )
            owners[binding.state_variable_id] = instance.participant_id
        return owners

    def validate_against(self, graph: PhysicsGraph, twins: Mapping[tuple[str, str], ScientificTwin]) -> None:
        self.validate_graph(graph)
        for instance in self.instances:
            twin = twins.get(instance.twin.key)
            if twin is None or twin.reference != instance.twin:
                raise InvalidScientificProblem(f"instance {instance.instance_id!r} has no exact ScientificTwin authority")
        for binding in (*self.parameter_bindings, *self.state_bindings):
            instance = next(item for item in self.instances if item.instance_id == binding.instance_id)
            twin = twins[instance.twin.key]
            datum = twin.declaration(binding.twin_datum)
            expected_role = (
                TwinDatumRole.PARAMETER
                if isinstance(binding, ParameterBinding)
                else TwinDatumRole.STATE
            )
            if datum.role is not expected_role:
                raise InvalidScientificProblem(
                    f"binding {binding.binding_id!r} requires twin datum role "
                    f"{expected_role.value}, got {datum.role.value}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SYSTEM_DEFINITION_SCHEMA, "system_id": self.system_id, "version": self.version, "definitions": [item.to_dict() for item in self.definitions], "instances": [item.to_dict() for item in self.instances], "connections": [item.to_dict() for item in self.connections], "parameter_bindings": [item.to_dict() for item in self.parameter_bindings], "state_bindings": [item.to_dict() for item in self.state_bindings], "constraint_bindings": [item.to_dict() for item in self.constraint_bindings], "constraints": [item.to_dict() for item in self.constraints]}

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SystemDefinition":
        require_schema(payload, SYSTEM_DEFINITION_SCHEMA)
        return cls(payload["system_id"], payload["version"], tuple(ComponentDefinition.from_dict(item) for item in payload["definitions"]), tuple(ComponentInstance.from_dict(item) for item in payload["instances"]), tuple(ComponentConnection.from_dict(item) for item in payload.get("connections", ())), tuple(ParameterBinding.from_dict(item) for item in payload.get("parameter_bindings", ())), tuple(StateBinding.from_dict(item) for item in payload.get("state_bindings", ())), tuple(ConstraintBinding.from_dict(item) for item in payload.get("constraint_bindings", ())), tuple(ConstraintDefinition.from_dict(item) for item in payload.get("constraints", ())))
