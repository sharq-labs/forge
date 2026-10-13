"""Hostile review (MED/P1): the genesis signature guard had no test that only it could fail.

The genesis digest covers its signature, so most rewrites of a genesis break the
chain or the anchor first. The case only the signature check catches: an anchor
that pins the VICTIM's root key id over a forged genesis that declares the
victim's root public key but was signed by someone else. Without the guard that
ledger opens, and every issuer it registers is "authorized" by a root that never
signed anything.
"""

from __future__ import annotations

import pytest

from engcore.authority import AuthorityLedger, EphemeralKeyProvider, MemoryLedgerStore
from engcore.authority.ledger import GENESIS_PREVIOUS, AuthorityRefused, LedgerEvent, TrustAnchor, canonical


def _forged_genesis(victim_ledger: AuthorityLedger, forger) -> LedgerEvent:
    genuine = victim_ledger.events()[0]
    unsigned = LedgerEvent(genuine.ledger_id, 0, GENESIS_PREVIOUS, "genesis", genuine.body, genuine.key_id)
    return LedgerEvent(unsigned.ledger_id, 0, GENESIS_PREVIOUS, "genesis", unsigned.body, unsigned.key_id,
                       forger.sign(unsigned.signed_bytes()))


@pytest.fixture()
def victim():
    keys = EphemeralKeyProvider()
    ledger = AuthorityLedger.create(MemoryLedgerStore(), ledger_id="victim-ledger", profile="test", root=keys.signer("root"))
    return keys, ledger


def test_a_genesis_declaring_the_victims_root_but_signed_by_another_key_is_refused(victim) -> None:
    keys, ledger = victim
    forged = _forged_genesis(ledger, keys.signer("forger"))
    store = MemoryLedgerStore()
    store.append(canonical(forged.to_dict()), expected_lines=0)
    anchor = TrustAnchor(forged.ledger_id, "test", ledger.root_key_id, 0, forged.digest)
    with pytest.raises(AuthorityRefused, match="genesis signature invalid"):
        AuthorityLedger.open(store, anchor=anchor)


def test_the_genuine_genesis_under_the_same_anchor_shape_opens(victim) -> None:
    _, ledger = victim
    genuine = ledger.events()[0]
    store = MemoryLedgerStore()
    store.append(canonical(genuine.to_dict()), expected_lines=0)
    opened = AuthorityLedger.open(store, anchor=TrustAnchor(genuine.ledger_id, "test", ledger.root_key_id, 0, genuine.digest))
    assert opened.root_key_id == ledger.root_key_id
