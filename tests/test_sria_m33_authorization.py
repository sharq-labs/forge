"""SRIA V0.1 M3.3 — authorization asymmetry audit.

Runs under pytest, and standalone via
``python -m tests.test_sria_m33_authorization``.

The property under test:

    The verification side (AdmissionAuthority, Registry, Gateway) can check
    that an authorization came from a genuine Arbiter, but does not possess
    the capability required to mint one.

M3.2 claimed this while using an HMAC whose key the authority also held —
which is symmetric, so the authority could forge. M3.3 replaces it with a hash
commitment: the Arbiter draws a random code and registers only
``sha256(code | payload)``. These tests attack from the verifier side, holding
everything the authority stores.

Scope, stated plainly: this is a same-process Python architectural authenticity
boundary. It is not public-key cryptography and not a security control. Code
that mutates ``_commitments`` directly, monkey-patches the module, or reaches
into another object can still defeat it. What it does guarantee is that
possession of a trusted authority, and of everything that authority legitimately
stores, is not sufficient to authorize admission.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys

from src.engcore.sria import (
    AdmissionAuthorityError,
    AdmissionAuthorityRegistry,
    BeliefUpdateGateway,
)
from src.engcore.sria.admission import (
    AdmissionAuthority,
    AdmissionDeclaration,
    DecisionBinding,
)
from src.engcore.sria.assurance import Arbiter, AssuranceVerdict, CriticClass

from tests.test_sria_m31_semantics import (  # noqa: E402
    budget,
    charter_obligations,
    evidence_for,
    good_result,
    numerical_assessment,
)


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


def setup(tag: str):
    """A trusted authority, a genuine Arbiter, a gateway and evidence."""
    authority = AdmissionAuthority(f"authority.{tag}", secret=f"sig-{tag}")
    arbiter = Arbiter(authority)
    gateway = BeliefUpdateGateway(
        authorities=AdmissionAuthorityRegistry([authority])
    )
    evidence = evidence_for(good_result(), f"ev-{tag}")
    return authority, arbiter, gateway, evidence


def valid_decision(arbiter, evidence, decision_id="d-valid"):
    result = good_result()
    decision = arbiter.decide(
        decision_id=decision_id,
        subject_ref=evidence.evidence_id,
        assessments=[numerical_assessment(result)],
        obligations=charter_obligations(
            required_critics=(CriticClass.NUMERICAL,)
        ),
        budget=budget(),
    )
    assert decision.verdict is AssuranceVerdict.VALID
    return decision


# =====================================================================
# 1. What secret material does each component actually hold?
# =====================================================================

def test_authority_holds_no_arbiter_key_material():
    """The audit question, asserted rather than argued."""
    authority, arbiter, _gateway, evidence = setup("keys")
    decision = valid_decision(arbiter, evidence)
    arbiter.authorize_admission(decision, evidence)

    state = vars(authority)
    # Its own declaration-signing key is legitimate — signing declarations is
    # the authority's job. What it must NOT hold is the Arbiter's capability.
    assert "_secret" in state
    assert "_arbiters" not in state, "authority must not store arbiter keys"

    commitments = state["_commitments"]
    assert commitments, "a genuine authorization registers a commitment"
    for digest in commitments.values():
        assert len(digest) == 64      # a SHA-256 hex digest
        int(digest, 16)               # …and nothing but a digest

    # The authority exposes verification, not minting.
    assert hasattr(authority, "verifies_authorization")
    assert hasattr(authority, "register_authorization")
    for forbidden in ("mint_authorization", "make_authorization", "authorize"):
        assert not hasattr(authority, forbidden)


def test_arbiter_keeps_no_long_lived_shared_secret():
    authority, arbiter, _gateway, _evidence = setup("nosecret")
    assert not hasattr(arbiter, "_authorization_secret"), (
        "M3.3 removes the shared HMAC key entirely"
    )


# =====================================================================
# A. The verifier cannot mint
# =====================================================================

def test_A_verification_side_cannot_mint_an_authorization():
    """Attacker holds the authority and everything it stores. Not enough."""
    authority, arbiter, gateway, evidence = setup("A")
    # A genuine authorization exists, so the attacker sees real commitments.
    genuine_decision = valid_decision(arbiter, evidence)
    arbiter.authorize_admission(genuine_decision, evidence)
    assert authority._commitments  # noqa: SLF001 — this is the attack surface

    # Attacker fabricates a decision and tries every code it can produce.
    fabricated = DecisionBinding(
        decision_id="dec-fabricated",
        decision_hash="d" * 64,
        verdict="valid",
        policy_id="sria.arbiter",
        policy_version="arbiter/1",
        arbiter_id="arbiter/1:attacker",
        authorization_code=secrets.token_hex(32),
    )
    assert (
        authority.verifies_authorization(
            fabricated, subject_record_hash=evidence.record_hash
        )
        is False
    )

    # Trying to derive a code from stored material: the authority holds only
    # digests, and inverting them is the whole point.
    for digest in list(authority._commitments.values()):  # noqa: SLF001
        guess = DecisionBinding(
            decision_id="dec-fabricated",
            decision_hash="d" * 64,
            verdict="valid",
            authorization_code=digest,   # the digest is not a preimage
        )
        assert (
            authority.verifies_authorization(
                guess, subject_record_hash=evidence.record_hash
            )
            is False
        )

    _raises(
        AdmissionAuthorityError,
        authority.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=fabricated,
    )
    assert len(gateway.belief) == 0


def test_A2_authority_with_no_commitments_can_authorize_nothing():
    authority = AdmissionAuthority("lonely", secret="s")
    evidence = evidence_for(good_result(), "ev-lonely3")
    assert authority._commitments == {}  # noqa: SLF001
    _raises(
        AdmissionAuthorityError,
        authority.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=DecisionBinding(
            decision_id="d",
            decision_hash="h",
            verdict="valid",
            authorization_code=secrets.token_hex(32),
        ),
    )


# =====================================================================
# B. Fabricated authorization is rejected end-to-end
# =====================================================================

def test_B_fabricated_authorization_rejected_by_gateway():
    """Even if signing is bypassed, the Gateway re-verifies independently."""
    authority, arbiter, gateway, evidence = setup("B")
    valid_decision(arbiter, evidence)

    fabricated = DecisionBinding(
        decision_id="dec-fake",
        decision_hash="f" * 64,
        verdict="valid",
        authorization_code=secrets.token_hex(32),
    )
    forged = AdmissionDeclaration(
        admitted=True,
        arbiter_id=authority.authority_id,
        subject_record_hash=evidence.record_hash,
        authorization=fabricated,
        issuer_id=authority.authority_id,
    )
    signature = authority._sign(forged.signing_payload())  # noqa: SLF001
    signed = AdmissionDeclaration(
        admitted=True,
        arbiter_id=authority.authority_id,
        subject_record_hash=evidence.record_hash,
        authorization=fabricated,
        issuer_id=authority.authority_id,
        issued_signature=signature,
    )
    assert authority.verifies(signed), "signature genuine by construction"
    _raises(AdmissionAuthorityError, gateway.submit, evidence.admit(signed))
    assert len(gateway.belief) == 0


# =====================================================================
# C. Copied to another evidence record
# =====================================================================

def test_C_authorization_copied_to_another_record_rejected():
    authority, arbiter, gateway, evidence_a = setup("C")
    decision = valid_decision(arbiter, evidence_a)
    genuine = arbiter.authorize_admission(decision, evidence_a)

    evidence_b = evidence_for(good_result("res-c2"), "ev-C2")
    assert evidence_b.record_hash != evidence_a.record_hash

    # The commitment covers the record hash, so the same code does not verify.
    assert (
        authority.verifies_authorization(
            genuine.authorization, subject_record_hash=evidence_b.record_hash
        )
        is False
    )
    _raises(
        AdmissionAuthorityError,
        authority.issue,
        admitted=True,
        subject_record_hash=evidence_b.record_hash,
        authorization=genuine.authorization,
    )
    assert len(gateway.belief) == 0


# =====================================================================
# D. Modified verdict
# =====================================================================

def test_D_modified_verdict_rejected():
    """A genuine code for one verdict cannot authorize another."""
    authority, arbiter, gateway, evidence = setup("D")
    decision = valid_decision(arbiter, evidence)
    genuine = arbiter.authorize_admission(decision, evidence)
    assert genuine.authorization.verdict == "valid"

    relabelled = DecisionBinding(
        decision_id=genuine.authorization.decision_id,
        decision_hash=genuine.authorization.decision_hash,
        verdict="inconclusive",          # changed
        policy_id=genuine.authorization.policy_id,
        policy_version=genuine.authorization.policy_version,
        arbiter_id=genuine.authorization.arbiter_id,
        authorization_code=genuine.authorization.authorization_code,
    )
    assert (
        authority.verifies_authorization(
            relabelled, subject_record_hash=evidence.record_hash
        )
        is False
    )

    # And the reverse: a code minted for a non-VALID decision relabelled VALID.
    arbiter2 = Arbiter(authority)
    inconclusive = arbiter2.decide(
        decision_id="d-inc",
        subject_ref=evidence.evidence_id,
        assessments=[numerical_assessment(good_result())],
        obligations=charter_obligations(),   # nothing required -> INCONCLUSIVE
        budget=budget(),
    )
    assert inconclusive.verdict is AssuranceVerdict.INCONCLUSIVE
    declining = arbiter2.authorize_admission(inconclusive, evidence)
    promoted = DecisionBinding(
        decision_id=declining.authorization.decision_id,
        decision_hash=declining.authorization.decision_hash,
        verdict="valid",                 # the lie
        policy_id=declining.authorization.policy_id,
        policy_version=declining.authorization.policy_version,
        arbiter_id=declining.authorization.arbiter_id,
        authorization_code=declining.authorization.authorization_code,
    )
    assert (
        authority.verifies_authorization(
            promoted, subject_record_hash=evidence.record_hash
        )
        is False
    )
    _raises(
        AdmissionAuthorityError,
        authority.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=promoted,
    )
    assert len(gateway.belief) == 0


def test_D2_modified_decision_identity_rejected():
    authority, arbiter, gateway, evidence = setup("D2")
    decision = valid_decision(arbiter, evidence)
    genuine = arbiter.authorize_admission(decision, evidence)

    for field, value in (
        ("decision_id", "other-decision"),
        ("decision_hash", "a" * 64),
        ("policy_version", "arbiter/99"),
        ("arbiter_id", "someone-else"),
    ):
        kwargs = {
            "decision_id": genuine.authorization.decision_id,
            "decision_hash": genuine.authorization.decision_hash,
            "verdict": "valid",
            "policy_id": genuine.authorization.policy_id,
            "policy_version": genuine.authorization.policy_version,
            "arbiter_id": genuine.authorization.arbiter_id,
            "authorization_code": genuine.authorization.authorization_code,
        }
        kwargs[field] = value
        assert (
            authority.verifies_authorization(
                DecisionBinding(**kwargs),
                subject_record_hash=evidence.record_hash,
            )
            is False
        ), f"tampering with {field} was not detected"
    assert len(gateway.belief) == 0


# =====================================================================
# E. The genuine path still works
# =====================================================================

def test_E_genuine_arbiter_authorization_accepted():
    authority, arbiter, gateway, evidence = setup("E")
    decision = valid_decision(arbiter, evidence)
    declaration = arbiter.authorize_admission(decision, evidence)

    binding = declaration.authorization
    assert binding.verdict == "valid"
    assert binding.decision_hash == decision.decision_hash
    assert binding.arbiter_id
    assert len(binding.authorization_code) == 64
    assert authority.verifies_authorization(
        binding, subject_record_hash=evidence.record_hash
    )

    entry = gateway.submit(evidence.admit(declaration))
    assert entry.evidence_id == evidence.evidence_id
    assert len(gateway.belief) == 1
    assert gateway.rejection_log == ()


def test_E2_genuine_authorization_survives_serialization():
    authority, arbiter, gateway, evidence = setup("E2")
    decision = valid_decision(arbiter, evidence)
    declaration = arbiter.authorize_admission(decision, evidence)

    reloaded = AdmissionDeclaration.from_dict(
        json.loads(json.dumps(declaration.to_dict()))
    )
    assert reloaded == declaration
    assert reloaded.authorization.arbiter_id == declaration.authorization.arbiter_id
    gateway.submit(evidence.admit(reloaded))
    assert len(gateway.belief) == 1


def test_commitment_is_a_one_way_digest():
    """The registered value reveals nothing usable about the code."""
    payload = AdmissionAuthority.authorization_payload(
        decision_id="d",
        decision_hash="h",
        subject_record_hash="r",
        verdict="valid",
    )
    code = secrets.token_hex(32)
    commitment = AdmissionAuthority.commitment_for(code, payload)

    assert commitment != code
    assert code not in commitment
    assert commitment == hashlib.sha256(f"{code}|{payload}".encode()).hexdigest()
    # A different code for the same payload gives a different commitment.
    assert AdmissionAuthority.commitment_for(secrets.token_hex(32), payload) != (
        commitment
    )


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M3.3 — authorization asymmetry audit")
    print("=" * 72)
    failures = 0
    tests = _all_tests()
    for name, test in tests:
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    print("=" * 72)
    if failures:
        print(f"M3.3 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M3.3 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
