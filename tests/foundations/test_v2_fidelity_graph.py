"""Roadmap V2 R2: FidelityGraph -- measured links, elimination only through an admitted in-domain link,
recorded margin-stratified false-elimination audit with suspension, and deterministic resurrection.
Includes the checkpoint-1 hostile-review counterexamples (H1-H5, M3-M5, L2-L4)."""

from __future__ import annotations

import dataclasses
import hashlib
import random

import pytest

from engcore.design.fidelity import FidelityLadder, FidelityRung
from engcore.design.fidelity_graph import (
    DiscrepancyStatus, EliminationLedger, FalseEliminationPolicy, FidelityGraph, FidelityGraphRefusal, FidelityLink, FidelityNode,
    HardRejection, HardRejectionBasis, LinkAdmissionPolicy, LinkAuditEvent, LinkStatus, PairedEvaluation, ScreeningDecision,
    ScreeningOutcome, Sense, ValidityDomain, draw_audit, measure_link, record_audit, resurrection_queue, screen,
)
from engcore.design.multifidelity import standard_ladder

LADDER = standard_ladder()
LOW = FidelityNode(LADDER.rung("analytic"), "model:beam", "euler_bernoulli", "1")
HIGH = FidelityNode(LADDER.rung("numerical"), "model:beam", "fem_p2", "1")
DOMAIN = ValidityDomain({"x": (0.0, 10.0)}, {"x": "m"})
POLICY = LinkAdmissionPolicy("campaign-7.admission", 20, 0.9, 0.8)
AUDIT = FalseEliminationPolicy("campaign-7.audit", fraction=0.2, strata=3, bound=0.1, min_audits=3)


def pairs(n=40, bias=0.5, noise=0.05, seed=1, x_max=10.0):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        x = x_max * i / (n - 1)
        low = 2.0 * x
        out.append(PairedEvaluation(f"c{i:03d}-{seed}", {"x": x}, low, low + bias + rng.gauss(0.0, noise)))
    return out


def measured(**kw):
    m = measure_link(pairs(**kw), threshold=10.0, sense=Sense.AT_MOST, near_band=1.0)
    return FidelityLink("beam.deflection", LOW, HIGH, "deflection", "mm", DOMAIN, m)


def admitted(**kw):
    return measured(**kw).admit(POLICY, actor="reviewer:a", reason="paired campaign")


def sc(key, value, link, x=5.0):
    return screen(key, low_value=value, point={"x": x}, link=link, low_node=LOW, observable="deflection")


def test_a_link_is_measured_not_declared():
    m = measure_link(pairs(), threshold=10.0, sense=Sense.AT_MOST, near_band=1.0)
    assert m.pairs == 40 and m.rank_correlation > 0.99 and m.discrepancy_status is DiscrepancyStatus.QUANTIFIED
    assert m.discrepancy_mean == pytest.approx(0.5, abs=0.05) and m.point_hull == {"x": (0.0, 10.0)}
    lo, hi = m.discrepancy_envelope
    assert lo <= min(p.high_value - p.low_value for p in pairs()) and hi >= max(p.high_value - p.low_value for p in pairs())
    with pytest.raises(FidelityGraphRefusal, match="at least 10"):
        measure_link(pairs()[:5], threshold=10.0, sense=Sense.AT_MOST, near_band=1.0, min_pairs_for_discrepancy=2)
    few = measure_link(pairs()[:5], threshold=10.0, sense=Sense.AT_MOST, near_band=1.0)
    assert few.discrepancy_status is DiscrepancyStatus.UNKNOWN and few.discrepancy_envelope is None  # never zero
    with pytest.raises(FidelityGraphRefusal, match="LOWER to a HIGHER"):
        FidelityLink("x", HIGH, LOW, "deflection", "mm", DOMAIN, m)


