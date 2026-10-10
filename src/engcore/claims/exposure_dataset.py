"""The dataset boundary of a confirmatory campaign: exploratory data is open, confirmatory data is RELEASED.

A :class:`DatasetManifest` records a dataset's identity -- id, version, source, per-file digests (where available),
the row/sample identity policy and the partition of row ids into ``exploratory`` and ``confirmatory`` -- and is
registered into the authority ledger by the campaign's EXPOSURE issuer.  The confirmatory rows' VALUES are not in the
manifest, not in a fixture and not in the proposer's reach: they live behind a ``rows`` provider held by the data
authority, and :class:`ExposureGate` releases them one acquisition at a time, through the durable campaign's
ExposureAuthority (so each release is on the authority clock, journaled and signed), and only when ALL hold:

* the manifest is registered and the pre-registration is FROZEN for the campaign;
* the OWNER (an OWNER-role issuer, not the campaign operator) has attested approval of exactly that pre-registration
  and manifest;
* every pre-registered hypothesis has at least one sealed falsifier, OR was declared UNTESTABLE (an EXPOSURE-signed
  abstention, with its reason, e.g. its exploratory fit is too uncertain to reach the pre-registered resolution) --
  before any confirmatory release; an untestable hypothesis is reported, never quietly dropped and never scored.

:func:`verify_discipline` re-derives, from the ledger alone, whether the campaign is still CONFIRMATORY: a
confirmatory release before freeze / approval / sealing, a pre-registration revision or a falsifier sealed after the
first confirmatory release, or a multiplicity budget exceeded each makes it EXPLORATORY, with the reason.  Calling the
campaign's ``release`` directly around the gate is therefore detected, not trusted.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ..authority import Attestation, AttestationRecord, AuthorityLedger, Role, Signer
from .durable_campaign import OP_KIND, DurableCampaign, campaign_subject
from .falsification import EvidenceItem, EvidenceSource
from .preregistration import Preregistration, frozen_revisions

MANIFEST_SCHEMA = "engcore.claims.dataset_manifest/1"
MANIFEST_KIND = "dataset_manifest"
APPROVAL_KIND = "confirmatory_approval"
APPROVAL_SCHEMA = "engcore.claims.confirmatory_approval/1"
UNTESTABLE_KIND = "untestable_declaration"
UNTESTABLE_SCHEMA = "engcore.claims.untestable_declaration/1"
PARTITIONS = ("exploratory", "confirmatory")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class ExposureRefused(ValueError):
    pass


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    version: str
    source: str
    row_identity_policy: str
    partitions: Mapping[str, tuple[str, ...]] = field(hash=False)
    files: Mapping[str, str | None] = field(hash=False, default_factory=dict)   # name -> sha256 (None: not available)

    def __post_init__(self) -> None:
        for label in ("dataset_id", "version", "source", "row_identity_policy"):
            if not str(getattr(self, label)).strip():
                raise ExposureRefused(f"a dataset manifest states its {label}")
        parts = {k: tuple(str(r) for r in v) for k, v in dict(self.partitions).items()}
        if set(parts) != set(PARTITIONS):
            raise ExposureRefused(f"a manifest partitions rows into exactly {PARTITIONS}")
        if set(parts["exploratory"]) & set(parts["confirmatory"]):
            raise ExposureRefused("a row is exploratory or confirmatory, never both")
        if any(len(set(v)) != len(v) for v in parts.values()):
            raise ExposureRefused("row ids are unique")
        for name, d in dict(self.files).items():
            if d is not None and not _HEX64.fullmatch(str(d)):
                raise ExposureRefused(f"file {name!r}: a digest is sha256 hex, or None when not available")
        object.__setattr__(self, "partitions", MappingProxyType(parts))
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MANIFEST_SCHEMA, "dataset_id": self.dataset_id, "version": self.version, "source": self.source,
                "row_identity_policy": self.row_identity_policy,
                "partitions": {k: list(v) for k, v in sorted(self.partitions.items())}, "files": dict(sorted(self.files.items()))}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def partition_of(self, row_id: str) -> str:
        for k, v in self.partitions.items():
            if row_id in v:
                return k
        raise ExposureRefused(f"row {row_id!r} is not in the dataset manifest")


def register_manifest(campaign: DurableCampaign, ledger: AuthorityLedger, signer: Signer, issuer_id: str,
                      manifest: DatasetManifest) -> AttestationRecord:
    record = {"campaign_id": campaign.campaign_id, "manifest": manifest.to_dict(), "digest": manifest.digest}
    return ledger.attest(signer, issuer_id, Attestation(MANIFEST_KIND, MANIFEST_SCHEMA, record, campaign_subject(campaign.campaign_id),
                                                        campaign.context_digest, Role.EXPOSURE))


def approve_confirmatory(ledger: AuthorityLedger, owner: Signer, owner_issuer_id: str, *, campaign_id: str, context_digest: str,
                         preregistration_digest: str, manifest_digest: str, note: str) -> AttestationRecord:
    """The OWNER's approval to release confirmatory data for exactly this pre-registration and manifest."""
    if not str(note).strip():
        raise ExposureRefused("an approval states what was approved and why")
    record = {"campaign_id": campaign_id, "preregistration_digest": preregistration_digest, "manifest_digest": manifest_digest,
              "note": str(note)}
    return ledger.attest(owner, owner_issuer_id, Attestation(APPROVAL_KIND, APPROVAL_SCHEMA, record, campaign_subject(campaign_id),
                                                             context_digest, Role.OWNER))


