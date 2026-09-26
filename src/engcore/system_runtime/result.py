"""The unified system run result, the system checkpoint, and result tracing.

The result *references* existing records (provider execution identities, artifacts, receipts); it
does not copy provider bulk data.  It answers, for every requested observable, one of AVAILABLE /
BLOCKED / REFUSED / FAILED / UNKNOWN together with the dependency path that decided it, so a
partial run can neither pass as a whole run nor throw away a valid independent branch.

Execution status here is never scientific support.  ``trust_inputs`` hands facts to the existing
credibility authority and states plainly that this runtime assessed nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..execution.orchestration.resources import ResourceUsage
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import UncertaintyKind
from ._common import digest_of, hex64, identifier, require_schema, schema, strict_keys
from .plan import SystemExecutionPlan
from .preflight import PreflightReport
from .records import ArtifactRef, NodeReceipt, NodeStatus, OutputValue, ProviderRecordRef
from .state import SystemState

RESULT_SCHEMA = schema("system_run_result")
OBSERVABLE_RESULT_SCHEMA = schema("observable_result")
TRUST_INPUTS_SCHEMA = schema("trust_inputs")
CHECKPOINT_SCHEMA = schema("system_checkpoint")
TRACE_SCHEMA = schema("result_trace")


class Availability(str, Enum):
    AVAILABLE = "available"
    BLOCKED = "blocked"
    REFUSED = "refused"
    FAILED = "failed"
    UNKNOWN = "unknown"


class RunStatus(str, Enum):
    #: every node succeeded
    SUCCEEDED = "succeeded"
    #: some observable available, some not
    PARTIAL = "partial"
    #: preflight refused; nothing was executed
    REFUSED = "refused"
    #: executed, but no requested observable is available
    FAILED = "failed"
    #: stopped at a declared checkpoint; the rest is PENDING and resumable
    PAUSED = "paused"


@dataclass(frozen=True)
class ObservableResult:
    observable_id: str
    node_id: str
    output_name: str
    unit: str
    availability: Availability
    value: OutputValue | None
    #: the nodes this observable depends on (transitively), in plan order, plus the producing node
    dependency_path: tuple[str, ...]
    #: the failed / refused / pending nodes that decided a non-AVAILABLE answer
    root_causes: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if (self.availability is Availability.AVAILABLE) != (self.value is not None):
            raise InvalidScientificProblem(f"observable {self.observable_id!r}: a value is exposed exactly when it is AVAILABLE")
        if self.availability is not Availability.AVAILABLE and not self.root_causes and self.availability is not Availability.UNKNOWN:
            raise InvalidScientificProblem(f"observable {self.observable_id!r} is {self.availability.value} without a stated root cause")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": OBSERVABLE_RESULT_SCHEMA, "observable_id": self.observable_id, "node_id": self.node_id, "output_name": self.output_name,
                "unit": self.unit, "availability": self.availability.value, "value": None if self.value is None else self.value.to_dict(),
                "dependency_path": list(self.dependency_path), "root_causes": list(self.root_causes), "reason": self.reason}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ObservableResult":
        require_schema(payload, OBSERVABLE_RESULT_SCHEMA)
        strict_keys(payload, {"schema", "observable_id", "node_id", "output_name", "unit", "availability", "value", "dependency_path",
                              "root_causes", "reason"}, "observable result")
        v = payload["value"]
        return cls(payload["observable_id"], payload["node_id"], payload["output_name"], payload["unit"], Availability(payload["availability"]),
                   None if v is None else OutputValue.from_dict(v), tuple(payload["dependency_path"]), tuple(payload["root_causes"]), payload["reason"])


@dataclass(frozen=True)
class TrustInputs:
    """Facts for the existing credibility authority.  This runtime assesses nothing.

    ``validation_evidence`` is always empty here: only an existing validation authority can add to it.
    """

    execution_status: str
    unknown_uncertainty_outputs: tuple[str, ...]
    applicability_reports: tuple[tuple[str, str, str], ...]
    provider_execution_identities: tuple[str, ...]
    #: state-committing nodes that ran with a stated applicability waiver instead of a runtime check (caller statement, not evidence)
    waived_applicability: tuple[str, ...] = ()
    validation_evidence: tuple[str, ...] = ()
    assessment: str = "not_assessed_by_runtime"

    def __post_init__(self) -> None:
        if self.validation_evidence:
            raise InvalidScientificProblem("the system runtime cannot supply validation evidence; only a validation authority can")
        if self.assessment != "not_assessed_by_runtime":
            raise InvalidScientificProblem("the system runtime issues no scientific assessment")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TRUST_INPUTS_SCHEMA, "execution_status": self.execution_status,
                "unknown_uncertainty_outputs": list(self.unknown_uncertainty_outputs),
                "applicability_reports": [list(a) for a in self.applicability_reports],
                "provider_execution_identities": list(self.provider_execution_identities),
                "waived_applicability": list(self.waived_applicability),
                "validation_evidence": list(self.validation_evidence), "assessment": self.assessment}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TrustInputs":
        require_schema(payload, TRUST_INPUTS_SCHEMA)
        strict_keys(payload, {"schema", "execution_status", "unknown_uncertainty_outputs", "applicability_reports", "provider_execution_identities",
                              "waived_applicability", "validation_evidence", "assessment"}, "trust inputs")
        return cls(payload["execution_status"], tuple(payload["unknown_uncertainty_outputs"]),
                   tuple(tuple(a) for a in payload["applicability_reports"]), tuple(payload["provider_execution_identities"]),
                   tuple(payload["waived_applicability"]), tuple(payload["validation_evidence"]), payload["assessment"])


def _outputs_to_dict(outputs: Mapping[str, Mapping[str, OutputValue]]) -> dict[str, Any]:
    return {node: {name: value.to_dict() for name, value in sorted(items.items())} for node, items in sorted(outputs.items())}


def _outputs_from_dict(payload: Mapping[str, Any]) -> dict[str, dict[str, OutputValue]]:
    return {node: {name: OutputValue.from_dict(v) for name, v in items.items()} for node, items in payload.items()}


@dataclass(frozen=True)
class AuthorityCheckpoint:
    """One authority's resumable state as captured after its node."""

    node_id: str
    authority_id: str
    identity_digest: str
    payload: Mapping[str, Any] | None
    declared_complete: bool

    @property
    def payload_digest(self) -> str:
        return digest_of(self.payload if self.payload is not None else {"none": True})

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "authority_id": self.authority_id, "identity_digest": self.identity_digest,
                "payload": self.payload, "declared_complete": self.declared_complete}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AuthorityCheckpoint":
        strict_keys(payload, {"node_id", "authority_id", "identity_digest", "payload", "declared_complete"}, "authority checkpoint")
        if not isinstance(payload["declared_complete"], bool):
            raise InvalidScientificProblem("an authority checkpoint's completeness declaration must be a boolean")
        return cls(payload["node_id"], payload["authority_id"], hex64(payload["identity_digest"], "authority identity digest"),
                   payload["payload"], payload["declared_complete"])


