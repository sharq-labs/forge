"""Roadmap V2 R5: sealed falsifiers and verdicts, multiplicity accounting, novelty against a sealed snapshot
(incl. the checkpoint-3 hostile review and its two re-reviews)."""

from __future__ import annotations

import dataclasses
import itertools

import pytest

from engcore.blindfold.expression import c, evaluate, mul, pw, structure_digest, v
from engcore.claims.falsification import (
    K_MAX, CriterionKind, EvidenceSource, ExposureAuthority, FalsificationRefused, Falsifier, FalsifierRegistry, FalsifierVerdict,
    HypothesisTicket, Verdict, apply_verdicts, conditions_match, judge, verify_status,
)
from engcore.claims.multiplicity import (
    MultiplicityContext, MultiplicityLedger, MultiplicityRefused, PromotedResult, promote, verify_promoted,
)
from engcore.claims.novelty import (
    Canonicalizer, EquivalenceSpec, NoveltyCheck, NoveltyLedger, NoveltyRefused, PriorArtEntry, PriorArtSnapshot, apply_novelty,
    check_novelty, register_canonicalizer, register_evaluator, verify_novelty,
)
from engcore.sria.decision import (
    Hypothesis, HypothesisKind, HypothesisPrediction, HypothesisStatus, NoveltyStatus, VerdictReference, derive_hypothesis,
)

LAW = mul(c(2.0), pw(v("x"), 1.37))
SRC = EvidenceSource.ESCROW_OBSERVATION
COND = {"x": 2.0}
_ids = itertools.count()
_camps = itertools.count()


def hypothesis(**kw):
    base = dict(hypothesis_id="h1", model_ref="law:candidate", kind=HypothesisKind.EQUATION, statement="y = a x^1.37",
                statement_payload={"expression": LAW}, structure_digest=structure_digest(LAW),
                predictions=(HypothesisPrediction("y", "m", "cond:x=2"),), falsifier_refs=("f1@v1",))
    base.update(kw)
    return Hypothesis(**base)


def falsifier(h, **kw):
    base = dict(falsifier_id="f1", hypothesis_id=h.hypothesis_id, hypothesis_content_digest=h.content_digest, observable="y", unit="m",
                test_conditions=COND, evidence_source=SRC, criterion=CriterionKind.PREDICTION_DEVIATION,
                parameters={"k": 3.0, "predicted": 5.17, "prediction_uncertainty": 0.01, "resolution": 0.2})
    base.update(kw)
    return Falsifier(**base)


def setup(campaign="c", **kw):
    auth = ExposureAuthority("escrow-1", **kw)
    return auth, auth.registry(campaign)


def release(auth, value, u=0.01, conditions=COND, **kw):
    return auth.release(evidence_id=kw.pop("evidence_id", f"acq-{next(_ids)}"), source=kw.pop("source", SRC), observable="y",
                        unit="m", value=value, uncertainty=u, conditions=conditions, **kw)


def sealed(reg, h, ticket=None, **kw):
    """Register h (or use its ticket), seal a falsifier for it, return (falsifier, ticket)."""
    ticket = reg.register(h, ticket)
    f = falsifier(h, **kw)
    reg.seal(f, ticket)
    return f, ticket


# ---------------------------------------------------------------------------- falsification


