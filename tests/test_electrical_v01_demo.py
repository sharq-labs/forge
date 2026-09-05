"""Electrical V0.1 demo — proof that the demo shows what it claims to show.

Deliberately small. The science is already tested by E1, E2, E3 and the V0.1
certification tests; these assert only that the demo is deterministic, that it
changed no production code or frozen artifact, and that the lifecycle it
reports is the one that actually ran.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from experiments.electrical_v01_demo import BASE_COMMIT, DEMO_VERSION
from experiments.electrical_v01_demo.demo_config import (
    REQUIRED_ACTION_IDS,
    REQUIREMENT_ID,
    RESERVED_VALIDATION_BUDGET,
    TOTAL_BUDGET,
    config_hash,
    scenario_hash,
)
from experiments.electrical_v01_demo.demo_run import result_digest, run_demo
from src.engcore.sria.campaign.stopping import StopReviewOutcome

_RESULT = None


def demo_result():
    global _RESULT
    if _RESULT is None:
        _RESULT = run_demo()
    return _RESULT


def world_a():
    return demo_result()["world_a_model_adequate"]


def world_b():
    return demo_result()["world_b_model_inadequate"]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# =====================================================================
# 1-4. Provenance: deterministic, frozen base, nothing production touched
# =====================================================================

def test_1_demo_config_is_deterministic():
    first = config_hash()
    assert config_hash() == first
    assert len(first) == 64
    assert scenario_hash() == scenario_hash()
    assert scenario_hash() != first
    result = demo_result()
    assert result["config_hash"] == first
    assert result["demo_version"] == DEMO_VERSION


def test_2_frozen_base_commit_is_recorded():
    assert BASE_COMMIT == "4ac821b8b3fbbc06fb784d9d66a7e12a5fe391cc"
    assert demo_result()["base_commit"] == BASE_COMMIT


def test_3_frozen_experiment_artifacts_are_unchanged():
    """The demo reads E1/E2/E3; it must not have written to them."""
    from experiments.electrical_e2.e2_config import (
        E1_FROZEN_FILE_DIGESTS,
        config_hash as e2_hash,
    )
    from experiments.electrical_e3.e3_config import (
        E2_CONFIG_HASH,
        E2_FROZEN_FILE_DIGESTS,
    )
    from experiments.electrical_v01_demo.demo_config import (
        E2_CONFIG_HASH as DEMO_PIN,
    )

    root = _repo_root()
    for digests in (E1_FROZEN_FILE_DIGESTS, E2_FROZEN_FILE_DIGESTS):
        for name, expected in digests.items():
            raw = (root / name).read_bytes().replace(b"\r\n", b"\n")
            assert hashlib.sha256(raw).hexdigest() == expected, name
    assert e2_hash() == E2_CONFIG_HASH == DEMO_PIN


def test_4_demo_touches_no_production_source():
    """Nothing under experiments/ or the demo imports may write to src/."""
    import experiments.electrical_v01_demo as package

    root = Path(package.__file__).resolve().parent
    for path in sorted(root.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "src/engcore" not in source.replace(
            "from src.engcore", ""
        ).replace("import src.engcore", ""), path.name
        # The demo may import production code; it may not write files into it.
        assert "write_text" not in source or path.name == "run.py"
    # run.py writes only into its own package directory.
    run_source = (root / "run.py").read_text(encoding="utf-8")
    assert "root / \"demo_" in run_source
    assert "src" not in run_source.split("def main")[1].split("root =")[1][:200]


# =====================================================================
# 5-6. CampaignRunner does the routing, in both worlds
# =====================================================================

def test_5_world_a_routes_certification_actions_via_campaignrunner():
    world = world_a()
    assert world["routed_by_runner_for_certification"] == list(
        REQUIRED_ACTION_IDS
    )
    first = world["selection_trace"][0]
    assert first["action_id"] == "measure_vmid_10V_precise"
    assert first["execution_reason"] == "POSITIVE_NET_VALUE"
    for row in world["selection_trace"][1:]:
        assert row["execution_reason"] == "CERTIFICATION_REQUIREMENT"
        assert row["action_id"] in REQUIRED_ACTION_IDS
    assert world["certification_requirement_status"] == "satisfied"


def test_6_world_b_routes_certification_actions_via_campaignrunner():
    world = world_b()
    assert world["routed_by_runner_for_certification"] == list(
        REQUIRED_ACTION_IDS
    )
    assert world["selection_trace"][0]["execution_reason"] == "POSITIVE_NET_VALUE"
    assert world["certification_requirement_status"] == "satisfied"
    # The two probes the requirement does not name were never bought.
    executed = set(world["executed_actions"])
    assert "validate_vmid_20V" not in executed
    assert "validate_vmid_24V" not in executed


# =====================================================================
# 7. The requirement changed no parameter-learning score
# =====================================================================

def test_7_evsi_scores_are_unchanged_by_the_certification_requirement():
    invariance = demo_result()["evsi_invariance"]
    assert invariance["identical_on_shared_points"] is True
    assert invariance["shared_score_points"] > 0
    assert invariance["without_requirement_executed"] == [
        "measure_vmid_10V_precise"
    ]
    rows = invariance["certification_action_scores"]
    assert rows, "no certification action was scored"
    for row in rows:
        assert row["parameter_evsi"] < 1e-9, row["action_id"]
        assert row["net_value"] < 0.0, row["action_id"]
        assert row["execution_reason"] == "CERTIFICATION_REQUIREMENT"


# =====================================================================
# 8-11. The two worlds end differently, for the right reason
# =====================================================================

def test_8_world_a_ends_stop_approved_and_eligible():
    world = world_a()
    review = world["stop_review"]
    assert review["outcome"] == StopReviewOutcome.STOP_APPROVED.value
    assert review["arbiter_verdict"] == "valid"
    assert review["arbiter_decision_id"]
    assert review["criterion_id"] == REQUIREMENT_ID
    assert review["is_certification"] is False
    assert world["terminal"]["scientific_certification"] == "eligible"


def test_9_world_b_ends_stop_rejected_and_not_certifiable():
    world = world_b()
    review = world["stop_review"]
    assert review["outcome"] == StopReviewOutcome.STOP_REJECTED.value
    assert review["arbiter_verdict"] == "invalid"
    assert review["approves"] is False
    terminal = world["terminal"]
    assert terminal["scientific_certification"] == "not_certifiable"
    assert terminal["reason"] == "MODEL_SPACE_INADEQUATE"
    assert terminal["disposition"] == "model_revision_required"
    # Confident, and still refused.
    assert world["posterior_final"]["p_above_threshold"] > 0.999999
    assert terminal["parameter_evpi"] <= 1e-30
    assert terminal["parameter_evsi_max"] <= 1e-30


def test_10_requirement_is_satisfied_in_both_worlds():
    assert world_a()["certification_requirement_status"] == "satisfied"
    assert world_b()["certification_requirement_status"] == "satisfied"


def test_11_adequacy_outcome_differs_between_worlds():
    assert world_a()["terminal"]["model_adequacy"] == (
        "acceptable_for_declared_scope"
    )
    assert world_b()["terminal"]["model_adequacy"] == "model_space_inadequate"
    assert world_a()["adequacy"]["aggregate"]["n_extreme"] == 0
    assert world_b()["adequacy"]["aggregate"]["n_extreme"] >= 2


# =====================================================================
# 12-14. Evidence, belief and budget
# =====================================================================

def test_12_surprising_but_valid_evidence_remains_admitted():
    world = world_b()
    worst = min(
        world["adequacy"]["surprises"], key=lambda s: s["tail_probability"]
    )
    assert worst["tail_probability"] < 1e-4
    row = next(
        r
        for r in world["selection_trace"]
        if r["action_id"] == worst["action_id"]
    )
    assert row["admitted"] is True
    counters = world["belief"]
    assert counters["evidence_admitted"] == counters["evidence_records_created"]
    assert counters["evidence_rejected"] == 0
    assert set(REQUIRED_ACTION_IDS) <= set(counters["belief_action_ids"])


def test_13_invalid_execution_cannot_update_belief():
    for world in (world_a(), world_b()):
        probe = world["belief_integrity_probe"]
        assert probe["critic_verdict"] == "fail"
        assert probe["arbiter_verdict"] == "invalid"
        assert probe["admitted"] is False
        assert probe["execution_validity"] == "invalid"
        assert probe["belief_size_before"] == probe["belief_size_after"]
        assert probe["belief_unchanged"] is True
        assert probe["posterior_unchanged"] is True


def test_14_budget_accounting_is_correct_and_uses_the_frozen_ledger():
    for world in (world_a(), world_b()):
        budget = world["budget"]
        assert budget["total"] == TOTAL_BUDGET
        assert budget["reserved_validation"] == RESERVED_VALIDATION_BUDGET
        # One parameter action at 0.10, three probes at 0.15.
        assert abs(budget["spent_parameter_learning"] - 0.10) < 1e-9
        assert abs(budget["spent_validation"] - 0.45) < 1e-9
        assert abs(budget["spent_total"] - 0.55) < 1e-9
        assert budget["ledger"] == "frozen BudgetLedger"


# =====================================================================
# 15-16. Commitment ordering and determinism
# =====================================================================

def test_15_prediction_ref_exists_before_every_required_execution():
    for world in (world_a(), world_b()):
        rows = [
            r
            for r in world["selection_trace"]
            if r["action_id"] in REQUIRED_ACTION_IDS
        ]
        assert len(rows) == len(REQUIRED_ACTION_IDS)
        for row in rows:
            assert row["prediction_ref"]
            assert row["action_selected_sequence"] < (
                row["execution_started_sequence"]
            )
            assert row["prediction_precedes_execution"] is True
        # The references are the sealed ledger's, and the ledger verifies.
        adequacy = world["adequacy"]
        assert adequacy["chain_verified"] is True
        valid = {c["artifact_hash"] for c in adequacy["commitments"]}
        assert {r["prediction_ref"] for r in rows} == valid


def test_16_demo_is_deterministic():
    first = demo_result()
    second = run_demo()
    assert second["result_digest"] == first["result_digest"]
    assert result_digest(second) == result_digest(first)
    # ...and the scientific fields really are identical, not just the digest.
    for key in ("world_a_model_adequate", "world_b_model_inadequate"):
        assert second[key]["terminal"] == first[key]["terminal"]
        assert second[key]["posterior_final"] == first[key]["posterior_final"]
        assert second[key]["selection_trace"] == first[key]["selection_trace"]


def test_17_demo_verdict_and_checks():
    result = demo_result()
    for name, value in result["checks"].items():
        assert value is True, name
    assert result["verdict"] == "ELECTRICAL V0.1 DEMO VERIFIED"
    # The limitation is stated, not buried.
    limitation = result["prediction_ref_limitation"]
    assert "does NOT verify in production" in limitation
    assert "would have tested nothing" in limitation


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("Electrical V0.1 demo tests")
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
        print(f"DEMO: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"DEMO: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
