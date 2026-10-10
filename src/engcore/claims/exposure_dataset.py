"""The dataset boundary of a confirmatory campaign: exploratory data is open, confirmatory data is RELEASED.

A :class:`DatasetManifest` records a dataset's identity -- id, version, source, per-file digests (where available),
the row/sample identity policy, the partition of row ids into ``exploratory`` and ``confirmatory``, a salted
COMMITMENT per row (:func:`commit_row`: the row's value, uncertainty and conditions under a salt the data authority
keeps) and the public design CONDITIONS of rows (where a row will be measured -- never what was measured).  It is
registered into the authority ledger by the campaign's owner (its EXPOSURE issuer); a later manifest may not move a
registered row to the other partition.  The confirmatory rows' VALUES are not in the manifest, not in a fixture and
not in the proposer's reach: they live behind a ``rows`` provider held by the data authority, and
:class:`ExposureGate` releases them one acquisition at a time, through the durable campaign's ExposureAuthority (so
each release is on the authority clock, journaled and signed), each one checked against its row commitment, and only
when ALL hold:

* the manifest is registered and the pre-registration is FROZEN for the campaign;
* an OWNER has attested approval of exactly that pre-registration and manifest, in the campaign's context; the owner
  is not the campaign's issuer, holds no EXPOSURE role, and is not revoked when the data is released;
* every pre-registered hypothesis has at least one sealed falsifier, OR was declared UNTESTABLE
  (:func:`declare_untestable`: an EXPOSURE-signed abstention with its reason and the inputs of the pre-registered
  resolution rule, refused when the rule would in fact reach a resolution or a falsifier is already sealed) -- before
  any confirmatory release; an untestable hypothesis is reported, never quietly dropped and never scored.

:func:`verify_discipline` re-derives, from the LEDGER and the registered manifests (never from labels a caller wrote
on a release), whether the campaign is CONFIRMATORY.  It classifies every journaled release by its manifest row, then
re-checks the gate's conditions at the first confirmatory release (the revision in force, its approval, every
pre-registered hypothesis covered), the sealed falsifiers against the pre-registered criteria, every untestable
declaration against the rule, late revisions / seals / abstentions, and the multiplicity budget from the journal.
Its status is ``CONFIRMATORY`` only when a frozen protocol exists, at least one confirmatory row was released and no
issue was found; ``NOT_FROZEN`` / ``NO_CONFIRMATORY_RELEASE`` say that nothing confirmatory happened (never a pass);
any issue makes it ``EXPLORATORY``, with the reasons.

Residuals (stated): the data authority's ``rows`` provider is trusted to hold the salts (a commitment binds the row,
it does not prove the measurement); inside one process the wrapped objects are reachable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ..authority import (
    Attestation,
    AttestationRecord,
    AuthorityLedger,
    Role,
    Signer,
    receipt_outputs,
    verify_receipt,
)
from .durable_campaign import OP_KIND, DurableCampaign, campaign_subject
from .falsification import EvidenceItem, EvidenceSource
from .preregistration import (
    FORBIDDEN_CONFIRMATORY_KEYS,
    Preregistration,
    frozen_revisions,
)

MANIFEST_SCHEMA = "engcore.claims.dataset_manifest/2"
MANIFEST_KIND = "dataset_manifest"
APPROVAL_KIND = "confirmatory_approval"
APPROVAL_SCHEMA = "engcore.claims.confirmatory_approval/1"
UNTESTABLE_KIND = "untestable_declaration"
UNTESTABLE_SCHEMA = "engcore.claims.untestable_declaration/2"
PARTITIONS = ("exploratory", "confirmatory")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_GATE_LABELS = ("partition", "dataset", "dataset_version")      # what the gate adds to a row's own conditions


class ExposureRefused(ValueError):
    pass


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def row_key(dataset_id: str, row_id: str, salt: bytes) -> bytes:
    """The per-ROW commitment key derived from the data authority's salt.  A release opens its commitment with this key
    only: the salt itself is never journaled, so a salt shared across rows cannot open (or brute-force) another row."""
    if not isinstance(salt, (bytes, bytearray)) or len(salt) < 16:
        raise ExposureRefused("a row commitment is salted with at least 16 random bytes")
    return hmac.new(bytes(salt), f"forge.dataset.row-key/1\n{dataset_id}\n{row_id}".encode(), hashlib.sha256).digest()


def _commit_with_key(dataset_id: str, row_id: str, row: Mapping[str, Any], key: bytes) -> str:
    norm = {"value": None if row.get("value") is None else float(row["value"]),
            "uncertainty": None if row.get("uncertainty") is None else float(row["uncertainty"]),
            "conditions": dict(row.get("conditions") or {})}
    body = json.dumps(norm, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
    return hmac.new(key, f"forge.dataset.row/2\n{dataset_id}\n{row_id}\n{body}".encode(), hashlib.sha256).hexdigest()


def commit_row(dataset_id: str, row_id: str, row: Mapping[str, Any], salt: bytes) -> str:
    """The salted commitment to one row (value, uncertainty, conditions), under its per-row key (:func:`row_key`).  The
    salt stays with the data authority: a low-entropy value under a plain hash could be brute-forced from the manifest."""
    return _commit_with_key(dataset_id, row_id, row, row_key(dataset_id, row_id, salt))


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    version: str
    source: str
    row_identity_policy: str
    partitions: Mapping[str, tuple[str, ...]] = field(hash=False)
    files: Mapping[str, str | None] = field(hash=False, default_factory=dict)   # name -> sha256 (None: not available)
    row_commitments: Mapping[str, str] = field(hash=False, default_factory=dict)  # row id -> commit_row(...)
    conditions: Mapping[str, Mapping[str, Any]] = field(hash=False, default_factory=dict)   # row id -> design conditions

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
        rows = set(parts["exploratory"]) | set(parts["confirmatory"])
        if "/" in str(self.dataset_id) or any("/" in r for r in rows):
            raise ExposureRefused("dataset and row ids contain no '/': the evidence id 'dataset/row' must be unambiguous")
        for name, d in dict(self.files).items():
            if d is not None and not _HEX64.fullmatch(str(d)):
                raise ExposureRefused(f"file {name!r}: a digest is sha256 hex, or None when not available")
        commits = {str(k): str(v) for k, v in dict(self.row_commitments).items()}
        if set(commits) - rows or not all(_HEX64.fullmatch(v) for v in commits.values()):
            raise ExposureRefused("row commitments are sha256 hex, for rows of this manifest")
        conds = json.loads(json.dumps({str(k): dict(v) for k, v in dict(self.conditions).items()}, sort_keys=True, allow_nan=False))
        if set(conds) - rows:
            raise ExposureRefused("design conditions are stated for rows of this manifest")
        leaked = {k.casefold() for c in conds.values() for k in c} & (FORBIDDEN_CONFIRMATORY_KEYS | {"value", "uncertainty"})
        if leaked:
            raise ExposureRefused(f"design conditions say where a row is measured, never what was measured: {sorted(leaked)}")
        object.__setattr__(self, "partitions", MappingProxyType(parts))
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))
        object.__setattr__(self, "row_commitments", MappingProxyType(commits))
        object.__setattr__(self, "conditions", MappingProxyType({k: MappingProxyType(v) for k, v in conds.items()}))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MANIFEST_SCHEMA, "dataset_id": self.dataset_id, "version": self.version, "source": self.source,
                "row_identity_policy": self.row_identity_policy,
                "partitions": {k: list(v) for k, v in sorted(self.partitions.items())}, "files": dict(sorted(self.files.items())),
                "row_commitments": dict(sorted(self.row_commitments.items())),
                "conditions": {k: dict(v) for k, v in sorted(self.conditions.items())}}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DatasetManifest:
        if d.get("schema") != MANIFEST_SCHEMA:
            raise ExposureRefused("not a dataset manifest record")
        return cls(d["dataset_id"], d["version"], d["source"], d["row_identity_policy"], d["partitions"], d.get("files", {}),
                   d.get("row_commitments", {}), d.get("conditions", {}))

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def partition_of(self, row_id: str) -> str:
        for k, v in self.partitions.items():
            if row_id in v:
                return k
        raise ExposureRefused(f"row {row_id!r} is not in the dataset manifest")

    def evidence_id(self, row_id: str) -> str:
        return f"{self.dataset_id}/{row_id}"


def _owner(campaign: DurableCampaign, issuer_id: str | None) -> str:
    if issuer_id is not None and issuer_id != campaign.issuer_id:
        raise ExposureRefused(f"campaign {campaign.campaign_id!r} is owned by {campaign.issuer_id!r}, not {issuer_id!r}")
    return campaign.issuer_id


def _bound(campaign: DurableCampaign, ledger: AuthorityLedger | None) -> AuthorityLedger:
    """Every gate and verifier reads the ONE ledger the campaign is journaled in; another ledger reusing the same issuer
    id strings is never consulted."""
    if ledger is not None and ledger is not campaign.ledger:
        raise ExposureRefused("this is not the campaign's own authority ledger: records are read only from the ledger the "
                              "campaign is journaled in")
    return campaign.ledger


def _trusted(ledger: AuthorityLedger, r: AttestationRecord) -> bool:
    """Not signed inside a root-declared compromise window of its key."""
    return not ledger.compromised_at(r.issuer_id, r.key_id, r.sequence)


def _manifests(ledger: AuthorityLedger, campaign: DurableCampaign) -> list[tuple[AttestationRecord, DatasetManifest]]:
    out = []
    for r in ledger.attestations(record_kind=MANIFEST_KIND, subject_digest=campaign_subject(campaign.campaign_id)):
        if r.issuer_id != campaign.issuer_id or r.attestation.role is not Role.EXPOSURE \
                or r.attestation.context_digest != campaign.context_digest or not _trusted(ledger, r):
            continue
        m = DatasetManifest.from_dict(r.attestation.record_dict()["manifest"])
        if m.digest != r.attestation.record.get("digest"):
            raise ExposureRefused(f"registered manifest at {r.sequence} does not rebuild to its digest")
        out.append((r, m))
    return out


def _row_partitions(manifests: list[tuple[AttestationRecord | None, DatasetManifest]]) -> tuple[dict[str, tuple[str, int]], list[str]]:
    """evidence id -> (partition, first registration sequence); conflicts are listed, never resolved quietly."""
    rows: dict[str, tuple[str, int]] = {}
    commitments: dict[str, str] = {}
    conflicts: list[str] = []
    for r, m in manifests:
        seq = r.sequence if r is not None else 1 << 62
        for part, ids in m.partitions.items():
            for rid in ids:
                eid = m.evidence_id(rid)
                if eid in rows and rows[eid][0] != part:
                    conflicts.append(f"row {eid!r} is {rows[eid][0]} in one registered manifest and {part} in another")
                rows.setdefault(eid, (part, seq))
                c = m.row_commitments.get(rid)
                if c is not None and commitments.setdefault(eid, c) != c:
                    conflicts.append(f"row {eid!r} carries another commitment in a later manifest: a commitment is never replaced")
    return rows, conflicts


def register_manifest(campaign: DurableCampaign, ledger: AuthorityLedger, signer: Signer, issuer_id: str,
                      manifest: DatasetManifest) -> AttestationRecord:
    _owner(campaign, issuer_id)
    ledger = _bound(campaign, ledger)
    _rows, conflicts = _row_partitions([*_manifests(ledger, campaign), (None, manifest)])
    if conflicts:
        raise ExposureRefused(f"a manifest never moves a registered row or replaces its commitment: {conflicts[0]}")
    record = {"campaign_id": campaign.campaign_id, "manifest": manifest.to_dict(), "digest": manifest.digest}
    return ledger.attest(signer, issuer_id, Attestation(MANIFEST_KIND, MANIFEST_SCHEMA, record, campaign_subject(campaign.campaign_id),
                                                        campaign.context_digest, Role.EXPOSURE))


def approve_confirmatory(ledger: AuthorityLedger, owner: Signer, owner_issuer_id: str, *, campaign_id: str, context_digest: str,
                         preregistration_digest: str, manifest_digest: str, note: str) -> AttestationRecord:
    """The OWNER's approval to release confirmatory data for exactly this pre-registration and manifest."""
    if not str(note).strip():
        raise ExposureRefused("an approval states what was approved and why")
    if ledger.role_at(owner_issuer_id, Role.EXPOSURE, ledger.length):
        raise ExposureRefused("the approver holds an EXPOSURE role: a campaign operator never approves its own release")
    record = {"campaign_id": campaign_id, "preregistration_digest": preregistration_digest, "manifest_digest": manifest_digest,
              "note": str(note)}
    return ledger.attest(owner, owner_issuer_id, Attestation(APPROVAL_KIND, APPROVAL_SCHEMA, record, campaign_subject(campaign_id),
                                                             context_digest, Role.OWNER))