@dataclass(frozen=True)
class SystemCheckpoint:
    """Everything needed to resume a run in a fresh runtime, bound to the exact context it came from.

    Agreement between a resumed and an uninterrupted run is reproducibility, not validation.
    """

    request_digest: str
    plan_digest: str
    run_id: str
    state: SystemState
    state_history: tuple[SystemState, ...]
    completed_receipts: tuple[NodeReceipt, ...]
    outputs: Mapping[str, Mapping[str, OutputValue]]
    authority_checkpoints: tuple[AuthorityCheckpoint, ...]
    context_digests: tuple[tuple[str, str], ...]
    #: True only if every completed node's authority DECLARED its state complete
    complete: bool
    incomplete_reason: str = ""
    classification: str = "checkpoint_reproducibility_not_validation"

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_digest", hex64(self.request_digest, "checkpoint request digest"))
        object.__setattr__(self, "plan_digest", hex64(self.plan_digest, "checkpoint plan digest"))
        object.__setattr__(self, "run_id", identifier(self.run_id, "checkpoint run id"))
        if not isinstance(self.state, SystemState) or not self.state_history or self.state_history[-1].digest != self.state.digest:
            raise InvalidScientificProblem("a checkpoint's state must be the last of its state history")
        for a, b in zip(self.state_history, self.state_history[1:]):
            if b.previous_digest != a.digest or b.sequence != a.sequence + 1:
                raise InvalidScientificProblem("checkpoint state history is not a digest chain")
        for receipt in self.completed_receipts:
            if receipt.status is not NodeStatus.SUCCEEDED:
                raise InvalidScientificProblem("a checkpoint holds only SUCCEEDED node receipts")
            if receipt.plan_digest != self.plan_digest or receipt.request_digest != self.request_digest:
                raise InvalidScientificProblem("a checkpoint receipt belongs to another plan or request")
            held = self.outputs.get(receipt.node_id)
            if held is None or tuple(sorted((n, v.digest) for n, v in held.items())) != receipt.output_digests:
                raise InvalidScientificProblem(f"checkpoint outputs of {receipt.node_id!r} do not match its receipt")
        if self.complete == bool(self.incomplete_reason):
            raise InvalidScientificProblem("a checkpoint is complete exactly when it states no incompleteness reason")
        if self.classification != "checkpoint_reproducibility_not_validation":
            raise InvalidScientificProblem("a system checkpoint is reproducibility, never validation")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CHECKPOINT_SCHEMA, "classification": self.classification, "request_digest": self.request_digest,
                "plan_digest": self.plan_digest, "run_id": self.run_id, "state": self.state.to_dict(), "state_history": [s.to_dict() for s in self.state_history],
                "completed_receipts": [r.to_dict() for r in self.completed_receipts], "outputs": _outputs_to_dict(self.outputs),
                "authority_checkpoints": [a.to_dict() for a in self.authority_checkpoints], "context_digests": [list(p) for p in self.context_digests],
                "complete": self.complete, "incomplete_reason": self.incomplete_reason}

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SystemCheckpoint":
        require_schema(payload, CHECKPOINT_SCHEMA)
        strict_keys(payload, {"schema", "classification", "request_digest", "plan_digest", "run_id", "state", "state_history", "completed_receipts", "outputs",
                              "authority_checkpoints", "context_digests", "complete", "incomplete_reason"}, "system checkpoint")
        if not isinstance(payload["complete"], bool):
            raise InvalidScientificProblem("a system checkpoint's completeness flag must be a boolean")
        return cls(payload["request_digest"], payload["plan_digest"], payload["run_id"], SystemState.from_dict(payload["state"]),
                   tuple(SystemState.from_dict(s) for s in payload["state_history"]),
                   tuple(NodeReceipt.from_dict(r) for r in payload["completed_receipts"]), _outputs_from_dict(payload["outputs"]),
                   tuple(AuthorityCheckpoint.from_dict(a) for a in payload["authority_checkpoints"]),
                   tuple(tuple(p) for p in payload["context_digests"]), payload["complete"], payload["incomplete_reason"], payload["classification"])


