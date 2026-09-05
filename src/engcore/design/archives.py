"""D1 — exact Pareto and scoped-elite selection archives.

These archives preserve plural success. They use only explicit objective
definitions and attributable eligible evaluations; there is no hidden weighted
score, normalization, product logic or claim that archive membership is
scientific truth.

Persistence is intentionally evidence-dependent: an archive payload records the
exact evaluation universe used to construct it, and deserialization requires the
caller to provide those concrete evaluations so membership can be recomputed.
A list of member references by itself is not treated as a verified Pareto claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.objectives import ObjectiveDefinition, ObjectiveDirection
from ..scientific.serialization import require_schema, schema_string
from .evaluation import (
    DesignEvaluation,
    DesignEvaluationReference,
    SelectionEligibility,
    project_objectives,
    require_objectives,
)
from .space import DesignSpaceReference

PARETO_ARCHIVE_SCHEMA = schema_string("pareto_archive")
SCOPED_ELITE_ARCHIVE_SCHEMA = schema_string("scoped_elite_archive")


def _require_eligible(evaluation: DesignEvaluation) -> None:
    if evaluation.eligibility is not SelectionEligibility.ELIGIBLE:
        raise InvalidScientificProblem(
            "Pareto comparison requires explicitly ELIGIBLE evaluations"
        )


def dominates(
    left: DesignEvaluation,
    right: DesignEvaluation,
    objectives: Iterable[ObjectiveDefinition],
) -> bool:
    """Return whether ``left`` exactly Pareto-dominates ``right``.

    Dominance is no-worse on every objective and strictly better on at least
    one. Values are converted through each objective's declared unit before
    comparison. No tolerance or scalarization is hidden here.
    """
    if not isinstance(left, DesignEvaluation) or not isinstance(right, DesignEvaluation):
        raise InvalidScientificProblem("dominance requires DesignEvaluation records")
    _require_eligible(left)
    _require_eligible(right)
    if left.design_space.key != right.design_space.key:
        raise InvalidScientificProblem(
            "cannot compare evaluations from different design spaces"
        )

    declared = require_objectives(objectives)
    left_values = project_objectives(left, declared)
    right_values = project_objectives(right, declared)

    no_worse_all = True
    strictly_better_any = False
    for lproj, rproj in zip(left_values, right_values):
        objective = lproj.objective
        lv = lproj.value.magnitude
        rv = rproj.value.magnitude
        if objective.direction is ObjectiveDirection.MAXIMIZE:
            no_worse = lv >= rv
            strictly_better = lv > rv
        else:
            no_worse = lv <= rv
            strictly_better = lv < rv
        no_worse_all = no_worse_all and no_worse
        strictly_better_any = strictly_better_any or strictly_better

    return no_worse_all and strictly_better_any


def _validate_evaluations(
    evaluations: Sequence[DesignEvaluation],
    design_space: DesignSpaceReference,
) -> tuple[DesignEvaluation, ...]:
    items = tuple(evaluations)
    if not items:
        raise InvalidScientificProblem("archive verification requires evaluations")
    if any(not isinstance(item, DesignEvaluation) for item in items):
        raise InvalidScientificProblem("archive inputs must be DesignEvaluation records")
    ids = [item.evaluation_id for item in items]
    if len(ids) != len(set(ids)):
        raise InvalidScientificProblem("archive evaluation ids must be unique")
    for item in items:
        if item.design_space.key != design_space.key:
            raise InvalidScientificProblem(
                "archive evaluation design-space identity mismatch"
            )
    return tuple(sorted(items, key=lambda item: item.evaluation_id))


def _evaluation_refs(
    evaluations: Sequence[DesignEvaluation],
) -> tuple[DesignEvaluationReference, ...]:
    return tuple(item.reference for item in sorted(evaluations, key=lambda item: item.evaluation_id))


def _require_reference_set_equal(
    declared: Sequence[DesignEvaluationReference],
    evaluations: Sequence[DesignEvaluation],
) -> None:
    declared_ids = tuple(sorted(item.evaluation_id for item in declared))
    actual_ids = tuple(item.evaluation_id for item in sorted(evaluations, key=lambda item: item.evaluation_id))
    if declared_ids != actual_ids:
        raise InvalidScientificProblem(
            "archive verification evaluation universe does not match persisted source_evaluations"
        )


def _pareto_refs(
    evaluations: Sequence[DesignEvaluation],
    objectives: tuple[ObjectiveDefinition, ...],
) -> tuple[DesignEvaluationReference, ...]:
    eligible = tuple(
        item
        for item in evaluations
        if item.eligibility is SelectionEligibility.ELIGIBLE
    )
    nondominated: list[DesignEvaluationReference] = []
    for candidate in eligible:
        if any(
            other.evaluation_id != candidate.evaluation_id
            and dominates(other, candidate, objectives)
            for other in eligible
        ):
            continue
        nondominated.append(candidate.reference)
    return tuple(sorted(nondominated, key=lambda ref: ref.evaluation_id))


def _validate_refs(
    refs: Sequence[DesignEvaluationReference], *, context: str
) -> tuple[DesignEvaluationReference, ...]:
    items = tuple(refs)
    if any(not isinstance(item, DesignEvaluationReference) for item in items):
        raise InvalidScientificProblem(
            f"{context} must be DesignEvaluationReference records"
        )
    ids = [item.evaluation_id for item in items]
    if len(ids) != len(set(ids)):
        raise InvalidScientificProblem(f"{context} must be unique")
    return tuple(sorted(items, key=lambda item: item.evaluation_id))


@dataclass(frozen=True)
class ParetoArchive:
    archive_id: str
    design_space: DesignSpaceReference
    objectives: tuple[ObjectiveDefinition, ...]
    source_evaluations: tuple[DesignEvaluationReference, ...]
    members: tuple[DesignEvaluationReference, ...]

    def __post_init__(self) -> None:
        archive_id = str(self.archive_id).strip()
        if not archive_id:
            raise InvalidScientificProblem("Pareto archive requires archive_id")
        if not isinstance(self.design_space, DesignSpaceReference):
            raise InvalidScientificProblem(
                "Pareto archive requires DesignSpaceReference"
            )
        objectives = require_objectives(self.objectives)
        source = _validate_refs(
            self.source_evaluations, context="Pareto source evaluations"
        )
        if not source:
            raise InvalidScientificProblem("Pareto archive requires source evaluations")
        members = _validate_refs(self.members, context="Pareto archive members")
        source_ids = {item.evaluation_id for item in source}
        if any(item.evaluation_id not in source_ids for item in members):
            raise InvalidScientificProblem(
                "Pareto archive member must belong to source_evaluations"
            )
        object.__setattr__(self, "archive_id", archive_id)
        object.__setattr__(self, "objectives", objectives)
        object.__setattr__(self, "source_evaluations", source)
        object.__setattr__(self, "members", members)

    @classmethod
    def build(
        cls,
        *,
        archive_id: str,
        design_space: DesignSpaceReference,
        objectives: Iterable[ObjectiveDefinition],
        evaluations: Sequence[DesignEvaluation],
    ) -> "ParetoArchive":
        declared = require_objectives(objectives)
        items = _validate_evaluations(evaluations, design_space)
        return cls(
            archive_id=archive_id,
            design_space=design_space,
            objectives=declared,
            source_evaluations=_evaluation_refs(items),
            members=_pareto_refs(items, declared),
        )

    def validate_against(
        self, evaluations: Sequence[DesignEvaluation]
    ) -> "ParetoArchive":
        """Recompute membership against the exact persisted evaluation universe."""
        items = _validate_evaluations(evaluations, self.design_space)
        _require_reference_set_equal(self.source_evaluations, items)
        expected = _pareto_refs(items, self.objectives)
        if expected != self.members:
            raise InvalidScientificProblem(
                "persisted Pareto membership does not match recomputed membership"
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARETO_ARCHIVE_SCHEMA,
            "archive_id": self.archive_id,
            "design_space": self.design_space.to_dict(),
            "objectives": [item.to_dict() for item in self.objectives],
            "source_evaluations": [item.to_dict() for item in self.source_evaluations],
            "members": [item.to_dict() for item in self.members],
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        evaluations: Sequence[DesignEvaluation] | None = None,
    ) -> "ParetoArchive":
        """Deserialize only with evidence sufficient to re-verify membership."""
        require_schema(payload, PARETO_ARCHIVE_SCHEMA)
        if evaluations is None:
            raise InvalidScientificProblem(
                "ParetoArchive.from_dict requires concrete evaluations for verification"
            )
        archive = cls(
            archive_id=payload["archive_id"],
            design_space=DesignSpaceReference.from_dict(payload["design_space"]),
            objectives=tuple(
                ObjectiveDefinition.from_dict(item)
                for item in payload.get("objectives", ())
            ),
            source_evaluations=tuple(
                DesignEvaluationReference.from_dict(item)
                for item in payload.get("source_evaluations", ())
            ),
            members=tuple(
                DesignEvaluationReference.from_dict(item)
                for item in payload.get("members", ())
            ),
        )
        return archive.validate_against(evaluations)


@dataclass(frozen=True)
class ScopedEliteArchive:
    """Partial-success archive under an opaque caller-declared scientific scope."""

    archive_id: str
    scope_ref: str
    design_space: DesignSpaceReference
    objectives: tuple[ObjectiveDefinition, ...]
    source_evaluations: tuple[DesignEvaluationReference, ...]
    members: tuple[DesignEvaluationReference, ...]

    def __post_init__(self) -> None:
        archive_id = str(self.archive_id).strip()
        scope_ref = str(self.scope_ref).strip()
        if not archive_id:
            raise InvalidScientificProblem("scoped elite archive requires archive_id")
        if not scope_ref:
            raise InvalidScientificProblem("scoped elite archive requires scope_ref")
        if not isinstance(self.design_space, DesignSpaceReference):
            raise InvalidScientificProblem(
                "scoped elite archive requires DesignSpaceReference"
            )
        objectives = require_objectives(self.objectives)
        source = _validate_refs(
            self.source_evaluations, context="scoped elite source evaluations"
        )
        if not source:
            raise InvalidScientificProblem(
                "scoped elite archive requires source evaluations"
            )
        members = _validate_refs(self.members, context="scoped elite members")
        source_ids = {item.evaluation_id for item in source}
        if any(item.evaluation_id not in source_ids for item in members):
            raise InvalidScientificProblem(
                "scoped elite member must belong to source_evaluations"
            )
        object.__setattr__(self, "archive_id", archive_id)
        object.__setattr__(self, "scope_ref", scope_ref)
        object.__setattr__(self, "objectives", objectives)
        object.__setattr__(self, "source_evaluations", source)
        object.__setattr__(self, "members", members)

    @classmethod
    def build(
        cls,
        *,
        archive_id: str,
        scope_ref: str,
        design_space: DesignSpaceReference,
        objectives: Iterable[ObjectiveDefinition],
        evaluations: Sequence[DesignEvaluation],
    ) -> "ScopedEliteArchive":
        declared = require_objectives(objectives)
        items = _validate_evaluations(evaluations, design_space)
        return cls(
            archive_id=archive_id,
            scope_ref=scope_ref,
            design_space=design_space,
            objectives=declared,
            source_evaluations=_evaluation_refs(items),
            members=_pareto_refs(items, declared),
        )

    def validate_against(
        self, evaluations: Sequence[DesignEvaluation]
    ) -> "ScopedEliteArchive":
        items = _validate_evaluations(evaluations, self.design_space)
        _require_reference_set_equal(self.source_evaluations, items)
        expected = _pareto_refs(items, self.objectives)
        if expected != self.members:
            raise InvalidScientificProblem(
                "persisted scoped-elite membership does not match recomputed membership"
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCOPED_ELITE_ARCHIVE_SCHEMA,
            "archive_id": self.archive_id,
            "scope_ref": self.scope_ref,
            "design_space": self.design_space.to_dict(),
            "objectives": [item.to_dict() for item in self.objectives],
            "source_evaluations": [item.to_dict() for item in self.source_evaluations],
            "members": [item.to_dict() for item in self.members],
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        evaluations: Sequence[DesignEvaluation] | None = None,
    ) -> "ScopedEliteArchive":
        require_schema(payload, SCOPED_ELITE_ARCHIVE_SCHEMA)
        if evaluations is None:
            raise InvalidScientificProblem(
                "ScopedEliteArchive.from_dict requires concrete evaluations for verification"
            )
        archive = cls(
            archive_id=payload["archive_id"],
            scope_ref=payload["scope_ref"],
            design_space=DesignSpaceReference.from_dict(payload["design_space"]),
            objectives=tuple(
                ObjectiveDefinition.from_dict(item)
                for item in payload.get("objectives", ())
            ),
            source_evaluations=tuple(
                DesignEvaluationReference.from_dict(item)
                for item in payload.get("source_evaluations", ())
            ),
            members=tuple(
                DesignEvaluationReference.from_dict(item)
                for item in payload.get("members", ())
            ),
        )
        return archive.validate_against(evaluations)
