"""Deterministic toy decision benchmark for M4.

Not a scientific claim and not a use of D5. A small exact problem whose
expected utilities can be checked by hand, so the VoI machinery is tested
against arithmetic rather than against a model's opinion.

The campaign
------------
Choose between two designs. The unknown state is which one is better:

    theta in {A_better, B_better},  prior P(A_better) = 0.5

Terminal utility: pick the design the belief favours, and be right or wrong.

    u(belief with confidence p) = PAYOFF * max(p, 1 - p)

At the prior this is ``PAYOFF * 0.5`` — a coin flip. An action that would
leave the campaign with confidence ``r`` is therefore worth

    E[delta u] = PAYOFF * r - PAYOFF * 0.5

which is exact, monotone in ``r``, and independent of anything learned.

Every scenario's ground-truth net value is computable in closed form:

    net(a) = (PAYOFF * r_a - PAYOFF * 0.5) * (1 - p_fail_a)
             + failure_value_a
             - lambda * cost_a

That closed form is what the tests compare against — the benchmark never asks
the engine to grade its own homework.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.engcore.scientific import Quantity
from src.engcore.sria import (
    CampaignCharter,
    ExecutorType,
    FeasibilityVerdict,
    HardFeasibilityGate,
    ResearchAction,
    TerminalDecision,
)
from src.engcore.sria.calibration.critic import CalibrationVerdict
from src.engcore.sria.decision import (
    ActionFamily,
    CostTradeoff,
    ActionProposal,
    AtomicAction,
    BeliefSnapshot,
    CalibrationState,
    ComponentStatus,
    DependencyIdentity,
    DependencyKind,
    ScoreComponent,
    canonical_digest,
)

PAYOFF = 10.0
PRIOR = 0.5
#: The campaign's declared exchange rate. M4.1 forbids a hidden lambda: the
#: rate, its unit and the utility scale it refers to must all be stated.
COST_WEIGHT = 1.0     # utility units per compute-hour, declared below


# =====================================================================
# Campaign + terminal utility
# =====================================================================

def toy_cost_tradeoff() -> CostTradeoff:
    """One declared utility-hour of compute is worth one utility unit here."""
    return CostTradeoff(
        rate=COST_WEIGHT,
        cost_unit="hour",
        utility_reference="toy/confidence-payoff/1",
        source="toy campaign charter",
        assumptions=("compute time is the only cost the campaign charges for",),
    )


def toy_charter(campaign_id: str = "toy-campaign") -> CampaignCharter:
    return CampaignCharter(
        campaign_id=campaign_id,
        terminal_decisions=(
            TerminalDecision(
                decision_id="pick_design",
                statement="Select the better of design_a and design_b",
                options=("design_a", "design_b"),
            ),
        ),
        utility_reference="toy/confidence-payoff/1",
    )


class ToyTerminalUtility:
    """u = PAYOFF * max(p, 1-p). Exact, and owned by the campaign."""

    utility_id = "toy.confidence_payoff"
    utility_version = "1"

    def expected_utility(self, snapshot: BeliefSnapshot, decision_id: str) -> float:
        p = float(snapshot.metadata.get("confidence", PRIOR))
        return PAYOFF * max(p, 1.0 - p)

    def expected_utility_after(
        self, snapshot: BeliefSnapshot, decision_id: str, outcome: Mapping[str, Any]
    ) -> float:
        r = float(outcome["reliability"])
        return PAYOFF * max(r, 1.0 - r)

    def state_digest(self) -> str:
        """This utility genuinely *is* its two constants.

        Closed form, no fitted parameters, no hidden state: PAYOFF and PRIOR
        determine every value it can return. Digesting them is a complete
        description, not a stand-in for one. A utility with learned internals
        must not implement this method unless it can say the same.
        """
        return canonical_digest(
            {"form": "PAYOFF*max(p,1-p)", "payoff": PAYOFF, "prior": PRIOR}
        )


def toy_snapshot(
    snapshot_id: str = "snap-1",
    *,
    confidence: float = PRIOR,
    cost_verdict: CalibrationVerdict | None = CalibrationVerdict.TRUSTED,
    failure_verdict: CalibrationVerdict | None = None,
    obligation_state: Mapping[str, bool] | None = None,
) -> BeliefSnapshot:
    return BeliefSnapshot(
        snapshot_id=snapshot_id,
        campaign_id="toy-campaign",
        charter_version="1",
        active_evidence=("ev-prior",),
        calibration=CalibrationState(
            cost_model_id="cost.hierarchical",
            cost_verdict=cost_verdict,
            failure_model_id="failure.smoothed_rate",
            failure_verdict=failure_verdict,
        ),
        obligation_state=dict(obligation_state or {}),
        metadata={"confidence": confidence},
    )


# =====================================================================
# Candidate construction
# =====================================================================

def toy_action(
    action_id: str,
    *,
    family: ActionFamily,
    reliability: float,
    cost: float,
    conditional_failure_gain: float = 0.0,
    informative_failure_causes: tuple[str, ...] = (),
    target_ref: str = "theta",
) -> AtomicAction:
    """One candidate with its exact reliability and cost declared."""
    return AtomicAction(
        action=ResearchAction(
            action_id=action_id,
            executor_type=ExecutorType.SIMULATION,
            target_ref=target_ref,
            expected_cost={"compute": Quantity(cost, "hour")},
            metadata={
                "reliability": reliability,
                "cost": cost,
                "conditional_failure_gain": conditional_failure_gain,
            },
        ),
        proposal=ActionProposal(
            family=family,
            target_ref=target_ref,
            rationale=f"toy candidate with reliability {reliability}",
            expected_observable="theta",
            informative_failure_causes=informative_failure_causes,
        ),
    )


def ground_truth_net_value(
    candidate: Any, *, p_fail: float = 0.0, cost_weight: float = COST_WEIGHT
) -> float:
    """Closed-form value of a candidate. The tests' independent reference."""
    members = candidate.members
    reliability = max(float(m.action.metadata["reliability"]) for m in members)
    cost = sum(float(m.action.metadata["cost"]) for m in members)
    conditional_failure_gain = sum(
        float(m.action.metadata.get("conditional_failure_gain", 0.0))
        for m in members
    )
    gain = PAYOFF * max(reliability, 1.0 - reliability) - PAYOFF * max(
        PRIOR, 1.0 - PRIOR
    )
    # Expected failure VoI is the conditional gain weighted by p_fail — the
    # same decomposition the engine uses, written out independently.
    return (
        gain * (1.0 - p_fail)
        + conditional_failure_gain * p_fail
        - cost_weight * cost
    )


