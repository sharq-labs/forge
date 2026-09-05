"""Calibration Critic V0 — is this model decision-grade?

Verdicts come from **predeclared diagnostics with predeclared thresholds**, not
from a confidence score. A scalar "confidence: 0.83" invites the reader to
supply their own meaning, and it hides which check actually failed. Every
verdict here names the diagnostic that produced it.

The verdicts:

``TRUSTED``            every declared diagnostic is within threshold
``DEGRADED``           usable with stated caveats; something is off
``UNTRUSTED``          diagnostics failed; must not inform decisions
``INSUFFICIENT_DATA``  not enough evidence to judge — distinct from UNTRUSTED,
                       because "we checked and it is bad" and "we could not
                       check" call for different responses

The rule this exists to enforce: **an untrusted model must not silently present
itself as decision-grade.** :meth:`CalibrationReport.require_decision_grade`
raises rather than returning a prediction, so a caller has to handle the
degraded case explicitly instead of reading a number and moving on.

M2 stops at the verdict. What to *do* about a degraded cost model — run
anyway, gather more data, refuse the campaign — is a decision, and decisions
belong to a later milestone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from ...scientific.serialization import schema_string

CALIBRATION_REPORT_SCHEMA = schema_string("sria_calibration_report")


class CalibrationVerdict(str, Enum):
    TRUSTED = "trusted"
    DEGRADED = "degraded"
    UNTRUSTED = "untrusted"
    INSUFFICIENT_DATA = "insufficient_data"


class NotDecisionGrade(Exception):
    """Raised when an untrusted model is asked to inform a decision."""


# ---- predeclared thresholds ------------------------------------------
#: Cost model, in log10 units. 0.30 log10 ~ a 2x typical error; 0.70 ~ 5x.
COST_MAE_TRUSTED = 0.30
COST_MAE_DEGRADED = 0.70
#: An 80% interval should cover roughly 80% of held-out points.
COST_COVERAGE_TRUSTED = (0.60, 0.95)
COST_MIN_EVAL_POINTS = 20

#: Censoring gate. The V0 estimator *excludes* censored rows, which biases the
#: median downward — every excluded timeout was, by definition, longer than the
#: values that remain. That is acceptable when censoring is rare and dishonest
#: when it is not, so the trust ladder is capped by the censored fraction of
#: the fitted support rather than left to the reader to remember.
COST_CENSORING_TRUSTED_MAX = 0.05     # above this, TRUSTED is unreachable
COST_CENSORING_DEGRADED_MAX = 0.30    # above this, the estimate is not usable

#: Failure model. Brier is compared against the base-rate predictor: a model
#: that cannot beat "always predict the base rate" has learned nothing.
FAILURE_BRIER_IMPROVEMENT_TRUSTED = 0.02
FAILURE_MIN_EVAL_POINTS = 30
FAILURE_MIN_MINORITY_COUNT = 10


@dataclass(frozen=True)
class Diagnostic:
    """One named check with its measured value and threshold."""

    name: str
    value: float | None
    threshold: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "threshold": self.threshold,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CalibrationReport:
    """A model's calibration standing, with the evidence attached."""

    model_id: str
    model_version: str
    verdict: CalibrationVerdict
    diagnostics: tuple[Diagnostic, ...] = ()
    training_provenance: Mapping[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "verdict", CalibrationVerdict(self.verdict))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "training_provenance", dict(self.training_provenance))

    @property
    def is_decision_grade(self) -> bool:
        return self.verdict in (
            CalibrationVerdict.TRUSTED,
            CalibrationVerdict.DEGRADED,
        )

    def require_decision_grade(self) -> None:
        """Refuse to let an untrusted model inform anything silently."""
        if not self.is_decision_grade:
            failed = [d.name for d in self.diagnostics if not d.passed]
            raise NotDecisionGrade(
                f"model {self.model_id!r} ({self.model_version}) is "
                f"{self.verdict.value}; failed diagnostics: {failed or ['none run']}. "
                f"{self.notes}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CALIBRATION_REPORT_SCHEMA,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "verdict": self.verdict.value,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "training_provenance": dict(self.training_provenance),
            "notes": self.notes,
        }


