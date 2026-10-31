"""Incomplete measurement records cannot establish exact software equivalence."""
from copy import deepcopy

import pytest

from tools.genesis_performance.analyse import comparison


def record():
    return {"arm": "pysr_units", "seed": 0, "campaign_id": "public-perf-0", "status": "VALID",
            "reasons": [], "observe_calls": 6, "universes": [{"universe_id": f"u{i}"} for i in range(6)],
            "key_digest": "key", "presented_card_digests": {}, "leakage_audit": "NO_LITERAL_LEAK_FOUND",
            "evaluator_status": "VALID", "v3_total_credit": 0, "config_digest": "config", "escrow_rule": "rule",
            "proposer_kind": "baseline", "budget_fraction": 1, "library_versions": {}, "campaign_total_seconds": 10,
            "operator_timings": [{"universe_id": f"u{i}", "proposal_sha256": "a" * 64,
                                  "query_trace_without_transport_nonce_sha256": "b" * 64} for i in range(6)]}


def test_complete_trace_comparison_detects_a_changed_query_or_proposal():
    before = record()
    assert comparison([before], [deepcopy(before)])["equivalence_status"] == "PASS"
    for field in ("proposal_sha256", "query_trace_without_transport_nonce_sha256"):
        changed = deepcopy(before)
        changed["operator_timings"][0][field] = "c" * 64
        out = comparison([before], [changed])
        assert out["equivalence_status"] == "FAIL" and out["paired_service_speedup"]["n"] == 0


@pytest.mark.parametrize("missing", ["all", "one", "duplicate", "proposal", "query"])
def test_equal_missing_evidence_never_becomes_exact_equivalence(missing):
    incomplete = record()
    timings = incomplete["operator_timings"]
    if missing == "all":
        timings.clear()
    elif missing == "one":
        timings.pop()
    elif missing == "duplicate":
        timings[-1] = deepcopy(timings[0])
    else:
        del timings[0]["proposal_sha256" if missing == "proposal" else "query_trace_without_transport_nonce_sha256"]
    out = comparison([incomplete], [deepcopy(incomplete)])
    assert out["equivalence_status"] == "UNKNOWN"
    assert out["exact_matching_campaigns"] == 0 and out["paired_service_speedup"]["n"] == 0


def test_duplicate_and_missing_tasks_do_not_collapse_into_a_complete_comparison():
    assert comparison([], [])["equivalence_status"] == "UNKNOWN"
    run = record()
    for before, after in (([run, run], [run]), ([run], [run, run])):
        with pytest.raises(ValueError, match="duplicate comparison task"):
            comparison(before, after)
    out = comparison([run], [])
    assert out["equivalence_status"] == "UNKNOWN" and len(out["missing_reference_tasks"]) == 1


def test_retained_worker_failure_is_a_mismatch_not_an_exception_or_speedup():
    before = record()
    failed = {key: before[key] for key in ("arm", "seed", "campaign_id")}
    failed.update(status="WORKER_FAILED", reasons=["infrastructure"])
    out = comparison([before], [failed])
    assert out["equivalence_status"] == "FAIL" and out["paired_service_speedup"]["n"] == 0
    assert comparison([failed], [deepcopy(failed)])["equivalence_status"] == "UNKNOWN"


def test_explicit_method_failure_can_be_compared_but_missing_failure_cannot():
    run = record()
    timing = run["operator_timings"][0]
    del timing["proposal_sha256"]
    timing["proposer_failure"] = {"exception_type": "RuntimeError", "message": "the proposer failed: method failure"}
    assert comparison([run], [deepcopy(run)])["equivalence_status"] == "PASS"
    timing["proposer_failure"] = {}
    assert comparison([run], [deepcopy(run)])["equivalence_status"] == "UNKNOWN"
