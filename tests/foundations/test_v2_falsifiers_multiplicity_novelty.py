"""Roadmap V2 R5: sealed falsifiers and verdicts, multiplicity accounting, novelty against a sealed snapshot
(incl. the checkpoint-3 hostile review)."""

from __future__ import annotations

import dataclasses
import itertools

import pytest

from engcore.blindfold.expression import c, evaluate, mul, pw, structure_digest, v
from engcore.claims.falsification import (
    K_MAX, CriterionKind, EvidenceSource, ExposureAuthority, FalsificationRefused, Falsifier, FalsifierRegistry, FalsifierVerdict,
    Verdict, apply_verdicts, judge, verify_status,
)
from engcore.claims.multiplicity import MultiplicityContext, MultiplicityLedger, MultiplicityRefused, PromotedResult, promote
from engcore.claims.novelty import (
    Canonicalizer, EquivalenceSpec, NoveltyCheck, NoveltyLedger, NoveltyRefused, PriorArtEntry, PriorArtSnapshot, apply_novelty,
    check_novelty,
)
from engcore.sria.decision import Hypothesis, HypothesisKind, HypothesisPrediction, HypothesisStatus, NoveltyStatus, VerdictReference

LAW = mul(c(2.0), pw(v("x"), 1.37))
SRC = EvidenceSource.ESCROW_OBSERVATION
_ids = itertools.count()


def hypothesis(**kw):
    base = dict(hypothesis_id="h1", model_ref="law:candidate", kind=HypothesisKind.EQUATION, statement="y = a x^1.37",
                statement_payload={"expression": LAW}, structure_digest=structure_digest(LAW),
                predictions=(HypothesisPrediction("y", "m", "cond:x=2"),), falsifier_refs=("f1@v1",))
    base.update(kw)
    return Hypothesis(**base)


def falsifier(h, **kw):
    base = dict(falsifier_id="f1", hypothesis_id=h.hypothesis_id, hypothesis_content_digest=h.content_digest, observable="y", unit="m",
                test_conditions={"x": 2.0}, evidence_source=SRC, criterion=CriterionKind.PREDICTION_DEVIATION,
                parameters={"k": 3.0, "predicted": 5.17, "prediction_uncertainty": 0.01, "resolution": 0.2})
    base.update(kw)
    return Falsifier(**base)


def setup(campaign="c"):
    auth = ExposureAuthority("escrow-1")
    return auth, auth.registry(campaign)


def release(auth, value, u=0.01, **kw):
    return auth.release(evidence_id=f"e{next(_ids)}", source=kw.pop("source", SRC), observable="y", unit="m", value=value,
                        uncertainty=u, conditions={"x": 2.0}, **kw)


# ---------------------------------------------------------------------------- falsification


def test_the_authority_clock_orders_seals_and_exposures():
    auth, reg = setup()
    h = hypothesis()
    early = release(auth, 5.2)                                  # the proposer saw this before writing the falsifier ...
    f = falsifier(h)
    reg.seal(f)
    with pytest.raises(FalsificationRefused, match="post-hoc"):
        judge(f.digest, reg, early)                              # ... and cannot "expose" it later: the clock is the authority's
    with pytest.raises(FalsificationRefused, match="post-hoc"):  # re-releasing the same data keeps its FIRST exposure (F5)
        judge(f.digest, reg, auth.release(evidence_id="copy", source=SRC, observable="y", unit="m", value=5.2, uncertainty=0.01,
                                          conditions={"x": 2.0}))
    late = release(auth, 5.21)                                 # a NEW measurement after the seal
    assert judge(f.digest, reg, late).verdict is Verdict.NOT_REFUTED
    forged = dataclasses.replace(late, value=99.0)               # a value swapped under a released item (F5)
    with pytest.raises(FalsificationRefused, match="not released by this registry's exposure authority"):
        judge(f.digest, reg, forged)
    other = ExposureAuthority("elsewhere")
    with pytest.raises(FalsificationRefused, match="not released"):
        judge(f.digest, reg, other.release(evidence_id="x", source=SRC, observable="y", unit="m", value=5.2, uncertainty=0.01))
    with pytest.raises(FalsificationRefused, match="admissible source"):
        judge(f.digest, reg, release(auth, 5.22, source=EvidenceSource.MEASUREMENT_RECORD))
    with pytest.raises(FalsificationRefused, match="evidence source must be one of"):      # free-text sources are gone (F10)
        falsifier(h, evidence_source="caller:assertion")
    with pytest.raises(FalsificationRefused, match="issued by its exposure authority"):    # no forked registry (F2)
        FalsifierRegistry(auth, "c")
    assert auth.registry("c") is reg
    with pytest.raises(FalsificationRefused, match="non-finite"):                          # NaN is not evidence (F8)
        release(auth, float("nan"))