def test_the_authority_clock_and_novel_predictions():
    auth, reg = setup()
    h = hypothesis()
    t = reg.register(h)
    release(auth, 6.0)                                           # the proposer has seen data at x = 2 ...
    with pytest.raises(FalsificationRefused, match="NOVEL prediction"):   # re-review 3 H1-a: ... so no falsifier there
        reg.seal(falsifier(h, parameters={"k": 3.0, "predicted": 6.0, "prediction_uncertainty": 0.01, "resolution": 0.2}), t)
    auth2, reg2 = setup()
    t2 = reg2.register(h)
    f = falsifier(h)
    reg2.seal(f, t2)
    early = release(auth2, 5.2, evidence_id="acq-early")
    assert auth2.release(evidence_id="acq-early", source=SRC, observable="y", unit="m", value=5.2, uncertainty=0.01,
                         conditions=COND) == early                # an acquisition re-released keeps its first exposure
    assert judge(f.digest, reg2, early).verdict is Verdict.NOT_REFUTED
    repeat = release(auth2, 5.2)                                 # a genuine repeat (new acquisition) is new evidence
    assert judge(f.digest, reg2, repeat).verdict is Verdict.NOT_REFUTED
    with pytest.raises(FalsificationRefused, match="not released by this registry's exposure authority"):
        judge(f.digest, reg2, dataclasses.replace(repeat, value=99.0))
    other = ExposureAuthority("escrow-1")                        # same id string, different key
    with pytest.raises(FalsificationRefused, match="not released"):
        judge(f.digest, reg2, other.release(evidence_id="x", source=SRC, observable="y", unit="m", value=5.2, uncertainty=0.01,
                                            conditions=COND))
    with pytest.raises(FalsificationRefused, match="admissible source"):
        judge(f.digest, reg2, release(auth2, 5.22, source=EvidenceSource.MEASUREMENT_RECORD))
    with pytest.raises(FalsificationRefused, match="other conditions"):
        judge(f.digest, reg2, release(auth2, 5.2, conditions={"x": 3.0}))
    with pytest.raises(FalsificationRefused, match="evidence source must be one of"):
        falsifier(h, evidence_source="caller:assertion")
    with pytest.raises(FalsificationRefused, match="issued by its exposure authority"):
        FalsifierRegistry(auth2, "c")
    assert auth2.registry("c") is reg2 and not hasattr(reg2, "authority")
    with pytest.raises(FalsificationRefused, match="non-finite"):
        release(auth2, float("nan"))
    assert conditions_match({"x": 2.0}, {"x": 2.0, "run": "b"}) and conditions_match({"x": 2.0, "T": 300}, {"x": 2.0})
    assert not conditions_match({"x": 2.0}, {"x": 3.0})          # re-review 3 M3: a label never hides a measurement


def test_only_the_owner_seals_and_only_registered_content():
    auth, reg = setup()
    h = hypothesis()
    owner = reg.register(h)
    with pytest.raises(FalsificationRefused, match="owner"):     # re-review 3 H2: no griefing seals
        reg.seal(falsifier(h, falsifier_id="grief", parameters={"k": 3.0, "predicted": 1000.0, "prediction_uncertainty": 0.01,
                                                                 "resolution": 100.0}), HypothesisTicket("h1", "0" * 32))
    with pytest.raises(FalsificationRefused, match="never registered"):
        reg.seal(falsifier(h, hypothesis_content_digest="a" * 64), owner)
    with pytest.raises(FalsificationRefused, match="owner ticket"):
        reg.register(h.revise(statement="hijack"))


