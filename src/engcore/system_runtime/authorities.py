"""Authority adapters: how a node delegates to something that already exists.

None of these contain a solver, a coupling loop or a lifecycle rule.  They translate between the
generic node contract (:class:`NodeCall` -> :class:`NodeOutcome`) and:

* :class:`CallbackAuthority` - any in-process computation (also the unit-test double);
* :class:`ProviderAuthority` - one BIG 11 provider execution returning a ``ProviderExecutionRecord``;
* :class:`MultiphysicsAuthority` - the BIG 9 ``MultiphysicsRuntime`` (the coupling loop stays there);
* :class:`MultiscaleAuthority` - the BIG 10 ``MultiTimescaleRuntime`` (long-horizon logic stays there).

Every adapter states its result's uncertainty explicitly (UNKNOWN unless the delegated record
carries something else) and reports which providers actually executed, so the executor can refuse
a provider the request did not authorise.
"""

from __future__ import annotations

import time
from fractions import Fraction
from typing import Any, Callable, Mapping

from ..execution.orchestration.resources import ResourceUsage
from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics.state import InitialStateValue
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity
from ._common import digest_of, identifier
from .plan import PlanNode
from .records import ApplicabilityReport, NodeAuthority, NodeCall, NodeOutcome, OutputValue, ProviderRecordRef, StateProposal
from .request import AuthorityRef
from .state import OwnerState


class _Base(NodeAuthority):
    def _init(self, authority_id: str, kind: str, identity_payload: Mapping[str, Any]) -> None:
        self.authority_id = identifier(authority_id, "authority id")
        self.kind = identifier(kind, "authority kind")
        self.identity_digest = digest_of({"authority": self.authority_id, "kind": self.kind, "identity": identity_payload})

    @property
    def ref(self) -> AuthorityRef:
        return AuthorityRef(self.authority_id, self.kind, self.identity_digest)


class CallbackAuthority(_Base):
    """An in-process computation.  ``config`` is what makes it *this* computation (it is part of identity)."""

    def __init__(self, authority_id: str, fn: Callable[[NodeCall], NodeOutcome], *, config: Mapping[str, Any] | None = None, kind: str = "callback",
                 deterministic: bool = False, stateless: bool = True) -> None:
        self._init(authority_id, kind, {"config": dict(config or {})})
        self._fn = fn
        self.deterministic = deterministic
        self.stateless = stateless

    def execute(self, call: NodeCall) -> NodeOutcome:
        return self._fn(call)


def scalar_outputs(record: Any, mapping: Mapping[str, str]) -> dict[str, OutputValue]:
    """Node outputs from a provider record's scalars: ``{output name: scalar key}``.  A missing scalar is an error."""
    out: dict[str, OutputValue] = {}
    for name, key in mapping.items():
        if key not in record.scalars:
            raise InvalidScientificProblem(f"provider record has no scalar {key!r} (a missing output is never a default)")
        out[name] = OutputValue(record.scalars[key], record.uncertainty, f"provider:{record.identity.provider_id}@{record.identity.provider_version}")
    return out


class ProviderAuthority(_Base):
    """One provider execution per node.  ``solve(call)`` returns a ``ProviderExecutionRecord``; the provider is used only if the request bound it."""

    def __init__(self, authority_id: str, registry: Any, provider_id: str, solve: Callable[[NodeCall], Any], output_map: Mapping[str, str], *,
                 config: Mapping[str, Any] | None = None, applicability: Callable[[Any, NodeCall], tuple[ApplicabilityReport, ...]] | None = None,
                 state_proposal: Callable[[Any, NodeCall], StateProposal | None] | None = None) -> None:
        status = registry.status(provider_id)
        self._init(authority_id, "provider", {"provider": provider_id, "version": status.version, "digest": status.digest,
                                              "outputs": dict(sorted(output_map.items())), "config": dict(config or {})})
        self._solve, self._map, self._applicability, self._proposal = solve, dict(output_map), applicability, state_proposal
        self.deterministic = False
        self.stateless = True

    def execute(self, call: NodeCall) -> NodeOutcome:
        record = self._solve(call)
        ref = ProviderRecordRef.of_record(record)
        if not record.succeeded:
            return NodeOutcome.failed(record.reason, provider_records=(ref,))
        return NodeOutcome(
            "succeeded", scalar_outputs(record, self._map), provider_records=(ref,), delegated_record_digest=record.digest,
            applicability=() if self._applicability is None else self._applicability(record, call),
            state_proposal=None if self._proposal is None else self._proposal(record, call),
            diagnostics={"provider_metrics": str(sorted(dict(record.metrics).items()))})


