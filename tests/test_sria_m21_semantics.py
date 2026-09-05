"""SRIA V0.1 M2.1 — semantic correction tests.

Runs under pytest, and standalone via ``python -m tests.test_sria_m21_semantics``.

Each test guards a *category error* — the kind that survives review because
the arithmetic is correct and only the meaning is wrong.
"""

from __future__ import annotations

import json
import sys

from src.engcore.scientific import EvaluationStatus
from src.engcore.sria import AttributedCause, CensoringType, Disposition, Retryability
from src.engcore.sria.calibration import (
    CalibrationCritic,
    CalibrationMemory,
    CalibrationMemoryEntry,
    CalibrationVerdict,
    ComputationalLearningRecord,
    Consumer,
    CostModel,
    FidelityDataStatus,
    FidelityOwnership,
    FidelityRung,
    FidelitySemanticError,
    KNOWN_STRATEGY_IDENTITIES,
    MemoryKind,
    ModelFidelityRelationship,
    StrategyCostRelationship,
    assert_not_a_strategy_identity,
    bridge_evaluation_status,
    eligible_records,
    feasibility_records,
    fidelity_corpus_status,
    learn_strategy_cost_ratios,
    mapping_table_rows,
    structure_for,
)
from src.engcore.sria.calibration.ingest import CAMPAIGN_ENVIRONMENT

ENV = CAMPAIGN_ENVIRONMENT
STRUCT = structure_for(2, 40)


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


def make_record(
    rid: str,
    *,
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
        structure=STRUCT,
        environment=ENV,
        solver_identity=(solver, "v1"),
        disposition=Disposition.SUCCESS if success else Disposition.FAILED,
        attributed_cause=cause,
        informative_for_pf=informative,
        retryability=Retryability.RETRYABLE,
        realized_cost=cost,
        cost_censoring=censoring,
        group_key=group,
        pairing_key=pairing or f"{group}:{rid}",
    )


# =====================================================================
# 1. FIDELITY SEMANTICS
# =====================================================================

def test_optimizer_identity_cannot_be_a_fidelity_rung():
    """The M2 category error, made unrepeatable."""
    for strategy in ("cmaes", "ngopt", "stacked_v0301", "adaptive_stacked_v033"):
        _raises(FidelitySemanticError, assert_not_a_strategy_identity, strategy)
        _raises(
            FidelitySemanticError,
            FidelityRung,
            rung_id=strategy,
            rank=0,
            model_ref="thermal.plate",
        )

    # Case and variant spellings are caught too.
    _raises(FidelitySemanticError, assert_not_a_strategy_identity, "CMAES")
    _raises(FidelitySemanticError, assert_not_a_strategy_identity, "cmaes_v2")
    _raises(FidelitySemanticError, assert_not_a_strategy_identity, "stacked-fast")

    # A genuine rung is accepted.
    coarse = FidelityRung(rung_id="mesh_coarse", rank=0, model_ref="thermal.plate")
    assert coarse.rung_id == "mesh_coarse"


def test_fidelity_rung_requires_the_model_it_approximates():
    _raises(FidelitySemanticError, FidelityRung, rung_id="coarse", rank=0, model_ref="")


def test_fidelity_relationship_requires_the_same_physical_model():
    a = FidelityRung(rung_id="coarse", rank=0, model_ref="thermal.plate")
    b = FidelityRung(rung_id="fine", rank=1, model_ref="thermal.plate")
    other = FidelityRung(rung_id="fine2", rank=1, model_ref="electrical.dc")

    rel = ModelFidelityRelationship(
        low_rung=a,
        high_rung=b,
        ownership=FidelityOwnership.STRUCTURE_TRANSFERABLE,
        metric="cost_ratio",
    )
    assert rel.data_status is FidelityDataStatus.INSUFFICIENT_REAL_DATA

    # Two different models are not two rungs of one ladder.
    _raises(
        FidelitySemanticError,
        ModelFidelityRelationship,
        low_rung=a,
        high_rung=other,
        ownership=FidelityOwnership.STRUCTURE_TRANSFERABLE,
        metric="cost_ratio",
    )
    # Accuracy/sufficiency remains domain-owned and unrepresentable here.
    _raises(
        FidelitySemanticError,
        ModelFidelityRelationship,
        low_rung=a,
        high_rung=b,
        ownership=FidelityOwnership.DOMAIN_OWNED,
        metric="accuracy_sufficiency",
    )
    # OBSERVED must be backed by observations.
    _raises(
        FidelitySemanticError,
        ModelFidelityRelationship,
        low_rung=a,
        high_rung=b,
        ownership=FidelityOwnership.STRUCTURE_TRANSFERABLE,
        metric="cost_ratio",
        data_status=FidelityDataStatus.OBSERVED,
        paired_observations=0,
    )


