"""Deterministic clarification questions derived from planning gaps."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..claims.capabilities import CapabilityRegistry
from ..scientific.serialization import require_schema, schema_string
from .intent import EngineeringIntent
from .validation import IntentValidation, IssueKind

CLARIFICATION_SCHEMA = schema_string("engineering_clarification_question")


class ClarificationKind(str, Enum):
    MISSING_INPUT = "missing_input"
    CAPABILITY_CHOICE = "capability_choice"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class ClarificationQuestion:
    question_id: str
    qoi_id: str
    kind: ClarificationKind
    prompt: str
    reason: str
    path: str | None = None
    expected_kind: str | None = None
    unit_exemplar: str | None = None
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label in ("question_id", "qoi_id", "prompt", "reason"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"clarification requires {label}")
            object.__setattr__(self, label, value)
        object.__setattr__(self, "kind", ClarificationKind(self.kind))
        object.__setattr__(self, "options", tuple(sorted(set(str(x) for x in self.options))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CLARIFICATION_SCHEMA,
            "question_id": self.question_id,
            "qoi_id": self.qoi_id,
            "kind": self.kind.value,
            "prompt": self.prompt,
            "reason": self.reason,
            "path": self.path,
            "expected_kind": self.expected_kind,
            "unit_exemplar": self.unit_exemplar,
            "options": list(self.options),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ClarificationQuestion":
        require_schema(payload, CLARIFICATION_SCHEMA)
        return cls(
            question_id=payload["question_id"],
            qoi_id=payload["qoi_id"],
            kind=ClarificationKind(payload["kind"]),
            prompt=payload["prompt"],
            reason=payload["reason"],
            path=payload.get("path"),
            expected_kind=payload.get("expected_kind"),
            unit_exemplar=payload.get("unit_exemplar"),
            options=tuple(payload.get("options", ())),
        )


def clarification_questions(
    intent: EngineeringIntent,
    validation: IntentValidation,
    registry: CapabilityRegistry,
    *,
    selected_capabilities: Mapping[str, str] | None = None,
) -> tuple[ClarificationQuestion, ...]:
    if validation.intent_identity != intent.identity_digest:
        raise ValueError("validation belongs to another engineering intent")
    if validation.registry_digest != registry.digest:
        raise ValueError("validation belongs to another capability registry")

    selected_capabilities = dict(selected_capabilities or {})
    questions: list[ClarificationQuestion] = []
    for qoi in intent.qois:
        eligible = validation.eligible_for(qoi.qoi_id)
        selected = selected_capabilities.get(qoi.qoi_id)
        if selected is not None:
            eligible = tuple(
                screen
                for screen in eligible
                if screen.capability_id == selected
            )
        if len(eligible) > 1:
            options = tuple(
                f"{screen.capability_id}@{screen.capability_version} — "
                f"{registry.get(screen.capability_id).summary}"
                for screen in eligible
            )
            questions.append(
                ClarificationQuestion(
                    question_id=f"choose-capability:{qoi.qoi_id}",
                    qoi_id=qoi.qoi_id,
                    kind=ClarificationKind.CAPABILITY_CHOICE,
                    prompt=f"Which declared simulation capability should answer {qoi.name!r}?",
                    reason=(
                        "More than one registered capability is scientifically compatible; "
                        "Forge does not select one from registration order."
                    ),
                    options=options,
                )
            )
            continue
        if len(eligible) != 1:
            continue

        screen = eligible[0]
        declaration = registry.get(screen.capability_id)
        by_path = {item.path: item for item in declaration.inputs}
        for path in screen.missing_inputs:
            item = by_path[path]
            unit = item.unit_exemplar
            expected = item.kind.value
            unit_text = f" in {unit}" if unit else ""
            questions.append(
                ClarificationQuestion(
                    question_id=f"missing:{qoi.qoi_id}:{screen.capability_id}:{path}",
                    qoi_id=qoi.qoi_id,
                    kind=ClarificationKind.MISSING_INPUT,
                    path=path,
                    expected_kind=expected,
                    unit_exemplar=unit,
                    prompt=f"Provide {path}{unit_text}.",
                    reason=item.description or f"{screen.capability_id} requires this {item.role.value}.",
                )
            )

    for issue in validation.issues:
        if issue.kind is not IssueKind.INVALID_INPUT:
            continue
        qoi_id = issue.subject.split(":", 1)[0]
        questions.append(
            ClarificationQuestion(
                question_id=f"invalid:{len(questions)}:{qoi_id}",
                qoi_id=qoi_id,
                kind=ClarificationKind.INVALID_INPUT,
                prompt="Correct the supplied engineering input described below.",
                reason=issue.detail,
            )
        )

    unique = {question.question_id: question for question in questions}
    return tuple(unique[key] for key in sorted(unique))


__all__ = [
    "CLARIFICATION_SCHEMA",
    "ClarificationKind",
    "ClarificationQuestion",
    "clarification_questions",
]
