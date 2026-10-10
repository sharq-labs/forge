"""Big Rock 1 -- issuer-bound scientific authority: hostile tests.

Every attack must end in REFUSE / UNKNOWN / INVALID, never in silent admission.  The ledger and keys here are TEST
profile / TEST class (``EphemeralKeyProvider``); the production-profile checks are their own tests.
"""

from __future__ import annotations

import hashlib
import json
import os

import pytest

from engcore.authority import (
    Attestation, AuthorityLedger, AuthorityRefused, DirectoryKeyProvider, EphemeralKeyProvider, FileLedgerStore, MemoryLedgerStore,
    Role, TrustAnchor, generate_key_files, verify_evidence,
)
from engcore.claims.attestation import attest_receipt, attest_record
from engcore.claims.credibility_vector import (
    UNKNOWN, ClaimNode, DecisionRequirement, Factor, FactorClaim, RiskClass, assess_credibility, record_digest,
)
from engcore.credibility.evidence_graph import EvidenceAuthority as A, EvidenceEdge, EvidenceGraph, EvidenceNode, EvidenceRelation as R
from engcore.scientific.results.validation import ValidationCheck, ValidationLevel as VL, ValidationOutcome
from engcore.system_runtime.records import ApplicabilityReport
from tests.authority_helpers import World, receipt_for

CTX = hashlib.sha256(b"decision-context").hexdigest()
OTHER = hashlib.sha256(b"other-context").hexdigest()


def _h(s):
    return hashlib.sha256(s.encode()).hexdigest()


RESULT = _h("result")
CONV = ValidationCheck("conv", ValidationOutcome.PASS, establishes=VL.NUMERICALLY_CONVERGED, residual=0.001, tolerance=0.01,
                       evidence=("richardson:3-level",))
WITHIN = ApplicabilityReport("domain.check", "within", RESULT, "inside the declared envelope")


def graph(*records, subject_digest=RESULT):
    nodes = [EvidenceNode("result", A.SIMULATION, subject_digest, "src:result", applicability=CTX)]
    for i, r in enumerate(records):
        nodes.append(EvidenceNode(f"n{i}", A.SIMULATION if isinstance(r, ValidationCheck) else A.ANALYTICAL, record_digest(r), f"src:n{i}",
                                  applicability=CTX))
    return EvidenceGraph(tuple(nodes), tuple(EvidenceEdge(f"n{i}", "result", R.SUPPORTS) for i in range(len(records))))


LOW = [FactorClaim(Factor.VERIFICATION, 1, ("n0",), VL.NUMERICALLY_CONVERGED.value)]


def verification_level(ledger, g=None, ctx=CTX):
    g = g or graph(CONV)
    rep = assess_credibility(ClaimNode("c", tuple(LOW), subject_id="result"), g, DecisionRequirement("d", ctx, RiskClass.LOW),
                             validation_checks=(CONV,), authority=ledger)
    return rep.vector.level(Factor.VERIFICATION), rep


def test_the_issuer_bound_path_admits_a_correctly_attested_record_and_nothing_else():
    w = World()
    assert verification_level(w.ledger)[0] == UNKNOWN                       # caller-supplied, unattested: backs nothing
    w.attest(CONV, RESULT, CTX)
    level, rep = verification_level(w.ledger)
    assert level == 1 and rep.issuer_bound and rep.authority_anchor["head"] == w.ledger.head
    unattested = assess_credibility(ClaimNode("c", tuple(LOW), subject_id="result"), graph(CONV), DecisionRequirement("d", CTX, RiskClass.LOW),
                                    validation_checks=(CONV,))
    assert not unattested.requirement_met and not unattested.issuer_bound and any("UNATTESTED" in n for n in unattested.notes)


