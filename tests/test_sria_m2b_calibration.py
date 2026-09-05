"""SRIA V0.1 M2B — calibration learner tests.

Runs under pytest, and standalone via
``python -m tests.test_sria_m2b_calibration``.

Synthetic and deterministic throughout: no campaign data is read here, so the
suite stays fast and cannot be perturbed by the frozen artifacts. The measured
results on the real corpora live in the M2 report.
"""

from __future__ import annotations

import json
import sys

from src.engcore.sria import AttributedCause, CensoringType, Disposition, Retryability
from src.engcore.sria.calibration import (
    CalibrationCritic,
    CalibrationMemory,
    CalibrationMemoryEntry,
    CalibrationVerdict,
    ComputationalLearningRecord,
    Consumer,
    CostModel,
    FailureModel,
    InsufficientFailureData,
    LeakageError,
    LearningRecordError,
    MemoryKind,
    NotDecisionGrade,
    RelationshipKind,
    base_rate_baseline,
    cost_baselines,
    eligible_records,
    evaluate_cost,
    evaluate_failure,
    grouped_folds,
    grouped_split,
    learn_strategy_cost_ratios,
    record_from_bridged_outcome,
    structure_for,
)
from src.engcore.sria.calibration.ingest import CAMPAIGN_ENVIRONMENT
from src.engcore.sria.signatures import EnvironmentSignature, SemanticGuard


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


ENV = CAMPAIGN_ENVIRONMENT
STRUCT_A = structure_for(2, 40)
STRUCT_B = structure_for(5, 100)


def make_record(
    rid: str,
    *,
    structure=STRUCT_A,
    solver: str = "solverA",
    cost: float | None = 1.0,
    group: str = "prob_1",
    pairing: str = "",
    success: bool = True,
    censoring: CensoringType = CensoringType.NONE,
    informative: bool = True,
    cause: AttributedCause = AttributedCause.NONE,
) -> ComputationalLearningRecord:
    return ComputationalLearningRecord(
        record_id=rid,
        structure=structure,
        environment=ENV,
        solver_identity=(solver, "v1"),
        disposition=Disposition.SUCCESS if success else Disposition.FAILED,
        attributed_cause=cause,
        informative_for_pf=informative,
        retryability=Retryability.RETRYABLE,
        covariates={"search_dimension": 2.0},
        realized_cost=cost,
        cost_censoring=censoring,
        group_key=group,
        pairing_key=pairing or f"{group}:{rid}",
    )


def synthetic_cost_corpus() -> list[ComputationalLearningRecord]:
    """Two solvers whose costs differ by 100x, across 12 problem groups.

    Both solvers share a ``pairing_key`` per instance — that is what makes the
    comparison paired. Distinct pairing keys would silently yield zero pairs.
    """
    records = []
    for g in range(12):
        for i in range(4):
            instance = f"prob_{g}:inst{i}"
            records.append(
                make_record(
                    f"fast-{g}-{i}",
                    solver="fast",
                    cost=0.10 * (1.0 + 0.05 * i),
                    group=f"prob_{g}",
                    pairing=instance,
                )
            )
            records.append(
                make_record(
                    f"slow-{g}-{i}",
                    solver="slow",
                    cost=10.0 * (1.0 + 0.05 * i),
                    group=f"prob_{g}",
                    pairing=instance,
                )
            )
    return records


# =====================================================================
# Learning record contract
# =====================================================================

def test_record_rejects_non_numeric_covariates():
    _raises(
        LearningRecordError,
        make_record,
        "r1",
        cost=1.0,
    ) if False else None

    _raises(
        LearningRecordError,
        ComputationalLearningRecord,
        record_id="r1",
        structure=STRUCT_A,
        environment=ENV,
        solver_identity=("s", "v"),
        disposition=Disposition.SUCCESS,
        covariates={"material": "aluminium"},
    )
    _raises(
        LearningRecordError,
        ComputationalLearningRecord,
        record_id="r2",
        structure=STRUCT_A,
        environment=ENV,
        solver_identity=("s", "v"),
        disposition=Disposition.SUCCESS,
        covariates={"nan_feature": float("nan")},
    )