def test_the_prediction_k_and_resolution_are_sealed_and_cannot_be_vacuous():
    h = hypothesis()
    with pytest.raises(FalsificationRefused, match="seals"):
        falsifier(h, parameters={"k": 3.0, "resolution": 0.2})
    with pytest.raises(FalsificationRefused, match="cannot fail"):
        falsifier(h, parameters={"k": K_MAX * 10, "predicted": 5.17, "resolution": 0.2})
    with pytest.raises(FalsificationRefused, match="predicted magnitude"):
        falsifier(h, parameters={"k": 1.0, "predicted": 5.17, "prediction_uncertainty": 1e6, "resolution": 1e7})
    with pytest.raises(FalsificationRefused, match="never discriminate"):
        falsifier(h, parameters={"k": 3.0, "predicted": 5.17, "prediction_uncertainty": 0.5, "resolution": 1.2})
    with pytest.raises(FalsificationRefused, match="at most its width"):
        falsifier(h, criterion=CriterionKind.FORBIDDEN_REGION, parameters={"k": 2.0, "low": 1e9, "high": 1e9 + 1, "resolution": 5.0})
    with pytest.raises(FalsificationRefused, match="unknown criterion parameters"):            # the free `scale` is gone
        falsifier(h, parameters={"k": 1.0, "predicted": 0.0, "scale": 1e12, "resolution": 1e11})
    zero = {"k": 1.0, "predicted": 0.0, "prediction_uncertainty": 0.001, "resolution": 1e11}
    _a, reg = setup()
    with pytest.raises(FalsificationRefused, match="declared measurement scale"):              # re-review 3 H1-b
        sealed(reg, h, parameters=zero)
    _a, reg = setup(resolution_scales={("y", "m"): 1.0})
    t = reg.register(h)
    with pytest.raises(FalsificationRefused, match="declared measurement scale"):
        reg.seal(falsifier(h, parameters=zero), t)
    reg.seal(falsifier(h, parameters={**zero, "resolution": 0.2}), t)
    auth, reg = setup()
    f, _t = sealed(reg, h)
    assert judge(f.digest, reg, release(auth, 9.9)).verdict is Verdict.REFUTED
    assert judge(f.digest, reg, release(auth, 5.17, u=1e6)).verdict is Verdict.INCONCLUSIVE
    assert judge(f.digest, reg, release(auth, 5.171, u=0.0)).verdict is Verdict.INCONCLUSIVE
    assert judge(f.digest, reg, release(auth, 9.8, u=None)).verdict is Verdict.INCONCLUSIVE
    h2 = hypothesis(hypothesis_id="h2", statement_payload={"expression": mul(c(3.0), v("x"))}, structure_digest=structure_digest(mul(c(3.0), v("x"))))
    f2, _t2 = sealed(reg, h2, falsifier_id="g", test_conditions={"x": 5.0}, parameters={"k": 3.0, "predicted": 5.17, "resolution": 0.2})
    assert judge(f2.digest, reg, release(auth, 9.7, conditions={"x": 5.0})).verdict is Verdict.INCONCLUSIVE   # u_pred UNKNOWN


def test_every_matching_release_is_judged_and_nothing_hides_a_refutation():
    auth, reg = setup()
    h = hypothesis(falsifier_refs=("f1@v1", "f2@v1"))
    f1, t = sealed(reg, h)
    f2 = falsifier(h, falsifier_id="f2", test_conditions={"x": 3.0},
                   parameters={"k": 3.0, "predicted": 9.0, "prediction_uncertainty": 0.01, "resolution": 0.2})
    reg.seal(f2, t)
    judge(f1.digest, reg, release(auth, 5.2))
    release(auth, 99.0, conditions={"x": 3.0})                                             # a refuting release, never judged by hand
    judge(f2.digest, reg, release(auth, 9.01, conditions={"x": 3.0}))
    anchor = reg.anchor
    claim = h.revise(status=HypothesisStatus.SURVIVING,
                     status_basis=tuple(VerdictReference(x.falsifier_ref, x.digest, "not_refuted", h.content_digest)
                                        for x in reg.verdicts_for("h1", h.content_digest) if x.verdict is Verdict.NOT_REFUTED))
    assert any("not judged yet" in p for p in verify_status(claim, reg, anchor=anchor))
    pending_oos = h.revise(status=HypothesisStatus.OUT_OF_SCOPE, status_note="x")         # re-review 3 M1
    assert any("not judged yet" in p for p in verify_status(pending_oos, reg, anchor=anchor))
    refuted = apply_verdicts(h, reg)
    assert refuted.status is HypothesisStatus.REFUTED and verify_status(refuted, reg, anchor=anchor) == []
    fake = FalsifierVerdict(f2.digest, "f2@v1", "h1", h.content_digest, "e", "0" * 64, 999, 1, Verdict.NOT_REFUTED, 9.0, 9.0, 3.0,
                            0.01, "forged")
    forged = h.revise(status=HypothesisStatus.SURVIVING,
                      status_basis=(VerdictReference("f2@v1", fake.digest, "not_refuted", h.content_digest),))
    assert any("not in the registry chain" in p for p in verify_status(forged, reg, anchor=anchor))
    for hidden in (refuted.revise(status=HypothesisStatus.PROPOSED, status_basis=()), refuted.revise(falsifier_refs=()),
                   refuted.revise(status=HypothesisStatus.OUT_OF_SCOPE, status_basis=(), status_note="x")):
        assert any("refuted in the registry" in p for p in verify_status(hidden, reg, anchor=anchor)), hidden.status