# =====================================================================
# Suppliers — exact, deterministic, no learning
# =====================================================================

class ToyOutcomeModel:
    """Reads the declared reliability. No inference, no surprises."""

    def dependency_identity(self) -> DependencyIdentity:
        """Stateless: it reads declared metadata and fits nothing.

        The absence of fitted state is itself the state, and it is stable
        across processes — so this is pinnable without inventing anything.
        """
        return DependencyIdentity(
            dependency_id="toy.outcome_model",
            kind=DependencyKind.OUTCOME_MODEL,
            version="1",
            state_digest=canonical_digest({"outcome_model": "toy.declared", "v": 1}),
            detail="stateless reader of declared reliability",
        )

    def conditional_success_utility_gain(
        self, candidate, snapshot, objective
    ) -> ScoreComponent:
        reliability = max(
            float(m.action.metadata["reliability"]) for m in candidate.members
        )
        after = objective.expected_utility_after(
            snapshot, {"reliability": reliability}
        )
        now = objective.current_expected_utility(snapshot)
        return ScoreComponent(
            name="conditional_success_utility_gain",
            value=after - now,
            status=ComponentStatus.AVAILABLE,
            source="toy.outcome_model",
            assumptions=("declared reliability is exact",),
            detail=f"reliability {reliability}",
        )

    def conditional_failure_utility_gain(
        self, candidate, snapshot, objective
    ) -> ScoreComponent:
        """Value learned GIVEN execution failure. Not probability-weighted —
        the engine multiplies by p_cf itself, so the conditioning is stated
        once and cannot be double counted."""
        value = sum(
            float(m.action.metadata.get("conditional_failure_gain", 0.0))
            for m in candidate.members
        )
        return ScoreComponent(
            name="conditional_failure_utility_gain",
            value=value,
            status=ComponentStatus.AVAILABLE,
            source="toy.outcome_model",
            detail="declared value learned given an informative execution failure",
        )


