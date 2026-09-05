from __future__ import annotations

import numpy as np
import pytest

from experiments.kinetics_k15.k15_config import (
    HOLDOUT,
    UNUSABLE_ENVELOPE_EXIT,
    USABLE_BUT_SEQUENCE_INVALID,
)
from src.engcore.domains.kinetics.cstr.inference import CSTRInferenceForwardAdapter
from src.engcore.domains.kinetics.cstr.problem import (
    CA_FINAL_METRIC,
    METRIC_UNITS,
    T_FINAL_METRIC,
)
from src.engcore.domains.kinetics.cstr.solver import solve_reactor
from src.engcore.inference import (
    AdmissibleNumericalPrediction,
    InferenceAdmissibilityError,
    require_admissible_numerical_prediction,
)
from src.engcore.scientific.results.validation import ValidationLevel
from src.engcore.scientific.units.quantity import Quantity


def test_shared_guard_refuses_unadmitted_values_and_bare_scientific_result():
    with pytest.raises(InferenceAdmissibilityError):
        require_admissible_numerical_prediction(np.array([1.0, 2.0]))
    with pytest.raises(InferenceAdmissibilityError):
        require_admissible_numerical_prediction({"T": 350.0})

    run = HOLDOUT.build()
    source = solve_reactor(run, run_id="k15-guard-bare-source")
    assert source.is_usable is True

    # The source has provenance and is usable, but its per-solve validation
    # intentionally cannot establish tolerance independence.
    assert ValidationLevel.NUMERICALLY_CONVERGED not in source.attained_levels
    with pytest.raises(InferenceAdmissibilityError):
        require_admissible_numerical_prediction(source)


def test_numerical_prediction_constructor_refuses_single_solve_validation():
    run = HOLDOUT.build()
    source = solve_reactor(run, run_id="k15-constructor-source")
    assert source.is_usable

    with pytest.raises(
        InferenceAdmissibilityError, match="NUMERICALLY_CONVERGED"
    ):
        AdmissibleNumericalPrediction(
            prediction_id="must-fail",
            domain="kinetics.cstr",
            adapter_id="test-domain-adapter",
            binding_ref=run.physics_fingerprint(),
            source_result=source,
            observable_names=(CA_FINAL_METRIC, T_FINAL_METRIC),
            # This is the critical negative control: the ordinary source report
            # has only per-solve evidence, not sequence-level convergence.
            sequence_validation=source.validation,
            verification_ref="not-a-sequence",
        )


def test_h1_confirmatory_holdout_is_admitted_with_units_provenance_and_sequence():
    run = HOLDOUT.build()
    prediction = CSTRInferenceForwardAdapter().evaluate(
        run,
        observable_names=(CA_FINAL_METRIC, T_FINAL_METRIC),
        run_id_prefix="k15-h1",
    )

    assert require_admissible_numerical_prediction(prediction) is prediction
    assert prediction.binding_ref == run.physics_fingerprint()
    assert prediction.source_result.is_usable
    assert prediction.source_result.provenance is not None
    assert (
        prediction.source_result.provenance.metadata["physics_fingerprint"]
        == run.physics_fingerprint()
    )
    assert ValidationLevel.NUMERICALLY_CONVERGED in prediction.attained_levels

    for name, value in prediction.values.items():
        assert isinstance(value, Quantity)
        # Conversion itself is the assertion: wrong dimensionality raises.
        value.magnitude_in(METRIC_UNITS[name])


def test_r7_usable_single_solve_is_rejected_without_sequence_validation():
    run = USABLE_BUT_SEQUENCE_INVALID.build()
    source = solve_reactor(run, run_id="k15-r7-single")

    # Frozen K1 fact that K1.5 is specifically designed not to over-read.
    assert source.is_usable is True

    with pytest.raises(
        InferenceAdmissibilityError, match="NUMERICALLY_CONVERGED"
    ):
        CSTRInferenceForwardAdapter().evaluate(
            run,
            observable_names=(CA_FINAL_METRIC, T_FINAL_METRIC),
            run_id_prefix="k15-r7",
        )


def test_r8_completed_but_domain_unusable_result_is_rejected():
    run = UNUSABLE_ENVELOPE_EXIT.build()
    source = solve_reactor(run, run_id="k15-r8-single")
    assert bool(source.values) is True
    assert source.is_usable is False

    with pytest.raises(InferenceAdmissibilityError, match="not scientifically usable"):
        CSTRInferenceForwardAdapter().evaluate(
            run,
            observable_names=(CA_FINAL_METRIC, T_FINAL_METRIC),
            run_id_prefix="k15-r8",
        )
