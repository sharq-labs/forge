"""The existing SOC-dependent OCV curve, parameterized and calibrated -- SYNTHETIC controls.

B2's Phase 6 obligation: before the measured result means anything, the
pipeline has to reach both verdicts on known answers with the CURVE, exactly as
B1 showed it for the chord:

* a truth generated from the degree-2 node-parameterized polynomial itself must
  calibrate and pass held-out adequacy;
* a structurally different OCV (a knee and a plateau step) must fail.

Plus the parameterization facts the protocol rests on: a degree-1 curve through
nodes {0, 1} IS the chord, the nodes are declared not measured, and a curve with
more free voltages than calibration observations is structurally unidentifiable.
Every observation is labelled synthetic in its source reference.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import chi2

from engcore.adequacy import assess_predictive_observation
from engcore.domains.battery import calibration as bc
from engcore.domains.battery import context as ctx
from engcore.inference import (
    CalibrationSpec,
    CalibrationStatus,
    GaussianObservation,
    IdentifiabilityStatus,
    NoiseModel,
    ObservationSet,
    ObservationSplit,
    assess_identifiability,
    calibrate,
    gaussian_grid_posterior,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity as Q
from engcore.uq import PredictiveObservableSpec

VOLT = ctx.VOLTAGE_UNIT
TWIN = TwinReference(twin_id="battery.synthetic.curve_control_cell", version="1")
FIXED = bc.FixedCellDeclaration(
    cell_id="SYNTH_CURVE",
    nominal_capacity=Q(1.1, ctx.CAPACITY_UNIT),
    internal_resistance=Q(0.0126, ctx.RESISTANCE_UNIT),
    chemistry=ctx.LITHIUM_ION,
)
POLY2 = bc.PolynomialNodeParameterization((0.0, 0.5, 1.0))
TAB3 = bc.TabulatedKnotParameterization((0.0, 0.5, 1.0))
TAB5 = bc.TabulatedKnotParameterization((0.0, 0.25, 0.5, 0.75, 1.0))
SIGMA_V = 0.002
CAL_Z = (0.2, 0.5, 0.8)
HELD_Z = (0.0, 0.4, 0.6)


def condition(z: float, current_a: float = 0.22) -> bc.RestedOcvCondition:
    return bc.RestedOcvCondition(
        condition_id=f"Z{int(round(z * 100)):03d}",
        target_state_of_charge=Q(z, ctx.DIMENSIONLESS),
        conditioning_current=Q(current_a, ctx.CURRENT_UNIT),
        cell_temperature=Q(296.15, ctx.TEMPERATURE_UNIT),
    )


CONDITIONS = {c.condition_id: c for c in (condition(z) for z in CAL_Z + HELD_Z)}


def predict(parameterization, voltages, z):
    return bc.curve_ocv_prediction(
        FIXED, condition(z), parameterization=parameterization, voltages=voltages
    ).value(bc.OCV_OBSERVABLE).magnitude_in(VOLT)


# =====================================================================
# the parameterization
# =====================================================================

@pytest.mark.parametrize("z", [0.0, 0.2, 0.4, 0.5, 0.6, 0.8])
def test_a_degree_one_curve_through_the_ends_is_the_chord(z):
    """B2 nests B1: the linear special case of the curve family is B1's model."""
    linear = bc.PolynomialNodeParameterization((0.0, 1.0))
    chord = bc.ocv_prediction(
        FIXED, condition(z), ocv_at_empty=Q(3.2197, VOLT), ocv_at_full=Q(3.3609, VOLT)
    ).value(bc.OCV_OBSERVABLE).magnitude_in(VOLT)
    assert predict(linear, (3.2197, 3.3609), z) == pytest.approx(chord, abs=1e-12)


def test_the_polynomial_passes_through_its_declared_nodes():
    voltages = (3.05, 3.29, 3.37)
    for node, voltage in zip(POLY2.nodes, voltages):
        if node < 1.0:
            assert predict(POLY2, voltages, node) == pytest.approx(voltage, abs=1e-12)
    assert POLY2.curve(voltages).evaluate(Q(1.0, ctx.DIMENSIONLESS)).value.magnitude == pytest.approx(3.37)


def test_the_tabulated_form_interpolates_linearly_between_declared_knots():
    assert predict(TAB3, (3.0, 3.3, 3.4), 0.25) == pytest.approx(3.15, abs=1e-12)
    assert predict(TAB3, (3.0, 3.3, 3.4), 0.75) == pytest.approx(3.35, abs=1e-12)


