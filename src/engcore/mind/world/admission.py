"""Non-bypassable action admission: proposal -> verified admission -> admitted action -> dispatch authorization.

A proposal is never executable because it exists.  The only path to an executor is:

1. :func:`admit` (the execution side's call, with ITS :class:`~.authority.Authorities`): the world is verified against
   its owners first (:func:`~.projection.verify_world`); a world any of whose projected facts is stale, missing,
   mismatched or unbound is MISSING_INFORMATION with one AUTHORITY reason per failed binding, and no check is run on
   the unverified copy.  Only on a verified world is the feasibility check run, and only a FEASIBLE decision mints an
   :class:`AdmittedAction`.
2. :class:`AdmittedAction` is minted by admission alone: constructing one directly is refused.  It binds the
   proposal, the world revision, the action space, every authority binding verified, and the admission's identity,
   and carries the execution kind, the provider requirements, the gating models and the world's synthetic status.
3. :func:`authorize_dispatch` (the execution owner's call, at dispatch time, with its CURRENT authorities) re-runs
   admission from the admitted action's own proposal and world and requires the identical admitted action.  Any
   owner that moved on (a state advanced, a provider went down, a ledger was charged, a declaration revised), any
   forged or edited admitted action, and any raw proposal is refused (:class:`DispatchRefused`).
4. :class:`ExecutionDesk` is that boundary as an object: an executor callable supplied by the execution owner is
   handed a :class:`DispatchAuthorization`, never a proposal.

Nothing here dispatches by itself, reserves or settles a budget, mutates state or selects a provider: those stay
with the execution owner and its executor.  An admission is ``action_admission_not_scientific_support``.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Mapping

from engcore.mind.repsem import canonical_bytes
from engcore.scientific import Quantity, ScientificCoreError
from engcore.scientific.results.immutable import detach, freeze
from engcore.sria.decision.replay import ReplayMode, ReplayOutcome, ReplayResult

from .actions import ExecutionKind, ProposedAction
from .authority import Authorities, AuthorityReport
from .base import StaleProposal, WorldRefused, digest, schema, value_payload
from .feasibility import (
    CheckFamily, FeasibilityDecision, FeasibilityReason, FeasibilityStatus, FeasibleActionSpace, canonical,
    context_reads,
)
from .projection import verify_world
from .world import ScientificWorld

ADMISSION_SCHEMA = schema("admission_result")
ADMITTED_SCHEMA = schema("admitted_action")
AUTHORIZATION_SCHEMA = schema("dispatch_authorization")
RECORD_SCHEMA = schema("admission_record")
ADMISSION_CLASSIFICATION = "action_admission_not_scientific_support"
#: No canonical owner holds experiment protocols (allowed levels, action controls, guards): the declaration is
#: caller-declared, held in force by the execution side and bound by identity, revision and digest.  It is reported
#: as such, distinct from the owner-verified facts (state, models, providers, budgets, units).
DECLARATION_PROVENANCE = "caller_declared_held_in_force_by_the_execution_side_no_canonical_protocol_owner"
F = FeasibilityStatus

_MINTING: ContextVar[bool] = ContextVar("engcore_mind_world_admission_minting", default=False)


@contextmanager
def _minting() -> Iterator[None]:
    token = _MINTING.set(True)
    try:
        yield
    finally:
        _MINTING.reset(token)


class DispatchRefused(WorldRefused):
    """Dispatch refused: not an admitted action, or one its owners no longer support."""


def _frozen(payload: Mapping[str, Any]) -> Any:
    return freeze(detach(dict(payload)))


# ---- the admitted action --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class AdmittedAction:
    """A FEASIBLE proposal on a verified world, as admission minted it.  Authorization metadata for the execution
    owner, never a dispatch.  ``configuration`` is exactly what was proposed plus the action's fixed conditions (no
    value is rewritten); ``context`` is every other value a decision on this action may read, with the authority
    binding or declared basis it came from and its uncertainty."""

    proposal: ProposedAction
    world: ScientificWorld = field(repr=False)
    space_id: str
    world_revision: str
    admission: str                                    # identity of the admission result (before minting)
    bindings: tuple[str, ...]                         # every authority binding verified for it
    configuration: tuple[tuple[str, Any], ...]
    context: tuple[Any, ...]
    observe: tuple[str, ...]
    execution: ExecutionKind
    providers: tuple[Any, ...]
    models: tuple[Any, ...]
    synthetic: bool

    def __post_init__(self) -> None:
        if not _MINTING.get():
            raise WorldRefused("an AdmittedAction is minted only by admission (admit); a proposer, an engine or a "
                               "replay cannot construct one")

    @property
    def proposal_digest(self) -> str:
        return self.proposal.digest

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ADMITTED_SCHEMA, "classification": ADMISSION_CLASSIFICATION,
                "proposal": self.proposal.to_dict(), "proposal_digest": self.proposal.digest,
                "space_id": self.space_id, "world_revision": self.world_revision, "admission": self.admission,
                "bindings": list(self.bindings),
                "configuration": [{"variable": n, "value": value_payload(v)} for n, v in self.configuration],
                "context": [detach(x) for x in self.context], "observe": list(self.observe),
                "execution": self.execution.value, "providers": [detach(p) for p in self.providers],
                "models": [detach(m) for m in self.models], "synthetic": self.synthetic,
                "declaration_provenance": DECLARATION_PROVENANCE}

    @property
    def digest(self) -> str:
        return digest(self.to_dict())

    def settings_in_declared_units(self) -> dict[str, Any]:
        """Quantities as magnitudes in each variable's declared unit (the unit owner's conversion, ``magnitude_in``),
        other typed values unchanged: the sanctioned exit from the unit-aware world for an executor."""
        return {name: value.magnitude_in(self.world.variable(name).unit) if isinstance(value, Quantity) else value
                for name, value in self.configuration}


def _context_entry(world: ScientificWorld, name: str) -> dict[str, Any]:
    var = world.variable(name)
    source = var.source
    binding = None if source is None else (source.to_dict() if hasattr(source, "ref") else source.identity())
    return {"variable": name, "value": None if var.value is None else value_payload(var.value),
            "origin": None if var.origin is None else var.origin.value, "binding": binding,
            "basis": var.value_basis, "uncertainty": var.uncertainty.to_dict()}


def _mint(space: FeasibleActionSpace, proposal: ProposedAction, report: AuthorityReport, admission: str
          ) -> AdmittedAction:
    world = space.world
    spec = world.action(proposal.action_id)
    config = {f.name: f.value for f in spec.fixed_conditions}
    for name, value in proposal.assignments:
        config.setdefault(name, value)
    context = tuple(_frozen(_context_entry(world, n)) for n in sorted(context_reads(world, spec) - set(config)))
    models = tuple(_frozen({"binding_id": a, "authority": None if world.applicability_binding(a).authority is None
                            else world.applicability_binding(a).authority.identity()}) for a in spec.applicability)
    with _minting():
        return AdmittedAction(proposal, world, space.space_id, world.revision_id, admission,
                              tuple(sorted({c.binding_digest for c in report.checks})), tuple(sorted(config.items())),
                              context, tuple(proposal.observe or spec.expected_observables), spec.execution,
                              tuple(_frozen(r.to_dict()) for r in spec.provider_requirements), models, world.synthetic)


# ---- the admission result --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class AdmissionResult:
    status: FeasibilityStatus
    reasons: tuple[FeasibilityReason, ...]
    verification: AuthorityReport
    decision: FeasibilityDecision | None
    admitted: AdmittedAction | None
    proposal: ProposedAction = field(repr=False)
    world: ScientificWorld = field(repr=False)
    space_id: str = ""

    @property
    def feasible(self) -> bool:
        return self.admitted is not None

    def codes(self) -> tuple[str, ...]:
        return tuple(sorted({r.code for r in self.reasons}))

    def _basis(self) -> dict[str, Any]:
        return {"schema": ADMISSION_SCHEMA, "classification": ADMISSION_CLASSIFICATION, "status": self.status.value,
                "reasons": [r.to_dict() for r in self.reasons], "verification": self.verification.to_dict(),
                "decision": None if self.decision is None else self.decision.to_dict(),
                "proposal_digest": self.proposal.digest, "world_revision": self.world.revision_id,
                "space_id": self.space_id}

    @property
    def basis_digest(self) -> str:
        """The admission's identity before any action is minted (the admitted action binds it)."""
        return digest(self._basis())

    def to_dict(self) -> dict[str, Any]:
        return {**self._basis(), "admitted": None if self.admitted is None else self.admitted.to_dict()}

    @property
    def digest(self) -> str:
        return digest(self.to_dict())


