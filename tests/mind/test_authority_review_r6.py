"""GEN2-BR1.1 review round 6: one control per finding behind a PARTIAL verdict (benchmarks/mind_gen2_authority_v1/README.md).

Round 6 found 0 BLOCKER / 0 MAJOR, but Q2, Q3, Q4 and Q7 stayed PARTIAL on MINOR findings, and the brief does not close
on PARTIAL.  These pin the fixes: the budget follower (a baseline at construction, reads ordered and atomic, a first
refusal that can be recorded, experiments read back in linear time, every handed account observed at every
verification and served as observed), proposer-directed reads, the level rule over both
level sets, the fixed-kind rule, and controls that were missing (gating False, the recorded remainder basis)."""

from __future__ import annotations

import dataclasses
import json

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import VariableRole as R
from engcore.mind.world import (
    ActionMode, AdmissionRecord, BudgetReader, BudgetSource, DispatchRefused, ExecutionDesk, FeasibilityStatus as F,
    FeasibleActionSpace, OwnerKind, TemporalSemantics as TS, admit, authorize_dispatch, replay_admission,
)
from engcore.mind.world import feasibility as fz
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific import Quantity
from engcore.scientific.experiments.evaluation import ScientificEvaluation
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.replay import ReplayOutcome

SIM = ax.base("battery")["simulate_pulse"]


def _solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))


def _followed(o):
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    return reader, authorities


# ---- the follower ----------------------------------------------------------------------------------------------------------------
def test_a_restore_before_the_first_verification_is_refused_against_what_construction_observed():
    """R6-D1 / B6-M4: construction observes the accounts handed over (the round-4 protection, restored)."""
    o = ax.owned("battery")
    lid = _solver(o)
    o.ledgers[lid].settle(charge_id="spent", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    before_charges = before.charges[:-1]
    reader, _ = _followed(o)                                              # observes the spent account
    o.ledgers[lid] = BudgetLedger(total_budget=before.total_budget, cost_unit=before.cost_unit, charges=before_charges)
    with pytest.raises(OwnerUnavailable, match="behind"):
        reader.read(OwnerKind.BUDGET_LEDGER, lid)


def test_an_older_snapshot_read_after_a_newer_one_serves_what_it_observed_and_refuses_nothing():
    """B6-M1 / R6-C-M2 / R6-D2: two verifications on one desk; the older snapshot reaches the account second.  Each
    snapshot observed every account when it was taken (in order) and serves exactly that."""
    o = ax.owned("battery")
    lid = _solver(o)
    reader, _ = _followed(o)
    r0 = o.ledgers[lid].revision
    older = reader.pinned()
    newer_ledger = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    newer_ledger.settle(charge_id="moved", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
    o.ledgers[lid] = newer_ledger                                         # the execution side replaces the object
    newer = reader.pinned()
    assert newer.read(OwnerKind.BUDGET_LEDGER, lid).revision == str(r0 + 1)     # the newer snapshot is read first
    assert older.read(OwnerKind.BUDGET_LEDGER, lid).revision == str(r0)         # the older one: what it observed
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid).revision == str(r0 + 1)    # and nothing was refused for good


def test_concurrent_verifications_never_refuse_for_good_an_account_that_only_moves_forward():
    """B6-M1 / R6-C-M2 / R6-D2 under threads: verifications pin and read while the execution side moves the account
    forward, replacing the object each time.  Since round 7 a verification whose snapshot is older than one already
    observed is refused while it is behind (a supplementary stress control; the deterministic one is the older-snapshot
    test above); nothing is refused for good, and the account is read afterwards (round 8, A8-F1 / B8-m2)."""
    import threading
    o = ax.owned("battery")
    lid = _solver(o)
    reader, _ = _followed(o)
    r0 = o.ledgers[lid].revision
    errors: list[str] = []
    stop = threading.Event()

    def verify():
        while not stop.is_set():
            try:
                reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid)
            except OwnerUnavailable as exc:
                errors.append(str(exc))

    threads = [threading.Thread(target=verify) for _ in range(4)]
    for t in threads:
        t.start()
    for i in range(40):
        moved = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
        moved.settle(charge_id=f"c{i}", action_id="x", iteration=i, family=ActionFamily.EXPLORE, realized=0.01)
        o.ledgers[lid] = moved
    stop.set()
    for t in threads:
        t.join()
    assert all("behind" in e or "still in flight" in e for e in errors), errors        # transient (rounds 7, 9)
    assert not any("rewrote" in e for e in errors), errors                                # never for good
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid).revision == str(r0 + 40)
    assert reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid).revision == str(r0 + 40)


