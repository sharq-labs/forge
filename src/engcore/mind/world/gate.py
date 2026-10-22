"""The gate between a cleared action and the existing execution system (held by the execution owner, never the Mind).

An :class:`ExecutionGate` dispatches only what it re-derives itself.  At construction it takes its OWN detached copy of
the world (rebuilt from the world's payload, so later mutation of the caller's objects cannot reach it) and refuses to
serve a world it cannot trust: bound values are verified against their owner records, model records against a
``ModelRegistry``, and a world bound to synthetic fixtures is refused unless the owner explicitly allows it (tests and
development benchmarks only).

At dispatch it accepts only an exact :class:`ClearedAction`, rebuilds the proposal from its payload, re-checks it
against its own action space, re-derives the clearance and compares it byte for byte, refuses a proposal already
dispatched against this world revision, reserves the declared costs against what the budget owner says remains, and
reads each required provider's status live from the provider authority (``provider_status``, e.g.
``ProviderRegistry.status``) and requires the build that was cleared.  Then it calls the executor it was given with
the clearance IT derived -- never the caller's object.

The dispatch ledger is shared by every gate for one world revision in this process.  It is a reservation, not the
budget owner's ledger: the owner's next statement of spent amounts arrives as a new world revision.  It decides no
science: a refusal here is an admissibility fact, never evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Mapping

from engcore.mind.repsem import canonical_bytes
from engcore.scientific import Quantity

from .actions import ExecutionKind, ProposedAction
from .base import WorldRefused, digest, magnitude_key, value_payload
from .domains import DiscreteLevels
from .feasibility import FeasibilityDecision, FeasibleActionSpace, canonical
from .world import ScientificWorld


class GateRefused(WorldRefused):
    """The execution gate refused a dispatch.  ``code`` says why; nothing was executed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class ClearedAction:
    """A proposal that cleared the check against one exact action space, with its resolved configuration.

    ``configuration`` is closed: every active control and every fixed condition, as typed values; the executor never
    fills a missing value.  A fixed condition carries the action's DECLARED value (a restatement in another spelling
    does not replace it), and a discrete control carries the DECLARED level it matched."""

    proposal: ProposedAction
    decision: FeasibilityDecision
    configuration: tuple[tuple[str, Any], ...]
    observe: tuple[str, ...]
    space_id: str

    @classmethod
    def of(cls, space: FeasibleActionSpace, proposal: ProposedAction, decision: FeasibilityDecision) -> "ClearedAction":
        spec = space.world.action(proposal.action_id)
        config = {f.name: f.value for f in spec.fixed_conditions}
        for name, value in proposal.assignments:
            if name in config:
                continue
            control = spec.control(name)
            if control is not None and isinstance(control.domain, DiscreteLevels) and isinstance(value, Quantity):
                value = next(lv for lv in control.domain.levels if magnitude_key(lv) == magnitude_key(value))
            config[name] = value
        observe = proposal.observe or spec.expected_observables
        return cls(proposal, decision, tuple(sorted(config.items())), tuple(observe), space.space_id)

    def settings_in_declared_units(self, world: Any) -> dict[str, Any]:
        """Quantities as magnitudes in each variable's declared unit (the sanctioned exit from the unit-aware world,
        ``Quantity.magnitude_in``), other typed values unchanged.  For an executor that takes plain numbers."""
        return {name: value.magnitude_in(world.variable(name).unit) if isinstance(value, Quantity) else value
                for name, value in self.configuration}

    def to_dict(self) -> dict[str, Any]:
        return {"proposal": self.proposal.to_dict(), "decision": self.decision.to_dict(),
                "configuration": [{"variable": n, "value": value_payload(v)} for n, v in self.configuration],
                "observe": list(self.observe), "space_id": self.space_id}


@dataclass
class _Ledger:
    dispatched: set[str] = field(default_factory=set)
    reserved: dict[str, float] = field(default_factory=dict)


