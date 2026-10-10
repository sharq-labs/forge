"""A Discovery Passport: the durable record of what ONE hypothesis went through, and the limits of what it shows.

It is a digest-bound summary of records owned elsewhere -- it holds no authority of its own and creates no evidence:

* identity: hypothesis id, content and claim digests, its verdict-backed status and its novelty status;
* protocol: the frozen pre-registration digest and revision, the dataset manifest digest, the exposure discipline
  (``CONFIRMATORY`` / ``EXPLORATORY`` with reasons, re-derived from the ledger);
* tests: every sealed falsifier (ref, digest) with every recorded verdict;
* search: the FINAL multiplicity context digest and the family size the result was selected from;
* screening: the FidelityGraph link identity and status, eliminations and the recorded false-elimination audit;
* adversarial: the Red Team envelope digest, outcome and its own statement of the region, routes and budget;
* credibility: the credibility report digest, ``requirement_met`` and ``issuer_bound``;
* authority: the authority-ledger anchor everything above can be re-verified against.

``verdict_limits`` always states what the passport does NOT show and always includes :data:`STANDARD_LIMITS` (a
SURVIVING status is not truth; solver or route agreement is not physical validation; a synthetic or exploratory run
is not a discovery).

``counts_as_discovery`` is computed from the passport's OWN fields, so it is an assertion until re-derived: True only
for a confirmatory run whose discipline is CONFIRMATORY with no issue, a SURVIVING, POSSIBLY_NOVEL hypothesis with at
least one sealed falsifier, EVERY falsifier NOT_REFUTED on at least one CONFIRMATORY row with no confirmatory REFUTED (and
no REFUTED anywhere), a credibility requirement met issuer-bound outside test mode, a PRODUCTION-profile authority
anchor and a SURVIVED Red Team envelope -- never for a dry run.  Exploratory verdicts never make a discovery.

:func:`verify_passport` re-derives every one of those from the records themselves -- the campaign's own ledger held to
the operator's TrustAnchor, the discipline, the hypothesis status (``verify_status``), every falsifier's verdicts and
confirmatory verdicts, the novelty check (re-run against the sealed snapshot), the credibility assessment (RE-RUN
against the campaign's ledger) and the Red Team outcome (read from its RED_TEAM attestation) -- and lists every
disagreement.  A passport is read as a discovery only when ``counts_as_discovery`` holds AND that list is empty.
Residual (stated): the Red Team envelope is bound to the hypothesis by its claim-route label.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

PASSPORT_SCHEMA = "engcore.claims.discovery_passport/1"
#: a discovery is held at least to a bar that REQUIRES validation (RISK_POLICY_V1: MEDIUM and above); a LOW bar can be met
#: by verification alone, and verification does not become validation
DISCOVERY_RISK_CLASSES = ("medium", "high", "critical")


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class DiscoveryPassport:
    passport_id: str
    run_kind: str                                  # "dry_run_synthetic" | "exploratory" | "confirmatory"
    hypothesis: Mapping[str, Any] = field(hash=False)
    protocol: Mapping[str, Any] = field(hash=False)
    falsifiers: tuple[Mapping[str, Any], ...] = ()
    multiplicity: Mapping[str, Any] = field(hash=False, default_factory=dict)
    screening: Mapping[str, Any] = field(hash=False, default_factory=dict)
    adversarial: Mapping[str, Any] = field(hash=False, default_factory=dict)
    credibility: Mapping[str, Any] = field(hash=False, default_factory=dict)
    authority_anchor: Mapping[str, Any] = field(hash=False, default_factory=dict)
    verdict_limits: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.run_kind not in ("dry_run_synthetic", "exploratory", "confirmatory"):
            raise ValueError("a passport states whether it is a dry run, exploratory or confirmatory")
        if not self.verdict_limits or not set(STANDARD_LIMITS) <= set(self.verdict_limits):
            raise ValueError("a passport states the limits of what it shows, the standard limits included")

    @property
    def counts_as_discovery(self) -> bool:
        verdicts = [v for f in self.falsifiers for v in f.get("verdicts", ())]
        confirmatory = [list(f.get("confirmatory_verdicts", ())) for f in self.falsifiers]
        return (self.run_kind == "confirmatory" and self.protocol.get("discipline") == "CONFIRMATORY"
                and self.protocol.get("discipline_issues") == []
                and self.hypothesis.get("status") == "surviving" and self.hypothesis.get("novelty_status") == "possibly_novel"
                and bool(self.falsifiers) and all(confirmatory) and all("refuted" not in c for c in confirmatory)
                and all("not_refuted" in c for c in confirmatory) and "refuted" not in verdicts
                and self.credibility.get("requirement_met") is True and self.credibility.get("issuer_bound") is True
                and self.credibility.get("risk_class") in DISCOVERY_RISK_CLASSES
                and self.credibility.get("test_mode") is False and self.authority_anchor.get("profile") == "production"
                and self.adversarial.get("outcome") == "survived")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PASSPORT_SCHEMA, "passport_id": self.passport_id, "run_kind": self.run_kind, "hypothesis": dict(self.hypothesis),
                "protocol": dict(self.protocol), "falsifiers": [dict(f) for f in self.falsifiers], "multiplicity": dict(self.multiplicity),
                "screening": dict(self.screening), "adversarial": dict(self.adversarial), "credibility": dict(self.credibility),
                "authority_anchor": dict(self.authority_anchor), "verdict_limits": list(self.verdict_limits),
                "counts_as_discovery": self.counts_as_discovery}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def verify_passport(passport: DiscoveryPassport, campaign: Any, *, trust_anchor: Any, hypothesis: Any,
                    credibility_inputs: Mapping[str, Any], envelope: Any, snapshot: Any, canonicalizer: Any, equivalence: Any = None,
                    red_team_subject: Any = None) -> list[str]:
    """Every way the passport disagrees with the records it summarizes (empty: it says what they say).  ``campaign`` is
    the durable campaign resumed from the operator's ledger; ``trust_anchor`` the OPERATOR's anchor (configuration, never
    the passport's own); the remaining arguments are the records themselves -- exact types, never look-alikes.
    ``credibility_inputs``: ``{"claim", "graph", "requirement", ...}`` -- the verifier RE-RUNS :func:`assess_credibility`
    against the campaign's ledger and the operator's anchor (a report object is never taken on trust).  Bindings: the
    credibility claim for hypothesis ``h`` is named ``claim:h`` and its requirement is in the campaign's context; the Red
    Team envelope's outcome and subject are read from its RED_TEAM attestation in the campaign's context, and it attacks
    a ``ClaimSubject`` whose claim route is ``h`` (a route LABEL: residual), with the pre-registered attack plan; every
    other admissible envelope for that claim must also have survived.  The credibility claim's leaf subjects are chosen
    by the verifier's inputs and bound to the hypothesis only by the claim label (residual); the decision, risk class,
    policy and claim structure are compared.  Not re-derived (stated): the manifest digest, the hypothesis claim digest,
    the screening summary and the original report digest (the re-run binds today's anchor)."""
    from ..authority import AuthorityLedger, Role, TrustAnchor
    from .durable_campaign import DurableCampaign
    from .exposure_dataset import verify_discipline
    from .falsification import RegistryAnchor, verify_status
    from .novelty import check_novelty
    from .redteam import _subject_digest
    out: list[str] = []
    if type(campaign) is not DurableCampaign:
        return ["campaign: not a DurableCampaign (its registry and novelty ledger must be the journal's replay)"]
    try:
        campaign._guard()                                  # live state equals the last journaled heads (nothing mutated around it)
    except Exception as exc:                               # noqa: BLE001
        return [f"campaign: {str(exc)[:160]}"]
    ledger = campaign.ledger
    if type(ledger) is not AuthorityLedger or ledger.verified_anchor is None or not ledger.extends(trust_anchor):
        return ["authority: the campaign's ledger is not an AuthorityLedger opened against, and extending, the operator's anchor"]
    try:
        if not ledger.extends(TrustAnchor.from_dict(dict(passport.authority_anchor))):
            out.append("authority anchor: the ledger does not extend the anchor the passport names")
    except Exception as exc:                                             # noqa: BLE001 - an unreadable anchor verifies nothing
        out.append(f"authority anchor: unreadable ({str(exc)[:80]})")
    if passport.authority_anchor.get("profile") != ledger.profile:
        out.append(f"authority anchor: the passport says profile {passport.authority_anchor.get('profile')!r}, the ledger is "
                   f"{ledger.profile!r}")
    d = verify_discipline(None, campaign)
    if passport.protocol.get("discipline") != d["status"] or list(passport.protocol.get("discipline_issues", [])) != d["issues"]:
        out.append(f"discipline: the passport says {passport.protocol.get('discipline')!r}, the ledger says {d['status']!r}")
    hid, cd = passport.hypothesis.get("hypothesis_id"), passport.hypothesis.get("content_digest")
    from ..sria.decision import Hypothesis
    from .durable_campaign import OP_KIND, campaign_subject
    registered: set[str] = set()
    for r in ledger.attestations(record_kind=OP_KIND, subject_digest=campaign_subject(campaign.campaign_id)):
        if r.issuer_id != campaign.issuer_id or r.attestation.role is not Role.EXPOSURE or r.attestation.record.get("op") != "register" \
                or r.attestation.context_digest != campaign.context_digest or ledger.compromised_at(r.issuer_id, r.key_id, r.sequence):
            continue
        try:
            h_rec = Hypothesis.from_dict(r.attestation.record_dict()["args"]["hypothesis"])
        except Exception:                                                # noqa: BLE001 - an unreadable registration registers nothing
            continue
        if h_rec.hypothesis_id == hid:
            registered.add(h_rec.content_digest)
    if type(hypothesis) is not Hypothesis or (hypothesis.hypothesis_id, hypothesis.content_digest) != (hid, cd) \
            or cd not in registered:
        return out + ["hypothesis: the record given is not the registered hypothesis the passport names"]
    reg = campaign.registry
    if hypothesis.status.value != passport.hypothesis.get("status"):
        out.append(f"status: the passport says {passport.hypothesis.get('status')!r}, the hypothesis is {hypothesis.status.value!r}")
    out.extend(f"status: {p}" for p in verify_status(hypothesis, reg, anchor=RegistryAnchor(campaign.authority.fingerprint,
                                                                                               campaign.campaign_id)))
    in_force = d.get("preregistration_in_force") or {}
    from .preregistration import frozen_revisions
    in_force_prereg = next((p for _s, p in frozen_revisions(ledger, campaign.campaign_id, issuer_id=campaign.issuer_id,
                                                            context_digest=campaign.context_digest)
                            if p.digest == in_force.get("digest")), None)
    if passport.protocol.get("preregistration_digest") != in_force.get("digest"):
        out.append("protocol: the passport's pre-registration is not the revision in force at the first confirmatory release")
    final = campaign.multiplicity.final
    if final is None or passport.multiplicity.get("final_context_digest") != final.digest \
            or passport.multiplicity.get("family_size") != final.family_size:
        out.append("multiplicity: the passport's search-scale record is not the campaign's final multiplicity context")
    recorded = reg.verdicts_for(hid, cd)
    conf_ids = set(d["confirmatory_evidence_ids"])
    for f in passport.falsifiers:
        mine = [v for v in recorded if v.falsifier_digest == f.get("digest")]
        got = sorted(v.verdict.value for v in mine)
        got_conf = sorted(v.verdict.value for v in mine if v.evidence_id in conf_ids)
        if got != sorted(f.get("verdicts", ())) or got_conf != sorted(f.get("confirmatory_verdicts", ())):
            out.append(f"falsifier {f.get('ref')!r}: the passport lists {sorted(f.get('verdicts', ()))} / confirmatory "
                       f"{sorted(f.get('confirmatory_verdicts', ()))}, the registry holds {got} / {got_conf}")
    if {f.get("digest") for f in passport.falsifiers} != {f.digest for f in reg.sealed_for(hid, cd)}:
        out.append("falsifiers: the passport does not list exactly the sealed falsifiers of this hypothesis")
    try:
        nov = check_novelty(hypothesis, snapshot, campaign.novelty, canonicalizer=canonicalizer, equivalence=equivalence)
        if nov.status.value != passport.hypothesis.get("novelty_status"):
            out.append(f"novelty: the passport says {passport.hypothesis.get('novelty_status')!r}, the check gives {nov.status.value!r}")
    except Exception as exc:                                             # noqa: BLE001 - an unverifiable novelty is a disagreement
        out.append(f"novelty: cannot be re-checked ({str(exc)[:120]})")
    c = passport.credibility
    from .credibility_vector import assess_credibility
    try:
        ci = dict(credibility_inputs)
        claim, graph, requirement = ci.pop("claim"), ci.pop("graph"), ci.pop("requirement")
        report = assess_credibility(claim, graph, requirement, authority=ledger, trust_anchor=trust_anchor,
                                    allow_test_profile=ledger.profile == "test", **ci)
    except Exception as exc:                                             # noqa: BLE001 - an unre-derivable credibility is a disagreement
        report = None
        out.append(f"credibility: cannot be re-derived ({str(exc)[:120]})")
    if report is not None:
        if report.claim_id != f"claim:{hid}" or report.context_digest != campaign.context_digest:
            out.append(f"credibility: the re-run claim is {report.claim_id!r} in another context, not claim:{hid} in this campaign's")
        if any(getattr(report, k) != c.get(k) for k in ("requirement_met", "issuer_bound", "test_mode")):
            out.append("credibility: the passport's credibility verdict is not what re-running the assessment gives")
        if (report.decision_id, report.risk_class.value, report.policy_digest, report.claim_structure_digest) != (
                c.get("decision_id"), c.get("risk_class"), c.get("policy_digest"), c.get("claim_structure_digest")):
            out.append("credibility: the passport does not name the decision, risk class, policy and claim structure re-assessed")
    from ..authority import verify_evidence
    from .credibility_vector import _coherent, record_digest
    from .redteam import ClaimSubject, TrustEnvelope
    if type(red_team_subject) is not ClaimSubject or red_team_subject.claim_route != hid:
        return out + [f"adversarial: no ClaimSubject made with this hypothesis (claim route {hid!r}) is given"]
    subject_dig = _subject_digest(red_team_subject)

    def admissible(r: Any, *, negative: bool) -> bool:
        if r.attestation.role is not Role.RED_TEAM or r.attestation.context_digest != campaign.context_digest:
            return False
        if r.issuer_id == campaign.issuer_id or ledger.role_at(r.issuer_id, Role.EXPOSURE, r.sequence):
            return False                                                 # the operator never red-teams its own campaign
        ok, _why = verify_evidence(ledger, record_kind="trust_envelope", record_digest=r.record_digest,
                                   subject_digest=r.attestation.subject_digest, context_digest=campaign.context_digest,
                                   roles=[Role.RED_TEAM], allow_self_issued=negative)
        return ok is not None and ok.evidence.sequence == r.sequence
    same_claim = [r for r in ledger.attestations(record_kind="trust_envelope")
                  if r.attestation.record.get("subject_digest") == subject_dig and admissible(r, negative=True)]
    hidden = sorted({str(r.attestation.record.get("outcome")) if _coherent(r.attestation.record_dict()) else "incoherent"
                     for r in same_claim} - {"survived"})
    if hidden:
        out.append(f"adversarial: another attested envelope for this claim is {hidden}: a passport never cites one survived "
                   "attack while others stand")
    env_digest = record_digest(envelope) if type(envelope) is TrustEnvelope else None
    cited = [r for r in same_claim if r.record_digest == env_digest and admissible(r, negative=False)]
    if env_digest is None or env_digest != passport.adversarial.get("envelope_digest"):
        out.append("adversarial: the envelope given is not (exactly) the one the passport summarizes")
    elif not cited:
        out.append("adversarial: the envelope is not admitted as RED_TEAM evidence about this claim in this campaign's context "
                   "(role, receipt, independence and context checked)")
    else:
        rec = cited[0].attestation.record_dict()                         # what was ATTESTED, never the object's own fields
        outcome = str(rec.get("outcome")) if _coherent(rec) else "incoherent"
        if outcome != passport.adversarial.get("outcome"):
            out.append(f"adversarial: the passport says {passport.adversarial.get('outcome')!r}, the attested envelope says {outcome!r}")
        planned = (in_force_prereg.sections.get("red_team_attack_space") if in_force_prereg is not None else None)
        if isinstance(planned, Mapping) and planned.get("plan_digest") and rec.get("plan_digest") != planned.get("plan_digest"):
            out.append("adversarial: the attested envelope ran another attack plan than the pre-registered one")
    return out


STANDARD_LIMITS = (
    "SURVIVING means not refuted by its sealed falsifiers on the released evidence; it is not truth.",
    "Route or solver agreement in the Red Team is agreement of models, not a physical measurement.",
    "Novelty is POSSIBLY_NOVEL at most, against a frozen prior-art snapshot that is not claimed exhaustive.",
    "Parameters fitted on exploratory data carry that data; they are not independent support.",
)


__all__ = ["DISCOVERY_RISK_CLASSES", "PASSPORT_SCHEMA", "STANDARD_LIMITS", "DiscoveryPassport", "verify_passport"]