def test_a_refutation_follows_the_id_and_the_claim():
    auth, reg = setup()
    h = hypothesis()
    f, t = sealed(reg, h)
    judge(f.digest, reg, release(auth, 9.9))                                               # REFUTED by v1
    loosened = f.revise(parameters={"k": 9.0, "predicted": 5.17, "prediction_uncertainty": 0.1, "resolution": 1.2})
    with pytest.raises(FalsificationRefused, match="NOVEL prediction"):                    # a post-hoc loosening at the
        reg.seal(loosened, t)                                                              # observed conditions is refused
    moved = f.revise(test_conditions={"x": 2.5}, parameters={"k": 9.0, "predicted": 7.6, "prediction_uncertainty": 0.1,
                                                              "resolution": 1.9})
    reg.seal(moved, t)                                                                     # v2 at new conditions ...
    assert judge(moved.digest, reg, release(auth, 7.6, conditions={"x": 2.5})).verdict is Verdict.NOT_REFUTED
    assert apply_verdicts(h.revise(falsifier_refs=("f1@v2",)), reg).status is HypothesisStatus.REFUTED   # ... v1's refutation stands
    with pytest.raises(FalsificationRefused, match="new falsifier"):
        f.revise(hypothesis_content_digest=h.revise(statement="y = a x^1.37 ").content_digest)
    # re-review 3 BLOCKER-1: the same claim under a NEW id is the same (refuted) hypothesis
    with pytest.raises(ValueError, match="different claim"):
        derive_hypothesis(h, hypothesis_id="h1b", kind=HypothesisKind.EQUATION, model_ref="law:again", statement=h.statement,
                          statement_payload=h.statement_payload, structure_digest=h.structure_digest, predictions=h.predictions)
    twin = hypothesis(hypothesis_id="h1b", model_ref="law:again", falsifier_refs=("g@v1",))
    assert twin.claim_digest == h.claim_digest
    g, _tg = sealed(reg, twin, falsifier_id="g", test_conditions={"x": 4.0},
                    parameters={"k": 3.0, "predicted": 13.0, "prediction_uncertainty": 0.01, "resolution": 0.2})
    judge(g.digest, reg, release(auth, 13.0, conditions={"x": 4.0}))
    assert apply_verdicts(twin, reg).status is HypothesisStatus.REFUTED
    # a genuinely different claim is a new hypothesis, tested afresh
    other = derive_hypothesis(h, hypothesis_id="h-new", kind=HypothesisKind.EQUATION, model_ref="law:b", statement="y = a x^1.5",
                              statement_payload={"expression": mul(c(2.0), pw(v("x"), 1.5))},
                              structure_digest=structure_digest(mul(c(2.0), pw(v("x"), 1.5)))).revise(
                                  falsifier_refs=("n@v1",))
    n, _tn = sealed(reg, other, falsifier_id="n", test_conditions={"x": 6.0},
                    parameters={"k": 3.0, "predicted": 29.4, "prediction_uncertainty": 0.05, "resolution": 1.0})
    judge(n.digest, reg, release(auth, 29.4, conditions={"x": 6.0}))
    assert apply_verdicts(other, reg).status is HypothesisStatus.SURVIVING
    with pytest.raises(FalsificationRefused, match="already sealed"):
        reg.seal(falsifier(h, parameters={"k": 4.0, "predicted": 5.17, "prediction_uncertainty": 0.01, "resolution": 0.2}), t)
    with pytest.raises(FalsificationRefused, match="names the falsifier it supersedes"):
        falsifier(h, version=2)
    with pytest.raises(ValueError, match="stated claim"):
        Hypothesis(hypothesis_id="n", model_ref="m", kind=HypothesisKind.EQUATION, description="claim lives only here",
                   falsifier_refs=("f1@v1",), status=HypothesisStatus.SURVIVING,
                   status_basis=(VerdictReference("f1@v1", "a" * 64, "not_refuted", "b" * 64),))


