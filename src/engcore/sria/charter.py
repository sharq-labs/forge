"""Campaign Charter — what a research campaign is *for*.

A campaign without a declared terminal decision drifts: every result looks
interesting, nothing is decisive, and the stopping rule becomes "when we get
bored". The charter is the artifact that makes drift visible, by writing down
in advance what decision the work exists to serve, what would count as
acceptable evidence, and what budget is on the table.

The charter is immutable. Changing one produces a new charter carrying an
append-only amendment history — because "we changed the acceptance criteria
after seeing the data" is exactly the fact a reviewer needs to see, and a
mutable object would let it disappear.

M1 defines the record and its amendment discipline. It contains no scientific
strategy: nothing here proposes actions, scores utility, or decides when a
campaign is finished.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping

from ..scientific.ir.values import ScientificValue, decode_value, encode_value
from ..scientific.results.validation import ValidationLevel
from ..scientific.serialization import require_schema, schema_string
from .errors import CharterError, ReservedNotImplemented

CHARTER_SCHEMA = schema_string("sria_campaign_charter")
DECISION_SCHEMA = schema_string("sria_terminal_decision")
CONFIDENCE_SCHEMA = schema_string("sria_confidence_requirement")
ACCEPTANCE_SCHEMA = schema_string("sria_acceptance_criterion")
AMENDMENT_SCHEMA = schema_string("sria_charter_amendment")


class CampaignType(str, Enum):
    """Why the campaign exists.

    ``DECISION`` is implemented in V0.1. ``OPEN_RESEARCH`` is reserved: an
    exploratory campaign needs a different stopping theory, and pretending the
    decision-shaped machinery fits it would produce confident nonsense.
    """

    DECISION = "decision"
    OPEN_RESEARCH = "open_research"   # reserved


IMPLEMENTED_CAMPAIGN_TYPES = frozenset({CampaignType.DECISION})


@dataclass(frozen=True)
class TerminalDecision:
    """The decision the campaign must be able to make when it ends."""

    decision_id: str
    statement: str
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        decision_id = str(self.decision_id).strip()
        statement = str(self.statement).strip()
        if not decision_id:
            raise CharterError("terminal decision requires a decision_id")
        if not statement:
            raise CharterError(
                f"terminal decision {decision_id!r} requires a statement; an "
                f"unstated decision cannot be tested against evidence"
            )
        object.__setattr__(self, "decision_id", decision_id)
        object.__setattr__(self, "statement", statement)
        object.__setattr__(self, "options", tuple(self.options))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DECISION_SCHEMA,
            "decision_id": self.decision_id,
            "statement": self.statement,
            "options": list(self.options),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TerminalDecision":
        require_schema(payload, DECISION_SCHEMA)
        return cls(
            decision_id=payload["decision_id"],
            statement=payload["statement"],
            options=tuple(payload.get("options", ())),
        )


@dataclass(frozen=True)
class ConfidenceRequirement:
    """How strong the evidence must be before the decision may be made."""

    requirement_id: str
    description: str = ""
    required_levels: tuple[ValidationLevel, ...] = ()
    threshold: float | None = None

    def __post_init__(self) -> None:
        requirement_id = str(self.requirement_id).strip()
        if not requirement_id:
            raise CharterError("confidence requirement needs a requirement_id")
        object.__setattr__(self, "requirement_id", requirement_id)
        object.__setattr__(
            self,
            "required_levels",
            tuple(ValidationLevel(level) for level in self.required_levels),
        )
        if self.threshold is not None:
            object.__setattr__(self, "threshold", float(self.threshold))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONFIDENCE_SCHEMA,
            "requirement_id": self.requirement_id,
            "description": self.description,
            "required_levels": [level.value for level in self.required_levels],
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConfidenceRequirement":
        require_schema(payload, CONFIDENCE_SCHEMA)
        return cls(
            requirement_id=payload["requirement_id"],
            description=payload.get("description", ""),
            required_levels=tuple(
                ValidationLevel(v) for v in payload.get("required_levels", ())
            ),
            threshold=payload.get("threshold"),
        )


@dataclass(frozen=True)
class AcceptanceCriterion:
    """A condition the campaign result must satisfy to be accepted."""

    criterion_id: str
    statement: str
    mandatory: bool = True

    def __post_init__(self) -> None:
        criterion_id = str(self.criterion_id).strip()
        statement = str(self.statement).strip()
        if not criterion_id or not statement:
            raise CharterError(
                "acceptance criterion requires both a criterion_id and a statement"
            )
        object.__setattr__(self, "criterion_id", criterion_id)
        object.__setattr__(self, "statement", statement)
        if not isinstance(self.mandatory, bool):
            raise CharterError("acceptance criterion 'mandatory' must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ACCEPTANCE_SCHEMA,
            "criterion_id": self.criterion_id,
            "statement": self.statement,
            "mandatory": self.mandatory,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AcceptanceCriterion":
        require_schema(payload, ACCEPTANCE_SCHEMA)
        return cls(
            criterion_id=payload["criterion_id"],
            statement=payload["statement"],
            mandatory=bool(payload.get("mandatory", True)),
        )


@dataclass(frozen=True)
class CharterAmendment:
    """One recorded change to a charter. Never removed, never rewritten."""

    amendment_id: str
    reason: str
    changed_fields: tuple[str, ...] = ()
    author: str = ""
    at: str | None = None

    def __post_init__(self) -> None:
        amendment_id = str(self.amendment_id).strip()
        reason = str(self.reason).strip()
        if not amendment_id:
            raise CharterError("amendment requires an amendment_id")
        if not reason:
            raise CharterError(
                "amendment requires a reason: an unexplained charter change is "
                "indistinguishable from moving the goalposts"
            )
        object.__setattr__(self, "amendment_id", amendment_id)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "changed_fields", tuple(self.changed_fields))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": AMENDMENT_SCHEMA,
            "amendment_id": self.amendment_id,
            "reason": self.reason,
            "changed_fields": list(self.changed_fields),
            "author": self.author,
            "at": self.at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CharterAmendment":
        require_schema(payload, AMENDMENT_SCHEMA)
        return cls(
            amendment_id=payload["amendment_id"],
            reason=payload["reason"],
            changed_fields=tuple(payload.get("changed_fields", ())),
            author=payload.get("author", ""),
            at=payload.get("at"),
        )


_AMENDABLE_FIELDS = frozenset(
    {
        "terminal_decisions",
        "utility_reference",
        "total_budget",
        "confidence_requirements",
        "acceptance_criteria",
        "metadata",
    }
)


@dataclass(frozen=True)
class CampaignCharter:
    """The governing record of one research campaign."""

    campaign_id: str
    campaign_type: CampaignType = CampaignType.DECISION
    terminal_decisions: tuple[TerminalDecision, ...] = ()
    utility_reference: str = ""
    total_budget: Mapping[str, ScientificValue] = field(default_factory=dict)
    confidence_requirements: tuple[ConfidenceRequirement, ...] = ()
    acceptance_criteria: tuple[AcceptanceCriterion, ...] = ()
    amendment_history: tuple[CharterAmendment, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        campaign_id = str(self.campaign_id).strip()
        if not campaign_id:
            raise CharterError("charter requires a campaign_id")
        object.__setattr__(self, "campaign_id", campaign_id)
        object.__setattr__(self, "campaign_type", CampaignType(self.campaign_type))
        object.__setattr__(self, "terminal_decisions", tuple(self.terminal_decisions))
        object.__setattr__(
            self, "confidence_requirements", tuple(self.confidence_requirements)
        )
        object.__setattr__(
            self, "acceptance_criteria", tuple(self.acceptance_criteria)
        )
        object.__setattr__(self, "amendment_history", tuple(self.amendment_history))
        object.__setattr__(self, "metadata", dict(self.metadata))

        budget = dict(self.total_budget)
        for name, value in budget.items():
            # encode_value rejects anything outside the core's typed union, so
            # a budget can never become an untyped number with a unit in a
            # comment somewhere.
            encode_value(value)
        object.__setattr__(self, "total_budget", budget)

        if (
            self.campaign_type is CampaignType.DECISION
            and not self.terminal_decisions
        ):
            raise CharterError(
                f"campaign {campaign_id!r} is a DECISION campaign but declares "
                f"no terminal decision; that is an open research campaign "
                f"wearing a decision label"
            )

        ids = [d.decision_id for d in self.terminal_decisions]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise CharterError(f"duplicate terminal decision ids: {sorted(duplicates)}")

    def amend(self, amendment: CharterAmendment, **changes: Any) -> "CampaignCharter":
        """Produce the amended charter, preserving the full history.

        The returned charter's history contains this charter's history as a
        prefix; there is no code path that shortens it.
        """
        if not isinstance(amendment, CharterAmendment):
            raise CharterError("amend requires a CharterAmendment")
        unknown = set(changes) - _AMENDABLE_FIELDS
        if unknown:
            raise CharterError(
                f"cannot amend {sorted(unknown)}; amendable fields are "
                f"{sorted(_AMENDABLE_FIELDS)}"
            )
        if not changes:
            raise CharterError(
                "an amendment must change something; record a note in metadata "
                "if the intent is commentary"
            )
        recorded = replace(amendment, changed_fields=tuple(sorted(changes)))
        return replace(
            self,
            amendment_history=self.amendment_history + (recorded,),
            **changes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CHARTER_SCHEMA,
            "campaign_id": self.campaign_id,
            "campaign_type": self.campaign_type.value,
            "terminal_decisions": [d.to_dict() for d in self.terminal_decisions],
            "utility_reference": self.utility_reference,
            "total_budget": {
                k: encode_value(self.total_budget[k])
                for k in sorted(self.total_budget)
            },
            "confidence_requirements": [
                c.to_dict() for c in self.confidence_requirements
            ],
            "acceptance_criteria": [c.to_dict() for c in self.acceptance_criteria],
            "amendment_history": [a.to_dict() for a in self.amendment_history],
            "metadata": dict(sorted(self.metadata.items(), key=lambda kv: kv[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CampaignCharter":
        require_schema(payload, CHARTER_SCHEMA)
        return cls(
            campaign_id=payload["campaign_id"],
            campaign_type=CampaignType(payload.get("campaign_type", "decision")),
            terminal_decisions=tuple(
                TerminalDecision.from_dict(d)
                for d in payload.get("terminal_decisions", ())
            ),
            utility_reference=payload.get("utility_reference", ""),
            total_budget={
                k: decode_value(v)
                for k, v in (payload.get("total_budget") or {}).items()
            },
            confidence_requirements=tuple(
                ConfidenceRequirement.from_dict(c)
                for c in payload.get("confidence_requirements", ())
            ),
            acceptance_criteria=tuple(
                AcceptanceCriterion.from_dict(c)
                for c in payload.get("acceptance_criteria", ())
            ),
            amendment_history=tuple(
                CharterAmendment.from_dict(a)
                for a in payload.get("amendment_history", ())
            ),
            metadata=dict(payload.get("metadata", {})),
        )


def require_implemented_campaign_type(campaign_type: CampaignType) -> None:
    """Guard for execution paths; representation of reserved types is allowed."""
    campaign_type = CampaignType(campaign_type)
    if campaign_type not in IMPLEMENTED_CAMPAIGN_TYPES:
        raise ReservedNotImplemented(
            f"campaign type {campaign_type.value!r} is reserved in SRIA V0.1"
        )
