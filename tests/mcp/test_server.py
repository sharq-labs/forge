"""What an agent sees, and whether the transport changed anything on the way.

Driven through the **in-process MCP client** — the real protocol path, real
serialization, no network and no subprocess — because the thing under test is
what an agent receives, not what a Python function returns.

Two claims run through the file. **The transport changes nothing**: a verdict
reached over the wire is the verdict `run_electrothermal_case` produces
directly, including when it is unflattering. And **a refusal is repairable**:
an agent that sends a bad case gets the field, what it sent and what was
expected, not a traceback and not "Error executing tool".
"""

from __future__ import annotations

import copy
import json
import types

import pytest

anyio = pytest.importorskip("anyio")
# The MCP SDK is the optional `[mcp]` dependency group. The suite must stay
# runnable — and green — without it, the same rule pytest-xdist is held to.
# `mcp.types`, not `mcp`. This guard was written as `importorskip("mcp")` and
# never fired: `tests/mcp/` has no `__init__.py` and pytest puts `tests/` on
# `sys.path`, so this directory IS an importable PEP 420 namespace package
# named `mcp`. The guard only appeared to work because the `anyio` check above
# it skips first on the machines anyone tried. `mcp.types` exists only in the
# real SDK. See tests/mcp/test_battery_boundary.py for the measurement.
pytest.importorskip("mcp.types",
                    reason="install the optional [mcp] dependency group")

import mcp.types as mcp_types  # noqa: E402
from mcp import Client  # noqa: E402

from src.engcore.domains.electrical import material as mat  # noqa: E402
from src.engcore.domains.electrical.dc import models as dc_models  # noqa: E402
from src.engcore.domains.thermal_models import lumped as lump  # noqa: E402
from src.engcore.mcp.systems import SYSTEMS  # noqa: E402
from src.engcore.mcp import (  # noqa: E402
    COUPLING_SUPPLIED_INPUTS,
    CredibilityVerdict,
    example_electrothermal_payload,
    example_over_rating_payload,
    run_electrothermal_case,
)
from src.engcore.mcp import server  # noqa: E402
from src.engcore.mcp.server import (  # noqa: E402
    CAPABILITIES_SCHEMA,
    RESPONSE_SCHEMA,
    build_server,
)
from src.engcore.scientific.models.definition import (  # noqa: E402
    ValidityAssessment,
    ValidityStatus,
)

MODELS = (
    lump.LUMPED_CAPACITY_MODEL,
    mat.LINEAR_TCR_MODEL,
    mat.RATED_LINEAR_TCR_MODEL,
    dc_models.IDEAL_VOLTAGE_SOURCE_MODEL,
    dc_models.RESISTOR_OHM_MODEL,
    dc_models.KCL_MODEL,
)


def _in_session(work):
    """Run one coroutine against a freshly built server over the real protocol."""

    async def main():
        async with Client(build_server()) as client:
            return await work(client)

    return anyio.run(main)


def list_tools():
    return _in_session(lambda c: c.list_tools())


def call(name, arguments=None):
    return _in_session(lambda c: c.call_tool(name, arguments or {}))


def capabilities():
    return call("describe_capabilities").structured_content


def run_case(payload):
    return call("run_electrothermal", {"case": payload})


def unrated_payload():
    """The example case with its declared component ratings stripped off.

    The shipped example declares ratings read from real datasheets, so it no
    longer has a gap in it. Two tests below are *about* gaps — one about how a
    gap is reported, one about a violation outranking one — and they need a
    payload that still has one. Removing the two blocks is that payload, and it
    is what the example was before the ratings were added.
    """
    payload = example_electrothermal_payload()
    payload["stages"][0]["conductor"].pop("ratings", None)
    payload.pop("source_ratings", None)
    return payload


def violating_payload():
    """The example case with the conductor rated below where it will run.

    `maximum_operating_temperature` is a condition of the *rated* material
    model, and the run settles near 338 K, so 301 K is a bound the run is
    known to cross — a finding, not a gap.

    Built on `unrated_payload` rather than on the example directly, because the
    test that reads it asserts *precedence* — that a violation outranks a gap
    without erasing it — and that needs a report which has both.
    """
    payload = unrated_payload()
    payload["stages"][0]["conductor"]["limits"][
        "maximum_operating_temperature"
    ] = "301 kelvin"
    return payload


