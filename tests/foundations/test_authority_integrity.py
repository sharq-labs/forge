"""Big Rock 1 -- issuer-bound scientific authority: hostile tests (incl. the checkpoint-A review).

Every attack must end in REFUSE / UNKNOWN / INVALID, never in silent admission.  The ledgers and keys here are TEST
profile / TEST class (``EphemeralKeyProvider``) and are admitted only in explicit test mode; the production-profile
checks are their own tests.
"""

from __future__ import annotations

import hashlib
import json
import os

import pytest

from engcore.authority import (
    Attestation,
    AuthorityLedger,
    AuthorityRefused,
    DirectoryKeyProvider,
    EphemeralKeyProvider,
    FileLedgerStore,
    MemoryLedgerStore,
    Role,
    Signer,
    TrustAnchor,
    generate_key_files,
    verify_evidence,
)
from engcore.claims.attestation import attest_receipt, attest_record
from engcore.claims.credibility_vector import (
    UNKNOWN,
    ClaimNode,
    CredibilityRefused,
    DecisionRequirement,
    Factor,
    FactorClaim,
    RiskClass,
    assess_credibility,
    record_digest,
)
from engcore.credibility.evidence_graph import EvidenceAuthority as A
from engcore.credibility.evidence_graph import EvidenceEdge, EvidenceGraph, EvidenceNode
from engcore.credibility.evidence_graph import EvidenceRelation as R
from engcore.scientific.results.validation import ValidationCheck, ValidationOutcome
from engcore.scientific.results.validation import ValidationLevel as VL
from engcore.sria.assurance.uncertainty_budget import ChannelEntry, ChannelState
from engcore.sria.uncertainty import UncertaintyChannel as UC
from engcore.system_runtime.records import ApplicabilityReport
from tests.authority_helpers import World, receipt_for

CTX = hashlib.sha256(b"decision-context").hexdigest()
OTHER = hashlib.sha256(b"other-context").hexdigest()


def _h(s):
    return hashlib.sha256(s.encode()).hexdigest()


RESULT = _h("result")
CONV = ValidationCheck("conv", ValidationOutcome.PASS, establishes=VL.NUMERICALLY_CONVERGED, residual=0.001, tolerance=0.01,
                       evidence=("richardson:3-level",))
FAILED = ValidationCheck("conv-fine", ValidationOutcome.FAIL, establishes=VL.NUMERICALLY_CONVERGED, residual=0.5, tolerance=0.01,
                         evidence=("richardson:3-level",))
WITHIN = ApplicabilityReport("domain.check", "within", RESULT, "inside the declared envelope")


def graph(*records, subject_digest=RESULT, subject_id="result", ctx=CTX):
    nodes = [EvidenceNode(subject_id, A.SIMULATION, subject_digest, "src:result", applicability=ctx)]
    for i, r in enumerate(records):
        nodes.append(EvidenceNode(f"n{i}", A.SIMULATION if isinstance(r, ValidationCheck) else A.ANALYTICAL, record_digest(r), f"src:n{i}",
                                  applicability=ctx))
    return EvidenceGraph(tuple(nodes), tuple(EvidenceEdge(f"n{i}", subject_id, R.SUPPORTS) for i in range(len(records))))


LOW = [FactorClaim(Factor.VERIFICATION, 1, ("n0",), VL.NUMERICALLY_CONVERGED.value)]


def assess(w, g=None, ctx=CTX, claims=LOW, subject_id="result", **kw):
    g = g or graph(CONV)
    kw = {**w.assess_kwargs(), **kw} if isinstance(w, World) else kw
    return assess_credibility(ClaimNode("c", tuple(claims), subject_id=subject_id), g, DecisionRequirement("d", ctx, RiskClass.LOW),
                              validation_checks=(CONV,), **kw)


def verification_level(w, **kw):
    rep = assess(w, **kw)
    return rep.vector.level(Factor.VERIFICATION), rep


