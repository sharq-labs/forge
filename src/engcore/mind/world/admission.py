"""Non-bypassable action admission: proposal -> verified admission -> admitted action -> dispatch authorization.

A proposal is never executable because it exists.  The only path to an executor is:

1. :func:`admit` (the execution side's call, with ITS :class:`~.authority.Authorities`): admission never decides on
   the caller's object; it rebuilds the world from its own payload (an object edited after it was built does not
   rebuild) and the action space from that world, and the proposal from its payload.  The world is then verified against
   its owners (:func:`~.projection.verify_world`: exactly the projection of the declaration in force, revision
   included); a world any of whose projected facts is stale, missing,
   mismatched or unbound is MISSING_INFORMATION with one AUTHORITY reason per failed binding, and no check is run on
   the unverified copy.  Only on a verified world is the feasibility check run, and only a FEASIBLE decision mints an
   :class:`AdmittedAction`.
2. :class:`AdmittedAction` is minted by admission alone: constructing one directly is refused.  It binds the
   proposal, the world revision, the action space, every authority binding verified, and the admission's identity,
   and carries the execution kind, the provider requirements, the gating models and the world's synthetic status.
3. :func:`authorize_dispatch` (the execution owner's call, at dispatch time, with its CURRENT authorities) re-runs
   admission from the admitted action's own proposal and world and requires the identical admitted action.  The
   authorities must be LIVE (derived: every reader consults its owner at every read; a fixed run record, a fixed
   declaration set or a snapshot never backs a dispatch).  Any bound owner that moved on (the followed run head
   advanced, a provider's status changed, a ledger was charged, an observation recorded, the declaration in force
   revised), any forged or edited admitted action, and any raw proposal is refused (:class:`DispatchRefused`).
4. :class:`ExecutionDesk` is that boundary as an object, held by the execution side: an executor callable supplied by
   the execution owner is handed a :class:`DispatchAuthorization`, never a proposal, and the desk wraps it so that it
   re-derives every authorization it is handed (:func:`verify_authorization`) before acting.  The Mind is handed only
   the desk's :class:`AdmissionGateway` (admit and dispatch, nothing else): it never holds the readers or the executor.

What this does NOT do.  The desk is not an effect ledger: it records nothing about what was dispatched, and it reserves
no budget (``BUDGET_BASIS``: two admitted actions may each be affordable alone and not together; reservation needs an
owner reservation API, which ``BudgetLedger`` does not expose).  "Synthetic" is what the declaration labels synthetic
(``SYNTHETIC_BASIS``).  An admitted
action whose execution moves none of the owners it is bound to re-admits as long as they state the same records, and
is authorized again.  At-most-once execution, budget reservation, state mutation and provider invocation are the
execution owner's (for example ``sria.campaign`` ``EffectLedger.once`` and ``BudgetLedger.settle``); after its executor
moves a bound owner, the same admitted action no longer re-admits.  Nothing here dispatches by itself or selects a
provider.  The guarantees hold against code that uses the public interface: in-process code that reaches private
members (the desk's executor, the minting context) or rewrites frozen objects with ``object.__setattr__`` is inside
the execution side's trust boundary: a Python process is one trust domain, and isolating a proposer from it is a
process boundary, not this module.  What holds against such code is that every record crossing the boundary is
re-derived (a world from its payload and its owners, an admitted action by re-admission, an authorization by
re-authorization), so an edited record never acts.  An admission is ``action_admission_not_scientific_support``.
"""

from __future__ import annotations

import dataclasses
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
from .domains import DiscreteLevels, matched_level
from .feasibility import (
    CheckFamily, FeasibilityDecision, FeasibilityReason, FeasibilityStatus, FeasibleActionSpace, canonical,
    context_reads,
)
from .projection import verified_projection
from .world import ScientificWorld