# =====================================================================
# The tools, and their schemas
# =====================================================================

def test_the_server_exposes_one_run_tool_per_system_with_usable_schemas():
    """One describe tool, and one run tool for every registered system.

    Was "exactly two tools" while there was one system. The list is derived
    from the registry rather than written out, so a third system's tool joins
    it here without this test being edited -- and a system registered without
    a tool fails in `build_server` before it can reach an agent.
    """
    tools = {tool.name: tool for tool in list_tools().tools}
    assert sorted(tools) == sorted(
        ["describe_capabilities"] + [s.tool for s in SYSTEMS]
    )

    describe = tools["describe_capabilities"]
    assert describe.input_schema.get("properties") == {}
    assert describe.output_schema is not None

    for boundary in SYSTEMS:
        run = tools[boundary.tool]
        assert list(run.input_schema["properties"]) == ["case"]
        assert run.input_schema["required"] == ["case"]
        assert run.output_schema is not None


def test_the_descriptions_say_what_an_agent_must_know_before_calling():
    """The tool text is the product. These are the facts it cannot omit."""
    tools = {tool.name: tool.description for tool in list_tools().tools}
    describe = tools["describe_capabilities"]
    # A unit is mandatory, and an unknown key is refused rather than dropped.
    assert '"10 ohm", never 10' in describe
    assert "refused, not ignored" in describe

    run = tools["run_electrothermal"]
    for verdict in CredibilityVerdict:
        assert verdict.name in run
    # The unflattering nominal verdict is announced rather than hidden, so an
    # agent does not read it as a failure and retry.
    assert "Expect INSUFFICIENT_EVIDENCE" in run
    assert "advisory input to an engineer of record" in run


# =====================================================================
# describe_capabilities
# =====================================================================

def test_capabilities_describe_exactly_the_fields_the_registries_declare():
    """The expectation is recomputed from the model records, not from the
    description, so drift on either side fails here."""
    system = capabilities()["systems"][0]
    described = {
        field["model_input"]
        for field in system["fields"]
        if field["model_input"] is not None
    }
    declared = {spec.name for model in MODELS for spec in model.inputs}

    assert described | set(COUPLING_SUPPLIED_INPUTS) == declared
    assert described & set(COUPLING_SUPPLIED_INPUTS) == set()
    assert system["models"] == sorted({m.model_id for m in MODELS})


def test_every_described_field_carries_the_models_own_required_and_dimension():
    by_name = {spec.name: spec for model in MODELS for spec in model.inputs}
    fields = capabilities()["systems"][0]["fields"]
    assert len(fields) == len({f["path"] for f in fields}), "duplicated path"
    for field in fields:
        assert field["required"] in (True, False)
        if field["model_input"] is None:
            continue
        spec = by_name[field["model_input"]]
        assert field["required"] is spec.required, field["path"]
        assert field["unit_exemplar"] == spec.unit_exemplar, field["path"]
        assert field["dimension"], field["path"]


def test_an_optional_field_says_which_conditions_it_unlocks():
    """Every condition name reported is one a model actually declares, and
    only an optional field can unlock anything."""
    known = {c.name for m in MODELS for c in m.validity.conditions}
    mentioned = set()
    for field in capabilities()["systems"][0]["fields"]:
        if field["unlocks_conditions"]:
            assert not field["required"], field["path"]
        mentioned |= set(field["unlocks_conditions"])
        mentioned |= set(field["group_unlocks_conditions"])
    assert mentioned, "no optional field unlocks anything"
    assert mentioned <= known, sorted(mentioned - known)


def test_capabilities_name_the_fields_a_caller_may_not_supply():
    """Per system, because which inputs a run solves for is a per-system fact.

    It was a top-level key while there was one system, which read as a
    statement about the runtime and was a statement about the electro-thermal
    composition. The battery system solves for nothing a caller might
    otherwise declare -- the march advances the temperature and the state of
    charge from declared starting points -- so its list is empty, and that is
    a fact about that system rather than a gap in this description.
    """
    caps = capabilities()
    by_name = {entry["name"]: entry for entry in caps["systems"]}
    assert set(by_name) == {s.name for s in SYSTEMS}

    forbidden = {
        entry["model_input"]: entry["why"]
        for entry in by_name["electrothermal"]["fields_you_may_not_supply"]
    }
    assert forbidden == dict(COUPLING_SUPPLIED_INPUTS)

    for entry in caps["systems"]:
        # Whatever a system solves for, no field of that system may declare it.
        names = {e["model_input"] for e in entry["fields_you_may_not_supply"]}
        assert {f["key"] for f in entry["fields"]} & names == set()


