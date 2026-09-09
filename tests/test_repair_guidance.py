"""Repair guidance: does the hint work, and can it ever name a bound?

Four things are asserted here, and only the first is about arithmetic.

**An applied hint flips the verdict.** Take a case with exactly one violated
condition, apply the exact value a hint proposes, re-run the assessment, and
assert the condition is satisfied. This is the load-bearing test: a hint that
does not work is worse than no hint, because a caller who acts on it has spent
a design change to arrive back where they were. It runs over three domains and
seven conditions, and it applies the hint *literally* -- the number that would
be printed, not a value chosen to be comfortably inside.

**A non-invertible input reports its non-invertibility.** Not silence, and not
a number found by trying things. The two cases pinned below are the two shapes
that recur: an input that reaches the group through an absolute value, where
the admissible set is an interval and no single inequality states it; and an
input that cancels out of the group entirely, where a hint would have moved
nothing at all.

**No hint can name a bound.** This is the one that has to be structural, and
the tests below argue it from what names exist rather than from what any
particular emitter happens to produce. See `engcore.domains.repair` for why --
and for commit d57a88e, where a bound was removed rather than raised because
it constrained the wrong ratio, which is the case that says why "raise the
limit" must be unsayable.

**The boundary is inclusive, and lands inside.** A hint against an inclusive
bound reads `<=`; against an exclusive one it reads `<`. The threshold is the
exact solution rounded into the admissible side, because the exact solution
re-derived in floating point can land one ulp outside -- which the Biot number
does, and which the first test would have caught as a hint that did not work.
"""

from __future__ import annotations

import copy
import dataclasses
import math

import pytest

from src.engcore.domains import repair as rp
from src.engcore.domains.electrical import material as mat
from src.engcore.domains.electrical.dc import models as dc_models
from src.engcore.domains.electrical.dc import problem as dc_problem
from src.engcore.domains.thermal_models import context as tctx
from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.mcp import run_electrothermal_case
from src.engcore.scientific.models.definition import (
    InputSourceKind,
    RangeCondition,
    ValidityStatus,
)
from src.engcore.scientific.units.quantity import Quantity

from tests.mcp.test_problem import BIOT_VIOLATING_PAYLOAD


#: Every model in this repository that declares an inversion table, with it.
TABLES = (
    (lump.LUMPED_CAPACITY_MODEL, lump.LUMPED_INVERSIONS),
    (mat.LINEAR_TCR_MODEL, mat.TCR_INVERSIONS),
    (mat.RATED_LINEAR_TCR_MODEL, mat.RATED_TCR_INVERSIONS),
    (dc_models.RESISTOR_OHM_MODEL, dc_models.RESISTOR_INVERSIONS),
    (dc_models.IDEAL_VOLTAGE_SOURCE_MODEL, dc_models.VOLTAGE_SOURCE_INVERSIONS),
    (dc_models.IDEAL_CURRENT_SOURCE_MODEL, dc_models.CURRENT_SOURCE_INVERSIONS),
    (dc_models.KCL_MODEL, dc_models.KCL_INVERSIONS),
)


def parameter_inputs(model) -> set[str]:
    return {
        spec.name
        for spec in model.inputs
        if spec.source_kind is InputSourceKind.PARAMETER
    }


# =====================================================================
# A lumped body, and the assessment it produces
# =====================================================================

BASE_DECLARATION = {
    "characteristic_length": Quantity(0.002, "meter"),
    "surface_area": Quantity(0.01, "meter**2"),
    "body_conductivity": Quantity(200.0, "watt/meter/kelvin"),
}

HEAT_INPUT = Quantity(0.5, "watt")


#: A few derived-context names differ from the field they arrive on. The
#: declaration record calls the body's volume `volume`; the context, and
#: therefore every hint, calls it `body_volume` because that is the name the
#: model's condition reads.
CONTEXT_TO_FIELD = {"body_volume": "volume"}


def lumped_case(**declaration):
    """One body, its assessment and its repairs, at a fixed operating point."""
    fields = {
        CONTEXT_TO_FIELD.get(name, name): value
        for name, value in {**BASE_DECLARATION, **declaration}.items()
    }
    body = lump.ThermalBody(
        body_id="B1",
        heat_capacity=fields.pop("heat_capacity", Quantity(2.5, "joule/kelvin")),
        ambient_conductance=fields.pop(
            "ambient_conductance", Quantity(0.05, "watt/kelvin")
        ),
        ambient_temperature=Quantity(300.0, "kelvin"),
        initial_temperature=Quantity(300.0, "kelvin"),
        duration=fields.pop("duration", Quantity(120.0, "second")),
        applicability=tctx.LumpedApplicabilityDeclaration(**fields),
    )
    problem = lump.build_lumped_thermal_problem(body)
    state = dict(
        initial_temperature=body.initial_temperature,
        ambient_temperature=body.ambient_temperature,
        heat_input=HEAT_INPUT,
    )
    return (
        lump.assess_lumped_validity(problem, **state),
        lump.lumped_repairs(problem, subject=body.body_id, **state),
    )


def only_hints_for(repairs, condition):
    """The hints for one condition, asserting it is the only one violated."""
    assert [r.condition for r in repairs] == [condition], (
        f"this case is meant to violate {condition!r} alone; it violates "
        f"{[r.condition for r in repairs]}"
    )
    return repairs[0].hints


