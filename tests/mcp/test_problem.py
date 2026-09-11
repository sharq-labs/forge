"""What a JSON case description may and may not leave unsaid.

The other half of `test_evidence.py`. That file asks what a report may claim;
this one asks what a payload must state before a report exists at all.

Two things are asserted throughout and are worth naming up front. **A refusal
must name the field**, because the caller is frequently an agent that cannot
read the source and has no other way to find its mistake. And **a refusal must
be a refusal**, not a quiet reinterpretation: the test at
`test_ignoring_an_unknown_field_would_have_changed_the_verdict` is the one that
says why, by measuring the verdict the tolerant alternative would have
produced.
"""

from __future__ import annotations

import copy
import json

import pytest

from engcore.domains.electrical import material as mat
from engcore.domains.electrical import dc_applicability as dc_app
from engcore.domains.electrical.dc import models as dc_models
from engcore.domains.thermal_models import context as ctx
from engcore.domains.thermal_models import lumped as lump
from engcore.mcp import (
    COUPLING_SUPPLIED_INPUTS,
    CredibilityVerdict,
    MalformedPayloadError,
    MissingFieldError,
    MissingUnitError,
    ProblemPayloadError,
    UnknownFieldError,
    WrongDimensionError,
    build_electrothermal_problems,
    build_electrothermal_system,
    describe_electrothermal_case,
    example_electrothermal_payload,
    example_over_rating_payload,
    run_electrothermal_case,
)
from engcore.mcp import evidence
# Not re-exported from the package: the check name and the
# level-withholding rule are this boundary's internals, and the tests
# that pin them import them where they live.
from engcore.mcp.problem import (
    CROSS_SOLVER_CHECK_NAME,
    _withhold_level,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.models.definition import ValidityStatus
from engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
)
from engcore.scientific.units.quantity import Quantity, dimensionality
from engcore.systems.electrothermal import coupled as cp

K = "kelvin"

#: The payload equivalent of `test_evidence.py`'s APPLICABLE case, field for
#: field. Kept separate from `example_electrothermal_payload()` — which also
#: declares material limits and a volume — so that the verdict comparison
#: below is against the *same* case and not merely a similar one.
APPLICABLE_PAYLOAD = {
    "source_voltage": "5 volt",
    "stages": [
        {
            "component_id": "R1",
            "conductor": {
                "reference_resistance": "10 ohm",
                "temperature_coefficient": "0.00393 1/kelvin",
                "reference_temperature": "293.15 kelvin",
            },
            "body": {
                "heat_capacity": "2.5 joule/kelvin",
                "ambient_conductance": "0.05 watt/kelvin",
                "ambient_temperature": "300 kelvin",
                "initial_temperature": "300 kelvin",
                "duration": "120 second",
                "applicability": {
                    "characteristic_length": "0.002 meter",
                    "surface_area": "0.01 meter**2",
                    "body_conductivity": "200 watt/meter/kelvin",
                    "surface_emissivity": "0.05 dimensionless",
                    "convection_regime": "forced",
                    "fluid_conductivity": "0.0261 watt/meter/kelvin",
                    "fluid_kinematic_viscosity": "1.589e-5 meter**2/second",
                    "fluid_prandtl_number": "0.707 dimensionless",
                    "fluid_velocity": "1 meter/second",
                    "convection_length": "0.6 meter",
                    "conductance_excursion_bound": "60 kelvin",
                    "capacity_excursion_bound": "100 kelvin",
                    "melting_temperature": "900 kelvin",
                },
            },
        }
    ],
    "coupling": {
        "seed_temperature": "300 kelvin",
        "tolerance": "1e-6 kelvin",
        "max_iterations": 50,
    },
}

#: 50 mm of a 0.2 W/(m K) insulator: Bi = 1.25, twelve times the limit. The
#: numbers are `test_evidence.py`'s BIOT_VIOLATING, and the point here is that
#: a violated bound is a *finding* — the only case whose verdict is
#: NOT_SUPPORTED, and therefore the only one that can demonstrate what
#: swallowing a typo would cost.
BIOT_VIOLATING_PAYLOAD = copy.deepcopy(APPLICABLE_PAYLOAD)
BIOT_VIOLATING_PAYLOAD["stages"][0]["body"]["applicability"].update(
    {"characteristic_length": "0.05 meter", "body_conductivity": "0.2 watt/meter/kelvin"}
)

#: Every model this boundary can bind, including the two companion records.
#: The companions are *attachable* rather than always attached: they appear in
#: a report only when the caller declared something they read, which is what
#: `ATTACHED_MODELS` below is for.
MODELS = (
    lump.LUMPED_CAPACITY_MODEL,
    mat.LINEAR_TCR_MODEL,
    mat.RATED_LINEAR_TCR_MODEL,
    dc_models.IDEAL_VOLTAGE_SOURCE_MODEL,
    dc_models.RESISTOR_OHM_MODEL,
    dc_models.KCL_MODEL,
    dc_app.SELF_HEATED_RESISTOR_MODEL,
    dc_app.REGULATED_VOLTAGE_SOURCE_MODEL,
)

#: What the shipped example actually attaches. It declares the `element` block
#: and so raises `electrical.dc.self_heated_resistor`; it declares no
#: `source_regulation`, because this repository's component data carries no
#: output impedance for the part the example's supply names, so
#: `electrical.dc.regulated_voltage_source` stays off the report.
ATTACHED_MODELS = tuple(
    m for m in MODELS
    if m.model_id != dc_app.REGULATED_VOLTAGE_SOURCE_MODEL.model_id
)


#: The same body on the FREE-CONVECTION route. Air near 300 K over a 67 mm
#: plate: beta = 2/(T_ss + T_amb) for an ideal gas at the film temperature,
#: Ra = 1.0e6, Nu = 0.68 + 0.670 Ra^(1/4)/[1 + (0.492/Pr)^(9/16)]^(4/9) = 16.93
#: and h = Nu k_f / L = 5.00 W/(m^2 K), the same 0.05 W/K over 0.01 m^2.
#:
#: Needed because a declaration cannot carry both an expansion coefficient and
#: a velocity -- that is mixed convection and the record refuses it -- so one
#: payload cannot witness what both route fields unlock.
NATURAL_CONVECTION_PAYLOAD = copy.deepcopy(APPLICABLE_PAYLOAD)
NATURAL_CONVECTION_PAYLOAD["stages"][0]["body"]["applicability"].pop(
    "fluid_velocity"
)
NATURAL_CONVECTION_PAYLOAD["stages"][0]["body"]["applicability"].update(
    {
        "convection_regime": "natural",
        "fluid_expansion_coefficient": "0.00313196 1/kelvin",
        "convection_length": "0.067048 meter",
        "fluid_conductivity": "0.0197968 watt/meter/kelvin",
    }
)


def payload_without(section_path, key, *, payload=None):
    """A deep copy of a payload with one key removed."""
    payload = copy.deepcopy(APPLICABLE_PAYLOAD if payload is None else payload)
    target = payload
    for step in section_path:
        target = target[step]
    target.pop(key, None)
    return payload


def payload_with(section_path, key, value):
    payload = copy.deepcopy(APPLICABLE_PAYLOAD)
    target = payload
    for step in section_path:
        target = target[step]
    target[key] = value
    return payload


APPLICABILITY_PATH = ("stages", 0, "body", "applicability")
BODY_PATH = ("stages", 0, "body")
CONDUCTOR_PATH = ("stages", 0, "conductor")


# =====================================================================
# A well-formed payload runs, and agrees with the hand-built case
# =====================================================================

def test_a_well_formed_payload_builds_the_three_problems():
    problems = build_electrothermal_problems(APPLICABLE_PAYLOAD)
    assert [p.problem_id for p in problems] == [
        "electrical_dc:electrothermal-series-R1",
        "resistance-tcr-R1",
        "thermal-lumped-R1",
    ]


def test_a_well_formed_payload_runs_and_matches_the_hand_built_case():
    """Same numbers, same verdict as the APPLICABLE case in test_evidence.py.

    That case is assembled in Python from the domain records directly. If this
    boundary changed any value on the way through — a unit converted wrongly,
    an optional declaration dropped, a default invented — the coupled fixed
    point would land somewhere else, and 338.577018 K is a sharp enough
    instrument to say so.
    """
    outcome = run_electrothermal_case(APPLICABLE_PAYLOAD, run_id="payload-applicable")
    report = outcome.reports[0]

    assert report.values["final_temperature"].magnitude_in(K) == pytest.approx(
        338.577018, abs=1e-6
    )
    assert report.violated_conditions == ()
    assert report.failed_checks == () and report.not_run_checks == ()
    # The lumped solver's reference comparison establishes a level, exactly as
    # in the hand-built case and for the same reason. The payload boundary
    # neither adds nor removes evidence.
    assert report.attained_levels == frozenset(
        {ValidationLevel.ANALYTICALLY_VERIFIED}
    )

    # INSUFFICIENT_EVIDENCE and not SUPPORTED, and the reason is in the report
    # rather than in this comment: since the report is assembled over the
    # dependency closure it covers the electrical models too, and nothing in
    # this payload declares a resistor's rated dissipation, a source's current
    # limit, or any condition at all for Kirchhoff's law. The thermal model is
    # still in domain, and the gaps are named.
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert report.unknown_conditions
    thermal = next(
        r for r in report.validity
        if r.model_id == lump.LUMPED_CAPACITY_MODEL.model_id
    )
    assert thermal.status is ValidityStatus.IN_DOMAIN
    assert thermal.assessment.unknown == ()


def test_a_violated_bound_reaches_the_report_as_a_finding():
    outcome = run_electrothermal_case(BIOT_VIOLATING_PAYLOAD, run_id="payload-biot")
    report = outcome.reports[0]
    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED
    assert report.violated_conditions == (
        (lump.LUMPED_CAPACITY_MODEL.model_id, ctx.BIOT_NUMBER),
    )