def test_capabilities_say_what_each_verdict_means_and_does_not():
    caps = capabilities()
    stated = {entry["value"]: entry for entry in caps["verdicts"]}
    assert set(stated) == {v.value for v in CredibilityVerdict}
    for entry in stated.values():
        assert entry["means"] and entry["does_not_mean"] and entry["action"]
    assert "not a decision" in caps["notice"]
    assert caps["schema"] == CAPABILITIES_SCHEMA


def test_the_example_case_in_the_capabilities_actually_runs():
    example = capabilities()["systems"][0]["example_case"]
    assert run_case(example).is_error is False


# =====================================================================
# The transport changes nothing
# =====================================================================

@pytest.mark.parametrize(
    "make_payload",
    [example_electrothermal_payload, violating_payload],
    ids=["nominal", "violated_bound"],
)
def test_the_wire_verdict_is_the_verdict_the_runtime_produced(make_payload):
    payload = make_payload()
    direct = run_electrothermal_case(copy.deepcopy(payload)).reports
    response = run_case(payload)
    assert response.is_error is False

    stages = response.structured_content["stages"]
    assert len(stages) == len(direct)
    for stage, report in zip(stages, direct):
        assert stage["verdict"]["value"] == report.verdict.value
        assert stage["report"]["verdict"] == report.verdict.value
        assert stage["report"]["values"] == report.to_dict()["values"]


def test_the_nominal_case_reaches_a_supported_verdict_over_the_wire():
    """The default example of the product, as an agent actually receives it.

    This is the assertion the round closed. The shipped example declares
    ratings from real parts, every condition it raises is now answered, and the
    transport carries SUPPORTED with nothing left unknown and nothing violated.
    """
    stage = run_case(example_electrothermal_payload()).structured_content[
        "stages"
    ][0]
    assert stage["verdict"]["value"] == CredibilityVerdict.SUPPORTED.value
    assert stage["verdict"]["verdict_reasons"] == []
    for record in stage["report"]["validity"]:
        assert record["assessment"]["unknown"] == []
        assert record["assessment"]["violated"] == []


def test_the_over_rating_example_is_not_supported_over_the_wire():
    """The second exported example, named by the condition it crosses."""
    stage = run_case(example_over_rating_payload()).structured_content[
        "stages"
    ][0]
    assert stage["verdict"]["value"] == CredibilityVerdict.NOT_SUPPORTED.value
    violated = [
        reason for reason in stage["verdict"]["verdict_reasons"]
        if reason["rule"] == "model_validity_violated"
    ]
    assert violated[0]["detail"]["violated_conditions"] == [
        {
            "model_id": "electrical.dc.ideal_voltage_source",
            "condition": "source_current_utilization",
        }
    ]


def test_an_unrated_case_reports_its_gaps_and_is_not_made_nicer():
    """INSUFFICIENT_EVIDENCE is the runtime's real answer to a payload that
    declares no ratings, and the transport says so, naming what is missing.

    ``electrical.dc.kcl`` used to be the other half of this and no longer is:
    it declares a condition now, satisfied by the DC model's own scope, so it
    is assessed rather than unknown. What keeps the verdict where it is here is
    the missing ``ratings`` block, which is the only thing this payload takes
    away from the shipped example.
    """
    stage = run_case(unrated_payload()).structured_content[
        "stages"
    ][0]
    assert stage["verdict"]["value"] == CredibilityVerdict.INSUFFICIENT_EVIDENCE.value

    unknown = [
        reason for reason in stage["verdict"]["verdict_reasons"]
        if reason["rule"] == "model_validity_unknown"
    ]
    assert unknown, "a gap verdict with nothing named is unactionable"
    models = {m["model_id"]: m for m in unknown[0]["detail"]["models"]}
    assert "dissipated_power_utilization" in models[
        "electrical.dc.resistor_ohm"
    ]["unknown_conditions"]
    # Kirchhoff's law is no longer among the gaps: its condition is satisfied
    # by scope. The gap that remains is the one the payload really has.
    assert "electrical.dc.kcl" not in models


