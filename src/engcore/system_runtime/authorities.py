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
from .records import ApplicabilityReport, ArtifactRef, NodeAuthority, NodeCall, NodeOutcome, OutputValue, ProviderRecordRef, StateProposal
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


#: ``MultiphysicsRuntime.run`` arguments through which a scenario materially participates in a coupled run. The
#: runtime refuses any of them without a scenario digest. OD-27 is stricter inside a system execution: there every run
#: must name the authorized scenario, whether or not it uses any of these.
_SCENARIO_DRIVEN_RUN_ARGUMENTS = (
    "initial_state", "external_input_schedules", "operating_conditions", "scheduled_events",
    "termination_conditions", "quantities_of_interest",
)


def _authorized_scenario_digest(call: NodeCall) -> str:
    """The scenario this system execution is authorized for: the context's scenario, which preflight pins to the
    request by content digest (``CONTENT_DIGEST_MISMATCH``). Empty only when the context supplies no scenario."""
    scenario = getattr(getattr(call, "context", None), "scenario", None)
    return "" if scenario is None else str(scenario.digest).strip().lower()


def _scenario_refusal_before_run(kwargs: Mapping[str, Any], authorized: str) -> str:
    """Why the coupled run must not start under this call's scenario identity, or ''.

    OD-27: inside a system execution that has an authorized scenario, the run must name exactly that scenario --
    another one, or none, is refused before any participant executes (scenario identity is required and is not
    inferred; a runtime factory can carry scenario-derived state or inputs without leaving scenario evidence on
    the record, so the absence of evidence is no proof of independence). Only a call with no authorized scenario
    (no execution context) may run unbound, and then only without scenario-driven arguments.
    """
    supplied = str(kwargs.get("scenario_digest", "") or "").strip().lower()
    if authorized:
        if not supplied:
            return (f"the coupled run names no scenario digest, but this system execution is authorized for scenario "
                    f"{authorized[:12]}..; scenario identity is required and is not inferred, so nothing is run")
        if supplied != authorized:
            return (f"the coupled run would be bound to scenario {supplied[:12]}.., not the authorized scenario "
                    f"{authorized[:12]}.. of this system execution; nothing is run")
        return ""
    if supplied:
        return ("the coupled run names a scenario, but this execution supplies no authorized scenario to bind it to; "
                "nothing is run")
    driving = sorted(name for name in _SCENARIO_DRIVEN_RUN_ARGUMENTS if kwargs.get(name))
    if driving:
        return (f"the coupled run is driven by a scenario ({', '.join(driving)}) but no scenario is authorized or named; "
                f"nothing is run")
    return ""


def _scenario_refusal_after_run(run: Any, authorized: str) -> str:
    """Why a returned run record is not bound to this call's authorized scenario, or ''.

    Checked on the record itself, so a runtime that ignored, replaced or replayed the scenario it was given is
    caught whatever its arguments said: the run's digest must be the authorized one, and so must the digest every
    scenario-bound receipt in it carries (state transitions, scenario inputs, operating conditions, quantities of
    interest, termination) -- a record whose top-level digest was rewritten after construction is not admitted on
    that field alone. With no authorized scenario, only a record with no scenario identity and no scenario
    evidence is admitted.
    """
    bound = str(run.scenario_digest or "").strip().lower()
    receipts = (*run.state_transitions, *run.scenario_input_receipts, *run.operating_condition_receipts,
                *run.quantities_of_interest, *(() if run.termination is None else (run.termination,)))
    if authorized:
        if bound != authorized:
            return (f"the coupled run is bound to scenario {(bound or 'none')[:12]}.., not the authorized scenario "
                    f"{authorized[:12]}.. of this system execution; nothing is exposed")
        stray = sorted({str(item.scenario_digest).strip().lower() for item in receipts} - {authorized})
        if stray:
            return (f"the coupled run carries receipts bound to another scenario ({', '.join(d[:12] + '..' for d in stray)}); "
                    f"nothing is exposed")
        return ""
    if bound or any(str(item.scenario_digest).strip() for item in receipts):
        return "the coupled run is bound to a scenario, but this execution authorizes none; nothing is exposed"
    if (run.initial_state_receipts or run.scheduled_events or run.scenario_input_receipts
            or run.operating_condition_receipts or run.quantities_of_interest or run.termination is not None):
        return "the coupled run carries scenario evidence but no scenario identity; nothing is exposed"
    return ""


