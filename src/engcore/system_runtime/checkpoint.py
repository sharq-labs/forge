"""Resume safety: a checkpoint resumes only into exactly the context it came from.

``verify_checkpoint`` refuses a resume after ANY change to what the run means: the request, the plan,
the system, scenario, timeline, environment, materials, the initial state, an authority's identity,
or a provider's version/build.  It also refuses an incomplete checkpoint (an authority that did not
declare its state complete) and a checkpoint whose completed nodes are not dependency-closed or whose
node definitions changed.  Agreement between a resumed and an uninterrupted run is reproducibility,
never validation.
"""

from __future__ import annotations

from typing import Any

from ..scientific.errors import InvalidScientificProblem
from .plan import SystemExecutionPlan
from .request import SystemRunRequest
from .result import SystemCheckpoint


class ResumeRefused(InvalidScientificProblem):
    """A checkpoint cannot be resumed into this context."""


def verify_checkpoint(checkpoint: SystemCheckpoint, request: SystemRunRequest, plan: SystemExecutionPlan,
                      current_context: tuple[tuple[str, str], ...], context: Any) -> None:
    problems: list[str] = []
    if not isinstance(checkpoint, SystemCheckpoint):
        raise ResumeRefused("resume takes a SystemCheckpoint (deserialize and verify the payload first)")
    if checkpoint.request_digest != request.digest:
        problems.append("the request changed")
    if checkpoint.plan_digest != plan.digest:
        problems.append("the plan changed")
    old, new = dict(checkpoint.context_digests), dict(current_context)
    for key in sorted(set(old) | set(new)):
        if old.get(key) != new.get(key):
            problems.append(f"{key} changed")
    if not checkpoint.complete:
        problems.append(f"checkpoint is incomplete: {checkpoint.incomplete_reason}")
    if checkpoint.state.request_digest != request.digest or checkpoint.state.system_digest != request.system.digest:
        problems.append("the checkpoint state belongs to another request or system")
    completed = {r.node_id for r in checkpoint.completed_receipts}
    plan_ids = {n.node_id for n in plan.nodes}
    if not completed <= plan_ids:
        problems.append(f"checkpoint completed unknown nodes {sorted(completed - plan_ids)}")
    else:
        for receipt in checkpoint.completed_receipts:
            node = plan.node(receipt.node_id)
            if receipt.node_digest != node.digest:
                problems.append(f"node {receipt.node_id!r} definition changed")
            if not set(node.depends_on) <= completed:
                problems.append(f"completed node {receipt.node_id!r} has uncompleted dependencies {sorted(set(node.depends_on) - completed)}")
        committed = [r for r in checkpoint.completed_receipts if r.state_after_digest]
        if committed and committed[-1].state_after_digest not in {s.digest for s in checkpoint.state_history}:
            problems.append("a committed state named by a receipt is missing from the state history")
    for cp in checkpoint.authority_checkpoints:
        if cp.node_id in plan_ids and plan.node(cp.node_id).authority.identity_digest != cp.identity_digest:
            problems.append(f"authority of {cp.node_id!r} has another identity than the checkpoint recorded")
    # a checkpoint that is merely self-consistent is not enough: it must be the state chain THIS request produces
    from .state import SystemState
    expected_initial = SystemState.initial(request.initial_state, request_digest=request.digest, system_digest=request.system.digest,
                                           environment_digest="" if request.environment is None else request.environment.digest)
    if checkpoint.state_history[0].digest != expected_initial.digest:
        problems.append("the state history does not start from this request's initial state")
    order = {n.node_id: i for i, n in enumerate(plan.nodes)}
    committed = sorted((r for r in checkpoint.completed_receipts if r.state_after_digest and r.node_id in order), key=lambda r: order[r.node_id])
    tip = committed[-1].state_after_digest if committed else expected_initial.digest
    if checkpoint.state.digest != tip:
        problems.append("the checkpoint state is not the state after the last committed node")
    # the state history must be exactly the chain the completed committing nodes produced: nothing dropped, nothing reordered
    history = checkpoint.state_history
    if len(history) != 1 + len(committed):
        problems.append(f"the state history has {len(history)} states but {len(committed)} committing nodes completed (a commit was dropped or invented)")
    else:
        for i, receipt in enumerate(committed):
            if receipt.state_before_digest != history[i].digest or receipt.state_after_digest != history[i + 1].digest or history[i + 1].produced_by != receipt.node_id:
                problems.append(f"the state history disagrees with the receipt of committing node {receipt.node_id!r}")
    for receipt in checkpoint.completed_receipts:
        if receipt.node_id in order and receipt.status.value == "succeeded" and plan.node(receipt.node_id).commits_state != bool(receipt.state_after_digest):
            problems.append(f"node {receipt.node_id!r} commits_state does not match whether its receipt committed a state")
    by_node = {r.node_id: r for r in checkpoint.completed_receipts}
    listed = {cp.node_id for cp in checkpoint.authority_checkpoints}
    for cp in checkpoint.authority_checkpoints:
        if not isinstance(cp.declared_complete, bool):
            problems.append(f"the completeness declaration of {cp.node_id!r} is not a boolean")
        receipt = by_node.get(cp.node_id)
        if receipt is None:
            problems.append(f"the authority checkpoint of {cp.node_id!r} belongs to no completed node")
            continue
        if receipt.authority_checkpoint is None:
            # the authority declared no state: the checkpoint may then carry none (an arbitrary payload could not be checked against anything)
            if cp.payload is not None:
                problems.append(f"the authority checkpoint of {cp.node_id!r} carries a payload its receipt never declared")
            continue
        if receipt.authority_checkpoint[0] != cp.payload_digest:
            problems.append(f"the authority payload of {cp.node_id!r} is not the one its receipt recorded")
        if bool(receipt.authority_checkpoint[1]) != cp.declared_complete:
            problems.append(f"the completeness declaration of {cp.node_id!r} differs from its receipt")
    # a stateful authority that completed a node must have declared its state: deleting its entry would resume a fresh instance
    for receipt in checkpoint.completed_receipts:
        if receipt.node_id in order and receipt.status.value == "succeeded" and receipt.node_id not in listed and not plan.node(receipt.node_id).derived:
            try:
                authority = context.authorities.resolve(plan.node(receipt.node_id).authority)
            except Exception:
                continue
            if not authority.stateless:
                problems.append(f"completed node {receipt.node_id!r} runs a stateful authority but the checkpoint carries no declaration for it")
    if not isinstance(checkpoint.complete, bool):
        problems.append("the checkpoint's completeness flag is not a boolean")
    elif checkpoint.complete != all(cp.declared_complete for cp in checkpoint.authority_checkpoints):
        problems.append("the checkpoint's completeness flag does not follow from its authority declarations")
    if problems:
        raise ResumeRefused("checkpoint refused: " + "; ".join(problems))