ADMISSION_SCHEMA = schema("admission_result")
ADMITTED_SCHEMA = schema("admitted_action")
AUTHORIZATION_SCHEMA = schema("dispatch_authorization")
RECORD_SCHEMA = schema("admission_record")
ADMISSION_CLASSIFICATION = "action_admission_not_scientific_support"
#: What the budget decision of an admission rests on: the action's declared cost / duration estimate, decided by the
#: budget owner's rule against its current account.  Not an owner's cost prediction (``sria.calibration.CostModel`` is
#: not consulted), and nothing is reserved (reservation is the execution owner's).
BUDGET_BASIS = "declared_estimate_against_the_owner_account_not_reserved"
#: What "synthetic" means: some reference the DECLARATION itself labels a synthetic fixture.  Owners are not asked
#: whether they are fixtures; a declaration that relabels its references is the declarer's responsibility.
SYNTHETIC_BASIS = "labelled_synthetic_by_the_declaration"
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
                "synthetic_basis": SYNTHETIC_BASIS, "budget_basis": BUDGET_BASIS,
                "declaration_provenance": DECLARATION_PROVENANCE}

    @property
    def digest(self) -> str:
        return digest(self.to_dict())

    def settings_in_declared_units(self) -> dict[str, Any]:
        """Quantities as magnitudes in each variable's declared unit (the unit owner's conversion, ``magnitude_in``),
        other typed values unchanged: the sanctioned exit from the unit-aware world for an executor.  A value that IS a
        declared discrete level (``domains.matched_level``) is given as that declared level, so a level proposed in
        another unit never reaches an executor off the level by conversion noise."""
        spec = self.world.action(self.proposal.action_id)
        out: dict[str, Any] = {}
        for name, value in self.configuration:
            if not isinstance(value, Quantity):
                out[name] = value
                continue
            control = None if spec is None else spec.control(name)
            level = matched_level(control.domain, value) if control is not None and isinstance(
                control.domain, DiscreteLevels) else None
            out[name] = (value if level is None else level).magnitude_in(self.world.variable(name).unit)
        return out


def _context_entry(world: ScientificWorld, name: str) -> dict[str, Any]:
    var = world.variable(name)
    source = var.source
    binding = None if source is None else (source.to_dict() if hasattr(source, "ref") else source.identity())
    return {"variable": name, "value": None if var.value is None else value_payload(var.value),
            "origin": None if var.origin is None else var.origin.value, "origin_stated_by": "declaration",
            "binding": binding, "basis": var.value_basis, "uncertainty": var.uncertainty.to_dict()}


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

    def feasibility_verdicts(self) -> tuple[Any, ...]:
        """Definite infeasibilities as SRIA ``FeasibilityVerdict`` records, only from a decision made on a world
        verified against its owners (an unverified copy's refusals are never exported)."""
        if not self.verification.ok or self.decision is None:
            return ()
        return self.decision.feasibility_verdicts()

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


def _detached(world: Any) -> ScientificWorld:
    """The world its payload names, as a new object nobody else holds (``ScientificWorld.from_dict`` recomputes and
    compares both identities, so an object edited in place after it was built is refused)."""
    if type(world) is not ScientificWorld:
        raise WorldRefused("admission reads exactly a ScientificWorld")
    try:
        return ScientificWorld.from_dict(world.to_dict())
    except (WorldRefused, ScientificCoreError, AttributeError, KeyError, TypeError, ValueError) as exc:
        raise WorldRefused(f"the world is not the world its identity names (edited after it was built?): {exc}") from None


def admit(space: FeasibleActionSpace, proposal: ProposedAction, authorities: Authorities) -> AdmissionResult:
    """Admission of ``proposal`` on ``space``'s world under ``authorities`` (the execution side's owner readers).

    Verified on a detached rebuild of the world (never the caller's object); decided on, and minted with, the owners'
    own fresh projection that the rebuild was verified to be (so no caller-written text, even non-material, reaches
    an executor)."""
    if type(space) is not FeasibleActionSpace:
        raise WorldRefused("admission reads exactly a FeasibleActionSpace")
    if type(authorities) is not Authorities:
        raise WorldRefused("admission verifies against the execution side's Authorities")
    proposal = canonical(proposal)
    world = _detached(space.world)
    rebuilt = FeasibleActionSpace.build(world)
    if rebuilt.space_id != space.space_id:
        raise WorldRefused("the action space is not the one its world builds")
    space = rebuilt
    report, fresh = verified_projection(world, authorities)
    if fresh is not None:                                 # decide on what the owners project, not on the caller's copy
        world, space = fresh, FeasibleActionSpace.build(fresh)
        if space.space_id != rebuilt.space_id:
            raise WorldRefused("the owners' projection does not build the verified action space")
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
    """What an executor receives: one admitted action, re-admitted against the executor's own current authorities.

    Minted from a fresh rebuild (it shares no object with the AdmittedAction the proposer holds), with the settings an
    executor needs as plain values in each variable's declared unit, fixed at mint.  ``verify()`` is its self-check (its
    payload is still what was minted): an executor that runs later than it is handed the authorization calls it at
    execution time; :func:`verify_authorization` re-derives it against the owners as they are then."""

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
    declaration: Any                                   # the declaration in force it was admitted under (identity)
    owners: tuple[tuple[str, str], ...]                # the owner instances (kind, id) it was re-admitted against
    settings: Any                                      # {variable: magnitude in its declared unit | typed value payload}
    admitted: AdmittedAction = field(repr=False, compare=False)
    minted: str = field(default="", compare=False)     # the payload digest at mint (``verify``)

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
                "providers": [detach(p) for p in self.providers], "synthetic": self.synthetic,
                "declaration": detach(self.declaration), "declaration_provenance": DECLARATION_PROVENANCE,
                "owners": [list(o) for o in self.owners], "settings": detach(self.settings),
                "budget_basis": BUDGET_BASIS, "synthetic_basis": SYNTHETIC_BASIS}

    @property
    def digest(self) -> str:
        return digest(self.to_dict())

    def verify(self) -> "DispatchAuthorization":
        """Refuse an authorization whose payload is no longer what was minted (edited in place after it was handed
        over).  A self-check only: whether the owners still support it is :func:`verify_authorization`."""
        if type(self) is not DispatchAuthorization or not self.minted or self.digest != self.minted:
            raise DispatchRefused("the authorization is not what was minted (edited after it was handed over)")
        return self


