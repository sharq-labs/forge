"""Core re-audit 2026-09-16, batch 38: what a serialized grid record is held to, and what it is not.

Problem R-27's finding 22 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-14
part F of six, under benchmarks/core_v4_false_confidence/BATCH38_THRESHOLD_PROTOCOL.json.

Three of the finding's five claims are closed here: a rebuilt record carrying a misfit or structurally
refused local posterior, an effective sample size and spacing held to nothing, and a `considered` ledger
nobody reads. The other two -- a covariance shrunk inside the Cantelli window, and relative widths lowered --
are provably undetectable from a record without its grid, so they are STATED as a number instead of implied
away. The fuzzer at the end is the standing check that no single-field edit changes what a claim rests on.
"""

from __future__ import annotations

import copy
import itertools
import math
import random

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    GridRebuildPolicy,
    MultistartPolicy,
    RouteClaim,
    RouteDecision,
    local_gaussian_posterior,
    route_uncertainty,
)
from engcore.hybrid_uq import identifiability as ID
from engcore.hybrid_uq import router as RO
from engcore.hybrid_uq._records import decode_matrix, decode_vector, encode_matrix
from engcore.hybrid_uq.router import HybridUQResult
from engcore.hybrid_uq.vocabulary import HybridUQError

K_CANTELLI = math.sqrt(0.975 / 0.025)
FUZZER_SEED = 20260917


def _symbol(module, name):
    assert hasattr(module, name), (
        f"{module.__name__} has no {name!r}; it is preregistered in BATCH38_THRESHOLD_PROTOCOL.json"
    )
    return getattr(module, name)


def _grid_result():
    """The audited grid record: GRID_AS_SUPPLIED SUPPORTED over a 41x41 box."""
    problem = S.affine("B38_grid")
    z = np.asarray(problem.calibrate().estimate_vector)
    axes = [np.linspace(z[0] - 0.4, z[0] + 0.4, 41), np.linspace(z[1] - 0.8, z[1] + 0.8, 41)]
    grid = problem.grid(axes)
    return route_uncertainty(grid=grid, calibration=problem.calibrate(), observations=problem.observations,
                             forward=problem.forward, multistart=MultistartPolicy())


def _rebuilt_result():
    problem = S.at_bound()
    return route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                             forward=problem.forward, multistart=MultistartPolicy(),
                             rebuild=GridRebuildPolicy(problem.table_builder()))


def _misfit_posterior():
    """A genuine REFUSED posterior over the same parameter names whose only reason is the misfit.

    The reasons are not forged: they are re-derived from this posterior's own measurements on read, which is
    why the forged record passes -- nothing relates the grid decision to them.
    """
    x = np.linspace(0.0, 1.0, 12)
    problem = S.Problem("B38_misfit", lambda t, x: t[0] + t[1] * x, x, (1.0, 2.0), 0.01,
                        (-50.0, -50.0), (50.0, 50.0), (0.0, 0.0), observed=1.0 + 2.0 * x + 3.0 * x ** 2)
    return local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                    multistart=MultistartPolicy())


def _singular_posterior():
    problem = S.nearly_singular()
    return local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                    multistart=MultistartPolicy())


def _with_moments(payload):
    """A payload whose integrity-only moments digest is recomputed, as the record's own writer would."""
    summary = dict(payload["grid_summary"])
    summary["moments_digest"] = RO._grid_moments_digest(
        payload["decision"], payload["parameter_names"], summary["grid_digest"],
        decode_vector(payload["mean"]), decode_matrix(payload["covariance"]),
        summary["dataset_id"], summary["points"])
    payload["grid_summary"] = summary
    return payload


def _scaled_covariance(payload, factor):
    covariance = np.asarray(decode_matrix(payload["covariance"]), dtype=float) / float(factor)
    payload["covariance"] = encode_matrix(tuple(tuple(float(v) for v in row) for row in covariance))
    return _with_moments(payload)


def _report(payload):
    return payload["identifiability"]["report"]


def _sd(result):
    return np.sqrt(np.diag(np.asarray(result.covariance, dtype=float)))


# ---------------------------------------------------------------------------
# the premise
# ---------------------------------------------------------------------------
def test_r27f_the_baseline_record_is_the_one_the_finding_describes():
    result = _grid_result()
    assert result.decision is RouteDecision.GRID_AS_SUPPLIED and result.claim is RouteClaim.SUPPORTED
    report = result.identifiability.report
    assert np.allclose(_sd(result), [0.02714564, 0.04599331], rtol=1e-5)
    assert 10.0 < report.effective_sample_size < 11.0 and max(report.spacing_to_std) < 1.0
    assert HybridUQResult.from_dict(result.to_dict()) == result


