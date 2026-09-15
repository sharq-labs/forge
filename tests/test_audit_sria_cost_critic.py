"""Audit stream sria — INF-11: omitted calibration inputs cannot yield TRUSTED.

``CalibrationCritic.assess_cost_model`` treated a missing ``coverage`` as
passing and skipped the censoring check when neither ``censored_fraction`` nor
censoring counts in ``training_provenance`` were given. Its own comment said a
caller "cannot obtain TRUSTED simply by omitting" censoring — but omitting both
did exactly that.
"""

from __future__ import annotations

from engcore.sria.calibration import CalibrationVerdict
from engcore.sria.calibration.critic import CalibrationCritic


def _assess(**overrides):
    kwargs = dict(
        model_id="cost.audit",
        model_version="cost/1",
        mae_log10=0.1,
        n_eval=20,
        coverage=0.80,
        baseline_mae_log10=1.0,
        censored_fraction=0.0,
    )
    kwargs.update(overrides)
    return CalibrationCritic().assess_cost_model(**kwargs)


def test_inf11_probe_everything_omitted_is_not_trusted():
    report = CalibrationCritic().assess_cost_model(
        model_id="cost.audit", model_version="cost/1",
        mae_log10=0.1, n_eval=20, coverage=None,
    )
    assert report.verdict is not CalibrationVerdict.TRUSTED
    assert report.verdict is CalibrationVerdict.DEGRADED


def test_inf11_missing_coverage_caps_at_degraded():
    report = _assess(coverage=None)
    assert report.verdict is CalibrationVerdict.DEGRADED
    failed = {d.name for d in report.diagnostics if not d.passed}
    assert "interval_coverage" in failed


def test_inf11_missing_censoring_caps_at_degraded():
    report = _assess(censored_fraction=None)
    assert report.verdict is CalibrationVerdict.DEGRADED
    failed = {d.name for d in report.diagnostics if not d.passed}
    assert "censored_fraction_of_support" in failed


def test_inf11_provenance_without_censoring_counts_is_not_censoring_evidence():
    report = _assess(censored_fraction=None, training_provenance={"dataset_id": "x"})
    assert report.verdict is CalibrationVerdict.DEGRADED


def test_inf11_complete_inputs_can_still_be_trusted():
    assert _assess().verdict is CalibrationVerdict.TRUSTED
    counted = _assess(
        censored_fraction=None,
        training_provenance={"observed_costs_used": 100, "censored_excluded": 0},
    )
    assert counted.verdict is CalibrationVerdict.TRUSTED
