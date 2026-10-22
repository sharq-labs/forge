"""GEN2-BR1 failing-first tests: ScientificWorld + FeasibleActionSpace v1 on synthetic contract fixtures.

Written before ``engcore.mind.world`` existed.  Each test pins one required behaviour of the BR1 brief (section 13,
cases A-M) or one role-semantics invariant (section 3).  Fixtures are synthetic contract worlds
(``benchmarks/mind_gen2_world_v1/fixtures.py``); no battery v1/v2/v3 data, answer or truth is read.

A. discrete current {1 A, 2 A}: 1.15 A is INFEASIBLE_PROTOCOL, never clamped
B. fixed temperature 25 degC: proposing 30 degC is INFEASIBLE_PROTOCOL
C. SOC (STATE_VARIABLE) cannot be set directly; only an explicit state intervention may set it
D. terminal voltage (MEASUREMENT) cannot be a control
E. R1 (LATENT_PARAMETER) is never an observed measurement
F. a current stated in seconds is rejected before any execution
G. a continuous value outside its range is rejected
H. an action that needs an unavailable provider is rejected
I. an action costing 2 solver calls with 1 remaining is rejected
J. a control valid in one protocol mode is invalid in another
K. a changed budget produces a different WORLD_REVISION
L. identical world + proposal give a byte-identical decision, and replay reproduces it
M. no role / domain / protocol information is guessed from a name
"""

from __future__ import annotations

import dataclasses

import pytest

from benchmarks.mind_gen2_authority_v1 import synthetic as fx
from engcore.mind.repsem import canonical_bytes
from engcore.mind.repsem.roles import RoleDeclaration, RoleSource, VariableRole as R, legacy_role_table
from engcore.mind.world import (
    ActionMode, Controllability, FeasibilityStatus as F, FeasibleActionSpace, Observability, ProposedAction,
    ScientificWorld, StaleProposal, TemporalSemantics, ValueOrigin, WorldBudget, WorldRefused, WorldVariable,
    replay_decision,
)
from engcore.scientific import ExperimentBudget
from engcore.sria.decision.replay import ReplayOutcome


def check(world: ScientificWorld, action_id: str, assignments, observe=()):
    return FeasibleActionSpace.build(world).check(fx.propose(world, action_id, assignments, observe))


def codes(decision) -> set[str]:
    return {r.code for r in decision.reasons}


PULSE_OK = {"I": fx.q(1.0, "A"), "t_pulse": fx.q(60, "s")}


@pytest.fixture(scope="module")
def battery() -> ScientificWorld:
    return fx.battery_world()


# ---- A. discrete levels -------------------------------------------------------------------------------------------------
def test_a_off_level_current_is_infeasible_protocol_and_not_clamped(battery):
    d = check(battery, "pulse", {"I": fx.q(1.15, "A"), "t_pulse": fx.q(60, "s")})
    assert d.status is F.INFEASIBLE_PROTOCOL and "LEVEL_NOT_DECLARED" in codes(d)
    reason = next(r for r in d.reasons if r.code == "LEVEL_NOT_DECLARED")
    assert reason.subject == "I" and reason.detail["proposed"]["magnitude"] == 1.15
    assert len(reason.detail["declared_levels"]) == 2
    text = str(canonical_bytes(d.to_dict())).lower()
    assert "nearest" not in text and "clamp" not in text


def test_a_declared_levels_are_feasible_in_any_unit_spelling(battery):
    assert check(battery, "pulse", PULSE_OK).status is F.FEASIBLE
    assert check(battery, "pulse", {"I": fx.q(2000, "mA"), "t_pulse": fx.q(1, "min")}).status is F.FEASIBLE


# ---- B. fixed protocol condition ----------------------------------------------------------------------------------------
def test_b_changing_a_fixed_condition_is_infeasible_protocol(battery):
    d = check(battery, "pulse", {**PULSE_OK, "T_amb": fx.q(30, "degC")})
    assert d.status is F.INFEASIBLE_PROTOCOL and "FIXED_CONDITION_CHANGED" in codes(d)