def declare_untestable(campaign: DurableCampaign, ledger: AuthorityLedger, signer: Signer, issuer_id: str, *, hypothesis_id: str,
                       content_digest: str, reason: str) -> AttestationRecord:
    """Abstain from testing one pre-registered hypothesis, with the reason, BEFORE any confirmatory release."""
    if not str(reason).strip():
        raise ExposureRefused("an untestable declaration states why")
    record = {"campaign_id": campaign.campaign_id, "hypothesis_id": hypothesis_id, "content_digest": content_digest, "reason": str(reason)}
    return ledger.attest(signer, issuer_id, Attestation(UNTESTABLE_KIND, UNTESTABLE_SCHEMA, record, campaign_subject(campaign.campaign_id),
                                                        campaign.context_digest, Role.EXPOSURE))


def _untestable(ledger: AuthorityLedger, campaign_id: str, issuer_id: str) -> list[AttestationRecord]:
    return [r for r in ledger.attestations(record_kind=UNTESTABLE_KIND, subject_digest=campaign_subject(campaign_id))
            if r.issuer_id == issuer_id and r.attestation.role is Role.EXPOSURE]


def _manifests(ledger: AuthorityLedger, campaign_id: str, issuer_id: str) -> list[AttestationRecord]:
    return [r for r in ledger.attestations(record_kind=MANIFEST_KIND, subject_digest=campaign_subject(campaign_id))
            if r.issuer_id == issuer_id and r.attestation.role is Role.EXPOSURE]


def _approvals(ledger: AuthorityLedger, campaign_id: str) -> list[AttestationRecord]:
    return [r for r in ledger.attestations(record_kind=APPROVAL_KIND, subject_digest=campaign_subject(campaign_id))
            if r.attestation.role is Role.OWNER and ledger.role_at(r.issuer_id, Role.OWNER, r.sequence)]


class ExposureGate:
    """Exploratory rows on request; confirmatory rows only under the conditions in the module docstring."""

    def __init__(self, campaign: DurableCampaign, ledger: AuthorityLedger, *, issuer_id: str, manifest: DatasetManifest,
                 rows: Callable[[str], Mapping[str, Any]], observable: str, unit: str) -> None:
        self._campaign, self._ledger, self._issuer = campaign, ledger, issuer_id
        self._manifest, self._rows = manifest, rows
        self._observable, self._unit = observable, unit
        if not any(r.attestation.record.get("digest") == manifest.digest for r in _manifests(ledger, campaign.campaign_id, issuer_id)):
            raise ExposureRefused("the dataset manifest is not registered for this campaign")

    def _release(self, row_id: str, partition: str) -> EvidenceItem:
        row = dict(self._rows(row_id))
        conditions = {**dict(row.get("conditions", {})), "partition": partition, "dataset": self._manifest.dataset_id,
                      "dataset_version": self._manifest.version}
        return self._campaign.release(evidence_id=f"{self._manifest.dataset_id}/{row_id}", source=EvidenceSource.MEASUREMENT_RECORD.value,
                                      observable=self._observable, unit=self._unit, value=float(row["value"]),
                                      uncertainty=None if row.get("uncertainty") is None else float(row["uncertainty"]),
                                      conditions=conditions)

    def exploratory(self, row_id: str) -> EvidenceItem:
        if self._manifest.partition_of(row_id) != "exploratory":
            raise ExposureRefused(f"row {row_id!r} is confirmatory; it is released only through the confirmatory gate")
        return self._release(row_id, "exploratory")

    def confirmatory(self, row_id: str, *, preregistration: Preregistration) -> EvidenceItem:
        if self._manifest.partition_of(row_id) != "confirmatory":
            raise ExposureRefused(f"row {row_id!r} is exploratory")
        cid = self._campaign.campaign_id
        revs = frozen_revisions(self._ledger, cid, issuer_id=self._issuer)
        if not revs or revs[-1][1].digest != preregistration.digest:
            raise ExposureRefused("the campaign's latest FROZEN pre-registration is not the one given: freeze it first")
        if not any(a.attestation.record.get("preregistration_digest") == preregistration.digest
                   and a.attestation.record.get("manifest_digest") == self._manifest.digest for a in _approvals(self._ledger, cid)):
            raise ExposureRefused("no OWNER approval of this pre-registration and manifest: confirmatory data stays sealed")
        reg = self._campaign.registry
        abstained = {(r.attestation.record["hypothesis_id"], r.attestation.record["content_digest"])
                     for r in _untestable(self._ledger, cid, self._issuer)}
        unsealed = [h for h in preregistration.sections["hypothesis_set"]
                    if not reg.sealed_for(h["hypothesis_id"], h["content_digest"])
                    and (h["hypothesis_id"], h["content_digest"]) not in abstained]
        if unsealed:
            raise ExposureRefused(f"hypotheses with neither a sealed falsifier nor an untestable declaration: "
                                  f"{[h['hypothesis_id'] for h in unsealed]}")
        return self._release(row_id, "confirmatory")