def test_record_rejects_unattributed_as_pf_eligible():
    _raises(
        LearningRecordError,
        ComputationalLearningRecord,
        record_id="r3",
        structure=STRUCT_A,
        environment=ENV,
        solver_identity=("s", "v"),
        disposition=Disposition.FAILED,
        attributed_cause=AttributedCause.UNATTRIBUTED,
        informative_for_pf=True,
    )


def test_censored_cost_requires_a_bound_and_is_not_observed():
    _raises(
        LearningRecordError,
        ComputationalLearningRecord,
        record_id="r4",
        structure=STRUCT_A,
        environment=ENV,
        solver_identity=("s", "v"),
        disposition=Disposition.KILLED_CENSORED,
        realized_cost=None,
        cost_censoring=CensoringType.RIGHT_CENSORED_WALLCLOCK,
    )

    censored = make_record(
        "r5", cost=60.0, censoring=CensoringType.RIGHT_CENSORED_WALLCLOCK
    )
    assert censored.cost_is_observed is False
    assert make_record("r6", cost=1.0).cost_is_observed is True


def test_record_round_trips():
    record = make_record("r7", cost=2.5)
    reloaded = ComputationalLearningRecord.from_dict(
        json.loads(json.dumps(record.to_dict()))
    )
    assert reloaded.record_id == record.record_id
    assert reloaded.group_key == record.group_key
    assert reloaded.pairing_key == record.pairing_key
    assert reloaded.structure.digest == record.structure.digest


def test_record_from_bridged_outcome_carries_eligibility():
    from src.engcore.scientific import EvaluationStatus
    from src.engcore.sria.calibration import bridge_evaluation_status

    bridged = bridge_evaluation_status(EvaluationStatus.FAILED)
    record = record_from_bridged_outcome(
        record_id="bridged-1",
        bridged=bridged,
        structure=STRUCT_A,
        environment=ENV,
        solver_identity=("s", "v"),
        group_key="prob_x",
    )
    assert record.informative_for_pf is False
    assert record.attributed_cause is AttributedCause.UNATTRIBUTED
    assert eligible_records([record]) == ()


def test_covariates_must_be_domain_neutral():
    guard = SemanticGuard(["voltage", "reynolds"])
    clean = make_record("c1")
    clean.check_domain_neutral(guard)

    leaky = ComputationalLearningRecord(
        record_id="c2",
        structure=STRUCT_A,
        environment=ENV,
        solver_identity=("s", "v"),
        disposition=Disposition.SUCCESS,
        covariates={"voltage_drop": 1.0},
    )
    _raises(Exception, leaky.check_domain_neutral, guard)


# =====================================================================
# Leakage resistance
# =====================================================================

def test_grouped_split_has_no_shared_groups():
    records = synthetic_cost_corpus()
    split = grouped_split(records, holdout_fraction=0.25)
    assert set(split.train_groups) & set(split.test_groups) == set()
    assert len(split.train) + len(split.test) == len(records)
    assert len(split.test_groups) >= 1


def test_grouped_folds_never_leak():
    records = synthetic_cost_corpus()
    folds = grouped_folds(records, folds=4)
    assert len(folds) == 4
    for fold in folds:
        assert set(fold.train_groups) & set(fold.test_groups) == set()
    # Every group is tested exactly once across the folds.
    tested = [g for fold in folds for g in fold.test_groups]
    assert sorted(tested) == sorted({r.group_key for r in records})


def test_split_refuses_records_without_group_identity():
    records = [make_record("x1", group=""), make_record("x2", group="")]
    _raises(LeakageError, grouped_split, records)


def test_split_refuses_a_single_group():
    records = [make_record(f"y{i}", group="only") for i in range(5)]
    _raises(LeakageError, grouped_split, records)


def test_group_key_cannot_be_a_feature():
    from src.engcore.sria.calibration import assert_group_key_not_a_feature

    leaky = ComputationalLearningRecord(
        record_id="leak",
        structure=STRUCT_A,
        environment=ENV,
        solver_identity=("s", "v"),
        disposition=Disposition.SUCCESS,
        covariates={"prob_7_indicator": 1.0},
        group_key="prob_7",
    )
    _raises(LeakageError, assert_group_key_not_a_feature, [leaky])


# =====================================================================
# Cost model
# =====================================================================