def test_a_spend_seen_by_a_verification_of_another_account_still_refuses_a_later_rollback():
    """R6-C-M1: a verification observes every account handed over, not only those its world binds, so a desk whose
    later verifications read other accounts still refuses a rollback of one it observed moving."""
    o = ax.owned("battery")
    lid = _solver(o)
    eid = next(iter(o.experiments))
    reader, authorities = _followed(o)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    o.ledgers[lid].settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                          realized=2.0)                                    # the executor spends
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None             # a verification that reads another account
    o.ledgers[lid] = before                                               # the execution side rolls the ledger back
    for attempt in range(2):
        with pytest.raises(DispatchRefused, match="OWNER_UNAVAILABLE"):
            gateway.dispatch(r.admitted)
    assert len(calls) == 1


def test_the_refusal_that_first_sees_a_divergence_can_be_recorded_and_replays():
    """B6-M3 / R6-D4: the first and every later refusal state the divergence alike, so it is recordable."""
    o = ax.owned("battery")
    lid = _solver(o)
    world = o.world
    reader, authorities = _followed(o)
    o.ledgers[lid].settle(charge_id="moved", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid) is not None          # observed after the spend
    o.ledgers[lid] = BudgetLedger.from_dict({**o.ledgers[lid].to_dict(), "charges": o.ledgers[lid].to_dict()["charges"][:-1]})
    r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), authorities)
    assert r.status is F.MISSING_INFORMATION and "AUTHORITY_OWNER_UNAVAILABLE" in r.codes()
    record = json.loads(json.dumps(AdmissionRecord.of(r, authorities).to_dict()))
    assert replay_admission(record).outcome is ReplayOutcome.REPRODUCED


def test_a_bound_experiment_rolled_back_after_it_was_observed_is_refused_at_every_later_dispatch():
    """K6-F1: the experiment half of the follower, through the desk (the twin of round 5's ledger control)."""
    from engcore.scientific.experiments.evaluation import EvaluationStatus
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader, authorities = _followed(o)
    before = type(o.experiments[eid]).from_dict(o.experiments[eid].to_dict())
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.feasible and any(bd is not None and bd.record_id == eid for _, bd, _ in o.world.projected_facts())
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    o.experiments[eid].record(ScientificEvaluation(f"{eid}.run-1", {}, status=EvaluationStatus.FAILED,
                                                   detail="synthetic"))   # the executor records an observation
    with pytest.raises(DispatchRefused, match="AUTHORITY_STALE"):
        gateway.dispatch(r.admitted)
    o.experiments[eid] = before                                          # the execution side rolls the account back
    for attempt in range(2):
        with pytest.raises(DispatchRefused, match="OWNER_UNAVAILABLE"):
            gateway.dispatch(r.admitted)
    assert len(calls) == 1


def test_an_experiment_rewritten_at_the_same_length_is_refused_for_good():
    """K6-F1: a rewritten evaluation is a divergence, however many evaluations the account still states."""
    o = ax.gen1_pool()
    eid = next(iter(o.experiments))
    o.experiments[eid] = ax.experiment(eid, 5, 2)                         # two evaluations recorded
    o._world = None
    reader, _ = _followed(o)
    payload = o.experiments[eid].to_dict()
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None
    rewritten = [*payload["evaluations"][:-1], {**payload["evaluations"][-1], "detail": "rewritten"}]
    o.experiments[eid] = type(o.experiments[eid]).from_dict({**payload, "evaluations": rewritten})
    for attempt in range(2):
        with pytest.raises(OwnerUnavailable):
            reader.read(OwnerKind.EXPERIMENT, eid)