def test_parameter_names_carry_the_declared_positions_not_measured_values():
    assert POLY2.names == (
        "open_circuit_voltage_curve@z=0",
        "open_circuit_voltage_curve@z=0.5",
        "open_circuit_voltage_curve@z=1",
    )
    parameters = bc.build_curve_parameter_set(POLY2, lower=Q(2.0, VOLT), upper=Q(3.6, VOLT))
    assert tuple(p.name for p in parameters.parameters) == POLY2.names


@pytest.mark.parametrize("nodes", [(0.0,), (0.2, 0.2), (0.0, 1.5)])
def test_a_malformed_polynomial_parameterization_is_refused(nodes):
    with pytest.raises(InvalidScientificProblem):
        bc.PolynomialNodeParameterization(nodes)


def test_a_curve_that_does_not_reach_both_ends_cannot_build_a_cell():
    """The domain requires OCV at z = 0 AND z = 1 -- the fact that makes the
    measured-map use of a table untestable when z = 0 is held out."""
    partial = bc.TabulatedKnotParameterization((0.2, 0.5, 0.8))
    refusal = bc.curve_candidate_refusal(FIXED, parameterization=partial, voltages=(3.25, 3.29, 3.33))
    assert refusal is not None and "whole charge axis" in refusal


def test_a_non_rising_curve_candidate_is_refused_not_scored():
    assert bc.curve_candidate_refusal(FIXED, parameterization=POLY2, voltages=(3.3, 3.3, 3.3)) is not None
    evaluate = bc.curve_forward_evaluator(
        ObservationSet(
            (GaussianObservation("Z050", bc.OCV_OBSERVABLE, Q(3.3, VOLT), Q(0.002, VOLT), "synthetic:x"),),
            dataset_id="synthetic.flat_curve",
        ),
        fixed=FIXED, conditions=CONDITIONS, parameterization=POLY2,
    )
    assert evaluate((3.3, 3.3, 3.3)) is None
    assert evaluate((3.2, 3.3, 3.4)) is not None


def test_the_curve_prediction_does_not_depend_on_the_conditioning_current():
    voltages = (3.1, 3.29, 3.36)
    for z in (0.0, 0.4, 0.8):
        slow = bc.curve_ocv_prediction(FIXED, condition(z, 0.22), parameterization=POLY2, voltages=voltages)
        fast = bc.curve_ocv_prediction(FIXED, condition(z, 1.1), parameterization=POLY2, voltages=voltages)
        assert slow.value(bc.OCV_OBSERVABLE) == fast.value(bc.OCV_OBSERVABLE)


# =====================================================================
# the flexibility guard
# =====================================================================

def jacobian(parameterization, zs):
    """The map from node voltages to predictions, which is linear for both forms."""
    base = np.full(len(parameterization.names), 3.3) + np.linspace(-0.1, 0.1, len(parameterization.names))
    f0 = np.asarray([predict(parameterization, tuple(base), z) for z in zs])
    columns = []
    for index in range(len(base)):
        bumped = base.copy()
        bumped[index] += 0.01
        columns.append((np.asarray([predict(parameterization, tuple(bumped), z) for z in zs]) - f0) / 0.01)
    return np.column_stack(columns)


def test_three_free_voltages_are_determined_by_three_calibration_levels():
    assert np.linalg.matrix_rank(jacobian(POLY2, CAL_Z), tol=1e-9) == 3
    assert np.linalg.matrix_rank(jacobian(TAB3, CAL_Z), tol=1e-9) == 3


def test_five_free_voltages_are_structurally_unidentifiable_from_three_levels():
    """More flexibility than the calibration data can pin down, by rank, before any data."""
    rank = np.linalg.matrix_rank(jacobian(TAB5, CAL_Z), tol=1e-9)
    assert rank == 3 < len(TAB5.names)


# =====================================================================
# the pipeline, on synthetic controls with a known answer
# =====================================================================

def closed_form_centre(parameterization, observations):
    zs = [float(o.condition_id[1:]) / 100 for o in observations.observations]
    y = np.asarray([o.value.magnitude_in(VOLT) for o in observations.observations])
    s = np.asarray([o.sigma.magnitude_in(VOLT) for o in observations.observations])
    # Both forms map node voltages to predictions linearly, with no offset, so
    # weighted least squares on the Jacobian is the exact estimator.
    J = jacobian(parameterization, zs)
    weighted = J / s[:, None]
    cov = np.linalg.inv(weighted.T @ weighted)
    theta = cov @ weighted.T @ (y / s)
    return theta, np.sqrt(np.diag(cov))