def _authority_reasons(report: AuthorityReport) -> tuple[FeasibilityReason, ...]:
    return tuple(FeasibilityReason(
        F.MISSING_INFORMATION, f"AUTHORITY_{c.status.name}", CheckFamily.AUTHORITY, c.subject,
        f"{c.owner_kind.value} binding is {c.status.value}: an unverified fact never supports admission",
        {"record_id": c.record_id, "binding_digest": c.binding_digest, **dict(c.detail or {})})
        for c in report.failures())


def admit(space: FeasibleActionSpace, proposal: ProposedAction, authorities: Authorities) -> AdmissionResult:
    """Admission of ``proposal`` on ``space``'s world under ``authorities`` (the execution side's owner readers)."""
    if type(space) is not FeasibleActionSpace:
        raise WorldRefused("admission reads exactly a FeasibleActionSpace")
    if type(authorities) is not Authorities:
        raise WorldRefused("admission verifies against the execution side's Authorities")
    proposal = canonical(proposal)
    world = space.world
    if FeasibleActionSpace.build(world).space_id != space.space_id:
        raise WorldRefused("the action space is not the one its world builds")
    report = verify_world(world, authorities)
    if not report.ok:
        if proposal.world_revision != world.revision_id:
            raise StaleProposal("the proposal was made for another world revision")
        return AdmissionResult(F.MISSING_INFORMATION, _authority_reasons(report), report, None, None, proposal, world,
                               space.space_id)
    decision = space.check(proposal)
    result = AdmissionResult(decision.status, decision.reasons, report, decision, None, proposal, world, space.space_id)
    if not decision.feasible:
        return result
    admitted = _mint(space, proposal, report, result.basis_digest)
    return AdmissionResult(decision.status, decision.reasons, report, decision, admitted, proposal, world,
                           space.space_id)


