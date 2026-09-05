"""SRIA V0.1 M4.3 — decision state coherence audit.

Runs under pytest, and standalone via ``python -m tests.test_sria_m43_coherence``.

The property under test:

    Formal decision scoring uses an immutable, internally coherent
    scientific/computational state. A changed computational calibration
    requires a new snapshot before it may influence a new formal
    recommendation.

Before this module existed, the normal ``evaluate()`` path scored a frozen
snapshot against a refit cost model and emitted an ordinary ``STOP_PROPOSAL``:
the same snapshot digest produced totals of +0.0 and then -396.0. That measured
failure is reproduced here as a regression test.
"""

from __future__ import annotations

import dataclasses
import json
import sys

from src.engcore.scientific import Quantity
from src.engcore.scientific.ir.values import IntegerValue
from src.engcore.sria import ExecutorType, ResearchAction
from src.engcore.sria.calibration import CostModel
from src.engcore.sria.calibration.critic import CalibrationVerdict
from src.engcore.sria.decision import (
    ActionFamily,
    ActionProposal,
    AtomicAction,
    CoherenceConflict,
    CoherenceReport,
    CoherenceStatus,
    CompositeAction,
    CostAggregation,
    DecisionRecommendation,
    ExecutionOrder,
    OutcomeDependence,
    RecommendationOutcome,
    ReplayOutcome,
    calibration_state_for,
    candidate_decision_identity,
    pin_decision_basis,
    candidate_set_digest,
    check_state_coherence,
)

from tests.sria_m4_benchmark import (
    ToyFailureSupplier,
    ground_truth_net_value,
    toy_snapshot,
)
from tests.test_sria_m4_decision import SCENARIOS, evaluate
from tests.test_sria_m42_replay import (
    CANDIDATES,
    GOOD,
    POOR,
    build_stack,
    decide,
    objective,
    replay,
    training,
)
import tests.test_sria_m42_replay as M42


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


CHARTER = "1"


def pinned_snapshot(evaluator, *, snapshot_id="snap-pinned", base=None):
    """Mint a snapshot pinned to the dependencies that would score it.

    This is the legitimate way to make a decision on the current models: take a
    *new* snapshot against them. It is exactly what a caller must do after a
    refit instead of reusing an old snapshot. Since M4.4 it pins the whole
    decision basis, not only the calibration half.
    """
    base = base if base is not None else toy_snapshot(snapshot_id)
    manifest = evaluator.build_manifest(
        candidates=CANDIDATES,
        snapshot=base,
        objective=objective(),
        charter_version=CHARTER,
    )
    return pin_decision_basis(base, manifest)


# =====================================================================
# A. Coherent state evaluates
# =====================================================================

def test_A_snapshot_A_with_model_A_evaluates():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)

    assert snapshot.calibration.pins_fitted_state is True

    rec = decide(evaluator, snapshot, rid="A", charter_version=CHARTER)
    assert rec.outcome is not RecommendationOutcome.STATE_INCOHERENT
    assert rec.coherence.status is CoherenceStatus.COHERENT
    assert rec.is_state_coherent is True
    assert rec.coherence.conflicts == ()
    assert "cost_model_state_digest" in rec.coherence.checked
    assert "failure_model_state_digest" in rec.coherence.checked
    assert rec.scores[0].component("expected_cost").value == 4.0


# =====================================================================
# B. The measured pre-fix attack, now a regression
# =====================================================================