def test_survival_is_verified_only_against_the_expected_registry():
    auth, reg = setup()
    h = hypothesis()
    f, _t = sealed(reg, h)
    judge(f.digest, reg, release(auth, 5.2))
    survived = apply_verdicts(h, reg)
    assert survived.status is HypothesisStatus.SURVIVING and verify_status(survived, reg, anchor=reg.anchor) == []
    fresh = auth.registry(f"c-{next(_camps)}")
    assert verify_status(survived, fresh, anchor=reg.anchor)
    with pytest.raises(AttributeError):                                                    # re-review 3 H5: not relabelable
        fresh.campaign_id = "c"
    assert verify_status(survived, ExposureAuthority("escrow-1").registry("c"), anchor=reg.anchor)
    assert any("INDISTINGUISHABLE" in p for p in verify_status(survived.revise(status=HypothesisStatus.INDISTINGUISHABLE), reg,
                                                                anchor=reg.anchor))
    # re-review 3 M2: refuted in another campaign of the same authority -> flagged here
    other = auth.registry("c-other")
    g, _tg = sealed(other, h, falsifier_id="g", test_conditions={"x": 8.0},
                    parameters={"k": 3.0, "predicted": 34.6, "prediction_uncertainty": 0.05, "resolution": 1.0})
    judge(g.digest, other, release(auth, 50.0, conditions={"x": 8.0}))
    assert apply_verdicts(h.revise(falsifier_refs=("g@v1",)), other).status is HypothesisStatus.REFUTED
    assert any("other campaigns" in p for p in verify_status(survived, reg, anchor=reg.anchor))


# ---------------------------------------------------------------------------- multiplicity


def test_multiplicity_records_ids_checks_the_stage_chain_and_binds_the_final_context():
    cid = f"camp-{next(_camps)}"
    led = MultiplicityLedger(cid)
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
    with pytest.raises(TypeError):
        r.multiplicity.counts["generated"] = 1
    with pytest.raises(MultiplicityRefused, match="does not match"):
        PromotedResult("x", "h1", r.multiplicity, "0" * 64)
    with pytest.raises(MultiplicityRefused, match="does not record this hypothesis"):
        PromotedResult("x", "h7", r.multiplicity, r.multiplicity.digest)
    with pytest.raises(MultiplicityRefused, match="issued by its campaign's ledger"):
        MultiplicityContext("other", {"generated": 1, "promoted": 1, "hypotheses_tested": 1}, {}, {}, (), (), ("h1",), ("h1",), "0" * 64)
    with pytest.raises(MultiplicityRefused, match="recorded by id"):
        led.count("promoted", 1)
    with pytest.raises(MultiplicityRefused, match="tested"):
        promote("y", "never-tested", led)
    led.count("generated", 10)
    assert verify_promoted(r, led, campaign_id=cid)
    final = led.close()
    assert verify_promoted(r, led, campaign_id=cid) and verify_promoted(r.rebind(led), led, campaign_id=cid) == []
    assert final.selected_from == 1_000_010 and verify_promoted(r.rebind(led), led, campaign_id="elsewhere")
    for late in (lambda: led.count("generated", 1), lambda: led.seed("s"), lambda: led.evaluated("x", 1)):   # re-review 3 L1
        with pytest.raises(MultiplicityRefused, match="closed"):
            late()
    with pytest.raises(AttributeError):                                                    # re-review 3 H5
        led.campaign_id = "other"
    del led
    with pytest.raises(MultiplicityRefused, match="already opened"):
        MultiplicityLedger(cid)
    # re-review 3 M5: a family that omits hypotheses the campaign registered is not verified
    small = MultiplicityLedger(f"camp-{next(_camps)}")
    small.count("generated", 4)
    small.count("deduplicated", 4)
    small.count("admitted", 4)
    small.tested("h0")
    res = promote("r", "h0", small)
    small.close()
    auth2, reg2 = setup(small.campaign_id)
    reg2.register(hypothesis(hypothesis_id="h0"))
    reg2.register(hypothesis(hypothesis_id="hidden-attempt", statement="other"))
    assert any("omits" in p for p in verify_promoted(res.rebind(small), small, campaign_id=small.campaign_id, registry=reg2))
    empty = MultiplicityLedger(f"camp-{next(_camps)}")
    empty.tested("h1")
    with pytest.raises(MultiplicityRefused, match="generated and admitted"):
        promote("x", "h1", empty)
    bad = MultiplicityLedger(f"camp-{next(_camps)}")
    bad.count("generated", 5)
    bad.count("deduplicated", 50)
    with pytest.raises(MultiplicityRefused, match="missed a stage"):
        bad.context()
    for bad_call in (lambda: bad.evaluated("x", 1.5), lambda: bad.compute("s", float("inf")), lambda: bad.seed(""),
                     lambda: bad.strategy("", "1"), lambda: bad.tested(5)):
        with pytest.raises(MultiplicityRefused):
            bad_call()


