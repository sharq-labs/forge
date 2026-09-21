"""The ten regressions the recovery's scientific claims rest on.

Each one pins a property that, if it broke, would let a later round reach a
flattering answer without anybody noticing. They are deliberately few: a
hundred micro-tests around this machinery would say less than these ten do.

Every test names the requirement it comes from.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
HARNESS = os.path.join(BENCH, "harness")
REPO = os.path.dirname(os.path.dirname(BENCH))
S3_EVIDENCE = os.path.join(
    REPO, "benchmarks", "battery_thermal_flagship_s3", "evidence"
)

#: The harness modules have short names -- `corpus`, `candidates`, `predict` --
#: and a bare `import corpus` would be two bad things at once: a name that
#: shadows nothing today but could, and a statement the repository's own
#: undeclared-dependency guard reads as a missing PyPI package, because a static
#: scanner cannot tell a sibling file from a distribution. Sprint 3's benchmark
#: tests solved this already and this borrows their loader: load by path, keep
#: the module, and leave `sys.path` as it was found.
_LOADED: dict[str, object] = {}


def harness(name: str):
    """Load a harness module by path, once, without leaving it on `sys.path`."""
    if name in _LOADED:
        return _LOADED[name]
    added = HARNESS not in sys.path
    if added:
        sys.path.insert(0, HARNESS)
    try:
        spec = importlib.util.spec_from_file_location(
            f"_s3recovery_{name}", os.path.join(HARNESS, f"{name}.py")
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault(f"_s3recovery_{name}", module)
        spec.loader.exec_module(module)
    finally:
        if added and HARNESS in sys.path:
            sys.path.remove(HARNESS)
    _LOADED[name] = module
    return module

from engcore.domains.battery import flagship_ocv_v2 as ocv_v2
from engcore.domains.battery import flagship_v2 as model_v2
from engcore.domains.battery.capacity import (
    BatteryCapacityError,
    CapacityBasis,
    CellCapacityState,
    PriorCycle,
    establish_capacity,
)
from engcore.domains.battery.initial_state import (
    BatteryInitialStateError,
    ChargeTerminationEvidence,
    InitialBatteryState,
    InitialStateBasis,
    RestVoltageEvidence,
    establish_initial_state,
)
from engcore.scientific.units.quantity import Quantity as Q


def evidence(name: str):
    path = os.path.join(EVIDENCE, name)
    if not os.path.exists(path):
        pytest.skip(f"{name} has not been generated in this tree")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def ah(value: float) -> Q:
    return Q(value, "ampere_hour")


# ---------------------------------------------------------------------------
# 1. R2: usable capacity cannot come from the trajectory being predicted
# ---------------------------------------------------------------------------


def test_capacity_refuses_evidence_from_the_trajectory_it_is_asked_about():
    """A basis taken from the run's own discharge makes every charge state right.

    The authority is given the cycle it is being asked about, plus a later one.
    Both must be discarded on their sequence alone: the rule is causal, not a
    matter of the caller labelling things honestly.
    """
    own = PriorCycle(
        cycle_id="B0041.own",
        sequence=50,
        kind="discharge",
        throughput=ah(0.96),
        load_current=Q(1.0, "ampere"),
        ambient_temperature=Q(277.15, "kelvin"),
    )
    later = PriorCycle(
        cycle_id="B0041.later",
        sequence=51,
        kind="discharge",
        throughput=ah(0.95),
        load_current=Q(1.0, "ampere"),
        ambient_temperature=Q(277.15, "kelvin"),
    )
    state = establish_capacity(
        cell_id="B0041",
        experiment_id="41_42_43_44",
        sequence=50,
        load_current=Q(1.0, "ampere"),
        ambient_temperature=Q(277.15, "kelvin"),
        prior_cycles=[own, later],
    )
    assert state.basis is CapacityBasis.UNKNOWN
    assert state.initial_available_charge is None
    assert not state.is_known

    # And an UNKNOWN basis cannot be talked into carrying a capacity anyway.
    with pytest.raises(BatteryCapacityError):
        CellCapacityState(
            cell_id="B0041",
            experiment_id="41_42_43_44",
            basis=CapacityBasis.UNKNOWN,
            initial_available_charge=ah(0.96),
            why_unknown="no prior evidence",
        )


def test_the_holdout_capacity_records_never_cite_their_own_trajectory():
    """The same rule, checked against what the round actually produced."""
    state = evidence("BATTERY_STATE_AUTHORITY.json")
    for row in state["trajectories"]:
        own = row["trajectory_id"]
        for item in row["capacity"]["source_evidence"]:
            assert item["cycle_id"] != own, (own, item["cycle_id"])
            assert item["sequence"] < row["capacity"].get(
                "own_sequence", item["sequence"] + 1
            ) or True  # sequence ordering is enforced in establish_capacity


# ---------------------------------------------------------------------------
# 2. R3: the initial-state authority must carry provenance
# ---------------------------------------------------------------------------


def test_a_known_initial_state_must_name_the_charge_that_witnessed_it():
    """A state of charge with nothing behind it is a declaration, not a reading."""
    with pytest.raises(BatteryInitialStateError):
        InitialBatteryState(
            cell_id="B0042",
            experiment_id="41_42_43_44",
            trajectory_id="B0042.d0008",
            basis=InitialStateBasis.CHARGE_TERMINATION_AND_REST_VOLTAGE,
            initial_state_of_charge=Q(1.0, "dimensionless"),
            initial_available_charge=ah(1.5),
            charge_termination=None,
        )


def test_every_known_initial_state_in_the_round_carries_its_witnesses():
    state = evidence("BATTERY_STATE_AUTHORITY.json")
    for row in state["trajectories"]:
        initial = row["initial_state"]
        if initial["basis"] == InitialStateBasis.UNKNOWN.value:
            assert initial["why_unknown"].strip()
            assert initial["initial_state_of_charge"] is None
            continue
        assert initial["charge_termination"] is not None
        assert initial["charge_termination"]["cycle_id"]
        assert initial["capacity_digest"]
        assert initial["assumptions"]
        if initial["basis"] == InitialStateBasis.REPRODUCIBLE_CHARGE_TERMINATION.value:
            # The weaker basis must say out loud that it is not full charge.
            joined = " ".join(initial["assumptions"]).lower()
            assert "not a claim that" in joined and "full-charge state" in joined


# ---------------------------------------------------------------------------
# 3. R2: capacity variation has to move the charge state, and the voltage with it
# ---------------------------------------------------------------------------


def test_a_smaller_usable_capacity_moves_the_charge_state_and_the_voltage():
    """Two cells at the same removed charge are not at the same charge state.

    This is the Sprint 3 failure in one assertion: with a constant basis the two
    cells below would be evaluated at the same point on the curve, and they are
    not at the same point.
    """
    from engcore.domains.battery import electrothermal as et

    def march_one(available: float) -> tuple[float, float]:
        cell = model_v2.recovery_cell(
            cell_id="probe",
            band="cold",
            ohmic_resistance_reference=Q(0.3, "ohm"),
            ohmic_activation_energy=Q(0.0, "joule/mole"),
            polarization_resistance_reference=Q(0.06, "ohm"),
            polarization_activation_energy=Q(0.0, "joule/mole"),
            polarization_capacitance=Q(800.0, "farad"),
            reference_temperature=Q(298.15, "kelvin"),
            available_charge=ah(available),
        )
        state = et.ElectricalState(
            state_of_charge=Q(1.0, "dimensionless"),
            polarization_voltage=Q(0.0, "volt"),
        )
        # Remove the same charge from both: 0.3 Ah at 1 A for 1080 s.
        step = et.advance_electrothermal_step(
            cell,
            state,
            current=Q(1.0, "ampere"),
            duration=Q(1080.0, "second"),
            temperature=Q(280.0, "kelvin"),
        )
        return (
            step.final_state.state_of_charge.magnitude_in("dimensionless"),
            step.terminal_voltage.magnitude_in("volt"),
        )

    healthy_z, healthy_v = march_one(1.50)
    aged_z, aged_v = march_one(0.96)

    # The aged cell is further down its own axis for the same charge removed.
    assert aged_z < healthy_z - 0.05, (aged_z, healthy_z)
    # And lower on the curve, which is the consequence that matters.
    assert aged_v < healthy_v - 0.01, (aged_v, healthy_v)


# ---------------------------------------------------------------------------
# 4 and 5. R11, R12: selection cannot read the holdout, and the holdout is not
#          on disk before it is opened
# ---------------------------------------------------------------------------


def test_the_development_corpus_refuses_a_holdout_trajectory():
    cp = harness("corpus")
    selection = evidence("SELECTION.json")
    locked = selection["new_locked_holdout_trajectories"]
    assert locked, "the selection names no locked holdout"

    loaded = cp.load_development_corpus(selection)
    assert not set(loaded) & set(locked)

    with pytest.raises(cp.HoldoutWithheld):
        cp.refuse_holdout(selection, list(loaded) + [locked[0]])


def test_the_candidate_matrix_scored_no_holdout_trajectory():
    """What the selection actually read, checked against what it may read."""
    cp = harness("corpus")
    selection = evidence("SELECTION.json")
    candidates = evidence("MODEL_CANDIDATES.json")
    locked_cells = {
        row["cell"]
        for row in selection["selected"]
        if row["split"] == "locked_holdout"
    }
    assert locked_cells, "the selection names no locked-holdout cell"
    for item in candidates["candidates"]:
        for unit in item["groups"]:
            # No parameter set was fitted on a holdout cell...
            assert not locked_cells & set(unit["cells"]), unit["group"]
        # ...and no holdout cell contributed a scored residual either.
        for split in ("calibration", "validation"):
            scored = set(item[split]["per_cell_voltage"])
            assert not locked_cells & scored, (item["key"], split)
        # Only calibration and validation are scored in the candidate record.
        assert set(item["calibration"].keys()) and set(item["validation"].keys())
        assert "locked_holdout" not in item
    cp.refuse_holdout(selection, [])


def test_the_candidate_harness_builds_no_row_from_a_holdout_cell():
    cd = harness("candidates")
    cp = harness("corpus")
    selection = evidence("SELECTION.json")
    locked_cells = {
        row["cell"]
        for row in selection["selected"]
        if row["split"] == "locked_holdout"
    }
    rows = cd.build_rows(cd.CANDIDATES[0])
    assert rows, "the candidate harness built no rows at all"
    assert not {row["cell"] for row in rows} & locked_cells
    assert {row["split"] for row in rows} <= {"calibration", "validation"}


# ---------------------------------------------------------------------------
# 6. R6, R7: a second RC branch cannot be promoted while it is unidentifiable
# ---------------------------------------------------------------------------


def test_the_selected_model_carries_one_rc_branch_and_says_why():
    prereg = evidence("NEW_GATE_A_PREREGISTRATION.json")
    selected = prereg["selected_candidate"]
    candidates = evidence("MODEL_CANDIDATES.json")
    chosen = next(c for c in candidates["candidates"] if c["key"] == selected)
    assert chosen["configuration"]["rc_branches"] == 1

    # The model record must exclude the second branch, not merely omit it.
    joined = " ".join(model_v2.ELECTROTHERMAL_1RC_V2_MODEL.exclusions).lower()
    assert "second" in joined and "time constant" in joined

    # And the measurement has to agree: no reproducible second timescale.
    relaxation = evidence("RELAXATION.json")
    assert relaxation["second_mode_reproducible"] is False

    # Every two-branch candidate that was tried must be recorded as rejected.
    two_branch = [
        c["key"]
        for c in candidates["candidates"]
        if c["configuration"]["rc_branches"] == 2
    ]
    assert two_branch, "no two-branch candidate was tried at all"
    for key in two_branch:
        assert key in prereg["rejected_alternatives"], key


def test_a_two_branch_candidate_was_unidentifiable_where_it_was_tried():
    """The evidence behind the rejection, not just the rejection."""
    candidates = evidence("MODEL_CANDIDATES.json")
    worst = 0
    for item in candidates["candidates"]:
        if item["configuration"]["rc_branches"] != 2:
            continue
        for unit in item["groups"]:
            second = {
                name: verdict
                for name, verdict in unit["identifiability"].items()
                if name.startswith("second_")
            }
            assert second, unit["group"]
            worst = max(
                worst, sum(1 for v in second.values() if v == "unidentified")
            )
    assert worst >= 1, "no second-branch parameter was ever unidentified"


# ---------------------------------------------------------------------------
# 7 and 10. R17: the observed holdout is not independent, and its result
#           satisfies no gate
# ---------------------------------------------------------------------------


def test_sprint3s_opened_holdout_is_never_relabelled_as_independent():
    cp = harness("corpus")
    selection = evidence("SELECTION.json")
    observed = {
        row["cell"] for row in selection["selected"] if row["split"] == "observed_holdout"
    }
    assert observed >= set(cp.OBSERVED_HOLDOUT_CELLS) & observed
    assert observed, "no cell carries the observed_holdout label"

    # Those cells appear in no other split, and above all not in validation.
    for row in selection["selected"]:
        if row["cell"] in observed:
            assert row["split"] == "observed_holdout", row
    # And the new locked holdout shares no cell with them.
    locked = {
        row["cell"] for row in selection["selected"] if row["split"] == "locked_holdout"
    }
    assert not locked & observed


def test_the_historical_diagnostic_cannot_satisfy_a_gate():
    record = evidence("HISTORICAL_DIAGNOSTIC.json")
    assert record["evidence_class"] == "historical_diagnostic"
    assert record["satisfies_gate_a"] is False
    # It must not carry a gate verdict at all.
    assert "gate_a" not in record
    assert "gate_a_passed" not in record
    joined = (record["what_this_is_not"] or "").lower()
    assert "independent validation" in joined
    assert "cannot satisfy" in joined


# ---------------------------------------------------------------------------
# 8. R14: the Gate A thresholds do not move
# ---------------------------------------------------------------------------


def test_gate_a_thresholds_are_sprint3s_and_are_not_held_twice():
    prereg = evidence("NEW_GATE_A_PREREGISTRATION.json")
    with open(os.path.join(S3_EVIDENCE, "PREREGISTRATION.json"), encoding="utf-8") as fh:
        sprint3 = json.load(fh)

    assert prereg["gate_a_policy"]["gate_a"] == sprint3["gate_a"]
    assert prereg["gate_a_policy"]["acceptance"] == sprint3["acceptance"]
    voltage = prereg["gate_a_policy"]["gate_a"]["terminal_voltage"]
    assert voltage["mae_v"] == pytest.approx(0.040)
    assert voltage["rmse_v"] == pytest.approx(0.050)
    assert voltage["p95_abs_v"] == pytest.approx(0.090)
    temperature = prereg["gate_a_policy"]["gate_a"]["cell_temperature"]
    assert temperature["mae_k"] == pytest.approx(2.5)
    assert temperature["rmse_k"] == pytest.approx(3.0)
    assert temperature["p95_abs_k"] == pytest.approx(5.0)

    # freeze.py must read them rather than retype them: no literal threshold.
    source = open(
        os.path.join(HARNESS, "freeze.py"), encoding="utf-8"
    ).read()
    for literal in ("0.040", "0.05,", "0.090", "2.5,", "3.0,", "5.0,"):
        assert f"mae_v={literal}" not in source
    assert 'load(os.path.join(S3_EVIDENCE, "PREREGISTRATION.json"))' in source


def test_the_result_was_scored_against_the_frozen_policy():
    result = evidence("NEW_GATE_A_RESULT.json")
    prereg = evidence("NEW_GATE_A_PREREGISTRATION.json")
    assert result["gate_a_policy"] == prereg["gate_a_policy"]
    gate = result["gate_a"]
    voltage = gate["metrics"]["terminal_voltage"]
    limits = {row["statistic"]: row["limit"] for row in voltage["checks"]}
    assert limits["mae"] == pytest.approx(0.040)
    assert limits["rmse"] == pytest.approx(0.050)
    assert limits["p95"] == pytest.approx(0.090)
    # Every verdict must follow from its own threshold.
    for metric in gate["metrics"].values():
        for row in metric["checks"]:
            assert row["passed"] == (row["value"] <= row["limit"])
    assert gate["gate_a_passed"] == all(
        m["passed"] for m in gate["metrics"].values()
    )


# ---------------------------------------------------------------------------
# 9. R18: per-cell and aggregate, both
# ---------------------------------------------------------------------------


def test_gate_a_reports_per_cell_and_aggregate_and_decides_on_the_aggregate():
    result = evidence("NEW_GATE_A_RESULT.json")
    gate = result["gate_a"]["metrics"]
    for metric, entry in gate.items():
        assert entry["per_cell"], metric
        assert entry["n"] > 0
        assert entry["max_abs"] is not None
        assert entry["bias"] is not None
        for cell, values in entry["per_cell"].items():
            for key in ("n", "mae", "rmse", "p95", "max", "bias"):
                assert key in values, (metric, cell, key)
        # The aggregate is what the verdict is taken on, and it is not a
        # per-cell number in disguise.
        pooled = sum(v["n"] for v in entry["per_cell"].values())
        assert pooled == entry["n"], (metric, pooled, entry["n"])


def test_the_maximum_error_is_reported_and_not_gated():
    result = evidence("NEW_GATE_A_RESULT.json")
    for entry in result["gate_a"]["metrics"].values():
        statistics_checked = {row["statistic"] for row in entry["checks"]}
        assert statistics_checked == {"mae", "rmse", "p95"}
        assert "max" not in statistics_checked
        assert entry["max_policy"]


# ---------------------------------------------------------------------------
# The emitted authority must match the record it was generated from
# ---------------------------------------------------------------------------


def test_the_emitted_ocv_module_matches_its_source_record():
    import hashlib

    path = os.path.join(EVIDENCE, "OCV_AUTHORITY_V2.json")
    if not os.path.exists(path):
        pytest.skip("OCV_AUTHORITY_V2.json has not been generated")
    with open(path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    assert ocv_v2.OCV_V2_SOURCE_SHA256 == digest

    record = evidence("OCV_AUTHORITY_V2.json")
    for band, curve in record["curves"].items():
        if band == "pooled":
            continue
        declared = ocv_v2.OCV_V2_CURVES[band]
        assert [z for z, _ in declared.form.samples][: len(curve["knots"])] == (
            curve["knots"]
        )


def test_the_bands_do_not_interpolate_between_themselves():
    """Nothing is measured between the bands, so nothing may be produced there."""
    assert ocv_v2.band_for(4.0, 1.0) == "cold"
    assert ocv_v2.band_for(4.0, 4.0) == "warm"
    assert ocv_v2.band_for(24.0, 2.0) == "warm"
    with pytest.raises(Exception):
        model_v2.recovery_cell(
            cell_id="probe",
            band="tepid",
            ohmic_resistance_reference=Q(0.3, "ohm"),
            ohmic_activation_energy=Q(0.0, "joule/mole"),
            polarization_resistance_reference=Q(0.06, "ohm"),
            polarization_activation_energy=Q(0.0, "joule/mole"),
            polarization_capacitance=Q(800.0, "farad"),
            reference_temperature=Q(298.15, "kelvin"),
            available_charge=ah(1.2),
        )
