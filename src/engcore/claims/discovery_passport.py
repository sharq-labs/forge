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
least one sealed falsifier, EVERY falsifier judged on at least one CONFIRMATORY row with no confirmatory REFUTED (and
no REFUTED anywhere), a credibility requirement met issuer-bound outside test mode, a PRODUCTION-profile authority
anchor and a SURVIVED Red Team envelope -- never for a dry run.  Exploratory verdicts never make a discovery.

:func:`verify_passport` re-derives every one of those from the records themselves -- the campaign's own ledger held to
the operator's TrustAnchor, the discipline, the hypothesis status (``verify_status``), every falsifier's verdicts and
confirmatory verdicts, the novelty check (re-run against the sealed snapshot), the credibility report and the Red Team
envelope (attested in the ledger by a RED_TEAM issuer) -- and lists every disagreement.  A passport is read as a
discovery only when ``counts_as_discovery`` holds AND that list is empty.  Residual (stated): the credibility report is
checked for consistency with the passport and the ledger, not re-run (re-run :func:`assess_credibility` on the graph).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

PASSPORT_SCHEMA = "engcore.claims.discovery_passport/1"


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
                and any("not_refuted" in c for c in confirmatory) and "refuted" not in verdicts
                and self.credibility.get("requirement_met") is True and self.credibility.get("issuer_bound") is True
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


def verify_passport(passport: DiscoveryPassport, campaign: Any, *, trust_anchor: Any, hypothesis: Any, credibility: Any,
                    envelope: Any, snapshot: Any, canonicalizer: Any, equivalence: Any = None) -> list[str]:
    """Every way the passport disagrees with the records it summarizes (empty: it says what they say).  ``campaign`` is
    the durable campaign resumed from the operator's ledger; ``trust_anchor`` the OPERATOR's anchor (configuration, never
    the passport's own); the remaining arguments are the records themselves."""
    from ..authority import AuthorityLedger, Role, TrustAnchor
    from .credibility_vector import record_digest
    from .exposure_dataset import verify_discipline
    from .falsification import verify_status
    from .novelty import check_novelty
    out: list[str] = []
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
    if (getattr(hypothesis, "hypothesis_id", None), getattr(hypothesis, "content_digest", None)) != (hid, cd):
        return out + ["hypothesis: the record given is not the hypothesis the passport names"]
    reg = campaign.registry
    if hypothesis.status.value != passport.hypothesis.get("status"):
        out.append(f"status: the passport says {passport.hypothesis.get('status')!r}, the hypothesis is {hypothesis.status.value!r}")
    out.extend(f"status: {p}" for p in verify_status(hypothesis, reg, anchor=reg.anchor))
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
    if getattr(credibility, "digest", None) != c.get("report_digest") or any(
            getattr(credibility, k, None) != c.get(k) for k in ("requirement_met", "issuer_bound", "test_mode")):
        out.append("credibility: the report given is not the one the passport summarizes")
    elif credibility.authority_profile != ledger.profile or credibility.authority_anchor is None \
            or not ledger.extends(TrustAnchor.from_dict(dict(credibility.authority_anchor))):
        out.append("credibility: the report was not assessed against this campaign's ledger")
    env_digest = record_digest(envelope)
    if env_digest != passport.adversarial.get("envelope_digest") or envelope.outcome.value != passport.adversarial.get("outcome"):
        out.append("adversarial: the envelope given is not the one the passport summarizes")
    elif not any(r.attestation.role is Role.RED_TEAM and ledger.role_at(r.issuer_id, Role.RED_TEAM, r.sequence)
                 and not ledger.compromised_at(r.issuer_id, r.key_id, r.sequence)
                 for r in ledger.attestations(record_kind="trust_envelope", record_digest=env_digest)):
        out.append("adversarial: the envelope is not attested in the ledger by a RED_TEAM issuer")
    return out


STANDARD_LIMITS = (
    "SURVIVING means not refuted by its sealed falsifiers on the released evidence; it is not truth.",
    "Route or solver agreement in the Red Team is agreement of models, not a physical measurement.",
    "Novelty is POSSIBLY_NOVEL at most, against a frozen prior-art snapshot that is not claimed exhaustive.",
    "Parameters fitted on exploratory data carry that data; they are not independent support.",
)


__all__ = ["PASSPORT_SCHEMA", "STANDARD_LIMITS", "DiscoveryPassport", "verify_passport"]