# ---------------------------------------------------------------------------- novelty


register_canonicalizer("blindfold.structure/2", structure_digest)
register_evaluator("blindfold.evaluate/1", evaluate)


def _zero_aware(e, p):
    return 0.0 if p["x"] == 0 else evaluate(e, p)


def _nan(e, p):
    return float("nan")


register_evaluator("zero-aware", _zero_aware)
register_evaluator("nan", _nan)
CANON = Canonicalizer.resolve("blindfold.structure/2")
KNOWN = mul(c(1.0), pw(v("x"), 1.37))
EQ = EquivalenceSpec("blindfold.evaluate/1", evaluate, ({"x": 1.5}, {"x": 3.0}, {"x": 7.0}), 1e-9)


def snapshot(entries=None, **kw):
    entries = entries if entries is not None else (
        PriorArtEntry("textbook-1", structure_digest(KNOWN), "doi:10.0/known", KNOWN),
        PriorArtEntry("textbook-2", structure_digest(mul(c(1.0), pw(v("x"), 2.0))), "doi:10.0/other", mul(c(1.0), pw(v("x"), 2.0))))
    base = dict(snapshot_id="prior-art-2026-10", covers_kinds=("equation",), entries=entries, sources=("corpus:handbook-v3",),
                coverage_criteria="power laws in x from the handbook index", canonicalizer_id=CANON.canonicalizer_id,
                equivalence=EQ.to_dict() if any(e.expression is not None for e in entries) else None)
    base.update(kw)
    return PriorArtSnapshot(**base)


def ledger(auth=None):
    return (auth or ExposureAuthority("novelty-auth")).novelty_ledger("n")


def sealed_then_proposed(snap, *hyps):
    led = ledger()
    led.seal(snap)
    for h in hyps:
        led.record_proposal(h)
    return led


def novel_h(expr, **kw):
    return hypothesis(statement_payload={"expression": expr}, structure_digest=structure_digest(expr), **kw)


