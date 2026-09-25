"""Proof A: real PyBaMM executions (discharge, charge/discharge cycle, temperature dependence) + Proof H (environment).

Integration and numerical execution only: no battery validation is claimed.
"""

from __future__ import annotations

import hashlib

import pytest

from engcore.providers import ProviderRefusal, ProviderRegistry, ProviderUnavailable
from engcore.scenarios import (
    ChannelRepresentation, EnvironmentChannel, EnvironmentKindRegistry, EnvironmentSource, EnvironmentTimeline, HistoryEntry,
    NamedQuantity, QuantityHistory, ReferenceContext, ScenarioSegment, ScenarioSpecification, TimeBasis, Timeline, TimePoint, TimeWindow,
)
from engcore.scientific.units.quantity import Quantity
from forge_pybamm import BatteryProblem, PyBaMMProvider, Segment, descriptor, parameter_set, segments_from_records

REG = ProviderRegistry()
descriptor.register(REG)
OK = REG.status("pybamm").available
pytestmark = pytest.mark.skipif(not OK, reason="PyBaMM unavailable")
p = lambda s: TimePoint("cell", Quantity(s, "s"))  # noqa: E731


def seg(a, b, amps, amb=298.15):
    return Segment(TimeWindow(p(a), p(b)), Quantity(amps, "A"), Quantity(amb, "K"))


def problem(segments, *, thermal="lumped", soc=0.9, fade=0.0, model="SPM"):
    return BatteryProblem(model, thermal, "Chen2020", soc, Quantity(298.15, "K"), fade, tuple(segments))


def test_proof_a_discharge_records_voltage_current_soc_temperature():
    rec = PyBaMMProvider(REG).run(problem([seg(0, 1800, 5.0)]))  # 1C for 30 min on the 5 Ah Chen2020 cell
    assert rec.succeeded, rec.reason
    soc, v, T = (rec.series_for(k) for k in ("soc", "voltage", "cell_temperature"))
    assert soc.values[0] == pytest.approx(0.9) and soc.values[-1] == pytest.approx(0.9 - 2.5 / 5.0, abs=1e-3)
    assert v.values[-1] < v.values[0] and T.values[-1] > T.values[0]  # discharging heats a lumped cell
    pset, _ = parameter_set("Chen2020")
    assert f"'digest': '{pset.digest}'" in rec.artifacts["configuration"] and "provider_bundled_literature" in rec.artifacts["configuration"]
    assert rec.uncertainty.kind.value == "unknown" and rec.metrics["solve_s"] < 60


def test_proof_a_charge_discharge_cycle_and_infeasible_request_fails_closed():
    cycle = PyBaMMProvider(REG).run(problem([seg(0, 3600, 2.0), seg(3600, 7200, -2.0)], soc=0.7))
    assert cycle.succeeded and cycle.series_for("soc").values[-1] == pytest.approx(0.7, abs=1e-6)  # balanced coulombs
    over = PyBaMMProvider(REG).run(problem([seg(0, 7200, 5.0)], soc=0.5))  # 10 Ah from a half-full 5 Ah cell
    assert not over.succeeded and "infeasible" in over.reason and not over.series


def test_proof_a_temperature_dependence_is_real_and_bound_to_identity():
    cold = PyBaMMProvider(REG).run(problem([seg(0, 1800, 5.0, 273.15)], thermal="isothermal"))
    warm = PyBaMMProvider(REG).run(problem([seg(0, 1800, 5.0, 318.15)], thermal="isothermal"))
    assert cold.succeeded and warm.succeeded and cold.identity.digest != warm.identity.digest
    assert cold.series_for("voltage").values[-1] < warm.series_for("voltage").values[-1] - 0.01  # Chen2020 Arrhenius kinetics/transport


def test_capacity_fade_mapping_changes_the_cell_and_the_identity():
    fresh = PyBaMMProvider(REG).run(problem([seg(0, 1800, 5.0)]))
    aged = PyBaMMProvider(REG).run(problem([seg(0, 1800, 5.0)], fade=0.2))
    assert aged.identity.digest != fresh.identity.digest
    assert aged.series_for("soc").values[-1] < fresh.series_for("soc").values[-1]  # same coulombs, smaller capacity
    with pytest.raises(ProviderRefusal):
        problem([seg(0, 10, 1.0), seg(20, 30, 1.0)])  # a gap is never "rest"
    with pytest.raises(ProviderRefusal, match="no parameter set"):
        PyBaMMProvider(REG).run(BatteryProblem("SPM", "lumped", "NotASet2099", 0.5, Quantity(298.15, "K"), 0.0, (seg(0, 10, 1.0),)))