def authorize_dispatch(admitted: Any, authorities: Authorities, *, accept_synthetic: bool = False
                       ) -> DispatchAuthorization:
    """Re-admit ``admitted`` from its own proposal and world against ``authorities`` NOW; refuse anything else.

    ``authorities`` must be live (never readers rebuilt from a snapshot), and a world citing synthetic contract
    fixtures is dispatched only to an executor that says it accepts synthetic content (a test executor)."""
    if type(admitted) is not AdmittedAction:
        raise DispatchRefused(f"only an AdmittedAction minted by admission is dispatchable, not "
                              f"{type(admitted).__name__} (a raw proposal never executes)")
    if type(authorities) is not Authorities or not authorities.live:
        raise DispatchRefused("dispatch is authorized only against live owner readers (each read consults the owner "
                              "now); a fixed run record, a fixed declaration set, a snapshot or a look-alike reader "
                              "states what an owner said before")
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
    declaration = None if a.world.declaration is None else _frozen(a.world.declaration.identity())
    owners = tuple(sorted({(k.value, authorities.reader(k).owner_id) for r in authorities.readers for k in r.kinds}))
    settings = _frozen({name: v if isinstance(v, (int, float)) else value_payload(v)
                        for name, v in a.settings_in_declared_units().items()})
    with _minting():
        minted = DispatchAuthorization(a.digest, result.digest, result.verification.digest, a.world_revision,
                                       a.proposal_digest, a.proposal.action_id, a.configuration, a.observe,
                                       a.execution, a.providers, a.synthetic, declaration, owners, settings, a)
        return dataclasses.replace(minted, minted=minted.digest)


def verify_authorization(authorization: Any, authorities: Authorities, *, accept_synthetic: bool = False
                         ) -> DispatchAuthorization:
    """For an executor: re-derive ``authorization`` from its admitted action against ``authorities`` now, and require
    the identical authorization (a hand-built or edited one, or one its owners no longer support, is refused)."""
    if type(authorization) is not DispatchAuthorization:
        raise DispatchRefused("not a DispatchAuthorization")
    authorization.verify()
    again = authorize_dispatch(authorization.admitted, authorities, accept_synthetic=accept_synthetic)
    if again.digest != authorization.digest:
        raise DispatchRefused("the authorization is not what authorize_dispatch yields now (edited or forged)")
    return again


class _GuardedExecutor:
    """The execution owner's executor behind a re-derivation of every authorization it is handed (``__call__``); the
    desk's own dispatch authorizes once and hands the fresh authorization straight on (``_dispatch``)."""

    __slots__ = ("_call", "_dispatch")

    def __init__(self, executor: Callable[[DispatchAuthorization], Any], authorities: Authorities,
                 accept_synthetic: bool) -> None:
        def call(authorization: Any) -> Any:
            return executor(verify_authorization(authorization, authorities, accept_synthetic=accept_synthetic))

        def dispatch(admitted: Any) -> Any:
            return executor(authorize_dispatch(admitted, authorities, accept_synthetic=accept_synthetic))
        object.__setattr__(self, "_call", call)
        object.__setattr__(self, "_dispatch", dispatch)

    def __setattr__(self, name: str, value: Any) -> None:
        raise WorldRefused("an executor guard is immutable")

    def __call__(self, authorization: Any) -> Any:
        return self._call(authorization)