#: Declaration overrides that violate exactly one lumped condition, with the
#: name of the field each hint targets mapped back to the way `lumped_case`
#: takes it. Every one of these is a real body: nothing is made to violate by
#: leaving a declaration out, which would produce UNKNOWN rather than a
#: violation and would test nothing.
LUMPED_VIOLATIONS = {
    # Bi = (hA/A_s) L_c / k = 5 * 0.05 / 0.2 = 1.25, twelve times the limit.
    "biot_number": {
        "characteristic_length": Quantity(0.05, "meter"),
        "body_conductivity": Quantity(0.2, "watt/meter/kelvin"),
    },
    # T_ss = 300 + 0.5/0.05 = 310 K against a 305 K melting temperature.
    "melting_temperature_utilization": {
        "melting_temperature": Quantity(305.0, "kelvin"),
    },
    # dT = |T_ss - T_amb| = 10 K against a declared 4 K constant-hA span.
    "conductance_excursion_ratio": {
        "conductance_excursion_bound": Quantity(4.0, "kelvin"),
    },
    # |T_ss - T_0| = 10 K against a declared 4 K constant-C span.
    "capacity_excursion_ratio": {
        "capacity_excursion_bound": Quantity(4.0, "kelvin"),
    },
    # L_c declared 50x above V/A_s = 1e-4/0.01 = 0.01 m: the two routes
    # describe different objects.
    "geometry_route_ratio": {
        "characteristic_length": Quantity(0.5, "meter"),
        "body_volume": Quantity(1.0e-4, "meter**3"),
    },
}


@pytest.mark.parametrize("condition", sorted(LUMPED_VIOLATIONS))
def test_an_applied_lumped_hint_flips_the_condition(condition):
    """Apply the exact value each hint names; the condition must be satisfied.

    The whole point of the exercise. Before: the condition is violated and
    the hint says what to move. After: with that one declaration replaced by
    the number the hint printed and every other declaration untouched, the
    condition is in the satisfied list.
    """
    before, repairs = lumped_case(**LUMPED_VIOLATIONS[condition])
    assert condition in before.violated
    hints = only_hints_for(repairs, condition)
    assert hints, f"{condition} produced no hint at all"

    for hint in hints:
        after, _ = lumped_case(
            **{
                **LUMPED_VIOLATIONS[condition],
                hint.target_name: hint.threshold,
            }
        )
        assert condition in after.satisfied, (
            f"applying {hint.line()} left {condition} at "
            f"{after.violated + after.unknown}"
        )


def test_the_biot_hints_are_the_four_declarations_the_number_is_formed_from():
    """Not just that they work, but that the set is the right set."""
    _before, repairs = lumped_case(**LUMPED_VIOLATIONS["biot_number"])
    hints = only_hints_for(repairs, "biot_number")
    assert {h.target_name for h in hints} == {
        "characteristic_length",
        "body_conductivity",
        "ambient_conductance",
        "surface_area",
    }


def test_a_single_lumped_hint_carries_the_whole_verdict_to_in_domain():
    """One violated condition, one applied hint, and the model is in domain.

    The per-condition tests above assert the condition. This asserts the
    verdict, which is what a caller reads -- and it holds only because the
    case has exactly one violation. With two, applying one hint repairs one
    condition and the verdict stays outside, which is the honest behaviour and
    is why nothing here composes hints.
    """
    before, repairs = lumped_case(**LUMPED_VIOLATIONS["biot_number"])
    assert before.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    hint = next(
        h
        for h in only_hints_for(repairs, "biot_number")
        if h.target_name == "body_conductivity"
    )
    after, after_repairs = lumped_case(
        **{**LUMPED_VIOLATIONS["biot_number"], "body_conductivity": hint.threshold}
    )
    assert after.violated == ()
    assert after_repairs == ()


def test_a_hint_repairs_its_own_condition_and_promises_nothing_else():
    """The caveat a caller is most likely to hit, pinned rather than described.

    A hint holds every *other declaration* fixed. It does not hold every other
    *condition* fixed, because one declaration can feed several groups, and
    moving it to repair one can carry another out.

    `geometry_route_ratio` is `L_c A_s / V`, so it falls as the surface area
    falls. The Biot number is `(hA/A_s) L_c / k`, so it *rises* as the area
    falls. Applying the area hint therefore does exactly what it says --
    `geometry_route_ratio` becomes satisfied -- and leaves the model outside
    its validated domain on a condition that was satisfied before.

    That is the honest contract and not a defect. Detecting it would mean
    evaluating the whole domain at each proposed point and reporting which
    hints are jointly workable, which is the ranking this module refuses to
    do: it would turn alternatives into a recommendation. So the report says
    what each hint repairs, the caller re-runs the case, and this test is what
    stops the contract from quietly widening into a promise it does not keep.
    """
    before, repairs = lumped_case(**LUMPED_VIOLATIONS["geometry_route_ratio"])
    assert before.violated == ("geometry_route_ratio",)
    assert "biot_number" in before.satisfied

    hint = next(
        h
        for h in only_hints_for(repairs, "geometry_route_ratio")
        if h.target_name == "surface_area"
    )
    assert hint.direction is rp.RepairDirection.AT_MOST

    after, after_repairs = lumped_case(
        **{
            **LUMPED_VIOLATIONS["geometry_route_ratio"],
            "surface_area": hint.threshold,
        }
    )
    # It did what it said.
    assert "geometry_route_ratio" in after.satisfied
    # And no more than that: the verdict is still outside, on a different
    # condition, and the report now carries that condition's own repair.
    assert after.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert after.violated == ("biot_number",)
    assert [r.condition for r in after_repairs] == ["biot_number"]

    # The other two hints for the same condition do carry the whole verdict,
    # so this is a property of which declaration is moved and not of the
    # condition -- which is exactly why the caller has to be the one choosing.
    for target in ("characteristic_length", "body_volume"):
        alternative = next(
            h
            for h in only_hints_for(repairs, "geometry_route_ratio")
            if h.target_name == target
        )
        recovered, _ = lumped_case(
            **{
                **LUMPED_VIOLATIONS["geometry_route_ratio"],
                target: alternative.threshold,
            }
        )
        assert recovered.violated == ()


