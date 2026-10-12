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

Load-bearing rules:

* **A cheaper favourable result never overwrites a higher-fidelity
  contradiction.**  :meth:`FidelityLedger.standing` reads the highest-rank
  DECISIVE observation; SUPPORTS and CONTRADICTS at the same rank are a
  CONFLICT, reported and never resolved by preference.
* A REFUSED or INCONCLUSIVE observation ABOVE the deciding rank makes the
  standing UNDECIDED: a higher-fidelity model that refused the case (e.g.
  outside its applicability) or could not decide is not outvoted by a cheaper
  one.  A provider failure above is reported but decides nothing.
* SUPPORTS must carry a three-valued :class:`~.grammar.ConstraintEvaluation`
  with ``feasible is True``; an undetermined evaluation can only be
  INCONCLUSIVE.
* The evidence rung (``experimental``) decides only for observations whose
  ``evaluation_ref`` is in the caller-supplied set of ADMITTED evidence
  records; a computed or asserted "experimental" observation decides nothing.
* Ledgers are bound to one ladder and validate every observation against it.

SUPPORTED means "met the declared criteria at the highest rung that decided".
It is not validation, and promotion is a scheduling decision about cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import AbstractSet, Any, Iterable, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.objectives import ObjectiveDefinition, ObjectiveDirection
from ..scientific.units.quantity import Quantity
from .fidelity import FidelityLadder, FidelityRung
from .grammar import ConstraintEvaluation

PROMOTION_SCHEMA = "engcore.design.promotion_decision/1"
OBSERVATION_SCHEMA = "engcore.design.fidelity_observation/1"
EVIDENCE_RUNG = "experimental"


def standard_ladder(version: str = "1") -> FidelityLadder:
    return FidelityLadder("forge.standard_fidelity", version, (
        FidelityRung("analytic", 0, description="algebraic / closed-form screening"),
        FidelityRung("reduced_order", 1, description="lumped / reduced-order model"),
        FidelityRung("numerical", 2, description="moderate numerical solver"),
        FidelityRung("high_fidelity", 3, description="high-fidelity external solver"),
        FidelityRung(EVIDENCE_RUNG, 4, description="experimental / external evidence (decides only with admitted evidence)"),
    ))


class FidelityOutcome(str, Enum):
    SUPPORTS = "supports"            # met the declared criteria under this rung
    CONTRADICTS = "contradicts"      # failed the declared criteria under this rung
    INCONCLUSIVE = "inconclusive"    # ran, but UNKNOWN constraints/uncertainty prevent a decision
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
    UNDECIDED = "undecided"          # nothing decisive, or a higher rung refused / could not decide


@dataclass(frozen=True)
class FidelityObservation:
    """One candidate at one rung: outcome, provider, constraint evaluation, metrics, uncertainty status, cost, why."""

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
    constraints: ConstraintEvaluation | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", FidelityOutcome(self.outcome))
        for label in ("candidate_key", "rung_id", "provider", "reason"):
            if not str(getattr(self, label) or "").strip():
                raise InvalidScientificProblem(f"a fidelity observation states its {label}")
        if self.uncertainty not in ("unknown", "quantified", "not_applicable"):
            raise InvalidScientificProblem("observation uncertainty is 'unknown', 'quantified' or 'not_applicable'")
        if self.constraints is not None and not isinstance(self.constraints, ConstraintEvaluation):
            raise InvalidScientificProblem("constraints must be a ConstraintEvaluation")
        if self.outcome is FidelityOutcome.SUPPORTS:
            if self.constraints is None or not self.constraints.outcomes or self.constraints.feasible is not True:
                raise InvalidScientificProblem("SUPPORTS requires a constraint evaluation with at least one constraint, all SATISFIED; "
                                               "an undetermined evaluation is INCONCLUSIVE")
        if self.outcome is FidelityOutcome.CONTRADICTS and self.constraints is not None and self.constraints.feasible is not False:
            raise InvalidScientificProblem("CONTRADICTS with a constraint evaluation requires a VIOLATED constraint")
        if self.outcome in (FidelityOutcome.REFUSED, FidelityOutcome.PROVIDER_FAILED) and (self.metrics or self.constraints):
            raise InvalidScientificProblem(f"a {self.outcome.value} observation exposes no metrics or constraint results")
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
                "evaluation_ref": self.evaluation_ref, "constraints": None if self.constraints is None else self.constraints.to_dict()}


