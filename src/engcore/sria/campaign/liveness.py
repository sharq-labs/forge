"""M5 — validation liveness.

M4 fences a reserved validation budget so that a long tail of attractive
exploration cannot spend the money certification depends on. It does not ensure
the validation ever gets *scheduled*: a campaign could keep picking the highest
scoring ordinary action every iteration, never spend the reservation, and run
out of iterations with its mandatory obligations untouched. The money was
protected; the obligation still went unmet. That is the specific gap M5 closes.

The rule implemented here is narrow on purpose:

    If a mandatory validation obligation is unsatisfied, and deferring the
    cheapest feasible action that would satisfy it for one more iteration would
    make it unreachable within the remaining reserved resources or the
    remaining iterations, then that validation action is scheduled now — even
    if an ordinary action scores higher.

Everything in that sentence is derived from things the campaign already
declared: the charter's obligations, the reserved validation budget, the
remaining budget, and the declared iteration ceiling. There is no universal
"validate every N steps", no invented scientific deadline, and no notion that
validation is intrinsically more valuable than information. The override fires
only when waiting would destroy the *option*, which is a fact about
reachability rather than a preference about science.

When it fires, the ruling records exactly why — which obligation, which action,
what the remaining pools were, and what would have been chosen instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from ...scientific.serialization import require_schema, schema_string
from ..decision.actions import ActionFamily, CandidateAction
from .budget import BudgetLedger

LIVENESS_SCHEMA = schema_string("sria_validation_liveness_ruling")

LIVENESS_POLICY_ID = "sria.validation_liveness.reachability"
LIVENESS_POLICY_VERSION = "1"


class LivenessStatus(str, Enum):
    """Whether validation scheduling had to intervene."""

    #: No mandatory obligation is outstanding, or none is addressable now.
    NOT_REQUIRED = "not_required"
    #: Outstanding, but still reachable if deferred one more iteration.
    REACHABLE_IF_DEFERRED = "reachable_if_deferred"
    #: Deferring would make it unreachable. Validation is scheduled now.
    SCHEDULED_TO_PRESERVE_REACHABILITY = "scheduled_to_preserve_reachability"
    #: Already unreachable — recorded honestly rather than silently dropped.
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class ValidationTarget:
    """One outstanding mandatory obligation and what would discharge it."""

    obligation_id: str
    action_id: str
    cost: float | None = None
    detail: str = ""

    @property
    def is_costed(self) -> bool:
        return self.cost is not None


@dataclass(frozen=True)
class LivenessRuling:
    """What the policy decided, and the arithmetic it decided on."""

    status: LivenessStatus
    policy_id: str = LIVENESS_POLICY_ID
    policy_version: str = LIVENESS_POLICY_VERSION
    forced_action_id: str = ""
    obligation_id: str = ""
    displaced_action_id: str = ""
    remaining_iterations: int = 0
    validation_pool: float = 0.0
    general_pool: float = 0.0
    validation_cost: float | None = None
    competing_cost: float | None = None
    unsatisfied_obligations: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", LivenessStatus(self.status))
        object.__setattr__(
            self, "unsatisfied_obligations", tuple(self.unsatisfied_obligations)
        )
        if self.overrides and not self.forced_action_id:
            raise ValueError(
                "a liveness override must name the action it schedules"
            )
        if self.overrides and not self.reason.strip():
            raise ValueError(
                "a liveness override must record why; an unexplained override "
                "of a higher-scoring action cannot be reviewed"
            )

    @property
    def overrides(self) -> bool:
        return self.status is LivenessStatus.SCHEDULED_TO_PRESERVE_REACHABILITY

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LIVENESS_SCHEMA,
            "status": self.status.value,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "forced_action_id": self.forced_action_id,
            "obligation_id": self.obligation_id,
            "displaced_action_id": self.displaced_action_id,
            "remaining_iterations": self.remaining_iterations,
            "validation_pool": self.validation_pool,
            "general_pool": self.general_pool,
            "validation_cost": self.validation_cost,
            "competing_cost": self.competing_cost,
            "unsatisfied_obligations": list(self.unsatisfied_obligations),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LivenessRuling":
        require_schema(payload, LIVENESS_SCHEMA)
        return cls(
            status=LivenessStatus(payload["status"]),
            policy_id=payload.get("policy_id", LIVENESS_POLICY_ID),
            policy_version=payload.get("policy_version", LIVENESS_POLICY_VERSION),
            forced_action_id=payload.get("forced_action_id", ""),
            obligation_id=payload.get("obligation_id", ""),
            displaced_action_id=payload.get("displaced_action_id", ""),
            remaining_iterations=int(payload.get("remaining_iterations", 0)),
            validation_pool=float(payload.get("validation_pool", 0.0)),
            general_pool=float(payload.get("general_pool", 0.0)),
            validation_cost=payload.get("validation_cost"),
            competing_cost=payload.get("competing_cost"),
            unsatisfied_obligations=tuple(payload.get("unsatisfied_obligations", ())),
            reason=payload.get("reason", ""),
        )


def validation_targets(
    candidates: Sequence[CandidateAction],
    *,
    unsatisfied_obligation_ids: Sequence[str],
    costs: Mapping[str, float | None],
) -> tuple[ValidationTarget, ...]:
    """Match VALIDATE candidates to the obligations they would discharge.

    The link is the ``obligation_id`` the ValidateGenerator stamps into the
    action's metadata — the campaign's own declaration, not an inference.
    """
    outstanding = set(unsatisfied_obligation_ids)
    out: list[ValidationTarget] = []
    for candidate in candidates:
        if candidate.family is not ActionFamily.VALIDATE:
            continue
        for member in candidate.members:
            obligation_id = str(member.action.metadata.get("obligation_id", ""))
            if obligation_id and obligation_id in outstanding:
                out.append(
                    ValidationTarget(
                        obligation_id=obligation_id,
                        action_id=candidate.action_id,
                        cost=costs.get(candidate.action_id),
                        detail=member.proposal.rationale,
                    )
                )
                break
    return tuple(out)


@dataclass(frozen=True)
class ValidationLivenessPolicy:
    """Deterministic reachability check. Declared, versioned, auditable."""

    policy_id: str = LIVENESS_POLICY_ID
    policy_version: str = LIVENESS_POLICY_VERSION
    #: Iterations that must remain for a deferred validation to still run.
    #: One means "there must be at least one iteration left after this one".
    required_slack_iterations: int = 1

    def assess(
        self,
        *,
        targets: Sequence[ValidationTarget],
        budget: BudgetLedger,
        remaining_iterations: int,
        competing_action_id: str = "",
        competing_cost: float | None = None,
        unsatisfied_obligation_ids: Sequence[str] = (),
    ) -> LivenessRuling:
        """Decide whether validation must be scheduled this iteration."""
        common = dict(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            remaining_iterations=remaining_iterations,
            validation_pool=budget.validation_pool,
            general_pool=budget.general_pool,
            competing_cost=competing_cost,
            displaced_action_id=competing_action_id,
            unsatisfied_obligations=tuple(unsatisfied_obligation_ids),
        )

        costed = [t for t in targets if t.is_costed]
        if not costed:
            return LivenessRuling(
                status=LivenessStatus.NOT_REQUIRED,
                reason=(
                    "no costed validation candidate addresses an outstanding "
                    "mandatory obligation this iteration"
                ),
                **common,
            )

        # Cheapest first: the campaign should preserve the option it can most
        # easily afford, not the one that happens to be listed first.
        cheapest = min(costed, key=lambda t: (t.cost, t.action_id))
        affordable_now = budget.affordable(
            cheapest.cost, family=ActionFamily.VALIDATE
        )
        if not affordable_now:
            return LivenessRuling(
                status=LivenessStatus.UNREACHABLE,
                obligation_id=cheapest.obligation_id,
                validation_cost=cheapest.cost,
                reason=(
                    f"obligation {cheapest.obligation_id!r} needs "
                    f"{cheapest.cost} but only {budget.validation_pool} reserved "
                    f"+ {budget.general_pool} general remains; it is already "
                    f"unreachable and the campaign is not pretending otherwise"
                ),
                **common,
            )

        # Would deferring one more iteration keep it reachable?
        iterations_after_this = remaining_iterations - 1
        if iterations_after_this < self.required_slack_iterations:
            return LivenessRuling(
                status=LivenessStatus.SCHEDULED_TO_PRESERVE_REACHABILITY,
                forced_action_id=cheapest.action_id,
                obligation_id=cheapest.obligation_id,
                validation_cost=cheapest.cost,
                reason=(
                    f"mandatory obligation {cheapest.obligation_id!r} is "
                    f"unsatisfied and only {remaining_iterations} iteration(s) "
                    f"remain; deferring {cheapest.action_id!r} would leave no "
                    f"iteration in which to run it"
                ),
                **common,
            )

        # Spending the competing action's cost comes out of the general pool.
        # Validation may draw on the reservation plus whatever general money is
        # left, so this is the pool it would face next iteration.
        spend = float(competing_cost or 0.0)
        general_after = max(0.0, budget.general_pool - spend)
        reachable_after = cheapest.cost <= budget.validation_pool + general_after + 1e-12
        if reachable_after:
            return LivenessRuling(
                status=LivenessStatus.REACHABLE_IF_DEFERRED,
                obligation_id=cheapest.obligation_id,
                validation_cost=cheapest.cost,
                reason=(
                    f"obligation {cheapest.obligation_id!r} remains reachable "
                    f"after spending {spend} on {competing_action_id!r}"
                ),
                **common,
            )

        return LivenessRuling(
            status=LivenessStatus.SCHEDULED_TO_PRESERVE_REACHABILITY,
            forced_action_id=cheapest.action_id,
            obligation_id=cheapest.obligation_id,
            validation_cost=cheapest.cost,
            reason=(
                f"mandatory obligation {cheapest.obligation_id!r} costs "
                f"{cheapest.cost}; spending {spend} on {competing_action_id!r} "
                f"would leave {budget.validation_pool} reserved + "
                f"{general_after} general, making it unreachable. Validation is "
                f"scheduled now to preserve the declared obligation, not because "
                f"it scored higher"
            ),
            **common,
        )
