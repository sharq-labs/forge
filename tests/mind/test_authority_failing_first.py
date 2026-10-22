"""GEN2-BR1.1 failing-first controls: an authority-bound ScientificWorld and non-bypassable action admission.

Written before the repair.  Each test pins one blocker from the GEN2-BR1 review (``benchmarks/mind_gen2_world_v1/
README.md`` section 6) or one BR1.1 brief control (section 21, A-O).  The authority-bound fixtures
(``benchmarks/mind_gen2_authority_v1/fixtures.py``) read every projected fact from a real owner record; they are
imported per test so that this module collects on the unrepaired tree and every control fails on its own.

A. a 10 %-coverage interval cannot prove hard-domain containment
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
L. an admitted action becomes unusable when material authority changes before dispatch
M. replay of a historical admission is exact even after the owners moved on; dispatching it now is refused
N. the exact current verified world still admits every valid BR1 control
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


def test_a_without_a_declared_guard_band_a_95_percent_interval_proves_nothing(ax):
    o = ax.owned("battery")
    assert _admit(o.world, o.propose("pulse", PULSE), o.authorities()).status is F.FEASIBLE   # guard band 0.95 declared
    hard = ax.owned("battery")
    hard.declaration = dataclasses.replace(hard.declaration, variables=tuple(
        dataclasses.replace(v, guard_band=None) if v.name == "SOC" else v for v in hard.declaration.variables))
    r = _admit(hard.world, hard.propose("pulse", PULSE), hard.authorities())
    assert r.status is F.MISSING_INFORMATION and r.admitted is None


def test_a_coverage_below_the_guard_band_is_missing_information(ax):
    o = ax.owned("battery")
    vals = {"cell": ("component", {"SOC": (br1.q(0.11, D), Uncertainty(
        kind="interval", lower=br1.q(0.105, D), upper=br1.q(0.115, D), confidence_level=0.10, method="10 %")),
        "R0": (br1.q(0.012, "ohm"), Uncertainty.unknown("not quantified"))})}
    run = ax.run_state("battery.low-coverage", vals)
    authorities = o.authorities(state=run.checkpoint)
    world = _api("projection").project_world(o.declaration, authorities)
    r = _admit(world, o.propose("pulse", PULSE, world=world), authorities)
    assert r.status is F.MISSING_INFORMATION and r.admitted is None
    assert any("COVERAGE" in c or "GUARD_BAND" in c for c in _codes(r))


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
    forged = dataclasses.replace(w, variables=_soc(w, value=br1.q(0.05, D)))      # bypassing derive entirely
    r = _admit(forged, o.propose("pulse", PULSE, world=forged), o.authorities())
    assert r.admitted is None and r.status is F.MISSING_INFORMATION
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
    good = _admit(o.world, o.propose("pulse", PULSE), o.authorities())
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
    for extra_key in ("admitted", "authority_binding", "bindings", "admission"):
        s = ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", ax.ActionFamily.CHARACTERIZE, "pulse",
                               {**point, extra_key: True}, "r", None, {"world_revision": o.world.revision_id})
        assert isinstance(proposed_action_from_suggestion(s, world=o.world), IntakeRefusal), extra_key


def test_l_an_admitted_action_is_refused_at_dispatch_once_its_authority_moved(ax):
    admission = _api("admission")
    o = ax.owned("battery")
    calls = []
    desk = admission.ExecutionDesk(o.authorities(), calls.append)
    result = desk.admit(FeasibleActionSpace.build(o.world), o.propose("pulse", PULSE))
    assert result.admitted is not None
    o.ledgers["synthetic.battery.pulse-cell.solver"].settle(charge_id="elsewhere", action_id="other", iteration=1,
                                                             family=ax.ActionFamily.EXPLORE, realized=1.0)
    with pytest.raises(admission.DispatchRefused):
        desk.dispatch(result.admitted)
    moved = admission.ExecutionDesk(o.authorities(state=o.run.result), calls.append)
    with pytest.raises(admission.DispatchRefused):
        moved.dispatch(result.admitted)
    assert calls == []


def test_l_a_current_admitted_action_reaches_the_executor_exactly_once_per_authority_state(ax):
    admission = _api("admission")
    o = ax.owned("battery")
    calls = []
    desk = admission.ExecutionDesk(o.authorities(), calls.append)
    result = desk.admit(FeasibleActionSpace.build(o.world), o.propose("pulse", PULSE))
    desk.dispatch(result.admitted)
    assert len(calls) == 1 and isinstance(calls[0], admission.DispatchAuthorization)
    assert calls[0].admitted_digest == result.admitted.digest


# ---- M. replay -----------------------------------------------------------------------------------------------------------------
def test_m_historical_replay_is_exact_and_stale_dispatch_is_refused(ax):
    admission = _api("admission")
    from engcore.sria.decision.replay import ReplayOutcome
    o = ax.owned("battery")
    result = _admit(o.world, o.propose("pulse", PULSE), o.authorities())
    record = admission.AdmissionRecord.of(result, o.authorities())
    o.ledgers["synthetic.battery.pulse-cell.solver"].settle(charge_id="moved", action_id="other", iteration=2,
                                                             family=ax.ActionFamily.EXPLORE, realized=1.0)
    replayed = admission.replay_admission(record.to_dict())
    assert replayed.outcome is ReplayOutcome.REPRODUCED
    with pytest.raises(admission.DispatchRefused):
        admission.authorize_dispatch(result.admitted, o.authorities())


# ---- N-O. BR1 behaviour survives ----------------------------------------------------------------------------------------------
#: Actions whose model applicability reads a value known only within an interval: the core assesses points only, so
#: admission fails closed (brief section 10).  Every other BR1 base proposal must still be admitted.
NOT_EXACT = {("hvac_field", "simulate_building"), ("drone", "simulate_flight")}


@pytest.mark.parametrize("name", ["battery", "hvac_chamber", "hvac_field", "drone", "motor"])
def test_n_the_exact_current_world_admits_every_valid_br1_control(ax, name):
    o = ax.WORLDS[name]()
    for action_id, (assignments, observe) in ax.base(name).items():
        r = _admit(o.world, o.propose(action_id, assignments, observe), o.authorities())
        if (name, action_id) in NOT_EXACT:
            assert r.status is F.MISSING_INFORMATION and "APPLICABILITY_INPUT_NOT_EXACT" in _codes(r), action_id
        else:
            assert r.status is F.FEASIBLE and r.admitted is not None, (action_id, sorted(_codes(r)))


def test_o_an_off_level_current_stays_refused_with_the_declared_alternatives(ax):
    o = ax.gen1_pool()
    p = o.propose("pool_query", {"I_A": br1.q(1.15, "A"), "t_on_s": br1.q(60, "s")})
    r = _admit(o.world, p, o.authorities())
    assert r.status is F.INFEASIBLE_PROTOCOL and "LEVEL_NOT_DECLARED" in _codes(r) and r.admitted is None
    alt = FeasibleActionSpace.build(o.world).alternatives(p, "I_A")
    assert [x.magnitude for x in alt["options"]] == [1.0, 2.0]
