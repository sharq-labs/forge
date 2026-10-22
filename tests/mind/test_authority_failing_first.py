"""GEN2-BR1.1 failing-first controls: an authority-bound ScientificWorld and non-bypassable action admission.

Written before the repair.  Each test pins one blocker from the GEN2-BR1 review (``benchmarks/mind_gen2_world_v1/
README.md`` section 6) or one BR1.1 brief control (section 21, A-O).  The authority-bound fixtures
(``benchmarks/mind_gen2_authority_v1/fixtures.py``) read every projected fact from a real owner record; they are
imported per test so that this module collects on the unrepaired tree and every control fails on its own.

A. a 10 %-coverage interval cannot prove hard-domain containment (BR1.1 round 1: no interval at any coverage or
   source proves one, and a declared set point is never exact by default)
B. one owner record cannot be re-bound to a different value (lineage laundering)
C. a non-existent owner record cannot support admission
D. a stale state binding refuses
E. a stale applicability (model record) binding refuses
F. a stale provider binding refuses
G. a stale protocol / domain declaration binding refuses
H. a stale budget binding refuses, and the budget owner states a verifiable identity
I. copied unit display text cannot change unit authority
J. a raw proposal cannot execute
K. an external proposer cannot mint an admitted action
L. an admitted action becomes unusable when material authority changes before dispatch (BR1.1 round 1: against
   live readers only; the desk is not an effect ledger)
M. replay of a historical admission is exact even after the owners moved on; dispatching it now is refused
N. the exact current verified world still admits every valid BR1 control that reads no current value
O. an invalid 1.15 A proposal stays refused with alternatives 1.0 A and 2.0 A
"""

from __future__ import annotations

import copy
import dataclasses
import importlib

import pytest

from benchmarks.mind_gen2_world_v1 import fixtures as br1
from engcore.mind.world import FeasibilityStatus as F, FeasibleActionSpace, ValueOrigin, WorldRefused, verify_lineage
from engcore.scientific import Uncertainty

D = "dimensionless"
PULSE = {"I": br1.q(1.0, "A"), "t_pulse": br1.q(60, "s")}
SIM = br1.base("battery")["simulate_pulse"]                  # admissible: it reads no current value of the world


@pytest.fixture(scope="module")
def ax():
    """The BR1.1 authority-bound fixtures (imported lazily: they need the repaired API)."""
    return importlib.import_module("benchmarks.mind_gen2_authority_v1.fixtures")


def _api(name: str):
    return importlib.import_module(f"engcore.mind.world.{name}")


def _admit(world, proposal, authorities):
    admission = _api("admission")
    return admission.admit(FeasibleActionSpace.build(world), proposal, authorities)


def _codes(result) -> set[str]:
    return {r.code for r in result.reasons}


def _soc(world, **fields):
    return tuple(dataclasses.replace(v, **fields) if v.name == "SOC" else v for v in world.variables)


# ---- A. coverage is not an enclosure ----------------------------------------------------------------------------------
def test_a_a_10_percent_coverage_interval_never_proves_hard_containment():
    """BR1 reproduced: [0.105, 0.115] at 10 % coverage against a 0.1 floor was FEASIBLE."""
    w = br1.battery_world()
    u10 = Uncertainty(kind="interval", lower=br1.q(0.105, D), upper=br1.q(0.115, D), confidence_level=0.10,
                      method="synthetic 10 % coverage")
    low = w.derive(reason="a low estimate", variables=_soc(w, value=br1.q(0.11, D), uncertainty=u10,
                                                          source=br1.synthetic("soc/low")))
    d = FeasibleActionSpace.build(low).check(br1.propose(low, "pulse", PULSE))
    assert d.status is F.MISSING_INFORMATION