class ExecutionDesk:
    """The execution side's boundary: it holds the owner readers and the executor; a proposer holds neither.

    ``dispatch`` hands the executor a :class:`DispatchAuthorization` for a currently admissible
    :class:`AdmittedAction` and refuses anything else.  The authorities must be live (derived), so a dispatch is
    always decided on what the owners state at that moment; the executor is wrapped so that it re-derives every
    authorization it receives, however it is reached.  The desk is immutable.  It records no effects (see the module
    docstring): at-most-once execution, budget reservation, state mutation and provider invocation stay with the
    executor; once it moves an owner the action is bound to, the same admitted action no longer re-admits.  The Mind is
    given :meth:`gateway`, never the desk."""

    __slots__ = ("_authorities", "_executor", "_accept_synthetic")

    def __init__(self, authorities: Authorities, executor: Callable[[DispatchAuthorization], Any], *,
                 accept_synthetic: bool = False) -> None:
        if type(authorities) is not Authorities or not authorities.live or not callable(executor):
            raise WorldRefused("an execution desk holds the execution side's live Authorities (every reader consults "
                               "its owner at every read) and an executor callable")
        if type(accept_synthetic) is not bool:
            raise WorldRefused("accept_synthetic is a bool")
        object.__setattr__(self, "_authorities", authorities)
        object.__setattr__(self, "_executor", _GuardedExecutor(executor, authorities, accept_synthetic))
        object.__setattr__(self, "_accept_synthetic", accept_synthetic)

    def __setattr__(self, name: str, value: Any) -> None:
        raise WorldRefused("an execution desk is immutable: its owners and executor are fixed when it is built")

    def __delattr__(self, name: str) -> None:
        raise WorldRefused("an execution desk is immutable")

    def admit(self, space: FeasibleActionSpace, proposal: ProposedAction) -> AdmissionResult:
        return admit(space, proposal, self._authorities)

    def dispatch(self, admitted: Any) -> Any:
        return self._executor._dispatch(admitted)

    def gateway(self) -> "AdmissionGateway":
        """What the Mind is handed: admit and dispatch through this desk's owners and executor, and nothing else (no
        bound method, so the desk itself is not an attribute of anything the Mind holds)."""
        authorities, dispatch_ = self._authorities, self._executor._dispatch

        def admit_(space: FeasibleActionSpace, proposal: ProposedAction) -> AdmissionResult:
            return admit(space, proposal, authorities)
        return AdmissionGateway(admit_, dispatch_)


class AdmissionGateway:
    """The Mind's handle on the execution side: request admission, request dispatch of an admitted action.  It exposes
    no reader, no executor and no setting, and is immutable."""

    __slots__ = ("_admit", "_dispatch")

    def __init__(self, admit_: Callable[..., AdmissionResult], dispatch: Callable[[Any], Any]) -> None:
        object.__setattr__(self, "_admit", admit_)
        object.__setattr__(self, "_dispatch", dispatch)

    def __setattr__(self, name: str, value: Any) -> None:
        raise WorldRefused("an admission gateway is immutable")

    def admit(self, space: FeasibleActionSpace, proposal: ProposedAction) -> AdmissionResult:
        return self._admit(space, proposal)

    def dispatch(self, admitted: Any) -> Any:
        return self._dispatch(admitted)


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
        """Record ``result`` when it is made: re-admitted against the LIVE owners, with exactly the owner records that
        re-admission read (one consistent read of each owner); refused if the owners no longer give it."""
        if type(authorities) is not Authorities or not authorities.live:
            raise WorldRefused("an admission is recorded against the live owners it was made under, never a snapshot")
        served = authorities.memoized()
        again = admit(FeasibleActionSpace.build(result.world), result.proposal, served)
        if again.digest != result.digest:
            raise WorldRefused("the owners no longer give this admission; record it when it is made")
        return cls(_frozen(result.world.to_dict()), _frozen(result.proposal.to_dict()), _frozen(served.served()),
                   _frozen(result.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": RECORD_SCHEMA, "world": detach(self.world), "proposal": detach(self.proposal),
                "snapshot": detach(self.snapshot), "result": detach(self.result)}


def replay_admission(payload: Mapping[str, Any]) -> ReplayResult:
    """Re-run a recorded admission against the owner records it read (``sria.decision.replay`` vocabulary).

    Every recorded owner payload must first re-derive its recorded revision and digest by the owner's own identity rule
    (``owners.rederive``); a record its payload refutes is REPLAY_DEPENDENCY_UNAVAILABLE.  REPRODUCED then attests that
    the record is self-consistent under the owners' rules and that admission decides on it exactly as recorded.  It does
    not attest that the owners held those records (provenance is the owner's own anchor, e.g. the run's state chain),
    and it never authorizes anything: a replayed admitted action is not dispatchable unless :func:`authorize_dispatch`
    re-admits it against the owners as they are now."""
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
    "ADMISSION_CLASSIFICATION", "AdmissionGateway", "AdmissionRecord", "AdmissionResult", "AdmittedAction",
    "DispatchAuthorization",
    "DispatchRefused", "ExecutionDesk", "admit", "authorize_dispatch", "replay_admission", "verify_authorization",
]