def test_novelty_needs_the_latest_snapshot_sealed_before_the_first_sighting_and_never_reads_novel():
    snap = snapshot()
    h = hypothesis()
    led = sealed_then_proposed(snap, h)
    assert check_novelty(h, snap, led, canonicalizer=CANON, equivalence=EQ).status is NoveltyStatus.KNOWN_EQUIVALENT
    fresh = novel_h(mul(c(1.0), pw(v("x"), 0.83)), hypothesis_id="h-fresh")
    led.record_proposal(fresh)
    assert check_novelty(fresh, snap, led, canonicalizer=CANON, equivalence=EQ).status is NoveltyStatus.POSSIBLY_NOVEL
    late = ledger()
    late.record_proposal(h)
    trimmed = snapshot(entries=(snap.entries[1],))
    late.seal(trimmed)
    for again in (h, h.revise(statement="y = a x^1.37 "), hypothesis(hypothesis_id="h-rederived")):
        late.record_proposal(again)
        with pytest.raises(NoveltyRefused, match="sealed AFTER"):
            check_novelty(again, trimmed, late, canonicalizer=CANON, equivalence=EQ)
    # re-review 3 H3: prior art is never removed, and the latest snapshot before the proposal is the one used
    grow = ledger()
    grow.seal(snap)
    with pytest.raises(NoveltyRefused, match="never removed"):
        grow.seal(trimmed)
    bigger = snapshot(entries=snap.entries + (PriorArtEntry("textbook-3", structure_digest(mul(c(1.0), pw(v("x"), 3.0))), "doi:3",
                                                            mul(c(1.0), pw(v("x"), 3.0))),))
    grow.seal(bigger)
    grow.record_proposal(fresh)
    with pytest.raises(NoveltyRefused, match="LATEST snapshot"):
        check_novelty(fresh, snap, grow, canonicalizer=CANON, equivalence=EQ)
    assert check_novelty(fresh, bigger, grow, canonicalizer=CANON, equivalence=EQ).status is NoveltyStatus.POSSIBLY_NOVEL
    # re-review 3 H4: a falsifier-registry registration is a sighting; delaying the novelty record proves nothing
    auth = ExposureAuthority("shared")
    auth.registry("c").register(fresh)
    shared = ledger(auth)
    shared.seal(snap)
    shared.record_proposal(fresh)
    with pytest.raises(NoveltyRefused, match="first seen"):
        check_novelty(fresh, snap, shared, canonicalizer=CANON, equivalence=EQ)
    with pytest.raises(NoveltyRefused, match="issued by its campaign's exposure authority"):
        NoveltyLedger(object(), "n")
    with pytest.raises(AttributeError):
        led.campaign_id = "other"
    stripped = snapshot(entries=tuple(dataclasses.replace(e, expression=None) for e in snap.entries))
    assert stripped.digest != snap.digest
    with pytest.raises(NoveltyRefused, match="never sealed"):
        check_novelty(h, stripped, led, canonicalizer=CANON)
    for bad in (hypothesis(hypothesis_id="h-bad1", structure_digest="z" * 64), hypothesis(hypothesis_id="h-bad2", structure_digest="")):
        with pytest.raises(NoveltyRefused, match="not the canonical structure"):
            check_novelty(bad, snap, sealed_then_proposed(snap, bad), canonicalizer=CANON, equivalence=EQ)
    with pytest.raises(NoveltyRefused, match="not registered"):                            # re-review 3 M4
        Canonicalizer(CANON.canonicalizer_id, lambda e: "u" * 64)
    with pytest.raises(NoveltyRefused, match="already bound"):
        register_canonicalizer(CANON.canonicalizer_id, lambda e: "u" * 64)
    with pytest.raises(NoveltyRefused, match="not registered"):
        EquivalenceSpec("blindfold.evaluate/1", lambda e, p: 1.0, ({"x": 1.0}, {"x": 2.0}), 1e-9)
    no_expr = hypothesis(hypothesis_id="h-noexpr", statement_payload={}, structure_digest="")
    assert check_novelty(no_expr, snap, sealed_then_proposed(snap, no_expr), canonicalizer=CANON,
                         equivalence=EQ).status is NoveltyStatus.NOVELTY_UNRESOLVED
    empty = snapshot(entries=())
    assert check_novelty(fresh, empty, sealed_then_proposed(empty, fresh), canonicalizer=CANON).status is NoveltyStatus.NOVELTY_UNRESOLVED
    unverifiable = snapshot(entries=stripped.entries)
    assert check_novelty(fresh, unverifiable, sealed_then_proposed(unverifiable, fresh),
                         canonicalizer=CANON).status is NoveltyStatus.NOVELTY_UNRESOLVED
    with pytest.raises(NoveltyRefused, match="sources"):
        snapshot(sources=())
    mech = novel_h(mul(c(1.0), pw(v("x"), 0.83)), hypothesis_id="h-mech", kind=HypothesisKind.MECHANISM, model_ref="m")
    assert check_novelty(mech, snap, sealed_then_proposed(snap, mech), canonicalizer=CANON,
                         equivalence=EQ).status is NoveltyStatus.NOVELTY_UNRESOLVED