#: A cold-soaked part warming towards a warmer ambient. It starts 93.15 K from
#: its 293.15 K reference and converges 37.41 K from it, so a 60 K band covers
#: where it ends and not where it began — which is the only shape that can tell
#: a path-assessed band from an endpoint-assessed one.
#: The thermal excursion budgets are widened to cover the 143 K span this body
#: traverses, so that the *only* thing the 200 K start violates is the material
#: band. Left at their default 60 K and 100 K the run is refused three times
#: over and the test could not tell which reading earned the refusal.
COLD_START_PAYLOAD = copy.deepcopy(APPLICABLE_PAYLOAD)
COLD_START_PAYLOAD["stages"][0]["body"]["initial_temperature"] = "200 kelvin"
COLD_START_PAYLOAD["stages"][0]["body"]["applicability"].update(
    {
        "conductance_excursion_bound": "150 kelvin",
        "capacity_excursion_bound": "200 kelvin",
    }
)
COLD_START_PAYLOAD["stages"][0]["conductor"]["limits"] = {
    "linearization_band": "60 kelvin",
    "maximum_operating_temperature": "450 kelvin",
    "debye_temperature": "343 kelvin",
}


def test_the_band_is_assessed_over_the_path_not_at_the_converged_endpoint():
    """A run that begins outside its linear band is refused for beginning there.

    The body starts at 200 K and converges to 330.56 K against a 293.15 K
    reference and a declared 60 K band. The endpoint is 37.41 K out — 0.62 of
    the band, comfortably inside. The start is 93.15 K out — 1.55 of it. The
    same single alpha produced R(T) at both, so the band has to hold at both,
    and a reading taken only where the run stops would report the 0.62 and
    never the 1.55.

    This is the assertion that ``_material_assessments`` hands the domain the
    furthest state and not just the converged one. If a future edit dropped
    that argument the endpoint alone would satisfy the band, and every other
    condition in this report would still pass — so nothing else here would
    notice.
    """
    outcome = run_electrothermal_case(COLD_START_PAYLOAD, run_id="payload-cold")
    report = outcome.reports[0]

    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED
    assert report.violated_conditions == (
        (mat.RATED_LINEAR_TCR_MODEL.model_id, mat.LINEARIZATION_EXCURSION_RATIO),
    )
    assert report.values["final_temperature"].magnitude_in(K) == pytest.approx(
        330.5643, abs=1e-3
    )

    # The distinction itself: the same conductor, the same converged
    # temperature, assessed at the endpoint alone, satisfies the band. The
    # refusal above is the path and nothing else.
    problem = mat.build_resistance_problem(
        mat.TemperatureDependentConductor(
            component_id="R1",
            reference_resistance=Quantity(10.0, "ohm"),
            temperature_coefficient=Quantity(0.00393, "1/kelvin"),
            reference_temperature=Quantity(293.15, K),
            limits=mat.MaterialLimits(
                linearization_band=Quantity(60.0, K),
                maximum_operating_temperature=Quantity(450.0, K),
                debye_temperature=Quantity(343.0, K),
            ),
        )
    )
    endpoint_only = mat.assess_rated_resistance_validity(
        problem, Quantity(330.5643, K)
    )
    assert mat.LINEARIZATION_EXCURSION_RATIO in endpoint_only.satisfied


def test_a_run_that_stays_inside_its_band_the_whole_way_is_still_accepted():
    """The other half: assessing the path must not refuse a sound case.

    Same body, same 60 K band, started at 300 K instead of 200 K. Both
    endpoints are inside the band now, so the wider reading finds nothing and
    the band is satisfied — the guard against a change that simply refuses
    more.
    """
    payload = copy.deepcopy(COLD_START_PAYLOAD)
    payload["stages"][0]["body"]["initial_temperature"] = "300 kelvin"
    report = run_electrothermal_case(payload, run_id="payload-warm").reports[0]

    rated = next(
        record
        for record in report.validity
        if record.model_id == mat.RATED_LINEAR_TCR_MODEL.model_id
    )
    assert mat.LINEARIZATION_EXCURSION_RATIO in rated.assessment.satisfied
    assert mat.LINEARIZATION_EXCURSION_RATIO not in rated.assessment.violated


def test_the_declaration_is_carried_as_the_callers_claim():
    outcome = run_electrothermal_case(APPLICABLE_PAYLOAD, run_id="payload-declared")
    (declaration,) = outcome.reports[0].declarations
    assert declaration.source == "LumpedApplicabilityDeclaration"
    assert declaration.to_dict()["caller_asserted"] is True
    assert declaration.to_dict()["consumed_by_verdict"] is False


# =====================================================================
# Every physical value carries a unit
# =====================================================================

def test_a_bare_number_is_refused_and_the_error_names_the_field():
    with pytest.raises(MissingUnitError) as excinfo:
        build_electrothermal_system(payload_with(BODY_PATH, "heat_capacity", 2.5))
    message = str(excinfo.value)
    assert "stages[0].body.heat_capacity" in message
    assert "2.5" in message
    # and it says what to write instead, so the repair needs no second guess
    assert "joule / kelvin" in message
    assert "will not choose a unit on your behalf" in message


def test_a_bare_number_is_refused_everywhere_a_quantity_is_expected():
    """Not a special case for one field: the rule is the boundary's, not a check."""
    description = describe_electrothermal_case()
    quantity_fields = [f for f in description.fields if f.kind == "quantity"]
    assert len(quantity_fields) >= 15  # the rule is worth this much coverage

    for field in quantity_fields:
        if field.section == "stages[].body.applicability":
            path = APPLICABILITY_PATH
        elif field.section == "stages[].body":
            path = BODY_PATH
        elif field.section == "stages[].conductor":
            path = CONDUCTOR_PATH
        elif field.section in (
            "stages[].conductor.limits",
            "stages[].conductor.ratings",
            "stages[].conductor.element",
            "source_ratings",
            "source_regulation",
        ):
            continue  # absent from this payload; covered by their own tests
        elif field.section == "coupling":
            path = ("coupling",)
        else:
            path = ()
        with pytest.raises(MissingUnitError, match=field.key):
            build_electrothermal_system(payload_with(path, field.key, 1.0))


def test_a_null_and_an_object_are_refused_like_a_bare_number():
    for bad in (12, [1, "ohm"], {"magnitude": 1, "units": "ohm"}):
        with pytest.raises(MissingUnitError):
            build_electrothermal_system(
                payload_with(CONDUCTOR_PATH, "reference_resistance", bad)
            )


def test_an_unparsable_unit_is_refused_with_the_dimension_it_needed():
    with pytest.raises(MissingUnitError) as excinfo:
        build_electrothermal_system(
            payload_with(BODY_PATH, "duration", "120 fortnights_ish")
        )
    assert "stages[0].body.duration" in str(excinfo.value)
    assert dimensionality("second") in str(excinfo.value)


def test_a_missing_required_field_is_refused_and_names_what_it_wanted():
    with pytest.raises(MissingFieldError) as excinfo:
        build_electrothermal_system(payload_without(BODY_PATH, "heat_capacity"))
    message = str(excinfo.value)
    assert "stages[0].body.heat_capacity" in message
    assert "required" in message
    assert dimensionality("joule/kelvin") in message


# =====================================================================
# A wrong dimension is refused, and both dimensions are named
# =====================================================================

def test_a_wrong_dimension_is_refused_and_the_error_names_both_dimensions():
    """A length where a temperature belongs — the brief's own example."""
    with pytest.raises(WrongDimensionError) as excinfo:
        build_electrothermal_system(
            payload_with(BODY_PATH, "ambient_temperature", "300 meter")
        )
    message = str(excinfo.value)
    assert "stages[0].body.ambient_temperature" in message
    assert dimensionality("meter") in message      # what arrived
    assert dimensionality("kelvin") in message     # what was needed
    assert "300 meter" in message


def test_a_dimension_check_is_not_a_unit_check():
    """Any unit of the right dimension is accepted; the core converts it.

    The complement of the test above, and the reason the error names a
    *dimension* rather than a unit: rejecting `degC` where the model wrote
    `kelvin` would be the unit-string comparison this platform refuses.
    """
    system = build_electrothermal_system(
        payload_with(BODY_PATH, "duration", "2 minute")
    )
    assert system.stages[0].body.duration.magnitude_in("second") == 120.0


def test_a_composed_unit_of_the_right_dimension_is_accepted():
    """`I*R` reaching a field that wants volts is a conversion, not an error."""
    system = build_electrothermal_system(
        payload_with((), "source_voltage", "5000 millivolt")
    )
    assert system.source_voltage.magnitude_in("volt") == pytest.approx(5.0)


# =====================================================================
# Unknown fields are refused, and this is why
# =====================================================================

def test_a_misspelled_field_is_refused_and_the_error_suggests_the_real_one():
    with pytest.raises(UnknownFieldError) as excinfo:
        build_electrothermal_system(
            payload_with(APPLICABILITY_PATH, "conductivty", "200 watt/meter/kelvin")
        )
    message = str(excinfo.value)
    assert "conductivty" in message
    assert "body_conductivity" in message  # the suggestion
    assert "refused rather than ignored" in message


