"""Canonical MCP boundary for deterministic engineering planning.

This transport accepts only versioned EngineeringIntent records. Natural
language belongs outside this boundary: an LLM may translate a user's request
into the canonical contract, but MCP does not infer systems, quantities,
models, solvers, graphs or scientific verdicts from prose.

Optional display_metadata is intentionally non-authoritative. It may retain
the user's original language for presentation or provenance, but it never
enters EngineeringIntent identity, registry selection or planning decisions.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..planning import (
    EngineeringIntent,
    PlannerPolicy,
    plan_engineering_intent,
    production_planning_registries,
)
from ..scientific.serialization import schema_string, unwritable

CANONICAL_ENGINEERING_PLAN_SCHEMA = schema_string(
    "canonical_engineering_plan"
)


def _display_metadata(
    value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("display_metadata must be a JSON object")
    payload = dict(value)
    problem = unwritable(payload)
    if problem is not None:
        path, kind = problem
        raise ValueError(
            f"display_metadata{path} is not JSON-recordable ({kind})"
        )
    return payload


def plan_canonical_engineering_intent(
    intent: dict[str, Any],
    policy: dict[str, Any] | None = None,
    display_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan an already-canonical EngineeringIntent.

    The intent object is the scientific input. display_metadata is carried
    back for UI/LLM presentation and has zero scientific authority.
    """

    if not isinstance(intent, Mapping):
        raise TypeError(
            "intent must be a canonical EngineeringIntent JSON object"
        )
    typed_intent = EngineeringIntent.from_dict(intent)

    if policy is None:
        typed_policy = PlannerPolicy()
    else:
        if not isinstance(policy, Mapping):
            raise TypeError("policy must be a PlannerPolicy JSON object")
        typed_policy = PlannerPolicy.from_dict(policy)

    plan = plan_engineering_intent(
        typed_intent,
        production_planning_registries(),
        typed_policy,
    )

    return {
        "schema": CANONICAL_ENGINEERING_PLAN_SCHEMA,
        "authority": "deterministic_scientific_planner",
        "intent_identity": typed_intent.identity_digest,
        "intent_record": typed_intent.record_digest,
        "plan": plan.to_dict(),
        "display_metadata": _display_metadata(display_metadata),
    }


__all__ = [
    "CANONICAL_ENGINEERING_PLAN_SCHEMA",
    "plan_canonical_engineering_intent",
]
