"""Battery Flagship B3: frozen evidence, preregistered protocol, re-derived result, regressions."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import pathlib

import numpy as np
import pytest
from scipy.stats import chi2

from engcore.domains.battery import cell as battery_cell
from engcore.domains.battery import calibration as bc
from engcore.domains.battery import context as ctx
from engcore.domains.battery.empirical import (
    ConditioningDirection,
    MeasuredOcvPoint,
    OcvEmpiricalStatus,
    assess_ocv_empirical_adequacy,
)
from engcore.domains.battery.solver import evaluate_step
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.models.curves import DeclaredCurve, Interpolation, PiecewiseForm, PolynomialForm, TabulatedForm
from engcore.scientific.models.definition import ValidityStatus
from engcore.scientific.units.quantity import Quantity as Q

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "battery_flagship_b3"


def _json(name):
    return json.loads((ROUND / name).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def E():
    return _load("_b3_evidence_test", ROUND / "audit" / "b3_evidence.py")


@pytest.fixture(scope="module")
def H():
    return _load("_b3_harness_test", ROUND / "audit" / "run_b3.py")


@pytest.fixture(scope="module")
def prereg():
    return _json("PREREGISTRATION.json")


@pytest.fixture(scope="module")
def results():
    return _json("RESULTS.json")


@pytest.fixture(scope="module")
def comparison():
    return _json("COMPARISON.json")


@pytest.fixture(scope="module")
def secondary():
    return _json("SECONDARY.json")


@pytest.fixture(scope="module")
def data(H):
    return H.Data()


@pytest.fixture(scope="module")
def best(H, comparison, results, data):
    model_id = comparison["best_honest_model"]
    estimates = np.asarray(list(results["models"][model_id]["calibration"]["estimates_v"].values()))
    return model_id, H.parameterization(model_id), estimates


# =====================================================================
# Phase 5: the raw bytes are the published bytes
# =====================================================================

def test_raw_files_match_their_pinned_sha256_and_zenodo_md5(E):
    for entry in E.PROVENANCE["files"]:
        blob = (E.RAW / entry["raw_filename"]).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == entry["sha256"]
        assert hashlib.md5(blob).hexdigest() == entry["md5_published_by_zenodo"]
        assert len(blob) == entry["bytes"]


def test_the_raw_directory_is_exempt_from_line_ending_normalisation(E):
    assert "* -text" in (E.RAW / ".gitattributes").read_text(encoding="utf-8")
    assert b"\r\n" in (E.RAW / E.INCR_OCV).read_bytes(), "the published incrOCV file is CRLF; LF here means the bytes were rewritten"


def test_the_derived_artifacts_regenerate_to_their_preregistered_digests(prereg):
    prepare = _load("_b3_prepare_test", ROUND / "audit" / "prepare_b3.py")
    built = prepare.payloads()
    for name in ("DATA_QUALITY.json", "OBSERVATIONS.json"):
        digest = hashlib.sha256(prepare.encode(built[name])).hexdigest()
        assert digest == prereg["pinned_inputs"][f"{name}_sha256"] == sha(ROUND / name)


def test_the_selection_record_names_the_file_the_protocol_uses(prereg, E):
    selection = _json("DATA_SELECTION.json")
    assert selection["written_before_any_b3_model_score"] is True
    assert selection["selection"]["primary_dataset"].startswith("E1 JAHN-INCR")
    pinned = next(f for f in E.PROVENANCE["files"] if f["raw_filename"] == E.INCR_OCV)
    assert pinned["sha256"] == prereg["pinned_inputs"]["raw_incrOCV_sha256"]


# =====================================================================
# Phases 6-10: meaning, audit, split, leakage
# =====================================================================

def test_the_quality_audit_reports_the_anomalies_it_found_and_cleans_nothing(E):
    audit = _json("DATA_QUALITY.json")
    statuses = {f["check"]: f["status"] for f in audit["findings"]}
    assert statuses["duplicate_physical_measurement_under_two_labels"] == "ANOMALY"
    assert statuses["timing_and_rest_period_consistency"] == "UNVERIFIABLE"
    assert "FAIL" not in statuses.values()
    assert len(E.incremental_rows()) == 202 and len(E.discharge_points()) == 100


def test_the_shared_top_row_is_not_a_discharge_observation(E):
    ids = {p["row"] for p in E.discharge_points()}
    assert E.SHARED_TOP_ROW not in ids and E.TOP_ROW not in ids


def test_the_split_matches_the_preregistered_counts_and_covers_every_region(E, prereg):
    points = E.discharge_points()
    counts = prereg["phase9_split"]["counts"]
    held = [p for p in points if p["partition"] == "held_out"]
    assert len(held) == counts["held_out"] == 33
    for name, row in counts["regions"].items():
        assert sum(1 for p in held if p["region"] == name) == row["held_out"]
        assert sum(1 for p in points if p["region"] == name and p["partition"] == "calibration") == row["calibration"] > 0
    assert sum(1 for p in held if p["region"] == "KNEE") >= 2
    assert sum(1 for p in held if p["region"] == "PLATEAU") >= 2


def test_no_held_out_voltage_can_move_any_uncertainty(E):
    points = E.discharge_points()
    before = E.uncertainty_budget(points)
    shifted = [dict(p, voltage_v=p["voltage_v"] + (0.5 if p["partition"] == "held_out" else 0.0)) for p in points]
    after = E.uncertainty_budget(shifted)
    assert before == after


def test_calibration_and_held_out_are_disjoint_by_identity_and_content(data):
    proof = data.leakage_proof()
    assert proof["disjoint"] and proof["calibration_n"] == 67 and proof["held_out_n"] == 33


def test_the_ocv_observable_ignores_every_placeholder_declaration(H):
    param = H.parameterization("T6")
    voltages = (2.7, 3.05, 3.2, 3.29, 3.31, 3.4)

    def ocv(fixed, current, temperature):
        condition = bc.RestedOcvCondition(condition_id="c", target_state_of_charge=Q(0.07, "dimensionless"),
                                          conditioning_current=Q(current, "ampere"), cell_temperature=Q(temperature, "kelvin"))
        return bc.curve_ocv_prediction(fixed, condition, parameterization=param, voltages=voltages).value(bc.OCV_OBSERVABLE).magnitude_in("volt")

    reference = ocv(H.FIXED, 0.11, 298.15)
    other = bc.FixedCellDeclaration(cell_id="X", nominal_capacity=Q(2.5, "ampere_hour"),
                                    internal_resistance=Q(0.05, "ohm"), chemistry=ctx.LITHIUM_ION)
    assert ocv(other, 1.1, 273.15) == reference


@pytest.mark.parametrize("model_id", ["P4", "T21"])
def test_both_existing_forms_are_affine_in_their_voltages(H, data, model_id):
    param = H.parameterization(model_id)
    k = len(param.names)
    a, b = np.linspace(3.0, 3.4, k), np.linspace(2.8, 3.45, k)
    obs = data.split.held_out
    mix = H.forward(param, 0.3 * a + 0.7 * b, obs, data)
    assert np.max(np.abs(mix - (0.3 * H.forward(param, a, obs, data) + 0.7 * H.forward(param, b, obs, data)))) < 1e-12


def test_a_table_with_knots_no_calibration_point_can_see_is_refused_by_the_gate(H, data):
    param = bc.TabulatedKnotParameterization((0.0, 0.003, 0.006, 0.009, 1.0))
    design = H.wls(param, data.split.calibration, data)
    assert design["rank"] < design["p"]


def test_the_measured_map_table_is_refused_not_scored(results, secondary):
    tcal = secondary["t_cal_gate_demonstration"]
    assert tcal["p"] >= tcal["n_cal"] and tcal["gate"]["passed"] is False
    assert "T-CAL" not in results["models"]


# =====================================================================
# Controls, then the measured result
# =====================================================================

def test_the_synthetic_controls_behaved_as_preregistered(prereg):
    controls = _json("CONTROLS.json")
    assert controls["all_as_expected"] is True
    assert controls["controls"]["knee_misfit_P2"]["worst_region"] == "KNEE"
    assert controls["controls"]["in_model_T5"]["cross_check"]["passed"] is True


def test_the_results_are_bound_to_this_protocol_and_these_controls(results, secondary):
    assert results["preregistration_sha256"] == sha(ROUND / "PREREGISTRATION.json")
    assert results["controls_sha256"] == sha(ROUND / "CONTROLS.json")
    assert secondary["raw_unchanged"] is True


def test_every_model_reports_the_gate_quantities(results):
    for model_id, record in results["models"].items():
        assert record["residual_dof"] == record["n_cal"] - record["p"]
        s = record["structural"]
        assert {"rank", "singular_values", "weighted_jacobian_condition_number"} <= set(s)
        if record["gate"]["passed"]:
            assert record["p"] < record["n_cal"] and s["rank"] == record["p"]
            assert record["gate"]["identifiability_status"] == "PARAMETERS_IDENTIFIABLE"
            assert "secondary_identifiability" in record["routes"][record["primary_route"]]["parameterization_sensitivity"]


def test_regions_partition_the_held_out_set(results):
    for record in results["models"].values():
        for route in record.get("routes", {}).values():
            assert sum(r["n"] for r in route["regions"].values()) == route["metrics"]["n"] == 33


def test_the_best_honest_model_is_the_cross_validation_rule_applied(results, comparison):
    scores = {m: c["cv_score"] for m, c in results["cross_validation"].items() if c["eligible"]}
    assert scores == comparison["cv_eligible_scores"]
    lowest = min(scores.values())
    near = [m for m, s in scores.items() if s <= lowest * 1.01]
    expected = min(near, key=lambda m: (results["models"][m]["p"], scores[m]))
    assert comparison["best_honest_model"] == expected


def test_the_verdict_is_the_preregistered_mapping_applied(results, comparison, prereg, secondary):
    best = comparison["best_honest_model"]
    models = results["models"]

    def scored(m):
        return models[m]["routes"][models[m]["primary_route"]]

    def everywhere(m):
        s = scored(m)
        return s["metrics"]["adequacy"] == "MODEL_ADEQUATE" and all(r["adequacy"] == "MODEL_ADEQUATE" for r in s["regions"].values())

    passing = [m for m in models if models[m]["gate"]["passed"]]
    if models[best]["primary_route"] == "DOMAIN_LINEAR_GAUSSIAN" and not secondary["route_cross_check"]["domain_route_may_carry_a_claim"]:
        letter = "D"
    elif everywhere(best):
        letter = "A"
    else:
        family = prereg["phase17_complexity_and_selection"]["families"]["polynomial" if best.startswith("P") else "tabulated"]
        simpler = [m for m in passing if m in family and models[m]["p"] < models[best]["p"]]
        overfit = [m for m in simpler if scored(best)["metrics"]["rmse_v"] >= 1.2 * scored(m)["metrics"]["rmse_v"] or everywhere(m)]
        letter = "C" if overfit else "B"
    assert comparison["verdict_letter"] == letter
    assert comparison["verdict"] == prereg["phase23_verdict_mapping_fixed_now"]["final_verdict_strings"][letter]


def test_the_b1_and_b2_columns_are_the_historical_numbers(comparison):
    b1 = json.loads((ROOT / "benchmarks" / "battery_flagship_b1" / "RESULTS.json").read_text(encoding="utf-8"))["metrics"]
    b2 = json.loads((ROOT / "benchmarks" / "battery_flagship_b2" / "RESULTS.json").read_text(encoding="utf-8"))["primary"]["metrics"]
    rows = {r["metric"]: r for r in comparison["b1_b2_b3"]}
    assert rows["RMSE (mV)"]["b1"] == pytest.approx(215.27, abs=0.005) == b1["rmse_v"] * 1e3
    assert rows["RMSE (mV)"]["b2"] == pytest.approx(212.62, abs=0.005) == b2["rmse_v"] * 1e3


def test_the_domain_route_reproduces_the_committed_best_model(H, data, results, best):
    model_id, param, _ = best
    record = results["models"][model_id]
    full = H.wls(param, data.split.calibration, data)
    rerun = H.domain_route(model_id, data, full)
    committed = record["routes"]["DOMAIN_LINEAR_GAUSSIAN"]
    assert H.metrics(rerun["held_out"])["rmse_v"] == pytest.approx(committed["metrics"]["rmse_v"], rel=1e-9)
    assert H.metrics(rerun["held_out"])["chi_square"] == pytest.approx(committed["metrics"]["chi_square"], rel=1e-9)


def test_the_domain_route_agreed_with_the_core_grid_wherever_both_ran(secondary, results):
    cross = secondary["route_cross_check"]["per_model"]
    assert set(cross) == {m for m, r in results["models"].items() if r["model"]["route"] == "CORE_GRID" and "routes" in r}
    assert all(c["passed"] for c in cross.values()) == secondary["route_cross_check"]["domain_route_may_carry_a_claim"]


def test_the_chi_square_verdicts_follow_the_rule(results):
    for record in results["models"].values():
        for route in record.get("routes", {}).values():
            m = route["metrics"]
            assert m["chi_square_p_value"] == pytest.approx(chi2.sf(m["chi_square"], m["chi_square_df"]))
            assert (m["adequacy"] == "MODEL_INADEQUATE") == (m["chi_square_p_value"] < 0.01)


# =====================================================================
# Phase 19: empirical adequacy, regression only
# =====================================================================

def _curve_cell(param, estimates):
    return battery_cell.CellSpecification(
        cell_id="B3", nominal_capacity=Q(1.1, "ampere_hour"), internal_resistance=Q(0.0126, "ohm"),
        open_circuit_voltage_curve=param.curve(tuple(estimates)),
    )


def _points(data, ids, values=None, direction=ConditioningDirection.DISCHARGE):
    return [
        MeasuredOcvPoint(state_of_charge=Q(data.z[i], "dimensionless"),
                         open_circuit_voltage=Q(data.values[i] if values is None else values[i], "volt"),
                         standard_uncertainty=Q(data.sigma(i), "volt"), conditioning=direction, source_ref=f"b3:{i}")
        for i in ids
    ]


def test_no_measured_evidence_is_never_adequate(best):
    _, param, estimates = best
    assert assess_ocv_empirical_adequacy(_curve_cell(param, estimates), []).status is OcvEmpiricalStatus.NO_MEASURED_EVIDENCE


def test_charge_conditioned_evidence_stays_outside_the_claim(best, data):
    _, param, estimates = best
    ids = [o.condition_id for o in data.split.held_out.observations]
    result = assess_ocv_empirical_adequacy(_curve_cell(param, estimates), _points(data, ids, direction=ConditioningDirection.CHARGE))
    assert result.status is OcvEmpiricalStatus.EVIDENCE_OUTSIDE_CLAIM


def test_measured_b3_evidence_can_make_a_cell_inadequate_and_on_curve_values_adequate(H, best, data, results):
    ids = [o.condition_id for o in data.split.held_out.observations]
    p1 = H.parameterization("P1")
    chord = np.asarray(list(results["models"]["P1"]["calibration"]["estimates_v"].values()))
    assert assess_ocv_empirical_adequacy(_curve_cell(p1, chord), _points(data, ids)).status is OcvEmpiricalStatus.EMPIRICALLY_INADEQUATE
    _, param, estimates = best
    cell = _curve_cell(param, estimates)
    exact = {i: cell.open_circuit_voltage(Q(data.z[i], "dimensionless")).magnitude_in("volt") for i in ids}
    assert assess_ocv_empirical_adequacy(cell, _points(data, ids, exact)).status is OcvEmpiricalStatus.EMPIRICALLY_ADEQUATE


def test_applicability_is_carried_and_never_consulted(best, data):
    _, param, estimates = best
    cell = _curve_cell(param, estimates)
    ids = [o.condition_id for o in data.split.held_out.observations]
    exact = {i: cell.open_circuit_voltage(Q(data.z[i], "dimensionless")).magnitude_in("volt") for i in ids}
    # INF-09 (audit): applicability is a typed ValidityAssessment now; the bare string
    # "violated" (not even a validity status) is refused. Still carried, still not consulted.
    from engcore.scientific.models.definition import ValidityAssessment, ValidityStatus

    outside = ValidityAssessment(status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, violated=("audit",))
    result = assess_ocv_empirical_adequacy(cell, _points(data, ids, exact), applicability_status=outside)
    assert result.status is OcvEmpiricalStatus.EMPIRICALLY_ADEQUATE and result.applicability_status == "outside_validated_domain"


def test_a_curve_cell_is_scored_on_its_curve_not_its_endpoint_chord(best, data):
    _, param, estimates = best
    cell = _curve_cell(param, estimates)
    knee = [o.condition_id for o in data.split.held_out.observations if data.region[o.condition_id] == "KNEE"]
    scored = assess_ocv_empirical_adequacy(cell, _points(data, knee)).scored
    v0, v1 = cell.open_circuit_voltage_at_empty.magnitude_in("volt"), cell.open_circuit_voltage_at_full.magnitude_in("volt")
    for row in scored:
        on_curve = cell.open_circuit_voltage(Q(row["state_of_charge"], "dimensionless")).magnitude_in("volt")
        assert row["declared_v"] == on_curve
        assert abs(on_curve - (v0 + (v1 - v0) * row["state_of_charge"])) > 0.05


# =====================================================================
# Phase 20: curve cutoff, regression only
# =====================================================================

def _declared(form):
    return DeclaredCurve(quantity=ctx.OCV_CURVE, against=ctx.STATE_OF_CHARGE, against_unit="dimensionless",
                         unit="volt", lower=0.0, upper=1.0, form=form)


def _invert(curve, cutoff, current=0.11):
    return ctx.voltage_cutoff_state_of_charge_on_curve(cutoff_voltage=Q(cutoff, "volt"), current=Q(current, "ampere"),
                                                       internal_resistance=Q(0.0126, "ohm"), curve=curve)


def test_curve_inversion_is_active_on_the_b3_curve(best):
    _, param, estimates = best
    curve = param.curve(tuple(estimates))
    result = _invert(curve, 3.0)
    assert result.status is ValidityStatus.IN_DOMAIN
    z = result.value.magnitude
    assert curve.evaluate(Q(z, "dimensionless")).value.magnitude_in("volt") - 0.11 * 0.0126 == pytest.approx(3.0, abs=1e-9)


def test_no_chord_fallback_answers_the_dataset_cutoff(best, secondary):
    _, param, estimates = best
    result = _invert(param.curve(tuple(estimates)), 2.0)
    assert result.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN and result.value is None
    assert secondary["cutoff_regression_on_best_curve"]["dataset_cutoff_2.0V_at_0.11A"]["status"] == result.status.value


def test_a_non_monotone_curve_in_b3_parameterization_refuses(H):
    humped = H.parameterization("P2").curve((3.0, 3.5, 3.1))
    result = _invert(humped, 3.2)
    assert result.value is None and "not strictly increasing" in result.reason


def test_a_discontinuous_curve_refuses():
    jump = _declared(PiecewiseForm((0.5,), (PolynomialForm((3.0, 0.2)), PolynomialForm((3.3, 0.1)))))
    result = _invert(jump, 3.2 + 0.11 * 0.0126)
    assert result.value is None and "discontinuity" in result.reason


def test_a_step_table_refuses():
    step = _declared(TabulatedForm(((0.0, 2.9), (1.0, 3.4)), Interpolation.PREVIOUS))
    assert _invert(step, 3.1).value is None


def test_the_solver_still_refuses_a_b3_curve_with_a_cutoff(best):
    _, param, estimates = best
    cell = _curve_cell(param, estimates)
    load = battery_cell.DischargeLoad(load_id="L", current=Q(0.11, "ampere"), initial_state_of_charge=Q(0.9, "dimensionless"),
                                      cell_temperature=Q(298.15, "kelvin"), duration=Q(60.0, "second"), cutoff_voltage=Q(3.0, "volt"))
    with pytest.raises(InvalidScientificProblem, match="has not been migrated"):
        evaluate_step(cell, load)
