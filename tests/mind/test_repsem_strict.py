"""Synthetic unit/implementation controls, not measured battery evidence."""
from dataclasses import replace

import numpy as np
import pytest

from engcore.mind.repsem.families import DeclaredFamily, FamilySlot, bind, bind_trajectory
from engcore.mind.repsem.roles import RoleTable, RoleDeclaration, RoleSource, VariableRole as R
from engcore.mind.repsem.v2 import FamilyContract, adapt
from engcore.scientific.errors import UnitCompatibilityError


def model(params, trajectory, constants):
    return params["r"] * trajectory.slots["driver"], {}


def other_model(params, trajectory, constants):
    return 2 * params["r"] * trajectory.slots["driver"], {}


def family(simulate=model):
    return DeclaredFamily("synthetic", "Ohmic test", (FamilySlot("driver", (R.CONTROLLED_INPUT,)),),
                          ("r",), simulate)


def roles(current="A", clock="s", output="V", parameter="ohm"):
    return RoleTable(tuple(RoleDeclaration(name, role, unit, RoleSource.PROBLEM_SPECIFICATION, "synthetic")
                           for name, role, unit in (("t", R.CONTROLLED_INPUT, clock), ("i", R.CONTROLLED_INPUT, current),
                                                    ("v", R.MEASUREMENT, output), ("r", R.LATENT_PARAMETER, parameter))))


def trajectory(table, values):
    f = family()
    return bind_trajectory(f, bind(f, table, "t"), table,
                           {"id": "synthetic", "unit_id": "development",
                            "columns": {"t": [0., 1.], "i": values, "v": [2., 2.]}})


def test_equivalent_current_units_preserve_predictions():
    a = adapter(roles()).simulate({"r": 2}, trajectory(roles(), [1, 1]), {})[0]
    b = adapter(roles(current="mA")).simulate({"r": 2}, trajectory(roles(current="mA"), [1000, 1000]), {})[0]
    np.testing.assert_array_equal(a, b)


def test_same_family_name_different_execution_has_different_identity():
    assert contract().to_dict() != contract(family(other_model)).to_dict()


def contract(f=None, **kwargs):
    return FamilyContract(f or family(), "test-2", "s", "V", {"driver": "A"}, {"r": "ohm"}, {}, {}, **kwargs)


def adapter(table, f=None):
    return adapt(contract(f), table, "t", constant_units={}, condition_units={})


def test_output_and_parameter_units_are_converted():
    table = roles(output="mV", parameter="milliohm")
    actual = adapter(table).simulate({"r": 2000}, trajectory(table, [1, 1]), {})[0]
    np.testing.assert_array_equal(actual, [2000, 2000])


@pytest.mark.parametrize("table", [roles(current="kg"), roles(clock="kg"), roles(output="kg"), roles(parameter="kg")])
def test_incompatible_units_are_rejected(table):
    with pytest.raises(UnitCompatibilityError):
        adapter(table)


def test_missing_parameter_unit_is_rejected():
    with pytest.raises(ValueError, match="every slot"):
        replace(contract(), parameter_units={})


def test_changed_artifact_invalidates_contract(tmp_path):
    artifact = tmp_path / "model-data.txt"
    artifact.write_text("first")
    sealed = contract(artifact_files=(str(artifact),))
    artifact.write_text("second")
    with pytest.raises(ValueError, match="changed"):
        sealed.to_dict()


def test_changed_function_invalidates_contract(monkeypatch):
    sealed = contract()
    monkeypatch.setattr(model, "__code__", other_model.__code__)
    with pytest.raises(ValueError, match="changed"):
        sealed.to_dict()


def clock_model(params, trajectory, constants):
    return params["r"] * trajectory.slots["driver"] * trajectory.clock, {}


def test_clock_units_convert_before_simulation():
    table = roles(clock="minute")
    actual = adapter(table, family(clock_model)).simulate({"r": 2}, trajectory(table, [1, 1]), {})[0]
    np.testing.assert_array_equal(actual, [0, 120])


def test_affine_units_are_rejected():
    with pytest.raises(ValueError, match="ratio-scale"):
        replace(contract(), measurement_unit="degC")


