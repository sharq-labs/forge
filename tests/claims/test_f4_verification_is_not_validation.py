"""F4 (hostile review, HIGH): agreement with a benchmark is verification, never experimental validation.

A benchmark oracle (``OracleKind.BENCHMARK_DATASET``) is a published reference
SOLUTION of a stated mathematical problem. Agreeing with it shows the declared
equations were solved correctly; it compares the model with nothing outside
itself. Only an independent physical measurement (``EXPERIMENTAL_DATASET``)
compares the model with reality. The level keeps its legacy wire name
``benchmark_validated``; its authority is decided by kind.
"""

from __future__ import annotations

import pytest

import engcore.scientific.oracles as oracle_module
from claims_support import t3_claim
from engcore.claims import assess_claim
from engcore.claims.contract import EvidenceRequirement
from engcore.claims.governance.policy import builtin_context
from engcore.credibility.evidence import evidence_basis_of
from engcore.mcp.capabilities import production_registry
from engcore.scientific.oracles import OracleEvidenceSet, OracleKind, OracleObservation
from engcore.scientific.results.validation import (
    VALIDATION_LEVELS,
    VERIFICATION_LEVELS,
    ValidationLevel as VL,
    ValidationReport,
)
from engcore.scientific.units.quantity import Quantity
from tests.test_audit_consensus_level_issuers import AT, _oracle_check


@pytest.fixture(scope="module")
def registry():
    return production_registry()


@pytest.fixture()
def oracle_checks(monkeypatch):
    """One issued, passing oracle check per oracle kind, through the trusted-oracle registry."""
    def _oracle(kind):
        return OracleEvidenceSet.create(
            oracle_id=f"f4.{kind.value}.001", version="1", kind=kind, reference=f"doi:10.example/f4-{kind.value}",
            observations=(OracleObservation("voltage", Quantity(3.70, "volt"), Quantity(0.05, "volt"), conditions=AT),))
    oracles = {k: _oracle(k) for k in OracleKind}
    monkeypatch.setattr(oracle_module, "_TRUSTED_ORACLE_DECLARATIONS", {
        o.identity.key: {"kind": o.identity.kind.value, "evidence_digest": o.identity.evidence_digest,
                         "reference": o.identity.reference} for o in oracles.values()})
    return {kind: _oracle_check(oracle) for kind, oracle in oracles.items()}


# ---------------------------------------------------------------------------
# The classification, in the Core's own vocabulary.
# ---------------------------------------------------------------------------


def test_only_an_independent_physical_measurement_is_a_validation_level() -> None:
    assert VALIDATION_LEVELS == frozenset({VL.EXPERIMENTALLY_VALIDATED})


@pytest.mark.parametrize("level", [VL.BENCHMARK_VALIDATED, VL.CROSS_SOLVER_VALIDATED, VL.ANALYTICALLY_VERIFIED])
def test_reference_analytic_and_cross_solver_agreement_are_verification(level) -> None:
    assert level in VERIFICATION_LEVELS and level not in VALIDATION_LEVELS
    assert evidence_basis_of({level}) == "VERIFICATION_ONLY"


def test_a_level_named_validated_earns_nothing_by_its_name() -> None:
    """The legacy names are wire identity only: authority is the classification, never the word."""
    misleading = {level for level in VL if level.value.endswith("_validated")} - VALIDATION_LEVELS
    assert misleading == {VL.BENCHMARK_VALIDATED, VL.CROSS_SOLVER_VALIDATED}
    assert misleading <= VERIFICATION_LEVELS


# ---------------------------------------------------------------------------
# Issued checks: benchmark -> verified, experiment -> validated.
# ---------------------------------------------------------------------------


def test_a_passing_benchmark_oracle_check_is_verification_only(oracle_checks) -> None:
    check = oracle_checks[OracleKind.BENCHMARK_DATASET]
    assert check.establishes is VL.BENCHMARK_VALIDATED
    assert ValidationReport(checks=(check,)).evidence_basis == "VERIFICATION_ONLY"


def test_a_passing_analytic_reference_check_is_verification_only(oracle_checks) -> None:
    report = ValidationReport(checks=(oracle_checks[OracleKind.ANALYTIC_REFERENCE],))
    assert report.evidence_basis == "VERIFICATION_ONLY"


def test_a_passing_experimental_oracle_check_is_validation(oracle_checks) -> None:
    report = ValidationReport(checks=(oracle_checks[OracleKind.EXPERIMENTAL_DATASET],))
    assert report.evidence_basis == "VALIDATED"


def test_a_benchmark_beside_an_experiment_does_not_change_what_the_experiment_is() -> None:
    assert evidence_basis_of({VL.BENCHMARK_VALIDATED, VL.EXPERIMENTALLY_VALIDATED}) == "VALIDATED"
    assert evidence_basis_of({VL.BENCHMARK_VALIDATED}) == "VERIFICATION_ONLY"


# ---------------------------------------------------------------------------
# The production NAFEMS T3 vertical: strong verification, not validation.
# ---------------------------------------------------------------------------


def test_t3_at_the_benchmark_point_keeps_its_benchmark_level_as_verification(registry) -> None:
    record = assess_claim(t3_claim(), registry).to_dict()
    assert record["verdict"] == "supported"  # the claim asked for the benchmark level and the run attained it
    assert "benchmark_validated" in record["verification"]["attained"]
    assert record["validation"]["attained"] == []
    assert record["validation"]["evidence_basis"] == "VERIFICATION_ONLY"


def test_t3_benchmark_agreement_cannot_establish_experimental_validation(registry) -> None:
    claim = t3_claim(evidence=EvidenceRequirement((VL.BENCHMARK_VALIDATED, VL.EXPERIMENTALLY_VALIDATED)))
    record = assess_claim(claim, registry).to_dict()
    assert record["verdict"] != "supported"
    assert "experimentally_validated" in record["validation"]["missing_required"]


def test_a_policy_demanding_validation_evidence_is_not_met_by_a_benchmark(registry) -> None:
    context = builtin_context("engineering_decision", influence="high", consequence="high", owner="f4-test")
    record = assess_claim(t3_claim(decision_context=context), registry).to_dict()
    assert record["verdict"] != "supported"
    assert "validation_evidence" in str(record)