class CalibrationCritic:
    """Applies the predeclared diagnostics to M2 models."""

    def assess_cost_model(
        self,
        *,
        model_id: str,
        model_version: str,
        mae_log10: float,
        n_eval: int,
        coverage: float | None,
        baseline_mae_log10: float | None = None,
        training_provenance: Mapping[str, Any] | None = None,
        lower_bound_cells: int = 0,
        censored_fraction: float | None = None,
    ) -> CalibrationReport:
        diagnostics: list[Diagnostic] = []

        # Censoring is read from training provenance when not passed
        # explicitly, so a caller cannot obtain TRUSTED simply by omitting it.
        if censored_fraction is None and training_provenance:
            used = float(training_provenance.get("observed_costs_used", 0) or 0)
            excluded = float(training_provenance.get("censored_excluded", 0) or 0)
            total = used + excluded
            censored_fraction = (excluded / total) if total else 0.0

        if n_eval < COST_MIN_EVAL_POINTS:
            return CalibrationReport(
                model_id=model_id,
                model_version=model_version,
                verdict=CalibrationVerdict.INSUFFICIENT_DATA,
                diagnostics=(
                    Diagnostic(
                        name="eval_points",
                        value=float(n_eval),
                        threshold=f">= {COST_MIN_EVAL_POINTS}",
                        passed=False,
                        detail="too few held-out points to judge calibration",
                    ),
                ),
                training_provenance=training_provenance or {},
                notes="not enough held-out evidence to form a verdict",
            )

        accurate = mae_log10 <= COST_MAE_TRUSTED
        tolerable = mae_log10 <= COST_MAE_DEGRADED
        diagnostics.append(
            Diagnostic(
                name="held_out_mae_log10",
                value=mae_log10,
                threshold=f"<= {COST_MAE_TRUSTED} trusted, <= {COST_MAE_DEGRADED} degraded",
                passed=accurate,
                detail=f"typical multiplicative error {10 ** mae_log10:.2f}x",
            )
        )

        beats_baseline = True
        if baseline_mae_log10 is not None:
            beats_baseline = mae_log10 < baseline_mae_log10
            diagnostics.append(
                Diagnostic(
                    name="beats_best_baseline",
                    value=baseline_mae_log10 - mae_log10,
                    threshold="> 0 (lower MAE than the best cheap baseline)",
                    passed=beats_baseline,
                    detail=(
                        "a learned model that cannot beat a median lookup is "
                        "unnecessary, not merely weak"
                    ),
                )
            )

        coverage_ok = True
        if coverage is not None:
            low, high = COST_COVERAGE_TRUSTED
            coverage_ok = low <= coverage <= high
            diagnostics.append(
                Diagnostic(
                    name="interval_coverage",
                    value=coverage,
                    threshold=f"within [{low}, {high}]",
                    passed=coverage_ok,
                    detail="fraction of held-out costs inside the predicted interval",
                )
            )

        if lower_bound_cells:
            diagnostics.append(
                Diagnostic(
                    name="censored_lower_bound_cells",
                    value=float(lower_bound_cells),
                    threshold="== 0",
                    passed=False,
                    detail="some cells are lower bounds due to censoring",
                )
            )

        censoring_blocks_trust = False
        censoring_unusable = False
        if censored_fraction is not None:
            censoring_blocks_trust = censored_fraction > COST_CENSORING_TRUSTED_MAX
            censoring_unusable = censored_fraction > COST_CENSORING_DEGRADED_MAX
            diagnostics.append(
                Diagnostic(
                    name="censored_fraction_of_support",
                    value=censored_fraction,
                    threshold=(
                        f"<= {COST_CENSORING_TRUSTED_MAX} for TRUSTED, "
                        f"<= {COST_CENSORING_DEGRADED_MAX} for DEGRADED"
                    ),
                    passed=not censoring_blocks_trust,
                    detail=(
                        "the V0 estimator drops censored rows, and every dropped "
                        "row was longer than those kept, so the median is biased "
                        "downward in proportion to this fraction"
                    ),
                )
            )

        if not tolerable or not beats_baseline or censoring_unusable:
            verdict = CalibrationVerdict.UNTRUSTED
        elif (
            accurate
            and coverage_ok
            and not lower_bound_cells
            and not censoring_blocks_trust
        ):
            verdict = CalibrationVerdict.TRUSTED
        else:
            verdict = CalibrationVerdict.DEGRADED

        return CalibrationReport(
            model_id=model_id,
            model_version=model_version,
            verdict=verdict,
            diagnostics=tuple(diagnostics),
            training_provenance=training_provenance or {},
        )

    def assess_failure_model(
        self,
        *,
        model_id: str,
        model_version: str,
        brier: float | None,
        baseline_brier: float | None,
        n_eval: int,
        minority_count: int,
        training_provenance: Mapping[str, Any] | None = None,
        insufficient_reason: str = "",
    ) -> CalibrationReport:
        if insufficient_reason or brier is None:
            return CalibrationReport(
                model_id=model_id,
                model_version=model_version,
                verdict=CalibrationVerdict.INSUFFICIENT_DATA,
                diagnostics=(
                    Diagnostic(
                        name="trainable",
                        value=None,
                        threshold="target must have both classes present",
                        passed=False,
                        detail=insufficient_reason or "model could not be fitted",
                    ),
                ),
                training_provenance=training_provenance or {},
                notes=insufficient_reason,
            )

        diagnostics: list[Diagnostic] = []
        enough = n_eval >= FAILURE_MIN_EVAL_POINTS
        diagnostics.append(
            Diagnostic(
                name="eval_points",
                value=float(n_eval),
                threshold=f">= {FAILURE_MIN_EVAL_POINTS}",
                passed=enough,
            )
        )
        balanced = minority_count >= FAILURE_MIN_MINORITY_COUNT
        diagnostics.append(
            Diagnostic(
                name="minority_class_count",
                value=float(minority_count),
                threshold=f">= {FAILURE_MIN_MINORITY_COUNT}",
                passed=balanced,
                detail="too few minority events makes Brier uninformative",
            )
        )
        if not (enough and balanced):
            return CalibrationReport(
                model_id=model_id,
                model_version=model_version,
                verdict=CalibrationVerdict.INSUFFICIENT_DATA,
                diagnostics=tuple(diagnostics),
                training_provenance=training_provenance or {},
                notes="insufficient held-out evidence for a calibration verdict",
            )

        improvement = (baseline_brier - brier) if baseline_brier is not None else None
        beats = improvement is not None and improvement >= FAILURE_BRIER_IMPROVEMENT_TRUSTED
        diagnostics.append(
            Diagnostic(
                name="brier_improvement_over_base_rate",
                value=improvement,
                threshold=f">= {FAILURE_BRIER_IMPROVEMENT_TRUSTED}",
                passed=beats,
                detail=f"model brier {brier:.4f}",
            )
        )

        if improvement is not None and improvement < 0:
            verdict = CalibrationVerdict.UNTRUSTED
        elif beats:
            verdict = CalibrationVerdict.TRUSTED
        else:
            verdict = CalibrationVerdict.DEGRADED

        return CalibrationReport(
            model_id=model_id,
            model_version=model_version,
            verdict=verdict,
            diagnostics=tuple(diagnostics),
            training_provenance=training_provenance or {},
        )
