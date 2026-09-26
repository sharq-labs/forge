"""Execution records: what an authority returns, what the executor receipts, and the authority contract.

Execution status is deliberately a different vocabulary from scientific support.  A node can
SUCCEED and its outputs still carry UNKNOWN uncertainty and no validation; that is the normal case.

Outputs are :class:`OutputValue` (a ``Quantity`` plus an explicit ``Uncertainty``, never a bare
number).  Larger results (fields, series, provider records) are *referenced* through
:class:`ArtifactRef` (kind + digest), so JSON never carries bulk data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..execution.orchestration.resources import ResourceUsage
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity
from ._common import digest_of, hex64, identifier, reject_non_finite, require_schema, schema, strict_keys, text, unique
from .plan import PlanNode
from .state import OwnerState, ProviderCheckpointRef, SystemState

OUTPUT_SCHEMA = schema("output_value")
ARTIFACT_SCHEMA = schema("artifact_ref")
PROVIDER_REF_SCHEMA = schema("provider_record_ref")
APPLICABILITY_SCHEMA = schema("applicability_report")
PROPOSAL_SCHEMA = schema("state_proposal")
OUTCOME_SCHEMA = schema("node_outcome")
RECEIPT_SCHEMA = schema("node_receipt")
USAGE_SCHEMA = schema("resource_usage")


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    REFUSED = "refused"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class OutputValue:
    """One node output: a value with an explicit uncertainty statement and a stated origin."""

    value: Quantity
    uncertainty: Uncertainty
    origin: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.value, Quantity) or not isinstance(self.uncertainty, Uncertainty):
            raise InvalidScientificProblem("an output needs a Quantity and an explicit Uncertainty (Uncertainty.unknown() is explicit)")
        reject_non_finite(self.value.to_dict(), "output value")
        object.__setattr__(self, "origin", str(self.origin).strip())

    def to_dict(self) -> dict[str, Any]:
        return {"schema": OUTPUT_SCHEMA, "value": self.value.to_dict(), "uncertainty": self.uncertainty.to_dict(), "origin": self.origin}

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OutputValue":
        require_schema(payload, OUTPUT_SCHEMA)
        strict_keys(payload, {"schema", "value", "uncertainty", "origin"}, "output value")
        return cls(Quantity.from_dict(payload["value"]), Uncertainty.from_dict(payload["uncertainty"]), payload["origin"])


@dataclass(frozen=True, order=True)
class ArtifactRef:
    """A reference to bulk or structured data held elsewhere (field, series, provider record, checkpoint)."""

    name: str
    kind: str
    digest: str
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", identifier(self.name, "artifact name"))
        object.__setattr__(self, "kind", identifier(self.kind, "artifact kind"))
        object.__setattr__(self, "digest", hex64(self.digest, "artifact digest"))
        object.__setattr__(self, "description", str(self.description).strip())

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ARTIFACT_SCHEMA, "name": self.name, "kind": self.kind, "digest": self.digest, "description": self.description}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactRef":
        require_schema(payload, ARTIFACT_SCHEMA)
        strict_keys(payload, {"schema", "name", "kind", "digest", "description"}, "artifact ref")
        return cls(payload["name"], payload["kind"], payload["digest"], payload["description"])


@dataclass(frozen=True, order=True)
class ProviderRecordRef:
    """The provider execution a node's outputs came from (identity, not the bulk record)."""

    provider_id: str
    provider_version: str
    provider_digest: str
    execution_identity_digest: str
    record_digest: str
    succeeded: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", identifier(self.provider_id, "provider id"))
        object.__setattr__(self, "provider_version", text(self.provider_version, "provider version"))
        object.__setattr__(self, "provider_digest", hex64(self.provider_digest, "provider digest", allow_empty=True))
        object.__setattr__(self, "execution_identity_digest", hex64(self.execution_identity_digest, "execution identity digest"))
        object.__setattr__(self, "record_digest", hex64(self.record_digest, "provider record digest", allow_empty=True))
        if not isinstance(self.succeeded, bool):
            raise InvalidScientificProblem("succeeded must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROVIDER_REF_SCHEMA, "provider_id": self.provider_id, "provider_version": self.provider_version,
                "provider_digest": self.provider_digest, "execution_identity_digest": self.execution_identity_digest,
                "record_digest": self.record_digest, "succeeded": self.succeeded}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProviderRecordRef":
        require_schema(payload, PROVIDER_REF_SCHEMA)
        strict_keys(payload, {"schema", "provider_id", "provider_version", "provider_digest", "execution_identity_digest", "record_digest",
                              "succeeded"}, "provider record ref")
        return cls(payload["provider_id"], payload["provider_version"], payload["provider_digest"], payload["execution_identity_digest"],
                   payload["record_digest"], payload["succeeded"])

    @classmethod
    def of_record(cls, record: Any) -> "ProviderRecordRef":
        """From a ``ProviderExecutionRecord`` (identity fields are read from the record, not stated by a caller)."""
        identity = record.identity
        return cls(identity.provider_id, identity.provider_version, identity.provider_digest, identity.digest, record.digest, bool(record.succeeded))


