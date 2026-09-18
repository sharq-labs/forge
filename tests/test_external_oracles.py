"""External oracle evidence is content-bound, authority-pinned and fail-closed."""

from __future__ import annotations

import pytest

import engcore.scientific.oracles as oracle_module
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.oracles import (
    OracleEvidenceSet,
    OracleIdentity,
    OracleKind,
    OracleObservation,
)
from engcore.scientific.results.validation import ValidationLevel, ValidationOutcome
from engcore.scientific.units.quantity import Quantity


def _observations():
    return (
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
    )


def _oracle(kind: OracleKind = OracleKind.EXPERIMENTAL_DATASET) -> OracleEvidenceSet:
    return OracleEvidenceSet.create(
        oracle_id="lab.cell.discharge.001",
        version="1",
        kind=kind,
        reference="doi:10.example/dataset",
        observations=_observations(),
    )


def _trust(monkeypatch, oracle: OracleEvidenceSet) -> None:
    monkeypatch.setattr(
        oracle_module,
        "_TRUSTED_ORACLE_DECLARATIONS",
        {
            oracle.identity.key: {
                "kind": oracle.identity.kind.value,
                "evidence_digest": oracle.identity.evidence_digest,
                "reference": oracle.identity.reference,
                "declared_by": "tests.test_external_oracles",
            }
        },
    )


def _predicted():
    return {
        "voltage": Quantity(3.72, "volt"),
        "temperature": Quantity(301.0, "kelvin"),
    }


#: R-49 (I-26): a validation LEVEL now requires the prediction to name the record it was computed from.
#: The operating point used to be the caller's assertion about a bare mapping of numbers, so a prediction
#: computed at 400 K earned a level at a stated 300 K. These fixtures name a record carrying exactly the
#: numbers they compare; the comparison itself is unchanged, and the tests that assert NO level is awarded
#: deliberately keep passing a bare mapping, because that is now one of the reasons a level is withheld.
#: The operating point these fixtures' evidence is observed at. R-49 (I-26): evidence that declares NO
#: point is compared anywhere and awards no level, because a level is a claim that the model was validated
#: somewhere. The two tests that assert a level therefore declare where their readings were taken.
AT = {"ambient_temperature": Quantity(298.15, "kelvin")}


def _observations_at_a_point():
    return tuple(
        OracleObservation(
            metric=item.metric, expected=item.expected,
            absolute_tolerance=item.absolute_tolerance, conditions=AT,
        )
        for item in _observations()
    )


def _oracle_at_a_point(kind: OracleKind = OracleKind.EXPERIMENTAL_DATASET) -> OracleEvidenceSet:
    return OracleEvidenceSet.create(
        oracle_id="lab.cell.discharge.001", version="1", kind=kind,
        reference="doi:10.example/dataset", observations=_observations_at_a_point(),
    )


def _record(predicted, *, result_id="oracle-fixture-result"):
    from engcore.scientific.results.provenance import ProvenanceRecord
    from engcore.scientific.results.result import ConvergenceState, ScientificResult
    from engcore.scientific.results.uncertainty import Uncertainty
    from engcore.scientific.results.validation import ValidationCheck, ValidationReport
    from engcore.scientific.solvers.protocol import SolverIdentity

    model = ("synthetic.oracle_fixture", "1.0.0")
    return ScientificResult(
        result_id=result_id, problem_id="oracle-fixture", values=dict(predicted), models=(model,),
        validity_not_assessed={model[0]: "a fixture: nothing asked whether the model applied"},
        solver=SolverIdentity("algebraic", "1.0.0"), convergence=ConvergenceState.NOT_APPLICABLE,
        validation=ValidationReport(checks=(ValidationCheck(
            name="dimensional_consistency", outcome=ValidationOutcome.PASS,
            establishes=ValidationLevel.DIMENSIONALLY_VALID, evidence=("fixture",)),)),
        uncertainty={name: Uncertainty.unknown("no quantification in this fixture") for name in predicted},
        provenance=ProvenanceRecord(run_id="oracle-fixture-run", models=(model,),
                                    solvers=(("algebraic", "1.0.0"),), inputs=dict(AT)),
    )


def test_self_declared_experimental_oracle_passes_comparison_but_awards_no_level():
    oracle = _oracle()
    check = oracle.compare(_predicted())
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is None
    assert "not pinned by the trusted oracle registry" in check.detail


def test_trusted_experimental_oracle_establishes_experimental_validation(monkeypatch):
    oracle = _oracle_at_a_point()
    _trust(monkeypatch, oracle)
    predicted = _predicted()
    check = oracle.compare(predicted, conditions=AT, predicted_from=_record(predicted))
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is ValidationLevel.EXPERIMENTALLY_VALIDATED
    assert check.residual is not None and check.residual <= 1.0
    assert f"sha256:{oracle.identity.evidence_digest}" in check.evidence
    assert "repository-pinned" in check.detail


