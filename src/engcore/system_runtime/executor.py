"""The generic executor: runs a plan's nodes through their authorities.

What it does, and refuses to do:

* runs nodes in the plan's topological order and delegates every computation to the authority the
  plan pins (id AND identity digest); it contains no physics and no domain branch;
* a node whose dependency did not SUCCEED is BLOCKED and names the root cause; independent
  branches still run (unless the request forbids partial results);
* a failed or refused node exposes no output and never advances state;
* every output is stamped with (run, plan, node, execution identity); a consumer re-verifies the
  stamp and the output digest, so a value from another run, another node, a changed state or a
  tampered store is refused instead of consumed;
* state advances only after the node succeeded, its outputs and provider records were validated,
  and every declared runtime applicability check reported ``within`` on the SOLVED state. A
  violated or UNKNOWN check refuses the node and the previous state stays authoritative;
* exact reuse (optional) only for a byte-identical execution identity, only for authorities that
  declare themselves deterministic, and only of successful outcomes;
* nothing here validates anything.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any, Callable, Mapping

from ..execution.orchestration.resources import ResourceBudget, ResourceUsage
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import Uncertainty, UncertaintyKind
from ..scientific.units.quantity import Quantity
from ._common import digest_of
from .plan import BUILTIN_CONSTRAINT, BUILTIN_ENVIRONMENT, BUILTIN_MATERIAL, PlanNode, SystemExecutionPlan, compile_plan, spread_unit
from .preflight import PreflightReport, PreflightStatus, preflight
from .records import (
    ApplicabilityReport, ArtifactRef, AuthorityMismatch, InputValue, NodeAuthority, NodeCall, NodeOutcome, NodeReceipt, NodeStatus,
    OutputValue, ProviderRecordRef, RuntimeContext,
)
from .request import SystemRunRequest
from .result import (
    Availability, AuthorityCheckpoint, ObservableResult, RunStatus, SystemCheckpoint, SystemRunResult, TrustInputs,
)
from .state import OwnerState, ProviderCheckpointRef, SystemState


# ----------------------------------------------------------------------------------------- built-in authorities
class _Builtin(NodeAuthority):
    deterministic = True
    stateless = True

    def __init__(self, ref: Any) -> None:
        self.authority_id, self.kind, self.identity_digest = ref.authority_id, ref.kind, ref.identity_digest


class _EnvironmentAuthority(_Builtin):
    def execute(self, call: NodeCall) -> NodeOutcome:
        from ..scenarios.timeline import TimePoint
        env = call.context.environment
        if env is None:
            return NodeOutcome.refused("no environment was supplied")
        at = Quantity.from_dict(__import__("json").loads(call.node.arg("at")))
        value = env.channel_value(call.node.arg("channel"), TimePoint(env.timeline.basis.basis_id, at))
        if value.status.value != "known" or value.value is None:
            return NodeOutcome.refused(f"environment channel {call.node.arg('channel')!r} is UNKNOWN at {at}: {value.reason or 'no reason stated'}")
        return NodeOutcome(
            "succeeded",
            {"value": OutputValue(value.value.value, Uncertainty.unknown("environment channel value: its source states no uncertainty"),
                                  f"environment:{env.digest[:16]}:{call.node.arg('channel')}")},
            diagnostics={"derivation": value.derivation.value, "source": value.source_id, "source_classification": str(value.source_classification)})


class _MaterialAuthority(_Builtin):
    def execute(self, call: NodeCall) -> NodeOutcome:
        prop = call.context.resolved_properties.get(call.node.arg("resolved_digest"))
        if prop is None or prop.status != "known" or prop.value is None:
            return NodeOutcome.refused("resolved material property is unavailable or UNKNOWN; it is never defaulted")
        return NodeOutcome(
            "succeeded",
            {"value": OutputValue(prop.value.value, Uncertainty.unknown("resolved material property: no uncertainty carried by the record"),
                                  f"material:{prop.derivation.value}:{call.node.arg('resolved_digest')[:16]}")},
            diagnostics={"derivation": prop.derivation.value, "origins": ",".join(prop.origins)})


class _ConstraintAuthority(_Builtin):
    def execute(self, call: NodeCall) -> NodeOutcome:
        definition = call.context.constraints.get(call.node.arg("constraint_digest"))
        if definition is None:
            return NodeOutcome.refused("constraint definition was not supplied")
        check = definition.check(call.value("observed"))
        unit = call.node.outputs[0].unit
        margin = Quantity(check.margin.magnitude_as_spread_in(unit), unit)
        return NodeOutcome(
            "succeeded",
            {"margin": OutputValue(margin, Uncertainty.unknown("constraint margin: the observed value's uncertainty is not propagated by this runtime"),
                                   f"constraint:{call.node.arg('constraint_id')}")},
            diagnostics={"satisfied": str(check.satisfied).lower(), "constraint": call.node.arg("constraint_id"), "binding": call.node.arg("binding")})


def _builtin_for(node: PlanNode) -> NodeAuthority | None:
    return {BUILTIN_ENVIRONMENT.authority_id: _EnvironmentAuthority, BUILTIN_MATERIAL.authority_id: _MaterialAuthority,
            BUILTIN_CONSTRAINT.authority_id: _ConstraintAuthority}.get(node.authority.authority_id, lambda ref: None)(node.authority)


# ----------------------------------------------------------------------------------------------- exact reuse cache
class ExecutionCache:
    """Exact-identity reuse of SUCCEEDED outcomes.  A hit is the original computation, never new evidence."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[NodeOutcome, str]] = {}
        self.hits = 0

    def get(self, identity: str) -> tuple[NodeOutcome, str] | None:
        return self._items.get(identity)

    def put(self, identity: str, outcome: NodeOutcome, receipt_digest: str) -> None:
        if outcome.status == "succeeded":
            self._items[identity] = (outcome, receipt_digest)

    def __len__(self) -> int:
        return len(self._items)


