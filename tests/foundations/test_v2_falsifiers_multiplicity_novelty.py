"""Roadmap V2 R5: sealed falsifiers and verdicts, multiplicity accounting, novelty against a sealed snapshot
(incl. the checkpoint-3 hostile review and its re-review)."""

from __future__ import annotations

import dataclasses
import itertools

import pytest

from engcore.blindfold.expression import c, evaluate, mul, pw, structure_digest, v
from engcore.claims.falsification import (
    K_MAX, CriterionKind, EvidenceSource, ExposureAuthority, FalsificationRefused, Falsifier, FalsifierRegistry, FalsifierVerdict,
    Verdict, apply_verdicts, judge, verify_status,
)
from engcore.claims.multiplicity import (
    MultiplicityContext, MultiplicityLedger, MultiplicityRefused, PromotedResult, promote, verify_promoted,
)
from engcore.claims.novelty import (
    Canonicalizer, EquivalenceSpec, NoveltyCheck, NoveltyLedger, NoveltyRefused, PriorArtEntry, PriorArtSnapshot, apply_novelty,
    check_novelty, verify_novelty,
)
from engcore.sria.decision import Hypothesis, HypothesisKind, HypothesisPrediction, HypothesisStatus, NoveltyStatus, VerdictReference

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


def setup(campaign="c"):
    auth = ExposureAuthority("escrow-1")
    return auth, auth.registry(campaign)


def release(auth, value, u=0.01, conditions=COND, **kw):
    return auth.release(evidence_id=kw.pop("evidence_id", f"acq-{next(_ids)}"), source=kw.pop("source", SRC), observable="y",
                        unit="m", value=value, uncertainty=u, conditions=conditions, **kw)


# ---------------------------------------------------------------------------- falsification


def test_the_authority_clock_orders_seals_and_exposures():
    auth, reg = setup()
    h = hypothesis()
    early = release(auth, 5.2, evidence_id="acq-early")          # the proposer saw this before writing the falsifier ...
    f = falsifier(h)
    reg.seal(f)
    with pytest.raises(FalsificationRefused, match="post-hoc"):
        judge(f.digest, reg, early)                              # ... and cannot "expose" it later: the clock is the authority's
    again = auth.release(evidence_id="acq-early", source=SRC, observable="y", unit="m", value=5.2, uncertainty=0.01, conditions=COND)
    assert again == early                                        # re-releasing an acquisition keeps its FIRST exposure
    repeat = release(auth, 5.2)                                  # re-review M1: a genuine repeat (new acquisition) is new evidence
    assert judge(f.digest, reg, repeat).verdict is Verdict.NOT_REFUTED
    forged = dataclasses.replace(repeat, value=99.0)             # a value swapped under a released item (F5)
    with pytest.raises(FalsificationRefused, match="not released by this registry's exposure authority"):
        judge(f.digest, reg, forged)
    other = ExposureAuthority("escrow-1")                        # same id string, different key
    with pytest.raises(FalsificationRefused, match="not released"):
        judge(f.digest, reg, other.release(evidence_id="x", source=SRC, observable="y", unit="m", value=5.2, uncertainty=0.01,
                                           conditions=COND))
    with pytest.raises(FalsificationRefused, match="admissible source"):
        judge(f.digest, reg, release(auth, 5.22, source=EvidenceSource.MEASUREMENT_RECORD))
    with pytest.raises(FalsificationRefused, match="other conditions"):                    # re-review B1
        judge(f.digest, reg, release(auth, 5.2, conditions={"x": 3.0}))
    with pytest.raises(FalsificationRefused, match="evidence source must be one of"):      # free-text sources are gone (F10)
        falsifier(h, evidence_source="caller:assertion")
    with pytest.raises(FalsificationRefused, match="issued by its exposure authority"):    # no forked registry (F2)
        FalsifierRegistry(auth, "c")
    assert auth.registry("c") is reg and not hasattr(reg, "authority")                     # re-review H3: no release via registry
    with pytest.raises(FalsificationRefused, match="non-finite"):                          # NaN is not evidence (F8)
        release(auth, float("nan"))