def test_ignoring_an_unknown_field_would_have_changed_the_verdict():
    """The whole argument for refusing, measured rather than asserted.

    A caller describes a body that violates its Biot bound and misspells the
    conductivity. Refused, they fix one character. *Ignored*, the payload they
    did not write is the one that runs: a body with no declared conductivity,
    whose Biot number cannot be formed, whose validity is UNKNOWN — and the
    report comes back INSUFFICIENT_EVIDENCE.

    Both verdicts are unwelcome and they mean opposite things. NOT_SUPPORTED
    says the evidence in hand argues against this design and more evidence
    will not rescue it. INSUFFICIENT_EVIDENCE says go and gather more. A typo
    would have turned a finding into a gap, silently, and pointed the caller
    at the wrong repair.
    """
    correct = run_electrothermal_case(BIOT_VIOLATING_PAYLOAD, run_id="typo-correct")
    assert correct.reports[0].verdict is CredibilityVerdict.NOT_SUPPORTED
    assert correct.reports[0].violated_conditions != ()

    # What "ignore the unknown key" would have run: the same payload with the
    # misspelled declaration simply absent.
    as_if_ignored = copy.deepcopy(BIOT_VIOLATING_PAYLOAD)
    as_if_ignored["stages"][0]["body"]["applicability"].pop("body_conductivity")
    swallowed = run_electrothermal_case(as_if_ignored, run_id="typo-ignored")

    assert swallowed.reports[0].verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert ctx.BIOT_NUMBER in [
        name for _, name in swallowed.reports[0].unknown_conditions
    ]
    assert swallowed.reports[0].violated_conditions == ()
    assert correct.reports[0].verdict is not swallowed.reports[0].verdict

    # And the boundary refuses the payload that would have produced it.
    with pytest.raises(UnknownFieldError):
        run_electrothermal_case(
            payload_with(
                APPLICABILITY_PATH, "conductivty", "0.2 watt/meter/kelvin"
            ),
            run_id="typo-refused",
        )


def test_an_unknown_key_is_refused_in_every_section():
    for path, section in (
        ((), ""),
        (("stages", 0), "stages[0]"),
        (CONDUCTOR_PATH, "stages[0].conductor"),
        (BODY_PATH, "stages[0].body"),
        (APPLICABILITY_PATH, "stages[0].body.applicability"),
        (("coupling",), "coupling"),
    ):
        with pytest.raises(UnknownFieldError) as excinfo:
            build_electrothermal_system(payload_with(path, "not_a_field", "1 meter"))
        assert "not_a_field" in str(excinfo.value)


def test_a_coupling_supplied_input_is_not_an_accepted_field():
    """A caller may not assert the operating point the run exists to find."""
    for name in COUPLING_SUPPLIED_INPUTS:
        with pytest.raises(UnknownFieldError):
            build_electrothermal_system(payload_with(BODY_PATH, name, "300 kelvin"))


def test_the_structure_itself_is_checked():
    with pytest.raises(MalformedPayloadError):
        build_electrothermal_system({"source_voltage": "5 volt", "stages": {}})
    with pytest.raises(MalformedPayloadError):
        build_electrothermal_system({"source_voltage": "5 volt", "stages": []})
    with pytest.raises(MissingFieldError):
        build_electrothermal_system({"source_voltage": "5 volt"})
    with pytest.raises(MalformedPayloadError):
        build_electrothermal_system(
            payload_with(("coupling",), "max_iterations", "50 second")
        )
    with pytest.raises(MalformedPayloadError):
        build_electrothermal_system(
            payload_with(APPLICABILITY_PATH, "convection_regime", "vigorous")
        )


def test_every_refusal_is_catchable_as_one_family():
    """An agent that only wants "the payload was bad" catches one type."""
    for bad in (
        payload_with(BODY_PATH, "heat_capacity", 2.5),
        payload_with(BODY_PATH, "ambient_temperature", "300 meter"),
        payload_with(APPLICABILITY_PATH, "conductivty", "1 watt/meter/kelvin"),
        payload_without(BODY_PATH, "duration"),
    ):
        with pytest.raises(ProblemPayloadError):
            build_electrothermal_system(bad)


# =====================================================================
# Optional stays optional
# =====================================================================

def test_omitting_every_optional_declaration_at_once_still_builds_and_runs():
    """The floor of the contract: nothing optional is secretly required."""
    bare = copy.deepcopy(APPLICABLE_PAYLOAD)
    bare["stages"][0]["body"].pop("applicability")
    bare.pop("coupling")
    outcome = run_electrothermal_case(bare, run_id="payload-bare")
    report = outcome.reports[0]
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert report.violated_conditions == ()
    assert report.unknown_conditions != ()


@pytest.mark.parametrize(
    "key",
    [
        f.key
        for f in describe_electrothermal_case().fields
        if f.section == "stages[].body.applicability" and not f.required
    ],
)
def test_omitting_one_optional_declaration_yields_unknown_and_never_in_domain(key):
    """Each optional field, dropped alone, against the description's own claim.

    The expectation is not written here: it is the `unlocks` the description
    measured against the model's validity domain. So this test asserts the
    description is *true of a real run*, not merely self-consistent — if the
    domain changed which condition reads which declaration, the description
    would move and this test would follow it, but a description that had
    stopped matching the run would fail here.
    """
    description = describe_electrothermal_case()
    field = description.field(f"stages[].body.applicability.{key}")

    # Run the omission on BOTH convection routes and union what goes UNKNOWN.
    #
    # `unlocks` is measured over both routes, because no single declaration can
    # carry an expansion coefficient and a velocity at once -- that is mixed
    # convection and the record refuses it. So a forced payload alone cannot
    # witness what `fluid_expansion_coefficient` unlocks, and a natural one
    # cannot witness `fluid_velocity`. Checking against the union is the same
    # statement the description makes, and it is still a statement about real
    # runs rather than about the description's self-consistency.
    unknown: set[str] = set()
    reports = []
    for name, payload in (("forced", APPLICABLE_PAYLOAD),
                          ("natural", NATURAL_CONVECTION_PAYLOAD)):
        outcome = run_electrothermal_case(
            payload_without(APPLICABILITY_PATH, key, payload=payload),
            run_id=f"omit-{key}-{name}",
        )
        reports.append(outcome.reports[0])
        unknown |= {
            condition for _, condition in outcome.reports[0].unknown_conditions
        }

    assert set(field.unlocks) <= unknown, (key, field.unlocks, sorted(unknown))
    # The asymmetry that makes optional safe: a missing declaration never
    # satisfies anything, and never violates anything either. Checked on BOTH
    # routes, because "never satisfied" has to hold everywhere the field could
    # have been read, not only where it happened to be witnessed.
    for report in reports:
        assessment = report.validity[0].assessment
        for condition in field.unlocks:
            assert condition not in assessment.satisfied or (
                # The one legitimate exception: a field belonging to the OTHER
                # route was never in this payload, so this run is unaffected by
                # its omission and its conditions are decided by the route that
                # is declared. Nothing was satisfied BY the omission.
                key in ("fluid_expansion_coefficient", "fluid_velocity")
            )
            assert condition not in assessment.violated
        assert report.verdict is not CredibilityVerdict.NOT_SUPPORTED
    if field.unlocks:
        assert any(
            r.validity[0].assessment.status is ValidityStatus.UNKNOWN
            for r in reports
        )


@pytest.mark.parametrize(
    "key",
    [f.key for f in describe_electrothermal_case().fields
     if f.section == "stages[].conductor.limits"],
)
def test_omitting_one_material_limit_yields_unknown_for_what_it_unlocked(key):
    """The rated claim's half of the same rule.

    Asserted against the rated model directly rather than through the report,
    because the report is assembled from the *thermal* sub-result — the two
    claims live on different models and the platform keeps them apart.
    """
    description = describe_electrothermal_case()
    field = description.field(f"stages[].conductor.limits.{key}")

    payload = copy.deepcopy(example_electrothermal_payload())
    payload["stages"][0]["conductor"]["limits"].pop(key)
    system = build_electrothermal_system(payload)
    problem = mat.build_resistance_problem(system.stages[0].conductor)
    assessment = mat.assess_rated_resistance_validity(problem, Quantity(320.0, K))

    assert set(field.unlocks) <= set(assessment.unknown)
    for condition in field.unlocks:
        assert condition not in assessment.satisfied
        assert condition not in assessment.violated


def test_an_alternative_declaration_is_reported_as_one_not_as_inert():
    """`characteristic_length` and `body_volume` are two routes to one L_c.

    Dropping either alone changes nothing, which a solo measurement reports as
    "unlocks nothing" — the same answer it gives for `convection_regime`,
    which genuinely is read by nothing. The description distinguishes them,
    and this is the test that says the distinction is real.
    """
    description = describe_electrothermal_case()
    length = description.field("stages[].body.applicability.characteristic_length")
    volume = description.field("stages[].body.applicability.body_volume")
    regime = description.field("stages[].body.applicability.convection_regime")

    assert length.unlocks == () and volume.unlocks == ()
    assert length.alternative_to == ("body_volume",)
    assert volume.alternative_to == ("characteristic_length",)
    assert ctx.BIOT_NUMBER in length.group_unlocks

    # inert is inert: no solo unlock, no alternative, no group
    assert regime.unlocks == () and regime.alternative_to == ()
    assert regime.group_unlocks == ()

    # and the group claim holds against a real run
    payload = copy.deepcopy(example_electrothermal_payload())
    payload["stages"][0]["body"]["applicability"].pop("characteristic_length")
    payload["stages"][0]["body"]["applicability"].pop("body_volume")
    outcome = run_electrothermal_case(payload, run_id="omit-both-length-routes")
    unknown = {name for _, name in outcome.reports[0].unknown_conditions}
    assert set(length.group_unlocks) <= unknown


def test_a_declared_but_unmodelled_field_is_carried_and_unlocks_nothing():
    """`convection_regime` reaches the report as context and no further."""
    with_regime = run_electrothermal_case(APPLICABLE_PAYLOAD, run_id="regime-yes")
    without = run_electrothermal_case(
        payload_without(APPLICABILITY_PATH, "convection_regime"), run_id="regime-no"
    )
    assert with_regime.reports[0].verdict is without.reports[0].verdict
    assert (
        with_regime.reports[0].declarations[0].payload["convection_regime"]
        == ctx.FORCED_CONVECTION
    )
    assert without.reports[0].declarations[0].payload["convection_regime"] is None


# =====================================================================
# The description is the models', not this module's
# =====================================================================

def test_the_description_accounts_for_every_declared_model_input():
    """Derived on both sides, so drift on either fails here.

    The expectation is recomputed from the model registries in this test, not
    copied from the description. Every input a model declares must be either a
    payload field or an entry in COUPLING_SUPPLIED_INPUTS, and no input may be
    both — a field the caller supplies *and* the coupling solves for would be
    a way to assert the answer.
    """
    declared = {spec.name for model in MODELS for spec in model.inputs}
    described = {f.model_input for f in describe_electrothermal_case().fields
                 if f.model_input is not None}
    supplied = set(COUPLING_SUPPLIED_INPUTS)

    assert described | supplied == declared
    assert described & supplied == set()
    assert described  # not vacuous


