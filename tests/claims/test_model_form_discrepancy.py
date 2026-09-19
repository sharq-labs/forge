"""Held-out model-form discrepancy candidates never self-promote."""

from __future__ import annotations

import pytest

from engcore.claims import (
    DatasetSplit,
    DiscrepancyEstimateStatus,
    DiscrepancyProtocol,
    ModelFormDiscrepancyError,
    PairedObservation,
    estimate_model_form_discrepancy,
)
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from engcore.scientific.units.quantity import Quantity


def _interval(center: float, half_width: float, source: UncertaintySource) -> Uncertainty:
    return Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=Quantity(center - half_width, "kelvin"),
        upper=Quantity(center + half_width, "kelvin"),
        method="fixture interval",
        source_kind=source,
    )


def _pair(
    observation_id: str,
    group: str,
    split: DatasetSplit,
    *,
    observed: float = 300.0,
    predicted: float = 300.0,
    measurement_half_width: float = 0.05,
    numerical_half_width: float = 0.05,
) -> PairedObservation:
    return PairedObservation(
        observation_id=observation_id,
        independence_group=group,
        split=split,
        quantity="temperature",
        observed=Quantity(observed, "kelvin"),
        predicted=Quantity(predicted, "kelvin"),
        measurement_uncertainty=_interval(observed, measurement_half_width, UncertaintySource.MEASUREMENT),
        prediction_uncertainties=(
            _interval(predicted, numerical_half_width, UncertaintySource.NUMERICAL),
        ),
        context_digest=f"context:{observation_id}",
        measurement_digest=f"measurement:{observation_id}",
    )


def _protocol() -> DiscrepancyProtocol:
    return DiscrepancyProtocol("fixture-held-out-v1", 2, 2)


def test_calibration_envelope_must_survive_independent_holdout() -> None:
    estimate = estimate_model_form_discrepancy(
        (
            _pair("c1", "pack:c1", DatasetSplit.CALIBRATION, predicted=300.30),
            _pair("c2", "pack:c2", DatasetSplit.CALIBRATION, predicted=300.25),
            _pair("v1", "pack:v1", DatasetSplit.VALIDATION, predicted=300.20),
            _pair("v2", "pack:v2", DatasetSplit.VALIDATION, predicted=300.29),
        ),
        _protocol(),
    )

    assert estimate.status is DiscrepancyEstimateStatus.VALIDATED_CANDIDATE
    assert estimate.minimum_required_half_width == pytest.approx(0.20)
    assert estimate.conservative_compatible_half_width == pytest.approx(0.40)
    candidate = estimate.candidate
    assert candidate is not None
    assert candidate.minimum_required_half_width == pytest.approx(0.20)
    assert candidate.conservative_compatible_half_width == pytest.approx(0.40)
    assert candidate.to_dict()["zero_established"] is False
    assert candidate.to_dict()["is_uncertainty_record"] is False
    assert candidate.to_dict()["can_satisfy_claim"] is False
    assert estimate.to_dict()["promotes_model_form_uncertainty"] is False


def test_holdout_failure_refuses_a_model_form_candidate() -> None:
    estimate = estimate_model_form_discrepancy(
        (
            _pair("c1", "pack:c1", DatasetSplit.CALIBRATION, predicted=300.30),
            _pair("c2", "pack:c2", DatasetSplit.CALIBRATION, predicted=300.25),
            _pair("v1", "pack:v1", DatasetSplit.VALIDATION, predicted=300.20),
            _pair("v2", "pack:v2", DatasetSplit.VALIDATION, predicted=300.55),
        ),
        _protocol(),
    )

    assert estimate.status is DiscrepancyEstimateStatus.FAILED_VALIDATION
    assert estimate.candidate is None
    assert estimate.failed_validation_groups == ("pack:v2",)


def test_calibration_without_enough_holdout_stays_unvalidated() -> None:
    estimate = estimate_model_form_discrepancy(
        (
            _pair("c1", "pack:c1", DatasetSplit.CALIBRATION, predicted=300.30),
            _pair("c2", "pack:c2", DatasetSplit.CALIBRATION, predicted=300.25),
            _pair("v1", "pack:v1", DatasetSplit.VALIDATION, predicted=300.20),
        ),
        _protocol(),
    )
    assert estimate.status is DiscrepancyEstimateStatus.CALIBRATED_UNVALIDATED
    assert estimate.candidate is None


def test_unknown_or_wrong_uncertainty_never_becomes_zero() -> None:
    pair = _pair("c1", "pack:c1", DatasetSplit.CALIBRATION)
    unknown = PairedObservation(
        pair.observation_id,
        pair.independence_group,
        pair.split,
        pair.quantity,
        pair.observed,
        pair.predicted,
        Uncertainty.unknown("sensor accuracy not supplied"),
        pair.prediction_uncertainties,
        pair.context_digest,
        pair.measurement_digest,
    )
    estimate = estimate_model_form_discrepancy(
        (
            unknown,
            _pair("c2", "pack:c2", DatasetSplit.CALIBRATION),
            _pair("v1", "pack:v1", DatasetSplit.VALIDATION),
            _pair("v2", "pack:v2", DatasetSplit.VALIDATION),
        ),
        _protocol(),
    )
    assert estimate.status is DiscrepancyEstimateStatus.INSUFFICIENT_UNCERTAINTY
    assert estimate.minimum_required_half_width is None
    assert estimate.conservative_compatible_half_width is None
    assert estimate.candidate is None