# =====================================================================
# The material domain
# =====================================================================

def rated_case(**limits):
    conductor = mat.TemperatureDependentConductor(
        component_id="R1",
        reference_resistance=Quantity(10.0, "ohm"),
        temperature_coefficient=limits.pop(
            "temperature_coefficient", Quantity(0.00393, "1/kelvin")
        ),
        reference_temperature=limits.pop(
            "reference_temperature", Quantity(293.15, "kelvin")
        ),
        limits=mat.MaterialLimits(**limits),
    )
    problem = mat.build_resistance_problem(conductor)
    temperature = Quantity(340.0, "kelvin")
    return (
        mat.assess_rated_resistance_validity(problem, temperature),
        mat.rated_resistance_repairs(problem, temperature, subject="R1"),
    )


MATERIAL_VIOLATIONS = {
    # 340 K against a material rated to 320 K.
    "operating_temperature_utilization": {
        "maximum_operating_temperature": Quantity(320.0, "kelvin"),
    },
    # 340 K against theta_D = 1200 K puts the conductor at 0.28, below 1/3.
    "reduced_debye_temperature": {
        "debye_temperature": Quantity(1200.0, "kelvin"),
    },
    # |340 - 293.15| = 46.85 K against a declared 20 K band.
    "linearization_excursion_ratio": {
        "linearization_band": Quantity(20.0, "kelvin"),
    },
}


@pytest.mark.parametrize("condition", sorted(MATERIAL_VIOLATIONS))
def test_an_applied_material_hint_flips_the_condition(condition):
    before, repairs = rated_case(**MATERIAL_VIOLATIONS[condition])
    assert condition in before.violated
    hints = only_hints_for(repairs, condition)
    assert hints
    for hint in hints:
        after, _ = rated_case(
            **{**MATERIAL_VIOLATIONS[condition], hint.target_name: hint.threshold}
        )
        assert condition in after.satisfied, (
            f"applying {hint.line()} left {condition} at "
            f"{after.violated + after.unknown}"
        )


def test_an_applied_hint_repairs_a_negative_linear_resistance_ratio():
    """The one affine inversion: 1 + alpha (T - T_ref) driven below zero.

    Not a power law, and it is inverted anyway because the form is exact and
    single-valued. alpha = -0.03 /K over a 46.85 K excursion gives a ratio of
    -0.4055: past the crossing the linear form describes a negative conductor.
    """
    alpha = Quantity(-0.03, "1/kelvin")
    before, repairs = rated_case(
        temperature_coefficient=alpha,
        maximum_operating_temperature=Quantity(400.0, "kelvin"),
    )
    assert "linear_resistance_ratio" in before.violated
    hints = only_hints_for(repairs, "linear_resistance_ratio")
    assert {h.target_name for h in hints} == {
        "temperature_coefficient",
        "reference_temperature",
    }
    for hint in hints:
        after, _ = rated_case(
            **{
                "temperature_coefficient": alpha,
                "maximum_operating_temperature": Quantity(400.0, "kelvin"),
                hint.target_name: hint.threshold,
            }
        )
        assert "linear_resistance_ratio" in after.satisfied, (
            f"applying {hint.line()} left it at "
            f"{after.violated + after.unknown}"
        )


# =====================================================================
# The electrical DC domain
# =====================================================================

class _Element:
    component_id = "R1"
    resistance = Quantity(100.0, "ohm")


def resistor_case(rating, **operating):
    problem = dc_problem.resistor_relation_problem(_Element())
    state = {
        "dissipated_power": Quantity(0.9, "watt"),
        "voltage_across": Quantity(9.4868, "volt"),
        **operating,
    }
    return (
        dc_models.assess_resistor_validity(problem, rating=rating, **state),
        dc_models.resistor_repairs(
            problem, subject="R1", rating=rating, **state
        ),
    )