def test_benchmark_and_analytic_oracles_map_to_their_own_levels_only_when_pinned(monkeypatch):
    predicted = {
        "voltage": Quantity(3.70, "volt"),
        "temperature": Quantity(300.0, "kelvin"),
    }
    benchmark = _oracle_at_a_point(OracleKind.BENCHMARK_DATASET)
    _trust(monkeypatch, benchmark)
    benchmark_check = benchmark.compare(predicted, conditions=AT, predicted_from=_record(predicted))
    assert benchmark_check.establishes is ValidationLevel.BENCHMARK_VALIDATED

    analytic = _oracle_at_a_point(OracleKind.ANALYTIC_REFERENCE)
    _trust(monkeypatch, analytic)
    analytic_check = analytic.compare(predicted, conditions=AT, predicted_from=_record(predicted))
    assert analytic_check.establishes is ValidationLevel.ANALYTICALLY_VERIFIED


def test_outside_tolerance_fails_and_awards_no_level_even_when_trusted(monkeypatch):
    oracle = _oracle()
    _trust(monkeypatch, oracle)
    check = oracle.compare(
        {
            "voltage": Quantity(3.90, "volt"),
            "temperature": Quantity(300.0, "kelvin"),
        }
    )
    assert check.outcome is ValidationOutcome.FAIL
    assert check.establishes is None
    assert check.residual is not None and check.residual > 1.0


def test_missing_metric_does_not_compare_the_intersection_and_awards_no_level():
    """R-53 (I-26): an unpredicted metric used to be recorded as a failure, so the check was FAIL and
    derive_verdict read NOT_SUPPORTED -- evidence AGAINST the model built out of a comparison nobody made.
    It is now NOT_RUN: nothing was compared for that metric, and nothing may rest on the absence. The
    rest of what this test guards is unchanged: no intersection is silently compared and no level is
    awarded."""
    check = _oracle().compare({"voltage": Quantity(3.70, "volt")})
    assert check.outcome is ValidationOutcome.NOT_RUN
    assert check.establishes is None
    assert "temperature:not predicted" in check.detail


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


def test_oracle_identity_requires_digest_syntax_and_reference():
    with pytest.raises(ScientificValidationError, match="SHA-256"):
        OracleIdentity(
            oracle_id="x",
            version="1",
            kind=OracleKind.BENCHMARK_DATASET,
            evidence_digest="not-a-digest",
            reference="benchmark-v1",
        )


def test_digest_shaped_string_cannot_be_attached_to_arbitrary_observations():
    with pytest.raises(ScientificValidationError, match="digest mismatch"):
        OracleEvidenceSet(
            identity=OracleIdentity(
                oracle_id="lab.cell.discharge.001",
                version="1",
                kind=OracleKind.EXPERIMENTAL_DATASET,
                evidence_digest="a" * 64,
                reference="doi:10.example/dataset",
            ),
            observations=_observations(),
        )


def test_changing_kind_without_rehashing_is_rejected():
    oracle = _oracle(OracleKind.BENCHMARK_DATASET)
    with pytest.raises(ScientificValidationError, match="digest mismatch"):
        OracleEvidenceSet(
            identity=OracleIdentity(
                oracle_id=oracle.identity.oracle_id,
                version=oracle.identity.version,
                kind=OracleKind.EXPERIMENTAL_DATASET,
                evidence_digest=oracle.identity.evidence_digest,
                reference=oracle.identity.reference,
            ),
            observations=oracle.observations,
        )


def test_duplicate_metric_observations_are_refused():
    observation = OracleObservation(
        metric="voltage",
        expected=Quantity(3.7, "volt"),
        absolute_tolerance=Quantity(0.05, "volt"),
    )
    # R-53 (I-26): the identity of an observation is its metric AT ITS OPERATING POINT, so the message
    # now names the point too. Two readings of one metric at one point are still refused, which is what
    # this test is about; a metric at two DIFFERENT points is no longer a duplicate.
    with pytest.raises(ScientificValidationError, match="must not repeat one metric at one operating point"):
        OracleEvidenceSet.create(
            oracle_id="oracle",
            version="1",
            kind=OracleKind.BENCHMARK_DATASET,
            reference="benchmark-v1",
            observations=(observation, observation),
        )


def test_oracle_records_round_trip_without_losing_content_identity():
    oracle = _oracle()
    restored = OracleEvidenceSet.from_dict(oracle.to_dict())
    assert restored == oracle
    assert restored.identity.evidence_digest == oracle.identity.evidence_digest


def test_serialized_observation_tampering_is_detected_by_content_digest():
    oracle = _oracle()
    payload = oracle.to_dict()
    payload["observations"][0]["expected"]["magnitude"] = 3.95
    with pytest.raises(ScientificValidationError, match="digest mismatch"):
        OracleEvidenceSet.from_dict(payload)


def test_repository_pin_must_match_exact_digest_kind_and_reference(monkeypatch):
    oracle = _oracle()
    monkeypatch.setattr(
        oracle_module,
        "_TRUSTED_ORACLE_DECLARATIONS",
        {
            oracle.identity.key: {
                "kind": oracle.identity.kind.value,
                "evidence_digest": "0" * 64,
                "reference": oracle.identity.reference,
            }
        },
    )
    check = oracle.compare(_predicted())
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is None
    assert "does not match its trusted declaration" in check.detail