def test_same_independence_group_cannot_leak_across_the_split() -> None:
    with pytest.raises(ModelFormDiscrepancyError, match="row-wise leakage"):
        estimate_model_form_discrepancy(
            (
                _pair("c1", "pack:same", DatasetSplit.CALIBRATION),
                _pair("c2", "pack:c2", DatasetSplit.CALIBRATION),
                _pair("v1", "pack:same", DatasetSplit.VALIDATION),
                _pair("v2", "pack:v2", DatasetSplit.VALIDATION),
            ),
            _protocol(),
        )


def test_model_form_uncertainty_cannot_be_subtracted_from_itself() -> None:
    pair = _pair("c1", "pack:c1", DatasetSplit.CALIBRATION)
    circular = PairedObservation(
        pair.observation_id,
        pair.independence_group,
        pair.split,
        pair.quantity,
        pair.observed,
        pair.predicted,
        pair.measurement_uncertainty,
        (_interval(300.0, 0.1, UncertaintySource.MODEL_FORM),),
        pair.context_digest,
        pair.measurement_digest,
    )
    estimate = estimate_model_form_discrepancy(
        (
            circular,
            _pair("c2", "pack:c2", DatasetSplit.CALIBRATION),
            _pair("v1", "pack:v1", DatasetSplit.VALIDATION),
            _pair("v2", "pack:v2", DatasetSplit.VALIDATION),
        ),
        _protocol(),
    )
    assert estimate.status is DiscrepancyEstimateStatus.INSUFFICIENT_UNCERTAINTY
    assert "not admissible" in next(p.problem for p in estimate.points if p.problem)


def test_residuals_below_known_uncertainty_do_not_establish_zero_model_form() -> None:
    estimate = estimate_model_form_discrepancy(
        (
            _pair("c1", "pack:c1", DatasetSplit.CALIBRATION, predicted=300.04),
            _pair("c2", "pack:c2", DatasetSplit.CALIBRATION, predicted=300.03),
            _pair("v1", "pack:v1", DatasetSplit.VALIDATION, predicted=300.02),
            _pair("v2", "pack:v2", DatasetSplit.VALIDATION, predicted=300.01),
        ),
        _protocol(),
    )

    assert estimate.minimum_required_half_width == pytest.approx(0.0)
    assert estimate.conservative_compatible_half_width is not None
    assert estimate.status is DiscrepancyEstimateStatus.UNRESOLVED_BELOW_KNOWN_UNCERTAINTY
    assert estimate.candidate is None
    assert "zero" in estimate.reason.lower()
    assert "known" in estimate.reason.lower()
    assert "uncertainty" in estimate.reason.lower()


def test_known_uncertainty_widths_are_normalized_before_residual_constraints() -> None:
    def mixed(observation_id: str, group: str, split: DatasetSplit) -> PairedObservation:
        return PairedObservation(
            observation_id=observation_id,
            independence_group=group,
            split=split,
            quantity="terminal_voltage",
            observed=Quantity(300000.0, "millivolt"),
            predicted=Quantity(300.0, "volt"),
            measurement_uncertainty=Uncertainty(
                kind=UncertaintyKind.INTERVAL,
                lower=Quantity(299950.0, "millivolt"),
                upper=Quantity(300050.0, "millivolt"),
                method="fixture interval",
                source_kind=UncertaintySource.MEASUREMENT,
            ),
            prediction_uncertainties=(
                Uncertainty(
                    kind=UncertaintyKind.INTERVAL,
                    lower=Quantity(299.95, "volt"),
                    upper=Quantity(300.05, "volt"),
                    method="fixture interval",
                    source_kind=UncertaintySource.NUMERICAL,
                ),
            ),
            context_digest=f"context:{observation_id}",
            measurement_digest=f"measurement:{observation_id}",
        )

    estimate = estimate_model_form_discrepancy(
        (
            mixed("c1", "pack:c1", DatasetSplit.CALIBRATION),
            mixed("c2", "pack:c2", DatasetSplit.CALIBRATION),
            mixed("v1", "pack:v1", DatasetSplit.VALIDATION),
            mixed("v2", "pack:v2", DatasetSplit.VALIDATION),
        ),
        _protocol(),
    )

    assert estimate.status is DiscrepancyEstimateStatus.UNRESOLVED_BELOW_KNOWN_UNCERTAINTY
    assert estimate.points[0].known_half_width == pytest.approx(0.10)
    assert estimate.points[0].minimum_discrepancy == pytest.approx(0.0)
