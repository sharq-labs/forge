"""The battery OCV inference adapter, and the pipeline it feeds, on SYNTHETIC controls.

Nothing here touches measured data. That is deliberate: before a measured
result can mean anything, the pipeline has to be shown able to reach BOTH
verdicts on cases whose answer is known --

* a chord generated from the model itself, plus declared noise, must calibrate,
  be identifiable, and pass held-out adequacy;
* a curved open-circuit voltage the chord cannot represent must calibrate, be
  identifiable, and FAIL held-out adequacy.

If only the second held, a measured failure could be the pipeline's inability
to pass anything. If only the first held, a measured pass could be its
inability to fail. Every observation below is labelled synthetic in its source
reference, and none is ever called a measurement.
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
    InferenceAdmissibilityError,
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
TWIN = TwinReference(twin_id="battery.synthetic.control_cell", version="1")
FIXED = bc.FixedCellDeclaration(
    cell_id="SYNTH_1",
    nominal_capacity=Q(1.1, ctx.CAPACITY_UNIT),
    internal_resistance=Q(0.0126, ctx.RESISTANCE_UNIT),
    chemistry=ctx.LITHIUM_ION,
)
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


def predict(z: float, empty: float, full: float, current_a: float = 0.22) -> float:
    return bc.ocv_prediction(
        FIXED, condition(z, current_a), ocv_at_empty=Q(empty, VOLT), ocv_at_full=Q(full, VOLT)
    ).value(bc.OCV_OBSERVABLE).magnitude_in(VOLT)


# =====================================================================
# the adapter
# =====================================================================

def test_a_prediction_is_admitted_through_the_production_solver():
    prediction = bc.ocv_prediction(
        FIXED, condition(0.4), ocv_at_empty=Q(3.0, VOLT), ocv_at_full=Q(3.4, VOLT)
    )
    assert prediction.admission_route == "analytic"
    assert prediction.source_result.is_usable
    assert prediction.source_result.provenance.solvers == (
        ("engcore.battery.cell_closed_form", "0.1.0"),
    )
    assert prediction.observable_names == (bc.OCV_OBSERVABLE,)


@pytest.mark.parametrize("z", [0.0, 0.2, 0.4, 0.5, 0.6, 0.8])
def test_the_admitted_value_is_the_models_own_chord(z):
    assert predict(z, 2.9, 3.4) == pytest.approx(2.9 + 0.5 * z, abs=1e-12)


@pytest.mark.parametrize("z", [0.0, 0.2, 0.5, 0.8])
def test_the_compared_value_does_not_depend_on_the_conditioning_current(z):
    """Asserted bitwise, because the claim is that current does not ENTER it."""
    assert predict(z, 2.9, 3.4, 0.22) == predict(z, 2.9, 3.4, 1.1) == predict(z, 2.9, 3.4, 0.011)


def test_reaching_a_state_of_charge_by_charging_is_refused():
    with pytest.raises(InvalidScientificProblem, match="discharge only"):
        bc.RestedOcvCondition(
            "UP", Q(0.9, ctx.DIMENSIONLESS), Q(0.22, ctx.CURRENT_UNIT),
            Q(296.15, ctx.TEMPERATURE_UNIT), initial_state_of_charge=Q(0.5, ctx.DIMENSIONLESS),
        )


@pytest.mark.parametrize("target", [-0.01, 1.01])
def test_a_state_of_charge_outside_the_unit_interval_is_refused(target):
    with pytest.raises(InvalidScientificProblem, match=r"\[0, 1\]"):
        condition(target)


def test_a_non_positive_conditioning_current_is_refused():
    with pytest.raises(InvalidScientificProblem, match="strictly positive"):
        bc.RestedOcvCondition(
            "I0", Q(0.5, ctx.DIMENSIONLESS), Q(0.0, ctx.CURRENT_UNIT),
            Q(296.15, ctx.TEMPERATURE_UNIT),
        )


def test_a_discharge_that_misses_its_target_is_refused(monkeypatch):
    """The target check is what makes 'OCV at that state of charge' true, so it bites."""
    real = bc.RestedOcvCondition.load

    def short(self, fixed):
        load = real(self, fixed)
        return type(load)(
            load_id=load.load_id, current=load.current,
            initial_state_of_charge=load.initial_state_of_charge,
            cell_temperature=load.cell_temperature,
            duration=Q(load.duration.magnitude_in("hour") * 0.9, "hour"),
        )

    monkeypatch.setattr(bc.RestedOcvCondition, "load", short)
    with pytest.raises(InferenceAdmissibilityError, match="not the declared"):
        bc.ocv_prediction(FIXED, condition(0.4), ocv_at_empty=Q(3.0, VOLT), ocv_at_full=Q(3.4, VOLT))


def test_only_the_open_circuit_voltage_is_admitted():
    observations = ObservationSet(
        (GaussianObservation("Z040", "terminal_voltage", Q(3.2, VOLT), Q(0.002, VOLT), "synthetic:x"),),
        dataset_id="synthetic.wrong_observable",
    )
    with pytest.raises(InferenceAdmissibilityError, match="admits only"):
        bc.ocv_forward_evaluator(observations, fixed=FIXED, conditions=CONDITIONS)


def test_an_observation_with_no_declared_conditioning_is_refused():
    observations = ObservationSet(
        (GaussianObservation("Z999", bc.OCV_OBSERVABLE, Q(3.2, VOLT), Q(0.002, VOLT), "synthetic:x"),),
        dataset_id="synthetic.unconditioned",
    )
    with pytest.raises(InferenceAdmissibilityError, match="no declared conditioning"):
        bc.ocv_forward_table(observations, [(3.0, 3.4)], fixed=FIXED, conditions=CONDITIONS)


def test_a_chord_that_does_not_rise_with_charge_is_refused_not_scored():
    """V_full <= V_empty is not a bad fit, it is not a cell."""
    observations = ObservationSet(
        (GaussianObservation("Z040", bc.OCV_OBSERVABLE, Q(3.2, VOLT), Q(0.002, VOLT), "synthetic:x"),),
        dataset_id="synthetic.flat",
    )
    evaluate = bc.ocv_forward_evaluator(observations, fixed=FIXED, conditions=CONDITIONS)
    assert evaluate((3.3, 3.3)) is None
    assert evaluate((3.4, 3.2)) is None
    assert evaluate((3.2, 3.4)) is not None
    table = bc.ocv_forward_table(
        observations, [(3.3, 3.3), (3.2, 3.4)], fixed=FIXED, conditions=CONDITIONS
    )
    assert list(table.admissible_mask) == [False, True]
    assert "must exceed" in table.rejection_reasons[0]


def test_the_parameter_set_is_the_two_chord_endpoints_in_volts():
    parameters = bc.build_ocv_chord_parameter_set(lower=Q(2.0, VOLT), upper=Q(3.6, VOLT))
    assert tuple(p.name for p in parameters.parameters) == bc.CHORD_PARAMETERS
    assert all(p.unit == VOLT for p in parameters.parameters)
    assert all(p.model == bc.RINT_MODEL_REF for p in parameters.parameters)


# =====================================================================
# the pipeline, on synthetic controls with a known answer
# =====================================================================

def synthetic_source(truth, seed):
    rng = np.random.default_rng(seed)
    return ObservationSet(
        tuple(
            GaussianObservation(
                condition_id=condition(z).condition_id,
                observable_name=bc.OCV_OBSERVABLE,
                value=Q(truth(z) + float(rng.normal(0.0, SIGMA_V)), VOLT),
                sigma=Q(SIGMA_V, VOLT),
                source_ref=f"synthetic:battery_ocv_control:seed={seed}",
            )
            for z in CAL_Z + HELD_Z
        ),
        dataset_id="synthetic.battery.ocv.source",
    )


def run_pipeline(truth, seed=20260912):
    source = synthetic_source(truth, seed)
    split = ObservationSplit.partition(
        source=source,
        held_out_condition_ids=tuple(condition(z).condition_id for z in HELD_Z),
        twin=TWIN,
        calibration_dataset_id="synthetic.battery.ocv.cal",
        heldout_dataset_id="synthetic.battery.ocv.held",
    )
    spec = CalibrationSpec(
        parameters=bc.build_ocv_chord_parameter_set(lower=Q(2.0, VOLT), upper=Q(3.6, VOLT)),
        fixed={},
        initial_point={bc.CHORD_PARAMETERS[0]: Q(3.2, VOLT), bc.CHORD_PARAMETERS[1]: Q(3.4, VOLT)},
        noise_model=NoiseModel(),
    )
    fit = calibrate(
        spec, split.calibration,
        bc.ocv_forward_evaluator(split.calibration, fixed=FIXED, conditions=CONDITIONS),
        heldout_dataset_id=split.heldout_dataset_id, seed=seed,
    )
    empty, full = (e.value.magnitude_in(VOLT) for e in fit.estimates)
    # A chord has a closed-form standard error; +/-6 of it resolves the grid.
    z = np.asarray(CAL_Z)
    design = np.column_stack([1.0 - z, z]) / SIGMA_V
    se = np.sqrt(np.diag(np.linalg.inv(design.T @ design)))
    axes = [np.linspace(c - 6 * s, c + 6 * s, 31) for c, s in zip((empty, full), se)]
    grid = [(float(a), float(b)) for a in axes[0] for b in axes[1]]
    table = bc.ocv_forward_table(split.calibration, grid, fixed=FIXED, conditions=CONDITIONS)
    posterior = gaussian_grid_posterior(table, split.calibration)
    predictive = bc.ocv_forward_table(split.held_out, grid, fixed=FIXED, conditions=CONDITIONS)
    residuals = []
    for observation in split.held_out.observations:
        assessment = assess_predictive_observation(
            posterior, predictive,
            PredictiveObservableSpec(observation.key, VOLT, observation.sigma),
            observation.value, twin=TWIN, model=bc.RINT_MODEL_REF,
            source_ref=observation.source_ref, heldout_dataset_id=split.heldout_dataset_id,
        )
        residuals.append(assessment.standardized_residual)
    statistic = float(np.sum(np.square(residuals)))
    return fit, assess_identifiability(posterior), residuals, float(chi2.sf(statistic, len(residuals)))


def test_control_a_known_chord_calibrates_is_identifiable_and_passes():
    fit, identifiability, residuals, p = run_pipeline(lambda z: 2.95 + 0.40 * z)
    assert fit.status is CalibrationStatus.CONVERGED
    assert identifiability.status is IdentifiabilityStatus.IDENTIFIABLE, identifiability.why
    assert p >= 0.01, (residuals, p)


def test_control_a_curved_ocv_calibrates_is_identifiable_and_fails():
    """The chord's own declared limitation: a knee near empty it cannot bend to."""
    fit, identifiability, residuals, p = run_pipeline(
        lambda z: 3.30 + 0.05 * z - 0.45 * math.exp(-z / 0.06)
    )
    assert fit.status is CalibrationStatus.CONVERGED
    assert identifiability.status is IdentifiabilityStatus.IDENTIFIABLE, identifiability.why
    assert p < 0.01, (residuals, p)
    # the miss is at the knee, not everywhere
    assert abs(residuals[0]) == max(abs(r) for r in residuals)
