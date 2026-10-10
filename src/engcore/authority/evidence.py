"""Issuer-bound evidence: is THIS record, about THIS result, from an issuer authorized for THIS role?

:func:`verify_evidence` answers with the admitted attestation or with every reason it is refused.  A record counts only
when ALL hold:

* an ``attest`` event in the (anchored, re-verified) ledger carries exactly this record digest and record kind;
* its issuer held one of the required roles AT THAT SEQUENCE (unknown, revoked, wrong-role issuers never sign anything
  the ledger admits -- :mod:`.ledger` refuses them on append and on load);
* its subject is THIS result (``subject_digest``) in THIS decision context;
* its ``receipt_digest`` names a NodeReceipt attestation by an EXECUTOR-role issuer, attested BEFORE the evidence,
  whose receipt lists the subject digest among its outputs (``subject_output`` names which);
* the evidence issuer is not the executor issuer of that receipt: a result does not certify itself.

Every refusal is UNKNOWN for the consumer, never a lower rung it could misread as support.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ledger import AttestationRecord, AuthorityLedger, Role

RECEIPT_KIND = "node_receipt"


@dataclass(frozen=True)
class AdmittedEvidence:
    evidence: AttestationRecord
    receipt: AttestationRecord


def receipt_outputs(receipt: AttestationRecord) -> dict[str, str]:
    """``{output name: output digest}`` of an attested NodeReceipt record (empty if it is not a SUCCEEDED receipt)."""
    rec = receipt.attestation.record
    if receipt.attestation.record_kind != RECEIPT_KIND or rec.get("status") != "succeeded":
        return {}
    try:
        return {str(n): str(d) for n, d in rec.get("output_digests", [])}
    except (TypeError, ValueError):
        return {}


def verify_receipt(ledger: AuthorityLedger, receipt_digest: str, *, context_digest: str) -> tuple[AttestationRecord | None, list[str]]:
    hits = [r for r in ledger.attestations(record_kind=RECEIPT_KIND, record_digest=receipt_digest)
            if r.attestation.role is Role.EXECUTOR and ledger.role_at(r.issuer_id, Role.EXECUTOR, r.sequence)]
    if not hits:
        return None, [f"no EXECUTOR attestation of node receipt {receipt_digest[:12]} in the ledger"]
    same_ctx = [r for r in hits if r.attestation.context_digest == context_digest]
    if not same_ctx:
        return None, [f"node receipt {receipt_digest[:12]} was attested for another context"]
    return same_ctx[0], []


def executors_of(ledger: AuthorityLedger, receipt_digest: str) -> frozenset[str]:
    """EVERY issuer that ever attested this receipt as its executor (any context)."""
    return frozenset(r.issuer_id for r in ledger.attestations(record_kind=RECEIPT_KIND, record_digest=receipt_digest)
                     if r.attestation.role is Role.EXECUTOR)


def verify_evidence(ledger: AuthorityLedger, *, record_kind: str, record_digest: str, subject_digest: str,
                    context_digest: str, roles: Iterable[Role], allow_self_issued: bool = False) -> tuple[AdmittedEvidence | None, list[str]]:
    """``allow_self_issued`` is for NEGATIVE records only (a failure, an 'outside' finding, a falsification): those only
    ever lower, so the executor reporting against its own result is admitted; positive support never is."""
    roles = frozenset(Role(r) for r in roles)
    candidates = ledger.attestations(record_kind=record_kind, record_digest=record_digest)
    if not candidates:
        return None, [f"{record_kind} {record_digest[:12]} is not attested in the authority ledger"]
    reasons: list[str] = []
    for c in candidates:
        a = c.attestation
        why = []
        if a.role not in roles or not ledger.role_at(c.issuer_id, a.role, c.sequence):
            why.append(f"issuer {c.issuer_id!r} attested it as {a.role.value}; {sorted(r.value for r in roles)} is required")
        if a.subject_digest != subject_digest:
            why.append(f"it is about result {a.subject_digest[:12]}, not {subject_digest[:12]}")
        if a.context_digest != context_digest:
            why.append("it was attested for another context")
        receipt, rwhy = (None, ["it names no node receipt"]) if not a.receipt_digest else \
            verify_receipt(ledger, a.receipt_digest, context_digest=context_digest)
        why.extend(rwhy)
        if receipt is not None:
            outputs = receipt_outputs(receipt)
            if outputs.get(a.subject_output) != subject_digest:
                why.append(f"the attested receipt has no output {a.subject_output!r} with digest {subject_digest[:12]}")
            if receipt.sequence >= c.sequence:
                why.append("the receipt was attested after the evidence about it")
            if not allow_self_issued and c.issuer_id in executors_of(ledger, a.receipt_digest):
                why.append(f"issuer {c.issuer_id!r} executed the result it attests: self-issued evidence is not independent")
        if not why and receipt is not None:
            return AdmittedEvidence(c, receipt), []
        reasons.extend(f"attestation @{c.sequence}: {w}" for w in why)
    return None, reasons


__all__ = ["RECEIPT_KIND", "AdmittedEvidence", "executors_of", "receipt_outputs", "verify_evidence", "verify_receipt"]