def test_the_issuer_bound_path_admits_a_correctly_attested_record_and_nothing_else():
    w = World()
    assert verification_level(w)[0] == UNKNOWN                              # caller-supplied, unattested: backs nothing
    w.attest(CONV, RESULT, CTX)
    level, rep = verification_level(w)
    assert level == 1 and rep.issuer_bound and rep.test_mode and rep.authority_anchor["head"] == w.ledger.head
    unattested = assess(None)
    assert not unattested.requirement_met_in_test_mode and not unattested.issuer_bound and any("UNATTESTED" in n for n in unattested.notes)


def test_an_unopened_unanchored_or_foreign_ledger_is_refused():                 # checkpoint A B1
    w = World()
    w.attest(CONV, RESULT, CTX)
    with pytest.raises(CredibilityRefused, match="pinned TrustAnchor"):
        assess(None, authority=w.opened()[0])
    with pytest.raises(CredibilityRefused, match="not opened against an anchor"):
        assess(None, authority=w.ledger, trust_anchor=w.ledger.anchor(), allow_test_profile=True)   # created, never opened
    attacker = World(ledger_id="test-ledger")                               # same id, the attacker's own root and issuers
    attacker.attest(CONV, RESULT, CTX)
    led, _ = attacker.opened()
    with pytest.raises(CredibilityRefused, match="not the consumer's anchored ledger"):
        assess(None, authority=led, trust_anchor=w.ledger.anchor(), allow_test_profile=True)
    led, anchor = w.opened()
    rep = assess(None, authority=led, trust_anchor=anchor)                  # a TEST ledger without explicit test mode
    assert rep.vector.level(Factor.VERIFICATION) == 1 and not rep.issuer_bound and not rep.requirement_met_in_test_mode
    assert any("TEST-PROFILE" in n for n in rep.notes) and rep.inputs_digest != assess(w).inputs_digest


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


def test_a_key_is_registered_only_by_its_holder_in_its_providers_class(tmp_path):                 # checkpoint A H1
    with pytest.raises(AuthorityRefused, match="minted by a key provider"):
        Signer("root", "production", "00" * 32, object())
    w = World()
    t = EphemeralKeyProvider().signer("t")
    forged = dict(t.possession(w.ledger_id, "t"), key_class="production")         # relabel a test key
    with pytest.raises(AuthorityRefused, match="proof of possession does not verify"):
        w.ledger.register_issuer(w.root, "t", forged, roles=[Role.VALIDATION])
    other_holder = EphemeralKeyProvider().signer("o").possession(w.ledger_id, "t")
    with pytest.raises(AuthorityRefused, match="proof of possession"):             # a possession made for another identity
        w.ledger.register_issuer(w.root, "t2", other_holder, roles=[Role.VALIDATION])
    keydir = tmp_path / "keys"
    for name in ("root", "exec"):
        generate_key_files(keydir, name)
    prov = DirectoryKeyProvider(keydir)
    prod = AuthorityLedger.create(MemoryLedgerStore(), ledger_id="prod", profile="production", root=prov.signer("root"))
    with pytest.raises(AuthorityRefused, match="refuses test key material"):
        prod.register_issuer(prov.signer("root"), "t", t.possession("prod", "t"), roles=[Role.EXECUTOR])
    prod.register_issuer(prov.signer("root"), "exec", prov.signer("exec").possession("prod", "exec"), roles=[Role.EXECUTOR])
    with pytest.raises(AuthorityRefused, match="production ledger's root"):
        AuthorityLedger.create(MemoryLedgerStore(), ledger_id="prod2", profile="production", root=EphemeralKeyProvider().signer("r"))