@dataclass(frozen=True)
class SystemRunResult:
    request_digest: str
    plan_digest: str
    run_id: str
    status: RunStatus
    preflight: PreflightReport
    plan: SystemExecutionPlan
    initial_state: SystemState | None
    final_state: SystemState | None
    state_history: tuple[SystemState, ...]
    node_receipts: tuple[NodeReceipt, ...]
    node_outputs: Mapping[str, Mapping[str, OutputValue]]
    observables: tuple[ObservableResult, ...]
    provider_records: tuple[ProviderRecordRef, ...]
    artifacts: tuple[tuple[str, ArtifactRef], ...]
    diagnostics: tuple[tuple[str, str, str], ...]
    resource_usage: ResourceUsage
    checkpoints: tuple[SystemCheckpoint, ...]
    provenance: tuple[tuple[str, str], ...]
    trust_inputs: TrustInputs
    classification: str = "system_execution_not_scientific_support"

    def __post_init__(self) -> None:
        if self.classification != "system_execution_not_scientific_support":
            raise InvalidScientificProblem("a system run result is execution, never scientific support")
        if self.plan.digest != self.plan_digest or self.plan.request_digest != self.request_digest:
            raise InvalidScientificProblem("result plan does not match the plan/request digests it states")
        if self.preflight.request_digest != self.request_digest or self.preflight.plan_digest != self.plan_digest:
            raise InvalidScientificProblem("result preflight belongs to another request/plan")
        receipts = {r.node_id: r for r in self.node_receipts}
        if len(receipts) != len(self.node_receipts):
            raise InvalidScientificProblem("duplicate node receipts")
        if self.status is not RunStatus.REFUSED and set(receipts) != {n.node_id for n in self.plan.nodes}:
            raise InvalidScientificProblem("a run that executed has exactly one receipt per plan node")
        for receipt in self.node_receipts:
            if receipt.plan_digest != self.plan_digest or receipt.request_digest != self.request_digest:
                raise InvalidScientificProblem(f"receipt of {receipt.node_id!r} belongs to another plan or request")
            held = self.node_outputs.get(receipt.node_id, {})
            if receipt.status is NodeStatus.SUCCEEDED:
                if tuple(sorted((n, v.digest) for n, v in held.items())) != receipt.output_digests:
                    raise InvalidScientificProblem(f"outputs of {receipt.node_id!r} do not match its receipt (tampered value?)")
            elif held:
                raise InvalidScientificProblem(f"node {receipt.node_id!r} is {receipt.status.value} but exposes outputs")
        extra = set(self.node_outputs) - {n for n, r in receipts.items() if r.status is NodeStatus.SUCCEEDED}
        if extra:
            raise InvalidScientificProblem(f"outputs exist for nodes that did not succeed: {sorted(extra)}")
        by_obs = {o.observable_id: o for o in self.observables}
        if set(by_obs) != {o.observable_id for o in self.plan.observables}:
            raise InvalidScientificProblem("result observables differ from the requested observables")
        for obs in self.observables:
            receipt = receipts.get(obs.node_id)
            if obs.availability is Availability.AVAILABLE:
                if receipt is None or receipt.status is not NodeStatus.SUCCEEDED:
                    raise InvalidScientificProblem(f"observable {obs.observable_id!r} is AVAILABLE but its producing node did not succeed")
                held = self.node_outputs.get(obs.node_id, {}).get(obs.output_name)
                if held is None or held.digest != obs.value.digest:
                    raise InvalidScientificProblem(f"observable {obs.observable_id!r} does not carry the value its node produced")
        history = tuple(self.state_history)
        for a, b in zip(history, history[1:]):
            if b.previous_digest != a.digest or b.sequence != a.sequence + 1:
                raise InvalidScientificProblem("state history is not a digest chain")
        if history and (self.final_state is None or self.final_state.digest != history[-1].digest):
            raise InvalidScientificProblem("final state is not the last committed state")
        if history and (self.initial_state is None or self.initial_state.digest != history[0].digest):
            raise InvalidScientificProblem("initial state is not the first state")
        if self.status is RunStatus.SUCCEEDED and any(r.status is not NodeStatus.SUCCEEDED for r in self.node_receipts):
            raise InvalidScientificProblem("a SUCCEEDED run has a node that did not succeed")
        if self.status is RunStatus.SUCCEEDED and any(o.availability is not Availability.AVAILABLE for o in self.observables):
            raise InvalidScientificProblem("a SUCCEEDED run has an unavailable observable")
        # derived collections are re-derived, never trusted
        derived_refs = tuple(sorted({p for r in self.node_receipts for p in r.provider_records}))
        if tuple(sorted(self.provider_records)) != derived_refs:
            raise InvalidScientificProblem("result provider records differ from those its receipts carry")
        if self.trust_inputs.execution_status != self.status.value or \
                set(self.trust_inputs.provider_execution_identities) != {p.execution_identity_digest for p in derived_refs}:
            raise InvalidScientificProblem("result trust inputs differ from what its status and receipts state")
        unknown = tuple(sorted(f"{n}.{k}" for n, items in self.node_outputs.items() for k, v in items.items() if v.uncertainty.kind is UncertaintyKind.UNKNOWN))
        applic = tuple(sorted((r.node_id, a.check_id, a.status) for r in self.node_receipts for a in r.applicability))
        waived = tuple(sorted(n.node_id for n in self.plan.nodes if n.applicability_waiver))
        if (tuple(self.trust_inputs.unknown_uncertainty_outputs) != unknown or tuple(self.trust_inputs.applicability_reports) != applic
                or tuple(self.trust_inputs.waived_applicability) != waived):
            raise InvalidScientificProblem("result trust inputs differ from what its outputs, applicability reports and plan state (uncertainty and waivers are re-derived)")

    def observable(self, observable_id: str) -> ObservableResult:
        for item in self.observables:
            if item.observable_id == observable_id:
                return item
        raise KeyError(observable_id)

    def receipt(self, node_id: str) -> NodeReceipt:
        for item in self.node_receipts:
            if item.node_id == node_id:
                return item
        raise KeyError(node_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RESULT_SCHEMA, "classification": self.classification, "request_digest": self.request_digest, "plan_digest": self.plan_digest,
            "run_id": self.run_id, "status": self.status.value, "preflight": self.preflight.to_dict(), "plan": self.plan.to_dict(),
            "initial_state": None if self.initial_state is None else self.initial_state.to_dict(),
            "final_state": None if self.final_state is None else self.final_state.to_dict(),
            "state_history": [s.to_dict() for s in self.state_history], "node_receipts": [r.to_dict() for r in self.node_receipts],
            "node_outputs": _outputs_to_dict(self.node_outputs), "observables": [o.to_dict() for o in self.observables],
            "provider_records": [p.to_dict() for p in self.provider_records], "artifacts": [[n, a.to_dict()] for n, a in self.artifacts],
            "diagnostics": [list(d) for d in self.diagnostics],
            "resource_usage": {"wall_seconds": self.resource_usage.wall_seconds, "cpu_seconds": self.resource_usage.cpu_seconds,
                               "peak_memory_bytes": self.resource_usage.peak_memory_bytes,
                               "function_evaluations": self.resource_usage.function_evaluations},
            "checkpoints": [c.to_dict() for c in self.checkpoints], "provenance": [list(p) for p in self.provenance],
            "trust_inputs": self.trust_inputs.to_dict(),
        }

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())

    @property
    def scientific_digest(self) -> str:
        """Identity without operational facts (resource usage, attempt numbers, cache provenance, run label)."""
        payload = self.to_dict()
        for key in ("resource_usage", "run_id", "checkpoints"):
            payload.pop(key)
        payload["node_receipts"] = [r.scientific_digest for r in self.node_receipts]
        return digest_of(payload)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SystemRunResult":
        require_schema(payload, RESULT_SCHEMA)
        strict_keys(payload, {"schema", "classification", "request_digest", "plan_digest", "run_id", "status", "preflight", "plan", "initial_state",
                              "final_state", "state_history", "node_receipts", "node_outputs", "observables", "provider_records", "artifacts",
                              "diagnostics", "resource_usage", "checkpoints", "provenance", "trust_inputs"}, "system run result")
        ini, fin = payload["initial_state"], payload["final_state"]
        return cls(
            payload["request_digest"], payload["plan_digest"], payload["run_id"], RunStatus(payload["status"]),
            PreflightReport.from_dict(payload["preflight"]), SystemExecutionPlan.from_dict(payload["plan"]),
            None if ini is None else SystemState.from_dict(ini), None if fin is None else SystemState.from_dict(fin),
            tuple(SystemState.from_dict(s) for s in payload["state_history"]), tuple(NodeReceipt.from_dict(r) for r in payload["node_receipts"]),
            _outputs_from_dict(payload["node_outputs"]), tuple(ObservableResult.from_dict(o) for o in payload["observables"]),
            tuple(ProviderRecordRef.from_dict(p) for p in payload["provider_records"]),
            tuple((n, ArtifactRef.from_dict(a)) for n, a in payload["artifacts"]), tuple(tuple(d) for d in payload["diagnostics"]),
            ResourceUsage(**payload["resource_usage"]), tuple(SystemCheckpoint.from_dict(c) for c in payload["checkpoints"]),
            tuple(tuple(p) for p in payload["provenance"]), TrustInputs.from_dict(payload["trust_inputs"]), payload["classification"])


