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

from src.engcore.domains.electrical import material as mat
from src.engcore.domains.electrical.dc import models as dc_models
from src.engcore.domains.thermal_models import context as ctx
from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.mcp import (
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
    run_electrothermal_case,
)
from src.engcore.mcp import evidence
from src.engcore.scientific.errors import InvalidScientificProblem
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.results.validation import ValidationLevel
from src.engcore.scientific.units.quantity import Quantity, dimensionality
from src.engcore.systems.electrothermal import coupled as cp

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

MODELS = (
    lump.LUMPED_CAPACITY_MODEL,
    mat.LINEAR_TCR_MODEL,
    mat.RATED_LINEAR_TCR_MODEL,
    dc_models.IDEAL_VOLTAGE_SOURCE_MODEL,
    dc_models.RESISTOR_OHM_MODEL,
    dc_models.KCL_MODEL,
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
            "source_ratings",
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
    }
    assert assessed(report) == expected
    assert {m for m, _v in report.contributing_models} >= expected
    assert report.unassessed_models == ()


def test_the_undeclared_electrical_ratings_are_reported_as_gaps():
    """Nobody declared these limits, so they stay UNKNOWN.

    The example payload declares no ``ratings`` block, and an absent rating is
    UNKNOWN rather than unlimited. That behaviour is the point and it did not
    change when the block was added: what changed is that a caller who *can*
    state the ratings is no longer forced into this verdict by the boundary
    having nowhere to put them. ``test_declared_ratings_reach_the_report``
    below is the other half.
    """
    report = run_electrothermal_case(
        example_electrothermal_payload(), run_id="gaps"
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
        example_electrothermal_payload(), run_id="bare"
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