def test_the_prediction_k_and_resolution_are_sealed_and_cannot_be_vacuous():
    h = hypothesis()
    with pytest.raises(FalsificationRefused, match="seals"):                               # F1: nothing supplied later
        falsifier(h, parameters={"k": 3.0, "resolution": 0.2})
    with pytest.raises(FalsificationRefused, match="cannot fail"):                         # F7: k is bounded
        falsifier(h, parameters={"k": K_MAX * 10, "predicted": 5.17, "resolution": 0.2})
    with pytest.raises(FalsificationRefused, match="predicted magnitude"):                 # re-review H4
        falsifier(h, parameters={"k": 1.0, "predicted": 5.17, "prediction_uncertainty": 1e6, "resolution": 1e7})
    with pytest.raises(FalsificationRefused, match="never discriminate"):
        falsifier(h, parameters={"k": 3.0, "predicted": 5.17, "prediction_uncertainty": 1.0, "resolution": 2.5})
    with pytest.raises(FalsificationRefused, match="at most its width"):
        falsifier(h, criterion=CriterionKind.FORBIDDEN_REGION, parameters={"k": 2.0, "low": 1e9, "high": 1e9 + 1, "resolution": 5.0})
    auth, reg = setup()
    f = falsifier(h)
    reg.seal(f)
    assert judge(f.digest, reg, release(auth, 9.9)).verdict is Verdict.REFUTED             # the sealed prediction decides
    assert judge(f.digest, reg, release(auth, 5.17, u=1e6)).verdict is Verdict.INCONCLUSIVE  # uninformative evidence
    assert judge(f.digest, reg, release(auth, 5.171, u=0.0)).verdict is Verdict.INCONCLUSIVE  # F9: zero uncertainty is a claim
    assert judge(f.digest, reg, release(auth, 9.8, u=None)).verdict is Verdict.INCONCLUSIVE  # UNKNOWN never becomes zero
    h2 = hypothesis(hypothesis_id="h2")
    f2 = falsifier(h2, falsifier_id="g", parameters={"k": 3.0, "predicted": 5.17, "resolution": 0.2})   # u_pred UNKNOWN
    reg.seal(f2)
    assert judge(f2.digest, reg, release(auth, 9.7)).verdict is Verdict.INCONCLUSIVE


def test_every_matching_release_is_judged_and_verdicts_cannot_be_shopped_forged_or_omitted():
    auth, reg = setup()
    h = hypothesis(falsifier_refs=("f1@v1", "f2@v1"))
    f1, f2 = falsifier(h), falsifier(h, falsifier_id="f2", test_conditions={"x": 3.0},
                                     parameters={"k": 3.0, "predicted": 9.0, "prediction_uncertainty": 0.01, "resolution": 0.2})
    reg.seal(f1)
    reg.seal(f2)
    judge(f1.digest, reg, release(auth, 5.2))
    release(auth, 99.0, conditions={"x": 3.0})                                             # a refuting release, never judged by hand
    passing = release(auth, 9.01, conditions={"x": 3.0})
    judge(f2.digest, reg, passing)                                                         # the claimant judges only the passing one
    anchor = reg.anchor
    claim = h.revise(status=HypothesisStatus.SURVIVING,
                     status_basis=tuple(VerdictReference(x.falsifier_ref, x.digest, "not_refuted", h.content_digest)
                                        for x in reg.verdicts_for("h1", h.content_digest) if x.verdict is Verdict.NOT_REFUTED))
    assert any("not judged yet" in p for p in verify_status(claim, reg, anchor=anchor))    # re-review B1
    refuted = apply_verdicts(h, reg)                                                       # judges every matching release itself
    assert refuted.status is HypothesisStatus.REFUTED and verify_status(refuted, reg, anchor=anchor) == []
    assert any("refuted in the registry" in p for p in verify_status(claim, reg, anchor=anchor))
    fake = FalsifierVerdict(f2.digest, "f2@v1", "h1", h.content_digest, "e", "0" * 64, 999, 1, Verdict.NOT_REFUTED, 9.0, 9.0, 3.0,
                            0.01, "forged")
    forged = h.revise(status=HypothesisStatus.SURVIVING,
                      status_basis=(VerdictReference("f2@v1", fake.digest, "not_refuted", h.content_digest),))
    assert any("not in the registry chain" in p for p in verify_status(forged, reg, anchor=anchor))
    # re-review H1: no other status may hide the refutation
    for hidden in (refuted.revise(status=HypothesisStatus.PROPOSED, status_basis=()), refuted.revise(falsifier_refs=()),
                   refuted.revise(status=HypothesisStatus.OUT_OF_SCOPE, status_basis=(), status_note="x")):
        assert any("refuted in the registry" in p for p in verify_status(hidden, reg, anchor=anchor)), hidden.status