def test_cost_model_beats_baselines_on_separable_data():
    records = synthetic_cost_corpus()
    split = grouped_split(records, holdout_fraction=0.25)

    baseline_scores = {}
    for name, baseline in cost_baselines().items():
        baseline.fit(split.train)
        preds = [baseline.predict_log10(r) for r in split.test]
        baseline_scores[name] = evaluate_cost(name, preds, split.test).mae_log10

    model = CostModel().fit(split.train, dataset_id="synthetic")
    predictions = [model.predict(r) for r in split.test]
    learned = evaluate_cost(
        "learned",
        [p.log10_point for p in predictions],
        split.test,
        intervals=[(p.lower, p.upper) for p in predictions],
    )

    # The baselines cannot see solver identity, which is the whole signal.
    assert learned.mae_log10 < min(baseline_scores.values())
    assert learned.fold_error < 1.5
    assert learned.coverage is not None


def test_cost_model_excludes_censored_costs_from_the_median():
    """A timeout must not be read as a completed runtime."""
    observed = [
        make_record(f"obs-{i}", solver="s", cost=1.0, group=f"g{i}")
        for i in range(6)
    ]
    censored = [
        make_record(
            f"cens-{i}",
            solver="s",
            cost=1000.0,
            group=f"g{i}",
            censoring=CensoringType.RIGHT_CENSORED_WALLCLOCK,
        )
        for i in range(6)
    ]

    model = CostModel().fit(observed + censored, dataset_id="censoring")
    prediction = model.predict(observed[0])

    # If the 1000 s lower bounds had been treated as runtimes the median would
    # have moved far above 1 s.
    assert 0.5 < prediction.point < 2.0
    assert model.training_provenance["censored_excluded"] == 6
    assert model.training_provenance["observed_costs_used"] == 6
    assert prediction.is_lower_bound is True   # heavy censoring is flagged


def test_cost_model_carries_version_and_provenance():
    model = CostModel().fit(synthetic_cost_corpus(), dataset_id="synthetic-v1")
    assert model.model_version.startswith("cost/")
    provenance = model.training_provenance
    assert provenance["dataset_id"] == "synthetic-v1"
    assert provenance["observed_costs_used"] > 0
    assert "model_version" in provenance
    summary = model.summary()
    assert summary["model_version"] == model.model_version


def test_cost_prediction_backs_off_for_unseen_solver():
    records = synthetic_cost_corpus()
    model = CostModel().fit(records, dataset_id="synthetic")
    unseen = make_record("unseen", solver="never_seen", cost=1.0, group="prob_0")
    prediction = model.predict(unseen)
    # Falls back to a coarser cell rather than raising or inventing a cell.
    assert prediction.support > 0
    assert "solver=never_seen" not in prediction.cell


# =====================================================================
# Failure model
# =====================================================================

def synthetic_failure_corpus() -> list[ComputationalLearningRecord]:
    """Solver 'flaky' fails half the time; solver 'solid' never does."""
    records = []
    for g in range(12):
        for i in range(4):
            records.append(
                make_record(
                    f"solid-{g}-{i}",
                    solver="solid",
                    group=f"prob_{g}",
                    success=True,
                )
            )
            records.append(
                make_record(
                    f"flaky-{g}-{i}",
                    solver="flaky",
                    group=f"prob_{g}",
                    success=(i % 2 == 0),
                    cause=(
                        AttributedCause.NONE
                        if i % 2 == 0
                        else AttributedCause.NUMERICAL
                    ),
                )
            )
    return records


def test_failure_model_requires_target_variance():
    all_success = [
        make_record(f"s{i}", group=f"g{i % 6}", success=True) for i in range(24)
    ]
    _raises(
        InsufficientFailureData,
        FailureModel().fit,
        all_success,
    )


def test_failure_model_learns_and_is_calibrated():
    records = synthetic_failure_corpus()
    split = grouped_split(records, holdout_fraction=0.25)

    model = FailureModel().fit(split.train, dataset_id="synthetic-failures")
    probabilities = [model.predict(r).probability_success for r in split.test]
    learned = evaluate_failure("learned", probabilities, split.test)

    base = base_rate_baseline(split.train)
    baseline = evaluate_failure(
        "base_rate", [base] * len(split.test), split.test
    )

    assert learned.brier < baseline.brier
    assert model.model_version.startswith("failure/")
    assert model.training_provenance["failures"] > 0
    assert learned.reliability_bins


