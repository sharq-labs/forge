"""Where a conductor's linear alpha(T) law stops holding, and who says so.

Four conditions on ``electrical.material.rated_linear_tcr_resistance``, each
with three tests — inside, outside, and with the material declaration that
would settle it withheld. Withholding must never buy a verdict: a conductor
whose datasheet nobody supplied is UNKNOWN, not fine.

The unrated ``electrical.material.linear_tcr_resistance`` is left exactly as it
was, and one test here holds it to that: it is a published record that existing
results were assessed against, and silently narrowing its domain would re-judge
them without their inputs, their solver or their numbers having changed.
"""

from __future__ import annotations

import pytest

from src.engcore.domains.electrical import material as mat
from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.scientific.errors import InvalidScientificProblem
from src.engcore.scientific.ir.problem import ScientificProblem
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.results.validation import ValidationOutcome
from src.engcore.scientific.solvers.protocol import ConvergenceState
from src.engcore.scientific.units.quantity import Quantity
from src.engcore.systems.electrothermal import coupled as cp

K = "kelvin"

#: Copper-like. The Debye temperature is copper's: 343 K, Kittel, *Introduction
#: to Solid State Physics*, 8th ed. (2005), Ch. 5, Table 1.
COPPER_LIMITS = mat.MaterialLimits(
    linearization_band=Quantity(100.0, K),
    maximum_operating_temperature=Quantity(450.0, K),
    debye_temperature=Quantity(343.0, K),
)

#: The operating point the tests assess at, unless they say otherwise: 340 K,
#: 46.85 K above the 293.15 K reference.
OPERATING = Quantity(340.0, K)


def limits(**overrides):
    fields = {
        "linearization_band": COPPER_LIMITS.linearization_band,
        "maximum_operating_temperature": COPPER_LIMITS.maximum_operating_temperature,
        "debye_temperature": COPPER_LIMITS.debye_temperature,
    }
    fields.update(overrides)
    return mat.MaterialLimits(**fields)


def conductor(declared=COPPER_LIMITS, *, alpha=0.00393, r_ref=10.0):
    return mat.TemperatureDependentConductor(
        component_id="R1",
        reference_resistance=Quantity(r_ref, "ohm"),
        temperature_coefficient=Quantity(alpha, "1/kelvin"),
        reference_temperature=Quantity(293.15, K),
        limits=declared,
    )


def assess(declared=COPPER_LIMITS, *, temperature=OPERATING, **kwargs):
    problem = mat.build_resistance_problem(conductor(declared, **kwargs))
    return mat.assess_rated_resistance_validity(problem, temperature)


def condition(name):
    return next(
        c
        for c in mat.RATED_LINEAR_TCR_MODEL.validity.conditions
        if c.name == name
    )


# =====================================================================
# The unrated claim is unchanged
# =====================================================================

def test_the_unrated_model_still_declares_exactly_the_two_conditions_it_had():
    """A published record is not narrowed underneath the results that cite it."""
    assert {c.name for c in mat.LINEAR_TCR_MODEL.validity.conditions} == {
        mat.TEMPERATURE,
        mat.REFERENCE_RESISTANCE,
    }
    assert mat.LINEAR_TCR_MODEL.version == "0.1.0"
    problem = mat.build_resistance_problem(conductor(mat.MaterialLimits()))
    assert (
        mat.assess_resistance_validity(problem, Quantity(300.0, K)).status
        is ValidityStatus.IN_DOMAIN
    )


def test_the_rated_model_is_a_separate_record_with_a_strictly_smaller_domain():
    unrated = {c.name for c in mat.LINEAR_TCR_MODEL.validity.conditions}
    rated = {c.name for c in mat.RATED_LINEAR_TCR_MODEL.validity.conditions}
    assert unrated < rated
    assert mat.RATED_LINEAR_TCR_MODEL.model_id != mat.LINEAR_TCR_MODEL.model_id
    # Same arithmetic, different claim: the realization says so explicitly.
    assert (
        mat.RATED_LINEAR_TCR_REALIZATION.formulation
        is mat.LINEAR_TCR_REALIZATION.formulation
    )


def test_a_conductor_with_no_declared_limits_is_unknown_under_the_rated_claim():
    """The point of the whole file, in one assertion."""
    assessment = assess(mat.MaterialLimits())
    assert assessment.status is ValidityStatus.UNKNOWN
    assert set(assessment.unknown) == {
        mat.LINEARIZATION_EXCURSION_RATIO,
        mat.OPERATING_TEMPERATURE_UTILIZATION,
        mat.REDUCED_DEBYE_TEMPERATURE,
    }
    assert assessment.violated == ()