# ---- dispatch ----------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DispatchAuthorization:
    """What an executor receives: one admitted action, re-admitted against the executor's own current authorities."""

    admitted_digest: str
    admission_digest: str
    verification_digest: str
    world_revision: str
    proposal_digest: str
    action_id: str
    configuration: tuple[tuple[str, Any], ...]
    observe: tuple[str, ...]
    execution: ExecutionKind
    providers: tuple[Any, ...]
    synthetic: bool
    admitted: AdmittedAction = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not _MINTING.get():
            raise WorldRefused("a DispatchAuthorization is issued only by authorize_dispatch")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": AUTHORIZATION_SCHEMA, "classification": ADMISSION_CLASSIFICATION,
                "admitted_digest": self.admitted_digest, "admission_digest": self.admission_digest,
                "verification_digest": self.verification_digest, "world_revision": self.world_revision,
                "proposal_digest": self.proposal_digest, "action_id": self.action_id,
                "configuration": [{"variable": n, "value": value_payload(v)} for n, v in self.configuration],
                "observe": list(self.observe), "execution": self.execution.value,
                "providers": [detach(p) for p in self.providers], "synthetic": self.synthetic}


def authorize_dispatch(admitted: Any, authorities: Authorities, *, accept_synthetic: bool = False
                       ) -> DispatchAuthorization:
    """Re-admit ``admitted`` from its own proposal and world against ``authorities`` NOW; refuse anything else.

    ``authorities`` must be live (never readers rebuilt from a snapshot), and a world citing synthetic contract
    fixtures is dispatched only to an executor that says it accepts synthetic content (a test executor)."""
    if type(admitted) is not AdmittedAction:
        raise DispatchRefused(f"only an AdmittedAction minted by admission is dispatchable, not "
                              f"{type(admitted).__name__} (a raw proposal never executes)")
    if type(authorities) is not Authorities or not authorities.live:
        raise DispatchRefused("dispatch is authorized only against the execution side's live owners, never against "
                              "a snapshot of what they said before")
    try:
        world, proposal, claimed = admitted.world, admitted.proposal, admitted.digest
        result = admit(FeasibleActionSpace.build(world), proposal, authorities)
    except (WorldRefused, ScientificCoreError, AttributeError, TypeError, KeyError, ValueError) as exc:
        raise DispatchRefused(f"the admitted action does not re-admit: {exc}") from None
    if result.admitted is None:
        raise DispatchRefused(f"admission now refuses this action ({result.status.value}: {', '.join(result.codes())})")
    if result.admitted.digest != claimed:
        raise DispatchRefused("the admitted action is not what admission yields now (edited, forged or re-bound)")
    a = result.admitted
    if a.synthetic and not accept_synthetic:
        raise DispatchRefused("the world cites synthetic contract fixtures; it is dispatched only to an executor "
                              "that accepts synthetic content")
    with _minting():
        return DispatchAuthorization(a.digest, result.digest, result.verification.digest, a.world_revision,
                                     a.proposal_digest, a.proposal.action_id, a.configuration, a.observe, a.execution,
                                     a.providers, a.synthetic, a)