def test_b_restating_a_fixed_condition_in_another_unit_is_not_a_change(battery):
    assert check(battery, "pulse", {**PULSE_OK, "T_amb": fx.q(298.15, "K")}).status is F.FEASIBLE
    assert check(battery, "pulse", {**PULSE_OK, "T_amb": fx.q(77, "degF")}).status is F.FEASIBLE


# ---- C. state vs control ------------------------------------------------------------------------------------------------
def test_c_soc_cannot_be_set_by_an_ordinary_action(battery):
    d = check(battery, "pulse", {**PULSE_OK, "SOC": fx.q(0.5, "dimensionless")})
    assert d.status is F.INFEASIBLE_STATE and "STATE_NOT_DIRECTLY_SETTABLE" in codes(d)


def test_c_only_a_separate_explicit_state_intervention_sets_soc(battery):
    assert check(battery, "precondition_to_soc", {"SOC": fx.q(0.5, "dimensionless")}).status is F.FEASIBLE
    with pytest.raises(WorldRefused, match="STATE_VARIABLE"):
        fx.action("bad", fx.ActionFamily.EXPLORE, ActionMode.INTERVENE,
                  controls=(fx.ctrl("SOC", fx.crange("SOC", "dimensionless", 0.1, 0.9), fx.P),)).bind(battery)
    with pytest.raises(WorldRefused, match="separate action"):
        fx.action("mixed", fx.ActionFamily.EXPLORE, ActionMode.INTERVENE,
                  controls=(fx.ctrl("SOC", fx.crange("SOC", "dimensionless", 0.1, 0.9), fx.P, state_intervention=True),
                            fx.ctrl("t_pulse", fx.crange("t_pulse", "s", 10, 600))))


# ---- D. measurement is not a control --------------------------------------------------------------------------------------
def test_d_voltage_is_never_a_control(battery):
    d = check(battery, "pulse", {**PULSE_OK, "V": fx.q(3.7, "V")})
    assert d.status is F.INFEASIBLE_DOMAIN and "ROLE_NOT_CONTROLLABLE" in codes(d)
    with pytest.raises(WorldRefused, match="MEASUREMENT"):
        fx.action("set_v", fx.ActionFamily.EXPLORE, ActionMode.INTERVENE,
                  controls=(fx.ctrl("V", fx.crange("V", "V", 3, 4)),)).bind(battery)


# ---- E. latent parameter is not an observation ----------------------------------------------------------------------------
def test_e_r1_is_not_observable_and_cannot_hold_an_observed_value(battery):
    assert battery.observability("R1") is Observability.NOT_OBSERVABLE
    d = check(battery, "pulse", PULSE_OK, observe=("R1",))
    assert d.status is F.INFEASIBLE_DOMAIN and "LATENT_NOT_OBSERVABLE" in codes(d)
    with pytest.raises(WorldRefused, match="LATENT_PARAMETER"):
        fx.var("R1", R.LATENT_PARAMETER, "ohm", TemporalSemantics.TIME_INVARIANT,
               **fx.bound(fx.q(0.01, "ohm"), ValueOrigin.OBSERVED, "meter/0"))
    with pytest.raises(WorldRefused, match="latent"):
        dataclasses.replace(battery, channels=battery.channels + (fx.channel("R1"),))
    with pytest.raises(WorldRefused, match="LATENT_PARAMETER"):
        fx.action("look", fx.ActionFamily.EXPLORE, ActionMode.OBSERVE, expected_observables=("R1",)).bind(battery)


# ---- F. units --------------------------------------------------------------------------------------------------------------
def test_f_current_in_seconds_is_rejected_as_a_unit_error(battery):
    d = check(battery, "pulse", {"I": fx.q(2, "s"), "t_pulse": fx.q(60, "s")})
    assert d.status is F.INFEASIBLE_DOMAIN and "UNIT_INCOMPATIBLE" in codes(d)


def test_f_a_bare_number_is_never_a_proposal_value(battery):
    with pytest.raises(WorldRefused, match="typed scientific value"):
        fx.propose(battery, "pulse", {"I": 1.0, "t_pulse": fx.q(60, "s")})


