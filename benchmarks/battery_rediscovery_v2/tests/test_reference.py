"""The reference truth table on synthetic problems whose truth is known by construction.

Every problem here is generated in this file by a plain per-sample loop of the declared 1RC recursion (the
test's own forward model, independent of the module's blockwise one), so the expected verdicts follow from
the design of the data, not from the module under test. No real pack data is read.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from benchmarks.battery_rediscovery_v2.evaluator import reference as ref

TRUE = {"R0": 0.02, "R1": 0.015, "C1": 2000.0}
OCV_Z = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def ocv_true(z):
    return 3.0 + 1.1 * z - 0.35 * (z - 0.5) ** 2 + 0.05 * math.sin(6.0 * z)


OCV_KNOTS = [[z, ocv_true(z)] for z in OCV_Z]
BOUNDS = {"R0": [1e-3, 0.2], "R1": [1e-3, 0.2], "C1": [10.0, 1e5]}


# ------------------------------------------------------------------------------------- generators


def naive_simulate(t, current, z0, q, p0, theta, knot_z, knot_v):
    """The declared recursion, one sample at a time."""
    r0, r1, c1 = theta
    n = len(t)
    v = [0.0] * n
    z, v1 = z0, p0
    v[0] = float(np.interp(z, knot_z, knot_v)) - current[0] * r0 - v1
    for k in range(1, n):
        dt = t[k] - t[k - 1]
        z = z - current[k] * dt / q
        a = math.exp(-dt / (r1 * c1))
        v1 = a * v1 + r1 * (1.0 - a) * current[k]
        v[k] = float(np.interp(z, knot_z, knot_v)) - current[k] * r0 - v1
    return np.asarray(v)


def segment_times(duration):
    """Logger-like non-uniform sampling: dense after a switch, sparse later (dt 0.02 s .. 5 s)."""
    out, t, dt = [], 0.0, 0.02
    while t + dt < duration:
        t += dt
        out.append(t)
        dt = min(dt * 1.7, 5.0)
    out.append(duration)
    return out


def pulse_protocol(level, pulses=4, on=30.0, off=60.0):
    """Discharge pulses with rests. The current at a sample flowed over the interval ending there."""
    t, current = [0.0], [0.0]
    start = 0.0
    for _ in range(pulses):
        for amp, duration in ((level, on), (0.0, off)):
            for s in segment_times(duration):
                t.append(start + s)
                current.append(amp)
            start += duration
    return np.asarray(t), np.asarray(current)


def trajectory(tid, unit, level, *, z0=0.9, q=9000.0, theta=None, knot_z=None, knot_v=None, noise=0.5e-3,
               seed=0, extra=None, protocol=None, temperature=25.0):
    theta = theta or TRUE
    knot_z = OCV_Z if knot_z is None else knot_z
    knot_v = [v for _, v in OCV_KNOTS] if knot_v is None else knot_v
    t, current = protocol if protocol is not None else pulse_protocol(level)
    v = naive_simulate(t, current, z0, q, 0.0, (theta["R0"], theta["R1"], theta["C1"]), knot_z, knot_v)
    rng = np.random.default_rng(seed)
    v = v + rng.uniform(-noise, noise, size=v.size)
    if extra is not None:
        v = v + extra(t)
    return {"id": tid, "unit_id": unit, "kind": "pulse",
            "columns": {"t_s": t.tolist(), "current_A": current.tolist(), "level_A": [level] * len(t),
                        "voltage_V": v.tolist(), "temperature_C": [temperature] * len(t)},
            "initial_state": {"soc": z0}, "conditions": {"initial_polarization": 0.0, "capacity_As": q}}


def problem(calibration, *, within=None, cross=None, sigma="declared", family=None, bar=(3e-3, 6e-3),
            half_width=1e-3):
    if sigma == "declared":
        noise = {"sigma": half_width / math.sqrt(3.0), "status": "DECLARED_TYPE_B", "half_width": half_width,
                 "distribution": "uniform"}
    else:
        noise = {"sigma": None, "status": "UNKNOWN"}
    family = family or {"family_id": "rc1_measured_ocv/1", "parameter_bounds": BOUNDS,
                        "constants": {"ocv_knots": OCV_KNOTS}, "ocv": {"status": "MEASURED_FIXED"}}
    sets = {"calibration": calibration}
    acceptance = {}
    for key, value in (("within_unit_heldout", within), ("cross_unit_heldout", cross)):
        if value is not None:
            sets[key] = value
            for name in value:
                acceptance[f"{key}/{name}"] = {"rmse_max": bar[0], "p95_abs_max": bar[1]}
    return {"schema": "forge.mind.repsem.problem/1", "clock": "t_s", "observable": "voltage_V",
            "declared_family": family, "requested_parameters": ["R0", "R1", "C1"], "measurement_noise": noise,
            "adequacy_bar": {"rmse_max": bar[0], "p95_abs_max": bar[1]}, "acceptance": acceptance,
            "applicability": {"variables": ["level_A", "soc", "temperature_C"],
                              "widen": {"level_A": 0.1, "soc": 0.01, "temperature_C": 2.0}},
            "sets": sets}


def base_calibration(**kwargs):
    return [trajectory("cal-1", "U1", 1.0, seed=1, **kwargs), trajectory("cal-2", "U1", 2.0, seed=2, **kwargs)]


# ------------------------------------------------------------------------------------ forward model


def test_linear_recursion_matches_a_loop_across_extreme_steps():
    rng = np.random.default_rng(7)
    n = 1000
    lna = -np.concatenate([rng.uniform(0.0, 1e-3, 300), rng.uniform(0.0, 5.0, 300), rng.uniform(100.0, 1e5, 100),
                           np.zeros(50), rng.uniform(0.0, 0.1, 250)])
    rng.shuffle(lna)
    b = rng.normal(size=n)
    expected, x = [], 0.37
    for k in range(n):
        x = math.exp(lna[k]) * x + b[k]
        expected.append(x)
    got = ref._linrec(lna, b, 0.37)
    assert np.max(np.abs(got - np.asarray(expected))) < 1e-12
    for m in (1, 15, 16, 17, 33, 256, 257):
        loop, x = [], -1.5
        for k in range(m):
            x = math.exp(lna[k]) * x + b[k]
            loop.append(x)
        assert np.max(np.abs(ref._linrec(lna[:m], b[:m], -1.5) - np.asarray(loop))) < 1e-12


def test_forward_model_matches_the_declared_recursion_with_nonzero_polarization():
    traj = trajectory("x", "U1", 2.0, noise=0.0)
    traj["conditions"]["initial_polarization"] = 0.004
    tr = ref._Trajectory(traj)
    model = ref._Model({"family_id": "rc1_measured_ocv/1", "parameter_bounds": BOUNDS,
                        "constants": {"ocv_knots": OCV_KNOTS}})
    theta = np.array([0.031, 0.012, 900.0])
    predicted, _ = model.simulate(tr, theta, False)
    expected = naive_simulate(tr.t, tr.current, 0.9, 9000.0, 0.004, theta, OCV_Z, [v for _, v in OCV_KNOTS])
    assert np.max(np.abs(predicted - expected)) < 1e-13


def test_analytic_jacobian_matches_central_differences_for_the_fitted_family():
    knots = [0.5, 0.65, 0.8, 0.95]
    family = {"family_id": "rc1_fitted_ocv/1",
              "parameter_bounds": {**BOUNDS, **{f"ocv_k{j}": [2.0, 4.5] for j in range(4)}},
              "constants": {"ocv_knots_soc": knots}, "ocv": {"status": "UNKNOWN_FITTED_TABLE"}}
    model = ref._Model(family)
    traj = trajectory("x", "U1", 2.0, q=600.0, z0=0.95, noise=0.0)
    traj["conditions"]["initial_polarization"] = -0.002
    tr = ref._Trajectory(traj)
    x = np.log(np.array([0.025, 0.011, 1500.0, 3.4, 3.6, 3.75, 3.9]))
    _, jac = model.simulate(tr, np.exp(x), True)
    h = 1e-6
    for j in range(x.size):
        up, down = x.copy(), x.copy()
        up[j] += h
        down[j] -= h
        fd = (model.simulate(tr, np.exp(up), False)[0] - model.simulate(tr, np.exp(down), False)[0]) / (2 * h)
        assert np.max(np.abs(fd - jac[:, j])) < 1e-7 * max(1.0, np.max(np.abs(fd)))


# --------------------------------------------------------------------------------- truth by design


@pytest.fixture(scope="module")
def clean_table():
    """1RC data with small noise; in-domain same-unit held-out; a different cell (R0 x2.5) cross-unit."""
    other = dict(TRUE, R0=0.05)
    spec = problem(base_calibration(),
                   within={"mid": [trajectory("w-mid", "U1", 1.5, z0=0.895, seed=3)]},
                   cross={"other_cell": [trajectory("x-1", "U2", 1.5, z0=0.895, theta=other, seed=4)]})
    return spec, ref.truth_table(spec)


def test_generated_by_the_model_is_adequate_identifiable_and_has_no_discrepancy(clean_table):
    _, table = clean_table
    assert table["MODEL_ADEQUACY"]["truth"] == "SUPPORTED"
    ident = table["IDENTIFIABILITY"]
    assert ident["truth"] == "SUPPORTED", ident["basis"]
    assert ident["declared"]["status"] == "PARAMETERS_IDENTIFIABLE"
    assert not ident["near_structural"] and not ident["ambiguous"] and ident["on_bound"] == []
    assert table["MODEL_DISCREPANCY"]["truth"] == "SUPPORTED", table["MODEL_DISCREPANCY"]["basis"]
    params = table["diagnostics"]["parameters"]
    for name, value in TRUE.items():
        assert abs(params[name] / value - 1.0) < 0.05, (name, params[name])


def test_in_domain_same_unit_heldout_is_supported_and_a_different_cell_is_not(clean_table):
    _, table = clean_table
    assert table["WITHIN_CELL_GENERALIZATION"]["truth"] == "SUPPORTED"
    assert table["diagnostics"]["subsets"]["within_unit_heldout"]["mid"]["in_domain"] is True
    cross = table["diagnostics"]["subsets"]["cross_unit_heldout"]["other_cell"]
    assert cross["in_domain"] is True and cross["label"] == "NOT_SUPPORTED"
    assert table["CROSS_CELL_TRANSFER"]["truth"] == "NOT_SUPPORTED"
    assert cross["bias"] > 0.0  # r = V_pred - V_meas, and a larger true R0 makes the measured voltage lower


def test_output_is_json_clean_and_deterministic(clean_table):
    spec, table = clean_table
    text = json.dumps(table, sort_keys=True, allow_nan=False)
    assert json.dumps(ref.truth_table(spec), sort_keys=True, allow_nan=False) == text
    fit = ref.reference_fit(spec)
    json.dumps(fit, allow_nan=False)
    assert len(fit["starts"]) == 125
    assert fit["optimum"] == table["diagnostics"]["parameters"]
    assert len(fit["jacobian_ln"]) == table["diagnostics"]["calibration"]["n"]


def test_unknown_sigma_refuses_identifiability_and_discrepancy_and_absent_sets_are_not_assessable():
    table = ref.truth_table(problem(base_calibration(), sigma=None))
    assert table["MODEL_ADEQUACY"]["truth"] == "SUPPORTED"
    assert table["IDENTIFIABILITY"]["truth"] == "NOT_ASSESSABLE"
    assert table["MODEL_DISCREPANCY"]["truth"] == "NOT_ASSESSABLE"
    assert table["WITHIN_CELL_GENERALIZATION"] == {"truth": "NOT_ASSESSABLE", "basis": "no set supplied",
                                                   "subsets": {}}
    assert table["CROSS_CELL_TRANSFER"]["truth"] == "NOT_ASSESSABLE"


def test_an_unmodelled_term_is_inadequate_with_discrepancy():
    def ripple(t):
        return 0.015 * np.sin(2.0 * np.pi * t / 40.0)

    table = ref.truth_table(problem(base_calibration(extra=ripple)))
    assert table["MODEL_ADEQUACY"]["truth"] == "NOT_SUPPORTED"
    assert table["MODEL_DISCREPANCY"]["truth"] == "NOT_SUPPORTED", table["MODEL_DISCREPANCY"]
    assert table["IDENTIFIABILITY"]["sigma_inflated"] > table["IDENTIFIABILITY"]["sigma"]


def test_heldout_outside_the_calibration_domain_is_not_assessable_when_it_passes():
    spec = problem(base_calibration(),
                   within={"mid": [trajectory("w-mid", "U1", 1.5, z0=0.895, seed=3)],
                           "high": [trajectory("w-high", "U1", 4.0, seed=5)],
                           "hot": [trajectory("w-hot", "U1", 1.5, z0=0.895, seed=6, temperature=40.0)]},
                   cross={"twin": [trajectory("x-twin", "U2", 1.5, z0=0.895, seed=7)],
                          "includes_cal_unit": [trajectory("x-mixed", "U1", 1.5, z0=0.895, seed=8)]})
    table = ref.truth_table(spec)
    within = table["diagnostics"]["subsets"]["within_unit_heldout"]
    assert within["mid"]["label"] == "SUPPORTED"
    assert within["high"]["label"] == "OOD_PASS" and {"level_A", "soc"} <= set(within["high"]["outside"])
    assert within["high"]["outside"]["level_A"]["above_by"] == pytest.approx(4.0 - 2.1)
    assert within["hot"]["label"] == "OOD_PASS" and set(within["hot"]["outside"]) == {"temperature_C"}
    assert table["WITHIN_CELL_GENERALIZATION"]["truth"] == "NOT_ASSESSABLE"
    cross = table["diagnostics"]["subsets"]["cross_unit_heldout"]
    assert cross["twin"]["label"] == "SUPPORTED"
    assert cross["includes_cal_unit"]["unit_relation_holds"] is False
    assert cross["includes_cal_unit"]["label"] == "OOD_PASS"
    assert table["CROSS_CELL_TRANSFER"]["truth"] == "NOT_ASSESSABLE"


def test_a_failing_out_of_domain_subset_is_unscored_not_refused():
    other = dict(TRUE, R0=0.05)
    spec = problem(base_calibration(),
                   within={"mid": [trajectory("w-mid", "U1", 1.5, z0=0.895, seed=3)]},
                   cross={"other_high": [trajectory("x-h", "U2", 4.0, theta=other, seed=9)]})
    table = ref.truth_table(spec)
    assert table["diagnostics"]["subsets"]["cross_unit_heldout"]["other_high"]["label"] == "OOD_FAIL"
    assert table["CROSS_CELL_TRANSFER"]["truth"] is None


def test_constant_current_without_rest_is_near_structurally_non_identifiable():
    # tau <= 0.25 s inside the bounds and a 20 s logger step: the transient is never sampled, so R0 and R1
    # enter only through I (R0 + R1) and their Jacobian columns are parallel.
    t = np.arange(0.0, 1201.0, 20.0)
    current = np.full(t.size, 2.0)
    theta = {"R0": 0.02, "R1": 0.015, "C1": 2.0}
    calibration = [trajectory("cc", "U1", 2.0, theta=theta, protocol=(t, current), seed=11)]
    bounds = {"R0": [1e-3, 0.2], "R1": [1e-3, 0.05], "C1": [0.1, 5.0]}
    family = {"family_id": "rc1_measured_ocv/1", "parameter_bounds": bounds,
              "constants": {"ocv_knots": OCV_KNOTS}, "ocv": {"status": "MEASURED_FIXED"}}
    for sigma in ("declared", None):
        table = ref.truth_table(problem(calibration, family=family, sigma=sigma))
        ident = table["IDENTIFIABILITY"]
        assert ident["near_structural"] is True
        assert min(ident["orthogonal_norms"][n] for n in ("R0", "R1")) < 1e-6
        assert ident["truth"] == "NOT_SUPPORTED"
        assert table["MODEL_ADEQUACY"]["truth"] == "SUPPORTED"  # the sum R0 + R1 still fits


def fitted_family(knots):
    return {"family_id": "rc1_fitted_ocv/1",
            "parameter_bounds": {**BOUNDS, **{f"ocv_k{j}": [2.0, 4.5] for j in range(len(knots))}},
            "constants": {"ocv_knots_soc": knots}, "ocv": {"status": "UNKNOWN_FITTED_TABLE"}}


def fitted_calibration():
    # a small capacity so four pulses sweep SOC from 0.95 to about 0.55
    return [trajectory("f-1", "U1", 2.0, q=600.0, z0=0.95, seed=21),
            trajectory("f-2", "U1", 1.0, q=600.0, z0=0.9, seed=22)]


def test_fitted_ocv_family_recovers_the_cell():
    knots = [0.5, 0.65, 0.8, 0.95]
    spec = problem(fitted_calibration(), family=fitted_family(knots))
    fit = ref.reference_fit(spec)
    assert len(fit["starts"]) == 27
    for name, value in TRUE.items():
        assert abs(fit["optimum"][name] / value - 1.0) < 0.1, (name, fit["optimum"][name])
    table = ref.truth_table(spec)
    assert table["MODEL_ADEQUACY"]["truth"] == "SUPPORTED"
    assert table["IDENTIFIABILITY"]["near_structural"] is False


def test_an_unsupported_ocv_knot_makes_the_fisher_information_singular():
    knots = [0.1, 0.5, 0.65, 0.8, 0.95]  # no sample reaches below 0.5, so ocv_k0 has a zero column
    table = ref.truth_table(problem(fitted_calibration(), family=fitted_family(knots)))
    ident = table["IDENTIFIABILITY"]
    assert ident["truth"] == "NOT_SUPPORTED" and ident["singular"] is True
    assert "singular Fisher information" in ident["basis"]
    assert table["MODEL_DISCREPANCY"]["truth"] is None