def test_an_unchanged_experiment_is_read_back_by_its_owner_once_per_content(monkeypatch):
    """R6-D3, as restated in round 7 (E8-F4): the owner reads an experiment back whole (its quadratic from_dict, the
    rule replay uses) once per content; a later verification of the unchanged experiment does not rebuild it."""
    from engcore.scientific.experiments.experiment import ScientificExperiment
    o = ax.gen1_pool()
    eid = next(iter(o.experiments))
    o.experiments[eid] = ax.experiment(eid, 5, 3)
    o._world = None
    reader, _ = _followed(o)

    def no_rebuild(cls, payload):
        raise AssertionError("the follower rebuilt the whole experiment")

    monkeypatch.setattr(ScientificExperiment, "from_dict", classmethod(no_rebuild))
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None


# ---- K6-F2: a world never chooses which accounts or providers are read ---------------------------------------------------------
def test_a_world_bound_to_an_account_the_declaration_does_not_name_is_refused_without_reading_it():
    o = ax.owned("battery")
    lid = _solver(o)
    o.ledgers["other.campaign.ledger"] = ax.ledger(10.0, 0.0, o.ledgers[lid].cost_unit, "other")
    reader, authorities = _followed(o)
    world = o.world
    statements = tuple(dataclasses.replace(s, authority=dataclasses.replace(s.authority, record_id="other.campaign.ledger"))
                       if s.authority.record_id == lid else s for s in world.budget.statements)
    from engcore.mind.world import ScientificWorld
    payload = world.to_dict()
    payload["budget"] = dataclasses.replace(world.budget, statements=statements).to_dict()
    forged = ScientificWorld.from_dict({k: v for k, v in payload.items() if k not in ("content_digest", "revision_id")})
    seen_before = dict(reader._seen)                                      # (private: what the follower observed)
    r = admit(FeasibleActionSpace.build(forged), o.propose("simulate_pulse", *SIM, world=forged), authorities)
    assert r.status is F.MISSING_INFORMATION and "AUTHORITY_MISMATCH" in r.codes()
    why = [c.detail.get("why", "") for c in r.verification.checks if c.record_id == "other.campaign.ledger"]
    assert why and "not read" in why[0]
    assert reader._seen == seen_before                     # the follower observes every handed account, whatever the
    assert ("ledger", "other.campaign.ledger") in seen_before   # world: a submitted world never chooses what it tracks


# ---- A6-F1: a level is matched in one level set, never nearer another declared level -------------------------------------------
@pytest.mark.parametrize("action_levels,variable_levels", [((1.0,), (1.0, 1.000000000006)),
                                                         ((1.0, 1.000000000006), (1.0, 1.000000000009))])
def test_a_value_nearer_another_declared_level_of_its_variable_is_never_executed_at_a_farther_one(action_levels,
                                                                                                  variable_levels):
    w = b.world("synthetic.two_level_sets", (
        b.var("I", R.CONTROLLED_INPUT, "A", TS.CONSTANT_PER_RUN, domain=b.levels("A", *variable_levels)),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("step", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                          controls=(b.ctrl("I", b.levels("A", *action_levels), b.P),), expected_observables=("y",),
                          estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="tl"), references=(b.synthetic("tl/1"),))
    value = Quantity(1.000000000004, "A")
    assert fz.as_executed(w, w.action("step"), "I", value) != Quantity(1.0, "A")
    d = FeasibleActionSpace.build(w).check(b.propose(w, "step", {"I": value}, ("y",)))
    assert not d.feasible and "LEVEL_NOT_DECLARED" in d.codes()


# ---- A6-F3 / B6-M2 / E6-F2: the gating=False path ---------------------------------------------------------------------------------
def test_an_annotation_only_applicability_binding_is_listed_as_not_gating():
    base = b.battery_world()
    observe = base.action("observe_rest")
    route = next(a.applicability[0] for a in base.actions if a.applicability)
    annotated = dataclasses.replace(observe, applicability=(route,))
    o = ax.owned("battery", base.derive(reason="annotated", actions=tuple(
        annotated if a.action_id == "observe_rest" else a for a in base.actions)))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("observe_rest", *ax.base("battery")["observe_rest"]),
              o.authorities())
    assert r.feasible and o.world.action("observe_rest").execution.value != "model_execution"
    auth = authorize_dispatch(r.admitted, o.authorities(), accept_synthetic=True)
    for payload in (r.admitted.to_dict(), auth.to_dict()):
        assert payload["models"] and all(m["gating"] is False for m in payload["models"])


