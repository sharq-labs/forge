"""The Mind-facing port: READ the world, READ the action space, PROPOSE.  Nothing here executes anything.

Flow: Mind -> ProposedAction -> FeasibleActionSpace.check -> ClearedAction -> ExecutionGate -> existing executor.

The Mind holds a :class:`MindWorldPort`.  The port holds an action space and a journal; it holds no executor, no
provider, no gate and imports none, so it cannot reach one.  The gate (:mod:`.gate`) is held by the execution owner.
"""

from __future__ import annotations

from engcore.sria.decision.external import ExternalSuggestion

from .actions import IntakeCode, IntakeRefusal, ProposedAction, proposal_from_suggestion
from .base import StaleProposal, WorldRefused
from .feasibility import FeasibilityDecision, FeasibleActionSpace


class MindWorldPort:
    """What the Mind may do: READ the world, READ the action space, PROPOSE.  Nothing here executes anything."""

    __slots__ = ("_space", "_journal")

    def __init__(self, space: FeasibleActionSpace) -> None:
        if not isinstance(space, FeasibleActionSpace):
            raise WorldRefused("a Mind port reads one FeasibleActionSpace")
        self._space = space
        self._journal: list[tuple[str, str, str]] = []

    @property
    def world(self):
        return self._space.world

    @property
    def action_space(self) -> FeasibleActionSpace:
        return self._space

    @property
    def journal(self) -> tuple[tuple[str, str, str], ...]:
        """(kind, input digest, outcome digest) for every proposal received, in order."""
        return tuple(self._journal)

    def propose(self, proposal: ProposedAction) -> FeasibilityDecision:
        decision = self._space.check(proposal)
        self._journal.append(("proposal", proposal.digest, decision.digest))
        return decision

    def propose_suggestion(self, suggestion: ExternalSuggestion) -> FeasibilityDecision | IntakeRefusal:
        """An external proposer's suggestion: refused with a structured code at intake, or checked like any other."""
        result = proposal_from_suggestion(suggestion, world_revision=self._space.world.revision_id)
        if isinstance(result, IntakeRefusal):
            self._journal.append(("suggestion", suggestion.digest, result.code.value))
            return result
        try:
            decision = self._space.check(result)
        except StaleProposal as exc:
            refusal = IntakeRefusal(IntakeCode.STALE_REVISION, result.action_id, str(exc), suggestion.digest)
            self._journal.append(("suggestion", suggestion.digest, refusal.code.value))
            return refusal
        self._journal.append(("suggestion", suggestion.digest, decision.digest))
        return decision


__all__ = ["MindWorldPort"]