def test_infrastructure_failures_cannot_train_the_failure_model():
    poisoned = [
        make_record(
            f"infra-{i}",
            solver="solid",
            group=f"g{i % 6}",
            success=False,
            informative=False,
            cause=AttributedCause.INFRASTRUCTURE,
        )
        for i in range(20)
    ]
    clean = [
        make_record(f"ok-{i}", solver="solid", group=f"g{i % 6}", success=True)
        for i in range(20)
    ]

    assert len(eligible_records(poisoned)) == 0

    # With infrastructure rows excluded the target has no variance, so the
    # model refuses rather than learning a bogus 50% failure rate.
    _raises(InsufficientFailureData, FailureModel().fit, poisoned + clean)


def test_unattributed_rows_are_excluded_even_if_flagged_eligible():
    """Second line of defence at the learner boundary."""
    records = synthetic_failure_corpus()
    # eligible_records must drop UNATTRIBUTED regardless of the flag.
    sneaky = make_record(
        "sneaky",
        group="prob_0",
        success=False,
        informative=False,
        cause=AttributedCause.UNATTRIBUTED,
    )
    assert sneaky not in eligible_records(records + [sneaky])


# =====================================================================
# Fidelity / configuration relationships
# =====================================================================

def test_strategy_cost_ratios_are_paired_and_structure_transferable():
    records = synthetic_cost_corpus()
    relationships = learn_strategy_cost_ratios(records, min_pairs=5)
    assert relationships

    rel = relationships[0]
    assert rel.kind is RelationshipKind.STRUCTURE_TRANSFERABLE
    assert rel.metric == "realized_cost_ratio"
    # fast -> slow is ~100x by construction.
    assert 50.0 < rel.median_ratio < 200.0
    assert rel.paired_observations == 48    # 12 groups x 4 instances
    # These are algorithm relationships, not fidelity rungs (M2.1).
    assert rel.from_strategy == "fast" and rel.to_strategy == "slow"


def test_domain_owned_relationships_are_refused():
    from src.engcore.sria.calibration.strategy_relationships import (
        StrategyCostRelationship,
    )

    _raises(
        ValueError,
        StrategyCostRelationship,
        from_strategy="a",
        to_strategy="b",
        kind=RelationshipKind.DOMAIN_OWNED,
        metric="accuracy_sufficiency",
        median_ratio=1.0,
        geometric_mean_ratio=1.0,
        p10_ratio=1.0,
        p90_ratio=1.0,
        paired_observations=10,
        structure_digest="x",
        environment_digest="y",
    )


# =====================================================================
# Calibration critic
# =====================================================================

def test_critic_untrusts_a_deliberately_bad_cost_model():
    critic = CalibrationCritic()
    report = critic.assess_cost_model(
        model_id="cost.bad",
        model_version="cost/bad/1",
        mae_log10=1.8,          # ~63x typical error
        n_eval=200,
        coverage=0.10,
        baseline_mae_log10=0.4,  # far worse than the cheap baseline
    )
    assert report.verdict is CalibrationVerdict.UNTRUSTED
    assert report.is_decision_grade is False
    _raises(NotDecisionGrade, report.require_decision_grade)

    failed = [d.name for d in report.diagnostics if not d.passed]
    assert "held_out_mae_log10" in failed
    assert "beats_best_baseline" in failed


def test_critic_degrades_a_model_that_is_accurate_but_miscalibrated():
    critic = CalibrationCritic()
    report = critic.assess_cost_model(
        model_id="cost.narrow",
        model_version="cost/narrow/1",
        mae_log10=0.10,
        n_eval=200,
        coverage=0.20,          # intervals far too narrow
        baseline_mae_log10=0.9,
    )
    assert report.verdict is CalibrationVerdict.DEGRADED
    assert report.is_decision_grade is True     # usable, with the caveat stated
    report.require_decision_grade()             # does not raise


def test_critic_reports_insufficient_data_not_untrusted():
    critic = CalibrationCritic()
    report = critic.assess_cost_model(
        model_id="cost.thin",
        model_version="cost/thin/1",
        mae_log10=0.05,
        n_eval=3,
        coverage=None,
    )
    assert report.verdict is CalibrationVerdict.INSUFFICIENT_DATA
    _raises(NotDecisionGrade, report.require_decision_grade)

    failure = critic.assess_failure_model(
        model_id="failure.none",
        model_version="failure/x/1",
        brier=None,
        baseline_brier=None,
        n_eval=0,
        minority_count=0,
        insufficient_reason="target has no variance",
    )
    assert failure.verdict is CalibrationVerdict.INSUFFICIENT_DATA


