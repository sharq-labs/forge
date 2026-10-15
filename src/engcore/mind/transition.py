"""Deterministic next-action transition.

The core reads a typed problem, the authority statuses already recorded on
its hypotheses, and the dependencies those statuses left open. It then
admits or rejects candidate actions. An optional language-model proposal is
advisory: it is recorded and cannot change the selected action.

No function in this module writes ``supported_by_authority`` or
``refuted_by_authority``. A caller who already holds such a status may put
it in the input state, with the authority result id that issued it. The
transition refuses to replace it. Evidence becoming unavailable blocks the
named dependency and leaves every non-descendant where it was. It does not
convert a refusal into physical infeasibility, and it does not revive a
dead branch. An availability result does not rewrite hypothesis status.

A capability action is not admissible while an applicability, identifiability,
or operating-point dependency that blocks the same question is anything
other than resolved. Resolved here means the dependency record is closed.
It does not mean the model is applicable. A negative outcome has to already
be present as a hypothesis status.

Information gain is a category, not a number. When more than one action
would address an open dependency of the unresolved question, the tie-break
is dependency id then action id. That order is replay identity, not a
scientific value ranking.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


SOFTWARE_VERSION = "engcore.mind.transition/1.0.0"

_TERMINAL = "supported_by_authority", "refuted_by_authority"
_OPEN_QUESTION = "unresolved", "active"


class MindRefusal(Exception):
    """The transition refused an input that would cross the authority boundary."""


class HypothesisStatus(str, Enum):
    ACTIVE = "active"
    SUPPORTED_BY_AUTHORITY = "supported_by_authority"
    REFUTED_BY_AUTHORITY = "refuted_by_authority"
    UNRESOLVED = "unresolved"
    STALE = "stale"


class DependencyKind(str, Enum):
    OPERATING_POINT_EVIDENCE = "operating_point_evidence"
    IDENTIFIABILITY = "identifiability"
    APPLICABILITY = "applicability"
    CAPABILITY_EXECUTION = "capability_execution"


class DependencyStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    BLOCKED = "blocked"
    DEAD = "dead"


class ActionType(str, Enum):
    RUN_CAPABILITY = "run_capability"
    REQUEST_EVIDENCE = "request_evidence"
    CHECK_APPLICABILITY = "check_applicability"
    CHECK_IDENTIFIABILITY = "check_identifiability"
    STOP = "stop"


class BoundaryRequest(str, Enum):
    NONE = "none"
    DECLARE_TRUTH = "declare_truth"
    MARK_EVIDENCE_VALID = "mark_evidence_valid"
    MANUFACTURE_EVIDENCE = "manufacture_evidence"
    INVENT_UNCERTAINTY = "invent_uncertainty"
    EXTEND_APPLICABILITY = "extend_applicability"
    CHANGE_THRESHOLD = "change_threshold"
    DECLARE_VALIDATION = "declare_validation"
    CONVERT_UNKNOWN_TO_ZERO = "convert_unknown_to_zero"
    OVERRIDE_REFUSAL = "override_refusal"
    SET_CLAIM = "set_claim"
    DECLARE_PHYSICAL_INFEASIBILITY = "declare_physical_infeasibility"


class InformationGain(str, Enum):
    OPEN_DEPENDENCY = "open_dependency"
    ALREADY_RESOLVED = "already_resolved"
    DEAD_BRANCH = "dead_branch"
    AUTHORITY_OVERRIDE = "authority_override"
    PREREQUISITE_OPEN = "prerequisite_open"
    NOT_ON_QUESTION = "not_on_question"
    STOP = "stop"


class ResultKind(str, Enum):
    EVIDENCE_UNAVAILABLE = "evidence_unavailable"


_ACTION_FOR_KIND = {
    DependencyKind.OPERATING_POINT_EVIDENCE: ActionType.REQUEST_EVIDENCE,
    DependencyKind.IDENTIFIABILITY: ActionType.CHECK_IDENTIFIABILITY,
    DependencyKind.APPLICABILITY: ActionType.CHECK_APPLICABILITY,
    DependencyKind.CAPABILITY_EXECUTION: ActionType.RUN_CAPABILITY,
}

_GATE_KINDS = frozenset({
    DependencyKind.APPLICABILITY,
    DependencyKind.IDENTIFIABILITY,
    DependencyKind.OPERATING_POINT_EVIDENCE,
})


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MindRefusal(f"{field} must be a non-empty string")
    return value


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _enum(cls: type[Enum], value: Any, field: str) -> Enum:
    if isinstance(value, cls):
        return value
    if not isinstance(value, str):
        raise MindRefusal(f"{field} must be a string token")
    try:
        return cls(value)
    except ValueError as exc:
        raise MindRefusal(f"unknown {field}: {value!r}") from exc


def _id_tuple(values: Any, field: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise MindRefusal(f"{field} must be a list of ids")
    cleaned = tuple(_text(item, field) for item in values)
    if len(set(cleaned)) != len(cleaned):
        raise MindRefusal(f"{field} contains a duplicate id")
    return tuple(sorted(cleaned))


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MindRefusal(f"{field} must be an object")
    return dict(value)


def _require_fields(payload: Mapping[str, Any], allowed: set[str], field: str) -> None:
    extra = set(payload) - allowed
    missing = allowed - set(payload)
    if extra or missing:
        raise MindRefusal(
            f"{field} fields mismatch; missing={sorted(missing)} extra={sorted(extra)}"
        )


def canonical_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class MindProblem:
    problem_id: str
    question_hypothesis_id: str
    statement: str
    source_revision: str
    run_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "problem_id": self.problem_id,
            "question_hypothesis_id": self.question_hypothesis_id,
            "run_id": self.run_id,
            "source_revision": self.source_revision,
            "statement": self.statement,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MindProblem":
        data = _mapping(payload, "problem")
        _require_fields(
            data,
            {
                "problem_id",
                "question_hypothesis_id",
                "statement",
                "source_revision",
                "run_id",
            },
            "problem",
        )
        return cls(
            problem_id=_text(data["problem_id"], "problem_id"),
            question_hypothesis_id=_text(
                data["question_hypothesis_id"], "question_hypothesis_id"
            ),
            statement=_text(data["statement"], "statement"),
            source_revision=_text(data["source_revision"], "source_revision"),
            run_id=_text(data["run_id"], "run_id"),
        )


@dataclass(frozen=True)
class MindHypothesis:
    hypothesis_id: str
    status: HypothesisStatus
    statement: str
    authority_result_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hypothesis_id", _text(self.hypothesis_id, "hypothesis_id"))
        object.__setattr__(self, "statement", _text(self.statement, "statement"))
        status = _enum(HypothesisStatus, self.status, "hypothesis status")
        object.__setattr__(self, "status", status)
        authority = _optional_text(self.authority_result_id, "authority_result_id")
        object.__setattr__(self, "authority_result_id", authority)
        if status.value in _TERMINAL and authority is None:
            raise MindRefusal(
                f"hypothesis {self.hypothesis_id} carries {status.value} "
                "without an authority result id"
            )
        if status.value in _OPEN_QUESTION and authority is not None:
            raise MindRefusal(
                f"hypothesis {self.hypothesis_id} is {status.value} and cannot "
                "carry an authority result id"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_result_id": self.authority_result_id,
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MindHypothesis":
        data = _mapping(payload, "hypothesis")
        _require_fields(
            data,
            {"hypothesis_id", "status", "statement", "authority_result_id"},
            "hypothesis",
        )
        return cls(
            hypothesis_id=data["hypothesis_id"],
            status=data["status"],
            statement=data["statement"],
            authority_result_id=data["authority_result_id"],
        )


@dataclass(frozen=True)
class Dependency:
    dependency_id: str
    kind: DependencyKind
    status: DependencyStatus
    blocks: tuple[str, ...]
    upstream_result_ids: tuple[str, ...] = ()
    prerequisite_ids: tuple[str, ...] = ()
    availability_observation_id: str | None = None
    availability_result_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependency_id", _text(self.dependency_id, "dependency_id"))
        object.__setattr__(self, "kind", _enum(DependencyKind, self.kind, "dependency kind"))
        object.__setattr__(
            self, "status", _enum(DependencyStatus, self.status, "dependency status")
        )
        object.__setattr__(self, "blocks", _id_tuple(self.blocks, "blocks"))
        object.__setattr__(
            self,
            "upstream_result_ids",
            _id_tuple(self.upstream_result_ids, "upstream_result_ids"),
        )
        object.__setattr__(
            self,
            "prerequisite_ids",
            _id_tuple(self.prerequisite_ids, "prerequisite_ids"),
        )
        observation = _optional_text(
            self.availability_observation_id, "availability_observation_id"
        )
        result_id = _optional_text(self.availability_result_id, "availability_result_id")
        object.__setattr__(self, "availability_observation_id", observation)
        object.__setattr__(self, "availability_result_id", result_id)
        if self.status is DependencyStatus.BLOCKED:
            if observation is None or result_id is None:
                raise MindRefusal(
                    f"blocked dependency {self.dependency_id} must cite the availability "
                    "result and observation"
                )
        elif observation is not None or result_id is not None:
            raise MindRefusal(
                f"dependency {self.dependency_id} cites an availability result "
                "without being blocked"
            )
        if not self.blocks:
            raise MindRefusal(f"dependency {self.dependency_id} blocks nothing")

    def to_dict(self) -> dict[str, Any]:
        return {
            "availability_observation_id": self.availability_observation_id,
            "availability_result_id": self.availability_result_id,
            "blocks": list(self.blocks),
            "dependency_id": self.dependency_id,
            "kind": self.kind.value,
            "prerequisite_ids": list(self.prerequisite_ids),
            "status": self.status.value,
            "upstream_result_ids": list(self.upstream_result_ids),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Dependency":
        data = _mapping(payload, "dependency")
        _require_fields(
            data,
            {
                "dependency_id",
                "kind",
                "status",
                "blocks",
                "upstream_result_ids",
                "prerequisite_ids",
                "availability_observation_id",
                "availability_result_id",
            },
            "dependency",
        )
        return cls(
            dependency_id=data["dependency_id"],
            kind=data["kind"],
            status=data["status"],
            blocks=tuple(data["blocks"]),
            upstream_result_ids=tuple(data["upstream_result_ids"]),
            prerequisite_ids=tuple(data["prerequisite_ids"]),
            availability_observation_id=data["availability_observation_id"],
            availability_result_id=data["availability_result_id"],
        )


@dataclass(frozen=True)
class CandidateAction:
    action_id: str
    action_type: ActionType
    reason: str
    dependency_id: str | None
    boundary_request: BoundaryRequest = BoundaryRequest.NONE
    capability_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", _text(self.action_id, "action_id"))
        action_type = _enum(ActionType, self.action_type, "action type")
        object.__setattr__(self, "action_type", action_type)
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        boundary = _enum(BoundaryRequest, self.boundary_request, "boundary request")
        object.__setattr__(self, "boundary_request", boundary)
        capability = _optional_text(self.capability_id, "capability_id")
        object.__setattr__(self, "capability_id", capability)
        if action_type is ActionType.STOP:
            if self.dependency_id is not None or capability is not None:
                raise MindRefusal("STOP carries no dependency and no capability")
            if boundary is not BoundaryRequest.NONE:
                raise MindRefusal("STOP cannot request an authority change")
            object.__setattr__(self, "dependency_id", None)
        else:
            object.__setattr__(
                self, "dependency_id", _text(self.dependency_id, "dependency_id")
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "boundary_request": self.boundary_request.value,
            "capability_id": self.capability_id,
            "dependency_id": self.dependency_id,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateAction":
        data = _mapping(payload, "action")
        _require_fields(
            data,
            {
                "action_id",
                "action_type",
                "reason",
                "dependency_id",
                "boundary_request",
                "capability_id",
            },
            "action",
        )
        return cls(
            action_id=data["action_id"],
            action_type=data["action_type"],
            reason=data["reason"],
            dependency_id=data["dependency_id"],
            boundary_request=data["boundary_request"],
            capability_id=data["capability_id"],
        )


@dataclass(frozen=True)
class ActionResult:
    result_id: str
    action_id: str
    kind: ResultKind
    target_dependency_id: str
    observation_id: str
    problem_id: str
    run_id: str
    source_revision: str
    state_digest: str
    physical_infeasibility_claimed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_id", _text(self.result_id, "result_id"))
        object.__setattr__(self, "action_id", _text(self.action_id, "action_id"))
        object.__setattr__(self, "kind", _enum(ResultKind, self.kind, "result kind"))
        object.__setattr__(
            self,
            "target_dependency_id",
            _text(self.target_dependency_id, "target_dependency_id"),
        )
        object.__setattr__(
            self, "observation_id", _text(self.observation_id, "observation_id")
        )
        object.__setattr__(self, "problem_id", _text(self.problem_id, "problem_id"))
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id"))
        object.__setattr__(
            self, "source_revision", _text(self.source_revision, "source_revision")
        )
        object.__setattr__(self, "state_digest", _text(self.state_digest, "state_digest"))
        claimed = self.physical_infeasibility_claimed
        if type(claimed) is not bool:
            raise MindRefusal("physical_infeasibility_claimed must be a boolean")
        if claimed:
            raise MindRefusal(
                "an evidence-availability result cannot claim physical infeasibility"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "kind": self.kind.value,
            "observation_id": self.observation_id,
            "physical_infeasibility_claimed": False,
            "problem_id": self.problem_id,
            "result_id": self.result_id,
            "run_id": self.run_id,
            "source_revision": self.source_revision,
            "state_digest": self.state_digest,
            "target_dependency_id": self.target_dependency_id,
        }


@dataclass(frozen=True)
class MindState:
    problem: MindProblem
    hypotheses: tuple[MindHypothesis, ...]
    dependencies: tuple[Dependency, ...]
    actions: tuple[CandidateAction, ...]
    attempted_action_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.problem, MindProblem):
            raise MindRefusal("problem must be a MindProblem")
        hypotheses = _unique(self.hypotheses, "hypothesis_id", MindHypothesis, "hypotheses")
        dependencies = _unique(self.dependencies, "dependency_id", Dependency, "dependencies")
        actions = _unique(self.actions, "action_id", CandidateAction, "actions")
        attempted = _id_tuple(self.attempted_action_ids, "attempted_action_ids")
        object.__setattr__(self, "hypotheses", hypotheses)
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "actions", actions)
        object.__setattr__(self, "attempted_action_ids", attempted)
        known_hypotheses = {item.hypothesis_id for item in hypotheses}
        known_dependencies = {item.dependency_id for item in dependencies}
        if self.problem.question_hypothesis_id not in known_hypotheses:
            raise MindRefusal("question hypothesis is not in the state")
        for dependency in dependencies:
            unknown = set(dependency.blocks) - known_hypotheses
            if unknown:
                raise MindRefusal(
                    f"dependency {dependency.dependency_id} blocks unknown hypotheses {sorted(unknown)}"
                )
            missing = set(dependency.prerequisite_ids) - known_dependencies
            if missing:
                raise MindRefusal(
                    f"dependency {dependency.dependency_id} names unknown prerequisites {sorted(missing)}"
                )
            if dependency.dependency_id in dependency.prerequisite_ids:
                raise MindRefusal(
                    f"dependency {dependency.dependency_id} cannot prerequisite itself"
                )
        known_actions = {item.action_id for item in actions}
        unknown_attempts = set(attempted) - known_actions
        if unknown_attempts:
            raise MindRefusal(f"attempted actions are not candidates: {sorted(unknown_attempts)}")
        for action in actions:
            if action.action_type is ActionType.STOP:
                continue
            if action.dependency_id not in known_dependencies:
                raise MindRefusal(
                    f"action {action.action_id} names unknown dependency {action.dependency_id}"
                )
        if sum(item.action_type is ActionType.STOP for item in actions) != 1:
            raise MindRefusal("the candidate set must contain exactly one STOP action")

    def hypothesis(self, hypothesis_id: str) -> MindHypothesis:
        for item in self.hypotheses:
            if item.hypothesis_id == hypothesis_id:
                return item
        raise MindRefusal(f"unknown hypothesis {hypothesis_id}")

    def dependency(self, dependency_id: str) -> Dependency:
        for item in self.dependencies:
            if item.dependency_id == dependency_id:
                return item
        raise MindRefusal(f"unknown dependency {dependency_id}")

    def action(self, action_id: str) -> CandidateAction:
        for item in self.actions:
            if item.action_id == action_id:
                return item
        raise MindRefusal(f"unknown action {action_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [item.to_dict() for item in self.actions],
            "attempted_action_ids": list(self.attempted_action_ids),
            "dependencies": [item.to_dict() for item in self.dependencies],
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "problem": self.problem.to_dict(),
            "software_version": SOFTWARE_VERSION,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MindState":
        data = _mapping(payload, "state")
        _require_fields(
            data,
            {
                "problem",
                "hypotheses",
                "dependencies",
                "actions",
                "attempted_action_ids",
                "software_version",
            },
            "state",
        )
        if data["software_version"] != SOFTWARE_VERSION:
            raise MindRefusal(
                f"software version {data['software_version']!r} is not {SOFTWARE_VERSION}"
            )
        if not isinstance(data["hypotheses"], list):
            raise MindRefusal("hypotheses must be a list")
        if not isinstance(data["dependencies"], list):
            raise MindRefusal("dependencies must be a list")
        if not isinstance(data["actions"], list):
            raise MindRefusal("actions must be a list")
        return cls(
            problem=MindProblem.from_dict(data["problem"]),
            hypotheses=tuple(MindHypothesis.from_dict(item) for item in data["hypotheses"]),
            dependencies=tuple(Dependency.from_dict(item) for item in data["dependencies"]),
            actions=tuple(CandidateAction.from_dict(item) for item in data["actions"]),
            attempted_action_ids=tuple(data["attempted_action_ids"]),
        )


def _unique(items: Any, key: str, kind: type, field: str) -> tuple[Any, ...]:
    if not isinstance(items, (list, tuple)):
        raise MindRefusal(f"{field} must be a list")
    built = []
    for item in items:
        if not isinstance(item, kind):
            raise MindRefusal(f"{field} contains a value that is not {kind.__name__}")
        built.append(item)
    ids = [getattr(item, key) for item in built]
    if len(set(ids)) != len(ids):
        raise MindRefusal(f"{field} contains a duplicate id")
    return tuple(sorted(built, key=lambda item: getattr(item, key)))


@dataclass(frozen=True)
class ActionDecision:
    action_id: str
    admissible: bool
    information_gain: InformationGain
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "admissible": self.admissible,
            "information_gain": self.information_gain.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Selection:
    action_id: str
    action_type: ActionType
    dependency_id: str | None
    information_gain: InformationGain
    reason: str
    state_digest: str
    decisions: tuple[ActionDecision, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "decisions": [item.to_dict() for item in self.decisions],
            "dependency_id": self.dependency_id,
            "information_gain": self.information_gain.value,
            "reason": self.reason,
            "state_digest": self.state_digest,
        }


@dataclass(frozen=True)
class LlmActionProposal:
    model_identity: str
    prompt_identity: str
    proposed_action_id: str
    output_payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_identity", _text(self.model_identity, "model_identity"))
        object.__setattr__(self, "prompt_identity", _text(self.prompt_identity, "prompt_identity"))
        object.__setattr__(
            self, "proposed_action_id", _text(self.proposed_action_id, "proposed_action_id")
        )
        payload = _mapping(self.output_payload, "output_payload")
        try:
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        except (TypeError, ValueError) as exc:
            raise MindRefusal("output_payload is not canonical JSON") from exc
        object.__setattr__(self, "output_payload", payload)


@dataclass(frozen=True)
class ProposalRecord:
    model_identity: str
    prompt_identity: str
    input_digest: str
    output_digest: str
    proposed_action_id: str
    matches_selected_action: bool
    payload_interpreted: bool
    rejection_reason: str | None

    def __post_init__(self) -> None:
        if self.payload_interpreted is not False:
            raise MindRefusal("a proposal payload is not interpreted")

    def to_dict(self) -> dict[str, Any]:
        return {
            "matches_selected_action": self.matches_selected_action,
            "payload_interpreted": False,
            "input_digest": self.input_digest,
            "model_identity": self.model_identity,
            "output_digest": self.output_digest,
            "prompt_identity": self.prompt_identity,
            "proposed_action_id": self.proposed_action_id,
            "rejection_reason": self.rejection_reason,
        }


def _decision(
    action: CandidateAction,
    gain: InformationGain,
    reason: str,
    *,
    admissible: bool,
) -> ActionDecision:
    return ActionDecision(action.action_id, admissible, gain, reason)


def _classify(state: MindState, action: CandidateAction) -> ActionDecision:
    if action.action_type is ActionType.STOP:
        return _decision(
            action,
            InformationGain.STOP,
            "stop remains a candidate and does not change an authority result",
            admissible=True,
        )
    if action.boundary_request is not BoundaryRequest.NONE:
        return _decision(
            action,
            InformationGain.AUTHORITY_OVERRIDE,
            f"action requests {action.boundary_request.value}, which this layer cannot grant",
            admissible=False,
        )
    if action.action_id in state.attempted_action_ids:
        return _decision(
            action,
            InformationGain.DEAD_BRANCH,
            "this action was already attempted",
            admissible=False,
        )
    dependency = state.dependency(action.dependency_id or "")
    if dependency.status in {DependencyStatus.DEAD, DependencyStatus.BLOCKED}:
        return _decision(
            action,
            InformationGain.DEAD_BRANCH,
            f"dependency {dependency.dependency_id} is {dependency.status.value}",
            admissible=False,
        )
    if dependency.status is DependencyStatus.RESOLVED:
        return _decision(
            action,
            InformationGain.ALREADY_RESOLVED,
            f"dependency {dependency.dependency_id} is already resolved",
            admissible=False,
        )
    expected = _ACTION_FOR_KIND[dependency.kind]
    if action.action_type is not expected:
        return _decision(
            action,
            InformationGain.NOT_ON_QUESTION,
            f"dependency kind {dependency.kind.value} admits {expected.value}",
            admissible=False,
        )
    for prerequisite_id in dependency.prerequisite_ids:
        prerequisite = state.dependency(prerequisite_id)
        if prerequisite.status is not DependencyStatus.RESOLVED:
            return _decision(
                action,
                InformationGain.PREREQUISITE_OPEN,
                f"prerequisite {prerequisite_id} is {prerequisite.status.value}",
                admissible=False,
            )
    if dependency.kind is DependencyKind.CAPABILITY_EXECUTION:
        gate = _unresolved_gate(state)
        if gate is not None:
            return _decision(
                action,
                InformationGain.PREREQUISITE_OPEN,
                f"gate {gate.dependency_id} is {gate.status.value}",
                admissible=False,
            )
    blocked_statuses = [state.hypothesis(item).status for item in dependency.blocks]
    if all(
        status in {HypothesisStatus.REFUTED_BY_AUTHORITY, HypothesisStatus.STALE}
        for status in blocked_statuses
    ):
        return _decision(
            action,
            InformationGain.DEAD_BRANCH,
            "every hypothesis blocked by this dependency is already refused or stale",
            admissible=False,
        )
    question = state.hypothesis(state.problem.question_hypothesis_id)
    if question.status in {
        HypothesisStatus.SUPPORTED_BY_AUTHORITY,
        HypothesisStatus.REFUTED_BY_AUTHORITY,
    }:
        return _decision(
            action,
            InformationGain.ALREADY_RESOLVED,
            f"question {question.hypothesis_id} is already {question.status.value}",
            admissible=False,
        )
    if question.status is HypothesisStatus.STALE:
        return _decision(
            action,
            InformationGain.DEAD_BRANCH,
            "a stale question is not revived by another action",
            admissible=False,
        )
    if question.hypothesis_id not in dependency.blocks:
        return _decision(
            action,
            InformationGain.NOT_ON_QUESTION,
            "dependency does not block the question hypothesis",
            admissible=False,
        )
    return _decision(
        action,
        InformationGain.OPEN_DEPENDENCY,
        f"dependency {dependency.dependency_id} is open on {question.hypothesis_id}",
        admissible=True,
    )


def _unresolved_gate(state: MindState) -> Dependency | None:
    """A non-resolved scientific gate that blocks the question, if one exists."""
    question_id = state.problem.question_hypothesis_id
    for dependency in state.dependencies:
        if dependency.kind not in _GATE_KINDS:
            continue
        if question_id not in dependency.blocks:
            continue
        if dependency.status is not DependencyStatus.RESOLVED:
            return dependency
    return None


def select_next_action(state: MindState) -> Selection:
    """Return the admissible next action. Does not mutate ``state``."""
    decisions = tuple(_classify(state, action) for action in state.actions)
    by_id = {action.action_id: action for action in state.actions}
    workable = [
        by_id[decision.action_id]
        for decision in decisions
        if decision.admissible and decision.information_gain is InformationGain.OPEN_DEPENDENCY
    ]
    if workable:
        chosen = min(workable, key=lambda action: (action.dependency_id or "", action.action_id))
        gain = InformationGain.OPEN_DEPENDENCY
        reason = f"open dependency {chosen.dependency_id} blocks the question"
    else:
        chosen = next(action for action in state.actions if action.action_type is ActionType.STOP)
        gain = InformationGain.STOP
        question = state.hypothesis(state.problem.question_hypothesis_id)
        if question.status.value in _TERMINAL:
            reason = (
                f"question {question.hypothesis_id} is {question.status.value} "
                "by an existing authority result; no further action is useful"
            )
        else:
            reason = (
                f"no admissible action remains for question {question.hypothesis_id}"
            )
    return Selection(
        action_id=chosen.action_id,
        action_type=chosen.action_type,
        dependency_id=chosen.dependency_id,
        information_gain=gain,
        reason=reason,
        state_digest=canonical_digest(state.to_dict()),
        decisions=decisions,
    )


def apply_result(state: MindState, result: ActionResult) -> MindState:
    """Block one open dependency after an evidence-availability observation.

    Hypothesis statuses are copied unchanged. The observation is bound to this
    problem, run, revision, and the digest of the state it was applied to.
    """
    if result.problem_id != state.problem.problem_id:
        raise MindRefusal("availability result is for a different problem")
    if result.run_id != state.problem.run_id:
        raise MindRefusal("availability result is for a different run")
    if result.source_revision != state.problem.source_revision:
        raise MindRefusal("availability result is for a different source revision")
    if result.state_digest != canonical_digest(state.to_dict()):
        raise MindRefusal("availability result does not match this state")
    if result.action_id not in {item.action_id for item in state.actions}:
        raise MindRefusal(f"result names unknown action {result.action_id}")
    dependency = state.dependency(result.target_dependency_id)
    action = state.action(result.action_id)
    if action.dependency_id != dependency.dependency_id:
        raise MindRefusal("result action does not address the target dependency")
    decision = _classify(state, action)
    if not decision.admissible or decision.information_gain is not InformationGain.OPEN_DEPENDENCY:
        raise MindRefusal(
            f"action {action.action_id} is not an admissible open-dependency action"
        )
    dependencies = []
    for item in state.dependencies:
        if item.dependency_id == dependency.dependency_id:
            dependencies.append(
                Dependency(
                    dependency_id=item.dependency_id,
                    kind=item.kind,
                    status=DependencyStatus.BLOCKED,
                    blocks=item.blocks,
                    upstream_result_ids=item.upstream_result_ids,
                    prerequisite_ids=item.prerequisite_ids,
                    availability_observation_id=result.observation_id,
                    availability_result_id=result.result_id,
                )
            )
        else:
            dependencies.append(item)
    attempted = tuple(sorted({*state.attempted_action_ids, result.action_id}))
    return MindState(
        problem=state.problem,
        hypotheses=state.hypotheses,
        dependencies=tuple(dependencies),
        actions=state.actions,
        attempted_action_ids=attempted,
    )


def review_proposal(state: MindState, proposal: LlmActionProposal) -> ProposalRecord:
    """Record an advisory proposal. The state is not modified.

    ``matches_selected_action`` means the proposal names the action the
    deterministic core would select. The payload is hashed and not interpreted.
    A match is not evidence admission, a claim, or a validation result.
    """
    if not isinstance(proposal, LlmActionProposal):
        raise MindRefusal("proposal must be an LlmActionProposal")
    selected = select_next_action(state)
    output_digest = canonical_digest(dict(proposal.output_payload))
    matches = proposal.proposed_action_id == selected.action_id
    return ProposalRecord(
        model_identity=proposal.model_identity,
        prompt_identity=proposal.prompt_identity,
        input_digest=selected.state_digest,
        output_digest=output_digest,
        proposed_action_id=proposal.proposed_action_id,
        matches_selected_action=matches,
        payload_interpreted=False,
        rejection_reason=None if matches else "advisory proposal is not the admissible next action",
    )