def test_admission_cannot_be_set_carried_over_or_widened():  # review H1, H2, M4
    m = measure_link(pairs(), threshold=10.0, sense=Sense.AT_MOST, near_band=1.0)
    with pytest.raises(FidelityGraphRefusal, match="admission is not a field"):
        FidelityLink("x", LOW, HIGH, "deflection", "mm", DOMAIN, m, status=LinkStatus.ADMITTED,
                     audit=(LinkAuditEvent("admitted", "x", "y"),))
    lk = admitted()
    with pytest.raises(FidelityGraphRefusal, match="admission is not a field"):
        dataclasses.replace(lk.remeasured(measure_link(pairs(seed=2), threshold=10.0, sense=Sense.AT_MOST, near_band=1.0),
                                          actor="lab", reason="new"), status=LinkStatus.ADMITTED)
    with pytest.raises(FidelityGraphRefusal, match="admission is not a field"):
        dataclasses.replace(lk, measurement=measure_link(pairs(seed=3), threshold=10.0, sense=Sense.AT_MOST, near_band=1.0))
    # the domain may not be declared wider than the measured points
    with pytest.raises(FidelityGraphRefusal, match="exceeds what the link was measured on"):
        FidelityLink("x", LOW, HIGH, "deflection", "mm", ValidityDomain({"x": (0.0, 1000.0)}, {"x": "m"}), m)
    with pytest.raises(FidelityGraphRefusal, match="never varied"):
        FidelityLink("x", LOW, HIGH, "deflection", "mm", ValidityDomain({"y": (0.0, 1.0)}, {"y": "m"}), m)
    # admission floors come from a policy record and are recorded
    assert lk.audit[-1].detail["policy_digest"] == POLICY.digest
    with pytest.raises(FidelityGraphRefusal, match="at least 10"):
        LinkAdmissionPolicy("p", 2, 0.0, 0.0)
    with pytest.raises(FidelityGraphRefusal, match="decision agreement"):
        measured().admit(LinkAdmissionPolicy("strict", 20, 0.9, 0.999), actor="a", reason="r")
    # a suspended link cannot be re-admitted on the same evaluation set
    suspended = lk.suspend(actor="auditor", reason="bad")
    with pytest.raises(FidelityGraphRefusal, match="new evaluation set"):
        suspended.remeasured(lk.measurement, actor="lab", reason="again")


def test_cheap_models_eliminate_only_through_an_admitted_in_domain_link():
    lk = admitted()
    d = sc("c1", 20.0, lk)
    assert d.outcome is ScreeningOutcome.ELIMINATE and d.margin > 0 and d.standing_digest == lk.standing_digest
    assert sc("c2", 9.4, lk).outcome is ScreeningOutcome.PROMOTE        # the envelope admits a pass
    assert sc("c3", 50.0, lk, x=20.0).outcome is ScreeningOutcome.PROMOTE  # outside the domain
    assert screen("c4", low_value=50.0, point={}, link=lk, low_node=LOW, observable="deflection").outcome is ScreeningOutcome.PROMOTE
    assert sc("c5", 50.0, measured()).outcome is ScreeningOutcome.PROMOTE  # measured, not admitted
    assert screen("c6", low_value=50.0, point={"x": 5.0}, link=None).outcome is ScreeningOutcome.PROMOTE
    assert sc("c7", None, lk).outcome is ScreeningOutcome.PROMOTE
    # review M3: a value from another realization or observable is not what the link measured
    other = FidelityNode(LADDER.rung("analytic"), "model:beam", "euler_bernoulli", "2")
    with pytest.raises(FidelityGraphRefusal, match="low realization and observable"):
        screen("c8", low_value=50.0, point={"x": 5.0}, link=lk, low_node=other, observable="deflection")
    with pytest.raises(FidelityGraphRefusal, match="low realization and observable"):
        screen("c8", low_value=50.0, point={"x": 5.0}, link=lk, low_node=LOW, observable="stress")


