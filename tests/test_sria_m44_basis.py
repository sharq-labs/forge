"""SRIA V0.1 M4.4 — formal decision basis audit.

Runs under pytest, and standalone via ``python -m tests.test_sria_m44_basis``.

The property under test:

    SRIA formal decision scoring fails closed unless the scientific,
    computational and decision-theoretic dependencies used by the score are
    pinned and verified as one coherent decision basis.

M4.3 pinned the calibration half. The decision-theoretic half — terminal
utility, outcome model, cost tradeoff, utility policy — was unchecked, and
every one of these was measured changing a score silently while the snapshot,
candidates, charter version and policy_id/policy_version were all held fixed:

    tampered terminal utility  ->  +0.0 became +891.0
    tampered outcome model     ->  +0.0 became  +36.0
    changed cost tradeoff      ->  +0.0 became  +3.996
    mutated policy state       ->  +0.0 became   +4.0

Each reported ``coherence=coherent``. They are reproduced here as regressions.
"""

from __future__ import annotations

import dataclasses
import json
import sys

from src.engcore.sria.calibration import CostModel
from src.engcore.sria.calibration.critic import CalibrationVerdict
from src.engcore.sria.decision import (
    CandidateEvaluator,
    CoherenceStatus,
    CostTradeoff,
    DecisionRecommendation,
    DependencyKind,
    PROVISIONAL_DECISION_MODE_RESERVED,
    RecommendationOutcome,
    ReplayOutcome,
    UtilityEngine,
    UtilityPolicy,
    CalibrationCostSupplier,
    audit_replay,
    check_state_coherence,
    executable_replay,
    information_only_ranking,
    pin_decision_basis,
    resolve_terminal_objective,
)

from tests.sria_m4_benchmark import (
    PAYOFF,
    PRIOR,
    ToyFailureSupplier,
    ToyOutcomeModel,
    ToyTerminalUtility,
    ground_truth_net_value,
    toy_charter,
    toy_cost_tradeoff,
    toy_snapshot,
)
from tests.test_sria_m4_decision import SCENARIOS, evaluate
from tests.test_sria_m42_replay import CANDIDATES, GOOD, record_builder, training
import tests.test_sria_m42_replay as M42
import tests.test_sria_m43_coherence as M43

CHARTER = "1"


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


# =====================================================================
# A configurable stack, so one provider can move at a time
# =====================================================================

def stack(*, outcome=None, tradeoff=None, failure=None, cost=None, model=None):
    model = model if model is not None else CostModel().fit(
        training(4.0), dataset_id="corpus-v1"
    )
    engine = UtilityEngine(
        policy=UtilityPolicy(
            policy_id="toy.policy",
            cost_tradeoff=tradeoff if tradeoff is not None else toy_cost_tradeoff(),
        ),
        outcome_model=outcome if outcome is not None else ToyOutcomeModel(),
        cost_supplier=cost
        if cost is not None
        else CalibrationCostSupplier(
            model,
            record_builder=record_builder,
            verdict=CalibrationVerdict.TRUSTED,
            cost_unit="hour",
        ),
        failure_supplier=(
            failure
            if failure is not None
            else ToyFailureSupplier(0.0, CalibrationVerdict.TRUSTED)
        ),
    )
    return CandidateEvaluator(engine), model


def objective(utility=None):
    return resolve_terminal_objective(
        toy_charter(), utility if utility is not None else ToyTerminalUtility()
    )


def basis(evaluator, obj=None, *, snapshot_id="snap-basis"):
    obj = obj if obj is not None else objective()
    base = toy_snapshot(snapshot_id)
    return pin_decision_basis(
        base,
        evaluator.build_manifest(
            candidates=CANDIDATES,
            snapshot=base,
            objective=obj,
            charter_version=CHARTER,
        ),
    )


def decide(evaluator, snapshot, obj=None, *, rid="R"):
    return evaluator.evaluate(
        recommendation_id=rid,
        candidates=CANDIDATES,
        snapshot=snapshot,
        objective=obj if obj is not None else objective(),
        charter_version=CHARTER,
    )


# =====================================================================
# A. A complete, verified basis scores
# =====================================================================

