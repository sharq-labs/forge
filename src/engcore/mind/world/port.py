"""The Mind-facing port: READ the world, READ the action space, PROPOSE, REQUEST ADMISSION.  Nothing here executes.

Flow: Mind -> ProposedAction -> (the execution side's) ExecutionDesk.admit -> AdmittedAction -> ExecutionDesk.dispatch
-> the execution owner's executor, which receives a DispatchAuthorization re-admitted against its current owners.

The Mind holds a :class:`MindWorldPort`.  The port holds its own detached copy of the world and its action space
(rebuilt from the payload, so it shares no object with anyone else's) and a journal; it holds no executor, no
provider and no owner reader, and imports none, so it can neither admit against owners it chose nor reach an
executor.  Admission and dispatch go through an :class:`~.admission.ExecutionDesk` the execution side hands in; the
only execution path, :meth:`MindWorldPort.execute`, accepts an :class:`~.admission.AdmittedAction` and nothing else.

A language-model proposal is accepted only through :meth:`MindWorldPort.propose_suggestion` (a certified
``ExternalSuggestion``); :meth:`MindWorldPort.propose` refuses one that claims that provenance.  The rule does not
depend on the port: a proposal carrying a suggestion is re-derived from it by the check itself.
"""

from __future__ import annotations

from typing import Any

from engcore.sria.decision.external import ExternalSuggestion
from engcore.sria.decision.hypotheses import ProposerKind

from .actions import IntakeRefusal, ProposedAction, proposed_action_from_suggestion
from .admission import AdmissionResult, AdmittedAction, DispatchRefused, ExecutionDesk
from .base import WorldRefused
from .feasibility import FeasibilityDecision, FeasibleActionSpace
from .world import ScientificWorld


class MindWorldPort:
    """What the Mind may do: READ the world, READ the action space, PROPOSE, REQUEST ADMISSION.  Never execute."""

    __slots__ = ("_space", "_journal")

    def __init__(self, space: FeasibleActionSpace) -> None:
        if not isinstance(space, FeasibleActionSpace):
            raise WorldRefused("a Mind port reads one FeasibleActionSpace")
        own = FeasibleActionSpace.build(ScientificWorld.from_dict(space.world.to_dict()))
        if own.space_id != space.space_id:
            raise WorldRefused("the action space does not rebuild from its world's payload")
        self._space = own
        self._journal: list[tuple[str, str, str]] = []

    @property
    def world(self) -> ScientificWorld:
        return self._space.world

    @property
    def action_space(self) -> FeasibleActionSpace:
        return self._space

    @property
    def journal(self) -> tuple[tuple[str, str, str], ...]:
        """(kind, input digest, outcome digest or intake code) for every proposal received, in order."""
        return tuple(self._journal)

    def propose(self, proposal: ProposedAction) -> FeasibilityDecision:
        """A feasibility check on this (possibly stale) view: reasoning only, never an admission."""
        if isinstance(proposal, ProposedAction) and proposal.proposer.proposer_kind is ProposerKind.LANGUAGE_MODEL:
            raise WorldRefused("a language-model proposal enters through propose_suggestion (an ExternalSuggestion), "
                               "where the port itself binds its provenance")
        decision = self._space.check(proposal)
        self._journal.append(("proposal", proposal.digest, decision.digest))
        return decision

    def propose_suggestion(self, suggestion: ExternalSuggestion) -> FeasibilityDecision | IntakeRefusal:
        """An external proposer's suggestion: refused with a structured code at intake, or checked like any other."""
        result = proposed_action_from_suggestion(suggestion, world=self._space.world)
        if isinstance(result, IntakeRefusal):
            self._journal.append(("suggestion", suggestion.digest, result.code.value))
            return result
        decision = self._space.check(result)
        self._journal.append(("suggestion", suggestion.digest, decision.digest))
        return decision

    def request_admission(self, proposal: ProposedAction, desk: ExecutionDesk) -> AdmissionResult:
        """Ask the execution side to admit ``proposal``: it verifies this world against ITS owners first."""
        if type(desk) is not ExecutionDesk:
            raise WorldRefused("admission is requested from the execution side's ExecutionDesk")
        result = desk.admit(self._space, proposal)
        self._journal.append(("admission", proposal.digest, result.digest))
        return result

    def execute(self, admitted: Any, desk: ExecutionDesk) -> Any:
        """The Mind's only execution path: an AdmittedAction, re-admitted by the desk against its current owners."""
        if type(desk) is not ExecutionDesk:
            raise WorldRefused("execution goes through the execution side's ExecutionDesk")
        if type(admitted) is not AdmittedAction:
            raise DispatchRefused(f"only an AdmittedAction is executable, not {type(admitted).__name__}")
        outcome = desk.dispatch(admitted)
        self._journal.append(("dispatch", admitted.digest, "dispatched"))
        return outcome


__all__ = ["MindWorldPort"]
