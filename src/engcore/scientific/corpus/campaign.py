"""Campaigns: Core derives the verdict, the caller supplies only the prediction.

THE RULE THIS MODULE EXISTS FOR
--------------------------------
A caller hands in what its model produced. It does not hand in ``PASS``. The
comparison -- units, residual, the reviewed tolerance, the applicability
screen -- is made here, from the reference observation and the prediction,
so "this validated" is a statement Core made rather than one it was told.

A REFUSAL IS A SCIENTIFIC RESULT
---------------------------------
A model that declines to answer outside its declared domain is behaving
correctly, and a campaign that scored that as failure would push the system
toward answering anyway. So refusals split two ways:

``CORRECT_REFUSAL``
    the case is declared outside applicability and the model refused. This is
    the trust engine working.
``UNEXPECTED_REFUSAL``
    the case is inside the declared envelope and the model refused anyway.
    Something is wrong, and it is visible rather than averaged away.

The mirror case is equally important. A model that *answers* a case declared
outside its applicability has claimed something it does not support, so that
result is ``OUTSIDE_APPLICABILITY`` -- recorded, never scored as a pass.

APPLICABILITY IS THREE-VALUED AND SCORING NEEDS THE FIRST VALUE
----------------------------------------------------------------
Only ``INSIDE`` is scorable. ``UNDECLARED`` means nobody screened the case
against the model's declared domain, and an unscreened point cannot produce
empirical support: a PASS there would say the model is validated in a region
nothing established it claims, and a FAIL would hold it to a region it never
claimed. Both are ``APPLICABILITY_UNDECLARED``, which is recorded, is not
scored, does not enter coverage as evidence and does not widen an envelope.

It is also not silently promoted to ``OUTSIDE``. "Not established" and
"established to be outside" are different facts, and the second is a decision
somebody made.

A CORRECT REFUSAL IS NOT SCIENTIFIC SUPPORT
--------------------------------------------
This is the distinction most easily lost, so it is stated once here and
enforced everywhere below. A correct refusal means *the system correctly
recognized that it was not entitled to make the prediction*. It is evidence
about the guardrail, not about the science. It says nothing about whether the
model would have been right at that point, because the model never answered.

So a correct refusal never raises a pass count, never enters
``pass_fraction``, never turns an untested coverage cell into a supported one,
and never widens a validated envelope. If it did, a model could earn territory
by declining more often -- which is exactly backwards.

The two live on separate axes and are reported separately:
:attr:`ValidationCampaignReport.pass_fraction` for empirical support, and
:attr:`ValidationCampaignReport.refusal_accuracy` for guardrail correctness.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping

from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, base_unit
from .dataset import (
    Applicability,
    DatasetSplit,
    HoldoutLedger,
    HoldoutOpening,
    HoldoutRelease,
    ReferenceCase,
    ReferenceDataset,
    ReferenceObservation,
)
from .authority import EvidenceBinding, require_binding
from .source import CorpusError, CorpusLeakageError, require_quantity, text

PREDICTION_SCHEMA = schema_string("corpus_prediction")
COMPARISON_SCHEMA = schema_string("corpus_validation_comparison")
CAMPAIGN_SCHEMA = schema_string("corpus_validation_campaign")
CAMPAIGN_REPORT_SCHEMA = schema_string("corpus_validation_campaign_report")


class CaseVerdict(str, Enum):
    """What a campaign concluded about one reference observation."""

    PASS = "pass"
    FAIL = "fail"
    #: A reference observation with no reviewed acceptance tolerance. Never a pass.
    UNSCORED = "unscored"
    #: No prediction was offered at all.
    MISSING = "missing"
    #: The comparison itself could not be made (incompatible units, non-finite).
    ERROR = "error"
    #: Declined, and the case was declared outside the model's applicability.
    CORRECT_REFUSAL = "correct_refusal"
    #: Declined inside the claimed envelope. A defect, made visible.
    UNEXPECTED_REFUSAL = "unexpected_refusal"
    #: Answered a case declared outside applicability. Recorded, never scored.
    OUTSIDE_APPLICABILITY = "outside_applicability"
    #: The case's applicability was never established. UNDECLARED is not
    #: INSIDE: nobody screened this point against the model's declared domain,
    #: so neither agreement nor disagreement here is a statement about a region
    #: the model claims. Recorded, never scored, and never converted to
    #: OUTSIDE -- "not established" is its own state.
    APPLICABILITY_UNDECLARED = "applicability_undeclared"

    @property
    def is_scored(self) -> bool:
        """Whether this verdict contributes to a pass fraction."""
        return self in (CaseVerdict.PASS, CaseVerdict.FAIL)

    @property
    def is_empirical_support(self) -> bool:
        """Whether this verdict is evidence the model is RIGHT here.

        ``PASS`` and nothing else. In particular **not** ``CORRECT_REFUSAL``:
        a correct refusal means the system recognized it was not entitled to
        predict at this point, which says nothing whatever about whether the
        model would have been right. Counting it as support would let a model
        expand its validated envelope by declining more often, which is
        precisely backwards.
        """
        return self is CaseVerdict.PASS

    @property
    def is_guardrail_success(self) -> bool:
        """Whether this verdict is evidence the *guardrail* behaved correctly.

        A separate axis from empirical support, and deliberately never summed
        with it. ``refusal_accuracy`` is built from this; ``pass_fraction`` is
        built from :attr:`is_empirical_support`.
        """
        return self is CaseVerdict.CORRECT_REFUSAL

    @property
    def is_refusal(self) -> bool:
        """A refusal this corpus can judge as right or wrong.

        A refusal at an UNDECLARED case is deliberately NOT one. There is no
        declared envelope to place it inside or outside, so calling it correct
        or unexpected would be inventing the judgement. It is recorded as
        APPLICABILITY_UNDECLARED and kept out of refusal accuracy.
        """
        return self in (CaseVerdict.CORRECT_REFUSAL, CaseVerdict.UNEXPECTED_REFUSAL)


class RefusalKind(str, Enum):
    """Why a model declined. Declared by the producer, never inferred."""

    APPLICABILITY = "applicability"
    NUMERICAL = "numerical"
    INSUFFICIENT_DATA = "insufficient_data"
    UNSUPPORTED_REGIME = "unsupported_regime"
    OTHER = "other"


@dataclass(frozen=True)
class PredictedValue:
    """A model answered."""

    value: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "value", require_quantity(self.value, label="predicted value")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PREDICTION_SCHEMA,
            "outcome": "value",
            "value": self.value.to_dict(),
        }


@dataclass(frozen=True)
class PredictionRefusal:
    """A model declined, and said why."""

    kind: RefusalKind
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", RefusalKind(self.kind))
        object.__setattr__(self, "reason", text(self.reason, label="refusal reason"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PREDICTION_SCHEMA,
            "outcome": "refusal",
            "kind": self.kind.value,
            "reason": self.reason,
        }


Prediction = PredictedValue | PredictionRefusal


def prediction_from_dict(payload: Mapping[str, Any]) -> Prediction:
    require_schema(payload, PREDICTION_SCHEMA)
    outcome = payload.get("outcome")
    if outcome == "value":
        return PredictedValue(Quantity.from_dict(payload["value"]))
    if outcome == "refusal":
        return PredictionRefusal(RefusalKind(payload["kind"]), payload["reason"])
    raise CorpusError(f"unknown prediction outcome {outcome!r}")


@dataclass(frozen=True, order=True)
class ValidationComparison:
    """One reference observation, one prediction, and the verdict Core derived.

    ``residual`` and ``allowed`` are read as differences in the expected
    value's base unit, which is what makes a tolerance stated in ``delta_degC``
    comparable against a bound stated in kelvin without either of them being
    silently converted as an absolute temperature.
    """

    case_id: str
    metric: str
    split: DatasetSplit
    verdict: CaseVerdict
    expected: Quantity | None = None
    observed: Quantity | None = None
    residual: float | None = None
    allowed: float | None = None
    normalized_residual: float | None = None
    #: What the SOURCE says about its own number, read as a difference in
    #: ``unit``. Carried separately from ``allowed`` -- which is Forge's
    #: acceptance policy -- because a diagnosis that confuses the two attributes
    #: disagreement to measurement spread on the strength of a policy choice.
    source_uncertainty: float | None = None
    unit: str = ""
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", text(self.case_id, label="case_id"))
        object.__setattr__(self, "metric", text(self.metric, label="metric"))
        object.__setattr__(self, "split", DatasetSplit(self.split))
        object.__setattr__(self, "verdict", CaseVerdict(self.verdict))
        if self.verdict.is_scored:
            if self.normalized_residual is None:
                raise CorpusError(
                    f"{self.case_id}/{self.metric} is scored {self.verdict.value!r} but "
                    f"carries no normalized residual; a verdict and the number it came "
                    f"from are one result"
                )
            normalized = float(self.normalized_residual)
            if math.isnan(normalized) or normalized < 0.0:
                raise CorpusError(
                    f"{self.case_id}/{self.metric} normalized residual must be "
                    f"non-negative and not NaN"
                )
            derived = (
                CaseVerdict.PASS if normalized <= 1.0 else CaseVerdict.FAIL
            )
            if self.verdict is not derived:
                raise CorpusError(
                    f"{self.case_id}/{self.metric} declares verdict "
                    f"{self.verdict.value!r}, but normalized residual "
                    f"{normalized!r} derives {derived.value!r}; a stored verdict "
                    f"may report the comparison, not override it"
                )
            object.__setattr__(self, "normalized_residual", normalized)
        object.__setattr__(self, "unit", str(self.unit).strip())
        object.__setattr__(self, "detail", str(self.detail).strip())

    @property
    def key(self) -> tuple[str, str]:
        return self.case_id, self.metric

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COMPARISON_SCHEMA,
            "case_id": self.case_id,
            "metric": self.metric,
            "split": self.split.value,
            "verdict": self.verdict.value,
            "expected": None if self.expected is None else self.expected.to_dict(),
            "observed": None if self.observed is None else self.observed.to_dict(),
            "residual": self.residual,
            "allowed": self.allowed,
            "normalized_residual": self.normalized_residual,
            "source_uncertainty": self.source_uncertainty,
            "unit": self.unit,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationComparison":
        require_schema(payload, COMPARISON_SCHEMA)
        expected = payload.get("expected")
        observed = payload.get("observed")
        return cls(
            payload["case_id"],
            payload["metric"],
            DatasetSplit(payload["split"]),
            CaseVerdict(payload["verdict"]),
            None if expected is None else Quantity.from_dict(expected),
            None if observed is None else Quantity.from_dict(observed),
            payload.get("residual"),
            payload.get("allowed"),
            payload.get("normalized_residual"),
            payload.get("source_uncertainty"),
            payload.get("unit", ""),
            payload.get("detail", ""),
        )


def compare_observation(
    case: ReferenceCase,
    observation: ReferenceObservation,
    prediction: Prediction | None,
) -> ValidationComparison:
    """Derive one verdict. The only place a corpus PASS is produced."""

    common = {"case_id": observation.case_id, "metric": observation.metric, "split": case.split}

    if prediction is None:
        return ValidationComparison(
            **common,
            verdict=CaseVerdict.MISSING,
            expected=observation.expected,
            detail="no prediction was offered for this reference observation",
        )

    if isinstance(prediction, PredictionRefusal):
        if case.applicability is Applicability.UNDECLARED:
            # No declared envelope to be inside or outside of, so this refusal
            # is neither a guardrail success nor a defect. Saying either would
            # be inventing the judgement.
            return ValidationComparison(
                **common,
                verdict=CaseVerdict.APPLICABILITY_UNDECLARED,
                expected=observation.expected,
                detail=(
                    f"declined at a case whose applicability was never "
                    f"established ({prediction.kind.value}: {prediction.reason}); "
                    f"this is neither a correct nor an unexpected refusal"
                ),
            )
        outside = case.applicability is Applicability.OUTSIDE
        return ValidationComparison(
            **common,
            verdict=CaseVerdict.CORRECT_REFUSAL if outside else CaseVerdict.UNEXPECTED_REFUSAL,
            expected=observation.expected,
            detail=(
                f"{prediction.kind.value}: {prediction.reason}"
                if outside
                else (
                    f"refused inside the declared envelope "
                    f"({prediction.kind.value}: {prediction.reason})"
                )
            ),
        )

    if not isinstance(prediction, PredictedValue):
        raise CorpusError(
            "a prediction must be PredictedValue, PredictionRefusal or None"
        )

    if case.applicability is Applicability.OUTSIDE:
        return ValidationComparison(
            **common,
            verdict=CaseVerdict.OUTSIDE_APPLICABILITY,
            expected=observation.expected,
            observed=prediction.value,
            detail=(
                "the model produced a value at a case declared outside its "
                "applicability; this is recorded, not scored"
            ),
        )

    if case.applicability is not Applicability.INSIDE:
        # UNDECLARED. Scoring would manufacture support for, or hold the model
        # to, a region nobody established it claims.
        return ValidationComparison(
            **common,
            verdict=CaseVerdict.APPLICABILITY_UNDECLARED,
            expected=observation.expected,
            observed=prediction.value,
            detail=(
                "this case was never screened against the model's declared "
                "applicability, so its agreement or disagreement is not "
                "empirical evidence about a claimed region"
            ),
        )

    if observation.acceptance_tolerance is None:
        return ValidationComparison(
            **common,
            verdict=CaseVerdict.UNSCORED,
            expected=observation.expected,
            observed=prediction.value,
            detail=(
                "the reference observation exists but no reviewed acceptance "
                "tolerance is bound to it; missing policy is not agreement"
            ),
        )

    try:
        unit = base_unit(observation.expected.units)
        expected_value = observation.expected.magnitude_in(unit)
        observed_value = prediction.value.magnitude_in(unit)
        allowed = observation.acceptance_tolerance.magnitude_in(unit)
        reported = (
            None
            if observation.source_uncertainty is None
            else observation.source_uncertainty.magnitude_in(unit)
        )
    except Exception as exc:  # noqa: BLE001 -- the campaign records, it does not abort
        return ValidationComparison(
            **common,
            verdict=CaseVerdict.ERROR,
            expected=observation.expected,
            observed=prediction.value,
            detail=f"{type(exc).__name__}: {exc}",
        )

    residual = abs(observed_value - expected_value)
    if not math.isfinite(residual):
        return ValidationComparison(
            **common,
            verdict=CaseVerdict.ERROR,
            expected=observation.expected,
            observed=prediction.value,
            unit=unit,
            detail="residual is not finite",
        )
    if allowed == 0.0:
        normalized = 0.0 if residual == 0.0 else math.inf
    else:
        normalized = residual / allowed
    return ValidationComparison(
        **common,
        verdict=CaseVerdict.PASS if normalized <= 1.0 else CaseVerdict.FAIL,
        expected=observation.expected,
        observed=prediction.value,
        residual=residual,
        allowed=allowed,
        normalized_residual=normalized,
        source_uncertainty=reported,
        unit=unit,
    )


@dataclass(frozen=True)
class ValidationCampaign:
    """What is to be evaluated, over which splits, against which dataset.

    A campaign that wants the locked holdout must carry the release; asking for
    ``LOCKED_HOLDOUT`` without one is refused at construction rather than
    quietly producing an empty holdout result that reads like a clean run.
    """

    campaign_id: str
    version: str
    dataset: ReferenceDataset
    splits: tuple[DatasetSplit, ...]
    #: WHICH SCIENCE this campaign validates. Without it a campaign report is a
    #: set of numbers that any computation could claim, which is how a validated
    #: envelope ends up certifying a model it was never about.
    target: EvidenceBinding | None = None
    holdout_release: HoldoutRelease | None = None
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "campaign_id", text(self.campaign_id, label="campaign_id"))
        object.__setattr__(self, "version", text(self.version, label="version"))
        if not isinstance(self.dataset, ReferenceDataset):
            raise CorpusError("a campaign requires a ReferenceDataset")
        splits = tuple(sorted({DatasetSplit(item) for item in self.splits}, key=lambda i: i.value))
        if not splits:
            raise CorpusError("a campaign must name at least one dataset split")
        object.__setattr__(self, "splits", splits)
        if self.target is not None:
            require_binding(self.target, label="campaign target")
        if DatasetSplit.LOCKED_HOLDOUT in splits and self.holdout_release is None:
            raise CorpusError(
                "a campaign over the locked holdout requires a registered "
                "HoldoutRelease; there is no unrecorded evaluation of it"
            )
        if self.holdout_release is not None:
            if not isinstance(self.holdout_release, HoldoutRelease):
                raise CorpusError("holdout_release must be a HoldoutRelease")
            # A RELEASE IS REGISTERED FOR ONE EVALUATION. Checked here, at the
            # only place a campaign can reach the holdout, so a release granted
            # for one evaluation cannot silently open the holdout for another.
            self.holdout_release.require_for(self.campaign_id, self.version)
            # Validates the dataset digest binding WITHOUT exposing cases:
            # checking permission is not the same act as using it.
            self.dataset.require_release(self.holdout_release)
        object.__setattr__(self, "description", str(self.description).strip())

    def cases(self) -> tuple[ReferenceCase, ...]:
        """The cases this campaign may see BEFORE the holdout is opened.

        A campaign covering the locked holdout refuses here. That is the whole
        point: predictions are built from the cases a caller can reach, so a
        ``cases()`` that handed over the locked ones let anybody inspect them
        without going near the ledger -- and the earlier version of this
        module's own regression did exactly that. Open it first::

            opened = campaign.open_holdout(ledger)
            predictions = {...for case in opened.cases()...}
            run_campaign(opened, predictions)
        """
        if DatasetSplit.LOCKED_HOLDOUT in self.splits:
            raise CorpusLeakageError(
                f"campaign {self.campaign_id!r} covers the locked holdout, whose "
                f"cases are not visible until it is opened; call "
                f"open_holdout(ledger) and take the cases from the opened campaign"
            )
        return self._cases_for(self.splits)

    def _cases_for(self, splits: tuple[DatasetSplit, ...], opening=None):
        selected: list[ReferenceCase] = []
        for split in splits:
            if split is DatasetSplit.CALIBRATION:
                selected.extend(self.dataset.calibration_cases())
            elif split is DatasetSplit.VALIDATION:
                selected.extend(self.dataset.validation_cases())
            else:
                selected.extend(self.dataset.opened_holdout_cases(opening))
        return tuple(sorted(selected))

    def open_holdout(self, ledger: HoldoutLedger) -> "OpenedValidationCampaign":
        """Open the locked holdout through an authority, once, and return a view.

        The returned view is the only object that can produce the locked cases.
        A campaign that does not cover the holdout has nothing to open and says
        so rather than quietly handing back a view that means nothing.
        """
        if DatasetSplit.LOCKED_HOLDOUT not in self.splits:
            raise CorpusError(
                f"campaign {self.campaign_id!r} covers no locked holdout, so "
                f"there is nothing to open"
            )
        if ledger is None:
            raise CorpusLeakageError(
                "opening a locked holdout requires a holdout-opening authority"
            )
        opening = ledger.open(self.holdout_release)
        return OpenedValidationCampaign(self, opening)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CAMPAIGN_SCHEMA,
            "campaign_id": self.campaign_id,
            "version": self.version,
            "dataset": self.dataset.to_dict(),
            "splits": [item.value for item in self.splits],
            "target": None if self.target is None else self.target.to_dict(),
            "holdout_release": (
                None if self.holdout_release is None else self.holdout_release.to_dict()
            ),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationCampaign":
        require_schema(payload, CAMPAIGN_SCHEMA)
        release = payload.get("holdout_release")
        target = payload.get("target")
        return cls(
            payload["campaign_id"],
            payload["version"],
            ReferenceDataset.from_dict(payload["dataset"]),
            tuple(DatasetSplit(item) for item in payload["splits"]),
            None if target is None else EvidenceBinding.from_dict(target),
            None if release is None else HoldoutRelease.from_dict(release),
            payload.get("description", ""),
        )


@dataclass(frozen=True)
class OpenedValidationCampaign:
    """A campaign whose locked holdout has been opened, and the record of it.

    Only this view can produce locked cases, and it can only be built by
    :meth:`ValidationCampaign.open_holdout`, which goes through the ledger. So
    the sequence "inspect the holdout, then decide whether to record having
    looked" has no expression: the looking requires the record.
    """

    campaign: "ValidationCampaign"
    opening: HoldoutOpening

    def __post_init__(self) -> None:
        if not isinstance(self.campaign, ValidationCampaign):
            raise CorpusError("an opened campaign wraps a ValidationCampaign")
        if not isinstance(self.opening, HoldoutOpening):
            raise CorpusLeakageError(
                "an opened campaign requires the HoldoutOpening that opened it"
            )
        release = self.campaign.holdout_release
        if release is None or self.opening.release_digest != release.digest:
            raise CorpusLeakageError(
                "the opening does not correspond to this campaign's holdout release"
            )

    @property
    def campaign_id(self) -> str:
        return self.campaign.campaign_id

    @property
    def version(self) -> str:
        return self.campaign.version

    @property
    def dataset(self) -> ReferenceDataset:
        return self.campaign.dataset

    @property
    def splits(self) -> tuple[DatasetSplit, ...]:
        return self.campaign.splits

    @property
    def target(self) -> EvidenceBinding | None:
        return self.campaign.target

    def cases(self) -> tuple[ReferenceCase, ...]:
        """Every case this campaign covers, locked ones included."""
        return self.campaign._cases_for(self.splits, self.opening)


@dataclass(frozen=True)
class ValidationCampaignReport:
    """What one campaign found, bound to the exact dataset it was run against."""

    campaign_id: str
    campaign_version: str
    dataset_id: str
    dataset_version: str
    source_snapshot_sha256: str
    normalized_dataset_sha256: str
    splits: tuple[DatasetSplit, ...]
    comparisons: tuple[ValidationComparison, ...]
    #: The scientific authority this campaign validated. Travels with the
    #: report so coverage, an envelope and finally certification can all ask
    #: the same question: is this evidence about the computation in front of me.
    target: EvidenceBinding | None = None
    #: The digest of the actual :class:`HoldoutOpening` -- the event -- not of
    #: the release that permitted it. A release digest says the holdout *could*
    #: have been opened; this says it *was*, by whom and when.
    holdout_opening_digest: str = ""

    def __post_init__(self) -> None:
        comparisons = tuple(sorted(self.comparisons))
        if any(not isinstance(item, ValidationComparison) for item in comparisons):
            raise CorpusError("campaign report requires ValidationComparison records")
        keys = [item.key for item in comparisons]
        if len(keys) != len(set(keys)):
            raise CorpusError("campaign report repeats a case_id/metric pair")
        object.__setattr__(self, "comparisons", comparisons)
        object.__setattr__(
            self,
            "splits",
            tuple(sorted({DatasetSplit(i) for i in self.splits}, key=lambda i: i.value)),
        )
        declared_splits = set(self.splits)
        stray_splits = sorted({
            item.split.value
            for item in comparisons
            if item.split not in declared_splits
        })
        if stray_splits:
            raise CorpusError(
                f"campaign report carries comparison split(s) {stray_splits} "
                f"outside its declared splits {[item.value for item in self.splits]}"
            )
        if self.target is not None:
            require_binding(self.target, label="campaign report target")
        opening = str(self.holdout_opening_digest).strip().lower()
        if opening and (
            len(opening) != 64 or any(ch not in "0123456789abcdef" for ch in opening)
        ):
            raise CorpusError("holdout_opening_digest must be sha256 hex")
        if DatasetSplit.LOCKED_HOLDOUT in self.splits and not opening:
            raise CorpusError(
                "a report covering the locked holdout must name the release that "
                "opened it; an unrecorded opening is the thing the lock exists "
                "to prevent"
            )
        if opening and DatasetSplit.LOCKED_HOLDOUT not in self.splits:
            raise CorpusError(
                "a holdout opening is recorded but no holdout split was scored"
            )
        object.__setattr__(self, "holdout_opening_digest", opening)

    @property
    def counts(self) -> dict[str, int]:
        result = {verdict.value: 0 for verdict in CaseVerdict}
        for item in self.comparisons:
            result[item.verdict.value] += 1
        return result

    @property
    def pass_fraction(self) -> float | None:
        """Over scored cases only. ``None`` when nothing was scorable.

        Deliberately not "passes divided by cases": an unscored observation and
        a correct refusal are neither successes nor failures, and folding them
        into a percentage would let a dataset with no reviewed tolerances
        report a respectable number.
        """
        scored = [item for item in self.comparisons if item.verdict.is_scored]
        if not scored:
            return None
        return sum(item.verdict.is_empirical_support for item in scored) / len(scored)

    @property
    def refusal_accuracy(self) -> float | None:
        """How often a refusal was the right call. A guardrail metric, not support.

        Over refusals only: correct refusals divided by all refusals. ``None``
        when nothing was refused, because a model that never declined has no
        guardrail record -- which is not the same as a perfect one.

        Kept rigorously apart from :attr:`pass_fraction`. A system can have
        excellent refusal accuracy and no validated envelope at all: it would
        mean it reliably knows when to stay quiet, and has not yet been shown
        to be right about anything.
        """
        refusals = [item for item in self.comparisons if item.verdict.is_refusal]
        if not refusals:
            return None
        return sum(item.verdict.is_guardrail_success for item in refusals) / len(refusals)

    @property
    def guardrail_counts(self) -> dict[str, int]:
        """Correct against unexpected refusals, and the answers that should not have been."""
        return {
            "correct_refusals": sum(
                item.verdict is CaseVerdict.CORRECT_REFUSAL for item in self.comparisons
            ),
            "unexpected_refusals": sum(
                item.verdict is CaseVerdict.UNEXPECTED_REFUSAL for item in self.comparisons
            ),
            "answered_outside_applicability": sum(
                item.verdict is CaseVerdict.OUTSIDE_APPLICABILITY
                for item in self.comparisons
            ),
            "applicability_undeclared": sum(
                item.verdict is CaseVerdict.APPLICABILITY_UNDECLARED
                for item in self.comparisons
            ),
        }

    def for_split(self, split: DatasetSplit) -> tuple[ValidationComparison, ...]:
        wanted = DatasetSplit(split)
        return tuple(item for item in self.comparisons if item.split is wanted)

    def failures(self) -> tuple[ValidationComparison, ...]:
        return tuple(item for item in self.comparisons if item.verdict is CaseVerdict.FAIL)

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CAMPAIGN_REPORT_SCHEMA,
            "campaign_id": self.campaign_id,
            "campaign_version": self.campaign_version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "normalized_dataset_sha256": self.normalized_dataset_sha256,
            "splits": [item.value for item in self.splits],
            "comparisons": [item.to_dict() for item in self.comparisons],
            "target": None if self.target is None else self.target.to_dict(),
            "holdout_opening_digest": self.holdout_opening_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationCampaignReport":
        require_schema(payload, CAMPAIGN_REPORT_SCHEMA)
        return cls(
            payload["campaign_id"],
            payload["campaign_version"],
            payload["dataset_id"],
            payload["dataset_version"],
            payload["source_snapshot_sha256"],
            payload["normalized_dataset_sha256"],
            tuple(DatasetSplit(i) for i in payload["splits"]),
            tuple(ValidationComparison.from_dict(i) for i in payload["comparisons"]),
            (
                None
                if payload.get("target") is None
                else EvidenceBinding.from_dict(payload["target"])
            ),
            payload.get("holdout_opening_digest", ""),
        )


def run_campaign(
    campaign: "ValidationCampaign | OpenedValidationCampaign",
    predictions: Mapping[tuple[str, str], Prediction],
    *,
    holdout_ledger: HoldoutLedger | None = None,
) -> ValidationCampaignReport:
    """Score one campaign. Core derives every verdict from the evidence.

    A prediction offered for a case the campaign was not permitted to see is
    refused rather than ignored: it is the signature of a path that read the
    locked holdout.

    THE OPENING HAPPENS HERE, BEFORE THE LOCKED CASES ARE TOUCHED. A ledger
    that only worked when a caller remembered to invoke it beside the campaign
    enforced nothing about the campaign, so a locked-holdout campaign now
    requires a :class:`HoldoutLedger` and opens through it on the authoritative
    path. What the ledger guarantees is the ledger's business -- see
    :class:`InMemoryHoldoutLedger` for the exact scope of the in-process one.
    """
    opening: HoldoutOpening | None = None
    if isinstance(campaign, OpenedValidationCampaign):
        if holdout_ledger is not None:
            raise CorpusLeakageError(
                "this campaign is already open; opening it again through a "
                "ledger would be a second look"
            )
        opening = campaign.opening
    elif DatasetSplit.LOCKED_HOLDOUT in campaign.splits:
        if holdout_ledger is None:
            raise CorpusLeakageError(
                "scoring a locked holdout requires a holdout-opening authority; "
                "without one nothing records that the holdout was opened and "
                "nothing can refuse a second opening"
            )
        # The single-call form: open here, then score the opened view.
        campaign = campaign.open_holdout(holdout_ledger)
        opening = campaign.opening
    cases = {case.case_id: case for case in campaign.cases()}
    observations = campaign.dataset.observations_for(cases.values())
    permitted = {item.key for item in observations}
    offered = set(predictions)
    trespass = sorted(key for key in offered - permitted if key[0] not in cases)
    if trespass:
        raise CorpusError(
            f"predictions were offered for observations outside this campaign's "
            f"splits: {trespass}"
        )
    comparisons = tuple(
        compare_observation(cases[item.case_id], item, predictions.get(item.key))
        for item in observations
    )
    dataset = campaign.dataset
    return ValidationCampaignReport(
        campaign_id=campaign.campaign_id,
        campaign_version=campaign.version,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        source_snapshot_sha256=dataset.snapshot.snapshot_sha256,
        normalized_dataset_sha256=dataset.normalized_digest,
        splits=campaign.splits,
        comparisons=comparisons,
        target=campaign.target,
        holdout_opening_digest="" if opening is None else opening.digest,
    )


__all__ = [
    "CAMPAIGN_REPORT_SCHEMA",
    "CAMPAIGN_SCHEMA",
    "COMPARISON_SCHEMA",
    "PREDICTION_SCHEMA",
    "CaseVerdict",
    "Prediction",
    "PredictedValue",
    "PredictionRefusal",
    "RefusalKind",
    "OpenedValidationCampaign",
    "ValidationCampaign",
    "ValidationCampaignReport",
    "ValidationComparison",
    "compare_observation",
    "prediction_from_dict",
    "run_campaign",
]
