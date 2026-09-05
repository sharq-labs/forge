"""What the DC domain's idealisations cost, once the components are rated.

Four conditions across the three element models, each with three tests —
inside, outside, and with the rating withheld. Each condition is the direct
falsification of an assumption the model already states in words: "unlimited
current compliance", "unlimited compliance voltage", and, for the resistor, an
element whose dissipation nobody bounded.

A withheld rating is UNKNOWN and never satisfied. An undeclared limit is not an
absent one — it is a limit nobody told us about.
"""

from __future__ import annotations

import pytest

from src.engcore.domains.electrical.dc import (
    DCCircuit,
    DCCurrentSource,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
    build_dc_problem,
    solve_circuit,
)
from src.engcore.domains.electrical.dc.models import (
    COMPLIANCE_VOLTAGE_UTILIZATION,
    DISSIPATED_POWER_UTILIZATION,
    IDEAL_CURRENT_SOURCE_MODEL,
    IDEAL_VOLTAGE_SOURCE_MODEL,
    NO_DERATING,
    RATING_UTILIZATION_LIMIT,
    RESISTOR_OHM_MODEL,
    SOURCE_CURRENT_UTILIZATION,
    WORKING_VOLTAGE_UTILIZATION,
    ComponentRating,
    assess_current_source_validity,
    assess_resistor_validity,
    assess_voltage_source_validity,
)
from src.engcore.domains.electrical.dc.problem import (
    current_source_relation_problem,
    resistor_relation_problem,
    voltage_source_relation_problem,
)
from src.engcore.domains.electrical import material as mat
from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.scientific.errors import InvalidScientificProblem
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.results.validation import ValidationOutcome
from src.engcore.scientific.solvers.protocol import ConvergenceState
from src.engcore.scientific.units.quantity import Quantity
from src.engcore.systems.electrothermal import coupled as cp

GND = ElectricalNode("gnd", is_reference=True)

#: A quarter-watt, 200 V element — an ordinary through-hole resistor. Both
#: numbers come from the same class of datasheet and neither implies the other.
QUARTER_WATT = ComponentRating(
    rated_power=Quantity(0.25, "watt"),
    maximum_working_voltage=Quantity(200.0, "volt"),
)

RESISTOR = Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm"))
VOLTAGE_SOURCE = DCVoltageSource("V1", "n1", "gnd", Quantity(10.0, "volt"))
CURRENT_SOURCE = DCCurrentSource("I1", "gnd", "n1", Quantity(1.0, "milliampere"))


def resistor_condition(name):
    return next(
        c for c in RESISTOR_OHM_MODEL.validity.conditions if c.name == name
    )


# =====================================================================
# Condition 1 — the dissipation ceiling
# =====================================================================

def test_resistor_model_accepts_an_element_inside_its_rated_dissipation():
    """0.1 W in a quarter-watt part: 40 % of the rating."""
    assessment = assess_resistor_validity(
        resistor_relation_problem(RESISTOR),
        rating=QUARTER_WATT,
        dissipated_power=Quantity(0.1, "watt"),
        voltage_across=Quantity(10.0, "volt"),
    )
    assert assessment.status is ValidityStatus.IN_DOMAIN
    assert DISSIPATED_POWER_UTILIZATION in assessment.satisfied


