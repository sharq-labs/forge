"""A machine-readable, frozen pre-registration for a confirmatory discovery campaign.

A :class:`Preregistration` states, BEFORE any confirmatory observation is released, everything the campaign will be
judged by (:data:`REQUIRED_SECTIONS`): the question, the hypothesis set, outcomes, applicability domain, the data
(exploratory, and the confirmatory dataset's IDENTITY -- never its values), falsification criteria, uncertainty
treatment, multiplicity budget, selection rule, FidelityGraph policy, false-elimination audit rate, Red Team attack
space, independent-confirmation requirement, novelty protocol, abstention policy, stopping rule, compute / query
budget, success criteria and the negative-result rule.

It is FROZEN by an EXPOSURE-role issuer attesting it into the authority ledger (:func:`freeze`); the attestation's
ledger sequence is the time it was frozen.  A change is a NEW revision naming its parent's digest
(:meth:`Preregistration.revise`); the sealed original is never mutated, and a revision frozen after confirmatory
exposure makes the campaign exploratory (see :func:`engcore.claims.exposure_dataset.verify_discipline`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ..authority import Attestation, AttestationRecord, AuthorityLedger, Role, Signer

PREREG_SCHEMA = "engcore.claims.preregistration/1"
PREREG_KIND = "preregistration"
REQUIRED_SECTIONS = (
    "scientific_question", "hypothesis_set", "primary_outcome", "secondary_outcomes", "applicability_domain",
    "exploratory_data", "confirmatory_dataset", "falsification_criteria", "uncertainty_treatment", "multiplicity_budget",
    "selection_rule", "fidelity_graph_policy", "false_elimination_audit_rate", "red_team_attack_space",
    "independent_confirmation", "novelty_protocol", "abstention_policy", "stopping_rule", "compute_query_budget",
    "success_criteria", "negative_result_rule",
)
#: keys that would carry confirmatory TRUTH: a pre-registration names the confirmatory dataset, never its contents
FORBIDDEN_CONFIRMATORY_KEYS = frozenset({"values", "observations", "outcomes", "data", "rows", "measurements", "results", "truth",
                                         "value", "observation", "outcome", "measurement", "result", "holdout"})
MULTIPLICITY_KEYS = ("max_generated_hypotheses", "max_admitted_hypotheses", "confirmatory_query_budget")
#: the ONLY keys a confirmatory-dataset section may carry (identity and requirements, never content); values are
#: strings, null or lists of strings -- a number under it is refused
CONFIRMATORY_DATASET_KEYS = frozenset({"status", "identity", "dataset", "version", "partition", "manifest_digest", "requirements",
                                       "source", "location", "row_identity_policy"})


class PreregistrationRefused(ValueError):
    pass


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _keys_anywhere(o: Any) -> set[str]:
    if isinstance(o, Mapping):
        out = set(map(str, o))
        for v in o.values():
            out |= _keys_anywhere(v)
        return out
    if isinstance(o, (list, tuple)):
        return set().union(set(), *(_keys_anywhere(v) for v in o))
    return set()


def _empty(v: Any) -> bool:
    return v is None or isinstance(v, bool) or (isinstance(v, (str, list, tuple, dict)) and len(v) == 0) \
        or (isinstance(v, str) and not v.strip())


def _identity_only(o: Any) -> bool:
    if o is None or isinstance(o, str):
        return True
    if isinstance(o, list):
        return all(isinstance(x, str) for x in o)
    return False


@dataclass(frozen=True)
class Preregistration:
    prereg_id: str
    revision: int
    sections: Mapping[str, Any] = field(hash=False)
    parent_digest: str = ""

    def __post_init__(self) -> None:
        if not str(self.prereg_id).strip():
            raise PreregistrationRefused("a pre-registration has an id")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise PreregistrationRefused("revisions are integers from 1")
        if (self.revision > 1) != bool(self.parent_digest):
            raise PreregistrationRefused("a revision above 1 names its parent's digest, and revision 1 has none")
        secs = json.loads(json.dumps(dict(self.sections), sort_keys=True, allow_nan=False))
        missing = [k for k in REQUIRED_SECTIONS if _empty(secs.get(k))]
        if missing:
            raise PreregistrationRefused(f"a pre-registration states every required section; missing or empty: {missing}")
        unknown = sorted(set(secs) - set(REQUIRED_SECTIONS) - {"notes", "deviations_policy", "dataset_manifests"})
        if unknown:
            raise PreregistrationRefused(f"unknown sections {unknown}")
        # LEXICAL guard (it cannot read meaning): content-like keys are refused in every section, case-folded, and the
        # confirmatory-dataset section is an allowlist of identity fields with string values
        nested = set().union(set(), *(_keys_anywhere(v) for v in secs.values()))
        leaked = {k.casefold() for k in nested} & FORBIDDEN_CONFIRMATORY_KEYS
        if leaked:
            raise PreregistrationRefused(f"a pre-registration names data by identity only; it carries {sorted(leaked)}")
        cd = secs["confirmatory_dataset"]
        if not isinstance(cd, Mapping) or set(cd) - CONFIRMATORY_DATASET_KEYS or not all(_identity_only(v) for v in cd.values()):
            raise PreregistrationRefused(f"the confirmatory dataset is named by identity only: keys within "
                                         f"{sorted(CONFIRMATORY_DATASET_KEYS)}, string / null / string-list values")
        mb = secs["multiplicity_budget"]
        if not isinstance(mb, Mapping) or any(isinstance(mb.get(k), bool) or not isinstance(mb.get(k), int) or mb.get(k) < 0
                                              for k in MULTIPLICITY_KEYS):
            raise PreregistrationRefused(f"the multiplicity budget declares non-negative integers {MULTIPLICITY_KEYS}")
        rate = secs["false_elimination_audit_rate"]
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 < float(rate) <= 1:
            raise PreregistrationRefused("the false-elimination audit rate is a fraction in (0, 1]")
        if not isinstance(secs["hypothesis_set"], list) or not all(isinstance(h, Mapping) and h.get("hypothesis_id")
                                                                   and h.get("content_digest") for h in secs["hypothesis_set"]):
            raise PreregistrationRefused("the hypothesis set names each hypothesis by id AND content digest")
        ids = [h["hypothesis_id"] for h in secs["hypothesis_set"]]
        if len(set(ids)) != len(ids):
            raise PreregistrationRefused("a hypothesis is pre-registered once")
        object.__setattr__(self, "sections", MappingProxyType(secs))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PREREG_SCHEMA, "prereg_id": self.prereg_id, "revision": self.revision, "parent_digest": self.parent_digest,
                "sections": json.loads(json.dumps(dict(self.sections)))}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Preregistration:
        if payload.get("schema") != PREREG_SCHEMA:
            raise PreregistrationRefused("not a pre-registration record")
        return cls(payload["prereg_id"], payload["revision"], payload["sections"], payload.get("parent_digest", ""))

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def revise(self, **sections: Any) -> Preregistration:
        """A NEW revision (the original stays as it was sealed)."""
        return Preregistration(self.prereg_id, self.revision + 1, {**dict(self.sections), **sections}, self.digest)

    @property
    def hypothesis_ids(self) -> tuple[str, ...]:
        return tuple(h["hypothesis_id"] for h in self.sections["hypothesis_set"])

    @property
    def multiplicity_budget(self) -> Mapping[str, int]:
        return self.sections["multiplicity_budget"]


def campaign_subject(campaign_id: str) -> str:
    from .durable_campaign import campaign_subject as _cs
    return _cs(campaign_id)


def freeze(ledger: AuthorityLedger, signer: Signer, issuer_id: str, prereg: Preregistration, *, campaign_id: str,
           context_digest: str) -> AttestationRecord:
    """Freeze ``prereg`` for ``campaign_id``: an EXPOSURE-role attestation; its ledger sequence is when."""
    if not isinstance(prereg, Preregistration):
        raise PreregistrationRefused("only a Preregistration is frozen")
    again = Preregistration.from_dict(prereg.to_dict())
    prior = frozen_revisions(ledger, campaign_id, issuer_id=issuer_id, context_digest=context_digest)
    if prior and (again.revision != prior[-1][1].revision + 1 or again.parent_digest != prior[-1][1].digest):
        raise PreregistrationRefused("a frozen revision extends the campaign's latest frozen revision")
    if not prior and again.revision != 1:
        raise PreregistrationRefused("the first frozen pre-registration is revision 1")
    record = {"campaign_id": campaign_id, "preregistration": again.to_dict(), "digest": again.digest}
    return ledger.attest(signer, issuer_id, Attestation(PREREG_KIND, PREREG_SCHEMA, record, campaign_subject(campaign_id), context_digest,
                                                        Role.EXPOSURE))


def frozen_revisions(ledger: AuthorityLedger, campaign_id: str, *, issuer_id: str,
                     context_digest: str | None = None) -> tuple[tuple[int, Preregistration], ...]:
    """Every revision the campaign's EXPOSURE issuer froze, as (ledger sequence, record), re-read and chain-checked
    (revision n+1 names revision n's digest).  Records by any other issuer, in another context (when given) or signed
    inside a declared compromise window of the issuer's key are not this campaign's pre-registration."""
    out: list[tuple[int, Preregistration]] = []
    for r in ledger.attestations(record_kind=PREREG_KIND, subject_digest=campaign_subject(campaign_id)):
        if r.issuer_id != issuer_id or r.attestation.role is not Role.EXPOSURE or r.attestation.record.get("campaign_id") != campaign_id:
            continue
        if (context_digest is not None and r.attestation.context_digest != context_digest) \
                or ledger.compromised_at(r.issuer_id, r.key_id, r.sequence):
            continue
        p = Preregistration.from_dict(r.attestation.record_dict()["preregistration"])
        if p.digest != r.attestation.record.get("digest"):
            raise PreregistrationRefused(f"frozen pre-registration at {r.sequence} does not rebuild to its digest")
        if out and (p.revision != out[-1][1].revision + 1 or p.parent_digest != out[-1][1].digest):
            raise PreregistrationRefused(f"frozen pre-registration at {r.sequence} does not extend the previous revision")
        if not out and p.revision != 1:
            raise PreregistrationRefused("the first frozen pre-registration is revision 1")
        out.append((r.sequence, p))
    return tuple(out)


__all__ = ["CONFIRMATORY_DATASET_KEYS", "FORBIDDEN_CONFIRMATORY_KEYS", "MULTIPLICITY_KEYS", "PREREG_KIND", "PREREG_SCHEMA", "REQUIRED_SECTIONS", "Preregistration",
           "PreregistrationRefused", "freeze", "frozen_revisions"]