def test_a_violated_material_limit_is_not_supported_and_names_the_condition():
    stage = run_case(violating_payload()).structured_content["stages"][0]
    assert stage["verdict"]["value"] == CredibilityVerdict.NOT_SUPPORTED.value

    violated = [
        reason for reason in stage["verdict"]["verdict_reasons"]
        if reason["rule"] == "model_validity_violated"
    ]
    assert len(violated) == 1
    assert violated[0]["detail"]["violated_conditions"] == [
        {
            "model_id": "electrical.material.rated_linear_tcr_resistance",
            "condition": "operating_temperature_utilization",
        }
    ]
    # The gaps are still present and still reported — outranked, not erased.
    assert any(
        reason["produces"] == CredibilityVerdict.INSUFFICIENT_EVIDENCE.value
        for reason in stage["verdict"]["other_findings"]
    )


def test_a_capped_coupling_reaches_the_response_as_its_own_field():
    payload = example_electrothermal_payload()
    payload["coupling"]["max_iterations"] = 1
    response = run_case(payload).structured_content

    assert response["coupling"]["outcome"] == "iteration_limit_reached"
    assert response["coupling"]["criterion"] == "not_met"
    assert response["coupling"]["iterations_run"] == 1

    verdict = response["stages"][0]["verdict"]
    assert verdict["value"] == CredibilityVerdict.INSUFFICIENT_EVIDENCE.value
    capped = [
        reason for reason in verdict["verdict_reasons"]
        if reason["rule"] == "coupling_criterion_not_met"
    ]
    assert capped and capped[0]["detail"]["iteration_limit"] == 1


def test_a_report_carries_validity_validation_provenance_and_the_claim():
    stage = run_case(example_electrothermal_payload()).structured_content[
        "stages"
    ][0]
    report = stage["report"]
    assert stage["component_id"] == "R1"
    assert report["schema"] == "mcp_evidence_package/1"

    assert {r["model_id"] for r in report["validity"]} == {
        m.model_id for m in MODELS
    }
    for record in report["validity"]:
        assert set(record["assessment"]) >= {
            "status", "satisfied", "violated", "unknown"
        }
    for check in report["validation"]:
        assert check["outcome"] in {"pass", "fail", "warning", "not_run"}
        assert "establishes" in check
    assert report["provenance"]["run_id"]
    # The caller's own claim, fenced by markings that survive the wire.
    claim = report["declarations"][0]
    assert claim["caller_asserted"] is True
    assert claim["consumed_by_verdict"] is False


# =====================================================================
# A refusal an agent can repair from
# =====================================================================

@pytest.mark.parametrize(
    "mutate, error, field, received",
    [
        (lambda p: p["stages"][0]["conductor"].__setitem__(
            "reference_resistance", 10),
         "MissingUnitError", "stages[0].conductor.reference_resistance", 10),
        (lambda p: p["stages"][0]["body"].__setitem__("duration", "120 kelvin"),
         "WrongDimensionError", "stages[0].body.duration", "120 kelvin"),
        (lambda p: p["stages"][0]["body"].pop("heat_capacity"),
         "MissingFieldError", "stages[0].body.heat_capacity", None),
        (lambda p: p["stages"][0]["body"]["applicability"].__setitem__(
            "conductivty", "1 watt/meter/kelvin"),
         "UnknownFieldError",
         "stages[0].body.applicability.conductivty", "1 watt/meter/kelvin"),
        (lambda p: p["coupling"].__setitem__("max_iterations", 0),
         "MalformedPayloadError", "coupling.max_iterations", 0),
    ],
    ids=["bare_number", "wrong_dimension", "missing_required",
         "misspelled_key", "inadmissible_value"],
)
def test_a_bad_case_returns_a_structured_error_naming_the_field(
    mutate, error, field, received
):
    payload = example_electrothermal_payload()
    mutate(payload)
    response = run_case(payload)

    assert response.is_error is True
    detail = response.structured_content
    assert detail["error"] == error
    assert detail["field"] == field
    # Echoed from the caller's own payload, not re-parsed out of the message.
    assert detail["received"] == received
    assert detail["repair"]
    assert detail["expected"]

    text = response.content[0].text
    assert "Traceback" not in text
    assert "Error executing tool" not in text
    assert field in text