def _approvals(ledger: AuthorityLedger, campaign: DurableCampaign, *, at: int) -> list[AttestationRecord]:
    """Approvals that count at ledger sequence ``at``: OWNER-role, not the campaign's issuer, no EXPOSURE role when it
    approved nor at ``at``, still an unrevoked OWNER at ``at``, in the campaign's context, not signed in a compromise
    window."""
    return [r for r in ledger.attestations(record_kind=APPROVAL_KIND, subject_digest=campaign_subject(campaign.campaign_id))
            if r.attestation.role is Role.OWNER and r.issuer_id != campaign.issuer_id
            and r.attestation.context_digest == campaign.context_digest and r.attestation.record.get("campaign_id") == campaign.campaign_id
            and ledger.role_at(r.issuer_id, Role.OWNER, r.sequence) and ledger.role_at(r.issuer_id, Role.OWNER, at)
            and not ledger.role_at(r.issuer_id, Role.EXPOSURE, r.sequence) and not ledger.role_at(r.issuer_id, Role.EXPOSURE, at)
            and _trusted(ledger, r)]


def _revisions(ledger: AuthorityLedger, campaign: DurableCampaign) -> tuple[tuple[int, Preregistration], ...]:
    return frozen_revisions(ledger, campaign.campaign_id, issuer_id=campaign.issuer_id, context_digest=campaign.context_digest)