def test_resistor_model_rejects_an_element_beyond_its_rated_dissipation():
    """0.5 W in a quarter-watt part: twice the rating.

    The model's own assumption list says "temperature-independent resistance".
    That is the first thing an element loses when it is run at twice its
    rating, which is why the ceiling belongs to this model's validity rather
    than to somebody's checklist.
    """
    assessment = assess_resistor_validity(
        resistor_relation_problem(RESISTOR),
        rating=QUARTER_WATT,
        dissipated_power=Quantity(0.5, "watt"),
        voltage_across=Quantity(10.0, "volt"),
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (DISSIPATED_POWER_UTILIZATION,)


def test_dissipation_ceiling_is_unknown_when_no_rated_power_is_declared():
    """An unrated part is not an unlimited part."""
    assessment = assess_resistor_validity(
        resistor_relation_problem(RESISTOR),
        rating=ComponentRating(maximum_working_voltage=Quantity(200.0, "volt")),
        dissipated_power=Quantity(0.5, "watt"),
        voltage_across=Quantity(10.0, "volt"),
    )
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (DISSIPATED_POWER_UTILIZATION,)
    assert assessment.violated == ()


def test_a_derating_policy_shrinks_the_usable_fraction_of_the_rating():
    """0.2 W is 80 % of a quarter watt, and 160 % of a half-derated one.

    The derating factor is a declared input rather than a number folded into
    the threshold, so the same operating point can be inside one study's policy
    and outside another's without either study editing a constant.
    """
    problem = resistor_relation_problem(RESISTOR)
    full = assess_resistor_validity(
        problem, rating=QUARTER_WATT, dissipated_power=Quantity(0.2, "watt")
    )
    derated = assess_resistor_validity(
        problem,
        rating=ComponentRating(
            rated_power=Quantity(0.25, "watt"), derating_factor=0.5
        ),
        dissipated_power=Quantity(0.2, "watt"),
    )
    assert DISSIPATED_POWER_UTILIZATION in full.satisfied
    assert derated.violated == (DISSIPATED_POWER_UTILIZATION,)


def test_the_utilization_limit_is_a_named_constant_at_one():
    assert RATING_UTILIZATION_LIMIT.magnitude_in("dimensionless") == 1.0
    assert NO_DERATING == 1.0
    assert (
        resistor_condition(DISSIPATED_POWER_UTILIZATION).maximum
        == RATING_UTILIZATION_LIMIT
    )
    assert "60115" in resistor_condition(DISSIPATED_POWER_UTILIZATION).description


# =====================================================================
# Condition 2 — the working-voltage ceiling
# =====================================================================

def test_resistor_model_accepts_an_element_inside_its_working_voltage():
    assessment = assess_resistor_validity(
        resistor_relation_problem(RESISTOR),
        rating=QUARTER_WATT,
        dissipated_power=Quantity(0.1, "watt"),
        voltage_across=Quantity(10.0, "volt"),
    )
    assert WORKING_VOLTAGE_UTILIZATION in assessment.satisfied


def test_resistor_model_rejects_an_element_beyond_its_working_voltage():
    """A high-value element breaks down across its body long before it heats.

    250 V across a 200 V part, at a dissipation of 0.0625 W — a quarter of the
    power rating. The two limits are independent and this is the case that
    proves it: the power condition passes while the voltage condition fails.
    """
    assessment = assess_resistor_validity(
        resistor_relation_problem(Resistor("R1", "n1", "gnd", Quantity(1.0, "Mohm"))),
        rating=QUARTER_WATT,
        dissipated_power=Quantity(0.0625, "watt"),
        voltage_across=Quantity(250.0, "volt"),
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (WORKING_VOLTAGE_UTILIZATION,)
    assert DISSIPATED_POWER_UTILIZATION in assessment.satisfied


def test_working_voltage_ceiling_is_unknown_when_no_voltage_rating_is_declared():
    assessment = assess_resistor_validity(
        resistor_relation_problem(RESISTOR),
        rating=ComponentRating(rated_power=Quantity(0.25, "watt")),
        dissipated_power=Quantity(0.1, "watt"),
        voltage_across=Quantity(250.0, "volt"),
    )
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (WORKING_VOLTAGE_UTILIZATION,)
    assert assessment.violated == ()


def test_a_resistor_with_no_rating_at_all_is_unknown_on_both_counts():
    """The gap this closes: a positive resistance proved nothing about the part."""
    assessment = assess_resistor_validity(resistor_relation_problem(RESISTOR))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert set(assessment.unknown) == {
        DISSIPATED_POWER_UTILIZATION,
        WORKING_VOLTAGE_UTILIZATION,
    }
    assert assessment.satisfied == ("resistance",)


# =====================================================================
# Condition 3 — the voltage source's current limit
# =====================================================================

def test_voltage_source_model_accepts_a_load_inside_its_current_rating():
    assessment = assess_voltage_source_validity(
        voltage_source_relation_problem(VOLTAGE_SOURCE),
        rating=ComponentRating(maximum_current=Quantity(1.0, "ampere")),
        source_current=Quantity(0.5, "ampere"),
    )
    assert assessment.status is ValidityStatus.IN_DOMAIN
    assert assessment.satisfied == (SOURCE_CURRENT_UTILIZATION,)


def test_voltage_source_model_rejects_a_load_beyond_its_current_rating():
    """Twice the rated current: past its limit a real supply stops imposing V.

    The model's declared assumption is *unlimited* current compliance. No
    supply has it, and above the limit the terminal voltage is set by the
    fold-back or the drop-out, not by the constant this model asserts.
    """
    assessment = assess_voltage_source_validity(
        voltage_source_relation_problem(VOLTAGE_SOURCE),
        rating=ComponentRating(maximum_current=Quantity(1.0, "ampere")),
        source_current=Quantity(2.0, "ampere"),
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (SOURCE_CURRENT_UTILIZATION,)


def test_source_current_limit_is_unknown_when_no_current_rating_is_declared():
    assessment = assess_voltage_source_validity(
        voltage_source_relation_problem(VOLTAGE_SOURCE),
        source_current=Quantity(2.0, "ampere"),
    )
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (SOURCE_CURRENT_UTILIZATION,)
    assert assessment.violated == ()


def test_a_sign_on_the_current_is_a_direction_and_not_a_smaller_load():
    """A rating is a magnitude, so -2 A uses as much of it as +2 A.

    The DC domain's own sign convention makes a delivering source's branch
    current negative, so a condition that compared signed values would have
    called every real supply comfortably inside its rating.
    """
    problem = voltage_source_relation_problem(VOLTAGE_SOURCE)
    rating = ComponentRating(maximum_current=Quantity(1.0, "ampere"))
    forward = assess_voltage_source_validity(
        problem, rating=rating, source_current=Quantity(2.0, "ampere")
    )
    reverse = assess_voltage_source_validity(
        problem, rating=rating, source_current=Quantity(-2.0, "ampere")
    )
    assert forward.status is reverse.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


# =====================================================================
# Condition 4 — the current source's compliance range
# =====================================================================

def test_current_source_model_accepts_a_network_inside_its_compliance_range():
    assessment = assess_current_source_validity(
        current_source_relation_problem(CURRENT_SOURCE),
        rating=ComponentRating(compliance_voltage=Quantity(12.0, "volt")),
        terminal_voltage=Quantity(5.0, "volt"),
    )
    assert assessment.status is ValidityStatus.IN_DOMAIN
    assert assessment.satisfied == (COMPLIANCE_VOLTAGE_UTILIZATION,)


def test_current_source_model_rejects_a_network_beyond_its_compliance_range():
    """30 V demanded of a 12 V compliance: the network sets the current now.

    The dual of the voltage source's limit, and the direct falsification of
    this model's declared *unlimited compliance voltage*.
    """
    assessment = assess_current_source_validity(
        current_source_relation_problem(CURRENT_SOURCE),
        rating=ComponentRating(compliance_voltage=Quantity(12.0, "volt")),
        terminal_voltage=Quantity(30.0, "volt"),
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (COMPLIANCE_VOLTAGE_UTILIZATION,)


def test_compliance_range_is_unknown_when_no_compliance_voltage_is_declared():
    assessment = assess_current_source_validity(
        current_source_relation_problem(CURRENT_SOURCE),
        terminal_voltage=Quantity(30.0, "volt"),
    )
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (COMPLIANCE_VOLTAGE_UTILIZATION,)
    assert assessment.violated == ()


def test_the_two_source_models_state_one_condition_each_and_not_the_others():
    """Each idealisation is bounded where it is made, not in a shared checklist."""
    assert {c.name for c in IDEAL_VOLTAGE_SOURCE_MODEL.validity.conditions} == {
        SOURCE_CURRENT_UTILIZATION
    }
    assert {c.name for c in IDEAL_CURRENT_SOURCE_MODEL.validity.conditions} == {
        COMPLIANCE_VOLTAGE_UTILIZATION
    }


# =====================================================================
# No condition can be bought by omission
# =====================================================================

def test_omitting_the_operating_point_cannot_produce_a_valid_verdict():
    """A rating with nothing to compare it against decides nothing."""
    assessment = assess_resistor_validity(
        resistor_relation_problem(RESISTOR), rating=QUARTER_WATT
    )
    assert assessment.status is ValidityStatus.UNKNOWN
    assert set(assessment.unknown) == {
        DISSIPATED_POWER_UTILIZATION,
        WORKING_VOLTAGE_UTILIZATION,
    }


def test_the_rating_context_omits_every_key_it_could_not_derive():
    from src.engcore.domains.electrical.dc.models import resistor_rating_context

    assert resistor_rating_context() == {}
    assert resistor_rating_context(rating=QUARTER_WATT) == {}
    assert set(
        resistor_rating_context(
            rating=QUARTER_WATT, dissipated_power=Quantity(0.1, "watt")
        )
    ) == {DISSIPATED_POWER_UTILIZATION}


# =====================================================================
# The rating record
# =====================================================================

def test_a_component_rating_round_trips_through_its_serialized_form():
    rating = ComponentRating(
        rated_power=Quantity(0.25, "watt"),
        maximum_working_voltage=Quantity(200.0, "volt"),
        maximum_current=Quantity(1.0, "ampere"),
        compliance_voltage=Quantity(12.0, "volt"),
        derating_factor=0.6,
    )
    restored = ComponentRating.from_dict(rating.to_dict())
    assert restored == rating
    assert restored.to_dict() == rating.to_dict()
    empty = ComponentRating()
    assert ComponentRating.from_dict(empty.to_dict()) == empty
    assert empty.is_empty and not rating.is_empty
    assert empty.derating_factor == NO_DERATING


def test_a_rating_refuses_a_non_positive_or_wrongly_dimensioned_value():
    for field, unit in (
        ("rated_power", "watt"),
        ("maximum_working_voltage", "volt"),
        ("maximum_current", "ampere"),
        ("compliance_voltage", "volt"),
    ):
        with pytest.raises(InvalidScientificProblem):
            ComponentRating(**{field: Quantity(0.0, unit)})
    with pytest.raises(Exception):
        ComponentRating(rated_power=Quantity(1.0, "volt"))
    with pytest.raises(InvalidScientificProblem):
        ComponentRating(rated_power=0.25)


def test_a_derating_factor_above_one_would_report_overuse_as_headroom():
    for bad in (0.0, -0.5, 1.5):
        with pytest.raises(InvalidScientificProblem):
            ComponentRating(
                rated_power=Quantity(0.25, "watt"), derating_factor=bad
            )
    assert ComponentRating(derating_factor=1.0).derating_factor == 1.0


def test_the_resistor_model_still_binds_to_a_problem_that_declares_no_rating():
    """No new model *inputs* were added: the ratings are computed context.

    A rating is not something a circuit declares; it is something a reader
    knows about a part. Adding it as a required input would have broken every
    problem in the domain, and adding it as an optional one would have implied
    the problem record could carry it.
    """
    report = RESISTOR_OHM_MODEL.check_against(resistor_relation_problem(RESISTOR))
    assert report.is_satisfied
    assert set(report.valid_bindings) == {"resistance", "voltage_across"}
    assert {s.name for s in RESISTOR_OHM_MODEL.inputs} == {
        "resistance",
        "voltage_across",
    }


# =====================================================================
# Integration — a solved circuit is untouched by any of this
# =====================================================================

#: A 10 V source across 1 kohm: 10 mA, 0.1 W, 10 V across the element. Every
#: number here is exact in binary and hand-checkable.
def divider():
    return DCCircuit(
        circuit_id="rating-integration",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(RESISTOR,),
        voltage_sources=(VOLTAGE_SOURCE,),
    )


def test_component_ratings_leave_a_solved_circuit_numerically_identical():
    """Three independent claims about one solve, asserted one at a time.

    1. **Numerical convergence** — the linear system is solved and its own
       residual checks pass, exactly as they do with no rating in sight.
    2. **Coupling convergence** — not applicable here, and the record says
       NOT_APPLICABLE rather than borrowing the numerical verdict.
    3. **Scientific validity** — IN_DOMAIN, a third answer that neither of the
       first two implies.
    """
    result = solve_circuit(divider(), run_id="rating-in-domain")

    # 1. numerical convergence
    assert result.convergence is ConvergenceState.CONVERGED
    assert result.validation.status is ValidationOutcome.PASS
    power = result.value("resistor_power:R1")
    voltage = result.value("resistor_voltage:R1")
    assert power.magnitude_in("watt") == pytest.approx(0.1, rel=1e-12)
    assert voltage.magnitude_in("volt") == pytest.approx(10.0, rel=1e-12)

    # 2. coupling convergence — a different question with no answer here
    assert "coupling" not in result.to_dict()

    # 3. scientific validity
    assessment = assess_resistor_validity(
        resistor_relation_problem(RESISTOR),
        rating=QUARTER_WATT,
        dissipated_power=power,
        voltage_across=voltage,
    )
    assert assessment.status is ValidityStatus.IN_DOMAIN


def test_a_solved_circuit_can_be_correct_and_still_cook_its_resistor():
    """The same solve, judged against a 50 mW part instead of a 250 mW one.

    Nothing numerical moves — a rating is not in the conductance matrix — so
    the values and the convergence are the assertions above, bit for bit. Only
    the validity verdict changes, which is the whole separation: a converged,
    residual-checked solve of a circuit whose element is at twice its rating.
    """
    baseline = solve_circuit(divider(), run_id="rating-baseline")
    result = solve_circuit(divider(), run_id="rating-outside")

    # 1. numerical convergence — unchanged
    assert result.convergence is ConvergenceState.CONVERGED
    assert result.validation.status is ValidationOutcome.PASS
    assert {
        name: q.magnitude for name, q in result.values.items()
    } == {name: q.magnitude for name, q in baseline.values.items()}

    # 2. the numerical checks are the ones that ran, and they still pass
    assert baseline.attained_levels == result.attained_levels

    # 3. validity — and only validity — has moved
    assessment = assess_resistor_validity(
        resistor_relation_problem(RESISTOR),
        rating=ComponentRating(rated_power=Quantity(0.05, "watt")),
        dissipated_power=result.value("resistor_power:R1"),
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (DISSIPATED_POWER_UTILIZATION,)
    # the solved result was not downgraded on account of it
    assert result.validation.status is ValidationOutcome.PASS


def test_the_source_that_delivered_the_current_is_judged_on_its_own_terms():
    """One circuit, three element models, three separate applicability verdicts.

    The source is inside its rating while the resistor is outside its own, in
    the same solve. A single circuit-level verdict could not say that.
    """
    result = solve_circuit(divider(), run_id="rating-per-element")
    source_current = result.value("source_current:V1")

    source = assess_voltage_source_validity(
        voltage_source_relation_problem(VOLTAGE_SOURCE),
        rating=ComponentRating(maximum_current=Quantity(1.0, "ampere")),
        source_current=source_current,
    )
    element = assess_resistor_validity(
        resistor_relation_problem(RESISTOR),
        rating=ComponentRating(rated_power=Quantity(0.05, "watt")),
        dissipated_power=result.value("resistor_power:R1"),
    )
    assert source.status is ValidityStatus.IN_DOMAIN
    assert element.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    # and the problem record still describes the circuit that was solved
    assert build_dc_problem(divider()).problem_id == result.problem_id


# =====================================================================
# Integration — the same, inside the electro-thermal coupled run
# =====================================================================

#: The preregistered CASE A trace of the electro-thermal vertical milestone.
CASE_A_TEMPERATURE = 338.577018
CASE_A_RESISTANCE = 11.785282
CASE_A_POWER = 2.121290
CASE_A_VOLTAGE = 5.0
CASE_A_ITERATIONS = 10


def run_coupled(run_id):
    """The nominal single-stage self-heating resistor, unchanged in every way.

    A rating is never an input to the run: it is knowledge a reader has about
    the part, applied to the run's own output afterwards. So there is one run
    here and two verdicts over it, rather than two runs.
    """
    system = cp.CoupledElectroThermalSystem(
        stages=(
            cp.CoupledStage(
                mat.TemperatureDependentConductor(
                    component_id="R1",
                    reference_resistance=Quantity(10.0, "ohm"),
                    temperature_coefficient=Quantity(0.00393, "1/kelvin"),
                    reference_temperature=Quantity(293.15, "kelvin"),
                ),
                lump.ThermalBody(
                    body_id="R1",
                    heat_capacity=Quantity(2.5, "joule/kelvin"),
                    ambient_conductance=Quantity(0.05, "watt/kelvin"),
                    ambient_temperature=Quantity(300.0, "kelvin"),
                    initial_temperature=Quantity(300.0, "kelvin"),
                    duration=Quantity(120.0, "second"),
                ),
            ),
        ),
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
        seed=Quantity(300.0, "kelvin"),
        tolerance=Quantity(1e-6, "kelvin"),
        max_iterations=50,
    )
    return cp.run_fixed_point_coupling(system, plan, run_id=run_id), problems


def test_resistor_ratings_leave_the_coupled_run_numerically_identical():
    """Three independent claims about one coupled run, asserted one at a time.

    1. **Numerical convergence** — each electrical sub-solve converged and
       passed its own residual checks, reproducing the preregistered CASE A
       trace.
    2. **Coupling convergence** — the fixed point is reached in the same ten
       iterations, to the same tolerance. A different question with a different
       record.
    3. **Scientific validity** — the element is inside a 5 W part's rating.
       A third answer, implied by neither of the first two.
    """
    run, problems = run_coupled("dc-rating-in-domain")
    electrical = problems[0].problem_id

    # 1. numerical convergence
    assert {r.convergence for i in run.iterations for r in i.results} == {
        ConvergenceState.CONVERGED,
        ConvergenceState.NOT_APPLICABLE,
    }
    for iteration in run.iterations:
        assert (
            iteration.result_for(electrical).validation.status
            is ValidationOutcome.PASS
        )
    power = run.final.result_for(electrical).value("resistor_power:R1")
    voltage = run.final.result_for(electrical).value("resistor_voltage:R1")
    assert power.magnitude_in("watt") == pytest.approx(CASE_A_POWER, abs=1e-6)
    assert voltage.magnitude_in("volt") == pytest.approx(CASE_A_VOLTAGE, rel=1e-12)
    assert run.final.result_for(problems[1].problem_id).value(
        "resistance"
    ).magnitude_in("ohm") == pytest.approx(CASE_A_RESISTANCE, abs=1e-6)
    (temperature,) = run.final_values.values()
    assert temperature.magnitude_in("kelvin") == pytest.approx(
        CASE_A_TEMPERATURE, abs=1e-6
    )

    # 2. coupling convergence
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert run.criterion_met is True
    assert run.iterations_run == CASE_A_ITERATIONS
    assert run.final_iterate_change.magnitude_in("kelvin") <= 1e-6

    # 3. scientific validity
    assessment = assess_resistor_validity(
        resistor_relation_problem(
            Resistor("R1", "n0", "gnd", Quantity(CASE_A_RESISTANCE, "ohm"))
        ),
        rating=ComponentRating(
            rated_power=Quantity(5.0, "watt"),
            maximum_working_voltage=Quantity(200.0, "volt"),
        ),
        dissipated_power=power,
        voltage_across=voltage,
    )
    assert assessment.status is ValidityStatus.IN_DOMAIN


def test_a_coupled_run_can_converge_while_its_resistor_is_over_its_rating():
    """The identical run, judged against a 1 W part instead of a 5 W one.

    Nothing numerical moves — the same run object would serve, and a second one
    is used only to show the run is reproducible. Only the validity verdict
    changes: a converged coupling, of converged and residual-checked electrical
    solves, of an element at twice the dissipation it is rated for.
    """
    baseline, _ = run_coupled("dc-rating-baseline")
    run, problems = run_coupled("dc-rating-outside")
    electrical = problems[0].problem_id

    # 1. numerical convergence — unchanged
    assert {r.convergence for i in run.iterations for r in i.results} == {
        ConvergenceState.CONVERGED,
        ConvergenceState.NOT_APPLICABLE,
    }
    assert run.final_values == baseline.final_values
    power = run.final.result_for(electrical).value("resistor_power:R1")
    assert power.magnitude_in("watt") == pytest.approx(CASE_A_POWER, abs=1e-6)

    # 2. coupling convergence — unchanged
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert run.iterations_run == CASE_A_ITERATIONS

    # 3. validity — and only validity — has moved
    assessment = assess_resistor_validity(
        resistor_relation_problem(
            Resistor("R1", "n0", "gnd", Quantity(CASE_A_RESISTANCE, "ohm"))
        ),
        rating=ComponentRating(rated_power=Quantity(1.0, "watt")),
        dissipated_power=power,
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (DISSIPATED_POWER_UTILIZATION,)
    # no sub-result was downgraded on account of it
    for iteration in run.iterations:
        for result in iteration.results:
            assert result.validation.status is not ValidationOutcome.FAIL