def test_no_genuine_fidelity_corpus_exists():
    status = fidelity_corpus_status([])
    assert status["status"] == FidelityDataStatus.INSUFFICIENT_REAL_DATA.value
    assert status["models_with_a_real_ladder"] == 0
    assert "NOT fidelity data" in status["note"]

    # A single rung is not a ladder.
    lone = [FidelityRung(rung_id="coarse", rank=0, model_ref="thermal.plate")]
    assert (
        fidelity_corpus_status(lone)["status"]
        == FidelityDataStatus.INSUFFICIENT_REAL_DATA.value
    )


def test_strategy_ratios_are_named_as_strategies_not_fidelity():
    records = []
    for g in range(6):
        for i in range(3):
            instance = f"prob_{g}:inst{i}"
            records.append(
                make_record(
                    f"fast-{g}-{i}", solver="cmaes", cost=0.1,
                    group=f"prob_{g}", pairing=instance,
                )
            )
            records.append(
                make_record(
                    f"slow-{g}-{i}", solver="stacked_v0301", cost=10.0,
                    group=f"prob_{g}", pairing=instance,
                )
            )

    relationships = learn_strategy_cost_ratios(records, min_pairs=5)
    assert relationships
    rel = relationships[0]
    assert isinstance(rel, StrategyCostRelationship)
    assert rel.from_strategy and rel.to_strategy

    payload = json.loads(json.dumps(rel.to_dict()))
    # The serialized form must not present itself as fidelity.
    assert "fidelity" not in json.dumps(payload).lower()
    assert payload["schema"].startswith("sria_strategy_cost_relationship")
    assert "from_strategy" in payload and "to_strategy" in payload

    # And these identities are exactly the ones barred from being rungs.
    assert "cmaes" in KNOWN_STRATEGY_IDENTITIES
    assert "stacked_v0301" in KNOWN_STRATEGY_IDENTITIES


# =====================================================================
# 2. FAILURE TARGET SEMANTICS
# =====================================================================

def test_infeasible_is_not_evidence_the_solver_failed():
    """A perfect solve of an infeasible point says nothing about the solver."""
    infeasible = make_record(
        "infeasible-1",
        success=False,
        cause=AttributedCause.INFEASIBLE,
        informative=True,
    )
    assert infeasible.eligible_for_computational_failure_learning is False
    assert infeasible.eligible_for_feasibility_learning is True
    assert infeasible.is_feasibility_evidence_only is True

    numerical = make_record(
        "numerical-1",
        success=False,
        cause=AttributedCause.NUMERICAL,
        informative=True,
    )
    assert numerical.eligible_for_computational_failure_learning is True

    pool = [infeasible, numerical]
    assert [r.record_id for r in eligible_records(pool)] == ["numerical-1"]
    assert "infeasible-1" in [r.record_id for r in feasibility_records(pool)]


def test_legacy_invalid_routes_to_feasibility_not_solver_failure():
    bridged = bridge_evaluation_status(EvaluationStatus.INVALID)
    assert bridged.outcome.attributed_cause is AttributedCause.INFEASIBLE
    assert bridged.pf_eligible is True                       # carries signal
    assert bridged.eligible_for_computational_failure_learning is False
    assert bridged.eligible_for_feasibility_learning is True

    row = [r for r in mapping_table_rows() if r["legacy_status"] == "invalid"][0]
    assert row["computational_failure_eligible"] is False
    assert row["feasibility_eligible"] is True
    assert "FEASIBILITY" in row["note"]


def test_infeasible_rows_cannot_reach_the_solver_failure_model():
    from src.engcore.sria.calibration import FailureModel, InsufficientFailureData

    successes = [
        make_record(f"ok-{i}", group=f"g{i % 6}", success=True) for i in range(20)
    ]
    infeasibles = [
        make_record(
            f"inf-{i}",
            group=f"g{i % 6}",
            success=False,
            cause=AttributedCause.INFEASIBLE,
        )
        for i in range(20)
    ]
    # With infeasibility routed away, the target has no variance and the model
    # refuses — rather than learning a 50% "solver failure rate" that is really
    # a feasibility rate.
    _raises(
        InsufficientFailureData, FailureModel().fit, successes + infeasibles
    )


def test_other_causes_keep_their_existing_eligibility():
    for cause, expected in (
        (AttributedCause.NUMERICAL, True),
        (AttributedCause.SCIENTIFIC, True),
        (AttributedCause.INFRASTRUCTURE, False),
        (AttributedCause.UNATTRIBUTED, False),
    ):
        record = make_record(
            f"c-{cause.value}",
            success=False,
            cause=cause,
            informative=cause
            not in (AttributedCause.INFRASTRUCTURE, AttributedCause.UNATTRIBUTED),
        )
        assert record.eligible_for_computational_failure_learning is expected


# =====================================================================
# 3. COST CENSORING TRUST RULE
# =====================================================================

def heavily_censored_corpus():
    """80% of the support is right-censored."""
    records = []
    for g in range(8):
        records.append(
            make_record(f"obs-{g}", solver="s", cost=1.0, group=f"g{g}")
        )
        for k in range(4):
            records.append(
                make_record(
                    f"cens-{g}-{k}",
                    solver="s",
                    cost=100.0,
                    group=f"g{g}",
                    censoring=CensoringType.RIGHT_CENSORED_WALLCLOCK,
                )
            )
    return records


