from __future__ import annotations
from dataclasses import dataclass
import re

_SHA256=re.compile(r"^[0-9a-f]{64}$")

@dataclass(frozen=True)
class CheckpointReference:
    """A resume point of ONE solver build, for ONE problem.

    ``solver_id`` names the solver whose state the checkpoint holds; empty means
    the producer was not recorded.  A checkpoint is solver state, not a neutral
    physical state: the runners route it back only to the solver that produced
    it and never resume an unbound checkpoint.

    Phase 2 BR10: ``solver_build`` (the producing build: version and content
    digest, as the backend states it) and ``problem_digest`` (the canonical
    problem it was produced for) bind it further.  Empty means not recorded; a
    resume that would need a recorded value and finds none is refused as
    ambiguous rather than assumed compatible.
    """

    checkpoint_id:str
    state_digest:str
    solver_id:str=""
    solver_build:str=""
    problem_digest:str=""

    def __post_init__(self)->None:
        cid=str(self.checkpoint_id).strip()
        digest=str(self.state_digest).strip().lower()
        if not cid or not _SHA256.fullmatch(digest):
            raise ValueError("checkpoint requires id and lowercase SHA-256 state_digest")
        object.__setattr__(self,"checkpoint_id",cid)
        object.__setattr__(self,"state_digest",digest)
        object.__setattr__(self,"solver_id",str(self.solver_id).strip())
        object.__setattr__(self,"solver_build",str(self.solver_build).strip())
        problem=str(self.problem_digest).strip().lower()
        if problem and not _SHA256.fullmatch(problem):
            raise ValueError("checkpoint problem_digest must be a lowercase SHA-256 digest")
        object.__setattr__(self,"problem_digest",problem)


@dataclass(frozen=True)
class CheckpointConversion:
    """A QUALIFIED conversion of one solver build's state into another's (Phase 2 BR10).

    A checkpoint is not portable between numerical solvers: their states are
    different discretisations, variables and internal histories.  Restoring one
    solver's state into another is allowed only through a declared conversion
    whose qualification says why the converted state is a valid initial state
    of the target, and only into a backend that declares it accepts converted
    state.  Without one, a fallback solver cold-starts from the admitted problem.
    Checkpoint portability is this contract; it is not implied by two solvers
    accepting the same problem (interoperability).
    """

    conversion_id:str
    source_solver:str
    source_build:str
    target_solver:str
    target_build:str
    qualification:str

    def __post_init__(self)->None:
        for label in ("conversion_id","source_solver","source_build","target_solver","target_build","qualification"):
            value=str(getattr(self,label)).strip()
            if not value:
                raise ValueError(f"checkpoint conversion requires {label}; an unstated build or basis is not a qualification")
            object.__setattr__(self,label,value)
        if (self.source_solver,self.source_build)==(self.target_solver,self.target_build):
            raise ValueError("a checkpoint conversion converts between two different solver builds")


#: The only attempt states whose checkpoint is a valid continuation point; a
#: failed, diverged or non-terminal (planned/running) attempt never supplies one.
_USABLE_STATES=frozenset({"converged","cancelled"})


def adopt_checkpoint(checkpoint:object,*,solver_id:str,state:object,solver_build:str="",
                     problem_digest:str="")->tuple[CheckpointReference|None,str]:
    """Bind an attempt's checkpoint to the solver build and problem that returned it, or say why it is discarded.

    Returns ``(bound_checkpoint, "")`` or ``(None, problem)``.  Only a converged
    or cancelled attempt supplies a resume point; a checkpoint naming another
    solver, another build or another problem than the one that returned it is
    refused.
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
    build=str(solver_build).strip()
    if checkpoint.solver_build and build and checkpoint.solver_build!=build:
        return None,f"{solver_id}:checkpoint_names_build_{checkpoint.solver_build}_not_{build}_refused"
    problem=str(problem_digest).strip().lower()
    if checkpoint.problem_digest and problem and checkpoint.problem_digest!=problem:
        return None,f"{solver_id}:checkpoint_of_another_problem_refused"
    if not build or not problem:
        return None,f"{solver_id}:checkpoint_missing_execution_build_or_problem_refused"
    bound=CheckpointReference(checkpoint.checkpoint_id,checkpoint.state_digest,solver_id,
                              checkpoint.solver_build or build,checkpoint.problem_digest or problem)
    return (checkpoint if bound==checkpoint else bound),""


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


def resume_refusal(checkpoint:CheckpointReference,*,solver_build:str="",problem_digest:str="")->str:
    """Why ``checkpoint`` cannot be resumed by its own solver at this build for this problem ('' when it can).

    Both sides must name the exact build and problem. Legacy records remain
    readable, but missing bindings never authorize execution. Producer-backed
    migration or an explicit cold start is required; current context cannot
    retroactively supply the identity of an old checkpoint.
    """
    build=str(solver_build).strip()
    problem=str(problem_digest).strip().lower()
    if not checkpoint.solver_build:
        return f"checkpoint {checkpoint.checkpoint_id!r} states no producing build"
    if not checkpoint.problem_digest:
        return f"checkpoint {checkpoint.checkpoint_id!r} states no producing problem"
    if checkpoint.solver_build and not build:
        return f"checkpoint {checkpoint.checkpoint_id!r} was produced by build {checkpoint.solver_build!r}; the backend states no build"
    if checkpoint.solver_build and build!=checkpoint.solver_build:
        return f"checkpoint {checkpoint.checkpoint_id!r} was produced by build {checkpoint.solver_build!r}, not {build!r}"
    if checkpoint.problem_digest and not problem:
        return f"checkpoint {checkpoint.checkpoint_id!r} names its problem; the plan states none"
    if checkpoint.problem_digest and problem!=checkpoint.problem_digest:
        return f"checkpoint {checkpoint.checkpoint_id!r} was produced for another problem"
    return ""


def resume_point_for(checkpoint:CheckpointReference|None,solver_id:str,*,solver_build:str="",
                     problem_digest:str="")->CheckpointReference|None:
    """The checkpoint ``solver_id`` (at ``solver_build``, for ``problem_digest``) may resume from.

    Only one it produced itself: same solver, and -- when the checkpoint
    records them -- the same build and the same problem.  Anything else is None
    (a cold start); :func:`resume_refusal` says why.
    """
    if checkpoint is None or checkpoint.solver_id!=solver_id:
        return None
    return checkpoint if not resume_refusal(checkpoint,solver_build=solver_build,problem_digest=problem_digest) else None


def converted_resume_point(checkpoint:CheckpointReference|None,*,solver_id:str,solver_build:str,
                           conversions:tuple[CheckpointConversion,...],accepts_converted:bool,
                           problem_digest:str=""
                           )->tuple[CheckpointReference|None,CheckpointConversion|None]:
    """Another solver's checkpoint for ``solver_id``, through a declared qualified conversion only.

    Returns ``(checkpoint, conversion)`` when one applies; ``(None, None)`` means
    cold start.  Never applies without both builds recorded, and never into a
    backend that does not declare it accepts converted state.
    """
    if checkpoint is None or checkpoint.solver_id==solver_id or not accepts_converted:
        return None,None
    if not checkpoint.solver_build or not str(solver_build).strip():
        return None,None
    if not problem_digest or checkpoint.problem_digest != str(problem_digest).strip().lower():
        return None,None
    for conversion in conversions:
        if (conversion.source_solver,conversion.source_build,conversion.target_solver,conversion.target_build)==(
                checkpoint.solver_id,checkpoint.solver_build,solver_id,str(solver_build).strip()):
            return checkpoint,conversion
    return None,None
