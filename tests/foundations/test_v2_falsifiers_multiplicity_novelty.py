"""Roadmap V2 R5: sealed falsifiers and verdicts, multiplicity accounting, novelty against a frozen snapshot."""

from __future__ import annotations

import hashlib

import pytest

from engcore.blindfold.expression import c, evaluate, mul, pw, structure_digest, v
from engcore.claims.falsification import (
    CriterionKind, EvidenceItem, FalsificationRefused, Falsifier, FalsifierRegistry, Verdict, VerdictStore, apply_verdicts, judge,
    verify_status,
)
from engcore.claims.multiplicity import MultiplicityLedger, MultiplicityRefused, PromotedResult, promote
from engcore.claims.novelty import (
    NoveltyRefused, PriorArtEntry, PriorArtSnapshot, apply_novelty, check_novelty, numeric_equivalence,
)
from engcore.sria.decision import Hypothesis, HypothesisKind, HypothesisPrediction, HypothesisStatus, NoveltyStatus, VerdictReference

LAW = mul(c(2.0), pw(v("x"), 1.37))


def hypothesis(**kw):
    base = dict(hypothesis_id="h1", model_ref="law:candidate", kind=HypothesisKind.EQUATION, statement="y = a x^1.37",
                structure_digest=structure_digest(LAW), predictions=(HypothesisPrediction("y", "m", "cond:x=2"),),
                falsifier_refs=("f1@v1",))
    base.update(kw)
    return Hypothesis(**base)


def falsifier(h, **kw):
    base = dict(falsifier_id="f1", hypothesis_id=h.hypothesis_id, hypothesis_content_digest=h.content_digest, observable="y", unit="m",
                test_conditions={"x": 2.0}, evidence_source="escrow:observe", criterion=CriterionKind.PREDICTION_DEVIATION,
                parameters={"k": 3.0})
    base.update(kw)
    return Falsifier(**base)


def ev(eid, value, u=0.01, source="escrow:observe"):
    return EvidenceItem(eid, hashlib.sha256(eid.encode()).hexdigest(), source, "y", "m", value, u)


def test_a_falsifier_is_sealed_before_the_evidence_it_judges():
    h = hypothesis()
    reg = FalsifierRegistry()
    f = falsifier(h)
    reg.expose("early", evidence_digest=hashlib.sha256(b"early").hexdigest())   # seen before the falsifier existed
    reg.seal(f)
    with pytest.raises(FalsificationRefused, match="post-hoc"):
        judge(f.digest, reg, ev("early", 5.2), predicted=5.17, prediction_uncertainty=0.01)
    with pytest.raises(FalsificationRefused, match="never exposed"):
        judge(f.digest, reg, ev("unlogged", 5.2), predicted=5.17, prediction_uncertainty=0.01)
    reg.expose("late", evidence_digest=hashlib.sha256(b"late").hexdigest())
    ok = judge(f.digest, reg, ev("late", 5.2), predicted=5.17, prediction_uncertainty=0.01)
    assert ok.verdict is Verdict.NOT_REFUTED
    with pytest.raises(FalsificationRefused, match="admissible source"):
        judge(f.digest, reg, ev("late", 5.2, source="llm:opinion"), predicted=5.17, prediction_uncertainty=0.01)
    with pytest.raises(FalsificationRefused, match="not sealed"):
        judge(falsifier(h, falsifier_id="f9").digest, reg, ev("late", 5.2), predicted=5.17, prediction_uncertainty=0.01)


def test_unknown_uncertainty_is_inconclusive_never_zero():
    h = hypothesis()
    reg = FalsifierRegistry()
    f = falsifier(h)
    reg.seal(f)
    reg.expose("e", evidence_digest=hashlib.sha256(b"e").hexdigest())
    assert judge(f.digest, reg, ev("e", 9.9, u=None), predicted=5.17, prediction_uncertainty=0.01).verdict is Verdict.INCONCLUSIVE
    assert judge(f.digest, reg, ev("e", 9.9), predicted=5.17, prediction_uncertainty=None).verdict is Verdict.INCONCLUSIVE
    assert judge(f.digest, reg, ev("e", 9.9), predicted=5.17, prediction_uncertainty=0.01).verdict is Verdict.REFUTED
    with pytest.raises(FalsificationRefused, match="never defaulted"):
        falsifier(h, parameters={})


def test_a_post_hoc_change_is_a_new_sealed_revision_judged_only_on_later_evidence():
    h = hypothesis()
    reg = FalsifierRegistry()
    f = falsifier(h)
    reg.seal(f)
    reg.expose("e1", evidence_digest=hashlib.sha256(b"e1").hexdigest())
    loosened = f.revise(parameters={"k": 50.0})                     # widened after seeing e1
    assert loosened.version == 2 and loosened.supersedes == f.digest and f.parameters["k"] == 3.0
    reg.seal(loosened)
    with pytest.raises(FalsificationRefused, match="post-hoc"):
        judge(loosened.digest, reg, ev("e1", 9.9), predicted=5.17, prediction_uncertainty=0.01)


