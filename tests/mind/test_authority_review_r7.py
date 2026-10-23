"""GEN2-BR1.1 review round 7: one control per confirmed finding (benchmarks/mind_gen2_authority_v1/README.md).

Round 7 found a BLOCKER and MAJORs the round-6 fixes introduced: the nearer-level rule counted another SPELLING of the
matched level as another level, so a spelling of a refuted level was decided and executed one ulp off it (R7-C-F1 =
A7-F1); a pinned budget snapshot was derived live (B7-M1 = R7-D1).  And MINORs: the follower held its lock across the
execution side's callback, was pinned only when a world bound an account, served undetached payloads, raised raw
errors for unbound accounts, and read experiments back by another rule than replay; providers were named by another
rule than the projection's."""

from __future__ import annotations

import copy
import datetime
import json
import threading
import time

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import (
    ActionMode, AdmissionRecord, BudgetReader, DeclaredConstraint, DispatchRefused, ExecutionDesk, FeasibleActionSpace,
    MindWorldPort, OwnerKind, TemporalSemantics as TS, WorldRefused, admit, authorize_dispatch, project_world,
    proposed_action_from_suggestion, replay_admission,
)
from engcore.mind.world import admission as admission_mod
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.domains import DiscreteLevels
from engcore.mind.world.owners import is_live
from engcore.scientific import ConstraintDefinition, ConstraintOperator as Op, Quantity
from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment
from engcore.scientific.ir.problem import ScientificProblem
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.external import ExternalSuggestion
from engcore.sria.decision.hypotheses import ProposerKind
from engcore.sria.decision.replay import ReplayOutcome

SIM = ax.base("battery")["simulate_pulse"]
P = RoleSource.PROTOCOL_METADATA


def _solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))


def _followed(o, accounts=None):
    reader = BudgetReader.following(accounts or (lambda: (o.ledgers, o.experiments)))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    return reader, authorities


# ---- R7-C-F1 (BLOCKER) = A7-F1 (MAJOR): every spelling of a refuted level is refused --------------------------------------------
def _reach():
    """x in m, own levels {50, 121.1} m, the action's levels the same in mm, and x < 121.1 m strictly."""
    below = DeclaredConstraint("x_below", ConstraintDefinition("x_below", "x", Op.LESS_THAN, Quantity(121.1, "m")),
                               None, ("*",), RoleSource.PROBLEM_SPECIFICATION, "synthetic: strictly below 121.1 m")
    w = b.world("synthetic.reach", (
        b.var("x", R.CONTROLLED_INPUT, "m", TS.CONSTANT_PER_RUN, domain=b.levels("m", 50.0, 121.1)),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("reach", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                          controls=(b.ctrl("x", b.levels("mm", 50000.0, 121100.0), b.P),), expected_observables=("y",),
                          estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        constraints=(below,), channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="reach"),
        references=(b.synthetic("reach/1"),))
    return ax.owned("reach", w)


SPELLINGS = (Quantity(121.1, "m"), Quantity(121100.0, "mm"), Quantity(12110.0, "cm"), Quantity(397.3097112860892, "ft"),
             Quantity(4767.716535433071, "inch"), Quantity(121.09999999999, "m"), Quantity(121099.99999999, "mm"))


@pytest.mark.parametrize("suggestions_only", [False, True])
def test_every_spelling_of_a_refuted_level_is_refused_through_the_gateway(suggestions_only):
    o = _reach()
    calls = []
    gw = ExecutionDesk(o.authorities(), calls.append, accept_synthetic=True, suggestions_only=suggestions_only).gateway()
    port = MindWorldPort(FeasibleActionSpace.build(project_world(o.declaration, o.authorities())),
                         suggestions_only=suggestions_only)
    for spelled in SPELLINGS:
        if suggestions_only:
            s = ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", ActionFamily.EXPLORE, "reach",
                                   {"assignments": [{"variable": "x", "value": spelled.to_dict()}], "observe": ["y"]},
                                   "a language-model suggestion", extra={"world_revision": port.world.revision_id})
            p = proposed_action_from_suggestion(s, world=port.world)
        else:
            p = o.propose("reach", {"x": spelled}, ("y",), world=port.world)
        r = port.request_admission(p, gw)
        assert r.admitted is None and "CONSTRAINT_VIOLATED" in r.codes(), spelled
    assert calls == []
    r = port.request_admission(o.propose("reach", {"x": Quantity(50, "m")}, ("y",), world=port.world), gw) \
        if not suggestions_only else None
    if r is not None:
        assert r.feasible and dict(r.decision.decided)["x"] == Quantity(50.0, "m")