def test_B_stale_snapshot_with_refit_model_refuses():
    """The exact failure measured before M4.3: +0.0 silently became -396.0.

    The refit keeps the same dataset label, which is the pure staleness case:
    nothing about the model's *identity* changed, only its fitted state.
    """
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)

    R1 = decide(evaluator, snapshot, rid="R", charter_version=CHARTER)
    assert R1.coherence.status is CoherenceStatus.COHERENT
    assert R1.scores[0].total == 0.0

    # The live cost model moves. The snapshot does not.
    model.fit(training(400.0), dataset_id="corpus-v1")

    R2 = decide(evaluator, snapshot, rid="R", charter_version=CHARTER)
    assert R2.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert R2.coherence.status is CoherenceStatus.STALE_SNAPSHOT
    assert R2.scores == ()                      # nothing was scored at all
    assert R2.chosen_action_id == ""
    assert R2.is_state_coherent is False
    fields = {c.field for c in R2.coherence.conflicts}
    # Caught twice over: once at the decision-basis level (M4.4) and once by
    # the calibration cross-check (M4.3).
    assert fields == {"cost_model:cost.hierarchical", "cost_model_state_digest"}
    for conflict in R2.coherence.conflicts:
        assert conflict.snapshot_value != conflict.executed_value
    assert "pin a new decision basis" in R2.reason

    # R1 is untouched and still says what it said.
    assert R1.scores[0].total == 0.0


def test_B2_refit_onto_a_new_dataset_is_the_stronger_refusal():
    """The originally measured run also changed dataset id.

    Identity moved as well as fitted state, so the verdict escalates from
    STALE_SNAPSHOT to DEPENDENCY_MISMATCH — and both conflicts are named.
    """
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)
    decide(evaluator, snapshot, rid="R", charter_version=CHARTER)

    model.fit(training(400.0), dataset_id="corpus-v2")
    R2 = decide(evaluator, snapshot, rid="R", charter_version=CHARTER)

    assert R2.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert R2.coherence.status is CoherenceStatus.DEPENDENCY_MISMATCH
    fields = {c.field for c in R2.coherence.conflicts}
    assert fields == {
        "cost_model:cost.hierarchical",   # basis-level: identity moved
        "cost_dataset_id",                # calibration cross-check
        "cost_model_state_digest",
    }


# =====================================================================
# C. A new snapshot on the new models is legitimate
# =====================================================================

def test_C_new_snapshot_with_new_model_evaluates():
    """Deciding on updated calibration is allowed — it needs a new snapshot."""
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    old = pinned_snapshot(evaluator, snapshot_id="snap-A")

    model.fit(training(400.0), dataset_id="corpus-v2")
    assert (
        decide(evaluator, old, rid="stale", charter_version=CHARTER).outcome
        is RecommendationOutcome.STATE_INCOHERENT
    )

    fresh = pinned_snapshot(evaluator, snapshot_id="snap-A2")
    assert fresh.digest != old.digest
    assert (
        fresh.calibration.cost_model_state_digest
        != old.calibration.cost_model_state_digest
    )

    rec = decide(evaluator, fresh, rid="fresh", charter_version=CHARTER)
    assert rec.outcome is not RecommendationOutcome.STATE_INCOHERENT
    assert rec.coherence.status is CoherenceStatus.COHERENT
    assert rec.scores[0].component("expected_cost").value == 400.0000000000001


# =====================================================================
# D. Determinism is preserved
# =====================================================================

def test_D_same_state_gives_the_same_recommendation():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)

    first = decide(evaluator, snapshot, rid="D", charter_version=CHARTER)
    second = decide(evaluator, snapshot, rid="D", charter_version=CHARTER)
    assert first.to_dict() == second.to_dict()
    assert first.coherence.to_dict() == second.coherence.to_dict()


# =====================================================================
# E. Candidate identity is content, not the action id
# =====================================================================

def action(
    *,
    action_id="same-id",
    executor=ExecutorType.SIMULATION,
    target="theta",
    parameters=None,
    cost=1.0,
    context_ref="ctx-1",
    metadata=None,
    family=ActionFamily.EXPLORE,
    rationale="baseline",
    assumptions=(),
    fidelity="rung-1",
    observable="qoi.theta",
    failure_causes=("numerical",),
):
    return AtomicAction(
        action=ResearchAction(
            action_id=action_id,
            executor_type=executor,
            target_ref=target,
            parameters=(
                parameters
                if parameters is not None
                else {"mesh": IntegerValue(32)}
            ),
            expected_cost={"compute": Quantity(cost, "hour")},
            context_ref=context_ref,
            metadata=metadata if metadata is not None else {"reliability": 0.9},
        ),
        proposal=ActionProposal(
            family=family,
            target_ref=target,
            rationale=rationale,
            assumptions=tuple(assumptions),
            required_fidelity=fidelity,
            expected_observable=observable,
            informative_failure_causes=tuple(failure_causes),
        ),
    )


