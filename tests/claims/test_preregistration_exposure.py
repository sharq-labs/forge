"""Big Rocks Rock 3 (generic): pre-registration freeze, dataset exposure gate, discipline re-derivation, Discovery Passport.

Every refusal here is an attack on blinding: releasing confirmatory data before the protocol is frozen, before the
owner approved it, before every hypothesis has a sealed falsifier, by a non-owner "approving" their own campaign, by
calling the campaign's release around the gate, or by revising the protocol after exposure.
"""

from __future__ import annotations

import hashlib

import pytest

from engcore.authority import (
    AuthorityLedger,
    AuthorityRefused,
    EphemeralKeyProvider,
    MemoryLedgerStore,
    Role,
)
from engcore.blindfold.expression import c, mul, pw, structure_digest, v
from engcore.claims.discovery_passport import STANDARD_LIMITS, DiscoveryPassport
from engcore.claims.durable_campaign import DurableCampaign
from engcore.claims.exposure_dataset import (
    DatasetManifest,
    ExposureGate,
    ExposureRefused,
    approve_confirmatory,
    declare_untestable,
    register_manifest,
    verify_discipline,
)
from engcore.claims.falsification import CriterionKind, EvidenceSource, Falsifier
from engcore.claims.preregistration import (
    REQUIRED_SECTIONS,
    Preregistration,
    PreregistrationRefused,
    freeze,
    frozen_revisions,
)
from engcore.sria.decision import Hypothesis, HypothesisKind, HypothesisPrediction

CTX = hashlib.sha256(b"prereg-exposure").hexdigest()
LAW = mul(c(2.0), pw(v("x"), 1.37))
ROWS = {"e1": {"value": 2.6, "uncertainty": 0.01, "conditions": {"x": 1.0}},
        "c1": {"value": 5.2, "uncertainty": 0.01, "conditions": {"x": 2.0}}}


def hyp(hid="h1"):
    return Hypothesis(hypothesis_id=hid, model_ref=f"law:{hid}", kind=HypothesisKind.EQUATION, statement="y = a x^1.37",
                      statement_payload={"expression": LAW}, structure_digest=structure_digest(LAW),
                      predictions=(HypothesisPrediction("y", "m", "cond:x=2"),), falsifier_refs=(f"{hid}-f1@v1",))


def falsifier(h, x=2.0):
    return Falsifier(f"{h.hypothesis_id}-f1", h.hypothesis_id, h.content_digest, "y", "m", {"x": x}, EvidenceSource.MEASUREMENT_RECORD,
                     CriterionKind.PREDICTION_DEVIATION, {"k": 3.0, "predicted": 5.17, "prediction_uncertainty": 0.01, "resolution": 0.2})


def sections(hs, **over):
    base = {k: f"stated: {k}" for k in REQUIRED_SECTIONS}
    base.update(hypothesis_set=[{"hypothesis_id": h.hypothesis_id, "content_digest": h.content_digest} for h in hs],
                multiplicity_budget={"max_generated_hypotheses": 4, "max_admitted_hypotheses": 2, "confirmatory_query_budget": 4},
                false_elimination_audit_rate=0.5, confirmatory_dataset={"dataset": "ds", "partition": "confirmatory"})
    base.update(over)
    return base


class Setup:
    def __init__(self, hs=None):
        self.keys = EphemeralKeyProvider()
        root = self.keys.signer("root")
        self.led = AuthorityLedger.create(MemoryLedgerStore(), ledger_id="prereg", profile="test", root=root)
        for issuer, roles in (("exposure", [Role.EXPOSURE]), ("owner", [Role.OWNER]), ("other", [Role.EXPOSURE])):
            self.led.register_issuer(root, issuer, self.keys.signer(issuer).possession("prereg", issuer), roles=roles)
        self.camp = DurableCampaign.start(self.led, self.keys, issuer_id="exposure", campaign_id="c", authority_id="lab", context_digest=CTX)
        self.hs = hs or (hyp("h1"),)
        self.tickets = {h.hypothesis_id: self.camp.register(h) for h in self.hs}
        self.manifest = DatasetManifest("ds", "1", "test", "one row per checkpoint", {"exploratory": ["e1"], "confirmatory": ["c1"]})
        register_manifest(self.camp, self.led, self.keys.signer("exposure"), "exposure", self.manifest)
        self.prereg = Preregistration("p", 1, sections(self.hs))
        self.gate = ExposureGate(self.camp, self.led, issuer_id="exposure", manifest=self.manifest, rows=ROWS.__getitem__,
                                 observable="y", unit="m")

    def freeze(self, prereg=None):
        return freeze(self.led, self.keys.signer("exposure"), "exposure", prereg or self.prereg, campaign_id="c", context_digest=CTX)

    def approve(self, prereg=None, *, signer="owner"):
        return approve_confirmatory(self.led, self.keys.signer(signer), signer, campaign_id="c", context_digest=CTX,
                                    preregistration_digest=(prereg or self.prereg).digest, manifest_digest=self.manifest.digest,
                                    note="approved for test")

    def seal_all(self):
        for h in self.hs:
            self.camp.seal(falsifier(h), self.tickets[h.hypothesis_id])

    def ready(self):
        self.freeze()
        self.approve()
        self.seal_all()


