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
    if problems:
        raise ResumeRefused("checkpoint refused: " + "; ".join(problems))