#: Every mutation is decision-relevant: scoring, hard feasibility, cost
#: aggregation or the failure-VoI channel reads each of these.
DECISION_RELEVANT_MUTATIONS = {
    "executor": {"executor": ExecutorType.PHYSICAL},
    "target_ref": {"target": "phi"},
    "parameters": {"parameters": {"mesh": IntegerValue(64)}},
    "expected_cost": {"cost": 2.0},
    "context_ref": {"context_ref": "ctx-2"},
    "metadata": {"metadata": {"reliability": 0.5}},
    "family": {"family": ActionFamily.VALIDATE},
    "assumptions": {"assumptions": ("steady state",)},
    "required_fidelity": {"fidelity": "rung-2"},
    "expected_observable": {"observable": "qoi.phi"},
    "informative_failure_causes": {"failure_causes": ("solver",)},
}


def test_E_same_action_id_different_payload_changes_the_digest():
    """A reused action_id must never collapse two different actions."""
    base = action()
    base_digest = candidate_set_digest((base,))

    for label, mutation in DECISION_RELEVANT_MUTATIONS.items():
        variant = action(**mutation)
        assert variant.action_id == base.action_id, label
        assert candidate_set_digest((variant,)) != base_digest, (
            f"changing {label} did not change the candidate-set digest"
        )


def test_E2_narrative_only_change_does_not_change_the_digest():
    """Free-text rationale is provenance, not a decision.

    Two candidates that differ only in prose score identically, so they are the
    same decision. This is the one field deliberately left out of the identity
    — recorded here so the choice is visible rather than accidental.
    """
    base = action(rationale="because the mesh is coarse")
    reworded = action(rationale="rewritten by a reviewer, same experiment")
    assert base.proposal.rationale != reworded.proposal.rationale
    assert candidate_set_digest((base,)) == candidate_set_digest((reworded,))

    identity = candidate_decision_identity(base)
    assert "rationale" not in identity["proposal"]
    # ...but everything scoring reads survives the projection.
    for key in (
        "family",
        "target_ref",
        "assumptions",
        "required_fidelity",
        "expected_observable",
        "informative_failure_causes",
    ):
        assert key in identity["proposal"], key
    for key in (
        "action_id",
        "executor_type",
        "target_ref",
        "parameters",
        "expected_cost",
        "context_ref",
        "metadata",
    ):
        assert key in identity["action"], key


# =====================================================================
# F. Composite semantics
# =====================================================================

def composite(
    *,
    members=None,
    order=ExecutionOrder.UNSPECIFIED,
    aggregation=CostAggregation.SUM,
    declared_total=None,
    dependence=OutcomeDependence.UNDECLARED,
    dependence_rationale="",
    failure_dependencies=(),
):
    return CompositeAction(
        composite_id="pair",
        proposal=ActionProposal(
            family=ActionFamily.DISCRIMINATE,
            target_ref="theta",
            rationale="paired design",
        ),
        members=members
        if members is not None
        else (action(action_id="m1"), action(action_id="m2", cost=3.0)),
        order=order,
        cost_aggregation=aggregation,
        declared_total_cost=declared_total,
        outcome_dependence=dependence,
        dependence_rationale=dependence_rationale,
        failure_dependencies=tuple(failure_dependencies),
    )


