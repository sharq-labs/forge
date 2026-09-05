"""SRIA V0.1 M3.2 — final trust-chain audit.

Runs under pytest, and standalone via
``python -m tests.test_sria_m32_trust_chain``.

The property under test, stated exactly:

    A signed admission declaration is only accepted when it is bound to an
    ArbiterDecision *genuinely issued* through the Arbiter path — not merely
    to a payload that claims one.

Before M3.2 this did not hold. A trusted authority would sign any
hand-constructed ``DecisionBinding`` claiming VALID, and the Gateway checked
only the signature and the claimed verdict. These tests are the regression.
"""

from __future__ import annotations

import json
import sys

from src.engcore.sria import (
    AdmissionAuthority,
    AdmissionAuthorityError,
    AdmissionAuthorityRegistry,
    BeliefUpdateGateway,
)
from src.engcore.sria.admission import AdmissionDeclaration, DecisionBinding
from src.engcore.sria.assurance import (
    Arbiter,
    AssuranceVerdict,
    CriticClass,
    NumericalCritic,
    ObligationSet,
)
from src.engcore.scientific import (
    ConvergenceState,
    ProvenanceRecord,
    Quantity,
    ScientificResult,
)

# Reuse the M3.1 fixtures rather than re-deriving them.
from tests.test_sria_m31_semantics import (  # noqa: E402
    budget,
    charter_obligations,
    clean_run,
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


def fresh_authority(tag: str = "m32") -> AdmissionAuthority:
    """A new authority per test: Arbiters register with it at construction."""
    return AdmissionAuthority(f"arbiter.{tag}", secret=f"secret-{tag}")


def gateway_for(authority: AdmissionAuthority) -> BeliefUpdateGateway:
    return BeliefUpdateGateway(
        authorities=AdmissionAuthorityRegistry([authority])
    )


def valid_flow(authority: AdmissionAuthority, eid: str = "ev-32"):
    """Genuine path: critics -> Arbiter -> VALID decision."""
    result = good_result()
    evidence = evidence_for(result, eid)
    arbiter = Arbiter(authority)
    decision = arbiter.decide(
        decision_id=f"d-{eid}",
        subject_ref=evidence.evidence_id,
        assessments=[numerical_assessment(result)],
        obligations=charter_obligations(
            required_critics=(CriticClass.NUMERICAL,)
        ),
        budget=budget(),
    )
    return arbiter, decision, evidence


# =====================================================================
# D. The genuine path still works (proved first, so A-C mean something)
# =====================================================================

def test_D_genuine_valid_decision_admits():
    authority = fresh_authority("D")
    gateway = gateway_for(authority)
    arbiter, decision, evidence = valid_flow(authority)

    assert decision.verdict is AssuranceVerdict.VALID
    declaration = arbiter.authorize_admission(decision, evidence)

    binding = declaration.authorization
    assert binding is not None
    assert binding.decision_hash == decision.decision_hash
    assert binding.verdict == "valid"
    assert binding.authorization_code, "genuine binding must carry a capability"
    assert authority.verifies_authorization(
        binding, subject_record_hash=evidence.record_hash
    )

    entry = gateway.submit(evidence.admit(declaration))
    assert entry.evidence_id == evidence.evidence_id
    assert len(gateway.belief) == 1
    assert gateway.rejection_log == ()


# =====================================================================
# A. Trusted authority + fabricated DecisionBinding
# =====================================================================

def test_A_fabricated_binding_cannot_be_signed_or_admitted():
    """The strongest supported bypass. It must fail."""
    authority = fresh_authority("A")
    gateway = gateway_for(authority)
    # Make the authority genuinely useful: a real Arbiter exists and is
    # recognised, so this is not "an authority that trusts nobody".
    arbiter, real_decision, evidence = valid_flow(authority, "ev-A")
    assert real_decision.verdict is AssuranceVerdict.VALID
    assert authority.authority_id in gateway.authorities.authority_ids

    fabricated = DecisionBinding(
        decision_id="dec-totally-legit",
        decision_hash="0" * 64,
        verdict="valid",
        policy_id="sria.arbiter",
        policy_version="arbiter/1",
    )
    # 1. The authority refuses to sign it at all.
    _raises(
        AdmissionAuthorityError,
        authority.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=fabricated,
        rationale="fabricated binding, no Arbiter involved",
    )
    assert len(gateway.belief) == 0

    # 2. Even a fabricated code does not verify.
    with_code = DecisionBinding(
        decision_id="dec-totally-legit",
        decision_hash="0" * 64,
        verdict="valid",
        authorization_code="f" * 64,
    )
    assert (
        authority.verifies_authorization(
            with_code, subject_record_hash=evidence.record_hash
        )
        is False
    )
    _raises(
        AdmissionAuthorityError,
        authority.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=with_code,
    )
    assert len(gateway.belief) == 0


def test_A2_gateway_rejects_independently_of_issue():
    """Defence in depth: the Gateway re-verifies rather than trusting issue().

    Simulates a compromised or bypassed signing path by constructing the
    signed declaration directly with a fabricated binding.
    """
    authority = fresh_authority("A2")
    gateway = gateway_for(authority)
    arbiter, _decision, evidence = valid_flow(authority, "ev-A2")

    fabricated = DecisionBinding(
        decision_id="dec-fake",
        decision_hash="1" * 64,
        verdict="valid",
        authorization_code="e" * 64,
    )
    forged = AdmissionDeclaration(
        admitted=True,
        arbiter_id=authority.authority_id,
        subject_record_hash=evidence.record_hash,
        authorization=fabricated,
        issuer_id=authority.authority_id,
    )
    # Sign it with the authority's own key, bypassing issue()'s check.
    signature = authority._sign(forged.signing_payload())  # noqa: SLF001
    signed = AdmissionDeclaration(
        admitted=True,
        arbiter_id=authority.authority_id,
        subject_record_hash=evidence.record_hash,
        authorization=fabricated,
        issuer_id=authority.authority_id,
        issued_signature=signature,
    )
    assert authority.verifies(signed), "signature is genuine by construction"

    _raises(AdmissionAuthorityError, gateway.submit, evidence.admit(signed))
    assert len(gateway.belief) == 0
    assert "authorization code" in gateway.rejection_log[-1].reason


# =====================================================================
# B. Binding copied from another evidence record
# =====================================================================

def test_B_binding_copied_from_another_record_is_rejected():
    """A genuine capability is bound to one record and cannot be moved."""
    authority = fresh_authority("B")
    gateway = gateway_for(authority)

    arbiter_a, decision_a, evidence_a = valid_flow(authority, "ev-B1")
    genuine = arbiter_a.authorize_admission(decision_a, evidence_a)
    assert genuine.authorization.authorization_code

    # A different evidence record, same claim shape.
    evidence_b = evidence_for(good_result("res-b"), "ev-B2")
    assert evidence_b.record_hash != evidence_a.record_hash

    # The stolen binding does not verify against the other record.
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

    # And the whole declaration cannot be replayed either: Evidence.admit
    # refuses a declaration issued for a different record.
    _raises(Exception, evidence_b.admit, genuine)
    assert len(gateway.belief) == 0


def test_B2_arbiter_will_not_authorize_a_mismatched_record():
    authority = fresh_authority("B2")
    arbiter, decision, evidence_a = valid_flow(authority, "ev-B3")
    evidence_b = evidence_for(good_result("res-b2"), "ev-B4")
    _raises(ValueError, arbiter.authorize_admission, decision, evidence_b)


# =====================================================================
# C. Genuine but non-accepting decisions
# =====================================================================

def test_C_inconclusive_and_invalid_decisions_cannot_admit():
    authority = fresh_authority("C")
    gateway = gateway_for(authority)
    arbiter = Arbiter(authority)
    result = good_result()
    evidence = evidence_for(result, "ev-C")

    # Genuine INCONCLUSIVE (no obligations declared).
    inconclusive = arbiter.decide(
        decision_id="d-inc",
        subject_ref=evidence.evidence_id,
        assessments=[numerical_assessment(result)],
        obligations=ObligationSet(campaign_id="none"),
        budget=budget(),
    )
    assert inconclusive.verdict is AssuranceVerdict.INCONCLUSIVE

    # Genuine INVALID (demonstrated non-convergence).
    failed = ScientificResult(
        result_id="res-failed",
        values={"V": Quantity(1.0, "volt")},
        provenance=ProvenanceRecord(run_id="r"),
        convergence=ConvergenceState.FAILED,
    )
    invalid = arbiter.decide(
        decision_id="d-inv",
        subject_ref=evidence.evidence_id,
        assessments=[
            NumericalCritic().assess(
                failed,
                assessment_id="as-f",
                budget=budget(),
                run_outcome=clean_run(),
            )
        ],
        obligations=charter_obligations(
            required_critics=(CriticClass.NUMERICAL,)
        ),
        budget=budget(),
    )
    assert invalid.verdict is AssuranceVerdict.INVALID

    for decision in (inconclusive, invalid):
        declaration = arbiter.authorize_admission(decision, evidence)
        # A non-VALID decision yields a declining declaration...
        assert declaration.admitted is False
        # ...and it cannot be flipped: the verdict is inside the signature.
        _raises(Exception, gateway.submit, evidence.admit(declaration))

    assert len(gateway.belief) == 0


def test_C2_cannot_relabel_a_non_valid_decision_as_valid():
    """Copying a real code onto a VALID-claiming binding fails.

    The code covers the verdict, so a capability issued for INCONCLUSIVE
    cannot be re-presented as authorizing VALID.
    """
    authority = fresh_authority("C2")
    gateway = gateway_for(authority)
    arbiter = Arbiter(authority)
    result = good_result()
    evidence = evidence_for(result, "ev-C2")

    inconclusive = arbiter.decide(
        decision_id="d-inc2",
        subject_ref=evidence.evidence_id,
        assessments=[numerical_assessment(result)],
        obligations=ObligationSet(campaign_id="none"),
        budget=budget(),
    )
    declining = arbiter.authorize_admission(inconclusive, evidence)
    stolen_code = (
        declining.authorization.authorization_code
        if declining.authorization
        else ""
    )

    relabelled = DecisionBinding(
        decision_id=inconclusive.decision_id,
        decision_hash=inconclusive.decision_hash,
        verdict="valid",                 # the lie
        authorization_code=stolen_code,  # a genuine code for another verdict
    )
    assert (
        authority.verifies_authorization(
            relabelled, subject_record_hash=evidence.record_hash
        )
        is False
    )
    _raises(
        AdmissionAuthorityError,
        authority.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=relabelled,
    )
    assert len(gateway.belief) == 0


# =====================================================================
# Supporting properties
# =====================================================================

def test_authority_exposes_no_way_to_mint_an_authorization():
    """Holding the authority must not confer the power to authorize."""
    authority = fresh_authority("mint")
    # Verification only — no public production method.
    assert hasattr(authority, "verifies_authorization")
    for forbidden in ("mint_authorization", "make_authorization", "authorize"):
        assert not hasattr(authority, forbidden)


def test_authority_with_no_registered_arbiter_can_admit_nothing():
    authority = fresh_authority("lonely")
    evidence = evidence_for(good_result(), "ev-lonely")
    binding = DecisionBinding(
        decision_id="d", decision_hash="h", verdict="valid",
        authorization_code="c" * 64,
    )
    _raises(
        AdmissionAuthorityError,
        authority.issue,
        admitted=True,
        subject_record_hash=evidence.record_hash,
        authorization=binding,
    )


def test_declining_declarations_need_no_authorization():
    """Refusal must stay cheap: declining does not require a capability."""
    authority = fresh_authority("decline")
    evidence = evidence_for(good_result(), "ev-decline")
    declined = authority.issue(
        admitted=False,
        subject_record_hash=evidence.record_hash,
        rationale="not admitted",
    )
    assert declined.admitted is False
    assert declined.is_signed


def test_authorization_survives_serialization():
    authority = fresh_authority("ser")
    arbiter, decision, evidence = valid_flow(authority, "ev-ser")
    declaration = arbiter.authorize_admission(decision, evidence)

    reloaded = AdmissionDeclaration.from_dict(
        json.loads(json.dumps(declaration.to_dict()))
    )
    assert reloaded == declaration
    assert reloaded.authorization.authorization_code == (
        declaration.authorization.authorization_code
    )
    assert authority.verifies(reloaded)
    assert authority.verifies_authorization(
        reloaded.authorization, subject_record_hash=evidence.record_hash
    )

    gateway = gateway_for(authority)
    gateway.submit(evidence.admit(reloaded))
    assert len(gateway.belief) == 1


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M3.2 — final trust-chain audit")
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
        print(f"M3.2 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M3.2 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
