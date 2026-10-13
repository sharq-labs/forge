"""Test-only helpers: a TEST-profile authority ledger with one issuer per role, and NodeReceipts for test subjects.

Everything here is test key material (``EphemeralKeyProvider``): a production ledger refuses it.
"""

from __future__ import annotations

import hashlib

from engcore.authority import (
    AuthorityLedger,
    EphemeralKeyProvider,
    MemoryLedgerStore,
    Role,
)
from engcore.claims.attestation import attest_receipt, attest_record, record_kind_of
from engcore.execution.orchestration.resources import ResourceUsage
from engcore.scientific.results.validation import VERIFICATION_LEVELS
from engcore.system_runtime.records import NodeReceipt, NodeStatus

ISSUERS = {
    "exec": (Role.EXECUTOR,),
    "ver": (Role.NUMERICAL_VERIFICATION,),
    "val": (Role.VALIDATION,),
    "app": (Role.APPLICABILITY,),
    "meas": (Role.MEASUREMENT,),
    "uq": (Role.UNCERTAINTY,),
    "rt": (Role.RED_TEAM,),
}


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def receipt_for(subject_digest: str, *, output: str = "y", node_id: str = "solve") -> NodeReceipt:
    """A SUCCEEDED receipt whose output ``output`` has digest ``subject_digest`` (the executor vouches for it by attesting)."""
    return NodeReceipt(node_id, NodeStatus.SUCCEEDED, _h("plan"), _h("request"), _h("node:" + node_id), _h("authority"),
                       _h("execution:" + subject_digest), (), ((output, subject_digest),), (), (), (), _h("state0"), _h("state1"),
                       ResourceUsage(), "", (), 1)


class World:
    """One test ledger + key provider + per-role issuers."""

    def __init__(self, *, ledger_id: str = "test-ledger") -> None:
        self.keys = EphemeralKeyProvider()
        self.root = self.keys.signer("root")
        self.store = MemoryLedgerStore()
        self.ledger = AuthorityLedger.create(self.store, ledger_id=ledger_id, profile="test", root=self.root)
        self.ledger_id = ledger_id
        for issuer, roles in ISSUERS.items():
            self.register(issuer, roles)
        self.receipts: dict[tuple[str, str], object] = {}

    def register(self, issuer: str, roles) -> None:
        self.ledger.register_issuer(self.root, issuer, self.keys.signer(issuer).possession(self.ledger_id, issuer), roles=roles)

    def opened(self):
        """What a CONSUMER holds: the ledger re-opened from its store against the anchor it pinned, and that anchor."""
        anchor = self.ledger.anchor()
        return AuthorityLedger.open(self.store, anchor=anchor), anchor

    def assess_kwargs(self) -> dict:
        led, anchor = self.opened()
        return {"authority": led, "trust_anchor": anchor, "allow_test_profile": True}

    def signer(self, issuer: str):
        return self.keys.signer(issuer)

    def receipt(self, subject_digest: str, context: str, *, output: str = "y"):
        key = (subject_digest, context)
        if key not in self.receipts:
            self.receipts[key] = attest_receipt(self.ledger, self.signer("exec"), "exec", receipt_for(subject_digest, output=output),
                                                context_digest=context)
        return self.receipts[key]

    def attest(self, record, subject_digest: str, context: str, *, issuer: str | None = None, role: Role | None = None, output: str = "y"):
        issuer, role = issuer or default_issuer(record), role or default_role(record)
        return attest_record(self.ledger, self.signer(issuer), issuer, record, receipt=self.receipt(subject_digest, context, output=output),
                             subject_output=output, context_digest=context, role=role)


#: the Core's own classification, never a copy of it (F4 moved BENCHMARK_VALIDATED into it)
_VERIFY = VERIFICATION_LEVELS


def default_role(record) -> Role:
    kind = record_kind_of(record)
    if kind == "validation_check":
        return Role.NUMERICAL_VERIFICATION if record.establishes in _VERIFY else Role.VALIDATION
    if kind == "applicability_report":
        return Role.APPLICABILITY
    if kind == "trust_envelope":
        return Role.RED_TEAM
    channel = record.channel.value
    return {"aleatoric": Role.MEASUREMENT, "numerical": Role.NUMERICAL_VERIFICATION}.get(channel, Role.UNCERTAINTY)


def default_issuer(record) -> str:
    return {Role.NUMERICAL_VERIFICATION: "ver", Role.VALIDATION: "val", Role.APPLICABILITY: "app", Role.MEASUREMENT: "meas",
            Role.UNCERTAINTY: "uq", Role.RED_TEAM: "rt"}[default_role(record)]
