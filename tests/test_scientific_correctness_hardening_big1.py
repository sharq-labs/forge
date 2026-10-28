"""Cross-cutting false-confidence regressions for BIG 1 hardening."""

import pytest

from engcore.scientific.corpus.campaign import (
    CaseVerdict,
    ValidationCampaignReport,
    ValidationComparison,
)
from engcore.scientific.corpus.coverage import (
    CoverageCell,
    CoverageDimension,
    CoverageStatus,
    ValidationCoverage,
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
from engcore.scientific.corpus.source import CorpusError, ReferenceSource, SourceSnapshot
from engcore.scientific.discovery.candidate import (
    DiscoveredEquationCandidate,
    DiscoveryCandidateStatus,
)
from engcore.scientific.discovery.campaign import (
    DiscoveryDecision,
    review_discovery_candidate,
)
from engcore.scientific.errors import InvalidScientificProblem, UnitCompatibilityError
from engcore.scientific.verification import VerificationDecision
from engcore.scientific.fields.profiles import ConstantProfile, SeparableProfile2D
from engcore.scientific.multiphysics.report import (
    CouplingIterationRecord,
    CouplingWindowRecord,
    EdgeResidual,
    ParticipantStepRecord,
    WindowOutcome,
)
from engcore.scientific.units.quantity import Quantity


def _region(minimum=1):
    return ValidationRegion(
        "operating-region",
        (CoverageDimension("temperature", "kelvin", ()),),
        minimum,
    )


def test_scored_campaign_verdict_is_derived_from_normalized_residual():
    with pytest.raises(CorpusError, match="derives 'pass'"):
        ValidationComparison(
            "case", "temperature", DatasetSplit.VALIDATION,
            CaseVerdict.FAIL, normalized_residual=0.25,
        )
    with pytest.raises(CorpusError, match="derives 'fail'"):
        ValidationComparison(
            "case", "temperature", DatasetSplit.VALIDATION,
            CaseVerdict.PASS, normalized_residual=2.0,
        )


def test_coverage_refuses_a_caller_asserted_status_that_counts_do_not_derive():
    region = _region(minimum=2)
    forged = CoverageCell(
        cell=(0,),
        label=region.label((0,)),
        passed=0,
        failed=1,
        unscored=0,
        correct_refusals=0,
        unexpected_refusals=0,
        undeclared=0,
        status=CoverageStatus.SUPPORTED,
    )
    with pytest.raises(CorpusError, match="counts derive 'failed'"):
        ValidationCoverage(region, (forged,), "temperature")


def _dataset():
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
    cases = (
        ReferenceCase(
            "cal",
            DatasetSplit.CALIBRATION,
            "cal-group",
            conditions=(ReferenceCondition("temperature", Quantity(300, "K")),),
            applicability=Applicability.INSIDE,
        ),
        ReferenceCase(
            "val",
            DatasetSplit.VALIDATION,
            "val-group",
            conditions=(ReferenceCondition("temperature", Quantity(300, "K")),),
            applicability=Applicability.INSIDE,
        ),
    )
    observations = (
        ReferenceObservation("cal", "temperature", Quantity(300, "K")),
        ReferenceObservation("val", "temperature", Quantity(300, "K")),
    )
    return ReferenceDataset(
        "dataset-a", "1", source, snapshot, cases, observations
    )


def _report(dataset, comparisons, splits):
    return ValidationCampaignReport(
        "campaign-a",
        "1",
        dataset.dataset_id,
        dataset.version,
        dataset.snapshot.snapshot_sha256,
        dataset.normalized_digest,
        tuple(splits),
        tuple(comparisons),
    )


def test_calibration_passes_do_not_validate_a_failed_independent_case():
    dataset = _dataset()
    report = _report(
        dataset,
        (
            ValidationComparison(
                "cal", "temperature", DatasetSplit.CALIBRATION,
                CaseVerdict.PASS, normalized_residual=0.0,
            ),
            ValidationComparison(
                "val", "temperature", DatasetSplit.VALIDATION,
                CaseVerdict.FAIL, normalized_residual=2.0,
            ),
        ),
        (DatasetSplit.CALIBRATION, DatasetSplit.VALIDATION),
    )
    cell = build_coverage(
        report, dataset, _region(), metric="temperature"
    ).cells[0]
    assert (cell.passed, cell.failed, cell.status) == (
        0, 1, CoverageStatus.FAILED
    )


def test_calibration_only_evidence_leaves_validation_coverage_untested():
    dataset = _dataset()
    report = _report(
        dataset,
        (
            ValidationComparison(
                "cal", "temperature", DatasetSplit.CALIBRATION,
                CaseVerdict.PASS, normalized_residual=0.0,
            ),
        ),
        (DatasetSplit.CALIBRATION,),
    )
    cell = build_coverage(
        report, dataset, _region(), metric="temperature"
    ).cells[0]
    assert (cell.passed, cell.failed, cell.status) == (
        0, 0, CoverageStatus.UNTESTED
    )


def test_a_report_cannot_relabel_a_calibration_case_as_validation():
    dataset = _dataset()
    report = _report(
        dataset,
        (
            ValidationComparison(
                "cal", "temperature", DatasetSplit.VALIDATION,
                CaseVerdict.PASS, normalized_residual=0.0,
            ),
        ),
        (DatasetSplit.VALIDATION,),
    )
    with pytest.raises(CorpusError, match="split identity is evidence"):
        build_coverage(report, dataset, _region(), metric="temperature")


def _iteration(*, satisfied):
    step = ParticipantStepRecord(
        "participant", Quantity(0, "s"), Quantity(1, "s"), 1, True
    )
    residual = EdgeResidual(
        "edge", Quantity(50 if not satisfied else 0, "K"),
        50.0 if not satisfied else 0.0, "linf", satisfied
    )
    return CouplingIterationRecord(
        1, (step,), (residual,), {"edge": 1.0}
    )


def test_window_cannot_claim_converged_when_final_residuals_do_not():
    with pytest.raises(InvalidScientificProblem, match="declares CONVERGED"):
        CouplingWindowRecord(
            0, Quantity(0, "s"), Quantity(1, "s"),
            WindowOutcome.CONVERGED, (_iteration(satisfied=False),)
        )


def test_window_cannot_claim_iteration_limit_after_residuals_converged():
    with pytest.raises(InvalidScientificProblem, match="declares ITERATION_LIMIT"):
        CouplingWindowRecord(
            0, Quantity(0, "s"), Quantity(1, "s"),
            WindowOutcome.ITERATION_LIMIT, (_iteration(satisfied=True),)
        )


def test_scaled_dimensionless_profile_factors_use_their_physical_scale():
    profile = SeparableProfile2D(
        Quantity(100.0, "watt/meter**3"),
        ConstantProfile(Quantity(50.0, "percent")),
        ConstantProfile(Quantity(20.0, "percent")),
    )
    assert profile.evaluate(x=0.0, y=0.0) == pytest.approx(10.0)


@pytest.mark.parametrize("operation", ["multiply", "divide"])
def test_absolute_celsius_is_refused_in_multiplicative_arithmetic(operation):
    value = Quantity(20.0, "degC")
    with pytest.raises(UnitCompatibilityError, match="absolute affine unit"):
        if operation == "multiply":
            value * 2.0
        else:
            value / 2.0


def test_ratio_and_delta_scales_remain_multiplicative():
    assert (Quantity(300.0, "kelvin") * 2.0).magnitude_in("kelvin") == 600.0
    assert (
        Quantity(10.0, "delta_degC") * 2.0
    ).magnitude_as_spread_in("kelvin") == pytest.approx(20.0)


def test_discovery_does_not_promote_an_unrelated_verified_subject():
    from engcore.scientific.discovery import DiscoveryDataset, DiscoveryFeature, SparseDiscoveryPolicy, discover_sparse_equations
    from engcore.scientific.discovery.final_evaluation import FrozenDiscoverySelection, evaluate_final_test
    from engcore.scientific.equations import Symbol
    def data(prefix, values, evidence):
        feature = DiscoveryFeature("x", Symbol("x"), values, tuple({"x": Quantity(v, "1")} for v in values))
        return DiscoveryDataset(prefix, (feature,), values, (0, 1), (2, 3), "a" * 64, evidence,
                                tuple(f"{prefix}-{i}" for i in range(4)), (prefix,) * 4)
    # final data is separate: new rows and new evidence, not the development data relabelled
    dev, final = data("dev", (1., 2., 3., 4.), ("b" * 64,)), data("final", (5., 6., 7., 8.), ("c" * 64,))
    selection = FrozenDiscoverySelection(dev, SparseDiscoveryPolicy(), discover_sparse_equations(dev)[0], .05)
    candidate = evaluate_final_test(selection, final)

    # a real, complete verification -- of another subject (look-alike objects are refused outright)
    from engcore.scientific.verification import (
        DependencyComponent, DependencyRole, RouteDependencyManifest, VerificationCandidate, VerificationObservation,
        VerificationPolicy, VerificationRoute, VerificationRouteKind, VerificationRunRecord, plan_verification,
    )
    plan = plan_verification(
        VerificationRoute("p", VerificationRouteKind.DIFFERENT_IMPLEMENTATION, "a" * 64),
        RouteDependencyManifest("p", (DependencyComponent("p-family", "a" * 64, DependencyRole.SOLVER),), "ours", False),
        (VerificationCandidate(VerificationRoute("v", VerificationRouteKind.EXTERNAL_SOLVER, "b" * 64),
                               RouteDependencyManifest("v", (DependencyComponent("v-family", "b" * 64, DependencyRole.SOLVER),),
                                                       "lab", True)),),
        VerificationPolicy())
    unrelated = VerificationRunRecord(plan, VerificationObservation("p", Quantity(300, "kelvin"), "1" * 64, True),
                                      (VerificationObservation("v", Quantity(300.2, "kelvin"), "2" * 64, True),),
                                      Quantity(1, "kelvin"), subject_digest="c" * 64)
    assert unrelated.result.complete and unrelated.result.verification.decision is VerificationDecision.VERIFIED

    review = review_discovery_candidate(candidate, verification=unrelated,
                                       final_selection=selection, final_data=final)
    assert review.decision is DiscoveryDecision.HOLDOUT_SURVIVOR
    assert "not bound to this candidate" in review.reasons[0]