_APPLICABILITY = ("within", "outside", "unknown")


@dataclass(frozen=True, order=True)
class ApplicabilityReport:
    """One runtime applicability assessment, evaluated on the SOLVED state."""

    check_id: str
    status: str
    evidence_digest: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", identifier(self.check_id, "applicability check id"))
        if self.status not in _APPLICABILITY:
            raise InvalidScientificProblem(f"applicability status must be one of {_APPLICABILITY}")
        object.__setattr__(self, "evidence_digest", hex64(self.evidence_digest, "applicability evidence digest", allow_empty=True))
        object.__setattr__(self, "reason", str(self.reason).strip())
        if self.status == "within" and not self.evidence_digest:
            raise InvalidScientificProblem("a 'within' applicability report must carry the digest of the evidence it was decided on")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": APPLICABILITY_SCHEMA, "check_id": self.check_id, "status": self.status, "evidence_digest": self.evidence_digest,
                "reason": self.reason}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ApplicabilityReport":
        require_schema(payload, APPLICABILITY_SCHEMA)
        strict_keys(payload, {"schema", "check_id", "status", "evidence_digest", "reason"}, "applicability report")
        return cls(payload["check_id"], payload["status"], payload["evidence_digest"], payload["reason"])


@dataclass(frozen=True)
class StateProposal:
    """What a node proposes to commit.  Nothing changes until the executor commits it."""

    time: Quantity
    updates: tuple[OwnerState, ...]
    provider_checkpoints: tuple[ProviderCheckpointRef, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.time, Quantity):
            raise InvalidScientificProblem("a state proposal needs a time Quantity")
        if not tuple(self.updates):
            raise InvalidScientificProblem("a state proposal with no updates is not a proposal")
        object.__setattr__(self, "updates", tuple(self.updates))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROPOSAL_SCHEMA, "time": self.time.to_dict(), "updates": [u.to_dict() for u in self.updates],
                "provider_checkpoints": None if self.provider_checkpoints is None else [c.to_dict() for c in self.provider_checkpoints]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StateProposal":
        require_schema(payload, PROPOSAL_SCHEMA)
        strict_keys(payload, {"schema", "time", "updates", "provider_checkpoints"}, "state proposal")
        cps = payload["provider_checkpoints"]
        return cls(Quantity.from_dict(payload["time"]), tuple(OwnerState.from_dict(u) for u in payload["updates"]),
                   None if cps is None else tuple(ProviderCheckpointRef.from_dict(c) for c in cps))


OUTCOME_STATUSES = ("succeeded", "refused", "failed")


@dataclass(frozen=True)
class NodeOutcome:
    """What an authority reports for one node execution.

    A refused or failed outcome carries no outputs and no state proposal; if an authority hands
    them over anyway the executor discards them (a failed execution exposes nothing).
    """

    status: str
    outputs: Mapping[str, OutputValue] = field(default_factory=dict)
    reason: str = ""
    provider_records: tuple[ProviderRecordRef, ...] = ()
    applicability: tuple[ApplicabilityReport, ...] = ()
    state_proposal: StateProposal | None = None
    artifacts: tuple[ArtifactRef, ...] = ()
    resource_usage: ResourceUsage = field(default_factory=ResourceUsage)
    diagnostics: Mapping[str, str] = field(default_factory=dict)
    #: digest of the delegated runtime's own record (a coupled run, a multi-timescale run, ...)
    delegated_record_digest: str = ""
    #: this authority's own checkpoint identity after the node, and whether it DECLARES it complete
    authority_checkpoint: tuple[str, bool] | None = None

    def __post_init__(self) -> None:
        if self.status not in OUTCOME_STATUSES:
            raise InvalidScientificProblem(f"outcome status must be one of {OUTCOME_STATUSES}")
        if self.status != "succeeded" and not str(self.reason).strip():
            raise InvalidScientificProblem("a refused or failed outcome states its reason")
        object.__setattr__(self, "outputs", dict(self.outputs))
        object.__setattr__(self, "provider_records", tuple(self.provider_records))
        object.__setattr__(self, "applicability", tuple(self.applicability))
        object.__setattr__(self, "artifacts", tuple(sorted(self.artifacts)))
        object.__setattr__(self, "diagnostics", {str(k): str(v) for k, v in dict(self.diagnostics).items()})
        object.__setattr__(self, "delegated_record_digest", hex64(self.delegated_record_digest, "delegated record digest", allow_empty=True))

    @classmethod
    def refused(cls, reason: str, **kw: Any) -> "NodeOutcome":
        return cls("refused", reason=reason, **kw)

    @classmethod
    def failed(cls, reason: str, **kw: Any) -> "NodeOutcome":
        return cls("failed", reason=reason, **kw)


