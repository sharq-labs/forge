"""The Mind-facing port: READ the world, READ the action space, PROPOSE, REQUEST ADMISSION.  Nothing here executes.

Flow: Mind -> ProposedAction -> (the execution side's) AdmissionGateway.admit -> AdmittedAction ->
AdmissionGateway.dispatch -> the execution owner's executor, which receives a DispatchAuthorization re-admitted against
its current owners.

The Mind holds a :class:`MindWorldPort`.  The port holds its own detached copy of the world and its action space
(rebuilt from the payload, so it shares no object with anyone else's) and a journal; it holds no executor, no
provider and no owner reader.  Admission and dispatch go through the :class:`~.admission.AdmissionGateway` the
execution side hands in (``ExecutionDesk.gateway()``): it exposes admit and dispatch and nothing else, so the Mind
neither chooses the owners an admission is verified against nor reaches the executor.  The desk itself is refused
here.  The only execution path, :meth:`MindWorldPort.execute`, accepts an :class:`~.admission.AdmittedAction` and
nothing else; admission decides on its own rebuild of the world, so editing the port's copy changes nothing.

A language-model proposal is accepted only through :meth:`MindWorldPort.propose_suggestion` (a certified
``ExternalSuggestion``); :meth:`MindWorldPort.propose` refuses one that claims that provenance.  The rule does not
depend on the port: a proposal carrying a suggestion is re-derived from it by the check itself.  A proposer's kind is
what the proposer says (``ProposalProvenance`` is caller-asserted): a deployment that hosts an external or
language-model proposer builds the port with ``suggestions_only=True``, and then only proposals that carry their
certified suggestion are requested for admission.
"""

from __future__ import annotations

from typing import Any

from engcore.sria.decision.external import ExternalSuggestion
from engcore.sria.decision.hypotheses import ProposerKind

from .actions import IntakeRefusal, ProposedAction, proposed_action_from_suggestion
from .admission import AdmissionGateway, AdmissionResult, AdmittedAction, DispatchRefused
from .base import WorldRefused
from .feasibility import FeasibilityDecision, FeasibleActionSpace
from .world import ScientificWorld


class MindWorldPort:
    """What the Mind may do: READ the world, READ the action space, PROPOSE, REQUEST ADMISSION.  Never execute."""

    __slots__ = ("_space", "_journal", "_suggestions_only")

    def __init__(self, space: FeasibleActionSpace, *, suggestions_only: bool = False) -> None:
        if not isinstance(space, FeasibleActionSpace):
            raise WorldRefused("a Mind port reads one FeasibleActionSpace")
        if type(suggestions_only) is not bool:
            raise WorldRefused("suggestions_only is a bool")
        self._suggestions_only = suggestions_only
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

    def request_admission(self, proposal: ProposedAction, gateway: AdmissionGateway) -> AdmissionResult:
        """Ask the execution side to admit ``proposal``: it verifies this world against ITS owners first."""
        if type(gateway) is not AdmissionGateway:
            raise WorldRefused("admission is requested through the execution side's AdmissionGateway "
                               "(ExecutionDesk.gateway()); the Mind is never handed the desk")
        if self._suggestions_only and (type(proposal) is not ProposedAction or proposal.source is None):
            raise WorldRefused("this port admits only proposals that carry their certified ExternalSuggestion")
        result = gateway.admit(self._space, proposal)
        self._journal.append(("admission", proposal.digest, result.digest))
        return result

    def execute(self, admitted: Any, gateway: AdmissionGateway) -> Any:
        """The Mind's only execution path: an AdmittedAction, re-admitted by the desk against its current owners."""
        if type(gateway) is not AdmissionGateway:
            raise WorldRefused("execution goes through the execution side's AdmissionGateway (ExecutionDesk.gateway())")
        if type(admitted) is not AdmittedAction:
            raise DispatchRefused(f"only an AdmittedAction is executable, not {type(admitted).__name__}")
        outcome = gateway.dispatch(admitted)
        self._journal.append(("dispatch", admitted.digest, "dispatched"))
        return outcome


__all__ = ["MindWorldPort"]
