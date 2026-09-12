"""An admitted forward row is an invariant of the type, not of its factory.

TB-2 of the trust-boundary hardening sprint.

``AdmittedForwardRow`` is what inference consumes after K1.5 admission: the
compact numbers ``gaussian_grid_posterior`` turns into a likelihood. The
admission rule lived in ``from_predictions``, and the public constructor took
the finished fields -- ``values``, ``admission_refs``, ``admissible=True`` --
directly. ``AdmittedForwardRow((0.5,), keys, (1.0,), ("forged",))`` was an
admitted row built from a number no prediction produced, and
``AdmittedForwardTable.from_rows`` and the posterior accepted it; ``from_rows``
also accepted any object with the right attribute names.

The constructor IS the admission gate now: its only inputs are an observation
set and ``AdmissibleNumericalPrediction`` records, and the numbers are read out
of those. A rejected row, which asserts nothing, is still built by ``rejected``.
"""

from __future__ import annotations

import copy
import dataclasses
import pickle
from types import SimpleNamespace

import numpy as np
import pytest

from engcore.inference.admissibility import (
    AdmissibleNumericalPrediction,
    InferenceAdmissibilityError,
)
from engcore.inference.grid import (
    AdmittedForwardRow,
    AdmittedForwardTable,
    GaussianObservation,
    InferenceProblemError,
    ObservationSet,
    gaussian_grid_posterior,
)
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from engcore.scientific.solvers.protocol import ConvergenceState, SolverIdentity
from engcore.scientific.units.quantity import Quantity

MODEL = ("synthetic.tb2_response", "1.0.0")


def _source(result_id: str, value: float) -> ScientificResult:
    return ScientificResult(
        result_id=result_id,
        problem_id="tb2_problem",
        values={"y": Quantity(value, "kelvin")},
        models=(MODEL,),
        validity_not_assessed={
            MODEL[0]: "a synthetic fixture: nothing asked whether the model applied"
        },
        solver=SolverIdentity("algebraic", "1.0.0"),
        convergence=ConvergenceState.NOT_APPLICABLE,
        validation=ValidationReport(
            checks=(
                ValidationCheck(
                    name="dimensional_consistency",
                    outcome=ValidationOutcome.PASS,
                    establishes=ValidationLevel.DIMENSIONALLY_VALID,
                    evidence=("fixture: kelvin declared by the fixture",),
                ),
            )
        ),
        uncertainty={"y": Uncertainty.unknown("not evaluated in this fixture")},
        assumptions=("synthetic fixture",),
        provenance=ProvenanceRecord(
            run_id=f"{result_id}-run",
            software_version="tb2-fixture",
            git_commit="0" * 40,
            models=(MODEL,),
            solvers=(("algebraic", "1.0.0"),),
            inputs={"x": Quantity(1.0, "kelvin")},
            assumptions=("synthetic fixture",),
            tolerances={"rtol": 1e-9},
            environment={"python": "3.x"},
            timestamp="2026-01-01T00:00:00+00:00",
        ),
    )


SEQUENCE = ValidationReport(
    checks=(
        ValidationCheck(
            name="tolerance_ladder",
            outcome=ValidationOutcome.PASS,
            establishes=ValidationLevel.NUMERICALLY_CONVERGED,
            residual=1e-10,
            tolerance=1e-8,
            evidence=("fixture: a synthetic tolerance ladder",),
        ),
    )
)


def _prediction(prediction_id: str = "tb2-pred", value: float = 1.25):
    return AdmissibleNumericalPrediction(
        prediction_id=prediction_id,
        domain="synthetic",
        adapter_id="tb2-adapter",
        binding_ref=f"binding:{prediction_id}",
        source_result=_source(f"{prediction_id}-source", value),
        observable_names=("y",),
        sequence_validation=SEQUENCE,
        verification_ref=f"verification:{prediction_id}",
    )


OBSERVATIONS = ObservationSet(
    observations=(
        GaussianObservation(
            condition_id="c",
            observable_name="y",
            value=Quantity(1.0, "kelvin"),
            sigma=Quantity(0.2, "kelvin"),
            source_ref="tb2",
        ),
    ),
    dataset_id="tb2",
)


