"""M4A — the terminal objective, and the refusal to proceed without one.

Formal value-of-information is defined only relative to a decision. "How much
is this experiment worth?" has no answer until someone says what the campaign
is ultimately deciding and how outcomes are valued. Without that, any number a
VoI engine produces is a preference dressed as arithmetic.

So this module's most important behaviour is a refusal:
:func:`resolve_terminal_objective` returns
``TerminalObjectiveStatus.TERMINAL_OBJECTIVE_UNAVAILABLE`` when the charter
declares no terminal decision or no utility is supplied, and the utility engine
will not score candidates in that state.

The decision set comes from the frozen M1
:class:`~engcore.sria.charter.CampaignCharter`. There is no second objective
system: a campaign that has already declared what it is deciding does not get
asked again in different words.

Utility *semantics* belong to the campaign or domain — SRIA owns only the
protocol. A universal scientific utility function would be wrong for every
campaign that has an actual objective.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable

from ...scientific.serialization import require_schema, schema_string
from ..charter import CampaignCharter, CampaignType, TerminalDecision

TERMINAL_OBJECTIVE_SCHEMA = schema_string("sria_terminal_objective")


class TerminalObjectiveStatus(str, Enum):
    """Whether formal VoI is admissible at all."""

    AVAILABLE = "available"
    #: Declared, named, and returned rather than raised — "we cannot compute
    #: this" is a legitimate answer that the caller must be able to record.
    TERMINAL_OBJECTIVE_UNAVAILABLE = "terminal_objective_unavailable"


@runtime_checkable
class TerminalUtility(Protocol):
    """Campaign/domain-supplied utility. SRIA never defines the semantics.

    ``expected_utility`` scores the current belief; ``expected_utility_after``
    scores a hypothetical post-observation belief. Both return plain floats in
    the campaign's own utility units — comparing them across campaigns is
    meaningless and nothing here tries.
    """

    utility_id: str
    utility_version: str

    def expected_utility(self, snapshot: Any, decision_id: str) -> float:
        ...

    def expected_utility_after(
        self, snapshot: Any, decision_id: str, outcome: Mapping[str, Any]
    ) -> float:
        ...


@dataclass(frozen=True)
class TerminalObjective:
    """A resolved decision + utility pair, or an explicit unavailability."""

    status: TerminalObjectiveStatus
    campaign_id: str = ""
    decision: TerminalDecision | None = None
    utility_id: str = ""
    utility_version: str = ""
    reason: str = ""
    _utility: TerminalUtility | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", TerminalObjectiveStatus(self.status))
        if self.status is TerminalObjectiveStatus.AVAILABLE:
            if self.decision is None or self._utility is None:
                raise ValueError(
                    "an AVAILABLE terminal objective needs both a decision and "
                    "a utility; anything less cannot support formal VoI"
                )

    @property
    def is_available(self) -> bool:
        return self.status is TerminalObjectiveStatus.AVAILABLE

    @property
    def utility(self) -> TerminalUtility:
        if self._utility is None:
            raise ValueError(
                f"terminal utility is unavailable: {self.reason or self.status.value}"
            )
        return self._utility

    def current_expected_utility(self, snapshot: Any) -> float:
        return self.utility.expected_utility(snapshot, self.decision.decision_id)

    def expected_utility_after(
        self, snapshot: Any, outcome: Mapping[str, Any]
    ) -> float:
        return self.utility.expected_utility_after(
            snapshot, self.decision.decision_id, outcome
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TERMINAL_OBJECTIVE_SCHEMA,
            "status": self.status.value,
            "campaign_id": self.campaign_id,
            "decision_id": self.decision.decision_id if self.decision else "",
            "utility_id": self.utility_id,
            "utility_version": self.utility_version,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TerminalObjective":
        """Rebuilds the *record*, not the callable.

        A serialized objective can be audited but not re-executed; the utility
        implementation belongs to the campaign, not to this record.
        """
        require_schema(payload, TERMINAL_OBJECTIVE_SCHEMA)
        status = TerminalObjectiveStatus(payload["status"])
        if status is TerminalObjectiveStatus.AVAILABLE:
            status = TerminalObjectiveStatus.TERMINAL_OBJECTIVE_UNAVAILABLE
            reason = "reloaded record: the utility callable is not serializable"
        else:
            reason = payload.get("reason", "")
        return cls(
            status=status,
            campaign_id=payload.get("campaign_id", ""),
            utility_id=payload.get("utility_id", ""),
            utility_version=payload.get("utility_version", ""),
            reason=reason,
        )


def resolve_terminal_objective(
    charter: CampaignCharter,
    utility: TerminalUtility | None = None,
    *,
    decision_id: str = "",
) -> TerminalObjective:
    """Resolve the objective, or say precisely why it is unavailable."""

    def unavailable(reason: str) -> TerminalObjective:
        return TerminalObjective(
            status=TerminalObjectiveStatus.TERMINAL_OBJECTIVE_UNAVAILABLE,
            campaign_id=charter.campaign_id,
            reason=reason,
        )

    if charter.campaign_type is not CampaignType.DECISION:
        # OPEN_RESEARCH remains reserved. Faking formal VoI for open-ended
        # discovery would be the most damaging thing this module could do.
        return unavailable(
            f"campaign type {charter.campaign_type.value!r} has no terminal "
            f"decision; formal VoI is defined only for DECISION campaigns"
        )
    if not charter.terminal_decisions:
        return unavailable("charter declares no terminal decision")

    if decision_id:
        matches = [
            d for d in charter.terminal_decisions if d.decision_id == decision_id
        ]
        if not matches:
            return unavailable(f"charter has no decision {decision_id!r}")
        decision = matches[0]
    elif len(charter.terminal_decisions) == 1:
        decision = charter.terminal_decisions[0]
    else:
        return unavailable(
            "charter declares multiple terminal decisions; the campaign must "
            "name which one this ranking serves"
        )

    if utility is None:
        return unavailable(
            "no terminal utility supplied; a decision without a utility cannot "
            "value an outcome"
        )
    for attribute in ("expected_utility", "expected_utility_after"):
        if not callable(getattr(utility, attribute, None)):
            return unavailable(
                f"supplied utility does not implement {attribute}()"
            )

    return TerminalObjective(
        status=TerminalObjectiveStatus.AVAILABLE,
        campaign_id=charter.campaign_id,
        decision=decision,
        utility_id=str(getattr(utility, "utility_id", "")),
        utility_version=str(getattr(utility, "utility_version", "")),
        _utility=utility,
    )