# ---- G. continuous range -----------------------------------------------------------------------------------------------------
def test_g_continuous_value_outside_its_range_is_rejected(battery):
    d = check(battery, "pulse", {"I": fx.q(1.0, "A"), "t_pulse": fx.q(900, "s")})
    assert d.status is F.INFEASIBLE_DOMAIN and "OUTSIDE_RANGE" in codes(d)
    assert check(battery, "pulse", {"I": fx.q(1.0, "A"), "t_pulse": fx.q(10, "min")}).status is F.FEASIBLE  # = bound


# ---- H. provider ---------------------------------------------------------------------------------------------------------------
def test_h_unavailable_provider_is_rejected(battery):
    sim = fx.base("battery")["simulate_pulse"]
    down = battery.derive(reason="provider went down", providers=(fx.provider("sim.ecm", "1.0", available=False),))
    d = check(down, "simulate_pulse", *sim)
    assert d.status is F.INFEASIBLE_PROVIDER and "PROVIDER_UNAVAILABLE" in codes(d)
    gone = battery.derive(reason="provider removed", providers=())
    assert check(gone, "simulate_pulse", *sim).status is F.INFEASIBLE_PROVIDER
    other = battery.derive(reason="provider upgraded", providers=(fx.provider("sim.ecm", "2.0"),))
    assert "PROVIDER_VERSION_MISMATCH" in codes(check(other, "simulate_pulse", *sim))


# ---- I. budget -----------------------------------------------------------------------------------------------------------------
def test_i_two_solver_calls_with_one_remaining_is_rejected(battery):
    tight = battery.derive(reason="nine of ten solver calls spent", budget=fx.budget(20, 3, solver=(10, 9), ledger="b"))
    d = check(tight, "simulate_pulse", *fx.base("battery")["simulate_pulse"])
    assert d.status is F.INFEASIBLE_BUDGET and "OVER_BUDGET" in codes(d)
    reason = next(r for r in d.reasons if r.code == "OVER_BUDGET")
    assert (reason.subject, reason.detail["requested"], reason.detail["remaining"]) == ("solver_calls", 2, 1)


# ---- J. conditional (mode-dependent) constraint -----------------------------------------------------------------------------
def test_j_a_current_valid_in_charge_mode_is_invalid_in_discharge_mode(battery):
    ok = check(battery, "signed_pulse", {"mode": fx.cat("charge"), "I": fx.q(2, "A"), "t_pulse": fx.q(30, "s")})
    bad = check(battery, "signed_pulse", {"mode": fx.cat("discharge"), "I": fx.q(2, "A"), "t_pulse": fx.q(30, "s")})
    assert ok.status is F.FEASIBLE
    assert bad.status is F.INFEASIBLE_PROTOCOL and "CONSTRAINT_VIOLATED" in codes(bad)


# ---- K. revisions ---------------------------------------------------------------------------------------------------------------
def test_k_changed_budget_makes_a_new_revision_and_the_old_one_is_untouched(battery):
    before = canonical_bytes(battery.to_dict())
    spent = fx.budget(20, 4, solver=(10, 4), ledger="battery/2")
    child = battery.derive(reason="one experiment consumed", budget=spent)
    assert child.revision_id != battery.revision_id
    assert (child.lineage.parent, child.lineage.revision, child.lineage.changed_fields) == (battery.revision_id, 1, ("budget",))
    assert battery.derive(reason="a different narrative", budget=spent).revision_id == child.revision_id
    assert canonical_bytes(battery.to_dict()) == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        battery.budget = spent  # type: ignore[misc]
    with pytest.raises(WorldRefused, match="no material change"):
        battery.derive(reason="nothing", budget=battery.budget)


# ---- L. replay -------------------------------------------------------------------------------------------------------------------
def test_l_identical_world_and_proposal_give_byte_identical_decisions():
    a, b = fx.battery_world(), fx.battery_world()
    assignments = {"I": fx.q(1.15, "A"), "t_pulse": fx.q(60, "s")}
    da, db = check(a, "pulse", assignments), check(b, "pulse", assignments)
    assert canonical_bytes(da.to_dict()) == canonical_bytes(db.to_dict())
    result = replay_decision(da.to_dict(), a.to_dict(), fx.propose(a, "pulse", assignments).to_dict())
    assert result.outcome is ReplayOutcome.REPRODUCED


