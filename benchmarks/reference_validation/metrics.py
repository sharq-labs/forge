"""Scoring a reference dataset. The comparison itself lives in Core.

This module used to hold its own copy of the comparison: unit resolution,
residual, tolerance, the pass/fail decision and a five-member status enum. That
is the same scientific judgement the Scientific Core now makes in
:func:`engcore.scientific.corpus.run_campaign`, and two implementations of one
judgement drift -- one of them silently, in whichever direction nobody is
testing.

So the comparison is gone from here and this is a thin call into Core. What is
kept is the convenience of scoring a whole authored catalog in one call, and a
report shape that is pleasant to print in a benchmark round.

``CampaignStatus`` is retained as an alias of the Core verdict, not as a second
vocabulary. It gained three members in the process -- correct refusal,
unexpected refusal and outside-applicability -- because those are scientific
results this package previously had no way to express and would have been
forced to score as ``ERROR``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Mapping

from engcore.scientific.corpus import (
    CaseVerdict,
    DatasetSplit,
    Prediction,
    PredictedValue,
    ValidationCampaign,
    ValidationCampaignReport,
    run_campaign,
)
from engcore.scientific.units.quantity import Quantity

from .contracts import ReferenceDataset

#: The Core verdict vocabulary, under the name this package already used.
CampaignStatus = CaseVerdict


@dataclass(frozen=True)
class CampaignCaseResult:
    case_id: str
    metric: str
    status: CaseVerdict
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
        result = {status.value: 0 for status in CaseVerdict}
        for case in self.cases:
            result[case.status.value] += 1
        return result

    @property
    def pass_fraction(self) -> float | None:
        """Empirical support only. A correct refusal is not in here."""
        scored = [item for item in self.cases if item.status.is_scored]
        if not scored:
            return None
        return sum(item.status.is_empirical_support for item in scored) / len(scored)

    @property
    def refusal_accuracy(self) -> float | None:
        """How often declining was the right call. Never mixed with the above.

        Reported separately for the same reason Core reports it separately: a
        correct refusal says the guardrail worked, not that the model is right
        there, and adding the two would let declining look like validating.
        """
        refusals = [item for item in self.cases if item.status.is_refusal]
        if not refusals:
            return None
        return sum(item.status.is_guardrail_success for item in refusals) / len(refusals)

    @property
    def normalized_residual_summary(self) -> dict[str, float] | None:
        values = sorted(
            item.normalized_residual
            for item in self.cases
            if item.normalized_residual is not None
            and math.isfinite(item.normalized_residual)
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

    @classmethod
    def from_core(cls, report: ValidationCampaignReport) -> "CampaignReport":
        return cls(
            dataset_id=report.dataset_id,
            dataset_version=report.dataset_version,
            source_snapshot_sha256=report.source_snapshot_sha256,
            normalized_dataset_sha256=report.normalized_dataset_sha256,
            cases=tuple(
                CampaignCaseResult(
                    case_id=item.case_id,
                    metric=item.metric,
                    status=item.verdict,
                    residual=item.residual,
                    tolerance=item.allowed,
                    normalized_residual=item.normalized_residual,
                    unit=item.unit or None,
                    detail=item.detail,
                )
                for item in report.comparisons
            ),
        )


def score_reference_dataset(
    dataset: ReferenceDataset,
    predictions: Mapping[tuple[str, str], Quantity | Prediction],
) -> CampaignReport:
    """Promote the authored dataset and score it through the Core corpus.

    A bare :class:`Quantity` is accepted for convenience and wrapped as a
    produced value. A caller that wants to record a *refusal* passes a
    :class:`~engcore.scientific.corpus.PredictionRefusal`, which is the only way
    to reach the correct-refusal verdict -- a refusal expressed as an absent
    prediction is ``MISSING``, and rightly so.
    """
    corpus = dataset.promote()
    splits = tuple({case.split for case in corpus.cases})
    if DatasetSplit.LOCKED_HOLDOUT in splits:
        raise ValueError(
            "this catalog declares locked-holdout points; score them through a "
            "ValidationCampaign carrying a registered HoldoutRelease rather than "
            "through the convenience scorer"
        )
    campaign = ValidationCampaign(
        campaign_id=f"{dataset.dataset_id}.campaign",
        version=dataset.version,
        dataset=corpus,
        splits=splits,
    )
    wrapped: dict[tuple[str, str], Prediction] = {
        key: PredictedValue(value) if isinstance(value, Quantity) else value
        for key, value in predictions.items()
    }
    return CampaignReport.from_core(run_campaign(campaign, wrapped))


__all__ = [
    "CampaignCaseResult",
    "CampaignReport",
    "CampaignStatus",
    "score_reference_dataset",
]