def test_a_refutation_follows_the_hypothesis_id_through_revisions():
    auth, reg = setup()
    h = hypothesis()
    f = falsifier(h)
    reg.seal(f)
    judge(f.digest, reg, release(auth, 9.9))                                               # REFUTED by v1
    loosened = f.revise(parameters={"k": 9.0, "predicted": 5.17, "prediction_uncertainty": 0.2, "resolution": 2.5})
    assert loosened.version == 2 and loosened.supersedes == f.digest
    h2 = h.revise(falsifier_refs=("f1@v2",))
    assert h2.content_digest == h.content_digest and h2.status is HypothesisStatus.PROPOSED     # the claim is the same
    reg.seal(loosened)
    assert judge(loosened.digest, reg, release(auth, 6.5)).verdict is Verdict.NOT_REFUTED       # passes the loosened test ...
    assert apply_verdicts(h2, reg).status is HypothesisStatus.REFUTED                      # ... F4: not laundered by v2
    cosmetic = h.revise(statement="y = a x^1.37 ")                                          # re-review H2: whitespace "new content"
    assert cosmetic.content_digest != h.content_digest
    with pytest.raises(FalsificationRefused, match="new falsifier"):
        f.revise(hypothesis_content_digest=cosmetic.content_digest)
    g = falsifier(cosmetic, falsifier_id="g1")
    reg.seal(g)
    judge(g.digest, reg, release(auth, 5.18))
    assert apply_verdicts(cosmetic.revise(falsifier_refs=("g1@v1",)), reg).status is HypothesisStatus.REFUTED
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


def test_survival_is_verified_only_against_the_expected_registry():
    auth, reg = setup()
    h = hypothesis()
    f = falsifier(h)
    reg.seal(f)
    judge(f.digest, reg, release(auth, 5.2))
    survived = apply_verdicts(h, reg)
    assert survived.status is HypothesisStatus.SURVIVING and verify_status(survived, reg, anchor=reg.anchor) == []
    # re-review H3: a fresh campaign, or a same-id authority, is not the expected verifier
    fresh = auth.registry(f"c-{next(_camps)}")
    assert verify_status(survived, fresh, anchor=reg.anchor)
    assert verify_status(survived, ExposureAuthority("escrow-1").registry("c"), anchor=reg.anchor)
    partial = survived.revise(status=HypothesisStatus.INDISTINGUISHABLE)
    assert any("INDISTINGUISHABLE" in p for p in verify_status(partial, reg, anchor=reg.anchor))


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
    with pytest.raises(TypeError):                                                         # M3: immutable once bound
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
    # re-review H8: promoted early, then the rest of the search is recorded -> the early result is not final
    led.count("generated", 10)
    assert verify_promoted(r, led)                                                         # not closed yet
    final = led.close()
    assert verify_promoted(r, led) and verify_promoted(r.rebind(led), led) == [] and final.selected_from == 1_000_010
    with pytest.raises(MultiplicityRefused, match="closed"):
        led.count("generated", 1)
    del led                                                                                # dropping a ledger does not free its id
    with pytest.raises(MultiplicityRefused, match="already opened"):
        MultiplicityLedger(cid)
    empty = MultiplicityLedger(f"camp-{next(_camps)}")                                    # M1: a zero-candidate promotion
    empty.tested("h1")
    with pytest.raises(MultiplicityRefused, match="generated and admitted"):
        promote("x", "h1", empty)
    bad = MultiplicityLedger(f"camp-{next(_camps)}")
    bad.count("generated", 5)
    bad.count("deduplicated", 50)
    with pytest.raises(MultiplicityRefused, match="missed a stage"):
        bad.context()
    for bad_call in (lambda: bad.evaluated("x", 1.5), lambda: bad.compute("s", float("inf")), lambda: bad.seed(""),
                     lambda: bad.strategy("", "1"), lambda: bad.tested(5)):                # M4
        with pytest.raises(MultiplicityRefused):
            bad_call()


