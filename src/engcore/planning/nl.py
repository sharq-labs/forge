"""Outer natural-language adapter for EngineeringIntent proposals.

The LLM proposes structure. This boundary verifies that every numeric/typed
engineering fact, decision bound and declared resource/evidence preference
that could change the scientific plan is grounded in an exact source span.
Model, realization, solver, graph and verdict authority fields are refused.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import re
from typing import Any, Mapping, Protocol, Sequence

from ..scientific.errors import InvalidScientificProblem
from .intent import EngineeringIntent

FORBIDDEN_PLANNER_AUTHORITY_FIELDS = frozenset(
    {
        "selected_model",
        "selected_realization",
        "selected_solver",
        "selected_capability",
        "physics_graph",
        "coupling_plan",
        "validation_result",
        "attained_levels",
        "quantified_uncertainty",
        "credibility",
        "assurance",
        "verdict",
        "result",
        "decision_outcome",
    }
)


class IntentProposer(Protocol):
    def propose(self, text: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class NaturalLanguageIntent:
    status: str
    findings: tuple[str, ...]
    dropped_facts: tuple[str, ...]
    intent: EngineeringIntent | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "findings": list(self.findings),
            "dropped_facts": list(self.dropped_facts),
            "intent": None if self.intent is None else self.intent.to_dict(),
            "intent_identity": (
                None if self.intent is None else self.intent.identity_digest
            ),
            "authority": (
                "language-model proposal only; grounding admits user-stated "
                "facts, the deterministic planner chooses scientific execution"
            ),
        }


def _forbidden(node: Any, where: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, Mapping):
        for key, child in node.items():
            path = f"{where}/{key}"
            if str(key) in FORBIDDEN_PLANNER_AUTHORITY_FIELDS:
                found.append(path)
            found.extend(_forbidden(child, path))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            found.extend(_forbidden(child, f"{where}/{index}"))
    return found


def _literal_in(span: str, raw: Any) -> bool:
    if isinstance(raw, Mapping):
        if "magnitude" in raw:
            raw = raw["magnitude"]
        elif "value" in raw:
            raw = raw["value"]
        elif "rung_id" in raw:
            raw = raw["rung_id"]
        else:
            return False
    if isinstance(raw, bool):
        return str(raw).lower() in span.lower()
    if isinstance(raw, int) and not isinstance(raw, bool):
        number = float(raw)
    elif isinstance(raw, float):
        number = raw
    elif isinstance(raw, str):
        return raw.lower() in span.lower()
    else:
        return False
    for token in re.findall(
        r"[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?",
        span,
    ):
        try:
            if float(token.replace(",", ".")) == number:
                return True
        except ValueError:
            continue
    return False


def _span(
    text: str,
    spans: Mapping[str, Sequence[int]],
    key: str,
) -> str | None:
    span = spans.get(key)
    if span is None:
        return None
    if (
        isinstance(span, (str, bytes))
        or not isinstance(span, Sequence)
        or len(span) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in span
        )
    ):
        return None
    start, end = int(span[0]), int(span[1])
    if not (0 <= start < end <= len(text)):
        return None
    return text[start:end]


def _grounded(
    text: str,
    spans: Mapping[str, Sequence[int]],
    key: str,
    raw: Any,
) -> bool:
    source = _span(text, spans, key)
    return source is not None and _literal_in(source, raw)


def _semantically_grounded(
    text: str,
    spans: Mapping[str, Sequence[int]],
    key: str,
) -> bool:
    source = _span(text, spans, key)
    return source is not None and bool(source.strip())


def compile_natural_language_intent(
    text: str,
    proposal: Mapping[str, Any],
    spans: Mapping[str, Sequence[int]],
) -> NaturalLanguageIntent:
    text = str(text)
    if not text.strip():
        raise InvalidScientificProblem(
            "natural-language intent text must be non-empty"
        )
    if not isinstance(proposal, Mapping):
        raise InvalidScientificProblem("intent proposal must be a mapping")
    if not isinstance(spans, Mapping):
        raise InvalidScientificProblem("intent spans must be a mapping")

    proposal = copy.deepcopy(dict(proposal))
    forbidden = _forbidden(proposal)
    if forbidden:
        return NaturalLanguageIntent(
            "refused",
            tuple(
                f"proposal may not carry {path}: planner/runtime authority "
                "is not an LLM input"
                for path in sorted(forbidden)
            ),
            (),
            None,
        )

    capability_assertions = []
    if proposal.get("required_capabilities"):
        capability_assertions.append("required_capabilities")
    context = proposal.get("context")
    if (
        isinstance(context, Mapping)
        and context.get("required_capabilities")
    ):
        capability_assertions.append("context.required_capabilities")
    for index, component in enumerate(proposal.get("components", ())):
        if (
            isinstance(component, Mapping)
            and component.get("required_capabilities")
        ):
            capability_assertions.append(
                f"components[{index}].required_capabilities"
            )
    if capability_assertions:
        return NaturalLanguageIntent(
            "refused",
            tuple(
                f"{path} contains internal scientific capability authority; "
                "the deterministic planner/decomposer derives capability "
                "requirements"
                for path in capability_assertions
            ),
            (),
            None,
        )

    findings: list[str] = []
    dropped: list[str] = []
    grounded_facts = []
    for raw_fact in list(proposal.get("facts", ())):
        if not isinstance(raw_fact, Mapping):
            return NaturalLanguageIntent(
                "refused",
                ("facts must be structured records",),
                (),
                None,
            )
        path = str(raw_fact.get("path", ""))
        if not _grounded(text, spans, path, raw_fact.get("value")):
            findings.append(
                f"fact {path!r} is not literally stated at its cited source "
                "span; removed so planning can ask for it"
            )
            dropped.append(path)
            continue
        grounded_facts.append(raw_fact)
    proposal["facts"] = grounded_facts

    for raw in proposal.get("constraints", ()):
        constraint = (
            raw.get("constraint", {})
            if isinstance(raw, Mapping)
            else {}
        )
        name = str(constraint.get("name", ""))
        operator_key = f"constraints.{name}.operator"
        if (
            constraint.get("operator") is not None
            and not _semantically_grounded(
                text,
                spans,
                operator_key,
            )
        ):
            return NaturalLanguageIntent(
                "refused",
                (
                    f"{operator_key} changes the engineering decision but "
                    "has no cited source span",
                ),
                tuple(sorted(dropped)),
                None,
            )
        for field in ("bound", "tolerance"):
            value = constraint.get(field)
            if value is None:
                continue
            key = f"constraints.{name}.{field}"
            if not _grounded(text, spans, key, value):
                return NaturalLanguageIntent(
                    "refused",
                    (
                        f"{key} changes the engineering decision but is not "
                        "grounded in the cited user text",
                    ),
                    tuple(sorted(dropped)),
                    None,
                )

    for raw in proposal.get("objectives", ()):
        if not isinstance(raw, Mapping) or raw.get("target") is None:
            continue
        objective_id = str(raw.get("objective_id", ""))
        key = f"objectives.{objective_id}.target"
        if not _grounded(text, spans, key, raw.get("target")):
            return NaturalLanguageIntent(
                "refused",
                (
                    f"{key} changes the engineering objective but is not "
                    "grounded in the cited user text",
                ),
                tuple(sorted(dropped)),
                None,
            )
        if raw.get("weight", 1.0) != 1.0:
            weight_key = f"objectives.{objective_id}.weight"
            if not _grounded(
                text,
                spans,
                weight_key,
                raw.get("weight"),
            ):
                return NaturalLanguageIntent(
                    "refused",
                    (
                        f"{weight_key} changes objective trade-offs but is "
                        "not grounded in the cited user text",
                    ),
                    tuple(sorted(dropped)),
                    None,
                )

    context = proposal.get("context")
    if isinstance(context, Mapping):
        for level in context.get("required_levels", ()):
            key = f"context.required_levels.{level}"
            if not _semantically_grounded(text, spans, key):
                return NaturalLanguageIntent(
                    "refused",
                    (
                        f"{key} has no cited source span; the LLM may not "
                        "silently set the evidence bar",
                    ),
                    tuple(sorted(dropped)),
                    None,
                )
        for channel in context.get("required_uncertainty", ()):
            key = f"context.required_uncertainty.{channel}"
            if not _semantically_grounded(text, spans, key):
                return NaturalLanguageIntent(
                    "refused",
                    (
                        f"{key} has no cited source span; the LLM may not "
                        "silently demand or waive uncertainty work",
                    ),
                    tuple(sorted(dropped)),
                    None,
                )
        if context.get("require_independent_verification") is True:
            key = "context.require_independent_verification"
            if not _semantically_grounded(text, spans, key):
                return NaturalLanguageIntent(
                    "refused",
                    (
                        f"{key} has no cited source span; independent "
                        "verification demand cannot be invented",
                    ),
                    tuple(sorted(dropped)),
                    None,
                )

    budget = proposal.get("compute_budget")
    if (
        isinstance(budget, Mapping)
        and budget.get("max_wall_time") is not None
        and not _grounded(
            text,
            spans,
            "compute_budget.max_wall_time",
            budget["max_wall_time"],
        )
    ):
        return NaturalLanguageIntent(
            "refused",
            (
                "compute_budget.max_wall_time is not grounded in the cited "
                "user text",
            ),
            tuple(sorted(dropped)),
            None,
        )
    if (
        isinstance(budget, Mapping)
        and budget.get("max_solver_calls") is not None
        and not _grounded(
            text,
            spans,
            "compute_budget.max_solver_calls",
            budget["max_solver_calls"],
        )
    ):
        return NaturalLanguageIntent(
            "refused",
            (
                "compute_budget.max_solver_calls is not grounded in the "
                "cited user text",
            ),
            tuple(sorted(dropped)),
            None,
        )

    fidelity = proposal.get("fidelity")
    if isinstance(fidelity, Mapping):
        for field in ("ladder_id", "ladder_version"):
            value = fidelity.get(field)
            if (
                value is not None
                and not _semantically_grounded(
                    text,
                    spans,
                    f"fidelity.{field}",
                )
            ):
                return NaturalLanguageIntent(
                    "refused",
                    (
                        f"fidelity.{field} has no cited source span; a "
                        "language model may not select an internal study "
                        "ladder silently",
                    ),
                    tuple(sorted(dropped)),
                    None,
                )
        for field in ("minimum_rung", "preferred_rung"):
            value = fidelity.get(field)
            if value is None:
                continue
            key = f"fidelity.{field}"
            if not _semantically_grounded(text, spans, key):
                return NaturalLanguageIntent(
                    "refused",
                    (f"{key} has no cited source span",),
                    tuple(sorted(dropped)),
                    None,
                )

    try:
        intent = EngineeringIntent.from_dict(proposal)
    except Exception as exc:
        return NaturalLanguageIntent(
            "refused",
            (f"structured EngineeringIntent is invalid: {exc}",),
            tuple(sorted(dropped)),
            None,
        )

    return NaturalLanguageIntent(
        "grounded",
        tuple(findings),
        tuple(sorted(dropped)),
        intent,
    )


__all__ = [
    "FORBIDDEN_PLANNER_AUTHORITY_FIELDS",
    "IntentProposer",
    "NaturalLanguageIntent",
    "compile_natural_language_intent",
]
