"""External oracle evidence is explicit, content-addressed and fail-closed."""

from __future__ import annotations

import pytest

from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.oracles import (
    OracleEvidenceSet,
    OracleIdentity,
    OracleKind,
    OracleObservation,
)
from engcore.scientific.results.validation import ValidationLevel, ValidationOutcome
from engcore.scientific.units.quantity import Quantity


_DIGEST = "a" * 64


def _oracle(kind: OracleKind = OracleKind.EXPERIMENTAL_DATASET) -> OracleEvidenceSet:
    return OracleEvidenceSet(
        identity=OracleIdentity(
            oracle_id="lab.cell.discharge.001",
            version="1",
            kind=kind,
            evidence_digest=_DIGEST,
            reference="doi:10.example/dataset",
        ),
        observations=(
            OracleObservation(
                metric="voltage",
                expected=Quantity(3.70, "volt"),
                absolute_tolerance=Quantity(0.05, "volt"),
            ),
            OracleObservation(
                metric="temperature",
                expected=Quantity(300.0, "kelvin"),
                absolute_tolerance=Quantity(2.0, "kelvin"),
            ),
        ),
    )


def test_experimental_oracle_pass_establishes_experimental_validation():
    check = _oracle().compare(
        {
            "voltage": Quantity(3.72, "volt"),
            "temperature": Quantity(301.0, "kelvin"),
        }
    )
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is ValidationLevel.EXPERIMENTALLY_VALIDATED
    assert check.residual is not None and check.residual <= 1.0
    assert f"sha256:{_DIGEST}" in check.evidence


def test_benchmark_and_analytic_oracles_map_to_their_own_evidence_levels():
    predicted = {
        "voltage": Quantity(3.70, "volt"),
        "temperature": Quantity(300.0, "kelvin"),
    }
    benchmark = _oracle(OracleKind.BENCHMARK_DATASET).compare(predicted)
    analytic = _oracle(OracleKind.ANALYTIC_REFERENCE).compare(predicted)
    assert benchmark.establishes is ValidationLevel.BENCHMARK_VALIDATED
    assert analytic.establishes is ValidationLevel.ANALYTICALLY_VERIFIED


def test_outside_tolerance_fails_and_awards_no_level():
    check = _oracle().compare(
        {
            "voltage": Quantity(3.90, "volt"),
            "temperature": Quantity(300.0, "kelvin"),
        }
    )
    assert check.outcome is ValidationOutcome.FAIL
    assert check.establishes is None
    assert check.residual is not None and check.residual > 1.0


def test_missing_metric_fails_closed_instead_of_comparing_the_intersection():
    check = _oracle().compare({"voltage": Quantity(3.70, "volt")})
    assert check.outcome is ValidationOutcome.FAIL
    assert check.establishes is None
    assert "temperature:missing" in check.detail


def test_wrong_dimension_fails_closed():
    check = _oracle().compare(
        {
            "voltage": Quantity(3.70, "ampere"),
            "temperature": Quantity(300.0, "kelvin"),
        }
    )
    assert check.outcome is ValidationOutcome.FAIL
    assert check.establishes is None
    assert "voltage:incompatible" in check.detail


def test_oracle_tolerance_must_match_expected_dimension():
    with pytest.raises(Exception):
        OracleObservation(
            metric="voltage",
            expected=Quantity(3.7, "volt"),
            absolute_tolerance=Quantity(1.0, "ampere"),
        )


def test_oracle_identity_requires_content_digest_and_reference():
    with pytest.raises(ScientificValidationError, match="SHA-256"):
        OracleIdentity(
            oracle_id="x",
            version="1",
            kind=OracleKind.BENCHMARK_DATASET,
            evidence_digest="not-a-digest",
            reference="benchmark-v1",
        )


def test_duplicate_metric_observations_are_refused():
    observation = OracleObservation(
        metric="voltage",
        expected=Quantity(3.7, "volt"),
        absolute_tolerance=Quantity(0.05, "volt"),
    )
    with pytest.raises(ScientificValidationError, match="unique"):
        OracleEvidenceSet(
            identity=OracleIdentity(
                "oracle",
                "1",
                OracleKind.BENCHMARK_DATASET,
                _DIGEST,
                "benchmark-v1",
            ),
            observations=(observation, observation),
        )


def test_oracle_records_round_trip_without_losing_identity_or_bounds():
    oracle = _oracle()
    restored = OracleEvidenceSet.from_dict(oracle.to_dict())
    assert restored == oracle
    assert restored.identity.evidence_digest == _DIGEST