def test_a_no_interval_at_any_coverage_or_from_any_source_proves_containment(ax):
    """Brief section 9; round-1 MAJORs A-F1 and A-F3: the state owner commits SOC [0.105, 0.115] (and [0.7, 0.9],
    wholly above the 0.1 floor) at 10 %, 95 % or 99.9999 % coverage, from a NUMERICAL, MEASUREMENT or COMBINED source:
    admission is MISSING_INFORMATION every time and no admitted action is minted.  No core uncertainty record is an
    enclosure and no owner states a decision-coverage policy, so no world or caller rule turns a band into a decision."""
    from engcore.scientific.results.uncertainty import UncertaintySource as S
    o = ax.owned("battery")
    for lo, hi in ((0.105, 0.115), (0.7, 0.9)):
        for level in (0.10, 0.95, 0.999999):
            for source in (S.NUMERICAL, S.MEASUREMENT, S.COMBINED, S.UNSPECIFIED):
                u = Uncertainty(kind="interval", lower=br1.q(lo, D), upper=br1.q(hi, D), confidence_level=level,
                                method="stated", source_kind=source)
                vals = {"cell": ("component", {"SOC": (br1.q((lo + hi) / 2, D), u),
                                               "R0": (br1.q(0.012, "ohm"), Uncertainty.unknown("not quantified"))})}
                authorities = o.authorities(state=ax.run_state(f"battery.{lo}.{level}.{source.value}", vals).checkpoint)
                world = _api("projection").project_world(o.declaration, authorities)
                r = _admit(world, o.propose("pulse", PULSE, world=world), authorities)
                assert r.verification.ok and r.admitted is None and r.status is F.MISSING_INFORMATION, (lo, level, source)
                assert "PRECONDITION_ENCLOSURE_REQUIRED" in _codes(r) and not r.feasibility_verdicts()


def test_a_a_declared_set_point_is_never_exact_by_default_so_unknown_never_improves_the_answer():
    """Round-1 MAJOR A-F2: with the model reading the DECLARED ambient set point (25 degC), UNKNOWN realization
    uncertainty gave FEASIBLE while a stated 0.2 K uncertainty refused.  Now UNKNOWN, STANDARD and an interval at any
    coverage all give the same MISSING_INFORMATION; the protocol level decides exactly only when the action declares it
    as its fixed condition."""
    w = br1.battery_world()
    spec = w.action("simulate_pulse")
    reads_declared = dataclasses.replace(spec, controls=tuple(c for c in spec.controls if c.variable != "T_amb"))
    base = w.derive(reason="the model reads the declared ambient", actions=tuple(
        reads_declared if a is spec else a for a in w.actions))
    proposal = {"I": br1.q(2.0, "A"), "t_pulse": br1.q(60, "s")}
    outcomes = set()
    for u in (Uncertainty.unknown("chamber realization not characterized"),
              Uncertainty(kind="standard", standard_uncertainty=br1.q(0.2, "delta_degC"), method="stated"),
              Uncertainty(kind="interval", lower=br1.q(24.5, "degC"), upper=br1.q(25.5, "degC"),
                          confidence_level=0.95, method="stated")):
        world = base.derive(reason=f"ambient realization {u.kind.value}", variables=tuple(
            dataclasses.replace(v, uncertainty=u) if v.name == "T_amb" else v for v in base.variables))
        d = FeasibleActionSpace.build(world).check(br1.propose(world, "simulate_pulse", proposal))
        assert d.status is F.MISSING_INFORMATION and "APPLICABILITY_INPUT_NOT_EXACT" in _codes(d), u.kind
        assert not d.feasibility_verdicts() and all(r.status is F.MISSING_INFORMATION for r in d.reasons)
        outcomes.add(d.status)
    assert outcomes == {F.MISSING_INFORMATION}                      # monotone: stating an uncertainty changes nothing
    fixed = dataclasses.replace(reads_declared, fixed_conditions=reads_declared.fixed_conditions + (
        br1.fixed("T_amb", br1.q(25, "degC")),))
    exact = base.derive(reason="the protocol fixes the ambient for this action", actions=tuple(
        fixed if a.action_id == "simulate_pulse" else a for a in base.actions))
    assert FeasibleActionSpace.build(exact).check(br1.propose(exact, "simulate_pulse", proposal)).status is F.FEASIBLE