def test_hard_rejections_are_typed_and_input_only():  # review M5
    with pytest.raises(FidelityGraphRefusal, match="inputs only"):
        HardRejectionBasis(HardRejection.PHYSICAL_CONSTRAINT, "yield@1", "stress > yield")  # judged on a model output
    with pytest.raises(FidelityGraphRefusal, match="versioned"):
        HardRejectionBasis(HardRejection.LOGICAL_CONSTRAINT, "mass_positive", "negative mass", judged_on_inputs_only=True)
    with pytest.raises(FidelityGraphRefusal, match="content digest"):
        HardRejectionBasis(HardRejection.EXACT_DUPLICATE, "c0", "same candidate")
    with pytest.raises(FidelityGraphRefusal, match="HardRejectionBasis"):
        ScreeningDecision("c", ScreeningOutcome.REJECT_HARD, "meh")
    hard = HardRejectionBasis(HardRejection.LOGICAL_CONSTRAINT, "mass_positive@1", "negative mass", judged_on_inputs_only=True)
    ledger = EliminationLedger()
    ledger.record(screen("h1", low_value=None, point={}, link=None, hard_rejection=hard))
    graph = FidelityGraph(LADDER, (LOW, HIGH), ())
    assert resurrection_queue(ledger, graph, actor="s", constraint_versions={"mass_positive": "1"}) == ()
    assert resurrection_queue(ledger, graph, actor="s", constraint_versions={"mass_positive": "2"}) == ("h1",)


def test_the_ledger_refuses_fabricated_and_duplicate_eliminations():  # review H3, L3, L4
    lk = admitted()
    ledger = EliminationLedger()
    with pytest.raises(FidelityGraphRefusal, match="positive margin"):
        ScreeningDecision("c", ScreeningOutcome.ELIMINATE, "x", "beam.deflection", lk.version)
    forged = dataclasses.replace(sc("c1", 20.0, lk), low_value=9.0)   # claims elimination for a value that would promote
    with pytest.raises(FidelityGraphRefusal, match="does not reproduce"):
        ledger.record(forged, link=lk, low_node=LOW)
    with pytest.raises(FidelityGraphRefusal, match="against the link"):
        ledger.record(sc("c1", 20.0, lk))
    ledger.record(sc("c1", 20.0, lk), link=lk, low_node=LOW)
    with pytest.raises(FidelityGraphRefusal, match="already stands"):
        ledger.record(sc("c1", 20.0, lk), link=lk, low_node=LOW)
    head = ledger.head
    ledger.entries[0].payload["margin"] = 0.0                          # a copy: the stored entry is unchanged
    assert ledger.head == head
    with pytest.raises(dataclasses.FrozenInstanceError):
        ledger.entries[0].payload_json = "{}"
    again = EliminationLedger.from_dict(ledger.to_dict(), expected_head=ledger.head)
    assert again.head == ledger.head
    tampered = ledger.to_dict()
    tampered["entries"][0]["payload"]["margin"] = 0.0
    with pytest.raises(FidelityGraphRefusal, match="digest"):
        EliminationLedger.from_dict(tampered, expected_head=None)
    with pytest.raises(FidelityGraphRefusal, match="expected"):
        EliminationLedger.from_dict(ledger.to_dict(), expected_head="0" * 64)


def _eliminate(ledger, lk, n=30):
    keys = [f"e{i:02d}" for i in range(n)]
    for i, k in enumerate(keys):
        ledger.record(sc(k, 12.0 + i * 0.5, lk), link=lk, low_node=LOW)
    return keys


