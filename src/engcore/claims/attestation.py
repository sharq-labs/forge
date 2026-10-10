"""Issuing the existing scientific records into the authority ledger (:mod:`engcore.authority`).

Nothing here is a new record type: a NodeReceipt, ValidationCheck, ApplicabilityReport, ChannelEntry or TrustEnvelope
is attested AS IT IS, by digest, with the record carried whole.  Two steps, two different issuers:

1. :func:`attest_receipt` -- an EXECUTOR-role issuer states that it executed a node and that the receipt (with its
   output digests) is what the execution produced.  The receipt is re-read (``NodeReceipt.from_dict``) and must be
   SUCCEEDED.
2. :func:`attest_record` -- an evidence issuer (validation, applicability, uncertainty, red team, ...) states that a
   record is about output ``subject_output`` of THAT attested receipt, in THAT decision context.  The subject digest is
   READ from the receipt, never stated by the caller, so evidence cannot be pointed at a result the receipt does not
   contain.

The consumer side (``claims.credibility_vector`` with ``authority=``) admits a record only through
:func:`engcore.authority.verify_evidence`.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from ..authority import (
    Attestation,
    AttestationRecord,
    AuthorityLedger,
    AuthorityRefused,
    Role,
    Signer,
    receipt_outputs,
)
from ..authority.evidence import RECEIPT_KIND

VALIDATION_CHECK = "validation_check"
APPLICABILITY_REPORT = "applicability_report"
CHANNEL_ENTRY = "uncertainty_channel_entry"
TRUST_ENVELOPE = "trust_envelope"

#: which roles may attest each record kind at all (the factor a record backs narrows this further)
KIND_ROLES: Mapping[str, frozenset[Role]] = MappingProxyType({
    VALIDATION_CHECK: frozenset({Role.NUMERICAL_VERIFICATION, Role.VALIDATION}),
    APPLICABILITY_REPORT: frozenset({Role.APPLICABILITY}),
    CHANNEL_ENTRY: frozenset({Role.NUMERICAL_VERIFICATION, Role.UNCERTAINTY, Role.MEASUREMENT}),
    TRUST_ENVELOPE: frozenset({Role.RED_TEAM}),
})


def record_kind_of(record: Any) -> str:
    from ..scientific.results.validation import ValidationCheck
    from ..sria.assurance.uncertainty_budget import ChannelEntry
    from ..system_runtime.records import ApplicabilityReport
    from .redteam import TrustEnvelope
    for cls, kind in ((ValidationCheck, VALIDATION_CHECK), (ApplicabilityReport, APPLICABILITY_REPORT), (ChannelEntry, CHANNEL_ENTRY),
                      (TrustEnvelope, TRUST_ENVELOPE)):
        if isinstance(record, cls):
            return kind
    raise AuthorityRefused(f"{type(record).__name__} is not an attestable scientific record")


def _schema_of(record_dict: Mapping[str, Any], kind: str) -> str:
    return str(record_dict.get("schema") or f"engcore.{kind}")


def attest_receipt(ledger: AuthorityLedger, signer: Signer, issuer_id: str, receipt: Any, *, context_digest: str) -> AttestationRecord:
    """EXECUTOR attestation of a SUCCEEDED NodeReceipt (re-read through ``NodeReceipt.from_dict``)."""
    from ..system_runtime.records import NodeReceipt, NodeStatus
    if not isinstance(receipt, NodeReceipt):
        raise AuthorityRefused("an executor attests a NodeReceipt")
    again = NodeReceipt.from_dict(receipt.to_dict())
    if again.status is not NodeStatus.SUCCEEDED or not again.output_digests:
        raise AuthorityRefused("only a SUCCEEDED receipt with outputs is attested as having produced a result")
    d = again.to_dict()
    att = Attestation(RECEIPT_KIND, _schema_of(d, RECEIPT_KIND), d, again.digest, context_digest, Role.EXECUTOR)
    return ledger.attest(signer, issuer_id, att)


def attest_record(ledger: AuthorityLedger, signer: Signer, issuer_id: str, record: Any, *, receipt: AttestationRecord,
                  subject_output: str, context_digest: str, role: Role) -> AttestationRecord:
    """An evidence issuer attests ``record`` as being about output ``subject_output`` of the attested ``receipt``."""
    kind = record_kind_of(record)
    role = Role(role)
    if role not in KIND_ROLES[kind]:
        raise AuthorityRefused(f"a {kind} is attested in one of {sorted(r.value for r in KIND_ROLES[kind])}, not {role.value}")
    if receipt.attestation.record_kind != RECEIPT_KIND:
        raise AuthorityRefused("evidence names an attested node receipt")
    subject = receipt_outputs(receipt).get(subject_output)
    if subject is None:
        raise AuthorityRefused(f"the attested receipt has no output {subject_output!r}")
    d = record.to_dict()
    if kind == APPLICABILITY_REPORT and record.evidence_digest and record.evidence_digest != subject:
        raise AuthorityRefused(f"the applicability report is decided on {record.evidence_digest[:12]}, not on the attested output "
                               f"{subject[:12]}: it is attested about the result it names")
    att = Attestation(kind, _schema_of(d, kind), d, subject, context_digest, role, receipt.record_digest, subject_output)
    return ledger.attest(signer, issuer_id, att)


__all__ = ["APPLICABILITY_REPORT", "CHANNEL_ENTRY", "KIND_ROLES", "TRUST_ENVELOPE", "VALIDATION_CHECK", "attest_receipt", "attest_record",
           "record_kind_of"]