def verify_discipline(ledger: AuthorityLedger, campaign: DurableCampaign, *, issuer_id: str) -> dict[str, Any]:
    """Re-derive, from the ledger alone, whether the campaign is still CONFIRMATORY (see the module docstring)."""
    cid = campaign.campaign_id
    issues: list[str] = []
    journal = [r for r in ledger.attestations(record_kind=OP_KIND, subject_digest=campaign_subject(cid))
               if r.issuer_id == issuer_id and r.attestation.role is Role.EXPOSURE]
    conf = [r.sequence for r in journal if r.attestation.record.get("op") == "release"
            and r.attestation.record["args"]["release"].get("conditions", {}).get("partition") == "confirmatory"]
    seals = [r.sequence for r in journal if r.attestation.record.get("op") == "seal"]
    revs = frozen_revisions(ledger, cid, issuer_id=issuer_id)
    approvals = _approvals(ledger, cid)
    first = min(conf) if conf else None
    if first is not None:
        if not revs or revs[0][0] > first:
            issues.append("confirmatory data was released before any pre-registration was frozen")
        if not any(a.sequence < first for a in approvals):
            issues.append("confirmatory data was released before the owner's approval")
        if not seals or min(seals) > first:
            issues.append("confirmatory data was released before any falsifier was sealed")
        late_revs = [s for s, _p in revs if s > first]
        if late_revs:
            issues.append(f"the pre-registration was revised after confirmatory exposure (ledger {late_revs})")
        late_abstentions = [r.sequence for r in _untestable(ledger, cid, issuer_id) if r.sequence > first]
        if late_abstentions:
            issues.append(f"hypotheses were declared untestable after confirmatory exposure (ledger {late_abstentions})")
        late_seals = [s for s in seals if s > first]
        if late_seals:
            issues.append(f"falsifiers were sealed after confirmatory exposure (ledger {late_seals}): those test nothing confirmatory")
    if revs:
        budget = revs[-1][1].multiplicity_budget
        counts = campaign.multiplicity._counts
        if counts["generated"] > budget["max_generated_hypotheses"]:
            issues.append(f"generated {counts['generated']} > pre-registered max {budget['max_generated_hypotheses']}")
        if counts["admitted"] > budget["max_admitted_hypotheses"]:
            issues.append(f"admitted {counts['admitted']} > pre-registered max {budget['max_admitted_hypotheses']}")
        if len(conf) > budget["confirmatory_query_budget"]:
            issues.append(f"{len(conf)} confirmatory releases > pre-registered budget {budget['confirmatory_query_budget']}")
    return {"status": "CONFIRMATORY" if not issues else "EXPLORATORY", "issues": issues,
            "confirmatory_releases": len(conf), "first_confirmatory_sequence": first,
            "preregistration_revisions": [{"sequence": s, "revision": p.revision, "digest": p.digest} for s, p in revs],
            "approvals": [a.sequence for a in approvals],
            "untestable": [{"hypothesis_id": r.attestation.record["hypothesis_id"], "reason": r.attestation.record["reason"],
                            "sequence": r.sequence} for r in _untestable(ledger, cid, issuer_id)]}


__all__ = ["APPROVAL_KIND", "MANIFEST_KIND", "PARTITIONS", "UNTESTABLE_KIND", "DatasetManifest", "ExposureGate", "ExposureRefused",
           "approve_confirmatory", "declare_untestable", "register_manifest", "verify_discipline"]