def _values_of(owner: OwnerState) -> dict[str, InitialStateValue]:
    return {v.variable_id: v for v in owner.values}


class MultiphysicsAuthority(_Base):
    """Delegates to a BIG 9 ``MultiphysicsRuntime``.  The coupling loop lives there and only there.

    ``run_kwargs(call)`` builds the runtime's ``run`` arguments (external inputs, initial coupling
    values, scenario digest, ...).  ``state_owners`` maps a PhysicsGraph participant to the system
    state owner whose values it receives (as ``initial_state``) and reports back (its final public
    state).  ``outputs`` maps a node output name to a key of the run's ``final_outputs``.
    """

    def __init__(self, authority_id: str, runtime: Any, *, run_kwargs: Callable[[NodeCall], Mapping[str, Any]], outputs: Mapping[str, str],
                 state_owners: Mapping[str, str] | None = None, config: Mapping[str, Any] | None = None,
                 applicability: Callable[[Any, NodeCall], tuple[ApplicabilityReport, ...]] | None = None,
                 providers: Callable[[Any], tuple[ProviderRecordRef, ...]] | None = None) -> None:
        self._init(authority_id, "multiphysics", {
            "graph": runtime.graph.fingerprint(), "plan": runtime.plan.fingerprint(), "outputs": dict(sorted(outputs.items())),
            "state_owners": dict(sorted((state_owners or {}).items())), "config": dict(config or {})})
        self.runtime, self._kwargs, self._outputs = runtime, run_kwargs, dict(outputs)
        self._owners, self._applicability, self._providers = dict(state_owners or {}), applicability, providers
        self.deterministic = False
        self.stateless = True

    def _initial_state(self, call: NodeCall) -> dict[str, dict[str, InitialStateValue]]:
        out: dict[str, dict[str, InitialStateValue]] = {}
        for participant, owner_id in sorted(self._owners.items()):
            try:
                out[participant] = _values_of(call.state.owner(owner_id))
            except KeyError:
                raise InvalidScientificProblem(f"system state has no owner {owner_id!r} for participant {participant!r}") from None
        return out

    def execute(self, call: NodeCall) -> NodeOutcome:
        kwargs = dict(self._kwargs(call))
        if self._owners and "initial_state" not in kwargs:
            kwargs["initial_state"] = self._initial_state(call)
        t0 = time.perf_counter()
        run = self.runtime.run(call.run_id + "." + call.node.node_id, **kwargs)  # refusals raise: the executor records a FAILED node
        wall = time.perf_counter() - t0
        outputs: dict[str, OutputValue] = {}
        for name, key in self._outputs.items():
            if key not in run.final_outputs:
                return NodeOutcome.failed(f"coupled run produced no final output {key!r}")
            outputs[name] = OutputValue(Quantity.from_dict(run.final_outputs[key]), Uncertainty.unknown(
                "coupled-run output: participants state no uncertainty; convergence is numerical, not uncertainty"), f"multiphysics:{run.run_id}:{key}")
        if any(w.outcome.value != "converged" for w in run.windows):
            return NodeOutcome.failed("a coupling window did not converge; nothing is exposed")
        proposal = None
        if call.node.commits_state:
            updates = []
            for participant, owner_id in sorted(self._owners.items()):
                last = [t for t in run.state_transitions if t.participant_id == participant]
                if not last or not last[-1].end_values:
                    return NodeOutcome.failed(f"participant {participant!r} reported no public end state for owner {owner_id!r}")
                previous = _values_of(call.state.owner(owner_id))
                new = []
                for item in last[-1].end_values:
                    base = previous.get(item.variable_id)
                    if base is None:
                        return NodeOutcome.failed(f"participant reported unknown state variable {item.variable_id!r}")
                    new.append(InitialStateValue(item.variable_id, item.value.to(base.value.units), base.uncertainty))
                if {v.variable_id for v in new} != set(previous):
                    return NodeOutcome.failed(f"participant {participant!r} did not report every variable of owner {owner_id!r}")
                updates.append(OwnerState(owner_id, call.state.owner(owner_id).role, tuple(new)))
            proposal = StateProposal(run.ended_at, tuple(updates))
        return NodeOutcome(
            "succeeded", outputs, applicability=() if self._applicability is None else self._applicability(run, call), state_proposal=proposal,
            provider_records=() if self._providers is None else self._providers(run), delegated_record_digest=digest_of(run.to_dict()),
            resource_usage=ResourceUsage(wall_seconds=wall), diagnostics={"windows": str(len(run.windows)),
                                                                        "iterations": str(sum(len(w.iterations) for w in run.windows))})


