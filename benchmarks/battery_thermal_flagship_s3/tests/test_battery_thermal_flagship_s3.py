"""Sprint 3 battery + thermal flagship: the regressions worth having.

Each test pins something a later change could break silently. There is no test
here that re-asserts a Sprint 1 or Sprint 2 contract: those have their own, and
a second copy would go stale rather than protect anything.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "battery_thermal_flagship_s3"
HARNESS = ROUND / "harness"

#: The harness modules import each other by bare name, so the directory has to
#: be importable while they load. It is removed again straight afterwards: a
#: `sys.path` entry that outlives the load would put four short names into
#: every later import in the session.
_LOADED: dict[str, object] = {}


def harness(name: str):
    """Load a harness module by path, once, without leaving it on `sys.path`."""
    if name in _LOADED:
        return _LOADED[name]
    added = str(HARNESS) not in sys.path
    if added:
        sys.path.insert(0, str(HARNESS))
    try:
        spec = importlib.util.spec_from_file_location(name, HARNESS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault(name, module)
        spec.loader.exec_module(module)
    finally:
        if added and str(HARNESS) in sys.path:
            sys.path.remove(str(HARNESS))
    _LOADED[name] = module
    return module

from engcore.compositionpacks.builtin_battery_electrothermal import (  # noqa: E402
    AMBIENT_LOWER,
    AMBIENT_UPPER,
    BLUEPRINT,
    CAPABILITY_ID,
    CHARGE_CURRENT_FLOOR,
    REST_CURRENT_FLOOR,
)
from engcore.domains.battery import electrothermal as et  # noqa: E402
from engcore.domains.battery import measurement as ms  # noqa: E402
from engcore.domains.battery.flagship import (  # noqa: E402
    ELECTROTHERMAL_1RC_MODEL,
    flagship_cell,
)
from engcore.domains.battery.flagship_ocv import (  # noqa: E402
    CHARGE_STATE_BASIS_AH,
    FLAGSHIP_OCV_CURVE,
    OCV_KNOTS,
    OCV_LOWER,
    OCV_UPPER,
)
from engcore.scientific.corpus import (  # noqa: E402
    Applicability,
    CorpusLeakageError,
    DatasetSplit,
    HoldoutOpening,
    HoldoutRelease,
    InMemoryHoldoutLedger,
    ToleranceBasis,
    ToleranceSpec,
    ValidationCampaign,
)
from engcore.scientific.errors import InvalidScientificProblem  # noqa: E402
from engcore.scientific.models.definition import ValidityStatus  # noqa: E402
from engcore.scientific.units.quantity import Quantity as Q  # noqa: E402


def _json(name: str):
    return json.loads((ROUND / "evidence" / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def selection():
    return _json("DATA_SELECTION.json")


@pytest.fixture(scope="module")
def vendored():
    return _json("selected_trajectories.json")


# =====================================================================
# THE FROZEN EVIDENCE
# =====================================================================


def test_the_ocv_module_is_the_authority_record_and_nothing_else():
    """The production curve is generated from the evidence record.

    A hand edit to the table, or a re-derivation that was not regenerated into
    source, makes the model answer differently from the record its provenance
    points at. That is the one way this authority can drift silently.
    """
    record = _json("OCV_AUTHORITY.json")
    assert record["charge_state_basis_ah"] == CHARGE_STATE_BASIS_AH
    assert [z for z, _ in OCV_KNOTS] == record["knots"]
    assert [v for _, v in OCV_KNOTS] == record["values_v"]
    assert [OCV_LOWER, OCV_UPPER] == record["interval"]
    assert record["derived_from_split"] == "calibration"


def test_the_ocv_authority_refuses_outside_its_declared_interval():
    for outside in (OCV_LOWER - 1e-6, OCV_UPPER + 1e-6, 0.0):
        evaluated = FLAGSHIP_OCV_CURVE.evaluate(Q(outside, "dimensionless"))
        assert evaluated.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        assert evaluated.value is None


def test_the_ocv_authority_rises_with_charge():
    values = [v for _, v in OCV_KNOTS]
    assert all(b > a for a, b in zip(values, values[1:]))


def test_no_validation_or_holdout_cell_contributed_to_the_ocv_authority(selection):
    record = _json("OCV_AUTHORITY.json")
    independent = {
        item["cell"]
        for item in selection["selected"]
        if item["split"] != "calibration"
    }
    assert not independent & set(record["calibration_cells"])
    assert not {pair["cell"] for pair in record["pairs"]} & independent


def test_the_calibration_saw_only_calibration_trajectories(selection):
    calibration = _json("CALIBRATION.json")
    allowed = {
        item["trajectory_id"]
        for item in selection["selected"]
        if item["split"] == "calibration"
    }
    for group in calibration["groups"]:
        assert set(group["trajectories"]) <= allowed
    assert calibration["split"] == "calibration"


def test_a_group_with_no_independent_cell_makes_no_claim(selection):
    calibration = _json("CALIBRATION.json")
    claimless = set(selection["groups_without_independent_cells"])
    for group in calibration["groups"]:
        assert group["produces_a_claim"] == (group["group"] not in claimless)
        if not group["produces_a_claim"]:
            assert group["why_no_claim"]


# =====================================================================
# THE KERNEL, AND WHAT IT REFUSES
# =====================================================================


def _cell(**overrides):
    values = dict(
        cell_id="test",
        ohmic_resistance_reference=Q(0.11, "ohm"),
        ohmic_activation_energy=Q(5000.0, "joule/mole"),
        polarization_resistance_reference=Q(0.06, "ohm"),
        polarization_activation_energy=Q(8000.0, "joule/mole"),
        polarization_capacitance=Q(1500.0, "farad"),
        reference_temperature=Q(298.15, "kelvin"),
    )
    values.update(overrides)
    return flagship_cell(**values)


def test_a_step_that_would_leave_the_charge_interval_is_refused_not_clipped():
    cell = _cell()
    state = et.ElectricalState(Q(0.3, "dimensionless"), Q(0.0, "volt"))
    with pytest.raises(et.ChargeStateExhausted):
        et.advance_electrothermal_step(
            cell,
            state,
            current=Q(2.0, "ampere"),
            duration=Q(4000.0, "second"),
            temperature=Q(298.15, "kelvin"),
        )


def test_a_step_below_the_ocv_authority_is_refused_not_extrapolated():
    cell = _cell()
    state = et.ElectricalState(Q(OCV_LOWER + 0.001, "dimensionless"), Q(0.0, "volt"))
    with pytest.raises(et.OpenCircuitVoltageUnavailable):
        et.advance_electrothermal_step(
            cell,
            state,
            current=Q(2.0, "ampere"),
            duration=Q(60.0, "second"),
            temperature=Q(298.15, "kelvin"),
        )


def test_the_heat_is_the_interval_mean_and_not_its_endpoint():
    """The polarization branch is still charging, so the mean is below the end.

    A step reporting its endpoint power as the interval's dissipation would
    hand the thermal body more energy than the branch actually gave it.
    """
    cell = _cell()
    state = et.ElectricalState(Q(1.0, "dimensionless"), Q(0.0, "volt"))
    step = et.advance_electrothermal_step(
        cell,
        state,
        current=Q(2.0, "ampere"),
        duration=Q(20.0, "second"),
        temperature=Q(298.15, "kelvin"),
    )
    endpoint = 2.0 * (
        step.open_circuit_voltage.magnitude - step.terminal_voltage.magnitude
    )
    assert 0.0 < step.heat_generation.magnitude < endpoint
    assert step.mean_polarization_voltage.magnitude < (
        step.final_state.polarization_voltage.magnitude
    )


def test_a_hotter_cell_has_a_lower_resistance_under_a_positive_activation_energy():
    cell = _cell()
    cold = cell.ohmic_resistance.at(Q(288.15, "kelvin")).magnitude
    hot = cell.ohmic_resistance.at(Q(328.15, "kelvin")).magnitude
    assert hot < cold


def test_the_model_record_states_what_it_excludes():
    excluded = " ".join(ELECTROTHERMAL_1RC_MODEL.exclusions).lower()
    for phrase in ("entropic", "ageing", "hysteresis"):
        assert phrase in excluded


# =====================================================================
# THE ADAPTER DECIDES NO SCIENCE
# =====================================================================


def _sample(index, *, temperature=True):
    return ms.TrajectorySample(
        Q(index * 20.0, "second"),
        Q(-2.0, "ampere"),
        Q(4.0 - index * 0.01, "volt"),
        Q(298.0 + index * 0.1, "kelvin") if temperature else None,
    )


def _trajectory(**overrides):
    values = dict(
        trajectory_id="T1",
        cell_id="B0005",
        cycle_index=1,
        ambient_temperature=Q(297.15, "kelvin"),
        rated_capacity=Q(2.0, "ampere_hour"),
        samples=tuple(_sample(i) for i in range(10)),
        provenance=ms.FileProvenance("B0005.mat", "b" * 64, 123),
        source_sign=ms.CurrentSign.NEGATIVE_DISCHARGE,
    )
    values.update(overrides)
    return ms.MeasuredTrajectory(**values)


def test_the_adapter_refuses_a_trajectory_with_no_declared_split():
    from engcore.scientific.corpus import ReferenceSource, SourceSnapshot

    source = ReferenceSource(
        "s", "a", "battery", "1", "https://h.invalid/x", ("h.invalid",)
    )
    snapshot = SourceSnapshot(
        "s", "1", "a" * 64, "https://h.invalid/x.zip", 10, "2026-01-01T00:00:00+00:00"
    )
    policy = [
        ms.MetricPolicy(
            ms.TERMINAL_VOLTAGE_METRIC,
            ToleranceSpec(
                Q(0.05, "volt"), ToleranceBasis.REVIEWED_ACCEPTANCE, "declared"
            ),
        )
    ]
    with pytest.raises(Exception) as excinfo:
        ms.build_reference_dataset(
            dataset_id="d",
            version="1",
            source=source,
            snapshot=snapshot,
            trajectories=[_trajectory()],
            placements={},
            metrics=policy,
        )
    assert "split" in str(excinfo.value)


def test_a_channel_that_drops_out_partway_is_a_finding_not_a_gap():
    samples = tuple(_sample(i, temperature=i < 5) for i in range(10))
    with pytest.raises(Exception) as excinfo:
        _trajectory(samples=samples)
    assert "appears and disappears" in str(excinfo.value)


def test_the_source_sign_convention_is_applied_and_recorded():
    trajectory = _trajectory()
    assert trajectory.domain_current(1).magnitude == pytest.approx(2.0)
    assert trajectory.to_dict()["source_current_sign"] == "negative_discharge"


def test_no_state_of_charge_observation_is_ever_produced():
    """A coulomb counter compared against a coulomb counter tests nothing."""
    placement = ms.TrajectoryPlacement(
        "T1", DatasetSplit.CALIBRATION, "cell:B0005", Applicability.INSIDE
    )
    policies = [
        ms.MetricPolicy(
            metric,
            ToleranceSpec(
                Q(0.05, unit), ToleranceBasis.REVIEWED_ACCEPTANCE, "declared"
            ),
        )
        for metric, unit in (
            (ms.TERMINAL_VOLTAGE_METRIC, "volt"),
            (ms.CELL_TEMPERATURE_METRIC, "kelvin"),
        )
    ]
    _cases, observations = ms.trajectory_cases(
        _trajectory(), placement, metrics=policies
    )
    assert {item.metric for item in observations} == {
        ms.TERMINAL_VOLTAGE_METRIC,
        ms.CELL_TEMPERATURE_METRIC,
    }
    with pytest.raises(Exception):
        ms.trajectory_cases(
            _trajectory(),
            placement,
            metrics=[
                ms.MetricPolicy(
                    "state_of_charge",
                    ToleranceSpec(
                        Q(0.05, "dimensionless"),
                        ToleranceBasis.REVIEWED_ACCEPTANCE,
                        "declared",
                    ),
                )
            ],
        )


def test_the_first_sample_is_an_input_and_is_never_scored():
    placement = ms.TrajectoryPlacement(
        "T1", DatasetSplit.CALIBRATION, "cell:B0005", Applicability.INSIDE
    )
    policy = [
        ms.MetricPolicy(
            ms.TERMINAL_VOLTAGE_METRIC,
            ToleranceSpec(
                Q(0.05, "volt"), ToleranceBasis.REVIEWED_ACCEPTANCE, "declared"
            ),
        )
    ]
    cases, _ = ms.trajectory_cases(_trajectory(), placement, metrics=policy)
    assert ms.case_id_for("T1", 0) not in {case.case_id for case in cases}


# =====================================================================
# SPLIT GOVERNANCE
# =====================================================================


def test_no_cell_appears_in_two_splits(selection):
    by_cell: dict[str, set[str]] = {}
    for item in selection["selected"]:
        by_cell.setdefault(item["cell"], set()).add(item["split"])
    straddling = {k: sorted(v) for k, v in by_cell.items() if len(v) > 1}
    assert not straddling


def test_the_corpus_refuses_a_group_that_straddles_the_calibration_boundary():
    """The structural half of independence, enforced where the dataset is built."""
    from engcore.scientific.corpus import (
        ReferenceCase,
        ReferenceDataset,
        ReferenceObservation,
        ReferenceSource,
        SourceSnapshot,
    )

    source = ReferenceSource(
        "s", "a", "battery", "1", "https://h.invalid/x", ("h.invalid",)
    )
    snapshot = SourceSnapshot(
        "s", "1", "a" * 64, "https://h.invalid/x.zip", 10, "2026-01-01T00:00:00+00:00"
    )
    cases = (
        ReferenceCase("c1", DatasetSplit.CALIBRATION, "cell:B0005"),
        ReferenceCase("c2", DatasetSplit.VALIDATION, "cell:B0005"),
    )
    observations = tuple(
        ReferenceObservation(case.case_id, "terminal_voltage", Q(3.7, "volt"))
        for case in cases
    )
    with pytest.raises(CorpusLeakageError):
        ReferenceDataset("d", "1", source, snapshot, cases, observations)


def test_the_holdout_needs_a_recorded_opening_and_not_merely_a_release(selection):
    """Permission is not proof, and the campaign path is where that is enforced."""
    cmp = harness("campaign")

    _sel, vendored_data, calibration, inventory = cmp.load_inputs()
    dataset = cmp.build_dataset(selection, vendored_data, inventory)
    release = cmp.holdout_release(dataset)

    with pytest.raises(Exception):
        dataset.opened_holdout_cases(release)  # a release is not an opening

    prereg = harness("prereg")

    # A release is bound to one evaluation, so a campaign that is not the one it
    # names cannot use it -- checked here rather than assumed.
    with pytest.raises(CorpusLeakageError):
        ValidationCampaign(
            campaign_id="some.other.campaign",
            version="1",
            dataset=dataset,
            splits=(DatasetSplit.LOCKED_HOLDOUT,),
            holdout_release=release,
        )

    ledger = InMemoryHoldoutLedger(clock=lambda: "2026-09-21T00:00:00+00:00")
    campaign = ValidationCampaign(
        campaign_id=prereg.CAMPAIGN_ID,
        version=prereg.CAMPAIGN_VERSION,
        dataset=dataset,
        splits=(DatasetSplit.LOCKED_HOLDOUT,),
        holdout_release=release,
    )
    opened = campaign.open_holdout(ledger)
    assert isinstance(ledger.openings[0], HoldoutOpening)
    assert any(
        case.split is DatasetSplit.LOCKED_HOLDOUT for case in opened.cases()
    )


def test_a_release_for_a_changed_corpus_does_not_carry_over(selection):
    cmp = harness("campaign")

    _sel, vendored_data, calibration, inventory = cmp.load_inputs()
    dataset = cmp.build_dataset(selection, vendored_data, inventory)
    stale = HoldoutRelease(
        "e", "c", "1", "f" * 64, "2026-01-01T00:00:00+00:00", "stale"
    )
    with pytest.raises(CorpusLeakageError):
        dataset.require_release(stale)


def test_a_campaign_that_does_not_name_the_holdout_cannot_reach_it(selection):
    cmp = harness("campaign")

    _sel, vendored_data, calibration, inventory = cmp.load_inputs()
    dataset = cmp.build_dataset(selection, vendored_data, inventory)
    campaign = ValidationCampaign(
        campaign_id="t",
        version="1",
        dataset=dataset,
        splits=(DatasetSplit.CALIBRATION, DatasetSplit.VALIDATION),
    )
    assert all(
        case.split is not DatasetSplit.LOCKED_HOLDOUT for case in campaign.cases()
    )


# =====================================================================
# THE COMPOSITION'S DECLARED ENVELOPE
# =====================================================================


def test_the_composition_declares_its_ambient_band_and_its_rest_band():
    assert AMBIENT_LOWER.magnitude_in("kelvin") == pytest.approx(293.15)
    assert AMBIENT_UPPER.magnitude_in("kelvin") == pytest.approx(303.15)
    # The rest band is a magnitude and the charge floor its negative, so a
    # schedule and a predicate cannot disagree about where rest ends.
    assert CHARGE_CURRENT_FLOOR.magnitude_in("ampere") == pytest.approx(
        -REST_CURRENT_FLOOR.magnitude_in("ampere")
    )


def test_the_coupling_is_a_cycle_and_not_a_one_way_march():
    """Both edges exist, so the temperature drives the resistances back."""
    edges = {(e.source.key, e.target.key) for e in BLUEPRINT.edges}
    assert ("thermal.temperature", "cell.cell_temperature") in edges
    assert ("cell.heat_generation", "thermal.heat_input") in edges


def test_the_quantity_ports_the_campaign_names_exist_on_the_blueprint():
    """The campaign says which output answers which observable; this pins it."""
    sim = harness("simulate")

    ports = {
        (participant.participant_id, port.port_id)
        for participant in BLUEPRINT.participants
        for port in participant.ports
        if port.direction.value == "output"
    }
    for _quantity, participant, port in sim.QUANTITY_PORTS:
        assert (participant, port) in ports


# =====================================================================
# THE FAST MARCH IS THE AUTHORIZED PATH
# =====================================================================


@pytest.mark.expensive
def test_the_calibration_march_reproduces_an_authorized_run(selection, vendored):
    """Calibration is fitted on a march that must be the same physics.

    If these diverge, the parameters were fitted to something the flagship does
    not execute, and every number downstream is about a different model.
    """
    mm = harness("march")
    sim = harness("simulate")

    trajectory_id = "B0005.d0001"
    item = next(
        x for x in selection["selected"] if x["trajectory_id"] == trajectory_id
    )
    raw = next(
        x for x in vendored["trajectories"] if x["trajectory_id"] == trajectory_id
    )
    channels = raw["channels"]
    currents = [-x for x in channels["current_a"]]
    parameters = [0.09, 20000.0, 0.05, 25000.0, 2000.0, 45.0, 0.25]

    _instants, voltage, temperature, charge, _stop = mm.march(
        times_s=channels["time_s"],
        currents_a=currents,
        ambient_k=item["ambient_temperature_c"] + 273.15,
        initial_temperature_k=channels["temperature_c"][0] + 273.15,
        r0_ref=parameters[0],
        ea0=parameters[1],
        r1_ref=parameters[2],
        ea1=parameters[3],
        c1=parameters[4],
        c_th=parameters[5],
        ha=parameters[6],
    )
    authorized = sim.run_trajectory(
        parameters=sim.parameter_quantities(parameters),
        times_s=channels["time_s"],
        currents_a=currents,
        ambient_k=item["ambient_temperature_c"] + 273.15,
        initial_temperature_k=channels["temperature_c"][0] + 273.15,
        run_id="flagship-march-equivalence",
        scenario_id="flagship-march-equivalence",
    )
    rows = sim.trajectory_from_run(authorized)
    count = min(len(rows), len(voltage))
    assert count > 100
    for index in range(count):
        assert rows[index]["terminal_voltage"] == pytest.approx(
            voltage[index], abs=1e-12
        )
        assert rows[index]["cell_temperature"] == pytest.approx(
            temperature[index], abs=1e-12
        )
        assert rows[index]["state_of_charge"] == pytest.approx(
            charge[index], abs=1e-12
        )


@pytest.mark.expensive
def test_the_composition_refuses_a_trajectory_outside_its_declared_ambient(
    selection, vendored
):
    """The guardrail is the pack's, and it fires before any state advances."""
    sim = harness("simulate")

    trajectory_id = next(
        item["trajectory_id"]
        for item in selection["selected"]
        if item["applicability"] == "outside"
    )
    item = next(
        x for x in selection["selected"] if x["trajectory_id"] == trajectory_id
    )
    raw = next(
        x for x in vendored["trajectories"] if x["trajectory_id"] == trajectory_id
    )
    channels = raw["channels"]
    with pytest.raises(InvalidScientificProblem) as excinfo:
        sim.run_trajectory(
            parameters=sim.parameter_quantities(
                [0.11, 5000.0, 0.06, 8000.0, 1500.0, 60.0, 0.05]
            ),
            times_s=channels["time_s"],
            currents_a=[-x for x in channels["current_a"]],
            ambient_k=item["ambient_temperature_c"] + 273.15,
            initial_temperature_k=channels["temperature_c"][0] + 273.15,
            run_id="flagship-guardrail",
            scenario_id="flagship-guardrail",
        )
    message = str(excinfo.value)
    assert "applicability" in message
    assert "battery_electrothermal." in message