def test_forged_and_unknown_issuers_never_reach_the_ledger():
    w = World()
    rogue = EphemeralKeyProvider().signer("rogue")
    receipt = w.receipt(RESULT, CTX)
    att = Attestation("validation_check", "validation_check/1", CONV.to_dict(), RESULT, CTX, Role.NUMERICAL_VERIFICATION,
                      receipt.record_digest, "y")
    with pytest.raises(AuthorityRefused, match="unknown issuer"):
        w.ledger.attest(rogue, "nobody", att)
    with pytest.raises(AuthorityRefused, match="not 'ver'.s active key"):          # a registered id, the wrong key
        w.ledger.attest(rogue, "ver", att)
    assert verify_evidence(w.ledger, record_kind="validation_check", record_digest=record_digest(CONV), subject_digest=RESULT,
                           context_digest=CTX, roles=[Role.NUMERICAL_VERIFICATION])[0] is None


def test_wrong_role_wrong_result_wrong_receipt_and_wrong_context_are_refused():
    w = World()
    with pytest.raises(AuthorityRefused, match="not authorized for role"):          # the VALIDATION issuer has no verification role
        attest_record(w.ledger, w.signer("val"), "val", CONV, receipt=w.receipt(RESULT, CTX), subject_output="y", context_digest=CTX,
                      role=Role.NUMERICAL_VERIFICATION)
    # an issuer attests the check as VALIDATION: the ledger admits it (it holds that role) -- but it cannot back VERIFICATION
    attest_record(w.ledger, w.signer("val"), "val", CONV, receipt=w.receipt(RESULT, CTX), subject_output="y", context_digest=CTX,
                  role=Role.VALIDATION)
    assert verification_level(w.ledger)[0] == UNKNOWN
    w2 = World()
    w2.attest(CONV, _h("another result"), CTX)                                     # about another result
    assert verification_level(w2.ledger)[0] == UNKNOWN
    w3 = World()
    w3.attest(CONV, RESULT, OTHER)                                                 # in another context
    assert verification_level(w3.ledger)[0] == UNKNOWN
    with pytest.raises(AuthorityRefused, match="no output"):                     # the receipt does not contain the output
        attest_record(w.ledger, w.signer("ver"), "ver", CONV, receipt=w.receipt(RESULT, CTX), subject_output="T", context_digest=CTX,
                      role=Role.NUMERICAL_VERIFICATION)


def test_a_receipt_not_attested_by_an_executor_backs_nothing():
    w = World()
    w.ledger.set_roles(w.root, "ver", [Role.NUMERICAL_VERIFICATION, Role.EXECUTOR])
    receipt = attest_receipt(w.ledger, w.signer("ver"), "ver", receipt_for(RESULT), context_digest=CTX)
    attest_record(w.ledger, w.signer("ver"), "ver", CONV, receipt=receipt, subject_output="y", context_digest=CTX,
                  role=Role.NUMERICAL_VERIFICATION)
    level, rep = verification_level(w.ledger)                                      # self-issued: it executed the result
    assert level == UNKNOWN and any("self-issued" in n for n in rep.notes)
    w2 = World()                                                                    # an EXECUTOR that loses the role later: history stands
    r2 = w2.receipt(RESULT, CTX)
    w2.ledger.set_roles(w2.root, "exec", [])
    attest_record(w2.ledger, w2.signer("ver"), "ver", CONV, receipt=r2, subject_output="y", context_digest=CTX, role=Role.NUMERICAL_VERIFICATION)
    assert verification_level(w2.ledger)[0] == 1


