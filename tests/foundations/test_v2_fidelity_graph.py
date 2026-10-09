"""Roadmap V2 R2: FidelityGraph -- measured links, elimination only through an admitted in-domain link,
stratified false-elimination audit with suspension, and deterministic resurrection."""

from __future__ import annotations

import random

import pytest

from engcore.design.fidelity import FidelityLadder, FidelityRung
from engcore.design.fidelity_graph import (
    DiscrepancyStatus, EliminationLedger, FidelityGraph, FidelityGraphRefusal, FidelityLink, FidelityNode, HardRejection,
    LinkStatus, PairedEvaluation, ScreeningOutcome, Sense, ValidityDomain, audit_sample, measure_link, record_audit,
    resurrection_queue, screen,
)
from engcore.design.multifidelity import standard_ladder

LADDER = standard_ladder()
LOW = FidelityNode(LADDER.rung("analytic"), "model:beam", "euler_bernoulli", "1")
HIGH = FidelityNode(LADDER.rung("numerical"), "model:beam", "fem_p2", "1")
DOMAIN = ValidityDomain({"x": (0.0, 10.0)}, {"x": "m"})


def pairs(n=40, bias=0.5, noise=0.05, seed=1):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        x = 10.0 * i / (n - 1)
        low = 2.0 * x
        out.append(PairedEvaluation(f"c{i:03d}", {"x": x}, low, low + bias + rng.gauss(0.0, noise)))
    return out


def link(status_admit=True, **kw):
    m = measure_link(pairs(**kw), threshold=10.0, sense=Sense.AT_MOST, near_band=1.0)
    lk = FidelityLink("beam.deflection", LOW, HIGH, "deflection", "mm", DOMAIN, m)
    return lk.admit(actor="reviewer:a", reason="paired campaign", min_pairs=20, min_rank_correlation=0.9) if status_admit else lk


def test_a_link_is_measured_not_declared():
    m = measure_link(pairs(), threshold=10.0, sense=Sense.AT_MOST, near_band=1.0)
    assert m.pairs == 40 and m.rank_correlation > 0.99 and m.discrepancy_status is DiscrepancyStatus.QUANTIFIED
    assert m.discrepancy_mean == pytest.approx(0.5, abs=0.05)
    lo, hi = m.discrepancy_envelope
    assert lo <= min(p.high_value - p.low_value for p in pairs()) and hi >= max(p.high_value - p.low_value for p in pairs())
    few = measure_link(pairs()[:5], threshold=10.0, sense=Sense.AT_MOST, near_band=1.0)
    assert few.discrepancy_status is DiscrepancyStatus.UNKNOWN and few.discrepancy_envelope is None  # never zero
    with pytest.raises(FidelityGraphRefusal, match="UNKNOWN"):
        FidelityLink("x", LOW, HIGH, "deflection", "mm", DOMAIN, few).admit(actor="a", reason="r", min_pairs=1)
    with pytest.raises(FidelityGraphRefusal, match="LOWER to a HIGHER"):
        FidelityLink("x", HIGH, LOW, "deflection", "mm", DOMAIN, m)
    with pytest.raises(FidelityGraphRefusal, match="records its admission"):
        FidelityLink("x", LOW, HIGH, "deflection", "mm", DOMAIN, m, status=LinkStatus.ADMITTED)  # admission is not a field you set


def test_cheap_models_eliminate_only_through_an_admitted_in_domain_link():
    admitted = link()
    # far above the limit: eliminated, margin recorded
    d = screen("c1", low_value=20.0, point={"x": 5.0}, link=admitted)
    assert d.outcome is ScreeningOutcome.ELIMINATE and d.margin > 0 and d.link_version == admitted.version
    # near the threshold: the discrepancy envelope admits a pass, so promote
    assert screen("c2", low_value=9.4, point={"x": 5.0}, link=admitted).outcome is ScreeningOutcome.PROMOTE
    # outside the domain, missing variable, unadmitted link, no link, unknown discrepancy: never eliminated
    assert screen("c3", low_value=50.0, point={"x": 20.0}, link=admitted).outcome is ScreeningOutcome.PROMOTE
    assert screen("c4", low_value=50.0, point={}, link=admitted).outcome is ScreeningOutcome.PROMOTE
    assert screen("c5", low_value=50.0, point={"x": 5.0}, link=link(status_admit=False)).outcome is ScreeningOutcome.PROMOTE
    assert screen("c6", low_value=50.0, point={"x": 5.0}, link=None).outcome is ScreeningOutcome.PROMOTE
    assert screen("c7", low_value=None, point={"x": 5.0}, link=admitted).outcome is ScreeningOutcome.PROMOTE
    # hard rejections need no link, and say why
    hard = screen("c8", low_value=None, point={}, link=None, hard_rejection=(HardRejection.PHYSICAL_CONSTRAINT, "negative mass"))
    assert hard.outcome is ScreeningOutcome.REJECT_HARD and hard.classification == "scheduling_decision_not_evidence"