@dataclass(frozen=True)
class FidelityLedger:
    """All observations of ONE candidate on ONE ladder.  Append-only; every observation is checked against the ladder."""

    candidate_key: str
    ladder: FidelityLadder
    observations: tuple[FidelityObservation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.ladder, FidelityLadder):
            raise InvalidScientificProblem("a ledger is bound to one FidelityLadder")
        for o in self.observations:
            if o.candidate_key != self.candidate_key:
                raise InvalidScientificProblem("a ledger holds observations of one candidate only")
            o.validate_against(self.ladder)

    def add(self, observation: FidelityObservation) -> "FidelityLedger":
        return FidelityLedger(self.candidate_key, self.ladder, self.observations + (observation,))

    def _decides(self, o: FidelityObservation, admitted: AbstractSet[str]) -> bool:
        if not o.outcome.decisive:
            return False
        if o.rung_id == EVIDENCE_RUNG:
            return bool(o.evaluation_ref) and o.evaluation_ref in admitted
        return True

    def standing(self, admitted_evidence: AbstractSet[str] = frozenset()) -> tuple[Standing, int | None, str]:
        """(standing, deciding rank, why)."""
        if not self.observations:
            return Standing.UNEVALUATED, None, "no observation"
        decisive = [o for o in self.observations if self._decides(o, admitted_evidence)]
        unadmitted = [o for o in self.observations if o.outcome.decisive and not self._decides(o, admitted_evidence)]
        note_unadmitted = f"; {len(unadmitted)} evidence-rung observation(s) not backed by admitted evidence were ignored" if unadmitted else ""
        if not decisive:
            return Standing.UNDECIDED, None, "no decisive observation at any rung" + note_unadmitted
        top = max(o.rank for o in decisive)
        at_top = {o.outcome for o in decisive if o.rank == top}
        if len(at_top) > 1:
            return Standing.CONFLICTED, top, f"rung rank {top} both supports and contradicts; not resolved by preference"
        above = [o for o in self.observations if o.rank > top and o.outcome in (FidelityOutcome.REFUSED, FidelityOutcome.INCONCLUSIVE)]
        if above:
            worst = max(above, key=lambda o: o.rank)
            return Standing.UNDECIDED, top, (f"rank {top} decided, but rank {worst.rank} was {worst.outcome.value} "
                                             f"({worst.reason}); a cheaper decision does not outvote it")
        outcome = at_top.pop()
        lower_disagree = [o for o in decisive if o.rank < top and o.outcome is not outcome]
        failed_above = [o for o in self.observations if o.rank > top and o.outcome is FidelityOutcome.PROVIDER_FAILED]
        note = f" (overrides {len(lower_disagree)} lower-fidelity disagreement(s))" if lower_disagree else ""
        note += f"; {len(failed_above)} higher-rank provider failure(s) decided nothing" if failed_above else ""
        deciding = [o for o in decisive if o.rank == top]
        if any(o.uncertainty == "unknown" for o in deciding):
            note += "; uncertainty UNKNOWN"
        if outcome is FidelityOutcome.CONTRADICTS:
            return Standing.CONTRADICTED, top, f"contradicted at rank {top}{note}{note_unadmitted}"
        return Standing.SUPPORTED, top, f"supported at rank {top}{note}{note_unadmitted}; supported is not validated"

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
    """Promote at most ``budget[rung]`` candidates SUPPORTED at ``rung``, ranked by one declared objective.

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

    def decide(self, ledgers: Iterable[FidelityLedger], rung_id: str,
               admitted_evidence: AbstractSet[str] = frozenset()) -> tuple[PromotionDecision, ...]:
        nxt = self.ladder.next_after(rung_id)
        if nxt is None:
            raise InvalidScientificProblem(f"{rung_id!r} is the top rung; there is nothing to promote to")
        rank = self.ladder.rung(rung_id).rank
        eligible: list[tuple[float, str]] = []
        decisions: list[PromotionDecision] = []
        for ledger in sorted(ledgers, key=lambda x: x.candidate_key):
            if (ledger.ladder.ladder_id, ledger.ladder.version) != (self.ladder.ladder_id, self.ladder.version):
                raise InvalidScientificProblem("a ledger on another ladder cannot be promoted by this policy")
            standing, deciding, why = ledger.standing(admitted_evidence)
            here = ledger.at(rung_id)
            key = ledger.candidate_key
            refuse = lambda text: decisions.append(PromotionDecision(key, rung_id, nxt.rung_id, False, f"not promoted: {text}"))  # noqa: E731
            if standing is not Standing.SUPPORTED:
                refuse(why if standing is not Standing.UNEVALUATED else f"never observed at {rung_id!r}")
            elif not here:
                refuse(f"never observed at {rung_id!r}")
            elif deciding is None or deciding != rank:
                refuse(f"standing is decided at rank {deciding}, not at {rung_id!r}")
            else:
                support = [o for o in here if o.outcome is FidelityOutcome.SUPPORTS]
                value = support[0].metrics.get(self.objective.metric) if support else None
                if value is None:
                    refuse(f"objective metric {self.objective.metric!r} is UNKNOWN at {rung_id!r}")
                    continue
                v = value.magnitude_in(self.objective.unit)
                eligible.append((v if self.objective.direction is ObjectiveDirection.MINIMIZE else -v, key))
        n = int(self.budget.get(rung_id, 0))
        chosen = {k for _, k in sorted(eligible)[:n]}
        for _, key in sorted(eligible, key=lambda x: x[1]):
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