def test_a_preregistration_states_every_section_and_names_confirmatory_data_by_identity_only():
    hs = (hyp(),)
    Preregistration("p", 1, sections(hs))
    for k in ("falsification_criteria", "stopping_rule", "negative_result_rule"):
        with pytest.raises(PreregistrationRefused, match="missing or empty"):
            Preregistration("p", 1, {**sections(hs), k: ""})
    with pytest.raises(PreregistrationRefused, match="identity only"):
        Preregistration("p", 1, sections(hs, confirmatory_dataset={"dataset": "ds", "nested": {"values": [5.2]}}))
    with pytest.raises(PreregistrationRefused, match="non-negative integers"):
        Preregistration("p", 1, sections(hs, multiplicity_budget={"max_generated_hypotheses": True, "max_admitted_hypotheses": 1,
                                                                  "confirmatory_query_budget": 1}))
    with pytest.raises(PreregistrationRefused, match="content digest"):
        Preregistration("p", 1, sections(hs, hypothesis_set=[{"hypothesis_id": "h1"}]))
    with pytest.raises(PreregistrationRefused, match="parent"):
        Preregistration("p", 2, sections(hs))


def test_frozen_revisions_chain_and_ignore_other_issuers():
    s = Setup()
    s.freeze()
    rev2 = s.prereg.revise(stopping_rule="stop sooner")
    assert rev2.parent_digest == s.prereg.digest and s.prereg.sections["stopping_rule"] == "stated: stopping_rule"
    s.freeze(rev2)
    freeze(s.led, s.keys.signer("other"), "other", Preregistration("p", 1, sections(s.hs, stopping_rule="squatter")), campaign_id="c",
           context_digest=CTX)
    assert [p.digest for _seq, p in frozen_revisions(s.led, "c", issuer_id="exposure")] == [s.prereg.digest, rev2.digest]
    with pytest.raises(PreregistrationRefused, match="extends"):
        s.freeze(rev2.revise(stopping_rule="x").revise(stopping_rule="y"))      # skips a revision
    with pytest.raises(PreregistrationRefused, match="extends"):
        s.freeze(s.prereg.revise(stopping_rule="a fork of revision 1"))         # forks an older revision


def test_the_gate_refuses_confirmatory_data_until_frozen_approved_and_sealed():
    s = Setup()
    s.gate.exploratory("e1")
    with pytest.raises(ExposureRefused, match="confirmatory gate"):
        s.gate.exploratory("c1")
    with pytest.raises(ExposureRefused, match="FROZEN"):
        s.gate.confirmatory("c1", preregistration=s.prereg)
    s.freeze()
    with pytest.raises(ExposureRefused, match="OWNER approval"):
        s.gate.confirmatory("c1", preregistration=s.prereg)
    with pytest.raises(AuthorityRefused):                      # the campaign operator cannot approve its own release
        s.approve(signer="exposure")
    s.approve(Preregistration("p", 1, sections(s.hs, stopping_rule="another protocol")))
    with pytest.raises(ExposureRefused, match="OWNER approval"):  # approval of another protocol is not approval of this one
        s.gate.confirmatory("c1", preregistration=s.prereg)
    s.approve()
    with pytest.raises(ExposureRefused, match="neither a sealed falsifier"):
        s.gate.confirmatory("c1", preregistration=s.prereg)
    s.seal_all()
    item = s.gate.confirmatory("c1", preregistration=s.prereg)
    assert item.conditions["partition"] == "confirmatory"
    assert verify_discipline(s.led, s.camp, issuer_id="exposure")["status"] == "CONFIRMATORY"


def test_an_untestable_declaration_is_an_abstention_not_a_drop():
    hs = (hyp("h1"), hyp("h2"))
    s = Setup(hs)
    s.freeze()
    s.approve()
    s.camp.seal(falsifier(hs[0]), s.tickets["h1"])
    with pytest.raises(ExposureRefused, match="h2"):
        s.gate.confirmatory("c1", preregistration=s.prereg)
    declare_untestable(s.camp, s.led, s.keys.signer("exposure"), "exposure", hypothesis_id="h2", content_digest=hs[1].content_digest,
                       reason="fit too uncertain to reach the resolution")
    s.gate.confirmatory("c1", preregistration=s.prereg)
    d = verify_discipline(s.led, s.camp, issuer_id="exposure")
    assert d["status"] == "CONFIRMATORY" and [u["hypothesis_id"] for u in d["untestable"]] == ["h2"]
    with pytest.raises(ExposureRefused, match="states why"):
        declare_untestable(s.camp, s.led, s.keys.signer("exposure"), "exposure", hypothesis_id="h1", content_digest="x", reason=" ")


