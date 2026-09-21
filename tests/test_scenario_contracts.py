import copy

import pytest

from engcore.scenarios import (
    InterpolationKind,
    NamedQuantity,
    QuantityOfInterest,
    ScenarioSegment,
    ScenarioSpecification,
    StateSnapshot,
    StateVariable,
    TimeSample,
    TimeSeriesInput,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity


def _scenario():
    input_series = TimeSeriesInput(
        "source.command",
        (
            TimeSample(Quantity(0, "s"), Quantity(0, "W")),
            TimeSample(Quantity(5, "s"), Quantity(10, "W")),
            TimeSample(Quantity(10, "s"), Quantity(20, "W")),
        ),
        InterpolationKind.LINEAR,
    )
    return ScenarioSpecification(
        "generic.transient",
        "1",
        Quantity(0, "s"),
        Quantity(10, "s"),
        state_variables=(StateVariable("body.energy", "J", "body"),),
        initial_state=StateSnapshot(
            Quantity(0, "s"),
            (NamedQuantity("body.energy", Quantity(0, "J")),),
        ),
        segments=(
            ScenarioSegment(
                "mission",
                Quantity(0, "s"),
                Quantity(10, "s"),
                inputs=(input_series,),
            ),
        ),
        quantities_of_interest=(
            QuantityOfInterest("delivered_energy", "body.energy", "J"),
        ),
    )


def test_scenario_round_trip_and_identity_are_deterministic():
    scenario = _scenario()

    restored = ScenarioSpecification.from_dict(scenario.to_dict())

    assert restored == scenario
    assert restored.digest == scenario.digest
    assert scenario.inputs_at(Quantity(2.5, "s"))["source.command"] == Quantity(5, "W")


def test_scenario_refuses_incomplete_initial_state_and_timeline_gaps():
    with pytest.raises(InvalidScientificProblem, match="every state variable"):
        ScenarioSpecification(
            "bad.state",
            "1",
            Quantity(0, "s"),
            Quantity(1, "s"),
            state_variables=(StateVariable("state.x", "m", "body"),),
            initial_state=StateSnapshot(Quantity(0, "s"), ()),
        )

    with pytest.raises(InvalidScientificProblem, match="contiguously"):
        ScenarioSpecification(
            "bad.timeline",
            "1",
            Quantity(0, "s"),
            Quantity(2, "s"),
            segments=(
                ScenarioSegment("late", Quantity(1, "s"), Quantity(2, "s")),
            ),
        )


def test_scenario_refuses_unit_drift_and_wire_shape_tampering():
    with pytest.raises(Exception):
        TimeSeriesInput(
            "input",
            (
                TimeSample(Quantity(0, "s"), Quantity(1, "W")),
                TimeSample(Quantity(1, "s"), Quantity(1, "K")),
            ),
            InterpolationKind.STEP,
        )

    payload = copy.deepcopy(_scenario().to_dict())
    payload["unexpected"] = True
    with pytest.raises(InvalidScientificProblem, match="shape mismatch"):
        ScenarioSpecification.from_dict(payload)