@dataclass(frozen=True)
class InputValue:
    """A value handed to a node, with the identity of the producer that made it."""

    name: str
    value: Quantity
    uncertainty: Uncertainty
    producer_node: str
    producer_output: str
    #: digest binding this value to (run, producer node, plan, producer execution identity): an in-run staleness check
    producer_stamp: str
    #: the producer's RUN-INDEPENDENT execution identity; this (not the stamp) is what identifies the input's content
    producer_identity: str = ""

    @property
    def digest(self) -> str:
        return digest_of({"name": self.name, "value": self.value.to_dict(), "uncertainty": self.uncertainty.to_dict(),
                          "producer_node": self.producer_node, "producer_output": self.producer_output, "producer_identity": self.producer_identity})


@dataclass(frozen=True)
class NodeCall:
    """Everything an authority is given for one execution."""

    node: PlanNode
    inputs: Mapping[str, InputValue]
    state: SystemState
    run_id: str
    plan_digest: str
    request_digest: str
    attempt: int
    context: "RuntimeContext"

    def value(self, name: str) -> Quantity:
        return self.inputs[name].value


class NodeAuthority(ABC):
    """An execution authority a node delegates to.  It computes; it never decides validity.

    ``identity_digest`` must change whenever anything result-changing about the authority changes
    (configuration, provider identity, delegated runtime identity).  The plan pins it.
    """

    authority_id: str
    kind: str
    identity_digest: str
    #: whether this authority guarantees the same outputs for the same identity (else replay is 'not guaranteed')
    deterministic: bool = False
    supports_checkpoint: bool = False
    #: True when the authority holds no state between executions (so it never blocks checkpoint completeness)
    stateless: bool = False
    #: True only for an authority that DECLARES its output uncertainty accounts for its inputs' uncertainty. Otherwise a quantified
    #: output uncertainty from UNKNOWN inputs is refused (UNKNOWN in, UNKNOWN out).
    accounts_for_input_uncertainty: bool = False

    def committed(self, call: "NodeCall", outcome: "NodeOutcome") -> None:
        """Called by the executor only AFTER the node's outputs, provider records, applicability and state proposal were all
        accepted and committed.  An authority must promote any pending internal state here, never in ``execute``."""

    @abstractmethod
    def execute(self, call: NodeCall) -> NodeOutcome:
        ...

    def preflight_findings(self, node: PlanNode, context: "RuntimeContext") -> tuple[tuple[str, str], ...]:
        """Known-in-advance problems this authority can see for a node: ``(code, message)`` pairs, all blocking."""
        return ()

    def unsupported_scenario_features(self, scenario: Any) -> tuple[str, ...]:
        """Scenario features this authority cannot honour (refused before execution)."""
        return ()

    def checkpoint_payload(self) -> Mapping[str, Any] | None:
        """This authority's own resumable state (JSON-able), or ``None`` if it has none / cannot state it."""
        return None

    def restore(self, payload: Mapping[str, Any]) -> None:
        raise InvalidScientificProblem(f"authority {self.authority_id!r} cannot restore a checkpoint")


class AuthorityMismatch(InvalidScientificProblem):
    """A registered authority does not have the identity the plan pinned."""


class AuthorityRegistry:
    """Authorities by id.  Lookup is by the plan's :class:`AuthorityRef`: id AND identity digest must match."""

    def __init__(self, authorities: tuple[NodeAuthority, ...] = ()) -> None:
        self._items: dict[str, NodeAuthority] = {}
        for item in authorities:
            self.register(item)

    def register(self, authority: NodeAuthority) -> None:
        if not isinstance(authority, NodeAuthority):
            raise InvalidScientificProblem("only NodeAuthority instances can be registered")
        if authority.authority_id in self._items:
            raise InvalidScientificProblem(f"authority {authority.authority_id!r} is already registered")
        self._items[authority.authority_id] = authority

    def has(self, authority_id: str) -> bool:
        return authority_id in self._items

    def resolve(self, ref: Any) -> NodeAuthority:
        item = self._items.get(ref.authority_id)
        if item is None:
            raise AuthorityMismatch(f"no authority {ref.authority_id!r} is registered (no substitute is chosen)")
        if item.identity_digest != ref.identity_digest or item.kind != ref.kind:
            raise AuthorityMismatch(
                f"authority {ref.authority_id!r} has identity {item.identity_digest[:12]}../kind {item.kind!r}, not the pinned "
                f"{ref.identity_digest[:12]}../{ref.kind!r}")
        return item

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))


