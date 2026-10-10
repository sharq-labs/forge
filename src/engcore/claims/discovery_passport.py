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
least one sealed falsifier, every falsifier judged, at least one NOT_REFUTED and no REFUTED verdict, a credibility
requirement met issuer-bound outside test mode, a PRODUCTION-profile authority anchor and a SURVIVED Red Team envelope
-- never for a dry run.  :func:`verify_passport` re-derives the discipline, the anchor and the verdicts from the
ledger and the campaign registry and lists every disagreement; a passport is read as a discovery only when that list
is empty.
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
        return (self.run_kind == "confirmatory" and self.protocol.get("discipline") == "CONFIRMATORY"
                and self.protocol.get("discipline_issues") == []
                and self.hypothesis.get("status") == "surviving" and self.hypothesis.get("novelty_status") == "possibly_novel"
                and bool(self.falsifiers) and all(f.get("verdicts") for f in self.falsifiers)
                and "not_refuted" in verdicts and "refuted" not in verdicts
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


def verify_passport(passport: DiscoveryPassport, ledger: Any, campaign: Any) -> list[str]:
    """Every way the passport's fields disagree with the ledger and the campaign: discipline (re-derived), authority
    anchor (the ledger must extend it), and each listed falsifier's verdicts (from the campaign registry)."""
    from ..authority import TrustAnchor
    from .exposure_dataset import verify_discipline
    out: list[str] = []
    d = verify_discipline(ledger, campaign)
    if passport.protocol.get("discipline") != d["status"] or list(passport.protocol.get("discipline_issues", [])) != d["issues"]:
        out.append(f"discipline: the passport says {passport.protocol.get('discipline')!r}, the ledger says {d['status']!r}")
    try:
        if not ledger.extends(TrustAnchor.from_dict(dict(passport.authority_anchor))):
            out.append("authority anchor: the ledger does not extend the anchor the passport names")
    except Exception as exc:                                             # noqa: BLE001 - an unreadable anchor verifies nothing
        out.append(f"authority anchor: unreadable ({str(exc)[:80]})")
    hid, cd = passport.hypothesis.get("hypothesis_id"), passport.hypothesis.get("content_digest")
    recorded = campaign.registry.verdicts_for(hid, cd)
    for f in passport.falsifiers:
        got = sorted(v.to_dict()["verdict"] for v in recorded if v.falsifier_digest == f.get("digest"))
        if got != sorted(f.get("verdicts", ())):
            out.append(f"falsifier {f.get('ref')!r}: the passport lists {sorted(f.get('verdicts', ()))}, the registry holds {got}")
    sealed = {f.digest for f in campaign.registry.sealed_for(hid, cd)}
    if {f.get("digest") for f in passport.falsifiers} != sealed:
        out.append("falsifiers: the passport does not list exactly the sealed falsifiers of this hypothesis")
    return out


STANDARD_LIMITS = (
    "SURVIVING means not refuted by its sealed falsifiers on the released evidence; it is not truth.",
    "Route or solver agreement in the Red Team is agreement of models, not a physical measurement.",
    "Novelty is POSSIBLY_NOVEL at most, against a frozen prior-art snapshot that is not claimed exhaustive.",
    "Parameters fitted on exploratory data carry that data; they are not independent support.",
)


__all__ = ["PASSPORT_SCHEMA", "STANDARD_LIMITS", "DiscoveryPassport", "verify_passport"]