def test_wrong_role_wrong_result_wrong_receipt_and_wrong_context_are_refused():
    w = World()
    with pytest.raises(AuthorityRefused, match="not authorized for role"):          # the VALIDATION issuer has no verification role
        attest_record(w.ledger, w.signer("val"), "val", CONV, receipt=w.receipt(RESULT, CTX), subject_output="y", context_digest=CTX,
                      role=Role.NUMERICAL_VERIFICATION)
    attest_record(w.ledger, w.signer("val"), "val", CONV, receipt=w.receipt(RESULT, CTX), subject_output="y", context_digest=CTX,
                  role=Role.VALIDATION)                                            # admitted as VALIDATION -- cannot back VERIFICATION
    assert verification_level(w)[0] == UNKNOWN
    w2 = World()
    w2.attest(CONV, _h("another result"), CTX)                                     # about another result
    assert verification_level(w2)[0] == UNKNOWN
    w3 = World()
    w3.attest(CONV, RESULT, OTHER)                                                 # in another context
    assert verification_level(w3)[0] == UNKNOWN
    with pytest.raises(AuthorityRefused, match="no output"):
        attest_record(w.ledger, w.signer("ver"), "ver", CONV, receipt=w.receipt(RESULT, CTX), subject_output="T", context_digest=CTX,
                      role=Role.NUMERICAL_VERIFICATION)


def test_self_issued_support_is_refused_from_any_executor_of_the_receipt():                        # incl. checkpoint A L1
    w = World()
    w.ledger.set_roles(w.root, "ver", [Role.NUMERICAL_VERIFICATION, Role.EXECUTOR])
    receipt = attest_receipt(w.ledger, w.signer("ver"), "ver", receipt_for(RESULT), context_digest=CTX)
    attest_record(w.ledger, w.signer("ver"), "ver", CONV, receipt=receipt, subject_output="y", context_digest=CTX,
                  role=Role.NUMERICAL_VERIFICATION)
    level, rep = verification_level(w)
    assert level == UNKNOWN and any("self-issued" in n for n in rep.notes)
    w2 = World()                                                                    # 'exec' attests first; 'ver' re-attests as executor later
    r2 = w2.receipt(RESULT, CTX)
    w2.ledger.set_roles(w2.root, "ver", [Role.NUMERICAL_VERIFICATION, Role.EXECUTOR])
    attest_receipt(w2.ledger, w2.signer("ver"), "ver", receipt_for(RESULT), context_digest=OTHER)
    attest_record(w2.ledger, w2.signer("ver"), "ver", CONV, receipt=r2, subject_output="y", context_digest=CTX, role=Role.NUMERICAL_VERIFICATION)
    assert verification_level(w2)[0] == UNKNOWN
    w3 = World()                                                                    # an EXECUTOR that loses the role later: history stands
    r3 = w3.receipt(RESULT, CTX)
    w3.ledger.set_roles(w3.root, "exec", [])
    attest_record(w3.ledger, w3.signer("ver"), "ver", CONV, receipt=r3, subject_output="y", context_digest=CTX, role=Role.NUMERICAL_VERIFICATION)
    assert verification_level(w3)[0] == 1


def test_negative_records_cap_and_defeat_even_from_the_results_own_executor():                    # checkpoint A M1, L8
    w = World()
    w.attest(CONV, RESULT, CTX)
    w.attest(FAILED, RESULT, CTX)                                                   # one failing check beside the passing one
    level, rep = verification_level(w)
    assert level == UNKNOWN and any("capped at UNKNOWN by attested fail check" in n for n in rep.notes)
    w2 = World()
    entry_known = ChannelEntry(UC.MODEL_FORM, ChannelState.KNOWN, __import__("engcore.scientific.results.uncertainty", fromlist=["x"]).Uncertainty(
        kind="standard", standard_uncertainty=__import__("engcore.scientific.units.quantity", fromlist=["x"]).Quantity(0.01, "volt"),
        method="m", source_kind="model_form"), source="t")
    entry_unknown = ChannelEntry(UC.MODEL_FORM, ChannelState.UNKNOWN)
    w2.attest(entry_known, RESULT, CTX)
    w2.attest(entry_unknown, RESULT, CTX)
    g = EvidenceGraph((EvidenceNode("result", A.SIMULATION, RESULT, "s", applicability=CTX),
                       EvidenceNode("mf", A.EXPERIMENT, record_digest(entry_known), "s:mf", applicability=CTX)),
                      (EvidenceEdge("mf", "result", R.SUPPORTS),))
    rep = assess(w2, g=g, claims=[FactorClaim(Factor.MODEL_FORM_UQ, 1, ("mf",), "model_form")])
    assert rep.vector.level(Factor.MODEL_FORM_UQ) == UNKNOWN and any("UNKNOWN model_form entry" in n for n in rep.notes)
    w3 = World()
    w3.attest(CONV, RESULT, CTX)
    w3.ledger.set_roles(w3.root, "exec", [Role.EXECUTOR, Role.APPLICABILITY])
    outside = ApplicabilityReport("own.check", "outside", RESULT, "the executor's own range check")
    attest_record(w3.ledger, w3.signer("exec"), "exec", outside, receipt=w3.receipt(RESULT, CTX), subject_output="y", context_digest=CTX,
                  role=Role.APPLICABILITY)
    rep = assess(w3)
    assert not rep.requirement_met_in_test_mode and any(d.kind == "outside_domain" for d in rep.open_defeaters)