@dataclass
class RuntimeContext:
    """The supplied scientific objects and services.  Their digests are verified against the request."""

    authorities: AuthorityRegistry
    system: Any = None
    scenario: Any = None
    timeline: Any = None
    environment: Any = None
    material_states: Mapping[str, Any] = field(default_factory=dict)      # MaterialState digest -> object
    resolved_properties: Mapping[str, Any] = field(default_factory=dict)  # ResolvedProperty digest -> object
    constraints: Mapping[str, Any] = field(default_factory=dict)          # ConstraintDefinition digest -> object
    providers: Any = None                                                 # a ProviderRegistry, or None if no provider is used


@dataclass(frozen=True)
class NodeReceipt:
    """The immutable record of one node's execution attempt."""

    node_id: str
    status: NodeStatus
    plan_digest: str
    request_digest: str
    node_digest: str
    authority_identity_digest: str
    execution_identity_digest: str
    input_digests: tuple[tuple[str, str], ...]
    output_digests: tuple[tuple[str, str], ...]
    provider_records: tuple[ProviderRecordRef, ...]
    applicability: tuple[ApplicabilityReport, ...]
    artifacts: tuple[ArtifactRef, ...]
    state_before_digest: str
    state_after_digest: str
    resource_usage: ResourceUsage
    reason: str
    blocked_by: tuple[str, ...]
    attempt: int
    delegated_record_digest: str = ""
    cache_hit: bool = False
    original_receipt_digest: str = ""
    authority_checkpoint: tuple[str, bool] | None = None
    stamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RECEIPT_SCHEMA, "node_id": self.node_id, "status": self.status.value, "plan_digest": self.plan_digest,
            "request_digest": self.request_digest, "node_digest": self.node_digest, "authority_identity_digest": self.authority_identity_digest,
            "execution_identity_digest": self.execution_identity_digest, "input_digests": [list(p) for p in self.input_digests],
            "output_digests": [list(p) for p in self.output_digests], "provider_records": [p.to_dict() for p in self.provider_records],
            "applicability": [a.to_dict() for a in self.applicability], "artifacts": [a.to_dict() for a in self.artifacts],
            "state_before_digest": self.state_before_digest, "state_after_digest": self.state_after_digest,
            "resource_usage": {"wall_seconds": self.resource_usage.wall_seconds, "cpu_seconds": self.resource_usage.cpu_seconds,
                               "peak_memory_bytes": self.resource_usage.peak_memory_bytes,
                               "function_evaluations": self.resource_usage.function_evaluations},
            "reason": self.reason, "blocked_by": list(self.blocked_by), "attempt": self.attempt,
            "delegated_record_digest": self.delegated_record_digest, "cache_hit": self.cache_hit,
            "original_receipt_digest": self.original_receipt_digest,
            "authority_checkpoint": None if self.authority_checkpoint is None else list(self.authority_checkpoint), "stamp": self.stamp,
        }

    @property
    def scientific_digest(self) -> str:
        """The receipt without operational fields (resource usage, attempt, cache provenance, the run-bound staleness stamp): same science, same digest."""
        payload = self.to_dict()
        for key in ("resource_usage", "attempt", "cache_hit", "original_receipt_digest", "stamp"):
            payload.pop(key)
        return digest_of(payload)

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NodeReceipt":
        require_schema(payload, RECEIPT_SCHEMA)
        strict_keys(payload, {"schema", "node_id", "status", "plan_digest", "request_digest", "node_digest", "authority_identity_digest",
                              "execution_identity_digest", "input_digests", "output_digests", "provider_records", "applicability", "artifacts",
                              "state_before_digest", "state_after_digest", "resource_usage", "reason", "blocked_by", "attempt",
                              "delegated_record_digest", "cache_hit", "original_receipt_digest", "authority_checkpoint", "stamp"}, "node receipt")
        cp = payload["authority_checkpoint"]
        return cls(
            payload["node_id"], NodeStatus(payload["status"]), payload["plan_digest"], payload["request_digest"], payload["node_digest"],
            payload["authority_identity_digest"], payload["execution_identity_digest"], tuple(tuple(p) for p in payload["input_digests"]),
            tuple(tuple(p) for p in payload["output_digests"]), tuple(ProviderRecordRef.from_dict(p) for p in payload["provider_records"]),
            tuple(ApplicabilityReport.from_dict(a) for a in payload["applicability"]), tuple(ArtifactRef.from_dict(a) for a in payload["artifacts"]),
            payload["state_before_digest"], payload["state_after_digest"], ResourceUsage(**payload["resource_usage"]), payload["reason"],
            tuple(payload["blocked_by"]), payload["attempt"], payload["delegated_record_digest"], payload["cache_hit"],
            payload["original_receipt_digest"], None if cp is None else (cp[0], cp[1]), payload["stamp"])