# =====================================================================
# THE RECORDED RESULT
# =====================================================================


def test_gate_a_is_scored_against_thresholds_that_never_moved():
    prereg = harness("prereg")

    gate = _json("GATE_A.json")
    assert gate["campaign_id"] == prereg.CAMPAIGN_ID
    for metric, expected in (
        ("terminal_voltage", prereg.GATE_A["terminal_voltage"]),
        ("cell_temperature", prereg.GATE_A["cell_temperature"]),
    ):
        limits = {row["statistic"]: row["limit"] for row in gate["metrics"][metric]["checks"]}
        assert limits["mae"] == expected[
            "mae_v" if metric == "terminal_voltage" else "mae_k"
        ]
        assert limits["rmse"] == expected[
            "rmse_v" if metric == "terminal_voltage" else "rmse_k"
        ]
        assert limits["p95"] == expected[
            "p95_abs_v" if metric == "terminal_voltage" else "p95_abs_k"
        ]


def test_the_holdout_result_is_reported_as_it_came_out():
    """The recorded verdict is what the numbers say, in both directions."""
    gate = _json("GATE_A.json")
    voltage = gate["metrics"]["terminal_voltage"]
    temperature = gate["metrics"]["cell_temperature"]
    assert not voltage["passed"]
    assert temperature["passed"]
    assert not gate["gate_a_passed"]
    failing = {row["statistic"] for row in voltage["checks"] if not row["passed"]}
    assert failing == {"rmse", "p95"}