def test_a_fully_declared_conductor_at_a_benign_temperature_is_in_domain():
    assessment = assess()
    assert assessment.status is ValidityStatus.IN_DOMAIN
    assert assessment.unknown == () and assessment.violated == ()
    assert set(assessment.satisfied) == {
        c.name for c in mat.RATED_LINEAR_TCR_MODEL.validity.conditions
    }


# =====================================================================
# Condition 1 — the linearization band
# =====================================================================

def test_linear_tcr_law_holds_within_the_materials_declared_linearization_band():
    """|340 - 293.15| = 46.85 K, under half of the declared 100 K band."""
    assessment = assess()
    assert mat.LINEARIZATION_EXCURSION_RATIO in assessment.satisfied
    ratio = mat.linearization_excursion_ratio(
        temperature=OPERATING,
        reference_temperature=Quantity(293.15, K),
        band=Quantity(100.0, K),
    )
    assert ratio.magnitude_in("dimensionless") == pytest.approx(0.4685, rel=1e-9)


def test_linear_tcr_law_is_rejected_beyond_the_materials_linearization_band():
    """The same excursion against a 10 K band: nearly five times over.

    The linear form is the first-order Taylor expansion of rho(T) about T_ref,
    so its truncation error grows with the excursion. A material that supports
    one coefficient over 10 K has said nothing about 47 K.
    """
    assessment = assess(limits(linearization_band=Quantity(10.0, K)))
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (mat.LINEARIZATION_EXCURSION_RATIO,)


def test_linearization_band_is_unknown_when_the_material_declares_none():
    assessment = assess(limits(linearization_band=None))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (mat.LINEARIZATION_EXCURSION_RATIO,)
    assert assessment.violated == ()


def test_the_linearization_budget_limit_is_a_named_constant_at_one():
    assert mat.LINEARIZATION_BUDGET_LIMIT.magnitude_in("dimensionless") == 1.0
    assert (
        condition(mat.LINEARIZATION_EXCURSION_RATIO).maximum
        == mat.LINEARIZATION_BUDGET_LIMIT
    )


# =====================================================================
# Condition 2 — the maximum operating temperature
# =====================================================================

def test_linear_tcr_law_holds_below_the_materials_maximum_operating_temperature():
    """340 K against a 450 K rating: three quarters of the way up."""
    assessment = assess()
    assert mat.OPERATING_TEMPERATURE_UTILIZATION in assessment.satisfied


def test_linear_tcr_law_is_rejected_above_the_materials_maximum_operating_temperature():
    """340 K against a 320 K rating.

    A hard limit rather than a modelling tolerance: past its rating the
    conductor is annealing or oxidising, and no coefficient describes a part
    that is no longer the part that was specified.
    """
    assessment = assess(limits(maximum_operating_temperature=Quantity(320.0, K)))
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (mat.OPERATING_TEMPERATURE_UTILIZATION,)


def test_maximum_operating_temperature_is_unknown_when_the_material_declares_none():
    assessment = assess(limits(maximum_operating_temperature=None))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (mat.OPERATING_TEMPERATURE_UTILIZATION,)
    assert assessment.violated == ()


def test_the_rating_utilization_is_a_ratio_of_two_absolute_temperatures():
    """So 'ratio reaches 1' is exactly 'T reaches T_max', with no offset error."""
    ratio = mat.operating_temperature_utilization(
        temperature=Quantity(450.0, K),
        maximum_temperature=Quantity(450.0, K),
    )
    assert ratio.magnitude_in("dimensionless") == pytest.approx(1.0, rel=1e-12)
    assert (
        condition(mat.OPERATING_TEMPERATURE_UTILIZATION).maximum
        == mat.OPERATING_TEMPERATURE_LIMIT
    )


# =====================================================================
# Condition 3 — the Bloch-Grueneisen low-temperature floor
# =====================================================================

def test_linear_tcr_law_holds_well_above_a_third_of_the_debye_temperature():
    """340 K against copper's 343 K theta_D: T/theta_D ~ 0.99, comfortably above."""
    assessment = assess()
    assert mat.REDUCED_DEBYE_TEMPERATURE in assessment.satisfied