def run_pipeline(truth, seed=20260912, per_axis=13):
    rng = np.random.default_rng(seed)
    source = ObservationSet(
        tuple(
            GaussianObservation(
                condition_id=condition(z).condition_id, observable_name=bc.OCV_OBSERVABLE,
                value=Q(truth(z) + float(rng.normal(0.0, SIGMA_V)), VOLT), sigma=Q(SIGMA_V, VOLT),
                source_ref=f"synthetic:battery_ocv_curve_control:seed={seed}",
            )
            for z in CAL_Z + HELD_Z
        ),
        dataset_id="synthetic.battery.curve.source",
    )
    split = ObservationSplit.partition(
        source=source, held_out_condition_ids=tuple(condition(z).condition_id for z in HELD_Z),
        twin=TWIN, calibration_dataset_id="synthetic.battery.curve.cal",
        heldout_dataset_id="synthetic.battery.curve.held",
    )
    spec = CalibrationSpec(
        parameters=bc.build_curve_parameter_set(POLY2, lower=Q(2.0, VOLT), upper=Q(3.6, VOLT)),
        fixed={},
        initial_point={n: Q(v, VOLT) for n, v in zip(POLY2.names, (3.2, 3.3, 3.4))},
        noise_model=NoiseModel(),
    )
    fit = calibrate(
        spec, split.calibration,
        bc.curve_forward_evaluator(split.calibration, fixed=FIXED, conditions=CONDITIONS, parameterization=POLY2),
        heldout_dataset_id=split.heldout_dataset_id, seed=seed,
    )
    theta, se = closed_form_centre(POLY2, split.calibration)
    axes = [np.linspace(t - 6 * e, t + 6 * e, per_axis) for t, e in zip(theta, se)]
    grid = [(float(a), float(b), float(c)) for a in axes[0] for b in axes[1] for c in axes[2]]
    table = bc.curve_forward_table(split.calibration, grid, fixed=FIXED, conditions=CONDITIONS, parameterization=POLY2)
    posterior = gaussian_grid_posterior(table, split.calibration)
    predictive = bc.curve_forward_table(split.held_out, grid, fixed=FIXED, conditions=CONDITIONS, parameterization=POLY2)
    residuals = []
    for obs in split.held_out.observations:
        a = assess_predictive_observation(
            posterior, predictive, PredictiveObservableSpec(obs.key, VOLT, obs.sigma), obs.value,
            twin=TWIN, model=bc.RINT_MODEL_REF, source_ref=obs.source_ref,
            heldout_dataset_id=split.heldout_dataset_id,
        )
        residuals.append(a.standardized_residual)
    p = float(chi2.sf(float(np.sum(np.square(residuals))), len(residuals)))
    return fit, theta, assess_identifiability(posterior), residuals, p


def test_control_a_truth_from_the_curve_itself_calibrates_and_passes():
    truth_nodes = (3.22, 3.30, 3.36)
    truth = lambda z: POLY2.curve(truth_nodes).evaluate(Q(z, ctx.DIMENSIONLESS)).value.magnitude  # noqa: E731
    fit, theta, identifiability, residuals, p = run_pipeline(truth)
    assert fit.status is CalibrationStatus.CONVERGED
    estimates = [e.value.magnitude_in(VOLT) for e in fit.estimates]
    assert estimates == pytest.approx(list(theta), abs=1e-6), "calibrate and the closed form disagree"
    assert identifiability.status is IdentifiabilityStatus.IDENTIFIABLE, identifiability.why
    assert p >= 0.01, (residuals, p)


def test_control_a_structurally_different_ocv_calibrates_and_fails():
    """A knee near empty and a plateau step: what three calibration levels cannot see."""
    truth = lambda z: 3.30 + 0.03 * z + 0.02 * math.tanh((z - 0.7) / 0.03) - 0.45 * math.exp(-z / 0.06)  # noqa: E731
    fit, _, identifiability, residuals, p = run_pipeline(truth)
    assert fit.status is CalibrationStatus.CONVERGED
    assert identifiability.status is IdentifiabilityStatus.IDENTIFIABLE, identifiability.why
    assert p < 0.01, (residuals, p)
    assert abs(residuals[0]) == max(abs(r) for r in residuals)