# ---------------------------------------------------------------------------
# a_rebuilt_grid_carries_no_misfit_or_structurally_refused_posterior
# ---------------------------------------------------------------------------
def test_r27f_an_honest_rebuilt_record_still_reads_back():
    result = _rebuilt_result()
    assert result.decision is RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE
    assert HybridUQResult.from_dict(result.to_dict()) == result


@pytest.mark.xfail(strict=True, reason="R-27 finding 22, third claim: read-back holds a rebuilt record's local "
                                       "posterior to its names only, so the misfit the local route recorded is "
                                       "laundered into a SUPPORTED grid claim")
def test_r27f_a_rebuilt_record_carrying_a_misfit_posterior_is_refused():
    payload = copy.deepcopy(_rebuilt_result().to_dict())
    misfit = _misfit_posterior()
    assert misfit.claim is RouteClaim.REFUSED and "MODEL_MISFIT_BEYOND_DECLARED_NOISE" in {r.value for r in misfit.reasons}
    payload["local_posterior"] = misfit.to_dict()
    with pytest.raises(HybridUQError, match="MODEL_MISFIT_BEYOND_DECLARED_NOISE"):
        HybridUQResult.from_dict(payload)


@pytest.mark.xfail(strict=True, reason="R-27 finding 22, third claim: the router refuses to design a grid from a "
                                       "posterior with no usable covariance, and read-back does not")
def test_r27f_a_rebuilt_record_carrying_a_structurally_refused_posterior_is_refused():
    payload = copy.deepcopy(_rebuilt_result().to_dict())
    singular = _singular_posterior()
    assert "NUMERICALLY_SINGULAR_JACOBIAN" in {str(r).rsplit(".", 1)[-1] for r in singular.diagnostics.refusals}
    payload["local_posterior"] = singular.to_dict()
    with pytest.raises(HybridUQError, match="no usable local covariance"):
        HybridUQResult.from_dict(payload)


# ---------------------------------------------------------------------------
# the_considered_ledger_names_the_route_the_decision_reports
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-27 finding 22, fifth claim: `considered` is never read, so () is accepted")
def test_r27f_an_empty_considered_ledger_is_refused():
    payload = copy.deepcopy(_grid_result().to_dict())
    payload["considered"] = []
    with pytest.raises(HybridUQError, match="considered"):
        HybridUQResult.from_dict(payload)


@pytest.mark.xfail(strict=True, reason="R-27 finding 22, fifth claim: a ledger saying the used route was passed "
                                       "over for a misfit reads back beside a SUPPORTED grid decision")
def test_r27f_a_ledger_that_says_the_used_route_was_passed_over_is_refused():
    payload = copy.deepcopy(_grid_result().to_dict())
    rows = [dict(row) for row in payload["considered"]]
    for row in rows:
        if row.get("outcome") == "USED":
            row["outcome"] = "PASSED_OVER"
            row["reason"] = "MODEL_MISFIT_BEYOND_DECLARED_NOISE"
    payload["considered"] = rows
    with pytest.raises(HybridUQError, match="considered"):
        HybridUQResult.from_dict(payload)


@pytest.mark.xfail(strict=True, reason="R-27 finding 22, fifth claim: nothing ties the USED row to the decision")
def test_r27f_a_ledger_naming_another_used_route_is_refused():
    payload = copy.deepcopy(_grid_result().to_dict())
    rows = [dict(row) for row in payload["considered"]]
    for row in rows:
        if row.get("outcome") == "USED":
            row["route"] = "LOCAL_GAUSSIAN"
    payload["considered"] = rows
    with pytest.raises(HybridUQError, match="considered"):
        HybridUQResult.from_dict(payload)


@pytest.mark.xfail(strict=True, reason="R-27 finding 22, fifth claim: a row can carry any route name and any outcome")
def test_r27f_a_ledger_row_outside_the_routers_own_vocabulary_is_refused():
    payload = copy.deepcopy(_grid_result().to_dict())
    payload["considered"] = list(payload["considered"]) + [{"route": "SOMETHING_ELSE", "outcome": "FINE"}]
    with pytest.raises(HybridUQError, match="considered"):
        HybridUQResult.from_dict(payload)


