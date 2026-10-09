"""Multi-fidelity scheduling: observations per rung, a monotone standing, and explicit promotion decisions.

Five generic fidelity classes are offered by :func:`standard_ladder` (an
existing :class:`~.fidelity.FidelityLadder`, nothing new):

====  ========================  =========================================
rank  rung                      meaning
====  ========================  =========================================
0     ``analytic``              algebraic / closed-form screening
1     ``reduced_order``         lumped / reduced-order models
2     ``numerical``             moderate numerical solver
3     ``high_fidelity``         high-fidelity external solver
4     ``experimental``          experimental / external evidence
====  ========================  =========================================

The load-bearing rule: **a cheaper favourable result never overwrites a
higher-fidelity contradiction.**  :meth:`FidelityLedger.standing` reads the
highest-rank DECISIVE observation; a later rank-0 SUPPORTS cannot undo a
rank-3 CONTRADICTS, and SUPPORTS and CONTRADICTS at the same rank are a
CONFLICT that is reported, not resolved.

A SUPPORTS observation means "the candidate met the declared criteria under
this rung's model and provider".  It is not validation, and promotion is a
scheduling decision about where to spend cost, not a scientific verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.objectives import ObjectiveDefinition, ObjectiveDirection
from ..scientific.units.quantity import Quantity
from .fidelity import FidelityLadder, FidelityRung

PROMOTION_SCHEMA = "engcore.design.promotion_decision/1"
OBSERVATION_SCHEMA = "engcore.design.fidelity_observation/1"


def standard_ladder(version: str = "1") -> FidelityLadder:
    return FidelityLadder("forge.standard_fidelity", version, (
        FidelityRung("analytic", 0, description="algebraic / closed-form screening"),
        FidelityRung("reduced_order", 1, description="lumped / reduced-order model"),
        FidelityRung("numerical", 2, description="moderate numerical solver"),
        FidelityRung("high_fidelity", 3, description="high-fidelity external solver"),
        FidelityRung("experimental", 4, description="experimental / external evidence"),
    ))


class FidelityOutcome(str, Enum):
    SUPPORTS = "supports"            # met the declared criteria under this rung
    CONTRADICTS = "contradicts"      # failed the declared criteria under this rung
    INCONCLUSIVE = "inconclusive"    # ran, but uncertainty/UNKNOWN prevents a decision
    REFUSED = "refused"              # inputs/applicability refused before execution
    PROVIDER_FAILED = "provider_failed"  # the provider was unavailable or failed

    @property
    def decisive(self) -> bool:
        return self in (FidelityOutcome.SUPPORTS, FidelityOutcome.CONTRADICTS)


class Standing(str, Enum):
    UNEVALUATED = "unevaluated"
    SUPPORTED = "supported"          # highest decisive rung supports (NOT validated)
    CONTRADICTED = "contradicted"
    CONFLICTED = "conflicted"        # same-rank disagreement; never resolved silently
    UNDECIDED = "undecided"          # only inconclusive / refused / failed observations


@dataclass(frozen=True)
class FidelityObservation:
    """One candidate at one rung: outcome, provider, cost, uncertainty status, metrics and the reason."""

    candidate_key: str
    rung_id: str
    rank: int
    outcome: FidelityOutcome
    provider: str
    reason: str
    metrics: Mapping[str, Quantity] = field(default_factory=dict)
    cost_s: float | None = None
    uncertainty: str = "unknown"
    evaluation_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", FidelityOutcome(self.outcome))
        for label in ("candidate_key", "rung_id", "provider", "reason"):
            if not str(getattr(self, label) or "").strip():
                raise InvalidScientificProblem(f"a fidelity observation states its {label}")
        if self.uncertainty not in ("unknown", "quantified", "not_applicable"):
            raise InvalidScientificProblem("observation uncertainty is 'unknown', 'quantified' or 'not_applicable'")
        if self.outcome.decisive and self.uncertainty == "unknown" and self.rank >= 2:
            # A numerical or higher rung that decided with UNKNOWN uncertainty must say so in its reason.
            if "uncertainty" not in self.reason.lower():
                raise InvalidScientificProblem("a decisive rung>=2 observation with UNKNOWN uncertainty must state that in its reason")
        if not self.outcome.decisive and self.metrics and self.outcome is not FidelityOutcome.INCONCLUSIVE:
            raise InvalidScientificProblem(f"a {self.outcome.value} observation exposes no metrics")
        if self.cost_s is not None and not float(self.cost_s) >= 0:
            raise InvalidScientificProblem("cost must be a non-negative number of seconds")
        object.__setattr__(self, "metrics", dict(sorted(self.metrics.items())))

    def validate_against(self, ladder: FidelityLadder) -> "FidelityObservation":
        if ladder.rung(self.rung_id).rank != self.rank:
            raise InvalidScientificProblem(f"observation rank {self.rank} does not match rung {self.rung_id!r}")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"schema": OBSERVATION_SCHEMA, "candidate_key": self.candidate_key, "rung_id": self.rung_id, "rank": self.rank,
                "outcome": self.outcome.value, "provider": self.provider, "reason": self.reason,
                "metrics": {k: v.to_dict() for k, v in self.metrics.items()}, "cost_s": self.cost_s, "uncertainty": self.uncertainty,
                "evaluation_ref": self.evaluation_ref}


@dataclass(frozen=True)
class FidelityLedger:
    """All observations of ONE candidate.  Append-only; standing is monotone in rank."""

    candidate_key: str
    observations: tuple[FidelityObservation, ...] = ()

    def __post_init__(self) -> None:
        if any(o.candidate_key != self.candidate_key for o in self.observations):
            raise InvalidScientificProblem("a ledger holds observations of one candidate only")

    def add(self, observation: FidelityObservation) -> "FidelityLedger":
        return FidelityLedger(self.candidate_key, self.observations + (observation,))

    def standing(self) -> tuple[Standing, int | None, str]:
        """(standing, deciding rank, why).  The highest decisive rank rules; a same-rank split is CONFLICTED."""
        if not self.observations:
            return Standing.UNEVALUATED, None, "no observation"
        decisive = [o for o in self.observations if o.outcome.decisive]
        if not decisive:
            return Standing.UNDECIDED, None, "no decisive observation at any rung"
        top = max(o.rank for o in decisive)
        at_top = {o.outcome for o in decisive if o.rank == top}
        if len(at_top) > 1:
            return Standing.CONFLICTED, top, f"rung rank {top} both supports and contradicts; not resolved by preference"
        outcome = at_top.pop()
        lower_disagree = [o for o in decisive if o.rank < top and o.outcome is not outcome]
        note = f" (overrides {len(lower_disagree)} lower-fidelity disagreement(s))" if lower_disagree else ""
        if outcome is FidelityOutcome.CONTRADICTS:
            return Standing.CONTRADICTED, top, f"contradicted at rank {top}{note}"
        return Standing.SUPPORTED, top, f"supported at rank {top}{note}; supported is not validated"

    def highest_rank(self) -> int | None:
        return max((o.rank for o in self.observations), default=None)

    def at(self, rung_id: str) -> tuple[FidelityObservation, ...]:
        return tuple(o for o in self.observations if o.rung_id == rung_id)


@dataclass(frozen=True)
class PromotionDecision:
    candidate_key: str
    from_rung: str
    to_rung: str
    promoted: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROMOTION_SCHEMA, "candidate_key": self.candidate_key, "from_rung": self.from_rung, "to_rung": self.to_rung,
                "promoted": self.promoted, "reason": self.reason}


@dataclass(frozen=True)
class PromotionPolicy:
    """Promote at most ``budget[rung]`` candidates that are SUPPORTED at ``rung``, ranked by one declared objective.

    Ties break by candidate key (deterministic).  Every candidate considered
    receives a decision with its reason, promoted or not.
    """

    ladder: FidelityLadder
    objective: ObjectiveDefinition
    budget: Mapping[str, int]

    def __post_init__(self) -> None:
        for rung, n in self.budget.items():
            self.ladder.rung(rung)
            if isinstance(n, bool) or not isinstance(n, int) or n < 0:
                raise InvalidScientificProblem(f"promotion budget for {rung!r} must be a non-negative integer")

    def decide(self, ledgers: Iterable[FidelityLedger], rung_id: str) -> tuple[PromotionDecision, ...]:
        nxt = self.ladder.next_after(rung_id)
        if nxt is None:
            raise InvalidScientificProblem(f"{rung_id!r} is the top rung; there is nothing to promote to")
        rank = self.ladder.rung(rung_id).rank
        eligible: list[tuple[float, str]] = []
        decisions: list[PromotionDecision] = []
        for ledger in sorted(ledgers, key=lambda x: x.candidate_key):
            standing, deciding, why = ledger.standing()
            here = [o for o in ledger.at(rung_id)]
            key = ledger.candidate_key
            if standing is Standing.CONTRADICTED:
                decisions.append(PromotionDecision(key, rung_id, nxt.rung_id, False, f"not promoted: {why}"))
            elif standing is Standing.CONFLICTED:
                decisions.append(PromotionDecision(key, rung_id, nxt.rung_id, False, f"not promoted: {why}"))
            elif not here:
                decisions.append(PromotionDecision(key, rung_id, nxt.rung_id, False, f"not promoted: never observed at {rung_id!r}"))
            elif not any(o.outcome is FidelityOutcome.SUPPORTS for o in here) or deciding is None or deciding < rank:
                outcomes = sorted({o.outcome.value for o in here})
                decisions.append(PromotionDecision(key, rung_id, nxt.rung_id, False, f"not promoted: {outcomes} at {rung_id!r} is not support"))
            elif deciding > rank:
                decisions.append(PromotionDecision(key, rung_id, nxt.rung_id, False, f"not promoted: already decided at rank {deciding}"))
            else:
                value = next(o.metrics.get(self.objective.metric) for o in here if o.outcome is FidelityOutcome.SUPPORTS)
                if value is None:
                    decisions.append(PromotionDecision(key, rung_id, nxt.rung_id, False,
                                                       f"not promoted: objective metric {self.objective.metric!r} is UNKNOWN at {rung_id!r}"))
                    continue
                v = value.magnitude_in(self.objective.unit)
                eligible.append((v if self.objective.direction is ObjectiveDirection.MINIMIZE else -v, key))
        n = int(self.budget.get(rung_id, 0))
        chosen = {k for _, k in sorted(eligible)[:n]}
        for score, key in sorted(eligible, key=lambda x: x[1]):
            if key in chosen:
                decisions.append(PromotionDecision(key, rung_id, nxt.rung_id, True,
                                                   f"promoted: within budget {n} by {self.objective.name} (a scheduling choice, not a verdict)"))
            else:
                decisions.append(PromotionDecision(key, rung_id, nxt.rung_id, False, f"not promoted: outside budget {n} by {self.objective.name}"))
        return tuple(sorted(decisions, key=lambda d: d.candidate_key))

    def to_dict(self) -> dict[str, Any]:
        return {"ladder": [self.ladder.ladder_id, self.ladder.version], "objective": self.objective.to_dict(), "budget": dict(sorted(self.budget.items()))}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())
