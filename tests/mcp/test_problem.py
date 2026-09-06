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
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.results.validation import ValidationLevel
from src.engcore.scientific.units.quantity import Quantity, dimensionality

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


def payload_without(section_path, key):
    """A deep copy of the applicable payload with one key removed."""
    payload = copy.deepcopy(APPLICABLE_PAYLOAD)
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
    assert report.verdict is CredibilityVerdict.SUPPORTED
    assert report.violated_conditions == ()
    assert report.unknown_conditions == ()
    assert report.failed_checks == () and report.not_run_checks == ()
    # SUPPORTED here rests on the level the lumped solver's reference
    # comparison establishes — exactly as in the hand-built case, and for the
    # same reason. The payload boundary neither adds nor removes evidence.
    assert report.attained_levels == frozenset(
        {ValidationLevel.ANALYTICALLY_VERIFIED}
    )


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
        elif field.section == "stages[].conductor.limits":
            continue  # absent from this payload; covered by its own test below
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

    outcome = run_electrothermal_case(
        payload_without(APPLICABILITY_PATH, key), run_id=f"omit-{key}"
    )
    report = outcome.reports[0]
    unknown = {name for _, name in report.unknown_conditions}

    assert set(field.unlocks) <= unknown, (key, field.unlocks, sorted(unknown))
    # The asymmetry that makes optional safe: a missing declaration never
    # satisfies anything, and never violates anything either.
    assessment = report.validity[0].assessment
    for condition in field.unlocks:
        assert condition not in assessment.satisfied
        assert condition not in assessment.violated
    if field.unlocks:
        assert assessment.status is ValidityStatus.UNKNOWN
        assert report.verdict is not CredibilityVerdict.NOT_SUPPORTED


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
    known = lumped_conditions | rated_conditions

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
    assert report.unknown_conditions == ()
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
