"""D3 - domain-neutral design memory for attributable retention.

This module records evaluated design observations beside frozen D1 archives.
It classifies entries with caller-declared policy, keeps classification
separate from Layer A observations, and applies capacity after classification.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.objectives import ObjectiveDefinition, ObjectiveDirection
from ..scientific.ir.values import ScientificValue, decode_value, encode_value
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity
from .candidate import DesignCandidate, DesignCandidateReference
from .evaluation import (
    DesignEvaluation,
    DesignEvaluationReference,
    ProjectedObjective,
    ResultBinding,
    SelectionEligibility,
    project_objectives,
    require_objectives,
)
from .space import DesignSpaceReference

DESIGN_MEMORY_SCOPE_SCHEMA = schema_string("design_memory_scope")
DESIGN_MEMORY_ENTRY_SCHEMA = schema_string("design_memory_entry")
DESIGN_MEMORY_LAYER_A_SCHEMA = schema_string("design_memory_layer_a")
DESIGN_MEMORY_ASSESSMENT_SCHEMA = schema_string("design_memory_assessment_context")
DESIGN_MEMORY_EXPLICIT_SCHEMA = schema_string("design_memory_explicit_retention")
DESIGN_MEMORY_POLICY_SCHEMA = schema_string("design_memory_policy")
DESIGN_MEMORY_CLASSIFICATION_SCHEMA = schema_string("design_memory_classification")
DESIGN_MEMORY_RECORD_SCHEMA = schema_string("design_memory_record")


Partitioner = Callable[[Mapping[str, ScientificValue]], bytes]


class RetentionReason(str, Enum):
    PARETO_MEMBER = "PARETO_MEMBER"
    SCOPED_ELITE = "SCOPED_ELITE"
    NEAR_EXTREME = "NEAR_EXTREME"
    NEAR_THRESHOLD = "NEAR_THRESHOLD"
    DIVERSITY_REPRESENTATIVE = "DIVERSITY_REPRESENTATIVE"
    EXPLICIT = "EXPLICIT"


REASON_ORDER = (
    RetentionReason.PARETO_MEMBER,
    RetentionReason.SCOPED_ELITE,
    RetentionReason.NEAR_EXTREME,
    RetentionReason.NEAR_THRESHOLD,
    RetentionReason.DIVERSITY_REPRESENTATIVE,
    RetentionReason.EXPLICIT,
)


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _require_canonical_text(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidScientificProblem(f"{context} must be a non-empty canonical string")
    return value


def _require_digest(value: Any, *, context: str) -> str:
    text = _require_canonical_text(value, context=context)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise InvalidScientificProblem(f"{context} must be a 64-character hex digest")
    return text


def _quantity_map_to_dict(values: Mapping[str, Quantity]) -> dict[str, Any]:
    return {name: values[name].to_dict() for name in sorted(values)}


def _quantity_map_from_dict(payload: Mapping[str, Any]) -> dict[str, Quantity]:
    return {str(name): Quantity.from_dict(value) for name, value in payload.items()}


def _canonical_identity_payload(
    candidate: DesignCandidateReference,
    evaluation: DesignEvaluationReference,
) -> list[dict[str, Any]]:
    return [candidate.to_dict(), evaluation.to_dict()]


def _identity_key(
    candidate: DesignCandidateReference,
    evaluation: DesignEvaluationReference,
) -> bytes:
    return _canonical_bytes(_canonical_identity_payload(candidate, evaluation))


@dataclass(frozen=True)
class DesignMemoryScope:
    design_space: DesignSpaceReference
    objectives: tuple[ObjectiveDefinition, ...]
    context_reference: str
    scope_identity: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.design_space, DesignSpaceReference):
            raise InvalidScientificProblem("D3 scope requires DesignSpaceReference")
        objectives = require_objectives(self.objectives)
        context = _require_canonical_text(
            self.context_reference, context="D3 scope context_reference"
        )
        object.__setattr__(self, "objectives", objectives)
        object.__setattr__(self, "context_reference", context)
        object.__setattr__(self, "scope_identity", _digest(self._identity_payload()))

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "design_space": self.design_space.to_dict(),
            "objective_projection": [
                {
                    "name": item.name,
                    "metric": item.metric,
                    "unit": item.unit,
                    "direction": item.direction.value,
                }
                for item in self.objectives
            ],
            "context_reference": self.context_reference,
        }

    @property
    def objective_map(self) -> dict[str, ObjectiveDefinition]:
        return {objective.name: objective for objective in self.objectives}

    def require_same_scope(self, other: "DesignMemoryScope") -> None:
        if not isinstance(other, DesignMemoryScope):
            raise InvalidScientificProblem("D3 scope comparison requires a D3 scope")
        if self.scope_identity != other.scope_identity:
            raise InvalidScientificProblem("D3 refuses cross-scope comparison")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_MEMORY_SCOPE_SCHEMA,
            "design_space": self.design_space.to_dict(),
            "objectives": [item.to_dict() for item in self.objectives],
            "context_reference": self.context_reference,
            "scope_identity": self.scope_identity,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DesignMemoryScope":
        require_schema(payload, DESIGN_MEMORY_SCOPE_SCHEMA)
        scope = cls(
            design_space=DesignSpaceReference.from_dict(payload["design_space"]),
            objectives=tuple(
                ObjectiveDefinition.from_dict(item)
                for item in payload.get("objectives", ())
            ),
            context_reference=payload["context_reference"],
        )
        recorded = _require_digest(
            payload.get("scope_identity"), context="D3 scope_identity"
        )
        if recorded != scope.scope_identity:
            raise InvalidScientificProblem("D3 scope identity does not match payload")
        return scope


@dataclass(frozen=True)
class DesignMemoryEntry:
    candidate: DesignCandidateReference
    design_space: DesignSpaceReference
    evaluation: DesignEvaluationReference
    result_binding: ResultBinding
    scope_identity: str
    assignments: Mapping[str, ScientificValue]
    objective_values: Mapping[str, Quantity]
    entry_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, DesignCandidateReference):
            raise InvalidScientificProblem("D3 entry requires candidate reference")
        if not isinstance(self.design_space, DesignSpaceReference):
            raise InvalidScientificProblem("D3 entry requires design-space reference")
        if not isinstance(self.evaluation, DesignEvaluationReference):
            raise InvalidScientificProblem("D3 entry requires evaluation reference")
        if not isinstance(self.result_binding, ResultBinding):
            raise InvalidScientificProblem("D3 entry requires exact result binding")
        scope_identity = _require_digest(
            self.scope_identity, context="D3 entry scope_identity"
        )
        if self.result_binding.candidate.candidate_id != self.candidate.candidate_id:
            raise InvalidScientificProblem("D3 entry result-binding candidate mismatch")
        if self.result_binding.design_space.key != self.design_space.key:
            raise InvalidScientificProblem("D3 entry result-binding design-space mismatch")
        assignments = dict(self.assignments)
        if not assignments:
            raise InvalidScientificProblem("D3 entry requires candidate assignments")
        objectives = dict(self.objective_values)
        if not objectives:
            raise InvalidScientificProblem("D3 entry requires objective values")
        for name, value in objectives.items():
            if not isinstance(name, str) or not name.strip():
                raise InvalidScientificProblem("D3 objective names must be non-empty")
            if not isinstance(value, Quantity):
                raise InvalidScientificProblem("D3 objective values must be Quantities")
        object.__setattr__(self, "scope_identity", scope_identity)
        object.__setattr__(self, "assignments", assignments)
        object.__setattr__(self, "objective_values", objectives)
        object.__setattr__(self, "entry_digest", _digest(self._digest_payload()))

    @classmethod
    def from_evaluation(
        cls,
        *,
        scope: DesignMemoryScope,
        candidate: DesignCandidate,
        evaluation: DesignEvaluation,
    ) -> "DesignMemoryEntry":
        if evaluation.eligibility is not SelectionEligibility.ELIGIBLE:
            raise InvalidScientificProblem("D3 entry requires eligible D1 evaluation")
        if evaluation.design_space.key != scope.design_space.key:
            raise InvalidScientificProblem("D3 entry evaluation scope mismatch")
        evaluation.validate_candidate(candidate)
        projected = project_objectives(evaluation, scope.objectives)
        return cls(
            candidate=candidate.reference,
            design_space=candidate.design_space,
            evaluation=evaluation.reference,
            result_binding=evaluation.result_binding,
            scope_identity=scope.scope_identity,
            assignments=dict(candidate.assignments),
            objective_values={item.objective.name: item.value for item in projected},
        )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "design_space": self.design_space.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "result_binding": self.result_binding.to_dict(),
            "scope_identity": self.scope_identity,
            "assignments": {
                name: encode_value(value)
                for name, value in sorted(self.assignments.items())
            },
            "objective_values": _quantity_map_to_dict(self.objective_values),
        }

    @property
    def identity(self) -> str:
        return _digest(_canonical_identity_payload(self.candidate, self.evaluation))

    @property
    def identity_sort_key(self) -> bytes:
        return _identity_key(self.candidate, self.evaluation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_MEMORY_ENTRY_SCHEMA,
            **self._digest_payload(),
            "entry_digest": self.entry_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DesignMemoryEntry":
        require_schema(payload, DESIGN_MEMORY_ENTRY_SCHEMA)
        entry = cls(
            candidate=DesignCandidateReference.from_dict(payload["candidate"]),
            design_space=DesignSpaceReference.from_dict(payload["design_space"]),
            evaluation=DesignEvaluationReference.from_dict(payload["evaluation"]),
            result_binding=ResultBinding.from_dict(payload["result_binding"]),
            scope_identity=payload["scope_identity"],
            assignments={
                name: decode_value(value)
                for name, value in payload.get("assignments", {}).items()
            },
            objective_values=_quantity_map_from_dict(payload.get("objective_values", {})),
        )
        recorded = _require_digest(
            payload.get("entry_digest"), context="D3 entry_digest"
        )
        if recorded != entry.entry_digest:
            raise InvalidScientificProblem("D3 entry digest does not match payload")
        return entry


@dataclass(frozen=True)
class DesignMemoryLayerA:
    scope: DesignMemoryScope
    entries: tuple[DesignMemoryEntry, ...]
    partition_keys: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.scope, DesignMemoryScope):
            raise InvalidScientificProblem("D3 Layer A requires a scope")
        entries = tuple(sorted(self.entries, key=lambda item: item.identity_sort_key))
        if not entries:
            raise InvalidScientificProblem("D3 Layer A requires entries")
        identities = [entry.identity for entry in entries]
        if len(identities) != len(set(identities)):
            raise InvalidScientificProblem("D3 Layer A identities must be unique")
        for entry in entries:
            if entry.scope_identity != self.scope.scope_identity:
                raise InvalidScientificProblem("D3 Layer A entry scope mismatch")
            if entry.design_space.key != self.scope.design_space.key:
                raise InvalidScientificProblem("D3 Layer A entry design-space mismatch")
            if set(entry.objective_values) != set(self.scope.objective_map):
                raise InvalidScientificProblem("D3 Layer A objective projection mismatch")
            for objective in self.scope.objectives:
                entry.objective_values[objective.name].to(objective.unit)
        keys = dict(self.partition_keys)
        if set(keys) != set(identities):
            raise InvalidScientificProblem("D3 Layer A partition keys must cover entries")
        for identity, key in keys.items():
            if not isinstance(key, str) or any(ch not in "0123456789abcdef" for ch in key):
                raise InvalidScientificProblem("D3 partition keys must be hex strings")
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "partition_keys", dict(sorted(keys.items())))

    @classmethod
    def build(
        cls,
        *,
        scope: DesignMemoryScope,
        candidates: Sequence[DesignCandidate],
        evaluations: Sequence[DesignEvaluation],
        partitioner: Partitioner,
    ) -> "DesignMemoryLayerA":
        if not callable(partitioner):
            raise InvalidScientificProblem("D3 requires a deterministic partitioner")
        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        if len(candidate_by_id) != len(tuple(candidates)):
            raise InvalidScientificProblem("D3 candidates must have unique identities")
        evaluation_ids = [evaluation.evaluation_id for evaluation in evaluations]
        if len(evaluation_ids) != len(set(evaluation_ids)):
            raise InvalidScientificProblem("D3 evaluations must have unique identities")
        entries: list[DesignMemoryEntry] = []
        partition_keys: dict[str, str] = {}
        for evaluation in evaluations:
            if evaluation.eligibility is not SelectionEligibility.ELIGIBLE:
                continue
            candidate = candidate_by_id.get(evaluation.candidate.candidate_id)
            if candidate is None:
                raise InvalidScientificProblem("D3 evaluation candidate absent")
            entry = DesignMemoryEntry.from_evaluation(
                scope=scope, candidate=candidate, evaluation=evaluation
            )
            key = partitioner(entry.assignments)
            if not isinstance(key, bytes):
                raise InvalidScientificProblem("D3 partitioner must return bytes")
            entries.append(entry)
            partition_keys[entry.identity] = key.hex()
        return cls(scope=scope, entries=tuple(entries), partition_keys=partition_keys)

    def entry_by_identity(self) -> dict[str, DesignMemoryEntry]:
        return {entry.identity: entry for entry in self.entries}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_MEMORY_LAYER_A_SCHEMA,
            "scope": self.scope.to_dict(),
            "entries": [entry.to_dict() for entry in self.entries],
            "partition_keys": dict(sorted(self.partition_keys.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DesignMemoryLayerA":
        require_schema(payload, DESIGN_MEMORY_LAYER_A_SCHEMA)
        return cls(
            scope=DesignMemoryScope.from_dict(payload["scope"]),
            entries=tuple(
                DesignMemoryEntry.from_dict(item) for item in payload.get("entries", ())
            ),
            partition_keys=dict(payload.get("partition_keys", {})),
        )


@dataclass(frozen=True)
class AssessmentContext:
    assessment_id: str
    thresholds: Mapping[str, Quantity]
    threshold_tolerances: Mapping[str, Quantity]
    assessment_identity: str = field(init=False)

    def __post_init__(self) -> None:
        assessment_id = _require_canonical_text(
            self.assessment_id, context="D3 assessment_id"
        )
        thresholds = _quantity_map_from_dict(
            _quantity_map_to_dict(dict(self.thresholds))
        )
        tolerances = _quantity_map_from_dict(
            _quantity_map_to_dict(dict(self.threshold_tolerances))
        )
        if set(thresholds) != set(tolerances):
            raise InvalidScientificProblem("D3 threshold maps must have identical keys")
        for name, tolerance in tolerances.items():
            if tolerance.magnitude < 0:
                raise InvalidScientificProblem("D3 tolerance must be >= 0")
        object.__setattr__(self, "assessment_id", assessment_id)
        object.__setattr__(self, "thresholds", thresholds)
        object.__setattr__(self, "threshold_tolerances", tolerances)
        object.__setattr__(self, "assessment_identity", _digest(self._identity_payload()))

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "thresholds": _quantity_map_to_dict(self.thresholds),
            "threshold_tolerances": _quantity_map_to_dict(self.threshold_tolerances),
        }

    def validate_against(self, scope: DesignMemoryScope) -> None:
        objective_map = scope.objective_map
        for name in self.thresholds:
            objective = objective_map.get(name)
            if objective is None:
                raise InvalidScientificProblem("D3 assessment objective absent from scope")
            self.thresholds[name].to(objective.unit)
            self.threshold_tolerances[name].to(objective.unit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_MEMORY_ASSESSMENT_SCHEMA,
            **self._identity_payload(),
            "assessment_identity": self.assessment_identity,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AssessmentContext":
        require_schema(payload, DESIGN_MEMORY_ASSESSMENT_SCHEMA)
        context = cls(
            assessment_id=payload["assessment_id"],
            thresholds=_quantity_map_from_dict(payload.get("thresholds", {})),
            threshold_tolerances=_quantity_map_from_dict(
                payload.get("threshold_tolerances", {})
            ),
        )
        recorded = _require_digest(
            payload.get("assessment_identity"), context="D3 assessment_identity"
        )
        if recorded != context.assessment_identity:
            raise InvalidScientificProblem("D3 assessment identity does not match payload")
        return context


@dataclass(frozen=True)
class ExplicitRetention:
    candidate: DesignCandidateReference
    evaluation: DesignEvaluationReference
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, DesignCandidateReference):
            raise InvalidScientificProblem("D3 explicit retention requires candidate")
        if not isinstance(self.evaluation, DesignEvaluationReference):
            raise InvalidScientificProblem("D3 explicit retention requires evaluation")
        reason = _require_canonical_text(self.reason, context="D3 explicit reason")
        object.__setattr__(self, "reason", reason)

    @property
    def identity(self) -> str:
        return _digest(_canonical_identity_payload(self.candidate, self.evaluation))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_MEMORY_EXPLICIT_SCHEMA,
            "candidate": self.candidate.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExplicitRetention":
        require_schema(payload, DESIGN_MEMORY_EXPLICIT_SCHEMA)
        return cls(
            candidate=DesignCandidateReference.from_dict(payload["candidate"]),
            evaluation=DesignEvaluationReference.from_dict(payload["evaluation"]),
            reason=payload["reason"],
        )


@dataclass(frozen=True)
class DesignMemoryPolicy:
    policy_id: str
    elite_scopes: tuple[tuple[str, ...], ...] = ()
    extreme_tolerances: Mapping[str, Quantity] = field(default_factory=dict)
    assessment_contexts: tuple[AssessmentContext, ...] = ()
    explicit_retention: tuple[ExplicitRetention, ...] = ()
    cap: int = 250

    def __post_init__(self) -> None:
        policy_id = _require_canonical_text(self.policy_id, context="D3 policy_id")
        elite_scopes = []
        for scope in self.elite_scopes:
            names = tuple(str(name).strip() for name in scope)
            if not names or any(not name for name in names):
                raise InvalidScientificProblem("D3 elite scopes must be non-empty")
            if len(names) != len(set(names)):
                raise InvalidScientificProblem("D3 elite scope objectives must be unique")
            elite_scopes.append(tuple(sorted(names)))
        if len(elite_scopes) != len(set(elite_scopes)):
            raise InvalidScientificProblem("D3 elite scopes must be unique")
        tolerances = _quantity_map_from_dict(
            _quantity_map_to_dict(dict(self.extreme_tolerances))
        )
        for tolerance in tolerances.values():
            if tolerance.magnitude < 0:
                raise InvalidScientificProblem("D3 tolerance must be >= 0")
        assessments = tuple(self.assessment_contexts)
        if any(not isinstance(item, AssessmentContext) for item in assessments):
            raise InvalidScientificProblem("D3 policy assessments are malformed")
        assessment_ids = [item.assessment_id for item in assessments]
        if len(assessment_ids) != len(set(assessment_ids)):
            raise InvalidScientificProblem("D3 assessment ids must be unique")
        explicit = tuple(self.explicit_retention)
        if any(not isinstance(item, ExplicitRetention) for item in explicit):
            raise InvalidScientificProblem("D3 explicit retention entries are malformed")
        if isinstance(self.cap, bool) or not isinstance(self.cap, int) or self.cap < 1:
            raise InvalidScientificProblem("D3 cap must be a positive integer")
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "elite_scopes", tuple(sorted(elite_scopes)))
        object.__setattr__(self, "extreme_tolerances", tolerances)
        object.__setattr__(self, "assessment_contexts", assessments)
        object.__setattr__(self, "explicit_retention", tuple(sorted(explicit, key=lambda x: (x.identity, x.reason))))

    def validate_against(self, layer_a: DesignMemoryLayerA) -> None:
        objective_map = layer_a.scope.objective_map
        for elite_scope in self.elite_scopes:
            for name in elite_scope:
                if name not in objective_map:
                    raise InvalidScientificProblem("D3 elite objective absent from scope")
        for name, tolerance in self.extreme_tolerances.items():
            objective = objective_map.get(name)
            if objective is None:
                raise InvalidScientificProblem("D3 extreme tolerance objective absent")
            tolerance.to(objective.unit)
        for assessment in self.assessment_contexts:
            assessment.validate_against(layer_a.scope)
        present = set(layer_a.entry_by_identity())
        for item in self.explicit_retention:
            if item.identity not in present:
                raise InvalidScientificProblem("D3 explicit retention reference absent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_MEMORY_POLICY_SCHEMA,
            "policy_id": self.policy_id,
            "elite_scopes": [list(item) for item in self.elite_scopes],
            "extreme_tolerances": _quantity_map_to_dict(self.extreme_tolerances),
            "assessment_contexts": [item.to_dict() for item in self.assessment_contexts],
            "explicit_retention": [item.to_dict() for item in self.explicit_retention],
            "cap": self.cap,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DesignMemoryPolicy":
        require_schema(payload, DESIGN_MEMORY_POLICY_SCHEMA)
        return cls(
            policy_id=payload["policy_id"],
            elite_scopes=tuple(tuple(item) for item in payload.get("elite_scopes", ())),
            extreme_tolerances=_quantity_map_from_dict(
                payload.get("extreme_tolerances", {})
            ),
            assessment_contexts=tuple(
                AssessmentContext.from_dict(item)
                for item in payload.get("assessment_contexts", ())
            ),
            explicit_retention=tuple(
                ExplicitRetention.from_dict(item)
                for item in payload.get("explicit_retention", ())
            ),
            cap=payload.get("cap", 250),
        )


@dataclass(frozen=True)
class EntryClassification:
    identity: str
    candidate_id: str
    evaluation_id: str
    entry_digest: str
    reasons: tuple[RetentionReason, ...] = ()
    scoped_elite_scopes: tuple[tuple[str, ...], ...] = ()
    near_extreme_distances: Mapping[str, float] = field(default_factory=dict)
    near_threshold_margins: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    diversity_partition_key: str | None = None
    explicit_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        identity = _require_digest(self.identity, context="D3 classification identity")
        entry_digest = _require_digest(
            self.entry_digest, context="D3 classification entry_digest"
        )
        reasons = tuple(RetentionReason(reason) for reason in self.reasons)
        reason_set = set(reasons)
        ordered = tuple(reason for reason in REASON_ORDER if reason in reason_set)
        object.__setattr__(self, "identity", identity)
        object.__setattr__(
            self, "candidate_id", _require_canonical_text(self.candidate_id, context="D3 candidate_id")
        )
        object.__setattr__(
            self, "evaluation_id", _require_canonical_text(self.evaluation_id, context="D3 evaluation_id")
        )
        object.__setattr__(self, "entry_digest", entry_digest)
        object.__setattr__(self, "reasons", ordered)
        object.__setattr__(
            self,
            "scoped_elite_scopes",
            tuple(sorted(tuple(scope) for scope in self.scoped_elite_scopes)),
        )
        object.__setattr__(
            self,
            "near_extreme_distances",
            dict(sorted((str(k), float(v)) for k, v in self.near_extreme_distances.items())),
        )
        object.__setattr__(
            self,
            "near_threshold_margins",
            {
                str(assessment): dict(sorted((str(k), float(v)) for k, v in margins.items()))
                for assessment, margins in sorted(self.near_threshold_margins.items())
            },
        )
        object.__setattr__(self, "explicit_reasons", tuple(sorted(self.explicit_reasons)))

    def carries_reason(self) -> bool:
        return bool(self.reasons)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "identity": self.identity,
            "candidate_id": self.candidate_id,
            "evaluation_id": self.evaluation_id,
            "entry_digest": self.entry_digest,
            "reasons": [reason.value for reason in self.reasons],
            "scoped_elite_scopes": [list(item) for item in self.scoped_elite_scopes],
            "near_extreme_distances": dict(self.near_extreme_distances),
            "near_threshold_margins": dict(self.near_threshold_margins),
            "explicit_reasons": list(self.explicit_reasons),
        }
        if self.diversity_partition_key is not None:
            payload["diversity_partition_key"] = self.diversity_partition_key
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EntryClassification":
        return cls(
            identity=payload["identity"],
            candidate_id=payload["candidate_id"],
            evaluation_id=payload["evaluation_id"],
            entry_digest=payload["entry_digest"],
            reasons=tuple(RetentionReason(item) for item in payload.get("reasons", ())),
            scoped_elite_scopes=tuple(
                tuple(item) for item in payload.get("scoped_elite_scopes", ())
            ),
            near_extreme_distances=dict(payload.get("near_extreme_distances", {})),
            near_threshold_margins=dict(payload.get("near_threshold_margins", {})),
            diversity_partition_key=payload.get("diversity_partition_key"),
            explicit_reasons=tuple(payload.get("explicit_reasons", ())),
        )


@dataclass(frozen=True)
class DesignMemoryClassification:
    classifications: tuple[EntryClassification, ...]
    retained_identities: tuple[str, ...]
    discarded_classified_identities: tuple[str, ...]
    summary: Mapping[str, Any]

    def __post_init__(self) -> None:
        classifications = tuple(sorted(self.classifications, key=lambda item: item.identity))
        identities = [item.identity for item in classifications]
        if len(identities) != len(set(identities)):
            raise InvalidScientificProblem("D3 classifications must be unique")
        present = set(identities)
        retained = tuple(self.retained_identities)
        discarded = tuple(self.discarded_classified_identities)
        for identity in retained + discarded:
            _require_digest(identity, context="D3 retained/discarded identity")
            if identity not in present:
                raise InvalidScientificProblem("D3 retention identity absent")
        if set(retained) & set(discarded):
            raise InvalidScientificProblem("D3 retained/discarded sets overlap")
        object.__setattr__(self, "classifications", classifications)
        object.__setattr__(self, "retained_identities", retained)
        object.__setattr__(self, "discarded_classified_identities", discarded)
        object.__setattr__(self, "summary", dict(sorted(self.summary.items())))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_MEMORY_CLASSIFICATION_SCHEMA,
            "classifications": [item.to_dict() for item in self.classifications],
            "retained_identities": list(self.retained_identities),
            "discarded_classified_identities": list(
                self.discarded_classified_identities
            ),
            "summary": dict(self.summary),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DesignMemoryClassification":
        require_schema(payload, DESIGN_MEMORY_CLASSIFICATION_SCHEMA)
        return cls(
            classifications=tuple(
                EntryClassification.from_dict(item)
                for item in payload.get("classifications", ())
            ),
            retained_identities=tuple(payload.get("retained_identities", ())),
            discarded_classified_identities=tuple(
                payload.get("discarded_classified_identities", ())
            ),
            summary=dict(payload.get("summary", {})),
        )


@dataclass(frozen=True)
class DesignMemoryRecord:
    layer_a: DesignMemoryLayerA
    policy: DesignMemoryPolicy
    classification: DesignMemoryClassification

    @classmethod
    def build(
        cls, *, layer_a: DesignMemoryLayerA, policy: DesignMemoryPolicy
    ) -> "DesignMemoryRecord":
        return cls(
            layer_a=layer_a,
            policy=policy,
            classification=classify_memory(layer_a=layer_a, policy=policy),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_MEMORY_RECORD_SCHEMA,
            "layer_a": self.layer_a.to_dict(),
            "policy": self.policy.to_dict(),
            "classification": self.classification.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DesignMemoryRecord":
        require_schema(payload, DESIGN_MEMORY_RECORD_SCHEMA)
        layer_a = DesignMemoryLayerA.from_dict(payload["layer_a"])
        policy = DesignMemoryPolicy.from_dict(payload["policy"])
        classification = DesignMemoryClassification.from_dict(payload["classification"])
        record = cls(layer_a=layer_a, policy=policy, classification=classification)
        if record.reconstruct().to_json() != record.to_json():
            raise InvalidScientificProblem("D3 memory record is not reconstructible")
        return record

    def reconstruct(self) -> "DesignMemoryRecord":
        return DesignMemoryRecord.build(layer_a=self.layer_a, policy=self.policy)

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), indent=indent)


def _entry_dominates(
    left: DesignMemoryEntry,
    right: DesignMemoryEntry,
    objectives: Sequence[ObjectiveDefinition],
) -> bool:
    if left.scope_identity != right.scope_identity:
        raise InvalidScientificProblem("D3 refuses cross-scope dominance comparison")
    no_worse_all = True
    strictly_better_any = False
    for objective in objectives:
        lv = left.objective_values[objective.name].to(objective.unit).magnitude
        rv = right.objective_values[objective.name].to(objective.unit).magnitude
        if objective.direction is ObjectiveDirection.MAXIMIZE:
            no_worse = lv >= rv
            strictly_better = lv > rv
        else:
            no_worse = lv <= rv
            strictly_better = lv < rv
        no_worse_all = no_worse_all and no_worse
        strictly_better_any = strictly_better_any or strictly_better
    return no_worse_all and strictly_better_any


def pareto_member_identities(
    entries: Sequence[DesignMemoryEntry],
    objectives: Sequence[ObjectiveDefinition],
) -> frozenset[str]:
    items = tuple(entries)
    declared = tuple(objectives)
    values = {
        entry.identity: tuple(
            entry.objective_values[objective.name].to(objective.unit).magnitude
            for objective in declared
        )
        for entry in items
    }

    def dominates_cached(left: DesignMemoryEntry, right: DesignMemoryEntry) -> bool:
        left_values = values[left.identity]
        right_values = values[right.identity]
        no_worse_all = True
        strictly_better_any = False
        for index, objective in enumerate(declared):
            lv = left_values[index]
            rv = right_values[index]
            if objective.direction is ObjectiveDirection.MAXIMIZE:
                no_worse = lv >= rv
                strictly_better = lv > rv
            else:
                no_worse = lv <= rv
                strictly_better = lv < rv
            no_worse_all = no_worse_all and no_worse
            strictly_better_any = strictly_better_any or strictly_better
        return no_worse_all and strictly_better_any

    members = []
    for candidate in items:
        if any(
            other.identity != candidate.identity
            and dominates_cached(other, candidate)
            for other in items
        ):
            continue
        members.append(candidate.identity)
    return frozenset(members)


def compare_entries(
    left: DesignMemoryEntry,
    right: DesignMemoryEntry,
    objectives: Sequence[ObjectiveDefinition],
) -> bool:
    return _entry_dominates(left, right, tuple(objectives))


def merge_layer_a_records(
    left: DesignMemoryLayerA, right: DesignMemoryLayerA
) -> DesignMemoryLayerA:
    left.scope.require_same_scope(right.scope)
    return DesignMemoryLayerA(
        scope=left.scope,
        entries=left.entries + right.entries,
        partition_keys={**left.partition_keys, **right.partition_keys},
    )


def verify_layer_a_attribution(
    *,
    layer_a: DesignMemoryLayerA,
    candidates: Sequence[DesignCandidate],
    evaluations: Sequence[DesignEvaluation],
) -> DesignMemoryLayerA:
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    evaluation_by_id = {
        evaluation.evaluation_id: evaluation for evaluation in evaluations
    }
    if len(candidate_by_id) != len(tuple(candidates)):
        raise InvalidScientificProblem("D3 attribution candidates must be unique")
    if len(evaluation_by_id) != len(tuple(evaluations)):
        raise InvalidScientificProblem("D3 attribution evaluations must be unique")
    for entry in layer_a.entries:
        candidate = candidate_by_id.get(entry.candidate.candidate_id)
        evaluation = evaluation_by_id.get(entry.evaluation.evaluation_id)
        if candidate is None or evaluation is None:
            raise InvalidScientificProblem("D3 attribution source is absent")
        expected = DesignMemoryEntry.from_evaluation(
            scope=layer_a.scope, candidate=candidate, evaluation=evaluation
        )
        if expected.to_dict() != entry.to_dict():
            raise InvalidScientificProblem("D3 attribution entry disagrees with D1 source")
    return layer_a


def classify_memory(
    *, layer_a: DesignMemoryLayerA, policy: DesignMemoryPolicy
) -> DesignMemoryClassification:
    if not isinstance(layer_a, DesignMemoryLayerA):
        raise InvalidScientificProblem("D3 classification requires Layer A")
    if not isinstance(policy, DesignMemoryPolicy):
        raise InvalidScientificProblem("D3 classification requires a policy")
    policy.validate_against(layer_a)

    entries = tuple(sorted(layer_a.entries, key=lambda item: item.identity_sort_key))
    objective_map = layer_a.scope.objective_map
    reasons: dict[str, set[RetentionReason]] = {entry.identity: set() for entry in entries}
    scoped_details: dict[str, list[tuple[str, ...]]] = {entry.identity: [] for entry in entries}
    near_extreme: dict[str, dict[str, float]] = {entry.identity: {} for entry in entries}
    near_threshold: dict[str, dict[str, dict[str, float]]] = {
        entry.identity: {} for entry in entries
    }
    explicit_details: dict[str, list[str]] = {entry.identity: [] for entry in entries}

    pareto_members = pareto_member_identities(entries, layer_a.scope.objectives)
    for identity in pareto_members:
        reasons[identity].add(RetentionReason.PARETO_MEMBER)

    for elite_scope in policy.elite_scopes:
        objectives = tuple(objective_map[name] for name in elite_scope)
        members = pareto_member_identities(entries, objectives)
        for identity in members:
            reasons[identity].add(RetentionReason.SCOPED_ELITE)
            scoped_details[identity].append(elite_scope)

    for name, tolerance in policy.extreme_tolerances.items():
        objective = objective_map[name]
        values = [entry.objective_values[name].to(objective.unit).magnitude for entry in entries]
        extreme = min(values) if objective.direction is ObjectiveDirection.MINIMIZE else max(values)
        tol = tolerance.to(objective.unit).magnitude
        for entry in entries:
            distance = abs(entry.objective_values[name].to(objective.unit).magnitude - extreme)
            if distance <= tol:
                reasons[entry.identity].add(RetentionReason.NEAR_EXTREME)
                near_extreme[entry.identity][name] = distance

    for assessment in policy.assessment_contexts:
        for name, threshold in assessment.thresholds.items():
            objective = objective_map[name]
            target = threshold.to(objective.unit).magnitude
            tol = assessment.threshold_tolerances[name].to(objective.unit).magnitude
            for entry in entries:
                margin = entry.objective_values[name].to(objective.unit).magnitude - target
                if abs(margin) <= tol:
                    reasons[entry.identity].add(RetentionReason.NEAR_THRESHOLD)
                    by_assessment = near_threshold[entry.identity].setdefault(
                        assessment.assessment_id, {}
                    )
                    by_assessment[name] = margin

    partitions: dict[str, list[DesignMemoryEntry]] = {}
    for entry in entries:
        partitions.setdefault(layer_a.partition_keys[entry.identity], []).append(entry)
    for partition_entries in partitions.values():
        chosen = min(partition_entries, key=lambda item: item.identity_sort_key)
        reasons[chosen.identity].add(RetentionReason.DIVERSITY_REPRESENTATIVE)

    for item in policy.explicit_retention:
        reasons[item.identity].add(RetentionReason.EXPLICIT)
        explicit_details[item.identity].append(item.reason)

    classifications = []
    for entry in entries:
        classifications.append(
            EntryClassification(
                identity=entry.identity,
                candidate_id=entry.candidate.candidate_id,
                evaluation_id=entry.evaluation.evaluation_id,
                entry_digest=entry.entry_digest,
                reasons=tuple(reasons[entry.identity]),
                scoped_elite_scopes=tuple(scoped_details[entry.identity]),
                near_extreme_distances=near_extreme[entry.identity],
                near_threshold_margins=near_threshold[entry.identity],
                diversity_partition_key=layer_a.partition_keys[entry.identity],
                explicit_reasons=tuple(explicit_details[entry.identity]),
            )
        )

    by_identity = {item.identity: item for item in classifications}
    classified = [entry for entry in entries if by_identity[entry.identity].carries_reason()]
    tier1 = [
        entry
        for entry in entries
        if RetentionReason.PARETO_MEMBER in reasons[entry.identity]
        or RetentionReason.SCOPED_ELITE in reasons[entry.identity]
    ]
    if len(tier1) > policy.cap:
        raise InvalidScientificProblem("D3 tier-1 count exceeds cap")
    tier1_ids = [entry.identity for entry in tier1]
    tier2_ids = [
        entry.identity
        for entry in entries
        if entry.identity not in set(tier1_ids) and reasons[entry.identity]
    ]
    retained = tuple((tier1_ids + tier2_ids)[: policy.cap])
    retained_set = set(retained)
    discarded = tuple(
        entry.identity for entry in entries if reasons[entry.identity] and entry.identity not in retained_set
    )
    reason_census = {
        reason.value: sum(1 for item in classifications if reason in item.reasons)
        for reason in REASON_ORDER
    }
    d1_archive_ids = {
        entry.identity
        for entry in entries
        if RetentionReason.PARETO_MEMBER in reasons[entry.identity]
        or RetentionReason.SCOPED_ELITE in reasons[entry.identity]
    }
    summary = {
        "eligible_population_count": len(entries),
        "d1_pareto_count": reason_census[RetentionReason.PARETO_MEMBER.value],
        "d1_scoped_elite_count": reason_census[RetentionReason.SCOPED_ELITE.value],
        "per_reason_census": reason_census,
        "with_at_least_one_reason_count": len(classified),
        "retained_after_cap_count": len(retained),
        "classified_discarded_by_cap_count": len(discarded),
        "unclassified_count": len(entries) - len(classified),
        "retained_not_d1_archived_count": sum(
            1 for identity in retained if identity not in d1_archive_ids
        ),
        "cap": policy.cap,
        "tier1_count": len(tier1),
    }
    return DesignMemoryClassification(
        classifications=tuple(classifications),
        retained_identities=retained,
        discarded_classified_identities=discarded,
        summary=summary,
    )


def reason_overlaps(classification: DesignMemoryClassification) -> dict[str, int]:
    overlaps: dict[str, int] = {}
    for left_index, left in enumerate(REASON_ORDER):
        for right in REASON_ORDER[left_index + 1 :]:
            count = sum(
                1
                for item in classification.classifications
                if left in item.reasons and right in item.reasons
            )
            overlaps[f"{left.value}&{right.value}"] = count
    return overlaps