class ExecutionDesk:
    """The execution side's boundary: it holds the owner readers and the executor; a proposer holds neither.

    ``dispatch`` hands the executor a :class:`DispatchAuthorization` for a currently admissible
    :class:`AdmittedAction` and refuses anything else.  Budget reservation, state mutation and provider invocation
    stay with the executor (the execution owner); after it runs, its owners move on and the same admitted action
    no longer re-admits."""

    __slots__ = ("_authorities", "_executor", "_accept_synthetic")

    def __init__(self, authorities: Authorities, executor: Callable[[DispatchAuthorization], Any], *,
                 accept_synthetic: bool = False) -> None:
        if type(authorities) is not Authorities or not authorities.live or not callable(executor):
            raise WorldRefused("an execution desk holds the execution side's live Authorities and an executor callable")
        if type(accept_synthetic) is not bool:
            raise WorldRefused("accept_synthetic is a bool")
        self._authorities = authorities
        self._executor = executor
        self._accept_synthetic = accept_synthetic

    def admit(self, space: FeasibleActionSpace, proposal: ProposedAction) -> AdmissionResult:
        return admit(space, proposal, self._authorities)

    def dispatch(self, admitted: Any) -> Any:
        return self._executor(authorize_dispatch(admitted, self._authorities, accept_synthetic=self._accept_synthetic))


# ---- replay -----------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class AdmissionRecord:
    """A replayable admission: the world, the proposal, the owner records admission read, and its result."""

    world: Mapping[str, Any]
    proposal: Mapping[str, Any]
    snapshot: Mapping[str, Any]
    result: Mapping[str, Any]

    @classmethod
    def of(cls, result: AdmissionResult, authorities: Authorities) -> "AdmissionRecord":
        """Record ``result`` with the owner records ``authorities`` serve now; refused if they no longer give it."""
        again = admit(FeasibleActionSpace.build(result.world), result.proposal, authorities)
        if again.digest != result.digest:
            raise WorldRefused("the owners no longer give this admission; record it when it is made")
        return cls(_frozen(result.world.to_dict()), _frozen(result.proposal.to_dict()),
                   _frozen(authorities.snapshot(result.world.authority_bindings())), _frozen(result.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": RECORD_SCHEMA, "world": detach(self.world), "proposal": detach(self.proposal),
                "snapshot": detach(self.snapshot), "result": detach(self.result)}


def replay_admission(payload: Mapping[str, Any]) -> ReplayResult:
    """Re-run a recorded admission against the owner records it read (``sria.decision.replay`` vocabulary).

    Exact replay proves what the world contained and what admission decided then.  It never authorizes anything: a
    replayed admitted action is not dispatchable unless :func:`authorize_dispatch` re-admits it against the owners as
    they are now."""
    mode = ReplayMode.EXECUTABLE_REPLAY
    record = dict(payload.get("result", {}))
    try:
        if payload.get("schema") != RECORD_SCHEMA:
            raise WorldRefused("not an admission record")
        world = ScientificWorld.from_dict(payload["world"])
        proposal = ProposedAction.from_dict(payload["proposal"])
        authorities = Authorities.from_snapshot(payload["snapshot"])
    except (WorldRefused, ScientificCoreError, KeyError, TypeError, ValueError) as exc:
        return ReplayResult(mode, ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE, record, mismatches=("inputs",),
                            detail=f"the recorded inputs do not rebuild: {exc}")
    if record.get("world_revision") != world.revision_id or record.get("proposal_digest") != proposal.digest:
        return ReplayResult(mode, ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE, record,
                            mismatches=("world_revision", "proposal_digest"),
                            detail="the recorded inputs are not the ones this admission was made for")
    try:
        recomputed = admit(FeasibleActionSpace.build(world), proposal, authorities).to_dict()
    except WorldRefused as exc:
        return ReplayResult(mode, ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE, record, mismatches=("admission",),
                            detail=f"the recorded proposal is refused on replay: {exc}")
    if canonical_bytes(recomputed) == canonical_bytes(record):
        return ReplayResult(mode, ReplayOutcome.REPRODUCED, record, recomputed)
    diff = tuple(sorted(k for k in set(recomputed) | set(record) if recomputed.get(k) != record.get(k)))
    return ReplayResult(mode, ReplayOutcome.NONDETERMINISM_DETECTED, record, recomputed, diff,
                        "the recomputed admission differs from the recorded one")


__all__ = [
    "ADMISSION_CLASSIFICATION", "AdmissionRecord", "AdmissionResult", "AdmittedAction", "DispatchAuthorization",
    "DispatchRefused", "ExecutionDesk", "admit", "authorize_dispatch", "replay_admission",
]