def test_heavy_censoring_prevents_trusted_status():
    records = heavily_censored_corpus()
    model = CostModel().fit(records, dataset_id="censored")
    provenance = model.training_provenance
    censored_fraction = provenance["censored_excluded"] / (
        provenance["censored_excluded"] + provenance["observed_costs_used"]
    )
    assert censored_fraction > 0.5

    critic = CalibrationCritic()
    report = critic.assess_cost_model(
        model_id="cost.censored",
        model_version=model.model_version,
        mae_log10=0.01,          # excellent on the rows it kept
        n_eval=200,
        coverage=0.82,
        baseline_mae_log10=1.0,
        training_provenance=provenance,
    )
    # Excellent apparent accuracy must NOT buy TRUSTED when most of the
    # support was discarded.
    assert report.verdict is not CalibrationVerdict.TRUSTED
    assert report.verdict is CalibrationVerdict.UNTRUSTED
    names = [d.name for d in report.diagnostics]
    assert "censored_fraction_of_support" in names


def test_moderate_censoring_degrades_rather_than_trusts():
    critic = CalibrationCritic()
    report = critic.assess_cost_model(
        model_id="cost.some_censoring",
        model_version="cost/v1",
        mae_log10=0.05,
        n_eval=200,
        coverage=0.80,
        baseline_mae_log10=1.0,
        censored_fraction=0.15,      # above TRUSTED cap, below unusable
    )
    assert report.verdict is CalibrationVerdict.DEGRADED


def test_censoring_cannot_be_hidden_by_omitting_the_argument():
    """Provenance is consulted when the caller does not pass the fraction."""
    critic = CalibrationCritic()
    report = critic.assess_cost_model(
        model_id="cost.sneaky",
        model_version="cost/v1",
        mae_log10=0.05,
        n_eval=200,
        coverage=0.80,
        baseline_mae_log10=1.0,
        training_provenance={
            "observed_costs_used": 10,
            "censored_excluded": 90,     # 90% censored
        },
    )
    assert report.verdict is CalibrationVerdict.UNTRUSTED


def test_uncensored_model_can_still_be_trusted():
    critic = CalibrationCritic()
    report = critic.assess_cost_model(
        model_id="cost.clean",
        model_version="cost/v1",
        mae_log10=0.05,
        n_eval=200,
        coverage=0.80,
        baseline_mae_log10=1.0,
        training_provenance={"observed_costs_used": 100, "censored_excluded": 0},
    )
    assert report.verdict is CalibrationVerdict.TRUSTED


# =====================================================================
# 4. CALIBRATION MEMORY ARCHIVE SAFETY
# =====================================================================

def test_archive_entries_never_reach_the_active_decision_path():
    memory = CalibrationMemory()
    memory.record(
        CalibrationMemoryEntry(
            entry_id="active-1",
            kind=MemoryKind.COST_MODEL,
            model_version="cost/v1",
            dataset_id="ds",
            payload={"cells": 5},
            consumed_by=(Consumer.COST_PREDICTION,),
        )
    )
    memory.record(
        CalibrationMemoryEntry(
            entry_id="archived-1",
            kind=MemoryKind.COST_MODEL,
            model_version="cost/v0",
            dataset_id="ds",
            payload={"cells": 999},
            consumed_by=(Consumer.ARCHIVE,),
        )
    )

    active = memory.active_lookup(
        MemoryKind.COST_MODEL, consumer=Consumer.COST_PREDICTION
    )
    assert [e.entry_id for e in active] == ["active-1"]
    assert all(not e.is_archive_only for e in active)

    # Archive is not a decision consumer at all.
    _raises(
        ValueError,
        memory.active_lookup,
        MemoryKind.COST_MODEL,
        consumer=Consumer.ARCHIVE,
    )

    # The archived entry is still retrievable as a record.
    assert [e.entry_id for e in memory.archive_only()] == ["archived-1"]


def test_archive_only_entry_is_excluded_even_when_it_also_lists_a_consumer():
    """Mixed consumers: only pure-ARCHIVE entries are archive-only."""
    memory = CalibrationMemory()
    memory.record(
        CalibrationMemoryEntry(
            entry_id="mixed-1",
            kind=MemoryKind.FAILURE_MODEL,
            model_version="f/v1",
            dataset_id="ds",
            payload={},
            consumed_by=(Consumer.FAILURE_PREDICTION, Consumer.ARCHIVE),
        )
    )
    assert memory.entries[0].is_archive_only is False
    active = memory.active_lookup(
        MemoryKind.FAILURE_MODEL, consumer=Consumer.FAILURE_PREDICTION
    )
    assert [e.entry_id for e in active] == ["mixed-1"]


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M2.1 — semantic correction tests")
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
        print(f"M2.1 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M2.1 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
