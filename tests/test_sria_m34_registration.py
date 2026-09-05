"""SRIA V0.1 M3.4 — commitment registration and replay audit.

Runs under pytest, and standalone via
``python -m tests.test_sria_m34_registration``.

M3.3 established that a verifier cannot *derive* an authorization code from a
stored digest. This suite audits the adjacent capability: **who may register a
new commitment**, and whether a genuine authorization can be replayed.

Both were open before M3.4. Possession of a trusted AdmissionAuthority allowed
arbitrary commitment registration, and a used authorization could re-activate
evidence that had since been suspended.
"""

from __future__ import annotations

import secrets
import sys

from src.engcore.sria import (
    AdmissionAuthorityError,
    AdmissionAuthorityRegistry,
    AdmissionError,
    BeliefUpdateGateway,
    EvidenceStatus,
)
from src.engcore.sria.admission import (
    AdmissionAuthority,
    DecisionBinding,
    _issue_registrar_capability,
)
from src.engcore.sria.assurance import Arbiter, AssuranceVerdict

from tests.test_sria_m33_authorization import (  # noqa: E402
    setup,
    valid_decision,
)
from tests.test_sria_m31_semantics import (  # noqa: E402
    evidence_for,
    good_result,
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


def attacker_payload(evidence, decision_id="dec-attacker"):
    return AdmissionAuthority.authorization_payload(
        decision_id=decision_id,
        decision_hash="c" * 64,
        subject_record_hash=evidence.record_hash,
        verdict="valid",
        policy_id="sria.arbiter",
        policy_version="arbiter/1",
        arbiter_id="attacker",
    )


# =====================================================================
# 1. A trusted authority cannot register a fabricated commitment
# =====================================================================

def test_1_trusted_authority_cannot_register_a_commitment():
    """The M3.4 attack, using only supported APIs."""
    authority, arbiter, gateway, evidence = setup("reg1")
    # A genuine Arbiter exists, so this is a fully operational authority.
    valid_decision(arbiter, evidence)

    code = secrets.token_hex(32)
    payload = attacker_payload(evidence)
    commitment = AdmissionAuthority.commitment_for(code, payload)

    # No capability at all.
    _raises(
        TypeError, authority.register_authorization, commitment, payload
    )
    # A plausible stand-in object is not a capability.
    for impostor in (None, object(), "registrar", {"registrar_id": "x"}):
        _raises(
            AdmissionAuthorityError,
            authority.register_authorization,
            impostor,
            commitment,
            payload,
        )
    # The capability class itself refuses direct construction.
    from src.engcore.sria.admission import _RegistrarCapability

    _raises(AdmissionAuthorityError, _RegistrarCapability, "attacker")

    assert authority._commitments == {}  # noqa: SLF001 — nothing registered


def test_1b_authority_exposes_no_way_to_obtain_a_capability():
    """Holding the authority must not yield registration rights."""
    authority, arbiter, _gateway, _evidence = setup("reg1b")
    from src.engcore.sria.admission import _RegistrarCapability

    for name in dir(authority):
        if name.startswith("__"):
            continue
        attribute = getattr(authority, name, None)
        assert not isinstance(attribute, _RegistrarCapability), (
            f"authority exposes a registrar capability via {name!r}"
        )
        if callable(attribute) and name in (
            "claim_registrar",
            "registrar",
            "new_registrar",
        ):
            raise AssertionError(f"authority exposes {name!r}")

    # The Arbiter holds one, and does not hand it out.
    assert isinstance(arbiter._registrar, _RegistrarCapability)  # noqa: SLF001
    assert not hasattr(arbiter, "registrar")


# =====================================================================
# 2. Fabricated commitment / code is rejected end to end
# =====================================================================

def test_2_fabricated_commitment_never_reaches_belief():
    authority, arbiter, gateway, evidence = setup("reg2")
    valid_decision(arbiter, evidence)

    code = secrets.token_hex(32)
    binding = DecisionBinding(
        decision_id="dec-attacker",
        decision_hash="c" * 64,
        verdict="valid",
        policy_id="sria.arbiter",
        policy_version="arbiter/1",
        arbiter_id="attacker",
        authorization_code=code,
    )
    assert (
        authority.verifies_authorization(
            binding, subject_record_hash=evidence.record_hash
        )
        is False
    )
    _raises(
        AdmissionAuthorityError,
        authority.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=binding,
    )
    assert len(gateway.belief) == 0


# =====================================================================
# 3. A genuine Arbiter commitment is accepted
# =====================================================================

def test_3_genuine_arbiter_commitment_accepted():
    authority, arbiter, gateway, evidence = setup("reg3")
    decision = valid_decision(arbiter, evidence)
    assert decision.verdict is AssuranceVerdict.VALID

    declaration = arbiter.authorize_admission(decision, evidence)
    assert authority._commitments, "the Arbiter registered a commitment"  # noqa: SLF001

    entry = gateway.submit(evidence.admit(declaration))
    assert entry.evidence_id == evidence.evidence_id
    assert len(gateway.belief) == 1
    assert gateway.rejection_log == ()


# =====================================================================
# 4. Cross-evidence replay
# =====================================================================

def test_4_cross_evidence_replay_rejected():
    authority, arbiter, gateway, evidence_a = setup("reg4")
    decision = valid_decision(arbiter, evidence_a)
    genuine = arbiter.authorize_admission(decision, evidence_a)

    evidence_b = evidence_for(good_result("res-r4"), "ev-reg4b")
    assert evidence_b.record_hash != evidence_a.record_hash

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
    _raises(Exception, evidence_b.admit, genuine)
    assert len(gateway.belief) == 0


# =====================================================================
# 5. Replay and suspension
# =====================================================================

def test_5_stale_authorization_cannot_reactivate_suspended_evidence():
    """The decisive case: option B — commitments are consumed on admission."""
    authority, arbiter, gateway, evidence = setup("reg5")
    decision = valid_decision(arbiter, evidence)
    declaration = arbiter.authorize_admission(decision, evidence)
    admitted = evidence.admit(declaration)

    gateway.submit(admitted)
    assert len(gateway.belief) == 1

    suspended = admitted.suspend("superseding measurement pending")
    gateway.update_standing(suspended)
    assert len(gateway.belief) == 0
    assert suspended.status is EvidenceStatus.SUSPENDED

    # Re-presenting the original accepting declaration must not resurrect it.
    _raises(AdmissionAuthorityError, gateway.submit, admitted)
    assert len(gateway.belief) == 0

    # Nor may a bare lifecycle move. `reinstate()` produces ACCEPTED status
    # carrying no fresh authorization, and update_standing() only lowers
    # standing — this is the bypass this test previously asserted as correct.
    unauthorized = suspended.reinstate("looks fine to me", actor="anyone")
    assert unauthorized.status is EvidenceStatus.ACCEPTED
    _raises(AdmissionError, gateway.update_standing, unauthorized)
    assert len(gateway.belief) == 0

    # ...and submit() refuses it too, because the stale declaration it still
    # carries no longer binds the mutated record.
    _raises(AdmissionAuthorityError, gateway.submit, unauthorized)
    assert len(gateway.belief) == 0

    # The only way back is a fresh decision and a fresh authorization, actually
    # consumed by submit().
    fresh_decision = valid_decision(arbiter, suspended, decision_id="d-fresh")
    fresh = arbiter.authorize_admission(fresh_decision, suspended)
    assert fresh.authorization.decision_id == "d-fresh"
    reinstated = suspended.admit(fresh, actor="arbiter")
    gateway.submit(reinstated)
    assert len(gateway.belief) == 1

    # That fresh authorization is now spent, exactly like the first one.
    assert (
        authority.verifies_authorization(
            fresh.authorization, subject_record_hash=suspended.record_hash
        )
        is False
    )
    _raises(AdmissionAuthorityError, gateway.submit, reinstated)
    assert len(gateway.belief) == 1


def test_5b_authorization_is_single_use():
    """Replay of the same accepting authorization is refused, not silently
    idempotent — the suspension case above is why."""
    authority, arbiter, gateway, evidence = setup("reg5b")
    decision = valid_decision(arbiter, evidence)
    declaration = arbiter.authorize_admission(decision, evidence)
    admitted = evidence.admit(declaration)

    gateway.submit(admitted)
    assert len(gateway.belief) == 1
    # The commitment is retired once used.
    assert (
        authority.verifies_authorization(
            declaration.authorization, subject_record_hash=evidence.record_hash
        )
        is False
    )
    _raises(AdmissionAuthorityError, gateway.submit, admitted)
    # The already-admitted contribution is untouched by the refusal.
    assert len(gateway.belief) == 1


def test_5c_update_standing_still_works_after_consumption():
    """Withdrawing standing must not require a live authorization.

    Lowering standing is always available — a reviewer must be able to pull a
    result without asking anyone for a token. Raising it is the asymmetric
    half, and needs the full path.
    """
    _authority, arbiter, gateway, evidence = setup("reg5c")
    decision = valid_decision(arbiter, evidence)
    admitted = evidence.admit(arbiter.authorize_admission(decision, evidence))
    gateway.submit(admitted)

    suspended = admitted.suspend("review")
    gateway.update_standing(suspended)          # no authorization needed
    assert len(gateway.belief) == 0

    # ...but the same method cannot put it back.
    _raises(
        AdmissionError,
        gateway.update_standing,
        suspended.reinstate("cleared"),
    )
    assert len(gateway.belief) == 0


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M3.4 — commitment registration audit")
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
        print(f"M3.4 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M3.4 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