class MultiscaleAuthority(_Base):
    """Delegates to a BIG 10 ``MultiTimescaleRuntime`` (representative windows, aggregation, degradation stay there)."""

    def __init__(self, authority_id: str, runtime: Any, *, initial_slow_state: Mapping[str, Mapping[str, InitialStateValue]],
                 initial_fast_state: Mapping[str, Mapping[str, InitialStateValue]] | None = None, extractors: Mapping[str, Callable[[Any], Quantity]],
                 slow_state_owners: Mapping[str, str] | None = None, until: Any = None, config: Mapping[str, Any] | None = None,
                 applicability: Callable[[Any, NodeCall], tuple[ApplicabilityReport, ...]] | None = None,
                 providers: Callable[[Any], tuple[ProviderRecordRef, ...]] | None = None) -> None:
        self._init(authority_id, "multiscale", {
            "runtime": dict(sorted(runtime.identities().items())), "outputs": sorted(extractors), "until": None if until is None else str(until.seconds),
            "initial_slow": digest_of([v.to_dict() for m in initial_slow_state.values() for v in m.values()]),
            "state_owners": dict(sorted((slow_state_owners or {}).items())), "config": dict(config or {})})
        self.runtime, self._slow, self._fast, self._extract = runtime, initial_slow_state, initial_fast_state, dict(extractors)
        self._until, self._owners, self._applicability, self._providers = until, dict(slow_state_owners or {}), applicability, providers
        self.deterministic = False
        self.stateless = False
        self.supports_checkpoint = True
        self._last_checkpoint: Mapping[str, Any] | None = None

    def execute(self, call: NodeCall) -> NodeOutcome:
        t0 = time.perf_counter()
        record = self.runtime.run(initial_slow_state=self._slow, initial_fast_state=self._fast, until=self._until)
        wall = time.perf_counter() - t0
        if record.status not in ("completed", "paused"):
            return NodeOutcome.failed(f"multi-timescale run ended {record.status}: {record.reason}")
        outputs = {name: OutputValue(fn(record), Uncertainty.unknown("multi-timescale output: uncertainty is not quantified; see the approximation ledger"),
                                     f"multiscale:{record.run_id}:{name}") for name, fn in self._extract.items()}
        proposal = None
        if call.node.commits_state:
            updates = []
            for domain, owner_id in sorted(self._owners.items()):
                final = record.final_slow_state.get(domain) if hasattr(record.final_slow_state, "get") else None
                if not final:
                    return NodeOutcome.failed(f"no final slow state for domain {domain!r}")
                previous = _values_of(call.state.owner(owner_id))
                new = tuple(InitialStateValue(v.variable_id, v.value.to(previous[v.variable_id].value.units), v.uncertainty) for v in final.values())
                updates.append(OwnerState(owner_id, call.state.owner(owner_id).role, new))
            proposal = StateProposal(record.reached.quantity, tuple(updates))
        if record.last_valid_checkpoint is not None:
            self._last_checkpoint = record.last_valid_checkpoint.to_dict()
        return NodeOutcome(
            "succeeded", outputs, applicability=() if self._applicability is None else self._applicability(record, call), state_proposal=proposal,
            provider_records=() if self._providers is None else self._providers(record), delegated_record_digest=record.digest,
            resource_usage=ResourceUsage(wall_seconds=wall), authority_checkpoint=(digest_of(self._last_checkpoint or {"none": True}), self._last_checkpoint is not None),
            diagnostics={"status": record.status, "accounting": str(sorted(dict(record.accounting).items()))})

    def checkpoint_payload(self) -> Mapping[str, Any] | None:
        return self._last_checkpoint

    def restore(self, payload: Mapping[str, Any]) -> None:
        self._last_checkpoint = dict(payload)
