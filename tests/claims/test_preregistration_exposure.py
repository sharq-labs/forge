"""Big Rocks Rock 3 (generic): pre-registration freeze, dataset exposure gate, discipline re-derivation, Discovery Passport.

Every refusal here is an attack on blinding: releasing confirmatory data before the protocol is frozen, before the
owner approved it, before every hypothesis has a sealed falsifier, by the operator "approving" its own campaign, by
calling the campaign's release around the gate (with or without a partition label), by re-partitioning rows in a
second manifest, by serving another row's value, by choosing the issuer the discipline is read for, by abstaining
from an inconvenient hypothesis, or by revising the protocol after exposure.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from engcore.authority import (
    AuthorityLedger,
    AuthorityRefused,
    EphemeralKeyProvider,
    MemoryLedgerStore,
    Role,
)
from engcore.blindfold.expression import c, mul, pw, structure_digest, v
from engcore.claims.discovery_passport import (
    STANDARD_LIMITS,
    DiscoveryPassport,
    verify_passport,
)
from engcore.claims.durable_campaign import DurableCampaign
from engcore.claims.exposure_dataset import (
    DatasetManifest,
    ExposureGate,
    ExposureRefused,
    approve_confirmatory,
    commit_row,
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
SALT = {"e1": os.urandom(16), "c1": os.urandom(16), "c2": os.urandom(16)}
ROWS = {"e1": {"value": 2.6, "uncertainty": 0.01, "conditions": {"x": 1.0}},
        "c1": {"value": 5.2, "uncertainty": 0.01, "conditions": {"x": 2.0}},
        "c2": {"value": 5.3, "uncertainty": 0.01, "conditions": {"x": 2.0}}}
for _rid, _row in ROWS.items():
    _row["salt"] = SALT[_rid].hex()
RULE = {"criterion": "prediction_deviation", "k": 3.0, "resolution": {"relative_cap": 0.25, "uncertainty_multiplier": 1.2,
                                                                      "absolute_floor": 0.004}}


def hyp(hid="h1"):
    return Hypothesis(hypothesis_id=hid, model_ref=f"law:{hid}", kind=HypothesisKind.EQUATION, statement="y = a x^1.37",
                      statement_payload={"expression": LAW}, structure_digest=structure_digest(LAW),
                      predictions=(HypothesisPrediction("y", "m", "cond:x=2"),), falsifier_refs=(f"{hid}-f1@v1",))


def falsifier(h, x=2.0, k=3.0):
    return Falsifier(f"{h.hypothesis_id}-f1", h.hypothesis_id, h.content_digest, "y", "m", {"x": x}, EvidenceSource.MEASUREMENT_RECORD,
                     CriterionKind.PREDICTION_DEVIATION, {"k": k, "predicted": 5.17, "prediction_uncertainty": 0.01, "resolution": 0.2})


def sections(hs, **over):
    base = {k: f"stated: {k}" for k in REQUIRED_SECTIONS}
    base.update(hypothesis_set=[{"hypothesis_id": h.hypothesis_id, "content_digest": h.content_digest} for h in hs],
                multiplicity_budget={"max_generated_hypotheses": 4, "max_admitted_hypotheses": 2, "confirmatory_query_budget": 4},
                false_elimination_audit_rate=0.5, confirmatory_dataset={"dataset": "ds", "partition": "confirmatory"})
    base.update(over)
    return base


def manifest(**over):
    kw = {"partitions": {"exploratory": ["e1"], "confirmatory": ["c1", "c2"]},
          "row_commitments": {r: commit_row("ds", r, ROWS[r], SALT[r]) for r in ROWS}}
    kw.update(over)
    return DatasetManifest("ds", "1", "test", "one row per checkpoint", **kw)


class Setup:
    def __init__(self, hs=None, *, owner_roles=(Role.OWNER,), **prereg_over):
        self.keys = EphemeralKeyProvider()
        self.root = self.keys.signer("root")
        self.led = AuthorityLedger.create(MemoryLedgerStore(), ledger_id="prereg", profile="test", root=self.root)
        for issuer, roles in (("exposure", [Role.EXPOSURE]), ("owner", list(owner_roles)), ("other", [Role.EXPOSURE])):
            self.led.register_issuer(self.root, issuer, self.keys.signer(issuer).possession("prereg", issuer), roles=roles)
        self.camp = DurableCampaign.start(self.led, self.keys, issuer_id="exposure", campaign_id="c", authority_id="lab", context_digest=CTX)
        self.hs = hs or (hyp("h1"),)
        self.tickets = {h.hypothesis_id: self.camp.register(h) for h in self.hs}
        self.manifest = manifest()
        register_manifest(self.camp, self.led, self.keys.signer("exposure"), "exposure", self.manifest)
        self.prereg = Preregistration("p", 1, sections(self.hs, **prereg_over))
        self.gate = ExposureGate(self.camp, self.led, manifest=self.manifest, rows=ROWS.__getitem__, observable="y", unit="m")

    def freeze(self, prereg=None):
        return freeze(self.led, self.keys.signer("exposure"), "exposure", prereg or self.prereg, campaign_id="c", context_digest=CTX)

    def approve(self, prereg=None, *, signer="owner", ctx=CTX, manifest_digest=None):
        return approve_confirmatory(self.led, self.keys.signer(signer), signer, campaign_id="c", context_digest=ctx,
                                    preregistration_digest=(prereg or self.prereg).digest,
                                    manifest_digest=manifest_digest or self.manifest.digest, note="approved for test")

    def seal_all(self):
        for h in self.hs:
            self.camp.seal(falsifier(h), self.tickets[h.hypothesis_id])

    def ready(self):
        self.freeze()
        self.approve()
        self.seal_all()

    def release_around(self, rid="c1", **conds):
        return self.camp.release(evidence_id=f"ds/{rid}", source="measurement_record", observable="y", unit="m", value=ROWS[rid]["value"],
                                 uncertainty=0.01, conditions={"x": 2.0, **conds})

    def discipline(self):
        return verify_discipline(self.led, self.camp)


# ---------------------------------------------------------------------------- pre-registration


def test_a_preregistration_states_every_section_and_names_confirmatory_data_by_identity_only():
    hs = (hyp(),)
    Preregistration("p", 1, sections(hs))
    for k in ("falsification_criteria", "stopping_rule", "negative_result_rule"):
        for empty in ("", "   ", False):
            with pytest.raises(PreregistrationRefused, match="missing or empty"):
                Preregistration("p", 1, {**sections(hs), k: empty})
    for leak in ({"dataset": "ds", "nested": {"values": [5.2]}}, {"dataset": "ds", "Values": [0.05]}, {"holdout": [0.05, 0.06]},
                 {"dataset": "ds", "identity": 5.2}, {"identity": "x", "requirements": [0.05]}):
        with pytest.raises(PreregistrationRefused, match="identity only"):
            Preregistration("p", 1, sections(hs, confirmatory_dataset=leak))
    with pytest.raises(PreregistrationRefused, match="identity only"):              # content keys are refused in ANY section
        Preregistration("p", 1, sections(hs, success_criteria={"Observations": [0.05]}))
    with pytest.raises(PreregistrationRefused, match="non-negative integers"):
        Preregistration("p", 1, sections(hs, multiplicity_budget={"max_generated_hypotheses": True, "max_admitted_hypotheses": 1,
                                                                  "confirmatory_query_budget": 1}))
    with pytest.raises(PreregistrationRefused, match="content digest"):
        Preregistration("p", 1, sections(hs, hypothesis_set=[{"hypothesis_id": "h1"}]))
    with pytest.raises(PreregistrationRefused, match="once"):
        Preregistration("p", 1, sections(hs, hypothesis_set=[{"hypothesis_id": "h1", "content_digest": "a"}] * 2))
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


# ---------------------------------------------------------------------------- the gate


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
    with pytest.raises(ExposureRefused, match="EXPOSURE role"):        # the campaign operator cannot approve its own release
        s.approve(signer="exposure")
    s.approve(Preregistration("p", 1, sections(s.hs, stopping_rule="another protocol")))
    s.approve(ctx=hashlib.sha256(b"another decision").hexdigest())
    with pytest.raises(ExposureRefused, match="OWNER approval"):      # another protocol, another context: not this one
        s.gate.confirmatory("c1", preregistration=s.prereg)
    s.approve()
    with pytest.raises(ExposureRefused, match="neither a sealed falsifier"):
        s.gate.confirmatory("c1", preregistration=s.prereg)
    s.seal_all()
    item = s.gate.confirmatory("c1", preregistration=s.prereg)
    assert item.conditions["partition"] == "confirmatory"
    assert s.discipline()["status"] == "CONFIRMATORY"


def test_an_owner_who_also_operates_or_was_revoked_does_not_count():                               # review C M-1
    s = Setup(owner_roles=(Role.OWNER, Role.EXPOSURE))
    s.freeze()
    with pytest.raises(ExposureRefused, match="EXPOSURE role"):
        s.approve()
    s2 = Setup()
    s2.ready()
    s2.led.revoke(s2.root, "owner", "left the project")
    with pytest.raises(ExposureRefused, match="OWNER approval"):
        s2.gate.confirmatory("c1", preregistration=s2.prereg)


def test_a_row_is_released_only_if_it_matches_its_manifest_commitment():                           # review C M-5
    s = Setup()
    s.ready()
    swapped = ExposureGate(s.camp, s.led, manifest=s.manifest, rows=lambda rid: ROWS["c1"], observable="y", unit="m")
    with pytest.raises(ExposureRefused, match="commitment"):
        swapped.exploratory("e1")                                  # another row's value under an exploratory id
    edited = ExposureGate(s.camp, s.led, manifest=s.manifest, rows=lambda rid: {**ROWS[rid], "value": 9.9}, observable="y", unit="m")
    with pytest.raises(ExposureRefused, match="commitment"):
        edited.confirmatory("c1", preregistration=s.prereg)        # a value changed after the seal
    bare = manifest(row_commitments={})
    register_manifest(s.camp, s.led, s.keys.signer("exposure"), "exposure", bare)
    s.approve(manifest_digest=bare.digest)
    gate = ExposureGate(s.camp, s.led, manifest=bare, rows=ROWS.__getitem__, observable="y", unit="m")
    with pytest.raises(ExposureRefused, match="no commitment"):
        gate.confirmatory("c1", preregistration=s.prereg)


def test_a_second_manifest_cannot_repartition_a_registered_row():                                  # review C HIGH-1 (B)
    s = Setup()
    moved = manifest(partitions={"exploratory": ["e1", "c1"], "confirmatory": ["c2"]})
    with pytest.raises(ExposureRefused, match="never moves a registered row"):
        register_manifest(s.camp, s.led, s.keys.signer("exposure"), "exposure", moved)


def test_the_gate_and_the_verifier_read_the_campaigns_own_issuer():                               # review C HIGH-2
    s = Setup()
    with pytest.raises(ExposureRefused, match="owned by 'exposure'"):
        verify_discipline(s.led, s.camp, issuer_id="other")
    with pytest.raises(ExposureRefused, match="owned by 'exposure'"):
        ExposureGate(s.camp, s.led, manifest=s.manifest, rows=ROWS.__getitem__, observable="y", unit="m", issuer_id="other")
    assert s.discipline()["status"] == "NOT_FROZEN"                 # nothing happened: never a pass
    s.freeze()
    assert s.discipline()["status"] == "NO_CONFIRMATORY_RELEASE"


# ---------------------------------------------------------------------------- re-derivation from the ledger


def test_releasing_around_the_gate_is_detected_whatever_the_label():                               # review C HIGH-1 (A)
    for label in ({"partition": "confirmatory"}, {}, {"partition": "exploratory"}):
        s = Setup()
        s.release_around(**label)
        d = s.discipline()
        assert d["status"] == "EXPLORATORY" and d["confirmatory_releases"] == 1, label
        assert any("before any pre-registration" in i for i in d["issues"])
    s = Setup()
    s.camp.release(evidence_id="elsewhere/r9", source="measurement_record", observable="y", unit="m", value=1.0, uncertainty=0.01,
                   conditions={"x": 2.0})
    assert any("no row of a registered manifest" in i for i in s.discipline()["issues"])


def test_the_gate_conditions_are_re_derived_at_the_first_confirmatory_release():                  # review C HIGH-3
    hs = (hyp("h1"), hyp("h2"))
    s = Setup(hs)
    s.freeze()
    s.approve(Preregistration("p", 1, sections(s.hs, stopping_rule="another protocol")))       # approval of another protocol
    s.camp.seal(falsifier(hs[0]), s.tickets["h1"])                                             # h2 neither sealed nor abstained
    s.release_around(partition="confirmatory")
    issues = s.discipline()["issues"]
    assert any("without an OWNER approval of the pre-registration in force" in i for i in issues)
    assert any("'h2' had neither a sealed falsifier" in i for i in issues)
    s2 = Setup()
    s2.ready()
    s2.freeze(s2.prereg.revise(stopping_rule="revised, never approved"))                       # rev 2 in force, rev 1 approved
    s2.release_around(partition="confirmatory")
    assert any("without an OWNER approval" in i for i in s2.discipline()["issues"])


def test_revising_or_sealing_after_exposure_makes_the_campaign_exploratory():
    s = Setup()
    s.ready()
    s.gate.confirmatory("c1", preregistration=s.prereg)
    s.freeze(s.prereg.revise(success_criteria="moved after seeing data"))
    d = s.discipline()
    assert d["status"] == "EXPLORATORY" and any("revised after confirmatory exposure" in i for i in d["issues"])
    s2 = Setup((hyp("h1"), hyp("h2")))
    s2.freeze()
    s2.approve()
    s2.camp.seal(falsifier(s2.hs[0]), s2.tickets["h1"])
    declare_untestable(s2.camp, s2.led, s2.keys.signer("exposure"), "exposure", hypothesis_id="h2",
                       content_digest=s2.hs[1].content_digest, reason="r")
    s2.gate.confirmatory("c1", preregistration=s2.prereg)
    s2.camp.seal(falsifier(s2.hs[1], x=3.0), s2.tickets["h2"])          # at unreleased conditions: sealable, but LATE
    d2 = s2.discipline()
    assert d2["status"] == "EXPLORATORY" and any("sealed after confirmatory exposure" in i for i in d2["issues"])


def test_the_confirmatory_query_budget_and_multiplicity_come_from_the_journal():
    s = Setup(multiplicity_budget={"max_generated_hypotheses": 2, "max_admitted_hypotheses": 2, "confirmatory_query_budget": 1})
    s.ready()
    s.gate.confirmatory("c1", preregistration=s.prereg)
    assert s.discipline()["status"] == "CONFIRMATORY"
    s.gate.confirmatory("c2", preregistration=s.prereg)
    d = s.discipline()
    assert d["status"] == "EXPLORATORY" and any("confirmatory releases" in i for i in d["issues"])
    s.camp.count("count", "generated", 5)
    s.camp.multiplicity._counts["generated"] = 0                     # in-memory edit: the journal still says 5
    assert any("generated 5" in i for i in s.discipline()["issues"])


# ---------------------------------------------------------------------------- abstention


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
    d = s.discipline()
    assert d["status"] == "CONFIRMATORY" and [u["hypothesis_id"] for u in d["untestable"]] == ["h2"]
    with pytest.raises(ExposureRefused, match="states why"):
        declare_untestable(s.camp, s.led, s.keys.signer("exposure"), "exposure", hypothesis_id="h1", content_digest="x", reason=" ")


def test_untestable_is_not_a_choice_under_a_machine_readable_rule():                               # review C M-3, M-4
    hs = (hyp("h1"), hyp("h2"))
    s = Setup(hs, falsification_criteria=RULE)
    s.freeze()
    small = ({"predicted": 0.01, "prediction_uncertainty": 0.01, "observation_uncertainty": 0.01},)
    kw = {"hypothesis_id": "h2", "content_digest": hs[1].content_digest, "reason": "inconvenient"}
    with pytest.raises(ExposureRefused, match="no inputs"):
        declare_untestable(s.camp, s.led, s.keys.signer("exposure"), "exposure", **kw)
    with pytest.raises(ExposureRefused, match="REACHES a resolution"):
        declare_untestable(s.camp, s.led, s.keys.signer("exposure"), "exposure", **kw,
                           rule_inputs=({"predicted": 5.0, "prediction_uncertainty": 0.01, "observation_uncertainty": 0.01},))
    declare_untestable(s.camp, s.led, s.keys.signer("exposure"), "exposure", **kw, rule_inputs=small)
    s.camp.seal(falsifier(hs[0]), s.tickets["h1"])
    with pytest.raises(ExposureRefused, match="already has sealed falsifiers"):
        declare_untestable(s.camp, s.led, s.keys.signer("exposure"), "exposure", hypothesis_id="h1",
                           content_digest=hs[0].content_digest, reason="r", rule_inputs=small)
    with pytest.raises(ExposureRefused, match="not a pre-registered hypothesis"):
        declare_untestable(s.camp, s.led, s.keys.signer("exposure"), "exposure", hypothesis_id="h9", content_digest="0" * 64,
                           reason="r", rule_inputs=small)
    s.camp.seal(Falsifier("h1-f2", "h1", hs[0].content_digest, "y", "m", {"x": 3.0}, EvidenceSource.MEASUREMENT_RECORD,
                          CriterionKind.PREDICTION_DEVIATION, {"k": 2.0, "predicted": 5.17, "prediction_uncertainty": 0.01,
                                                               "resolution": 0.2}), s.tickets["h1"])
    assert any("departs from the pre-registered criterion / k" in i for i in s.discipline()["issues"])


# ---------------------------------------------------------------------------- passports


def _passport(run_kind, **over):
    parts = {"hypothesis": {"status": "surviving", "novelty_status": "possibly_novel"},
             "protocol": {"discipline": "CONFIRMATORY", "discipline_issues": []},
             "credibility": {"requirement_met": True, "issuer_bound": True, "test_mode": False},
             "adversarial": {"outcome": "survived"}, "authority_anchor": {"profile": "production"},
             "falsifiers": ({"ref": "f1", "verdicts": ["not_refuted"]},)}
    parts.update(over)
    return DiscoveryPassport("p", run_kind, parts["hypothesis"], parts["protocol"], parts["falsifiers"], credibility=parts["credibility"],
                             adversarial=parts["adversarial"], authority_anchor=parts["authority_anchor"], verdict_limits=STANDARD_LIMITS)


def test_a_passport_counts_as_discovery_only_when_every_gate_holds_and_never_for_a_dry_run():     # review C HIGH-4
    assert _passport("confirmatory").counts_as_discovery
    assert not _passport("dry_run_synthetic").counts_as_discovery
    assert not _passport("exploratory").counts_as_discovery
    for over in ({"protocol": {"discipline": "EXPLORATORY", "discipline_issues": []}},
                 {"protocol": {"discipline": "CONFIRMATORY", "discipline_issues": ["x"]}},
                 {"protocol": {"discipline": "CONFIRMATORY"}},
                 {"hypothesis": {"status": "surviving", "novelty_status": "known_equivalent"}},
                 {"credibility": {"requirement_met": True, "issuer_bound": False, "test_mode": False}},
                 {"credibility": {"requirement_met": True, "issuer_bound": True, "test_mode": True}},
                 {"authority_anchor": {"profile": "test"}},
                 {"adversarial": {"outcome": "falsified"}},
                 {"falsifiers": ()},
                 {"falsifiers": ({"ref": "f1", "verdicts": []},)},
                 {"falsifiers": ({"ref": "f1", "verdicts": ["inconclusive"]},)},
                 {"falsifiers": ({"ref": "f1", "verdicts": ["not_refuted"]}, {"ref": "f2", "verdicts": ["refuted"]})}):
        assert not _passport("confirmatory", **over).counts_as_discovery, over
    with pytest.raises(ValueError, match="limits"):
        DiscoveryPassport("p", "confirmatory", {}, {}, verdict_limits=("-",))
    with pytest.raises(ValueError, match="dry run"):
        DiscoveryPassport("p", "real", {}, {}, verdict_limits=STANDARD_LIMITS)


def test_verify_passport_re_derives_what_the_passport_asserts():
    s = Setup()
    s.ready()
    s.gate.confirmatory("c1", preregistration=s.prereg)
    f = falsifier(s.hs[0])
    v = s.camp.judge(f.digest, "ds/c1")
    true_d = s.discipline()
    honest = DiscoveryPassport("p", "confirmatory", {"hypothesis_id": "h1", "content_digest": s.hs[0].content_digest},
                               {"discipline": true_d["status"], "discipline_issues": true_d["issues"]},
                               ({"ref": f.ref, "digest": f.digest, "verdicts": [v.to_dict()["verdict"]]},),
                               authority_anchor=s.led.anchor().to_dict(), verdict_limits=STANDARD_LIMITS)
    assert verify_passport(honest, s.led, s.camp) == []
    lying = DiscoveryPassport("p", "confirmatory", {"hypothesis_id": "h1", "content_digest": s.hs[0].content_digest},
                              {"discipline": "CONFIRMATORY", "discipline_issues": ["hidden"]},
                              ({"ref": f.ref, "digest": f.digest, "verdicts": ["not_refuted", "not_refuted"]},),
                              authority_anchor={**s.led.anchor().to_dict(), "head": "0" * 64}, verdict_limits=STANDARD_LIMITS)
    problems = verify_passport(lying, s.led, s.camp)
    assert any(p.startswith("discipline") for p in problems) and any(p.startswith("authority anchor") for p in problems)
    assert any(p.startswith("falsifier") for p in problems)
    with pytest.raises(AuthorityRefused):                           # an unregistered approver never reaches the ledger
        approve_confirmatory(s.led, EphemeralKeyProvider().signer("x"), "x", campaign_id="c", context_digest=CTX,
                             preregistration_digest=s.prereg.digest, manifest_digest=s.manifest.digest, note="n")
