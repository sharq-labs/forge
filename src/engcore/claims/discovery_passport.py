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

``verdict_limits`` always states what the passport does NOT show (a SURVIVING status is not truth; solver or route
agreement is not physical validation; a synthetic or exploratory run is not a discovery).  ``counts_as_discovery`` is
True only for a CONFIRMATORY, SURVIVING, POSSIBLY_NOVEL hypothesis whose credibility requirement is met issuer-bound and
whose Red Team envelope SURVIVED -- and never for a dry run.
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
        if not self.verdict_limits:
            raise ValueError("a passport states the limits of what it shows")

    @property
    def counts_as_discovery(self) -> bool:
        return (self.run_kind == "confirmatory" and self.protocol.get("discipline") == "CONFIRMATORY"
                and self.hypothesis.get("status") == "surviving" and self.hypothesis.get("novelty_status") == "possibly_novel"
                and self.credibility.get("requirement_met") is True and self.credibility.get("issuer_bound") is True
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


STANDARD_LIMITS = (
    "SURVIVING means not refuted by its sealed falsifiers on the released evidence; it is not truth.",
    "Route or solver agreement in the Red Team is agreement of models, not a physical measurement.",
    "Novelty is POSSIBLY_NOVEL at most, against a frozen prior-art snapshot that is not claimed exhaustive.",
    "Parameters fitted on exploratory data carry that data; they are not independent support.",
)


__all__ = ["PASSPORT_SCHEMA", "STANDARD_LIMITS", "DiscoveryPassport"]
