"""The canonical, content-bound request for one system run.

A request holds *references by content digest* to the heavy scientific records (system, scenario,
timeline, environment, material states) plus everything else a run depends on stated explicitly:
initial state, requested observables, provider selections (id + version [+ digest]), model
selections, the declared execution nodes, constraint observations and the execution profile.
The referenced objects are supplied at preflight/execution time and their digests are verified, so
a request can neither silently point at different content nor be built from a label alone.

Identity (``digest``) covers every scientifically relevant item.  It excludes the caller's request
label, the operational context (workspace hint, resource budget) and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..execution.orchestration.resources import ResourceBudget
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity
from ._common import digest_of, hex64, identifier, reject_non_finite, require_schema, schema, strict_keys, text, unique
from .state import InitialStateSpec

CONTENT_REF_SCHEMA = schema("content_ref")
PROVIDER_BINDING_SCHEMA = schema("provider_binding")
AUTHORITY_REF_SCHEMA = schema("authority_ref")
NODE_INPUT_SCHEMA = schema("node_input")
LITERAL_INPUT_SCHEMA = schema("literal_input")
NODE_OUTPUT_SCHEMA = schema("node_output_spec")
MATERIAL_REF_SCHEMA = schema("material_property_ref")
ENVIRONMENT_REQ_SCHEMA = schema("environment_requirement")
NODE_SPEC_SCHEMA = schema("node_spec")
OBSERVABLE_SCHEMA = schema("requested_observable")
CONSTRAINT_OBS_SCHEMA = schema("constraint_observation")
MODEL_SELECTION_SCHEMA = schema("model_selection")
PROFILE_SCHEMA = schema("execution_profile")
OPERATIONAL_SCHEMA = schema("operational_context")
REQUEST_SCHEMA = schema("system_run_request")

REF_KINDS = ("system", "scenario", "timeline", "environment", "material_state")
MODES = ("lifecycle", "multiphysics", "multiscale")
CACHE_POLICIES = ("off", "exact")


class NodeKind(str, Enum):
    RESOLVE_MATERIAL = "resolve_material"
    EVALUATE_ENVIRONMENT = "evaluate_environment"
    PROVIDER_EXECUTION = "provider_execution"
    NUMERICAL_EXECUTION = "numerical_execution"
    PDE_EXECUTION = "pde_execution"
    MAP_FIELD = "map_field"
    MULTIPHYSICS_EXECUTION = "multiphysics_execution"
    AGGREGATE = "aggregate"
    LIFECYCLE_TRANSITION = "lifecycle_transition"
    MULTISCALE_EXECUTION = "multiscale_execution"
    CONSTRAINT_ASSESSMENT = "constraint_assessment"
    CONSERVATION_ASSESSMENT = "conservation_assessment"
    CHECKPOINT = "checkpoint"
    RESULT_NORMALIZATION = "result_normalization"


#: Kinds the planner derives itself; a caller cannot declare them.
DERIVED_KINDS = (NodeKind.RESOLVE_MATERIAL, NodeKind.EVALUATE_ENVIRONMENT, NodeKind.CONSTRAINT_ASSESSMENT)
#: Kind -> the declared mode it requires.
KIND_MODE = {NodeKind.MULTIPHYSICS_EXECUTION: "multiphysics", NodeKind.MULTISCALE_EXECUTION: "multiscale",
             NodeKind.LIFECYCLE_TRANSITION: "lifecycle"}


def _unit_dimension(unit: str, label: str) -> str:
    try:
        return Quantity(1.0, unit).dimensionality
    except Exception as exc:  # unit parse failures are refusals, never coerced
        raise InvalidScientificProblem(f"{label}: unit {unit!r} is not a valid unit ({exc})") from exc


@dataclass(frozen=True, order=True)
class ContentRef:
    """A reference to a scientific record by content digest."""

    kind: str
    ref_id: str
    digest: str

    def __post_init__(self) -> None:
        if self.kind not in REF_KINDS:
            raise InvalidScientificProblem(f"content reference kind must be one of {REF_KINDS}, got {self.kind!r}")
        object.__setattr__(self, "ref_id", identifier(self.ref_id, "content reference id"))
        object.__setattr__(self, "digest", hex64(self.digest, f"{self.kind} digest"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CONTENT_REF_SCHEMA, "kind": self.kind, "ref_id": self.ref_id, "digest": self.digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContentRef":
        require_schema(payload, CONTENT_REF_SCHEMA)
        strict_keys(payload, {"schema", "kind", "ref_id", "digest"}, "content ref")
        return cls(payload["kind"], payload["ref_id"], payload["digest"])


@dataclass(frozen=True, order=True)
class ProviderBinding:
    """An explicit provider selection.  Version is required; a digest pins the exact build."""

    binding_id: str
    provider_id: str
    provider_version: str
    provider_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_id", identifier(self.binding_id, "provider binding id"))
        object.__setattr__(self, "provider_id", identifier(self.provider_id, "provider id"))
        object.__setattr__(self, "provider_version", text(self.provider_version, "provider version"))
        object.__setattr__(self, "provider_digest", hex64(self.provider_digest, "provider digest", allow_empty=True))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROVIDER_BINDING_SCHEMA, "binding_id": self.binding_id, "provider_id": self.provider_id,
                "provider_version": self.provider_version, "provider_digest": self.provider_digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProviderBinding":
        require_schema(payload, PROVIDER_BINDING_SCHEMA)
        strict_keys(payload, {"schema", "binding_id", "provider_id", "provider_version", "provider_digest"}, "provider binding")
        return cls(payload["binding_id"], payload["provider_id"], payload["provider_version"], payload["provider_digest"])


@dataclass(frozen=True, order=True)
class AuthorityRef:
    """Which execution authority a node delegates to, pinned by its identity digest."""

    authority_id: str
    kind: str
    identity_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "authority_id", identifier(self.authority_id, "authority id"))
        object.__setattr__(self, "kind", identifier(self.kind, "authority kind"))
        object.__setattr__(self, "identity_digest", hex64(self.identity_digest, "authority identity digest"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": AUTHORITY_REF_SCHEMA, "authority_id": self.authority_id, "kind": self.kind, "identity_digest": self.identity_digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AuthorityRef":
        require_schema(payload, AUTHORITY_REF_SCHEMA)
        strict_keys(payload, {"schema", "authority_id", "kind", "identity_digest"}, "authority ref")
        return cls(payload["authority_id"], payload["kind"], payload["identity_digest"])


@dataclass(frozen=True, order=True)
class NodeInput:
    name: str
    source_node: str
    source_output: str
    unit: str

    def __post_init__(self) -> None:
        for label in ("name", "source_node", "source_output"):
            object.__setattr__(self, label, identifier(getattr(self, label), f"node input {label}"))
        _unit_dimension(self.unit, f"node input {self.name!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": NODE_INPUT_SCHEMA, "name": self.name, "source_node": self.source_node, "source_output": self.source_output, "unit": self.unit}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NodeInput":
        require_schema(payload, NODE_INPUT_SCHEMA)
        strict_keys(payload, {"schema", "name", "source_node", "source_output", "unit"}, "node input")
        return cls(payload["name"], payload["source_node"], payload["source_output"], payload["unit"])


@dataclass(frozen=True)
class LiteralInput:
    """A value the request itself states.  Its uncertainty is stated too (UNKNOWN is a statement)."""

    name: str
    value: Quantity
    uncertainty: Uncertainty

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", identifier(self.name, "literal input name"))
        if not isinstance(self.value, Quantity) or not isinstance(self.uncertainty, Uncertainty):
            raise InvalidScientificProblem("a literal input needs a Quantity and an explicit Uncertainty (Uncertainty.unknown() is explicit)")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": LITERAL_INPUT_SCHEMA, "name": self.name, "value": self.value.to_dict(), "uncertainty": self.uncertainty.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LiteralInput":
        require_schema(payload, LITERAL_INPUT_SCHEMA)
        strict_keys(payload, {"schema", "name", "value", "uncertainty"}, "literal input")
        return cls(payload["name"], Quantity.from_dict(payload["value"]), Uncertainty.from_dict(payload["uncertainty"]))


@dataclass(frozen=True, order=True)
class NodeOutputSpec:
    name: str
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", identifier(self.name, "node output name"))
        _unit_dimension(self.unit, f"node output {self.name!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": NODE_OUTPUT_SCHEMA, "name": self.name, "unit": self.unit}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NodeOutputSpec":
        require_schema(payload, NODE_OUTPUT_SCHEMA)
        strict_keys(payload, {"schema", "name", "unit"}, "node output spec")
        return cls(payload["name"], payload["unit"])


@dataclass(frozen=True, order=True)
class MaterialPropertyRef:
    """A resolved material property a node consumes, bound by the ResolvedProperty digest."""

    alias: str
    owner_id: str
    property_id: str
    resolved_digest: str
    unit: str

    def __post_init__(self) -> None:
        for label in ("alias", "owner_id", "property_id"):
            object.__setattr__(self, label, identifier(getattr(self, label), f"material ref {label}"))
        object.__setattr__(self, "resolved_digest", hex64(self.resolved_digest, "resolved property digest"))
        _unit_dimension(self.unit, f"material ref {self.alias!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MATERIAL_REF_SCHEMA, "alias": self.alias, "owner_id": self.owner_id, "property_id": self.property_id,
                "resolved_digest": self.resolved_digest, "unit": self.unit}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MaterialPropertyRef":
        require_schema(payload, MATERIAL_REF_SCHEMA)
        strict_keys(payload, {"schema", "alias", "owner_id", "property_id", "resolved_digest", "unit"}, "material property ref")
        return cls(payload["alias"], payload["owner_id"], payload["property_id"], payload["resolved_digest"], payload["unit"])


@dataclass(frozen=True)
class EnvironmentRequirement:
    """An environment channel value a node consumes, evaluated at an explicit time."""

    alias: str
    channel_id: str
    at: Quantity
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "alias", identifier(self.alias, "environment requirement alias"))
        object.__setattr__(self, "channel_id", identifier(self.channel_id, "environment channel id"))
        if not isinstance(self.at, Quantity):
            raise InvalidScientificProblem("environment requirement time must be an explicit Quantity (no default instant)")
        self.at.magnitude_in("second")
        _unit_dimension(self.unit, f"environment requirement {self.alias!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ENVIRONMENT_REQ_SCHEMA, "alias": self.alias, "channel_id": self.channel_id, "at": self.at.to_dict(), "unit": self.unit}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvironmentRequirement":
        require_schema(payload, ENVIRONMENT_REQ_SCHEMA)
        strict_keys(payload, {"schema", "alias", "channel_id", "at", "unit"}, "environment requirement")
        return cls(payload["alias"], payload["channel_id"], Quantity.from_dict(payload["at"]), payload["unit"])


@dataclass(frozen=True)
class NodeSpec:
    """One declared execution node.  The planner adds derived nodes around these."""

    node_id: str
    kind: NodeKind
    authority: AuthorityRef
    outputs: tuple[NodeOutputSpec, ...]
    depends_on: tuple[str, ...] = ()
    inputs: tuple[NodeInput, ...] = ()
    literals: tuple[LiteralInput, ...] = ()
    provider_binding_ids: tuple[str, ...] = ()
    material_refs: tuple[MaterialPropertyRef, ...] = ()
    environment_requirements: tuple[EnvironmentRequirement, ...] = ()
    #: True for a node whose success advances the authoritative SystemState.
    commits_state: bool = False
    #: The state owners such a node may update (anything else is refused).
    writes_owners: tuple[str, ...] = ()
    #: Runtime applicability checks that must all report "within" BEFORE the node's state is committed.
    applicability_checks: tuple[str, ...] = ()
    checkpointable: bool = False
    configuration_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", identifier(self.node_id, "node id"))
        if not isinstance(self.kind, NodeKind):
            object.__setattr__(self, "kind", NodeKind(self.kind))
        if self.kind in DERIVED_KINDS:
            raise InvalidScientificProblem(f"node kind {self.kind.value!r} is derived by the planner and cannot be declared")
        if not isinstance(self.authority, AuthorityRef):
            raise InvalidScientificProblem("a node must name its execution authority (AuthorityRef)")
        outputs = tuple(self.outputs)
        if not outputs:
            raise InvalidScientificProblem(f"node {self.node_id!r} declares no outputs")
        unique(outputs, lambda o: o.name, f"node {self.node_id!r} outputs")
        inputs, literals = tuple(self.inputs), tuple(self.literals)
        materials, envs = tuple(self.material_refs), tuple(self.environment_requirements)
        names = [i.name for i in inputs] + [lit.name for lit in literals] + [m.alias for m in materials] + [e.alias for e in envs]
        if len(names) != len(set(names)):
            raise InvalidScientificProblem(f"node {self.node_id!r} input names (inputs, literals, material and environment aliases) must be unique")
        if self.commits_state and not tuple(self.writes_owners):
            raise InvalidScientificProblem(f"node {self.node_id!r} commits state but declares no owners it may write")
        if tuple(self.writes_owners) and not self.commits_state:
            raise InvalidScientificProblem(f"node {self.node_id!r} declares writes_owners without commits_state")
        if self.node_id in set(self.depends_on):
            raise InvalidScientificProblem(f"node {self.node_id!r} depends on itself")
        object.__setattr__(self, "outputs", tuple(sorted(outputs)))
        object.__setattr__(self, "depends_on", tuple(sorted({identifier(d, "dependency") for d in self.depends_on})))
        object.__setattr__(self, "inputs", tuple(sorted(inputs)))
        object.__setattr__(self, "literals", tuple(sorted(literals, key=lambda lit: lit.name)))
        object.__setattr__(self, "provider_binding_ids", tuple(sorted({identifier(b, "provider binding id") for b in self.provider_binding_ids})))
        object.__setattr__(self, "material_refs", tuple(sorted(materials)))
        object.__setattr__(self, "environment_requirements", tuple(sorted(envs, key=lambda e: e.alias)))
        object.__setattr__(self, "writes_owners", tuple(sorted({identifier(o, "written owner") for o in self.writes_owners})))
        object.__setattr__(self, "applicability_checks", tuple(sorted({identifier(c, "applicability check id") for c in self.applicability_checks})))
        object.__setattr__(self, "configuration_digest", hex64(self.configuration_digest, "node configuration digest", allow_empty=True))
        if not isinstance(self.commits_state, bool) or not isinstance(self.checkpointable, bool):
            raise InvalidScientificProblem("commits_state and checkpointable must be bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": NODE_SPEC_SCHEMA, "node_id": self.node_id, "kind": self.kind.value, "authority": self.authority.to_dict(),
            "outputs": [o.to_dict() for o in self.outputs], "depends_on": list(self.depends_on),
            "inputs": [i.to_dict() for i in self.inputs], "literals": [lit.to_dict() for lit in self.literals],
            "provider_binding_ids": list(self.provider_binding_ids), "material_refs": [m.to_dict() for m in self.material_refs],
            "environment_requirements": [e.to_dict() for e in self.environment_requirements], "commits_state": self.commits_state,
            "writes_owners": list(self.writes_owners), "applicability_checks": list(self.applicability_checks),
            "checkpointable": self.checkpointable, "configuration_digest": self.configuration_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NodeSpec":
        require_schema(payload, NODE_SPEC_SCHEMA)
        strict_keys(payload, {"schema", "node_id", "kind", "authority", "outputs", "depends_on", "inputs", "literals", "provider_binding_ids",
                              "material_refs", "environment_requirements", "commits_state", "writes_owners", "applicability_checks",
                              "checkpointable", "configuration_digest"}, "node spec")
        return cls(
            payload["node_id"], NodeKind(payload["kind"]), AuthorityRef.from_dict(payload["authority"]),
            tuple(NodeOutputSpec.from_dict(o) for o in payload["outputs"]), tuple(payload["depends_on"]),
            tuple(NodeInput.from_dict(i) for i in payload["inputs"]), tuple(LiteralInput.from_dict(x) for x in payload["literals"]),
            tuple(payload["provider_binding_ids"]), tuple(MaterialPropertyRef.from_dict(m) for m in payload["material_refs"]),
            tuple(EnvironmentRequirement.from_dict(e) for e in payload["environment_requirements"]), payload["commits_state"],
            tuple(payload["writes_owners"]), tuple(payload["applicability_checks"]), payload["checkpointable"], payload["configuration_digest"])


@dataclass(frozen=True, order=True)
class RequestedObservable:
    observable_id: str
    node_id: str
    output_name: str
    unit: str

    def __post_init__(self) -> None:
        for label in ("observable_id", "node_id", "output_name"):
            object.__setattr__(self, label, identifier(getattr(self, label), f"observable {label}"))
        _unit_dimension(self.unit, f"observable {self.observable_id!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": OBSERVABLE_SCHEMA, "observable_id": self.observable_id, "node_id": self.node_id, "output_name": self.output_name, "unit": self.unit}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RequestedObservable":
        require_schema(payload, OBSERVABLE_SCHEMA)
        strict_keys(payload, {"schema", "observable_id", "node_id", "output_name", "unit"}, "requested observable")
        return cls(payload["observable_id"], payload["node_id"], payload["output_name"], payload["unit"])


@dataclass(frozen=True, order=True)
class ConstraintObservation:
    """Binds one SystemDefinition constraint binding to the observable it constrains."""

    binding_id: str
    constraint_id: str
    constraint_digest: str
    observable_id: str

    def __post_init__(self) -> None:
        for label in ("binding_id", "constraint_id", "observable_id"):
            object.__setattr__(self, label, identifier(getattr(self, label), f"constraint observation {label}"))
        object.__setattr__(self, "constraint_digest", hex64(self.constraint_digest, "constraint definition digest"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CONSTRAINT_OBS_SCHEMA, "binding_id": self.binding_id, "constraint_id": self.constraint_id,
                "constraint_digest": self.constraint_digest, "observable_id": self.observable_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConstraintObservation":
        require_schema(payload, CONSTRAINT_OBS_SCHEMA)
        strict_keys(payload, {"schema", "binding_id", "constraint_id", "constraint_digest", "observable_id"}, "constraint observation")
        return cls(payload["binding_id"], payload["constraint_id"], payload["constraint_digest"], payload["observable_id"])


@dataclass(frozen=True, order=True)
class ModelSelection:
    """An explicit model / realization selection for a component (never chosen by the runtime)."""

    instance_id: str
    model_id: str
    model_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", identifier(self.instance_id, "model selection instance"))
        object.__setattr__(self, "model_id", identifier(self.model_id, "model id"))
        object.__setattr__(self, "model_version", text(self.model_version, "model version"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MODEL_SELECTION_SCHEMA, "instance_id": self.instance_id, "model_id": self.model_id, "model_version": self.model_version}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelSelection":
        require_schema(payload, MODEL_SELECTION_SCHEMA)
        strict_keys(payload, {"schema", "instance_id", "model_id", "model_version"}, "model selection")
        return cls(payload["instance_id"], payload["model_id"], payload["model_version"])


@dataclass(frozen=True)
class ExecutionProfile:
    """How the run is to be executed (scientifically relevant switches only)."""

    requested_modes: tuple[str, ...] = ()
    cache_policy: str = "off"
    allow_partial: bool = True
    checkpoint_after: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        modes = tuple(sorted(set(self.requested_modes)))
        if any(m not in MODES for m in modes):
            raise InvalidScientificProblem(f"requested modes must be among {MODES}, got {modes}")
        if self.cache_policy not in CACHE_POLICIES:
            raise InvalidScientificProblem(f"cache policy must be one of {CACHE_POLICIES}")
        if not isinstance(self.allow_partial, bool):
            raise InvalidScientificProblem("allow_partial must be a bool")
        object.__setattr__(self, "requested_modes", modes)
        object.__setattr__(self, "checkpoint_after", tuple(sorted({identifier(n, "checkpoint node") for n in self.checkpoint_after})))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROFILE_SCHEMA, "requested_modes": list(self.requested_modes), "cache_policy": self.cache_policy,
                "allow_partial": self.allow_partial, "checkpoint_after": list(self.checkpoint_after)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionProfile":
        require_schema(payload, PROFILE_SCHEMA)
        strict_keys(payload, {"schema", "requested_modes", "cache_policy", "allow_partial", "checkpoint_after"}, "execution profile")
        return cls(tuple(payload["requested_modes"]), payload["cache_policy"], payload["allow_partial"], tuple(payload["checkpoint_after"]))


@dataclass(frozen=True)
class OperationalContext:
    """Operational facts (workspace, budget).  Never part of scientific identity, never evidence."""

    workspace_hint: str = ""
    resource_budget: ResourceBudget | None = None

    def to_dict(self) -> dict[str, Any]:
        budget = None if self.resource_budget is None else {
            "max_wall_seconds": self.resource_budget.max_wall_seconds, "max_cpu_seconds": self.resource_budget.max_cpu_seconds,
            "max_peak_memory_bytes": self.resource_budget.max_peak_memory_bytes,
            "max_function_evaluations": self.resource_budget.max_function_evaluations}
        return {"schema": OPERATIONAL_SCHEMA, "workspace_hint": str(self.workspace_hint), "resource_budget": budget}

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OperationalContext":
        require_schema(payload, OPERATIONAL_SCHEMA)
        strict_keys(payload, {"schema", "workspace_hint", "resource_budget"}, "operational context")
        budget = payload["resource_budget"]
        return cls(payload["workspace_hint"], None if budget is None else ResourceBudget(**budget))


def _ref(kind: str, obj: Any, id_names: tuple[str, ...]) -> ContentRef:
    ref_id = next((str(getattr(obj, n)) for n in id_names if getattr(obj, n, None)), None)
    if ref_id is None:
        raise InvalidScientificProblem(f"cannot reference a {kind} record that carries none of {id_names}")
    return ContentRef(kind, ref_id, obj.digest)


@dataclass(frozen=True)
class SystemRunRequest:
    request_id: str
    system: ContentRef
    scenario: ContentRef
    timeline: ContentRef
    initial_state: InitialStateSpec
    nodes: tuple[NodeSpec, ...]
    observables: tuple[RequestedObservable, ...]
    provider_bindings: tuple[ProviderBinding, ...] = ()
    model_selections: tuple[ModelSelection, ...] = ()
    materials: tuple[ContentRef, ...] = ()
    environment: ContentRef | None = None
    #: Required when ``environment`` is None: the run STATES that it has no environment.
    environment_absent_reason: str = ""
    constraint_observations: tuple[ConstraintObservation, ...] = ()
    profile: ExecutionProfile = field(default_factory=ExecutionProfile)
    operational: OperationalContext = field(default_factory=OperationalContext)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", identifier(self.request_id, "request id"))
        for label, kind in (("system", "system"), ("scenario", "scenario"), ("timeline", "timeline")):
            ref = getattr(self, label)
            if not isinstance(ref, ContentRef) or ref.kind != kind:
                raise InvalidScientificProblem(f"request {label} must be a {kind} ContentRef")
        if self.environment is None:
            if not str(self.environment_absent_reason).strip():
                raise InvalidScientificProblem("a request without an environment must state why (environment_absent_reason); absence is never a default")
            object.__setattr__(self, "environment_absent_reason", str(self.environment_absent_reason).strip())
        else:
            if not isinstance(self.environment, ContentRef) or self.environment.kind != "environment":
                raise InvalidScientificProblem("request environment must be an environment ContentRef")
            if str(self.environment_absent_reason).strip():
                raise InvalidScientificProblem("an environment and an 'absent' reason are contradictory")
        if not isinstance(self.initial_state, InitialStateSpec):
            raise InvalidScientificProblem("request needs an explicit InitialStateSpec")
        nodes = tuple(self.nodes)
        if not nodes or any(not isinstance(n, NodeSpec) for n in nodes):
            raise InvalidScientificProblem("a request declares at least one NodeSpec")
        unique(nodes, lambda n: n.node_id, "request nodes")
        observables = tuple(self.observables)
        if not observables or any(not isinstance(o, RequestedObservable) for o in observables):
            raise InvalidScientificProblem("a request names at least one requested observable")
        unique(observables, lambda o: o.observable_id, "requested observables")
        bindings = tuple(self.provider_bindings)
        unique(bindings, lambda b: b.binding_id, "provider bindings")
        selections = tuple(self.model_selections)
        unique(selections, lambda s: s.instance_id, "model selections")
        materials = tuple(self.materials)
        if any(not isinstance(m, ContentRef) or m.kind != "material_state" for m in materials):
            raise InvalidScientificProblem("request materials must be material_state ContentRefs")
        unique(materials, lambda m: m.ref_id, "material references")
        constraints = tuple(self.constraint_observations)
        unique(constraints, lambda c: c.binding_id, "constraint observations")
        if not isinstance(self.profile, ExecutionProfile) or not isinstance(self.operational, OperationalContext):
            raise InvalidScientificProblem("request profile/operational must be typed records")
        object.__setattr__(self, "nodes", tuple(sorted(nodes, key=lambda n: n.node_id)))
        object.__setattr__(self, "observables", tuple(sorted(observables)))
        object.__setattr__(self, "provider_bindings", tuple(sorted(bindings)))
        object.__setattr__(self, "model_selections", tuple(sorted(selections)))
        object.__setattr__(self, "materials", tuple(sorted(materials)))
        object.__setattr__(self, "constraint_observations", tuple(sorted(constraints)))

    @classmethod
    def build(cls, *, request_id: str, system: Any, scenario: Any, timeline: Any, initial_state: InitialStateSpec, nodes: tuple[NodeSpec, ...],
              observables: tuple[RequestedObservable, ...], environment: Any = None, environment_absent_reason: str = "",
              materials: tuple[Any, ...] = (), provider_bindings: tuple[ProviderBinding, ...] = (), model_selections: tuple[ModelSelection, ...] = (),
              constraint_observations: tuple[ConstraintObservation, ...] = (), profile: ExecutionProfile | None = None,
              operational: OperationalContext | None = None) -> "SystemRunRequest":
        """Build a request from the scientific objects, reading their content digests (never labels)."""
        return cls(
            request_id, _ref("system", system, ("system_id",)), _ref("scenario", scenario, ("scenario_id", "name", "spec_id")),
            _ref("timeline", timeline, ("timeline_id", "name")), initial_state, nodes, observables, provider_bindings, model_selections,
            tuple(ContentRef("material_state", f"mat_{m.digest[:16]}", m.digest) for m in materials),
            None if environment is None else _ref("environment", environment, ("environment_id", "name", "timeline_id")),
            environment_absent_reason, constraint_observations, profile or ExecutionProfile(), operational or OperationalContext())

    def scientific_dict(self) -> dict[str, Any]:
        """Everything that changes what the run means.  Excludes the label and the operational context."""
        return {
            "schema": REQUEST_SCHEMA, "system": self.system.to_dict(), "scenario": self.scenario.to_dict(), "timeline": self.timeline.to_dict(),
            "environment": None if self.environment is None else self.environment.to_dict(),
            "environment_absent_reason": self.environment_absent_reason, "initial_state": self.initial_state.to_dict(),
            "materials": [m.to_dict() for m in self.materials], "provider_bindings": [b.to_dict() for b in self.provider_bindings],
            "model_selections": [s.to_dict() for s in self.model_selections], "nodes": [n.to_dict() for n in self.nodes],
            "observables": [o.to_dict() for o in self.observables],
            "constraint_observations": [c.to_dict() for c in self.constraint_observations], "profile": self.profile.to_dict(),
        }

    @property
    def digest(self) -> str:
        return digest_of(self.scientific_dict())

    @property
    def operational_digest(self) -> str:
        return self.operational.digest

    def to_dict(self) -> dict[str, Any]:
        out = self.scientific_dict()
        out["request_id"] = self.request_id
        out["operational"] = self.operational.to_dict()
        return out

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SystemRunRequest":
        require_schema(payload, REQUEST_SCHEMA)
        strict_keys(payload, {"schema", "request_id", "system", "scenario", "timeline", "environment", "environment_absent_reason", "initial_state",
                              "materials", "provider_bindings", "model_selections", "nodes", "observables", "constraint_observations",
                              "profile", "operational"}, "system run request")
        reject_non_finite(payload, "system run request")
        env = payload["environment"]
        return cls(
            payload["request_id"], ContentRef.from_dict(payload["system"]), ContentRef.from_dict(payload["scenario"]),
            ContentRef.from_dict(payload["timeline"]), InitialStateSpec.from_dict(payload["initial_state"]),
            tuple(NodeSpec.from_dict(n) for n in payload["nodes"]), tuple(RequestedObservable.from_dict(o) for o in payload["observables"]),
            tuple(ProviderBinding.from_dict(b) for b in payload["provider_bindings"]),
            tuple(ModelSelection.from_dict(s) for s in payload["model_selections"]),
            tuple(ContentRef.from_dict(m) for m in payload["materials"]), None if env is None else ContentRef.from_dict(env),
            payload["environment_absent_reason"], tuple(ConstraintObservation.from_dict(c) for c in payload["constraint_observations"]),
            ExecutionProfile.from_dict(payload["profile"]), OperationalContext.from_dict(payload["operational"]))