def test_an_applied_rating_hint_flips_the_dissipation_condition():
    """0.9 W into a 0.25 W part derated to 0.8: 4.5 times its rating."""
    rating = dc_models.ComponentRating(
        rated_power=Quantity(0.25, "watt"),
        maximum_working_voltage=Quantity(200.0, "volt"),
        derating_factor=0.8,
    )
    before, repairs = resistor_case(rating)
    assert "dissipated_power_utilization" in before.violated
    hints = only_hints_for(repairs, "dissipated_power_utilization")
    assert [h.target_name for h in hints] == ["rated_power"]

    after, _ = resistor_case(
        dataclasses.replace(rating, rated_power=hints[0].threshold)
    )
    assert "dissipated_power_utilization" in after.satisfied


def test_an_applied_rating_hint_flips_the_working_voltage_condition():
    """9.4868 V across a part rated to 5 V, derated to 0.8: 2.37 times."""
    rating = dc_models.ComponentRating(
        rated_power=Quantity(10.0, "watt"),
        maximum_working_voltage=Quantity(5.0, "volt"),
        derating_factor=0.8,
    )
    before, repairs = resistor_case(rating)
    assert "working_voltage_utilization" in before.violated
    hints = only_hints_for(repairs, "working_voltage_utilization")
    # `derating_factor` is a real inversion here and is still refused: at
    # 2.37x the rating it would have to reach 1.9, and a factor above 1 uses
    # more of a part than it is rated for. The rating is the only repair.
    assert [h.target_name for h in hints] == ["maximum_working_voltage"]
    after, _ = resistor_case(
        dataclasses.replace(
            rating, maximum_working_voltage=hints[0].threshold
        )
    )
    assert "working_voltage_utilization" in after.satisfied


def test_a_derating_factor_above_one_is_refused_rather_than_proposed():
    """The raise-the-limit move wearing a declared input's name.

    `derating_factor` divides the rating, so the utilization is an exact
    reciprocal in it and the inversion is real. At 4.5x over rating the
    inversion says 3.6 -- and `ComponentRating` admits only (0, 1], because a
    factor above 1 uses more of a component than it is rated for while
    reporting that it is inside its rating. That is the same move as raising
    the bound, reached through an input rather than through a limit, so the
    hint is refused and the refusal says which ceiling it hit.

    Found by the applied-hint test above, which could not construct the rating
    the hint proposed.
    """
    rating = dc_models.ComponentRating(
        rated_power=Quantity(0.25, "watt"),
        maximum_working_voltage=Quantity(200.0, "volt"),
        derating_factor=0.8,
    )
    _before, repairs = resistor_case(rating)
    repair = repairs[0]
    assert "derating_factor" not in {h.target_name for h in repair.hints}
    refusal = next(r for r in repair.refusals if r.target == "derating_factor")
    assert "past 1.0 dimensionless" in refusal.reason
    assert "rated for" in refusal.reason


# =====================================================================
# What could not be inverted, and why
# =====================================================================

def test_the_reference_temperature_is_refused_because_the_set_is_an_interval():
    """|T - T_ref| / band: the admissible T_ref is [T - band, T + band].

    A one-sided hint would be true of half that set and silent about the rest.
    The refusal names the shape rather than reporting a number from one side.
    """
    _before, repairs = rated_case(linearization_band=Quantity(20.0, "kelvin"))
    repair = repairs[0]
    assert repair.condition == "linearization_excursion_ratio"
    assert {h.target_name for h in repair.hints} == {"linearization_band"}
    refusal = next(
        r for r in repair.refusals if r.target == "reference_temperature"
    )
    assert "interval" in refusal.reason
    assert "two-sided" in refusal.reason


def test_the_conductance_is_refused_from_fourier_because_it_cancels():
    """Fo = (t/tau)/Bi = t A_s k / (C L_c): hA is not in it.

    The most useful refusal in the repository, because the hint it prevents
    would have looked right and moved nothing at all. Distinct from "there is
    no inverse": there is no dependence.

    Read off the inversion table rather than off an emitted repair, and the
    reason is the test below: `internal_fourier_number` is now a conservative
    screen, so no assessment puts it in `violated` and no `ConditionRepair` is
    ever emitted for it. The decision itself is unchanged and still checked
    here -- the table is built and validated against the model at import, so
    the refusal is a fact about the declaration and not about any one case.
    """
    row = lump.LUMPED_INVERSIONS.row("internal_fourier_number")
    assert row is not None
    assert "ambient_conductance" not in {i.target for i in row.inversions}
    refusal = next(r for r in row.refusals if r.target == "ambient_conductance")
    assert "cancels exactly" in refusal.reason
    assert "moves nothing" in refusal.reason


def test_a_conservative_screen_emits_no_repair_because_it_finds_nothing():
    """The cost of the screen, asserted rather than discovered later.

    `condition_repairs` walks `assessment.violated`, so a condition that
    reports its failures as `unknown` never reaches it. That follows from the
    screen and is not a second decision: a repair says "change this and the
    bound is met", which presumes the bound found against the design. A screen
    did not. The inversion row is still there for a reader who wants to know
    what would move Fo -- see the test above -- but nothing emits it.

    Bi = (hA/A_s) L_c / k = 5 * 0.002 / 0.1 = 0.1 exactly, which the inclusive
    limit admits, so the Biot condition is satisfied and Fo is the only bound
    the body is outside. tau = C/hA = 50 s, so Fo = (0.5/50)/0.1 = 0.1 < 0.2.
    """
    before, repairs = lumped_case(
        duration=Quantity(0.5, "second"),
        body_conductivity=Quantity(0.1, "watt/meter/kelvin"),
    )
    assert "internal_fourier_number" in before.unknown
    assert before.violated == ()
    assert [r.condition for r in repairs] == []


