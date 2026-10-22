"""The Mind-facing port: READ the world, READ the action space, PROPOSE.  Nothing here executes anything.

Flow: Mind -> ProposedAction -> FeasibleActionSpace.check -> ClearedAction -> ExecutionGate -> existing executor.

The Mind holds a :class:`MindWorldPort`.  The port holds its own detached copy of the world and its action space
(rebuilt from the payload, so it shares no object with an execution gate) and a journal; it holds no executor, no
provider, no gate and imports none, so it cannot reach one.  The gate (:mod:`.gate`) is held by the execution owner.

A language-model proposal is accepted only through :meth:`MindWorldPort.propose_suggestion` (a certified
``ExternalSuggestion``); :meth:`MindWorldPort.propose` refuses one that claims that provenance.
"""

from __future__ import annotations

from engcore.sria.decision.external import ExternalSuggestion
from engcore.sria.decision.hypotheses import ProposerKind

from .actions import IntakeCode, IntakeRefusal, ProposedAction, proposed_action_from_suggestion
from .base import WorldRefused
from .feasibility import FeasibilityDecision, FeasibleActionSpace
from .world import ScientificWorld


class MindWorldPort:
    """What the Mind may do: READ the world, READ the action space, PROPOSE.  Nothing here executes anything."""

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
        if isinstance(proposal, ProposedAction) and proposal.proposer.proposer_kind is ProposerKind.LANGUAGE_MODEL:
            raise WorldRefused("a language-model proposal enters through propose_suggestion (an ExternalSuggestion), "
                               "where the port itself binds its provenance")
        decision = self._space.check(proposal)
        self._journal.append(("proposal", proposal.digest, decision.digest))
        return decision

    def propose_suggestion(self, suggestion: ExternalSuggestion) -> FeasibilityDecision | IntakeRefusal:
        """An external proposer's suggestion: refused with a structured code at intake, or checked like any other."""
        result = proposed_action_from_suggestion(suggestion, world_revision=self._space.world.revision_id)
        if not isinstance(result, IntakeRefusal):
            spec = self._space.world.action(result.action_id)
            if spec is not None and spec.family is not suggestion.family:
                result = IntakeRefusal(IntakeCode.FAMILY_MISMATCH, result.action_id,
                                       f"the suggestion is labelled {suggestion.family.value}, the declared action is "
                                       f"{spec.family.value}", suggestion.digest)
        if isinstance(result, IntakeRefusal):
            self._journal.append(("suggestion", suggestion.digest, result.code.value))
            return result
        decision = self._space.check(result)
        self._journal.append(("suggestion", suggestion.digest, decision.digest))
        return decision


__all__ = ["MindWorldPort"]