def test_status_comes_from_every_verdict_and_a_refutation_cannot_be_left_out():
    h = hypothesis(falsifier_refs=("f1@v1", "f2@v1"))
    reg, store = FalsifierRegistry(), VerdictStore()
    f1, f2 = falsifier(h), falsifier(h, falsifier_id="f2", test_conditions={"x": 3.0})
    reg.seal(f1)
    reg.seal(f2)
    for e in ("a", "b"):
        reg.expose(e, evidence_digest=hashlib.sha256(e.encode()).hexdigest())
    store.add(judge(f1.digest, reg, ev("a", 5.2), predicted=5.17, prediction_uncertainty=0.01))
    assert apply_verdicts(h, reg, store).status is HypothesisStatus.UNKNOWN          # f2 not judged yet: not survival
    store.add(judge(f2.digest, reg, ev("b", 99.0), predicted=9.0, prediction_uncertainty=0.01))
    refuted = apply_verdicts(h, reg, store)
    assert refuted.status is HypothesisStatus.REFUTED and verify_status(refuted, reg, store) == []
    # a SURVIVING claim citing only the passing verdict is caught: the store holds a refutation for this content
    passing = store.for_content(h.hypothesis_id, h.content_digest)
    good = [x for x in passing if x.verdict is Verdict.NOT_REFUTED][0]
    claim = h.revise(status=HypothesisStatus.SURVIVING,
                     status_basis=(VerdictReference(good.falsifier_ref, good.digest, "not_refuted", h.content_digest),))
    assert any("establish refuted" in p for p in verify_status(claim, reg, store))
    fake = h.revise(status=HypothesisStatus.SURVIVING,
                    status_basis=(VerdictReference("f1@v1", "e" * 64, "not_refuted", h.content_digest),))
    assert any("not in the verdict store" in p for p in verify_status(fake, reg, store))


def test_multiplicity_binds_every_promoted_result():
    led = MultiplicityLedger("camp-1")
    led.count("generated", 1_000_000)
    led.count("deduplicated", 312_000)
    led.count("admitted", 9_000)
    led.evaluated("analytic", 9_000)
    led.evaluated("numerical", 40)
    led.count("promoted", 3)
    led.count("hypotheses_tested", 40)
    led.seed("s-17")
    led.strategy("careful", "1")
    r = promote("best", "h1", led)
    assert r.multiplicity.selected_from == 1_000_000 and r.multiplicity.family_size == 40
    assert "selected from 1000000 generated candidates" in r.to_dict()["multiplicity_statement"]
    with pytest.raises(MultiplicityRefused, match="does not match"):
        PromotedResult("x", "h1", r.multiplicity, "0" * 64)
    empty = MultiplicityLedger("camp-2")
    with pytest.raises(MultiplicityRefused, match="records no promotion"):
        promote("x", "h1", empty)
    with pytest.raises(MultiplicityRefused, match="unknown counter"):
        led.count("best_of", 1)


def test_novelty_is_checked_against_a_frozen_snapshot_and_never_reads_novel():
    known = PriorArtEntry("textbook-1", structure_digest(mul(c(1.0), pw(v("x"), 1.37))), "doi:10.0/known", mul(c(1.0), pw(v("x"), 1.37)))
    other = PriorArtEntry("textbook-2", structure_digest(mul(c(1.0), pw(v("x"), 2.0))), "doi:10.0/other", mul(c(1.0), pw(v("x"), 2.0)))
    snap = PriorArtSnapshot("prior-art-2026-10", ("equation",), (known, other))
    frozen = snap.digest
    h = hypothesis()
    hit = check_novelty(h, snap, frozen_digest=frozen)
    assert hit.status is NoveltyStatus.KNOWN_EQUIVALENT and hit.matched_entry == "textbook-1"
    fresh = hypothesis(structure_digest=structure_digest(mul(c(1.0), pw(v("x"), 0.83))), statement="y = a x^0.83")
    assert check_novelty(fresh, snap, frozen_digest=frozen).status is NoveltyStatus.POSSIBLY_NOVEL
    assert check_novelty(hypothesis(kind=HypothesisKind.MECHANISM, model_ref="m", structure_digest="z" * 64), snap,
                         frozen_digest=frozen).status is NoveltyStatus.NOVELTY_UNRESOLVED
    assert check_novelty(hypothesis(structure_digest=""), snap, frozen_digest=frozen).status is NoveltyStatus.NOVELTY_UNRESOLVED
    # a numerically equivalent law in a different written form is known, not novel
    rewritten = mul(pw(v("x"), 0.37), v("x"), c(5.0))
    eq = numeric_equivalence(evaluate, [{"x": 1.5}, {"x": 3.0}, {"x": 7.0}], rel_tol=1e-9)
    alt = hypothesis(structure_digest=structure_digest(rewritten))
    assert check_novelty(alt, snap, frozen_digest=frozen, equivalence=eq, expression=rewritten).status is NoveltyStatus.KNOWN_EQUIVALENT
    with pytest.raises(NoveltyRefused, match="changed after it was frozen"):
        check_novelty(h, PriorArtSnapshot("prior-art-2026-10", ("equation",), (other,)), frozen_digest=frozen)
    applied = apply_novelty(fresh, check_novelty(fresh, snap, frozen_digest=frozen))
    assert applied.novelty_status is NoveltyStatus.POSSIBLY_NOVEL and applied.knowledge_snapshot_ref == frozen and applied.novelty_basis