def test_A_fully_pinned_basis_succeeds():
    evaluator, _ = stack()
    snapshot = basis(evaluator)
    assert snapshot.pins_decision_basis is True

    rec = decide(evaluator, snapshot, rid="A")
    assert rec.outcome is RecommendationOutcome.STOP_PROPOSAL
    assert rec.coherence.status is CoherenceStatus.COHERENT
    assert rec.is_state_coherent is True
    assert rec.coherence.unverified == ()
    assert rec.scores

    # Every dependency kind that can move a score is pinned and checked.
    kinds = {d.kind for d in snapshot.decision_basis}
    assert kinds == {
        DependencyKind.COST_MODEL,
        DependencyKind.FAILURE_SOURCE,
        DependencyKind.OUTCOME_MODEL,
        DependencyKind.TERMINAL_UTILITY,
        DependencyKind.COST_TRADEOFF,
        DependencyKind.UTILITY_POLICY,
        DependencyKind.UTILITY_ENGINE,
    }
    for dependency in snapshot.decision_basis:
        assert dependency.key in rec.coherence.checked, dependency.key


# =====================================================================
# B. Unpinned cost dependency
# =====================================================================

def test_B_unpinned_cost_dependency_is_refused():
    evaluator, _ = stack()
    snapshot = basis(evaluator)
    stripped = dataclasses.replace(
        snapshot,
        decision_basis=tuple(
            d for d in snapshot.decision_basis if d.kind is not DependencyKind.COST_MODEL
        ),
    )
    rec = decide(evaluator, stripped, rid="B")
    assert rec.outcome is RecommendationOutcome.DECISION_BASIS_UNVERIFIED
    assert rec.coherence.status is CoherenceStatus.BASIS_UNVERIFIED
    assert rec.scores == ()
    assert any(
        "cost_model" in u and "absent from the decision basis" in u
        for u in rec.coherence.unverified
    )


def test_B2_cost_supplier_that_cannot_identify_itself_is_refused():
    class OpaqueCostSupplier:
        def __init__(self, inner):
            self._inner = inner

        def expected_cost(self, candidate, snapshot):
            return self._inner.expected_cost(candidate, snapshot)

    evaluator, model = stack()
    opaque, _ = stack(
        cost=OpaqueCostSupplier(evaluator._engine._cost), model=model
    )
    # Pin the basis around the opaque stack itself, so the only finding is the
    # unidentifiable provider rather than a leftover pin from another stack.
    snapshot = basis(opaque)
    rec = decide(opaque, snapshot, rid="B2")
    assert rec.outcome is RecommendationOutcome.DECISION_BASIS_UNVERIFIED
    assert rec.scores == ()
    assert any(
        "cannot identify its executable semantics" in u
        for u in rec.coherence.unverified
    )


# =====================================================================
# C. Unpinned failure dependency while p_cf is used
# =====================================================================

def test_C_unpinned_failure_dependency_is_refused():
    """The failure channel feeds the score, so it must be verifiable."""
    evaluator, _ = stack(
        failure=ToyFailureSupplier(0.25, CalibrationVerdict.TRUSTED)
    )
    snapshot = basis(evaluator)
    scored = decide(evaluator, snapshot, rid="C-ok")
    assert scored.coherence.status is CoherenceStatus.COHERENT
    # p_cf genuinely participates in this score.
    assert scored.scores[0].component("p_computational_failure").value == 0.25

    stripped = dataclasses.replace(
        snapshot,
        decision_basis=tuple(
            d
            for d in snapshot.decision_basis
            if d.kind is not DependencyKind.FAILURE_SOURCE
        ),
    )
    rec = decide(evaluator, stripped, rid="C")
    assert rec.outcome is RecommendationOutcome.DECISION_BASIS_UNVERIFIED
    assert rec.scores == ()
    assert any("failure_source" in u for u in rec.coherence.unverified)


# =====================================================================
# D. Terminal utility changes, charter version unchanged
# =====================================================================

class TamperedUtility:
    """Same utility_id and utility_version. Different semantics."""

    utility_id = "toy.confidence_payoff"
    utility_version = "1"

    def expected_utility(self, snapshot, decision_id):
        p = float(snapshot.metadata.get("confidence", PRIOR))
        return PAYOFF * max(p, 1.0 - p)

    def expected_utility_after(self, snapshot, decision_id, outcome):
        r = float(outcome["reliability"])
        return 100.0 * PAYOFF * max(r, 1.0 - r)

    def state_digest(self):
        return "tampered-utility"


def test_D_changed_terminal_utility_is_refused_despite_same_charter():
    """Measured pre-fix: +0.0 silently became +891.0."""
    evaluator, _ = stack()
    snapshot = basis(evaluator)
    R1 = decide(evaluator, snapshot, rid="D")
    assert R1.scores[0].total == 0.0

    tampered = objective(TamperedUtility())
    assert tampered.utility_id == "toy.confidence_payoff"
    assert tampered.utility_version == "1"          # label unchanged
    assert snapshot.charter_version == CHARTER      # charter unchanged

    R2 = decide(evaluator, snapshot, tampered, rid="D")
    assert R2.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert R2.scores == ()
    assert any(
        c.field == "terminal_utility:toy.confidence_payoff"
        for c in R2.coherence.conflicts
    )