# ---- B. lineage laundering ---------------------------------------------------------------------------------------------
def test_b_br1_unbind_then_rebind_of_the_same_reference_is_refused():
    """BR1 reproduced: SOC unbound, then re-bound to the same reference with 0.05; the lineage verified."""
    w = br1.battery_world()
    ref = w.variable("SOC").source
    w1 = w.derive(reason="withdrawn", variables=_soc(w, value=None, origin=None, source=None,
                                                     uncertainty=Uncertainty.unknown("withdrawn")))
    with pytest.raises(WorldRefused):
        w2 = w1.derive(reason="re-bound", variables=_soc(w1, value=br1.q(0.05, D), origin=ValueOrigin.ESTIMATED,
                                                         source=ref, uncertainty=br1.interval(0.05, 0.02, D)))
        verify_lineage(w2, {x.revision_id: x for x in (w, w1, w2)})


def test_b_an_owner_record_never_carries_two_values(ax):
    o = ax.owned("battery")
    w = o.world
    soc = w.variable("SOC")
    with pytest.raises(WorldRefused):
        w.derive(reason="hand edit", variables=_soc(w, value=br1.q(0.05, D)))
    # a forger who also restates the binding's projection: same owner record, another value
    low = ax.covered(br1.q(0.04, D), br1.q(0.06, D))
    rebound = dataclasses.replace(soc.source, projection=_api("authority").projection_digest(
        _api("variables").value_projection(br1.q(0.05, D), low)))
    with pytest.raises(WorldRefused):
        w.derive(reason="re-bound", variables=_soc(w, value=br1.q(0.05, D), uncertainty=low, source=rebound))
    forged = dataclasses.replace(w, variables=_soc(w, value=br1.q(0.05, D), uncertainty=low, source=rebound))
    r = _admit(forged, o.propose("pulse", PULSE, world=forged), o.authorities())
    assert r.admitted is None and r.status is F.MISSING_INFORMATION and "AUTHORITY_MISMATCH" in _codes(r)
    with pytest.raises(WorldRefused):
        verify_lineage(dataclasses.replace(forged, lineage=type(w.lineage)(1, w.revision_id, "re-bound", ("variables",))),
                       {w.revision_id: w})
    assert soc.source is not None and soc.source.record_digest == o.run.checkpoint.state.digest


# ---- C. missing owner --------------------------------------------------------------------------------------------------
def test_c_a_binding_to_a_record_no_owner_holds_never_admits(ax):
    o = ax.owned("battery")
    w = o.world
    ghost = dataclasses.replace(w.variable("SOC").source, record_digest=ax.sha("no such state"))
    forged = dataclasses.replace(w, variables=_soc(w, source=ghost))
    r = _admit(forged, o.propose("pulse", PULSE, world=forged), o.authorities())
    assert r.status is F.MISSING_INFORMATION and r.admitted is None
    assert "AUTHORITY_MISSING" in _codes(r)


# ---- D-H. stale owners ---------------------------------------------------------------------------------------------------
def test_d_a_stale_state_binding_refuses(ax):
    o = ax.owned("battery")
    r = _admit(o.world, o.propose("pulse", PULSE), o.authorities(state=o.run.result))
    assert r.status is F.MISSING_INFORMATION and r.admitted is None and "AUTHORITY_STALE" in _codes(r)


def test_e_a_stale_applicability_binding_refuses(ax):
    o = ax.owned("battery")
    sim = ax.base("battery")["simulate_pulse"]
    route = o.models.list()[0]
    narrowed = br1.route_model(route.model_id, route.version, "T_amb", "degC", 0, 40).model
    registry = ax.ModelRegistry((narrowed,))
    r = _admit(o.world, o.propose("simulate_pulse", *sim), o.authorities(models=registry))
    assert r.admitted is None and r.status is F.MISSING_INFORMATION and "AUTHORITY_STALE" in _codes(r)
    empty = _admit(o.world, o.propose("simulate_pulse", *sim), o.authorities(models=ax.ModelRegistry(())))
    assert empty.admitted is None and "AUTHORITY_MISSING" in _codes(empty)


