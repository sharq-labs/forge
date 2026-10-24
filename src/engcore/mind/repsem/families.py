"""Declared model families and their role-typed binding to a problem's data.

A declared family states its own slots by ROLE, not by column name: "a driver that is a CONTROLLED_INPUT", "a state
that is a STATE_VARIABLE driven by that driver", "parameters that are LATENT_PARAMETERs".  :func:`bind` fills each slot
with the one variable the problem's role table declares for it.  Whether a column is an intervention, a state or a
nuisance is a fact about the experiment, so a family can only be bound through the problem's declared roles; with the
legacy two-class table (clock + passive covariates, no state, no latent parameter) binding is refused as
REPRESENTATION_UNAVAILABLE, which is exactly what v1's adapter could not express.

Initial states and any other per-trajectory condition a family needs are read from the trajectory's declared
``initial_state`` / ``conditions``; a missing one refuses the binding (a missing boundary condition is never defaulted).

The engine is domain-agnostic: a family's equations live in its ``simulate`` callable, supplied by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

import numpy as np

from .roles import RoleTable, VariableRole


class BindingRefused(ValueError):
    def __init__(self, message: str, condition: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.condition = dict(condition)


@dataclass(frozen=True)
class FamilySlot:
    name: str
    roles: tuple[VariableRole, ...]
    state_of: str | None = None      # a state slot names the driver slot whose variable must drive it


@dataclass(frozen=True)
class BoundTrajectory:
    traj_id: str
    unit_id: str
    clock: np.ndarray
    slots: Mapping[str, np.ndarray]          # slot -> column (states are NOT read from here by a family)
    initial_state: Mapping[str, float]       # slot -> declared initial value
    conditions: Mapping[str, Any]
    measurement: np.ndarray
    columns: Mapping[str, np.ndarray]        # every observed column, for applicability checks on free predictors


#: simulate(params, trajectory, constants) -> (predicted measurement, {state slot: reconstructed state trajectory})
Simulator = Callable[[Mapping[str, float], BoundTrajectory, Mapping[str, Any]], tuple[np.ndarray, Mapping[str, np.ndarray]]]


@dataclass(frozen=True)
class DeclaredFamily:
    family_id: str
    description: str
    slots: tuple[FamilySlot, ...]
    parameters: tuple[str, ...]
    simulate: Simulator
    required_conditions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"family_id": self.family_id, "description": self.description, "parameters": list(self.parameters),
                "slots": [{"name": s.name, "roles": [r.value for r in s.roles], "state_of": s.state_of} for s in self.slots],
                "required_conditions": list(self.required_conditions)}


@dataclass(frozen=True)
class Binding:
    family_id: str
    clock: str
    measurement: str
    slots: Mapping[str, str]                 # slot -> variable
    parameters: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"family_id": self.family_id, "clock": self.clock, "measurement": self.measurement,
                "slots": dict(sorted(self.slots.items())), "parameters": list(self.parameters)}


def bind(family: DeclaredFamily, roles: RoleTable, clock: str) -> Binding:
    slots: dict[str, str] = {}
    for slot in family.slots:
        cands = [d.name for d in roles.declarations if d.role in slot.roles and d.name != clock]
        if slot.state_of is not None:
            driver = slots[slot.state_of]
            cands = [c for c in cands if driver in roles.declaration(c).driven_by]
        if len(cands) != 1:
            raise BindingRefused(
                f"family {family.family_id}: slot {slot.name!r} needs exactly one variable declared "
                f"{[r.value for r in slot.roles]}" + (f" driven by {slots[slot.state_of]!r}" if slot.state_of else "")
                + f"; the role table offers {cands}",
                {"slot": slot.name, "roles": [r.value for r in slot.roles], "candidates": cands,
                 "legacy_roles": roles.is_legacy})
        slots[slot.name] = cands[0]
    measurements = roles.names(VariableRole.MEASUREMENT)
    if len(measurements) != 1:
        raise BindingRefused(f"family {family.family_id}: exactly one MEASUREMENT is needed, found {list(measurements)}",
                             {"measurements": list(measurements)})
    latent = set(roles.names(VariableRole.LATENT_PARAMETER))
    missing = sorted(set(family.parameters) - latent)
    if missing:
        raise BindingRefused(f"family {family.family_id}: parameters {missing} are not declared LATENT_PARAMETERs",
                             {"undeclared_parameters": missing, "legacy_roles": roles.is_legacy})
    return Binding(family.family_id, clock, measurements[0], slots, tuple(family.parameters))


def bind_trajectory(family: DeclaredFamily, binding: Binding, roles: RoleTable, traj: Mapping[str, Any]) -> BoundTrajectory:
    cols = traj["columns"]
    initial = {}
    for slot in family.slots:
        if slot.state_of is None:
            continue
        var = binding.slots[slot.name]
        if var not in traj.get("initial_state", {}):
            raise BindingRefused(f"trajectory {traj['id']}: no declared initial value of state {var!r}",
                                 {"trajectory": traj["id"], "missing_initial_state": var})
        initial[slot.name] = float(traj["initial_state"][var])
    conditions = dict(traj.get("conditions", {}))
    missing = sorted(set(family.required_conditions) - set(conditions))
    if missing:
        raise BindingRefused(f"trajectory {traj['id']}: missing declared conditions {missing}",
                             {"trajectory": traj["id"], "missing_conditions": missing})
    driven = {s.name: np.asarray(cols[binding.slots[s.name]], float) for s in family.slots if s.state_of is None}
    observed = {c: np.asarray(v, float) for c, v in cols.items() if c in roles.observed()}
    return BoundTrajectory(traj["id"], str(traj["unit_id"]), np.asarray(cols[binding.clock], float), driven, initial,
                           conditions, np.asarray(cols[binding.measurement], float), observed)


__all__ = ["Binding", "BindingRefused", "BoundTrajectory", "DeclaredFamily", "FamilySlot", "Simulator", "bind",
           "bind_trajectory"]