def test_the_prediction_k_and_resolution_are_sealed_never_supplied_at_judge_time():
    h = hypothesis()
    with pytest.raises(FalsificationRefused, match="seals"):                               # F1: nothing supplied later
        falsifier(h, parameters={"k": 3.0, "resolution": 0.2})
    with pytest.raises(FalsificationRefused, match="cannot fail"):                         # F7: k is bounded
        falsifier(h, parameters={"k": K_MAX * 10, "predicted": 5.17, "resolution": 0.2})
    auth, reg = setup()
    f = falsifier(h)
    reg.seal(f)
    assert judge(f.digest, reg, release(auth, 9.9)).verdict is Verdict.REFUTED             # the sealed prediction decides
    vague = release(auth, 5.17, u=1e6)                                                     # F7: uninformative evidence
    assert judge(f.digest, reg, vague).verdict is Verdict.INCONCLUSIVE
    exact = release(auth, 5.171, u=0.0)                                                    # F9: zero uncertainty is a claim
    assert judge(f.digest, reg, exact).verdict is Verdict.INCONCLUSIVE
    unknown = release(auth, 9.8, u=None)
    assert judge(f.digest, reg, unknown).verdict is Verdict.INCONCLUSIVE                   # UNKNOWN never becomes zero
    h2 = hypothesis(hypothesis_id="h2")
    f2 = falsifier(h2, falsifier_id="g", parameters={"k": 3.0, "predicted": 5.17, "resolution": 0.2})   # u_pred UNKNOWN
    reg.seal(f2)
    assert judge(f2.digest, reg, release(auth, 9.7)).verdict is Verdict.INCONCLUSIVE


def test_every_verdict_is_in_the_chain_and_cannot_be_shopped_forged_or_omitted():
    auth, reg = setup()
    h = hypothesis(falsifier_refs=("f1@v1", "f2@v1"))
    f1, f2 = falsifier(h), falsifier(h, falsifier_id="f2", test_conditions={"x": 3.0})
    reg.seal(f1)
    reg.seal(f2)
    judge(f1.digest, reg, release(auth, 5.2))
    assert apply_verdicts(h, reg).status is HypothesisStatus.UNKNOWN                      # f2 not judged yet: not survival
    judge(f2.digest, reg, release(auth, 99.0))                                             # refuted ...
    judge(f2.digest, reg, release(auth, 5.18))                                             # ... then "shopped" on other data
    refuted = apply_verdicts(h, reg)
    assert refuted.status is HypothesisStatus.REFUTED and verify_status(refuted, reg) == []
    good = [x for x in reg.verdicts_for("h1", h.content_digest) if x.verdict is Verdict.NOT_REFUTED]
    claim = h.revise(status=HypothesisStatus.SURVIVING,
                     status_basis=tuple(VerdictReference(x.falsifier_ref, x.digest, "not_refuted", h.content_digest) for x in good))
    assert any("establishes refuted" in p for p in verify_status(claim, reg))
    fake = FalsifierVerdict(f2.digest, "f2@v1", "h1", h.content_digest, "e", "0" * 64, 999, 1, Verdict.NOT_REFUTED, 5.17, 5.17, 3.0,
                            0.01, "forged")
    forged = h.revise(status=HypothesisStatus.SURVIVING,
                      status_basis=(VerdictReference("f2@v1", fake.digest, "not_refuted", h.content_digest),))
    assert any("not in the registry chain" in p for p in verify_status(forged, reg))
    # F3: listing fewer falsifiers than are sealed, or one not sealed here, is refused
    with pytest.raises(FalsificationRefused, match="lists falsifiers"):
        apply_verdicts(h.revise(falsifier_refs=("f2@v1",)), reg)
    with pytest.raises(FalsificationRefused, match="lists falsifiers"):
        apply_verdicts(h.revise(falsifier_refs=("f1@v1", "f2@v1", "f3@v1")), reg)