def test_f_a_stale_provider_binding_refuses(ax):
    o = ax.owned("battery")
    sim = ax.base("battery")["simulate_pulse"]
    assert o.world.provider("sim.ecm").executable                 # the world's copy still says available
    r = _admit(o.world, o.propose("simulate_pulse", *sim), o.authorities(providers=ax.provider_registry(o, down=("sim.ecm",))))
    assert r.admitted is None and r.status is F.MISSING_INFORMATION and "AUTHORITY_STALE" in _codes(r)


def test_g_a_stale_protocol_declaration_refuses(ax):
    o = ax.owned("battery")
    revised = dataclasses.replace(o.declaration, revision=2, basis=o.declaration.basis + " (revised)")
    r = _admit(o.world, o.propose("pulse", PULSE), o.authorities(declarations=(revised,)))
    assert r.admitted is None and r.status is F.MISSING_INFORMATION and "AUTHORITY_STALE" in _codes(r)


def test_h_a_stale_budget_binding_refuses_and_the_ledger_states_its_identity(ax):
    o = ax.owned("battery")
    led = o.ledgers["synthetic.battery.pulse-cell.solver"]
    before = (led.digest, led.revision)
    w = o.world
    led.settle(charge_id="later", action_id="other", iteration=1, family=ax.ActionFamily.EXPLORE, realized=1.0)
    assert (led.digest, led.revision) != before and led.revision == before[1] + 1
    r = _admit(w, o.propose("pulse", PULSE, world=w), o.authorities())
    assert r.admitted is None and r.status is F.MISSING_INFORMATION and "AUTHORITY_STALE" in _codes(r)


# ---- I. units ------------------------------------------------------------------------------------------------------------
def test_i_a_unit_spelling_never_changes_a_decision(ax):
    def spelled(unit):
        base = br1.battery_world()
        v = base.variable("I")
        if v.declaration.unit == unit:
            return ax.owned("battery", base)
        decl = dataclasses.replace(v.declaration, unit=unit)
        return ax.owned("battery", base.derive(reason="respelled", variables=tuple(
            dataclasses.replace(x, declaration=decl) if x.name == "I" else x for x in base.variables)))
    for assignments in (PULSE, {"I": br1.q(1.15, "A"), "t_pulse": br1.q(60, "s")}, {"I": br1.q(2, "s"), "t_pulse": br1.q(60, "s")}):
        a, b = spelled("A"), spelled("ampere")
        ra, rb = (_admit(x.world, x.propose("pulse", assignments), x.authorities()) for x in (a, b))
        assert ra.status is rb.status and _codes(ra) == _codes(rb)


def test_i_copied_unit_text_cannot_change_the_projected_value(ax):
    o = ax.owned("battery")
    payload = copy.deepcopy(o.world.to_dict())
    for v in payload["variables"]:
        if v["name"] == "SOC":
            v["value"]["units"] = "percent"                         # 0.8 dimensionless -> 0.8 percent
    try:
        tampered = type(o.world).from_dict(payload)
    except (WorldRefused, ValueError, KeyError):
        return
    r = _admit(tampered, o.propose("pulse", PULSE, world=tampered), o.authorities())
    assert r.admitted is None and r.status is F.MISSING_INFORMATION


def test_i_the_world_binds_the_unit_registry_it_was_projected_under(ax):
    authority = _api("authority")
    kinds = {b.owner_kind for b in ax.owned("battery").world.authority_bindings()}
    assert authority.OwnerKind.UNIT_REGISTRY in kinds