def test_a_level_spelled_by_the_action_and_the_variable_in_two_units_is_executed_as_the_action_level():
    """A7-F1: the variable's own 0.7 A beside the action's 700 mA is the SAME level, not another one."""
    w = b.world("synthetic.strict_level", (
        b.var("I", R.CONTROLLED_INPUT, "A", TS.CONSTANT_PER_RUN, domain=b.levels("A", 0.35, 0.7)),
        b.var("mode", R.CONTROLLED_INPUT, "dimensionless", TS.CONSTANT_PER_RUN, domain=b.cats("mode", "normal", "hot")),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        constraints=(DeclaredConstraint("hot_cap", ConstraintDefinition("hot_cap", "I", Op.LESS_THAN, Quantity(0.7, "A")),
                                        b.when("mode", "hot"), ("pulse",), P, "synthetic: hot runs stay below 0.7 A"),),
        actions=(b.action("pulse", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                          controls=(b.ctrl("I", DiscreteLevels("mA", (Quantity(350, "mA"), Quantity(700, "mA"))), P),
                                    b.ctrl("mode", b.cats("mode", "normal", "hot"), P)),
                          expected_observables=("y",), estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="sl"), references=(b.synthetic("sl/1"),))
    o = ax.owned("x", w)
    space = FeasibleActionSpace.build(o.world)
    for value in (Quantity(0.7, "A"), Quantity(700, "mA"), Quantity(0.6999999999999998, "A")):
        d = space.check(o.propose("pulse", {"I": value, "mode": b.cat("hot")}, ("y",)))
        assert not d.feasible and "CONSTRAINT_VIOLATED" in d.codes(), value
    d = space.check(o.propose("pulse", {"I": Quantity(0.6999999999999998, "A"), "mode": b.cat("normal")}, ("y",)))
    from engcore.mind.world.base import as_unit
    assert d.feasible and dict(d.decided)["I"] == as_unit(Quantity(700, "mA"), "A")   # the action's level, executed


def test_a_level_control_is_never_executed_at_a_value_that_is_no_declared_level(monkeypatch):
    """Two independent guards: if the shared reading path ever left a level control unmatched (here: forced to one
    ulp-scale off the 50 m level), the domain family refuses; and if the family's guard regressed too, mint refuses."""
    from engcore.mind.world import feasibility as fz
    o = _reach()
    real = fz.as_executed

    def unmatched(world, spec, name, value):
        out = real(world, spec, name, value)
        return Quantity(50.00000000001, "m") if name == "x" else out          # the owner calls it 50 m

    monkeypatch.setattr(fz, "as_executed", unmatched)
    monkeypatch.setattr(admission_mod, "as_executed", unmatched)
    proposal = o.propose("reach", {"x": Quantity(50, "m")}, ("y",))
    r = admit(FeasibleActionSpace.build(o.world), proposal, o.authorities())
    assert r.admitted is None and "LEVEL_NOT_DECLARED" in r.codes()
    monkeypatch.setattr(fz, "level_problem", lambda *a: None)             # the family's guard regressed as well
    with pytest.raises(WorldRefused, match="executed only as a declared level"):
        admit(FeasibleActionSpace.build(o.world), proposal, o.authorities())


# ---- B7-M1 = R7-D1 (MAJOR): a pinned budget snapshot is never live ----------------------------------------------------------------
def test_a_pinned_budget_snapshot_is_not_live_and_backs_no_desk_or_dispatch():
    o = ax.owned("battery")
    snapshot = BudgetReader.following(lambda: (o.ledgers, o.experiments)).pinned()
    assert not is_live(snapshot)
    authorities = o.authorities(budget=snapshot)
    assert not authorities.live
    with pytest.raises(WorldRefused, match="live"):
        ExecutionDesk(authorities, lambda a: None, accept_synthetic=True)
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), o.authorities())
    with pytest.raises((WorldRefused, DispatchRefused)):
        authorize_dispatch(r.admitted, authorities, accept_synthetic=True)