def test_every_described_field_reports_the_models_own_facts():
    """required, dimension and prose all come from the model record."""
    by_name = {
        spec.name: spec for model in MODELS for spec in model.inputs
    }
    for field in describe_electrothermal_case().fields:
        if field.model_input is None:
            continue
        spec = by_name[field.model_input]
        assert field.required is spec.required, field.path
        assert field.unit_exemplar == spec.unit_exemplar, field.path
        assert field.dimension == dimensionality(spec.unit_exemplar), field.path
        assert field.description == spec.description, field.path


def test_the_description_names_every_condition_the_models_declare():
    """Every optional field's unlocks are real condition names, and between
    them they cover every condition that depends on a declaration."""
    lumped_conditions = {c.name for c in lump.LUMPED_CAPACITY_MODEL.validity.conditions}
    rated_conditions = {
        c.name for c in mat.RATED_LINEAR_TCR_MODEL.validity.conditions
    }
    electrical_conditions = {
        c.name
        for model in (
            dc_models.RESISTOR_OHM_MODEL,
            dc_models.IDEAL_VOLTAGE_SOURCE_MODEL,
        )
        for c in model.validity.conditions
    }
    known = lumped_conditions | rated_conditions | electrical_conditions

    mentioned = set()
    for field in describe_electrothermal_case().fields:
        mentioned |= set(field.unlocks) | set(field.group_unlocks)
    assert mentioned <= known, sorted(mentioned - known)
    # the applicability declaration exists to unlock these five
    assert {
        ctx.BIOT_NUMBER,
        ctx.INTERNAL_FOURIER_NUMBER,
        ctx.CONDUCTANCE_EXCURSION_RATIO,
        ctx.CAPACITY_EXCURSION_RATIO,
        ctx.RADIATION_TO_CONVECTION_RATIO,
    } <= mentioned


def test_required_and_optional_split_the_described_fields():
    description = describe_electrothermal_case()
    assert set(description.required) | set(description.optional) == set(
        description.fields
    )
    assert not set(description.required) & set(description.optional)
    # a required field never claims to unlock anything: without it there is no
    # case to assess at all
    for field in description.required:
        assert field.unlocks == ()


def test_the_description_serializes_for_a_caller_that_never_imports_it():
    payload = describe_electrothermal_case().to_dict()
    assert {"fields", "coupling_supplied_inputs", "models", "example"} <= set(payload)
    first = payload["fields"][0]
    assert {"path", "required", "dimension", "unlocks_conditions"} <= set(first)
    assert payload["example"] == example_electrothermal_payload()


# =====================================================================
# Round trip
# =====================================================================

def test_description_to_payload_to_problem_to_report():
    """The whole boundary, driven only by what the description says.

    A caller that has read nothing but `describe_electrothermal_case()` must be
    able to write a payload that runs. So this test builds one from the
    description's own field list and example, checks it mentions every required
    field, and takes it all the way to a verdict.
    """
    description = describe_electrothermal_case()
    payload = description.to_dict()["example"]

    # every required field the description names is present in the example
    for field in description.required:
        target = payload
        if field.section.startswith("stages[]"):
            target = payload["stages"][0]
            for step in field.section.split(".")[1:]:
                target = target[step]
        elif field.section == "coupling":
            target = payload["coupling"]
        assert field.key in target, field.path

    problems = build_electrothermal_problems(payload)
    assert len(problems) == 3

    outcome = run_electrothermal_case(payload, run_id="round-trip")
    report = outcome.reports[0]
    assert report.verdict in set(CredibilityVerdict)
    assert report.violated_conditions == ()
    # The unknown conditions here are the electrical ratings this payload has
    # no field for — see the applicable-payload test above. What matters to
    # *this* test is that the described payload poses and runs, and that
    # nothing in it is violated.
    assert report.values["final_temperature"].magnitude_in(K) == pytest.approx(
        338.577018, abs=1e-6
    )
    # and the report survives the trip out to JSON and back
    restored = type(report).from_dict(report.to_dict())
    assert restored.verdict is report.verdict


def test_two_stages_produce_one_report_each():
    """Arity is not special-cased: N stages, N reports, in the payload's order."""
    payload = copy.deepcopy(APPLICABLE_PAYLOAD)
    second = copy.deepcopy(payload["stages"][0])
    second["component_id"] = "R2"
    payload["stages"].append(second)

    outcome = run_electrothermal_case(payload, run_id="two-stages")
    assert len(outcome.reports) == 2
    assert [p.problem_id for p in build_electrothermal_problems(payload)] == [
        "electrical_dc:electrothermal-series-R1-R2",
        "resistance-tcr-R1",
        "thermal-lumped-R1",
        "resistance-tcr-R2",
        "thermal-lumped-R2",
    ]


# =====================================================================
# F11 — coupling configuration is checked identically at both entry points
# =====================================================================

def test_f11_a_zero_coupling_tolerance_is_refused_by_the_builder_too():
    """The builder must refuse exactly what the runner refuses.

    A payload is accepted or refused as a whole. A zero tolerance that
    ``build_electrothermal_system`` waved through and ``run_electrothermal_case``
    then rejected made the boundary's answer depend on which entry point the
    caller happened to use — which is the same defect the misspelled
    ``max_iteratons`` guard already exists to prevent, in the one field where
    the check had been left to the runner.
    """
    payload = example_electrothermal_payload()
    payload["coupling"]["tolerance"] = "0 kelvin"

    with pytest.raises(ProblemPayloadError) as from_builder:
        build_electrothermal_system(payload)
    with pytest.raises(ProblemPayloadError) as from_runner:
        run_electrothermal_case(payload)

    for raised in (from_builder, from_runner):
        assert "coupling.tolerance" in str(raised.value)
        assert "strictly positive" in str(raised.value)


@pytest.mark.parametrize(
    "tolerance",
    ["0 kelvin", "-1 kelvin", "0 degC"],
)
def test_f11_every_inadmissible_tolerance_is_refused_at_both_entry_points(
    tolerance,
):
    """Zero, negative, and an interval scale a difference cannot live on.

    ``degC`` is a real refusal and not a stylistic one: a tolerance is a
    *difference*, and converting a difference between two scales that do not
    share a zero is not a conversion of a difference.
    """
    payload = example_electrothermal_payload()
    payload["coupling"]["tolerance"] = tolerance
    with pytest.raises(ProblemPayloadError):
        build_electrothermal_system(payload)
    with pytest.raises(ProblemPayloadError):
        run_electrothermal_case(payload)


def test_f11_an_admissible_coupling_block_still_builds_and_runs():
    """The shared rule refuses no configuration that was legitimate before."""
    payload = example_electrothermal_payload()
    payload["coupling"]["tolerance"] = "1e-9 kelvin"
    assert build_electrothermal_system(payload).stages
    assert run_electrothermal_case(payload).run.iterations_run >= 1


# =====================================================================
# F01 / F02 / F05 — the report is built over the dependency closure
# =====================================================================

MATERIAL = mat.RATED_LINEAR_TCR_MODEL.model_id
LINEAR_TCR = mat.LINEAR_TCR_MODEL.model_id
KCL = dc_models.KCL_MODEL.model_id
RESISTOR = dc_models.RESISTOR_OHM_MODEL.model_id
SOURCE = dc_models.IDEAL_VOLTAGE_SOURCE_MODEL.model_id


def assessed(report):
    return {record.model_id for record in report.validity}


def test_f01_a_capped_run_is_not_supported_and_the_report_names_the_cap():
    """A coupling that stopped on its budget cannot be read as one that met it.

    The finding: capping the iteration to 1 left the report SUPPORTED with no
    trace anywhere in it that the fixed point was never reached. The coupled
    run knew — ``CoupledRun.outcome`` is ``ITERATION_LIMIT_REACHED`` — and the
    reporting boundary threw that away, because the report was assembled from
    one sub-result and a sub-result carries no coupling.
    """
    payload = example_electrothermal_payload()
    payload["coupling"]["max_iterations"] = 1
    outcome = run_electrothermal_case(payload, run_id="f01-capped")
    report = outcome.reports[0]

    assert outcome.run.outcome is cp.CouplingOutcome.ITERATION_LIMIT_REACHED
    assert report.verdict is not CredibilityVerdict.SUPPORTED

    # the cap is *in the report*, not merely inferable from a sibling object
    assert report.coupling is not None
    assert report.coupling.outcome == "iteration_limit_reached"
    assert report.coupling.criterion is not evidence.CouplingCriterion.MET
    assert report.coupling.iterations_run == 1
    assert report.coupling.iteration_limit == 1
    assert "iteration_limit_reached" in json.dumps(report.to_dict())

    # and it survives the trip out to JSON and back
    restored = type(report).from_dict(
        json.loads(json.dumps(report.to_dict(), sort_keys=True))
    )
    assert restored.coupling == report.coupling
    assert restored.verdict is report.verdict


def test_f01_a_converged_run_carries_the_same_field_saying_so():
    """The field is not a failure flag; it is the coupling's own statement."""
    outcome = run_electrothermal_case(
        example_electrothermal_payload(), run_id="f01-converged"
    )
    report = outcome.reports[0]
    assert outcome.run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert report.coupling.criterion is evidence.CouplingCriterion.MET
    assert report.coupling.outcome == "criterion_met"
    assert report.coupling.largest_iterate_change.magnitude_in(K) <= (
        report.coupling.tolerance.magnitude_in(K)
    )