def test_D2_opaque_terminal_utility_makes_formal_scoring_unavailable():
    """No state_digest() means no identifiable semantics. Fail closed."""

    class OpaqueUtility:
        utility_id = "toy.confidence_payoff"
        utility_version = "1"

        def expected_utility(self, snapshot, decision_id):
            p = float(snapshot.metadata.get("confidence", PRIOR))
            return PAYOFF * max(p, 1.0 - p)

        def expected_utility_after(self, snapshot, decision_id, outcome):
            r = float(outcome["reliability"])
            return PAYOFF * max(r, 1.0 - r)

    evaluator, _ = stack()
    opaque = objective(OpaqueUtility())
    snapshot = basis(evaluator, opaque)

    rec = decide(evaluator, snapshot, opaque, rid="D2")
    assert rec.outcome is RecommendationOutcome.DECISION_BASIS_UNVERIFIED
    assert rec.scores == ()
    assert rec.dependency_manifest.is_executable is False
    assert any(
        "terminal_utility" in u and "cannot identify" in u
        for u in rec.coherence.unverified
    )
    # No identity was fabricated to make it work.
    pinned = next(
        d
        for d in snapshot.decision_basis
        if d.kind is DependencyKind.TERMINAL_UTILITY
    )
    assert pinned.state_digest == ""
    assert pinned.is_pinned is False

    # ...and audit replay is entirely unaffected.
    assert audit_replay(rec).outcome is ReplayOutcome.AUDIT_ONLY


# =====================================================================
# E. Outcome model changes
# =====================================================================

class TamperedOutcomeModel(ToyOutcomeModel):
    def conditional_success_utility_gain(self, candidate, snapshot, objective_):
        base = super().conditional_success_utility_gain(
            candidate, snapshot, objective_
        )
        return dataclasses.replace(base, value=base.value * 10.0)

    def dependency_identity(self):
        return dataclasses.replace(
            super().dependency_identity(), state_digest="tampered-outcome"
        )


def test_E_changed_outcome_model_is_refused():
    """Measured pre-fix: +0.0 silently became +36.0."""
    evaluator, model = stack()
    snapshot = basis(evaluator)
    assert decide(evaluator, snapshot, rid="E").scores[0].total == 0.0

    tampered, _ = stack(outcome=TamperedOutcomeModel(), model=model)
    rec = decide(tampered, snapshot, rid="E")
    assert rec.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert rec.scores == ()
    assert any(
        c.field.startswith("outcome_model:") for c in rec.coherence.conflicts
    )


# =====================================================================
# F. CostTradeoff changes
# =====================================================================

def test_F_changed_cost_tradeoff_is_refused():
    """Measured pre-fix: +0.0 silently became +3.996. The lambda is a policy."""
    evaluator, model = stack()
    snapshot = basis(evaluator)
    assert decide(evaluator, snapshot, rid="F").scores[0].total == 0.0

    cheapened, _ = stack(
        tradeoff=CostTradeoff(
            rate=0.001,
            cost_unit="hour",
            utility_reference="toy/confidence-payoff/1",
            source="a different exchange rate",
        ),
        model=model,
    )
    rec = decide(cheapened, snapshot, rid="F")
    assert rec.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert rec.scores == ()
    fields = {c.field for c in rec.coherence.conflicts}
    assert "cost_tradeoff:cost_tradeoff" in fields
    assert "utility_policy:toy.policy" in fields   # the policy embeds it too


def test_F2_mutated_policy_state_is_refused_under_the_same_label():
    """policy_id/policy_version are labels; mutable state needs an identity."""
    evaluator, model = stack()
    snapshot = basis(evaluator)
    R1 = decide(evaluator, snapshot, rid="F2")

    mutated, _ = stack(model=model)
    object.__setattr__(
        mutated._engine._policy,
        "cost_tradeoff",
        CostTradeoff(
            rate=0.0,
            cost_unit="hour",
            utility_reference="toy/confidence-payoff/1",
            source="mutated in place",
        ),
    )
    R2 = decide(mutated, snapshot, rid="F2")
    assert R2.policy_id == R1.policy_id
    assert R2.policy_version == R1.policy_version
    assert R2.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert R2.scores == ()