# ---- R7-C-F2 / B7-m2 / R7-D4: every verification observes the follower, whatever it reads -----------------------------------------
def test_every_verification_pins_the_follower_even_when_it_reads_no_budget_record():
    o = ax.owned("battery")
    lid = _solver(o)
    reader, authorities = _followed(o)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    o.ledgers[lid].settle(charge_id="run-1", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
    authorities.memoized()                                                # a verification that reads nothing
    o.ledgers[lid] = before                                              # the execution side rolls the ledger back
    with pytest.raises(OwnerUnavailable, match="behind"):
        reader.read(OwnerKind.BUDGET_LEDGER, lid)


# ---- forward-only semantics: behind is refused while behind, a rewrite for good, the observed state is accepted --------------------
def test_an_account_behind_is_refused_while_behind_and_a_rewrite_for_good():
    o = ax.owned("battery")
    lid = _solver(o)
    reader, _ = _followed(o)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    o.ledgers[lid].settle(charge_id="run-1", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
    after = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid) is not None          # observed the spend
    o.ledgers[lid] = BudgetLedger.from_dict(before.to_dict())
    for attempt in range(2):
        with pytest.raises(OwnerUnavailable, match="behind"):
            reader.read(OwnerKind.BUDGET_LEDGER, lid)
    o.ledgers[lid] = BudgetLedger.from_dict(after.to_dict())             # back at the state observed: the account
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid).revision == str(after.revision)   # moved past nothing
    rewritten = BudgetLedger.from_dict(before.to_dict())
    rewritten.settle(charge_id="other", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
    o.ledgers[lid] = rewritten                                           # same length, another history
    with pytest.raises(OwnerUnavailable, match="rewrote its history"):
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    o.ledgers[lid] = BudgetLedger.from_dict(after.to_dict())
    with pytest.raises(OwnerUnavailable, match="from then on"):          # a rewrite is refused for good
        reader.read(OwnerKind.BUDGET_LEDGER, lid)


# ---- B7-m3 / R7-D3: no lock is held across the execution side's accounts() --------------------------------------------------------
def test_no_deadlock_with_an_execution_side_that_verifies_under_its_own_lock():
    o = ax.owned("battery")
    lock = threading.RLock()
    inside = threading.Event()

    def accounts():
        if threading.current_thread().name == "A":
            inside.set()
            time.sleep(0.2)
        with lock:
            return o.ledgers, o.experiments

    reader, authorities = _followed(o, accounts)
    world, out = o.world, {}

    def verification():
        out["A"] = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world),
                         authorities).status.value

    def execution_step():
        inside.wait(2)
        with lock:
            out["B"] = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world),
                             authorities).status.value

    threads = [threading.Thread(target=verification, name="A", daemon=True),
               threading.Thread(target=execution_step, name="B", daemon=True)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not any(t.is_alive() for t in threads) and out["A"] == "FEASIBLE"      # no deadlock
    assert out["B"] == "MISSING_INFORMATION"   # round 10: B waits (WAIT_S) for A, whose accounts() waits for B's lock
    assert admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world),
                 authorities).status.value == "FEASIBLE"


# ---- B7-m4 / R7-D2: an unbound account its owner cannot serialize refuses nothing -------------------------------------------------
@pytest.mark.parametrize("value", [datetime.datetime(2026, 10, 23), {1, 2}, object()])
def test_an_unbound_experiment_its_owner_cannot_serialize_refuses_no_admission(value):
    o = ax.owned("battery")
    world = o.world
    other = ScientificExperiment("other.campaign.experiment", ScientificProblem("other.problem"), ExperimentBudget(5))
    other.metadata["note"] = value
    o.experiments["other.campaign.experiment"] = other
    r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), o.authorities())
    assert r.feasible
    with pytest.raises(OwnerUnavailable, match="owner writes down"):                    # round 10: its owner's own
        BudgetReader(o.ledgers, o.experiments).read(OwnerKind.EXPERIMENT, "other.campaign.experiment")   # rule


# ---- B7-m5: a snapshot serves a detached copy of what it observed -----------------------------------------------------------------
def test_a_snapshot_serves_what_it_observed_after_an_in_place_change():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    o.experiments[eid].metadata["runs"] = ["a"]
    snap = BudgetReader.following(lambda: (o.ledgers, o.experiments)).pinned()
    first = copy.deepcopy(snap.read(OwnerKind.EXPERIMENT, eid).payload["experiment"]["metadata"])
    o.experiments[eid].metadata["runs"].append("b")
    assert snap.read(OwnerKind.EXPERIMENT, eid).payload["experiment"]["metadata"] == first == {"runs": ["a"]}