def test_f01_the_coupling_statement_is_not_a_numerical_convergence_claim():
    """Distinct from every solver's own convergence, and not a check.

    Both closed-form participants report NOT_APPLICABLE and the MNA solve
    reports CONVERGED in every iteration of a run that converged not at all.
    Folding the coupling into either would make those the same token.
    """
    payload = example_electrothermal_payload()
    payload["coupling"]["max_iterations"] = 1
    report = run_electrothermal_case(payload, run_id="f01-distinct").reports[0]

    assert "iteration_limit_reached" not in json.dumps(
        [c.to_dict() for c in report.validation]
    )
    for check in report.validation:
        assert check.establishes is not ValidationLevel.NUMERICALLY_CONVERGED
    assert ValidationLevel.NUMERICALLY_CONVERGED not in report.attained_levels


def test_f02_a_violated_material_limit_reaches_the_report():
    """The finding: a declared limit the run walks straight past, unreported.

    ``maximum_operating_temperature`` is a condition of the *rated* material
    model. The report assessed only the thermal model, so a conductor declared
    good to 301 K and run to 338 K produced a SUPPORTED report in which the
    limit appeared nowhere.
    """
    payload = example_electrothermal_payload()
    limits = payload["stages"][0]["conductor"]["limits"]
    limits["maximum_operating_temperature"] = "301 kelvin"
    report = run_electrothermal_case(payload, run_id="f02-limit").reports[0]

    assert MATERIAL in assessed(report)
    assert (MATERIAL, mat.OPERATING_TEMPERATURE_UTILIZATION) in (
        report.violated_conditions
    )
    # a violation is a finding, and a finding outranks every gap beside it
    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED


def test_f02_an_undeclared_material_limit_is_a_gap_and_not_a_pass():
    """Omitting the limit does not buy the verdict the limit refused."""
    payload = example_electrothermal_payload()
    limits = payload["stages"][0]["conductor"]["limits"]
    del limits["maximum_operating_temperature"]
    report = run_electrothermal_case(payload, run_id="f02-omitted").reports[0]
    assert (MATERIAL, mat.OPERATING_TEMPERATURE_UTILIZATION) in (
        report.unknown_conditions
    )
    assert report.verdict is not CredibilityVerdict.SUPPORTED


def test_every_model_in_the_closure_is_named_and_assessed():
    """The report covers what the values it reports actually depend on.

    A body temperature depends on the heat, which depends on the circuit,
    which depends on every element's R(T), which depends back on the
    temperature. That closure is the whole composition, and every model in it
    now appears with a verdict rather than the thermal one appearing alone.
    """
    report = run_electrothermal_case(
        example_electrothermal_payload(), run_id="closure"
    ).reports[0]

    expected = {
        lump.LUMPED_CAPACITY_MODEL.model_id,
        LINEAR_TCR,
        MATERIAL,
        KCL,
        RESISTOR,
        SOURCE,
        # The example declares the `element` block, so the narrower element
        # claim is in the closure too. It is not in this set by default: a
        # payload that declares nothing about the element does not attach it,
        # which `test_a_companion_record_is_absent_until_the_caller_widens_it`
        # is the other half of.
        dc_app.SELF_HEATED_RESISTOR_MODEL.model_id,
    }
    assert assessed(report) == expected
    assert {m for m, _v in report.contributing_models} >= expected
    assert report.unassessed_models == ()


def unrated_example():
    """The example payload with its declared ratings stripped back off.

    ``example_electrothermal_payload`` now declares ratings read from real
    datasheets, so it is no longer the payload that demonstrates what an
    *undeclared* rating does. The behaviour it used to demonstrate has not
    changed and is still exactly the point -- an absent rating is UNKNOWN,
    never unlimited -- so the two tests that were about it now run against
    this, which is that payload minus the two blocks.
    """
    payload = copy.deepcopy(example_electrothermal_payload())
    payload["stages"][0]["conductor"].pop("ratings", None)
    payload.pop("source_ratings", None)
    return payload


def test_the_undeclared_electrical_ratings_are_reported_as_gaps():
    """Nobody declared these limits, so they stay UNKNOWN.

    A payload with no ``ratings`` block leaves every rating condition UNKNOWN,
    because an absent rating is not an unlimited one. That behaviour is the
    point and it did not change when the block was added, nor when the example
    started declaring one: what changed is that a caller who *can* state the
    ratings is no longer forced into this verdict by the boundary having
    nowhere to put them. ``test_declared_ratings_reach_the_report`` below is
    the other half, and the shipped example is now on that side of it.
    """
    report = run_electrothermal_case(
        unrated_example(), run_id="gaps"
    ).reports[0]
    assert (RESISTOR, dc_models.DISSIPATED_POWER_UTILIZATION) in (
        report.unknown_conditions
    )
    assert (SOURCE, dc_models.SOURCE_CURRENT_UTILIZATION) in (
        report.unknown_conditions
    )
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE

# =====================================================================
# Component ratings: the declaration the conditions were always waiting for
# =====================================================================

RATINGS_PATH = ("stages", 0, "conductor", "ratings")


def _rated_payload(**overrides):
    """The applicable payload with ratings that cannot bind, plus overrides."""
    payload = copy.deepcopy(APPLICABLE_PAYLOAD)
    ratings = {"rated_power": "1000 watt", "maximum_working_voltage": "1000 volt"}
    ratings.update(overrides.pop("ratings", {}))
    payload["stages"][0]["conductor"]["ratings"] = ratings
    payload["source_ratings"] = overrides.pop(
        "source_ratings", {"maximum_current": "1000 ampere"}
    )
    return payload


def test_declared_ratings_reach_the_report_and_lift_their_conditions():
    """The gap TASK 1 closed, stated as the one assertion that shows it."""
    report = run_electrothermal_case(_rated_payload(), run_id="rated").reports[0]

    assert (RESISTOR, dc_models.DISSIPATED_POWER_UTILIZATION) not in (
        report.unknown_conditions
    )
    assert (RESISTOR, dc_models.WORKING_VOLTAGE_UTILIZATION) not in (
        report.unknown_conditions
    )
    assert (SOURCE, dc_models.SOURCE_CURRENT_UTILIZATION) not in (
        report.unknown_conditions
    )
    for record in report.validity:
        if record.model_id in (RESISTOR, SOURCE):
            assert record.assessment.status is ValidityStatus.IN_DOMAIN


def test_the_shipped_example_declares_its_ratings_and_is_supported():
    """The default example of the product reaches a supported verdict.

    It is what a first-time reader runs, and until its ratings were declared
    it could not get there: three rating conditions read UNKNOWN on every
    nominal run and INSUFFICIENT_EVIDENCE was the honest answer to a payload
    that had not said what its parts survive. No level was added and no rule
    was relaxed to move it -- the evidence is the declaration, and the three
    utilizations below are the numbers that declaration produces.
    """
    report = run_electrothermal_case(
        example_electrothermal_payload(), run_id="shipped"
    ).reports[0]

    assert report.unknown_conditions == ()
    assert report.violated_conditions == ()
    assert report.verdict is CredibilityVerdict.SUPPORTED
    # Comfortably inside every rating, not marginally so.
    for model_id, condition in (
        (RESISTOR, dc_models.DISSIPATED_POWER_UTILIZATION),
        (RESISTOR, dc_models.WORKING_VOLTAGE_UTILIZATION),
        (SOURCE, dc_models.SOURCE_CURRENT_UTILIZATION),
    ):
        record = next(r for r in report.validity if r.model_id == model_id)
        assert condition in record.assessment.satisfied


def test_the_over_rating_example_violates_exactly_one_rating():
    """The second exported example, and the one bound it is known to cross.

    Same circuit, same element, same body: only the supply part differs, so a
    reader can see that a violation is a finding about a *specification* and
    not about the solve. Exactly one condition is violated, and nothing else in
    the report moves off IN_DOMAIN.
    """
    report = run_electrothermal_case(
        example_over_rating_payload(), run_id="over-rating"
    ).reports[0]

    assert report.violated_conditions == (
        (SOURCE, dc_models.SOURCE_CURRENT_UTILIZATION),
    )
    assert report.unknown_conditions == ()
    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED
    outside = [
        r.model_id for r in report.validity
        if r.assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    ]
    assert outside == [SOURCE]


def test_an_exceeded_rating_is_a_violation_rather_than_a_gap():
    """A rating that binds is a finding about the design, not a missing field."""
    report = run_electrothermal_case(
        _rated_payload(ratings={"rated_power": "0.001 watt"}), run_id="over"
    ).reports[0]

    resistor = next(r for r in report.validity if r.model_id == RESISTOR)
    assert resistor.assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert dc_models.DISSIPATED_POWER_UTILIZATION in resistor.assessment.violated
    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED


def test_omitting_the_ratings_block_is_not_an_error_and_stays_unknown():
    """Optional means optional. This is the behaviour that must not change.

    Supplying a rating can move a condition off UNKNOWN; omitting one can never
    move it onto IN_DOMAIN. An unrated part is not an unlimited part.
    """
    report = run_electrothermal_case(
        unrated_example(), run_id="bare"
    ).reports[0]
    assert (RESISTOR, dc_models.DISSIPATED_POWER_UTILIZATION) in (
        report.unknown_conditions
    )
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE

    # An empty block says exactly what an absent one says.
    payload = copy.deepcopy(APPLICABLE_PAYLOAD)
    payload["stages"][0]["conductor"]["ratings"] = {}
    empty = run_electrothermal_case(payload, run_id="empty").reports[0]
    assert (RESISTOR, dc_models.DISSIPATED_POWER_UTILIZATION) in (
        empty.unknown_conditions
    )


def test_the_derating_factor_narrows_a_rating_that_would_otherwise_hold():
    """Declared margin is applied, and is visible as an input rather than a
    number buried in a threshold."""
    # This stage dissipates about 2.12 W, so a 5 W part is comfortable at full
    # rating and over its limit once the caller elects to use a tenth of it.
    power = "5 watt"
    holds = run_electrothermal_case(
        _rated_payload(ratings={"rated_power": power}), run_id="full"
    ).reports[0]
    full = next(r for r in holds.validity if r.model_id == RESISTOR)
    assert dc_models.DISSIPATED_POWER_UTILIZATION in full.assessment.satisfied

    derated = run_electrothermal_case(
        _rated_payload(ratings={"rated_power": power, "derating_factor": 0.1}),
        run_id="derated",
    ).reports[0]
    resistor = next(r for r in derated.validity if r.model_id == RESISTOR)
    assert dc_models.DISSIPATED_POWER_UTILIZATION in resistor.assessment.violated