# ---------------------------------------------------------------------------- the pre-registered resolution rule


def structured_rule(prereg: Preregistration) -> Mapping[str, Any] | None:
    """The machine-readable falsification rule, when the pre-registration states one:
    ``{"criterion", "k", "resolution": {"relative_cap", "uncertainty_multiplier", "absolute_floor"},
    "declared_observation_uncertainty": number | null}``."""
    fc = prereg.sections.get("falsification_criteria")
    if not isinstance(fc, Mapping) or not isinstance(fc.get("resolution"), Mapping):
        return None
    res = fc["resolution"]
    if not all(isinstance(res.get(k), (int, float)) and not isinstance(res.get(k), bool)
               for k in ("relative_cap", "uncertainty_multiplier", "absolute_floor")) or not isinstance(fc.get("k"), (int, float)):
        return None
    return fc


def _declared_u_obs(rule: Mapping[str, Any]) -> float | None:
    u = rule.get("declared_observation_uncertainty")
    return None if isinstance(u, bool) or not isinstance(u, (int, float)) or u <= 0 else float(u)


def rule_resolution(rule: Mapping[str, Any], *, predicted: float, prediction_uncertainty: float,
                    observation_uncertainty: float) -> tuple[float, float]:
    """(resolution, k * combined uncertainty) under the pre-registered rule; testable iff resolution >= the second."""
    res, k = rule["resolution"], float(rule["k"])
    combined = math.sqrt(float(prediction_uncertainty) ** 2 + float(observation_uncertainty) ** 2)
    resolution = min(float(res["relative_cap"]) * abs(float(predicted)),
                     max(float(res["uncertainty_multiplier"]) * k * combined, float(res["absolute_floor"])))
    return resolution, k * combined