# ---- R7-D6: an experiment is read back live by the owner's whole rule, the rule replay uses -------------------------------------
def test_an_experiment_its_owner_cannot_read_back_whole_is_owner_unavailable_live():
    from engcore.scientific.experiments import EvaluationStatus, ScientificEvaluation
    o = ax.gen1_pool()
    eid = next(iter(o.experiments))
    exp = o.experiments[eid]
    for i in range(2):
        exp.record(ScientificEvaluation(f"obs-{i}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    exp.budget = ExperimentBudget(max(1, exp.observations - 1))           # cut below what it has observed
    with pytest.raises(OwnerUnavailable, match="reads back"):
        BudgetReader(o.ledgers, o.experiments).read(OwnerKind.EXPERIMENT, eid)


# ---- A7-F2 / B7-m1 / R7-C-F3 / R7-D5: providers are named as the projection binds them ---------------------------------------------
def test_a_declared_provider_no_action_requires_is_projected_and_verified():
    base = b.battery_world()
    w = b.world(base.world_id, base.variables, entities=base.entities, constraints=base.constraints,
                channels=base.channels, applicability=base.applicability,
                providers=base.providers + (b.provider("sim.backup", "1.0"),), budget=base.budget,
                references=base.references, actions=base.actions)
    o = ax.owned("battery", w)
    assert "sim.backup" in [p.provider_id for p in o.world.providers]
    for aid in ("observe_rest", "simulate_pulse"):
        r = admit(FeasibleActionSpace.build(o.world), o.propose(aid, *ax.base("battery")[aid]), o.authorities())
        assert r.feasible, (aid, r.codes())


def test_an_unreadable_declaration_reads_no_account_or_provider_and_says_why():
    o = ax.owned("battery")
    lid = _solver(o)
    world = o.world
    from engcore.mind.world import DeclarationReader
    held = {"set": [o.declaration]}
    decl = DeclarationReader.following(lambda: held["set"])
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    authorities = type(o.authorities()).of(*(decl if type(r) is DeclarationReader else reader if type(r) is BudgetReader
                                             else r for r in o.authorities().readers))
    held["set"] = None                                                   # the execution side cannot state it now
    r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), authorities)
    assert r.admitted is None
    budget_checks = [c for c in r.verification.checks if c.record_id == lid]
    assert budget_checks and all(c.status.value == "owner_unavailable" and "not read" in c.detail["why"]
                                 for c in budget_checks)


# ---- replay of the first refusal, under the round-7 rule ---------------------------------------------------------------------------
def test_the_refusal_of_an_account_behind_can_be_recorded_and_replays():
    o = ax.owned("battery")
    lid = _solver(o)
    world = o.world
    reader, authorities = _followed(o)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    o.ledgers[lid].settle(charge_id="moved", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid) is not None
    o.ledgers[lid] = before
    r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), authorities)
    assert "AUTHORITY_OWNER_UNAVAILABLE" in r.codes()
    record = json.loads(json.dumps(AdmissionRecord.of(r, authorities).to_dict()))
    assert replay_admission(record).outcome is ReplayOutcome.REPRODUCED


# ---- E7-F3: the provider half of K6-F2 ---------------------------------------------------------------------------------------------
def test_a_world_bound_to_a_provider_the_declaration_does_not_name_is_refused_without_probing_it(monkeypatch):
    """A world projected from another declaration (one that lists sim.secret) submitted where the declaration in
    force lists only sim.ecm: the sim.secret binding is not read, so the registry is never asked to probe it."""
    from engcore.providers.catalog import ProviderRegistry
    base = b.battery_world()
    w2 = b.world(base.world_id, base.variables, entities=base.entities, constraints=base.constraints,
                 channels=base.channels, applicability=base.applicability,
                 providers=base.providers + (b.provider("sim.secret", "1.0"),), budget=base.budget,
                 references=base.references, actions=base.actions)
    o2 = ax.owned("battery", w2)
    in_force = ax.owned("battery").declaration
    assert in_force.declaration_id == o2.declaration.declaration_id and "sim.secret" not in in_force.providers
    authorities = o2.authorities(declarations=(in_force,), refresh=True)
    world = o2.world                                                     # projected under o2's own declaration
    probed = []
    real = ProviderRegistry.status
    monkeypatch.setattr(ProviderRegistry, "status",
                        lambda self, pid, **kw: (probed.append(pid), real(self, pid, **kw))[1])
    r = admit(FeasibleActionSpace.build(world), o2.propose("simulate_pulse", *SIM, world=world), authorities)
    assert r.admitted is None                                            # not the declaration in force (same id and
    assert {c.status.value for c in r.verification.checks if c.record_id == "sim.secret"} == {"mismatch"}  # revision)
    why = [c.detail.get("why", "") for c in r.verification.checks if c.record_id == "sim.secret"]
    assert why and "not read" in why[0] and "sim.secret" not in probed and "sim.ecm" in probed