def test_an_attested_falsification_follows_the_result_not_the_node_name():                        # checkpoint A H2
    from engcore.claims.redteam import (
        AttackDimension,
        AttackKind,
        AttackPlan,
        AttackSpace,
        ClaimSubject,
        Route,
        RouteResult,
        Sense,
        run_red_team,
    )
    x = AttackDimension("F", AttackKind.INPUT_PARAMETER, "spec", low=0.0, high=1.0, unit="1")
    space = AttackSpace("result", (x,))
    broken = (Route("a", "f", 1, lambda p: RouteResult(5.0)), Route("b", "g", 2, lambda p: RouteResult(5.0)))
    falsified = run_red_team(ClaimSubject("result", "y", "1", Sense.AT_MOST, 1.0, broken, "a"), space, AttackPlan(space.digest, 200, "s"))
    w = World()
    w.attest(CONV, RESULT, CTX)
    w.attest(falsified, RESULT, CTX)
    rep = assess(w, g=graph(CONV, subject_id="result#renamed"), subject_id="result#renamed")
    assert not rep.requirement_met_in_test_mode and any(d.kind == "red_team_falsified" for d in rep.open_defeaters)


def test_attested_records_cannot_be_edited_in_memory():                                            # checkpoint A M2
    w = World()
    rec = w.receipt(RESULT, CTX)
    with pytest.raises((TypeError, AttributeError)):
        rec.attestation.record["output_digests"].append(["z", OTHER])
    with pytest.raises(TypeError):
        rec.attestation.record["status"] = "failed"
    copy = rec.attestation.record_dict()
    copy["output_digests"].append(["z", OTHER])                                     # a copy: changes nothing attested
    with pytest.raises(AuthorityRefused, match="no output"):
        attest_record(w.ledger, w.signer("ver"), "ver", CONV, receipt=rec, subject_output="z", context_digest=CTX,
                      role=Role.NUMERICAL_VERIFICATION)


def test_revocation_rotation_and_history():
    w = World()
    first = w.attest(CONV, RESULT, CTX)
    w.ledger.revoke(w.root, "ver", "key compromise drill")
    later = ValidationCheck("conv2", ValidationOutcome.PASS, establishes=VL.NUMERICALLY_CONVERGED, residual=0.002, tolerance=0.01,
                            evidence=("richardson:3-level",))
    with pytest.raises(AuthorityRefused, match="revoked"):
        w.attest(later, RESULT, CTX)
    assert verification_level(w)[0] == 1                                            # issued BEFORE revocation: still verifiable
    assert w.ledger.attestations(record_digest=first.record_digest)[0].sequence < len(w.ledger.events())
    with pytest.raises(AuthorityRefused, match="revocation is final"):
        w.ledger.set_roles(w.root, "ver", [Role.NUMERICAL_VERIFICATION])
    w2 = World()
    old_signer = w2.signer("ver")
    new_signer = w2.keys.new_signer("ver")
    w2.ledger.rotate_key(w2.root, "ver", new_signer.possession(w2.ledger_id, "ver"))
    receipt = w2.receipt(RESULT, CTX)
    with pytest.raises(AuthorityRefused, match="active key"):                       # the retired key signs nothing new
        attest_record(w2.ledger, old_signer, "ver", CONV, receipt=receipt, subject_output="y", context_digest=CTX,
                      role=Role.NUMERICAL_VERIFICATION)
    attest_record(w2.ledger, new_signer, "ver", CONV, receipt=receipt, subject_output="y", context_digest=CTX, role=Role.NUMERICAL_VERIFICATION)
    assert verification_level(w2)[0] == 1