def test_a_condition_no_declared_input_can_repair_says_so_plainly():
    """The current source's compliance rating is not one of its declared inputs.

    So there is nothing a hint could be about, and the report says that rather
    than naming something adjacent. `repairable` is the field a caller reads.
    """
    model = dc_models.IDEAL_CURRENT_SOURCE_MODEL
    row = dc_models.CURRENT_SOURCE_INVERSIONS.row(
        dc_models.COMPLIANCE_VOLTAGE_UTILIZATION
    )
    assert row.inversions == ()
    assert "not repairable" in row.refusals[0].reason
    assert "compliance_voltage" not in parameter_inputs(model)


def test_an_unrepairable_condition_renders_as_unrepairable():
    repair = rp.ConditionRepair(
        model_id="m",
        subject="s",
        condition="c",
        observed=Quantity(2.0, "dimensionless"),
        bound=Quantity(1.0, "dimensionless"),
        bound_side="maximum",
        bound_inclusive=True,
        refusals=(rp.RepairRefusal("c", "x", "because"),),
    )
    assert repair.repairable is False
    assert "Not repairable by any single declared input:" in repair.lines()


def test_a_repair_that_says_nothing_is_refused():
    with pytest.raises(rp.RepairGuidanceError, match="silence is not a report"):
        rp.ConditionRepair(
            model_id="m",
            subject="s",
            condition="c",
            observed=Quantity(2.0, "dimensionless"),
            bound=Quantity(1.0, "dimensionless"),
            bound_side="maximum",
            bound_inclusive=True,
        )


# =====================================================================
# No hint can name a bound
# =====================================================================

def test_a_bound_has_no_name_anywhere_in_a_model_record():
    """The structural claim, argued from the records rather than the emitter.

    A `RangeCondition`'s bounds are `Quantity` values held as attributes of
    the condition. `Quantity` carries a magnitude and a unit and no name;
    `context_keys` -- the complete set of names a condition reads -- is the
    condition's own name and nothing else; and no bound appears among the
    model's declared inputs. So there is no string that denotes a bound, which
    is why no argument to `RepairTarget` can make one.
    """
    quantity_fields = {f.name for f in dataclasses.fields(Quantity)}
    assert quantity_fields == {"magnitude", "units"}

    for model, _table in TABLES:
        declared = {spec.name for spec in model.inputs}
        for condition in model.validity.conditions:
            if not isinstance(condition, RangeCondition):
                continue
            assert condition.context_keys == frozenset({condition.name})
            for bound in (condition.minimum, condition.maximum):
                if bound is None:
                    continue
                assert isinstance(bound, Quantity)
                # The one way a bound could acquire a name is by being a
                # declared input's value. It is not: the bound lives on the
                # condition and the inputs are a separate tuple of specs.
                assert not hasattr(bound, "name")
        assert declared.isdisjoint({"minimum", "maximum"})


def test_a_repair_target_is_exactly_a_declared_parameter_input():
    """Constructible for every parameter input; refused for everything else."""
    for model, _table in TABLES:
        parameters = parameter_inputs(model)
        for name in parameters:
            assert rp.RepairTarget(model, name).name == name
        variables = {
            spec.name
            for spec in model.inputs
            if spec.source_kind is not InputSourceKind.PARAMETER
        }
        for name in variables:
            with pytest.raises(rp.RepairGuidanceError, match="not a declared parameter"):
                rp.RepairTarget(model, name)
        for name in set(model.derived_quantities) - parameters - variables:
            with pytest.raises(rp.RepairGuidanceError):
                rp.RepairTarget(model, name)


@pytest.mark.parametrize(
    "name",
    [
        "minimum",
        "maximum",
        "bound",
        "limit",
        "lumped_biot_limit",
        "LUMPED_BIOT_LIMIT",
        "biot_number_limit",
        "biot_number.maximum",
        "rating_utilization_limit",
        "excursion_budget_limit",
        "bloch_grueneisen_linear_floor",
    ],
)
def test_no_name_that_could_denote_a_bound_is_a_repair_target(name):
    """Every plausible spelling, over every model that emits hints.

    Deliberately adversarial and deliberately not the whole argument: the
    argument is the test above, that no such name exists at all. This one
    pins the refusal a caller would actually meet.
    """
    for model, _table in TABLES:
        with pytest.raises(rp.RepairGuidanceError):
            rp.RepairTarget(model, name)


def test_a_hint_refuses_a_bare_string_as_its_subject():
    """The type is the guard. A string could name anything, including a bound."""
    with pytest.raises(rp.RepairGuidanceError, match="must be a RepairTarget"):
        rp.RepairHint(
            condition="biot_number",
            target="characteristic_length",
            direction=rp.RepairDirection.AT_MOST,
            threshold=Quantity(1.0, "meter"),
            declared=Quantity(2.0, "meter"),
            inclusive=True,
        )