def test_linear_tcr_law_is_rejected_below_a_third_of_the_debye_temperature():
    """A beryllium-like conductor at 300 K: theta_D = 1000 K gives T/theta_D = 0.30.

    Beryllium's Debye temperature is 1000 K (Kittel 8th ed., Ch. 5, Table 1),
    and it is a real conductor. Below roughly theta_D/3 the phonon population
    is no longer classical and the ideal resistivity goes as T^5 rather than T,
    so a single coefficient is describing the wrong curve — at a temperature
    that every other condition here calls unremarkable.
    """
    assessment = assess(
        limits(debye_temperature=Quantity(1000.0, K)),
        temperature=Quantity(300.0, K),
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (mat.REDUCED_DEBYE_TEMPERATURE,)


def test_debye_floor_is_unknown_when_the_material_declares_no_debye_temperature():
    assessment = assess(limits(debye_temperature=None))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (mat.REDUCED_DEBYE_TEMPERATURE,)
    assert assessment.violated == ()


def test_the_debye_floor_is_a_named_constant_and_says_it_is_a_convention():
    assert mat.BLOCH_GRUENEISEN_LINEAR_FLOOR.magnitude_in(
        "dimensionless"
    ) == pytest.approx(1.0 / 3.0, rel=1e-15)
    description = condition(mat.REDUCED_DEBYE_TEMPERATURE).description
    assert "Ashcroft" in description and "Kittel" in description


# =====================================================================
# Condition 4 — the linear form's own multiplier
# =====================================================================

def test_the_linear_multiplier_stays_positive_for_a_metal_being_warmed():
    assessment = assess()
    assert mat.LINEAR_RESISTANCE_RATIO in assessment.satisfied
    ratio = mat.linear_resistance_ratio(
        temperature=OPERATING,
        reference_temperature=Quantity(293.15, K),
        temperature_coefficient=Quantity(0.00393, "1/kelvin"),
    )
    assert ratio.magnitude_in("dimensionless") == pytest.approx(
        1.0 + 0.00393 * 46.85, rel=1e-12
    )


def test_the_linear_form_is_rejected_where_it_extrapolates_through_zero():
    """alpha = -0.02 /K at 400 K gives 1 + alpha dT = -1.14: a negative element.

    The solver's admissibility check catches this *after* producing a number.
    This condition catches it before, which is the difference between "was the
    result checked" and "was the model applicable".
    """
    assessment = assess(
        limits(linearization_band=Quantity(200.0, K)),
        temperature=Quantity(400.0, K),
        alpha=-0.02,
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (mat.LINEAR_RESISTANCE_RATIO,)


def test_the_linear_multiplier_is_unknown_when_no_temperature_is_supplied():
    """A temperature is a STATE, so it never arrives through the parameters."""
    problem = mat.build_resistance_problem(conductor())
    assessment = mat.assess_rated_resistance_validity(problem, None)
    assert assessment.status is ValidityStatus.UNKNOWN
    assert mat.LINEAR_RESISTANCE_RATIO in assessment.unknown
    assert assessment.violated == ()


def test_the_multiplier_bound_is_exactly_zero_and_strictly_exclusive():
    """No epsilon: a zero-resistance element is as inadmissible as a negative one."""
    bound = condition(mat.LINEAR_RESISTANCE_RATIO)
    assert bound.minimum == mat.MINIMUM_LINEAR_RESISTANCE_RATIO
    assert bound.minimum.magnitude_in("dimensionless") == 0.0
    assert bound.minimum_inclusive is False


# =====================================================================
# No condition can be bought by omission
# =====================================================================

@pytest.mark.parametrize(
    "removed",
    [
        {"linearization_band": None},
        {"maximum_operating_temperature": None},
        {"debye_temperature": None},
    ],
)
def test_removing_any_single_material_limit_never_yields_in_domain(removed):
    assert assess(limits(**removed)).status is not ValidityStatus.IN_DOMAIN


def test_the_inherited_temperature_range_still_binds_under_the_rated_claim():
    """Material limits narrow the declared range; they never widen it.

    A material rated to 800 K is still outside the 200-450 K span this
    repository declares the linear TCR form over at all.
    """
    assessment = assess(
        limits(
            maximum_operating_temperature=Quantity(800.0, K),
            linearization_band=Quantity(400.0, K),
        ),
        temperature=Quantity(600.0, K),
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert mat.TEMPERATURE in assessment.violated


# =====================================================================
# The declaration record and the problem it produces
# =====================================================================

def test_material_limits_round_trip_through_their_serialized_form():
    restored = mat.MaterialLimits.from_dict(COPPER_LIMITS.to_dict())
    assert restored == COPPER_LIMITS
    assert restored.to_dict() == COPPER_LIMITS.to_dict()
    empty = mat.MaterialLimits()
    assert mat.MaterialLimits.from_dict(empty.to_dict()) == empty
    assert empty.is_empty and not COPPER_LIMITS.is_empty


def test_material_limits_refuse_a_non_positive_or_wrongly_dimensioned_value():
    for field in (
        "linearization_band",
        "maximum_operating_temperature",
        "debye_temperature",
    ):
        with pytest.raises(InvalidScientificProblem):
            mat.MaterialLimits(**{field: Quantity(0.0, K)})
    with pytest.raises(Exception):
        mat.MaterialLimits(linearization_band=Quantity(10.0, "ohm"))
    with pytest.raises(InvalidScientificProblem):
        mat.MaterialLimits(linearization_band=100.0)


def test_a_band_declared_on_an_affine_scale_is_refused_not_silently_converted():
    """A 50 degC *band* is not 323.15 K, and no dimension check would notice.

    The band is a difference carried in a type that means an absolute value, so
    Celsius and Fahrenheit are refused for it while kelvin and the delta scales
    are accepted. The other two limits are states and keep their zeros.
    """
    with pytest.raises(InvalidScientificProblem):
        mat.MaterialLimits(linearization_band=Quantity(50.0, "degC"))
    assert mat.MaterialLimits(
        linearization_band=Quantity(50.0, "delta_degC")
    ).linearization_band.magnitude_in(K) == pytest.approx(50.0, rel=1e-12)
    # a maximum operating temperature is a state, so degC is legitimate there
    assert mat.MaterialLimits(
        maximum_operating_temperature=Quantity(176.85, "degC")
    ).maximum_operating_temperature.magnitude_in(K) == pytest.approx(
        450.0, rel=1e-9
    )


def test_a_conductor_that_declares_no_limits_builds_the_problem_it_always_did():
    """Adding an optional record did not widen the record for callers who declined."""
    problem = mat.build_resistance_problem(conductor(mat.MaterialLimits()))
    assert [p.name for p in problem.parameters] == [
        mat.REFERENCE_RESISTANCE,
        mat.TEMPERATURE_COEFFICIENT,
        mat.REFERENCE_TEMPERATURE,
    ]
    assert [m.model_id for m in problem.models] == [mat.LINEAR_TCR_MODEL.model_id]


def test_a_conductor_that_declares_limits_states_the_stronger_claim_too():
    problem = mat.build_resistance_problem(conductor())
    names = {p.name for p in problem.parameters}
    assert {
        mat.LINEARIZATION_BAND,
        mat.MAXIMUM_OPERATING_TEMPERATURE,
        mat.DEBYE_TEMPERATURE,
    } <= names
    assert [m.model_id for m in problem.models] == [
        mat.LINEAR_TCR_MODEL.model_id,
        mat.RATED_LINEAR_TCR_MODEL.model_id,
    ]
    # Both models bind to it; neither is satisfied by the optional inputs alone.
    assert mat.LINEAR_TCR_MODEL.check_against(problem).is_satisfied
    assert mat.RATED_LINEAR_TCR_MODEL.check_against(problem).is_satisfied


def test_the_rated_problem_survives_serialization_with_its_verdict_intact():
    problem = mat.build_resistance_problem(conductor())
    restored = ScientificProblem.from_dict(problem.to_dict())
    assert restored.to_dict() == problem.to_dict()
    assert (
        mat.assess_rated_resistance_validity(restored, OPERATING).status
        is ValidityStatus.IN_DOMAIN
    )


def test_a_problem_that_contradicts_the_bound_conductors_limits_is_refused():
    solver = mat.ResistancePropertySolver()
    mismatched = mat.build_resistance_problem(
        conductor(limits(maximum_operating_temperature=Quantity(500.0, K)))
    )
    solver.bind_conductor(
        conductor(), mismatched.problem_id, temperature=OPERATING
    )
    with pytest.raises(InvalidScientificProblem):
        solver.prepare(mismatched)


# =====================================================================
# Integration — the coupled run is untouched by any of this
# =====================================================================

def body():

    return lump.ThermalBody(
        body_id="R1",
        heat_capacity=Quantity(2.5, "joule/kelvin"),
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
        ambient_temperature=Quantity(300.0, K),
        initial_temperature=Quantity(300.0, K),
        duration=Quantity(120.0, "second"),
    )


def run_coupled(declared, run_id):
    system = cp.CoupledElectroThermalSystem(
        stages=(cp.CoupledStage(conductor(declared), body()),),
        source_voltage=Quantity(5.0, "volt"),
    )
    problems = cp.coupled_problems(
        system,
        {s.component_id: s.conductor.reference_resistance for s in system.stages},
    )
    dependencies = cp.coupled_dependencies(system, problems)
    plan = cp.nominal_plan(
        system,
        dependencies,
        seed=Quantity(300.0, K),
        tolerance=Quantity(1e-6, K),
        max_iterations=50,
    )
    return cp.run_fixed_point_coupling(system, plan, run_id=run_id), problems


#: The preregistered CASE A trace of the electro-thermal vertical milestone,
#: reproduced rather than recomputed.
CASE_A_TEMPERATURE = 338.577018
CASE_A_RESISTANCE = 11.785282
CASE_A_POWER = 2.121290
CASE_A_ITERATIONS = 10


def _assert_case_a_trace(run, problems):

    electrical, prop, thermal = (p.problem_id for p in problems)
    (final_temperature,) = run.final_values.values()
    assert final_temperature.magnitude_in(K) == pytest.approx(
        CASE_A_TEMPERATURE, abs=1e-6
    )
    assert run.final.result_for(prop).value(
        mat.RESISTANCE_METRIC
    ).magnitude_in("ohm") == pytest.approx(CASE_A_RESISTANCE, abs=1e-6)
    assert run.final.result_for(electrical).value(
        "resistor_power:R1"
    ).magnitude_in("watt") == pytest.approx(CASE_A_POWER, abs=1e-6)
    assert run.final.result_for(thermal).value(
        "final_temperature"
    ).magnitude_in(K) == pytest.approx(CASE_A_TEMPERATURE, abs=1e-6)


def test_material_limits_leave_the_coupled_run_numerically_identical():
    """Three independent claims about one run, asserted one at a time.

    1. **Numerical convergence** — the sub-solves report what they always did
       and reproduce the preregistered CASE A trace.
    2. **Coupling convergence** — the same ten iterations to the same
       tolerance.
    3. **Scientific validity** — IN_DOMAIN under the rated claim, which is a
       third verdict and follows from neither of the first two.
    """
    run, problems = run_coupled(COPPER_LIMITS, "material-in-domain")

    # 1. numerical convergence
    assert {r.convergence for i in run.iterations for r in i.results} == {
        ConvergenceState.CONVERGED,
        ConvergenceState.NOT_APPLICABLE,
    }
    _assert_case_a_trace(run, problems)

    # 2. coupling convergence
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert run.criterion_met is True
    assert run.iterations_run == CASE_A_ITERATIONS
    assert run.final_iterate_change.magnitude_in(K) <= 1e-6

    # 3. scientific validity
    (temperature,) = run.final_values.values()
    assessment = mat.assess_rated_resistance_validity(problems[1], temperature)
    assert assessment.status is ValidityStatus.IN_DOMAIN

    # The derived multiplier is the solved resistance ratio, to the coupling
    # tolerance: the condition is stated over the same number the solver used.
    context = mat.rated_resistance_validity_context(problems[1], temperature)
    assert context[mat.LINEAR_RESISTANCE_RATIO].magnitude_in(
        "dimensionless"
    ) == pytest.approx(CASE_A_RESISTANCE / 10.0, rel=1e-6)


def test_a_coupled_run_can_converge_and_still_leave_the_material_band():
    """The same run with the declared band narrowed to 20 K.

    A band is not in the balance, so nothing numerical moves: the trace, the
    sub-solve convergence and the coupling outcome are the assertions above.
    Only the validity verdict changes — a converged coupling of converged
    solves of a model outside the range its material supports.
    """
    baseline, _ = run_coupled(COPPER_LIMITS, "material-baseline")
    run, problems = run_coupled(
        limits(linearization_band=Quantity(20.0, K)), "material-outside"
    )

    # 1. numerical convergence — unchanged
    assert {r.convergence for i in run.iterations for r in i.results} == {
        ConvergenceState.CONVERGED,
        ConvergenceState.NOT_APPLICABLE,
    }
    _assert_case_a_trace(run, problems)
    assert run.final_values == baseline.final_values

    # 2. coupling convergence — unchanged
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert run.iterations_run == CASE_A_ITERATIONS

    # 3. validity — and only validity — has moved
    (temperature,) = run.final_values.values()
    assessment = mat.assess_rated_resistance_validity(problems[1], temperature)
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (mat.LINEARIZATION_EXCURSION_RATIO,)

    # and the unrated claim, whose domain did not change, still says IN_DOMAIN
    assert (
        mat.assess_resistance_validity(problems[1], temperature).status
        is ValidityStatus.IN_DOMAIN
    )
    # no sub-result was downgraded on account of the narrower claim
    for iteration in run.iterations:
        for result in iteration.results:
            assert result.validation.status is not ValidationOutcome.FAIL
