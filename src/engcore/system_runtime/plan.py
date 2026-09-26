"""Compile a request into an immutable, deterministic execution plan (a DAG of nodes).

The planner is pure: the same canonical request always yields the same plan and the same digest.
It produces no evidence.  It derives three kinds of node around the declared ones (material
resolution, environment evaluation, constraint assessment) and refuses anything structurally
wrong: unknown dependencies, unknown outputs, unit-dimension mismatches, dangling inputs, unknown
provider bindings and cycles.  A cycle is never legal at this level; iteration is legal only
*inside* one node's authority (for example a BIG 9 coupling), which the plan treats as one node.

There is no domain knowledge here.  A node is a kind, an authority reference, wiring and
declarations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity, base_unit, is_ratio_scale
from ._common import canonical_json, digest_of, hex64, identifier, require_schema, schema, strict_keys
from .request import (
    AuthorityRef, LiteralInput, NodeInput, NodeKind, NodeOutputSpec, RequestedObservable, SystemRunRequest, KIND_MODE, ConstraintObservation,
)

PLAN_NODE_SCHEMA = schema("plan_node")
PLAN_SCHEMA = schema("execution_plan")

BUILTIN_VERSION = "builtin/1"
BUILTIN_ENVIRONMENT = AuthorityRef("builtin.environment", "builtin", digest_of({"builtin": "environment", "version": BUILTIN_VERSION}))
BUILTIN_MATERIAL = AuthorityRef("builtin.material", "builtin", digest_of({"builtin": "material", "version": BUILTIN_VERSION}))
BUILTIN_CONSTRAINT = AuthorityRef("builtin.constraint", "builtin", digest_of({"builtin": "constraint", "version": BUILTIN_VERSION}))
RESERVED_PREFIXES = ("env.", "mat.", "constraint.")


def _dimension(unit: str) -> str:
    return Quantity(1.0, unit).dimensionality


def spread_unit(unit: str) -> str:
    """The unit a spread/margin in this quantity's dimension is stated in (never an affine coordinate)."""
    return unit if is_ratio_scale(unit) else base_unit(unit)


@dataclass(frozen=True)
class PlanNode:
    node_id: str
    kind: NodeKind
    authority: AuthorityRef
    depends_on: tuple[str, ...]
    inputs: tuple[NodeInput, ...]
    literals: tuple[LiteralInput, ...]
    outputs: tuple[NodeOutputSpec, ...]
    provider_binding_ids: tuple[str, ...]
    commits_state: bool
    writes_owners: tuple[str, ...]
    applicability_checks: tuple[str, ...]
    checkpointable: bool
    configuration_digest: str
    derived: bool
    #: string pairs a built-in authority needs (channel id, evaluation time, ...); sorted, part of identity
    builtin_args: tuple[tuple[str, str], ...] = ()
    applicability_waiver: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", identifier(self.node_id, "plan node id"))
        if not isinstance(self.kind, NodeKind) or not isinstance(self.authority, AuthorityRef):
            raise InvalidScientificProblem("plan node needs a NodeKind and an AuthorityRef")
        object.__setattr__(self, "builtin_args", tuple(sorted((str(a), str(b)) for a, b in self.builtin_args)))

    def arg(self, key: str) -> str:
        for name, value in self.builtin_args:
            if name == key:
                return value
        raise KeyError(key)

    def output_unit(self, name: str) -> str:
        for spec in self.outputs:
            if spec.name == name:
                return spec.unit
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLAN_NODE_SCHEMA, "node_id": self.node_id, "kind": self.kind.value, "authority": self.authority.to_dict(),
            "depends_on": list(self.depends_on), "inputs": [i.to_dict() for i in self.inputs], "literals": [x.to_dict() for x in self.literals],
            "outputs": [o.to_dict() for o in self.outputs], "provider_binding_ids": list(self.provider_binding_ids),
            "commits_state": self.commits_state, "writes_owners": list(self.writes_owners),
            "applicability_checks": list(self.applicability_checks), "checkpointable": self.checkpointable,
            "configuration_digest": self.configuration_digest, "derived": self.derived, "builtin_args": [list(p) for p in self.builtin_args],
            "applicability_waiver": self.applicability_waiver,
        }

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlanNode":
        require_schema(payload, PLAN_NODE_SCHEMA)
        strict_keys(payload, {"schema", "node_id", "kind", "authority", "depends_on", "inputs", "literals", "outputs", "provider_binding_ids",
                              "commits_state", "writes_owners", "applicability_checks", "checkpointable", "configuration_digest",
                              "derived", "builtin_args", "applicability_waiver"}, "plan node")
        return cls(payload["node_id"], NodeKind(payload["kind"]), AuthorityRef.from_dict(payload["authority"]), tuple(payload["depends_on"]),
                   tuple(NodeInput.from_dict(i) for i in payload["inputs"]), tuple(LiteralInput.from_dict(x) for x in payload["literals"]),
                   tuple(NodeOutputSpec.from_dict(o) for o in payload["outputs"]), tuple(payload["provider_binding_ids"]),
                   payload["commits_state"], tuple(payload["writes_owners"]), tuple(payload["applicability_checks"]), payload["checkpointable"],
                   hex64(payload["configuration_digest"], "configuration digest", allow_empty=True), payload["derived"],
                   tuple((a, b) for a, b in payload["builtin_args"]), payload["applicability_waiver"])


