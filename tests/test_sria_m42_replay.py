"""SRIA V0.1 M4.2 â€” executable replay audit.

Runs under pytest, and standalone via ``python -m tests.test_sria_m42_replay``.

The property under test:

    A frozen decision snapshot never silently consumes a newer or different
    computational model. Either every pinned dependency resolves exactly and
    the decision re-executes deterministically, or executable replay is
    refused.

Before this module existed, the same snapshot re-scored after a refit produced
a cost of 4.0 and then 400.0 with no signal whatsoever. That measured failure
is reproduced here as a regression test.
"""

from __future__ import annotations

import json
import sys

from src.engcore.sria import Disposition
from src.engcore.sria.calibration import (
    CalibrationMemory,
    CalibrationMemoryEntry,
    ComputationalLearningRecord,
    Consumer,
    CostModel,
    MemoryKind,
    structure_for,
)
from src.engcore.sria.calibration.critic import CalibrationVerdict
from src.engcore.sria.calibration.ingest import CAMPAIGN_ENVIRONMENT
from src.engcore.sria.decision import (
    ActionFamily,
    CalibrationCostSupplier,
    CandidateEvaluator,
    DecisionRecommendation,
    DependencyIdentity,
    DependencyKind,
    ExecutionDependencyManifest,
    ReplayMode,
    ReplayOutcome,
    UtilityEngine,
    UtilityPolicy,
    audit_replay,
    cost_model_state_digest,
    executable_replay,
    information_only_ranking,
)

from tests.sria_m4_benchmark import (
    ToyFailureSupplier,
    ToyOutcomeModel,
    ToyTerminalUtility,
    ground_truth_net_value,
    toy_action,
    toy_cost_tradeoff,
    toy_snapshot,
)
from tests.test_sria_m4_decision import SCENARIOS, evaluate, objective


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


GOOD = toy_action("good", family=ActionFamily.EXPLORE, reliability=0.9, cost=0.5)
POOR = toy_action("poor", family=ActionFamily.EXPLORE, reliability=0.51, cost=5.0)
CANDIDATES = (GOOD, POOR)


def training(cost: float, n: int = 6):
    return [
        ComputationalLearningRecord(
            record_id=f"r{i}-{cost}",
            structure=structure_for(5, 100),
            environment=CAMPAIGN_ENVIRONMENT,
            solver_identity=("solverX", "v1"),
            disposition=Disposition.SUCCESS,
            realized_cost=cost,
            group_key=f"g{i}",
        )
        for i in range(n)
    ]


def record_builder(member, snapshot):
    return ComputationalLearningRecord(
        record_id=member.action_id,
        structure=structure_for(5, 100),
        environment=CAMPAIGN_ENVIRONMENT,
        solver_identity=("solverX", "v1"),
        disposition=Disposition.SUCCESS,
        group_key="query",
    )


def build_stack(model):
    supplier = CalibrationCostSupplier(
        model,
        record_builder=record_builder,
        verdict=CalibrationVerdict.TRUSTED,
        cost_unit="hour",
    )
    engine = UtilityEngine(
        policy=UtilityPolicy(policy_id="toy.policy", cost_tradeoff=toy_cost_tradeoff()),
        outcome_model=ToyOutcomeModel(),
        cost_supplier=supplier,
        failure_supplier=ToyFailureSupplier(0.0, CalibrationVerdict.TRUSTED),
    )
    return CandidateEvaluator(engine)


def basis(evaluator, snapshot=None, *, charter_version="1"):
    """Pin a snapshot to the stack that will score it (M4.4).

    Formal scoring now requires a verified decision basis, so replay tests
    start from one â€” which is also what makes the replay comparisons meaningful
    rather than comparing two refusals.
    """
    from src.engcore.sria.decision import pin_decision_basis

    snapshot = snapshot if snapshot is not None else toy_snapshot()
    return pin_decision_basis(
        snapshot,
        evaluator.build_manifest(
            candidates=CANDIDATES,
            snapshot=snapshot,
            objective=objective(),
            charter_version=charter_version,
        ),
    )


def decide(evaluator, snapshot, *, rid="R", charter_version="1"):
    return evaluator.evaluate(
        recommendation_id=rid,
        candidates=CANDIDATES,
        snapshot=snapshot,
        objective=objective(),
        charter_version=charter_version,
    )