# ---------------------------------------------------------------------------- novelty


CANON = Canonicalizer("blindfold.structure/2", structure_digest)
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


def ledger():
    return ExposureAuthority("novelty-auth").novelty_ledger("n")


def sealed_then_proposed(snap, *hyps):
    led = ledger()
    led.seal(snap)
    for h in hyps:
        led.record_proposal(h, CANON)
    return led


def novel_h(expr, **kw):
    return hypothesis(statement_payload={"expression": expr}, structure_digest=structure_digest(expr), **kw)


def test_novelty_needs_a_snapshot_sealed_before_the_first_proposal_and_never_reads_novel():
    snap = snapshot()
    h = hypothesis()
    led = sealed_then_proposed(snap, h)
    assert check_novelty(h, snap, led, canonicalizer=CANON, equivalence=EQ).status is NoveltyStatus.KNOWN_EQUIVALENT
    fresh = novel_h(mul(c(1.0), pw(v("x"), 0.83)), hypothesis_id="h-fresh")
    led.record_proposal(fresh, CANON)
    assert check_novelty(fresh, snap, led, canonicalizer=CANON, equivalence=EQ).status is NoveltyStatus.POSSIBLY_NOVEL
    # N2 / re-review H6: a snapshot sealed after the FIRST proposal -- even after a cosmetic revision or a re-derived id
    late = ledger()
    late.record_proposal(h, CANON)
    trimmed = snapshot(entries=(snap.entries[1],))
    late.seal(trimmed)
    for again in (h, h.revise(statement="y = a x^1.37 "), hypothesis(hypothesis_id="h-rederived")):
        late.record_proposal(again, CANON)
        with pytest.raises(NoveltyRefused, match="sealed AFTER"):
            check_novelty(again, trimmed, late, canonicalizer=CANON, equivalence=EQ)
    with pytest.raises(NoveltyRefused, match="issued by its campaign's exposure authority"):
        NoveltyLedger(object(), "n")
    stripped = snapshot(entries=tuple(dataclasses.replace(e, expression=None) for e in snap.entries))
    assert stripped.digest != snap.digest                                                  # expressions are part of identity
    with pytest.raises(NoveltyRefused, match="never sealed"):
        check_novelty(h, stripped, led, canonicalizer=CANON)
    # N1: the structure digest is derived from the stated expression; a mismatching or missing one is refused
    for bad in (hypothesis(hypothesis_id="h-bad1", structure_digest="z" * 64), hypothesis(hypothesis_id="h-bad2", structure_digest="")):
        with pytest.raises(NoveltyRefused, match="not the canonical structure"):
            check_novelty(bad, snap, sealed_then_proposed(snap, bad), canonicalizer=CANON, equivalence=EQ)
    # re-review H5: a stub canonicalizer does not reproduce the snapshot's own digests
    with pytest.raises(NoveltyRefused, match="does not reproduce"):
        check_novelty(h, snap, led, canonicalizer=Canonicalizer(CANON.canonicalizer_id, lambda e: "u" * 64), equivalence=EQ)
    no_expr = hypothesis(hypothesis_id="h-noexpr", statement_payload={}, structure_digest="")
    assert check_novelty(no_expr, snap, sealed_then_proposed(snap, no_expr), canonicalizer=CANON,
                         equivalence=EQ).status is NoveltyStatus.NOVELTY_UNRESOLVED
    empty = snapshot(entries=())                                                            # N3
    assert check_novelty(fresh, empty, sealed_then_proposed(empty, fresh), canonicalizer=CANON).status is NoveltyStatus.NOVELTY_UNRESOLVED
    unverifiable = snapshot(entries=stripped.entries)                                       # no expression to self-test against
    assert check_novelty(fresh, unverifiable, sealed_then_proposed(unverifiable, fresh),
                         canonicalizer=CANON).status is NoveltyStatus.NOVELTY_UNRESOLVED
    with pytest.raises(NoveltyRefused, match="sources"):
        snapshot(sources=())
    mech = novel_h(mul(c(1.0), pw(v("x"), 0.83)), hypothesis_id="h-mech", kind=HypothesisKind.MECHANISM, model_ref="m")
    assert check_novelty(mech, snap, sealed_then_proposed(snap, mech), canonicalizer=CANON,
                         equivalence=EQ).status is NoveltyStatus.NOVELTY_UNRESOLVED