def test_revocation_rotation_and_history():
    w = World()
    first = w.attest(CONV, RESULT, CTX)
    w.ledger.revoke(w.root, "ver", "key compromise drill")
    later = ValidationCheck("conv2", ValidationOutcome.PASS, establishes=VL.NUMERICALLY_CONVERGED, residual=0.002, tolerance=0.01,
                            evidence=("richardson:3-level",))
    with pytest.raises(AuthorityRefused, match="revoked"):
        w.attest(later, RESULT, CTX)
    assert verification_level(w.ledger)[0] == 1                                    # issued BEFORE revocation: still verifiable
    assert w.ledger.attestations(record_digest=first.record_digest)[0].sequence < len(w.ledger.events())
    with pytest.raises(AuthorityRefused, match="revocation is final"):
        w.ledger.set_roles(w.root, "ver", [Role.NUMERICAL_VERIFICATION])
    w2 = World()
    old_signer = w2.signer("ver")
    new_signer = w2.keys.new_signer("ver")
    w2.ledger.rotate_key(w2.root, "ver", new_signer.public_hex, key_class="test")
    receipt = w2.receipt(RESULT, CTX)
    with pytest.raises(AuthorityRefused, match="active key"):                      # the retired key signs nothing new
        attest_record(w2.ledger, old_signer, "ver", CONV, receipt=receipt, subject_output="y", context_digest=CTX,
                      role=Role.NUMERICAL_VERIFICATION)
    attest_record(w2.ledger, new_signer, "ver", CONV, receipt=receipt, subject_output="y", context_digest=CTX, role=Role.NUMERICAL_VERIFICATION)
    assert verification_level(w2.ledger)[0] == 1


def test_persistence_restart_and_tamper_detection(tmp_path):
    keys = EphemeralKeyProvider()
    root = keys.signer("root")
    path = tmp_path / "authority.jsonl"
    led = AuthorityLedger.create(FileLedgerStore(path), ledger_id="campaign", profile="test", root=root)
    for issuer, roles in (("exec", [Role.EXECUTOR]), ("ver", [Role.NUMERICAL_VERIFICATION])):
        led.register_issuer(root, issuer, keys.signer(issuer).public_hex, key_class="test", roles=roles)
    receipt = attest_receipt(led, keys.signer("exec"), "exec", receipt_for(RESULT), context_digest=CTX)
    attest_record(led, keys.signer("ver"), "ver", CONV, receipt=receipt, subject_output="y", context_digest=CTX, role=Role.NUMERICAL_VERIFICATION)
    anchor = led.anchor()
    saved = json.dumps(anchor.to_dict())                                           # what the consumer keeps
    reopened = AuthorityLedger.open(FileLedgerStore(path), anchor=TrustAnchor.from_dict(json.loads(saved)))
    assert verification_level(reopened)[0] == 1 and reopened.head == led.head
    lines = path.read_text().splitlines()

    def opened(new_lines, anchor=anchor):
        p2 = tmp_path / "tampered.jsonl"
        p2.write_text("\n".join(new_lines) + "\n")
        return AuthorityLedger.open(FileLedgerStore(p2), anchor=anchor)
    with pytest.raises(AuthorityRefused, match="truncated or rolled back"):
        opened(lines[:-1])                                                          # truncation / negative-entry drop
    with pytest.raises(AuthorityRefused, match="sequence"):
        opened([lines[0], lines[2], lines[1]] + lines[3:])                          # reorder
    ev = json.loads(lines[1])
    ev["body"]["public"] = EphemeralKeyProvider().signer("x").public_hex           # key substitution in the registry
    with pytest.raises(AuthorityRefused, match="root key"):
        opened([lines[0], json.dumps(ev)] + lines[2:])
    att = json.loads(lines[-1])
    att["body"]["attestation"]["subject_digest"] = _h("mutated")                   # rewrite what was attested
    with pytest.raises(AuthorityRefused):
        opened(lines[:-1] + [json.dumps(att)])
    # another ledger under the same id (a different root), restored in place of the real one
    other = AuthorityLedger.create(MemoryLedgerStore(), ledger_id="campaign", profile="test", root=EphemeralKeyProvider().signer("root"))
    with pytest.raises(AuthorityRefused, match="another ledger"):
        AuthorityLedger.open(other._store, anchor=TrustAnchor(anchor.ledger_id, "test", anchor.root_key_id, 0, other.head))
    # a stale anchor still opens a longer ledger (append-only growth is fine) but an older ledger never satisfies a newer anchor
    old_anchor = TrustAnchor(anchor.ledger_id, "test", anchor.root_key_id, 1, AuthorityLedger.open(FileLedgerStore(path), anchor=anchor).events()[1].digest)
    assert AuthorityLedger.open(FileLedgerStore(path), anchor=old_anchor).length == len(lines)


