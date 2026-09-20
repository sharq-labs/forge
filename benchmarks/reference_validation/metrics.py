"""Bulk scoring for external-reference validation campaigns."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from statistics import median
from typing import Mapping

from engcore.scientific.units.quantity import Quantity, base_unit

from .contracts import ReferenceDataset, ReferencePoint


class CampaignStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MISSING = "missing_prediction"
    UNSCORED = "unscored"
    ERROR = "error"


@dataclass(frozen=True)
class CampaignCaseResult:
    case_id: str
    metric: str
    status: CampaignStatus
    residual: float | None = None
    tolerance: float | None = None
    normalized_residual: float | None = None
    unit: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class CampaignReport:
    dataset_id: str
    dataset_version: str
    source_snapshot_sha256: str
    normalized_dataset_sha256: str
    cases: tuple[CampaignCaseResult, ...]

    @property
    def counts(self) -> dict[str, int]:
        result = {status.value: 0 for status in CampaignStatus}
        for case in self.cases:
            result[case.status.value] += 1
        return result

    @property
    def pass_fraction(self) -> float | None:
        scored = [
            item
            for item in self.cases
            if item.status in (CampaignStatus.PASS, CampaignStatus.FAIL)
        ]
        if not scored:
            return None
        return sum(item.status is CampaignStatus.PASS for item in scored) / len(scored)

    @property
    def normalized_residual_summary(self) -> dict[str, float] | None:
        values = sorted(
            item.normalized_residual
            for item in self.cases
            if item.normalized_residual is not None and math.isfinite(item.normalized_residual)
        )
        if not values:
            return None

        def percentile(q: float) -> float:
            if len(values) == 1:
                return values[0]
            index = q * (len(values) - 1)
            lower = int(math.floor(index))
            upper = int(math.ceil(index))
            if lower == upper:
                return values[lower]
            weight = index - lower
            return values[lower] * (1.0 - weight) + values[upper] * weight

        return {"p50": median(values), "p95": percentile(0.95), "max": max(values)}


def _score_point(point: ReferencePoint, prediction: Quantity | None) -> CampaignCaseResult:
    if prediction is None:
        return CampaignCaseResult(
            point.case_id, point.metric, CampaignStatus.MISSING,
            detail="prediction is absent",
        )
    if point.acceptance_tolerance is None:
        return CampaignCaseResult(
            point.case_id, point.metric, CampaignStatus.UNSCORED,
            detail=(
                "reference observation exists, but no reviewed acceptance "
                "tolerance is bound to this point"
            ),
        )
    try:
        expected = Quantity(point.expected_value, point.expected_unit)
        unit = base_unit(expected.units)
        actual_value = prediction.magnitude_in(unit)
        expected_value = expected.magnitude_in(unit)
        tolerance_value = point.acceptance_tolerance.quantity().magnitude_as_spread_in(unit)
        residual = abs(actual_value - expected_value)
        if tolerance_value == 0.0:
            normalized = 0.0 if residual == 0.0 else float("inf")
        else:
            normalized = residual / tolerance_value
        status = CampaignStatus.PASS if normalized <= 1.0 else CampaignStatus.FAIL
        return CampaignCaseResult(
            point.case_id,
            point.metric,
            status,
            residual=residual,
            tolerance=tolerance_value,
            normalized_residual=normalized,
            unit=unit,
        )
    except Exception as exc:  # noqa: BLE001 - campaign records the failure instead of aborting
        return CampaignCaseResult(
            point.case_id, point.metric, CampaignStatus.ERROR,
            detail=f"{type(exc).__name__}: {exc}",
        )


def score_reference_dataset(
    dataset: ReferenceDataset,
    predictions: Mapping[tuple[str, str], Quantity],
) -> CampaignReport:
    cases = tuple(_score_point(point, predictions.get(point.key)) for point in dataset.points)
    return CampaignReport(
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        source_snapshot_sha256=dataset.source_snapshot_sha256,
        normalized_dataset_sha256=dataset.normalized_digest,
        cases=cases,
    )


__all__ = [
    "CampaignCaseResult",
    "CampaignReport",
    "CampaignStatus",
    "score_reference_dataset",
]
