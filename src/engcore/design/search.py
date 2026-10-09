"""A deterministic multi-fidelity discovery loop over the existing design contracts.

    candidates (D2 Halton sampler) -> grammar gate -> history de-duplication
        -> rung 0 evaluation for all admitted -> promotion policy
        -> rung 1 for promoted only -> ... (while evaluators exist)

Everything is recorded: refused proposals, skipped repeats, every observation,
every promotion decision with its reason, and an append-only history.  The
run's output is a :class:`DiscoveryRun` whose classification is
``search_record_not_validation``.  There is no "winner": each candidate has a
fidelity standing (SUPPORTED / CONTRADICTED / CONFLICTED / UNDECIDED), and
SUPPORTED means "met the declared criteria at the highest rung that decided",
never validated, never scientifically supported.

Evaluators are caller-owned (:class:`RungEvaluator`): they materialize Twins,
run providers and return :class:`~.multifidelity.FidelityObservation` records.
The loop never fabricates an observation; an evaluator that raises is
recorded as a provider failure for that candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.values import ScientificValue, encode_value
from .generation import CandidateProposal, assignment_digest
from .grammar import DesignGrammar
from .history import AttemptOutcome, DesignAttempt, DesignHistory
from .multifidelity import FidelityLedger, FidelityObservation, FidelityOutcome, PromotionDecision, PromotionPolicy, Standing
from .sampling import MixedVariableSampler
from .space import DesignSpace

DISCOVERY_RUN_SCHEMA = "engcore.design.discovery_run/1"

_ATTEMPT = {FidelityOutcome.SUPPORTS: AttemptOutcome.SUCCEEDED, FidelityOutcome.CONTRADICTS: AttemptOutcome.CONTRADICTED,
            FidelityOutcome.INCONCLUSIVE: AttemptOutcome.PARTIAL, FidelityOutcome.REFUSED: AttemptOutcome.REFUSED,
            FidelityOutcome.PROVIDER_FAILED: AttemptOutcome.PROVIDER_FAILED}


@runtime_checkable
class RungEvaluator(Protocol):
    rung_id: str
    provider: str

    def evaluate(self, candidate_key: str, assignments: Mapping[str, ScientificValue]) -> FidelityObservation:
        ...


def candidate_key(space: DesignSpace, assignments: Mapping[str, ScientificValue]) -> str:
    return canonical_digest({"space": list(space.reference.key), "assignment": assignment_digest(assignments)})


@dataclass(frozen=True)
class DiscoveryRun:
    space: DesignSpace
    context_digest: str
    assignments: Mapping[str, Mapping[str, ScientificValue]]
    ledgers: Mapping[str, FidelityLedger]
    promotions: tuple[PromotionDecision, ...]
    rejected: Mapping[str, tuple[str, ...]]
    skipped: Mapping[str, str]
    history_head: str
    policy_digest: str
    grammar_digest: str

    def standings(self) -> dict[str, tuple[str, int | None, str]]:
        out = {}
        for key, ledger in sorted(self.ledgers.items()):
            s, rank, why = ledger.standing()
            out[key] = (s.value, rank, why)
        return out

    def supported_at_highest_rank(self) -> tuple[str, ...]:
        """Candidates SUPPORTED at the highest rank any candidate reached.  Not validated; not a design approval."""
        rows = [(k, *v.standing()[:2]) for k, v in self.ledgers.items()]
        ranks = [r for _, s, r in rows if s is Standing.SUPPORTED and r is not None]
        if not ranks:
            return ()
        top = max(ranks)
        return tuple(sorted(k for k, s, r in rows if s is Standing.SUPPORTED and r == top))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": DISCOVERY_RUN_SCHEMA, "classification": "search_record_not_validation",
                "space": list(self.space.reference.key), "context_digest": self.context_digest,
                "assignments": {k: {n: encode_value(v) for n, v in sorted(a.items())} for k, a in sorted(self.assignments.items())},
                "observations": {k: [o.to_dict() for o in led.observations] for k, led in sorted(self.ledgers.items())},
                "standings": {k: list(v) for k, v in self.standings().items()},
                "promotions": [p.to_dict() for p in self.promotions], "rejected": {k: list(v) for k, v in sorted(self.rejected.items())},
                "skipped": dict(sorted(self.skipped.items())), "history_head": self.history_head, "policy_digest": self.policy_digest,
                "grammar_digest": self.grammar_digest}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


def run_discovery(space: DesignSpace, *, count: int, evaluators: Mapping[str, RungEvaluator], policy: PromotionPolicy,
                  context_digest: str, grammar: DesignGrammar | None = None, history: DesignHistory | None = None,
                  start_index: int = 1) -> DiscoveryRun:
    """Run one deterministic campaign.  ``history`` is appended to (and consulted to skip deterministic repeats)."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise InvalidScientificProblem("count must be a positive integer")
    if len(str(context_digest)) != 64:
        raise InvalidScientificProblem("a discovery run is bound to a 64-hex evaluation context digest")
    if grammar is not None and grammar.space.reference.key != space.reference.key:
        raise InvalidScientificProblem("grammar ranges over another design space")
    ladder = policy.ladder
    for rung_id, ev in evaluators.items():
        ladder.rung(rung_id)
        if not isinstance(ev, RungEvaluator) or ev.rung_id != rung_id:
            raise InvalidScientificProblem(f"evaluator for {rung_id!r} does not declare that rung")
    rungs = [r for r in ladder.rungs if r.rung_id in evaluators]
    if not rungs or rungs[0].rank != min(r.rank for r in ladder.rungs if r.rung_id in evaluators):
        raise InvalidScientificProblem("no evaluator was supplied")
    history = history if history is not None else DesignHistory()
    sampler = MixedVariableSampler(space)
    assignments: dict[str, dict[str, ScientificValue]] = {}
    rejected: dict[str, tuple[str, ...]] = {}
    for index in range(start_index, start_index + count):
        a = sampler.assignments_at(index)
        key = candidate_key(space, a)
        if key in assignments or key in rejected:
            continue
        if grammar is not None:
            decision = grammar.decide(CandidateProposal(candidate_id=f"cand-{key[:16]}", design_space=space.reference,
                                                         sequence_index=index, assignments=a))
            if not decision.accepted:
                rejected[key] = decision.reasons
                history.record(DesignAttempt(key, "admission", context_digest, AttemptOutcome.REFUSED, "; ".join(decision.reasons),
                                             provider="design-grammar"))
                continue
        assignments[key] = a
    ledgers = {k: FidelityLedger(k) for k in assignments}
    skipped: dict[str, str] = {}
    promotions: list[PromotionDecision] = []
    active = sorted(assignments)
    for i, rung in enumerate(rungs):
        ev = evaluators[rung.rung_id]
        for key in active:
            skip, why = history.should_skip(key, rung.rung_id, context_digest, provider=ev.provider)
            if skip:
                skipped[f"{key}@{rung.rung_id}"] = why
                continue
            try:
                obs = ev.evaluate(key, assignments[key])
            except Exception as exc:  # noqa: BLE001 - recorded, never converted into an observation
                obs = FidelityObservation(key, rung.rung_id, rung.rank, FidelityOutcome.PROVIDER_FAILED, ev.provider,
                                          f"evaluator raised {type(exc).__name__}: {exc}")
            if not isinstance(obs, FidelityObservation) or obs.candidate_key != key or obs.rung_id != rung.rung_id:
                raise InvalidScientificProblem(f"evaluator for {rung.rung_id!r} returned an observation of another candidate or rung")
            obs.validate_against(ladder)
            ledgers[key] = ledgers[key].add(obs)
            history.record(DesignAttempt(key, rung.rung_id, context_digest, _ATTEMPT[obs.outcome], obs.reason, provider=obs.provider,
                                         verdict=ledgers[key].standing()[0].value, uncertainty=obs.uncertainty))
        if i + 1 < len(rungs):
            if ladder.next_after(rung.rung_id).rung_id != rungs[i + 1].rung_id:
                raise InvalidScientificProblem("evaluators must cover consecutive rungs; a skipped rung is not promoted over silently")
            decisions = policy.decide([ledgers[k] for k in active], rung.rung_id)
            promotions.extend(decisions)
            active = [d.candidate_key for d in decisions if d.promoted]
    return DiscoveryRun(space, context_digest, assignments, ledgers, tuple(promotions), rejected, skipped, history.head, policy.digest,
                        grammar.digest if grammar is not None else "")