def _file_ledger(tmp_path):
    keys = EphemeralKeyProvider()
    root = keys.signer("root")
    path = tmp_path / "authority.jsonl"
    led = AuthorityLedger.create(FileLedgerStore(path), ledger_id="campaign", profile="test", root=root)
    for issuer, roles in (("exec", [Role.EXECUTOR]), ("ver", [Role.NUMERICAL_VERIFICATION])):
        led.register_issuer(root, issuer, keys.signer(issuer).possession("campaign", issuer), roles=roles)
    receipt = attest_receipt(led, keys.signer("exec"), "exec", receipt_for(RESULT), context_digest=CTX)
    attest_record(led, keys.signer("ver"), "ver", CONV, receipt=receipt, subject_output="y", context_digest=CTX, role=Role.NUMERICAL_VERIFICATION)
    return keys, path, led


def test_persistence_restart_and_tamper_detection(tmp_path):
    keys, path, led = _file_ledger(tmp_path)
    anchor = led.anchor()
    saved = json.dumps(anchor.to_dict())                                           # what the consumer keeps
    pinned = TrustAnchor.from_dict(json.loads(saved))
    reopened = AuthorityLedger.open(FileLedgerStore(path), anchor=pinned)
    assert verification_level(None, authority=reopened, trust_anchor=pinned, allow_test_profile=True)[0] == 1 and reopened.head == led.head
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
    ev["body"]["possession"]["public"] = EphemeralKeyProvider().signer("x").public_hex       # key substitution in the registry
    with pytest.raises(AuthorityRefused, match="root key"):
        opened([lines[0], json.dumps(ev)] + lines[2:])
    att = json.loads(lines[-1])
    att["body"]["attestation"]["subject_digest"] = _h("mutated")                   # rewrite what was attested
    with pytest.raises(AuthorityRefused):
        opened(lines[:-1] + [json.dumps(att)])
    up = json.loads(lines[-1])
    up["signature"] = up["signature"].upper()                                      # a non-canonical spelling of a valid signature
    with pytest.raises(AuthorityRefused):
        opened(lines[:-1] + [json.dumps(up)])
    with pytest.raises(AuthorityRefused, match="body is a mapping|valid ledger event"):
        opened(lines[:1] + ['{"schema": "engcore.authority.ledger_event/1", "ledger_id": "campaign", "sequence": 1, "previous": "x", '
                            '"kind": "register", "body": [], "key_id": "", "signature": ""}'])
    other = AuthorityLedger.create(MemoryLedgerStore(), ledger_id="campaign", profile="test", root=EphemeralKeyProvider().signer("root"))
    with pytest.raises(AuthorityRefused, match="another ledger"):
        AuthorityLedger.open(other._store, anchor=TrustAnchor(anchor.ledger_id, "test", anchor.root_key_id, 0, other.head))