def test_i_r4_a_temperature_difference_never_bridges_into_a_point_through_kelvin():
    """BR1 round-2 MAJOR: hop-wise conversion through kelvin admitted a difference for a point variable."""
    from engcore.mind.world.base import converts
    from engcore.mind.world.domains import DiscreteLevels, membership
    assert not converts(br1.q(5, "delta_degC"), "kelvin") and not converts(br1.q(5, "kelvin"), "delta_degC")
    assert converts(br1.q(25, "degC"), "kelvin") and converts(br1.q(5, "delta_degC"), "delta_degF")
    found = membership(DiscreteLevels("kelvin", (br1.q(300, "kelvin"),)), br1.q(300, "delta_degC"))
    assert found is not None and found[0] == "UNIT_INCOMPATIBLE"


def test_r5_the_variables_own_domain_is_checked_pointwise_at_every_check(monkeypatch):
    """BR1 round-2 MAJOR: the world's containment rule stood in for the owner's pointwise check."""
    from engcore.mind.world import actions as actions_mod
    w = br1.battery_world()
    wide = dataclasses.replace(w.action("pulse"), controls=tuple(
        dataclasses.replace(c, domain=br1.crange("t_pulse", "s", 10, 7200)) if c.variable == "t_pulse" else c
        for c in w.action("pulse").controls))
    monkeypatch.setattr(actions_mod, "contained", lambda inner, outer: True)       # a containment rule that errs
    widened = w.derive(reason="an action domain wider than its variable's", actions=tuple(
        wide if a.action_id == "pulse" else a for a in w.actions))
    d = FeasibleActionSpace.build(widened).check(br1.propose(widened, "pulse", {"I": br1.q(1, "A"),
                                                                                 "t_pulse": br1.q(5000, "s")}))
    assert d.status is not F.FEASIBLE and "OUTSIDE_RANGE" in {r.code for r in d.reasons}


def test_r6_names_and_values_are_rebuilt_as_exact_builtin_types():
    """BR1 round-2 MAJOR: a str-subclass variable name survived canonical()."""
    from engcore.mind.world.feasibility import canonical

    class Sly(str):
        def __eq__(self, other):
            return True

        __hash__ = str.__hash__

    w = br1.battery_world()
    try:
        c = canonical(br1.propose(w, "pulse", {Sly("I"): br1.q(1.0, "A"), "t_pulse": br1.q(60, "s")}))
    except WorldRefused:
        return
    assert all(type(n) is str for n, _ in c.assignments) and type(c.action_id) is str


# ---- J-L. the admission boundary -------------------------------------------------------------------------------------------
def test_j_a_raw_proposal_never_reaches_an_executor(ax):
    admission = _api("admission")
    o = ax.owned("battery")
    calls = []
    desk = admission.ExecutionDesk(o.authorities(), calls.append)
    proposal = o.propose("pulse", PULSE)
    with pytest.raises((admission.DispatchRefused, TypeError)):
        desk.dispatch(proposal)
    assert calls == []


def test_k_a_proposer_cannot_mint_an_admitted_action(ax):
    admission = _api("admission")
    o = ax.owned("battery")
    good = _admit(o.world, o.propose("simulate_pulse", *SIM), o.authorities())
    assert good.admitted is not None
    with pytest.raises((WorldRefused, TypeError)):
        admission.AdmittedAction(**{f.name: getattr(good.admitted, f.name) for f in dataclasses.fields(good.admitted)})
    bad = o.propose("pulse", {"I": br1.q(1.15, "A"), "t_pulse": br1.q(60, "s")})
    forged = object.__new__(admission.AdmittedAction)
    for f in dataclasses.fields(good.admitted):
        object.__setattr__(forged, f.name, getattr(good.admitted, f.name))
    object.__setattr__(forged, "proposal", bad)
    calls = []
    desk = admission.ExecutionDesk(o.authorities(), calls.append)
    with pytest.raises(admission.DispatchRefused):
        desk.dispatch(forged)
    assert calls == []