def test_a_derating_factor_outside_the_unit_interval_is_refused():
    """Refused by ComponentRating's own rule, not by a copy of it here."""
    for bad in (0.0, -0.5, 1.5):
        with pytest.raises(InvalidScientificProblem, match="derating_factor"):
            build_electrothermal_system(
                _rated_payload(ratings={"derating_factor": bad})
            )


def test_a_rating_written_without_a_unit_is_refused_like_any_quantity():
    for key in ("rated_power", "maximum_working_voltage"):
        with pytest.raises(MissingUnitError, match=key):
            build_electrothermal_system(_rated_payload(ratings={key: 1.0}))


def test_the_derating_factor_is_the_one_field_written_without_a_unit():
    """And deliberately so: it is a policy, not a measurement.

    Pinned because it is the single exception to this boundary's strictest
    rule, and an exception nobody wrote down is one somebody later removes.
    """
    with pytest.raises(MalformedPayloadError, match="derating_factor"):
        build_electrothermal_system(
            _rated_payload(ratings={"derating_factor": "0.5 dimensionless"})
        )


def test_a_misspelled_rating_is_refused_with_a_suggestion():
    with pytest.raises(UnknownFieldError, match="rated_powr"):
        build_electrothermal_system(_rated_payload(ratings={"rated_powr": "1 watt"}))


def test_the_ratings_fields_are_described_from_the_model_records():
    """The description is derived, not restated. TASK 1 asked for exactly this."""
    described = {
        (f.section, f.key): f for f in describe_electrothermal_case().fields
    }

    power = described[("stages[].conductor.ratings", "rated_power")]
    assert power.required is False
    assert power.dimension == dimensionality("watt")
    assert dc_models.DISSIPATED_POWER_UTILIZATION in power.unlocks

    current = described[("source_ratings", "maximum_current")]
    assert current.required is False
    assert current.dimension == dimensionality("ampere")
    assert dc_models.SOURCE_CURRENT_UTILIZATION in current.unlocks


# =====================================================================
# A run that stops at the transfer boundary is a finding, not an exception
# =====================================================================

def _runaway_payload():
    """A conductor whose own declared alpha drives R(T) through zero."""
    payload = copy.deepcopy(APPLICABLE_PAYLOAD)
    conductor = payload["stages"][0]["conductor"]
    conductor["temperature_coefficient"] = "-0.05 1/kelvin"
    conductor["limits"] = {
        "linearization_band": "400 kelvin",
        "maximum_operating_temperature": "1200 kelvin",
        "debye_temperature": "343 kelvin",
    }
    return payload


def test_a_design_that_stops_the_loop_is_reported_rather_than_raised():
    """The whole of TASK 4 in one assertion.

    A declared alpha that takes R(T) through zero used to end the run with
    TransportRefused, which removed the finding from the report entirely: a
    caller saw an exception and the report said nothing at all.
    """
    outcome = run_electrothermal_case(_runaway_payload(), run_id="runaway")
    report = outcome.reports[0]

    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED
    assert outcome.run.outcome is cp.CouplingOutcome.TRANSFER_REFUSED
    assert report.coupling.outcome == "transfer_refused"


def test_the_finding_that_stopped_the_loop_is_named_in_the_report():
    """`linear_resistance_ratio` is the condition, and it is attributed."""
    report = run_electrothermal_case(
        _runaway_payload(), run_id="runaway-named"
    ).reports[0]

    violated = {
        (record.model_id, name)
        for record in report.validity
        for name in record.assessment.violated
    }
    assert (mat.RATED_LINEAR_TCR_MODEL.model_id, "linear_resistance_ratio") in (
        violated
    )
    failed = {check.name for check in report.validation if not check.passed}
    assert "coupling_transfer_refused" in failed


def test_a_stopped_run_reports_the_values_it_produced_and_omits_the_rest():
    """Absent, not zero and not null-with-units.

    The refused property solve produced a resistance -- a negative one, which
    is the evidence. No temperature was ever computed, and inventing one so the
    report keeps its usual shape is the substitution this boundary exists to
    refuse.
    """
    report = run_electrothermal_case(
        _runaway_payload(), run_id="runaway-values"
    ).reports[0]

    assert "resistance" in report.values
    assert report.values["resistance"].magnitude_in("ohm") < 0.0
    for never_produced in (
        "final_temperature",
        "steady_state_temperature",
        "time_constant",
    ):
        assert never_produced not in report.values


def test_the_transfer_guard_itself_is_unchanged():
    """F08 stays exactly as it was: the value still does not travel.

    What changed is the exit, not the guard. A provider returning nonsense
    still raises out of the generic runner, because a caller supplying its own
    executor table may be running one -- and an execution failure is not a
    finding about the design.
    """
    import inspect

    source = inspect.getsource(cp.run_fixed_point)
    assert "stop_on_transfer_refusal" in source
    assert inspect.signature(cp.run_fixed_point).parameters[
        "stop_on_transfer_refusal"
    ].default is False


def test_a_conflicting_pair_of_declared_limits_is_a_finding_not_a_refusal():
    """Melting point below the operating ceiling, via the validation hook.

    Reported rather than refused at build time, because cases whose real defect
    is that the run passes the melting point also declare a low melting point
    beside a high ceiling -- refusing early pre-empts the better finding.
    """
    payload = copy.deepcopy(APPLICABLE_PAYLOAD)
    payload["stages"][0]["body"]["applicability"]["melting_temperature"] = (
        "400 kelvin"
    )
    payload["stages"][0]["conductor"]["limits"] = {
        "maximum_operating_temperature": "900 kelvin"
    }
    report = run_electrothermal_case(payload, run_id="conflict").reports[0]

    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED
    failed = {c.name for c in report.validation if not c.passed}
    assert "declared_limits_are_mutually_consistent" in failed


def test_agreeing_limits_pass_the_same_check_rather_than_omitting_it():
    """A check that only ever fails is a check nobody can see working."""
    payload = copy.deepcopy(APPLICABLE_PAYLOAD)
    payload["stages"][0]["conductor"]["limits"] = {
        "maximum_operating_temperature": "600 kelvin"
    }
    report = run_electrothermal_case(payload, run_id="agree").reports[0]
    passed = {c.name for c in report.validation if c.passed}
    assert "declared_limits_are_mutually_consistent" in passed


def test_an_undeclared_limit_is_not_read_as_agreement():
    """Both limits are optional and the check is absent unless both are there."""
    payload = payload_without(APPLICABILITY_PATH, "melting_temperature")
    report = run_electrothermal_case(payload, run_id="absent").reports[0]
    names = {c.name for c in report.validation}
    assert "declared_limits_are_mutually_consistent" not in names


# =====================================================================
# NEEDS A2.9 -- which resistance the rating is assessed against
# =====================================================================
#
# The element list the resistor assessment is built from used to come from
# ``system.circuit_at(reference resistances)``: the element as the CALLER
# declared it, not the element the converged circuit was solved with. It now
# comes from ``cp.converged_resistances``, read back out of each stage's own
# property result.
#
# A2.9 predicted its own blast radius correctly, and overclaiming the fix would
# be worse than stating it plainly: the only resistor condition that reads
# ``resistance`` is ``resistance > 0``, and both readings are strictly positive
# in any run that reaches this point, so NO VERDICT MOVES. The operating-point
# values -- dissipated power, voltage across -- were already the converged
# ones, arriving as arguments from the electrical result rather than out of the
# element. What changed is that the report no longer names a resistance the
# circuit did not use.
#
# So the tests below pin two different things. The first pins the helper, which
# is what this change added. The third pins the property that must survive any
# future edit: with a rating placed between the two readings, reading the
# reference would refuse a design the converged point clears.


def _converged_probe(payload, run_id):
    """``(system, run, R_reference, R_converged, P_converged)`` for a payload."""
    system = build_electrothermal_system(payload)
    run = run_electrothermal_case(payload, run_id=run_id).run
    problems = cp.coupled_problems(
        system,
        {s.component_id: s.conductor.reference_resistance for s in system.stages},
    )
    electrical = run.final.result_for(problems[0].problem_id)
    return (
        system,
        run,
        system.stages[0].conductor.reference_resistance,
        cp.converged_resistances(system, run)["R1"],
        electrical.value("resistor_power:R1"),
    )


def test_converged_resistances_reads_the_run_not_the_declaration():
    """R(T), out of the property result, and into the circuit that is assessed."""
    system, run, reference, converged, _power = _converged_probe(
        _rated_payload(), run_id="converged_r"
    )

    # A positive TCR on a body that heats: the converged element is the
    # stiffer one, and by 18% -- far more than any tolerance could blur.
    assert reference.magnitude_in("ohm") == pytest.approx(10.0)
    assert converged.magnitude_in("ohm") == pytest.approx(11.7853, rel=1e-4)

    # Not recomputed here: it is the value the property solve published, so
    # there is one implementation of the TCR form rather than two.
    for _stage, prop_problem, _thermal in cp.stage_problems(system):
        published = run.final.result_for(prop_problem.problem_id).value(
            mat.RESISTANCE_METRIC
        )
        assert published == converged

    # And it is the element the assessment is built from.
    circuit = system.circuit_at(cp.converged_resistances(system, run))
    assert circuit.resistors[0].resistance == converged


def test_a_run_that_cannot_supply_the_converged_value_is_refused():
    """No silent fall back to the declaration. A wrong value read confidently
    is worse than an error that names what is missing."""
    run = run_electrothermal_case(_rated_payload(), run_id="mismatch").run

    renamed = copy.deepcopy(_rated_payload())
    renamed["stages"][0]["component_id"] = "R2"
    other = build_electrothermal_system(renamed)

    with pytest.raises(InvalidScientificProblem):
        cp.converged_resistances(other, run)


