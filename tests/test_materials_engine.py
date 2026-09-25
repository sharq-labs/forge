"""Scientific Data + Materials (BIG 5): identity, resolution, provenance, lifecycle coupling.

All numeric data below are ILLUSTRATIVE TEST FIXTURES, sourced as such (issuer
and locator say so, and the source digest is the digest of the fixture bytes).
They are not reference data.  Replay/roundtrip agreement is reproducibility only.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.domains.hygrothermal.moisture_uptake import INSULATION_STATE_SCHEMA, LinearWetnessMoistureUptake
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, InitialStateDefinition, InitialStateReceipt, InitialStateValue,
    InitializationResult, MultiphysicsRuntime,
)
from engcore.materials import (
    ApplicabilityRange, CompositionEntry, InterpolationRule, MaterialIdentity, MaterialPropertySet,
    MaterialState, MaterialStateSchema, PropertyApplicability, PropertyDatum, PropertyDerivation,
    TransformationRecord, source_identity,
)
from engcore.scenarios import (
    ChannelRepresentation, EnvironmentChannel, EnvironmentKindRegistry, EnvironmentSource,
    EnvironmentTimeline, HistoryEntry, InputBinding, NamedQuantity, QuantityHistory, ReferenceContext,
    ScenarioSegment, ScenarioSpecification, StepStatus, TimeBasis, Timeline, TimePoint, TimeWindow,
    run_lifecycle,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.knowledge.claim import KnowledgeClaim, KnowledgeKind
from engcore.scientific.knowledge.ingestion import KnowledgeIngestionReceipt, verify_ingestion_receipt
from engcore.scientific.knowledge.snapshot import KnowledgeSnapshot
from engcore.scientific.knowledge.source import KnowledgeSource, KnowledgeSourceClass
from engcore.scientific.multiphysics import (
    CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph, PortDefinition,
    PortDirection, PortKind, TimePolicy,
)
from engcore.scientific.multiphysics.receipts import StateVariableValue
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity

K = "K"


def D(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


def std(v, unit):
    return Uncertainty(kind="standard", standard_uncertainty=Quantity(v, unit), method="fixture")


# ---- fixture dataset builder --------------------------------------------------


def _dataset(material, rows, *, source_id, locator, set_id, rules=()):
    """rows: (claim_id, property_id, value Quantity, uncertainty|None, ranges, phase, origin, transformation)"""
    payload = json.dumps([[r[0], r[1], r[2].to_dict(), None if r[3] is None else r[3].to_dict()] for r in rows], sort_keys=True).encode()
    source = KnowledgeSource(source_id, "forge test fixture (illustrative values, not reference data)",
                             hashlib.sha256(payload).hexdigest(), "1", locator, KnowledgeSourceClass.OTHER)
    data, claims = [], []
    for claim_id, pid, value, uq, ranges, phase, origin, transformation in rows:
        app = PropertyApplicability(material.digest, pid, ranges, phase)
        claim = KnowledgeClaim(claim_id, KnowledgeKind.MATERIAL_PROPERTY, material.subject_key, pid, value, "", uq,
                               source.source_id, source.document_digest, app.digest)
        claims.append(claim)
        data.append((claim, app, origin, transformation))
    snapshot = KnowledgeSnapshot(f"{set_id}-snapshot", (source,), tuple(claims))
    receipt = KnowledgeIngestionReceipt.from_payload(source, payload, "forge.fixture_parser", "1", tuple(c.digest for c in claims))
    verify_ingestion_receipt(snapshot, receipt)
    resolved_data = []
    for claim, app, origin, transformation in data:
        if callable(transformation):
            transformation = transformation(claims)
        resolved_data.append(PropertyDatum(claim, app, origin, transformation))
    return MaterialPropertySet(set_id, material, snapshot, tuple(resolved_data), tuple(rules)), receipt


def T(v):
    return Quantity(v, K)


def point(var, q):
    return ApplicabilityRange(var, q, q)


# ---- example 1: temperature-dependent thermal properties ---------------------

ALLOY = MaterialIdentity("aluminium_alloy", specification="FIXTURE-SPEC-A", grade="X1", condition="annealed",
                         composition=(CompositionEntry("Al", NamedQuantity("Al", Quantity(0.97, "dimensionless"))),))
K_UNIT = "W/(m*K)"


def _alloy_set(extra_rows=(), breakpoints=()):
    rows = [
        (f"k{t}", "thermal_conductivity", Quantity(v, K_UNIT), std(4, K_UNIT), (point("temperature", T(t)),), "solid", "compiled", None)
        for t, v in ((300, 200.0), (400, 210.0), (500, 220.0), (600, 225.0))
    ] + [
        ("rho-room", "density", Quantity(2700, "kg/m^3"), None, (ApplicabilityRange("temperature", T(283.15), T(303.15)),), "solid", "measured", None),
    ] + list(extra_rows)
    return _dataset(ALLOY, rows, source_id="fixture-alloy", locator="tests/test_materials_engine.py::_alloy_set",
                    set_id="alloy-props", rules=(InterpolationRule("thermal_conductivity", "temperature", "linear", tuple(breakpoints)),))


def _alloy_state(t=None, phase="solid"):
    conditions = () if t is None else (NamedQuantity("temperature", T(t)),)
    return MaterialState(ALLOY, conditions, phase)


def test_thermal_conductivity_resolves_sourced_interpolated_and_refused():
    props, _ = _alloy_set()
    sourced = props.resolve("thermal_conductivity", _alloy_state(400))
    assert sourced.derivation is PropertyDerivation.SOURCED and sourced.value.value.magnitude == 210
    assert sourced.value.uncertainty.kind is UncertaintyKind.STANDARD
    mid = props.resolve("thermal_conductivity", _alloy_state(450))
    assert mid.derivation is PropertyDerivation.INTERPOLATED and mid.value.value.magnitude == pytest.approx(215)
    assert mid.value.uncertainty.kind is UncertaintyKind.UNKNOWN  # not the tabulated sigma
    assert len(mid.claim_digests) == 2 and mid.rule is not None
    for t, why in ((250, "extrapolation"), (650, "extrapolation")):
        assert props.resolve("thermal_conductivity", _alloy_state(t)).status == "unknown"
    missing = props.resolve("thermal_conductivity", _alloy_state(None))
    assert missing.status == "unknown" and "does not declare 'temperature'" in missing.reason


def test_room_temperature_property_is_not_used_at_500_c_equivalent():
    props, _ = _alloy_set()
    assert props.resolve("density", _alloy_state(293.15)).value.value.magnitude == 2700
    hot = props.resolve("density", _alloy_state(773.15))
    assert hot.status == "unknown" and "outside" in hot.reason and "no interpolation" in hot.reason
    # a density claim with no stated uncertainty stays UNKNOWN, never zero
    assert props.resolve("density", _alloy_state(293.15)).value.uncertainty.kind is UncertaintyKind.UNKNOWN


def test_phase_breakpoint_blocks_interpolation_and_phase_must_match():
    props, _ = _alloy_set(breakpoints=(T(550),))
    assert props.resolve("thermal_conductivity", _alloy_state(450)).status == "known"
    blocked = props.resolve("thermal_conductivity", _alloy_state(560))
    assert blocked.status == "unknown" and "breakpoint" in blocked.reason
    liquid = props.resolve("thermal_conductivity", _alloy_state(400, phase="liquid"))
    assert liquid.status == "unknown"


def test_two_admissible_sources_are_not_arbitrated():
    extra = (("k400b", "thermal_conductivity", Quantity(212.0, K_UNIT), None, (point("temperature", T(400)),), "solid", "measured", None),)
    props, _ = _alloy_set(extra)
    r = props.resolve("thermal_conductivity", _alloy_state(400))
    assert r.status == "unknown" and "not arbitrated" in r.reason


def test_derived_data_must_carry_transformation_and_stay_labelled():
    fitted = ("kfit350", "thermal_conductivity", Quantity(205.0, K_UNIT), None, (point("temperature", T(350)),), "solid", "fitted",
              lambda claims: TransformationRecord("fixture.linear_fit", "1", tuple(c.digest for c in claims if c.claim_id in ("k300", "k400"))))
    props, _ = _alloy_set((fitted,))
    r = props.resolve("thermal_conductivity", _alloy_state(350))
    assert r.derivation is PropertyDerivation.SOURCED and r.origins == ("fitted",)
    with pytest.raises(InvalidScientificProblem, match="transformation"):
        _alloy_set((fitted[:-1] + (None,),))


def test_material_identity_is_exact_and_never_name_only():
    with pytest.raises(InvalidScientificProblem, match="family only"):
        MaterialIdentity("steel")
    a = MaterialIdentity("steel", specification="FIXTURE-S", grade="G1")
    b = MaterialIdentity("steel", specification="FIXTURE-S", grade="G1", condition="quenched")
    assert a.digest != b.digest
    assert MaterialIdentity.from_dict(json.loads(json.dumps(ALLOY.to_dict()))) == ALLOY
    props, _ = _alloy_set()
    with pytest.raises(InvalidScientificProblem, match="different material"):
        props.resolve("thermal_conductivity", MaterialState(a, (NamedQuantity("temperature", T(400)),)))


def test_claims_must_bind_exact_material_and_applicability():
    props, _ = _alloy_set()
    datum = props.data[0]
    other_app = PropertyApplicability(ALLOY.digest, datum.applicability.property_id, (point("temperature", T(999)),), "solid")
    with pytest.raises(InvalidScientificProblem, match="applicability_context_digest"):
        PropertyDatum(datum.claim, other_app, datum.origin)
    with pytest.raises(InvalidScientificProblem, match="never universally applicable"):
        PropertyApplicability(ALLOY.digest, "density", ())
    with pytest.raises(InvalidScientificProblem, match="without stating why"):
        ApplicabilityRange("temperature", T(300), None)


def test_serialization_replay_and_source_identity():
    props, receipt = _alloy_set()
    again = MaterialPropertySet.from_dict(json.loads(json.dumps(props.to_dict())))
    assert again.digest == props.digest
    a = props.resolve("thermal_conductivity", _alloy_state(450))
    b = again.resolve("thermal_conductivity", _alloy_state(450))
    assert a.digest == b.digest and a.set_digest == props.digest and a.snapshot_digest == props.snapshot.digest
    assert a.sources[0].content_digest == receipt.raw_payload_digest
    assert a.to_dict()["classification"] == "resolved_input_not_evidence"
    # environment sources align to the same identity view without migration
    env_src = EnvironmentSource("met", "measured", "operator", D("met"), "1")
    ks = props.snapshot.sources[0]
    assert set(source_identity(env_src).to_dict()) == set(source_identity(ks).to_dict())


def test_state_schema_refuses_non_physical_state():
    schema = MaterialStateSchema("fixture.state", (ApplicabilityRange("temperature", T(0), None, lower_inclusive=False, unbounded_reason="no upper limit"),))
    with pytest.raises(InvalidScientificProblem, match="physical range"):
        MaterialState(ALLOY, (NamedQuantity("temperature", T(-5)),), "solid", schema)
    with pytest.raises(InvalidScientificProblem, match="does not declare"):
        MaterialState(ALLOY, (NamedQuantity("pressure", Quantity(1, "bar")),), "solid", schema)


# ---- example 2: lifecycle changes material state -> property -> physics ------

BOARD = MaterialIdentity("mineral_wool", specification="FIXTURE-SPEC-B", grade="board-40")
BASIS = TimeBasis("site", "elapsed", "install")
SCENARIO = ScenarioSpecification("wet-season", "1", Quantity(0, "day"), Quantity(3, "day"),
                                 segments=(ScenarioSegment("s", Quantity(0, "day"), Quantity(3, "day")),))
SERVICE_T = T(293.15)


def _board_set():
    rows = [
        (f"k-m{m}", "thermal_conductivity", Quantity(v, K_UNIT), None,
         (point("moisture_content", Quantity(m, "dimensionless")), ApplicabilityRange("temperature", T(273.15), T(313.15))), "", "measured", None)
        for m, v in ((0.0, 0.035), (0.05, 0.045), (0.10, 0.060))
    ]
    return _dataset(BOARD, rows, source_id="fixture-board", locator="tests/test_materials_engine.py::_board_set", set_id="board-props",
                    rules=(InterpolationRule("thermal_conductivity", "moisture_content", "linear"),))[0]


def _insulation_executor(props, resolved_log):
    def execute(run_id, window, initial_state):
        spec = ParticipantSpec("board", "model", "1", "realization", "1", "solver", "1", "adapter", "1",
                               (PortDefinition("heat_flux", PortDirection.OUTPUT, PortKind.SCALAR, "heat_flux", "W/m^2"),), transient=True)
        held = {}
        unknown = Uncertainty.unknown("not quantified")

        def flux():
            # future physics consumes the property RESOLVED from the current material state
            state = MaterialState(BOARD, (NamedQuantity("moisture_content", held["m"].value, held["m"].uncertainty),
                                          NamedQuantity("temperature", SERVICE_T)), schema=INSULATION_STATE_SCHEMA)
            resolved = props.resolve("thermal_conductivity", state)
            if resolved.status != "known":
                raise InvalidScientificProblem(f"conductivity unavailable: {resolved.reason}")
            resolved_log.append(resolved)
            return Quantity(resolved.value.value.magnitude_in(K_UNIT) * 20.0 / 0.1, "W/m^2")

        def digest():
            return hashlib.sha256(repr(held["m"].value.magnitude).encode()).hexdigest()

        def initialize_state(instant, state, _i, _u):
            held["m"] = state["moisture_content"]
            receipt = InitialStateReceipt("board", instant, (state["moisture_content"],), digest())
            return InitializationResult({"heat_flux": flux()}, {"heat_flux": unknown}, initial_state_receipt=receipt)

        participant = CallbackParticipant(
            spec, initialize=lambda *a: (_ for _ in ()).throw(InvalidScientificProblem("explicit state required")),
            advance=lambda req: AdvanceResult(req.end, {"heat_flux": flux()}, {"heat_flux": unknown}, 1, True),
            initial_state_definitions=(InitialStateDefinition("moisture_content", "dimensionless"),),
            initialize_state=initialize_state, state_identity=lambda _t: digest(),
            public_state=lambda _t: (StateVariableValue("moisture_content", held["m"].value, held["m"].uncertainty),),
        )
        start, end = window.start.quantity, window.end.quantity
        plan = CouplingPlan(f"{run_id}-p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                            TimePolicy(start, end, Quantity(end.magnitude - start.magnitude, "s")))
        store = InMemoryBulkStore()
        runtime = MultiphysicsRuntime(PhysicsGraph(f"{run_id}-g", (spec,), ()), plan, {"board": participant},
                                      resolver=BulkDataResolver(store), store=store)
        return runtime.run(run_id, external_inputs={}, initial_state=initial_state, scenario_digest=SCENARIO.digest)
    return execute


def _wet_environment(wetness=(0.3, 0.6, 0.5)):
    p = lambda d: TimePoint("site", Quantity(d, "day"))  # noqa: E731
    history = QuantityHistory("wet", "exposure", "wetness", "dimensionless", tuple(
        HistoryEntry(TimeWindow(p(i), p(i + 1)), NamedQuantity("wetness", Quantity(v, "dimensionless"))) for i, v in enumerate(wetness)))
    timeline = Timeline.from_scenario(SCENARIO, timeline_id="wet", basis=BASIS, histories=(history,))
    channel = EnvironmentChannel("wetness", "surface_wetness", "dimensionless", "met", ReferenceContext("roof", "site-1", "enu"),
                                 TimeWindow(p(0), p(3)), ChannelRepresentation.INTERVAL_HISTORY, history_id="wet")
    return EnvironmentTimeline("wet-env", timeline, EnvironmentKindRegistry.standard(),
                               (EnvironmentSource("met", "measured", "operator", D("met"), "1"),), (channel,))


def test_lifecycle_moisture_changes_resolved_conductivity_and_future_heat_flux():
    props = _board_set()
    log = []
    p = lambda d: TimePoint("site", Quantity(d, "day"))  # noqa: E731
    chain, runs = run_lifecycle(
        model=LinearWetnessMoistureUptake(k_uptake=Quantity(1e-6, "1/s"), max_wet_time=Quantity(1, "day")),
        environment=_wet_environment(), participant_id="board",
        definitions=(InitialStateDefinition("moisture_content", "dimensionless"),),
        initial_state={"board": {"moisture_content": InitialStateValue("moisture_content", Quantity(0.0, "dimensionless"), Uncertainty.unknown("as installed"))}},
        windows=tuple(TimeWindow(p(i), p(i + 1)) for i in range(3)),
        execute=_insulation_executor(props, log), bindings=(InputBinding("wet_time", "wetness"),),
    )
    assert [s.status for s in chain.steps] == [StepStatus.APPLIED] * 3
    moisture = [0.0] + [s.resulting_values[0].value.magnitude for s in chain.steps]
    assert all(a < b for a, b in zip(moisture, moisture[1:]))
    fluxes = [r.final_outputs["board.heat_flux"]["magnitude"] for r in runs]
    assert fluxes[0] < fluxes[1] < fluxes[2]
    # window 1+ resolved conductivity by INTERPOLATION from the degraded state, bound to the dataset
    later = [r for r in log if r.derivation is PropertyDerivation.INTERPOLATED]
    assert later and all(r.set_digest == props.digest for r in log)
    assert log[0].derivation is PropertyDerivation.SOURCED  # dry board: a tabulated point


def test_degraded_state_beyond_tabulated_data_stops_physics_instead_of_extrapolating():
    props = _board_set()
    p = lambda d: TimePoint("site", Quantity(d, "day"))  # noqa: E731
    with pytest.raises(InvalidScientificProblem, match="conductivity unavailable"):
        run_lifecycle(
            model=LinearWetnessMoistureUptake(k_uptake=Quantity(5e-6, "1/s"), max_wet_time=Quantity(1, "day")),
            environment=_wet_environment(), participant_id="board",
            definitions=(InitialStateDefinition("moisture_content", "dimensionless"),),
            initial_state={"board": {"moisture_content": InitialStateValue("moisture_content", Quantity(0.0, "dimensionless"), Uncertainty.unknown("as installed"))}},
            windows=tuple(TimeWindow(p(i), p(i + 1)) for i in range(3)),
            execute=_insulation_executor(props, []), bindings=(InputBinding("wet_time", "wetness"),),
        )


def test_interpolation_with_mixed_unit_points_uses_one_unit():
    rows = [
        ("kc20", "thermal_conductivity", Quantity(1.0, K_UNIT), None, (point("temperature", Quantity(20, "degC")),), "solid", "measured", None),
        ("kk373", "thermal_conductivity", Quantity(2.0, K_UNIT), None, (point("temperature", T(373.15)),), "solid", "measured", None),
    ]
    props, _ = _dataset(ALLOY, rows, source_id="fixture-mixed", locator="tests::mixed", set_id="mixed",
                        rules=(InterpolationRule("thermal_conductivity", "temperature", "linear"),))
    r = props.resolve("thermal_conductivity", MaterialState(ALLOY, (NamedQuantity("temperature", Quantity(50, "degC")),), "solid"))
    assert r.derivation is PropertyDerivation.INTERPOLATED
    assert r.value.value.magnitude == pytest.approx(1.375)  # w = 30/80
    r_k = props.resolve("thermal_conductivity", MaterialState(ALLOY, (NamedQuantity("temperature", T(323.15)),), "solid"))
    assert r_k.value.value.magnitude == pytest.approx(1.375)


def test_assumed_datum_resolves_as_assumed_not_sourced():
    rows = [("k-assumed", "thermal_conductivity", Quantity(150.0, K_UNIT), None, (ApplicabilityRange("temperature", T(250), T(350)),), "solid", "assumed", None)]
    props, _ = _dataset(ALLOY, rows, source_id="fixture-assumed", locator="tests::assumed", set_id="assumed")
    assert props.resolve("thermal_conductivity", _alloy_state(300)).derivation is PropertyDerivation.ASSUMED


def test_breakpoints_are_dimension_checked_at_construction():
    with pytest.raises(Exception):
        InterpolationRule("thermal_conductivity", "temperature", "linear", (T(500), Quantity(1, "m")))