# ---- 1. the official path still admits ------------------------------------
def test_the_official_admission_path_still_produces_an_admitted_row():
    prediction = _prediction()
    row = AdmittedForwardRow.from_predictions((0.5,), OBSERVATIONS, {"c": prediction})

    assert row.admissible is True
    assert row.coordinates == (0.5,)
    assert row.observation_keys == ("c:y",)
    assert row.values == (1.25,)
    # The leading field is the ADMISSION ROUTE, added when the analytic route
    # joined the numerical one. It is first because it is the strongest thing
    # the ref says: "numerical" means this value carries sequence-level
    # convergence evidence, "analytic" means it carries the declared
    # applicability of a closed form. A reader auditing what backs a number
    # needs that before the ids, and a ref that omitted it would make the two
    # routes indistinguishable after the fact.
    assert row.admission_refs == (
        "numerical|tb2-pred|verification:tb2-pred|binding:tb2-pred",
    )
    assert row.rejection_reason == ""
    # The constructor is the same gate under its own name.
    assert AdmittedForwardRow((0.5,), OBSERVATIONS, {"c": prediction}) == row


def test_admitted_rows_still_reach_the_posterior_unchanged():
    rows = (
        AdmittedForwardRow.from_predictions((0.0,), OBSERVATIONS, {"c": _prediction("p0", 0.0)}),
        AdmittedForwardRow.from_predictions((1.0,), OBSERVATIONS, {"c": _prediction("p1", 1.0)}),
        AdmittedForwardRow.from_predictions((2.0,), OBSERVATIONS, {"c": _prediction("p2", 2.0)}),
        AdmittedForwardRow.rejected((3.0,), OBSERVATIONS, "not admitted"),
    )
    table = AdmittedForwardTable.from_rows(("theta",), OBSERVATIONS, rows)
    posterior = gaussian_grid_posterior(table, OBSERVATIONS)

    assert table.admissible_mask.tolist() == [True, True, True, False]
    assert table.values[:3, 0].tolist() == [0.0, 1.0, 2.0]
    assert int(np.argmax(posterior.weights)) == 1
    assert posterior.weights[3] == 0.0
    assert abs(float(posterior.weights.sum()) - 1.0) <= 1e-12


# ---- 2/3. direct construction cannot claim admission ------------------------
def test_the_field_level_constructor_that_forged_admission_is_gone():
    """The reproduced bypass, verbatim: finished fields and no prediction."""
    with pytest.raises(TypeError):
        AdmittedForwardRow(
            coordinates=(0.5,),
            observation_keys=OBSERVATIONS.keys,
            values=(1.0,),
            admission_refs=("forged",),
        )
    with pytest.raises(TypeError):
        AdmittedForwardRow((0.5,), OBSERVATIONS.keys, (1.0,), ("forged",), True, "")


@pytest.mark.parametrize(
    "stand_in",
    [
        {"y": 1.0},
        1.0,
        np.array([1.0]),
        "tb2-pred",
        SimpleNamespace(
            prediction_id="duck",
            verification_ref="v",
            binding_ref="b",
            attained_levels=frozenset({ValidationLevel.NUMERICALLY_CONVERGED}),
            value=lambda name: Quantity(1.0, "kelvin"),
        ),
    ],
    ids=["mapping", "float", "array", "string", "duck-prediction"],
)
def test_arbitrary_finite_numbers_cannot_claim_admission(stand_in):
    with pytest.raises(InferenceAdmissibilityError):
        AdmittedForwardRow((0.5,), OBSERVATIONS, {"c": stand_in})


def test_a_bare_scientific_result_cannot_claim_admission():
    source = _prediction().source_result
    assert source.is_usable
    with pytest.raises(InferenceAdmissibilityError):
        AdmittedForwardRow((0.5,), OBSERVATIONS, {"c": source})


def test_a_missing_or_unadmitted_observable_cannot_be_filled_in():
    with pytest.raises(InferenceAdmissibilityError, match="missing admitted prediction"):
        AdmittedForwardRow((0.5,), OBSERVATIONS, {})
    other = ObservationSet(
        observations=(
            GaussianObservation("c", "z", Quantity(1.0, "kelvin"), Quantity(0.2, "kelvin"), "tb2"),
        ),
        dataset_id="tb2-other",
    )
    with pytest.raises(InferenceAdmissibilityError, match="was not admitted"):
        AdmittedForwardRow((0.5,), other, {"c": _prediction()})


def test_the_observations_must_be_an_observation_set():
    with pytest.raises(InferenceProblemError, match="ObservationSet"):
        AdmittedForwardRow((0.5,), ("c:y",), {"c": _prediction()})
    with pytest.raises(InferenceProblemError, match="ObservationSet"):
        AdmittedForwardRow.rejected((0.5,), ("c:y",), "no")


