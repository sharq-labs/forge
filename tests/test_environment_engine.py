"""Environment Engine (BIG 3) focused adversarial tests and executable scenarios.

Roundtrip, digest and replay agreement here are reproducibility checks only.
Environmental values are imposed inputs, never evidence.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from engcore.scenarios import (
    ChannelRepresentation, EnvironmentChannel, EnvironmentInterpolation,
    EnvironmentKindRegistry, EnvironmentQuantityKind, EnvironmentSample,
    EnvironmentSource, EnvironmentSourceKind, EnvironmentState,
    EnvironmentTimeline, HistoryEntry, InterpolationContract, NamedQuantity,
    QuantityHistory, ReferenceContext, ScenarioSegment, ScenarioSpecification,
    TimeBasis, TimeBasisKind, Timeline, TimelineEvent, TimelineEventKind,
    TimePoint, TimeWindow, ValueDerivation, ValueStatus, WindowClosure,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity

B = "site-clock"
BASIS = TimeBasis(B, TimeBasisKind.ELAPSED, "exposure-start")
HOUR = 3600
DAY = 24 * HOUR


def D(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


def tp(hours):
    return TimePoint(B, Quantity(hours, "hour"))


def hwin(a, b, closure=WindowClosure.HALF_OPEN):
    return TimeWindow(tp(a), tp(b), closure)


def std(value, unit):
    return Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(value, unit), method="instrument spec")


def _scenario(hours=48):
    return ScenarioSpecification(
        "coastal-exposure", "1", Quantity(0, "hour"), Quantity(hours, "hour"),
        segments=(ScenarioSegment("all", Quantity(0, "hour"), Quantity(hours, "hour")),),
    )


SOURCES = (
    EnvironmentSource("met-station", EnvironmentSourceKind.MEASURED, "site-operator", D("met-2026-09"), "2026-09"),
    EnvironmentSource("chloride-candle", EnvironmentSourceKind.MEASURED, "site-operator", D("wet-candle-2026-09"), "1"),
    EnvironmentSource("std-atmos", EnvironmentSourceKind.STANDARD_PROFILE, "standard-body", D("atmos"), "1976"),
)

SITE = ReferenceContext("site", "coast-A", "local-enu")
PANEL = ReferenceContext(
    "panel-south-30", "coast-A", "local-enu",
    (NamedQuantity("surface_tilt", Quantity(30, "degree")), NamedQuantity("surface_azimuth", Quantity(180, "degree"))),
)


def _chloride_history():
    # declared daily deposition; day 2 is missing (candle lost)
    return QuantityHistory("chloride-days", "exposure", "chloride", "milligram / meter ** 2 / day", (
        HistoryEntry(hwin(0, 24), NamedQuantity("chloride", Quantity(120, "milligram / meter ** 2 / day"), std(15, "milligram / meter ** 2 / day"))),
    ))


def _channels():
    temps = (8, 7, 12, 19, 22, 18, 12, 9, 8)  # every 3 hours, 0..24
    temperature = EnvironmentChannel(
        "air-temp", "ambient_temperature", "degC", "met-station", SITE, hwin(0, 48, WindowClosure.CLOSED),
        ChannelRepresentation.POINT_SAMPLES,
        tuple(EnvironmentSample(tp(3 * i), NamedQuantity("air-temp", Quantity(t, "degC"), std(0.3, "K"))) for i, t in enumerate(temps)),
        InterpolationContract(EnvironmentInterpolation.LINEAR, Quantity(3, "hour")),
    )
    irradiance = EnvironmentChannel(
        "poa", "plane_irradiance", "W/m^2", "met-station", PANEL, hwin(0, 48, WindowClosure.CLOSED),
        ChannelRepresentation.POINT_SAMPLES,
        tuple(EnvironmentSample(tp(h), NamedQuantity("poa", Quantity(g, "W/m^2"))) for h, g in ((6, 0), (9, 450), (12, 820), (15, 500), (18, 0))),
        InterpolationContract(EnvironmentInterpolation.STEP_HOLD, Quantity(3, "hour")),
    )
    humidity = EnvironmentChannel(
        "rh", "relative_humidity", "dimensionless", "met-station", SITE, hwin(0, 48, WindowClosure.CLOSED),
        ChannelRepresentation.POINT_SAMPLES,
        (EnvironmentSample(tp(0), NamedQuantity("rh", Quantity(0.85, "dimensionless"))), EnvironmentSample(tp(12), NamedQuantity("rh", Quantity(0.55, "dimensionless")))),
        InterpolationContract(EnvironmentInterpolation.NONE),
    )
    chloride = EnvironmentChannel(
        "chloride", "chloride_deposition_rate", "milligram / meter ** 2 / day", "chloride-candle", SITE,
        hwin(0, 48), ChannelRepresentation.INTERVAL_HISTORY, history_id="chloride-days",
    )
    return (temperature, irradiance, humidity, chloride)


def _environment(events=(), channels=None, required=(("ambient_temperature", "coast-A"), ("wind_speed", "coast-A"))):
    timeline = Timeline.from_scenario(_scenario(), timeline_id="coast", basis=BASIS, histories=(_chloride_history(),), extra_events=events)
    return EnvironmentTimeline("coast-env", timeline, EnvironmentKindRegistry.standard(), SOURCES, channels or _channels(), required)


# ---- executable scenario 1: a coastal exposure site -------------------------


def test_coastal_site_state_over_a_day_is_deterministic_and_provenance_bound():
    env = _environment()
    states = env.history("coast-A", [tp(h) for h in (13.5, 0, 6, 12, 4.5)])
    assert [s.at for s in states] == [tp(h) for h in (0, 4.5, 6, 12, 13.5)]
    noon = states[3]
    assert noon.environment_digest == env.digest
    t = noon.value("ambient_temperature")
    assert t.derivation is ValueDerivation.SAMPLED and t.value.value == Quantity(22, "degC")
    assert t.value.uncertainty.kind is UncertaintyKind.STANDARD and t.source_id == "met-station"
    # between samples: interpolated, labelled, uncertainty UNKNOWN (not the sample sigma)
    mid = states[1].value("ambient_temperature")
    assert mid.derivation is ValueDerivation.INTERPOLATED
    assert mid.value.value.magnitude == pytest.approx(9.5)
    assert mid.value.uncertainty.kind is UncertaintyKind.UNKNOWN
    # humidity authorizes no interpolation
    assert states[1].value("relative_humidity").status is ValueStatus.UNKNOWN
    # required but unsupplied
    wind = noon.value("wind_speed")
    assert wind.status is ValueStatus.UNKNOWN and "no channel" in wind.reason
    # interval-declared chloride with its declared uncertainty
    cl = noon.value("chloride_deposition_rate")
    assert cl.derivation is ValueDerivation.INTERVAL_DECLARED and cl.value.uncertainty.kind is UncertaintyKind.STANDARD
    # the whole history replays byte-identically from serialization
    again = EnvironmentTimeline.from_dict(json.loads(json.dumps(env.to_dict())))
    assert again.digest == env.digest
    assert [s.digest for s in again.history("coast-A", [tp(h) for h in (0, 4.5, 6, 12, 13.5)])] == [s.digest for s in states]
    assert EnvironmentState.from_dict(noon.to_dict()) == noon


def test_missing_data_is_unknown_never_defaulted():
    env = _environment()
    # after the last temperature sample (24 h) there is nothing to interpolate to
    assert env.channel_value("air-temp", tp(30)).status is ValueStatus.UNKNOWN
    # before the first irradiance sample: no extrapolation
    assert env.channel_value("poa", tp(3)).status is ValueStatus.UNKNOWN
    # 18 h -> next sample never comes; hold is bounded by max_gap
    assert env.channel_value("poa", tp(20)).status is ValueStatus.UNKNOWN
    # chloride day 2 was lost
    assert env.channel_value("chloride", tp(30)).status is ValueStatus.UNKNOWN
    # sample declared without uncertainty keeps UNKNOWN uncertainty
    assert env.channel_value("poa", tp(12)).value.uncertainty.kind is UncertaintyKind.UNKNOWN


def test_max_gap_bounds_interpolation():
    temp = _channels()[0]
    sparse = EnvironmentChannel(
        "air-temp", "ambient_temperature", "degC", "met-station", SITE, hwin(0, 48, WindowClosure.CLOSED),
        ChannelRepresentation.POINT_SAMPLES, (temp.samples[0], temp.samples[4]),
        InterpolationContract(EnvironmentInterpolation.LINEAR, Quantity(3, "hour")),
    )
    env = _environment(channels=(sparse,))
    value = env.channel_value("air-temp", tp(6))
    assert value.status is ValueStatus.UNKNOWN and "max_gap" in value.reason


def test_declared_discontinuity_blocks_interpolation():
    front = TimelineEvent("front", TimelineEventKind.DISCONTINUITY, tp(4), "air-temp")
    env = _environment(events=(front,))
    assert env.channel_value("air-temp", tp(3)).status is ValueStatus.KNOWN  # declared sample
    assert env.channel_value("air-temp", tp(4.5)).status is ValueStatus.UNKNOWN  # after the front
    assert env.channel_value("air-temp", tp(3.5)).status is ValueStatus.UNKNOWN  # LINEAR would cross it
    assert env.channel_value("air-temp", tp(7)).status is ValueStatus.KNOWN  # bracket [6, 9) is clear


def test_chloride_dose_for_lifecycle_consumers():
    env = _environment()
    dose = env.dose("chloride", hwin(0, 24))
    assert dose.status is ValueStatus.KNOWN
    assert dose.value.value.to("milligram / meter ** 2").magnitude == pytest.approx(120)
    assert "UPPER BOUND" in dose.value.uncertainty.notes
    assert env.dose("chloride", hwin(0, 30)).status is ValueStatus.UNKNOWN  # lost day
    assert env.dose("air-temp", hwin(0, 3)).status is ValueStatus.UNKNOWN  # affine
    assert env.dose("poa", hwin(9, 12)).status is ValueStatus.UNKNOWN  # point samples: no declared dose


# ---- executable scenario 2: a climb through a standard atmosphere -----------


def test_climb_profile_with_body_force_and_pressure():
    scenario = ScenarioSpecification("climb", "1", Quantity(0, "s"), Quantity(600, "s"),
                                     segments=(ScenarioSegment("climb", Quantity(0, "s"), Quantity(600, "s")),))
    basis = TimeBasis("flight", TimeBasisKind.ELAPSED, "takeoff")
    p = lambda s: TimePoint("flight", Quantity(s, "s"))  # noqa: E731
    gravity = QuantityHistory("g", "exposure", "g0", "m/s^2", (
        HistoryEntry(TimeWindow(p(0), p(600)), NamedQuantity("g0", Quantity(9.80665, "m/s^2"))),
    ))
    timeline = Timeline.from_scenario(scenario, timeline_id="climb", basis=basis, histories=(gravity,))
    ctx = ReferenceContext("vehicle", "vehicle", "msl", (NamedQuantity("datum_offset", Quantity(0, "m")),))
    window = TimeWindow(p(0), p(600), WindowClosure.CLOSED)
    channels = (
        EnvironmentChannel("g0", "gravitational_acceleration", "m/s^2", "std-atmos", ctx, TimeWindow(p(0), p(600)),
                           ChannelRepresentation.INTERVAL_HISTORY, history_id="g"),
        EnvironmentChannel("alt", "altitude", "m", "std-atmos", ctx, window, ChannelRepresentation.POINT_SAMPLES,
                           tuple(EnvironmentSample(p(s), NamedQuantity("alt", Quantity(h, "m"))) for s, h in ((0, 0), (300, 1500), (600, 3000))),
                           InterpolationContract("linear", Quantity(5, "minute"))),
        EnvironmentChannel("p", "ambient_pressure", "kPa", "std-atmos", ctx, window, ChannelRepresentation.POINT_SAMPLES,
                           tuple(EnvironmentSample(p(s), NamedQuantity("p", Quantity(v, "kPa"))) for s, v in ((0, 101.325), (300, 84.56), (600, 70.12))),
                           InterpolationContract("linear", Quantity(300, "s"))),
    )
    env = EnvironmentTimeline("climb-env", timeline, EnvironmentKindRegistry.standard(), SOURCES, channels)
    state = env.state_at(p(150), "vehicle")
    assert state.value("altitude").value.value.magnitude == pytest.approx(750)
    assert state.value("ambient_pressure").derivation is ValueDerivation.INTERPOLATED
    assert state.value("gravitational_acceleration").value.value.magnitude == pytest.approx(9.80665)
    # 5 minute and 300 s authorize the same gap under the exact same-instant rule
    assert env.channel_value("alt", p(450)).status is ValueStatus.KNOWN


# ---- refusals ----------------------------------------------------------------


def test_environment_requires_a_scenario_bound_timeline():
    bare = Timeline("t", BASIS, hwin(0, 48, WindowClosure.CLOSED))
    with pytest.raises(InvalidScientificProblem, match="scenario-bound"):
        EnvironmentTimeline("e", bare, EnvironmentKindRegistry.standard(), SOURCES, ())


def test_missing_reference_context_is_refused():
    bare_panel = ReferenceContext("panel", "coast-A", "local-enu")
    c = _channels()[1]
    with pytest.raises(InvalidScientificProblem, match="surface_azimuth"):
        _environment(channels=(EnvironmentChannel("poa", c.kind_id, c.unit, c.source_id, bare_panel, c.validity, c.representation, c.samples, c.interpolation),))


def test_wrong_dimension_unregistered_kind_and_undeclared_source_refused():
    c = _channels()[2]
    with pytest.raises(InvalidScientificProblem, match="not a relative_humidity unit"):
        _environment(channels=(EnvironmentChannel("rh", "relative_humidity", "K", c.source_id, c.context, c.validity, c.representation,
                                                  tuple(EnvironmentSample(s.at, NamedQuantity("rh", Quantity(1, "K"))) for s in c.samples), c.interpolation),))
    with pytest.raises(InvalidScientificProblem, match="not registered"):
        _environment(channels=(EnvironmentChannel("rh", "fog_index", c.unit, c.source_id, c.context, c.validity, c.representation, c.samples, c.interpolation),))
    with pytest.raises(InvalidScientificProblem, match="undeclared source"):
        _environment(channels=(EnvironmentChannel("rh", c.kind_id, c.unit, "ghost", c.context, c.validity, c.representation, c.samples, c.interpolation),))


def test_overlapping_sources_for_one_quantity_are_not_arbitrated():
    c = _channels()[2]
    twin = EnvironmentChannel("rh2", c.kind_id, c.unit, c.source_id, c.context, c.validity, c.representation,
                              tuple(EnvironmentSample(s.at, NamedQuantity("rh2", s.value.value)) for s in c.samples), c.interpolation)
    with pytest.raises(InvalidScientificProblem, match="does not arbitrate"):
        _environment(channels=(c, twin))


def test_interpolation_contract_needs_explicit_gap():
    with pytest.raises(InvalidScientificProblem, match="max_gap"):
        InterpolationContract(EnvironmentInterpolation.LINEAR)
    with pytest.raises(InvalidScientificProblem, match="unsupported"):
        InterpolationContract("spline", Quantity(1, "hour"))
    with pytest.raises(InvalidScientificProblem, match="InterpolationContract"):
        EnvironmentChannel("x", "relative_humidity", "dimensionless", "met-station", SITE, hwin(0, 1), "point_samples",
                           (EnvironmentSample(tp(0), NamedQuantity("x", Quantity(0.5, "dimensionless"))),))


def test_channel_without_context_or_validity_is_refused():
    with pytest.raises(InvalidScientificProblem, match="ReferenceContext"):
        EnvironmentChannel("x", "relative_humidity", "dimensionless", "met-station", None, hwin(0, 1), "interval_history", history_id="h")
    with pytest.raises(InvalidScientificProblem, match="validity"):
        EnvironmentChannel("x", "relative_humidity", "dimensionless", "met-station", SITE, None, "interval_history", history_id="h")


def test_query_on_other_basis_or_outside_horizon_is_refused():
    env = _environment()
    with pytest.raises(InvalidScientificProblem, match="basis"):
        env.channel_value("air-temp", TimePoint("other", Quantity(1, "hour")))
    with pytest.raises(InvalidScientificProblem, match="horizon"):
        env.channel_value("air-temp", tp(49))


def test_provenance_survives_roundtrip_and_tampering_changes_identity():
    env = _environment()
    payload = env.to_dict()
    forged = json.loads(json.dumps(payload))
    forged["sources"][0]["classification"] = "evidence"
    with pytest.raises(InvalidScientificProblem, match="classification"):
        EnvironmentTimeline.from_dict(forged)
    swapped = EnvironmentTimeline("coast-env", env.timeline, env.registry,
                                  (EnvironmentSource("met-station", "measured", "site-operator", D("other-file"), "2026-09"),) + SOURCES[1:],
                                  env.channels, env.required)
    assert swapped.digest != env.digest
    assert swapped.state_at(tp(12), "coast-A").environment_digest != env.state_at(tp(12), "coast-A").environment_digest


def test_design_assumptions_are_labelled_not_evidence():
    s = EnvironmentSource("assumed", EnvironmentSourceKind.DESIGN_ASSUMPTION, "designer", D("x"), "1")
    assert s.to_dict()["classification"] == "declared_assumption_not_evidence"


def test_kinds_are_extensible_by_registration_not_branching():
    registry = EnvironmentKindRegistry.standard().register(
        EnvironmentQuantityKind("uv_dose_rate", "watt / meter ** 2", "UV irradiance")
    )
    assert registry.get("uv_dose_rate").dimension == registry.get("plane_irradiance").dimension
    with pytest.raises(InvalidScientificProblem, match="twice"):
        registry.register(EnvironmentQuantityKind("uv_dose_rate", "watt / meter ** 2", "dup"))


def test_unknown_value_cannot_be_forged_with_a_value():
    from engcore.scenarios import EnvironmentValue
    with pytest.raises(InvalidScientificProblem, match="carries no value"):
        EnvironmentValue("k", "l", "c", "ch", "s", "unknown", "interpolated", NamedQuantity("x", Quantity(1, "K")), "why", "imposed_environment_input")
    with pytest.raises(InvalidScientificProblem, match="say why"):
        EnvironmentValue("k", "l", "c", "ch", "s", "unknown", "none", None, "", "imposed_environment_input")


@pytest.mark.parametrize("method", ["linear", "step_hold"])
@pytest.mark.parametrize("event_hours,query,expected", [
    (6, 4.5, {"linear": ValueStatus.UNKNOWN, "step_hold": ValueStatus.KNOWN}),  # at upper sample
    (3, 4.5, {"linear": ValueStatus.KNOWN, "step_hold": ValueStatus.KNOWN}),    # at lower sample: new baseline
    (4.5, 4.5, {"linear": ValueStatus.UNKNOWN, "step_hold": ValueStatus.UNKNOWN}),  # at query
])
def test_discontinuity_at_boundaries(method, event_hours, query, expected):
    c = _channels()[0]
    channel = EnvironmentChannel(c.channel_id, c.kind_id, c.unit, c.source_id, c.context, c.validity, c.representation,
                                 c.samples, InterpolationContract(method, Quantity(3, "hour")))
    env = _environment(events=(TimelineEvent("jump", TimelineEventKind.DISCONTINUITY, tp(event_hours), "air-temp"),), channels=(channel,))
    assert env.channel_value("air-temp", tp(query)).status is expected[method]


def test_circular_kind_refuses_linear_interpolation():
    ctx = ReferenceContext("mast", "coast-A", "local-enu", (NamedQuantity("direction_reference", Quantity(0, "degree")),))
    channel = EnvironmentChannel("wd", "wind_direction", "degree", "met-station", ctx, hwin(0, 48, WindowClosure.CLOSED),
                                 "point_samples", (EnvironmentSample(tp(0), NamedQuantity("wd", Quantity(350, "degree"))),
                                                   EnvironmentSample(tp(1), NamedQuantity("wd", Quantity(10, "degree")))),
                                 InterpolationContract("linear", Quantity(1, "hour")))
    with pytest.raises(InvalidScientificProblem, match="circular"):
        _environment(channels=(channel,))


def test_values_carry_source_classification_and_states_verify():
    env = _environment()
    state = env.state_at(tp(12), "coast-A")
    assert state.value("ambient_temperature").source_classification == "imposed_environment_input"
    env.verify_state(EnvironmentState.from_dict(state.to_dict()))
    forged = json.loads(json.dumps(state.to_dict()))
    for v in forged["values"]:
        if v["kind_id"] == "ambient_temperature":
            v["value"]["value"]["magnitude"] = 99.0
    with pytest.raises(InvalidScientificProblem, match="not the one"):
        env.verify_state(EnvironmentState.from_dict(forged))
    with pytest.raises(InvalidScientificProblem, match="no source"):
        env.source("ghost")