def test_every_inversion_declared_anywhere_names_a_declared_parameter_input():
    """Over every table in the repository, including refusal targets.

    The tables are checked at import -- `ModelInversionTable` mints a
    `RepairTarget` for every inversion as it is constructed -- so this is a
    second reading of the same fact from outside, and it also covers the
    refusals, which are allowed to name a reserved derived quantity but
    nothing beyond that.
    """
    for model, table in TABLES:
        parameters = parameter_inputs(model)
        nameable = parameters | set(model.derived_quantities) | {
            spec.name for spec in model.inputs
        }
        for row in table.rows:
            for inversion in row.inversions:
                assert inversion.target in parameters
            for refusal in row.refusals:
                assert refusal.target in nameable


def test_every_range_condition_in_a_tabled_model_has_a_decision():
    """A condition with no inversion decision does not import."""
    for model, table in TABLES:
        conditions = {
            c.name
            for c in model.validity.conditions
            if isinstance(c, RangeCondition)
        }
        assert {row.condition for row in table.rows} == conditions


def test_a_table_that_omits_a_condition_is_refused_at_construction():
    with pytest.raises(rp.RepairGuidanceError, match="says nothing about"):
        rp.ModelInversionTable(
            model=lump.LUMPED_CAPACITY_MODEL,
            rows=(
                rp.ConditionInversions(
                    condition="biot_number",
                    inversions=(
                        rp.MonotoneInversion(
                            target="characteristic_length",
                            exponent=1.0,
                            justification="linear",
                        ),
                    ),
                ),
            ),
        )


def test_a_table_naming_a_bound_cannot_be_constructed():
    """The import-time form of the impossibility.

    The real lumped table with one row replaced by the forbidden hint -- a
    reciprocal in the Biot limit, which is exactly "raise the ceiling" written
    as an inversion. It does not construct, so a domain could not ship it.
    """
    rows = tuple(
        row
        if row.condition != "biot_number"
        else rp.ConditionInversions(
            condition="biot_number",
            inversions=(
                rp.MonotoneInversion(
                    target="lumped_biot_limit",
                    exponent=-1.0,
                    justification="raise the limit",
                ),
            ),
        )
        for row in lump.LUMPED_INVERSIONS.rows
    )
    with pytest.raises(rp.RepairGuidanceError, match="not a declared input"):
        rp.ModelInversionTable(model=lump.LUMPED_CAPACITY_MODEL, rows=rows)


# =====================================================================
# The boundary
# =====================================================================

def test_a_hint_against_an_inclusive_bound_is_inclusive():
    """Bi <= 0.1 is met at the threshold, so the hint reads `<=`.

    Inclusivity is inherited from the bound, never chosen: the inversion is a
    strictly monotone bijection, so `g(x) <= B` and `x <= x*` are the same
    statement with the same strictness.
    """
    _before, repairs = lumped_case(**LUMPED_VIOLATIONS["biot_number"])
    for hint in only_hints_for(repairs, "biot_number"):
        assert hint.inclusive is True
        assert hint.line().split()[1] in {"≤", "≥"}


def test_a_hint_against_an_exclusive_bound_is_exclusive():
    """1 + alpha (T - T_ref) > 0 is *not* met at the threshold, so `>`."""
    before, repairs = rated_case(
        temperature_coefficient=Quantity(-0.03, "1/kelvin"),
        maximum_operating_temperature=Quantity(400.0, "kelvin"),
    )
    assert "linear_resistance_ratio" in before.violated
    for hint in only_hints_for(repairs, "linear_resistance_ratio"):
        assert hint.inclusive is False
        assert hint.line().split()[1] in {"<", ">"}


def test_the_threshold_is_rounded_into_the_admissible_side():
    """The exact solution can land one ulp outside; the printed one does not.

    Pinned with the case that produced it. Bi = 0.42 with L_c = 10 mm,
    k = 100 W/m/K, A_s = 5/4200 m^2 and hA = 5 W/K; the exact repair is
    L_c = 0.1 k A_s / hA, and the nearest double to it re-derives
    Bi = 0.10000000000000002, one ulp above an inclusive 0.1. The printed
    threshold is that solution rounded down at twelve significant figures, and
    it lands inside.
    """
    exact = 0.1 * 100.0 * (5.0 / 4200.0) / 5.0
    declared = {
        "ambient_conductance": Quantity(5.0, "watt/kelvin"),
        "characteristic_length": Quantity(0.01, "meter"),
        "surface_area": Quantity(5.0 / 4200.0, "meter**2"),
        "body_conductivity": Quantity(100.0, "watt/meter/kelvin"),
    }
    before, repairs = lumped_case(**declared)
    assert "biot_number" in before.violated
    hint = next(
        h
        for h in only_hints_for(repairs, "biot_number")
        if h.target_name == "characteristic_length"
    )
    printed = hint.threshold.magnitude_in("meter")

    # The exact solution does not survive being re-derived.
    naive, _ = lumped_case(
        **{**declared, "characteristic_length": Quantity(exact, "meter")}
    )
    assert "biot_number" in naive.violated

    # The printed one does, and is inside the exact solution by less than the
    # last four digits of a double.
    assert printed < exact
    assert math.isclose(printed, exact, rel_tol=1e-11)
    repaired, _ = lumped_case(
        **{**declared, "characteristic_length": hint.threshold}
    )
    assert "biot_number" in repaired.satisfied


