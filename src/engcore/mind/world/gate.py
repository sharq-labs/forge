"""The gate between a cleared action and the existing execution system (held by the execution owner, never the Mind).

An :class:`ExecutionGate` accepts only a :class:`ClearedAction`, re-checks it byte-identically against its own action
space, refuses a second dispatch of the same proposal, reserves the declared costs against what the budget owner says
remains (so N cleared actions cannot overspend one world revision), and requires the executor's provider builds to be
the ones that were cleared.  Only then does it call the executor it was given (``observe`` for the Minimal Mind,
``execute_plan`` for a claim, a SRIA ``SimulationExecutor``...).  It decides no science: a refusal here is an
admissibility fact, never evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from engcore.mind.repsem import canonical_bytes

from .actions import ProposedAction
from .base import WorldRefused, magnitude_key, value_payload
from .feasibility import FeasibilityDecision, FeasibleActionSpace


class GateRefused(WorldRefused):
    """The execution gate refused a dispatch.  ``code`` says why; nothing was executed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class ClearedAction:
    """A proposal that cleared the check against one exact action space, with its resolved configuration.

    ``configuration`` is closed: every active control and every fixed condition, as typed values; the executor never
    fills a missing value.  A hand-built ClearedAction gains nothing: the gate re-derives it."""

    proposal: ProposedAction
    decision: FeasibilityDecision
    configuration: tuple[tuple[str, Any], ...]
    observe: tuple[str, ...]
    space_id: str

    @classmethod
    def of(cls, space: FeasibleActionSpace, proposal: ProposedAction, decision: FeasibilityDecision) -> "ClearedAction":
        spec = space.world.action(proposal.action_id)
        config = {f.name: f.value for f in spec.fixed_conditions}
        config.update(dict(proposal.assignments))
        observe = proposal.observe or spec.expected_observables
        return cls(proposal, decision, tuple(sorted(config.items())), tuple(observe), space.space_id)

    def settings_in_declared_units(self, world: Any) -> dict[str, Any]:
        """Quantities as magnitudes in each variable's declared unit (the sanctioned exit from the unit-aware world,
        ``Quantity.magnitude_in``), other typed values unchanged.  For an executor that takes plain numbers."""
        out = {}
        for name, value in self.configuration:
            out[name] = value.magnitude_in(world.variable(name).unit) if hasattr(value, "magnitude_in") else value
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"proposal": self.proposal.to_dict(), "decision": self.decision.to_dict(),
                "configuration": [{"variable": n, "value": value_payload(v)} for n, v in self.configuration],
                "observe": list(self.observe), "space_id": self.space_id}


class ExecutionGate:
    """Held by the execution owner.  Dispatches a cleared action to the executor it was given, or refuses."""

    def __init__(self, space: FeasibleActionSpace, executor: Callable[[ClearedAction], Any], *,
                 provider_builds: Mapping[str, tuple[str, str]] | None = None) -> None:
        if not isinstance(space, FeasibleActionSpace):
            raise WorldRefused("a gate dispatches against one FeasibleActionSpace")
        if not callable(executor):
            raise WorldRefused("a gate is given an executor")
        self._space = space
        self._executor = executor
        self._builds = dict(provider_builds or {})
        self._dispatched: set[str] = set()
        self._reserved: dict[str, float] = {}

    @property
    def space_id(self) -> str:
        return self._space.space_id

    def reserved(self) -> dict[str, float]:
        return dict(self._reserved)

    def dispatch(self, cleared: ClearedAction) -> Any:
        if not isinstance(cleared, ClearedAction):
            raise GateRefused("NOT_CLEARED", "only a ClearedAction is dispatched")
        if cleared.space_id != self._space.space_id:
            raise GateRefused("OTHER_SPACE", "the action was cleared against another action space")
        decision = self._space.check(cleared.proposal)
        if not decision.feasible or canonical_bytes(decision.to_dict()) != canonical_bytes(cleared.decision.to_dict()):
            raise GateRefused("NOT_REPRODUCED", "the clearance does not reproduce against this action space")
        expected = ClearedAction.of(self._space, cleared.proposal, decision)
        if canonical_bytes(expected.to_dict()) != canonical_bytes(cleared.to_dict()):
            raise GateRefused("CONFIGURATION_TAMPERED", "the configuration is not the one the clearance resolves to")
        if cleared.proposal.digest in self._dispatched:
            raise GateRefused("DUPLICATE_DISPATCH", "this proposal was already dispatched against this revision")
        world = self._space.world
        spec = world.action(cleared.proposal.action_id)
        charges = self._charges(world, spec)
        for dim, amount in charges.items():
            remaining = world.budget.remaining(dim)
            total = self._reserved.get(dim, 0.0) + amount
            ok = world.budget.cost.affordable(total, family=spec.family) if dim == "cost" else total <= remaining
            if not ok:
                raise GateRefused("OVER_BUDGET_RESERVED", f"{dim}: {total} reserved would exceed the {remaining} the "
                                                          "budget owner says remains for this revision")
        for req in spec.provider_requirements:
            snap = world.provider(req.provider_id)
            build = self._builds.get(req.provider_id)
            if build is None or snap is None or tuple(build) != (snap.version, snap.build_digest):
                raise GateRefused("PROVIDER_BUILD_MISMATCH", f"the executor's {req.provider_id!r} build is not the one "
                                                             "the action was cleared against")
        self._dispatched.add(cleared.proposal.digest)
        for dim, amount in charges.items():
            self._reserved[dim] = self._reserved.get(dim, 0.0) + amount
        return self._executor(cleared)

    @staticmethod
    def _charges(world: Any, spec: Any) -> dict[str, float]:
        out = {}
        for dim in ("experiments", "solver_calls", "cost", "wall_time"):
            if world.budget.status(dim) != "limited":
                continue
            amount = spec.estimated_duration if dim == "wall_time" else spec.cost(dim)
            out[dim] = float(amount.value) if hasattr(amount, "value") and not hasattr(amount, "units") \
                else magnitude_key(amount)
        return out


__all__ = ["ClearedAction", "ExecutionGate", "GateRefused"]