def test_F_composite_semantics_change_the_digest():
    base = composite()
    base_digest = candidate_set_digest((base,))

    variants = {
        "member set": composite(
            members=(action(action_id="m1"), action(action_id="m3", cost=3.0))
        ),
        "member order": composite(
            members=(action(action_id="m2", cost=3.0), action(action_id="m1"))
        ),
        "execution order": composite(order=ExecutionOrder.PARALLEL),
        "cost aggregation": composite(aggregation=CostAggregation.MAX),
        "declared total": composite(
            aggregation=CostAggregation.DECLARED, declared_total=7.0
        ),
        "outcome dependence": composite(
            dependence=OutcomeDependence.INDEPENDENT_DECLARED,
            dependence_rationale="separate solvers, separate seeds",
        ),
        "failure dependencies": composite(
            failure_dependencies=(("m1", "m2"),)
        ),
    }
    for label, variant in variants.items():
        assert candidate_set_digest((variant,)) != base_digest, label


def test_F2_member_order_changes_identity_even_when_scoring_ignores_it():
    """Member order stays in the identity on purpose.

    The current engine aggregates member reliability with ``max`` and cost with
    ``sum``, both order-insensitive, so a reordered composite scores the same
    today. Keeping order in the digest can therefore cause a replay refusal
    where none was strictly necessary — a false refusal a human can inspect,
    versus a false ``REPRODUCED`` nobody would ever see. The asymmetry decides
    it.
    """
    a = composite(members=(action(action_id="m1"), action(action_id="m2", cost=3.0)))
    b = composite(members=(action(action_id="m2", cost=3.0), action(action_id="m1")))
    assert candidate_set_digest((a,)) != candidate_set_digest((b,))

    # The dependence rationale, by contrast, is narrative and is excluded.
    c = composite(
        dependence=OutcomeDependence.DEPENDENT_DECLARED,
        dependence_rationale="shared mesh generator",
    )
    d = composite(
        dependence=OutcomeDependence.DEPENDENT_DECLARED,
        dependence_rationale="worded differently, same claim",
    )
    assert candidate_set_digest((c,)) == candidate_set_digest((d,))


# =====================================================================
# G. Candidate-set order is irrelevant
# =====================================================================

def test_G_reordering_the_candidate_set_preserves_the_digest():
    """Ranking breaks ties on action id, so set order carries no meaning."""
    assert candidate_set_digest((GOOD, POOR)) == candidate_set_digest((POOR, GOOD))

    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)
    forward = evaluator.evaluate(
        recommendation_id="G",
        candidates=(GOOD, POOR),
        snapshot=snapshot,
        objective=objective(),
        charter_version=CHARTER,
    )
    reverse = evaluator.evaluate(
        recommendation_id="G",
        candidates=(POOR, GOOD),
        snapshot=snapshot,
        objective=objective(),
        charter_version=CHARTER,
    )
    assert (
        forward.dependency_manifest.candidate_set_digest
        == reverse.dependency_manifest.candidate_set_digest
    )
    assert forward.outcome is reverse.outcome
    assert forward.chosen_action_id == reverse.chosen_action_id


# =====================================================================
# H. M4.2 replay behaviour is unchanged
# =====================================================================

def test_H_m42_replay_suite_still_passes():
    """Every M4.2 guarantee re-run under the M4.3 changes."""
    names = [n for n in dir(M42) if n.startswith("test_")]
    assert len(names) >= 15
    for name in sorted(names):
        getattr(M42, name)()


def test_H2_executable_replay_of_a_coherent_decision_still_reproduces():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)
    stored = decide(evaluator, snapshot, rid="H2", charter_version=CHARTER)
    assert stored.coherence.status is CoherenceStatus.COHERENT

    result = replay(evaluator, stored, snapshot, charter_version=CHARTER)
    assert result.outcome is ReplayOutcome.REPRODUCED
    assert result.recomputed.coherence.status is CoherenceStatus.COHERENT


# =====================================================================
# Other coherence overlaps
# =====================================================================

