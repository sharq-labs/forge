"""Focused regressions for the post-PR104 BIG 1 scientific hardening batch.

These tests intentionally exercise refusal/derivation boundaries. They do not
weaken guards to preserve older convenience semantics.
"""

import json
import math

import pytest

from engcore.scientific.corpus.adequacy import InadequacyKind, diagnose_campaign
from engcore.scientific.corpus.campaign import (
    CaseVerdict,
    PredictedValue,
    ValidationCampaignReport,
    ValidationComparison,
    compare_observation,
)
from engcore.scientific.corpus.coverage import (
    CoverageDimension,
    CoverageStatus,
    ValidationRegion,
    build_coverage,
)
from engcore.scientific.corpus.dataset import (
    Applicability,
    DatasetSplit,
    ReferenceCase,
    ReferenceCondition,
    ReferenceDataset,
    ReferenceObservation,
)
from engcore.scientific.corpus.source import (
    CorpusLeakageError,
    ReferenceSource,
    SourceSnapshot,
    ToleranceBasis,
    ToleranceSpec,
)
from engcore.scientific.discovery.candidate import (
    DiscoveredEquationCandidate,
    DiscoveryCandidateStatus,
)
from engcore.scientific.errors import (
    InvalidScientificProblem,
    ScientificCoreError,
    UnitCompatibilityError,
)
from engcore.scientific.multiphysics import (
    CompositionAnalysis,
    CouplingCandidate,
    FrameTransform,
    PortKind,
    PortRef,
)
from engcore.scientific.numerics.health import assess_numeric_values
from engcore.scientific.numerics.stability import (
    NumericalStabilityDecision,
    NumericalStabilityPolicy,
    assess_numerical_stability,
)
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity
from engcore.uq.model_form.observation import ModelResidualObservation


def _source_and_snapshot():
    source = ReferenceSource(
        "source-a",
        "Example Authority",
        "test",
        "1",
        "https://example.com/data",
        ("example.com",),
    )
    snapshot = SourceSnapshot(
        "source-a",
        "1",
        "a" * 64,
        "https://example.com/data",
        1,
        "2026-09-24T00:00:00Z",
    )
    return source, snapshot


def _case(case_id, split, group):
    return ReferenceCase(
        case_id,
        split,
        group,
        conditions=(ReferenceCondition("temperature", Quantity(300, "K")),),
        applicability=Applicability.INSIDE,
    )


def _dataset(cases):
    source, snapshot = _source_and_snapshot()
    observations = tuple(
        ReferenceObservation(case.case_id, "temperature", Quantity(300, "K"))
        for case in cases
    )
    return ReferenceDataset(
        "dataset-a",
        "1",
        source,
        snapshot,
        tuple(cases),
        observations,
    )


def _report(dataset, comparisons):
    comparisons = tuple(comparisons)
    splits = tuple(
        sorted({item.split for item in comparisons}, key=lambda item: item.value)
    )
    return ValidationCampaignReport(
        "campaign-a",
        "1",
        dataset.dataset_id,
        dataset.version,
        dataset.snapshot.snapshot_sha256,
        dataset.normalized_digest,
        splits,
        comparisons,
    )


def _region(minimum=1):
    return ValidationRegion(
        "operating-region",
        (CoverageDimension("temperature", "kelvin", ()),),
        minimum,
    )


def _pass(case_id):
    return ValidationComparison(
        case_id,
        "temperature",
        DatasetSplit.VALIDATION,
        CaseVerdict.PASS,
        normalized_residual=0.0,
    )


def test_coverage_counts_one_piece_of_evidence_per_independence_group():
    dataset = _dataset(
        (
            _case("v1", DatasetSplit.VALIDATION, "same-run"),
            _case("v2", DatasetSplit.VALIDATION, "same-run"),
        )
    )
    cell = build_coverage(
        _report(dataset, (_pass("v1"), _pass("v2"))),
        dataset,
        _region(minimum=2),
        metric="temperature",
    ).cells[0]

    assert cell.passed == 1
    assert cell.status is CoverageStatus.SPARSE


def test_removing_or_replacing_support_with_unresolved_evidence_cannot_increase_coverage():
    dataset = _dataset(
        (
            _case("v1", DatasetSplit.VALIDATION, "run-1"),
            _case("v2", DatasetSplit.VALIDATION, "run-2"),
        )
    )
    region = _region(minimum=2)
    supported = build_coverage(
        _report(dataset, (_pass("v1"), _pass("v2"))),
        dataset,
        region,
        metric="temperature",
    ).cells[0]
    removed = build_coverage(
        _report(dataset, (_pass("v1"),)),
        dataset,
        region,
        metric="temperature",
    ).cells[0]
    unresolved = build_coverage(
        _report(
            dataset,
            (
                _pass("v1"),
                ValidationComparison(
                    "v2",
                    "temperature",
                    DatasetSplit.VALIDATION,
                    CaseVerdict.MISSING,
                ),
            ),
        ),
        dataset,
        region,
        metric="temperature",
    ).cells[0]

    assert supported.status is CoverageStatus.SUPPORTED
    assert removed.status is CoverageStatus.SPARSE
    assert unresolved.status is CoverageStatus.SPARSE
    assert unresolved.unscored == 1