# ---- E7-F5: the remaining_observations basis of a projected experiment ------------------------------------------------------------
def test_an_over_budget_experiment_with_attempts_left_records_remaining_observations():
    from engcore.scientific.experiments import EvaluationStatus, ScientificEvaluation
    p = ax.gen1_pool()
    eid = next(iter(p.experiments))
    exp = ScientificExperiment(eid, ScientificProblem(f"{eid}.problem"), ExperimentBudget(2, max_attempts=5))
    for i in range(2):
        exp.record(ScientificEvaluation(f"{eid}.{i}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="synthetic"))
    p.experiments[eid] = exp
    p._world = None
    r = admit(FeasibleActionSpace.build(p.world), p.propose("pool_query", {"I_A": Quantity(1, "A"),
                                                                           "t_on_s": Quantity(60, "s")}), p.authorities())
    over = {x.subject: x.detail for x in r.reasons if x.code == "OVER_BUDGET"}
    assert over["experiments"]["remaining_basis"] == "remaining_observations"
    assert over["experiments"]["remaining"] == exp.remaining_observations == 0


# ---- K7-F1 (BLOCKER) / K7-F2: offset units, set through a protocol control; strict and inclusive bounds -------------------------
# (the action fixed-condition half is controlled by test_authority_review_r8.py's fixed-condition level tests)
@pytest.mark.parametrize("role", [R.CONTROLLED_INPUT, R.FIXED_PROTOCOL_CONDITION],
                         ids=["controlled_input", "fixed_protocol_condition_variable_set_through_a_control"])
@pytest.mark.parametrize("op", [Op.LESS_THAN, Op.LESS_EQUAL, Op.GREATER_THAN, Op.GREATER_EQUAL])
def test_every_spelling_of_one_level_is_decided_alike_and_executed_as_one_value(role, op):
    """Variable and own levels in degC, the protocol's levels in degF, a limit at the 35 degC level: every spelling the
    unit owner calls 35 degC gets ONE decision, and an admitted one is executed as the protocol's level as executed."""
    from engcore.mind.world import feasibility as fz
    lim = DeclaredConstraint("t_lim", ConstraintDefinition("t_lim", "T", op, Quantity(35.0, "degC")), None, ("*",),
                             P, "synthetic chamber limit")
    w = b.world("synthetic.chamber", (
        b.var("T", role, "degC", TS.CONSTANT_PER_RUN, domain=b.levels("degC", 25.0, 35.0)),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("hold", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                          controls=(b.ctrl("T", b.levels("degF", 77.0, 95.0), b.P),), expected_observables=("y",),
                          estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        constraints=(lim,), channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="ch"),
        references=(b.synthetic("ch/1"),))
    o = ax.owned("chamber", w)
    calls = []
    gw = ExecutionDesk(o.authorities(), calls.append, accept_synthetic=True).gateway()
    port = MindWorldPort(FeasibleActionSpace.build(project_world(o.declaration, o.authorities())))
    level = fz.as_executed(port.world, port.world.action("hold"), "T", Quantity(95.0, "degF"))
    outcomes = set()
    for spelled in (Quantity(95.0, "degF"), Quantity(35.0, "degC"), Quantity(308.15, "K"),
                    Quantity(34.99999999999999, "degC"), Quantity(34.999999999999986, "degC"),
                    Quantity(94.99999999999997, "degF")):
        r = port.request_admission(o.propose("hold", {"T": spelled}, ("y",), world=port.world), gw)
        outcomes.add((r.status.value, tuple(sorted(r.codes()))))
        if r.admitted is not None:
            port.execute(r.admitted, gw)
            assert dict(calls[-1].settings)["T"] == level.magnitude, spelled
    assert len(outcomes) == 1, outcomes
    # round 8 (A8-F3, R8-C-F2): the protocol's 95 degF level executes as 35.00000000000006 degC, above 35 degC, so a
    # limit at 35 degC refuses it below (strict AND inclusive) and admits it above (strict AND inclusive), executed as
    # that one value: decided = executed, at the ulp (README section 4)
    assert level.magnitude > 35.0
    if op in (Op.LESS_THAN, Op.LESS_EQUAL):
        assert {code for _, codes in outcomes for code in codes} == {"CONSTRAINT_VIOLATED"} and not calls
    else:
        assert outcomes == {("FEASIBLE", ())} and len(calls) == 6
