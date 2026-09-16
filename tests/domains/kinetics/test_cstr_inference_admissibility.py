from __future__ import annotations

import numpy as np
import pytest

from experiments.kinetics_k15.k15_config import (
    HOLDOUT,
    UNUSABLE_ENVELOPE_EXIT,
    USABLE_BUT_SEQUENCE_INVALID,
)
from engcore.domains.kinetics.cstr.inference import CSTRInferenceForwardAdapter
from engcore.domains.kinetics.cstr.problem import (
    CSTR_MODEL,
    CA_FINAL_METRIC,
    METRIC_UNITS,
    T_FINAL_METRIC,
)
from engcore.domains.kinetics.cstr.solver import solve_reactor
from engcore.inference import (
    AdmissibleNumericalPrediction,
    InferenceAdmissibilityError,
    require_admissible_numerical_prediction,
)
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity
from engcore.domains.kinetics.cstr.fluids import SEBORG_TEXTBOOK_LIQUID, declare_fluid


#: Audit CAP-01, lead decision. The CSTR's single-liquid-phase conditions read
#: the fluid's own boiling and freezing temperatures and are UNKNOWN until they
#: are declared, so the frozen K-series code -- which declares none -- is
#: refused on applicability. The textbook liquid's real range is declared once,
#: in the domain (``engcore.domains.kinetics.cstr.fluids.SEBORG_TEXTBOOK_LIQUID``:
#: a dilute aqueous liquid at an assumed 101.325 kPa, 273.15-373.124 K), and a
#: solved run is assessed at the temperatures it actually reached. Runs that
#: stay liquid are admitted; runs that truly boil stay refused.
PHASE_CONDITIONS = (
    "declared_temperature_to_boiling_ratio",
    "reachable_maximum_to_boiling_ratio",
    "reachable_minimum_to_freezing_ratio",
)


def declared_liquid(chemistry):
    return declare_fluid(chemistry, SEBORG_TEXTBOOK_LIQUID)


def with_declared_liquid(run):
    from dataclasses import replace

    return replace(run, chemistry=declared_liquid(run.chemistry))


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
    # The textbook liquid declared: H1 stays liquid (peak 317.8 K), so the
    # applicability gate is passed and the gate this negative control is
    # about -- sequence-level convergence -- is the one that refuses.
    run = with_declared_liquid(HOLDOUT.build())
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


def test_frozen_h1_without_a_declared_liquid_range_is_refused_on_applicability():
    """Audit CAP-01: the preregistered H1 declares no boiling or freezing point.

    Its CSTR assessment is therefore UNKNOWN on the three liquid-phase
    conditions, and a prediction from a model not shown to apply is not
    admitted -- the boundary's own rule, now reached by this run.
    """
    run = HOLDOUT.build()
    assessment = run.validity_context().assess(CSTR_MODEL)
    assert set(PHASE_CONDITIONS) <= set(assessment.unknown)
    with pytest.raises(InferenceAdmissibilityError, match="applicability"):
        CSTRInferenceForwardAdapter().evaluate(
            run,
            observable_names=(CA_FINAL_METRIC, T_FINAL_METRIC),
            run_id_prefix="k15-h1-undeclared",
        )


def test_h1_is_refused_before_a_solve_and_admitted_on_the_states_it_reached():
    """The invariant ceiling (559 K) is above boiling; the run peaks at 317.8 K.

    Declaration-only, the reachable-maximum condition is asked at the ceiling
    and is violated. On the solved result it is asked at the realised peak and
    is satisfied, which is what lets a run that truly stays liquid through.
    """
    run = with_declared_liquid(HOLDOUT.build())
    before = run.validity_context().assess(CSTR_MODEL)
    assert "reachable_maximum_to_boiling_ratio" in before.violated
    solved = solve_reactor(run, run_id="k15-h1-realised")
    after = solved.validity_of(CSTR_MODEL.model_id)
    assert set(PHASE_CONDITIONS) <= set(after.satisfied)


def test_h1_confirmatory_holdout_is_admitted_with_units_provenance_and_sequence():
    run = with_declared_liquid(HOLDOUT.build())
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