class MultiphysicsAuthority(_Base):
    """Delegates to a BIG 9 ``MultiphysicsRuntime``.  The coupling loop lives there and only there.

    ``run_kwargs(call)`` builds the runtime's ``run`` arguments (external inputs, initial coupling
    values, scenario digest, ...).  ``state_owners`` maps a PhysicsGraph participant to the system
    state owner whose values it receives (as ``initial_state``) and reports back (its final public
    state).  ``outputs`` maps a node output name to a key of the run's ``final_outputs``.

    Phase 1 BR7: a node succeeds only on a real run record of this call, of the declared graph and
    plan, whose required conservation held and whose typed outcome
    (:func:`~engcore.execution.multiphysics.runtime.assess_run_outcome`) is COMPLETED_EXPLICIT or
    CONVERGED.  The outcome is reported in the diagnostics and carried into every output's UNKNOWN
    uncertainty note; completion is never presented as convergence.

    OD-27: under a ``SystemExecutor`` (which always has an authorized scenario, pinned by preflight) ``run_kwargs``
    must pass ``scenario_digest`` equal to ``call.context.scenario.digest``. A run naming another scenario or none is
    refused before the runtime (or its factory) is touched, and the returned record -- its own digest and every
    scenario-bound receipt in it -- must name the same scenario before anything is exposed or committed.
    """

    def __init__(self, authority_id: str, runtime: Any = None, *, run_kwargs: Callable[[NodeCall], Mapping[str, Any]], outputs: Mapping[str, str],
                 state_owners: Mapping[str, str] | None = None, config: Mapping[str, Any] | None = None,
                 applicability: Callable[[Any, NodeCall], tuple[ApplicabilityReport, ...]] | None = None,
                 providers: Callable[[Any], tuple[ProviderRecordRef, ...]] | None = None,
                 graph: Any = None, plan: Any = None, runtime_factory: Callable[[NodeCall], Any] | None = None,
                 state_outputs: Mapping[str, tuple[str, str]] | None = None,
                 extractors: Mapping[str, Callable[[Any, NodeCall], Quantity]] | None = None,
                 artifacts: Callable[[Any, NodeCall], tuple[ArtifactRef, ...]] | None = None,
                 allow_mock_participants: bool = False) -> None:
        """Either a fixed ``runtime``, or ``graph`` + ``plan`` + ``runtime_factory(call)`` for a participant that must be built from the committed
        state (for example a cell constructed with its initial state of charge).  Identity covers the graph and plan fingerprints and ``config``."""
        if (runtime is None) == (runtime_factory is None):
            raise InvalidScientificProblem("give exactly one of a runtime or a runtime_factory")
        graph = runtime.graph if runtime is not None else graph
        plan = runtime.plan if runtime is not None else plan
        if graph is None or plan is None:
            raise InvalidScientificProblem("a runtime_factory needs the graph and plan whose fingerprints define its identity")
        self._init(authority_id, "multiphysics", {
            "graph": graph.fingerprint(), "plan": plan.fingerprint(), "outputs": dict(sorted(outputs.items())),
            "state_outputs": {k: list(v) for k, v in sorted((state_outputs or {}).items())},
            "extractors": sorted(extractors or {}), "artifacts": artifacts is not None,
            "state_owners": dict(sorted((state_owners or {}).items())), "config": dict(config or {}),
            # absent unless allowed: authorities that never admit mocks keep their identity
            **({"allow_mock_participants": True} if allow_mock_participants else {})})
        if not isinstance(allow_mock_participants, bool):
            raise InvalidScientificProblem("allow_mock_participants must be boolean")
        self._allow_mock = allow_mock_participants
        self._extractors, self._artifacts = dict(extractors or {}), artifacts
        self._graph_fingerprint = graph.fingerprint()
        self._plan_fingerprint = plan.fingerprint()
        self.runtime, self._factory, self._kwargs, self._outputs = runtime, runtime_factory, run_kwargs, dict(outputs)
        self._state_outputs = dict(state_outputs or {})
        self._owners, self._applicability, self._providers = dict(state_owners or {}), applicability, providers
        self.deterministic = False
        self.stateless = True

    def preflight_findings(self, node: Any, context: Any) -> tuple[tuple[str, str], ...]:
        missing = sorted(set(self._owners.values()) - set(node.visible_owners))
        return () if not missing else (("UNDECLARED_STATE_READ", f"the authority reads state owners {missing} that node {node.node_id!r} does not declare "
                                                                  "in reads_owners or writes_owners"),)

    def _initial_state(self, call: NodeCall) -> dict[str, dict[str, InitialStateValue]]:
        out: dict[str, dict[str, InitialStateValue]] = {}
        for participant, owner_id in sorted(self._owners.items()):
            try:
                out[participant] = _values_of(call.state.owner(owner_id))
            except KeyError:
                raise InvalidScientificProblem(f"system state has no owner {owner_id!r} for participant {participant!r}") from None
        return out

    @staticmethod
    def _untraced_external_providers(runtime: Any, records: tuple[ProviderRecordRef, ...], *,
                                     skip_mocks: bool = False) -> str:
        """Why an external provider inside the coupled run is untraceable, or ''.

        The executor already refuses a node that names provider bindings but
        reports no execution.  A coupled node can run external providers
        through ``ExternalSolverParticipant``s without naming any; then every
        admitted provider identity must appear among the reported provider
        records, or the node fails.  Nothing is derived here: an unreported
        provider is refused, never reconstructed.
        """
        from ..execution.multiphysics.external import ExternalSolverParticipant

        participants = getattr(runtime, "participants", None) or {}
        external = sorted(
            (pid, p.provider_identity) for pid, p in dict(participants).items()
            if isinstance(p, ExternalSolverParticipant) and not (skip_mocks and p.is_mock)
        )
        if not external:
            return ""
        reported = {(r.provider_id, r.provider_version) for r in records}
        missing = [f"{pid} ({ident.provider_id}@{ident.provider_version})" for pid, ident in external
                   if (ident.provider_id, ident.provider_version) not in reported]
        if missing:
            return (f"external provider participant(s) {missing} ran without a reported provider execution; "
                    f"an unreported provider is untraceable")
        return ""

    def execute(self, call: NodeCall) -> NodeOutcome:
        kwargs = dict(self._kwargs(call))
        if self._owners and self._factory is None and "initial_state" not in kwargs:
            kwargs["initial_state"] = self._initial_state(call)
        # OD-27: scenario identity is admitted before anything is built or run (a runtime factory has side effects),
        # and again on the returned record below
        authorized_scenario = _authorized_scenario_digest(call)
        refused = _scenario_refusal_before_run(kwargs, authorized_scenario)
        if refused:
            return NodeOutcome.failed(refused)
        runtime = self._factory(call) if self._factory is not None else self.runtime
        t0 = time.perf_counter()
        run_id = call.run_id + "." + call.node.node_id
        run = runtime.run(run_id, **kwargs)  # refusals raise: the executor records a FAILED node
        wall = time.perf_counter() - t0
        # F5 (fifth review): a run whose REQUIRED conservation failed in any window exposes nothing downstream.
        from ..execution.multiphysics.runtime import (
            CouplingRunOutcome,
            MultiphysicsExecutionError,
            assess_run_outcome,
            require_conservation,
        )
        from ..scientific.multiphysics.report import MultiphysicsRunRecord

        if not isinstance(run, MultiphysicsRunRecord):
            # Phase 1 BR7: what a window's outcome means is checked against the run's own plan and graph;
            # an object that is not a run record cannot show that (and a fixed runtime is no exception)
            return NodeOutcome.failed("the runtime returned no run record to check its graph, plan, outcome and conservation on")
        # evidence stays bound to the call it was produced for
        if run.run_id != run_id:
            return NodeOutcome.failed(f"the coupled run is {run.run_id!r}, not the run {run_id!r} this call requested")
        # Sixth review: the run must be of the graph this authority's identity names -- a factory that builds a
        # runtime on another graph (one without the declared balances) would otherwise pass the check vacuously.
        if run.graph_fingerprint != self._graph_fingerprint:
            return NodeOutcome.failed("the coupled run executed a different graph than the one this authority declares")
        # Seventh review: and the declared plan -- its convergence tolerances decide what "converged" means below.
        if run.plan_fingerprint != self._plan_fingerprint:
            return NodeOutcome.failed("the coupled run executed a different coupling plan than the one this authority declares")
        # OD-27: and the scenario this system execution is authorized for -- before conservation, outcome, outputs,
        # state, artifacts or provider records are read, so a run of another scenario exposes and commits nothing
        refused = _scenario_refusal_after_run(run, authorized_scenario)
        if refused:
            return NodeOutcome.failed(refused)
        try:
            require_conservation(run)
        except MultiphysicsExecutionError as exc:
            return NodeOutcome.failed(f"declared conservation did not hold; nothing is exposed ({exc})")
        # Phase 1 BR7: explicit and event-aligned windows complete a run; only an implicit run whose every window
        # satisfied every required interface is converged; anything else exposes nothing
        assessment = assess_run_outcome(run)
        if not assessment.completed:
            return NodeOutcome.failed(f"the coupled run did not complete; nothing is exposed ({'; '.join(assessment.problems)})")
        explicit = assessment.outcome is CouplingRunOutcome.COMPLETED_EXPLICIT
        # Phase 2 BR12: a mock external participant is never evidence that a real provider executed; it is
        # refused unless this authority explicitly admits mocks, and then it is labelled (it has no provider
        # record to trace, so only an admitted, labelled mock is exempt from the trace requirement below)
        from ..execution.multiphysics.external import ExternalSolverParticipant

        mocks = sorted(pid for pid, p in dict(getattr(runtime, "participants", None) or {}).items()
                       if isinstance(p, ExternalSolverParticipant) and p.is_mock)
        if mocks and not self._allow_mock:
            return NodeOutcome.failed(f"the coupled run used MOCK external participants {mocks}; a mock is not a "
                                      f"provider execution and this authority does not admit mocks")
        provider_records = () if self._providers is None else tuple(self._providers(run))
        untraced = self._untraced_external_providers(runtime, provider_records, skip_mocks=self._allow_mock)
        if untraced:
            return NodeOutcome.failed(untraced)
        outputs: dict[str, OutputValue] = {}
        for name, (participant, variable) in self._state_outputs.items():
            last = [t for t in run.state_transitions if t.participant_id == participant]
            match = [v for v in (last[-1].end_values if last else ()) if v.variable_id == variable]
            if not match:
                return NodeOutcome.failed(f"participant {participant!r} reported no public state {variable!r}")
            outputs[name] = OutputValue(match[0].value, match[0].uncertainty, f"multiphysics:{run.run_id}:{participant}.{variable}")
        coupling_note = ("explicit coupling: windows completed, no convergence claim, splitting error not quantified"
                         if explicit else "convergence is numerical, not uncertainty")
        if mocks:
            coupling_note += f"; produced with MOCK participants {mocks}, not by real providers"
        for name, key in self._outputs.items():
            if key not in run.final_outputs:
                return NodeOutcome.failed(f"coupled run produced no final output {key!r}")
            outputs[name] = OutputValue(Quantity.from_dict(run.final_outputs[key]), Uncertainty.unknown(
                f"coupled-run output: participants state no uncertainty; {coupling_note}"), f"multiphysics:{run.run_id}:{key}")
        for name, fn in self._extractors.items():   # scalars the caller derives from the run's own histories; uncertainty stays UNKNOWN
            outputs[name] = OutputValue(fn(run, call), Uncertainty.unknown(
                f"derived from the coupled run's histories: participants state no uncertainty; {coupling_note}"),
                f"multiphysics:{run.run_id}:derived:{name}")
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
                    new.append(InitialStateValue(item.variable_id, item.value.to(base.value.units), item.uncertainty))
                if {v.variable_id for v in new} != set(previous):
                    return NodeOutcome.failed(f"participant {participant!r} did not report every variable of owner {owner_id!r}")
                updates.append(OwnerState(owner_id, call.state.owner(owner_id).role, tuple(new)))
            proposal = StateProposal(run.ended_at, tuple(updates))
        return NodeOutcome(
            "succeeded", outputs, applicability=() if self._applicability is None else self._applicability(run, call), state_proposal=proposal,
            provider_records=provider_records, delegated_record_digest=digest_of(run.to_dict()),
            artifacts=() if self._artifacts is None else self._artifacts(run, call),
            resource_usage=ResourceUsage(wall_seconds=wall), diagnostics={"windows": str(len(run.windows)),
                                                                        "iterations": str(sum(len(w.iterations) for w in run.windows)),
                                                                        "coupling_outcome": assessment.outcome.value,
                                                                        **({"mock_participants": ",".join(mocks)} if mocks else {})})