def test_wrong_model_identity_is_a_dependency_mismatch_not_staleness():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)
    misnamed = dataclasses.replace(
        snapshot,
        calibration=dataclasses.replace(
            snapshot.calibration, cost_model_id="some.other.cost.model"
        ),
    )
    rec = decide(evaluator, misnamed, rid="mis", charter_version=CHARTER)
    assert rec.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert rec.coherence.status is CoherenceStatus.DEPENDENCY_MISMATCH
    assert any(c.field == "cost_model_id" for c in rec.coherence.conflicts)


def test_dataset_change_is_detected():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)
    assert snapshot.calibration.cost_dataset_id == "corpus-v1"
    moved = dataclasses.replace(
        snapshot,
        calibration=dataclasses.replace(
            snapshot.calibration, cost_dataset_id="corpus-v9"
        ),
    )
    rec = decide(evaluator, moved, rid="ds", charter_version=CHARTER)
    assert rec.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert rec.scores == ()
    assert rec.coherence.status is CoherenceStatus.DEPENDENCY_MISMATCH
    assert any(c.field == "cost_dataset_id" for c in rec.coherence.conflicts)


def test_charter_version_contradiction_is_detected():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)
    assert snapshot.charter_version == "1"

    rec = decide(evaluator, snapshot, rid="ch", charter_version="2")
    assert rec.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert rec.coherence.status is CoherenceStatus.DEPENDENCY_MISMATCH
    assert any(c.field == "charter_version" for c in rec.coherence.conflicts)


def test_signature_version_contradiction_is_detected():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)
    old = dataclasses.replace(
        snapshot,
        calibration=dataclasses.replace(
            snapshot.calibration, structure_signature_version=0
        ),
    )
    rec = decide(evaluator, old, rid="sig", charter_version=CHARTER)
    assert rec.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert rec.scores == ()
    assert rec.coherence.status is CoherenceStatus.DEPENDENCY_MISMATCH
    assert any(
        c.field == "structure_signature_version" for c in rec.coherence.conflicts
    )


def test_pinned_state_against_an_unpinnable_supplier_fails_closed():
    """A pin nobody can confirm is a mismatch, never a pass."""
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)

    class OpaqueFailureSupplier:
        def __init__(self) -> None:
            self._inner = ToyFailureSupplier(0.0, CalibrationVerdict.TRUSTED)

        def computational_failure_probability(self, *args, **kwargs):
            return self._inner.computational_failure_probability(*args, **kwargs)

    opaque = build_stack(model)
    opaque._engine._failure = OpaqueFailureSupplier()

    rec = decide(evaluator=opaque, snapshot=snapshot, rid="op", charter_version=CHARTER)
    assert rec.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert rec.coherence.status is CoherenceStatus.DEPENDENCY_MISMATCH
    conflict = next(
        c for c in rec.coherence.conflicts if c.field == "failure_model_state_digest"
    )
    assert conflict.executed_value == "<unpinnable>"


def test_unpinned_snapshot_refuses_formal_scoring():
    """M4.3 evaluated this with a caveat. M4.4 refuses it.

    A line of prose in ``degraded_assumptions`` is not formal verification, and
    treating it as equivalent was the weakness M4.4 closed.
    """
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = toy_snapshot()          # declares ids, pins no fitted state
    assert snapshot.calibration.pins_fitted_state is False
    assert snapshot.pins_decision_basis is False

    rec = decide(evaluator, snapshot, rid="un", charter_version=CHARTER)
    assert rec.outcome is RecommendationOutcome.DECISION_BASIS_UNVERIFIED
    assert rec.coherence.status is CoherenceStatus.BASIS_UNVERIFIED
    assert rec.scores == ()
    assert rec.is_state_coherent is False
    assert "decision_basis: never pinned" in rec.coherence.unverified
    assert rec.degraded_assumptions == ()