def replay(evaluator, stored, snapshot, *, charter_version="1"):
    return executable_replay(
        stored,
        evaluator=evaluator,
        candidates=CANDIDATES,
        snapshot=snapshot,
        objective=objective(),
        charter_version=charter_version,
    )


# =====================================================================
# A. Same frozen dependencies reproduce exactly
# =====================================================================

def test_A_identical_dependencies_reproduce_the_recommendation():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = basis(evaluator)

    stored = decide(evaluator, snapshot)
    assert stored.dependency_manifest is not None
    assert stored.is_executable_replayable is True

    result = replay(evaluator, stored, snapshot)
    assert result.mode is ReplayMode.EXECUTABLE_REPLAY
    assert result.outcome is ReplayOutcome.REPRODUCED
    assert result.was_recomputed is True
    assert result.mismatches == ()
    assert (
        result.recomputed.scores[0].component("expected_cost").value
        == stored.scores[0].component("expected_cost").value
    )


# =====================================================================
# B. The measured pre-fix attack, now a regression
# =====================================================================

def test_B_refit_after_snapshot_does_not_silently_replay():
    """The exact failure measured before M4.2: 4.0 silently became 400.0."""
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = basis(evaluator)

    stored = decide(evaluator, snapshot)
    original_cost = stored.scores[0].component("expected_cost").value
    assert abs(original_cost - 4.0) < 1e-6

    # The live model moves under the frozen snapshot.
    model.fit(training(400.0), dataset_id="corpus-v2")

    result = replay(evaluator, stored, snapshot)
    assert result.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE
    assert result.was_recomputed is False
    assert result.recomputed is None
    assert any("cost_model" in m for m in result.mismatches)
    assert "refusing to recompute" in result.detail

    # The stored record is untouched and still says 4.0.
    assert stored.scores[0].component("expected_cost").value == original_cost


# =====================================================================
# C. Same version + dataset id, different fitted state
# =====================================================================

def test_C_same_labels_but_changed_fitted_state_is_detected():
    """A version label and a dataset id are not an identity."""
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = basis(evaluator)
    stored = decide(evaluator, snapshot)

    before_digest = cost_model_state_digest(model)
    before_version = model.model_version
    before_dataset = model.training_provenance["dataset_id"]

    # Refit on different data under the SAME dataset label and version.
    model.fit(training(40.0), dataset_id="corpus-v1")

    assert model.model_version == before_version
    assert model.training_provenance["dataset_id"] == before_dataset
    assert cost_model_state_digest(model) != before_digest, (
        "the state digest must change when the fitted cells change"
    )

    result = replay(evaluator, stored, snapshot)
    assert result.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE
    assert any("state" in m for m in result.mismatches)


# =====================================================================
# D. Unrelated calibration-memory activity does not disturb replay
# =====================================================================

def test_D_unrelated_memory_entries_do_not_break_executable_replay():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = basis(evaluator)
    stored = decide(evaluator, snapshot)

    # Record unrelated calibration memory. The fitted model is untouched.
    memory = CalibrationMemory()
    memory.record(
        CalibrationMemoryEntry(
            entry_id="unrelated-1",
            kind=MemoryKind.FIDELITY_OBSERVATION,
            model_version="other/1",
            dataset_id="some-other-corpus",
            payload={"note": "nothing to do with the pinned cost model"},
            consumed_by=(Consumer.ARCHIVE,),
        )
    )
    assert len(memory) == 1

    result = replay(evaluator, stored, snapshot)
    assert result.outcome is ReplayOutcome.REPRODUCED
    assert result.mismatches == ()


# =====================================================================
# E. A missing fitted model fails closed
# =====================================================================

def test_E_missing_model_yields_explicit_replay_unavailable():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = basis(evaluator)
    stored = decide(evaluator, snapshot)

    # A fresh, unfitted model stands in for "the old fitted state is gone".
    replacement = build_stack(CostModel())
    result = replay(replacement, stored, snapshot)
    assert result.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE
    assert result.recomputed is None
    assert result.mismatches


