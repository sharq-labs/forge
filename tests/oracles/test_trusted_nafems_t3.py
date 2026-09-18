"""Sprint 2 — first repository-reviewed external benchmark authority."""

from __future__ import annotations

import dataclasses

import pytest

from engcore.domains.thermal_models.nafems_t3_oracle import (
    CONDITIONS,
    EVIDENCE_DIGEST,
    OBSERVATIONS,
    ORACLE_ID,
    ORACLE_VERSION,
    REFERENCE,
    nafems_t3_evidence,
)
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.oracles import OracleEvidenceSet, OracleKind
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from engcore.scientific.solvers.protocol import ConvergenceState, SolverIdentity
from engcore.scientific.units.quantity import Quantity


def _record(
    temperature: float = 309.75,
    *,
    inputs=None,
    result_id: str = "nafems-t3-prediction",
) -> ScientificResult:
    model = ("thermal.nafems_t3.fixture", "1")
    declared = dict(CONDITIONS if inputs is None else inputs)
    return ScientificResult(
        result_id=result_id,
        problem_id="nafems-p18-t3",
        values={"temperature_at_probe": Quantity(temperature, "kelvin")},
        models=(model,),
        validity_not_assessed={
            model[0]: (
                "benchmark fixture: domain applicability is represented "
                "by the pinned operating point"
            )
        },
        solver=SolverIdentity("benchmark.fixture", "1"),
        convergence=ConvergenceState.CONVERGED,
        validation=ValidationReport(
            checks=(
                ValidationCheck(
                    name="dimensional_consistency",
                    outcome=ValidationOutcome.PASS,
                    establishes=ValidationLevel.DIMENSIONALLY_VALID,
                    evidence=("fixture",),
                ),
            )
        ),
        uncertainty={
            "temperature_at_probe": Uncertainty.unknown(
                "oracle-authority test does not quantify prediction uncertainty"
            )
        },
        provenance=ProvenanceRecord(
            run_id=f"{result_id}-run",
            models=(model,),
            solvers=(("benchmark.fixture", "1"),),
            inputs=declared,
        ),
    )


def test_nafems_t3_content_digest_is_review_pinned() -> None:
    evidence = nafems_t3_evidence()
    assert evidence.content_digest == EVIDENCE_DIGEST, (
        f"canonical digest is {evidence.content_digest}"
    )


def test_nafems_t3_is_a_repository_trusted_benchmark() -> None:
    evidence = nafems_t3_evidence()
    assert evidence.identity.key == (ORACLE_ID, ORACLE_VERSION)
    assert evidence.identity.kind is OracleKind.BENCHMARK_DATASET
    assert evidence.identity.reference == REFERENCE
    assert evidence.identity.is_trusted is True


def test_exact_target_at_exact_operating_point_earns_benchmark_validation() -> None:
    evidence = nafems_t3_evidence()
    record = _record()
    check = evidence.compare(
        record.values,
        conditions=CONDITIONS,
        predicted_from=record,
        name="nafems_t3",
    )

    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is ValidationLevel.BENCHMARK_VALIDATED
    assert f"sha256:{EVIDENCE_DIGEST}" in check.evidence
    assert "repository-pinned" in check.detail


def test_wrong_operating_point_never_earns_the_level() -> None:
    evidence = nafems_t3_evidence()
    wrong = dict(CONDITIONS)
    wrong["end_time"] = Quantity(31.0, "second")
    record = _record(inputs=wrong)

    check = evidence.compare(
        record.values,
        conditions=wrong,
        predicted_from=record,
        name="nafems_t3",
    )

    assert check.outcome is ValidationOutcome.NOT_RUN
    assert check.establishes is None


def test_stated_point_cannot_hide_a_record_computed_somewhere_else() -> None:
    evidence = nafems_t3_evidence()
    wrong = dict(CONDITIONS)
    wrong["conductivity"] = Quantity(34.0, "watt/meter/kelvin")
    record = _record(inputs=wrong)

    check = evidence.compare(
        record.values,
        conditions=CONDITIONS,
        predicted_from=record,
        name="nafems_t3",
    )

    assert check.outcome is ValidationOutcome.NOT_RUN
    assert check.establishes is None
    assert "was computed at" in check.detail


def test_tampering_with_pinned_observation_is_detected() -> None:
    trusted = nafems_t3_evidence()
    changed = dataclasses.replace(
        OBSERVATIONS[0],
        expected=Quantity(310.0, "kelvin"),
    )
    with pytest.raises(ScientificValidationError, match="digest mismatch"):
        OracleEvidenceSet(
            identity=trusted.identity,
            observations=(changed,),
        )


def test_same_oracle_name_with_different_content_has_no_authority() -> None:
    changed = dataclasses.replace(
        OBSERVATIONS[0],
        absolute_tolerance=Quantity(5.0, "kelvin"),
    )
    unreviewed = OracleEvidenceSet.create(
        oracle_id=ORACLE_ID,
        version=ORACLE_VERSION,
        kind=OracleKind.BENCHMARK_DATASET,
        reference=REFERENCE,
        observations=(changed,),
    )
    assert unreviewed.content_digest != EVIDENCE_DIGEST
    assert unreviewed.is_trusted is False

    record = _record()
    check = unreviewed.compare(
        record.values,
        conditions=CONDITIONS,
        predicted_from=record,
    )
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is None
    assert "does not match its trusted declaration" in check.detail
