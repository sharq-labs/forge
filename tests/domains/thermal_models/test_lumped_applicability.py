"""When the lumped-capacity model applies, and when it only appears to.

Six applicability conditions, each with three tests — inside, outside, and
without the declaration that would settle it. The third is the one that matters
most: a model that answered IN_DOMAIN when nobody told it the body's
conductivity would be reporting the *absence of evidence* as evidence, and the
platform's whole claim is that it does not.

Each OUTSIDE test pushes exactly one condition out and asserts the violated
tuple to check that, so a threshold moved by accident cannot hide behind a
neighbour's failure.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.engcore.domains.electrical import material as mat
from src.engcore.domains.thermal_models import context as ctx
from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.scientific.errors import InvalidScientificProblem
from src.engcore.scientific.ir.problem import ScientificProblem
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.results.validation import ValidationOutcome
from src.engcore.scientific.solvers.protocol import ConvergenceState
from src.engcore.scientific.units.quantity import Quantity
from src.engcore.systems.electrothermal import coupled as cp

K = "kelvin"

#: A body for which every condition is decidable and satisfied: 2 mm of a
#: 200 W/(m K) metal, 100 cm^2 of surface, a low-emissivity finish, forced
#: cooling, and a melting point far above anything it will reach.
#:
#:   h  = 0.05 / 0.01                     = 5 W/(m^2 K)
#:   Bi = 5 * 0.002 / 200                 = 2.5e-5      (<= 0.1)
#:   tau = 2.5 / 0.05                     = 50 s
#:   t/tau = 120 / 50                     = 2.4
#:   Fo = 2.4 / 2.5e-5                    = 9.6e4       (>= 0.2)
#:
#: The forced-convection declaration is recorded because it is *true of this
#: body*, and it is why a 60 K constant-hA span is credible here. It buys the
#: declaration nothing: the 60 K bound below is what the condition reads.
FULLY_DECLARED = ctx.LumpedApplicabilityDeclaration(
    characteristic_length=Quantity(0.002, "meter"),
    surface_area=Quantity(0.01, "meter**2"),
    body_conductivity=Quantity(200.0, "watt/meter/kelvin"),
    surface_emissivity=Quantity(0.05, "dimensionless"),
    convection_regime=ctx.FORCED_CONVECTION,
    conductance_excursion_bound=Quantity(60.0, K),
    capacity_excursion_bound=Quantity(100.0, K),
    melting_temperature=Quantity(900.0, K),
    fluid_conductivity=Quantity(0.0261, "watt/meter/kelvin"),
    fluid_kinematic_viscosity=Quantity(1.589e-5, "meter**2/second"),
    fluid_prandtl_number=Quantity(0.707, "dimensionless"),
    fluid_velocity=Quantity(1.0, "meter/second"),
    convection_length=Quantity(0.6, "meter"),
)

#: The operating point every test below assesses at: a 1 W input into a body
#: sitting at its 300 K ambient, so T_ss = 300 + 1/0.05 = 320 K.
AMBIENT = Quantity(300.0, K)
INITIAL = Quantity(300.0, K)
HEAT_INPUT = Quantity(1.0, "watt")


def body(declaration=FULLY_DECLARED, *, duration=120.0, conductance=0.05):
    return lump.ThermalBody(
        body_id="B1",
        heat_capacity=Quantity(2.5, "joule/kelvin"),
        ambient_conductance=Quantity(conductance, "watt/kelvin"),
        ambient_temperature=AMBIENT,
        initial_temperature=INITIAL,
        duration=Quantity(duration, "second"),
        applicability=declaration,
    )


def declared(**overrides):
    """The fully declared body with one or more facts replaced or removed.

    Built by copying every field off ``FULLY_DECLARED`` rather than by naming
    them, so a field added to the record joins this helper automatically. The
    hand-written list it replaced silently dropped the six convection fields
    when they were added, and every test using it then measured a body that
    was not fully declared.
    """
    fields = {
        field.name: getattr(FULLY_DECLARED, field.name)
        for field in dataclasses.fields(FULLY_DECLARED)
    }
    fields.update(overrides)
    return ctx.LumpedApplicabilityDeclaration(**fields)


def assess(thermal_body, *, heat_input=HEAT_INPUT):
    problem = lump.build_lumped_thermal_problem(thermal_body)
    return lump.assess_lumped_validity(
        problem,
        initial_temperature=thermal_body.initial_temperature,
        ambient_temperature=thermal_body.ambient_temperature,
        heat_input=heat_input,
    )


def dimensionless(value):
    return value.magnitude_in("dimensionless")


def _condition(name):
    return next(
        c for c in lump.LUMPED_CAPACITY_MODEL.validity.conditions if c.name == name
    )


# =====================================================================
# The baseline: everything decidable, everything satisfied
# =====================================================================

def test_a_fully_declared_body_at_a_benign_operating_point_is_in_domain():
    assessment = assess(body())
    assert assessment.status is ValidityStatus.IN_DOMAIN
    assert assessment.violated == ()
    assert assessment.unknown == ()
    # Every declared condition actually ran: none was skipped into silence.
    assert set(assessment.satisfied) == {
        c.name for c in lump.LUMPED_CAPACITY_MODEL.validity.conditions
    }


def test_a_body_that_declares_nothing_beyond_c_and_ha_is_unknown_not_valid():
    """The gap this milestone closes, stated as one assertion.

    Before the applicability conditions existed, this body reported IN_DOMAIN
    on the strength of two positivity checks. It now reports UNKNOWN, and the
    six conditions it cannot answer are named.
    """
    assessment = assess(body(ctx.LumpedApplicabilityDeclaration()))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert set(assessment.unknown) == {
        ctx.BIOT_NUMBER,
        ctx.INTERNAL_FOURIER_NUMBER,
        ctx.CONDUCTANCE_EXCURSION_RATIO,
        ctx.CAPACITY_EXCURSION_RATIO,
        ctx.RADIATION_TO_CONVECTION_RATIO,
        ctx.MELTING_TEMPERATURE_UTILIZATION,
        # Neither route to a characteristic length was declared, so whether
        # the two agree is genuinely unanswerable — unlike the single-route
        # case, where there is nothing to contradict.
        ctx.GEOMETRY_ROUTE_RATIO,
        # And where hA came from. A body that declares a conductance and
        # nothing else has not said whether it is a correlation, a measurement
        # or a guess, so no route resolves and all three stay unanswerable.
        ctx.CONVECTION_FLOW_RANGE,
        ctx.CONVECTION_PROPERTY_RANGE,
        ctx.CONVECTION_AGREEMENT_RATIO,
    }
    # The two old positivity checks still pass, and still prove nothing about
    # whether the lumped approximation holds.
    assert set(assessment.satisfied) == {
        lump.HEAT_CAPACITY,
        lump.AMBIENT_CONDUCTANCE,
    }


# =====================================================================
# Condition 1 — Biot number
# =====================================================================

def test_lumped_model_accepts_a_thin_high_conductivity_body_by_biot_number():
    """2 mm of a 200 W/(m K) metal: Bi = 2.5e-5, three decades inside 0.1."""
    assessment = assess(body())
    assert ctx.BIOT_NUMBER in assessment.satisfied
    assert assessment.status is ValidityStatus.IN_DOMAIN


def test_lumped_model_rejects_a_thick_low_conductivity_body_by_biot_number():
    """50 mm of a 0.2 W/(m K) insulator: Bi = 1.25, twelve times the limit.

    This is the case the model used to call IN_DOMAIN. Internal conduction
    dominates the surface exchange by more than an order of magnitude, so the
    body is nowhere near isothermal and a single temperature does not describe
    it.
    """
    assessment = assess(
        body(
            declared(
                characteristic_length=Quantity(0.05, "meter"),
                body_conductivity=Quantity(0.2, "watt/meter/kelvin"),
            )
        )
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (ctx.BIOT_NUMBER,)


def test_biot_number_is_unknown_when_the_body_declares_no_conductivity():
    """No k, no Bi — and no Fo either, because Fo is defined through Bi."""
    assessment = assess(body(declared(body_conductivity=None)))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert ctx.BIOT_NUMBER in assessment.unknown
    assert ctx.INTERNAL_FOURIER_NUMBER in assessment.unknown
    assert assessment.violated == ()


def test_the_biot_limit_is_a_named_constant_at_the_textbook_value():
    assert lump.LUMPED_BIOT_LIMIT.magnitude_in("dimensionless") == 0.1
    condition = _condition(ctx.BIOT_NUMBER)
    assert condition.maximum == lump.LUMPED_BIOT_LIMIT
    assert condition.minimum is None
    assert "5.10" in condition.description


# =====================================================================
# Condition 2 — internal Fourier number (the transient horizon)
# =====================================================================

def test_lumped_model_accepts_a_horizon_that_outlasts_internal_diffusion():
    """t/tau = 2.4 against Bi = 2.5e-5 gives Fo ~ 1e5: the body has settled."""
    assessment = assess(body())
    assert ctx.INTERNAL_FOURIER_NUMBER in assessment.satisfied


def test_lumped_model_rejects_a_horizon_shorter_than_internal_diffusion():
    """Bi = 0.05 (inside the limit) with t = 0.1 s gives Fo = 0.04 < 0.2.

    A legitimately thin, isothermal-enough body asked about a horizon so short
    that its internal profile has not relaxed. Bi passes; the model still does
    not apply, which is why the two conditions are separate.
    """
    assessment = assess(
        body(
            declared(body_conductivity=Quantity(0.2, "watt/meter/kelvin")),
            duration=0.1,
        )
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (ctx.INTERNAL_FOURIER_NUMBER,)
    assert ctx.BIOT_NUMBER in assessment.satisfied


def test_internal_fourier_number_is_unknown_when_no_surface_area_is_declared():
    """The area is what splits the declared hA product into an h.

    Without it there is no coefficient, so no Biot number, so no Fourier
    number — a chain of omissions that ends in UNKNOWN and never in IN_DOMAIN.
    """
    assessment = assess(body(declared(surface_area=None)))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert ctx.INTERNAL_FOURIER_NUMBER in assessment.unknown
    assert assessment.violated == ()


def test_the_fourier_floor_is_a_named_constant_at_the_one_term_value():
    assert lump.LUMPED_MIN_FOURIER_NUMBER.magnitude_in("dimensionless") == 0.2
    condition = _condition(ctx.INTERNAL_FOURIER_NUMBER)
    assert condition.minimum == lump.LUMPED_MIN_FOURIER_NUMBER
    assert condition.maximum is None
    assert "5.5.2" in condition.description


def test_the_fourier_condition_claims_only_what_its_source_establishes():
    """The bound is Sec. 5.5.2's number used for Sec. 5.5.2's claim.

    Incropera's one-term criterion establishes that above Fo = 0.2 the exact
    series is within ~2 % of its first term. It does *not* establish that below
    0.2 a lumped model is wrong — at small Bi the higher modes carry O(Bi)
    amplitude and may be negligible long before they have decayed. An earlier
    revision asserted the stronger claim ("no lumped description has the right
    shape, however small Bi is") on this citation; the description must state
    the criterion it actually rests on and must not restore the overclaim.
    """
    description = _condition(ctx.INTERNAL_FOURIER_NUMBER).description
    # what the source supports
    assert "one-term approximation" in description
    assert "first term" in description
    # and the honest statement of what a failure means
    assert "not shown to be wrong" in description
    # the removed overclaim must not come back
    assert "however small Bi is" not in description


def test_no_upper_bound_is_placed_on_the_horizon_because_the_integration_is_exact():
    """A deliberate absence, asserted so it stays deliberate.

    The closed form integrates the linear balance exactly, so a long horizon
    introduces no error of its own. The long-horizon limitation is a
    constant-property one and is carried by the two excursion budgets instead.
    Inventing a `t/tau < 10` rule would have looked more thorough and meant
    less.
    """
    horizon = ctx.transient_horizon_ratio(
        duration=Quantity(1.0e6, "second"), time_constant=Quantity(50.0, "second")
    )
    assert horizon.magnitude_in("dimensionless") == pytest.approx(2.0e4)
    assert ctx.TRANSIENT_HORIZON_RATIO not in {
        c.name for c in lump.LUMPED_CAPACITY_MODEL.validity.conditions
    }
    # A 10 000-hour horizon on the fully declared body is still in domain.
    assert assess(body(duration=3.6e7)).status is ValidityStatus.IN_DOMAIN


# =====================================================================
# Condition 3 — the constant ambient-conductance budget
# =====================================================================

def test_lumped_model_accepts_an_excursion_inside_the_declared_hA_span():
    """A 20 K rise against the declared 60 K constant-hA span: a third of it."""
    assessment = assess(body())
    assert ctx.CONDUCTANCE_EXCURSION_RATIO in assessment.satisfied
    assert assessment.status is ValidityStatus.IN_DOMAIN


def test_lumped_model_rejects_a_natural_convection_excursion_beyond_its_bound():
    """A 20 K rise against a 5 K declared constant-hA span: four times over.

    Under free convection h follows the driving difference, so a constant hA
    over four times the span the caller supported is an extrapolation of the
    exchange law, not of the balance.
    """
    assessment = assess(
        body(
            declared(
                convection_regime=ctx.NATURAL_CONVECTION,
                conductance_excursion_bound=Quantity(5.0, K),
            )
        )
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (ctx.CONDUCTANCE_EXCURSION_RATIO,)


def test_conductance_budget_is_unknown_without_a_declared_bound():
    """No stated span, so the honest answer is UNKNOWN.

    The caller has not said how far a constant hA carries, and nothing in the
    declaration lets the model guess.
    """
    assessment = assess(body(declared(conductance_excursion_bound=None)))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (ctx.CONDUCTANCE_EXCURSION_RATIO,)
    assert assessment.violated == ()


# ---- the forced-convection bypass, closed ----------------------------
#
# These three are the regression tests for a real defect: the condition used
# to return 0.0 on a declared forced regime *before reading either argument*,
# so a caller could satisfy it with a bare string that no record could check
# and that never reached provenance.


def test_declared_forced_convection_no_longer_waives_the_declared_bound():
    """Forced regime, no bound, everything else supplied → UNKNOWN.

    The declaration is present and correct; it buys nothing. Before the fix
    this same body reported IN_DOMAIN on this condition with no bound and no
    operating point behind it.
    """
    forced_without_bound = declared(
        convection_regime=ctx.FORCED_CONVECTION,
        conductance_excursion_bound=None,
    )
    assert forced_without_bound.convection_regime == ctx.FORCED_CONVECTION
    assessment = assess(body(forced_without_bound))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (ctx.CONDUCTANCE_EXCURSION_RATIO,)
    assert ctx.CONDUCTANCE_EXCURSION_RATIO not in assessment.satisfied


def test_declared_forced_convection_no_longer_waives_the_operating_point():
    """Forced regime, a bound, but no heat input → UNKNOWN, not satisfied.

    A bound with nothing to compare it against decides nothing, whatever
    mechanism the caller says is setting the coefficient.
    """
    assessment = assess(body(), heat_input=None)
    assert assessment.status is ValidityStatus.UNKNOWN
    assert ctx.CONDUCTANCE_EXCURSION_RATIO in assessment.unknown


def test_declared_forced_convection_is_still_judged_against_its_own_bound():
    """Forced regime with a 5 K bound and a 20 K rise → OUTSIDE.

    The regime does not widen the budget. A caller who declares forced flow
    and then declares a narrow span is held to the span they declared.
    """
    assessment = assess(
        body(
            declared(
                convection_regime=ctx.FORCED_CONVECTION,
                conductance_excursion_bound=Quantity(5.0, K),
            )
        )
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (ctx.CONDUCTANCE_EXCURSION_RATIO,)


def test_the_declared_regime_changes_no_verdict_at_all():
    """Same numbers under 'forced', 'natural' and no declaration.

    The strongest form of the fix: the regime is not merely insufficient to
    satisfy the condition, it is not consulted. Three declarations that differ
    only in the regime produce three identical assessments.
    """
    verdicts = [
        assess(body(declared(convection_regime=regime)))
        for regime in (ctx.FORCED_CONVECTION, ctx.NATURAL_CONVECTION, None)
    ]
    assert {v.status for v in verdicts} == {ValidityStatus.IN_DOMAIN}
    assert len({v.satisfied for v in verdicts}) == 1


# =====================================================================
# Condition 4 — the constant heat-capacity budget
# =====================================================================

def test_lumped_model_accepts_a_temperature_span_inside_the_capacity_bound():
    """A 20 K traverse against a 100 K declared constant-C span."""
    assessment = assess(body())
    assert ctx.CAPACITY_EXCURSION_RATIO in assessment.satisfied


def test_lumped_model_rejects_a_temperature_span_beyond_the_capacity_bound():
    """A 20 K traverse against a 5 K declared span: c_p is not one number here."""
    assessment = assess(body(declared(capacity_excursion_bound=Quantity(5.0, K))))
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (ctx.CAPACITY_EXCURSION_RATIO,)


def test_capacity_budget_is_unknown_when_no_constant_capacity_span_is_declared():
    assessment = assess(body(declared(capacity_excursion_bound=None)))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (ctx.CAPACITY_EXCURSION_RATIO,)
    assert assessment.violated == ()


def test_the_two_excursion_budgets_are_separate_conditions_over_separate_spans():
    """One is about the surface, the other about the body. Not one condition.

    The surface budget is measured on |T - T_amb| and the capacity budget on
    |T_ss - T_0|; a body started away from its ambient makes the two differ,
    which is the case that proves they were not the same number all along.
    """
    hot_start = lump.ThermalBody(
        body_id="B1",
        heat_capacity=Quantity(2.5, "joule/kelvin"),
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
        ambient_temperature=Quantity(300.0, K),
        initial_temperature=Quantity(400.0, K),
        duration=Quantity(120.0, "second"),
        applicability=declared(
            convection_regime=ctx.NATURAL_CONVECTION,
            conductance_excursion_bound=Quantity(100.0, K),
        ),
    )
    context = lump.lumped_validity_context(
        lump.build_lumped_thermal_problem(hot_start),
        initial_temperature=hot_start.initial_temperature,
        ambient_temperature=hot_start.ambient_temperature,
        heat_input=HEAT_INPUT,
    )
    # surface: max(|400-300|, |320-300|) = 100 K over a 100 K bound
    assert context[ctx.CONDUCTANCE_EXCURSION_RATIO].magnitude_in(
        "dimensionless"
    ) == pytest.approx(1.0, rel=1e-12)
    # body: |320 - 400| = 80 K over a 100 K bound
    assert context[ctx.CAPACITY_EXCURSION_RATIO].magnitude_in(
        "dimensionless"
    ) == pytest.approx(0.8, rel=1e-12)


# =====================================================================
# Condition 5 — radiation against convection
# =====================================================================

def test_lumped_model_accepts_a_low_emissivity_surface_that_barely_radiates():
    """eps = 0.05 at 320 K into 300 K surroundings: h_r/h below 1 %."""
    assessment = assess(body())
    assert ctx.RADIATION_TO_CONVECTION_RATIO in assessment.satisfied


def test_lumped_model_rejects_a_high_emissivity_surface_that_radiates_as_much_as_it_convects():
    """eps = 0.9 gives h_r comparable to h, so 'no radiation' is simply false.

    The assumption is listed in the model's own text. This is the condition
    that makes it falsifiable instead of decorative.
    """
    assessment = assess(
        body(declared(surface_emissivity=Quantity(0.9, "dimensionless")))
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (ctx.RADIATION_TO_CONVECTION_RATIO,)


def test_radiation_share_is_unknown_when_no_emissivity_is_declared():
    assessment = assess(body(declared(surface_emissivity=None)))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (ctx.RADIATION_TO_CONVECTION_RATIO,)
    assert assessment.violated == ()


def test_the_radiation_limit_is_a_named_constant_and_the_condition_cites_eq_1_9():
    assert (
        lump.RADIATION_NEGLIGIBILITY_LIMIT.magnitude_in("dimensionless") == 0.1
    )
    condition = _condition(ctx.RADIATION_TO_CONVECTION_RATIO)
    assert condition.maximum == lump.RADIATION_NEGLIGIBILITY_LIMIT
    assert "1.9" in condition.description


# =====================================================================
# Condition 6 — phase change
# =====================================================================

def test_lumped_model_accepts_a_body_that_stays_far_below_its_melting_point():
    assessment = assess(body())
    assert ctx.MELTING_TEMPERATURE_UTILIZATION in assessment.satisfied


def test_lumped_model_rejects_a_body_driven_past_its_phase_change_temperature():
    """T_ss = 320 K against a 310 K melting point: there is no latent-heat term.

    The balance is not merely inaccurate above the phase change; it is
    describing a solid that is no longer there. Note that the *reported*
    end-of-interval temperature is below 310 K — the condition is judged on
    where the trajectory is heading, because a shorter horizon defers the
    phase change rather than preventing it.
    """
    assessment = assess(body(declared(melting_temperature=Quantity(310.0, K))))
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (ctx.MELTING_TEMPERATURE_UTILIZATION,)


def test_phase_change_margin_is_unknown_when_no_melting_point_is_declared():
    assessment = assess(body(declared(melting_temperature=None)))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (ctx.MELTING_TEMPERATURE_UTILIZATION,)
    assert assessment.violated == ()


# =====================================================================
# No condition can be bought by omission
# =====================================================================

def test_omitting_the_operating_point_cannot_produce_a_valid_verdict():
    """No heat input, so no steady state, so every state-dependent condition
    goes UNKNOWN — all four of them, with no exception carved out for a
    declared regime.

    The direction of travel is the whole point: removing information moves the
    verdict towards UNKNOWN and never towards IN_DOMAIN. Only the two purely
    geometric conditions, which never needed the operating point, stay
    satisfied.
    """
    assessment = assess(body(), heat_input=None)
    assert assessment.status is ValidityStatus.UNKNOWN
    assert set(assessment.unknown) == {
        ctx.CONDUCTANCE_EXCURSION_RATIO,
        ctx.CAPACITY_EXCURSION_RATIO,
        ctx.RADIATION_TO_CONVECTION_RATIO,
        ctx.MELTING_TEMPERATURE_UTILIZATION,
    }
    assert set(assessment.satisfied) == {
        lump.HEAT_CAPACITY,
        lump.AMBIENT_CONDUCTANCE,
        ctx.BIOT_NUMBER,
        ctx.INTERNAL_FOURIER_NUMBER,
        # Geometry alone decides this one: both routes are declared here and
        # they agree, and no operating point is needed to say so.
        ctx.GEOMETRY_ROUTE_RATIO,
        # All three convection conditions survive the loss of the operating
        # point, and ONLY because this body declares the FORCED route.
        # Re = u L / nu, the flat-plate Nusselt number and the coefficient it
        # implies contain no temperature difference at all: a flow-set
        # coefficient does not depend on how hard the surface is driven. The
        # same three go UNKNOWN on a free-convection body, where the Rayleigh
        # number needs the excursion — see the natural-route test below.
        ctx.CONVECTION_FLOW_RANGE,
        ctx.CONVECTION_PROPERTY_RANGE,
        ctx.CONVECTION_AGREEMENT_RATIO,
    }


@pytest.mark.parametrize(
    "removed",
    [
        {"body_conductivity": None},
        {"surface_area": None},
        {"characteristic_length": None},
        {"surface_emissivity": None},
        {"conductance_excursion_bound": None},
        {"capacity_excursion_bound": None},
        {"melting_temperature": None},
    ],
)
def test_removing_any_single_evidential_declaration_never_yields_in_domain(removed):
    """The invariant, checked one omission at a time.

    Seven of the declaration's nine fields carry evidence, and removing any one
    of them costs a condition. ``volume`` is the eighth and is the alternative
    route to ``characteristic_length`` rather than an independent fact.
    ``convection_regime`` is the ninth and is deliberately absent from this
    list: it is recorded intent, no condition reads it, and the test below
    asserts that removing it changes nothing — which is the point of the fix,
    not a hole in it.
    """
    assert assess(body(declared(**removed))).status is not ValidityStatus.IN_DOMAIN


def test_supplying_a_volume_and_an_area_reaches_the_same_verdict_as_a_length():
    """L_c = V/A_s is a real second route, not a documented one."""
    via_ratio = assess(
        body(
            declared(
                characteristic_length=None,
                volume=Quantity(2.0e-5, "meter**3"),
            )
        )
    )
    assert via_ratio.status is ValidityStatus.IN_DOMAIN
    assert set(via_ratio.satisfied) == set(assess(body()).satisfied)


# =====================================================================
# The problem record transports the evidence
# =====================================================================

def test_a_declared_body_emits_its_facts_as_problem_parameters():
    problem = lump.build_lumped_thermal_problem(body())
    names = {p.name for p in problem.parameters}
    assert {
        ctx.CHARACTERISTIC_LENGTH,
        ctx.SURFACE_AREA,
        ctx.BODY_CONDUCTIVITY,
        ctx.SURFACE_EMISSIVITY,
        ctx.CAPACITY_EXCURSION_BOUND,
        ctx.MELTING_TEMPERATURE,
    } <= names


def test_an_undeclared_body_emits_exactly_the_three_parameters_it_always_did():
    """Adding optional inputs did not widen the record for callers who declined."""
    problem = lump.build_lumped_thermal_problem(
        body(ctx.LumpedApplicabilityDeclaration())
    )
    assert [p.name for p in problem.parameters] == [
        lump.HEAT_CAPACITY,
        lump.AMBIENT_CONDUCTANCE,
        lump.DURATION,
    ]


def test_the_declared_problem_survives_serialization_with_its_verdict_intact():
    """A problem sent elsewhere and rebuilt supports the same assessment."""
    problem = lump.build_lumped_thermal_problem(body())
    restored = ScientificProblem.from_dict(problem.to_dict())
    assert restored.to_dict() == problem.to_dict()
    assert (
        lump.assess_lumped_validity(
            restored,
            initial_temperature=INITIAL,
            ambient_temperature=AMBIENT,
            heat_input=HEAT_INPUT,
        ).status
        is ValidityStatus.IN_DOMAIN
    )


def test_the_optional_inputs_are_declared_on_the_model_and_are_not_required():
    """A reader holding only the record can see what unlocks which condition."""
    optional = {s.name for s in lump.LUMPED_CAPACITY_MODEL.inputs if not s.required}
    assert optional == {
        ctx.CHARACTERISTIC_LENGTH,
        ctx.BODY_VOLUME,
        ctx.SURFACE_AREA,
        ctx.BODY_CONDUCTIVITY,
        ctx.SURFACE_EMISSIVITY,
        ctx.CONDUCTANCE_EXCURSION_BOUND,
        ctx.CAPACITY_EXCURSION_BOUND,
        ctx.MELTING_TEMPERATURE,
        ctx.FLUID_CONDUCTIVITY,
        ctx.FLUID_VISCOSITY,
        ctx.FLUID_PRANDTL_NUMBER,
        ctx.FLUID_EXPANSION_COEFFICIENT,
        ctx.FLUID_VELOCITY,
        ctx.CONVECTION_LENGTH,
    }
    # and a problem that omits every one of them still binds cleanly
    bare = lump.build_lumped_thermal_problem(
        body(ctx.LumpedApplicabilityDeclaration())
    )
    assert lump.LUMPED_CAPACITY_MODEL.check_against(bare).is_satisfied
    assert lump.LUMPED_CAPACITY_MODEL.check_against(
        lump.build_lumped_thermal_problem(body())
    ).is_satisfied


def test_a_problem_that_contradicts_the_bound_bodys_declaration_is_refused():
    """The provenance guard, extended to the applicability facts."""
    solver = lump.LumpedThermalSolver()
    declared_body = body()
    mismatched = lump.build_lumped_thermal_problem(
        body(declared(body_conductivity=Quantity(15.0, "watt/meter/kelvin")))
    )
    solver.bind_body(
        declared_body, mismatched.problem_id, heat_input=HEAT_INPUT
    )
    with pytest.raises(InvalidScientificProblem):
        solver.prepare(mismatched)


# =====================================================================
# Integration — the coupled run is untouched by any of this
# =====================================================================

def conductor(component_id="R1"):
    return mat.TemperatureDependentConductor(
        component_id=component_id,
        reference_resistance=Quantity(10.0, "ohm"),
        temperature_coefficient=Quantity(0.00393, "1/kelvin"),
        reference_temperature=Quantity(293.15, K),
    )


#: The declaration that keeps the coupled operating point in domain. The body
#: settles towards T_ss = 300 + 2.1213/0.05 = 342.43 K, a 42.43 K rise over the
#: ambient, so a 60 K constant-hA span, a 100 K constant-capacity span and a
#: 900 K melting point all hold.
COUPLED_DECLARATION = ctx.LumpedApplicabilityDeclaration(
    characteristic_length=Quantity(0.002, "meter"),
    surface_area=Quantity(0.01, "meter**2"),
    body_conductivity=Quantity(200.0, "watt/meter/kelvin"),
    surface_emissivity=Quantity(0.05, "dimensionless"),
    convection_regime=ctx.FORCED_CONVECTION,
    conductance_excursion_bound=Quantity(60.0, K),
    capacity_excursion_bound=Quantity(100.0, K),
    melting_temperature=Quantity(900.0, K),
    fluid_conductivity=Quantity(0.0261, "watt/meter/kelvin"),
    fluid_kinematic_viscosity=Quantity(1.589e-5, "meter**2/second"),
    fluid_prandtl_number=Quantity(0.707, "dimensionless"),
    fluid_velocity=Quantity(1.0, "meter/second"),
    convection_length=Quantity(0.6, "meter"),
)


def coupled_body(declaration):
    return lump.ThermalBody(
        body_id="R1",
        heat_capacity=Quantity(2.5, "joule/kelvin"),
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
        ambient_temperature=Quantity(300.0, K),
        initial_temperature=Quantity(300.0, K),
        duration=Quantity(120.0, "second"),
        applicability=declaration,
    )


def run_coupled(declaration, run_id):
    system = cp.CoupledElectroThermalSystem(
        stages=(cp.CoupledStage(conductor(), coupled_body(declaration)),),
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


#: The preregistered CASE A trace of the electro-thermal vertical milestone.
#: Reproduced here, not recomputed: if declaring applicability changed any of
#: these, the declaration would have become an input to the physics.
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
    assert run.final.result_for(prop).value("resistance").magnitude_in(
        "ohm"
    ) == pytest.approx(CASE_A_RESISTANCE, abs=1e-6)
    assert run.final.result_for(electrical).value(
        "resistor_power:R1"
    ).magnitude_in("watt") == pytest.approx(CASE_A_POWER, abs=1e-6)
    assert run.final.result_for(thermal).value(
        lump.TEMPERATURE_METRIC
    ).magnitude_in(K) == pytest.approx(CASE_A_TEMPERATURE, abs=1e-6)


def test_lumped_applicability_leaves_the_coupled_run_numerically_identical():
    """Three independent claims about one run, asserted one at a time.

    1. **Numerical convergence** — every sub-solve reports the state it always
       reported, and the numbers are the preregistered CASE A trace.
    2. **Coupling convergence** — the fixed point is reached in the same ten
       iterations, to the same tolerance.
    3. **Scientific validity** — IN_DOMAIN, which is a *third* verdict and is
       not implied by either of the first two.
    """
    run, problems = run_coupled(COUPLED_DECLARATION, "lumped-in-domain")

    # 1. numerical convergence of the sub-solves
    assert {r.convergence for i in run.iterations for r in i.results} == {
        ConvergenceState.CONVERGED,
        ConvergenceState.NOT_APPLICABLE,
    }
    _assert_case_a_trace(run, problems)

    # 2. coupling convergence — a different question, a different record
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert run.criterion_met is True
    assert run.iterations_run == CASE_A_ITERATIONS
    assert run.final_iterate_change.magnitude_in(K) <= 1e-6

    # 3. scientific validity — a third question, answered separately
    electrical = problems[0].problem_id
    power = run.final.result_for(electrical).value("resistor_power:R1")
    assessment = lump.assess_lumped_validity(
        problems[2],
        initial_temperature=Quantity(300.0, K),
        ambient_temperature=Quantity(300.0, K),
        heat_input=power,
    )
    assert assessment.status is ValidityStatus.IN_DOMAIN


def test_a_coupled_run_can_converge_twice_over_and_still_be_outside_the_domain():
    """The same run with one declaration changed: a 330 K melting point.

    Nothing numerical moves — the melting point is not in the balance — so the
    trace, the sub-solve convergence and the coupling outcome are bit-for-bit
    the assertions above. Only the validity verdict changes, which is the
    separation the platform exists to make: a converged coupling of converged
    solves of an inapplicable model.
    """
    baseline, _ = run_coupled(COUPLED_DECLARATION, "lumped-baseline")
    run, problems = run_coupled(
        ctx.LumpedApplicabilityDeclaration(
            characteristic_length=COUPLED_DECLARATION.characteristic_length,
            surface_area=COUPLED_DECLARATION.surface_area,
            body_conductivity=COUPLED_DECLARATION.body_conductivity,
            surface_emissivity=COUPLED_DECLARATION.surface_emissivity,
            convection_regime=COUPLED_DECLARATION.convection_regime,
            conductance_excursion_bound=(
                COUPLED_DECLARATION.conductance_excursion_bound
            ),
            capacity_excursion_bound=COUPLED_DECLARATION.capacity_excursion_bound,
            melting_temperature=Quantity(330.0, K),
        ),
        "lumped-outside",
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
    electrical = problems[0].problem_id
    power = run.final.result_for(electrical).value("resistor_power:R1")
    assessment = lump.assess_lumped_validity(
        problems[2],
        initial_temperature=Quantity(300.0, K),
        ambient_temperature=Quantity(300.0, K),
        heat_input=power,
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (ctx.MELTING_TEMPERATURE_UTILIZATION,)
    # and no sub-result was downgraded on account of it
    for iteration in run.iterations:
        for result in iteration.results:
            assert result.validation.status is not ValidationOutcome.FAIL


# =====================================================================
# Two routes to one characteristic length must describe one body
# =====================================================================

def _geo(lc, vol, area=0.01):
    return ctx.derived_lumped_quantities({
        ctx.CHARACTERISTIC_LENGTH: Quantity(lc, "meter"),
        ctx.BODY_VOLUME: Quantity(vol, "meter**3"),
        ctx.SURFACE_AREA: Quantity(area, "meter**2"),
    }).get(ctx.GEOMETRY_ROUTE_RATIO)


def test_two_routes_that_agree_are_satisfied():
    ratio = _geo(0.002, 0.002 * 0.01)
    assert dimensionless(ratio) == pytest.approx(1.0, rel=1e-12)


def test_a_shape_factor_apart_is_still_one_body():
    """A sphere declares r_o where V/A_s is r_o/3, and both are correct.

    This is why the bound is a factor of 3 and not a percentage: the
    disagreement a convention can account for is set by geometry, not by
    measurement error.
    """
    for factor in (1.0, 2.0, 2.9):
        assert dimensionless(_geo(0.002 * factor, 0.002 * 0.01)) == (
            pytest.approx(factor, rel=1e-12)
        )
    assessment = assess(
        body(declared(characteristic_length=Quantity(0.004, "meter"),
                      volume=Quantity(0.002 * 0.01, "meter**3")))
    )
    assert ctx.GEOMETRY_ROUTE_RATIO in assessment.satisfied


def test_routes_that_disagree_beyond_any_shape_are_a_finding():
    """10x apart: no standard shape reconciles a length and a volume this far."""
    assessment = assess(
        body(declared(characteristic_length=Quantity(0.002, "meter"),
                      volume=Quantity(0.002 * 0.01 * 10, "meter**3")))
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert ctx.GEOMETRY_ROUTE_RATIO in assessment.violated


def test_the_disagreement_is_caught_in_both_directions():
    """Declaring the length too small is the dangerous direction and is caught.

    Below V/A_s the Biot number is understated and the model looks applicable
    when it may not be; above it the criterion is only made harder to pass.
    Both are refused, because nothing here can tell which convention was used.
    """
    for vol_factor in (10.0, 0.1):
        assessment = assess(
            body(declared(
                characteristic_length=Quantity(0.002, "meter"),
                volume=Quantity(0.002 * 0.01 * vol_factor, "meter**3"),
            ))
        )
        assert ctx.GEOMETRY_ROUTE_RATIO in assessment.violated


def test_one_route_alone_is_not_a_contradiction():
    """The alternative route must keep working, and a lone length must too.

    Reporting UNKNOWN here would demand all three fields from a model that has
    always accepted either route — a much larger claim than this condition is
    making.
    """
    via_volume = assess(
        body(declared(characteristic_length=None,
                      volume=Quantity(2.0e-5, "meter**3")))
    )
    assert via_volume.status is ValidityStatus.IN_DOMAIN
    assert ctx.GEOMETRY_ROUTE_RATIO in via_volume.satisfied

    only_length = ctx.derived_lumped_quantities({
        ctx.CHARACTERISTIC_LENGTH: Quantity(0.002, "meter"),
    })
    assert dimensionless(only_length[ctx.GEOMETRY_ROUTE_RATIO]) == 1.0


def test_neither_route_is_unknown_rather_than_agreement():
    derived = ctx.derived_lumped_quantities({
        ctx.SURFACE_AREA: Quantity(0.01, "meter**2"),
    })
    assert ctx.GEOMETRY_ROUTE_RATIO not in derived


def test_the_agreement_bound_is_a_named_factor_with_a_shape_reason():
    assert ctx.GEOMETRY_AGREEMENT_FACTOR.magnitude_in("dimensionless") == 3.0
    condition = next(
        c for c in lump.LUMPED_CAPACITY_MODEL.validity.conditions
        if c.name == ctx.GEOMETRY_ROUTE_RATIO
    )
    assert condition.maximum == ctx.GEOMETRY_AGREEMENT_FACTOR
    assert dimensionless(condition.minimum) == pytest.approx(1.0 / 3.0)
    assert "sphere" in condition.description