def _environment():
    basis = TimeBasis("cell", "elapsed", "test start")
    scenario = ScenarioSpecification("cell-day", "1", Quantity(0, "s"), Quantity(7200, "s"),
                                     segments=(ScenarioSegment("s", Quantity(0, "s"), Quantity(7200, "s")),))
    air = QuantityHistory("air-h", "exposure", "air", "K", tuple(
        HistoryEntry(TimeWindow(p(3600 * i), p(3600 * (i + 1))), NamedQuantity("air", Quantity(v, "K"))) for i, v in enumerate((278.15, 308.15))))
    load = QuantityHistory("load", "usage", "cell_current", "A", tuple(
        HistoryEntry(TimeWindow(p(3600 * i), p(3600 * (i + 1))), NamedQuantity("cell_current", Quantity(v, "A"))) for i, v in enumerate((2.0, -2.0))))
    tl = Timeline.from_scenario(scenario, timeline_id="cell", basis=basis, histories=(air, load))
    ch = EnvironmentChannel("air", "ambient_temperature", "K", "declared", ReferenceContext("bench", "lab", "enu"), TimeWindow(p(0), p(7200)),
                            ChannelRepresentation.INTERVAL_HISTORY, history_id="air-h")
    return EnvironmentTimeline("cell-env", tl, EnvironmentKindRegistry.standard(),
                               (EnvironmentSource("declared", "design_assumption", "BIG 11 proof", hashlib.sha256(b"air").hexdigest(), "1"),), (ch,))


def test_proof_h_ambient_and_current_come_from_exact_big3_big2_records():
    env = _environment()
    segs = segments_from_records(env, "air", "load", TimeWindow(p(0), p(7200)), 3600)
    assert [s.ambient.magnitude for s in segs] == [278.15, 308.15] and dict(segs[0].provenance)["ambient_classification"] == "declared_assumption_not_evidence"
    rec = PyBaMMProvider(REG).run(problem(segs, soc=0.6))
    assert rec.succeeded
    warmer = tuple(Segment(s.window, s.current, Quantity(s.ambient.magnitude + 5, "K"), s.provenance) for s in segs)
    assert PyBaMMProvider(REG).run(problem(warmer, soc=0.6)).identity.digest != rec.identity.digest  # environment is identity
    T = rec.series_for("cell_temperature")
    # the cell relaxes toward the colder then the warmer ambient: the provider consumed the environment
    assert min(T.values) < 298.15 < max(T.values)
    other = segments_from_records(_environment(), "air", "load", TimeWindow(p(0), p(7200)), 3600)
    assert other == segs  # same records -> same segments (and provenance digests)
    with pytest.raises(ProviderRefusal, match="inside a 7200 s segment"):
        segments_from_records(env, "air", "load", TimeWindow(p(0), p(7200)), 7200)  # a start-sample would hide the 3600 s change


def test_a_sampled_ambient_channel_that_changes_inside_a_segment_is_refused():
    from engcore.scenarios.environment import EnvironmentInterpolation, EnvironmentSample, InterpolationContract

    env = _environment()
    samples = tuple(EnvironmentSample(p(t), NamedQuantity("probe", Quantity(v, "K"))) for t, v in ((0, 280.0), (1800, 300.0), (3600, 290.0)))
    for method, gap, times in ((EnvironmentInterpolation.LINEAR, Quantity(7200, "s"), samples),  # a ramp held as a constant
                               (EnvironmentInterpolation.STEP_HOLD, Quantity(7200, "s"), samples)):  # a step at 1800 s inside
        ch = EnvironmentChannel("probe", "ambient_temperature", "K", "declared", ReferenceContext("bench", "lab", "enu"),
                                TimeWindow(p(0), p(7200)), ChannelRepresentation.POINT_SAMPLES, times, InterpolationContract(method, gap))
        sampled = EnvironmentTimeline("cell-env-s", env.timeline, EnvironmentKindRegistry.standard(), env.sources, (ch,))
        with pytest.raises(ProviderRefusal, match="not piecewise constant"):
            segments_from_records(sampled, "probe", "load", TimeWindow(p(0), p(7200)), 3600)


def test_unavailable_pybamm_is_refused():
    reg = ProviderRegistry()
    reg.register_unavailable(descriptor.CAPABILITY, "simulated absence")
    with pytest.raises(ProviderUnavailable):
        PyBaMMProvider(reg)
