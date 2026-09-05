"""M4F — ranking, stop proposals, protected validation budget, provenance.

Composition, not a god object. :class:`CandidateEvaluator` puts the pieces
together — generators propose, the feasibility gate filters, the utility engine
scores, this module ranks and records. There is no ``MetaBrain`` that owns the
architecture, and each part can be replaced without touching the others.

Three semantics carry most of the weight here.

**A stop proposal is not a stop.** When nothing scores positively the
recommendation is ``STOP_PROPOSAL``, which means exactly one thing: *under the
current utility model, no available candidate appears worth its cost.* It is
not "validated", not "safe to stop", not "scientifically complete" — those are
Arbiter verdicts, and :class:`RecommendationOutcome` deliberately contains no
member that could be mistaken for one.

**A stop proposal requires complete score coverage** (M4.1). ``NOT_SCORABLE``
means "we could not evaluate this action", which is a different claim from
"this action is not worth buying". If any otherwise-eligible candidate could
not be scored — missing cost, missing ``p_cf``, missing outcome expectation —
then the evidence for "nothing is worth buying" does not exist, and the
outcome is ``DECISION_INCOMPLETE`` instead. Likewise a positive winner chosen
while other candidates remain unevaluated is reported as
``PARTIAL_RECOMMENDATION``: it is the best of what could be scored, not the
best available.

**Mandatory validation cannot be starved.** A campaign may reserve budget for
its declared validation obligations. Ordinary candidates are ranked against the
*general* pool only, so a long tail of attractive exploration cannot consume
the budget that certification depends on. VoI is a good servant here and would
be a terrible master: validation obligations exist precisely because they are
not worth buying on information grounds alone.

**A ranking is scored against one world, not two** (M4.3). Before any candidate
is scored, the belief snapshot is checked against the dependency manifest that
would score it. A snapshot pinning one fitted cost model may not be scored
against another: that yields ``STATE_INCOHERENT`` and no scores at all. Deciding
on updated models is entirely legitimate — it requires a new snapshot pinned to
them, which is what distinguishes a new decision from stale-snapshot reuse.

**Determinism.** Same snapshot, same policy, same candidates → same
recommendation, with ties broken by action id rather than by dict order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from ...scientific.serialization import require_schema, schema_string
from ..provenance import DecisionProvenance
from .actions import ActionFamily, CandidateAction
from .belief_snapshot import BeliefSnapshot
from .coherence import CoherenceReport, CoherenceStatus, check_state_coherence
from .replay import (
    DependencyIdentity,
    DependencyKind,
    ExecutionDependencyManifest,
    candidate_set_digest,
)
from .terminal import TerminalObjective, TerminalObjectiveStatus
from .utility import CandidateScore, ScoreStatus, UtilityEngine

RECOMMENDATION_SCHEMA = schema_string("sria_decision_recommendation")
BUDGET_SCHEMA = schema_string("sria_campaign_budget_plan")


class RecommendationOutcome(str, Enum):
    """What the evaluator concluded.

    Note what is absent: there is no VALIDATED, SAFE_TO_STOP or
    SCIENTIFICALLY_COMPLETE. The utility engine is structurally incapable of
    emitting a certification, because certification is the Arbiter's.
    """

    #: A winner, and every eligible candidate was scored.
    RECOMMEND_ACTION = "recommend_action"
    #: A winner, but some eligible candidates could not be evaluated. The
    #: ranking is over what was scorable, not over everything available.
    PARTIAL_RECOMMENDATION = "partial_recommendation"
    #: Every eligible candidate was scored and none scored above zero.
    STOP_PROPOSAL = "stop_proposal"
    #: Some eligible candidate could not be evaluated, so neither a winner nor
    #: a stop proposal is warranted. Distinct from STOP_PROPOSAL on purpose.
    DECISION_INCOMPLETE = "decision_incomplete"
    #: Candidates existed but none could be scored honestly.
    NO_SCORABLE_CANDIDATE = "no_scorable_candidate"
    #: Formal VoI is not defined without a terminal decision and utility.
    TERMINAL_OBJECTIVE_UNAVAILABLE = "terminal_objective_unavailable"
    #: The belief snapshot and the dependencies that would score it describe
    #: different computational worlds (M4.3). Nothing was scored, because a
    #: number produced from a self-contradictory basis is worse than no number.
    STATE_INCOHERENT = "state_incoherent"
    #: At least one dependency that can move a formal score cannot be verified
    #: against the decision basis — never pinned, or a provider that cannot
    #: identify its own executable semantics (M4.4). Formal decision-theoretic
    #: scoring is unavailable. Distinct from STATE_INCOHERENT: nothing was
    #: found to contradict, because nothing could have been.
    DECISION_BASIS_UNVERIFIED = "decision_basis_unverified"


#: Which refusal a coherence verdict maps to. Kept as data so the two cannot
#: drift apart, and so a new refusing status cannot be added without deciding
#: what it means for the recommendation.
BASIS_REFUSAL_OUTCOMES: Mapping[CoherenceStatus, RecommendationOutcome] = {
    CoherenceStatus.BASIS_UNVERIFIED: RecommendationOutcome.DECISION_BASIS_UNVERIFIED,
    CoherenceStatus.STALE_SNAPSHOT: RecommendationOutcome.STATE_INCOHERENT,
    CoherenceStatus.DEPENDENCY_MISMATCH: RecommendationOutcome.STATE_INCOHERENT,
}


@dataclass(frozen=True)
class BudgetPlan:
    """Campaign budget, with validation money fenced off."""

    total_budget: float
    reserved_validation_budget: float = 0.0
    spent_general: float = 0.0
    spent_validation: float = 0.0

    def __post_init__(self) -> None:
        for label in (
            "total_budget",
            "reserved_validation_budget",
            "spent_general",
            "spent_validation",
        ):
            value = float(getattr(self, label))
            if value < 0.0:
                raise ValueError(f"{label} must be non-negative")
            object.__setattr__(self, label, value)
        if self.reserved_validation_budget > self.total_budget:
            raise ValueError(
                "reserved validation budget exceeds the total budget"
            )

    @property
    def general_pool(self) -> float:
        """What ordinary candidates may draw on — reservation excluded."""
        return max(
            0.0,
            self.total_budget - self.reserved_validation_budget - self.spent_general,
        )

    @property
    def validation_pool(self) -> float:
        return max(0.0, self.reserved_validation_budget - self.spent_validation)

    def affordable(self, cost: float, *, family: ActionFamily) -> bool:
        """VALIDATE draws on the reservation; everything else may not."""
        cost = float(cost)
        if ActionFamily(family) is ActionFamily.VALIDATE:
            return cost <= self.validation_pool + self.general_pool
        return cost <= self.general_pool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BUDGET_SCHEMA,
            "total_budget": self.total_budget,
            "reserved_validation_budget": self.reserved_validation_budget,
            "spent_general": self.spent_general,
            "spent_validation": self.spent_validation,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BudgetPlan":
        require_schema(payload, BUDGET_SCHEMA)
        return cls(
            total_budget=payload["total_budget"],
            reserved_validation_budget=payload.get("reserved_validation_budget", 0.0),
            spent_general=payload.get("spent_general", 0.0),
            spent_validation=payload.get("spent_validation", 0.0),
        )


@dataclass(frozen=True)
class DecisionRecommendation:
    """One ranking, fully explained and replayable."""

    recommendation_id: str
    outcome: RecommendationOutcome
    snapshot_digest: str
    campaign_id: str
    charter_version: str = ""
    policy_id: str = ""
    policy_version: str = ""
    engine_version: str = ""
    chosen_action_id: str = ""
    chosen_family: ActionFamily | None = None
    scores: tuple[CandidateScore, ...] = ()
    reason: str = ""
    degraded_assumptions: tuple[str, ...] = ()
    unresolved_action_ids: tuple[str, ...] = ()
    dependency_manifest: ExecutionDependencyManifest | None = None
    coherence: CoherenceReport | None = None
    human_override: bool = False
    decided_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", RecommendationOutcome(self.outcome))
        if self.chosen_family is not None:
            object.__setattr__(self, "chosen_family", ActionFamily(self.chosen_family))
        object.__setattr__(self, "scores", tuple(self.scores))
        object.__setattr__(
            self, "degraded_assumptions", tuple(self.degraded_assumptions)
        )
        if not isinstance(self.human_override, bool):
            raise ValueError("human_override must be an explicit bool")
        naming = {
            RecommendationOutcome.RECOMMEND_ACTION,
            RecommendationOutcome.PARTIAL_RECOMMENDATION,
        }
        if self.outcome in naming and not self.chosen_action_id:
            raise ValueError(f"{self.outcome.value} must name an action")
        if self.outcome not in naming and self.chosen_action_id:
            raise ValueError(
                f"outcome {self.outcome.value} must not name a chosen action"
            )
        object.__setattr__(
            self, "unresolved_action_ids", tuple(self.unresolved_action_ids)
        )
        # M4.3/M4.4: a record must not simultaneously assert an unusable basis
        # and a usable ranking. Either the basis was verified or nothing was
        # scored. The two refusals are distinct and each has its own outcome.
        if self.coherence is not None and self.coherence.is_refusal:
            if self.scores:
                raise ValueError(
                    f"{self.outcome.value} must not carry scores; nothing is "
                    f"legitimately scorable against an unverified basis"
                )
            expected = BASIS_REFUSAL_OUTCOMES[self.coherence.status]
            # TERMINAL_OBJECTIVE_UNAVAILABLE outranks a basis finding — there is
            # no formal VoI to verify a basis for — but the finding is still
            # true and stays on the record.
            if self.outcome not in (
                expected,
                RecommendationOutcome.TERMINAL_OBJECTIVE_UNAVAILABLE,
            ):
                raise ValueError(
                    f"coherence verdict {self.coherence.status.value} requires "
                    f"outcome {expected.value}, got {self.outcome.value}; a "
                    f"recommendation may not carry mutually contradictory basis "
                    f"pins and execution manifest identities"
                )
        if self.outcome in set(BASIS_REFUSAL_OUTCOMES.values()) and (
            self.coherence is None or not self.coherence.is_refusal
        ):
            raise ValueError(
                f"{self.outcome.value} must name the coherence findings it "
                f"rests on"
            )

    @property
    def is_state_coherent(self) -> bool:
        """True only when coherence was *established*, not merely unrefuted."""
        return (
            self.coherence is not None
            and self.coherence.status is CoherenceStatus.COHERENT
        )

    @property
    def rejected_action_ids(self) -> tuple[str, ...]:
        return tuple(
            s.action_id for s in self.scores if s.action_id != self.chosen_action_id
        )

    @property
    def is_certification(self) -> bool:
        """Always False. A recommendation never certifies anything."""
        return False

    @property
    def is_executable_replayable(self) -> bool:
        """Whether this record even claims to be re-executable."""
        return (
            self.dependency_manifest is not None
            and self.dependency_manifest.is_executable
        )

    @property
    def is_complete(self) -> bool:
        """Whether every eligible candidate was actually evaluated."""
        return not self.unresolved_action_ids

    @property
    def coverage_caveat(self) -> str:
        if self.is_complete:
            return ""
        return (
            f"{len(self.unresolved_action_ids)} eligible candidate(s) could not "
            f"be evaluated: {list(self.unresolved_action_ids)}"
        )

    def to_decision_provenance(self) -> DecisionProvenance:
        """Activate the M1 reservation with the real ranking."""
        return DecisionProvenance(
            decision_id=self.recommendation_id,
            belief_snapshot_ref=self.snapshot_digest,
            candidate_actions=tuple(s.action_id for s in self.scores),
            scores={
                s.action_id: s.total for s in self.scores if s.total is not None
            },
            chosen_action=self.chosen_action_id or self.outcome.value,
            reason=self.reason,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            human_override=self.human_override,
            decided_at=self.decided_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RECOMMENDATION_SCHEMA,
            "recommendation_id": self.recommendation_id,
            "outcome": self.outcome.value,
            "snapshot_digest": self.snapshot_digest,
            "campaign_id": self.campaign_id,
            "charter_version": self.charter_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "engine_version": self.engine_version,
            "chosen_action_id": self.chosen_action_id,
            "chosen_family": self.chosen_family.value if self.chosen_family else None,
            "scores": [s.to_dict() for s in self.scores],
            "reason": self.reason,
            "degraded_assumptions": list(self.degraded_assumptions),
            "unresolved_action_ids": list(self.unresolved_action_ids),
            "dependency_manifest": (
                self.dependency_manifest.to_dict()
                if self.dependency_manifest
                else None
            ),
            "coherence": self.coherence.to_dict() if self.coherence else None,
            "human_override": self.human_override,
            "decided_at": self.decided_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionRecommendation":
        require_schema(payload, RECOMMENDATION_SCHEMA)
        return cls(
            recommendation_id=payload["recommendation_id"],
            outcome=RecommendationOutcome(payload["outcome"]),
            snapshot_digest=payload["snapshot_digest"],
            campaign_id=payload["campaign_id"],
            charter_version=payload.get("charter_version", ""),
            policy_id=payload.get("policy_id", ""),
            policy_version=payload.get("policy_version", ""),
            engine_version=payload.get("engine_version", ""),
            chosen_action_id=payload.get("chosen_action_id", ""),
            chosen_family=(
                ActionFamily(payload["chosen_family"])
                if payload.get("chosen_family")
                else None
            ),
            scores=tuple(
                CandidateScore.from_dict(s) for s in payload.get("scores", ())
            ),
            reason=payload.get("reason", ""),
            degraded_assumptions=tuple(payload.get("degraded_assumptions", ())),
            unresolved_action_ids=tuple(payload.get("unresolved_action_ids", ())),
            dependency_manifest=(
                ExecutionDependencyManifest.from_dict(payload["dependency_manifest"])
                if payload.get("dependency_manifest")
                else None
            ),
            coherence=(
                CoherenceReport.from_dict(payload["coherence"])
                if payload.get("coherence")
                else None
            ),
            human_override=bool(payload.get("human_override", False)),
            decided_at=payload.get("decided_at"),
        )


class CandidateEvaluator:
    """Scores a candidate set and recommends one action, or proposes stopping."""

    def __init__(self, engine: UtilityEngine) -> None:
        self._engine = engine

    def build_manifest(
        self,
        *,
        candidates: Sequence[CandidateAction],
        snapshot: BeliefSnapshot,
        objective: TerminalObjective,
        charter_version: str = "",
    ) -> ExecutionDependencyManifest:
        """Pin every executable dependency of a ranking.

        The terminal utility is a live callable. It is identified by id and
        version, and marked unpinnable unless it exposes its own state digest —
        pickling an arbitrary function to make replay "work" would fabricate a
        guarantee nobody can honour.
        """
        dependencies = list(self._engine.dependency_identities())
        utility_digest = ""
        live_utility = getattr(objective, "_utility", None)
        if live_utility is not None and callable(
            getattr(live_utility, "state_digest", None)
        ):
            utility_digest = str(live_utility.state_digest())
        dependencies.append(
            DependencyIdentity(
                dependency_id=objective.utility_id or "terminal_utility",
                kind=DependencyKind.TERMINAL_UTILITY,
                version=objective.utility_version,
                state_digest=utility_digest,
                restorable=live_utility is not None,
                detail=(
                    "live utility callable present"
                    if live_utility is not None
                    else "utility callable was not restored; audit replay only"
                ),
            )
        )
        return ExecutionDependencyManifest(
            dependencies=tuple(dependencies),
            snapshot_digest=snapshot.digest,
            charter_version=charter_version,
            candidate_set_digest=candidate_set_digest(candidates),
        )

    def evaluate(
        self,
        *,
        recommendation_id: str,
        candidates: Sequence[CandidateAction],
        snapshot: BeliefSnapshot,
        objective: TerminalObjective,
        budget: BudgetPlan | None = None,
        decided_at: str | None = None,
        charter_version: str = "",
    ) -> DecisionRecommendation:
        policy = self._engine.policy
        manifest = self.build_manifest(
            candidates=candidates,
            snapshot=snapshot,
            objective=objective,
            charter_version=charter_version,
        )
        coherence = check_state_coherence(snapshot, manifest)
        base = dict(
            recommendation_id=recommendation_id,
            snapshot_digest=snapshot.digest,
            campaign_id=snapshot.campaign_id,
            charter_version=charter_version,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            engine_version=self._engine.engine_version,
            decided_at=decided_at,
            dependency_manifest=manifest,
            coherence=coherence,
        )

        # Without a terminal decision and utility there is no formal VoI to
        # verify a basis *for*, and that is the more specific diagnosis — so it
        # is reported ahead of any basis finding.
        if not objective.is_available:
            return DecisionRecommendation(
                outcome=RecommendationOutcome.TERMINAL_OBJECTIVE_UNAVAILABLE,
                reason=(
                    f"formal VoI requires a terminal decision and utility: "
                    f"{objective.reason}"
                ),
                **base,
            )

        # M4.3/M4.4 — before any formal scoring. A recommendation computed from
        # a basis that disagrees with, or cannot identify, the providers that
        # score it would describe a world nobody can point to. Nothing is
        # scored. Deciding on the current providers remains available; it
        # requires a new basis, which is what `pin_decision_basis` is for.
        if coherence.is_refusal:
            return DecisionRecommendation(
                outcome=BASIS_REFUSAL_OUTCOMES[coherence.status],
                reason=(
                    f"{coherence.status.value}: {coherence.detail}. No candidate "
                    f"was scored. To decide on the current dependencies, pin a "
                    f"new decision basis to them (pin_decision_basis) rather "
                    f"than reusing this one."
                ),
                **base,
            )

        scores = tuple(
            self._engine.score(candidate, snapshot, objective)
            for candidate in candidates
        )
        by_id = {c.action_id: c for c in candidates}

        # Eligibility is decided before affordability so that an unevaluated
        # candidate is never mistaken for an unaffordable one.
        rankable: list[CandidateScore] = []
        unresolved: list[str] = []
        for score in scores:
            if score.status is ScoreStatus.INFEASIBLE:
                continue          # properly excluded, not unresolved
            if score.is_unresolved:
                unresolved.append(score.action_id)
                continue
            candidate = by_id[score.action_id]
            cost = score.component("expected_cost")
            if budget is not None and cost is not None and cost.value is not None:
                if not budget.affordable(cost.value, family=candidate.family):
                    continue      # ineligible on budget, and we know it
            rankable.append(score)

        unresolved_ids = tuple(sorted(unresolved))
        common = dict(
            scores=scores,
            degraded_assumptions=self._degraded(scores),
            unresolved_action_ids=unresolved_ids,
            **base,
        )

        if not rankable:
            outcome = (
                RecommendationOutcome.DECISION_INCOMPLETE
                if unresolved_ids
                else RecommendationOutcome.NO_SCORABLE_CANDIDATE
            )
            return DecisionRecommendation(
                outcome=outcome,
                reason=(
                    "no candidate could be scored or afforded; nothing was "
                    "substituted to make one scorable"
                    + (
                        f". {len(unresolved_ids)} eligible candidate(s) remain "
                        f"unevaluated, so no stop proposal is warranted"
                        if unresolved_ids
                        else ""
                    )
                ),
                **common,
            )

        # Deterministic: score descending, then action id.
        ordered = sorted(rankable, key=lambda s: (-s.total, s.action_id))
        best = ordered[0]

        if best.total <= 0.0:
            if unresolved_ids:
                # "Nothing is worth buying" is a claim about all the options.
                # With some unevaluated, that claim is not supported.
                return DecisionRecommendation(
                    outcome=RecommendationOutcome.DECISION_INCOMPLETE,
                    reason=(
                        f"best scorable candidate {best.action_id!r} scores "
                        f"{best.total:.6g} <= 0, but {len(unresolved_ids)} "
                        f"eligible candidate(s) could not be evaluated "
                        f"({list(unresolved_ids)}). A stop proposal requires "
                        f"complete score coverage."
                    ),
                    **common,
                )
            return DecisionRecommendation(
                outcome=RecommendationOutcome.STOP_PROPOSAL,
                reason=(
                    f"every eligible candidate was scored; the best "
                    f"({best.action_id!r}) scores {best.total:.6g} <= 0 under "
                    f"policy {policy.policy_id!r}. This proposes that nothing "
                    f"is worth its cost; it does not assert the campaign is "
                    f"validated or safe to stop."
                ),
                **common,
            )

        outcome = (
            RecommendationOutcome.PARTIAL_RECOMMENDATION
            if unresolved_ids
            else RecommendationOutcome.RECOMMEND_ACTION
        )
        return DecisionRecommendation(
            outcome=outcome,
            chosen_action_id=best.action_id,
            chosen_family=best.family,
            reason=(
                f"highest scoring feasible affordable candidate "
                f"({best.total:.6g}) under policy {policy.policy_id!r}"
                + (
                    f"; ranking is partial — {list(unresolved_ids)} could not "
                    f"be evaluated"
                    if unresolved_ids
                    else ""
                )
            ),
            **common,
        )

    @staticmethod
    def _degraded(scores: Iterable[CandidateScore]) -> tuple[str, ...]:
        """Component-level degradations only.

        M4.3 also routed an unverifiable basis here as a caveat. M4.4 removed
        that: an unverifiable basis is now a refusal, and a line of prose in a
        list a caller may never read is not equivalent to formal verification.
        """
        out: set[str] = set()
        for score in scores:
            for component in score.components:
                if component.degrades_score:
                    out.add(
                        f"{score.action_id}:{component.name}="
                        f"{component.status.value}"
                    )
        return tuple(sorted(out))


def information_only_ranking(
    scores: Sequence[CandidateScore],
) -> tuple[CandidateScore, ...]:
    """Cost- and failure-unaware baseline: rank by information alone.

    Exists to make the comparison in the M4 benchmark concrete — it is what a
    naive "maximise expected information" ranker would choose, and the point of
    the benchmark is to show where that differs from the full objective and
    which one is right by the campaign's own declared utility.
    """
    def information_value(score: CandidateScore) -> float:
        gain = score.component("conditional_success_utility_gain")
        failure = score.component("expected_failure_voi")
        total = 0.0
        if gain is not None and gain.value is not None:
            total += gain.value
        if failure is not None and failure.value is not None:
            total += failure.value
        return total

    rankable = [s for s in scores if s.is_rankable]
    return tuple(sorted(rankable, key=lambda s: (-information_value(s), s.action_id)))