def _rule_fails_everywhere(rule: Mapping[str, Any], inputs: Any) -> tuple[bool, str]:
    if not isinstance(inputs, (list, tuple)) or not inputs:
        return False, "it carries no inputs of the pre-registered rule"
    declared = _declared_u_obs(rule)
    if declared is None:
        return False, "the pre-registered rule declares no observation uncertainty: no abstention can be checked against it"
    for n, x in enumerate(inputs):
        try:
            if float(x["observation_uncertainty"]) != declared:
                return False, f"rule input {n} uses an observation uncertainty other than the pre-registered {declared}"
            resolution, ku = rule_resolution(rule, predicted=x["predicted"], prediction_uncertainty=x["prediction_uncertainty"],
                                             observation_uncertainty=x["observation_uncertainty"])
        except (KeyError, TypeError, ValueError):
            return False, f"rule input {n} is malformed"
        if resolution >= ku:
            return False, f"the pre-registered rule REACHES a resolution at input {n} ({resolution:.4g} >= {ku:.4g})"
    return True, ""


def _seal_departs(rule: Mapping[str, Any], f: Mapping[str, Any]) -> str:
    """Why a sealed falsifier departs from the pre-registered rule ('' when it does not)."""
    if f.get("criterion") != rule.get("criterion"):
        return "criterion"
    params = f.get("parameters", {})
    if float(params.get("k", -1)) != float(rule["k"]):
        return "k"
    if f.get("criterion") != "prediction_deviation":
        return ""
    declared = _declared_u_obs(rule)
    if declared is None:
        return "the pre-registered rule declares no observation uncertainty, so no resolution can be checked"
    if "prediction_uncertainty" not in params:
        return "no prediction uncertainty"
    expected, ku = rule_resolution(rule, predicted=params["predicted"], prediction_uncertainty=params["prediction_uncertainty"],
                                   observation_uncertainty=declared)
    if abs(float(params["resolution"]) - expected) > 1e-9 * max(1.0, abs(expected)):
        return f"resolution {params['resolution']} is not the rule's {expected:.6g}"
    if not expected >= ku:
        return "the rule reaches no resolution here: it should have been declared untestable"
    return ""


def rule_inputs_digest(inputs: Any, *, hypothesis_id: str, content_digest: str, falsifier_ref: str | None) -> str:
    """The digest an attested fit receipt outputs (as ``rule_inputs``) for an abstention: bound to the hypothesis (id and
    content) and the planned falsifier it abstains from, so one fit cannot be cited for another hypothesis."""
    return _digest({"hypothesis_id": hypothesis_id, "content_digest": content_digest, "falsifier_ref": falsifier_ref,
                    "rule_inputs": [dict(x) for x in inputs]})


def falsifier_fit_digest(falsifier: Any) -> str:
    """The digest an attested fit receipt outputs (as ``falsifier_prediction``) for a sealed falsifier: hypothesis,
    falsifier id, conditions, predicted value and prediction uncertainty -- the numbers the rule sizes the test with."""
    d = falsifier if isinstance(falsifier, Mapping) else falsifier.to_dict()
    p = dict(d.get("parameters", {}))
    return _digest({"hypothesis_id": d.get("hypothesis_id"), "content_digest": d.get("hypothesis_content_digest"),
                    "falsifier_id": d.get("falsifier_id"), "test_conditions": dict(d.get("test_conditions", {})),
                    "predicted": p.get("predicted"), "prediction_uncertainty": p.get("prediction_uncertainty")})


def _fit_receipt_ok(ledger: AuthorityLedger, campaign: DurableCampaign, receipt_digest: Any, output: str, expected: str,
                    before: int) -> str:
    """The numbers come from an EXECUTOR-attested fit (another issuer than the campaign operator, attested BEFORE the
    record that cites it), not from the operator's say-so."""
    if not isinstance(receipt_digest, str) or not receipt_digest:
        return f"it names no attested fit receipt for its {output}"
    rec, why = verify_receipt(ledger, receipt_digest, context_digest=campaign.context_digest)
    if rec is None:
        return "; ".join(why)
    if rec.issuer_id == campaign.issuer_id or not _trusted(ledger, rec):
        return "the fit receipt is the campaign operator's own, or was signed inside a compromise window"
    if rec.sequence >= before:
        return "the fit receipt was attested after the record citing it"
    if receipt_outputs(rec).get(output) != expected:
        return f"the attested fit receipt does not output this {output}"
    return ""


