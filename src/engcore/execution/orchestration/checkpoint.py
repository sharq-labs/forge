from __future__ import annotations
from dataclasses import dataclass
import re

_SHA256=re.compile(r"^[0-9a-f]{64}$")

@dataclass(frozen=True)
class CheckpointReference:
    """A resume point of ONE solver.

    ``solver_id`` names the solver whose state the checkpoint holds; empty means
    the producer was not recorded.  A checkpoint is solver state, not a neutral
    physical state: the runners route it back only to the solver that produced
    it and never resume an unbound checkpoint.
    """

    checkpoint_id:str
    state_digest:str
    solver_id:str=""

    def __post_init__(self)->None:
        cid=str(self.checkpoint_id).strip()
        digest=str(self.state_digest).strip().lower()
        if not cid or not _SHA256.fullmatch(digest):
            raise ValueError("checkpoint requires id and lowercase SHA-256 state_digest")
        object.__setattr__(self,"checkpoint_id",cid)
        object.__setattr__(self,"state_digest",digest)
        object.__setattr__(self,"solver_id",str(self.solver_id).strip())


#: The only attempt states whose checkpoint is a valid continuation point; a
#: failed, diverged or non-terminal (planned/running) attempt never supplies one.
_USABLE_STATES=frozenset({"converged","cancelled"})


def adopt_checkpoint(checkpoint:object,*,solver_id:str,state:object)->tuple[CheckpointReference|None,str]:
    """Bind an attempt's checkpoint to the solver that returned it, or say why it is discarded.

    Returns ``(bound_checkpoint, "")`` or ``(None, problem)``.  Only a converged
    or cancelled attempt supplies a resume point, and a checkpoint naming a
    solver other than the one that returned it is refused.
    """
    if checkpoint is None:
        return None,""
    state_name=str(getattr(state,"value",state))
    if not isinstance(checkpoint,CheckpointReference):
        return None,f"{solver_id}:checkpoint_not_a_reference"
    if state_name not in _USABLE_STATES:
        return None,f"{solver_id}:checkpoint_of_{state_name}_attempt_discarded"
    if checkpoint.solver_id and checkpoint.solver_id!=solver_id:
        return None,f"{solver_id}:checkpoint_names_solver_{checkpoint.solver_id}_refused"
    if checkpoint.solver_id==solver_id:
        return checkpoint,""
    return CheckpointReference(checkpoint.checkpoint_id,checkpoint.state_digest,solver_id),""


def resume_owner(checkpoint:object)->str|None:
    """The solver a caller's resume checkpoint belongs to; refuses one that names none.

    A resume checkpoint is the requested initial state of a continuation.  An
    unbound one cannot be routed to any solver, and silently starting cold
    instead would replace that initial state with a backend default.
    """
    if checkpoint is None:
        return None
    if not isinstance(checkpoint,CheckpointReference):
        raise ValueError("resume checkpoint must be a CheckpointReference")
    if not checkpoint.solver_id:
        raise ValueError(
            f"resume checkpoint {checkpoint.checkpoint_id!r} does not name the solver whose state it holds; "
            "it cannot be resumed by any solver and is not silently replaced by a cold start"
        )
    return checkpoint.solver_id


def resume_point_for(checkpoint:CheckpointReference|None,solver_id:str)->CheckpointReference|None:
    """The checkpoint ``solver_id`` may resume from: only one it produced itself."""
    if checkpoint is None or checkpoint.solver_id!=solver_id:
        return None
    return checkpoint