def test_k_a_suggestion_cannot_carry_admission_or_binding_authority(ax):
    from engcore.mind.world import IntakeRefusal, proposed_action_from_suggestion
    from engcore.scientific.ir.values import encode_value
    from engcore.sria.decision.external import ExternalSuggestion
    from engcore.sria.decision.hypotheses import ProposerKind
    o = ax.owned("battery")
    point = {"assignments": [{"variable": k, "value": encode_value(v)} for k, v in PULSE.items()]}
    from engcore.sria.decision.external import SuggestionRefused
    for extra_key in ("admitted", "authority_binding", "bindings", "admission", "feasible", "record_digest"):
        for where in ("point", "extra"):
            try:
                s = ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", ax.ActionFamily.CHARACTERIZE, "pulse",
                                       {**point, extra_key: True} if where == "point" else point, "r", None,
                                       {"world_revision": o.world.revision_id,
                                        **({extra_key: True} if where == "extra" else {})})
            except SuggestionRefused:
                continue                                   # refused at the certified suggestion boundary itself
            assert isinstance(proposed_action_from_suggestion(s, world=o.world), IntakeRefusal), (extra_key, where)


def test_l_an_admitted_action_is_refused_at_dispatch_once_its_authority_moved(ax):
    admission = _api("admission")
    o = ax.owned("battery")
    calls = []
    desk = admission.ExecutionDesk(o.authorities(), calls.append, accept_synthetic=True)
    result = desk.admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM))
    assert result.admitted is not None
    o.ledgers["synthetic.battery.pulse-cell.solver"].settle(charge_id="elsewhere", action_id="other", iteration=1,
                                                             family=ax.ActionFamily.EXPLORE, realized=1.0)
    with pytest.raises(admission.DispatchRefused, match="AUTHORITY_STALE"):
        desk.dispatch(result.admitted)
    fresh = ax.owned("battery")
    again = _admit(fresh.world, fresh.propose("simulate_pulse", *SIM), fresh.authorities())
    moved = admission.ExecutionDesk(fresh.authorities(state=fresh.run.result), calls.append, accept_synthetic=True)
    with pytest.raises(admission.DispatchRefused, match="AUTHORITY_STALE"):
        moved.dispatch(again.admitted)
    assert calls == []


def test_l_the_desk_is_not_an_effect_ledger_and_a_moved_run_head_refuses_the_next_dispatch(ax):
    """Round-1 MAJOR B1: the desk's state reader follows the execution side's run head.  While no bound owner moves,
    the same admitted action is authorized again (the desk records no effects: at-most-once execution is the execution
    owner's); once the executor advances the run, the same admitted action no longer re-admits."""
    admission = _api("admission")
    o = ax.owned("battery")
    calls = []
    desk = admission.ExecutionDesk(o.authorities(), calls.append, accept_synthetic=True)   # a synthetic test executor
    result = desk.admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM))
    desk.dispatch(result.admitted)
    desk.dispatch(result.admitted)
    assert len(calls) == 2 and all(isinstance(c, admission.DispatchAuthorization) for c in calls)
    assert {c.admitted_digest for c in calls} == {result.admitted.digest}
    o.advance()                                                      # the run moved on: the same run, a later head
    with pytest.raises(admission.DispatchRefused, match="AUTHORITY_STALE"):
        desk.dispatch(result.admitted)
    assert len(calls) == 2
    p = ax.owned("battery")                                          # an executor that moves the head itself
    seen = []
    moving = admission.ExecutionDesk(p.authorities(), lambda auth: (seen.append(auth), p.advance()),
                                     accept_synthetic=True)
    admitted = moving.admit(FeasibleActionSpace.build(p.world), p.propose("simulate_pulse", *SIM)).admitted
    moving.dispatch(admitted)
    with pytest.raises(admission.DispatchRefused):
        moving.dispatch(admitted)
    assert len(seen) == 1