def test_an_admitted_row_cannot_be_edited_into_a_different_one():
    row = AdmittedForwardRow.from_predictions((0.5,), OBSERVATIONS, {"c": _prediction()})
    with pytest.raises(TypeError):
        dataclasses.replace(row, values=(99.0,))
    if hasattr(copy, "replace"):
        with pytest.raises(TypeError):
            copy.replace(row, values=(99.0,))
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.values = (99.0,)  # type: ignore[misc]


def test_an_admitted_row_cannot_be_subclassed_around_its_gate():
    with pytest.raises(TypeError, match="subclass"):

        class _Lenient(AdmittedForwardRow):  # noqa: F841 - the definition is the test
            def __init__(self, *args, **kwargs):
                pass


def test_a_rejected_row_is_still_constructible_and_is_never_admitted():
    row = AdmittedForwardRow.rejected((0.5,), OBSERVATIONS, "  ")
    assert row.admissible is False
    assert row.admission_refs == ()
    assert row.values == (0.0,)
    assert row.rejection_reason == "forward prediction was not scientifically admissible"


# ---- 4. downstream inference cannot receive an unadmitted row ---------------
def test_from_rows_refuses_anything_that_is_not_an_admitted_forward_row():
    duck = SimpleNamespace(
        coordinates=(0.5,),
        observation_keys=OBSERVATIONS.keys,
        values=(1.0,),
        admission_refs=("duck",),
        admissible=True,
        rejection_reason="",
    )
    with pytest.raises(InferenceAdmissibilityError, match="AdmittedForwardRow"):
        AdmittedForwardTable.from_rows(("theta",), OBSERVATIONS, (duck,))


def test_a_table_row_marked_admitted_must_carry_its_admission_records():
    """The table is also rebuilt from audited caches, so it cannot re-run
    admission -- but a row marked admitted with no admission record behind each
    of its values is an absence of evidence, and is refused."""
    base = dict(
        parameter_names=("theta",),
        observation_keys=OBSERVATIONS.keys,
        points=np.asarray([[0.5], [1.5]]),
        values=np.asarray([[1.0], [0.0]]),
        rejection_reasons=("", "not admitted"),
    )
    with pytest.raises(InferenceProblemError, match="admission record"):
        AdmittedForwardTable(
            **base, admissible_mask=np.asarray([True, False]), admission_refs=((), ())
        )
    with pytest.raises(InferenceProblemError, match="admission record"):
        AdmittedForwardTable(
            **base,
            admissible_mask=np.asarray([True, False]),
            admission_refs=(("  ",), ()),
        )
    with pytest.raises(InferenceProblemError, match="admission record"):
        AdmittedForwardTable(
            parameter_names=("theta",),
            observation_keys=("c:y", "c:z"),
            points=np.asarray([[0.5], [1.5]]),
            values=np.asarray([[1.0, 2.0], [0.0, 0.0]]),
            admissible_mask=np.asarray([True, False]),
            admission_refs=(("only-one",), ()),
            rejection_reasons=("", "not admitted"),
        )
    accepted = AdmittedForwardTable(
        **base, admissible_mask=np.asarray([True, False]), admission_refs=(("a",), ())
    )
    assert accepted.admissible_mask.tolist() == [True, False]


# ---- 5. equality, hashing and transport -------------------------------------
def test_equality_hashing_and_pickling_are_preserved():
    prediction = _prediction()
    first = AdmittedForwardRow.from_predictions((0.5,), OBSERVATIONS, {"c": prediction})
    second = AdmittedForwardRow.from_predictions((0.5,), OBSERVATIONS, {"c": prediction})
    moved = AdmittedForwardRow.from_predictions((0.75,), OBSERVATIONS, {"c": prediction})

    assert first == second and hash(first) == hash(second)
    assert first != moved
    restored = pickle.loads(pickle.dumps(first))
    assert restored == first and restored.admissible is True
    assert copy.deepcopy(first) == first
    rejected = AdmittedForwardRow.rejected((0.5,), OBSERVATIONS, "no")
    assert pickle.loads(pickle.dumps(rejected)) == rejected
    assert rejected != first


def test_the_row_stays_compact_and_keeps_no_prediction():
    row = AdmittedForwardRow.from_predictions((0.5,), OBSERVATIONS, {"c": _prediction()})
    assert set(vars(row)) == {f.name for f in dataclasses.fields(AdmittedForwardRow)}
    assert set(vars(row)) == {
        "coordinates", "observation_keys", "values",
        "admission_refs", "admissible", "rejection_reason",
    }