@dataclass(frozen=True)
class SystemExecutionPlan:
    request_digest: str
    nodes: tuple[PlanNode, ...]  # topological order, deterministic
    observables: tuple[RequestedObservable, ...]
    constraint_observations: tuple[ConstraintObservation, ...]
    checkpoint_after: tuple[str, ...]
    allow_partial: bool
    cache_policy: str
    requested_modes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_digest", hex64(self.request_digest, "plan request digest"))
        nodes = tuple(self.nodes)
        ids = [n.node_id for n in nodes]
        if not nodes or len(ids) != len(set(ids)):
            raise InvalidScientificProblem("a plan needs unique nodes")
        position = {node_id: i for i, node_id in enumerate(ids)}
        for node in nodes:
            for dep in node.depends_on:
                if dep not in position or position[dep] >= position[node.node_id]:
                    raise InvalidScientificProblem(f"plan node {node.node_id!r} is not in dependency order (or names unknown {dep!r})")

    def node(self, node_id: str) -> PlanNode:
        for item in self.nodes:
            if item.node_id == node_id:
                return item
        raise KeyError(node_id)

    def dependents(self, node_id: str) -> tuple[str, ...]:
        return tuple(n.node_id for n in self.nodes if node_id in n.depends_on)

    def ancestors(self, node_id: str) -> tuple[str, ...]:
        """Every node the given node transitively depends on, in plan order."""
        seen: set[str] = set()
        stack = list(self.node(node_id).depends_on)
        while stack:
            current = stack.pop()
            if current not in seen:
                seen.add(current)
                stack.extend(self.node(current).depends_on)
        return tuple(n.node_id for n in self.nodes if n.node_id in seen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLAN_SCHEMA, "request_digest": self.request_digest, "nodes": [n.to_dict() for n in self.nodes],
            "observables": [o.to_dict() for o in self.observables], "constraint_observations": [c.to_dict() for c in self.constraint_observations],
            "checkpoint_after": list(self.checkpoint_after), "allow_partial": self.allow_partial, "cache_policy": self.cache_policy,
            "requested_modes": list(self.requested_modes),
        }

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SystemExecutionPlan":
        require_schema(payload, PLAN_SCHEMA)
        strict_keys(payload, {"schema", "request_digest", "nodes", "observables", "constraint_observations", "checkpoint_after", "allow_partial",
                              "cache_policy", "requested_modes"}, "execution plan")
        return cls(payload["request_digest"], tuple(PlanNode.from_dict(n) for n in payload["nodes"]),
                   tuple(RequestedObservable.from_dict(o) for o in payload["observables"]),
                   tuple(ConstraintObservation.from_dict(c) for c in payload["constraint_observations"]),
                   tuple(payload["checkpoint_after"]), payload["allow_partial"], payload["cache_policy"], tuple(payload["requested_modes"]))