def declare_untestable(campaign: DurableCampaign, ledger: AuthorityLedger, signer: Signer, issuer_id: str, *, hypothesis_id: str,
                       content_digest: str, reason: str, rule_inputs: tuple[Mapping[str, float], ...] = (),
                       falsifier_ref: str | None = None, fit_receipt: AttestationRecord | None = None) -> AttestationRecord:
    """Abstain, with the reason, from testing one pre-registered hypothesis (``falsifier_ref=None``) or one of its planned
    falsifiers -- BEFORE any confirmatory release.  Refused for a hypothesis outside the latest frozen pre-registration,
    for one that already has a sealed falsifier (or that planned falsifier sealed), and -- when the pre-registration
    states a machine-readable rule -- unless ``rule_inputs`` (using the pre-registered observation uncertainty) show the
    rule fails at every condition AND come from ``fit_receipt``: an EXECUTOR-attested receipt (another issuer than the
    campaign operator) whose output ``rule_inputs`` is their digest."""
    _owner(campaign, issuer_id)
    ledger = _bound(campaign, ledger)
    if not str(reason).strip():
        raise ExposureRefused("an untestable declaration states why")
    revs = _revisions(ledger, campaign)
    if not revs:
        raise ExposureRefused("an abstention is declared against a FROZEN pre-registration")
    prereg = revs[-1][1]
    if (hypothesis_id, content_digest) not in {(h["hypothesis_id"], h["content_digest"]) for h in prereg.sections["hypothesis_set"]}:
        raise ExposureRefused(f"{hypothesis_id!r} (this content) is not a pre-registered hypothesis")
    sealed = campaign.registry.sealed_for(hypothesis_id, content_digest)
    if falsifier_ref is None and sealed:
        raise ExposureRefused(f"{hypothesis_id!r} already has sealed falsifiers: it is tested, not abstained from")
    if falsifier_ref is not None and any(f.ref == falsifier_ref for f in sealed):
        raise ExposureRefused(f"{falsifier_ref!r} is sealed: it is tested, not abstained from")
    rule = structured_rule(prereg)
    inputs = [dict(x) for x in rule_inputs]
    receipt_digest = fit_receipt.record_digest if fit_receipt is not None else ""
    if rule is not None:
        ok, why = _rule_fails_everywhere(rule, inputs)
        if not ok:
            raise ExposureRefused(f"untestable is not a choice: {why}")
        bad = _fit_receipt_ok(ledger, campaign, receipt_digest, "rule_inputs", rule_inputs_digest(
            inputs, hypothesis_id=hypothesis_id, content_digest=content_digest, falsifier_ref=falsifier_ref), ledger.length)
        if bad:
            raise ExposureRefused(f"untestable is not a choice: {bad}")
    record = {"campaign_id": campaign.campaign_id, "hypothesis_id": hypothesis_id, "content_digest": content_digest, "reason": str(reason),
              "falsifier_ref": falsifier_ref, "rule_inputs": inputs, "fit_receipt": receipt_digest, "preregistration_digest": prereg.digest}
    return ledger.attest(signer, issuer_id, Attestation(UNTESTABLE_KIND, UNTESTABLE_SCHEMA, record, campaign_subject(campaign.campaign_id),
                                                        campaign.context_digest, Role.EXPOSURE))


def _untestable(ledger: AuthorityLedger, campaign: DurableCampaign) -> list[AttestationRecord]:
    return [r for r in ledger.attestations(record_kind=UNTESTABLE_KIND, subject_digest=campaign_subject(campaign.campaign_id))
            if r.issuer_id == campaign.issuer_id and r.attestation.role is Role.EXPOSURE
            and r.attestation.context_digest == campaign.context_digest and _trusted(ledger, r)]


def _whole(r: AttestationRecord) -> bool:
    return r.attestation.record.get("falsifier_ref") is None