# ---------------------------------------------------------------------------
# a_grid_record_reports_diagnostics_a_grid_v1_accepted
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-27 finding 22, fourth claim: ESS and spacing_to_std are never held to "
                                       "anything, so a grid V1 would have refused reads back SUPPORTED")
def test_r27f_diagnostics_v1_would_have_refused_are_refused():
    payload = copy.deepcopy(_grid_result().to_dict())
    report = _report(payload)
    report["effective_sample_size"] = 1.5
    report["spacing_to_std"] = [50.0] * len(payload["parameter_names"])
    with pytest.raises(HybridUQError, match="effective sample size"):
        HybridUQResult.from_dict(payload)


@pytest.mark.xfail(strict=True, reason="R-27 finding 22, fourth claim: an effective sample size is a count of "
                                       "nodes and nothing holds it to the node count the summary commits to")
def test_r27f_an_effective_sample_size_above_the_point_count_is_refused():
    payload = copy.deepcopy(_grid_result().to_dict())
    _report(payload)["effective_sample_size"] = float(payload["grid_summary"]["points"] + 1)
    with pytest.raises(HybridUQError, match="effective sample size"):
        HybridUQResult.from_dict(payload)


@pytest.mark.xfail(strict=True, reason="R-27 finding 22, fourth claim: the occupied support fraction is a fraction "
                                       "and nothing holds it to (0, 1]")
def test_r27f_an_occupied_support_fraction_outside_its_range_is_refused():
    payload = copy.deepcopy(_grid_result().to_dict())
    _report(payload)["occupied_support_fraction"] = 1.5
    with pytest.raises(HybridUQError, match="occupied support"):
        HybridUQResult.from_dict(payload)


@pytest.mark.xfail(strict=True, reason="R-27 finding 22, fourth claim: spacing_to_std has one entry per axis and "
                                       "nothing holds its length")
def test_r27f_a_spacing_vector_of_the_wrong_length_is_refused():
    payload = copy.deepcopy(_grid_result().to_dict())
    _report(payload)["spacing_to_std"] = [0.5]
    with pytest.raises(HybridUQError, match="spacing"):
        HybridUQResult.from_dict(payload)


def test_r27f_a_broad_posterior_on_a_fine_grid_is_not_what_the_v1_rule_refuses():
    """The control for the rule above: V1 refuses on BOTH conditions, and so does read-back.

    A small effective sample size alone is a sharply informative posterior, not a coarse grid; what says
    'too coarse' is the step being as wide as the posterior. This record keeps its own spacing, well under 1.
    """
    payload = copy.deepcopy(_grid_result().to_dict())
    _report(payload)["effective_sample_size"] = 1.5
    assert HybridUQResult.from_dict(payload).claim is RouteClaim.SUPPORTED


# ---------------------------------------------------------------------------
# the_re_derivation_limit_of_a_grid_record_is_stated_as_a_number
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-27 finding 22, first and second claims: the limit is not stated anywhere, "
                                       "and the docstring claims the opposite")
def test_r27f_the_undetectable_shrink_window_is_stated_as_a_number():
    window = _symbol(ID, "grid_record_variance_shrink_window")
    result = _grid_result()
    mean, covariance = np.asarray(result.mean), np.asarray(result.covariance)
    widths = tuple(result.identifiability.report.relative_widths)
    sd = np.sqrt(np.diag(covariance))
    expected = min((2.0 * K_CANTELLI * sd[i] / (widths[i] * abs(mean[i]))) ** 2 for i in range(len(widths)))
    found = window(result.mean, result.covariance, widths)
    assert found == pytest.approx(expected, rel=1e-12), f"{found!r} is not the window {expected!r} the bound gives"
    assert 7.9 < found < 8.1, f"the window on the audited record is 7.98, not {found!r}"


@pytest.mark.xfail(strict=True, reason="R-27 finding 22, first and second claims: `_grid_report_problems` says 'A "
                                       "covariance shrunk under a recomputed commitment breaks that bound', which "
                                       "is not true inside the window")
def test_r27f_the_docstring_states_the_limit_instead_of_denying_it():
    text = RO._grid_report_problems.__doc__ or ""
    assert "A covariance shrunk under a recomputed commitment breaks that bound" not in text, (
        "the overclaim the audit's verifier named is still in the docstring")
    assert "grid_record_variance_shrink_window" in text, (
        "the docstring does not name the function that states the limit")