class ToyCostSupplier:
    """Declared cost, tagged with the calibration verdict it stands on."""

    def __init__(
        self,
        verdict: CalibrationVerdict | None = CalibrationVerdict.TRUSTED,
        unit: str = "hour",
    ):
        self._verdict = verdict
        self._unit = unit

    def dependency_identity(self) -> DependencyIdentity:
        """Its entire behaviour is determined by the verdict and the unit.

        The id matches what ``toy_snapshot()`` declares in its calibration
        state, because they are meant to be the same model — an M4.2 oversight
        that M4.3's coherence check surfaced immediately.
        """
        return DependencyIdentity(
            dependency_id="cost.hierarchical",
            kind=DependencyKind.COST_MODEL,
            version="1",
            state_digest=canonical_digest(
                {
                    "verdict": self._verdict.value if self._verdict else None,
                    "unit": self._unit,
                }
            ),
            detail="declared cost; no fitted parameters",
        )

    def expected_cost(self, candidate, snapshot) -> ScoreComponent:
        if self._verdict is None or self._verdict is CalibrationVerdict.INSUFFICIENT_DATA:
            return ScoreComponent(
                name="expected_cost",
                value=None,
                status=ComponentStatus.UNAVAILABLE,
                source="toy.cost",
                calibration_verdict=self._verdict,
                detail="no cost calibration",
            )
        total = sum(float(m.action.metadata["cost"]) for m in candidate.members)
        status = (
            ComponentStatus.AVAILABLE
            if self._verdict is CalibrationVerdict.TRUSTED
            else ComponentStatus.DEGRADED
        )
        return ScoreComponent(
            name="expected_cost",
            value=total,
            status=status,
            source="toy.cost",
            calibration_verdict=self._verdict,
            unit=self._unit,
            detail="declared toy cost",
        )


class ToyFailureSupplier:
    """p_fail, or an honest refusal — mirroring M2's real state."""

    def __init__(
        self,
        probability: float | None = None,
        verdict: CalibrationVerdict | None = None,
    ):
        self._probability = probability
        self._verdict = verdict

    def dependency_identity(self) -> DependencyIdentity:
        """Declared probability and verdict are the whole of its state."""
        return DependencyIdentity(
            dependency_id="failure.smoothed_rate",
            kind=DependencyKind.FAILURE_SOURCE,
            version="1",
            state_digest=canonical_digest(
                {
                    "p": self._probability,
                    "verdict": self._verdict.value if self._verdict else None,
                }
            ),
            detail="declared failure probability; no fitted parameters",
        )

    def computational_failure_probability(
        self, candidate, snapshot
    ) -> ScoreComponent:
        if self._probability is None:
            return ScoreComponent(
                name="p_computational_failure",
                value=None,
                status=ComponentStatus.UNAVAILABLE,
                source="toy.failure",
                calibration_verdict=self._verdict,
                detail="p_fail was not learned (mirrors M2 INSUFFICIENT_DATA)",
            )
        status = (
            ComponentStatus.AVAILABLE
            if self._verdict is CalibrationVerdict.TRUSTED
            else ComponentStatus.DEGRADED
        )
        return ScoreComponent(
            name="p_computational_failure",
            value=float(self._probability),
            status=status,
            source="toy.failure",
            calibration_verdict=self._verdict,
            detail="declared toy failure probability",
        )


# =====================================================================
# Feasibility
# =====================================================================

@dataclass(frozen=True)
class ForbiddenTargetConstraint:
    """Hard constraint: some targets are simply not permissible."""

    forbidden: tuple[str, ...] = ()
    constraint_id: str = "toy.forbidden_target"

    def evaluate(self, action: ResearchAction) -> FeasibilityVerdict:
        blocked = action.target_ref in self.forbidden
        return FeasibilityVerdict(
            constraint_id=self.constraint_id,
            feasible=not blocked,
            reason=(
                "" if not blocked else f"target {action.target_ref!r} is forbidden"
            ),
        )


def gate_forbidding(*targets: str) -> HardFeasibilityGate:
    return HardFeasibilityGate([ForbiddenTargetConstraint(forbidden=tuple(targets))])
