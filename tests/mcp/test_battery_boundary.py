"""The battery over MCP: a second system, and what having two proved.

The battery domain had 14 applicability conditions, 178 tests and a coupled
self-heating march, and no agent could reach any of it. This file tests the
boundary that changed that, and — as much — the restructuring the second
system forced: a description that only worked for one system was never a
description.
"""

from __future__ import annotations

import copy

import pytest

# The MCP SDK is the optional `[mcp]` dependency group. The suite must stay
# runnable — and green — without it, the same rule pytest-xdist is held to.
#
# This module carried no guard at all, and that was not cosmetic:
# `engcore.mcp.server` imports the SDK at module scope, so on any machine
# without it this file raised at COLLECTION and took the whole run with it. CI
# was red on every job from the commit that added this file (2026-09-06 16:47)
# until this one, and a clean-machine install lost 55 tests. NEEDS.md, evidence
# round B.1.
#
# The guard is on `mcp.types`, NOT on `mcp`, and the difference is the whole
# point. `tests/mcp/` has no `__init__.py`, and pytest's prepend import mode
# puts `tests/` on `sys.path` — which makes this very directory a PEP 420
# namespace package called `mcp`. `importorskip("mcp")` therefore FINDS
# something on a machine with no SDK at all and does not skip; measured with
# `importlib.util.find_spec`, it resolves to `tests/mcp` with `loader = None`.
# `mcp.types` exists only in the real SDK, so it is the thing worth asking
# about. `test_server.py` carries the same corrected guard.
pytest.importorskip("mcp.types",
                    reason="install the optional [mcp] dependency group")

from engcore.domains.battery import context as bctx  # noqa: E402
from engcore.domains.battery import models as bmdl  # noqa: E402
from engcore.domains.thermal_models import lumped as lump  # noqa: E402
from engcore.mcp import server as srv  # noqa: E402
from engcore.mcp.battery import (  # noqa: E402
    build_battery_case,
    describe_battery_case,
    example_battery_payload,
    run_battery_case,
)
from engcore.mcp.errors import (  # noqa: E402
    MalformedPayloadError,
    MissingFieldError,
    MissingUnitError,
    UnknownFieldError,
    WrongDimensionError,
)
from engcore.mcp.problem import describe_electrothermal_case  # noqa: E402
from engcore.mcp.systems import SYSTEMS, system  # noqa: E402
from engcore.scientific.models.definition import ValidityStatus  # noqa: E402


def payload(**edits):
    case = copy.deepcopy(example_battery_payload())
    for path, value in edits.items():
        node = case
        *steps, last = path.split(".")
        for step in steps:
            node = node[step]
        if value is None:
            node.pop(last, None)
        else:
            node[last] = value
    return case


def statuses(report):
    return {r.model_id: r.assessment.status for r in report.validity}


# =====================================================================
# It runs, and the verdicts are the domain's own
# =====================================================================

def test_the_example_case_runs_and_every_battery_model_is_in_domain() -> None:
    outcome = run_battery_case(example_battery_payload())
    by_model = statuses(outcome.report)
    for model in bmdl.BATTERY_MODELS:
        assert by_model[model.model_id] is ValidityStatus.IN_DOMAIN
    assert outcome.report.violated_conditions == ()


def test_the_thermal_model_is_reported_and_is_honestly_unknown() -> None:
    """The finding this boundary cannot fix, reported rather than hidden.

    ``run_self_heating_discharge`` takes no applicability declaration, so the
    body it marches has an empty one and the lumped model can never be better
    than UNKNOWN here. Leaving it out of the report would be a report claiming
    nothing about a model that produced half its numbers, so it is in, and it
    says what it is.
    """
    outcome = run_battery_case(example_battery_payload())
    assert (
        statuses(outcome.report)[lump.LUMPED_CAPACITY_MODEL.model_id]
        is ValidityStatus.UNKNOWN
    )
    # And that alone is what keeps a well-formed nominal case off SUPPORTED.
    assert outcome.report.verdict.value == "insufficient_evidence"
    assert outcome.report.violated_conditions == ()


