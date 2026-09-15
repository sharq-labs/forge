"""VAL-01 and RES-08: the strongest levels need an issuer, and derived summaries are checked.

VAL-01 (probe ``agentD/ind4.py``; also ``agentA/r2_validity.py``).
``ValidationCheck(outcome=PASS, establishes=CROSS_SOLVER_VALIDATED,
evidence=("trust me",))`` was attained by a ``ValidationReport``, survived
``from_dict``, and carried a hand-authored MCP evidence payload to a verdict.
Threshold authority protected the gates and never the record: GUARD 2 asks
only that *something* was compared, and a sentence is something.

The rule these tests pin, without changing any exported shape: a check that
passes (or warns) while declaring ``CROSS_SOLVER_VALIDATED``,
``BENCHMARK_VALIDATED`` or ``EXPERIMENTALLY_VALIDATED`` must carry, in its
``evidence``, the issuer record the platform writes when it awards that level,
and the record is re-verified against the registries the caller does not hold
-- on construction, on ``from_dict`` and on every read of the report:

* ``CROSS_SOLVER_VALIDATED``: the consensus's exact threshold record (a declared
  gate's own values, the check's tolerance being that gate's tolerance key), at
  least two routes pinned for that gate and key with verified dependencies, and
  execution bindings to distinct results and runs;
* ``BENCHMARK_VALIDATED`` / ``EXPERIMENTALLY_VALIDATED``: an oracle identity,
  content digest and reference that the trusted oracle registry pins for that
  kind.

RES-08. ``ValidationReport.from_dict`` never compared a stored ``status`` and
compared ``attained_levels`` only when the stored list was non-empty, so a
payload saying PASS over a FAIL, or ``[]`` over an attained level, was read.
"""

from __future__ import annotations

import json

import pytest

import engcore.scientific.oracles as oracle_module
from engcore.domains.electrical import dc_consensus as dcc
from engcore.execution.consensus import TrustedConsensusGate
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.oracles import OracleEvidenceSet, OracleKind, OracleObservation
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from engcore.scientific.units.quantity import Quantity
from tests.route_declarations_for_tests import (  # noqa: F401 - autouse fixture
    earned_consensus,
    route,
    route_declarations_for_tests,
)

STRONG = (
    ValidationLevel.CROSS_SOLVER_VALIDATED,
    ValidationLevel.BENCHMARK_VALIDATED,
    ValidationLevel.EXPERIMENTALLY_VALIDATED,
)


def _consensus_check():
    consensus = earned_consensus(
        (route("a"), route("b")), {"a": {"v": 1.0}, "b": {"v": 1.0}},
        thresholds=dcc.DC_CONSENSUS_THRESHOLDS, tolerance_key="agreement_rel_tol", required=("v",),
    )
    check = consensus.to_check()
    assert check.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    return check


def _oracle(kind=OracleKind.EXPERIMENTAL_DATASET):
    return OracleEvidenceSet.create(
        oracle_id="lab.cell.discharge.001", version="1", kind=kind, reference="doi:10.example/dataset",
        observations=(OracleObservation("voltage", Quantity(3.70, "volt"), Quantity(0.05, "volt")),),
    )


def _trust(monkeypatch, oracle):
    monkeypatch.setattr(oracle_module, "_TRUSTED_ORACLE_DECLARATIONS", {
        oracle.identity.key: {
            "kind": oracle.identity.kind.value,
            "evidence_digest": oracle.identity.evidence_digest,
            "reference": oracle.identity.reference,
        }
    })


def _rebuilt(check, **changes):
    fields = dict(name=check.name, outcome=check.outcome, detail=check.detail,
                  establishes=check.establishes, residual=check.residual,
                  tolerance=check.tolerance, evidence=check.evidence)
    fields.update(changes)
    return ValidationCheck(**fields)