def output_stamp(run_id: str, plan_digest: str, node_id: str, execution_identity: str) -> str:
    return digest_of({"run_id": run_id, "plan": plan_digest, "node": node_id, "execution": execution_identity})


def _roots(status: dict[str, NodeStatus], blocked_by: dict[str, tuple[str, ...]], deps: tuple[str, ...]) -> tuple[str, ...]:
    roots: set[str] = set()
    for dep in deps:
        if status[dep] is NodeStatus.BLOCKED:
            roots.update(blocked_by[dep])
        elif status[dep] is not NodeStatus.SUCCEEDED:
            roots.add(dep)
    return tuple(sorted(roots))


class SystemExecutor:
    def __init__(self, context: RuntimeContext, *, cache: ExecutionCache | None = None, clock: Callable[[], float] = time.perf_counter) -> None:
        self.context = context
        self.cache = cache
        self._clock = clock

    # ------------------------------------------------------------------------------------------------- public
    def run(self, request: SystemRunRequest, *, plan: SystemExecutionPlan | None = None, run_id: str | None = None,
            stop_after: str | None = None, resume: SystemCheckpoint | None = None) -> SystemRunResult:
        plan = plan if plan is not None else compile_plan(request)
        report = preflight(request, plan, self.context)
        if resume is not None:
            run_id = resume.run_id if run_id is None else run_id
        run_id = run_id or f"run-{request.digest[:12]}"
        if report.status is PreflightStatus.REFUSED:
            return self._refused(request, plan, report, run_id)
        if stop_after is not None and stop_after not in {n.node_id for n in plan.nodes}:
            raise InvalidScientificProblem(f"stop_after names unknown node {stop_after!r}")
        env_digest = "" if request.environment is None else request.environment.digest
        if resume is None:
            state = SystemState.initial(request.initial_state, request_digest=request.digest, system_digest=request.system.digest,
                                        environment_digest=env_digest)
            history = [state]
            store: dict[str, tuple[dict[str, OutputValue], NodeReceipt]] = {}
            authority_cps: dict[str, AuthorityCheckpoint] = {}
        else:
            if run_id != resume.run_id:
                raise InvalidScientificProblem("a resumed run keeps the run id of the checkpoint it continues")
            state, history, store, authority_cps = self._restore(request, plan, resume)

        statuses: dict[str, NodeStatus] = {n.node_id: NodeStatus.PENDING for n in plan.nodes}
        blocked_by: dict[str, tuple[str, ...]] = {}
        receipts: dict[str, NodeReceipt] = {}
        for node_id, (_, receipt) in store.items():
            statuses[node_id] = NodeStatus.SUCCEEDED
            receipts[node_id] = receipt
        checkpoints: list[SystemCheckpoint] = []
        usage = ResourceUsage()
        budget = request.operational.resource_budget
        started = self._clock()
        stopped = False
        failed_any = False
        commit_tainted = False     # a state-committing node did not succeed: later commits would build on a state that node was meant to advance
        if stop_after is not None and stop_after in store:
            raise InvalidScientificProblem(f"stop_after names {stop_after!r}, which the resumed checkpoint already completed")

        for node in plan.nodes:
            if node.node_id in store:
                continue
            if stopped:
                break
            failed_deps = tuple(d for d in node.depends_on if statuses[d] is not NodeStatus.SUCCEEDED)
            if failed_deps:
                roots = _roots(statuses, blocked_by, node.depends_on)
                statuses[node.node_id] = NodeStatus.BLOCKED
                blocked_by[node.node_id] = roots
                receipts[node.node_id] = self._receipt(node, plan, request, NodeStatus.BLOCKED, state.digest, "", f"blocked by {list(roots)}",
                                                      blocked_by=roots, run_id=run_id)
                commit_tainted = commit_tainted or node.commits_state
                continue
            if node.commits_state and commit_tainted:
                statuses[node.node_id] = NodeStatus.BLOCKED
                blocked_by[node.node_id] = ("an earlier state-committing node did not succeed; committing on a state it was meant to advance is refused",)
                receipts[node.node_id] = self._receipt(node, plan, request, NodeStatus.BLOCKED, state.digest, "", "an earlier state-committing node did not succeed",
                                                      blocked_by=blocked_by[node.node_id], run_id=run_id)
                continue
            if failed_any and not plan.allow_partial:
                statuses[node.node_id] = NodeStatus.BLOCKED
                blocked_by[node.node_id] = ("partial results are not allowed and an earlier node did not succeed",)
                receipts[node.node_id] = self._receipt(node, plan, request, NodeStatus.BLOCKED, state.digest, "", "partial results not allowed",
                                                      blocked_by=blocked_by[node.node_id], run_id=run_id)
                continue
            if budget is not None and budget.max_wall_seconds is not None and self._clock() - started > budget.max_wall_seconds:
                statuses[node.node_id] = NodeStatus.REFUSED
                receipts[node.node_id] = self._receipt(node, plan, request, NodeStatus.REFUSED, state.digest, "", "wall-time budget exhausted before this node",
                                                      run_id=run_id)
                failed_any = True
                continue

            status, receipt, outputs, new_state, cp = self._run_node(node, plan, request, state, store, run_id, attempt=1)
            statuses[node.node_id] = status
            receipts[node.node_id] = receipt
            usage = usage.plus(receipt.resource_usage)
            if status is NodeStatus.SUCCEEDED:
                store[node.node_id] = (outputs, receipt)
                if cp is not None:
                    authority_cps[node.node_id] = cp
                if new_state is not None:
                    state = new_state
                    history.append(state)
                if node.node_id in plan.checkpoint_after or node.node_id == stop_after:
                    checkpoints.append(self._checkpoint(request, plan, run_id, state, history, store, authority_cps))
                if node.node_id == stop_after:
                    stopped = True
            else:
                failed_any = True
                commit_tainted = commit_tainted or node.commits_state

        return self._assemble(request, plan, report, run_id, statuses, blocked_by, receipts, store, history, checkpoints, usage, stopped)

    # ------------------------------------------------------------------------------------------- node execution
    def _authority(self, node: PlanNode) -> NodeAuthority:
        builtin = _builtin_for(node)
        return builtin if builtin is not None else self.context.authorities.resolve(node.authority)

    def _run_node(self, node: PlanNode, plan: SystemExecutionPlan, request: SystemRunRequest, state: SystemState,
                  store: dict[str, tuple[dict[str, OutputValue], NodeReceipt]], run_id: str, attempt: int):
        def fail(kind: NodeStatus, reason: str, identity: str = "", inputs=(), authority_digest: str = "", **kw):
            return kind, self._receipt(node, plan, request, kind, state.digest, "", reason, identity=identity, inputs=inputs,
                                       authority_digest=authority_digest, run_id=run_id, attempt=attempt, **kw), {}, None, None

        try:
            authority = self._authority(node)
        except AuthorityMismatch as exc:
            return fail(NodeStatus.REFUSED, str(exc))

        # 1. inputs: only verified outputs of nodes that succeeded in THIS run
        values: dict[str, InputValue] = {}
        for item in node.inputs:
            held = store.get(item.source_node)
            if held is None:
                return fail(NodeStatus.FAILED, f"input {item.name!r}: producer {item.source_node!r} has no committed output", authority_digest=authority.identity_digest)
            produced, producer_receipt = held
            problem = self._verify_stored(plan, run_id, item.source_node, produced, producer_receipt)
            if problem:
                return fail(NodeStatus.FAILED, f"input {item.name!r}: {problem}", authority_digest=authority.identity_digest)
            output = produced.get(item.source_output)
            if output is None:
                return fail(NodeStatus.FAILED, f"input {item.name!r}: producer {item.source_node!r} has no output {item.source_output!r}", authority_digest=authority.identity_digest)
            try:
                converted = output.value.to(item.unit)
            except Exception as exc:
                return fail(NodeStatus.FAILED, f"input {item.name!r}: cannot express {output.value} as {item.unit!r} ({exc})", authority_digest=authority.identity_digest)
            values[item.name] = InputValue(item.name, converted, output.uncertainty, item.source_node, item.source_output, producer_receipt.stamp,
                                           producer_receipt.execution_identity_digest)
        for lit in node.literals:
            values[lit.name] = InputValue(lit.name, lit.value, lit.uncertainty, f"literal:{node.node_id}", lit.name, digest_of(lit.to_dict()),
                                          digest_of(lit.to_dict()))
        input_digests = tuple(sorted((name, v.digest) for name, v in values.items()))
        identity = digest_of({"node": node.digest, "authority": authority.identity_digest, "inputs": input_digests, "state": state.digest})

        # 2. exact reuse (deterministic authorities, identical identity, successes only)
        hit = None
        call = None
        reusable = authority.deterministic and authority.stateless        # a stateful authority must execute so its own state advances
        if self.cache is not None and plan.cache_policy == "exact" and reusable:
            hit = self.cache.get(identity)
        t0 = self._clock()
        if hit is not None:
            outcome, original = hit
            self.cache.hits += 1
            cache_meta = {"cache_hit": True, "original_receipt_digest": original}
        else:
            call = NodeCall(node, values, state, run_id, plan.digest, request.digest, attempt, self.context)
            try:
                outcome = authority.execute(call)
            except Exception as exc:  # an exception is a failed execution and exposes nothing
                return fail(NodeStatus.FAILED, f"{type(exc).__name__}: {exc}", identity=identity, inputs=input_digests, authority_digest=authority.identity_digest,
                            resource=ResourceUsage(wall_seconds=max(0.0, self._clock() - t0)))
            if not isinstance(outcome, NodeOutcome):
                return fail(NodeStatus.FAILED, "authority returned something other than a NodeOutcome", identity=identity, inputs=input_digests,
                            authority_digest=authority.identity_digest)
            cache_meta = {}
        wall = max(0.0, self._clock() - t0)
        usage = outcome.resource_usage if outcome.resource_usage.wall_seconds else replace(outcome.resource_usage, wall_seconds=wall)
        kw = dict(identity=identity, inputs=input_digests, authority_digest=authority.identity_digest, resource=usage, **cache_meta)

        if outcome.status != "succeeded":
            return fail(NodeStatus.REFUSED if outcome.status == "refused" else NodeStatus.FAILED, outcome.reason, **kw)

        # 3. validate what the authority claims
        declared = {o.name: o.unit for o in node.outputs}
        if set(outcome.outputs) != set(declared):
            return fail(NodeStatus.FAILED, f"outputs {sorted(outcome.outputs)} differ from the declared {sorted(declared)}", **kw)
        converted_outputs: dict[str, OutputValue] = {}
        for name, output in outcome.outputs.items():
            if not isinstance(output, OutputValue):
                return fail(NodeStatus.FAILED, f"output {name!r} is not an OutputValue", **kw)
            try:
                value = output.value.to(declared[name])
            except Exception as exc:
                return fail(NodeStatus.FAILED, f"output {name!r} is not expressible in {declared[name]!r} ({exc})", **kw)
            converted_outputs[name] = OutputValue(value, output.uncertainty, output.origin)
        if any(v.uncertainty.kind is UncertaintyKind.UNKNOWN for v in values.values()) and not authority.accounts_for_input_uncertainty:
            claimed = sorted(n for n, o in converted_outputs.items() if o.uncertainty.kind is not UncertaintyKind.UNKNOWN)
            if claimed:
                return fail(NodeStatus.FAILED, f"outputs {claimed} claim a quantified uncertainty although an input's uncertainty is UNKNOWN and the authority does not "
                                              f"declare that it accounts for its inputs (UNKNOWN in, UNKNOWN out)", **kw)
        problem = self._check_providers(node, request, outcome)
        if problem:
            return fail(NodeStatus.FAILED, problem, **kw)
        if authority.supports_checkpoint and outcome.authority_checkpoint is None:
            return fail(NodeStatus.FAILED, "the authority supports checkpointing but reported no state declaration (its checkpoint could not be verified on resume)", **kw)
        statuses_by_check: dict[str, set[str]] = {}
        for a in outcome.applicability:
            statuses_by_check.setdefault(a.check_id, set()).add(a.status)
        conflicting = sorted(c for c, s in statuses_by_check.items() if len(s) > 1)
        if conflicting:
            return fail(NodeStatus.FAILED, f"the authority reported conflicting applicability statuses for {conflicting} (a check cannot be both established and not)", **kw)
        reported = {a.check_id: a for a in outcome.applicability}
        for check_id in node.applicability_checks:
            item = reported.get(check_id)
            if item is None or item.status == "unknown":
                return fail(NodeStatus.REFUSED, f"runtime applicability check {check_id!r} was not established on the solved state (UNKNOWN never passes)",
                            applicability=outcome.applicability, **kw)
        for item in outcome.applicability:
            if item.status == "outside":
                return fail(NodeStatus.REFUSED, f"the solved state left applicability ({item.check_id}: {item.reason or 'outside declared bounds'}); the step is not committed",
                            applicability=outcome.applicability, **kw)

        # 4. state proposal: validated fully BEFORE anything is committed
        new_state = None
        if node.commits_state:
            proposal = outcome.state_proposal
            if proposal is None:
                return fail(NodeStatus.FAILED, "node declares commits_state but proposed no state", **kw)
            scenario = self.context.scenario
            try:
                proposed_s = proposal.time.magnitude_in("second")
                if scenario is not None and proposed_s > scenario.end.magnitude_in("second") + 1e-9:
                    return fail(NodeStatus.FAILED, f"proposed state time {proposed_s} s lies beyond the scenario end", **kw)
            except Exception as exc:
                return fail(NodeStatus.FAILED, f"proposed state time is not a valid time ({exc})", **kw)
            owners = {u.owner_id for u in proposal.updates}
            if not owners <= set(node.writes_owners):
                return fail(NodeStatus.FAILED, f"state proposal writes {sorted(owners - set(node.writes_owners))}, which the node is not allowed to write", **kw)
            if not authority.accounts_for_input_uncertainty:
                inputs_unknown = any(v.uncertainty.kind is UncertaintyKind.UNKNOWN for v in values.values())
                claimed_state = []
                for update in proposal.updates:
                    try:
                        previous = {v.variable_id: v for v in state.owner(update.owner_id).values}
                    except Exception:
                        previous = {}
                    for v in update.values:
                        was_unknown = v.variable_id not in previous or previous[v.variable_id].uncertainty.kind is UncertaintyKind.UNKNOWN
                        if v.uncertainty.kind is not UncertaintyKind.UNKNOWN and (inputs_unknown or was_unknown):
                            claimed_state.append(f"{update.owner_id}.{v.variable_id}")
                if claimed_state:
                    return fail(NodeStatus.FAILED, f"state values {sorted(claimed_state)} claim a quantified uncertainty although an input or the value they replace is UNKNOWN "
                                                  f"and the authority does not declare that it accounts for it (UNKNOWN in, UNKNOWN out)", **kw)
            try:
                new_state = state.advance(time=proposal.time, updates=proposal.updates, produced_by=node.node_id,
                                          provider_checkpoints=proposal.provider_checkpoints)
            except InvalidScientificProblem as exc:
                return fail(NodeStatus.FAILED, f"state proposal refused: {exc}", **kw)
        elif outcome.state_proposal is not None:
            return fail(NodeStatus.FAILED, "node proposed state but does not declare commits_state", **kw)

        stamp = output_stamp(run_id, plan.digest, node.node_id, identity)
        receipt = self._receipt(node, plan, request, NodeStatus.SUCCEEDED, state.digest, "" if new_state is None else new_state.digest, "", identity=identity,
                                inputs=input_digests, authority_digest=authority.identity_digest, resource=usage, outputs=converted_outputs,
                                provider_records=outcome.provider_records, applicability=outcome.applicability, artifacts=outcome.artifacts,
                                delegated=outcome.delegated_record_digest, checkpoint=outcome.authority_checkpoint, stamp=stamp, run_id=run_id,
                                attempt=attempt, **cache_meta)
        if self.cache is not None and hit is None and reusable and plan.cache_policy == "exact":
            self.cache.put(identity, outcome, receipt.digest)
        if hit is None and call is not None:
            authority.committed(call, outcome)      # only now may an authority promote pending internal state
        cp = None
        if node.checkpointable or authority.supports_checkpoint:
            payload = authority.checkpoint_payload() if authority.supports_checkpoint else None
            cp = AuthorityCheckpoint(node.node_id, authority.authority_id, authority.identity_digest, payload,
                                     bool(outcome.authority_checkpoint[1]) if outcome.authority_checkpoint else authority.stateless)
        elif not authority.stateless:
            cp = AuthorityCheckpoint(node.node_id, authority.authority_id, authority.identity_digest, None, False)
        return NodeStatus.SUCCEEDED, receipt, converted_outputs, new_state, cp

    def _check_providers(self, node: PlanNode, request: SystemRunRequest, outcome: NodeOutcome) -> str:
        allowed = [b for b in request.provider_bindings if b.binding_id in node.provider_binding_ids]
        if allowed and not outcome.provider_records:
            return f"node {node.node_id!r} names provider bindings {sorted(node.provider_binding_ids)} but reported no provider execution (an unreported provider is untraceable)"
        for ref in outcome.provider_records:
            candidates = [b for b in allowed if b.provider_id == ref.provider_id]
            if not candidates:
                return f"provider {ref.provider_id!r} executed but the request authorised none for node {node.node_id!r} (no substitute provider)"
            if not any(b.provider_version == ref.provider_version and (not b.provider_digest or b.provider_digest == ref.provider_digest) for b in candidates):
                versions = sorted({b.provider_version for b in candidates})
                return (f"provider {ref.provider_id!r} executed at version {ref.provider_version!r}"
                        f"{'' if ref.provider_digest else ' (no build digest)'}; no authorising binding matches (requires {versions} and any pinned build)")
            if not ref.succeeded:
                return f"provider {ref.provider_id!r} reports a failed execution but the node claims success"
        return ""

    def _verify_stored(self, plan: SystemExecutionPlan, run_id: str, node_id: str, outputs: Mapping[str, OutputValue], receipt: NodeReceipt) -> str:
        if receipt.node_id != node_id or receipt.status is not NodeStatus.SUCCEEDED:
            return f"stored output for {node_id!r} is not a SUCCEEDED receipt of that node (stale or foreign)"
        if receipt.plan_digest != plan.digest:
            return f"stored output for {node_id!r} belongs to another plan"
        if receipt.stamp != output_stamp(run_id, plan.digest, node_id, receipt.execution_identity_digest):
            return f"stored output for {node_id!r} belongs to another run or execution"
        if tuple(sorted((n, v.digest) for n, v in outputs.items())) != receipt.output_digests:
            return f"stored output for {node_id!r} does not match its receipt (modified after execution)"
        return ""

    def _receipt(self, node: PlanNode, plan: SystemExecutionPlan, request: SystemRunRequest, status: NodeStatus, before: str, after: str, reason: str, *,
                 identity: str = "", inputs=(), authority_digest: str = "", resource: ResourceUsage | None = None,
                 outputs: Mapping[str, OutputValue] | None = None, provider_records=(), applicability=(), artifacts=(), delegated: str = "",
                 checkpoint=None, stamp: str = "", blocked_by=(), run_id: str = "", attempt: int = 1, cache_hit: bool = False,
                 original_receipt_digest: str = "") -> NodeReceipt:
        outputs = outputs or {}
        return NodeReceipt(
            node.node_id, status, plan.digest, request.digest, node.digest, authority_digest or node.authority.identity_digest, identity, tuple(inputs),
            tuple(sorted((n, v.digest) for n, v in outputs.items())), tuple(provider_records), tuple(applicability), tuple(artifacts), before, after,
            resource or ResourceUsage(), reason, tuple(blocked_by), attempt, delegated, cache_hit, original_receipt_digest, checkpoint, stamp)

    # ------------------------------------------------------------------------------------- checkpoint / resume
    def _context_digests(self, request: SystemRunRequest, plan: SystemExecutionPlan, nodes: set[str]) -> tuple[tuple[str, str], ...]:
        pairs = [("system", request.system.digest), ("scenario", request.scenario.digest), ("timeline", request.timeline.digest),
                 ("environment", "" if request.environment is None else request.environment.digest), ("initial_state", request.initial_state.digest)]
        pairs += [(f"material:{m.ref_id}", m.digest) for m in request.materials]
        for node in plan.nodes:
            pairs.append((f"authority:{node.node_id}", node.authority.identity_digest))
        if self.context.providers is not None:
            for binding in request.provider_bindings:
                try:
                    status = self.context.providers.status(binding.provider_id)
                    pairs.append((f"provider:{binding.provider_id}", f"{status.version}:{status.digest}"))
                except Exception:
                    pairs.append((f"provider:{binding.provider_id}", "unavailable"))
        return tuple(sorted(pairs))

    def _checkpoint(self, request: SystemRunRequest, plan: SystemExecutionPlan, run_id: str, state: SystemState, history: list[SystemState],
                    store: dict[str, tuple[dict[str, OutputValue], NodeReceipt]], authority_cps: dict[str, AuthorityCheckpoint]) -> SystemCheckpoint:
        reasons: list[str] = []
        for node_id in store:
            cp = authority_cps.get(node_id)
            if cp is not None and not cp.declared_complete:
                reasons.append(f"authority of {node_id!r} did not declare its state complete")
        return SystemCheckpoint(
            request.digest, plan.digest, run_id, state, tuple(history), tuple(sorted((r for _, r in store.values()), key=lambda r: r.node_id)),
            {node: dict(out) for node, (out, _) in store.items()}, tuple(sorted(authority_cps.values(), key=lambda c: c.node_id)),
            self._context_digests(request, plan, set(store)), not reasons, "; ".join(reasons))

    def _restore(self, request: SystemRunRequest, plan: SystemExecutionPlan, checkpoint: SystemCheckpoint):
        from .checkpoint import verify_checkpoint
        verify_checkpoint(checkpoint, request, plan, self._context_digests(request, plan, set()), self.context)
        store = {r.node_id: (dict(checkpoint.outputs[r.node_id]), r) for r in checkpoint.completed_receipts}
        for receipt in checkpoint.completed_receipts:
            problem = self._verify_stored(plan, checkpoint.run_id, receipt.node_id, store[receipt.node_id][0], receipt)
            if problem:
                raise InvalidScientificProblem(f"checkpoint refused: {problem}")
        cps = {c.node_id: c for c in checkpoint.authority_checkpoints}
        for node in plan.nodes:              # plan (= execution) order, so an authority shared by several nodes ends on its LATEST checkpoint
            cp = cps.get(node.node_id) if node.node_id in store else None
            if cp is not None and cp.payload is not None:
                self._authority(node).restore(cp.payload)
        return checkpoint.state, list(checkpoint.state_history), store, cps

    # ---------------------------------------------------------------------------------------------- assembly
    def _refused(self, request: SystemRunRequest, plan: SystemExecutionPlan, report: PreflightReport, run_id: str) -> SystemRunResult:
        reason = "; ".join(f"{f.code}: {f.message}" for f in report.blocking)
        observables = tuple(ObservableResult(o.observable_id, o.node_id, o.output_name, o.unit, Availability.REFUSED, None, (o.node_id,),
                                             ("preflight",), f"preflight refused: {reason}") for o in plan.observables)
        return SystemRunResult(
            request.digest, plan.digest, run_id, RunStatus.REFUSED, report, plan, None, None, (), (), {}, observables, (), (), (), ResourceUsage(), (),
            self._provenance(request), TrustInputs("refused", (), (), (), tuple(sorted(n.node_id for n in plan.nodes if n.applicability_waiver))))

    def _provenance(self, request: SystemRunRequest) -> tuple[tuple[str, str], ...]:
        pairs = [("system", request.system.digest), ("scenario", request.scenario.digest), ("timeline", request.timeline.digest),
                 ("initial_state", request.initial_state.digest)]
        if request.environment is not None:
            pairs.append(("environment", request.environment.digest))
        pairs += [(f"material:{m.ref_id}", m.digest) for m in request.materials]
        pairs += [(f"provider_binding:{b.binding_id}", f"{b.provider_id}@{b.provider_version}") for b in request.provider_bindings]
        return tuple(sorted(pairs))

    def _assemble(self, request, plan, report, run_id, statuses, blocked_by, receipts, store, history, checkpoints, usage, stopped) -> SystemRunResult:
        observables: list[ObservableResult] = []
        for o in plan.observables:
            path = (*plan.ancestors(o.node_id), o.node_id)
            status = statuses[o.node_id]
            if status is NodeStatus.SUCCEEDED:
                value = store[o.node_id][0][o.output_name]
                observables.append(ObservableResult(o.observable_id, o.node_id, o.output_name, o.unit, Availability.AVAILABLE,
                                                    OutputValue(value.value.to(o.unit), value.uncertainty, value.origin), path, (), ""))
            elif status is NodeStatus.BLOCKED:
                observables.append(ObservableResult(o.observable_id, o.node_id, o.output_name, o.unit, Availability.BLOCKED, None, path,
                                                    blocked_by[o.node_id], f"blocked by {list(blocked_by[o.node_id])}"))
            elif status is NodeStatus.REFUSED:
                observables.append(ObservableResult(o.observable_id, o.node_id, o.output_name, o.unit, Availability.REFUSED, None, path, (o.node_id,),
                                                    receipts[o.node_id].reason))
            elif status is NodeStatus.FAILED:
                observables.append(ObservableResult(o.observable_id, o.node_id, o.output_name, o.unit, Availability.FAILED, None, path, (o.node_id,),
                                                    receipts[o.node_id].reason))
            else:
                observables.append(ObservableResult(o.observable_id, o.node_id, o.output_name, o.unit, Availability.UNKNOWN, None, path, (o.node_id,),
                                                    "the node has not executed (the run stopped at a checkpoint)"))
        for node in plan.nodes:  # pending nodes need a receipt too, so "one receipt per plan node" stays true
            if node.node_id not in receipts:
                receipts[node.node_id] = self._receipt(node, plan, request, NodeStatus.PENDING, history[-1].digest, "", "not executed (run stopped at a checkpoint)")
        available = [o for o in observables if o.availability is Availability.AVAILABLE]
        if stopped and any(s is NodeStatus.PENDING for s in statuses.values()):
            run_status = RunStatus.PAUSED
        elif len(available) == len(observables) and all(s is NodeStatus.SUCCEEDED for s in statuses.values()):
            run_status = RunStatus.SUCCEEDED
        elif available:
            run_status = RunStatus.PARTIAL
        else:
            run_status = RunStatus.FAILED
        outputs = {node: dict(out) for node, (out, _) in store.items()}
        ordered = tuple(receipts[n.node_id] for n in plan.nodes)
        provider_refs = tuple(sorted({p for r in ordered for p in r.provider_records}))
        artifacts = tuple(sorted((r.node_id, a) for r in ordered for a in r.artifacts))
        unknown_unc = tuple(sorted(f"{n}.{k}" for n, items in outputs.items() for k, v in items.items() if v.uncertainty.kind is UncertaintyKind.UNKNOWN))
        applic = tuple(sorted((r.node_id, a.check_id, a.status) for r in ordered for a in r.applicability))
        trust = TrustInputs(run_status.value, unknown_unc, applic, tuple(sorted({p.execution_identity_digest for p in provider_refs})),
                            tuple(sorted(n.node_id for n in plan.nodes if n.applicability_waiver)))
        return SystemRunResult(
            request.digest, plan.digest, run_id, run_status, report, plan, history[0], history[-1], tuple(history), ordered, outputs, tuple(observables),
            provider_refs, artifacts, (), usage, tuple(checkpoints), self._provenance(request), trust)