# =====================================================================
# G. Determinism
# =====================================================================

def test_G_identical_basis_and_dependencies_are_deterministic():
    evaluator, _ = stack()
    snapshot = basis(evaluator)
    first = decide(evaluator, snapshot, rid="G")
    second = decide(evaluator, snapshot, rid="G")
    assert first.to_dict() == second.to_dict()
    assert first.coherence.status is CoherenceStatus.COHERENT


# =====================================================================
# H. A new basis on changed dependencies is legitimate
# =====================================================================

def test_H_new_basis_on_changed_dependencies_scores():
    """Every refusal above has the same remedy: pin a new basis."""
    evaluator, model = stack()
    old = basis(evaluator)
    assert decide(evaluator, old, rid="H").coherence.status is (
        CoherenceStatus.COHERENT
    )

    tampered, _ = stack(outcome=TamperedOutcomeModel(), model=model)
    assert decide(tampered, old, rid="H").outcome is (
        RecommendationOutcome.STATE_INCOHERENT
    )

    fresh = basis(tampered, snapshot_id="snap-basis-2")
    rec = decide(tampered, fresh, rid="H")
    assert rec.outcome is RecommendationOutcome.RECOMMEND_ACTION
    assert rec.coherence.status is CoherenceStatus.COHERENT
    assert rec.scores[0].total == 36.0
    assert fresh.digest != old.digest


def test_H2_pinning_cannot_manufacture_a_missing_identity():
    """A basis pinned around an opaque provider is still unverifiable."""

    class OpaqueOutcome:
        def __init__(self):
            self._inner = ToyOutcomeModel()

        def conditional_success_utility_gain(self, *a, **k):
            return self._inner.conditional_success_utility_gain(*a, **k)

        def conditional_failure_utility_gain(self, *a, **k):
            return self._inner.conditional_failure_utility_gain(*a, **k)

    evaluator, _ = stack(outcome=OpaqueOutcome())
    snapshot = basis(evaluator)          # pinning "succeeds"...
    rec = decide(evaluator, snapshot, rid="H2")
    # ...but it copied through an unpinnable identity rather than inventing one.
    assert rec.outcome is RecommendationOutcome.DECISION_BASIS_UNVERIFIED
    assert rec.scores == ()


# =====================================================================
# I. M4.2 and M4.3 protections remain intact
# =====================================================================

def test_I_m42_and_m43_suites_still_pass():
    for module in (M42, M43):
        names = [n for n in dir(module) if n.startswith("test_")]
        assert len(names) >= 15
        for name in sorted(names):
            getattr(module, name)()


def test_I2_executable_replay_of_a_verified_basis_reproduces():
    evaluator, _ = stack()
    snapshot = basis(evaluator)
    stored = decide(evaluator, snapshot, rid="I2")
    result = executable_replay(
        stored,
        evaluator=evaluator,
        candidates=CANDIDATES,
        snapshot=snapshot,
        objective=objective(),
        charter_version=CHARTER,
    )
    assert result.outcome is ReplayOutcome.REPRODUCED
    assert result.recomputed.coherence.status is CoherenceStatus.COHERENT


def test_I3_a_refusal_is_still_fully_auditable():
    evaluator, model = stack()
    snapshot = basis(evaluator)
    tampered, _ = stack(outcome=TamperedOutcomeModel(), model=model)
    refused = decide(tampered, snapshot, rid="I3")

    audit = audit_replay(refused)
    assert audit.outcome is ReplayOutcome.AUDIT_ONLY
    assert audit.was_recomputed is False
    reloaded = DecisionRecommendation.from_dict(
        json.loads(json.dumps(refused.to_dict()))
    )
    assert reloaded.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert reloaded.coherence.to_dict() == refused.coherence.to_dict()


# =====================================================================
# Structure of the guarantee
# =====================================================================

def test_a_record_cannot_carry_scores_with_an_unverified_basis():
    evaluator, _ = stack()
    snapshot = basis(evaluator)
    good = decide(evaluator, snapshot, rid="ok")
    bad = decide(evaluator, toy_snapshot(), rid="bad")
    assert bad.coherence.is_refusal

    _raises(ValueError, dataclasses.replace, good, coherence=bad.coherence)
    _raises(
        ValueError,
        dataclasses.replace,
        bad,
        outcome=RecommendationOutcome.STOP_PROPOSAL,
        scores=good.scores,
    )


