"""M5K/M5.1 — stop proposals and Arbiter-owned stopping review.

M4's ``STOP_PROPOSAL`` says one thing: *under the current utility model, no
evaluated candidate appears worth its cost.* That is an economic statement about
prices, not a scientific one about sufficiency.

**What M5.1 corrected.** M5 shipped a ``StoppingReviewer`` that decided on its
own, and approved a stop whenever the declared validation obligations were
discharged and a terminal objective existed. Two things were wrong with that.
It made a generic campaign component into an independent final stopping
authority, which the frozen invariant reserves for the Arbiter. And it treated
necessary context as sufficient proof: obligations being met says the campaign
did what it promised to check, not that stopping is scientifically justified,
and non-positive VoI says the campaign has run out of *affordable* ideas, which
is a statement about prices.

**The corrected architecture.** ``STOP_APPROVED`` can now only be minted from a
genuine :class:`~engcore.sria.assurance.arbiter.ArbiterDecision` over an
explicitly registered stopping criterion:

    STOP_PROPOSAL -> campaign pause / stopping request
                  -> criterion evaluated into a CriticAssessment
                  -> Arbiter.decide(...)
                  -> STOP_APPROVED only if that decision is VALID

:class:`StopReview` structurally refuses to hold ``STOP_APPROVED`` without an
arbiter decision id, so no component in this package can approve a stop by
itself — including this one.

**Fail closed.** With no registered criterion, no evaluator for it, or an
evaluator that cannot reach a verdict, the answer is ``STOP_NOT_ASSESSED``.
Calibrated decision-risk and expected-regret certification are *not* implemented
here, because the repository has no calibrated decision-risk to certify
against; inventing the mathematics would produce a confident number nobody could
defend. UNKNOWN stays legal and is the common answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ...scientific.serialization import require_schema, schema_string
from ..assurance.arbiter import Arbiter, AssuranceVerdict
from ..assurance.assessment import CriticAssessment, CriticVerdict
from ..assurance.obligations import (
    ObligationKind,
    ObligationSet,
    ValidationObligation,
)

STOP_PROPOSAL_SCHEMA = schema_string("sria_campaign_stop_proposal")
STOP_REVIEW_SCHEMA = schema_string("sria_campaign_stop_review")
STOP_CRITERION_SCHEMA = schema_string("sria_campaign_stopping_criterion")

STOPPING_REVIEW_VERSION = "stopping_review/2"


class StopReviewOutcome(str, Enum):
    """The Arbiter's answer to a stop proposal.

    Note what is absent: no SCIENTIFICALLY_COMPLETE, no VALIDATED, no
    SAFE_TO_STOP. Approving a stop means one registered criterion was evaluated
    and the Arbiter found it satisfied — not that the science is finished.
    """

    STOP_APPROVED = "stop_approved"
    STOP_REJECTED = "stop_rejected"
    STOP_NOT_ASSESSED = "stop_not_assessed"


@dataclass(frozen=True)
class StoppingCriterion:
    """An independently declared, evaluable condition for stopping.

    Registered by the campaign charter, not inferred from the state of the
    utility engine. "Nothing scores positively" is not one of these, and neither
    is "the obligations are discharged" — a criterion has to say what would make
    stopping *right*, in terms someone can check.
    """

    criterion_id: str
    statement: str
    source: str
    evaluator_id: str = ""
    evaluator_version: str = ""

    def __post_init__(self) -> None:
        for label in ("criterion_id", "statement", "source"):
            if not str(getattr(self, label)).strip():
                raise ValueError(
                    f"a stopping criterion requires {label}; an unattributed "
                    f"criterion cannot be reviewed"
                )

    @property
    def obligation(self) -> ValidationObligation:
        """The criterion as an obligation the Arbiter can adjudicate."""
        return ValidationObligation(
            obligation_id=f"stopping:{self.criterion_id}",
            kind=ObligationKind.REQUIRED_CHECK,
            target=self.criterion_id,
            source=self.source,
            detail=self.statement,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": STOP_CRITERION_SCHEMA,
            "criterion_id": self.criterion_id,
            "statement": self.statement,
            "source": self.source,
            "evaluator_id": self.evaluator_id,
            "evaluator_version": self.evaluator_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StoppingCriterion":
        require_schema(payload, STOP_CRITERION_SCHEMA)
        return cls(
            criterion_id=payload["criterion_id"],
            statement=payload["statement"],
            source=payload["source"],
            evaluator_id=payload.get("evaluator_id", ""),
            evaluator_version=payload.get("evaluator_version", ""),
        )


@runtime_checkable
class StoppingCriterionEvaluator(Protocol):
    """Evaluates one registered criterion into a critic assessment.

    Supplied by the campaign or a domain pack. SRIA does not define what makes
    stopping right for a campaign it knows nothing about, and an evaluator that
    cannot reach a verdict must return ``NOT_ASSESSED`` rather than guess.
    """

    criterion_id: str
    critic_id: str
    critic_version: str

    def evaluate(self, context: Any, *, assessment_id: str) -> CriticAssessment:
        ...


@dataclass(frozen=True)
class StopProposal:
    """The loop asking a question. It carries no verdict of its own."""

    proposal_id: str
    campaign_id: str
    run_id: str
    iteration: int
    recommendation_id: str = ""
    snapshot_digest: str = ""
    scored_action_ids: tuple[str, ...] = ()
    economic_reason: str = ""

    def __post_init__(self) -> None:
        for label in ("proposal_id", "campaign_id", "run_id"):
            if not str(getattr(self, label)).strip():
                raise ValueError(f"stop proposal requires {label}")
        object.__setattr__(self, "scored_action_ids", tuple(self.scored_action_ids))

    @property
    def is_certification(self) -> bool:
        """Always False. A proposal is a question, not an answer."""
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": STOP_PROPOSAL_SCHEMA,
            "proposal_id": self.proposal_id,
            "campaign_id": self.campaign_id,
            "run_id": self.run_id,
            "iteration": self.iteration,
            "recommendation_id": self.recommendation_id,
            "snapshot_digest": self.snapshot_digest,
            "scored_action_ids": list(self.scored_action_ids),
            "economic_reason": self.economic_reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StopProposal":
        require_schema(payload, STOP_PROPOSAL_SCHEMA)
        return cls(
            proposal_id=payload["proposal_id"],
            campaign_id=payload["campaign_id"],
            run_id=payload["run_id"],
            iteration=int(payload.get("iteration", 0)),
            recommendation_id=payload.get("recommendation_id", ""),
            snapshot_digest=payload.get("snapshot_digest", ""),
            scored_action_ids=tuple(payload.get("scored_action_ids", ())),
            economic_reason=payload.get("economic_reason", ""),
        )


@dataclass(frozen=True)
class StopReview:
    """The response, with what was checked and who decided it."""

    review_id: str
    proposal_id: str
    outcome: StopReviewOutcome
    terminal_objective_available: bool = False
    #: The Arbiter decision this rests on. Required for STOP_APPROVED — which
    #: is what stops any component here from approving a stop by itself.
    arbiter_decision_id: str = ""
    arbiter_verdict: str = ""
    criterion_id: str = ""
    unmet_obligations: tuple[str, ...] = ()
    unresolved_assessments: tuple[str, ...] = ()
    unassessed_aspects: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    review_version: str = STOPPING_REVIEW_VERSION
    reviewed_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", StopReviewOutcome(self.outcome))
        for label in ("unmet_obligations", "unresolved_assessments",
                      "unassessed_aspects", "reasons"):
            object.__setattr__(self, label, tuple(getattr(self, label)))
        if not self.reasons:
            raise ValueError(
                "a stop review must state its reasons; an unexplained stopping "
                "verdict cannot be reviewed"
            )
        if self.outcome is StopReviewOutcome.STOP_APPROVED:
            if not str(self.arbiter_decision_id).strip():
                raise ValueError(
                    "STOP_APPROVED must name the Arbiter decision it rests on; "
                    "final stopping judgement is Arbiter-owned and no campaign "
                    "component may mint it"
                )
            if not str(self.criterion_id).strip():
                raise ValueError(
                    "STOP_APPROVED must name the registered stopping criterion "
                    "that was evaluated; non-positive VoI and discharged "
                    "obligations are context, not a criterion"
                )
            if self.unmet_obligations or self.unresolved_assessments:
                raise ValueError(
                    "stop cannot be approved while obligations or mandatory "
                    "assessments remain outstanding"
                )
            if not self.terminal_objective_available:
                raise ValueError(
                    "stop cannot be approved without a terminal decision and "
                    "utility to stop *against*"
                )

    @property
    def is_certification(self) -> bool:
        """Always False. Approving a stop is not certifying the science."""
        return False

    @property
    def approves(self) -> bool:
        return self.outcome is StopReviewOutcome.STOP_APPROVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": STOP_REVIEW_SCHEMA,
            "review_id": self.review_id,
            "proposal_id": self.proposal_id,
            "outcome": self.outcome.value,
            "terminal_objective_available": self.terminal_objective_available,
            "arbiter_decision_id": self.arbiter_decision_id,
            "arbiter_verdict": self.arbiter_verdict,
            "criterion_id": self.criterion_id,
            "unmet_obligations": list(self.unmet_obligations),
            "unresolved_assessments": list(self.unresolved_assessments),
            "unassessed_aspects": list(self.unassessed_aspects),
            "reasons": list(self.reasons),
            "review_version": self.review_version,
            "reviewed_at": self.reviewed_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StopReview":
        require_schema(payload, STOP_REVIEW_SCHEMA)
        return cls(
            review_id=payload["review_id"],
            proposal_id=payload["proposal_id"],
            outcome=StopReviewOutcome(payload["outcome"]),
            terminal_objective_available=bool(
                payload.get("terminal_objective_available", False)
            ),
            arbiter_decision_id=payload.get("arbiter_decision_id", ""),
            arbiter_verdict=payload.get("arbiter_verdict", ""),
            criterion_id=payload.get("criterion_id", ""),
            unmet_obligations=tuple(payload.get("unmet_obligations", ())),
            unresolved_assessments=tuple(payload.get("unresolved_assessments", ())),
            unassessed_aspects=tuple(payload.get("unassessed_aspects", ())),
            reasons=tuple(payload.get("reasons", ())),
            review_version=payload.get("review_version", STOPPING_REVIEW_VERSION),
            reviewed_at=payload.get("reviewed_at"),
        )


class ArbiterStoppingReview:
    """Routes a stop proposal to the Arbiter. Holds no authority of its own.

    Every path through :meth:`review` either returns a non-approving outcome or
    delegates to :meth:`Arbiter.decide`. There is no branch that constructs
    ``STOP_APPROVED`` from campaign state.
    """

    review_version = STOPPING_REVIEW_VERSION

    def __init__(self, arbiter: Arbiter) -> None:
        if not isinstance(arbiter, Arbiter):
            raise TypeError(
                "stopping review requires a real Arbiter; final stopping "
                "judgement is Arbiter-owned"
            )
        self._arbiter = arbiter

    def review(
        self,
        proposal: StopProposal,
        *,
        review_id: str,
        obligations: ObligationSet,
        obligation_state: Mapping[str, bool],
        terminal_objective_available: bool,
        criteria: Sequence[StoppingCriterion] = (),
        evaluators: Mapping[str, StoppingCriterionEvaluator] | None = None,
        evaluation_context: Any = None,
        unresolved_assessments: Sequence[str] = (),
        reviewed_at: str | None = None,
    ) -> StopReview:
        declared = tuple(o.obligation_id for o in obligations.obligations)
        unmet = tuple(
            sorted(o for o in declared if not obligation_state.get(o, False))
        )
        unassessed = tuple(sorted(o for o in declared if o not in obligation_state))
        unresolved = tuple(sorted(unresolved_assessments))
        common = dict(
            review_id=review_id,
            proposal_id=proposal.proposal_id,
            unmet_obligations=unmet,
            unresolved_assessments=unresolved,
            unassessed_aspects=unassessed,
            reviewed_at=reviewed_at,
        )

        def not_assessed(*reasons: str) -> StopReview:
            return StopReview(
                outcome=StopReviewOutcome.STOP_NOT_ASSESSED,
                terminal_objective_available=terminal_objective_available,
                reasons=tuple(reasons),
                **common,
            )

        # -- necessary context, none of it sufficient ----------------------
        if not terminal_objective_available:
            return not_assessed(
                "no terminal decision and utility are available, so there is "
                "nothing to stop against"
            )

        failed = tuple(sorted(set(unmet) - set(unassessed)))
        if failed:
            return StopReview(
                outcome=StopReviewOutcome.STOP_REJECTED,
                terminal_objective_available=True,
                reasons=(
                    f"declared validation obligations remain unsatisfied: "
                    f"{list(failed)}",
                ),
                **common,
            )
        if unassessed or unresolved:
            return not_assessed(
                *(
                    [f"obligations were never assessed: {list(unassessed)}"]
                    if unassessed
                    else []
                ),
                *(
                    [f"mandatory assessments remain unresolved: {list(unresolved)}"]
                    if unresolved
                    else []
                ),
                "a stop cannot be approved over checks the campaign never ran",
            )

        # -- the criterion, which is what actually decides -----------------
        if not criteria:
            return not_assessed(
                "no independently declared stopping criterion is registered for "
                "this campaign",
                "non-positive value of information means no candidate is worth "
                "its price, and discharged validation obligations mean the "
                "campaign did what it promised to check; neither is evidence "
                "that stopping is scientifically justified",
                "calibrated decision-risk / expected-regret certification is not "
                "implemented, and is not being approximated",
            )

        evaluators = dict(evaluators or {})
        assessments: list[CriticAssessment] = []
        evaluated: list[StoppingCriterion] = []
        missing: list[str] = []
        for criterion in criteria:
            evaluator = evaluators.get(criterion.criterion_id)
            if evaluator is None:
                missing.append(criterion.criterion_id)
                continue
            assessment = evaluator.evaluate(
                evaluation_context,
                assessment_id=f"{review_id}-{criterion.criterion_id}",
            )
            assessments.append(assessment)
            evaluated.append(criterion)

        if missing:
            return not_assessed(
                f"registered stopping criteria have no evaluator: {missing}",
                "a criterion nobody can evaluate cannot support approval",
            )
        if any(
            a.verdict in (CriticVerdict.NOT_ASSESSED, CriticVerdict.INCONCLUSIVE)
            for a in assessments
        ):
            return not_assessed(
                "the stopping criterion could not be evaluated to a verdict",
                "UNKNOWN is the honest answer; the campaign is not approving a "
                "stop it did not establish",
            )

        # -- delegate. This class mints no verdict of its own. -------------
        criterion_obligations = ObligationSet(
            campaign_id=proposal.campaign_id,
            obligations=tuple(c.obligation for c in evaluated),
        )
        decision = self._arbiter.decide(
            decision_id=f"{review_id}-arbiter",
            subject_ref=proposal.proposal_id,
            assessments=tuple(assessments),
            obligations=criterion_obligations,
            decided_at=reviewed_at,
        )
        criterion_id = ",".join(c.criterion_id for c in evaluated)

        if decision.verdict is AssuranceVerdict.VALID:
            return StopReview(
                outcome=StopReviewOutcome.STOP_APPROVED,
                terminal_objective_available=True,
                arbiter_decision_id=decision.decision_id,
                arbiter_verdict=decision.verdict.value,
                criterion_id=criterion_id,
                reasons=(
                    f"the Arbiter found the registered stopping criterion "
                    f"{criterion_id!r} satisfied",
                    "this approves stopping against that declared criterion; it "
                    "is not a general certification of scientific completeness",
                ),
                **common,
            )
        if decision.verdict is AssuranceVerdict.INVALID:
            return StopReview(
                outcome=StopReviewOutcome.STOP_REJECTED,
                terminal_objective_available=True,
                arbiter_decision_id=decision.decision_id,
                arbiter_verdict=decision.verdict.value,
                criterion_id=criterion_id,
                reasons=(
                    f"the Arbiter found the stopping criterion {criterion_id!r} "
                    f"not satisfied",
                ),
                **common,
            )
        return StopReview(
            outcome=StopReviewOutcome.STOP_NOT_ASSESSED,
            terminal_objective_available=True,
            arbiter_decision_id=decision.decision_id,
            arbiter_verdict=decision.verdict.value,
            criterion_id=criterion_id,
            reasons=(
                f"the Arbiter returned {decision.verdict.value} on the stopping "
                f"criterion {criterion_id!r}",
                "UNKNOWN remains a legal and honest answer",
            ),
            **common,
        )