class ExposureGate:
    """Exploratory rows on request; confirmatory rows only under the conditions in the module docstring."""

    def __init__(self, campaign: DurableCampaign, ledger: AuthorityLedger | None = None, *, manifest: DatasetManifest,
                 rows: Callable[[str], Mapping[str, Any]], observable: str, unit: str, issuer_id: str | None = None) -> None:
        _owner(campaign, issuer_id)
        self._campaign, self._ledger = campaign, _bound(campaign, ledger)
        self._manifest, self._rows = manifest, rows
        self._observable, self._unit = observable, unit
        if not any(m.digest == manifest.digest for _r, m in _manifests(self._ledger, campaign)):
            raise ExposureRefused("the dataset manifest is not registered for this campaign")

    def _release(self, row_id: str, partition: str) -> EvidenceItem:
        row = dict(self._rows(row_id))
        commitment = self._manifest.row_commitments.get(row_id)
        if commitment is None and partition == "confirmatory":
            raise ExposureRefused(f"confirmatory row {row_id!r} has no commitment in the manifest: it cannot be checked at release")
        if any(k in dict(row.get("conditions", {})) for k in _GATE_LABELS):
            raise ExposureRefused(f"row {row_id!r} carries a gate label in its own conditions")
        opening = None
        if commitment is not None:
            try:
                got = commit_row(self._manifest.dataset_id, row_id, row, bytes.fromhex(str(row.get("salt"))))
            except (ValueError, TypeError):
                got = ""
            if not hmac.compare_digest(got, commitment):
                raise ExposureRefused(f"row {row_id!r} does not match its manifest commitment (another row, or a changed value)")
            opening = {"dataset_id": self._manifest.dataset_id, "row_id": row_id, "manifest_digest": self._manifest.digest,
                       "row_key": row_key(self._manifest.dataset_id, row_id, bytes.fromhex(str(row["salt"]))).hex()}
        conditions = {**dict(row.get("conditions", {})), "partition": partition, "dataset": self._manifest.dataset_id,
                      "dataset_version": self._manifest.version}
        return self._campaign.release(evidence_id=self._manifest.evidence_id(row_id), source=EvidenceSource.MEASUREMENT_RECORD.value,
                                      observable=self._observable, unit=self._unit, value=float(row["value"]),
                                      uncertainty=None if row.get("uncertainty") is None else float(row["uncertainty"]),
                                      conditions=conditions, opening=opening)

    def exploratory(self, row_id: str) -> EvidenceItem:
        if self._manifest.partition_of(row_id) != "exploratory":
            raise ExposureRefused(f"row {row_id!r} is confirmatory; it is released only through the confirmatory gate")
        return self._release(row_id, "exploratory")

    def confirmatory(self, row_id: str, *, preregistration: Preregistration) -> EvidenceItem:
        if self._manifest.partition_of(row_id) != "confirmatory":
            raise ExposureRefused(f"row {row_id!r} is exploratory")
        camp = self._campaign
        if any(d is None for d in self._manifest.files.values()):
            raise ExposureRefused("a manifest with an unavailable file digest is not released confirmatorily")
        revs = _revisions(self._ledger, camp)
        if not revs or revs[-1][1].digest != preregistration.digest:
            raise ExposureRefused("the campaign's latest FROZEN pre-registration is not the one given: freeze it first")
        if not any(a.attestation.record.get("preregistration_digest") == preregistration.digest
                   and a.attestation.record.get("manifest_digest") == self._manifest.digest
                   for a in _approvals(self._ledger, camp, at=self._ledger.length)):
            raise ExposureRefused("no OWNER approval of this pre-registration and manifest: confirmatory data stays sealed")
        reg = camp.registry
        abstained = {(r.attestation.record["hypothesis_id"], r.attestation.record["content_digest"])
                     for r in _untestable(self._ledger, camp) if _whole(r)}
        unsealed = [h for h in preregistration.sections["hypothesis_set"]
                    if not reg.sealed_for(h["hypothesis_id"], h["content_digest"])
                    and (h["hypothesis_id"], h["content_digest"]) not in abstained]
        if unsealed:
            raise ExposureRefused(f"hypotheses with neither a sealed falsifier nor an untestable declaration: "
                                  f"{[h['hypothesis_id'] for h in unsealed]}")
        return self._release(row_id, "confirmatory")


def _opening_issue(manifests: list[tuple[AttestationRecord, DatasetManifest]], rel: Mapping[str, Any], opening: Any, part: str,
                   seq: int, allowed: set[str] | None) -> str:
    """Re-check, from the journal alone, that a released value is the one committed in the manifest the opening names --
    a manifest registered BEFORE the release and, for a confirmatory row, one the owner approved (``allowed``)."""
    eid = str(rel.get("evidence_id"))
    named = opening.get("manifest_digest") if isinstance(opening, Mapping) else None
    found = [(r, m) for r, m in manifests if m.digest == named and r.sequence < seq]
    holding = [m for _r, m in manifests if eid in {m.evidence_id(x) for ids in m.partitions.values() for x in ids}]
    any_commitment = any(m.row_commitments.get(eid.split("/", 1)[-1]) for m in holding)
    if not found:
        if part == "confirmatory" or any_commitment:
            return f"{part} release {eid!r} (ledger {seq}) carries no opening against a manifest registered before it"
        return ""
    m = found[0][1]
    rid = eid.split("/", 1)[1] if "/" in eid else ""
    if m.evidence_id(rid) != eid or rid not in {x for ids in m.partitions.values() for x in ids}:
        return f"release {eid!r} (ledger {seq}) is opened against a manifest that does not hold it"
    if part == "confirmatory" and allowed is not None and m.digest not in allowed:
        return f"confirmatory release {eid!r} (ledger {seq}) is opened against a manifest the owner did not approve"
    if part == "confirmatory" and any(d is None for d in m.files.values()):
        return f"confirmatory release {eid!r} (ledger {seq}) comes from a manifest with an unavailable file digest"
    commitment = m.row_commitments.get(rid)
    if commitment is None:
        return f"{part} release {eid!r} (ledger {seq}) has no row commitment in its manifest" if part == "confirmatory" else ""
    conds = {k: v for k, v in dict(rel.get("conditions") or {}).items() if k not in _GATE_LABELS}
    try:
        got = _commit_with_key(m.dataset_id, rid, {"value": rel.get("value"), "uncertainty": rel.get("uncertainty"),
                                                   "conditions": conds}, bytes.fromhex(str(opening.get("row_key"))))
    except (ValueError, TypeError):
        got = ""
    if not hmac.compare_digest(got, commitment):
        return f"release {eid!r} (ledger {seq}) does not open its manifest commitment: the released value is not the committed one"
    return ""