# ---- M. replay -----------------------------------------------------------------------------------------------------------------
def test_m_historical_replay_is_exact_and_stale_dispatch_is_refused(ax):
    admission = _api("admission")
    from engcore.sria.decision.replay import ReplayOutcome
    o = ax.owned("battery")
    result = _admit(o.world, o.propose("simulate_pulse", *SIM), o.authorities())
    assert result.admitted is not None
    record = admission.AdmissionRecord.of(result, o.authorities())
    o.ledgers["synthetic.battery.pulse-cell.solver"].settle(charge_id="moved", action_id="other", iteration=2,
                                                             family=ax.ActionFamily.EXPLORE, realized=1.0)
    replayed = admission.replay_admission(record.to_dict())
    assert replayed.outcome is ReplayOutcome.REPRODUCED
    with pytest.raises(admission.DispatchRefused, match="AUTHORITY_STALE"):
        admission.authorize_dispatch(result.admitted, o.authorities(), accept_synthetic=True)


# ---- N-O. BR1 behaviour survives ----------------------------------------------------------------------------------------------
#: BR1 base proposals that read a current value of the world for a containment: a state precondition (the battery
#: pulses read SOC, the HVAC speed step the room temperature, the drone tests the velocity, the motor load step the
#: winding temperature) or a model input (brief section 10).  No current value is exact (no core uncertainty record is
#: an enclosure), so these are MISSING_INFORMATION with exactly those reasons; every other BR1 base proposal is admitted.
READS_CURRENT_VALUE = {
    ("battery", "pulse"): {"PRECONDITION_ENCLOSURE_REQUIRED", "STATE_DOMAIN_ENCLOSURE_REQUIRED"},
    ("battery", "signed_pulse"): {"PRECONDITION_ENCLOSURE_REQUIRED", "STATE_DOMAIN_ENCLOSURE_REQUIRED"},
    ("hvac_chamber", "step_speed"): {"PRECONDITION_ENCLOSURE_REQUIRED"},
    ("hvac_field", "step_speed"): {"PRECONDITION_ENCLOSURE_REQUIRED"},
    ("hvac_field", "simulate_building"): {"APPLICABILITY_INPUT_NOT_EXACT"},
    ("drone", "hover_test"): {"PRECONDITION_ENCLOSURE_REQUIRED"},
    ("drone", "climb_test"): {"PRECONDITION_ENCLOSURE_REQUIRED"},
    ("drone", "simulate_flight"): {"APPLICABILITY_INPUT_NOT_EXACT"},
    ("motor", "load_step"): {"PRECONDITION_ENCLOSURE_REQUIRED"},
}


@pytest.mark.parametrize("name", ["battery", "hvac_chamber", "hvac_field", "drone", "motor"])
def test_n_the_exact_current_world_admits_every_valid_br1_control(ax, name):
    o = ax.WORLDS[name]()
    admitted = 0
    for action_id, (assignments, observe) in ax.base(name).items():
        r = _admit(o.world, o.propose(action_id, assignments, observe), o.authorities())
        assert r.verification.ok, action_id
        expected = READS_CURRENT_VALUE.get((name, action_id))
        if expected is not None:
            assert r.status is F.MISSING_INFORMATION and r.admitted is None and _codes(r) == expected, \
                (action_id, sorted(_codes(r)))
        else:
            assert r.status is F.FEASIBLE and r.admitted is not None, (action_id, sorted(_codes(r)))
            admitted += 1
    assert admitted >= 1


def test_o_an_off_level_current_stays_refused_with_the_declared_alternatives(ax):
    o = ax.gen1_pool()
    p = o.propose("pool_query", {"I_A": br1.q(1.15, "A"), "t_on_s": br1.q(60, "s")})
    r = _admit(o.world, p, o.authorities())
    assert r.status is F.INFEASIBLE_PROTOCOL and "LEVEL_NOT_DECLARED" in _codes(r) and r.admitted is None
    alt = FeasibleActionSpace.build(o.world).alternatives(p, "I_A")
    assert [x.magnitude for x in alt["options"]] == [1.0, 2.0]