class MultiscaleAuthority(_Base):
    """Delegates to a BIG 10 ``MultiTimescaleRuntime`` (representative windows, aggregation, degradation stay there)."""

    def __init__(self, authority_id: str, runtime: Any, *, initial_slow_state: Mapping[str, Mapping[str, InitialStateValue]],
                 initial_fast_state: Mapping[str, Mapping[str, InitialStateValue]] | None = None, extractors: Mapping[str, Callable[[Any], Quantity]],
                 slow_state_owners: Mapping[str, str] | None = None, until: Any = None, stages: Mapping[str, Mapping[str, Any]] | None = None,
                 config: Mapping[str, Any] | None = None,
                 applicability: Callable[[Any, NodeCall], tuple[ApplicabilityReport, ...]] | None = None,
                 providers: Callable[[Any], tuple[ProviderRecordRef, ...]] | None = None) -> None:
        self._init(authority_id, "multiscale", {
            "runtime": dict(sorted(runtime.identities().items())), "outputs": sorted(extractors), "until": None if until is None else str(until.seconds),
            "stages": {k: {"until": None if v.get("until") is None else str(v["until"].seconds), "resume": bool(v.get("resume")),
                           **({"from": str(v["from"])} if v.get("from") is not None else {})}
                       for k, v in sorted((stages or {}).items())},
            "initial_slow": digest_of([v.to_dict() for m in initial_slow_state.values() for v in m.values()]),
            "state_owners": dict(sorted((slow_state_owners or {}).items())), "config": dict(config or {})})
        self.runtime, self._slow, self._fast, self._extract = runtime, initial_slow_state, initial_fast_state, dict(extractors)
        self._until, self._owners, self._applicability, self._providers = until, dict(slow_state_owners or {}), applicability, providers
        self._stages = {k: dict(v) for k, v in (stages or {}).items()}
        self.deterministic = False
        self.stateless = False
        self.supports_checkpoint = True
        self._last_checkpoint: Mapping[str, Any] | None = None       # from a COMMITTED stage only
        self._last_origin: str | None = None                         # the node whose committed stage produced _last_checkpoint
        self._pending_checkpoint: Mapping[str, Any] | None = None    # from the stage being executed; promoted in committed()

    def committed(self, call: NodeCall, outcome: NodeOutcome) -> None:
        self._last_checkpoint = self._pending_checkpoint
        self._last_origin = call.node.node_id if self._pending_checkpoint is not None else None

    def preflight_findings(self, node: Any, context: Any) -> tuple[tuple[str, str], ...]:
        missing = sorted(set(self._owners.values()) - set(node.visible_owners))
        if missing:
            return (("UNDECLARED_STATE_READ", f"the authority reads state owners {missing} that node {node.node_id!r} does not declare "
                                              "in reads_owners or writes_owners"),)
        stage = self._stages.get(node.node_id)
        if not stage or not stage.get("resume"):
            return ()
        origin = stage.get("from")
        if origin is None:
            return (("INVALID_STAGE", f"resume stage {node.node_id!r} does not name the stage it continues ('from'); an unnamed source could be "
                                      "another run's checkpoint held by this authority instance"),)
        if origin not in node.depends_on:
            return (("INVALID_STAGE", f"resume stage {node.node_id!r} continues {origin!r} but does not depend on it, so it could run before that "
                                      "stage or after it was blocked"),)
        return ()

    def _state_mismatch(self, call: NodeCall, start: Mapping[str, Mapping[str, Any]]) -> str:
        """Why the committed system state is not the slow state ``start`` this run begins from ('' when it is).

        ``start`` is the authority's declared initial slow state for a fresh stage, and the macro checkpoint's slow state for a resume."""
        import math
        for domain, owner_id in sorted(self._owners.items()):
            declared = start.get(domain)
            if declared is None:
                return f"the authority declares no initial slow state for domain {domain!r}"
            try:
                current = _values_of(call.state.owner(owner_id))
            except KeyError:
                return f"system state has no owner {owner_id!r}"
            if set(current) != set(declared):
                return f"owner {owner_id!r} holds {sorted(current)}, the authority starts from {sorted(declared)}"
            for variable_id, initial in declared.items():
                try:
                    held = current[variable_id].value.to(initial.value.units).magnitude
                except Exception as exc:
                    return f"{owner_id}.{variable_id} is not comparable with the authority's initial value ({exc})"
                if not math.isclose(float(held), float(initial.value.magnitude), rel_tol=1e-12, abs_tol=0.0):
                    return f"{owner_id}.{variable_id} is {held} in the committed state but the authority's run starts from {initial.value.magnitude}"
        return ""

    def execute(self, call: NodeCall) -> NodeOutcome:
        from ..multiscale import MacroCheckpoint
        self._pending_checkpoint = None
        stage = self._stages.get(call.node.node_id, {"until": self._until, "resume": False})
        t0 = time.perf_counter()
        if stage.get("resume"):
            if self._last_checkpoint is None:
                return NodeOutcome.failed("this stage resumes from a macro checkpoint but none is held (it is never regenerated)")
            if stage.get("from") is None or self._last_origin != stage.get("from"):
                return NodeOutcome.failed(f"the held macro checkpoint comes from {self._last_origin!r}, not from the stage {stage.get('from')!r} "
                                          "this stage declares it continues")
            checkpoint = MacroCheckpoint.deserialize(self._last_checkpoint)
            mismatch = self._state_mismatch(call, checkpoint.slow_state)
            if mismatch:
                # another node changed the owner after the stage this one continues: resuming would commit over a state it never read
                return NodeOutcome.failed(f"the committed state is not the slow state the macro checkpoint continues from: {mismatch}")
            self.runtime.set_declared_fast_state(self._fast or {})
            record = self.runtime.resume(checkpoint, until=stage.get("until"))
        else:
            self._last_checkpoint = None      # a fresh run never inherits a checkpoint from an earlier run
            self._last_origin = None
            mismatch = self._state_mismatch(call, self._slow)
            if mismatch:
                # the run starts from the authority's own initial slow state; committing its end over a different state would
                # record a transition that was not derived from the state it claims to advance
                return NodeOutcome.failed(f"the committed state is not the state this multi-timescale run starts from: {mismatch}")
            record = self.runtime.run(initial_slow_state=self._slow, initial_fast_state=self._fast, until=stage.get("until"))
        wall = time.perf_counter() - t0
        if record.status not in ("completed", "paused"):
            return NodeOutcome.failed(f"multi-timescale run ended {record.status}: {record.reason}")
        until = stage.get("until")
        if record.status == "paused" and (until is None or record.reached.seconds < until.seconds):
            return NodeOutcome.failed("the multi-timescale run paused before the instant this stage requested; a short run is not exposed as complete")
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
            self._pending_checkpoint = record.last_valid_checkpoint.serialize()
        return NodeOutcome(
            "succeeded", outputs, applicability=() if self._applicability is None else self._applicability(record, call), state_proposal=proposal,
            provider_records=() if self._providers is None else self._providers(record), delegated_record_digest=record.digest,
            resource_usage=ResourceUsage(wall_seconds=wall), authority_checkpoint=(digest_of(self._pending_checkpoint or {"none": True}), self._pending_checkpoint is not None),
            diagnostics={"status": record.status, "accounting": str(sorted(dict(record.accounting).items()))})

    def checkpoint_payload(self) -> Mapping[str, Any] | None:
        return self._last_checkpoint

    def restore(self, payload: Mapping[str, Any]) -> None:
        self._last_checkpoint = dict(payload)
        self._last_origin = None           # set by restored_from(); a payload of unknown origin is never resumed

    def restored_from(self, node_id: str) -> None:
        """The executor names the checkpointed node whose payload it just restored."""
        self._last_origin = node_id