def test_the_flagship_run_replayed_and_certified():
    flagship = _json("FLAGSHIP.json")
    assert flagship["replay"]["status"] == "replayed_match"
    assert flagship["replay"]["verified"] is True
    assert flagship["certification"]["verified"] is True
    assert flagship["trust"]["production_policy"]["satisfied"] is True
    assert set(flagship["numerical"]["satisfied_checks"]) == {
        "convergence",
        "refinement",
        "conservation",
    }


def test_the_flagship_evidence_was_produced_on_a_validation_cell():
    """Building the evidence on a locked case would have opened the holdout."""
    flagship = _json("FLAGSHIP.json")
    assert flagship["trajectory"]["split"] == "validation"


def test_state_of_charge_is_not_claimed_as_validated():
    campaign_record = _json("CAMPAIGN_HOLDOUT.json")
    assert "NOT INDEPENDENTLY VALIDATED" in campaign_record["state_of_charge"]
    for metric in campaign_record["metrics"]:
        assert metric in ("terminal_voltage", "cell_temperature")


def test_every_refusal_in_the_campaign_was_a_correct_one():
    campaign_record = _json("CAMPAIGN_HOLDOUT.json")
    assert campaign_record["counts"]["unexpected_refusal"] == 0
    assert campaign_record["refusal_accuracy"] == 1.0