# ---- A6-F3 / E6-F3: the remainder basis is recorded in the decision ---------------------------------------------------------------
def test_an_over_budget_decision_records_the_remainder_basis_for_a_validate_ledger_and_an_attempt_cap():
    base = b.battery_world()
    sim = base.action("simulate_pulse")
    validating = dataclasses.replace(sim, family=ActionFamily.VALIDATE)
    o = ax.owned("battery", base.derive(reason="validate", actions=tuple(
        validating if a.action_id == "simulate_pulse" else a for a in base.actions)))
    lid = _solver(o)
    o.ledgers[lid] = BudgetLedger(total_budget=1.0, reserved_validation_budget=0.5, cost_unit="dimensionless")
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), o.authorities())
    over = {x.subject: x.detail for x in r.reasons if x.code == "OVER_BUDGET"}
    assert over["solver_calls"]["remaining_basis"] == "validation_pool+general_pool"
    assert over["solver_calls"]["remaining"]["magnitude"] == 1.0
    from engcore.scientific.experiments.evaluation import EvaluationStatus
    from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment
    from engcore.scientific.ir.problem import ScientificProblem
    p = ax.gen1_pool()
    eid = next(iter(p.experiments))
    capped = ScientificExperiment(eid, ScientificProblem(f"{eid}.problem"), ExperimentBudget(2, max_attempts=2))
    for i in range(2):
        capped.record(ScientificEvaluation(f"{eid}.{i}", {}, status=EvaluationStatus.FAILED, detail="synthetic"))
    p.experiments[eid] = capped
    p._world = None
    r = admit(FeasibleActionSpace.build(p.world), p.propose("pool_query", {"I_A": Quantity(1, "A"),
                                                                           "t_on_s": Quantity(60, "s")}), p.authorities())
    over = {x.subject: x.detail for x in r.reasons if x.code == "OVER_BUDGET"}
    assert over["experiments"]["remaining_basis"] == "attempt_cap" and over["experiments"]["remaining"] == 0


def test_a_br1_style_validate_refusal_records_both_pools_the_plan_compared_with():
    """A6-F4: an unprojected (BR1-style) world keeps BR1's plan rule, and its OVER_BUDGET now states the remainder that
    rule compared (validation_pool + general_pool for a VALIDATE action) and its basis."""
    from engcore.mind.world import WorldBudget
    from engcore.sria.decision.recommendation import BudgetPlan
    base = b.battery_world()
    sim = base.action("simulate_pulse")
    bud = base.budget
    plan = BudgetPlan(total_budget=10.0, reserved_validation_budget=6.0)
    budget = WorldBudget(experiments=bud.experiments, observations_spent=bud.observations_spent, compute=bud.compute,
                         compute_used=bud.compute_used, compute_spent=bud.compute_spent, cost=plan,
                         cost_spent=(0.0, 0.0), cost_unit="EUR",
                         unbounded=tuple((d, x) for d, x in bud.unbounded if d != "cost"),
                         authority=b.synthetic("ledger/validate-cost"))
    details = {}
    for family in (ActionFamily.VALIDATE, ActionFamily.EXPLORE):
        priced = dataclasses.replace(sim, family=family,
                                     estimated_cost={**dict(sim.estimated_cost), "cost": Quantity(12.0, "dimensionless")})
        w = b.world(base.world_id + ".v", base.variables, entities=base.entities, constraints=base.constraints,
                    channels=base.channels, applicability=base.applicability, providers=base.providers,
                    references=base.references + (b.synthetic("ledger/validate-cost"),), budget=budget,
                    actions=tuple(priced if a.action_id == "simulate_pulse" else a for a in base.actions))
        d = FeasibleActionSpace.build(w).check(b.propose(w, "simulate_pulse", *SIM))
        details[family] = next(dict(r.detail) for r in d.reasons if r.code == "OVER_BUDGET" and r.subject == "cost")
    assert details[ActionFamily.VALIDATE]["remaining"] == 10.0
    assert details[ActionFamily.VALIDATE]["remaining_basis"] == "validation_pool+general_pool"
    assert details[ActionFamily.EXPLORE]["remaining"] == 4.0
    assert details[ActionFamily.EXPLORE]["remaining_basis"] == "general_pool"