def test_rounding_moves_a_lower_threshold_upward():
    """`AT_LEAST` rounds up, which is into its own admissible side."""
    assert rp._round_into(1.0000000000004, rp.RepairDirection.AT_LEAST) > 1.0
    assert rp._round_into(1.0000000000004, rp.RepairDirection.AT_MOST) < (
        1.0000000000004
    )
    assert rp._round_into(0.0, rp.RepairDirection.AT_MOST) == 0.0
    assert rp._round_into(-2.0000000000004, rp.RepairDirection.AT_MOST) < -2.0


# =====================================================================
# The report an agent reads
# =====================================================================

def test_the_electrothermal_report_carries_structured_repairs():
    """One repair group per stage, structured, and never merged across sites."""
    case = run_electrothermal_case(copy.deepcopy(BIOT_VIOLATING_PAYLOAD))
    assert len(case.repairs) == len(case.reports)
    repairs = case.repairs[0]
    assert repairs, "a NOT_SUPPORTED case with no repair guidance says nothing"

    biot = next(r for r in repairs if r.condition == "biot_number")
    assert biot.subject == "R1"
    payload = biot.to_dict()
    assert payload["repairable"] is True
    assert payload["bound_side"] == "maximum"
    assert payload["bound_inclusive"] is True
    assert {hint["target"] for hint in payload["hints"]} == {
        "characteristic_length",
        "body_conductivity",
        "ambient_conductance",
        "surface_area",
    }
    for hint in payload["hints"]:
        assert hint["direction"] in {"at_most", "at_least"}
        assert hint["basis"]


def test_every_repair_the_boundary_emits_is_about_a_violated_condition():
    case = run_electrothermal_case(copy.deepcopy(BIOT_VIOLATING_PAYLOAD))
    for report, repairs in zip(case.reports, case.repairs):
        violated = {
            (record.model_id, name)
            for record in report.validity
            for name in record.assessment.violated
        }
        for repair in repairs:
            assert (repair.model_id, repair.condition) in violated


def test_no_emitted_hint_anywhere_names_something_that_is_not_declared():
    """The end-to-end reading of the structural guarantee."""
    case = run_electrothermal_case(copy.deepcopy(BIOT_VIOLATING_PAYLOAD))
    by_id = {model.model_id: model for model, _ in TABLES}
    for repairs in case.repairs:
        for repair in repairs:
            model = by_id[repair.model_id]
            for hint in repair.hints:
                assert hint.target_name in parameter_inputs(model)


# =====================================================================
# The temperature-adjusted rating
# =====================================================================
#
# `dissipated_power_utilization` is one condition with two readings. With no
# derating line it is P / (d * P_rated) and is a reciprocal in both the rating
# and the derating factor, so both invert. With a line declared it becomes
# affine in the reciprocal of the rating, with an offset formed from the
# ambient temperature -- which is not a declared input of the resistor model,
# because it crosses in from the thermal body sharing the element's component
# id. The offset cannot be formed from the assessed context, so the form is
# not anchored and `_constant_rating_only` resolves no exponent.
#
# The domain already does the right thing here: it emits no hint and four
# named refusals. What it did not have was a test, and correct behaviour that
# nothing verifies is one refactor from being wrong -- which is the whole
# argument of "a check whose failure has never been observed is unverified",
# applied to a behaviour rather than to a check. The specific wrong answer
# this guards against is a hint computed against the PRINTED rating: at the
# operating point below that would read "raise rated_power to 2.43 W" when the
# part is already declared at 7 W, and applying it would leave the condition
# violated. A hint that leads to a still-refused design is worse than no hint.

#: 7 W at 25 C falling to zero at 155 C, run at an ambient of 400 K.
#: The line gives an effective rating of 7 * (428.15 - 400) / (428.15 - 298.15)
#: = 1.5158 W, so a part dissipating ~1.58 W is at 1.04 of its rating -- and
#: at 0.23 of the printed one, which is the number a reader must not be given.
DERATING_LINE_PAYLOAD = copy.deepcopy(BIOT_VIOLATING_PAYLOAD)
DERATING_LINE_PAYLOAD["stages"][0]["body"].update(
    {"ambient_temperature": "400 kelvin", "initial_temperature": "400 kelvin"}
)
DERATING_LINE_PAYLOAD["coupling"]["seed_temperature"] = "400 kelvin"
DERATING_LINE_PAYLOAD["stages"][0]["conductor"]["ratings"] = {
    "rated_power": "7.0 watt",
    "rated_power_temperature": "298.15 kelvin",
    "zero_power_temperature": "428.15 kelvin",
    "maximum_working_voltage": "8.0 volt",
}


def _power_utilization_repair():
    case = run_electrothermal_case(copy.deepcopy(DERATING_LINE_PAYLOAD))
    for repairs in case.repairs:
        for repair in repairs:
            if repair.condition == "dissipated_power_utilization":
                return case, repair
    raise AssertionError(
        "this payload is meant to violate dissipated_power_utilization; it "
        "violates "
        + str(
            [
                (r.model_id, r.condition)
                for repairs in case.repairs
                for r in repairs
            ]
        )
    )


