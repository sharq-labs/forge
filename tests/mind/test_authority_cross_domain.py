"""GEN2-BR1.1 cross-domain authority controls and replay, on five structurally different worlds plus the Gen1 protocol.

For every world (battery pulse cell, HVAC chamber, HVAC field task, quadrotor, electric motor, Gen1 two-level pool):

* every current value is a projection of the governing run's committed head state, bound to it;
* the action domains are the declaration in force, bound by identity, revision and digest (caller-declared: no
  canonical protocol owner exists, and admission says so);
* the world binds the sealed unit registry it was read under;
* every provider status is the provider registry's, verified at admission;
* admission cannot be bypassed by a stale or edited projection;
* a historical admission replays exactly after the owners moved on, and the same admitted action is then refused at
  dispatch.

No domain-specific logic is involved: the same generic code runs every world.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import (
    AdmissionRecord, BindingStatus, DispatchRefused, ExecutionDesk, FeasibilityStatus as F, FeasibleActionSpace,
    OwnerKind, ProposedAction, ScientificWorld, WorldRefused, admit, authorize_dispatch, replay_admission, verify_world,
)
from engcore.mind.world.admission import DECLARATION_PROVENANCE
from engcore.sria.decision.replay import ReplayOutcome

NAMES = ("battery", "hvac_chamber", "hvac_field", "drone", "motor", "gen1_pool")


def owned(name: str):
    return ax.gen1_pool() if name == "gen1_pool" else ax.WORLDS[name]()


def proposals(o):
    if o.name == "gen1_pool":
        return {"pool_query": ({"I_A": ax.q(1.0, "A"), "t_on_s": ax.q(60, "s")}, ("y",))}
    return ax.base(o.name)


@pytest.mark.parametrize("name", NAMES)
def test_state_comes_from_the_state_owner(name):
    o = owned(name)
    bound = [v for v in o.world.variables if v.source is not None]
    if o.run is None:
        assert not bound
        return
    head = o.run.checkpoint.state
    assert bound
    for v in bound:
        b = v.source
        assert b.owner_kind is OwnerKind.SYSTEM_STATE and b.owner_id == o.run.request.digest
        assert b.record_digest == head.digest and b.revision == str(head.sequence)
        owner_id, variable = json.loads(b.record_id)
        held = next(x for x in head.owner(owner_id).values if x.variable_id == variable)
        assert held.value == v.value and held.uncertainty == v.uncertainty


@pytest.mark.parametrize("name", NAMES)
def test_action_domains_units_models_and_providers_are_bound_and_verified(name):
    o = owned(name)
    w = o.world
    report = verify_world(w, o.authorities())
    assert report.ok, [c.to_dict() for c in report.failures()]
    kinds = {c.owner_kind for c in report.checks}
    assert {OwnerKind.DECLARATION, OwnerKind.UNIT_REGISTRY} <= kinds
    assert w.declaration.record_digest == o.declaration.digest and w.actions == o.declaration.actions
    assert all(a.authority is not None for a in w.applicability)
    assert all(p.authority is not None for p in w.providers)
    assert all(s.authority is not None for s in w.budget.statements)


@pytest.mark.parametrize("name", NAMES)
def test_admission_cannot_bypass_a_stale_owner_in_any_world(name):
    o = owned(name)
    for aid, (assignments, observe) in proposals(o).items():
        p = o.propose(aid, assignments, observe)
        base = admit(FeasibleActionSpace.build(o.world), p, o.authorities())
        if o.run is not None:
            moved = admit(FeasibleActionSpace.build(o.world), p, o.authorities(state=o.run.result))
            assert moved.admitted is None and "AUTHORITY_STALE" in moved.codes(), (aid, moved.codes())
        if base.admitted is not None:
            assert base.admitted.to_dict()["declaration_provenance"] == DECLARATION_PROVENANCE


@pytest.mark.parametrize("name", [n for n in NAMES if n != "gen1_pool"])
def test_a_provider_that_went_down_is_refused_whatever_the_world_copy_says(name):
    o = owned(name)
    sims = [a for a in o.world.actions if a.provider_requirements]
    assert sims
    down = ax.provider_registry(o, down=tuple(p.provider_id for p in o.world.providers))
    for spec in sims:
        assignments, observe = proposals(o)[spec.action_id]
        r = admit(FeasibleActionSpace.build(o.world), o.propose(spec.action_id, assignments, observe),
                  o.authorities(providers=down))
        assert r.admitted is None and "AUTHORITY_STALE" in r.codes()
        report = verify_world(o.world, o.authorities(providers=down))
        assert {c.owner_kind for c in report.failures()} == {OwnerKind.PROVIDER_STATUS}
        assert all(c.status is BindingStatus.STALE for c in report.failures())


@pytest.mark.parametrize("name", NAMES)
def test_historical_replay_is_exact_and_dispatching_it_after_the_owners_moved_is_refused(name):
    o = owned(name)
    records, admitted = [], []
    for aid, (assignments, observe) in proposals(o).items():
        r = admit(FeasibleActionSpace.build(o.world), o.propose(aid, assignments, observe), o.authorities())
        records.append(AdmissionRecord.of(r, o.authorities()).to_dict())
        if r.admitted is not None:
            admitted.append(r.admitted)
            assert authorize_dispatch(r.admitted, o.authorities(), accept_synthetic=True).admitted_digest == \
                r.admitted.digest
    assert admitted
    # the owners move on: every ledger and experiment is charged, and (where the world reads state) the run advances
    for ledger in o.ledgers.values():
        ledger.settle(charge_id="moved-on", action_id="elsewhere", iteration=9, family=ax.ActionFamily.EXPLORE,
                      realized=0.0)
    for exp in o.experiments.values():
        exp.record(ax.ScientificEvaluation("moved-on", {}, status=ax.EvaluationStatus.FAILED))
    moved = o.authorities(state=None if o.run is None else o.run.result)
    for record in records:
        assert replay_admission(json.loads(json.dumps(record))).outcome is ReplayOutcome.REPRODUCED
    for a in admitted:
        with pytest.raises(DispatchRefused):
            authorize_dispatch(a, moved, accept_synthetic=True)
        with pytest.raises(DispatchRefused):
            ExecutionDesk(moved, lambda auth: None, accept_synthetic=True).dispatch(a)


def test_replay_identity_is_exact_for_every_record_kind():
    o = owned("battery")
    w = o.world
    again = ScientificWorld.from_dict(json.loads(json.dumps(w.to_dict())))
    assert again.revision_id == w.revision_id and again.content_digest == w.content_digest
    assert [b.digest for b in again.authority_bindings()] == [b.digest for b in w.authority_bindings()]
    assert FeasibleActionSpace.build(again).space_id == FeasibleActionSpace.build(w).space_id
    p = o.propose("simulate_pulse", *ax.base("battery")["simulate_pulse"])
    assert ProposedAction.from_dict(json.loads(json.dumps(p.to_dict()))).digest == p.digest
    r1 = admit(FeasibleActionSpace.build(w), p, o.authorities())
    r2 = admit(FeasibleActionSpace.build(again), p, o.authorities())
    assert r1.digest == r2.digest and r1.admitted.digest == r2.admitted.digest


def test_admission_identities_do_not_depend_on_the_hash_seed():
    script = ("import json\nfrom benchmarks.mind_gen2_authority_v1 import fixtures as ax\n"
              "from engcore.mind.world import FeasibleActionSpace, admit\n"
              "out = {}\n"
              "for name in ('battery', 'hvac_field', 'drone', 'motor'):\n"
              "    o = ax.WORLDS[name]()\n"
              "    for aid, (a, obs) in ax.base(name).items():\n"
              "        r = admit(FeasibleActionSpace.build(o.world), o.propose(aid, a, obs), o.authorities())\n"
              "        out[name + '/' + aid] = [o.world.revision_id, r.digest]\n"
              "print(json.dumps(out, sort_keys=True))\n")
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    runs = []
    for seed in ("0", "4242"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=os.pathsep.join([os.path.join(root, "src"), root]))
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, check=True,
                             cwd=root)
        runs.append(out.stdout.strip().splitlines()[-1])
    assert runs[0] == runs[1]


def test_a_world_whose_value_was_edited_after_projection_is_not_admitted_in_any_domain():
    """Round-1 critic CR-3: every world reaches admission.  A projected value edited in place (the frozen record
    rewritten, its binding untouched) is refused before anything is decided: admission decides only on the world its
    payload names, and this object is no longer that world."""
    reached = 0
    for name in ("battery", "hvac_field", "drone", "motor"):
        o = owned(name)
        aid, (assignments, observe) = next((a, x) for a, x in ax.base(name).items()
                                           if admit(FeasibleActionSpace.build(o.world),
                                                    o.propose(a, *x), o.authorities()).admitted is not None)
        edited = ScientificWorld.from_dict(o.world.to_dict())                 # the proposer's own copy
        v = next(x for x in edited.variables if x.source is not None and isinstance(x.value, ax.Quantity))
        object.__setattr__(v, "value", ax.q(v.value.magnitude * 3 + 1, v.value.units))
        with pytest.raises(WorldRefused, match="identity names"):
            admit(_space_over(edited, o.world), o.propose(aid, assignments, observe, world=o.world), o.authorities())
        reached += 1
    assert reached == 4


def _space_over(world, honest):
    """A space whose world is ``world`` (an edited object) but whose identity is the honest world's."""
    space = object.__new__(FeasibleActionSpace)
    built = FeasibleActionSpace.build(honest)
    object.__setattr__(space, "world", world)
    object.__setattr__(space, "entries", built.entries)
    object.__setattr__(space, "space_id", built.space_id)
    return space