# ----------------------------------------------------------------------------------------------------- tracing
@dataclass(frozen=True)
class TraceLink:
    level: str
    ref: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "ref": self.ref, "detail": self.detail}


@dataclass(frozen=True)
class ResultTrace:
    """The lineage of one final quantity.  Gaps are reported, never filled in."""

    observable_id: str
    links: tuple[TraceLink, ...]
    gaps: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.gaps

    def levels(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(link.level for link in self.links))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TRACE_SCHEMA, "observable_id": self.observable_id, "links": [x.to_dict() for x in self.links], "gaps": list(self.gaps)}


def trace_result(result: SystemRunResult, observable_id: str) -> ResultTrace:
    """result -> producing node -> execution record -> provider (+version+digest) -> inputs -> state -> scenario/time -> sources.

    The walk is transitive: every upstream node the value depends on contributes its authority, delegated
    record, provider executions and configuration, and the derived material / environment nodes name
    what they resolved.  Nothing is inferred: a missing link is reported as a gap.
    """
    obs = result.observable(observable_id)
    links: list[TraceLink] = [TraceLink("result", observable_id, f"{obs.availability.value} {obs.value.value if obs.value else ''}".strip())]
    gaps: list[str] = []
    if obs.availability is not Availability.AVAILABLE:
        return ResultTrace(observable_id, tuple(links), (f"observable is {obs.availability.value}: {obs.reason}",))
    chain = (*result.plan.ancestors(obs.node_id), obs.node_id)
    for node_id in chain:
        receipt = result.receipt(node_id)
        node = result.plan.node(node_id)
        if receipt.status is not NodeStatus.SUCCEEDED:
            gaps.append(f"upstream node {node_id!r} is {receipt.status.value}")
            continue
        if node.derived:
            kind = {"resolve_material": "material", "evaluate_environment": "environment", "constraint_assessment": "constraint"}[node.kind.value]
            key = {"material": lambda: node.arg("resolved_digest"), "environment": lambda: node.arg("channel"),
                   "constraint": lambda: node.arg("constraint_id")}[kind]()
            links.append(TraceLink(kind, key, f"resolved by {node_id}, receipt {receipt.digest[:16]}"))
            continue
        links.append(TraceLink("node", node_id, f"receipt {receipt.digest[:16]} status {receipt.status.value}"))
        if receipt.cache_hit:
            links.append(TraceLink("reuse", receipt.original_receipt_digest, f"{node_id!r} was NOT executed in this run: exact reuse of an earlier execution"))
        links.append(TraceLink("authority", node.authority.authority_id, f"identity {receipt.authority_identity_digest[:16]}"))
        if receipt.delegated_record_digest:
            links.append(TraceLink("execution_record", receipt.delegated_record_digest, f"delegated runtime record of {node_id}"))
        if node.provider_binding_ids and not receipt.provider_records:
            gaps.append(f"node {node_id!r} names provider bindings but its receipt records no provider execution")
        for ref in receipt.provider_records:
            links.append(TraceLink("provider", f"{ref.provider_id}@{ref.provider_version}", f"provider digest {ref.provider_digest[:16] or 'unrecorded'}"))
            links.append(TraceLink("provider_execution", ref.execution_identity_digest, f"record {ref.record_digest[:16] or 'unrecorded'}"))
            if not ref.provider_digest:
                gaps.append(f"provider {ref.provider_id!r} recorded no build digest")
        if node.configuration_digest:
            links.append(TraceLink("configuration", node.configuration_digest, f"problem/configuration pinned for {node_id}"))
        elif node.provider_binding_ids:
            gaps.append(f"node {node_id!r} pins no configuration digest")
        if not receipt.state_before_digest:
            gaps.append(f"receipt of {node_id!r} names no state")
    final = result.receipt(obs.node_id)
    if final.state_before_digest:
        links.append(TraceLink("state", final.state_before_digest, "state the producing node executed from"))
    prov = dict(result.provenance)
    for level in ("system", "scenario", "timeline", "environment"):
        if level in prov:
            links.append(TraceLink(level, prov[level]))
        elif level == "environment":
            links.append(TraceLink("environment", "absent", "the request states it has no environment"))
        else:
            gaps.append(f"result provenance lacks the {level}")
    return ResultTrace(observable_id, tuple(links), tuple(gaps))