def test_a_refutation_survives_falsifier_revision_and_versions_are_a_chain():
    auth, reg = setup()
    h = hypothesis()
    f = falsifier(h)
    reg.seal(f)
    judge(f.digest, reg, release(auth, 9.9))                                               # REFUTED by v1
    loosened = f.revise(parameters={"k": 9.0, "predicted": 5.17, "prediction_uncertainty": 0.5, "resolution": 10.0})
    assert loosened.version == 2 and loosened.supersedes == f.digest
    h2 = h.revise(falsifier_refs=("f1@v2",))
    assert h2.content_digest == h.content_digest and h2.status is HypothesisStatus.PROPOSED     # the claim is the same
    reg.seal(loosened)
    assert judge(loosened.digest, reg, release(auth, 9.5)).verdict is Verdict.NOT_REFUTED       # passes the loosened test ...
    assert apply_verdicts(h2, reg).status is HypothesisStatus.REFUTED                      # F4: not laundered by v2
    with pytest.raises(FalsificationRefused, match="already sealed"):
        reg.seal(falsifier(h, parameters={"k": 4.0, "predicted": 5.17, "prediction_uncertainty": 0.01, "resolution": 0.2}))
    with pytest.raises(FalsificationRefused, match="supersedes the sealed previous version"):
        reg.seal(dataclasses.replace(loosened, version=5))
    with pytest.raises(FalsificationRefused, match="names the falsifier it supersedes"):
        falsifier(h, version=2)
    with pytest.raises(ValueError, match="stated claim"):                                 # F12
        Hypothesis(hypothesis_id="n", model_ref="m", kind=HypothesisKind.EQUATION, description="claim lives only here",
                   falsifier_refs=("f1@v1",), status=HypothesisStatus.SURVIVING,
                   status_basis=(VerdictReference("f1@v1", "a" * 64, "not_refuted", "b" * 64),))


def test_survival_needs_every_listed_falsifier_not_refuted():
    auth, reg = setup()
    h = hypothesis()
    f = falsifier(h)
    reg.seal(f)
    judge(f.digest, reg, release(auth, 5.2))
    survived = apply_verdicts(h, reg)
    assert survived.status is HypothesisStatus.SURVIVING and verify_status(survived, reg) == []
    assert verify_status(survived, setup("other")[1])                                       # another chain does not hold it


# ---------------------------------------------------------------------------- multiplicity


