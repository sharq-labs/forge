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
    FORBIDDEN_PLANNER_AUTHORITY_FIELDS,
    EngineeringIntent,
    PlannerPolicy,
    plan_engineering_intent,
    production_planning_registries,
)
from ..scientific.serialization import schema_string, unwritable

CANONICAL_ENGINEERING_PLAN_SCHEMA = schema_string(
    "canonical_engineering_plan"
)


def _forbidden_authority_fields(
    node: Any,
    path: str = "",
) -> tuple[str, ...]:
    found: list[str] = []
    if isinstance(node, Mapping):
        for key, child in node.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text in FORBIDDEN_PLANNER_AUTHORITY_FIELDS:
                found.append(child_path)
            found.extend(_forbidden_authority_fields(child, child_path))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            child_path = f"{path}[{index}]"
            found.extend(_forbidden_authority_fields(child, child_path))
    return tuple(sorted(set(found)))


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
    forbidden = _forbidden_authority_fields(intent)
    if forbidden:
        raise ValueError(
            "canonical MCP intent contains planner/runtime authority fields: "
            f"{list(forbidden)}"
        )
    typed_intent = EngineeringIntent.from_dict(intent)

    capability_authority = {
        capability.identifier
        for capability in typed_intent.required_capabilities
    }
    capability_authority.update(
        capability.identifier
        for capability in typed_intent.context.required_capabilities
    )
    for component in typed_intent.components:
        capability_authority.update(
            capability.identifier
            for capability in component.required_capabilities
        )
    if capability_authority:
        raise ValueError(
            "canonical MCP intent may not supply internal scientific capability "
            f"authority: {sorted(capability_authority)}"
        )

    # The public MCP caller cannot inject PlannerPolicy. Model, realization,
    # solver and blueprint preferences are operator/server authority, not LLM
    # proposal fields. Ambiguity therefore remains explicit unless the product
    # assembly supplies a trusted policy through a different boundary.
    plan = plan_engineering_intent(
        typed_intent,
        production_planning_registries(),
        PlannerPolicy(),
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