def test_a_second_writer_or_a_failed_append_never_forks_the_ledger(tmp_path):                     # checkpoint A M3
    keys, path, led = _file_ledger(tmp_path)
    a = AuthorityLedger.open(FileLedgerStore(path), anchor=led.anchor())
    b = AuthorityLedger.open(FileLedgerStore(path), anchor=led.anchor())
    a.set_roles(keys.signer("root"), "ver", [Role.NUMERICAL_VERIFICATION])
    with pytest.raises(AuthorityRefused, match="another writer"):
        b.set_roles(keys.signer("root"), "ver", [Role.NUMERICAL_VERIFICATION, Role.VALIDATION])
    assert AuthorityLedger.open(FileLedgerStore(path), anchor=a.anchor()).length == a.length

    class Failing(MemoryLedgerStore):
        def append(self, line, *, expected_lines):
            super().append(line, expected_lines=expected_lines)
            raise OSError("fsync failed after the write")
    w = World()
    w.ledger._store = Failing(w.store.lines)
    with pytest.raises(OSError):
        w.ledger.set_roles(w.root, "ver", [])
    with pytest.raises(AuthorityRefused, match="unusable after a failed append"):
        w.ledger.set_roles(w.root, "ver", [])


def test_negative_records_are_read_from_the_ledger_whatever_the_caller_supplies():
    w = World()
    w.attest(CONV, RESULT, CTX)
    w.attest(WITHIN, RESULT, CTX)
    outside = ApplicabilityReport("domain.check2", "outside", RESULT, "temperature above the fitted range")
    w.attest(outside, RESULT, CTX)
    claims = LOW + [FactorClaim(Factor.APPLICABILITY, 1, ("n1",), "applicability")]
    rep = assess(w, g=graph(CONV, WITHIN), claims=claims, applicability_reports=(WITHIN,))      # 'outside' NOT supplied
    assert not rep.requirement_met_in_test_mode and any(d.kind == "outside_domain" for d in rep.open_defeaters)


def test_a_copied_record_or_a_mutated_result_backs_nothing():
    w = World()
    w.attest(CONV, RESULT, CTX)
    assert verification_level(w, g=graph(CONV, subject_digest=_h("result, mutated after issuance")))[0] == UNKNOWN
    assert verification_level(w, ctx=OTHER, g=graph(CONV, ctx=OTHER))[0] == UNKNOWN


def test_key_material_placement(tmp_path):
    keydir = tmp_path / "keys"
    generate_key_files(keydir, "exec")
    prov = DirectoryKeyProvider(keydir)
    with pytest.raises(AuthorityRefused, match="exists"):
        generate_key_files(keydir, "exec")                                           # never overwritten
    os.chmod(keydir / "exec.ed25519.pem", 0o644)
    with pytest.raises(AuthorityRefused, match="group/others"):
        prov.signer("exec")
    os.chmod(keydir / "exec.ed25519.pem", 0o600)
    os.symlink(keydir / "exec.ed25519.pem", keydir / "alias.ed25519.pem")
    with pytest.raises(AuthorityRefused, match="symbolic link"):
        prov.signer("alias")
    repo_dir = os.path.join(os.path.dirname(__file__), "..", "..", "keys-must-not-live-here")
    with pytest.raises(AuthorityRefused, match="inside the repository"):
        generate_key_files(repo_dir, "x")                                            # refused BEFORE anything is created
    assert not os.path.exists(repo_dir)


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


# ---------------------------------------------------------------------------- checkpoint A re-review


def _failed_balance():
    from engcore.scientific.conservation import BalanceTerm, ConservationBalance
    from engcore.scientific.units.quantity import Quantity
    return ConservationBalance("mass", (BalanceTerm("in", Quantity(10.0, "kilogram / second"), "fm:A"),),
                               (BalanceTerm("out", Quantity(9.0, "kilogram / second"), "fm:B"),),
                               tolerance=Quantity(0.01, "kilogram / second")).to_validation_check()