def test_releasing_around_the_gate_is_detected_from_the_ledger():
    s = Setup()
    s.camp.release(evidence_id="ds/c1", source="measurement_record", observable="y", unit="m", value=5.2, uncertainty=0.01,
                   conditions={"x": 2.0, "partition": "confirmatory"})
    d = verify_discipline(s.led, s.camp, issuer_id="exposure")
    assert d["status"] == "EXPLORATORY"
    assert any("before any pre-registration" in i for i in d["issues"])
    assert any("before the owner's approval" in i for i in d["issues"])
    assert any("before any falsifier" in i for i in d["issues"])


def test_revising_or_sealing_after_exposure_makes_the_campaign_exploratory():
    s = Setup()
    s.ready()
    s.gate.confirmatory("c1", preregistration=s.prereg)
    s.freeze(s.prereg.revise(success_criteria="moved after seeing data"))
    d = verify_discipline(s.led, s.camp, issuer_id="exposure")
    assert d["status"] == "EXPLORATORY" and any("revised after confirmatory exposure" in i for i in d["issues"])
    s2 = Setup((hyp("h1"), hyp("h2")))
    s2.freeze()
    s2.approve()
    s2.camp.seal(falsifier(s2.hs[0]), s2.tickets["h1"])
    declare_untestable(s2.camp, s2.led, s2.keys.signer("exposure"), "exposure", hypothesis_id="h2",
                       content_digest=s2.hs[1].content_digest, reason="r")
    s2.gate.confirmatory("c1", preregistration=s2.prereg)
    s2.camp.seal(falsifier(s2.hs[1], x=3.0), s2.tickets["h2"])          # at unreleased conditions: sealable, but LATE
    d2 = verify_discipline(s2.led, s2.camp, issuer_id="exposure")
    assert d2["status"] == "EXPLORATORY" and any("sealed after confirmatory exposure" in i for i in d2["issues"])


def test_the_confirmatory_query_budget_is_enforced_by_re_derivation():
    s = Setup()
    s.prereg = Preregistration("p", 1, sections(s.hs, multiplicity_budget={"max_generated_hypotheses": 4, "max_admitted_hypotheses": 2,
                                                                          "confirmatory_query_budget": 1}))
    s.ready()
    s.gate.confirmatory("c1", preregistration=s.prereg)
    assert verify_discipline(s.led, s.camp, issuer_id="exposure")["status"] == "CONFIRMATORY"
    s.gate.confirmatory("c1", preregistration=s.prereg)
    d = verify_discipline(s.led, s.camp, issuer_id="exposure")
    assert d["status"] == "EXPLORATORY" and any("confirmatory releases" in i for i in d["issues"])


def _passport(run_kind, **over):
    parts = {"hypothesis": {"status": "surviving", "novelty_status": "possibly_novel"}, "protocol": {"discipline": "CONFIRMATORY"},
             "credibility": {"requirement_met": True, "issuer_bound": True}, "adversarial": {"outcome": "survived"}}
    parts.update(over)
    return DiscoveryPassport("p", run_kind, parts["hypothesis"], parts["protocol"], credibility=parts["credibility"],
                             adversarial=parts["adversarial"], verdict_limits=STANDARD_LIMITS)


def test_a_passport_counts_as_discovery_only_when_every_gate_holds_and_never_for_a_dry_run():
    assert _passport("confirmatory").counts_as_discovery
    assert not _passport("dry_run_synthetic").counts_as_discovery
    assert not _passport("exploratory").counts_as_discovery
    assert not _passport("confirmatory", protocol={"discipline": "EXPLORATORY"}).counts_as_discovery
    assert not _passport("confirmatory", hypothesis={"status": "surviving", "novelty_status": "known_equivalent"}).counts_as_discovery
    assert not _passport("confirmatory", credibility={"requirement_met": True, "issuer_bound": False}).counts_as_discovery
    assert not _passport("confirmatory", adversarial={"outcome": "falsified"}).counts_as_discovery
    with pytest.raises(ValueError, match="limits"):
        DiscoveryPassport("p", "confirmatory", {}, {}, verdict_limits=())
    with pytest.raises(ValueError, match="dry run"):
        DiscoveryPassport("p", "real", {}, {}, verdict_limits=STANDARD_LIMITS)
