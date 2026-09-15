from __future__ import annotations

import numpy as np

import pytest

from experiments.kinetics_k2.k2_config import (
    CONDITION_BY_ID,
    MULTI_CONDITION_IDS,
    OBSERVABLE_NAMES,
    PRIMARY_SEED,
    TRUTH_COORDINATES,
    chemistry_from_coordinates,
)
from experiments.kinetics_k2.k2_forward import (
    evaluate_truth_predictions,
    observation_set_from_truth_means,
)
from engcore.domains.kinetics.cstr.inference import CSTRInferenceForwardAdapter
from engcore.domains.kinetics.cstr.problem import METRIC_UNITS
from engcore.inference import (
    InferenceAdmissibilityError,
    require_admissible_numerical_prediction,
)
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity


#: Audit CAP-01. The CSTR's single-liquid-phase conditions read the fluid's own
#: boiling and freezing temperatures and are UNKNOWN until they are declared.
#: The frozen K-series parameterization (the Seborg textbook liquid) declares
#: neither, so its runs are no longer IN_DOMAIN and the inference boundary
#: refuses them on applicability -- that refusal is asserted below, and is the
#: correct behaviour. To keep exercising the admission path itself, the
#: positive tests declare a liquid range HERE: a hypothetical pressurised liquid
#: that stays liquid between 260 K and 650 K. It is this test's declaration,
#: not a property of the textbook parameterization, and it clears every K-series
#: adiabatic ceiling (at most 579.2 K) and floor (at least 285 K).
DECLARED_BOILING = Quantity(650.0, "kelvin")
DECLARED_FREEZING = Quantity(260.0, "kelvin")
PHASE_CONDITIONS = (
    "declared_temperature_to_boiling_ratio",
    "adiabatic_ceiling_to_boiling_ratio",
    "adiabatic_floor_to_freezing_ratio",
)


def declared_liquid(chemistry):
    from dataclasses import replace

    return replace(
        chemistry,
        boiling_temperature=DECLARED_BOILING,
        freezing_temperature=DECLARED_FREEZING,
    )


def with_declared_liquid(run):
    from dataclasses import replace

    return replace(run, chemistry=declared_liquid(run.chemistry))


def test_k2_truth_conditions_cross_frozen_k15_boundary_and_seeded_observations_replay():
    chemistry = chemistry_from_coordinates(*TRUTH_COORDINATES)
    assert np.isclose(chemistry.k0_per_s, 1.2e9, rtol=0.0, atol=1.0e-6)
    assert np.isclose(chemistry.e_over_r_k, 8750.0, rtol=0.0, atol=1.0e-12)

    # Audit CAP-01: the frozen truth declares no liquid range, so the frozen
    # evaluation is refused on applicability ...
    with pytest.raises(InferenceAdmissibilityError, match="applicability"):
        evaluate_truth_predictions()

    # ... and the same truth, with a declared liquid range, still crosses the
    # boundary with everything this test has always asserted.
    liquid = declared_liquid(chemistry)
    adapter = CSTRInferenceForwardAdapter()
    predictions = {
        condition_id: adapter.evaluate(
            CONDITION_BY_ID[condition_id].build(liquid),
            observable_names=OBSERVABLE_NAMES,
            run_id_prefix=f"k2-truth-{condition_id}",
        )
        for condition_id in MULTI_CONDITION_IDS
    }
    assert tuple(predictions) == MULTI_CONDITION_IDS

    means: dict[str, Quantity] = {}
    for condition_id, prediction in predictions.items():
        admitted = require_admissible_numerical_prediction(prediction)
        assert ValidationLevel.NUMERICALLY_CONVERGED in admitted.attained_levels
        assert admitted.source_result.is_usable is True
        assert admitted.source_result.provenance is not None
        for observable_name in OBSERVABLE_NAMES:
            value = admitted.value(observable_name)
            assert isinstance(value, Quantity)
            value.magnitude_in(METRIC_UNITS[observable_name])
            means[f"{condition_id}:{observable_name}"] = value

    first = observation_set_from_truth_means(means, seed=PRIMARY_SEED)
    second = observation_set_from_truth_means(means, seed=PRIMARY_SEED)
    assert first.keys == second.keys
    assert [item.value.to_dict() for item in first.observations] == [
        item.value.to_dict() for item in second.observations
    ]
    assert all(item.sigma.magnitude > 0.0 for item in first.observations)
