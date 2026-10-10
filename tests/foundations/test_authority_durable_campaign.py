"""Big Rock 1 (1E): discovery ledgers survive restart -- a durable campaign journaled into the signed authority ledger.

Restart must not drop, reorder or rewrite anything, change an authority key, or replace the registry, without detection.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from engcore.authority import AuthorityLedger, AuthorityRefused, EphemeralKeyProvider, FileLedgerStore, Role
from engcore.blindfold.expression import c, mul, pw, structure_digest, v
from engcore.claims.durable_campaign import CampaignRefused, DurableCampaign
from engcore.claims.multiplicity import MultiplicityRefused
from engcore.claims.falsification import CriterionKind, EvidenceSource, Falsifier, Verdict, verify_status
from engcore.claims.novelty import PriorArtEntry, PriorArtSnapshot
from engcore.sria.decision import Hypothesis, HypothesisKind, HypothesisPrediction, HypothesisStatus

CTX = hashlib.sha256(b"battery-dry-run").hexdigest()
LAW = mul(c(2.0), pw(v("x"), 1.37))
COND = {"x": 2.0}


def hypothesis(**kw):
    base = dict(hypothesis_id="h1", model_ref="law:candidate", kind=HypothesisKind.EQUATION, statement="y = a x^1.37",
                statement_payload={"expression": LAW}, structure_digest=structure_digest(LAW),
                predictions=(HypothesisPrediction("y", "m", "cond:x=2"),), falsifier_refs=("f1@v1",))
    base.update(kw)
    return Hypothesis(**base)


def falsifier(h):
    return Falsifier("f1", h.hypothesis_id, h.content_digest, "y", "m", COND, EvidenceSource.MEASUREMENT_RECORD,
                     CriterionKind.PREDICTION_DEVIATION, {"k": 3.0, "predicted": 5.17, "prediction_uncertainty": 0.01, "resolution": 0.2})


def ledger(tmp_path, keys):
    root = keys.signer("root")
    led = AuthorityLedger.create(FileLedgerStore(tmp_path / "authority.jsonl"), ledger_id="battery-campaign", profile="test", root=root)
    led.register_issuer(root, "exposure", keys.signer("exposure").public_hex, key_class="test", roles=[Role.EXPOSURE])
    led.register_issuer(root, "other", keys.signer("other").public_hex, key_class="test", roles=[Role.VALIDATION])
    return led


def run_campaign(tmp_path):
    keys = EphemeralKeyProvider()                          # the SAME provider after restart = the operator's persistent key store
    led = ledger(tmp_path, keys)
    camp = DurableCampaign.start(led, keys, issuer_id="exposure", campaign_id="bat-1", authority_id="lab", context_digest=CTX)
    h = hypothesis()
    snap = PriorArtSnapshot("fade-laws/1", ("equation",), (PriorArtEntry("arrhenius", "0" * 64, "doi:x"),), ("corpus:manifest-1",),
                            "manual review", "forge.structure/1")
    camp.seal_prior_art(snap)
    ticket = camp.register(h)
    camp.seal(falsifier(h), ticket)
    camp.count("count", "generated", 3)
    camp.count("count", "deduplicated", 3)
    camp.count("count", "admitted", 1)
    camp.count("tested", "h1")
    item = camp.release(evidence_id="cell-7/rpt-12", source="measurement_record", observable="y", unit="m", value=5.9,
                        uncertainty=0.01, conditions=COND)
    refuted = camp.apply_verdicts(h)
    return keys, led, camp, h, ticket, item, refuted


def test_a_campaign_resumes_exactly_after_restart(tmp_path):
    keys, led, camp, h, ticket, item, refuted = run_campaign(tmp_path)
    assert refuted.status is HypothesisStatus.REFUTED
    anchor, heads, final = led.anchor(), camp.heads(), camp.close_multiplicity()
    saved_ctx = json.loads(json.dumps(final.to_dict()))
    anchor = led.anchor()
    # --- restart: a new ledger object from the file, a new campaign object from the journal
    led2 = AuthorityLedger.open(FileLedgerStore(tmp_path / "authority.jsonl"), anchor=anchor)
    camp2 = DurableCampaign.resume(led2, keys, issuer_id="exposure", campaign_id="bat-1")
    assert camp2.heads() == {**heads, "multiplicity": camp2.heads()["multiplicity"]} and camp2.journal_length == camp.journal_length + 0
    assert camp2.authority.fingerprint == camp.authority.fingerprint and camp2.authority.verify(item)       # same key, same MAC
    assert verify_status(refuted, camp2.registry, anchor=camp.registry.anchor) == []                        # the verdict survived
    assert camp2.verify_context(saved_ctx)
    camp2.register(h.revise(statement="y = a x^1.37 (revised)"), ticket)                                   # the owner ticket survived
    with pytest.raises(MultiplicityRefused, match="closed"):
        camp2.count("count", "generated", 1)                                                                # closed stays closed


def test_restart_detects_dropped_reordered_or_rewritten_operations(tmp_path):
    keys, led, camp, *_ = run_campaign(tmp_path)
    anchor = led.anchor()
    lines = (tmp_path / "authority.jsonl").read_text().splitlines()

    def resumed(new_lines, a=anchor):
        p = tmp_path / "copy.jsonl"
        p.write_text("\n".join(new_lines) + "\n")
        return DurableCampaign.resume(AuthorityLedger.open(FileLedgerStore(p), anchor=a), keys, issuer_id="exposure", campaign_id="bat-1")
    with pytest.raises(AuthorityRefused, match="truncated"):
        resumed(lines[:-1])                                         # the refuting release / verdict dropped
    with pytest.raises(AuthorityRefused):
        resumed(lines[:-3] + [lines[-1], lines[-2], lines[-3]])     # reordered
    ev = json.loads(lines[-2])
    ev["body"]["attestation"]["record"]["args"]["release"]["value"] = 5.17          # rewrite the measurement
    with pytest.raises(AuthorityRefused):
        resumed(lines[:-2] + [json.dumps(ev), lines[-1]])
    # an ANCHOR the attacker re-derives over a shortened ledger is not the consumer's anchor: the consumer keeps its own
    short = AuthorityLedger.open(FileLedgerStore(tmp_path / "authority.jsonl"), anchor=anchor)
    assert short.length == len(lines)


def test_another_key_or_issuer_cannot_resume_or_extend_the_campaign(tmp_path):
    keys, led, camp, h, *_ = run_campaign(tmp_path)
    with pytest.raises(CampaignRefused, match="not this campaign"):
        DurableCampaign.resume(led, keys, issuer_id="other", campaign_id="bat-1")
    forged_keys = EphemeralKeyProvider()
    forged_keys._signers["exposure"] = keys.signer("exposure")    # the right signer, another secret: another authority
    with pytest.raises(CampaignRefused, match="recorded heads"):
        DurableCampaign.resume(led, forged_keys, issuer_id="exposure", campaign_id="bat-1")
    with pytest.raises(CampaignRefused, match="already has a journal"):
        DurableCampaign.start(led, keys, issuer_id="exposure", campaign_id="bat-1", authority_id="lab", context_digest=CTX)
    led.revoke(keys.signer("root"), "exposure", "drill")
    with pytest.raises(AuthorityRefused, match="revoked"):
        camp.count("seed", "s1")


def test_a_mutation_around_the_journal_is_refused_not_lost(tmp_path):
    keys, led, camp, h, ticket, *_ = run_campaign(tmp_path)
    camp.registry.register(h.revise(statement="unjournaled"), ticket)          # bypasses the journal
    with pytest.raises(CampaignRefused, match="outside its journal"):
        camp.count("seed", "s1")


def test_a_verdict_judged_before_restart_is_the_same_verdict_after(tmp_path):
    keys, led, camp, h, *_ = run_campaign(tmp_path)
    before = [v.to_dict() for v in camp.registry.verdicts_for(h.hypothesis_id, h.content_digest)]
    assert before and before[0]["verdict"] == Verdict.REFUTED.value
    camp2 = DurableCampaign.resume(AuthorityLedger.open(FileLedgerStore(tmp_path / "authority.jsonl"), anchor=led.anchor()), keys,
                                   issuer_id="exposure", campaign_id="bat-1")
    assert [v.to_dict() for v in camp2.registry.verdicts_for(h.hypothesis_id, h.content_digest)] == before
