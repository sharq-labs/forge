"""Proof G (+H): PyBaMM operating days inside a BIG 10 long-horizon run.

new provider execution -> hourly aggregation -> BIG 4 throughput/temperature fade
-> changed SLOW state -> later PyBaMM executions start from the faded cell.
Declared scenario (not measured weather); no battery validation is claimed.
"""

from __future__ import annotations

import hashlib
import math
from fractions import Fraction

import pytest

from engcore.domains.battery.throughput_fade import ThroughputArrheniusFade
from engcore.execution.multiphysics import InitialStateValue
from engcore.multiscale import (
    AdaptationRule, AggregationSpec, FastExecutionRequest, FastStateAtMacroStart, LifecycleBinding, MacroStepPolicy, MultiTimescaleRuntime,
    RepresentativePolicy, ScaleHierarchy, ScaleLevel, StateChangeLimit, StateOwnership,
)
from engcore.providers import ProviderRegistry
from engcore.scenarios import (
    AggregateForm, ChannelRepresentation, EnvironmentChannel, EnvironmentKindRegistry, EnvironmentSource, EnvironmentTimeline, HistoryEntry,
    InputBinding, NamedQuantity, QuantityHistory, ReferenceContext, ScenarioSegment, ScenarioSpecification, TimeBasis, Timeline, TimePoint, TimeWindow,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

REG = ProviderRegistry()
try:
    from forge_pybamm import descriptor
    descriptor.register(REG)
    OK = REG.status("pybamm").available
except ImportError:
    OK = False
pytestmark = pytest.mark.skipif(not OK, reason="PyBaMM unavailable")
DAY, H = 86400, 3600
DAYS = 56
p = lambda s: TimePoint("site", Fraction(s))  # noqa: E731


def environment():
    ambient = [round(293.15 + 6.0 * math.sin(2 * math.pi * (h % 24 - 9) / 24) + 0.05 * (h // 24), 6) for h in range(DAYS * 24)]
    load = [1.0 if h % 24 in (8, 9) else (-1.0 if h % 24 in (14, 15) else 0.0) for h in range(DAYS * 24)]
    scenario = ScenarioSpecification("cell-duty", "1", Quantity(0, "s"), Quantity(DAYS * DAY, "s"),
                                     segments=(ScenarioSegment("duty", Quantity(0, "s"), Quantity(DAYS * DAY, "s")),))
    hist = lambda hid, kind, qid, unit, vals: QuantityHistory(hid, kind, qid, unit, tuple(  # noqa: E731
        HistoryEntry(TimeWindow(p(i * H), p((i + 1) * H)), NamedQuantity(qid, Quantity(v, unit))) for i, v in enumerate(vals)))
    tl = Timeline.from_scenario(scenario, timeline_id="cell", basis=TimeBasis("site", "elapsed", "install"),
                                histories=(hist("amb-h", "exposure", "ambient", "K", ambient), hist("load", "usage", "cell_current", "A", load)))
    ch = EnvironmentChannel("ambient", "ambient_temperature", "K", "site-profile", ReferenceContext("enclosure", "site", "enu"),
                            TimeWindow(p(0), p(DAYS * DAY)), ChannelRepresentation.INTERVAL_HISTORY, history_id="amb-h")
    src = EnvironmentSource("site-profile", "design_assumption", "BIG 11 declared diurnal enclosure profile",
                            hashlib.sha256(repr(ambient).encode()).hexdigest(), "1")
    return EnvironmentTimeline("cell-env", tl, EnvironmentKindRegistry.standard(), (src,), (ch,))


def build(env, *, default_days=7):
    from forge_pybamm.multiscale import BatteryFastSystem
    system = BatteryFastSystem(REG, env, ambient_channel="ambient", current_history="load", parameter_set_name="Chen2020",
                               model="SPM", segment_s=3600)
    hierarchy = ScaleHierarchy("cell-aging", "1", (ScaleLevel("electrochemistry", "fast", Quantity(60, "s"), "SPM + lumped thermal"),
                                                   ScaleLevel("duty_day", "operational", Quantity(1, "day"), "one charge/discharge duty day"),
                                                   ScaleLevel("aging", "slow", Quantity(30, "day"), "throughput capacity fade")),
                               (StateOwnership("cell", "soc", "fast", "dimensionless"), StateOwnership("cell", "capacity_fade", "slow", "dimensionless")))
    rep = RepresentativePolicy("duty-day", "leading_period", Quantity(1, "day"),
                               ("each represented day repeats the resolved day's current, temperature and voltage history",),
                               "while the duty cycle is 24 h periodic and the ambient drifts by less than the declared tolerance",
                               "throughput scales by the exact weight; mean temperature is weight-invariant",
                               periodicity_tolerances=(("ambient", Quantity(3, "K")), ("load", Quantity(0, "A"))),
                               fast_state_tolerances=(("cell.soc", Quantity(0.005, "dimensionless")),))
    policy = MacroStepPolicy("cell-macro", "1", (AdaptationRule("default", "default", Quantity(default_days, "day")),), Quantity(1, "day"),
                             "split", rep, (StateChangeLimit("cell", "capacity_fade", Quantity(0.1, "dimensionless"), 0.5),))
    model = ThroughputArrheniusFade(k_per_ampere_hour=Quantity(2e-4, "1/(A*h)"), activation_energy=Quantity(30, "kJ/mol"),
                                    reference_temperature=Quantity(298.15, "K"))
    lifecycle = (LifecycleBinding("cell", model, (InputBinding("charge_throughput", "throughput"), InputBinding("mean_cell_temperature", "cell_temp_mean"))),)
    aggs = (AggregationSpec("throughput", "abs_current", AggregateForm.INTEGRAL_DOSE),
            AggregationSpec("cell_temp_mean", "cell_temperature", AggregateForm.TIME_WEIGHTED_MEAN))
    rt = MultiTimescaleRuntime(run_id="pybamm-cell-ms", hierarchy=hierarchy, policy=policy, fast_system=system, environment=env,
                               aggregations=aggs, lifecycle=lifecycle, fast_state_policy=FastStateAtMacroStart.DECLARED_INITIAL)
    return rt, system


def states(fade=0.0):
    u = Uncertainty.unknown("declared")
    return ({"cell": {"capacity_fade": InitialStateValue("capacity_fade", Quantity(fade, "dimensionless"), u)}},
            {"cell": {"soc": InitialStateValue("soc", Quantity(0.8, "dimensionless"), u)}})


def test_proof_g_pybamm_days_drive_aging_that_changes_later_pybamm_executions():
    env = environment()
    rt, system = build(env)
    slow, fast = states()
    run = rt.run(initial_slow_state=slow, initial_fast_state=fast)
    assert run.status == "completed", run.reason
    acc = run.accounting
    assert Fraction(acc["represented_seconds"]) == DAYS * DAY and Fraction(acc["resolved_seconds"]) == 8 * DAY  # 8 weekly windows, 1 day each
    fades = [s.slow_after["cell"]["capacity_fade"].value.magnitude for s in run.steps]
    assert all(a < b for a, b in zip(fades, fades[1:])) and 0.02 < fades[-1] < 0.1
    # later PyBaMM executions really start from the faded cell: same first day, same records, only the slow state differs
    first = run.steps[0].executions[0].representative.resolved
    def request(slow_state):
        return FastExecutionRequest("cf", system.identity.digest, env.timeline.scenario_digest, env.timeline.digest, env.digest, first,
                                    slow_state, {"cell": dict(rt._declared_fast["cell"])},
                                    rt._environment_context(first), rt._usage_context(first))
    fresh = system.execute(request(run.steps[0].slow_before))
    aged = system.execute(request(run.final_slow_state))
    v_fresh = [s.value.magnitude for s in fresh.series_for("voltage").samples]
    v_aged = [s.value.magnitude for s in aged.series_for("voltage").samples]
    assert v_aged[9] < v_fresh[9] - 1e-3  # end of the discharge hours: the faded cell sits at a lower voltage
    assert run.ledger.entry("representative_window").status.value == "unknown"
    print("PROOF_G", {"accounting": acc, "fade": [round(f, 5) for f in fades], "v_end_discharge": (round(v_fresh[9], 4), round(v_aged[9], 4)),
                      "pybamm_executions": system.executions, "wall_s": round(run.wall_seconds, 1)})