def test_terminal_objective_unavailable_outranks_a_basis_finding():
    """The more specific diagnosis wins, and the finding still travels."""
    evaluator, _ = stack()
    unavailable = resolve_terminal_objective(toy_charter(), None)
    rec = decide(evaluator, toy_snapshot(), unavailable, rid="obj")
    assert rec.outcome is RecommendationOutcome.TERMINAL_OBJECTIVE_UNAVAILABLE
    assert rec.scores == ()
    assert rec.coherence.status is CoherenceStatus.BASIS_UNVERIFIED


def test_coherent_cannot_leave_a_blocking_dependency_unverified():
    from src.engcore.sria.decision import CoherenceReport

    _raises(
        ValueError,
        CoherenceReport,
        status=CoherenceStatus.COHERENT,
        unverified=("outcome_model:x: cannot identify",),
    )
    _raises(
        ValueError,
        CoherenceReport,
        status=CoherenceStatus.BASIS_UNVERIFIED,
    )


def test_not_declared_labels_do_not_block_a_verified_basis():
    """Absent optional labels are informational, never blocking (no over-hash)."""
    evaluator, _ = stack()
    snapshot = basis(evaluator)
    rec = decide(evaluator, snapshot, rid="nd")
    assert rec.coherence.status is CoherenceStatus.COHERENT
    assert rec.coherence.not_declared          # e.g. failure_dataset_id
    assert rec.coherence.unverified == ()


def test_basis_pinned_but_unused_dependency_is_a_mismatch():
    evaluator, _ = stack()
    snapshot = basis(evaluator)
    extra = dataclasses.replace(
        snapshot,
        decision_basis=snapshot.decision_basis
        + (
            dataclasses.replace(
                snapshot.decision_basis[0],
                dependency_id="ghost.model",
                state_digest="ghost",
            ),
        ),
    )
    rec = decide(evaluator, extra, rid="ghost")
    assert rec.outcome is RecommendationOutcome.STATE_INCOHERENT
    conflict = next(
        c for c in rec.coherence.conflicts if "ghost.model" in c.field
    )
    assert conflict.executed_value == "<absent>"
    assert "not used to score" in conflict.detail


def test_decision_basis_survives_serialization():
    from src.engcore.sria.decision import BeliefSnapshot

    evaluator, _ = stack()
    snapshot = basis(evaluator)
    reloaded = BeliefSnapshot.from_dict(json.loads(json.dumps(snapshot.to_dict())))
    assert reloaded.digest == snapshot.digest
    assert len(reloaded.decision_basis) == len(snapshot.decision_basis)
    assert check_state_coherence(
        reloaded,
        evaluator.build_manifest(
            candidates=CANDIDATES,
            snapshot=reloaded,
            objective=objective(),
            charter_version=CHARTER,
        ),
    ).status is CoherenceStatus.COHERENT


def test_duplicate_basis_keys_are_rejected():
    evaluator, _ = stack()
    snapshot = basis(evaluator)
    _raises(
        ValueError,
        dataclasses.replace,
        snapshot,
        decision_basis=snapshot.decision_basis + (snapshot.decision_basis[0],),
    )


def test_provisional_mode_is_reserved_not_implemented():
    """No escape hatch exists that would make BASIS_UNVERIFIED optional."""
    assert PROVISIONAL_DECISION_MODE_RESERVED is True
    assert not any(
        "provisional" in o.value or "exploratory" in o.value
        for o in RecommendationOutcome
    )


# =====================================================================
# 8. The predeclared benchmark is unchanged
# =====================================================================

def test_original_benchmark_unchanged_after_m44():
    expected = {
        "A_cheap_loses_to_informative": ("expensive_strong", "expensive_strong"),
        "B_expensive_rejected_for_marginal_gain": ("cheap_strong", "costly_marginal"),
        "NULL_both_agree": ("strong_cheap", "strong_cheap"),
    }
    for name, spec in SCENARIOS.items():
        recommendation = evaluate(spec["candidates"], rid=f"rec44-{name}")
        assert recommendation.coherence.status is CoherenceStatus.COHERENT
        sria = recommendation.chosen_action_id
        info = information_only_ranking(recommendation.scores)[0].action_id
        assert (sria, info) == expected[name], name
        for score in recommendation.scores:
            candidate = next(
                c for c in spec["candidates"] if c.action_id == score.action_id
            )
            assert abs(score.total - ground_truth_net_value(candidate)) < 1e-9


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M4.4 — formal decision basis audit")
    print("=" * 72)
    failures = 0
    tests = _all_tests()
    for name, test in tests:
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    print("=" * 72)
    if failures:
        print(f"M4.4 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M4.4 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