def test_r27f_the_window_is_where_the_bound_actually_bites():
    """The limit, pinned as behaviour: just inside the window reads back, just outside is refused.

    This is not a defence, it is the honest statement of one. A record's covariance can be divided by up to
    this factor and nothing in the record contradicts it.
    """
    result = _grid_result()
    mean, sd = np.asarray(result.mean), _sd(result)
    widths = tuple(result.identifiability.report.relative_widths)
    window = min((2.0 * K_CANTELLI * sd[i] / (widths[i] * abs(mean[i]))) ** 2 for i in range(len(widths)))
    inside = HybridUQResult.from_dict(_scaled_covariance(copy.deepcopy(result.to_dict()), window * 0.99))
    assert inside.claim is RouteClaim.SUPPORTED
    with pytest.raises(HybridUQError, match="cannot belong to a distribution"):
        HybridUQResult.from_dict(_scaled_covariance(copy.deepcopy(result.to_dict()), window * 1.01))


# ---------------------------------------------------------------------------
# no_single_field_edit_improves_a_claim -- the record-forgery fuzzer
# ---------------------------------------------------------------------------
def _numeric_edits(value, rng):
    return [0.0, 1.0, -1.0, float("nan"), float("inf"), value * 1.0e-4, value * 0.1, value * 10.0,
            value * (1.0 + rng.uniform(-0.5, 0.5))]


def _edited_payloads(payload, rng):
    """One edited payload per (field, edit): every carried field of the record and of its reports."""
    out = []

    def emit(note, edited):
        if "grid_summary" in edited and edited["grid_summary"] is not None:
            try:
                edited = _with_moments(edited)
            except Exception:  # an edit that makes the digest uncomputable is an edit like any other
                pass
        out.append((note, edited))

    for key in ("decision", "claim", "coordinates", "approximation_class"):
        for other in ("GRID_AS_SUPPLIED", "GRID_REBUILT_FROM_LOCAL_COVARIANCE", "LOCAL_GAUSSIAN", "REFUSED",
                      "SUPPORTED", "DOWNGRADED", "natural", "inference", "none", "POSTERIOR_GRID",
                      "LOCAL_GAUSSIAN_APPROXIMATION", None):
            if payload.get(key) != other:
                edited = copy.deepcopy(payload)
                edited[key] = other
                emit(f"{key}={other!r}", edited)

    for index in range(len(payload["parameter_names"])):
        for value in _numeric_edits(float(decode_vector(payload["mean"])[index]), rng):
            edited = copy.deepcopy(payload)
            vector = list(decode_vector(payload["mean"]))
            vector[index] = value
            edited["mean"] = list(vector)
            emit(f"mean[{index}]={value!r}", edited)
        for factor in (1.0e-4, 0.1, 10.0, 1.0e4):
            emit(f"covariance/{factor}", _scaled_covariance(copy.deepcopy(payload), factor))

    report = _report(payload)
    for key, value in report.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            for candidate in _numeric_edits(float(value), rng):
                edited = copy.deepcopy(payload)
                _report(edited)[key] = candidate
                emit(f"report.{key}={candidate!r}", edited)
        elif isinstance(value, list):
            for candidate in ([], list(value) + list(value), list(value)[:-1] or [0.0],
                              [float(len(value))] * len(value)):
                edited = copy.deepcopy(payload)
                _report(edited)[key] = candidate
                emit(f"report.{key}={candidate!r}", edited)
        elif isinstance(value, str):
            edited = copy.deepcopy(payload)
            _report(edited)[key] = value + " and also identifiable"
            emit(f"report.{key} appended", edited)

    rows = [dict(row) for row in payload["considered"]]
    edited = copy.deepcopy(payload)
    edited["considered"] = []
    emit("considered=[]", edited)
    for index, row in enumerate(rows):
        for key in tuple(row) + ("extra",):
            for candidate in ("USED", "PASSED_OVER", "LOCAL_GAUSSIAN", "GRID_AS_SUPPLIED", "", "anything"):
                edited = copy.deepcopy(payload)
                ledger = [dict(r) for r in edited["considered"]]
                ledger[index][key] = candidate
                edited["considered"] = ledger
                emit(f"considered[{index}].{key}={candidate!r}", edited)
        edited = copy.deepcopy(payload)
        ledger = [dict(r) for r in edited["considered"]]
        ledger.pop(index)
        edited["considered"] = ledger
        emit(f"considered without row {index}", edited)

    for key in ("dataset_id", "points", "grid_digest", "moments_digest"):
        for candidate in ("other", 0, 1, -1, 10 ** 9):
            edited = copy.deepcopy(payload)
            summary = dict(edited["grid_summary"])
            summary[key] = candidate
            edited["grid_summary"] = summary
            out.append((f"grid_summary.{key}={candidate!r}", edited))  # digest edits are not recomputed away
    return out