class OpaqueOutcomeModel:
    """An outcome model that cannot describe its own state.

    Scores exactly like the toy model but exposes no ``dependency_identity()``.
    Stands for any real learned component that has not been taught to identify
    itself: it must fail closed rather than be assumed stable.
    """

    def __init__(self) -> None:
        self._inner = ToyOutcomeModel()

    def conditional_success_utility_gain(self, *args, **kwargs):
        return self._inner.conditional_success_utility_gain(*args, **kwargs)

    def conditional_failure_utility_gain(self, *args, **kwargs):
        return self._inner.conditional_failure_utility_gain(*args, **kwargs)


def test_E2_unpinnable_dependency_blocks_executable_replay():
    """A component that cannot identify itself is never assumed stable."""
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    engine = UtilityEngine(
        policy=UtilityPolicy(policy_id="toy.policy", cost_tradeoff=toy_cost_tradeoff()),
        outcome_model=OpaqueOutcomeModel(),
        cost_supplier=CalibrationCostSupplier(
            model,
            record_builder=record_builder,
            verdict=CalibrationVerdict.TRUSTED,
            cost_unit="hour",
        ),
        failure_supplier=ToyFailureSupplier(0.0, CalibrationVerdict.TRUSTED),
    )
    evaluator = CandidateEvaluator(engine)
    snapshot = basis(evaluator)
    stored = decide(evaluator, snapshot)

    manifest = stored.dependency_manifest
    outcome_identity = next(
        d for d in manifest.dependencies if d.kind is DependencyKind.OUTCOME_MODEL
    )
    assert outcome_identity.restorable is False
    assert outcome_identity.state_digest == ""
    assert outcome_identity.is_pinned is False
    assert manifest.is_executable is False
    assert stored.is_executable_replayable is False
    assert "outcome_model" in " ".join(manifest.unpinnable)

    result = replay(evaluator, stored, snapshot)
    assert result.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE
    assert "cannot be pinned" in result.detail
    assert "Audit replay remains available" in result.detail

    # ...and the record is still fully auditable.
    assert audit_replay(stored).outcome is ReplayOutcome.AUDIT_ONLY


# =====================================================================
# F. Audit replay works regardless
# =====================================================================

def test_F_audit_replay_survives_when_executable_replay_cannot():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = basis(evaluator)
    stored = decide(evaluator, snapshot)
    original_cost = stored.scores[0].component("expected_cost").value

    model.fit(training(400.0), dataset_id="corpus-v2")
    assert (
        replay(evaluator, stored, snapshot).outcome
        is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE
    )

    audit = audit_replay(stored)
    assert audit.mode is ReplayMode.AUDIT_REPLAY
    assert audit.outcome is ReplayOutcome.AUDIT_ONLY
    assert audit.was_recomputed is False
    assert audit.stored.scores[0].component("expected_cost").value == original_cost
    assert "no scientific value was recomputed" in audit.detail

    # And it survives serialization â€” durability is the whole point.
    reloaded = DecisionRecommendation.from_dict(
        json.loads(json.dumps(stored.to_dict()))
    )
    audit2 = audit_replay(reloaded)
    assert audit2.stored.scores[0].component("expected_cost").value == original_cost
    assert reloaded.dependency_manifest.manifest_digest == (
        stored.dependency_manifest.manifest_digest
    )


# =====================================================================
# G. Stored values cannot be confused with recomputed ones
# =====================================================================

def test_G_stored_and_recomputed_scores_are_distinguishable():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = basis(evaluator)
    stored = decide(evaluator, snapshot)

    audit = audit_replay(stored)
    assert audit.was_recomputed is False
    assert audit.scores_are_historical is True
    assert audit.recomputed is None

    executed = replay(evaluator, stored, snapshot)
    assert executed.outcome is ReplayOutcome.REPRODUCED
    assert executed.was_recomputed is True
    assert executed.scores_are_historical is False
    assert executed.recomputed is not None

    # A refusal must never carry a recomputed result.
    from src.engcore.sria.decision import ReplayResult

    _raises(
        ValueError,
        ReplayResult,
        mode=ReplayMode.EXECUTABLE_REPLAY,
        outcome=ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE,
        stored=stored,
        recomputed=stored,
    )


# =====================================================================
# Manifest mechanics
# =====================================================================

