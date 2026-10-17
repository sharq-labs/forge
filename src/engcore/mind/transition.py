"""Deterministic next-action transition.

The core reads a typed problem, the authority statuses already recorded on
its hypotheses, and the dependencies those statuses left open. It then
admits or rejects candidate actions. An optional language-model proposal is
advisory: it is recorded and cannot change the selected action.

A caller who already holds ``supported_by_authority`` or
``refuted_by_authority`` may put it in the input state, with the authority
result id that issued it. The transition does not replace a refuted
hypothesis with support, and it does not clear a supported hypothesis.
The only new terminal support it copies is ``benchmark_validated``, and only
onto a hypothesis whose subject is the NAFEMS T3 benchmark subject cited by
``engcore.product.nafems_t3``. Advisory ``not_supported`` does not become a
refutation. A ledger maturity pass does not resolve a scientific dependency.
Evidence becoming unavailable blocks the named dependency and leaves every
other hypothesis where it was. It does not convert a refusal into physical
infeasibility, and it does not revive a dead branch.

A capability action is not admissible while an applicability, identifiability,
or operating-point dependency that blocks the same question is anything
other than resolved. Resolved here means the dependency record is closed.
It does not mean the model is applicable. A negative outcome has to already
be present as a hypothesis status.

Information gain is a category, not a number. Among admissible actions,
planning policy prefers a blocking dependency, then direct evidence, then a
downstream inspection. Optional evidence does not keep an investigation
going. Within one category, the dependency that is a prerequisite of more
other open dependencies is preferred. That count is planning structure, not
a scientific utility. When the category and that count are both equal, the
transition refuses instead of using action id.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


SOFTWARE_VERSION = "engcore.mind.transition/1.2.0"
POLICY_VERSION = "engcore.mind.planning/1.0.0"
NAFEMS_SUBJECT = "thermal.nafems_t3.benchmark_verification"
NAFEMS_MODULE = "engcore.product.nafems_t3"
NAFEMS_CAPABILITY = "run:thermal.nafems_t3"

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
    EVIDENCE_REQUEST = "evidence_request"


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


class DecisionValue(str, Enum):
    BLOCKING_DEPENDENCY = "blocking_dependency"
    DIRECT_EVIDENCE = "direct_evidence"
    DOWNSTREAM_ONLY = "downstream_only"
    REDUNDANT = "redundant"
    OPTIONAL = "optional"


class ResultKind(str, Enum):
    EVIDENCE_UNAVAILABLE = "evidence_unavailable"
    AUTHORITY_STATUS = "authority_status"


_ACTION_FOR_KIND = {
    DependencyKind.OPERATING_POINT_EVIDENCE: ActionType.REQUEST_EVIDENCE,
    DependencyKind.IDENTIFIABILITY: ActionType.CHECK_IDENTIFIABILITY,
    DependencyKind.APPLICABILITY: ActionType.CHECK_APPLICABILITY,
    DependencyKind.CAPABILITY_EXECUTION: ActionType.RUN_CAPABILITY,
    DependencyKind.EVIDENCE_REQUEST: ActionType.REQUEST_EVIDENCE,
}

_GATE_KINDS = frozenset({
    DependencyKind.APPLICABILITY,
    DependencyKind.IDENTIFIABILITY,
    DependencyKind.OPERATING_POINT_EVIDENCE,
})

_SUPPORT_TOKENS = frozenset({
    "benchmark_validated",
})
_ABSENCE_TOKENS = frozenset({
    "missing",
    "insufficient_evidence",
    "operating_point_not_established",
    "evidence_unavailable",
})
_NONTERMINAL_TOKENS = frozenset({
    "ledger_observed",
    "not_applicable",
    "not_supported",
})
_SELECTABLE = (
    DecisionValue.BLOCKING_DEPENDENCY,
    DecisionValue.DIRECT_EVIDENCE,
    DecisionValue.DOWNSTREAM_ONLY,
)


def _history(values: Any, field: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise MindRefusal(f"{field} must be a list of ids")
    cleaned = tuple(_text(item, field) for item in values)
    if len(set(cleaned)) != len(cleaned):
        raise MindRefusal(f"{field} contains a duplicate id")
    return cleaned


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
    authority_token: str | None = None
    prior_authority_result_ids: tuple[str, ...] = ()
    stale_result_id: str | None = None
    subject_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hypothesis_id", _text(self.hypothesis_id, "hypothesis_id"))
        object.__setattr__(self, "statement", _text(self.statement, "statement"))
        status = _enum(HypothesisStatus, self.status, "hypothesis status")
        object.__setattr__(self, "status", status)
        authority = _optional_text(self.authority_result_id, "authority_result_id")
        token = _optional_text(self.authority_token, "authority_token")
        stale = _optional_text(self.stale_result_id, "stale_result_id")
        subject = _optional_text(self.subject_id, "subject_id")
        object.__setattr__(self, "authority_result_id", authority)
        object.__setattr__(self, "authority_token", token)
        object.__setattr__(self, "stale_result_id", stale)
        object.__setattr__(self, "subject_id", subject)
        object.__setattr__(
            self,
            "prior_authority_result_ids",
            _history(self.prior_authority_result_ids, "prior_authority_result_ids"),
        )
        if status.value in _TERMINAL and authority is None:
            raise MindRefusal(
                f"hypothesis {self.hypothesis_id} carries {status.value} "
                "without an authority result id"
            )
        if status.value in _OPEN_QUESTION and (authority is not None or token is not None):
            raise MindRefusal(
                f"hypothesis {self.hypothesis_id} is {status.value} and cannot "
                "carry an authority result id"
            )
        if stale is not None and status is not HypothesisStatus.STALE:
            raise MindRefusal("only a stale hypothesis cites the result that made it stale")
        if status is HypothesisStatus.STALE and authority is None:
            raise MindRefusal("a stale hypothesis keeps the authority result it is no longer using")

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_result_id": self.authority_result_id,
            "authority_token": self.authority_token,
            "hypothesis_id": self.hypothesis_id,
            "prior_authority_result_ids": list(self.prior_authority_result_ids),
            "stale_result_id": self.stale_result_id,
            "statement": self.statement,
            "status": self.status.value,
            "subject_id": self.subject_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MindHypothesis":
        data = _mapping(payload, "hypothesis")
        _require_fields(
            data,
            {"hypothesis_id", "status", "statement", "authority_result_id",
             "authority_token", "prior_authority_result_ids", "stale_result_id",
             "subject_id"},
            "hypothesis",
        )
        return cls(
            hypothesis_id=data["hypothesis_id"],
            status=data["status"],
            statement=data["statement"],
            authority_result_id=data["authority_result_id"],
            authority_token=data["authority_token"],
            prior_authority_result_ids=tuple(data["prior_authority_result_ids"]),
            stale_result_id=data["stale_result_id"],
            subject_id=data["subject_id"],
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
    authority_token: str | None = None
    authority_result_id: str | None = None
    target_hypothesis_id: str | None = None
    producing_module: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_id", _text(self.result_id, "result_id"))
        object.__setattr__(self, "action_id", _text(self.action_id, "action_id"))
        kind = _enum(ResultKind, self.kind, "result kind")
        object.__setattr__(self, "kind", kind)
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
        token = _optional_text(self.authority_token, "authority_token")
        authority_id = _optional_text(self.authority_result_id, "authority_result_id")
        target = _optional_text(self.target_hypothesis_id, "target_hypothesis_id")
        module = _optional_text(self.producing_module, "producing_module")
        object.__setattr__(self, "authority_token", token)
        object.__setattr__(self, "authority_result_id", authority_id)
        object.__setattr__(self, "target_hypothesis_id", target)
        object.__setattr__(self, "producing_module", module)
        cited = (token, authority_id, target, module)
        if kind is ResultKind.EVIDENCE_UNAVAILABLE and any(item is not None for item in cited):
            raise MindRefusal("an availability result cannot carry an authority verdict")
        if kind is ResultKind.AUTHORITY_STATUS:
            if any(item is None for item in cited):
                raise MindRefusal("an authority result must cite its token, id, hypothesis, and module")
            allowed = _SUPPORT_TOKENS | _ABSENCE_TOKENS | _NONTERMINAL_TOKENS
            if token not in allowed:
                raise MindRefusal(f"unknown authority token {token!r}")
            if module.startswith("engcore.mind"):
                raise MindRefusal("the mind cannot be the producing module of an authority result")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "kind": self.kind.value,
            "observation_id": self.observation_id,
            "physical_infeasibility_claimed": False,
            "problem_id": self.problem_id,
            "producing_module": self.producing_module,
            "result_id": self.result_id,
            "run_id": self.run_id,
            "source_revision": self.source_revision,
            "state_digest": self.state_digest,
            "target_dependency_id": self.target_dependency_id,
            "target_hypothesis_id": self.target_hypothesis_id,
            "authority_result_id": self.authority_result_id,
            "authority_token": self.authority_token,
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
    decision_value: DecisionValue | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "admissible": self.admissible,
            "decision_value": None if self.decision_value is None else self.decision_value.value,
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
    decision_value: DecisionValue | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "decisions": [item.to_dict() for item in self.decisions],
            "decision_value": None if self.decision_value is None else self.decision_value.value,
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
    decision_value: DecisionValue | None = None,
) -> ActionDecision:
    return ActionDecision(action.action_id, admissible, gain, reason, decision_value)


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
        if prerequisite.status is DependencyStatus.RESOLVED:
            continue
        if (
            dependency.kind is DependencyKind.CAPABILITY_EXECUTION
            or prerequisite.status in {DependencyStatus.BLOCKED, DependencyStatus.DEAD}
        ):
            return _decision(
                action,
                InformationGain.PREREQUISITE_OPEN,
                f"prerequisite {prerequisite_id} is {prerequisite.status.value}",
                admissible=False,
                decision_value=DecisionValue.REDUNDANT,
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
    category = _planning_category(state, dependency)
    if category is DecisionValue.OPTIONAL:
        return _decision(
            action,
            InformationGain.NOT_ON_QUESTION,
            "dependency does not block the question and does not outrank a stop",
            admissible=True,
            decision_value=category,
        )
    return _decision(
        action,
        InformationGain.OPEN_DEPENDENCY,
        f"dependency {dependency.dependency_id} is {category.value} for {question.hypothesis_id}",
        admissible=True,
        decision_value=category,
    )


def _planning_category(state: MindState, dependency: Dependency) -> DecisionValue:
    """Planning rank for an otherwise open, type-matched action.

    This is not a scientific utility. It only says which admissible action
    addresses the question's blocking dependency most directly.
    """
    question_id = state.problem.question_hypothesis_id
    if question_id not in dependency.blocks:
        return DecisionValue.OPTIONAL
    unresolved_prerequisite = any(
        state.dependency(item).status is DependencyStatus.OPEN
        for item in dependency.prerequisite_ids
    )
    if unresolved_prerequisite:
        return DecisionValue.DOWNSTREAM_ONLY
    unblocks_other_work = any(
        dependency.dependency_id in other.prerequisite_ids and other.status is DependencyStatus.OPEN
        for other in state.dependencies
    )
    another_open_blocker = any(
        other.dependency_id != dependency.dependency_id
        and other.status is DependencyStatus.OPEN
        and question_id in other.blocks
        for other in state.dependencies
    )
    if unblocks_other_work or not another_open_blocker:
        return DecisionValue.BLOCKING_DEPENDENCY
    return DecisionValue.DIRECT_EVIDENCE


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
    by_id = {decision.action_id: decision for decision in decisions}
    by_action = {action.action_id: action for action in state.actions}
    workable = [
        by_action[decision.action_id]
        for decision in decisions
        if decision.admissible and decision.decision_value in _SELECTABLE
    ]
    if workable:
        best = min(_SELECTABLE.index(by_id[action.action_id].decision_value) for action in workable)
        shortlisted = [
            action
            for action in workable
            if _SELECTABLE.index(by_id[action.action_id].decision_value) == best
        ]

        def _unblocked(action: CandidateAction) -> int:
            dependency = state.dependency(action.dependency_id or "")
            return sum(
                1
                for other in state.dependencies
                if dependency.dependency_id in other.prerequisite_ids
                and other.status is DependencyStatus.OPEN
            )

        widest = max(_unblocked(action) for action in shortlisted)
        chosen_set = [action for action in shortlisted if _unblocked(action) == widest]
        if len(chosen_set) != 1:
            raise MindRefusal(
                "planning policy tie; refusing alphabetical or action-id selection"
            )
        chosen = chosen_set[0]
        gain = InformationGain.OPEN_DEPENDENCY
        value = by_id[chosen.action_id].decision_value
        reason = f"{value.value} dependency {chosen.dependency_id} is the next planning step"
    else:
        chosen = next(action for action in state.actions if action.action_type is ActionType.STOP)
        gain = InformationGain.STOP
        value = None
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
        decision_value=value,
    )


def apply_result(state: MindState, result: ActionResult) -> MindState:
    """Ingest one typed result bound to this problem, run, revision, and state.

    An availability result blocks one dependency and copies every hypothesis.
    An authority result copies the cited token onto the cited hypothesis.
    This function never chooses a scientific status that the result did not carry.
    """
    _bound_to_state(state, result)
    dependency = state.dependency(result.target_dependency_id)
    action = state.action(result.action_id)
    if action.dependency_id != dependency.dependency_id:
        raise MindRefusal("result action does not address the target dependency")
    decision = _classify(state, action)
    if not decision.admissible or decision.decision_value not in _SELECTABLE:
        raise MindRefusal(
            f"action {action.action_id} is not an admissible planning action"
        )
    if result.kind is ResultKind.EVIDENCE_UNAVAILABLE:
        hypotheses = state.hypotheses
        dependencies = _replace_dependency(
            state,
            _blocked_dependency(dependency, result),
        )
    elif result.kind is ResultKind.AUTHORITY_STATUS:
        hypotheses, dependencies = _consume_authority(state, dependency, action, result)
    else:
        raise MindRefusal(f"result kind {result.kind.value} is not ingested")
    attempted = tuple(sorted({*state.attempted_action_ids, result.action_id}))
    return MindState(
        problem=state.problem,
        hypotheses=hypotheses,
        dependencies=dependencies,
        actions=state.actions,
        attempted_action_ids=attempted,
    )


def _bound_to_state(state: MindState, result: ActionResult) -> None:
    if result.problem_id != state.problem.problem_id:
        raise MindRefusal("result is for a different problem")
    if result.run_id != state.problem.run_id:
        raise MindRefusal("result is for a different run")
    if result.source_revision != state.problem.source_revision:
        raise MindRefusal("result is for a different source revision")
    if result.state_digest != canonical_digest(state.to_dict()):
        raise MindRefusal("result does not match this state")
    if result.action_id not in {item.action_id for item in state.actions}:
        raise MindRefusal(f"result names unknown action {result.action_id}")


def _replace_dependency(state: MindState, updated: Dependency) -> tuple[Dependency, ...]:
    return tuple(
        updated if item.dependency_id == updated.dependency_id else item
        for item in state.dependencies
    )


def _blocked_dependency(dependency: Dependency, result: ActionResult) -> Dependency:
    return Dependency(
        dependency_id=dependency.dependency_id,
        kind=dependency.kind,
        status=DependencyStatus.BLOCKED,
        blocks=dependency.blocks,
        upstream_result_ids=dependency.upstream_result_ids,
        prerequisite_ids=dependency.prerequisite_ids,
        availability_observation_id=result.observation_id,
        availability_result_id=result.result_id,
    )


def _closed_dependency(
    dependency: Dependency,
    status: DependencyStatus,
    result: ActionResult,
) -> Dependency:
    authority_id = result.authority_result_id or ""
    upstream = dependency.upstream_result_ids
    if authority_id and authority_id not in upstream:
        upstream = tuple(sorted((*upstream, authority_id)))
    return Dependency(
        dependency_id=dependency.dependency_id,
        kind=dependency.kind,
        status=status,
        blocks=dependency.blocks,
        upstream_result_ids=upstream,
        prerequisite_ids=dependency.prerequisite_ids,
    )


def _consume_authority(
    state: MindState,
    dependency: Dependency,
    action: CandidateAction,
    result: ActionResult,
) -> tuple[tuple[MindHypothesis, ...], tuple[Dependency, ...]]:
    token = result.authority_token or ""
    if result.target_hypothesis_id not in dependency.blocks:
        raise MindRefusal("authority result targets a hypothesis this dependency does not block")
    target = state.hypothesis(result.target_hypothesis_id or "")
    if token in _NONTERMINAL_TOKENS:
        if token == "not_supported" and target.status is HypothesisStatus.SUPPORTED_BY_AUTHORITY:
            raise MindRefusal(
                "a supported authority result cannot become unsupported through planner mutation"
            )
        revised = target
        updated = _closed_dependency(dependency, dependency.status, result)
    else:
        revised = _copy_authority(target, action, result)
        updated = _dependency_after_authority(dependency, result, revised)
    hypotheses = tuple(
        revised if item.hypothesis_id == target.hypothesis_id else item
        for item in state.hypotheses
    )
    return hypotheses, _replace_dependency(state, updated)


def _dependency_after_authority(
    dependency: Dependency,
    result: ActionResult,
    revised: MindHypothesis,
) -> Dependency:
    token = result.authority_token or ""
    if token in _ABSENCE_TOKENS:
        return _blocked_dependency(dependency, result)
    if revised.status is HypothesisStatus.STALE or token in _SUPPORT_TOKENS:
        return _closed_dependency(dependency, DependencyStatus.RESOLVED, result)
    raise MindRefusal(f"authority token {token!r} was not consumed")


def _copy_authority(
    item: MindHypothesis,
    action: CandidateAction,
    result: ActionResult,
) -> MindHypothesis:
    token = result.authority_token or ""
    authority_id = result.authority_result_id or ""
    if token in _ABSENCE_TOKENS:
        if item.status in {HypothesisStatus.SUPPORTED_BY_AUTHORITY, HypothesisStatus.REFUTED_BY_AUTHORITY}:
            return item
        if item.status is HypothesisStatus.STALE:
            raise MindRefusal("a stale hypothesis is not rewritten by a missing-evidence token")
        if item.status is HypothesisStatus.ACTIVE:
            return MindHypothesis(
                hypothesis_id=item.hypothesis_id,
                status=HypothesisStatus.UNRESOLVED,
                statement=item.statement,
                subject_id=item.subject_id,
            )
        return item
    if token in _SUPPORT_TOKENS:
        _require_benchmark_binding(item, action, result)
        if item.status is HypothesisStatus.REFUTED_BY_AUTHORITY:
            raise MindRefusal("a refuted hypothesis cannot be resurrected")
        if item.status is HypothesisStatus.SUPPORTED_BY_AUTHORITY:
            return _mark_stale(item, authority_id)
        if item.status is HypothesisStatus.STALE:
            raise MindRefusal("a stale hypothesis is not revived by another support token")
        return MindHypothesis(
            hypothesis_id=item.hypothesis_id,
            status=HypothesisStatus.SUPPORTED_BY_AUTHORITY,
            statement=item.statement,
            authority_result_id=authority_id,
            authority_token=token,
            prior_authority_result_ids=item.prior_authority_result_ids,
            subject_id=item.subject_id,
        )
    raise MindRefusal(f"authority token {token!r} is not copied")


def _require_benchmark_binding(
    item: MindHypothesis,
    action: CandidateAction,
    result: ActionResult,
) -> None:
    if action.capability_id != NAFEMS_CAPABILITY:
        raise MindRefusal("benchmark result is not bound to the NAFEMS capability")
    if result.producing_module != NAFEMS_MODULE:
        raise MindRefusal("benchmark result is not bound to the NAFEMS authority")
    if item.subject_id != NAFEMS_SUBJECT:
        raise MindRefusal("benchmark result is not this hypothesis subject")


def _mark_stale(item: MindHypothesis, new_result_id: str) -> MindHypothesis:
    if item.authority_result_id == new_result_id:
        return item
    prior = item.prior_authority_result_ids
    if item.authority_result_id and item.authority_result_id not in prior:
        prior = prior + (item.authority_result_id,)
    return MindHypothesis(
        hypothesis_id=item.hypothesis_id,
        status=HypothesisStatus.STALE,
        statement=item.statement,
        authority_result_id=item.authority_result_id,
        authority_token=item.authority_token,
        prior_authority_result_ids=prior,
        stale_result_id=new_result_id,
        subject_id=item.subject_id,
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