def test_a_rating_between_the_two_readings_is_judged_at_the_converged_one():
    """**The regression guard.** R_ref = 10 ohm and R(T) = 11.79 ohm across one
    5 V source, so the same part dissipates 2.500 W as declared and 2.121 W as
    run. A 2.3 W rating sits between them: assessed at the converged point the
    design holds, assessed at the reference it is refused.

    This is the assertion a future edit that quietly went back to reading the
    declaration would break. It passes today for a reason worth being honest
    about -- the power has always arrived from the converged electrical result,
    so this half was already right before A2.9 was addressed -- and that is
    exactly why it is worth pinning: nothing else in the suite says the two
    readings must not be swapped.
    """
    _system, _run, reference, converged, power = _converged_probe(
        _rated_payload(), run_id="between"
    )
    at_reference = 5.0**2 / reference.magnitude_in("ohm")
    at_converged = 5.0**2 / converged.magnitude_in("ohm")
    assert at_converged == pytest.approx(power.magnitude_in("watt"), rel=1e-6)
    assert at_converged < 2.3 < at_reference

    report = run_electrothermal_case(
        _rated_payload(ratings={"rated_power": "2.3 watt"}), run_id="between_v"
    ).reports[0]
    resistor = next(r for r in report.validity if r.model_id == RESISTOR)
    assert dc_models.DISSIPATED_POWER_UTILIZATION in resistor.assessment.satisfied
    assert report.verdict is CredibilityVerdict.SUPPORTED


def test_a_rating_exceeded_at_the_converged_point_stays_refused():
    """Reading the converged value is not a licence to pass a part that is
    genuinely over its rating there: 2.121 W against a 2.0 W part."""
    report = run_electrothermal_case(
        _rated_payload(ratings={"rated_power": "2.0 watt"}), run_id="still_over"
    ).reports[0]
    resistor = next(r for r in report.validity if r.model_id == RESISTOR)
    assert dc_models.DISSIPATED_POWER_UTILIZATION in resistor.assessment.violated
    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED


#: Benchmark case ``S00709`` as it was drawn when it was the hard benchmark's
#: one false reject, field for field. ``benchmarks/hard/README.md`` attributed
#: that to A2.9 -- the tool "computes 3.5634 W", the dissipation at the
#: reference resistance. It does not, and these numbers are the evidence.
#:
#: The generator has since been corrected and the live case declares a
#: 3.5311 W rating, so this payload no longer matches the one on disk. It is
#: kept frozen here on purpose: it is the counterexample that settled which of
#: the two was wrong, and a test that read the case file would lose it the next
#: time the benchmark is regenerated.
S00709_PAYLOAD = {
    "source_voltage": "14.78541112 volt",
    "stages": [
        {
            "component_id": "R1",
            "conductor": {
                "reference_resistance": "61.34739865 ohm",
                "temperature_coefficient": "0.00393 1/kelvin",
                "reference_temperature": "293.15 kelvin",
                "limits": {
                    "linearization_band": "68.09849035 kelvin",
                    "maximum_operating_temperature": "328.3642412 kelvin",
                    "debye_temperature": "107.6403019 kelvin",
                },
                "ratings": {
                    "rated_power": "3.49889191 watt",
                    "maximum_working_voltage": "44.35623337 volt",
                },
            },
            "body": {
                "heat_capacity": "3.266688028 joule/kelvin",
                "ambient_conductance": "0.1193259777 watt/kelvin",
                "ambient_temperature": "269.1007548 kelvin",
                "initial_temperature": "269.1007548 kelvin",
                "duration": "66.16911106 second",
                "applicability": {
                    "characteristic_length": "5.764861959e-05 meter",
                    "body_volume": "4.638162492e-08 meter**3",
                    "surface_area": "0.0008045574248 meter**2",
                    "body_conductivity": "400 watt/meter/kelvin",
                    "surface_emissivity": "0.3180459303 dimensionless",
                    "convection_regime": "forced",
                    "conductance_excursion_bound": "87.79045923 kelvin",
                    "capacity_excursion_bound": "87.79045923 kelvin",
                    "melting_temperature": "728.3642412 kelvin",
                    "fluid_conductivity": "0.1253641637 watt/meter/kelvin",
                    "fluid_kinematic_viscosity": "1.589e-05 meter**2/second",
                    "fluid_prandtl_number": "0.707 dimensionless",
                    "convection_length": "0.05 meter",
                    "fluid_velocity": "3.178 meter/second",
                },
            },
        }
    ],
    "source_ratings": {"maximum_current": "0.7085147846 ampere"},
    "coupling": {
        "seed_temperature": "269.1007548 kelvin",
        "tolerance": "1e-06 kelvin",
        "max_iterations": 200,
    },
}


def test_s00709_is_over_its_rating_at_every_resistance_the_run_can_offer():
    """The benchmark's one false reject is a mislabelled case, not a bad read.

    The generator states each rating against ``R(T_ss)`` -- the resistance at
    the STEADY STATE -- and places this one 0.2% inside: T_ss = 298.364 K,
    R = 62.605 ohm, P = 3.4919 W, rated 3.4989 W. But the payload declares a
    66.169 s run against a 27.376 s time constant, so the body reaches
    295.999 K and stops there, 2.4 K short of the steady state it was rated
    against. Cooler means a lower resistance means MORE dissipation, and the
    part draws 3.5240 W: 1.0072x its rating, at the operating point the case
    itself declares.

    Reading the converged resistance is what makes the number 3.5240 W rather
    than the reference reading's 3.5635 W, so the fix moves the utilization from
    1.0185 to 1.0072. Both are over.

    **In the tool's model the dissipation is one value, not a curve.** Each
    coupled iteration does a single electrical solve at a single resistance, and
    at the fixed point that resistance is R(T_end); the thermal march then runs
    at constant heat input. So "the dissipation over the horizon" is 3.5240 W
    and there is no maximum to take. The physical device would dissipate more
    early on -- a positive-TCR part is least resistive when coldest, so
    3.5635 W at t = 0 falling towards the asymptote's 3.4919 W -- and the model
    does not represent that transient. If it did, the peak would be at the cold
    start and this case would be further over its rating, not less. Every
    reading available agrees the part is over.

    The tool is right and the ground truth was wrong, in the same way the
    ``geometry_conflict`` labels were wrong -- the expectation was computed at
    an operating point the case does not declare.

    **Since fixed, in the generator.** ``base_draw`` now sizes ratings from
    ``endpoint_temperature``, the temperature the march actually reaches, and
    ``shape_rating`` refreshes that operating point before placing a rating. The
    redrawn ``S00709`` declares a 3.5311 W rating against the same 3.5240 W
    dissipation and is SUPPORTED, and the benchmark's false reject went 1 to 0.
    Nothing in the tool changed to make that happen and no bound moved.

    This test keeps the ORIGINAL numbers, and it is not redundant: it is the
    assertion that the tool refuses a part which is over its rating at the
    operating point it converges to. If a future edit ever relaxed that, a
    benchmark whose labels are now sized at the same operating point could not
    tell -- every rating case would move with it.
    """
    _system, _run, reference, converged, power = _converged_probe(
        S00709_PAYLOAD, run_id="s00709"
    )
    rated = 3.49889191

    assert reference.magnitude_in("ohm") == pytest.approx(61.3474, rel=1e-5)
    assert converged.magnitude_in("ohm") == pytest.approx(62.0344, rel=1e-5)

    at_converged = power.magnitude_in("watt")
    at_reference = 14.78541112**2 / reference.magnitude_in("ohm")
    assert at_converged == pytest.approx(3.52399, rel=1e-5)
    assert at_reference == pytest.approx(3.56345, rel=1e-5)

    # Reading the converged value is a smaller overshoot, and still one.
    assert rated < at_converged < at_reference

    report = run_electrothermal_case(S00709_PAYLOAD, run_id="s00709_v").reports[0]
    resistor = next(r for r in report.validity if r.model_id == RESISTOR)
    assert dc_models.DISSIPATED_POWER_UTILIZATION in resistor.assessment.violated
    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED


# =====================================================================
# The companion records, wired
# =====================================================================
#
# `electrical/dc_applicability.py` declared two narrower claims and nothing
# evaluated them. A condition nobody evaluates is a condition that does not
# exist, so these tests are about the seam rather than about the physics --
# the physics is `tests/domains/electrical/test_dc_applicability.py`.

ELEMENT_PATH = ("stages", 0, "conductor", "element")

#: Both from the Bourns PWR220T-20 record in components.json, the same part
#: the shipped example's ratings come from.
ELEMENT_BLOCK = {
    "element_to_body_thermal_resistance": "6.5 kelvin/watt",
    "permissible_element_temperature": "428.15 kelvin",
}

SELF_HEATED = dc_app.SELF_HEATED_RESISTOR_MODEL.model_id
REGULATED = dc_app.REGULATED_VOLTAGE_SOURCE_MODEL.model_id


def _with_source_regulation(**overrides):
    payload = copy.deepcopy(example_electrothermal_payload())
    payload["source_regulation"] = {
        "output_resistance": "0.05 ohm",
        "regulation_band": 0.02,
        **overrides,
    }
    return payload


def test_the_shipped_example_evaluates_the_element_condition():
    """The default run of the product now answers it, rather than declaring it.

    0.42 A into 10 ohm is 2.12 W, the body converges to 338.6 K, and 6.5 K/W
    puts the element 13.8 K above that at 352.4 K against a permissible
    428.15 K. **No other condition in the report can see that number**: the
    lumped model assigns the part one temperature and the rating conditions
    read the declared ambient, 300 K, which is 52 K below where the element
    actually is.
    """
    report = run_electrothermal_case(
        example_electrothermal_payload(), run_id="element"
    ).reports[0]

    element = next(r for r in report.validity if r.model_id == SELF_HEATED)
    assert element.assessment.satisfied == (
        dc_app.ELEMENT_HOT_SPOT_UTILIZATION,
    )
    assert report.verdict is CredibilityVerdict.SUPPORTED
    assert (SELF_HEATED, dc_app.SELF_HEATED_RESISTOR_MODEL.version) in (
        report.contributing_models
    )

    # The arithmetic itself is asserted in the domain tests; what this one is
    # about is that the boundary reached it with the run's own numbers.
    assert dc_app.element_hot_spot_utilization(
        body_temperature=Quantity(338.5770175652607, "kelvin"),
        dissipated_power=Quantity(2.1212899619439667, "watt"),
        element_to_body_thermal_resistance=Quantity(6.5, "kelvin/watt"),
        permissible_element_temperature=Quantity(428.15, "kelvin"),
    ).magnitude == pytest.approx(0.823, abs=5e-4)