def compile_plan(request: SystemRunRequest) -> SystemExecutionPlan:
    """The deterministic plan for a request.  Pure: no clock, no randomness, no provider access."""
    if not isinstance(request, SystemRunRequest):
        raise InvalidScientificProblem("compile_plan requires a SystemRunRequest")
    user = {n.node_id: n for n in request.nodes}
    for node_id in user:
        if node_id.startswith(RESERVED_PREFIXES):
            raise InvalidScientificProblem(f"node id {node_id!r} uses a prefix reserved for planner-derived nodes {RESERVED_PREFIXES}")
    binding_ids = {b.binding_id for b in request.provider_bindings}
    for node in request.nodes:
        unknown = sorted(set(node.provider_binding_ids) - binding_ids)
        if unknown:
            raise InvalidScientificProblem(f"node {node.node_id!r} references unknown provider binding(s) {unknown}")
    declared_modes = set(request.profile.requested_modes)
    for node in request.nodes:
        needed = KIND_MODE.get(node.kind)
        if needed and needed not in declared_modes:
            raise InvalidScientificProblem(f"node {node.node_id!r} is a {node.kind.value} node but the request does not declare mode {needed!r}")

    plan_nodes: dict[str, PlanNode] = {}
    extra_inputs: dict[str, list[NodeInput]] = {n: [] for n in user}
    extra_deps: dict[str, set[str]] = {n: set() for n in user}

    for node in request.nodes:
        for env in node.environment_requirements:
            derived_id = f"env.{node.node_id}.{env.alias}"
            plan_nodes[derived_id] = PlanNode(
                derived_id, NodeKind.EVALUATE_ENVIRONMENT, BUILTIN_ENVIRONMENT, (), (), (), (NodeOutputSpec("value", env.unit),), (), False, (), (),
                False, "", True, (("at", canonical_json(env.at.to_dict())), ("channel", env.channel_id)))
            extra_inputs[node.node_id].append(NodeInput(env.alias, derived_id, "value", env.unit))
            extra_deps[node.node_id].add(derived_id)
        for mat in node.material_refs:
            derived_id = f"mat.{node.node_id}.{mat.alias}"
            plan_nodes[derived_id] = PlanNode(
                derived_id, NodeKind.RESOLVE_MATERIAL, BUILTIN_MATERIAL, (), (), (), (NodeOutputSpec("value", mat.unit),), (), False, (), (), False, "",
                True, (("owner", mat.owner_id), ("property", mat.property_id), ("resolved_digest", mat.resolved_digest)))
            extra_inputs[node.node_id].append(NodeInput(mat.alias, derived_id, "value", mat.unit))
            extra_deps[node.node_id].add(derived_id)

    for node in request.nodes:
        inputs = tuple(sorted((*node.inputs, *extra_inputs[node.node_id])))
        deps = set(node.depends_on) | extra_deps[node.node_id] | {i.source_node for i in inputs}
        plan_nodes[node.node_id] = PlanNode(
            node.node_id, node.kind, node.authority, tuple(sorted(deps)), inputs, node.literals, node.outputs, node.provider_binding_ids,
            node.commits_state, node.writes_owners, node.applicability_checks, node.checkpointable, node.configuration_digest, False, (),
            node.applicability_waiver)

    observable_by_id = {o.observable_id: o for o in request.observables}
    for obs in request.constraint_observations:
        target = observable_by_id.get(obs.observable_id)
        if target is None:
            raise InvalidScientificProblem(f"constraint observation {obs.binding_id!r} names unknown observable {obs.observable_id!r}")
        derived_id = f"constraint.{obs.binding_id}"
        plan_nodes[derived_id] = PlanNode(
            derived_id, NodeKind.CONSTRAINT_ASSESSMENT, BUILTIN_CONSTRAINT, (target.node_id,),
            (NodeInput("observed", target.node_id, target.output_name, target.unit),), (), (NodeOutputSpec("margin", spread_unit(target.unit)),), (),
            False, (), (), False, "", True, (("binding", obs.binding_id), ("constraint_digest", obs.constraint_digest), ("constraint_id", obs.constraint_id)))

    # wiring validation
    for node in plan_nodes.values():
        for dep in node.depends_on:
            if dep not in plan_nodes:
                raise InvalidScientificProblem(f"node {node.node_id!r} depends on unknown node {dep!r}")
        for item in node.inputs:
            source = plan_nodes.get(item.source_node)
            if source is None:
                raise InvalidScientificProblem(f"node {node.node_id!r} input {item.name!r} names unknown source node {item.source_node!r}")
            try:
                source_unit = source.output_unit(item.source_output)
            except KeyError:
                raise InvalidScientificProblem(
                    f"node {node.node_id!r} input {item.name!r} names unknown output {item.source_output!r} of {item.source_node!r}") from None
            if _dimension(source_unit) != _dimension(item.unit):
                raise InvalidScientificProblem(
                    f"node {node.node_id!r} input {item.name!r} expects {item.unit!r} but {item.source_node}.{item.source_output} is {source_unit!r}")
    for obs in request.observables:
        source = plan_nodes.get(obs.node_id)
        if source is None or obs.node_id.startswith(RESERVED_PREFIXES):
            raise InvalidScientificProblem(f"observable {obs.observable_id!r} names unknown declared node {obs.node_id!r}")
        try:
            unit = source.output_unit(obs.output_name)
        except KeyError:
            raise InvalidScientificProblem(f"observable {obs.observable_id!r} names unknown output {obs.output_name!r}") from None
        if _dimension(unit) != _dimension(obs.unit):
            raise InvalidScientificProblem(f"observable {obs.observable_id!r} unit {obs.unit!r} disagrees with output unit {unit!r}")
    for node_id in request.profile.checkpoint_after:
        if node_id not in user:
            raise InvalidScientificProblem(f"checkpoint_after names unknown declared node {node_id!r}")

    # deterministic Kahn ordering; a cycle is refused
    remaining = {n.node_id: set(n.depends_on) for n in plan_nodes.values()}
    order: list[str] = []
    while remaining:
        ready = sorted(n for n, deps in remaining.items() if not deps)
        if not ready:
            raise InvalidScientificProblem(
                f"the execution graph contains a cycle among {sorted(remaining)}; a generic DAG cannot iterate "
                f"(iteration belongs inside one node's authority, e.g. a coupling runtime)")
        for node_id in ready:
            order.append(node_id)
            del remaining[node_id]
        for deps in remaining.values():
            deps.difference_update(ready)

    return SystemExecutionPlan(
        request.digest, tuple(plan_nodes[n] for n in order), request.observables, request.constraint_observations,
        request.profile.checkpoint_after, request.profile.allow_partial, request.profile.cache_policy, request.profile.requested_modes)
