"""What the disagreement supports saying, after the alternatives are checked.

The motivating case: parameter fitting reached an excellent calibration fit and
then performed badly on held-out cases. Read carelessly that is "the
calibration failed". It is not -- the calibration succeeded at what it was
asked to do.

But the opposite careless reading is just as wrong, and it is the one a trust
engine is likely to encode:

    good calibration fit + poor holdout  =>  the model form is inadequate

That inference is not valid on its own. Independent failure has at least six
other explanations, every one of which this system can sometimes see:

* the independent cases sit in a different regime, or outside declared
  applicability -- a regime shift, not a form problem;
* the numerics failed, or the numerical study that would have shown they did
  not was never run;
* the disagreement is inside what the source says about its own numbers --
  judged against the source's stated uncertainty under a declared coverage
  policy, never against Forge's acceptance tolerance, which is a policy choice
  and would make the diagnosis depend on how strict somebody was feeling;
* a parameter was never identifiable, so "the fitted value" was never
  constrained by the data and cannot be expected to transfer;
* the parameter set was fitted against a different dataset than the one being
  scored -- a context mismatch;
* a governance problem: evidence acting as both the fit and its own test.

So the strongest conclusion available here is ``MODEL_FORM_SUSPECTED``, and its
meaning is exact: *the evidence is consistent with model-form inadequacy after
the alternative causes this system can currently check have been checked*. It
becomes ``confidence="supported"`` only when every checkable alternative was
ruled out; while any remains unchecked or outstanding it stays
``"suggestive"``, and when an alternative is positively indicated that cause is
returned instead.

Two things this never does. It never upgrades to certainty -- there is no
``MODEL_FORM_CONFIRMED``, because confirmation would require ruling out causes
this system cannot see. And it never names the missing physics: "residuals grow
along this operating coordinate" is evidence the form is insufficient there,
not a finding about which term is absent. That judgement belongs to a person
with evidence this record does not contain, and a diagnosis that guessed would
be believed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from ..serialization import require_schema, schema_string
from .calibration import CalibratedParameterSet, Identifiability
from .campaign import CaseVerdict, ValidationCampaignReport
from .coverage import FailureCluster
from .dataset import DatasetSplit
from .numerical import NumericalEvidence
from .source import CorpusError, text

DIAGNOSIS_SCHEMA = schema_string("corpus_model_form_diagnosis")
CAUSE_CHECK_SCHEMA = schema_string("corpus_alternative_cause_check")


class InadequacyKind(str, Enum):
    CALIBRATION_PARAMETER = "calibration_parameter"
    #: Consistent with model-form inadequacy AFTER the checkable alternatives
    #: were checked. Never a statement that the form is certainly at fault, and
    #: never a statement about which physics is missing.
    MODEL_FORM_SUSPECTED = "model_form_suspected"
    APPLICABILITY = "applicability"
    NUMERICAL = "numerical"
    MEASUREMENT_UNCERTAINTY = "measurement_uncertainty"
    IDENTIFIABILITY = "identifiability"
    CONTEXT_MISMATCH = "context_mismatch"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class AlternativeCause(str, Enum):
    """Explanations for independent failure other than the model's form."""

    APPLICABILITY = "applicability"
    NUMERICAL = "numerical"
    MEASUREMENT_UNCERTAINTY = "measurement_uncertainty"
    IDENTIFIABILITY = "identifiability"
    CONTEXT_MISMATCH = "context_mismatch"


class CauseState(str, Enum):
    """What the available evidence says about one alternative cause.

    ``NOT_CHECKABLE`` is not ``RULED_OUT``. A cause nobody supplied the
    evidence to examine remains an open explanation, and treating silence as
    exoneration is how a diagnosis becomes overconfident.
    """

    RULED_OUT = "ruled_out"
    INDICATED = "indicated"
    NOT_CHECKABLE = "not_checkable"