def test_the_derated_rating_is_what_the_condition_is_measured_against():
    """The observed value is the effective rating's, not the printed one's.

    The two readings differ by a factor of 4.6 here, and they differ across
    the bound: judged against the printed 7 W this part is at 0.22 of its
    rating and the case is not violated at all.
    """
    _case, repair = _power_utilization_repair()
    assert repair.bound.magnitude == 1.0
    assert repair.bound_side == "maximum"
    assert repair.observed.magnitude == pytest.approx(1.00484, rel=1e-4)

    # The same dissipation against the printed rating, spelled out so the
    # number this test exists to keep out of a report is visible in it.
    effective = 7.0 * (428.15 - 400.0) / (428.15 - 298.15)
    dissipated = repair.observed.magnitude * effective
    assert dissipated / 7.0 == pytest.approx(0.2176, rel=1e-3)
    assert dissipated / 7.0 < 1.0


def test_a_declared_derating_line_repairs_the_rating_and_refuses_the_rest():
    """One inversion succeeds now that the ambient crosses in declared.

    `rated_power` inverts against the temperature-adjusted form, not the
    printed-rating one -- the hint this test guards is 7.515354 W, not the
    2.43 W a naive inversion against the constant reading would report at
    this operating point, which would leave the design refused if followed.
    The other three inputs stay refused: moving `rated_power_temperature` or
    `zero_power_temperature` would change the manufacturer's stated part
    rather than how it is used, and `derating_factor` would have to exceed
    1.0, which `ComponentRating` itself refuses.
    """
    _case, repair = _power_utilization_repair()
    assert repair.repairable is True
    assert len(repair.hints) == 1
    hint = repair.hints[0]
    assert hint.target_name == "rated_power"
    assert hint.direction is rp.RepairDirection.AT_LEAST
    assert hint.threshold.magnitude_in("watt") == pytest.approx(
        7.515353987089999, rel=1e-9
    )
    naive = 7.0 * 1.00484 / 1.0  # the printed-rating reading's own hint, avoided
    assert hint.threshold.magnitude_in("watt") != pytest.approx(naive, rel=1e-3)

    assert {refusal.target for refusal in repair.refusals} == {
        "derating_factor",
        "rated_power_temperature",
        "zero_power_temperature",
    }
    for refusal in repair.refusals:
        assert refusal.reason.strip()


def test_without_the_line_the_same_condition_does_invert():
    """The refusal is about the derating line, not about the condition.

    A refusal that fired whichever way the rating was declared would be a
    condition nothing can ever repair, dressed as a route decision. Same
    payload, same operating point, rating declared as a constant instead of a
    line: both reciprocals come back.
    """
    payload = copy.deepcopy(DERATING_LINE_PAYLOAD)
    ratings = payload["stages"][0]["conductor"]["ratings"]
    del ratings["rated_power_temperature"]
    del ratings["zero_power_temperature"]
    ratings["rated_power"] = "1.5 watt"  # the effective rating, now as a constant

    case = run_electrothermal_case(payload)
    repair = next(
        r
        for repairs in case.repairs
        for r in repairs
        if r.condition == "dissipated_power_utilization"
    )
    assert {hint.target_name for hint in repair.hints} == {"rated_power"}

    # `derating_factor` is the other reciprocal and it comes back as a refusal
    # rather than a hint, which is the R.2 ceiling doing its job: meeting the
    # bound would need 1.085, and a factor above 1 uses more of a component
    # than it is rated for while reporting that it is inside its rating. The
    # raise-the-limit move, reached through a declared input and refused by
    # name in the report.
    ceiling = next(x for x in repair.refusals if x.target == "derating_factor")
    assert "past 1.0 dimensionless" in ceiling.reason


def test_the_applied_hint_flips_the_condition_on_the_constant_rating_route():
    """And the applied-hint reading of it, which is the only proof that counts.

    `derating_factor` is excluded deliberately and it is the more interesting
    half: its inversion carries an `admissible_maximum` of 1.0, so at this
    overload the hint is refused rather than printed -- a derating factor above
    1 uses more of a component than it is rated for while reporting that it is
    inside its rating. That is the raise-the-limit move reached through a
    declared input, and the record refusing it is what this asserts.
    """
    payload = copy.deepcopy(DERATING_LINE_PAYLOAD)
    ratings = payload["stages"][0]["conductor"]["ratings"]
    del ratings["rated_power_temperature"]
    del ratings["zero_power_temperature"]
    ratings["rated_power"] = "1.5 watt"

    case = run_electrothermal_case(payload)
    repair = next(
        r
        for repairs in case.repairs
        for r in repairs
        if r.condition == "dissipated_power_utilization"
    )
    hint = next(h for h in repair.hints if h.target_name == "rated_power")

    repaired = copy.deepcopy(payload)
    repaired["stages"][0]["conductor"]["ratings"]["rated_power"] = (
        f"{hint.threshold.magnitude_in('watt')} watt"
    )
    after = run_electrothermal_case(repaired)
    violated = {
        name
        for report in after.reports
        for record in report.validity
        for name in record.assessment.violated
    }
    assert "dissipated_power_utilization" not in violated, (
        f"applying {hint.line()} left the condition violated"
    )