def test_multiplicity_records_ids_checks_the_stage_chain_and_binds_every_promotion():
    led = MultiplicityLedger("camp-1")
    led.count("generated", 1_000_000)
    led.count("deduplicated", 312_000)
    led.count("admitted", 9_000)
    led.evaluated("analytic", 9_000)
    led.evaluated("numerical", 40)
    for i in range(40):
        led.tested(f"h{i}")
    led.seed("s-17")
    led.strategy("careful", "1")
    r = promote("best", "h1", led)
    assert r.multiplicity.selected_from == 1_000_000 and r.multiplicity.family_size == 40 and r.multiplicity.counts["promoted"] == 1
    assert "selected from 1000000 generated candidates" in r.to_dict()["multiplicity_statement"]
    with pytest.raises(TypeError):                                                         # M3: immutable once bound
        r.multiplicity.counts["generated"] = 1
    with pytest.raises(MultiplicityRefused, match="does not match"):
        PromotedResult("x", "h1", r.multiplicity, "0" * 64)
    with pytest.raises(MultiplicityRefused, match="does not record this hypothesis"):     # M2: one context, one promotion
        PromotedResult("x", "h7", r.multiplicity, r.multiplicity.digest)
    with pytest.raises(MultiplicityRefused, match="issued by its campaign's ledger"):     # M2: no hand-built context
        MultiplicityContext("other", {"generated": 1, "promoted": 1, "hypotheses_tested": 1}, {}, {}, (), (), ("h1",), ("h1",), "0" * 64)
    with pytest.raises(MultiplicityRefused, match="already has an open ledger"):
        MultiplicityLedger("camp-1")
    with pytest.raises(MultiplicityRefused, match="recorded by id"):
        led.count("promoted", 1)
    with pytest.raises(MultiplicityRefused, match="never recorded as tested|recorded as tested"):
        promote("y", "never-tested", led)
    empty = MultiplicityLedger("camp-2")                                                    # M1: a zero-candidate promotion
    empty.tested("h1")
    with pytest.raises(MultiplicityRefused, match="generated and admitted"):
        promote("x", "h1", empty)
    bad = MultiplicityLedger("camp-3")
    bad.count("generated", 5)
    bad.count("deduplicated", 50)
    with pytest.raises(MultiplicityRefused, match="missed a stage"):
        bad.context()
    later = r.rebind(led)
    led.count("generated", 10)
    assert r.rebind(led).multiplicity.selected_from == 1_000_010 and later.multiplicity.selected_from == 1_000_000
    for bad_call in (lambda: led.evaluated("x", 1.5), lambda: led.compute("s", float("inf")), lambda: led.seed(""),
                     lambda: led.strategy("", "1")):                                       # M4
        with pytest.raises(MultiplicityRefused):
            bad_call()


# ---------------------------------------------------------------------------- novelty


CANON = Canonicalizer("blindfold.structure/2", structure_digest)
KNOWN = mul(c(1.0), pw(v("x"), 1.37))


def snapshot(entries=None, **kw):
    entries = entries if entries is not None else (
        PriorArtEntry("textbook-1", structure_digest(KNOWN), "doi:10.0/known", KNOWN),
        PriorArtEntry("textbook-2", structure_digest(mul(c(1.0), pw(v("x"), 2.0))), "doi:10.0/other", mul(c(1.0), pw(v("x"), 2.0))))
    base = dict(snapshot_id="prior-art-2026-10", covers_kinds=("equation",), entries=entries, sources=("corpus:handbook-v3",),
                coverage_criteria="power laws in x from the handbook index", canonicalizer_id=CANON.canonicalizer_id)
    base.update(kw)
    return PriorArtSnapshot(**base)


def sealed_then_proposed(snap, *hyps):
    led = NoveltyLedger()
    led.seal(snap)
    for h in hyps:
        led.record_proposal(h)
    return led


def novel_h(expr, **kw):
    return hypothesis(statement_payload={"expression": expr}, structure_digest=structure_digest(expr), **kw)


def test_novelty_needs_a_snapshot_sealed_before_the_proposal_and_never_reads_novel():
    snap = snapshot()
    h = hypothesis()
    led = sealed_then_proposed(snap, h)
    assert check_novelty(h, snap, led, canonicalizer=CANON).status is NoveltyStatus.KNOWN_EQUIVALENT
    fresh = novel_h(mul(c(1.0), pw(v("x"), 0.83)))
    led.record_proposal(fresh)
    assert check_novelty(fresh, snap, led, canonicalizer=CANON).status is NoveltyStatus.POSSIBLY_NOVEL
    # N2: a snapshot sealed AFTER the proposal (assembled around it, without the matching entry) is refused
    late = NoveltyLedger()
    late.record_proposal(h)
    trimmed = snapshot(entries=(snap.entries[1],))
    late.seal(trimmed)
    with pytest.raises(NoveltyRefused, match="sealed AFTER the proposal"):
        check_novelty(h, trimmed, late, canonicalizer=CANON)
    # N2: removing entry expressions (to dodge numeric equivalence) changes the snapshot identity
    stripped = snapshot(entries=tuple(dataclasses.replace(e, expression=None) for e in snap.entries))
    assert stripped.digest != snap.digest
    with pytest.raises(NoveltyRefused, match="never sealed"):
        check_novelty(h, stripped, led, canonicalizer=CANON)
    # N1: the structure digest is derived from the stated expression; a mismatching one is refused
    with pytest.raises(NoveltyRefused, match="not the canonical structure"):
        check_novelty(hypothesis(structure_digest="z" * 64), snap, sealed_then_proposed(snap, hypothesis(structure_digest="z" * 64)),
                      canonicalizer=CANON)
    no_expr = hypothesis(statement_payload={}, structure_digest="")
    assert check_novelty(no_expr, snap, sealed_then_proposed(snap, no_expr), canonicalizer=CANON).status is NoveltyStatus.NOVELTY_UNRESOLVED
    # N3: an empty snapshot is never evidence of novelty
    empty = snapshot(entries=())
    assert check_novelty(fresh, empty, sealed_then_proposed(empty, fresh), canonicalizer=CANON).status is NoveltyStatus.NOVELTY_UNRESOLVED
    with pytest.raises(NoveltyRefused, match="sources"):
        snapshot(sources=())
    mech = novel_h(mul(c(1.0), pw(v("x"), 0.83)), kind=HypothesisKind.MECHANISM, model_ref="m")
    assert check_novelty(mech, snap, sealed_then_proposed(snap, mech), canonicalizer=CANON).status is NoveltyStatus.NOVELTY_UNRESOLVED