def verify_discipline(ledger: AuthorityLedger | None, campaign: DurableCampaign, *, issuer_id: str | None = None) -> dict[str, Any]:
    """Re-derive, from the campaign's ledger and its registered manifests alone, whether the campaign is CONFIRMATORY."""
    _owner(campaign, issuer_id)
    ledger = _bound(campaign, ledger)
    cid = campaign.campaign_id
    issues: list[str] = []
    journal_all = [r for r in ledger.attestations(record_kind=OP_KIND, subject_digest=campaign_subject(cid))
                   if r.issuer_id == campaign.issuer_id and r.attestation.role is Role.EXPOSURE
                   and r.attestation.context_digest == campaign.context_digest]
    tainted = [r.sequence for r in journal_all if not _trusted(ledger, r)]
    if tainted:
        issues.append(f"journal entries {tainted} were signed inside a declared compromise window of the owner's key")
    journal = [r for r in journal_all if _trusted(ledger, r)]
    manifests = _manifests(ledger, campaign)
    rows, conflicts = _row_partitions(list(manifests))
    issues.extend(conflicts)
    conf: list[tuple[int, str]] = []
    pending_openings: list[tuple[Mapping[str, Any], Any, str, int]] = []
    for r in journal:
        if r.attestation.record.get("op") != "release":
            continue
        args = r.attestation.record_dict()["args"]
        rel = args["release"]
        eid = str(rel.get("evidence_id"))
        conds = rel.get("conditions")
        label = conds.get("partition") if isinstance(conds, Mapping) else None
        part, since = rows.get(eid, (None, None))
        if part is None:
            issues.append(f"release {eid!r} (ledger {r.sequence}) is no row of a registered manifest: its partition is unknown")
            continue
        if since > r.sequence:
            issues.append(f"release {eid!r} (ledger {r.sequence}) happened before its manifest was registered")
        if label is not None and label != part:
            issues.append(f"release {eid!r} (ledger {r.sequence}) is labelled {label!r} but is a {part} row")
        pending_openings.append((rel, args.get("opening"), part, r.sequence))
        if part == "confirmatory":
            conf.append((r.sequence, eid))
    seal_ops = [(r.sequence, r.attestation.record_dict()["args"]) for r in journal if r.attestation.record.get("op") == "seal"]
    seals = [(seq, a["falsifier"]) for seq, a in seal_ops]
    revs = _revisions(ledger, campaign)
    untestable = _untestable(ledger, campaign)
    first = min(s for s, _e in conf) if conf else None
    in_force = None
    approved_conf: set[str] = set()
    approved: set[str] | None = None
    if first is not None:
        before = [p for s, p in revs if s < first]
        in_force = before[-1] if before else None
        if in_force is None:
            issues.append("confirmatory data was released before any pre-registration was frozen")
        else:
            approvals = [a for a in _approvals(ledger, campaign, at=first) if a.sequence < first
                         and a.attestation.record.get("preregistration_digest") == in_force.digest]
            approved = {a.attestation.record.get("manifest_digest") for a in approvals}
            if not approvals:
                issues.append("confirmatory data was released without an OWNER approval of the pre-registration in force")
            approved_rows = {m.evidence_id(x) for r, m in manifests if m.digest in approved and r.sequence < first
                             for x in m.partitions["confirmatory"]}
            for seq, eid in conf:
                if eid not in approved_rows:
                    issues.append(f"confirmatory release {eid!r} (ledger {seq}) is in no manifest the owner approved")
                else:
                    approved_conf.add(eid)
            covered = {(f["hypothesis_id"], f["hypothesis_content_digest"]) for s, f in seals if s < first}
            covered |= {(u.attestation.record["hypothesis_id"], u.attestation.record["content_digest"]) for u in untestable
                        if u.sequence < first and _whole(u)}
            for h in in_force.sections["hypothesis_set"]:
                if (h["hypothesis_id"], h["content_digest"]) not in covered:
                    issues.append(f"pre-registered hypothesis {h['hypothesis_id']!r} had neither a sealed falsifier nor an untestable "
                                  "declaration before the first confirmatory release (dropped without a record)")
        late_revs = [s for s, _p in revs if s > first]
        if late_revs:
            issues.append(f"the pre-registration was revised after confirmatory exposure (ledger {late_revs})")
        late_abstentions = [r.sequence for r in untestable if r.sequence > first]
        if late_abstentions:
            issues.append(f"hypotheses were declared untestable after confirmatory exposure (ledger {late_abstentions})")
        late_seals = [s for s, _f in seals if s > first]
        if late_seals:
            issues.append(f"falsifiers were sealed after confirmatory exposure (ledger {late_seals}): those test nothing confirmatory")
    for rel, opening, part, seq in pending_openings:
        bad = _opening_issue(manifests, rel, opening, part, seq, approved if part == "confirmatory" else None)
        if bad:
            issues.append(bad)
    rule_rev = in_force or (revs[-1][1] if revs else None)
    rule = structured_rule(rule_rev) if rule_rev is not None else None
    if rule is not None:
        for s, a in seal_ops:
            f = a["falsifier"]
            why = _seal_departs(rule, f) or (_fit_receipt_ok(ledger, campaign, a.get("fit_receipt"), "falsifier_prediction",
                                                             falsifier_fit_digest(f), s)
                                             if f.get("criterion") == "prediction_deviation" else "")
            if why:
                issues.append(f"falsifier {f.get('falsifier_id')!r} (ledger {s}) departs from the pre-registered rule: {why}")
        for u in untestable:
            rec = u.attestation.record_dict()
            ok, why = _rule_fails_everywhere(rule, rec.get("rule_inputs"))
            why = why or _fit_receipt_ok(ledger, campaign, rec.get("fit_receipt"), "rule_inputs", rule_inputs_digest(
                rec.get("rule_inputs") or [], hypothesis_id=rec["hypothesis_id"], content_digest=rec["content_digest"],
                falsifier_ref=rec.get("falsifier_ref")), u.sequence)
            if not ok or why:
                issues.append(f"untestable declaration for {rec['hypothesis_id']!r} (ledger {u.sequence}): {why}")
    counts = {"generated": 0, "admitted": 0}
    registered: set[str] = set()
    for r in journal:
        op = r.attestation.record.get("op")
        if op == "multiplicity":
            args = r.attestation.record_dict()["args"]
            a = list(args.get("args", []))
            if args.get("op") == "count" and a and a[0] in counts:
                counts[a[0]] += int(a[1]) if len(a) > 1 else 1        # the ledger's default n is 1
        elif op == "register":
            registered.add(str(r.attestation.record_dict()["args"]["hypothesis"]["hypothesis_id"]))
    if revs:
        budget_rev = in_force or revs[-1][1]
        budget = budget_rev.multiplicity_budget
        if counts["generated"] > budget["max_generated_hypotheses"]:
            issues.append(f"generated {counts['generated']} > pre-registered max {budget['max_generated_hypotheses']}")
        if counts["admitted"] > budget["max_admitted_hypotheses"]:
            issues.append(f"admitted {counts['admitted']} > pre-registered max {budget['max_admitted_hypotheses']}")
        if len(registered) > budget["max_admitted_hypotheses"]:
            issues.append(f"{len(registered)} hypotheses registered > pre-registered max {budget['max_admitted_hypotheses']}")
        if len(conf) > budget["confirmatory_query_budget"]:
            issues.append(f"{len(conf)} confirmatory releases > pre-registered budget {budget['confirmatory_query_budget']}")
        outside = sorted(registered - set(budget_rev.hypothesis_ids))
        if outside and first is not None:
            issues.append(f"hypotheses {outside} were registered but are not in the pre-registered set")
    status = "EXPLORATORY" if issues else "NOT_FROZEN" if not revs else "NO_CONFIRMATORY_RELEASE" if first is None else "CONFIRMATORY"
    return {"status": status, "issues": issues, "authority_profile": ledger.profile,
            "confirmatory_releases": len(conf), "first_confirmatory_sequence": first,
            "confirmatory_evidence_ids": sorted(approved_conf) if not issues else [],
            "preregistration_in_force": None if in_force is None else {"revision": in_force.revision, "digest": in_force.digest},
            "preregistration_revisions": [{"sequence": s, "revision": p.revision, "digest": p.digest} for s, p in revs],
            "approvals": [a.sequence for a in _approvals(ledger, campaign, at=ledger.length)],
            "multiplicity_from_journal": {**counts, "registered": sorted(registered)},
            "untestable": [{"hypothesis_id": r.attestation.record["hypothesis_id"], "falsifier_ref": r.attestation.record.get("falsifier_ref"),
                            "reason": r.attestation.record["reason"], "sequence": r.sequence} for r in untestable]}


__all__ = ["APPROVAL_KIND", "MANIFEST_KIND", "PARTITIONS", "UNTESTABLE_KIND", "DatasetManifest", "ExposureGate", "ExposureRefused",
           "approve_confirmatory", "commit_row", "declare_untestable", "falsifier_fit_digest", "register_manifest", "row_key",
           "rule_inputs_digest", "rule_resolution",
           "structured_rule",
           "verify_discipline"]