def test_numeric_equivalence_is_declared_tri_state_and_novelty_is_verified_not_asserted():
    snap = snapshot()
    rewritten = mul(pw(v("x"), 0.37), v("x"), c(5.0))
    assert structure_digest(rewritten) == structure_digest(KNOWN)
    h = novel_h({"exp": mul(c(1.37), {"log": v("x")})})
    led = sealed_then_proposed(snap, h)
    hit = check_novelty(h, snap, led, canonicalizer=CANON, equivalence=EQ)
    assert hit.status is NoveltyStatus.KNOWN_EQUIVALENT and hit.equivalence["probes"] and hit.equivalence["evaluator_id"]
    with pytest.raises(NoveltyRefused, match="exactly the one the snapshot declares"):
        check_novelty(h, snap, led, canonicalizer=CANON)
    with pytest.raises(NoveltyRefused, match="exactly the one the snapshot declares"):
        check_novelty(h, snap, led, canonicalizer=CANON,
                      equivalence=EquivalenceSpec("blindfold.evaluate/1", evaluate, ({"x": 1.0}, {"x": 2.0}), 1e-9))
    with pytest.raises(NoveltyRefused, match=">= 2 probe"):
        EquivalenceSpec("blindfold.evaluate/1", evaluate, ({"x": 1.0},), 1e-9)
    zeq = EquivalenceSpec("zero-aware", _zero_aware, ({"x": 0.0}, {"x": 1.0}, {"x": 2.0}), 1e-9)
    zsnap = snapshot(entries=(PriorArtEntry("zero-law", structure_digest(v("x")), "doi:z", v("x")),), equivalence=zeq.to_dict())
    hz = novel_h(mul(c(3.0), {"exp": {"log": v("x")}}), hypothesis_id="h-zero")
    assert check_novelty(hz, zsnap, sealed_then_proposed(zsnap, hz), canonicalizer=CANON,
                         equivalence=zeq).status is NoveltyStatus.KNOWN_EQUIVALENT
    nan_eq = EquivalenceSpec("nan", _nan, ({"x": 1.0}, {"x": 2.0}), 1e-9)
    nsnap = snapshot(equivalence=nan_eq.to_dict())
    hn = novel_h(mul(c(1.0), pw(v("x"), 0.83)), hypothesis_id="h-new")
    assert check_novelty(hn, nsnap, sealed_then_proposed(nsnap, hn), canonicalizer=CANON,
                         equivalence=nan_eq).status is NoveltyStatus.NOVELTY_UNRESOLVED
    nled = sealed_then_proposed(snap, hn)
    applied, check = apply_novelty(hn, snap, nled, canonicalizer=CANON, equivalence=EQ)
    assert applied.novelty_status is NoveltyStatus.POSSIBLY_NOVEL and applied.novelty_basis == check.digest
    assert isinstance(check, NoveltyCheck) and applied.knowledge_snapshot_ref == snap.digest
    assert verify_novelty(applied, snap, nled, anchor=nled.anchor, canonicalizer=CANON, equivalence=EQ) == []
    handmade = hn.revise(novelty_status=NoveltyStatus.POSSIBLY_NOVEL, knowledge_snapshot_ref="x", novelty_basis="y")
    assert verify_novelty(handmade, snap, nled, anchor=nled.anchor, canonicalizer=CANON, equivalence=EQ)
    moved = applied.revise(statement_payload={"expression": KNOWN}, structure_digest=structure_digest(KNOWN))
    assert moved.novelty_status is NoveltyStatus.NOT_CHECKED and moved.novelty_basis == ""
    assert verify_novelty(applied, snap, ledger(), anchor=nled.anchor, canonicalizer=CANON, equivalence=EQ)
