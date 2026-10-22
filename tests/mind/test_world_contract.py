"""GEN2-BR1 contract tests: the fail-closed, authority and replay properties the design review required.

Each block pins one property of ``engcore.mind.world`` that the failing-first file does not:

* removing information (a value, an uncertainty, a provider, a budget declaration, a cost, a fixed condition, a
  control's value) never turns a non-FEASIBLE decision FEASIBLE;
* model applicability gates model execution only, through the core assessment, with its status verbatim;
* an undeclared budget dimension or cost is MISSING_INFORMATION, never unlimited or zero;
* the execution gate refuses re-dispatch, cumulative overspend, a foreign provider build and a forged clearance;
* the Mind port reaches no executor; external proposals enter only as ExternalSuggestion records;
* replay verifies its inputs before recomputing; revisions verify as a chain; identity is unit-canonical.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib

import pytest

import engcore.mind.world as world_pkg
from benchmarks.mind_gen2_world_v1 import fixtures as fx
from engcore.mind.repsem import canonical_bytes
from engcore.mind.repsem.roles import RoleSource
from engcore.mind.world import (
    ActionMode, CheckFamily, ClearedAction, DeclaredConstraint, ExecutionGate, ExecutionKind, FeasibilityDecision,
    FeasibilityStatus as F, FeasibleActionSpace, FORBIDDEN_PROPOSAL_KEYS, GateRefused, IntakeCode, IntakeRefusal,
    MindWorldPort, ProposedAction, ScientificWorld, WorldRefused, replay_decision, verify_lineage,
)
from engcore.mind.world.feasibility import STATUS_BY_SOURCE, FamilyRecord, FeasibilityReason
from engcore.mind.world.world import EXECUTABLE_HEALTH, ProviderSnapshot
from engcore.providers.health import ProviderHealth, ProviderHealthReport
from engcore.scientific import Uncertainty
from engcore.scientific.ir.values import CategoricalValue, IntegerValue
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.external import AUTHORITY_KEYS, ExternalSuggestion
from engcore.sria.decision.hypotheses import ProposalProvenance, ProposerKind
from engcore.sria.decision.replay import ReplayOutcome

q, cat = fx.q, fx.cat


def space(w: ScientificWorld) -> FeasibleActionSpace:
    return FeasibleActionSpace.build(w)


def check(w: ScientificWorld, action_id: str, assignments, observe=()):
    return space(w).check(fx.propose(w, action_id, assignments, observe))


def codes(d) -> set[str]:
    return {r.code for r in d.reasons}


def with_variable(w: ScientificWorld, name: str, reason: str, **changes) -> ScientificWorld:
    return w.derive(reason=reason, variables=tuple(dataclasses.replace(v, **changes) if v.name == name else v
                                                   for v in w.variables))


def with_action(w: ScientificWorld, action_id: str, reason: str, **changes) -> ScientificWorld:
    return w.derive(reason=reason, actions=tuple(dataclasses.replace(a, **changes) if a.action_id == action_id else a
                                                 for a in w.actions))


@pytest.fixture(scope="module")
def battery():
    return fx.battery_world()


# ---- removal never improves an answer ---------------------------------------------------------------------------------------
def _proposals(name: str, w: ScientificWorld):
    out = []
    for aid, (assignments, observe) in fx.base(name).items():
        out.append((aid, assignments, observe))
        spec = w.action(aid)
        for control in spec.controls:                      # one non-FEASIBLE variant per control: never supplied
            out.append((aid, {k: v for k, v in assignments.items() if k != control.variable}, observe))
    return out


def _reductions(w: ScientificWorld):
    """World-side information removals: every one must leave a non-FEASIBLE decision non-FEASIBLE."""
    for v in w.variables:
        if v.value is not None:
            yield f"withdraw value {v.name}", lambda w=w, n=v.name: with_variable(
                w, n, "value withdrawn", value=None, origin=None, source=None, value_basis="",
                uncertainty=Uncertainty.unknown("withdrawn"))
            if v.uncertainty.is_quantified:
                yield f"forget uncertainty {v.name}", lambda w=w, n=v.name: with_variable(
                    w, n, "uncertainty forgotten", uncertainty=Uncertainty.unknown("forgotten"))
    for p in w.providers:
        yield f"drop provider {p.provider_id}", lambda w=w, pid=p.provider_id: w.derive(
            reason="provider snapshot dropped", providers=tuple(x for x in w.providers if x.provider_id != pid))
    for dim, _ in w.budget.unbounded:
        yield f"undeclare {dim}", lambda w=w, d=dim: w.derive(reason="declaration dropped", budget=dataclasses.replace(
            w.budget, unbounded=tuple(x for x in w.budget.unbounded if x[0] != d)))
    for a in w.actions:
        for dim, _ in a.estimated_cost:
            yield f"drop cost {a.action_id}.{dim}", lambda w=w, a=a, d=dim: with_action(
                w, a.action_id, "cost dropped", estimated_cost=tuple(x for x in a.estimated_cost if x[0] != d))
        for f in a.fixed_conditions:
            yield f"drop fixed {a.action_id}.{f.name}", lambda w=w, a=a, n=f.name: with_action(
                w, a.action_id, "fixed condition dropped",
                fixed_conditions=tuple(x for x in a.fixed_conditions if x.name != n))


@pytest.mark.parametrize("name", sorted(fx.WORLDS))
def test_removing_information_never_turns_a_refusal_into_feasible(name):
    w = fx.WORLDS[name]()
    proposals = _proposals(name, w)
    before = {(aid, repr(sorted(a)), o): check(w, aid, a, o).status for aid, a, o in proposals}
    assert F.FEASIBLE in before.values() and any(s is not F.FEASIBLE for s in before.values())
    for label, reduce in _reductions(w):
        try:
            reduced = reduce()
        except WorldRefused:
            continue                                        # a world that cannot be stated is not a FEASIBLE answer
        for aid, a, o in proposals:
            after = check(reduced, aid, {k: v for k, v in a.items()}, o).status
            if before[(aid, repr(sorted(a)), o)] is not F.FEASIBLE:
                assert after is not F.FEASIBLE, f"{name}: '{label}' turned {aid} FEASIBLE"


# ---- applicability gates model execution only ---------------------------------------------------------------------------------
def test_s9_outside_the_route_models_domain_is_infeasible_applicability_with_the_core_status(battery):
    d = check(battery, "simulate_pulse", {"I": q(2, "A"), "T_amb": q(80, "degC"), "t_pulse": q(60, "s")})
    assert d.status is F.INFEASIBLE_APPLICABILITY
    r = next(r for r in d.reasons if r.code == "OUTSIDE_VALIDATED_DOMAIN")
    assert r.detail["validity_status"] == "outside_validated_domain" and list(r.detail["violated"]) == ["T_amb"]
    payload = d.to_dict()
    assert payload["classification"] == "action_feasibility_not_scientific_support"
    assert not {"hypothesis", "claim", "verdict", "supported", "refused"} & set(payload)


def test_conditional_provider_availability_is_the_route_models_applicability():
    motor = fx.motor_world()
    d = check(motor, "simulate_thermal", {"I_cmd": q(28, "A"), "solver_iterations": IntegerValue(200)})
    assert d.status is F.INFEASIBLE_APPLICABILITY            # 28 A is inside the control's 0-30 A, outside the route
    assert check(motor, "simulate_thermal", {"I_cmd": q(25, "A"), "solver_iterations": IntegerValue(200)}).feasible


def test_applicability_is_an_annotation_for_a_system_query(battery):
    spec = battery.action("signed_pulse")
    w = battery.derive(reason="annotate", actions=tuple(
        dataclasses.replace(a, applicability=(battery.applicability[0].binding_id,)) if a is spec else a
        for a in battery.actions))
    d = check(w, "signed_pulse", {"mode": cat("discharge"), "I": q(-2, "A"), "t_pulse": q(30, "s")})
    assert d.feasible and d.annotations[0]["gating"] is False
    with pytest.raises(WorldRefused, match="MODEL_EXECUTION"):
        dataclasses.replace(battery.action("simulate_pulse"), applicability=())


def test_unknown_and_undecided_applicability_are_missing_information():
    drone = fx.drone_world()
    blind = with_variable(drone, "wind", "anemometer reading withdrawn", value=None, origin=None, source=None,
                          uncertainty=Uncertainty.unknown("withdrawn"))
    d = check(blind, "simulate_flight", {"thrust_cmd": q(12, "N")})
    assert d.status is F.MISSING_INFORMATION and "APPLICABILITY_NOT_SUPPLIED" in codes(d)
    straddle = with_variable(drone, "wind", "gusty", value=q(11.8, "m/s"), uncertainty=fx.interval(11.8, 0.5, "m/s"))
    assert "APPLICABILITY_UNDECIDED" in codes(check(straddle, "simulate_flight", {"thrust_cmd": q(12, "N")}))
    windy = with_variable(drone, "wind", "storm", value=q(15, "m/s"), uncertainty=fx.interval(15, 0.5, "m/s"))
    assert check(windy, "simulate_flight", {"thrust_cmd": q(12, "N")}).status is F.INFEASIBLE_APPLICABILITY


# ---- budget: undeclared is never unlimited, missing cost is never zero ----------------------------------------------------------
def test_undeclared_budget_dimension_and_cost_are_missing_information(battery):
    b = battery.budget
    w = battery.derive(reason="cost declaration dropped",
                       budget=dataclasses.replace(b, unbounded=tuple(x for x in b.unbounded if x[0] != "cost")))
    d = check(w, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")})
    assert d.status is F.MISSING_INFORMATION and "BUDGET_DIMENSION_UNDECLARED" in codes(d)
    nocost = with_action(battery, "pulse", "cost dropped", estimated_cost=())
    assert "COST_NOT_DECLARED" in codes(check(nocost, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}))


def test_wall_time_budget_is_checked_against_the_declared_duration():
    hvac = fx.hvac_world("chamber")
    long = with_action(hvac, "mode_change", "a longer run", estimated_duration=q(7, "hour"))
    d = check(long, "mode_change", {"hvac_mode": cat("heat"), "speed": q(3500, "rpm")})
    reason = next(r for r in d.reasons if r.code == "OVER_BUDGET")
    assert reason.subject == "wall_time" and reason.detail["remaining"] == 6 * 3600.0


def test_negative_or_untyped_costs_are_refused():
    with pytest.raises(WorldRefused):
        fx.action("x", ActionFamily.EXPLORE, ActionMode.OBSERVE, expected_observables=("V",),
                  estimated_cost={"experiments": IntegerValue(-1)})
    with pytest.raises(WorldRefused):
        fx.action("x", ActionFamily.EXPLORE, ActionMode.OBSERVE, expected_observables=("V",),
                  estimated_cost={"cost": q(-5, "dimensionless")})


# ---- the gate ------------------------------------------------------------------------------------------------------------------------
def _cleared(w: ScientificWorld, aid: str, assignments, observe=()):
    decision, cleared = space(w).clear(fx.propose(w, aid, assignments, observe))
    assert decision.feasible and cleared is not None
    return cleared


def test_the_gate_dispatches_a_cleared_action_once_with_its_resolved_configuration(battery):
    calls = []
    gate = ExecutionGate(space(battery), calls.append)
    sp = gate._space
    _, cleared = sp.clear(fx.propose(battery, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}, ("V",)))
    gate.dispatch(cleared)
    assert len(calls) == 1 and dict(calls[0].configuration)["T_amb"] == q(25, "degC")      # fixed conditions resolved
    with pytest.raises(GateRefused, match="DUPLICATE_DISPATCH"):
        gate.dispatch(cleared)
    assert len(calls) == 1


def test_the_gate_reserves_budget_across_dispatches():
    w = fx.gen1_pool_world()
    w = w.derive(reason="23 of 24 experiments spent", budget=fx.budget(24, 23, ledger="gen1-pool"))
    sp = space(w)
    gate = ExecutionGate(sp, lambda c: "ran")
    a = sp.clear(fx.propose(w, "pool_query", {"I_A": q(1.0, "A"), "t_on_s": q(30, "s")}))[1]
    b = sp.clear(fx.propose(w, "pool_query", {"I_A": q(2.0, "A"), "t_on_s": q(30, "s")}))[1]
    assert gate.dispatch(a) == "ran"
    with pytest.raises(GateRefused, match="OVER_BUDGET_RESERVED"):
        gate.dispatch(b)


def test_the_gate_requires_the_cleared_provider_build(battery):
    sp = space(battery)
    cleared = sp.clear(fx.propose(battery, "simulate_pulse", *fx.base("battery")["simulate_pulse"]))[1]
    with pytest.raises(GateRefused, match="PROVIDER_BUILD_MISMATCH"):
        ExecutionGate(sp, lambda c: None).dispatch(cleared)
    with pytest.raises(GateRefused, match="PROVIDER_BUILD_MISMATCH"):
        ExecutionGate(sp, lambda c: None, provider_builds={"sim.ecm": ("1.0", "0" * 64)}).dispatch(cleared)
    ok = ExecutionGate(sp, lambda c: "ran", provider_builds={"sim.ecm": ("1.0", fx.build_digest("sim.ecm", "1.0"))})
    assert ok.dispatch(cleared) == "ran"


def test_a_forged_clearance_is_refused(battery):
    sp = space(battery)
    bad = fx.propose(battery, "pulse", {"I": q(1.15, "A"), "t_pulse": q(60, "s")})
    good = sp.clear(fx.propose(battery, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}))[1]
    forged = dataclasses.replace(good, proposal=bad)
    with pytest.raises(GateRefused, match="NOT_REPRODUCED"):
        ExecutionGate(sp, lambda c: None).dispatch(forged)
    tampered = dataclasses.replace(good, configuration=good.configuration + (("SOC", q(0.5, "dimensionless")),))
    with pytest.raises(GateRefused, match="CONFIGURATION_TAMPERED"):
        ExecutionGate(sp, lambda c: None).dispatch(tampered)
    with pytest.raises(GateRefused, match="NOT_CLEARED"):
        ExecutionGate(sp, lambda c: None).dispatch(good.proposal)  # type: ignore[arg-type]
    other = space(battery.derive(reason="spent", budget=fx.budget(20, 4, solver=(10, 4), ledger="battery")))
    with pytest.raises(GateRefused, match="OTHER_SPACE"):
        ExecutionGate(other, lambda c: None).dispatch(good)


# ---- the Mind port -------------------------------------------------------------------------------------------------------------------
def test_the_port_reaches_no_executor():
    tree = ast.parse(pathlib.Path(world_pkg.__file__).with_name("port.py").read_bytes().decode("utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and ("gate" in m or "provider" in m or "execution" in m) for m in imported)
    identifiers = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
        a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert not {i for i in identifiers if "gate" in i.lower() or "execut" in i.lower() or "dispatch" in i.lower()}


def test_reading_and_proposing_through_the_port_never_executes(battery):
    calls = []
    sp = space(battery)
    ExecutionGate(sp, calls.append)                         # an executor exists, held by its owner only
    port = MindWorldPort(sp)
    assert port.world is battery and port.action_space is sp
    d = port.propose(fx.propose(battery, "pulse", {"I": q(1.15, "A"), "t_pulse": q(60, "s")}))
    assert d.status is F.INFEASIBLE_PROTOCOL and calls == [] and len(port.journal) == 1
    assert set(MindWorldPort.__slots__) == {"_space", "_journal"}


# ---- external intake --------------------------------------------------------------------------------------------------------------
def _suggestion(point, *, kind=ProposerKind.LANGUAGE_MODEL, target="pulse", extra=None):
    return ExternalSuggestion(kind, "llm", "1", ActionFamily.EXPLORE, target, point, "because", extra=extra or {})


def _assign(**values):
    return [{"variable": k, "value": v.to_dict() if hasattr(v, "to_dict") else v} for k, v in values.items()]


def test_a_language_model_proposal_enters_as_a_suggestion_and_meets_the_same_check(battery):
    port = MindWorldPort(space(battery))
    d = port.propose_suggestion(_suggestion({"assignments": _assign(I=q(1.15, "A"), t_pulse=q(60, "s"))}))
    assert isinstance(d, FeasibilityDecision) and d.status is F.INFEASIBLE_PROTOCOL
    with pytest.raises(WorldRefused, match="ExternalSuggestion"):
        ProposedAction("pulse", battery.revision_id, {"I": q(1.0, "A")}, (),
                       ProposalProvenance(ProposerKind.LANGUAGE_MODEL, "llm"))


@pytest.mark.parametrize("point, code", [
    ({"assignments": _assign(I=q(1.0, "A")), "feasible": True}, IntakeCode.AUTHORITY_KEY),
    ({"assignments": _assign(I=q(1.0, "A")), "confidence": 0.9}, IntakeCode.AUTHORITY_KEY),
    ({"assignments": [{"variable": "I", "value": 1.0}]}, IntakeCode.NOT_A_TYPED_VALUE),
    ({"assignments": _assign(I=q(1.0, "A")), "note": "x"}, IntakeCode.UNKNOWN_KEY),
    ({"assignments": [{"variable": "mode", "value": CategoricalValue("charge", ("charge", "x")).to_dict()}]},
     IntakeCode.AUTHORITY_KEY),
])
def test_intake_refusals_are_structured(battery, point, code):
    result = MindWorldPort(space(battery)).propose_suggestion(_suggestion(point))
    assert isinstance(result, IntakeRefusal) and result.code is code
    assert IntakeRefusal.from_dict(result.to_dict()) == result


def test_a_suggestion_is_bound_to_the_ports_own_revision_and_a_stale_proposal_is_refused(battery):
    child = battery.derive(reason="spent", budget=fx.budget(20, 4, solver=(10, 4), ledger="battery"))
    port = MindWorldPort(space(child))
    result = port.propose_suggestion(_suggestion({"assignments": _assign(I=q(1.0, "A"), t_pulse=q(60, "s"))}))
    assert isinstance(result, FeasibilityDecision) and result.world_revision == child.revision_id
    from engcore.mind.world import StaleProposal
    with pytest.raises(StaleProposal):
        port.propose(fx.propose(battery, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}))


def test_forbidden_keys_cover_the_certified_and_gen1_lists():
    from engcore.mind.minimal.structures import _FORBIDDEN_PROPOSAL_KEYS as gen1
    assert set(AUTHORITY_KEYS) <= FORBIDDEN_PROPOSAL_KEYS and set(gen1) <= FORBIDDEN_PROPOSAL_KEYS
    assert {"feasible", "budget", "domain", "levels", "vocabulary"} <= FORBIDDEN_PROPOSAL_KEYS


def test_a_variable_named_like_a_forbidden_key_still_works_through_intake():
    n = {"I": "status", "t_pulse": "budget"}.get
    w = fx.battery_world(lambda s: n(s) or s)
    d = MindWorldPort(space(w)).propose_suggestion(
        _suggestion({"assignments": [{"variable": "status", "value": q(1.0, "A").to_dict()},
                                     {"variable": "budget", "value": q(60, "s").to_dict()}]}))
    assert isinstance(d, FeasibilityDecision) and d.feasible


# ---- replay and identity --------------------------------------------------------------------------------------------------------------
def test_replay_verifies_its_inputs_before_recomputing(battery):
    p = fx.propose(battery, "pulse", {"I": q(1.15, "A"), "t_pulse": q(60, "s")})
    d = space(battery).check(p).to_dict()
    assert replay_decision(d, battery.to_dict(), p.to_dict()).outcome is ReplayOutcome.REPRODUCED
    other = fx.propose(battery, "pulse", {"I": q(2.0, "A"), "t_pulse": q(60, "s")})
    r = replay_decision(d, battery.to_dict(), other.to_dict())
    assert r.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE and "proposal_digest" in r.mismatches
    tampered_world = battery.to_dict()
    tampered_world["basis"] = "edited after the fact"
    assert replay_decision(d, tampered_world, p.to_dict()).outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE
    forged = dict(d, status="FEASIBLE", reasons=[])
    assert replay_decision(forged, battery.to_dict(), p.to_dict()).outcome is ReplayOutcome.NONDETERMINISM_DETECTED


@pytest.mark.parametrize("name", sorted(fx.WORLDS))
def test_every_fixture_world_round_trips_byte_identically(name):
    w = fx.WORLDS[name]()
    payload = w.to_dict()
    again = ScientificWorld.from_dict(payload)
    assert canonical_bytes(again.to_dict()) == canonical_bytes(payload) and again.revision_id == w.revision_id
    for aid, (a, o) in fx.base(name).items():
        d = check(w, aid, a, o)
        assert FeasibilityDecision.from_dict(d.to_dict()).to_dict() == d.to_dict()


def test_labels_are_not_identity_and_unit_spellings_are_one_value(battery):
    v = battery.variable("I")
    relabelled = dataclasses.replace(battery, variables=tuple(dataclasses.replace(x, label="renamed for humans")
                                                              if x is v else x for x in battery.variables),
                                     description="new words")
    assert relabelled.content_digest == battery.content_digest
    with pytest.raises(WorldRefused, match="no material change"):
        battery.derive(reason="only a label", variables=relabelled.variables)
    pulse = battery.action("pulse")
    in_mA = dataclasses.replace(pulse, controls=tuple(
        dataclasses.replace(c, domain=fx.levels("mA", 1000, 2000)) if c.variable == "I" else c for c in pulse.controls))
    assert in_mA.digest == pulse.digest                       # 1000 mA and 1 A are one level
    with pytest.raises(WorldRefused, match="no material change"):
        battery.derive(reason="levels respelled", actions=tuple(in_mA if a is pulse else a for a in battery.actions))
    widened = dataclasses.replace(pulse, controls=tuple(
        dataclasses.replace(c, domain=fx.levels("A", 1.0, 2.0, 4.0)) if c.variable == "I" else c for c in pulse.controls))
    moved = battery.derive(reason="a third level", actions=tuple(widened if a is pulse else a for a in battery.actions))
    assert moved.revision_id != battery.revision_id and moved.lineage.changed_fields == ("actions",)


def test_lineage_verifies_as_a_chain_and_refuses_forgery(battery):
    a = battery.derive(reason="spent one", budget=fx.budget(20, 4, solver=(10, 4), ledger="battery"))
    b = a.derive(reason="provider down", providers=(fx.provider("sim.ecm", "1.0", available=False),))
    store = {w.revision_id: w for w in (battery, a, b)}
    assert verify_lineage(b, store) == (battery.revision_id, a.revision_id, b.revision_id)
    forged = dataclasses.replace(b, lineage=dataclasses.replace(b.lineage, changed_fields=("budget",)))
    with pytest.raises(WorldRefused, match="changed fields"):
        verify_lineage(forged, store)
    with pytest.raises(WorldRefused, match="parent"):
        verify_lineage(b, {b.revision_id: b})


def test_provider_snapshots_are_the_owner_records_and_bind_together():
    snap = fx.provider("sim.ecm", "1.0")
    other = fx.provider("sim.ecm", "2.0")
    with pytest.raises(WorldRefused, match="status digest"):
        ProviderSnapshot(snap.status, other.report)
    with pytest.raises(TypeError):
        snap.status["version"] = "9"                             # frozen
    for health in ProviderHealth:
        report = ProviderHealthReport("p", health, "r", "0" * 64)
        assert (health in EXECUTABLE_HEALTH) is report.executable


def test_the_status_by_source_table_is_exhaustive_over_declarable_sources():
    assert set(STATUS_BY_SOURCE) == set(RoleSource) - {RoleSource.LEGACY_ADAPTER_DEFAULT}
    with pytest.raises(WorldRefused, match="legacy"):
        fx.ctrl("I", fx.levels("A", 1.0), RoleSource.LEGACY_ADAPTER_DEFAULT)


def test_a_decision_cannot_be_feasible_without_every_family_or_disagree_with_its_reasons(battery):
    d = check(battery, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")})
    assert d.feasible and {c.family for c in d.checked} == set(CheckFamily)
    with pytest.raises(WorldRefused, match="every check family"):
        dataclasses.replace(d, checked=d.checked[:-1])
    reason = FeasibilityReason(F.MISSING_INFORMATION, "X", CheckFamily.STATE, "s", "m")
    with pytest.raises(WorldRefused, match="disagrees"):
        dataclasses.replace(d, reasons=(reason,))
    bad = check(battery, "pulse", {"I": q(1.15, "A")})
    exported = bad.feasibility_verdicts()
    assert exported and all(not v.feasible for v in exported)
    assert not any("MISSING_INFORMATION" in v.reason for v in exported)


# ---- domains: kinds, units, edges, guards, scope, uncertainty --------------------------------------------------------------------------
def test_offset_units_compare_in_their_ratio_base(battery):
    drone = fx.drone_world()
    assert check(drone, "hover_test", {"thrust_cmd": q(12, "N"), "payload": q(500, "g")}).feasible
    w = fx.gen1_pool_world()
    assert check(w, "pool_query", {"I_A": q(1000, "mA"), "t_on_s": q(0.5, "min")}).feasible
    hvac = fx.hvac_world("chamber")
    assert check(hvac, "step_speed", {"speed": q(3000, "rpm"), "fan_stage": IntegerValue(3),
                                      "T_out": q(95, "degF")}).feasible        # 95 degF is the fixed 35 degC
    # identity precision is 12 significant digits: a value equal to a level at that precision IS that level
    assert check(w, "pool_query", {"I_A": q(1.0000000000004, "A"), "t_on_s": q(30, "s")}).feasible
    assert not check(w, "pool_query", {"I_A": q(1.000000001, "A"), "t_on_s": q(30, "s")}).feasible


def test_integer_and_categorical_kinds_are_checked_by_kind():
    hvac = fx.hvac_world("chamber")
    assert "OUTSIDE_RANGE" in codes(check(hvac, "step_speed", {"speed": q(3000, "rpm"), "fan_stage": IntegerValue(6)}))
    assert "VALUE_KIND_MISMATCH" in codes(check(hvac, "step_speed", {"speed": q(3000, "rpm"),
                                                                     "fan_stage": q(2.5, "dimensionless")}))
    d = check(hvac, "mode_change", {"hvac_mode": cat("defrost"), "speed": q(3000, "rpm")})
    assert d.status is F.INFEASIBLE_PROTOCOL and "CATEGORY_NOT_DECLARED" in codes(d)
    assert "VALUE_KIND_MISMATCH" in codes(check(hvac, "mode_change", {"hvac_mode": q(1, "dimensionless"),
                                                                      "speed": q(3000, "rpm")}))


def test_guard_precedence_is_proposal_then_fixed_condition_then_declared_value(battery):
    declared_discharge = with_variable(battery, "mode", "protocol states discharge", value=cat("discharge"),
                                       origin=fx.ValueOrigin.DECLARED, value_basis="protocol states it")
    ok = check(declared_discharge, "signed_pulse", {"mode": cat("charge"), "I": q(2, "A"), "t_pulse": q(30, "s")})
    assert ok.feasible                                         # the proposal's mode wins over the declared one


def test_constraint_scope_is_declared_and_names_resolve_exactly(battery):
    c = battery.constraints[0]
    widened = battery.derive(reason="charge rule for every action",
                             constraints=(dataclasses.replace(c, applies_to=("*",)),) + battery.constraints[1:])
    d = check(widened, "observe_rest", {}, ("V",))
    assert d.status is F.MISSING_INFORMATION and "GUARD_UNRESOLVED" in codes(d)   # observe_rest never states a mode
    with pytest.raises(WorldRefused, match="undeclared"):
        battery.derive(reason="typo", constraints=(dataclasses.replace(
            c, consequence=dataclasses.replace(c.consequence, metric="I_typo")),))
    with pytest.raises(WorldRefused, match="undeclared actions"):
        battery.derive(reason="typo", constraints=(dataclasses.replace(c, applies_to=("pulse_typo",)),))


def test_preconditions_hold_at_the_edges_of_the_current_value(battery):
    point = with_variable(battery, "SOC", "a point estimate", uncertainty=Uncertainty(
        kind="standard", standard_uncertainty=q(0.02, "dimensionless"), method="declared"))
    assert "PRECONDITION_UNCERTAINTY_UNKNOWN" in codes(check(point, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}))
    straddle = with_variable(battery, "SOC", "near the floor", value=q(0.11, "dimensionless"),
                             uncertainty=fx.interval(0.11, 0.02, "dimensionless"))
    assert "PRECONDITION_UNDECIDED" in codes(check(straddle, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}))
    low = with_variable(battery, "SOC", "empty", value=q(0.05, "dimensionless"),
                        uncertainty=fx.interval(0.05, 0.01, "dimensionless"))
    assert check(low, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}).status is F.INFEASIBLE_STATE


def test_alternatives_are_declared_options_never_projections():
    w = fx.gen1_pool_world()
    p = fx.propose(w, "pool_query", {"I_A": q(1.15, "A"), "t_on_s": q(55.62, "s")})
    alt = space(w).alternatives(p, "I_A")
    assert [o.magnitude for o in alt["options"]] == [1.0, 2.0] and "not recommendations" in alt["label"]
    rng = space(w).alternatives(p, "t_on_s")
    assert rng["kind"] == "declared_range" and "options" not in rng
