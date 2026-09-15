"""Audit stream "results": CAP-04 and the MCP half of RES-08.

Written against the unfixed boundary and seen failing first.

CAP-04  Every asserted-context record went on the wire as ``consumed_by_verdict: false``, and both MCP tool
        descriptions said the caller's declarations were "consumed by no verdict". In both shipped assemblers the
        declared values ARE what the validity conditions are computed from: the electrothermal body conductivity
        200 -> 0.05 W/(m K) and the battery continuous C-rate 3 -> 0.5 1/h each move the verdict, while the record
        kept saying ``false``. The flag now states whether the assembler evaluated validity conditions from the
        declared values (``true`` in both assemblers), is ``null`` when nobody stated it, and is never a default
        ``false``.
RES-08  ``CredibilityEvidenceReport.from_dict`` checked the serialized verdict only when the key was present, and
        never read ``verdict_qualifiers`` back, so a hand-edited report could drop its verdict or rewrite the
        qualifiers a JSON reader acts on (warnings, attained levels, gaps).
"""

from __future__ import annotations

import copy
import json

import pytest

from engcore.mcp.battery import example_battery_payload, run_battery_case
from engcore.mcp.errors import CredibilityEvidenceError
from engcore.mcp.evidence import (
    ASSERTED_CONTEXT_SCHEMA,
    AssertedContext,
    CredibilityEvidenceReport,
)
from engcore.mcp.problem import example_electrothermal_payload, run_electrothermal_case


def _electrothermal(conductivity: str):
    payload = example_electrothermal_payload()
    payload["stages"][0]["body"]["applicability"]["body_conductivity"] = conductivity
    return run_electrothermal_case(payload, run_id=f"cap04-{conductivity}").reports[0]


def _battery(c_rate: str):
    payload = example_battery_payload()
    payload["cell"]["limits"]["continuous_discharge_c_rate"] = c_rate
    return run_battery_case(payload, run_id=f"cap04-{c_rate}").report


# =====================================================================
# CAP-04
# =====================================================================

def test_cap04_a_declaration_that_moves_the_electrothermal_verdict_says_so():
    conducting, insulating = _electrothermal("200 watt/meter/kelvin"), _electrothermal("0.05 watt/meter/kelvin")
    assert conducting.verdict is not insulating.verdict, "the declared value must actually decide the verdict"
    for report in (conducting, insulating):
        (declaration,) = report.declarations
        assert declaration.to_dict()["consumed_by_verdict"] is True


def test_cap04_a_declaration_that_moves_the_battery_verdict_says_so():
    rated, derated = _battery("3 1/hour"), _battery("0.5 1/hour")
    assert rated.verdict is not derated.verdict, "the declared value must actually decide the verdict"
    for report in (rated, derated):
        wire = {d.source: d.to_dict() for d in report.declarations}
        assert wire["CellLimits"]["consumed_by_verdict"] is True
        assert wire["DischargeLoad"]["consumed_by_verdict"] is True


def test_cap04_an_unstated_flag_is_null_on_the_wire_never_false():
    declaration = AssertedContext(source="Caller", payload={"note": "anything"})
    wire = declaration.to_dict()
    assert wire["schema"] == ASSERTED_CONTEXT_SCHEMA == "mcp_asserted_context/2"
    assert wire["caller_asserted"] is True
    assert wire["consumed_by_verdict"] is None


def test_cap04_the_flag_round_trips_and_a_non_boolean_is_refused():
    stated = AssertedContext(source="Caller", payload={"x": "1 meter"}, consumed_by_verdict=True)
    assert AssertedContext.from_dict(json.loads(json.dumps(stated.to_dict()))) == stated
    bad = dict(stated.to_dict(), consumed_by_verdict="yes")
    with pytest.raises(CredibilityEvidenceError, match="consumed_by_verdict"):
        AssertedContext.from_dict(bad)


def test_cap04_a_v1_record_is_read_but_its_literal_false_is_not_believed():
    legacy = dict(
        AssertedContext(source="Caller", payload={"x": "1 meter"}).to_dict(),
        schema="mcp_asserted_context/1",
        consumed_by_verdict=False,
    )
    assert AssertedContext.from_dict(legacy).consumed_by_verdict is None


def test_cap04_the_tool_descriptions_no_longer_say_consumed_by_no_verdict():
    pytest.importorskip("mcp.types", reason="install the optional [mcp] dependency group")
    from engcore.mcp import server

    for description in (server._RUN_DESCRIPTION, server._RUN_BATTERY_DESCRIPTION):
        flat = " ".join(description.split())
        assert "consumed by no verdict" not in flat
        assert "consumed_by_verdict" in flat


# =====================================================================
# RES-08 (MCP)
# =====================================================================

def _report_payload() -> dict:
    return json.loads(json.dumps(_battery("3 1/hour").to_dict()))


def test_res08_the_control_round_trips():
    payload = _report_payload()
    assert CredibilityEvidenceReport.from_dict(payload).to_dict() == payload


def test_res08_a_report_without_its_verdict_is_refused():
    payload = _report_payload()
    del payload["verdict"]
    with pytest.raises(CredibilityEvidenceError, match="verdict"):
        CredibilityEvidenceReport.from_dict(payload)


@pytest.mark.parametrize(
    "qualifier, forged",
    [
        ("warning_checks", ["a_warning_nobody_raised"]),
        ("attained_levels", ["experimentally_validated"]),
        ("unassessed_models", []),
        ("unattributed_assessments", [["some.model", "1"]]),
        ("unresolved_models", [["some.model", "1"]]),
    ],
)
def test_res08_a_rewritten_verdict_qualifier_is_refused(qualifier, forged):
    payload = _report_payload()
    qualifiers = payload["verdict_qualifiers"]
    if qualifiers[qualifier] == forged:
        forged = forged + [["another.model", "1"]] if qualifier.endswith("models") else forged + ["x"]
    qualifiers[qualifier] = forged
    with pytest.raises(CredibilityEvidenceError, match=qualifier):
        CredibilityEvidenceReport.from_dict(copy.deepcopy(payload))


def test_res08_an_unknown_qualifier_is_refused():
    payload = _report_payload()
    payload["verdict_qualifiers"]["looks_fine"] = True
    with pytest.raises(CredibilityEvidenceError, match="looks_fine"):
        CredibilityEvidenceReport.from_dict(payload)