def test_a_refusal_says_what_the_field_should_have_been():
    payload = example_electrothermal_payload()
    payload["stages"][0]["body"]["duration"] = "120 kelvin"
    expected = run_case(payload).structured_content["expected"]
    assert expected["dimension"] == "[time]"
    assert expected["unit_exemplar"] == "second"
    assert expected["required"] is True

    # A key with no field record — a container, or one that does not exist —
    # is answered with the keys its section does take, derived the same way.
    payload = example_electrothermal_payload()
    payload["stages"][0]["bdy"] = {}
    assert run_case(payload).structured_content["expected"] == {
        "accepted_keys": ["body", "component_id", "conductor"]
    }


def test_the_repaired_case_runs():
    """The whole point of a structured refusal: one round trip, then a run."""
    payload = example_electrothermal_payload()
    payload["stages"][0]["body"]["heat_capacity"] = 2.5
    refusal = run_case(payload).structured_content
    payload["stages"][0]["body"][refusal["expected"]["key"]] = (
        f"2.5 {refusal['expected']['unit_exemplar']}"
    )
    assert run_case(payload).is_error is False


# =====================================================================
# Nothing is lost on the wire
# =====================================================================

def test_the_response_round_trips_as_json_with_nothing_lost():
    response = run_case(violating_payload())
    structured = response.structured_content
    assert structured["schema"] == RESPONSE_SCHEMA
    assert json.loads(json.dumps(structured)) == structured
    # The text block is the same document, not a summary of it.
    assert json.loads(response.content[0].text) == structured


def test_the_wire_report_is_the_reports_own_serialization():
    """Exactly the record `to_dict` produced: the transport wraps it and puts
    the reasons beside it, and edits nothing inside.

    Asserted whole rather than key by key, and the run is deterministic —
    provenance run id and timestamp included — so there is nothing to exempt.
    """
    payload = violating_payload()
    direct = run_electrothermal_case(copy.deepcopy(payload)).reports[0]
    wire = run_case(payload).structured_content["stages"][0]["report"]
    assert wire == json.loads(json.dumps(direct.to_dict()))


def test_an_unknown_tool_is_an_error_and_not_a_crash():
    result = call("run_electrothermal_v2")
    assert result.is_error is True
    assert isinstance(result.content[0], mcp_types.TextContent)


# =====================================================================
# The two guards that keep the transport honest
# =====================================================================

def test_a_verdict_no_rule_explains_is_refused_rather_than_transmitted():
    """If the reason enumeration falls out of step with `derive_verdict`, an
    agent would receive a refusal with nothing behind it. It fails here."""
    clean = types.SimpleNamespace(
        model_id="m",
        assessment=ValidityAssessment(
            status=ValidityStatus.IN_DOMAIN,
            satisfied=("c",), violated=(), unknown=(),
        ),
    )
    unexplained = types.SimpleNamespace(
        run_id="r", verdict=CredibilityVerdict.NOT_SUPPORTED, coupling=None,
        validity=(clean,), violated_conditions=(), failed_checks=(),
        not_run_checks=(), unassessed_models=(), unattributed_assessments=(),
        warning_checks=(), attained_levels={"level"}, missing_required_levels=(),
    )
    with pytest.raises(RuntimeError, match="no rule that produced it"):
        server._verdict_block(unexplained)

    # The same report reported as SUPPORTED needs no rule and is fine.
    unexplained.verdict = CredibilityVerdict.SUPPORTED
    assert server._verdict_block(unexplained)["verdict_reasons"] == []


def test_an_undescribed_verdict_or_refusal_class_fails_at_import(monkeypatch):
    """A verdict with no explanation, or a refusal class with no repair, must
    not reach an agent unexplained."""
    monkeypatch.setattr(
        server, "_VERDICT_GUIDANCE",
        {k: v for k, v in server._VERDICT_GUIDANCE.items()
         if k is not CredibilityVerdict.SUPPORTED},
    )
    with pytest.raises(RuntimeError, match="must not reach an agent"):
        server._audit_tables()