def problem():
    from engcore.mind.repsem.v2 import PROBLEM_SCHEMA
    return {"schema": PROBLEM_SCHEMA, "clock": "t", "observable": "v",
            "variables": [d.to_dict() for d in roles().declarations],
            "declared_family": {"family_id": "synthetic", "parameter_bounds": {"r": [1, 3]}, "constants": {}},
            "requested_parameters": ["r"],
            "measurement_noise": {"sigma": 0.1, "independent": True},
            "sets": {"calibration": [{"id": "dev", "unit_id": "dev",
                      "columns": {"t": list(range(20)), "i": [1.] * 20, "v": [2.] * 20}}]}}


def test_strict_assessment_replays_and_rejects_another_implementation():
    from engcore.mind.repsem.v2 import assess, replay, ReplayMismatch
    spec = problem()
    record = assess(spec, {"synthetic": contract()})
    assert replay(record, spec, {"synthetic": contract()})["status"] == "EXACT"
    with pytest.raises(ReplayMismatch):
        replay(record, spec, {"synthetic": contract(family(other_model))})


def test_unknown_noise_stays_unknown():
    from engcore.mind.repsem.v2 import assess
    spec = problem()
    spec.pop("measurement_noise")
    result = assess(spec, {"synthetic": contract()})
    assert all(p.standard_error is None for p in result.hypothesis.parameter_set)


GAIN = 1.0


def comprehension_model(params, trajectory, constants):
    return [GAIN * x for x in trajectory.slots["driver"]], {}


def module_model(params, trajectory, constants):
    return np.zeros_like(trajectory.clock), {}


def test_nested_code_global_dependency_is_sealed(monkeypatch):
    sealed = contract(family(comprehension_model))
    monkeypatch.setitem(comprehension_model.__globals__, "GAIN", 2.0)
    with pytest.raises(ValueError, match="changed"):
        sealed.to_dict()


def test_module_dependency_is_refused_until_explicitly_supported():
    with pytest.raises(ValueError, match="module dependencies"):
        contract(family(module_model))


def local_import_model(params, trajectory, constants):
    import math
    return trajectory.clock * math.pi, {}


def test_local_import_is_refused():
    with pytest.raises(ValueError, match="dynamic imports"):
        contract(family(local_import_model))


def test_adapter_rechecks_contract_before_execution_and_serialization(monkeypatch):
    adapted = adapter(roles(), family(comprehension_model))
    monkeypatch.setitem(comprehension_model.__globals__, "GAIN", 2.0)
    with pytest.raises(ValueError, match="changed"):
        adapted.simulate({"r": 2}, trajectory(roles(), [1, 1]), {})
    with pytest.raises(ValueError, match="changed"):
        adapted.to_dict()


def state_model(params, trajectory, constants):
    state = trajectory.clock * 0 + trajectory.initial_state["state"]
    return params["r"] * trajectory.slots["driver"] + constants["offset"] + trajectory.conditions["bias"], {"state": state}


def test_constants_conditions_and_state_use_declared_units():
    f = replace(family(state_model), slots=family().slots + (FamilySlot("state", (R.STATE_VARIABLE,), "driver"),), required_conditions=("bias",))
    table = RoleTable(roles().declarations + (RoleDeclaration("s", R.STATE_VARIABLE, "percent", RoleSource.PROBLEM_SPECIFICATION, "synthetic", driven_by=("i",)),))
    sealed = FamilyContract(f, "state-test", "s", "V", {"driver": "A", "state": "1"}, {"r": "ohm"}, {"bias": "V"}, {"offset": "V"})
    adapted = adapt(sealed, table, "t", constant_units={"offset": "mV"}, condition_units={"bias": "mV"})
    raw = {"id": "dev", "unit_id": "dev", "columns": {"t": [0., 1.], "i": [1., 1.], "s": [50., 50.], "v": [4., 4.]}, "initial_state": {"s": 50}, "conditions": {"bias": 1000}}
    bound = bind_trajectory(f, bind(f, table, "t"), table, raw)
    prediction, states = adapted.simulate({"r": 2}, bound, {"offset": 1000})
    np.testing.assert_array_equal(prediction, [4, 4])
    np.testing.assert_array_equal(states["state"], [50, 50])