def test_one_independence_group_cannot_cross_validation_and_locked_holdout():
    cases = (
        _case("validation", DatasetSplit.VALIDATION, "shared-evidence"),
        _case("holdout", DatasetSplit.LOCKED_HOLDOUT, "shared-evidence"),
    )
    with pytest.raises(CorpusLeakageError, match="cross dataset splits"):
        _dataset(cases)


def test_independent_failures_without_scored_calibration_do_not_indict_model_form():
    comparisons = tuple(
        ValidationComparison(
            f"v{i}",
            "temperature",
            DatasetSplit.VALIDATION,
            CaseVerdict.FAIL,
            normalized_residual=2.0,
        )
        for i in range(4)
    )
    report = ValidationCampaignReport(
        "campaign-a",
        "1",
        "dataset-a",
        "1",
        "a" * 64,
        "b" * 64,
        (DatasetSplit.VALIDATION,),
        comparisons,
    )

    diagnosis = diagnose_campaign(report, minimum_independent_cases=4)
    assert diagnosis.kind is InadequacyKind.INSUFFICIENT_EVIDENCE
    assert "no scored calibration cases" in diagnosis.why


def test_zero_acceptance_tolerance_failure_stays_finite_and_serializable():
    case = _case("exact", DatasetSplit.VALIDATION, "run")
    observation = ReferenceObservation(
        "exact",
        "temperature",
        Quantity(300, "K"),
        acceptance_tolerance=ToleranceSpec(
            Quantity(0, "K"),
            ToleranceBasis.REVIEWED_ACCEPTANCE,
            "exact benchmark fixture",
        ),
    )
    comparison = compare_observation(
        case,
        observation,
        PredictedValue(Quantity(301, "K")),
    )

    assert comparison.verdict is CaseVerdict.FAIL
    assert comparison.normalized_residual is not None
    assert math.isfinite(comparison.normalized_residual)
    assert comparison.normalized_residual > 1.0
    json.dumps(comparison.to_dict(), allow_nan=False)


def _candidate(**overrides):
    values = {
        "candidate_id": "candidate-a",
        "feature_names": ("x",),
        "coefficients": (1.0,),
        "intercept": 0.0,
        "calibration_rmse": 0.1,
        "holdout_rmse": 0.2,
        "complexity": 1,
        "context_digest": "a" * 64,
        "evidence_digests": ("b" * 64,),
        "status": DiscoveryCandidateStatus.SURVIVED_HOLDOUT,
    }
    values.update(overrides)
    return DiscoveredEquationCandidate(**values)


def test_discovery_holdout_status_requires_a_holdout_measurement():
    with pytest.raises(InvalidScientificProblem, match="carries no holdout RMSE"):
        _candidate(holdout_rmse=None)


@pytest.mark.parametrize(
    "change",
    (
        {"candidate_id": "candidate-b"},
        {"calibration_rmse": 0.11},
        {"holdout_rmse": 0.21},
        {"complexity": 2},
        {"status": DiscoveryCandidateStatus.FAILED_HOLDOUT},
    ),
)
def test_discovery_fingerprint_binds_every_scientific_identity_field(change):
    assert _candidate(**change).fingerprint != _candidate().fingerprint


def _candidate_edge(source_participant, target):
    return CouplingCandidate(
        PortRef(source_participant, "out"),
        target,
        "temperature",
        "temperature",
        PortKind.SCALAR,
        False,
        False,
    )


def test_composition_derives_unique_and_ambiguous_targets_from_candidates():
    target = PortRef("sink", "in")
    candidates = (
        _candidate_edge("source-a", target),
        _candidate_edge("source-b", target),
    )
    with pytest.raises(InvalidScientificProblem, match="unique_targets disagree"):
        CompositionAnalysis(
            candidates,
            (),
            (target,),
            (),
        )

    analysis = CompositionAnalysis(candidates, (), (), (target,))
    payload = analysis.to_dict()
    assert payload["record_fingerprint"] == analysis.fingerprint
    assert CompositionAnalysis.from_dict(payload) == analysis


def test_frame_transform_refuses_an_orthonormal_reflection():
    with pytest.raises(InvalidScientificProblem, match="determinant \+1"):
        FrameTransform(
            "reflection",
            "global",
            "local",
            ((1.0, 0.0), (0.0, -1.0)),
        )


def test_standard_uncertainty_requires_a_spread_scale():
    with pytest.raises(ScientificCoreError, match="spread/ratio"):
        Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(1.0, "degC"),
            method="fixture",
        )


def test_model_form_residual_units_require_a_spread_scale():
    with pytest.raises(UnitCompatibilityError):
        ModelResidualObservation(
            "observation",
            "independent-run",
            "temperature",
            "degC",
            1.0,
            0.5,
            True,
        )


@pytest.mark.parametrize("residual_ratio", (float("nan"), float("inf"), -1.0))
def test_numerical_stability_refuses_invalid_normalized_residuals(residual_ratio):
    result = assess_numerical_stability(
        assess_numeric_values((1.0,)),
        residual_ratio=residual_ratio,
        policy=NumericalStabilityPolicy(require_condition_estimate=False),
    )
    assert result.decision is NumericalStabilityDecision.REFUSED
    assert result.residual_ratio is None
    assert "non-finite or negative" in result.reasons