def test_numeric_equivalence_is_declared_tri_state_and_novelty_is_verified_not_asserted():
    snap = snapshot()
    rewritten = mul(pw(v("x"), 0.37), v("x"), c(5.0))           # canonicalization already merges this ...
    assert structure_digest(rewritten) == structure_digest(KNOWN)
    h = novel_h({"exp": mul(c(1.37), {"log": v("x")})})          # ... this needs numeric equivalence
    led = sealed_then_proposed(snap, h)
    hit = check_novelty(h, snap, led, canonicalizer=CANON, equivalence=EQ)
    assert hit.status is NoveltyStatus.KNOWN_EQUIVALENT and hit.equivalence["probes"] and hit.equivalence["evaluator_id"]
    with pytest.raises(NoveltyRefused, match="exactly the one the snapshot declares"):     # re-review M3: not optional or steered
        check_novelty(h, snap, led, canonicalizer=CANON)
    with pytest.raises(NoveltyRefused, match="exactly the one the snapshot declares"):
        check_novelty(h, snap, led, canonicalizer=CANON, equivalence=EquivalenceSpec("e", evaluate, ({"x": 1.0}, {"x": 2.0}), 1e-9))
    with pytest.raises(NoveltyRefused, match=">= 2 probe"):
        EquivalenceSpec("e", evaluate, ({"x": 1.0},), 1e-9)
    # N4: a probe at a shared zero is skipped, not "different"; NaN is undecided, not "different"
    zeq = EquivalenceSpec("zero-aware", lambda e, p: 0.0 if p["x"] == 0 else evaluate(e, p), ({"x": 0.0}, {"x": 1.0}, {"x": 2.0}), 1e-9)
    zsnap = snapshot(entries=(PriorArtEntry("zero-law", structure_digest(v("x")), "doi:z", v("x")),), equivalence=zeq.to_dict())
    hz = novel_h(mul(c(3.0), {"exp": {"log": v("x")}}), hypothesis_id="h-zero")
    assert check_novelty(hz, zsnap, sealed_then_proposed(zsnap, hz), canonicalizer=CANON,
                         equivalence=zeq).status is NoveltyStatus.KNOWN_EQUIVALENT
    nan_eq = EquivalenceSpec("nan", lambda e, p: float("nan"), ({"x": 1.0}, {"x": 2.0}), 1e-9)
    nsnap = snapshot(equivalence=nan_eq.to_dict())
    hn = novel_h(mul(c(1.0), pw(v("x"), 0.83)), hypothesis_id="h-new")
    assert check_novelty(hn, nsnap, sealed_then_proposed(nsnap, hn), canonicalizer=CANON,
                         equivalence=nan_eq).status is NoveltyStatus.NOVELTY_UNRESOLVED
    # N5 / re-review H7: apply runs the check; verify re-runs it; content change resets novelty
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