def test_negative_records_are_read_from_the_ledger_whatever_the_caller_supplies():
    w = World()
    w.attest(CONV, RESULT, CTX)
    w.attest(WITHIN, RESULT, CTX)
    outside = ApplicabilityReport("domain.check2", "outside", RESULT, "temperature above the fitted range")
    w.attest(outside, RESULT, CTX)
    claims = LOW + [FactorClaim(Factor.APPLICABILITY, 1, ("n1",), "applicability")]
    rep = assess_credibility(ClaimNode("c", tuple(claims), subject_id="result"), graph(CONV, WITHIN), DecisionRequirement("d", CTX, RiskClass.LOW),
                             validation_checks=(CONV,), applicability_reports=(WITHIN,), authority=w.ledger)   # 'outside' NOT supplied
    assert not rep.requirement_met and any(d.kind == "outside_domain" for d in rep.open_defeaters)


def test_a_copied_record_or_a_mutated_result_backs_nothing():
    w = World()
    w.attest(CONV, RESULT, CTX)
    assert verification_level(w.ledger, g=graph(CONV, subject_digest=_h("result, mutated after issuance")))[0] == UNKNOWN
    assert verification_level(w.ledger, ctx=OTHER, g=EvidenceGraph(
        tuple(EvidenceNode(n.evidence_id, n.authority, n.content_digest, n.source, applicability=OTHER) for n in graph(CONV).nodes),
        graph(CONV).edges))[0] == UNKNOWN


def test_profiles_and_key_material_placement(tmp_path):
    test_root = EphemeralKeyProvider().signer("root")
    with pytest.raises(AuthorityRefused, match="production ledger's root"):
        AuthorityLedger.create(MemoryLedgerStore(), ledger_id="prod", profile="production", root=test_root)
    keydir = tmp_path / "keys"
    generate_key_files(keydir, "root")
    generate_key_files(keydir, "exec")
    prov = DirectoryKeyProvider(keydir)
    prod = AuthorityLedger.create(MemoryLedgerStore(), ledger_id="prod", profile="production", root=prov.signer("root"))
    with pytest.raises(AuthorityRefused, match="refuses test key material"):
        prod.register_issuer(prov.signer("root"), "t", EphemeralKeyProvider().signer("t").public_hex, key_class="test", roles=[Role.EXECUTOR])
    prod.register_issuer(prov.signer("root"), "exec", prov.signer("exec").public_hex, key_class="production", roles=[Role.EXECUTOR])
    with pytest.raises(AuthorityRefused, match="production is required"):
        AuthorityLedger.open(World().store, anchor=World().ledger.anchor(), require_profile="production")
    with pytest.raises(AuthorityRefused, match="exists"):
        generate_key_files(keydir, "root")                                           # never overwritten
    os.chmod(keydir / "exec.ed25519.pem", 0o644)
    with pytest.raises(AuthorityRefused, match="group/others"):
        prov.signer("exec")
    repo_dir = os.path.join(os.path.dirname(__file__), "..", "..", "keys-must-not-live-here")
    os.makedirs(repo_dir, mode=0o700, exist_ok=True)
    try:
        with pytest.raises(AuthorityRefused, match="inside the repository"):
            DirectoryKeyProvider(repo_dir)
    finally:
        os.rmdir(repo_dir)


def test_the_authority_layer_imports_nothing_else_from_engcore():
    import ast
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2] / "src" / "engcore" / "authority"
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.level <= 1 and not (node.module or "").startswith("engcore"), (path.name, node.module, node.level)
            elif isinstance(node, ast.Import):
                assert not any(a.name.startswith("engcore") for a in node.names), path.name
