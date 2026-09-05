"""M4B — the six Action-Family Generators.

Each generator proposes candidates from a different angle. That is the whole
of their authority.

**They are not modes.** There is no ``current_family``, no state machine, no
ordering, no family that gates another, and no family that owns budget. Every
candidate from every family goes into one pool and is scored by one engine.
This matters because the alternative — a mode controller deciding "we are now
exploring" — makes the *mode* the decision, and then the utility calculation
is just decoration on a choice already made elsewhere.

A generator's job is to propose and to explain. Whether a proposal is worth
buying is not its call, and none of them can see a score.

Generators are deliberately thin. They read the snapshot, the hypotheses and
the obligations they are given, and emit candidates with typed provenance. Any
domain-specific notion of "poorly understood region" comes from the campaign
supplying targets — SRIA cannot know what is under-explored in someone else's
physics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from ..actions import ExecutorType, ResearchAction
from .actions import ActionFamily, ActionProposal, AtomicAction, CandidateAction
from .belief_snapshot import BeliefSnapshot, FactorAvailability
from .hypotheses import HypothesisSet


@dataclass(frozen=True)
class GenerationContext:
    """Everything a generator may look at. Read-only by construction."""

    snapshot: BeliefSnapshot
    #: Campaign-supplied targets, keyed by family. SRIA does not invent them.
    targets: Mapping[ActionFamily, tuple[Mapping[str, Any], ...]] = field(
        default_factory=dict
    )
    hypotheses: HypothesisSet = field(default_factory=HypothesisSet)
    #: Obligation id -> the check it requires, for VALIDATE.
    validation_targets: Mapping[str, str] = field(default_factory=dict)
    executor_type: ExecutorType = ExecutorType.SIMULATION

    def targets_for(self, family: ActionFamily) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.targets.get(ActionFamily(family), ()))


@runtime_checkable
class ActionFamilyGenerator(Protocol):
    """Proposes candidates. Cannot score, rank, or select."""

    family: ActionFamily

    def generate(self, context: GenerationContext) -> tuple[CandidateAction, ...]:
        ...


def _atomic(
    *,
    action_id: str,
    family: ActionFamily,
    target_ref: str,
    rationale: str,
    context: GenerationContext,
    target: Mapping[str, Any],
    assumptions: Iterable[str] = (),
    informative_failure_causes: Iterable[str] = (),
) -> AtomicAction:
    """Build one candidate from a campaign-supplied target."""
    return AtomicAction(
        action=ResearchAction(
            action_id=action_id,
            executor_type=context.executor_type,
            target_ref=str(target.get("target_ref", target_ref)),
            parameters=target.get("parameters", {}),
            expected_cost=target.get("expected_cost", {}),
            context_ref=context.snapshot.snapshot_id,
        ),
        proposal=ActionProposal(
            family=family,
            target_ref=target_ref,
            rationale=rationale,
            assumptions=tuple(assumptions),
            required_fidelity=str(target.get("fidelity_rung", "")),
            expected_observable=str(target.get("observable", "")),
            informative_failure_causes=tuple(informative_failure_causes),
        ),
    )


class _TargetDrivenGenerator:
    """Shared body: turn declared targets into explained candidates."""

    family: ActionFamily = ActionFamily.EXPLORE
    rationale: str = ""
    assumptions: tuple[str, ...] = ()
    informative_failure_causes: tuple[str, ...] = ()

    def generate(self, context: GenerationContext) -> tuple[CandidateAction, ...]:
        out: list[CandidateAction] = []
        for index, target in enumerate(context.targets_for(self.family)):
            action_id = str(
                target.get("action_id", f"{self.family.value}-{index}")
            )
            out.append(
                _atomic(
                    action_id=action_id,
                    family=self.family,
                    target_ref=str(target.get("target_ref", action_id)),
                    rationale=str(target.get("rationale", self.rationale)),
                    context=context,
                    target=target,
                    assumptions=target.get("assumptions", self.assumptions),
                    informative_failure_causes=target.get(
                        "informative_failure_causes",
                        self.informative_failure_causes,
                    ),
                )
            )
        return tuple(out)


class ExploreGenerator(_TargetDrivenGenerator):
    """Probes regions the campaign has declared poorly understood."""

    family = ActionFamily.EXPLORE
    rationale = "probe a region with little or no admitted evidence"
    assumptions = ("the declared region is reachable by the current solver",)
    #: An explore probe that fails *numerically* has told us where the solver
    #: breaks — a boundary, not a wasted run. Infeasibility is deliberately
    #: absent: an infeasible point is a successful execution whose scientific
    #: answer was "no", and it belongs in the outcome distribution.
    informative_failure_causes = ("numerical",)


class CharacterizeGenerator(_TargetDrivenGenerator):
    """Estimates response or parameter structure where it is already active."""

    family = ActionFamily.CHARACTERIZE
    rationale = "estimate local response structure around known evidence"
    assumptions = ("the response is locally smooth over the sampled span",)


class OptimizeGenerator(_TargetDrivenGenerator):
    """Candidates expected to move the terminal decision directly."""

    family = ActionFamily.OPTIMIZE
    rationale = "expected to improve the declared terminal decision"
    assumptions = ("the terminal utility is the campaign's declared one",)


class ReduceUncertaintyGenerator(_TargetDrivenGenerator):
    """Targets uncertainty that actually bears on the decision."""

    family = ActionFamily.REDUCE_UNCERTAINTY
    rationale = "reduce decision-relevant uncertainty"
    assumptions = ("the targeted channel is the one limiting the decision",)


class DiscriminateGenerator:
    """Proposes where competing hypotheses disagree.

    Needs no prior over models: divergence in prediction is enough to be worth
    resolving. When weights happen to exist they are recorded, not required.
    """

    family = ActionFamily.DISCRIMINATE

    def generate(self, context: GenerationContext) -> tuple[CandidateAction, ...]:
        declared = context.targets_for(self.family)
        disagreements = context.hypotheses.decision_relevant_disagreements()
        weights_note = (
            "hypothesis weights available"
            if context.hypotheses.weights_available
            else "no hypothesis weights exist; proposal rests on prediction "
            "divergence alone"
        )

        out: list[CandidateAction] = []
        for index, disagreement in enumerate(disagreements):
            # A campaign may supply the concrete evaluation for a divergence.
            target: Mapping[str, Any] = {}
            for candidate in declared:
                if candidate.get("observable") == disagreement.observable:
                    target = candidate
                    break
            action_id = str(
                target.get("action_id", f"discriminate-{disagreement.observable}-{index}")
            )
            out.append(
                _atomic(
                    action_id=action_id,
                    family=self.family,
                    target_ref=disagreement.observable,
                    rationale=(
                        f"{disagreement.hypothesis_a} and "
                        f"{disagreement.hypothesis_b} differ by "
                        f"{disagreement.separation:g} on "
                        f"{disagreement.observable}"
                    ),
                    context=context,
                    target={**target, "observable": disagreement.observable},
                    assumptions=(weights_note,),
                    # A contradicted hypothesis is a *successful* execution
                    # with a negative scientific result — it belongs in the
                    # outcome distribution, not the execution-failure channel.
                    # What this probe can learn from an execution failure is
                    # numerical.
                    informative_failure_causes=("numerical",),
                )
            )
        return tuple(out)


class ValidateGenerator:
    """Proposes the evaluations an explicit validation obligation requires.

    Generates candidates; it does not certify anything. Whether the obligation
    is ultimately satisfied stays with the Arbiter.
    """

    family = ActionFamily.VALIDATE

    def generate(self, context: GenerationContext) -> tuple[CandidateAction, ...]:
        declared = {
            str(t.get("obligation_id", "")): t
            for t in context.targets_for(self.family)
        }
        out: list[CandidateAction] = []
        for obligation_id in sorted(context.validation_targets):
            required_check = context.validation_targets[obligation_id]
            if context.snapshot.obligation_state.get(obligation_id) is True:
                continue        # already satisfied; nothing to buy
            target = declared.get(obligation_id, {})
            action_id = str(target.get("action_id", f"validate-{obligation_id}"))
            out.append(
                _atomic(
                    action_id=action_id,
                    family=self.family,
                    target_ref=obligation_id,
                    rationale=(
                        f"obligation {obligation_id!r} requires "
                        f"{required_check!r} and is not yet satisfied"
                    ),
                    context=context,
                    target=target,
                    assumptions=(
                        "certification remains the Arbiter's decision; this "
                        "action only produces the evidence it needs",
                    ),
                )
            )
        return tuple(out)


#: The six families. A tuple, not a controller — nothing here sequences them.
DEFAULT_GENERATORS: tuple[ActionFamilyGenerator, ...] = (
    ExploreGenerator(),
    CharacterizeGenerator(),
    DiscriminateGenerator(),
    OptimizeGenerator(),
    ReduceUncertaintyGenerator(),
    ValidateGenerator(),
)


def generate_candidates(
    context: GenerationContext,
    generators: Iterable[ActionFamilyGenerator] = DEFAULT_GENERATORS,
) -> tuple[CandidateAction, ...]:
    """Pool every family's proposals. Order is by family then id, for
    determinism only — it confers no priority whatsoever."""
    pooled: list[CandidateAction] = []
    for generator in generators:
        pooled.extend(generator.generate(context))
    seen: set[str] = set()
    for candidate in pooled:
        if candidate.action_id in seen:
            raise ValueError(
                f"duplicate candidate id {candidate.action_id!r}; two families "
                f"proposed the same action and the ranking would double-count it"
            )
        seen.add(candidate.action_id)
    return tuple(
        sorted(pooled, key=lambda c: (c.family.value, c.action_id))
    )
