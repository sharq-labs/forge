"""GEN2-BR1.1 adversarial authority mutations: no laundering through reserialization, rebinding or a new revision.

One property of an authority-bound world (or of an admitted action) is mutated at a time, in every fixture world.
Every scientifically material mutation must either be refused when the world is rebuilt, or leave a world its owners
do not support: admission is then MISSING_INFORMATION with an AUTHORITY reason, and nothing is admitted.  The only
way to change an authoritative value is a new owner record, re-projected under a new binding.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
from typing import Any

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.scientific import ScientificCoreError
from engcore.mind.world import (
    AdmittedAction, DispatchRefused, ExecutionDesk, FeasibilityStatus as F, FeasibleActionSpace, Lineage,
    ScientificWorld, StaleProposal, WorldRefused, admit, authorize_dispatch, verify_lineage, verify_world,
)

WORLD_NAMES = ("battery", "hvac_chamber", "hvac_field", "drone", "motor")
_CACHE: dict[str, Any] = {}


def owned(name: str):
    if name not in _CACHE:
        _CACHE[name] = ax.WORLDS[name]()
    return _CACHE[name]


def _hex(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _feasible_base(o) -> tuple[str, Any, Any]:
    """An action of this world that is admitted on the base world (the mutation then must take that away)."""
    for aid, (assignments, observe) in ax.base(o.name).items():
        r = admit(FeasibleActionSpace.build(o.world), o.propose(aid, assignments, observe), o.authorities())
        if r.admitted is not None:
            return aid, assignments, observe
    raise AssertionError(f"{o.name}: no admitted base action")


def _never_admitted(o, payload: dict[str, Any]) -> str:
    """'refused at rebuild', or the admission outcome on the rebuilt world, which must not admit anything."""
    try:
        world = ScientificWorld.from_dict(payload)
    except (WorldRefused, ScientificCoreError, ValueError, KeyError, TypeError) as exc:
        return f"refused at rebuild: {type(exc).__name__}"
    aid, assignments, observe = _feasible_base(o)
    r = admit(FeasibleActionSpace.build(world), o.propose(aid, assignments, observe, world=world), o.authorities())
    assert r.admitted is None and r.status is F.MISSING_INFORMATION, (o.name, r.status, r.codes())
    assert any(c.startswith("AUTHORITY_") for c in r.codes()), r.codes()
    return ",".join(r.codes())


from benchmarks.mind_gen2_authority_v1.mutations import MUTATIONS, NEEDS  # noqa: E402


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
@pytest.mark.parametrize("name", WORLD_NAMES)
def test_a_reserialized_mutation_never_admits(name, mutation):
    o = owned(name)
    payload = copy.deepcopy(o.world.to_dict())
    need = NEEDS.get(mutation)
    if need == "budget" and not payload["budget"].get("statements") or need and need != "budget" and not payload[need]:
        pytest.skip(f"{name} has no {need}")
    MUTATIONS[mutation](payload)
    payload.pop("content_digest", None)
    payload.pop("revision_id", None)
    outcome = _never_admitted(o, payload)
    assert outcome


@pytest.mark.parametrize("name", WORLD_NAMES)
def test_an_unmutated_reserialization_is_the_same_verified_world(name):
    o = owned(name)
    again = ScientificWorld.from_dict(o.world.to_dict())
    assert again.revision_id == o.world.revision_id and verify_world(again, o.authorities()).ok


@pytest.mark.parametrize("name", WORLD_NAMES)
def test_rebinding_or_a_new_revision_never_launders_a_value(name):
    o = owned(name)
    w = o.world
    v = next(x for x in w.variables if x.source is not None)
    with pytest.raises(WorldRefused):                                   # revision creation: a hand edit
        w.derive(reason="hand edit", variables=tuple(dataclasses.replace(x, value=ax.q(x.value.magnitude + 1,
                                                                                         x.value.units))
                                                     if x is v else x for x in w.variables))
    other = next((x for x in w.variables if x.source is not None and x is not v), None)
    if other is not None:                                               # rebinding: another variable's binding
        with pytest.raises(WorldRefused):
            dataclasses.replace(w, variables=tuple(dataclasses.replace(x, source=other.source) if x is v else x
                                                   for x in w.variables))
    unbound = w.derive(reason="unbound", variables=tuple(
        dataclasses.replace(x, value=None, origin=None, source=None, uncertainty=ax.Uncertainty.unknown("withdrawn"))
        if x is v else x for x in w.variables))
    with pytest.raises(WorldRefused):                                   # the BR1 laundering: re-bind after unbinding
        unbound.derive(reason="re-bound", variables=tuple(
            dataclasses.replace(x, value=v.value, origin=v.origin, source=dataclasses.replace(
                v.source, projection=_hex("another projection")), uncertainty=v.uncertainty) if x.name == v.name else x
            for x in unbound.variables))
    r = admit(FeasibleActionSpace.build(unbound), o.propose(*_feasible_base(o)[:2], world=unbound), o.authorities())
    assert r.admitted is None and "AUTHORITY_MISMATCH" in r.codes()      # an unbound copy is not the projection


@pytest.mark.parametrize("name", WORLD_NAMES)
def test_a_forged_parent_never_verifies_and_never_carries_a_proposal_over(name):
    o = owned(name)
    w = o.world
    forged = dataclasses.replace(w, lineage=Lineage(1, _hex("a parent nobody made"), "forged", ("variables",)))
    assert forged.revision_id != w.revision_id
    with pytest.raises(WorldRefused):
        verify_lineage(forged, {w.revision_id: w})
    aid, assignments, observe = _feasible_base(o)
    with pytest.raises(StaleProposal):
        admit(FeasibleActionSpace.build(forged), o.propose(aid, assignments, observe), o.authorities())


@pytest.mark.parametrize("field_name", ["proposal", "world_revision", "space_id", "admission", "bindings",
                                        "configuration", "context", "observe", "execution", "synthetic"])
def test_a_mutated_admitted_action_is_refused_at_dispatch(field_name):
    o = owned("battery")
    sim = ax.br1.base("battery")["simulate_pulse"]
    result = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *sim), o.authorities())
    a = result.admitted
    assert a is not None
    forged = object.__new__(AdmittedAction)
    for f in dataclasses.fields(a):
        object.__setattr__(forged, f.name, getattr(a, f.name))
    replacement = {
        "proposal": o.propose("simulate_pulse", {**sim[0], "I": ax.q(1.0, "A")}, sim[1]),
        "world_revision": _hex("another world"), "space_id": _hex("another space"),
        "admission": _hex("another admission"), "bindings": (), "configuration": (("I", ax.q(99, "A")),),
        "context": a.context + ({"variable": "SOC", "value": None, "binding": None},), "observe": ("T_surf",),
        "execution": next(k for k in type(a.execution) if k is not a.execution),
        "synthetic": not a.synthetic,
    }[field_name]
    assert replacement != getattr(a, field_name)                      # an actual mutation
    object.__setattr__(forged, field_name, replacement)
    calls: list[Any] = []
    with pytest.raises(DispatchRefused):
        ExecutionDesk(o.authorities(), calls.append, accept_synthetic=True).dispatch(forged)
    assert calls == []
    with pytest.raises(DispatchRefused):
        authorize_dispatch(a, o.authorities())                         # synthetic content: refused by default
    with pytest.raises(DispatchRefused):
        authorize_dispatch(a, type(o.authorities()).from_snapshot(o.authorities().snapshot(
            o.world.authority_bindings())), accept_synthetic=True)      # never against a snapshot
