"""Preflight: refuse what is knowable before an expensive solve, and list what is not.

The status vocabulary is READY / DEFERRED_CHECKS / REFUSED.  None of them is scientific support:
READY means "nothing known in advance argues against running", and DEFERRED_CHECKS means the same
plus "these applicability checks can only be evaluated on solved state and will be enforced
then".  A deferred check is never treated as passed.

Nothing falls back.  A required provider that is unavailable, of another version, or of another
build refuses the run; the runtime never substitutes one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity
from ._common import digest_of, require_schema, schema, strict_keys
from .plan import BUILTIN_CONSTRAINT, BUILTIN_ENVIRONMENT, BUILTIN_MATERIAL, SystemExecutionPlan, compile_plan
from .records import AuthorityMismatch, RuntimeContext
from .request import SystemRunRequest

PREFLIGHT_SCHEMA = schema("preflight_report")
CLASSIFICATION = "preflight_admission_not_scientific_support"
BUILTINS = {"builtin.environment": BUILTIN_ENVIRONMENT, "builtin.material": BUILTIN_MATERIAL, "builtin.constraint": BUILTIN_CONSTRAINT}


class PreflightStatus(str, Enum):
    READY = "ready"
    DEFERRED_CHECKS = "deferred_checks"
    REFUSED = "refused"


@dataclass(frozen=True, order=True)
class Finding:
    code: str
    node_id: str
    message: str
    blocking: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "node_id": self.node_id, "message": self.message, "blocking": self.blocking}


@dataclass(frozen=True, order=True)
class DeferredCheck:
    node_id: str
    check_id: str
    description: str = "evaluated on the solved state before the node's state is committed; UNKNOWN or outside refuses"

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "check_id": self.check_id, "description": self.description}


@dataclass(frozen=True)
class PreflightReport:
    status: PreflightStatus
    request_digest: str
    plan_digest: str
    findings: tuple[Finding, ...]
    deferred_checks: tuple[DeferredCheck, ...]

    def __post_init__(self) -> None:
        blocking = any(f.blocking for f in self.findings)
        expected = PreflightStatus.REFUSED if blocking else (PreflightStatus.DEFERRED_CHECKS if self.deferred_checks else PreflightStatus.READY)
        if self.status is not expected:
            raise InvalidScientificProblem(f"preflight status {self.status.value!r} disagrees with its findings (expected {expected.value!r})")

    @property
    def blocking(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.blocking)

    def codes(self) -> tuple[str, ...]:
        return tuple(sorted({f.code for f in self.findings}))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PREFLIGHT_SCHEMA, "classification": CLASSIFICATION, "status": self.status.value, "request_digest": self.request_digest,
                "plan_digest": self.plan_digest, "findings": [f.to_dict() for f in self.findings],
                "deferred_checks": [d.to_dict() for d in self.deferred_checks]}

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PreflightReport":
        require_schema(payload, PREFLIGHT_SCHEMA)
        strict_keys(payload, {"schema", "classification", "status", "request_digest", "plan_digest", "findings", "deferred_checks"}, "preflight report")
        if payload["classification"] != CLASSIFICATION:
            raise InvalidScientificProblem("preflight classification is not the admission classification")
        return cls(PreflightStatus(payload["status"]), payload["request_digest"], payload["plan_digest"],
                   tuple(Finding(**f) for f in payload["findings"]), tuple(DeferredCheck(**d) for d in payload["deferred_checks"]))


def _dim(unit: str) -> str:
    return Quantity(1.0, unit).dimensionality


def preflight(request: SystemRunRequest, plan: SystemExecutionPlan, context: RuntimeContext) -> PreflightReport:
    findings: list[Finding] = []
    add = lambda code, node, message, blocking=True: findings.append(Finding(code, node, message, blocking))  # noqa: E731

    # 1. the plan must be exactly the plan this request compiles to
    try:
        expected = compile_plan(request)
    except InvalidScientificProblem as exc:
        add("PLAN_INVALID", "", str(exc))
        return PreflightReport(PreflightStatus.REFUSED, request.digest, plan.digest, tuple(sorted(findings)), ())
    if plan.request_digest != request.digest or plan.digest != expected.digest:
        add("PLAN_REQUEST_MISMATCH", "", "the plan is not the deterministic plan of this request (request or plan was changed)")

    # 2. supplied scientific objects must be exactly the referenced content
    for label, ref, obj in (("system", request.system, context.system), ("scenario", request.scenario, context.scenario),
                            ("timeline", request.timeline, context.timeline)):
        if obj is None:
            add("MISSING_CONTENT", "", f"the {label} the request references was not supplied")
        elif obj.digest != ref.digest:
            add("CONTENT_DIGEST_MISMATCH", "", f"the supplied {label} has digest {obj.digest[:12]}.., the request pins {ref.digest[:12]}..")
    if request.environment is not None:
        if context.environment is None:
            add("MISSING_CONTENT", "", "the environment the request references was not supplied")
        elif context.environment.digest != request.environment.digest:
            add("CONTENT_DIGEST_MISMATCH", "", "the supplied environment is not the referenced one")
    elif context.environment is not None:
        add("UNDECLARED_ENVIRONMENT", "", "an environment was supplied but the request states it has none; a run cannot silently use one")
    for ref in request.materials:
        state = context.material_states.get(ref.digest)
        if state is None:
            add("MISSING_CONTENT", "", f"material state {ref.ref_id!r} was not supplied")
    for label, table, digest_of_obj in (("material state", context.material_states, lambda o: o.digest),
                                        ("resolved property", context.resolved_properties, lambda o: o.digest),
                                        ("constraint definition", context.constraints, lambda o: digest_of(o.to_dict()))):
        for key, obj in table.items():
            try:
                actual = digest_of_obj(obj)
            except Exception as exc:
                add("CONTENT_DIGEST_MISMATCH", "", f"a supplied {label} filed under {key[:12]}.. has no computable digest ({exc})")
                continue
            if actual != key:
                add("CONTENT_DIGEST_MISMATCH", "", f"a supplied {label} is filed under {key[:12]}.. but its content digest is {actual[:12]}..")

    system, scenario, timeline = context.system, context.scenario, context.timeline
    if timeline is not None and scenario is not None and timeline.scenario_digest != scenario.digest:
        add("TIME_BASIS_MISMATCH", "", "the timeline is not bound to the referenced scenario")
    if request.environment is not None and context.environment is not None and timeline is not None:
        if context.environment.timeline.digest != timeline.digest:
            add("TIME_BASIS_MISMATCH", "", "the environment lives on a different timeline than the request's")
    if scenario is not None:
        start, end = scenario.start.magnitude_in("second"), scenario.end.magnitude_in("second")
        t0 = request.initial_state.time.magnitude_in("second")
        if not start <= t0 <= end:
            add("INITIAL_TIME_OUTSIDE_SCENARIO", "", f"initial state time {t0} s is outside the scenario [{start}, {end}] s")

    # 3. system topology and state ownership
    if system is not None:
        instance_ids = {i.instance_id for i in system.instances}
        for owner in request.initial_state.owners:
            if owner.role == "component" and owner.owner_id not in instance_ids:
                add("UNKNOWN_STATE_OWNER", "", f"initial state owner {owner.owner_id!r} is not a component instance of the system")
        selected = {s.instance_id for s in request.model_selections}
        for instance in system.instances:
            if instance.participant_id and instance.instance_id not in selected:
                add("MODEL_SELECTION_MISSING", "", f"executable component {instance.instance_id!r} has no explicit model selection; the runtime never chooses a model")
        for selection in request.model_selections:
            if selection.instance_id not in instance_ids:
                add("UNKNOWN_MODEL_SELECTION_TARGET", "", f"model selection names {selection.instance_id!r}, which is not a component instance of the system")
        participants = [i.instance_id for i in system.instances if i.participant_id]
        if len(participants) > 1:
            parent = {p: p for p in participants}

            def find(x: str) -> str:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x
            for c in system.connections:
                if c.source_instance_id in parent and c.target_instance_id in parent:
                    parent[find(c.source_instance_id)] = find(c.target_instance_id)
            if len({find(p) for p in participants}) > 1:
                add("DISCONNECTED_TOPOLOGY", "", "the system's executable components are not all connected; a disconnected topology cannot be one coupled system")
        for node in plan.nodes:
            for owner in node.writes_owners:
                if owner not in {o.owner_id for o in request.initial_state.owners}:
                    add("UNKNOWN_STATE_OWNER", node.node_id, f"node writes owner {owner!r}, which the initial state does not declare")

    # 4. providers: explicit, available, exactly this version (and build, if pinned); never a substitute
    used = {b for n in plan.nodes for b in n.provider_binding_ids}
    for binding in request.provider_bindings:
        if binding.binding_id not in used:
            add("UNUSED_PROVIDER_BINDING", "", f"provider binding {binding.binding_id!r} is not used by any node", False)
    if used and context.providers is None:
        add("PROVIDER_REGISTRY_MISSING", "", "nodes use providers but no provider registry was supplied")
    elif context.providers is not None:
        for binding in request.provider_bindings:
            if binding.binding_id not in used:
                continue
            try:
                status = context.providers.status(binding.provider_id)
            except Exception as exc:
                add("PROVIDER_UNAVAILABLE", "", f"provider {binding.provider_id!r} is not known to the registry ({exc}); no substitute is chosen")
                continue
            if not status.available:
                add("PROVIDER_UNAVAILABLE", "", f"provider {binding.provider_id!r} is {status.availability.value}: {status.reason or 'unavailable'}; no substitute is chosen")
            elif status.version != binding.provider_version:
                add("PROVIDER_VERSION_MISMATCH", "", f"provider {binding.provider_id!r} is version {status.version!r}, the request requires {binding.provider_version!r}")
            elif binding.provider_digest and status.digest != binding.provider_digest:
                add("PROVIDER_DIGEST_MISMATCH", "", f"provider {binding.provider_id!r} build differs from the pinned digest")

    # 5. authorities
    for node in plan.nodes:
        if node.derived:
            continue
        if not context.authorities.has(node.authority.authority_id):
            add("AUTHORITY_UNAVAILABLE", node.node_id, f"authority {node.authority.authority_id!r} is not registered")
            continue
        try:
            authority = context.authorities.resolve(node.authority)
        except AuthorityMismatch as exc:
            add("AUTHORITY_IDENTITY_MISMATCH", node.node_id, str(exc))
            continue
        for code, message in authority.preflight_findings(node, context) if hasattr(authority, "preflight_findings") else ():
            add(code, node.node_id, message)
        for feature in authority.unsupported_scenario_features(scenario) if (hasattr(authority, "unsupported_scenario_features") and scenario is not None) else ():
            add("UNSUPPORTED_SCENARIO_FEATURE", node.node_id, feature)

    # 6. derived nodes: material and environment content, constraint bindings
    for node in plan.nodes:
        if node.kind.value == "resolve_material":
            digest = node.arg("resolved_digest")
            prop = context.resolved_properties.get(digest)
            owner_state = dict(request.initial_state.material_state_digests).get(node.arg("owner"))
            if owner_state is None:
                add("MATERIAL_MISMATCH", node.node_id, f"owner {node.arg('owner')!r} has no material state in the initial state, so the property has no material to belong to")
            elif owner_state not in {m.digest for m in request.materials}:
                add("MISSING_CONTENT", node.node_id, f"the material state bound to owner {node.arg('owner')!r} is not among the request's materials")
            if prop is None:
                add("MISSING_MATERIAL", node.node_id, f"resolved property {node.arg('property')!r} ({digest[:12]}..) was not supplied")
            elif prop.status != "known" or prop.value is None:
                add("MATERIAL_UNKNOWN", node.node_id, f"resolved property {node.arg('property')!r} is UNKNOWN ({prop.reason or 'no reason stated'}); it cannot be defaulted")
            else:
                if prop.property_id != node.arg("property"):
                    add("MATERIAL_MISMATCH", node.node_id, f"resolved property is {prop.property_id!r}, the node declares {node.arg('property')!r}")
                if owner_state is not None and prop.state_digest != owner_state:
                    add("MATERIAL_MISMATCH", node.node_id, "the resolved property was resolved for another material state than the one bound to its owner")
                try:
                    if prop.value.value.dimensionality != _dim(node.outputs[0].unit):
                        add("UNIT_INCOMPATIBLE", node.node_id, "resolved property dimension differs from the declared unit")
                except Exception as exc:
                    add("UNIT_INCOMPATIBLE", node.node_id, str(exc))
            if system is not None and node.arg("owner") not in {i.instance_id for i in system.instances}:
                add("UNKNOWN_STATE_OWNER", node.node_id, f"material owner {node.arg('owner')!r} is not a component instance")
        elif node.kind.value == "evaluate_environment":
            if request.environment is None or context.environment is None:
                add("MISSING_ENVIRONMENT", node.node_id, "a node requires an environment channel but the request has no environment")
                continue
            try:
                channel = context.environment.channel(node.arg("channel"))
            except InvalidScientificProblem:
                add("MISSING_ENVIRONMENT", node.node_id, f"environment has no channel {node.arg('channel')!r}")
                continue
            try:
                if _dim(channel.unit) != _dim(node.outputs[0].unit):
                    add("UNIT_INCOMPATIBLE", node.node_id, f"channel unit {channel.unit!r} is not dimensionally compatible with {node.outputs[0].unit!r}")
            except Exception as exc:
                add("UNIT_INCOMPATIBLE", node.node_id, str(exc))
        elif node.kind.value == "constraint_assessment":
            definition = context.constraints.get(node.arg("constraint_digest"))
            if definition is None:
                add("INVALID_CONSTRAINT_BINDING", node.node_id, f"constraint definition {node.arg('constraint_id')!r} was not supplied")
            else:
                try:
                    if definition.bound.dimensionality != _dim(node.inputs[0].unit):
                        add("INVALID_CONSTRAINT_BINDING", node.node_id, "constraint bound and observable differ in dimension")
                except Exception as exc:
                    add("INVALID_CONSTRAINT_BINDING", node.node_id, str(exc))
                if system is not None and definition.name not in {c.name for c in system.constraints}:
                    add("INVALID_CONSTRAINT_BINDING", node.node_id, f"constraint {definition.name!r} is not declared by the system")
    if system is not None:
        observed = {c.binding_id for c in request.constraint_observations}
        for binding in system.constraint_bindings:
            if binding.binding_id not in observed:
                add("CONSTRAINT_NOT_OBSERVED", "", f"system constraint binding {binding.binding_id!r} has no observable; its assessment will be UNAVAILABLE", False)
        for obs in request.constraint_observations:
            if obs.binding_id not in {b.binding_id for b in system.constraint_bindings}:
                add("INVALID_CONSTRAINT_BINDING", "", f"constraint observation {obs.binding_id!r} matches no system constraint binding")

    # 7. checkpoint requirements
    for node_id in plan.checkpoint_after:
        node = plan.node(node_id)
        if not node.checkpointable:
            add("CHECKPOINT_IMPOSSIBLE", node_id, "a checkpoint is requested after a node that does not declare itself checkpointable")
        elif context.authorities.has(node.authority.authority_id):
            try:
                authority = context.authorities.resolve(node.authority)
                if not (authority.supports_checkpoint or authority.stateless):
                    add("CHECKPOINT_IMPOSSIBLE", node_id, "the node's authority holds state it cannot declare, so its checkpoint could not be resumed")
            except AuthorityMismatch:
                pass

    deferred = tuple(sorted(DeferredCheck(n.node_id, c) for n in plan.nodes for c in n.applicability_checks))
    findings_t = tuple(sorted(findings))
    if any(f.blocking for f in findings_t):
        status = PreflightStatus.REFUSED
    elif deferred:
        status = PreflightStatus.DEFERRED_CHECKS
    else:
        status = PreflightStatus.READY
    return PreflightReport(status, request.digest, plan.digest, findings_t, deferred)
