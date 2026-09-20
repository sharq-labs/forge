"""Executable system-applicability predicates for Composition Packs.

Descriptions remain display/provenance text. Scientific admission is determined
only by typed predicates evaluated against canonical EngineeringIntent facts
and deterministic graph/policy properties.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.values import (
    ScientificValue,
    decode_value,
    encode_value,
    require_scientific_value,
)
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity

APPLICABILITY_PREDICATE_SCHEMA = schema_string(
    "composition_applicability_predicate"
)


class ApplicabilityPredicateKind(str, Enum):
    FACT_PRESENT = "fact_present"
    FACT_EQUALS = "fact_equals"
    FACT_LE = "fact_le"
    FACT_LT = "fact_lt"
    FACT_GE = "fact_ge"
    FACT_GT = "fact_gt"
    FACT_BETWEEN = "fact_between"
    STATIC_EXTERNAL_INPUTS = "static_external_inputs"


class ApplicabilityState(str, Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ApplicabilityPredicate:
    predicate_id: str
    kind: ApplicabilityPredicateKind
    path: str = ""
    expected: ScientificValue | None = None
    lower: ScientificValue | None = None
    upper: ScientificValue | None = None
    description: str = ""

    def __post_init__(self) -> None:
        pid = str(self.predicate_id).strip()
        if not pid:
            raise InvalidScientificProblem(
                "applicability predicate requires predicate_id"
            )
        object.__setattr__(self, "predicate_id", pid)
        object.__setattr__(self, "kind", ApplicabilityPredicateKind(self.kind))
        object.__setattr__(self, "path", str(self.path).strip())
        object.__setattr__(
            self, "description", str(self.description).strip()
        )

        if self.kind is ApplicabilityPredicateKind.STATIC_EXTERNAL_INPUTS:
            if self.path or any(
                item is not None
                for item in (self.expected, self.lower, self.upper)
            ):
                raise InvalidScientificProblem(
                    "STATIC_EXTERNAL_INPUTS carries no fact operands"
                )
            return

        if not self.path:
            raise InvalidScientificProblem(
                f"{self.kind.value} requires canonical fact path"
            )

        if self.kind is ApplicabilityPredicateKind.FACT_PRESENT:
            if any(
                item is not None
                for item in (self.expected, self.lower, self.upper)
            ):
                raise InvalidScientificProblem(
                    "FACT_PRESENT carries no value operands"
                )
            return

        if self.kind is ApplicabilityPredicateKind.FACT_BETWEEN:
            if self.lower is None or self.upper is None:
                raise InvalidScientificProblem(
                    "FACT_BETWEEN requires lower and upper"
                )
            require_scientific_value(
                self.lower, context=f"{pid}.lower"
            )
            require_scientific_value(
                self.upper, context=f"{pid}.upper"
            )
            return

        if self.expected is None:
            raise InvalidScientificProblem(
                f"{self.kind.value} requires expected"
            )
        require_scientific_value(
            self.expected, context=f"{pid}.expected"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": APPLICABILITY_PREDICATE_SCHEMA,
            "predicate_id": self.predicate_id,
            "kind": self.kind.value,
            "path": self.path,
            "expected": (
                None
                if self.expected is None
                else encode_value(self.expected)
            ),
            "lower": (
                None if self.lower is None else encode_value(self.lower)
            ),
            "upper": (
                None if self.upper is None else encode_value(self.upper)
            ),
            "description": self.description,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "ApplicabilityPredicate":
        require_schema(payload, APPLICABILITY_PREDICATE_SCHEMA)

        def read(name: str):
            raw = payload.get(name)
            return None if raw is None else decode_value(raw)

        return cls(
            predicate_id=payload["predicate_id"],
            kind=ApplicabilityPredicateKind(payload["kind"]),
            path=payload.get("path", ""),
            expected=read("expected"),
            lower=read("lower"),
            upper=read("upper"),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class ApplicabilityEvaluation:
    predicate_id: str
    state: ApplicabilityState
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "predicate_id", str(self.predicate_id).strip()
        )
        object.__setattr__(self, "state", ApplicabilityState(self.state))
        object.__setattr__(self, "reason", str(self.reason).strip())


def _compare(left: Any, right: Any, op: str) -> bool:
    if isinstance(left, Quantity) or isinstance(right, Quantity):
        if not isinstance(left, Quantity) or not isinstance(right, Quantity):
            raise InvalidScientificProblem(
                "applicability comparison mixes Quantity and non-Quantity"
            )
        converted = left.to(right.units)
        a = float(converted.magnitude)
        b = float(right.magnitude)
    else:
        a, b = left, right

    if op == "eq":
        return a == b
    if op == "le":
        return a <= b
    if op == "lt":
        return a < b
    if op == "ge":
        return a >= b
    if op == "gt":
        return a > b
    raise AssertionError(op)


def evaluate_applicability_predicate(
    predicate: ApplicabilityPredicate,
    *,
    facts: Mapping[str, ScientificValue],
    static_external_inputs: bool,
) -> ApplicabilityEvaluation:
    kind = predicate.kind
    if kind is ApplicabilityPredicateKind.STATIC_EXTERNAL_INPUTS:
        return ApplicabilityEvaluation(
            predicate.predicate_id,
            (
                ApplicabilityState.SATISFIED
                if static_external_inputs
                else ApplicabilityState.VIOLATED
            ),
            (
                "execution contract supplies constant external inputs over "
                "the run horizon"
                if static_external_inputs
                else "execution contract permits time-varying external inputs"
            ),
        )

    if predicate.path not in facts:
        return ApplicabilityEvaluation(
            predicate.predicate_id,
            ApplicabilityState.UNKNOWN,
            f"canonical fact {predicate.path!r} is absent",
        )

    if kind is ApplicabilityPredicateKind.FACT_PRESENT:
        return ApplicabilityEvaluation(
            predicate.predicate_id,
            ApplicabilityState.SATISFIED,
            f"canonical fact {predicate.path!r} is present",
        )

    value = facts[predicate.path]
    try:
        if kind is ApplicabilityPredicateKind.FACT_BETWEEN:
            assert predicate.lower is not None
            assert predicate.upper is not None
            passed = _compare(value, predicate.lower, "ge") and _compare(
                value, predicate.upper, "le"
            )
        else:
            assert predicate.expected is not None
            op = {
                ApplicabilityPredicateKind.FACT_EQUALS: "eq",
                ApplicabilityPredicateKind.FACT_LE: "le",
                ApplicabilityPredicateKind.FACT_LT: "lt",
                ApplicabilityPredicateKind.FACT_GE: "ge",
                ApplicabilityPredicateKind.FACT_GT: "gt",
            }[kind]
            passed = _compare(value, predicate.expected, op)
    except Exception as exc:
        return ApplicabilityEvaluation(
            predicate.predicate_id,
            ApplicabilityState.VIOLATED,
            f"predicate evaluation failed: {exc}",
        )

    return ApplicabilityEvaluation(
        predicate.predicate_id,
        (
            ApplicabilityState.SATISFIED
            if passed
            else ApplicabilityState.VIOLATED
        ),
        (
            f"predicate {predicate.predicate_id!r} satisfied"
            if passed
            else f"predicate {predicate.predicate_id!r} violated"
        ),
    )


__all__ = [
    "APPLICABILITY_PREDICATE_SCHEMA",
    "ApplicabilityEvaluation",
    "ApplicabilityPredicate",
    "ApplicabilityPredicateKind",
    "ApplicabilityState",
    "evaluate_applicability_predicate",
]
