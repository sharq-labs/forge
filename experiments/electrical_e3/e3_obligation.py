"""E3 decision path: the adequacy obligation, and what it is allowed to do.

DECISION-PATH MODULE. It must never import a grader truth — E3's or E2's — and
a test walks the import graph transitively through both packages.

WHAT AN OBLIGATION IS, AND WHAT IT IS NOT
------------------------------------------
An obligation is a preregistered statement that a particular scientific test
must be *performed* before a particular claim may be certified. Three things
follow, and E3 encodes all three rather than relying on anyone remembering:

**It is not evidence.** Declaring the obligation says nothing about the model.
Before the required probes exist the adequacy scope is NOT_ESTABLISHED, which
is a different thing from "provisionally acceptable".

**It is not a utility.** The obligation never touches the decision basis. It
does not add an information term, a validation reward, a priority weight or a
prior. Parameter EVSI for an adequacy probe is whatever E2's unmodified
quadrature says it is — at the floor — and this module cannot change that
because it does not import anything that computes it.

**Satisfying it is not passing it.** :class:`ObligationLedger` reports COMPLETED
when the required evidence has been acquired validly and predictively
committed. What that evidence says about the model is a separate question
answered by a separate object. A campaign that obtained its required evidence
and was refuted by it has discharged its obligation *completely* and must still
be refused certification.

HOW IT REACHES THE CAMPAIGN
---------------------------
Through the frozen M5.1 seam, not around it. :class:`AdequacyStoppingEvaluator`
is a real ``StoppingCriterionEvaluator``: the campaign registers the obligation
as a :class:`StoppingCriterion`, ``ArbiterStoppingReview`` asks this evaluator
for a ``CriticAssessment``, and the **Arbiter** decides. Nothing here mints a
stopping verdict, and the mapping onto M3.1's verdict algebra is deliberate:

    obligation OUTSTANDING          FAIL, assurance-blocking  -> INCONCLUSIVE
                                                              -> STOP_NOT_ASSESSED
    obligation COMPLETED, adequate  PASS                      -> VALID
                                                              -> STOP_APPROVED
    obligation COMPLETED, refuted   FAIL, evidence-invalidating-> INVALID
                                                              -> STOP_REJECTED
    required probe invalid          NOT_ASSESSED              -> STOP_NOT_ASSESSED

The middle two are the interesting pair. "We have not established that we may
stop" and "stopping here would be wrong" are different claims licensing
different actions, and M3.1 already draws that line — an outstanding obligation
blocks certification without refuting anything, while a model whose
precommitted predictions were refuted by valid evidence makes stopping
affirmatively wrong. E3 does not invent that distinction; it uses it.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from src.engcore.sria.assurance.assessment import (
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    Finding,
    FindingImpact,
    Severity,
)
from src.engcore.sria.campaign.stopping import StoppingCriterion
from src.engcore.sria.provenance import AssessmentProvenance

from experiments.electrical_e2.e2_adequacy import AdequacyState, ExecutionValidity

from .e3_config import (
    ADEQUACY_OBLIGATION,
    CANDIDATE_ACTIONS,
    STOPPING_CRITERION_ID,
    STOPPING_CRITERION_STATEMENT,
    STOPPING_EVALUATOR_ID,
    STOPPING_EVALUATOR_VERSION,
    AdequacyObligation,
)

ACTION_BY_ID = {a.action_id: a for a in CANDIDATE_ACTIONS}


class ObligationBindingError(Exception):
    """An action was offered as obligation evidence that cannot be that.

    Raised when a recorded probe does not correspond to a declared condition,
    or corresponds to one but at the wrong operating point. Without this, a
    campaign could discharge an expensive obligation by running a cheap action
    and asserting it counted.
    """


class ObligationStatus(str, Enum):
    """Whether the required scientific test has been performed.

    Note what is absent: there is no SATISFIED_AND_PASSED. Whether the model
    survived is not this enum's business.
    """

    OUTSTANDING = "outstanding"
    COMPLETED = "completed"
    UNRESOLVED_BUDGET_INFEASIBLE = "unresolved_budget_infeasible"
    UNRESOLVED_EXECUTION_FAILURE = "unresolved_execution_failure"


class AdequacyScope(str, Enum):
    """What the acquired evidence says about the family, for the declared scope."""

    NOT_ESTABLISHED = "not_established"
    ACCEPTABLE_FOR_DECLARED_SCOPE = "acceptable_for_declared_scope"
    MODEL_SPACE_INADEQUATE = "model_space_inadequate"
    NOT_ASSESSED = "not_assessed"


#: Total mapping from E2's frozen verdict. Kept explicit so a new E2 state
#: would break loudly rather than silently defaulting to something reassuring.
_E2_TO_SCOPE: Mapping[AdequacyState, AdequacyScope] = {
    AdequacyState.MODEL_ADEQUACY_ACCEPTABLE: (
        AdequacyScope.ACCEPTABLE_FOR_DECLARED_SCOPE
    ),
    AdequacyState.MODEL_ADEQUACY_NOT_ESTABLISHED: AdequacyScope.NOT_ESTABLISHED,
    AdequacyState.MODEL_SPACE_INADEQUATE: AdequacyScope.MODEL_SPACE_INADEQUATE,
}


def scope_from_e2_state(state: AdequacyState) -> AdequacyScope:
    if state not in _E2_TO_SCOPE:
        raise KeyError(
            f"no declared E3 scope mapping for E2 adequacy state {state!r}; "
            f"refusing to guess"
        )
    return _E2_TO_SCOPE[state]


# =====================================================================
# The obligation ledger
# =====================================================================

@dataclass(frozen=True)
class ProbeRecord:
    """One attempt at one required condition, and whether it counted."""

    action_id: str
    source_voltage_volt: float
    execution_id: str
    execution_valid: bool
    admitted: bool
    commitment_artifact_hash: str
    realized_cost: float
    execution_reason: str

    @property
    def is_obligation_evidence(self) -> bool:
        """Whether this attempt discharges its required condition.

        All three conditions are necessary. A computationally invalid run is
        not evidence; an unadmitted result never entered belief; and a probe
        with no predictive commitment tests nothing, because its prediction
        could have been written after its answer was known.
        """
        return bool(
            self.execution_valid
            and self.admitted
            and self.commitment_artifact_hash
        )

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["is_obligation_evidence"] = self.is_obligation_evidence
        return payload


class ObligationLedger:
    """Tracks one finite obligation. Append-only, and it never grows.

    The required set is fixed at construction from the frozen specification.
    Once every required condition has counting evidence the ledger reports
    COMPLETED and :meth:`next_probe` returns nothing — an obligation that could
    keep asking for one more measurement would not be a scientific requirement.
    """

    def __init__(self, spec: AdequacyObligation = ADEQUACY_OBLIGATION) -> None:
        self._spec = spec
        self._records: list[ProbeRecord] = []
        self._budget_infeasible = False
        self._infeasible_detail = ""

    @property
    def spec(self) -> AdequacyObligation:
        return self._spec

    @property
    def records(self) -> tuple[ProbeRecord, ...]:
        return tuple(self._records)

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(self._spec.required_action_ids)

    def _counting(self) -> set[str]:
        return {
            r.action_id
            for r in self._records
            if r.action_id in self.required and r.is_obligation_evidence
        }

    def satisfied_required(self) -> tuple[str, ...]:
        return tuple(a for a in self.required if a in self._counting())

    def outstanding_required(self) -> tuple[str, ...]:
        counting = self._counting()
        return tuple(a for a in self.required if a not in counting)

    def failed_attempts(self) -> tuple[ProbeRecord, ...]:
        """Required-condition attempts that did not count, and were not
        subsequently superseded by one that did."""
        counting = self._counting()
        return tuple(
            r
            for r in self._records
            if r.action_id in self.required
            and not r.is_obligation_evidence
            and r.action_id not in counting
        )

    @property
    def spent(self) -> float:
        return float(sum(r.realized_cost for r in self._records))

    def mark_budget_infeasible(self, detail: str) -> None:
        """Record that a required probe could not be afforded.

        Deliberately a distinct state. Not being able to buy the evidence is
        not a finding about the model, and must never be reported as one.
        """
        self._budget_infeasible = True
        self._infeasible_detail = detail

    def record_probe(
        self,
        *,
        action_id: str,
        source_voltage_volt: float,
        execution_id: str,
        execution_valid: bool,
        admitted: bool,
        commitment_artifact_hash: str,
        realized_cost: float,
        execution_reason: str,
    ) -> ProbeRecord:
        """Record one attempt, with the binding checks that make it meaningful."""
        action = ACTION_BY_ID.get(action_id)
        if action is None:
            raise ObligationBindingError(
                f"{action_id!r} is not a declared E3 action and cannot be "
                f"offered as evidence for {self._spec.obligation_id!r}"
            )
        if float(source_voltage_volt) != float(action.source_voltage_volt):
            raise ObligationBindingError(
                f"{action_id!r} is declared at Vs = "
                f"{action.source_voltage_volt} V but was executed at "
                f"{source_voltage_volt} V; an obligation is bound to a "
                f"condition, not to an action name"
            )
        record = ProbeRecord(
            action_id=action_id,
            source_voltage_volt=float(source_voltage_volt),
            execution_id=execution_id,
            execution_valid=bool(execution_valid),
            admitted=bool(admitted),
            commitment_artifact_hash=str(commitment_artifact_hash),
            realized_cost=float(realized_cost),
            execution_reason=execution_reason,
        )
        self._records.append(record)
        return record

    # -- the selection rule -------------------------------------------------
    def next_probe(
        self, *, affordable: Callable[[float], bool] | None = None
    ) -> str | None:
        """The next probe to execute, by the frozen constraint rule.

        Cheapest outstanding REQUIRED probe, ties broken by declared order.
        This ranks a fixed required set by price; it does not rank candidates
        by expected information value, and it cannot, because nothing in this
        module can compute one.
        """
        outstanding = self.outstanding_required()
        if not outstanding:
            return None
        ordered = sorted(
            outstanding,
            key=lambda a: (ACTION_BY_ID[a].cost, self.required.index(a)),
        )
        for action_id in ordered:
            if affordable is None or affordable(ACTION_BY_ID[action_id].cost):
                return action_id
        return None

    def remaining_required_cost(self) -> float:
        return float(
            sum(ACTION_BY_ID[a].cost for a in self.outstanding_required())
        )

    @property
    def status(self) -> ObligationStatus:
        if self.failed_attempts():
            return ObligationStatus.UNRESOLVED_EXECUTION_FAILURE
        if not self.outstanding_required():
            return ObligationStatus.COMPLETED
        if self._budget_infeasible:
            return ObligationStatus.UNRESOLVED_BUDGET_INFEASIBLE
        return ObligationStatus.OUTSTANDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self._spec.obligation_id,
            "status": self.status.value,
            "required": list(self.required),
            "satisfied": list(self.satisfied_required()),
            "outstanding": list(self.outstanding_required()),
            "failed_attempts": [r.to_dict() for r in self.failed_attempts()],
            "records": [r.to_dict() for r in self._records],
            "spent": self.spent,
            "max_adequacy_cost": self._spec.max_adequacy_cost,
            "budget_infeasible_detail": self._infeasible_detail,
        }


@dataclass
class ObligationState:
    """What the stopping evaluator is allowed to see. Nothing else."""

    ledger: ObligationLedger
    adequacy_scope: AdequacyScope = AdequacyScope.NOT_ESTABLISHED
    adequacy_detail: str = ""
    execution_validity: ExecutionValidity = ExecutionValidity.NOT_ASSESSED

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation": self.ledger.to_dict(),
            "adequacy_scope": self.adequacy_scope.value,
            "adequacy_detail": self.adequacy_detail,
            "execution_validity": self.execution_validity.value,
        }


# =====================================================================
# The Arbiter-facing stopping criterion
# =====================================================================

def adequacy_stopping_criterion() -> StoppingCriterion:
    """The obligation, expressed as something the frozen M5.1 review accepts."""
    return StoppingCriterion(
        criterion_id=STOPPING_CRITERION_ID,
        statement=STOPPING_CRITERION_STATEMENT,
        source=ADEQUACY_OBLIGATION.source,
        evaluator_id=STOPPING_EVALUATOR_ID,
        evaluator_version=STOPPING_EVALUATOR_VERSION,
    )


class AdequacyStoppingEvaluator:
    """Evaluates the adequacy obligation into a CriticAssessment.

    A real ``StoppingCriterionEvaluator``. It reads the obligation ledger and
    the adequacy scope and nothing else — no grader truth, no posterior, no
    EVPI, no EVSI, no budget. It mints no stopping verdict: it produces an
    assessment, and ``ArbiterStoppingReview`` hands that to the Arbiter.

    The check it emits is named for the criterion so the Arbiter's
    REQUIRED_CHECK path can adjudicate it. This is deliberately NOT the
    ``validation_level:*`` obligation vocabulary, which M3 records for
    provenance and explicitly cannot evaluate — an obligation that always fails
    closed would make every stop unassessable and would let E3 claim a
    governance result it had not demonstrated.
    """

    criterion_id = STOPPING_CRITERION_ID
    critic_id = STOPPING_EVALUATOR_ID
    critic_version = STOPPING_EVALUATOR_VERSION

    def __init__(self, state: ObligationState) -> None:
        self._state = state

    def _verdicts(self) -> tuple[CriticVerdict, tuple[Finding, ...], str]:
        status = self._state.ledger.status
        scope = self._state.adequacy_scope
        obligation_id = self._state.ledger.spec.obligation_id

        if status is ObligationStatus.UNRESOLVED_EXECUTION_FAILURE:
            return (
                CriticVerdict.NOT_ASSESSED,
                (),
                (
                    f"a required probe for {obligation_id!r} did not execute "
                    f"validly; the obligation is unresolved and no adequacy "
                    f"judgement may be drawn from an invalid run"
                ),
            )
        if status is ObligationStatus.UNRESOLVED_BUDGET_INFEASIBLE:
            return (
                CriticVerdict.FAIL,
                (
                    Finding(
                        code="e3.adequacy_evidence_budget_infeasible",
                        severity=Severity.BLOCKING,
                        category="process",
                        message=(
                            "required adequacy evidence cannot be purchased "
                            "within the declared adequacy budget"
                        ),
                        # Blocks certification. Says NOTHING about the model:
                        # not affording a test is not a result of the test.
                        impact=FindingImpact.ASSURANCE_BLOCKING,
                    ),
                ),
                (
                    f"{obligation_id!r} cannot be discharged within its "
                    f"declared budget; outstanding "
                    f"{list(self._state.ledger.outstanding_required())}"
                ),
            )
        if status is ObligationStatus.OUTSTANDING:
            return (
                CriticVerdict.FAIL,
                (
                    Finding(
                        code="e3.adequacy_obligation_outstanding",
                        severity=Severity.BLOCKING,
                        category="process",
                        message=(
                            "the declared model-adequacy obligation has not "
                            "been discharged"
                        ),
                        # Blocking, NOT invalidating. Nothing has been refuted;
                        # the required test simply has not been run yet.
                        impact=FindingImpact.ASSURANCE_BLOCKING,
                    ),
                ),
                (
                    f"{obligation_id!r} is outstanding: "
                    f"{list(self._state.ledger.outstanding_required())} of "
                    f"{list(self._state.ledger.required)} not yet acquired"
                ),
            )

        # --- the obligation is COMPLETED: the test was performed -----------
        if scope is AdequacyScope.ACCEPTABLE_FOR_DECLARED_SCOPE:
            return (
                CriticVerdict.PASS,
                (),
                (
                    f"{obligation_id!r} discharged; the precommitted predictive "
                    f"checks left the family adequate for the declared scope"
                ),
            )
        if scope is AdequacyScope.MODEL_SPACE_INADEQUATE:
            return (
                CriticVerdict.FAIL,
                (
                    Finding(
                        code="e3.model_space_inadequate",
                        severity=Severity.BLOCKING,
                        category="model_adequacy",
                        message=(
                            "the required adequacy evidence was acquired and "
                            "refuted the declared model family; stopping here "
                            "would certify a family this campaign's own "
                            "precommitted predictions have failed"
                        ),
                        # Evidence-backed refutation OF THE STOP PROPOSAL, which
                        # is this assessment's subject. Valid admitted evidence
                        # showed that stopping now is wrong, not merely
                        # unestablished. The EVIDENCE itself remains valid and
                        # admitted; it is the proposal to stop that is refuted.
                        impact=FindingImpact.EVIDENCE_INVALIDATING,
                    ),
                ),
                (
                    f"{obligation_id!r} discharged and FAILED: "
                    f"{self._state.adequacy_detail}"
                ),
            )
        return (
            CriticVerdict.FAIL,
            (
                Finding(
                    code="e3.adequacy_not_established",
                    severity=Severity.BLOCKING,
                    category="model_adequacy",
                    message=(
                        "the required evidence was acquired but did not "
                        "establish adequacy for the declared scope"
                    ),
                    impact=FindingImpact.ASSURANCE_BLOCKING,
                ),
            ),
            (
                f"{obligation_id!r} discharged but adequacy remains "
                f"{scope.value}"
            ),
        )

    def evaluate(self, context: Any, *, assessment_id: str) -> CriticAssessment:
        verdict, findings, summary = self._verdicts()
        ledger = self._state.ledger
        run_ref = str(getattr(context, "run_id", "") or "e3")
        return CriticAssessment(
            assessment_id=assessment_id,
            critic_id=self.critic_id,
            critic_version=self.critic_version,
            # PROCESS: "were the declared obligations followed?" — which is
            # exactly and only what this evaluator speaks to.
            critic_class=CriticClass.PROCESS,
            subject_ref=assessment_id,
            verdict=verdict,
            provenance=AssessmentProvenance(
                assessment_id=assessment_id,
                critic_id=self.critic_id,
                critic_version=self.critic_version,
                inputs_ref=(run_ref, ledger.spec.obligation_id),
            ),
            checks=(
                CheckRecord(
                    # Named for the criterion so the Arbiter's REQUIRED_CHECK
                    # path adjudicates it. This is a real, evaluable target.
                    name=self.criterion_id,
                    outcome=verdict,
                    mandatory=True,
                    detail=summary,
                ),
                CheckRecord(
                    name="adequacy_obligation_status",
                    outcome=(
                        CriticVerdict.PASS
                        if ledger.status is ObligationStatus.COMPLETED
                        else CriticVerdict.FAIL
                    ),
                    mandatory=False,
                    detail=(
                        f"status={ledger.status.value}; satisfied="
                        f"{list(ledger.satisfied_required())}; outstanding="
                        f"{list(ledger.outstanding_required())}"
                    ),
                ),
                CheckRecord(
                    name="model_adequacy_for_declared_scope",
                    outcome=(
                        CriticVerdict.PASS
                        if self._state.adequacy_scope
                        is AdequacyScope.ACCEPTABLE_FOR_DECLARED_SCOPE
                        else CriticVerdict.NOT_ASSESSED
                        if self._state.adequacy_scope
                        in (
                            AdequacyScope.NOT_ASSESSED,
                            AdequacyScope.NOT_ESTABLISHED,
                        )
                        else CriticVerdict.FAIL
                    ),
                    mandatory=False,
                    detail=(
                        f"scope={self._state.adequacy_scope.value}; "
                        f"TEST PERFORMED and MODEL PASSED are separate states"
                    ),
                ),
            ),
            findings=findings,
            summary=summary,
        )


# =====================================================================
# The certification gate
# =====================================================================

class Certification(str, Enum):
    ELIGIBLE = "eligible"
    NOT_CERTIFIABLE = "not_certifiable"


class Disposition(str, Enum):
    CERTIFICATION_ELIGIBLE = "certification_eligible"
    ADEQUACY_EVIDENCE_REQUIRED = "adequacy_evidence_required"
    CERTIFICATION_NOT_POSSIBLE = "certification_not_possible"
    EXECUTION_REPAIR_REQUIRED = "execution_repair_required"
    MODEL_REVISION_REQUIRED = "model_revision_required"


@dataclass(frozen=True)
class CampaignCertification:
    posterior_decision: str
    scientific_certification: Certification
    reason: str
    disposition: Disposition
    obligation_status: ObligationStatus
    adequacy_scope: AdequacyScope
    execution_validity: ExecutionValidity
    statement: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "posterior_decision": self.posterior_decision,
            "scientific_certification": self.scientific_certification.value,
            "reason": self.reason,
            "disposition": self.disposition.value,
            "obligation_status": self.obligation_status.value,
            "adequacy_scope": self.adequacy_scope.value,
            "execution_validity": self.execution_validity.value,
            "statement": self.statement,
        }


#: The exact parameter names :func:`certify_campaign` may have. A test compares
#: this against the live signature, so adding a posterior-strength or
#: value-of-information input to the certification gate breaks the build rather
#: than the argument.
CERTIFY_CAMPAIGN_ALLOWED_PARAMETERS = (
    "posterior_decision",
    "obligation_status",
    "adequacy_scope",
    "execution_validity",
)


def certify_campaign(
    posterior_decision: str,
    obligation_status: ObligationStatus,
    adequacy_scope: AdequacyScope,
    execution_validity: ExecutionValidity,
) -> CampaignCertification:
    """Decide whether the posterior's preferred decision may be certified.

    Three axes, evaluated in the order that keeps their meanings distinct:
    a broken computation is a computation problem, an undischarged obligation
    is a process problem, and a refuted family is a model problem. Collapsing
    any two of them would produce a system that answers "we could not afford
    the test" and "the model is wrong" with the same word.

    Note the parameters this function does NOT have: no posterior sd, no
    entropy, no P(decision), no EVPI, no EVSI, and no stop-proposal state.
    Every one of those is computed inside the family under test or is a
    statement about prices, and neither kind of thing gets a vote here.
    """
    if execution_validity is not ExecutionValidity.VALID:
        return CampaignCertification(
            posterior_decision=posterior_decision,
            scientific_certification=Certification.NOT_CERTIFIABLE,
            reason=f"EXECUTION_VALIDITY={execution_validity.value.upper()}",
            disposition=Disposition.EXECUTION_REPAIR_REQUIRED,
            obligation_status=obligation_status,
            adequacy_scope=adequacy_scope,
            execution_validity=execution_validity,
            statement=(
                "the computation did not produce trustworthy output; this is a "
                "computational failure, not an adequacy finding and not a "
                "budget finding"
            ),
        )
    if obligation_status is ObligationStatus.UNRESOLVED_EXECUTION_FAILURE:
        return CampaignCertification(
            posterior_decision=posterior_decision,
            scientific_certification=Certification.NOT_CERTIFIABLE,
            reason="REQUIRED_ADEQUACY_EVIDENCE_EXECUTION_FAILED",
            disposition=Disposition.EXECUTION_REPAIR_REQUIRED,
            obligation_status=obligation_status,
            adequacy_scope=adequacy_scope,
            execution_validity=execution_validity,
            statement=(
                "a required probe failed to execute validly, so the declared "
                "test was never performed. No adequacy judgement may be drawn "
                "from evidence that does not exist"
            ),
        )
    if obligation_status is ObligationStatus.UNRESOLVED_BUDGET_INFEASIBLE:
        return CampaignCertification(
            posterior_decision=posterior_decision,
            scientific_certification=Certification.NOT_CERTIFIABLE,
            reason="REQUIRED_ADEQUACY_EVIDENCE_BUDGET_INFEASIBLE",
            disposition=Disposition.CERTIFICATION_NOT_POSSIBLE,
            obligation_status=obligation_status,
            adequacy_scope=adequacy_scope,
            execution_validity=execution_validity,
            statement=(
                "the required evidence is affordable neither now nor within the "
                "declared adequacy budget. The model is not thereby inadequate "
                "and is not thereby adequate — it is untested, and an untested "
                "model is not certified"
            ),
        )
    if obligation_status is ObligationStatus.OUTSTANDING:
        return CampaignCertification(
            posterior_decision=posterior_decision,
            scientific_certification=Certification.NOT_CERTIFIABLE,
            reason="ADEQUACY_OBLIGATION_OUTSTANDING",
            disposition=Disposition.ADEQUACY_EVIDENCE_REQUIRED,
            obligation_status=obligation_status,
            adequacy_scope=adequacy_scope,
            execution_validity=execution_validity,
            statement=(
                "the declared adequacy test has not been performed. This is a "
                "finite, preregistered requirement, not an instruction to keep "
                "experimenting indefinitely"
            ),
        )

    # --- the obligation is COMPLETED. Now, and only now, the model answers.
    if adequacy_scope is AdequacyScope.MODEL_SPACE_INADEQUATE:
        return CampaignCertification(
            posterior_decision=posterior_decision,
            scientific_certification=Certification.NOT_CERTIFIABLE,
            reason="MODEL_SPACE_INADEQUATE",
            disposition=Disposition.MODEL_REVISION_REQUIRED,
            obligation_status=obligation_status,
            adequacy_scope=adequacy_scope,
            execution_validity=execution_validity,
            statement=(
                "the obligation was discharged COMPLETELY — the required test "
                "was performed on valid, admitted, predictively-committed "
                "evidence — and the model failed it. Test completed and model "
                "passed are separate states, and this is the first without the "
                "second"
            ),
        )
    if adequacy_scope is not AdequacyScope.ACCEPTABLE_FOR_DECLARED_SCOPE:
        return CampaignCertification(
            posterior_decision=posterior_decision,
            scientific_certification=Certification.NOT_CERTIFIABLE,
            reason="MODEL_ADEQUACY_NOT_ESTABLISHED",
            disposition=Disposition.ADEQUACY_EVIDENCE_REQUIRED,
            obligation_status=obligation_status,
            adequacy_scope=adequacy_scope,
            execution_validity=execution_validity,
            statement=(
                "the required evidence was acquired but did not settle the "
                "question either way for the declared scope"
            ),
        )
    return CampaignCertification(
        posterior_decision=posterior_decision,
        scientific_certification=Certification.ELIGIBLE,
        reason="ADEQUACY_ACCEPTABLE_FOR_DECLARED_SCOPE",
        disposition=Disposition.CERTIFICATION_ELIGIBLE,
        obligation_status=obligation_status,
        adequacy_scope=adequacy_scope,
        execution_validity=execution_validity,
        statement=(
            "execution was valid, the declared obligation was discharged, and "
            "the family survived its own precommitted predictions at the "
            "required conditions. ELIGIBLE is scoped to those conditions and is "
            "not a general certificate of scientific completeness"
        ),
    )