def test_the_verdicts_are_taken_over_the_step_not_at_its_start() -> None:
    """A cell that leaves its temperature range while heating is caught.

    The march assesses at both ends of every step and combines; a boundary
    that read only the instant a step began would report a run ending above a
    declared limit as satisfied. This asserts the boundary carries the
    combined verdict, which is the one the domain computed.
    """
    hot = run_battery_case(
        payload(**{
            "cell.limits.maximum_discharge_temperature": "298.2 kelvin",
        })
    )
    assert (
        statuses(hot.report)["battery.cell.rint_ocv"]
        is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    assert (
        "discharge_temperature_position"
        in dict(hot.report.violated_conditions).values()
        or ("battery.cell.rint_ocv", "discharge_temperature_position")
        in hot.report.violated_conditions
    )


def test_the_march_reports_its_own_outcome_and_never_a_convergence() -> None:
    """One-way, and the response says so rather than implying a fixed point."""
    response = srv.run_battery(example_battery_payload())
    assert response["march"]["coupling"] == "one_way"
    assert response["march"]["outcome"] == "horizon_reached"
    assert response["march"]["steps_run"] == 10
    # No coupling record at all: CouplingEvidence describes an iteration to a
    # fixed point and every number in it would have to be invented here.
    assert response["report"].get("coupling") is None


# =====================================================================
# Optional stays optional, and a missing declaration is UNKNOWN
# =====================================================================

@pytest.mark.parametrize(
    "limit",
    [
        "continuous_discharge_c_rate",
        "pulse_discharge_c_rate",
        "rated_pulse_duration",
        "usable_soc_minimum",
        "minimum_discharge_temperature",
        "resistance_temperature_span",
        "self_heating_rise_bound",
        "polarization_time_constant",
        "soc_step_resolution",
        "capacity_temperature_span",
        "peukert_exponent",
        "peukert_fit_decades",
    ],
)
def test_omitting_a_limit_yields_unknown_and_never_in_domain(limit) -> None:
    field = describe_battery_case().field(f"cell.limits.{limit}")
    assert not field.required

    outcome = run_battery_case(payload(**{f"cell.limits.{limit}": None}))
    unknown = {name for _, name in outcome.report.unknown_conditions}
    assert set(field.unlocks) <= unknown, (limit, field.unlocks)
    for record in outcome.report.validity:
        for condition in field.unlocks:
            assert condition not in record.assessment.satisfied
            assert condition not in record.assessment.violated


def test_the_conductance_is_required_for_a_coupled_run_and_says_so() -> None:
    """The one optional limit a coupled run cannot do without.

    It is both the conductance the self-heating condition is stated over and
    the one the body exchanges through, and the domain refuses to invent a
    second source. Named as a missing field here so an agent is told which key
    to add rather than reading it out of a domain exception.
    """
    with pytest.raises(MissingFieldError) as excinfo:
        build_battery_case(
            payload(**{"cell.limits.cell_thermal_conductance": None})
        )
    assert "cell.limits.cell_thermal_conductance" in str(excinfo.value)


# =====================================================================
# The boundary refuses what it should, with a repair
# =====================================================================

def test_a_bare_number_is_refused_rather_than_given_a_unit() -> None:
    with pytest.raises(MissingUnitError):
        build_battery_case(payload(**{"load.discharge_current": 1.5}))


def test_a_wrong_dimension_is_named_as_one() -> None:
    with pytest.raises(WrongDimensionError):
        build_battery_case(payload(**{"cell.nominal_capacity": "2.5 volt"}))


def test_an_unknown_key_is_refused_with_a_suggestion() -> None:
    case = example_battery_payload()
    case["cell"]["nominal_capactiy"] = "2.5 ampere_hour"
    with pytest.raises(UnknownFieldError) as excinfo:
        build_battery_case(case)
    assert "nominal_capacity" in str(excinfo.value)


def test_a_bad_category_is_refused_against_its_own_vocabulary() -> None:
    """Each system's categories are its own, which one table could not say."""
    with pytest.raises(MalformedPayloadError) as excinfo:
        build_battery_case(payload(**{"cell.chemistry": "forced"}))
    # 'forced' is a thermal convection regime, and was accepted here while the
    # category reader was closed over the thermal vocabulary.
    assert "lithium_ion" in str(excinfo.value)


def test_a_refusal_carries_the_field_the_value_and_the_repair() -> None:
    result = srv.run_battery({"cell": {"cell_id": "C1"}, "load": {},
                              "thermal": {}})
    structured = result.structured_content
    assert structured["error"] == "MissingFieldError"
    assert structured["field"].startswith("cell.")
    assert structured["repair"]
    assert structured["expected"]["required"] is True


# =====================================================================
# The description covers both systems, and is derived
# =====================================================================

def test_capabilities_describe_every_registered_system() -> None:
    capabilities = srv.describe_capabilities()
    described = {entry["name"] for entry in capabilities["systems"]}
    assert described == {boundary.name for boundary in SYSTEMS}
    assert described == {"electrothermal", "battery"}


def test_each_system_names_the_tool_that_runs_it() -> None:
    capabilities = srv.describe_capabilities()
    tools = {tool.name for tool in srv.build_server()._tool_manager.list_tools()}
    for entry in capabilities["systems"]:
        assert entry["tool"] in tools


def test_every_battery_field_is_derived_from_a_model_record() -> None:
    """Nothing about a field is written down twice.

    Required-ness, dimension, unit exemplar and prose come from the model the
    binding names. A field whose model input stopped existing is an import
    failure in ``audit_bindings``, not a description that has quietly stopped
    being true.
    """
    description = describe_battery_case()
    by_id = {m.model_id: m for m in (*bmdl.BATTERY_MODELS,
                                     lump.LUMPED_CAPACITY_MODEL)}
    for field in description.fields:
        if field.model_id is None:
            continue
        spec = next(
            s for s in by_id[field.model_id].inputs if s.name == field.model_input
        )
        assert field.required == spec.required
        assert field.unit_exemplar == spec.unit_exemplar
        assert field.description == spec.description


def test_every_declared_limit_is_a_payload_field() -> None:
    """The binding table is built from LIMIT_SPECS, so it cannot fall behind."""
    keys = {f.key for f in describe_battery_case().fields
            if f.section == "cell.limits"}
    assert {spec.name for spec in bctx.LIMIT_SPECS} <= keys


def test_the_two_descriptions_do_not_share_their_examples() -> None:
    """The regression the restructuring removes.

    ``CaseDescription`` used to call one system's example builder from its own
    ``to_dict``, so any second system would have handed an agent the
    electro-thermal example under its own name.
    """
    battery = describe_battery_case().to_dict()["example"]
    electrothermal = describe_electrothermal_case().to_dict()["example"]
    assert "cell" in battery and "stages" not in battery
    assert "stages" in electrothermal and "cell" not in electrothermal


def test_the_example_each_system_publishes_actually_runs() -> None:
    """A description that hands back an example nothing accepts is worse than
    no example, so both are executed here rather than inspected."""
    for boundary in SYSTEMS:
        example = boundary.description().to_dict()["example"]
        boundary.run(example)


def test_an_unregistered_system_is_a_loud_failure() -> None:
    with pytest.raises(KeyError):
        system("thermodynamics")


# =====================================================================
# An inert category says so where the caller reads it, not only in source
# =====================================================================
#
# `chemistry` and `duty_type` are validated, stored and serialized, and they
# select no equation and gate no condition. A caller who declares
# `lithium_ion` and believes the physics changed has been misled by the field
# existing. The records and the binding table have said "inert" in prose since
# they were written -- but prose in a source file is not the caller boundary,
# and nothing asserted that the sentence survives as far as the caller.
#
# These tests are that assertion. They do not narrow anything: the notes were
# already correct and already reaching `describe_capabilities`. What was
# missing is that deleting one would have broken nothing.

#: Every caller-declarable category that no condition reads, and the field
#: path a caller sees it at. Written out rather than derived: the claim is
#: about these four specifically, and a fifth inert category should have to be
#: added here deliberately.
INERT_CATEGORY_FIELDS = (
    "cell.chemistry",
    "cell.limits.cooling_mode",
    "load.duty_type",
)


@pytest.mark.parametrize("path", INERT_CATEGORY_FIELDS)
def test_an_inert_category_declares_its_inertness_to_the_caller(path):
    """The word a caller needs is in the description they are handed."""
    field = describe_battery_case().field(path)
    text = field.description.lower()
    assert any(
        phrase in text
        for phrase in ("inert", "not modelled", "unlocks nothing")
    ), f"{path} does not tell the caller it is inert: {field.description!r}"


@pytest.mark.parametrize("path", INERT_CATEGORY_FIELDS)
def test_an_inert_category_unlocks_no_condition(path):
    """And the prose agrees with the machinery.

    `unlocks` is computed by measurement -- declare the field, see which
    conditions stop being UNKNOWN. An inert category must move none, or the
    description above is the thing that is wrong.
    """
    field = describe_battery_case().field(path)
    assert field.unlocks == ()
    assert field.group_unlocks == ()
    assert field.alternative_to == ()


def test_the_inertness_survives_to_describe_capabilities():
    """The tool a caller actually calls, not the helper underneath it.

    `describe_capabilities` is the MCP surface. If the battery description
    were ever assembled into it by a path that drops `note`, every test above
    would still pass and the caller would still be misled.
    """
    import json

    blob = json.dumps(srv.describe_capabilities(), default=str)
    for phrase in (
        "no validity condition reads it and it unlocks nothing",
        "Declaring 'pulsed' does not satisfy the pulse conditions",
    ):
        assert phrase in blob, phrase


def test_the_chemistry_vocabulary_is_families_and_not_cathode_chemistries():
    """A caller cannot declare LFP or NMC at all, which is worth knowing.

    The vocabulary is three broad families. A lithium-ion sub-chemistry is
    refused at construction rather than silently accepted and ignored, so the
    "does LFP change the physics" question never reaches the inert field. That
    is a stronger answer than the note, and it is asserted here so that
    widening the vocabulary is a deliberate act.
    """
    assert set(bctx.CHEMISTRY_VOCABULARY) == {
        "lithium_ion", "lead_acid", "nickel_metal_hydride",
    }
    payload = copy.deepcopy(example_battery_payload())
    payload["cell"]["chemistry"] = "LFP"
    with pytest.raises(Exception):
        build_battery_case(payload)