def test_a_companion_record_is_absent_until_the_caller_widens_it():
    """Omission removes a claim nobody made. It never satisfies one.

    This is the rule `build_resistance_problem` states for the rated material
    model, applied here: a payload that says nothing about the element does not
    get `electrical.dc.self_heated_resistor` in its report at all, and is not
    told it is under-evidenced against a question it did not ask.

    The distinction that makes this honest rather than a loophole is asserted
    in the same breath: **half** a block is a gap, not an absence.
    """
    bare = copy.deepcopy(example_electrothermal_payload())
    bare["stages"][0]["conductor"].pop("element")
    report = run_electrothermal_case(bare, run_id="bare-element").reports[0]
    assert SELF_HEATED not in {r.model_id for r in report.validity}
    assert SELF_HEATED not in {m for m, _v in report.contributing_models}
    assert report.verdict is CredibilityVerdict.SUPPORTED

    half = copy.deepcopy(example_electrothermal_payload())
    half["stages"][0]["conductor"]["element"] = {
        "permissible_element_temperature": "428.15 kelvin"
    }
    partial = run_electrothermal_case(half, run_id="half-element").reports[0]
    assert (SELF_HEATED, dc_app.ELEMENT_HOT_SPOT_UTILIZATION) in (
        partial.unknown_conditions
    )
    assert partial.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_an_element_hotter_than_it_may_be_is_a_violation():
    """The finding the condition exists for, on a body that is itself fine.

    The permissible element temperature is dropped to 345 K. The **body** at
    338.6 K is below it and every other condition in the report still passes;
    the element, 13.8 K further up at 352.4 K, is not.
    """
    payload = copy.deepcopy(example_electrothermal_payload())
    payload["stages"][0]["conductor"]["element"][
        "permissible_element_temperature"
    ] = "345 kelvin"
    report = run_electrothermal_case(payload, run_id="hot-element").reports[0]

    assert report.violated_conditions == (
        (SELF_HEATED, dc_app.ELEMENT_HOT_SPOT_UTILIZATION),
    )
    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED


def test_the_source_regulation_condition_reaches_the_report():
    """Declared on both sides of its bound, since the example declares neither.

    The shipped example carries no `source_regulation` block on purpose: this
    repository's component data records no output impedance for the part its
    supply names, and one invented to make a condition evaluable would be the
    only number in that payload nobody read off a datasheet. The condition is
    exercised here instead, with numbers this test declares and owns.
    """
    inside = run_electrothermal_case(
        _with_source_regulation(), run_id="reg-in"
    ).reports[0]
    source = next(r for r in inside.validity if r.model_id == REGULATED)
    assert source.assessment.satisfied == (
        dc_app.SOURCE_REGULATION_UTILIZATION,
    )
    assert inside.verdict is CredibilityVerdict.SUPPORTED

    # 0.42 A through 0.05 ohm is 21 mV, 0.42 % of 5 V. A band of 0.002 is
    # tighter than that, and the same supply is then out of domain -- while
    # `source_current_utilization` stays satisfied at 0.14 of its 3 A rating,
    # which is the point: the two conditions fail independently.
    outside = run_electrothermal_case(
        _with_source_regulation(regulation_band=0.002), run_id="reg-out"
    ).reports[0]
    assert outside.violated_conditions == (
        (REGULATED, dc_app.SOURCE_REGULATION_UTILIZATION),
    )
    ideal = next(
        r for r in outside.validity
        if r.model_id == "electrical.dc.ideal_voltage_source"
    )
    assert ideal.assessment.status is ValidityStatus.IN_DOMAIN


def test_a_half_declared_source_regulation_block_is_a_gap():
    """An undeclared band is not an infinite band."""
    payload = copy.deepcopy(example_electrothermal_payload())
    payload["source_regulation"] = {"output_resistance": "0.05 ohm"}
    report = run_electrothermal_case(payload, run_id="reg-half").reports[0]
    assert (REGULATED, dc_app.SOURCE_REGULATION_UTILIZATION) in (
        report.unknown_conditions
    )
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


# =====================================================================
# The second route, wired
# =====================================================================

def test_no_cross_solver_check_is_emitted_unless_one_is_asked_for():
    """Not asking is not the same as asking and not getting.

    A `NOT_RUN` check makes a report INSUFFICIENT_EVIDENCE, so emitting one on
    every machine without a simulator installed would downgrade every report in
    the repository to buy nothing. Omitting the block costs nothing and claims
    nothing, which is how `required_levels` already works.
    """
    report = run_electrothermal_case(
        example_electrothermal_payload(), run_id="no-cross"
    ).reports[0]
    assert CROSS_SOLVER_CHECK_NAME not in {c.name for c in report.validation}
    assert report.verdict is CredibilityVerdict.SUPPORTED


def test_an_unreachable_provider_is_not_run_rather_than_a_pass(monkeypatch):
    """The audit standard's fourth rule, at this boundary.

    A caller who asked for a second route and did not get one has a gap, and
    the report says so rather than quietly reporting agreement it never
    measured. The provider is made unreachable here rather than assumed to be:
    it is installed on this machine, and a test that depended on its *absence*
    would pass for the wrong reason wherever it is missing.
    """
    from engcore.domains.electrical import ngspice as dc_ng

    def unavailable(*_args, **_kwargs):
        raise dc_ng.NgspiceUnavailable("no provider on this machine")

    monkeypatch.setattr(dc_ng, "solve_circuit_with_ngspice", unavailable)

    payload = copy.deepcopy(example_electrothermal_payload())
    payload["cross_solver_check"] = {"external_provider": "ngspice"}
    report = run_electrothermal_case(payload, run_id="cross-absent").reports[0]

    check = next(
        c for c in report.validation if c.name == CROSS_SOLVER_CHECK_NAME
    )
    assert check.outcome is ValidationOutcome.NOT_RUN
    assert check.establishes is None
    assert "could not be reached" in check.detail
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


@pytest.mark.expensive
def test_the_second_route_actually_runs_and_the_level_is_withheld():
    """The whole seam, end to end, against the real external simulator.

    Marked expensive because it shells out to another program, the same mark
    the cross-solver milestone's own tests carry. Measured when it landed: nine
    quantities compared, worst relative difference 4.9e-13 against a declared
    1e-9 -- agreement at machine epsilon, four orders inside the bound.

    And the level is **not** in the report. That is the assertion this test
    exists for: the comparison is real, its residual is recorded, a
    disagreement would fail the report, and `CROSS_SOLVER_VALIDATED` still does
    not attach to a set of temperatures no second route computed.
    """
    payload = copy.deepcopy(example_electrothermal_payload())
    payload["cross_solver_check"] = {"external_provider": "ngspice"}
    report = run_electrothermal_case(payload, run_id="cross-real").reports[0]

    check = next(
        c for c in report.validation if c.name == CROSS_SOLVER_CHECK_NAME
    )
    assert check.outcome is ValidationOutcome.PASS
    assert check.residual < check.tolerance
    assert check.establishes is None
    assert ValidationLevel.CROSS_SOLVER_VALIDATED not in report.attained_levels
    assert report.attained_levels == frozenset(
        {ValidationLevel.ANALYTICALLY_VERIFIED}
    )
    assert report.verdict is CredibilityVerdict.SUPPORTED
    # the routes' own independence argument survives into the record
    assert "sharing no declared component" in check.detail
    assert check.evidence


def test_an_unknown_provider_is_refused_at_the_boundary():
    """The vocabulary is closed, like every other category field."""
    payload = copy.deepcopy(example_electrothermal_payload())
    payload["cross_solver_check"] = {"external_provider": "spice3f5"}
    with pytest.raises(MalformedPayloadError, match="external_provider"):
        run_electrothermal_case(payload, run_id="cross-bogus")


def test_a_reached_consensus_reports_its_agreement_and_withholds_the_level():
    """The wiring, exercised without the provider.

    `_cross_solver_checks` shells out; `_withhold_level` is the part that
    decides what a reached consensus claims **in this report**, and that is what
    is under test. The consensus itself agrees at machine epsilon here because
    both sides are the same numbers -- which is exactly why the level must not
    be readable off this test, and it is not: the assertion is that the level is
    gone and the reason is present.
    """
    from engcore.domains.electrical import dc_consensus as dc_con

    payload = example_electrothermal_payload()
    case = run_electrothermal_case(payload, run_id="cross-wiring")
    problems = build_electrothermal_problems(payload)
    electrical = case.run.final.result_for(problems[0].problem_id)

    from engcore.domains.electrical.dc.solver import ElectricalDCSolver

    identity = ElectricalDCSolver().identity
    consensus = dc_con.dc_consensus(
        native=electrical,
        native_solver=identity,
        external=electrical,
        external_solver=identity,
    )
    raw = consensus.to_check(name=CROSS_SOLVER_CHECK_NAME)
    withheld = _withhold_level(raw)

    assert raw.outcome is withheld.outcome
    assert withheld.residual == raw.residual
    assert withheld.tolerance == raw.tolerance
    assert withheld.evidence == raw.evidence
    assert withheld.establishes is None
    assert "withheld" in withheld.detail
    assert "temperatures" in withheld.detail
    # and the reason is not a claim that the comparison was weak
    assert "not a defect in the comparison" in withheld.detail