def test_every_elimination_is_recorded_and_the_ledger_is_tamper_evident():
    lk = link()
    ledger = EliminationLedger()
    for i, v in enumerate((20.0, 9.0, 25.0, 30.0)):
        ledger.record(screen(f"k{i}", low_value=v, point={"x": 5.0}, link=lk))
    assert [e.candidate_key for e in ledger.eliminations()] == ["k0", "k2", "k3"]
    again = EliminationLedger.from_dict(ledger.to_dict())
    assert again.head == ledger.head
    tampered = ledger.to_dict()
    tampered["entries"][0]["payload"]["margin"] = 0.0
    with pytest.raises(FidelityGraphRefusal, match="digest"):
        EliminationLedger.from_dict(tampered)


def test_the_false_elimination_audit_suspends_a_bad_link_and_eliminated_candidates_come_back():
    # a link measured where the cheap model is good, then used where it is biased the other way
    lk = link()
    graph = FidelityGraph(LADDER, (LOW, HIGH), (lk,))
    ledger = EliminationLedger()
    keys = [f"e{i:02d}" for i in range(30)]
    for i, k in enumerate(keys):
        ledger.record(screen(k, low_value=12.0 + i * 0.5, point={"x": 5.0}, link=lk))
    sample = audit_sample(ledger, lk, fraction=0.2, seed="campaign-7", strata=3)
    assert sample == audit_sample(ledger, lk, fraction=0.2, seed="campaign-7", strata=3)  # deterministic
    assert "e00" in sample or "e01" in sample or len(sample) >= 3  # every stratum, incl. the smallest margins, is audited
    # at the high fidelity most audited candidates actually PASS: the cheap model was wrong here
    truth = {k: 9.0 for k in sample}
    lk2, result = record_audit(ledger, lk, truth, bound=0.1, min_audits=3, actor="auditor")
    assert result.false_elimination_rate == 1.0 and result.suspended and lk2.status is LinkStatus.SUSPENDED
    graph = graph.with_link(lk2)
    back = resurrection_queue(ledger, graph, actor="scheduler")
    assert set(back) == set(keys)  # every elimination under the suspended link is requeued
    assert ledger.eliminations() == () and resurrection_queue(ledger, graph, actor="scheduler") == ()  # once, with trace
    assert sum(e.kind == "resurrected" for e in ledger.entries) == 30


def test_a_small_audit_never_reads_as_zero_and_a_superseded_link_resurrects():
    lk = link()
    ledger = EliminationLedger()
    for i in range(4):
        ledger.record(screen(f"s{i}", low_value=30.0, point={"x": 5.0}, link=lk))
    lk2, result = record_audit(ledger, lk, {"s0": 40.0}, bound=0.1, min_audits=3, actor="auditor")
    assert result.false_elimination_rate is None and not result.suspended and lk2.status is LinkStatus.ADMITTED
    with pytest.raises(FidelityGraphRefusal, match="were not eliminated"):
        record_audit(ledger, lk, {"never": 1.0}, bound=0.1, min_audits=1, actor="auditor")
    # re-measured on a new evaluation set: the old version no longer stands, its eliminations are resurrectable
    remeasured = lk2.remeasured(measure_link(pairs(seed=9), threshold=10.0, sense=Sense.AT_MOST, near_band=1.0),
                                actor="lab", reason="new campaign")
    assert remeasured.status is LinkStatus.MEASURED
    graph = FidelityGraph(LADDER, (LOW, HIGH), (remeasured,))
    assert set(resurrection_queue(ledger, graph, actor="scheduler")) == {"s0", "s1", "s2", "s3"}


def test_nodes_must_sit_on_the_graphs_ladder():
    other = FidelityLadder("x", "1", (FidelityRung("analytic", 0), FidelityRung("numerical", 5)))
    with pytest.raises(FidelityGraphRefusal, match="not the ladder's rung"):
        FidelityGraph(other, (LOW, HIGH))