# ---- VAL-01: the probe --------------------------------------------------------------------
@pytest.mark.parametrize("level", STRONG)
@pytest.mark.parametrize("outcome", [ValidationOutcome.PASS, ValidationOutcome.WARNING])
def test_probe_a_hand_built_strong_level_is_refused(level, outcome):
    with pytest.raises(ScientificValidationError, match="issuer"):
        ValidationCheck(name="forged", outcome=outcome, detail="", establishes=level, evidence=("trust me",))


@pytest.mark.parametrize("level", STRONG)
def test_probe_a_hand_built_strong_level_is_refused_on_the_way_in(level):
    payload = ValidationReport(checks=(ValidationCheck("x", ValidationOutcome.NOT_RUN),)).to_dict()
    payload["checks"] = [{
        "schema": payload["checks"][0]["schema"], "name": "forged", "outcome": "pass", "detail": "",
        "establishes": level.value, "residual": None, "tolerance": None, "evidence": ["trust me"],
    }]
    payload["attained_levels"] = [level.value]
    payload["status"] = "pass"
    with pytest.raises(ScientificValidationError, match="issuer"):
        ValidationReport.from_dict(json.loads(json.dumps(payload)))


def test_a_residual_and_tolerance_are_not_an_issuer_either():
    with pytest.raises(ScientificValidationError, match="issuer"):
        ValidationCheck(name="forged", outcome=ValidationOutcome.PASS,
                        establishes=ValidationLevel.CROSS_SOLVER_VALIDATED,
                        residual=0.0, tolerance=1e-9, evidence=("route a vs route b",))


@pytest.mark.parametrize("outcome", [ValidationOutcome.FAIL, ValidationOutcome.NOT_RUN])
def test_a_check_that_claims_nothing_may_still_name_the_level(outcome):
    ValidationCheck(name="c", outcome=outcome, establishes=ValidationLevel.EXPERIMENTALLY_VALIDATED)


def test_weaker_levels_are_unchanged():
    ValidationCheck(name="c", outcome=ValidationOutcome.PASS,
                    establishes=ValidationLevel.ANALYTICALLY_VERIFIED, evidence=("closed form",))


# ---- VAL-01: what the platform issues still stands ----------------------------------------
def test_a_consensus_issued_check_stands_and_round_trips():
    check = _consensus_check()
    report = ValidationReport(checks=(check,))
    assert ValidationLevel.CROSS_SOLVER_VALIDATED in report.attained_levels
    again = ValidationReport.from_dict(json.loads(json.dumps(report.to_dict())))
    assert ValidationLevel.CROSS_SOLVER_VALIDATED in again.attained_levels


def test_a_trusted_gate_check_carries_its_issuer_record():
    check = _consensus_check()
    rebuilt = _rebuilt(check, name="trusted", evidence=(*check.evidence, "artifact independence: fixture"))
    assert rebuilt.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    assert TrustedConsensusGate  # the gate copies base.evidence, so its checks carry the record


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(lambda ev: [l for l in ev if not l.startswith("consensus-thresholds:")], id="no-threshold-record"),
        pytest.param(lambda ev: [l.replace('"agreement_rel_tol":1e-09', '"agreement_rel_tol":0.5') for l in ev], id="loosened-values"),
        pytest.param(lambda ev: [l for l in ev if " read from result " not in l], id="no-bindings"),
        pytest.param(lambda ev: [l.replace("of run test:b:run", "of run test:a:run") for l in ev], id="one-run"),
        pytest.param(lambda ev: [l for l in ev if not l.startswith("route b")], id="one-route"),
        pytest.param(lambda ev: [l.replace("dependencies verified against the domain layer's pin", "dependencies UNVERIFIED") for l in ev], id="unverified"),
    ],
)
def test_a_tampered_consensus_issuer_record_is_refused(tamper):
    check = _consensus_check()
    with pytest.raises(ScientificValidationError, match="issuer"):
        _rebuilt(check, evidence=tuple(tamper(list(check.evidence))))