# ---- M. nothing guessed from a name ------------------------------------------------------------------------------------------------
def test_m_an_undeclared_name_is_never_mapped_to_a_declared_one(battery):
    d = check(battery, "pulse", {"current": fx.q(1.0, "A"), "t_pulse": fx.q(60, "s")})
    assert d.status is F.MISSING_INFORMATION and {"UNDECLARED_VARIABLE", "CONTROL_NOT_SUPPLIED"} <= codes(d)


def test_m_the_same_name_behaves_by_its_declared_role():
    chamber, field = fx.hvac_world("chamber"), fx.hvac_world("field")
    assert chamber.role("T_out") is R.FIXED_PROTOCOL_CONDITION and field.role("T_out") is R.NUISANCE_VARIABLE
    assert chamber.controllability("T_out") is Controllability.PROTOCOL_SELECTABLE
    assert field.controllability("T_out") is Controllability.NOT_CONTROLLABLE
    assert field.observability("T_out") is Observability.OBSERVED_CHANNEL
    assert chamber.observability("T_out") is Observability.NO_CHANNEL


def test_m_decisions_do_not_depend_on_what_names_say(battery):
    # an adversarial permutation: the latent is called 'V', the measurement 'R1', the current 'SOC', the state 'I'
    swap = {"R1": "V", "V": "R1", "I": "SOC", "SOC": "I", "pulse": "precondition_to_soc", "precondition_to_soc": "pulse"}
    n = lambda s: swap.get(s, s)  # noqa: E731
    renamed = fx.battery_world(n)
    for assignments, observe in ((PULSE_OK, ("V",)), ({"I": fx.q(1.15, "A"), "t_pulse": fx.q(60, "s")}, ("R1",)),
                                 ({**PULSE_OK, "SOC": fx.q(0.5, "dimensionless")}, ())):
        plain = check(battery, "pulse", assignments, observe)
        other = check(renamed, n("pulse"), {n(k): v for k, v in assignments.items()}, tuple(n(o) for o in observe))
        assert plain.status is other.status
        assert sorted((r.code, n(r.subject)) for r in plain.reasons) == sorted((r.code, r.subject) for r in other.reasons)


def test_m_missing_declarations_are_refused_not_defaulted():
    decl = RoleDeclaration("x", R.MEASUREMENT, "V", RoleSource.PROBLEM_SPECIFICATION, "spec")
    with pytest.raises(WorldRefused, match="temporal"):
        WorldVariable(decl, None)  # type: ignore[arg-type]
    legacy = RoleDeclaration("x", R.MEASUREMENT, "V", RoleSource.LEGACY_ADAPTER_DEFAULT, "v1 adapter")
    with pytest.raises(WorldRefused, match="legacy"):
        WorldVariable(legacy, TemporalSemantics.TIME_SERIES)
    spec = {"clock": "t", "observable": "y", "sets": {"calibration": [{"id": "a", "columns": ["t", "y", "z"]}]}}
    table = legacy_role_table(spec)
    with pytest.raises(WorldRefused, match="legacy"):
        WorldVariable(table.declaration("z"), TemporalSemantics.TIME_SERIES)


# ---- section 3: role semantics invariants --------------------------------------------------------------------------------------------
def test_role_controlled_input_changes_only_through_an_action_that_offers_it(battery):
    d = check(battery, "precondition_to_soc", {"SOC": fx.q(0.5, "dimensionless"), "I": fx.q(1, "A")})
    assert d.status is F.INFEASIBLE_DOMAIN and "CONTROL_NOT_OFFERED_BY_ACTION" in codes(d)
    assert battery.controllability("I") is Controllability.INTERVENABLE


def test_role_fixed_protocol_condition_is_selectable_only_among_protocol_levels(battery):
    with pytest.raises(WorldRefused, match="FIXED_PROTOCOL_CONDITION"):
        fx.action("bad", fx.ActionFamily.EXPLORE, ActionMode.INTERVENE,
                  controls=(fx.ctrl("mode", fx.cats("mode", "charge", "discharge"), fx.S),)).bind(battery)
    assert battery.controllability("mode") is Controllability.PROTOCOL_SELECTABLE
    d = check(battery, "precondition_to_soc", {"SOC": fx.q(0.5, "dimensionless"), "mode": fx.cat("charge")})
    assert d.status is F.INFEASIBLE_PROTOCOL and "PROTOCOL_CONDITION_NOT_SELECTABLE" in codes(d)