def _claim_bearing(result):
    """The fields a claim rests on and that a record is held to EXACTLY (amendment 2).

    The diagnostics (effective sample size, occupied support fraction, spacing) are deliberately not here:
    they are grid quantities that a record without its grid cannot re-derive, and what holds them is the
    admission rule `_grid_diagnostic_problems` applies on read. Nor are a ledger row's `reason` and `detail`
    strings, which are not re-derivable without re-running the route. Both are stated residuals.
    """
    report = result.identifiability.report
    used = tuple(sorted(row.get("route", "") for row in result.considered if row.get("outcome") == "USED")),
    return {
        "decision": result.decision.value, "claim": result.claim.value, "status": report.status.value,
        "used_routes": used, "why": report.why,
        "thresholds": (float(report.correlation_threshold), float(report.condition_threshold),
                       float(report.width_threshold)),
    }


def _same_numbers(a, b):
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(_same_numbers(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return (math.isnan(a) and math.isnan(b)) or a == b
    return a == b


@pytest.mark.xfail(strict=True, reason="R-27 finding 22: single-field edits to a grid record's diagnostics and to "
                                       "its `considered` ledger read back with the claim untouched")
def test_r27f_no_single_field_edit_changes_what_a_claim_rests_on():
    """The record-forgery fuzzer I-14's brief asks for, over the grid record.

    Deterministic: the seed is preregistered. Every edit either is refused, or comes back with the original's
    decision, claim, identifiability status and `why`, thresholds and used route, with no width narrower and
    no variance shrunk past `grid_record_variance_shrink_window`. What is NOT held, and why, is in
    `_claim_bearing` and in the protocol's residuals: the mean, the grid diagnostics and a passed-over row's
    reason are integrity-only, so they are bounded on read rather than re-derived.
    """
    rng = random.Random(FUZZER_SEED)
    result = _grid_result()
    original = _claim_bearing(result)
    window = _symbol(ID, "grid_record_variance_shrink_window")(
        result.mean, result.covariance, result.identifiability.report.relative_widths)
    reference = np.diag(np.asarray(result.covariance, dtype=float))
    widths = np.asarray(result.identifiability.report.relative_widths, dtype=float)
    survivors, edits = [], _edited_payloads(result.to_dict(), rng)
    # 199 at the batch's record (amendment 1): the floor is a coverage sanity check, not a threshold.
    assert len(edits) >= 150, f"only {len(edits)} edits: the catalogue is not covering the record"
    for note, payload in edits:
        try:
            back = HybridUQResult.from_dict(payload)
        except Exception:
            continue
        found = _claim_bearing(back)
        if not all(_same_numbers(original[k], found[k]) for k in original):
            survivors.append((note, [k for k in original if not _same_numbers(original[k], found[k])]))
            continue
        narrower = np.asarray(back.identifiability.report.relative_widths, dtype=float)
        if len(narrower) == len(widths) and bool(np.any(narrower < widths * (1.0 - 1e-12))):
            survivors.append((note, f"widths narrowed to {list(narrower)} from {list(widths)}"))
            continue
        shrink = float(np.max(reference / np.maximum(np.diag(np.asarray(back.covariance, dtype=float)), 1e-300)))
        if shrink > window * (1.0 + 1e-9):
            survivors.append((note, f"variance shrunk by {shrink:.4g}, outside the window {window:.4g}"))
    assert not survivors, f"{len(survivors)} of {len(edits)} edits read back having changed a claim-bearing field: {survivors[:12]}"


# ---------------------------------------------------------------------------
# a_record_the_router_returns_can_be_read_back
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="found while reproducing finding 22: a posterior refused before any "
                                       "measurement carries an empty observation content digest, which batch 36's "
                                       "rule requires of a /3 record, so the router returns a record from_dict "
                                       "refuses")
def test_r27f_a_posterior_the_route_refused_early_reads_back():
    from engcore.hybrid_uq.local_gaussian import LocalGaussianPosterior

    singular = _singular_posterior()
    assert singular.claim is RouteClaim.REFUSED
    try:
        read = LocalGaussianPosterior.from_dict(singular.to_dict())
    except HybridUQError as exc:
        pytest.fail(f"the router returned a record it cannot read back: {exc}")
    assert read == singular
