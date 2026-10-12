"""Roadmap V2 R8: the discovery performance benchmark runs, reports per tier, and emits compact batch records."""

from __future__ import annotations

from tools import discovery_performance as perf


def test_the_benchmark_reports_each_tier_as_batch_records():
    batches, summary = perf.tier1(600, seed=3, high_cost_s=60.0)
    assert {b.tier for b in batches} == {"tier1_raw_low_fidelity", "tier1_screen_and_record", "tier1_audit"}
    assert all(len(b.ids_digest) == 64 for b in batches)                         # one digest per batch, not one record per item
    assert summary["promoted"] + summary["eliminated"] <= 600 and summary["useful_promotions"] <= summary["promoted"]
    assert summary["declared_high_fidelity_cost_s"] == 60.0                       # the cost model is declared, and says so
    rate = summary["false_elimination_rate_recorded_audit"]
    assert rate is None or 0.0 <= rate <= 1.0                                     # None below min_audits: never read as 0
    t0 = perf.tier0(500, seed=3)
    assert t0.items == 500 and t0.accepted + t0.rejected == 500
    t2 = perf.tier2(50)
    assert t2.rejected == 13                                                      # every 4th release is refuting (0, 4, ..., 48)