def test_numeric_equivalence_is_tri_state_bound_into_the_check_and_never_forged():
    snap = snapshot()
    rewritten = mul(pw(v("x"), 0.37), v("x"), c(5.0))           # canonicalization already merges this ...
    assert structure_digest(rewritten) == structure_digest(KNOWN)
    other_form = {"exp": mul(c(1.37), {"log": v("x")})}          # ... this needs numeric equivalence
    h = novel_h(other_form)
    led = sealed_then_proposed(snap, h)
    eq = EquivalenceSpec("blindfold.evaluate/1", evaluate, ({"x": 1.5}, {"x": 3.0}, {"x": 7.0}), 1e-9)
    hit = check_novelty(h, snap, led, canonicalizer=CANON, equivalence=eq)
    assert hit.status is NoveltyStatus.KNOWN_EQUIVALENT and hit.equivalence["probes"] and hit.equivalence["evaluator_id"]
    with pytest.raises(NoveltyRefused, match=">= 2 probe"):
        EquivalenceSpec("e", evaluate, ({"x": 1.0},), 1e-9)
    # N4: a probe at a shared zero is skipped, not "different"; NaN is undecided, not "different"
    zero = PriorArtEntry("zero-law", structure_digest(v("x")), "doi:z", v("x"))
    zsnap = snapshot(entries=(zero,))
    hz = novel_h(mul(c(3.0), {"exp": {"log": v("x")}}))
    zled = sealed_then_proposed(zsnap, hz)
    zeq = EquivalenceSpec("e", lambda e, p: 0.0 if p["x"] == 0 else evaluate(e, p), ({"x": 0.0}, {"x": 1.0}, {"x": 2.0}), 1e-9)
    assert check_novelty(hz, zsnap, zled, canonicalizer=CANON, equivalence=zeq).status is NoveltyStatus.KNOWN_EQUIVALENT
    nan_eq = EquivalenceSpec("e", lambda e, p: float("nan"), ({"x": 1.0}, {"x": 2.0}), 1e-9)
    hn = novel_h(mul(c(1.0), pw(v("x"), 0.83)))
    nled = sealed_then_proposed(snap, hn)
    assert check_novelty(hn, snap, nled, canonicalizer=CANON, equivalence=nan_eq).status is NoveltyStatus.NOVELTY_UNRESOLVED
    assert check_novelty(hn, snap, nled, canonicalizer=CANON).methods == (check_novelty(hn, snap, nled, canonicalizer=CANON).methods[0],)
    # N5: apply_novelty runs the check itself; there is no way to hand it a record
    applied, check = apply_novelty(hn, snap, nled, canonicalizer=CANON)
    assert applied.novelty_status is NoveltyStatus.POSSIBLY_NOVEL and applied.novelty_basis == check.digest
    assert isinstance(check, NoveltyCheck) and applied.knowledge_snapshot_ref == snap.digest
    with pytest.raises(NoveltyRefused, match="canonicalizer"):
        check_novelty(hn, snap, nled, canonicalizer=Canonicalizer("other", structure_digest))