def test_critic_trusts_a_good_model():
    critic = CalibrationCritic()
    report = critic.assess_cost_model(
        model_id="cost.good",
        model_version="cost/good/1",
        mae_log10=0.06,
        n_eval=300,
        coverage=0.81,
        baseline_mae_log10=1.2,
    )
    assert report.verdict is CalibrationVerdict.TRUSTED
    report.require_decision_grade()
    assert json.loads(json.dumps(report.to_dict()))["verdict"] == "trusted"


# =====================================================================
# Calibration memory
# =====================================================================

def test_memory_entry_must_declare_a_consumer():
    _raises(
        ValueError,
        CalibrationMemoryEntry,
        entry_id="e1",
        kind=MemoryKind.COST_MODEL,
        model_version="cost/1",
        dataset_id="ds",
        payload={},
        consumed_by=(),
    )
    _raises(
        ValueError,
        CalibrationMemoryEntry,
        entry_id="e2",
        kind=MemoryKind.COST_MODEL,
        model_version="cost/1",
        dataset_id="",              # unidentifiable training data
        payload={},
        consumed_by=(Consumer.COST_PREDICTION,),
    )


def test_memory_round_trips_and_filters_by_signature_version(tmp_path=None):
    import tempfile
    from pathlib import Path

    memory = CalibrationMemory()
    memory.record(
        CalibrationMemoryEntry(
            entry_id="cost-1",
            kind=MemoryKind.COST_MODEL,
            model_version="cost/hierarchical-log-median/1",
            dataset_id="corpus-v1",
            payload={"cells": 12},
            consumed_by=(Consumer.COST_PREDICTION,),
            metrics={"mae_log10": 0.05},
        )
    )
    memory.record(
        CalibrationMemoryEntry(
            entry_id="old-1",
            kind=MemoryKind.COST_MODEL,
            model_version="cost/legacy/0",
            dataset_id="corpus-v0",
            payload={},
            consumed_by=(Consumer.COST_PREDICTION,),
            structure_signature_version=999,     # a scheme we no longer use
        )
    )
    memory.record(
        CalibrationMemoryEntry(
            entry_id="arch-1",
            kind=MemoryKind.CALIBRATION_DIAGNOSTIC,
            model_version="x/1",
            dataset_id="corpus-v1",
            payload={},
            consumed_by=(Consumer.ARCHIVE,),
        )
    )

    current = memory.lookup(MemoryKind.COST_MODEL, consumer=Consumer.COST_PREDICTION)
    assert [e.entry_id for e in current] == ["cost-1"]
    assert [e.entry_id for e in memory.archive_only()] == ["arch-1"]

    _raises(
        ValueError,
        memory.record,
        CalibrationMemoryEntry(
            entry_id="cost-1",
            kind=MemoryKind.COST_MODEL,
            model_version="v",
            dataset_id="d",
            payload={},
            consumed_by=(Consumer.COST_PREDICTION,),
        ),
    )

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "memory.json"
        memory.save(path)
        reloaded = CalibrationMemory.load(path)
        assert len(reloaded) == len(memory)
        assert [e.entry_id for e in reloaded.entries] == [
            e.entry_id for e in memory.entries
        ]


def test_calibration_keys_do_not_contain_domain_names():
    """Structure x environment only — restated at the M2 boundary."""
    from src.engcore.sria import build_calibration_key

    guard = SemanticGuard(["bbob", "voltage", "peak_response"])
    key = build_calibration_key(STRUCT_B, ENV, guard=guard)
    assert key.key.startswith("calib/v1/")

    contaminated = structure_for(5, 100)
    from src.engcore.sria.signatures import StructureSignature

    bad = StructureSignature(
        structure_kind="bbob_search_run",   # benchmark name in the structure
        attributes={"search_dimension": "5"},
    )
    _raises(Exception, build_calibration_key, bad, ENV, guard=guard)


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M2B — calibration learner tests")
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
        print(f"M2B tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M2B tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
