"""The two arms of the GEN2-BR1 feasibility ablation.

GEN2_WORLD_ACTIONSPACE: ``FeasibleActionSpace.check`` on the world.

GEN1_ROLE_ONLY: what Generation 1 can decide about the same proposal, run through the REAL Gen1 code, not a
re-implementation:

* the variable roles come from the world's repsem ``RoleTable`` (Gen1's role layer); a control that is not
  ``RoleTable.interventional()`` cannot be posed;
* each control becomes a Gen1 ``InputSpec`` box over the hull of its declared domain in its declared unit, as the
  battery_rediscovery_v1 adapter did (``_box``); a categorical or boolean control, or a box Gen1 refuses (its boxes
  are positive log-space intervals), cannot be posed;
* the problem is a Gen1 ``ExperimentalProblem`` with the world's remaining experiment count as its query budget;
* the proposal's settings are the raw magnitudes as proposed, because Gen1 settings are plain floats with no unit;
* the verdict is ``ExperimentCandidate.feasible`` (box membership, every settable input set and nothing else), plus
  Gen1's run-loop stop when its query budget is spent.

A proposal Gen1 cannot pose is reported as NOT_POSABLE, never forced into a box and never counted as Gen1 being
right or wrong; the head-to-head comparison uses the cases Gen1 can pose.  Gen1 has no observation-target, provider,
solver-call, applicability, precondition or protocol-constraint semantics, so it neither checks nor refuses them.
"""

from __future__ import annotations

import math
from typing import Any

from engcore.mind.minimal.experiments import ExperimentCandidate
from engcore.mind.minimal.problem import ExperimentalProblem, InputSpec, ProblemRefused
from engcore.mind.repsem.roles import VariableRole as R
from engcore.mind.world import DiscreteLevels, FeasibleActionSpace, ProposedAction, ScientificWorld
from engcore.scientific import Quantity, VariableKind
from engcore.scientific.ir.values import BooleanValue, IntegerValue
from engcore.sria.decision import ActionProposal

ARMS = ("GEN2_WORLD_ACTIONSPACE", "GEN1_ROLE_ONLY")


def gen2(space: FeasibleActionSpace, proposal: ProposedAction) -> dict[str, Any]:
    decision = space.check(proposal)
    return {"verdict": "FEASIBLE" if decision.feasible else "NOT_FEASIBLE", "status": decision.status.value,
            "codes": list(decision.codes()), "decision": decision}


def _not_posable(reason: str) -> dict[str, Any]:
    return {"verdict": "NOT_POSABLE", "reason": reason}


def gen1_problem(world: ScientificWorld, action_id: str) -> tuple[ExperimentalProblem | None, str]:
    spec = world.action(action_id)
    if spec is None:
        return None, "Gen1 poses one problem per declared experiment, and there is none"
    interventional = set(world.roles.interventional())
    inputs = []
    for c in spec.controls:
        if c.variable not in interventional:
            return None, f"{c.variable} is a {world.role(c.variable).value}: not a Gen1 settable input"
        unit = world.variable(c.variable).unit
        d = c.domain
        if isinstance(d, DiscreteLevels):
            mags = [level.magnitude_in(unit) for level in d.levels]
            lo, hi = min(mags), max(mags)
        elif d.kind in (VariableKind.CONTINUOUS, VariableKind.INTEGER):
            lo, hi = d.lower.magnitude_in(unit), d.upper.magnitude_in(unit)
        else:
            return None, f"a {d.kind.value} input has no Gen1 form"
        try:
            inputs.append(InputSpec(c.variable, lo, hi, unit))
        except ProblemRefused as exc:
            return None, f"Gen1 refuses the box for {c.variable}: {exc}"
    if not inputs:
        return None, "an observation-only action has no Gen1 settable input"
    roles = {v.name: v.role for v in world.variables}
    observable = next((o for o in spec.expected_observables if roles[o] is R.MEASUREMENT), spec.expected_observables[0])
    covariates = tuple(sorted(v.name for v in world.variables if v.role is R.NUISANCE_VARIABLE
                              and world.has_channel(v.name) and v.name != observable))
    remaining = world.budget.remaining("experiments")
    try:
        problem = ExperimentalProblem(f"gen1:{world.world_id}:{action_id}", tuple(inputs), covariates, observable,
                                      world.variable(observable).unit, max(int(remaining or 1), 1), 1.0, {})
    except ProblemRefused as exc:
        return None, f"Gen1 refuses the problem: {exc}"
    return problem, ""


def _setting(value: Any) -> float:
    if isinstance(value, Quantity):
        return float(value.magnitude)            # Gen1 settings carry no unit: the magnitude as proposed
    if isinstance(value, (IntegerValue, BooleanValue)):
        return float(value.value)
    return math.nan                              # a category has no Gen1 float form


def gen1_role_only(world: ScientificWorld, proposal: ProposedAction) -> dict[str, Any]:
    problem, why = gen1_problem(world, proposal.action_id)
    if problem is None:
        return _not_posable(why)
    spec = world.action(proposal.action_id)
    settings = {name: _setting(value) for name, value in proposal.assignments}
    candidate = ExperimentCandidate(settings, ActionProposal(family=spec.family, target_ref=proposal.action_id,
                                                             rationale="GEN1_ROLE_ONLY ablation arm"),
                                    "gen1_role_only")
    ok, reason = candidate.feasible(problem)
    remaining = world.budget.remaining("experiments")
    if ok and remaining is not None and remaining < 1:
        ok, reason = False, "the query budget is spent (Gen1 run loop stops)"
    return {"verdict": "FEASIBLE" if ok else "NOT_FEASIBLE", "reason": reason}


__all__ = ["ARMS", "gen1_problem", "gen1_role_only", "gen2"]