def test_role_state_variable_is_state_intervention_only(battery):
    assert battery.controllability("SOC") is Controllability.STATE_INTERVENTION_ONLY
    assert battery.observability("SOC") is Observability.NO_CHANNEL


def test_role_measurement_is_observable_and_not_controllable(battery):
    assert battery.observability("V") is Observability.OBSERVED_CHANNEL
    assert battery.controllability("V") is Controllability.NOT_CONTROLLABLE


def test_role_derived_quantity_is_computed_never_declared_observed_or_controlled(battery):
    assert battery.controllability("P_el") is Controllability.NOT_CONTROLLABLE
    assert battery.observability("P_el") is Observability.DERIVED_ONLY
    with pytest.raises(WorldRefused, match="DERIVED_QUANTITY"):
        fx.var("P_el", R.DERIVED_QUANTITY, "W", TemporalSemantics.TIME_SERIES, derived_from=("I", "V"),
               **fx.declared(fx.q(5, "W")))
    assert "DERIVED_NOT_OBSERVABLE" in codes(check(battery, "pulse", PULSE_OK, observe=("P_el",)))


def test_role_latent_parameter_is_estimated_never_observed(battery):
    assert battery.controllability("R0") is Controllability.NOT_CONTROLLABLE
    assert battery.variable("R0").origin is ValueOrigin.ESTIMATED
    assert "R0" in battery.latent_quantities() and "R0" not in battery.observables()


def test_role_nuisance_is_observable_but_never_an_experiment_control(battery):
    assert battery.observability("T_surf") is Observability.OBSERVED_CHANNEL
    d = check(battery, "pulse", {**PULSE_OK, "T_surf": fx.q(30, "degC")})
    assert d.status is F.INFEASIBLE_DOMAIN and "ROLE_NOT_CONTROLLABLE" in codes(d)


# ---- fail-closed --------------------------------------------------------------------------------------------------------------------
def test_missing_information_is_never_feasible(battery):
    d = check(battery, "pulse", {"I": fx.q(1.0, "A")})                         # t_pulse is never defaulted
    assert d.status is F.MISSING_INFORMATION and "CONTROL_NOT_SUPPLIED" in codes(d)
    blind = battery.derive(reason="SOC estimate withdrawn", variables=tuple(
        dataclasses.replace(v, value=None, origin=None, source=None, uncertainty=fx.Uncertainty.unknown("withdrawn"))
        if v.name == "SOC" else v for v in battery.variables))
    assert check(blind, "pulse", PULSE_OK).status is F.MISSING_INFORMATION


def test_a_proposal_for_another_revision_is_refused(battery):
    child = battery.derive(reason="one experiment consumed", budget=fx.budget(20, 4, solver=(10, 4), ledger="battery/2"))
    with pytest.raises(StaleProposal):
        FeasibleActionSpace.build(child).check(fx.propose(battery, "pulse", PULSE_OK))


def test_budget_counts_are_explicit_and_not_coerced():
    ref = fx.synthetic("ledger/x")
    with pytest.raises(WorldRefused):
        WorldBudget(experiments=5, observations_spent=True, authority=ref)  # type: ignore[arg-type]
    with pytest.raises(WorldRefused):
        WorldBudget(experiments=5, observations_spent=None, authority=ref)
    payload = WorldBudget(experiments=5, observations_spent=0, authority=ref).to_dict()
    payload["experiments"] = ExperimentBudget(5, 7).to_dict()
    with pytest.raises(WorldRefused, match="attempt"):
        WorldBudget.from_dict(payload)


def test_proposed_action_is_bound_to_one_world_revision(battery):
    p = fx.propose(battery, "pulse", PULSE_OK)
    assert isinstance(p, ProposedAction) and p.world_revision == battery.revision_id
    assert ProposedAction.from_dict(p.to_dict()) == p