def test_an_attested_failed_check_without_a_level_caps_its_roles_factors():                       # re-review H-1
    bad = _failed_balance()
    assert bad.outcome is ValidationOutcome.FAIL and bad.establishes is None          # the real producer's shape
    w = World()
    w.attest(CONV, RESULT, CTX)
    assert verification_level(w)[0] == 1
    w.attest(bad, RESULT, CTX, issuer="ver", role=Role.NUMERICAL_VERIFICATION)         # the authorized verifier says: violated
    level, rep = verification_level(w)
    assert level == UNKNOWN and not rep.requirement_met_in_test_mode
    assert any("caps ['independent_routes', 'verification']" in n for n in rep.notes)
    w2 = World()
    w2.attest(CONV, RESULT, CTX)
    w2.attest(bad, RESULT, CTX, issuer="val", role=Role.VALIDATION)                    # a failed oracle comparison: no level
    rep2 = assess(w2)
    assert any("caps ['validation']" in n for n in rep2.notes) and rep2.vector.level(Factor.VERIFICATION) == 1


def test_an_attested_negative_report_counts_on_its_attested_subject_whatever_digest_it_carries():  # re-review H-2
    w = World()
    w.attest(CONV, RESULT, CTX)
    w.attest(ApplicabilityReport("range", "outside", "", "T above the fitted range"), RESULT, CTX)
    w.attest(ApplicabilityReport("range2", "within", RESULT, "inside"), RESULT, CTX)
    rep = assess(w)
    assert not rep.requirement_met_in_test_mode and any(d.kind == "outside_domain" for d in rep.open_defeaters)
    w2 = World()
    w2.attest(CONV, RESULT, CTX)
    w2.attest(ApplicabilityReport("range", "unknown", "", "never checked"), RESULT, CTX)
    rep2 = assess(w2, g=graph(CONV, WITHIN), claims=LOW + [FactorClaim(Factor.APPLICABILITY, 1, ("n1",), "applicability")],
                  applicability_reports=(WITHIN,))
    assert rep2.vector.level(Factor.APPLICABILITY) == UNKNOWN
    with pytest.raises(AuthorityRefused, match="attested about the result it names"):
        w.attest(ApplicabilityReport("range3", "outside", _h("another result"), "x"), RESULT, CTX)


def test_a_ledger_subclass_is_refused():                                                           # re-review M-1
    w = World()
    w.attest(CONV, RESULT, CTX)
    led, anchor = w.opened()

    class Lenient(AuthorityLedger):
        def extends(self, anchor):
            return True
    fake = Lenient.__new__(Lenient)
    fake.__dict__.update(led.__dict__)
    with pytest.raises(CredibilityRefused, match="exactly that type"):
        assess(None, authority=fake, trust_anchor=anchor, allow_test_profile=True)


def test_residual_the_anchor_is_the_trust_root_so_it_never_comes_from_the_call_path(tmp_path):   # re-review M-1 (pinned)
    """issuer_bound rests on WHO chose the anchor's root key: a caller that mints its own root, opens its own ledger and
    passes that ledger's anchor gets issuer_bound.  So the anchor must be operator configuration -- and no MCP / planner
    path may forward ``authority`` / ``trust_anchor`` / ``allow_test_profile``."""
    w = World()
    w.attest(CONV, RESULT, CTX)
    led, anchor = w.opened()
    assert assess(None, authority=led, trust_anchor=anchor, allow_test_profile=True).issuer_bound
    import pathlib
    mcp = pathlib.Path(__file__).resolve().parents[2] / "src" / "engcore" / "mcp"
    for f in mcp.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for token in ("trust_anchor", "allow_test_profile", "AuthorityLedger"):
            assert token not in text, f"{f}: MCP must never carry {token}"


def test_a_minted_signer_cannot_be_relabelled():                                                   # re-review M-2
    import copy
    import dataclasses
    s = EphemeralKeyProvider().signer("r")
    with pytest.raises(TypeError):
        dataclasses.replace(s, key_class="production")
    with pytest.raises(AuthorityRefused, match="immutable"):
        s.key_class = "production"
    with pytest.raises(AuthorityRefused, match="not serialized"):
        __import__("pickle").dumps(s)
    assert copy.deepcopy(s) is s and s.key_class == "test"