def test_manifest_pins_snapshot_charter_and_candidates():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    snapshot = basis(evaluator)
    stored = decide(evaluator, snapshot, charter_version="1")

    other_charter = evaluator.build_manifest(
        candidates=CANDIDATES,
        snapshot=snapshot,
        objective=objective(),
        charter_version="2",
    )
    assert "campaign charter version differs" in other_charter.mismatches(
        stored.dependency_manifest
    )

    other_candidates = evaluator.build_manifest(
        candidates=(GOOD,),
        snapshot=snapshot,
        objective=objective(),
        charter_version="1",
    )
    assert "candidate set differs" in other_candidates.mismatches(
        stored.dependency_manifest
    )

    other_snapshot = evaluator.build_manifest(
        candidates=CANDIDATES,
        snapshot=toy_snapshot("snap-2"),
        objective=objective(),
        charter_version="1",
    )
    assert "belief snapshot differs" in other_snapshot.mismatches(
        stored.dependency_manifest
    )


def test_candidate_set_digest_is_order_independent():
    from src.engcore.sria.decision import candidate_set_digest

    assert candidate_set_digest((GOOD, POOR)) == candidate_set_digest((POOR, GOOD))
    assert candidate_set_digest((GOOD,)) != candidate_set_digest((GOOD, POOR))


def test_unpinned_identity_never_matches_itself():
    """An unpinnable dependency can never satisfy an equality check."""
    unpinned = DependencyIdentity(
        dependency_id="x", kind=DependencyKind.OUTCOME_MODEL, restorable=False
    )
    assert unpinned.is_pinned is False
    assert unpinned.matches(unpinned) is False

    pinned = DependencyIdentity(
        dependency_id="x",
        kind=DependencyKind.COST_MODEL,
        state_digest="abc",
    )
    assert pinned.matches(pinned) is True


def test_terminal_utility_is_marked_unrestorable_when_absent():
    """A utility that was never restored is not silently assumed present.

    ``TerminalObjective.from_dict`` deliberately cannot rebuild the callable,
    and nothing here pickles a function to make replay "work".
    """
    from src.engcore.sria.decision import TerminalObjective

    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)

    reloaded = TerminalObjective.from_dict(objective().to_dict())
    assert reloaded.is_available is False

    manifest = evaluator.build_manifest(
        candidates=CANDIDATES,
        snapshot=toy_snapshot(),
        objective=reloaded,
        charter_version="1",
    )
    utility = next(
        d for d in manifest.dependencies if d.kind is DependencyKind.TERMINAL_UTILITY
    )
    assert utility.restorable is False
    assert utility.state_digest == ""
    assert utility.is_pinned is False
    assert "audit replay only" in utility.detail
    assert manifest.is_executable is False


def test_live_terminal_utility_is_pinned_by_its_own_digest():
    """When the utility can describe itself, the pin is real â€” not invented."""
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    manifest = evaluator.build_manifest(
        candidates=CANDIDATES,
        snapshot=toy_snapshot(),
        objective=objective(),
        charter_version="1",
    )
    utility = next(
        d for d in manifest.dependencies if d.kind is DependencyKind.TERMINAL_UTILITY
    )
    assert utility.restorable is True
    assert utility.state_digest == ToyTerminalUtility().state_digest()
    assert utility.is_pinned is True
    assert "live utility callable present" in utility.detail


def test_manifest_round_trips():
    model = CostModel().fit(training(4.0), dataset_id="corpus-v1")
    evaluator = build_stack(model)
    stored = decide(evaluator, toy_snapshot())
    manifest = stored.dependency_manifest

    reloaded = ExecutionDependencyManifest.from_dict(
        json.loads(json.dumps(manifest.to_dict()))
    )
    assert reloaded.manifest_digest == manifest.manifest_digest
    assert reloaded.mismatches(manifest) == ()
    assert len(reloaded.dependencies) == len(manifest.dependencies)


# =====================================================================
# 8. The predeclared benchmark is unchanged
# =====================================================================

def test_original_benchmark_unchanged_after_m42():
    expected = {
        "A_cheap_loses_to_informative": ("expensive_strong", "expensive_strong"),
        "B_expensive_rejected_for_marginal_gain": ("cheap_strong", "costly_marginal"),
        "NULL_both_agree": ("strong_cheap", "strong_cheap"),
    }
    for name, spec in SCENARIOS.items():
        recommendation = evaluate(spec["candidates"], rid=f"rec42-{name}")
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
    print("SRIA V0.1 M4.2 â€” executable replay audit")
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
        print(f"M4.2 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M4.2 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