class ExecutionGate:
    """Held by the execution owner.  Dispatches a cleared action to the executor it was given, or refuses."""

    _LEDGERS: ClassVar[dict[str, _Ledger]] = {}

    def __init__(self, space: FeasibleActionSpace, executor: Callable[[ClearedAction], Any], *,
                 provider_status: Callable[[str], Any] | None = None, model_registry: Any = None,
                 records: Mapping[str, Any] | None = None, allow_synthetic: bool = False) -> None:
        if not isinstance(space, FeasibleActionSpace):
            raise WorldRefused("a gate dispatches against one FeasibleActionSpace")
        if not callable(executor):
            raise WorldRefused("a gate is given an executor")
        world = ScientificWorld.from_dict(space.world.to_dict())          # the gate's own detached copy
        own = FeasibleActionSpace.build(world)
        if own.space_id != space.space_id:
            raise GateRefused("SPACE_NOT_REPRODUCED", "the action space does not rebuild from its world's payload")
        if world.synthetic and not allow_synthetic:
            raise GateRefused("SYNTHETIC_WORLD", "a world bound to synthetic fixtures is never executed")
        if not world.synthetic:
            world.verify_bindings(dict(records or {}))
        if any(a.execution is ExecutionKind.MODEL_EXECUTION for a in world.actions):
            if model_registry is None:
                raise GateRefused("MODELS_UNVERIFIED", "model execution needs the model registry to verify each "
                                                      "applicability binding against")
            world.verify_models(model_registry)
        self._world = world
        self._space = own
        self._executor = executor
        self._provider_status = provider_status
        self._ledger = self._LEDGERS.setdefault(world.revision_id, _Ledger())

    @property
    def space_id(self) -> str:
        return self._space.space_id

    def reserved(self) -> dict[str, float]:
        return dict(self._ledger.reserved)

    def dispatch(self, cleared: ClearedAction) -> Any:
        if type(cleared) is not ClearedAction:
            raise GateRefused("NOT_CLEARED", "only an exact ClearedAction is dispatched")
        if cleared.space_id != self._space.space_id:
            raise GateRefused("OTHER_SPACE", "the action was cleared against another action space")
        world = self._world
        if digest(world._material()) != world.content_digest:
            raise GateRefused("WORLD_TAMPERED", "the gate's world no longer matches its content digest")
        try:
            proposal = canonical(cleared.proposal)
        except WorldRefused as exc:
            raise GateRefused("NOT_CLEARED", str(exc)) from None
        decision = self._space.check(proposal)
        if not decision.feasible or canonical_bytes(decision.to_dict()) != canonical_bytes(cleared.decision.to_dict()):
            raise GateRefused("NOT_REPRODUCED", "the clearance does not reproduce against this action space")
        expected = ClearedAction.of(self._space, proposal, decision)
        if canonical_bytes(expected.to_dict()) != canonical_bytes(cleared.to_dict()):
            raise GateRefused("CONFIGURATION_TAMPERED", "the clearance is not the one this gate derives")
        if proposal.digest in self._ledger.dispatched:
            raise GateRefused("DUPLICATE_DISPATCH", "this proposal was already dispatched against this world revision")
        spec = world.action(proposal.action_id)
        charges = self._charges(world, spec)
        for dim, amount in charges.items():
            remaining = world.budget.remaining(dim)
            total = self._ledger.reserved.get(dim, 0.0) + amount
            ok = world.budget.cost.affordable(total, family=spec.family) if dim == "cost" else total <= remaining
            if not ok:
                raise GateRefused("OVER_BUDGET_RESERVED", f"{dim}: {total} reserved would exceed the {remaining} the "
                                                          "budget owner says remains for this world revision")
        for req in spec.provider_requirements:
            snap = world.provider(req.provider_id)
            if self._provider_status is None:
                raise GateRefused("PROVIDER_STATUS_UNAVAILABLE", "the gate reads provider builds from the provider "
                                                                 "authority, and none was given")
            live = self._provider_status(req.provider_id)
            if not (getattr(live, "available", False) and getattr(live, "version", None) == snap.version
                    == req.provider_version and getattr(live, "digest", None) == snap.build_digest):
                raise GateRefused("PROVIDER_BUILD_MISMATCH", f"the live {req.provider_id!r} build is not the one the "
                                                             "action was cleared against")
        self._ledger.dispatched.add(proposal.digest)
        for dim, amount in charges.items():
            self._ledger.reserved[dim] = self._ledger.reserved.get(dim, 0.0) + amount
        return self._executor(expected)

    @staticmethod
    def _charges(world: Any, spec: Any) -> dict[str, float]:
        out = {}
        for dim in ("experiments", "solver_calls", "cost", "wall_time"):
            if world.budget.status(dim) != "limited":
                continue
            amount = spec.estimated_duration if dim == "wall_time" else spec.cost(dim)
            out[dim] = magnitude_key(amount) if isinstance(amount, Quantity) else float(amount.value)
        return out


__all__ = ["ClearedAction", "ExecutionGate", "GateRefused"]
