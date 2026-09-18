"""CORE-7: repair records are structured, deterministic and built from declarations."""

from __future__ import annotations

import json

import pytest

from engcore.claims import ClaimLayerError, RepairAction, RepairKind, build_case, inputs_from_case, merge_repairs
from engcore.claims.errors import CapabilityInputError
from engcore.mcp import example_electrothermal_payload
from engcore.mcp.battery import example_battery_payload
from engcore.mcp.capabilities import production_registry


def test_a_repair_is_a_serializable_record_and_refuses_what_it_cannot_serialize() -> None:
    repair = RepairAction(
        RepairKind.SUPPLY_INPUT,
        "stages[0].body.heat_capacity",
        "Total heat capacity of the body; strictly positive.",
        required_for=("execution", "model:thermal.lumped.first_order_capacity"),
        source="capability:system.electrothermal#input:stages[].body.heat_capacity",
        detail={"unit_exemplar": "joule / kelvin"},
    )
    assert json.loads(json.dumps(repair.to_dict()))["kind"] == "supply_input"
    with pytest.raises(Exception):
        RepairAction(RepairKind.SUPPLY_INPUT, "x", "y", detail={"bad": object()})
    with pytest.raises(ClaimLayerError):
        RepairAction(RepairKind.SUPPLY_INPUT, "", "y")


def test_merging_unites_what_one_action_unblocks_and_never_combines_different_asks() -> None:
    a = RepairAction(RepairKind.SUPPLY_VALIDITY_EVIDENCE, "p", "why", required_for=("c1",))
    b = RepairAction(RepairKind.SUPPLY_VALIDITY_EVIDENCE, "p", "why", required_for=("c2",))
    c = RepairAction(RepairKind.SUPPLY_INPUT, "p", "why", required_for=("execution",))
    merged = merge_repairs([b, c, a])
    assert [(r.kind, r.target) for r in merged] == [(RepairKind.SUPPLY_INPUT, "p"), (RepairKind.SUPPLY_VALIDITY_EVIDENCE, "p")]
    assert merged[1].required_for == ("c1", "c2")
    assert merge_repairs([a, b, c]) == merged


@pytest.mark.parametrize(
    "capability_id, example",
    [("system.electrothermal", example_electrothermal_payload), ("system.battery", example_battery_payload)],
)
def test_a_case_restated_as_claim_inputs_builds_back_to_the_same_case(capability_id, example) -> None:
    declaration = production_registry().get(capability_id)
    case = example()
    rebuilt = build_case(declaration, inputs_from_case(declaration, case))
    assert inputs_from_case(declaration, rebuilt) == inputs_from_case(declaration, case)


def test_restating_a_case_refuses_a_field_the_capability_does_not_declare() -> None:
    declaration = production_registry().get("system.battery")
    case = example_battery_payload()
    case["cell"]["colour"] = "blue"
    with pytest.raises(CapabilityInputError, match="declares no input"):
        inputs_from_case(declaration, case)