def test_manifest_built_for_another_snapshot_is_rejected():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)
    other = evaluator.build_manifest(
        candidates=CANDIDATES,
        snapshot=toy_snapshot("a-different-snapshot"),
        objective=objective(),
        charter_version=CHARTER,
    )
    report = check_state_coherence(snapshot, other)
    assert report.status is CoherenceStatus.DEPENDENCY_MISMATCH
    assert any(c.field == "snapshot_digest" for c in report.conflicts)


def test_a_record_cannot_assert_a_contradiction_and_a_ranking():
    """The recommendation type itself forbids the incoherent combination."""
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)
    good = decide(evaluator, snapshot, rid="ok", charter_version=CHARTER)

    refusing = CoherenceReport(
        status=CoherenceStatus.STALE_SNAPSHOT,
        checked=("cost_model_state_digest",),
        conflicts=(
            CoherenceConflict(
                field="cost_model_state_digest",
                snapshot_value="aaa",
                executed_value="bbb",
                kind=CoherenceStatus.STALE_SNAPSHOT,
            ),
        ),
    )
    # A refusing verdict may not accompany an ordinary outcome...
    _raises(
        ValueError,
        dataclasses.replace,
        good,
        coherence=refusing,
    )
    # ...nor may STATE_INCOHERENT be claimed without conflicts to rest on.
    _raises(
        ValueError,
        dataclasses.replace,
        good,
        outcome=RecommendationOutcome.STATE_INCOHERENT,
        chosen_action_id="",
        scores=(),
        coherence=None,
    )
    # ...and a coherent verdict may not carry conflicts.
    _raises(
        ValueError,
        CoherenceReport,
        status=CoherenceStatus.COHERENT,
        conflicts=refusing.conflicts,
    )


def test_coherence_report_round_trips_through_the_recommendation():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)

    for rid, snap in (("ok", snapshot),):
        rec = decide(evaluator, snap, rid=rid, charter_version=CHARTER)
        reloaded = DecisionRecommendation.from_dict(
            json.loads(json.dumps(rec.to_dict()))
        )
        assert reloaded.coherence.to_dict() == rec.coherence.to_dict()
        assert reloaded.is_state_coherent == rec.is_state_coherent

    model.fit(training(400.0), dataset_id="corpus-v1")
    refused = decide(evaluator, snapshot, rid="bad", charter_version=CHARTER)
    reloaded = DecisionRecommendation.from_dict(
        json.loads(json.dumps(refused.to_dict()))
    )
    assert reloaded.outcome is RecommendationOutcome.STATE_INCOHERENT
    assert reloaded.coherence.status is CoherenceStatus.STALE_SNAPSHOT
    assert {c.field for c in reloaded.coherence.conflicts} == {
        c.field for c in refused.coherence.conflicts
    }


def test_snapshot_state_pins_survive_serialization():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = pinned_snapshot(evaluator)
    from src.engcore.sria.decision import BeliefSnapshot

    reloaded = BeliefSnapshot.from_dict(json.loads(json.dumps(snapshot.to_dict())))
    assert reloaded.digest == snapshot.digest
    assert reloaded.calibration.pin == snapshot.calibration.pin
    assert (
        reloaded.calibration.cost_model_state_digest
        == snapshot.calibration.cost_model_state_digest
    )


# =====================================================================
# 8. The predeclared benchmark is unchanged
# =====================================================================

def test_original_benchmark_unchanged_after_m43():
    from src.engcore.sria.decision import information_only_ranking

    expected = {
        "A_cheap_loses_to_informative": ("expensive_strong", "expensive_strong"),
        "B_expensive_rejected_for_marginal_gain": ("cheap_strong", "costly_marginal"),
        "NULL_both_agree": ("strong_cheap", "strong_cheap"),
    }
    for name, spec in SCENARIOS.items():
        recommendation = evaluate(spec["candidates"], rid=f"rec43-{name}")
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
    print("SRIA V0.1 M4.3 — decision state coherence audit")
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
        print(f"M4.3 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M4.3 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