def test_a_compromise_window_withdraws_what_the_key_signed_in_it():                                # re-review M-5
    w = World()
    w.attest(CONV, RESULT, CTX)
    mark = w.ledger.length
    assert verification_level(w)[0] == 1
    w.ledger.revoke(w.root, "ver", "drill: retired, not compromised")
    assert verification_level(w)[0] == 1                                    # a plain revocation leaves earlier records
    w2 = World()
    early = w2.ledger.length
    w2.attest(CONV, RESULT, CTX)
    w2.ledger.revoke(w2.root, "ver", "key exfiltrated", compromised_from=early)
    level, rep = verification_level(w2)
    assert level == UNKNOWN and any("compromise window" in n for n in rep.notes)
    with pytest.raises(AuthorityRefused, match="compromised_from"):
        w.ledger.revoke(w.root, "val", "x", compromised_from=mark + 99)
    w3 = World()
    w3.attest(CONV, RESULT, CTX)
    keys = EphemeralKeyProvider()
    w3.ledger.rotate_key(w3.root, "exec", keys.signer("exec2").possession(w3.ledger_id, "exec"), compromised_from=1)
    assert verification_level(w3)[0] == UNKNOWN                              # the RECEIPT key was compromised
    reopened = AuthorityLedger.open(w2.store, anchor=w2.ledger.anchor())
    assert reopened.compromised_at("ver", w2.ledger.attestations(record_kind="validation_check")[0].key_id, early + 1)


def test_an_issuer_that_produced_the_same_output_elsewhere_is_self_issued():                      # re-review L-2
    w = World()
    w.ledger.set_roles(w.root, "ver", [Role.NUMERICAL_VERIFICATION, Role.EXECUTOR])
    attest_receipt(w.ledger, w.signer("ver"), "ver", receipt_for(RESULT, node_id="rerun"), context_digest=OTHER)
    w.attest(CONV, RESULT, CTX)                                              # the verifier also produced this output
    level, rep = verification_level(w)
    assert level == UNKNOWN and any("self-issued" in n for n in rep.notes)


def test_an_attestation_subject_output_is_a_string():                                              # re-review L-1
    w = World()
    receipt = w.receipt(RESULT, CTX)
    with pytest.raises(AuthorityRefused, match="strings"):
        Attestation("validation_check", "validation_check/1", CONV.to_dict(), RESULT, CTX, Role.NUMERICAL_VERIFICATION,
                    receipt.record_digest, ["y"])


def test_a_retired_key_can_still_be_declared_compromised():                                         # combined review M-6
    w = World()
    w.attest(CONV, RESULT, CTX)
    old_key = w.ledger.attestations(record_kind="validation_check")[0].key_id
    stolen_from = w.ledger.attestations(record_kind="validation_check")[0].sequence
    w.ledger.rotate_key(w.root, "ver", EphemeralKeyProvider().signer("ver2").possession(w.ledger_id, "ver"))   # no window then
    assert verification_level(w)[0] == 1
    w.ledger.revoke(w.root, "ver", "left")
    w.ledger.declare_compromise(w.root, "ver", old_key, compromised_from=stolen_from, reason="theft found later")
    assert verification_level(w)[0] == UNKNOWN
    with pytest.raises(AuthorityRefused, match="active life"):
        w.ledger.declare_compromise(w.root, "ver", old_key, compromised_from=w.ledger.length + 5, reason="x")
    reopened = AuthorityLedger.open(w.store, anchor=w.ledger.anchor())       # the declaration replays from the chain
    assert reopened.compromised_at("ver", old_key, stolen_from)


def test_a_later_narrower_window_never_narrows_a_declared_compromise():                            # C2 LOW-1
    w = World()
    w.attest(CONV, RESULT, CTX)
    key = w.ledger.attestations(record_kind="validation_check")[0].key_id
    signed_at = w.ledger.attestations(record_kind="validation_check")[0].sequence
    w.ledger.declare_compromise(w.root, "ver", key, compromised_from=signed_at, reason="theft")
    w.ledger.revoke(w.root, "ver", "and revoked", compromised_from=w.ledger.length - 1)
    assert w.ledger.compromised_at("ver", key, signed_at) and verification_level(w)[0] == UNKNOWN