@dataclass(frozen=True)
class MeasurementInterpretation:
    """How a stated source uncertainty is read as an interval. Declared, not assumed.

    A source reporting ``u`` has not said what fraction of outcomes lie within
    ``u``; that depends on what kind of uncertainty it is. So the coverage
    factor is an explicit, recorded policy rather than a constant buried in a
    comparison, and the default states its own assumption.
    """

    policy_id: str = "corpus.measurement.k2"
    coverage_factor: float = 2.0
    rationale: str = (
        "a coverage factor of 2 read as approximately 95% for a normal "
        "distribution; stated here because the source did not state one"
    )

    def __post_init__(self) -> None:
        factor = float(self.coverage_factor)
        if not (factor > 0.0) or factor != factor or factor in (float("inf"),):
            raise CorpusError("measurement coverage factor must be finite and positive")
        object.__setattr__(self, "coverage_factor", factor)
        object.__setattr__(self, "policy_id", text(self.policy_id, label="policy_id"))
        object.__setattr__(self, "rationale", text(self.rationale, label="rationale"))

    def describe(self) -> str:
        return f"{self.coverage_factor:g}x ({self.policy_id})"


DEFAULT_MEASUREMENT_INTERPRETATION = MeasurementInterpretation()


@dataclass(frozen=True, order=True)
class CauseCheck:
    cause: AlternativeCause
    state: CauseState
    why: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "cause", AlternativeCause(self.cause))
        object.__setattr__(self, "state", CauseState(self.state))
        object.__setattr__(self, "why", text(self.why, label="cause check why"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CAUSE_CHECK_SCHEMA,
            "cause": self.cause.value,
            "state": self.state.value,
            "why": self.why,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CauseCheck":
        require_schema(payload, CAUSE_CHECK_SCHEMA)
        return cls(
            AlternativeCause(payload["cause"]),
            CauseState(payload["state"]),
            payload["why"],
        )


#: Which InadequacyKind an indicated alternative cause resolves to.
_CAUSE_KIND = {
    AlternativeCause.APPLICABILITY: InadequacyKind.APPLICABILITY,
    AlternativeCause.NUMERICAL: InadequacyKind.NUMERICAL,
    AlternativeCause.MEASUREMENT_UNCERTAINTY: InadequacyKind.MEASUREMENT_UNCERTAINTY,
    AlternativeCause.IDENTIFIABILITY: InadequacyKind.IDENTIFIABILITY,
    AlternativeCause.CONTEXT_MISMATCH: InadequacyKind.CONTEXT_MISMATCH,
}


@dataclass(frozen=True)
class ModelFormDiagnosis:
    """What the campaign's evidence supports saying about the disagreement.

    ``confidence`` is not a probability. It is a statement about how much the
    evidence carries: ``"supported"`` when every alternative this system can
    check was ruled out, ``"suggestive"`` when a pattern is present but
    alternatives remain unchecked, ``"none"`` when there is nothing to say.
    """

    kind: InadequacyKind
    why: str
    confidence: str
    calibration_pass_fraction: float | None = None
    independent_pass_fraction: float | None = None
    clusters: tuple[FailureCluster, ...] = ()
    cause_checks: tuple[CauseCheck, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", InadequacyKind(self.kind))
        object.__setattr__(self, "why", text(self.why, label="diagnosis why"))
        confidence = text(self.confidence, label="diagnosis confidence")
        if confidence not in {"none", "suggestive", "supported"}:
            raise CorpusError(
                "diagnosis confidence must be 'none', 'suggestive' or 'supported'; "
                "it is a statement about the weight of evidence, not a probability"
            )
        object.__setattr__(self, "confidence", confidence)
        clusters = tuple(sorted(self.clusters))
        if any(not isinstance(item, FailureCluster) for item in clusters):
            raise CorpusError("diagnosis clusters must be FailureCluster records")
        object.__setattr__(self, "clusters", clusters)
        checks = tuple(sorted(self.cause_checks))
        if any(not isinstance(item, CauseCheck) for item in checks):
            raise CorpusError("diagnosis cause_checks must be CauseCheck records")
        object.__setattr__(self, "cause_checks", checks)
        if (
            self.kind is InadequacyKind.MODEL_FORM_SUSPECTED
            and confidence == "supported"
            and self.outstanding_alternatives
        ):
            raise CorpusError(
                "a model-form suspicion cannot be 'supported' while alternative "
                f"causes remain unexamined: {list(self.outstanding_alternatives)}"
            )
        object.__setattr__(
            self,
            "evidence",
            tuple(str(item).strip() for item in self.evidence if str(item).strip()),
        )

    @property
    def ruled_out_alternatives(self) -> tuple[str, ...]:
        return tuple(
            item.cause.value
            for item in self.cause_checks
            if item.state is CauseState.RULED_OUT
        )

    @property
    def outstanding_alternatives(self) -> tuple[str, ...]:
        """Causes not ruled out. Empty is what 'supported' requires."""
        return tuple(
            item.cause.value
            for item in self.cause_checks
            if item.state is not CauseState.RULED_OUT
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DIAGNOSIS_SCHEMA,
            "kind": self.kind.value,
            "why": self.why,
            "confidence": self.confidence,
            "calibration_pass_fraction": self.calibration_pass_fraction,
            "independent_pass_fraction": self.independent_pass_fraction,
            "clusters": [item.to_dict() for item in self.clusters],
            "cause_checks": [item.to_dict() for item in self.cause_checks],
            "outstanding_alternatives": list(self.outstanding_alternatives),
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelFormDiagnosis":
        require_schema(payload, DIAGNOSIS_SCHEMA)
        return cls(
            InadequacyKind(payload["kind"]),
            payload["why"],
            payload["confidence"],
            payload.get("calibration_pass_fraction"),
            payload.get("independent_pass_fraction"),
            tuple(FailureCluster.from_dict(i) for i in payload.get("clusters", ())),
            tuple(CauseCheck.from_dict(i) for i in payload.get("cause_checks", ())),
            tuple(payload.get("evidence", ())),
        )


def _fraction(
    report: ValidationCampaignReport, splits: tuple[DatasetSplit, ...]
) -> tuple[float | None, int]:
    scored = [
        item
        for item in report.comparisons
        if item.split in splits and item.verdict.is_scored
    ]
    if not scored:
        return None, 0
    passes = sum(item.verdict.is_empirical_support for item in scored)
    return passes / len(scored), len(scored)


def _check_applicability(report: ValidationCampaignReport) -> CauseCheck:
    outside = sum(
        1
        for item in report.comparisons
        if item.verdict is CaseVerdict.OUTSIDE_APPLICABILITY
    )
    refusals = report.guardrail_counts["correct_refusals"]
    if outside or refusals:
        return CauseCheck(
            AlternativeCause.APPLICABILITY,
            CauseState.INDICATED,
            f"{outside} case(s) were answered outside the declared applicability "
            f"and {refusals} were correctly refused; a regime shift explains "
            f"disagreement without implicating the model's form",
        )
    return CauseCheck(
        AlternativeCause.APPLICABILITY,
        CauseState.RULED_OUT,
        "every scored case lies inside the declared applicability",
    )


def _check_numerical(numerical: NumericalEvidence | None) -> CauseCheck:
    if numerical is None:
        return CauseCheck(
            AlternativeCause.NUMERICAL,
            CauseState.NOT_CHECKABLE,
            "no numerical evidence was supplied, so a numerical cause cannot be "
            "excluded",
        )
    if numerical.violated_checks:
        return CauseCheck(
            AlternativeCause.NUMERICAL,
            CauseState.INDICATED,
            f"numerical checks {list(numerical.violated_checks)} are violated",
        )
    if numerical.absent_checks:
        return CauseCheck(
            AlternativeCause.NUMERICAL,
            CauseState.NOT_CHECKABLE,
            f"declared numerical checks {list(numerical.absent_checks)} were not "
            f"performed, so the numerics are not shown to be sound",
        )
    return CauseCheck(
        AlternativeCause.NUMERICAL,
        CauseState.RULED_OUT,
        "every declared numerical check was performed and none is violated",
    )


def _check_measurement(
    report: ValidationCampaignReport, interpretation: "MeasurementInterpretation"
) -> CauseCheck:
    """Is the disagreement inside what the SOURCE says about its own numbers?

    Derived from ``source_uncertainty`` and never from the acceptance
    tolerance. An earlier version compared the residual against twice the
    reviewed tolerance, which is a Forge policy choice: it would have called a
    disagreement "measurement spread" purely because somebody set a tight
    tolerance, and called the same physical disagreement a model problem under
    a loose one. The corpus separates those two numbers deliberately, and a
    diagnosis that collapses them throws the separation away.

    Where the source stated no uncertainty, the honest answer is
    ``NOT_CHECKABLE``. There is nothing to compare against, and silence is not
    exoneration.
    """
    failures = [item for item in report.failures() if item.residual is not None]
    if not failures:
        return CauseCheck(
            AlternativeCause.MEASUREMENT_UNCERTAINTY,
            CauseState.RULED_OUT,
            "there are no failing scored cases to attribute",
        )
    unquantified = [item for item in failures if item.source_uncertainty is None]
    if unquantified:
        return CauseCheck(
            AlternativeCause.MEASUREMENT_UNCERTAINTY,
            CauseState.NOT_CHECKABLE,
            f"{len(unquantified)} of {len(failures)} failing case(s) carry no "
            f"source uncertainty, so it cannot be established whether the "
            f"disagreement lies inside what the source says about its own "
            f"numbers; Forge's acceptance tolerance is a policy choice and is "
            f"not a substitute for it",
        )
    factor = interpretation.coverage_factor
    inside = [
        item
        for item in failures
        if item.residual <= factor * item.source_uncertainty
    ]
    if len(inside) == len(failures):
        return CauseCheck(
            AlternativeCause.MEASUREMENT_UNCERTAINTY,
            CauseState.INDICATED,
            f"every failure lies within {interpretation.describe()} of the "
            f"source's own stated uncertainty, so the reference and the model "
            f"may not actually disagree",
        )
    return CauseCheck(
        AlternativeCause.MEASUREMENT_UNCERTAINTY,
        CauseState.RULED_OUT,
        f"{len(failures) - len(inside)} failure(s) exceed "
        f"{interpretation.describe()} of the source's own stated uncertainty, "
        f"which measurement spread does not account for",
    )


def _check_identifiability(parameters: CalibratedParameterSet | None) -> CauseCheck:
    if parameters is None:
        return CauseCheck(
            AlternativeCause.IDENTIFIABILITY,
            CauseState.NOT_CHECKABLE,
            "no calibrated parameter set was supplied, so it is unknown whether "
            "the fitted parameters were constrained by the data at all",
        )
    weak = parameters.unidentified_parameters
    if weak:
        return CauseCheck(
            AlternativeCause.IDENTIFIABILITY,
            CauseState.INDICATED,
            f"parameters {list(weak)} are weak, unidentified or unchecked; an "
            f"unconstrained parameter is not expected to transfer to held-back "
            f"data whatever the model's form",
        )
    return CauseCheck(
        AlternativeCause.IDENTIFIABILITY,
        CauseState.RULED_OUT,
        "every fitted parameter is reported identified with its diagnostic",
    )


def _check_context(
    report: ValidationCampaignReport, parameters: CalibratedParameterSet | None
) -> CauseCheck:
    if parameters is None:
        return CauseCheck(
            AlternativeCause.CONTEXT_MISMATCH,
            CauseState.NOT_CHECKABLE,
            "no calibrated parameter set was supplied, so it cannot be shown that "
            "the fit and the scored evidence share a dataset",
        )
    if parameters.dataset_digest != report.normalized_dataset_sha256:
        return CauseCheck(
            AlternativeCause.CONTEXT_MISMATCH,
            CauseState.INDICATED,
            f"the parameter set was fitted against dataset "
            f"{parameters.dataset_digest[:12]}... and is scored against "
            f"{report.normalized_dataset_sha256[:12]}...; that is a different "
            f"context, not a verdict on the model's form",
        )
    return CauseCheck(
        AlternativeCause.CONTEXT_MISMATCH,
        CauseState.RULED_OUT,
        "the fit and the scored evidence name the same normalized dataset",
    )


def diagnose_campaign(
    report: ValidationCampaignReport,
    clusters: tuple[FailureCluster, ...] = (),
    *,
    numerical: NumericalEvidence | None = None,
    parameters: CalibratedParameterSet | None = None,
    measurement: MeasurementInterpretation = DEFAULT_MEASUREMENT_INTERPRETATION,
    minimum_independent_cases: int = 4,
    calibration_fit_threshold: float = 0.8,
    independent_failure_threshold: float = 0.5,
) -> ModelFormDiagnosis:
    """Classify one campaign's disagreement. Returns a finding, never a cause.

    The order is the order of the cheapest honest explanations: too little
    evidence first, then whether the fit itself landed, then every alternative
    cause the supplied evidence can speak to, and only then -- once none of
    them is indicated -- a suspicion about the model's form.

    Supplying ``numerical`` and ``parameters`` is what lets alternatives be
    *ruled out* rather than merely unexamined, and so is what lets the
    suspicion reach ``confidence="supported"``.
    """
    independent_splits = (DatasetSplit.VALIDATION, DatasetSplit.LOCKED_HOLDOUT)
    calibration_fraction, calibration_n = _fraction(report, (DatasetSplit.CALIBRATION,))
    independent_fraction, independent_n = _fraction(report, independent_splits)
    evidence = [
        f"calibration scored cases: {calibration_n}",
        f"independent scored cases: {independent_n}",
        f"verdict counts: {report.counts}",
        f"guardrail counts: {report.guardrail_counts}",
    ]

    def finding(kind, why, confidence, checks=()):
        return ModelFormDiagnosis(
            kind,
            why=why,
            confidence=confidence,
            calibration_pass_fraction=calibration_fraction,
            independent_pass_fraction=independent_fraction,
            clusters=clusters,
            cause_checks=tuple(checks),
            evidence=tuple(evidence),
        )

    if independent_n < minimum_independent_cases:
        return finding(
            InadequacyKind.INSUFFICIENT_EVIDENCE,
            f"{independent_n} independent scored case(s) is below the "
            f"{minimum_independent_cases} this diagnosis requires; nothing can yet "
            f"be said about why the model and the reference disagree",
            "none",
        )

    assert independent_fraction is not None
    independent_failure = 1.0 - independent_fraction

    if independent_failure <= (1.0 - calibration_fit_threshold):
        return finding(
            InadequacyKind.INSUFFICIENT_EVIDENCE,
            "independent evidence agrees with the model within the reviewed "
            "tolerances; there is no inadequacy here to attribute",
            "none",
        )

    if calibration_fraction is not None and calibration_fraction < calibration_fit_threshold:
        return finding(
            InadequacyKind.CALIBRATION_PARAMETER,
            f"the calibration cases themselves pass only "
            f"{calibration_fraction:.0%} of the time; the fit has not yet "
            f"reproduced the data it was fitted to, so the model's form is not "
            f"what this evidence indicts",
            "supported",
        )

    # EVERY ALTERNATIVE THIS SYSTEM CAN SEE, CHECKED BEFORE THE FORM IS BLAMED.
    checks = (
        _check_applicability(report),
        _check_numerical(numerical),
        _check_measurement(report, measurement),
        _check_identifiability(parameters),
        _check_context(report, parameters),
    )
    indicated = [item for item in checks if item.state is CauseState.INDICATED]
    if indicated:
        # An alternative is positively indicated. It is returned INSTEAD of a
        # model-form suspicion, not alongside one.
        first = sorted(indicated, key=lambda item: item.cause.value)[0]
        return finding(
            _CAUSE_KIND[first.cause],
            f"{first.why}. The model's form is not implicated while this remains "
            f"the better-supported explanation",
            "suggestive",
            checks,
        )

    unchecked = [item for item in checks if item.state is CauseState.NOT_CHECKABLE]
    structured = bool(clusters)
    if not structured and independent_failure < independent_failure_threshold:
        return finding(
            InadequacyKind.INSUFFICIENT_EVIDENCE,
            "independent cases fail, but the failures are neither concentrated in "
            "an operating region nor numerous enough to separate a form problem "
            "from ordinary scatter",
            "none",
            checks,
        )

    why = (
        f"calibration fits at {calibration_fraction:.0%} while independent "
        f"evidence passes at only {independent_fraction:.0%}"
        + (
            f", and failures are concentrated along {clusters[0].dimension!r} "
            f"rather than scattered"
            if structured
            else ""
        )
        + ". That is consistent with no parameter setting of this model form "
        "reproducing both, once the alternatives below were checked. It does not "
        "establish it, and it says nothing about which physics is missing"
    )
    if unchecked:
        return finding(
            InadequacyKind.MODEL_FORM_SUSPECTED,
            why
            + f". Alternatives still unexamined: "
            f"{[item.cause.value for item in unchecked]}",
            "suggestive",
            checks,
        )
    return finding(InadequacyKind.MODEL_FORM_SUSPECTED, why, "supported", checks)


__all__ = [
    "CAUSE_CHECK_SCHEMA",
    "DEFAULT_MEASUREMENT_INTERPRETATION",
    "DIAGNOSIS_SCHEMA",
    "MeasurementInterpretation",
    "AlternativeCause",
    "CauseCheck",
    "CauseState",
    "InadequacyKind",
    "ModelFormDiagnosis",
    "diagnose_campaign",
]