def test_the_audit_is_drawn_by_the_ledger_not_chosen_and_counts_cumulatively():  # review H4, H5, L2
    lk = admitted()
    ledger = EliminationLedger()
    keys = _eliminate(ledger, lk)
    with pytest.raises(FidelityGraphRefusal, match="no pending audit draw"):
        record_audit(ledger, lk, {"e29": 30.0}, AUDIT, actor="auditor")
    sample = draw_audit(ledger, lk, AUDIT)
    smallest = sorted(ledger.eliminations(), key=lambda e: e.payload["margin"])[: len(keys) // 3]
    assert set(sample) & {e.candidate_key for e in smallest}          # the near-threshold stratum is always audited
    with pytest.raises(FidelityGraphRefusal, match="still pending"):
        draw_audit(ledger, lk, AUDIT)
    with pytest.raises(FidelityGraphRefusal, match="exactly the drawn sample"):
        record_audit(ledger, lk, {k: 30.0 for k in list(sample)[:-1]}, AUDIT, actor="auditor")  # cherry-picking refused
    before = len(ledger.entries)
    with pytest.raises(FidelityGraphRefusal, match="not finite"):
        record_audit(ledger, lk, {**{k: 30.0 for k in sample}, sample[-1]: float("nan")}, AUDIT, actor="auditor")
    assert len(ledger.entries) == before                                # nothing half-written
    # one audited candidate actually passes: it is resurrected at once even though the link survives this audit
    loose = FalseEliminationPolicy("campaign-7.audit", fraction=0.2, strata=3, bound=0.5, min_audits=3)
    values = {k: 30.0 for k in sample}
    values[sample[0]] = 9.0
    lk2, result = record_audit(ledger, lk, values, loose, actor="auditor")
    assert lk2.status is LinkStatus.ADMITTED and result.false_eliminations == 1
    assert sample[0] in result.resurrected and sample[0] not in {e.candidate_key for e in ledger.eliminations()}
    # the rate accumulates across draws of the same standing: splitting audits into small batches does not reset it
    sample2 = draw_audit(ledger, lk2, loose)
    assert lk2.standing_digest == lk.standing_digest and sample2
    lk3, result2 = record_audit(ledger, lk2, {k: 9.0 for k in sample2}, loose, actor="auditor")
    assert result2.audited == result.audited + len(sample2)
    assert result2.false_eliminations == 1 + len(sample2)


def test_a_bad_link_is_suspended_and_every_elimination_comes_back():
    lk = admitted()
    graph = FidelityGraph(LADDER, (LOW, HIGH), (lk,))
    ledger = EliminationLedger()
    keys = _eliminate(ledger, lk)
    sample = draw_audit(ledger, lk, AUDIT)
    lk2, result = record_audit(ledger, lk, {k: 9.0 for k in sample}, AUDIT, actor="auditor")  # all pass: the cheap model was wrong
    assert result.false_elimination_rate == 1.0 and result.suspended and lk2.status is LinkStatus.SUSPENDED
    back = resurrection_queue(ledger, graph.with_link(lk2), actor="scheduler")
    assert set(back) | set(result.resurrected) == set(keys)
    assert ledger.eliminations() == () and resurrection_queue(ledger, graph.with_link(lk2), actor="scheduler") == ()


def test_a_small_audit_never_reads_as_zero_and_a_remeasured_link_resurrects():
    lk = admitted()
    ledger = EliminationLedger()
    for i in range(4):
        ledger.record(sc(f"s{i}", 30.0, lk), link=lk, low_node=LOW)
    sample = draw_audit(ledger, lk, FalseEliminationPolicy("p", 0.25, 1, 0.1, 3))
    lk2, result = record_audit(ledger, lk, {k: 40.0 for k in sample}, FalseEliminationPolicy("p", 0.25, 1, 0.1, 3), actor="a")
    assert result.false_elimination_rate is None and not result.suspended and lk2.status is LinkStatus.ADMITTED
    remeasured = lk2.remeasured(measure_link(pairs(seed=9), threshold=10.0, sense=Sense.AT_MOST, near_band=1.0),
                                actor="lab", reason="new campaign")
    graph = FidelityGraph(LADDER, (LOW, HIGH), (remeasured,))
    assert set(resurrection_queue(ledger, graph, actor="scheduler")) == {"s0", "s1", "s2", "s3"}


def test_nodes_must_sit_on_the_graphs_ladder():
    other = FidelityLadder("x", "1", (FidelityRung("analytic", 0), FidelityRung("numerical", 5)))
    with pytest.raises(FidelityGraphRefusal, match="not the ladder's rung"):
        FidelityGraph(other, (LOW, HIGH))
    assert hashlib.sha256(b"").hexdigest()  # keep import used