def test_a_consensus_issuer_record_of_undeclared_numbers_is_refused_even_when_self_consistent():
    check = _consensus_check()
    loosened = tuple(
        line.replace('"agreement_rel_tol":1e-09', '"agreement_rel_tol":0.5') for line in check.evidence
    )
    assert loosened != check.evidence
    with pytest.raises(ScientificValidationError, match="not a declared set"):
        _rebuilt(check, tolerance=0.5, evidence=loosened)


def test_a_consensus_issuer_record_under_another_tolerance_is_refused():
    check = _consensus_check()
    with pytest.raises(ScientificValidationError, match="issuer"):
        _rebuilt(check, tolerance=0.5, residual=0.0)


def test_a_consensus_issuer_record_for_a_gate_the_routes_do_not_name_is_refused(route_declarations_for_tests):
    check = _consensus_check()
    route_declarations_for_tests["b"]["threshold_gate_id"] = "kinetics.cstr.verification_gate"
    with pytest.raises(ScientificValidationError, match="issuer"):
        _rebuilt(check)


def test_a_pinned_oracle_issued_check_stands(monkeypatch):
    oracle = _oracle()
    _trust(monkeypatch, oracle)
    check = oracle.compare({"voltage": Quantity(3.71, "volt")})
    assert check.establishes is ValidationLevel.EXPERIMENTALLY_VALIDATED
    report = ValidationReport.from_dict(json.loads(json.dumps(ValidationReport(checks=(check,)).to_dict())))
    assert ValidationLevel.EXPERIMENTALLY_VALIDATED in report.attained_levels


def test_an_oracle_record_nobody_pinned_is_refused(monkeypatch):
    oracle = _oracle()
    _trust(monkeypatch, oracle)
    check = oracle.compare({"voltage": Quantity(3.71, "volt")})
    monkeypatch.setattr(oracle_module, "_TRUSTED_ORACLE_DECLARATIONS", {})
    with pytest.raises(ScientificValidationError, match="issuer"):
        _rebuilt(check)


def test_an_oracle_record_claiming_a_level_of_another_kind_is_refused(monkeypatch):
    oracle = _oracle(OracleKind.BENCHMARK_DATASET)
    _trust(monkeypatch, oracle)
    check = oracle.compare({"voltage": Quantity(3.71, "volt")})
    assert check.establishes is ValidationLevel.BENCHMARK_VALIDATED
    with pytest.raises(ScientificValidationError, match="issuer"):
        _rebuilt(check, establishes=ValidationLevel.EXPERIMENTALLY_VALIDATED)


def test_a_report_re_verifies_issuers_on_every_read(monkeypatch):
    oracle = _oracle()
    _trust(monkeypatch, oracle)
    report = ValidationReport(checks=(oracle.compare({"voltage": Quantity(3.71, "volt")}),))
    assert report.attained_levels
    monkeypatch.setattr(oracle_module, "_TRUSTED_ORACLE_DECLARATIONS", {})
    with pytest.raises(ScientificValidationError, match="issuer"):
        report.attained_levels


# ---- RES-08 ---------------------------------------------------------------------------------
def _payload():
    return ValidationReport(checks=(
        ValidationCheck("dims", ValidationOutcome.PASS, establishes=ValidationLevel.DIMENSIONALLY_VALID,
                        evidence=("x=kelvin",)),
        ValidationCheck("kcl", ValidationOutcome.FAIL, residual=1.0, tolerance=1e-9),
    )).to_dict()


def test_a_stored_status_that_is_not_the_recomputed_one_is_refused():
    payload = _payload()
    assert payload["status"] == "fail"
    payload["status"] = "pass"
    with pytest.raises(ScientificValidationError, match="status"):
        ValidationReport.from_dict(payload)


def test_a_stored_empty_attained_levels_over_an_attained_level_is_refused():
    payload = _payload()
    payload["attained_levels"] = []
    with pytest.raises(ScientificValidationError, match="attained_levels"):
        ValidationReport.from_dict(payload)


def test_an_honest_payload_and_one_without_the_derived_keys_still_read():
    ValidationReport.from_dict(_payload())
    payload = _payload()
    del payload["status"], payload["attained_levels"]
    ValidationReport.from_dict(payload)
