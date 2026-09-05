"""M4D/M4E — the one utility / value-of-information engine.

Every candidate, from every family, is scored by the same objective:

    score(a) = E[Δu | successful execution, a] · (1 − p_cf(a))
             + Δu_fail(a) · p_cf(a)
             − penalty(E[cost(a)])

where ``p_cf`` is the probability of **computational execution failure** and
``penalty`` converts cost into terminal-utility units through a declared
exchange rate.

M4.1 sharpened four things that were ambiguous in M4.

**Computational failure is not a scientific outcome.** ``p_cf`` is the chance
the *solver* fails to execute — divergence, a coupling breakdown, a numerical
blow-up. A scientifically infeasible design point, a contradicted hypothesis
and an ordinary negative result are all *successful executions*: they belong in
the campaign's outcome distribution, inside ``E[Δu | success]``, not in the
failure channel. Mixing them would let the engine pay twice for one event and
would make "the physics said no" indistinguishable from "the solver crashed".

**The failure term states its own conditioning.** The outcome model supplies a
*conditional* gain — what is learned **given** that execution failed — and the
engine multiplies by ``p_cf`` itself. A bare ``failure_value`` that might or
might not already be probability-weighted is exactly the ambiguity that
produces silent double counting.

**Cost is converted, never subtracted raw.** Seconds are not utility. A
:class:`CostTradeoff` carries the rate, the cost unit, the utility scale it
refers to, its source and its assumptions. Without a declared tradeoff — or an
explicit declaration that cost carries no penalty — formal cost-aware VoI is
simply unavailable. There is no hidden ``lambda = 1``.

**A component that does not exist is UNAVAILABLE**, which makes the candidate
``NOT_SCORABLE``. Nothing is silently defaulted; a declared policy fallback is
marked ``DEFAULTED`` and stays visible all the way into the decision record.

Feasibility still precedes utility: infeasible candidates never reach scoring,
so no amount of information gain can make an inadmissible action attractive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from ...scientific.serialization import require_schema, schema_string
from ..actions import HardFeasibilityGate
from ..calibration.critic import CalibrationVerdict
from .actions import ActionFamily, CandidateAction, OutcomeDependence
from .belief_snapshot import BeliefSnapshot
from .replay import (
    DependencyIdentity,
    DependencyKind,
    canonical_digest,
    identify,
)
from .terminal import TerminalObjective

SCORE_SCHEMA = schema_string("sria_candidate_score")
COMPONENT_SCHEMA = schema_string("sria_score_component")
TRADEOFF_SCHEMA = schema_string("sria_cost_tradeoff")

UTILITY_ENGINE_VERSION = "utility.myopic_evsi/2"

#: Execution-failure causes that can carry scientific information.
#:
#: Deliberately narrow. ``infeasible`` and ``hypothesis_contradiction`` were
#: removed in M4.1: those are *successful executions* whose scientific result
#: happened to be negative, and their value belongs in the outcome
#: distribution. ``infrastructure`` has never been here — a lost node teaches
#: nothing about the physics.
INFORMATIVE_COMPUTATIONAL_FAILURE_CAUSES = frozenset(
    {"numerical", "solver", "coupling"}
)

#: Causes that are scientific outcomes, not execution failures. Naming them
#: explicitly lets the engine reject the confusion instead of ignoring it.
SCIENTIFIC_OUTCOME_CAUSES = frozenset(
    {"infeasible", "hypothesis_contradiction", "scientific", "scope"}
)


class ComponentStatus(str, Enum):
    AVAILABLE = "available"        # measured or supplied by a trusted source
    DEGRADED = "degraded"          # present, but its support is doubtful
    DEFAULTED = "defaulted"        # a declared policy fallback was used
    UNAVAILABLE = "unavailable"    # nothing exists; never silently replaced


class ScoreStatus(str, Enum):
    SCORED = "scored"
    DEGRADED = "degraded"
    NOT_SCORABLE = "not_scorable"
    INFEASIBLE = "infeasible"


class MisusedFailureChannel(Exception):
    """A scientific outcome was declared as a computational failure cause."""


@dataclass(frozen=True)
class CostTradeoff:
    """Declared conversion from cost units into terminal-utility units.

    Generic SRIA cannot know what an hour of compute is worth to a campaign,
    and guessing is how a ranking silently encodes someone's unstated
    preference. The rate, its unit and the utility scale it refers to are all
    campaign-declared and travel with the score.
    """

    rate: float                     # utility units per cost unit
    cost_unit: str
    utility_reference: str
    source: str
    policy_version: str = "1"
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        rate = float(self.rate)
        if rate < 0.0:
            raise ValueError("cost tradeoff rate must be non-negative")
        object.__setattr__(self, "rate", rate)
        for label in ("cost_unit", "utility_reference", "source"):
            if not str(getattr(self, label)).strip():
                raise ValueError(
                    f"cost tradeoff requires {label}; an unattributed exchange "
                    f"rate is a hidden preference"
                )
        object.__setattr__(self, "assumptions", tuple(self.assumptions))

    def penalty(self, cost: float, *, cost_unit: str) -> float:
        """Convert a cost into utility units, refusing a unit mismatch."""
        if str(cost_unit) != self.cost_unit:
            raise ValueError(
                f"cost is expressed in {cost_unit!r} but the declared tradeoff "
                f"converts {self.cost_unit!r}; raw cost must not enter a score "
                f"unconverted"
            )
        return self.rate * float(cost)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TRADEOFF_SCHEMA,
            "rate": self.rate,
            "cost_unit": self.cost_unit,
            "utility_reference": self.utility_reference,
            "source": self.source,
            "policy_version": self.policy_version,
            "assumptions": list(self.assumptions),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CostTradeoff":
        require_schema(payload, TRADEOFF_SCHEMA)
        return cls(
            rate=payload["rate"],
            cost_unit=payload["cost_unit"],
            utility_reference=payload["utility_reference"],
            source=payload["source"],
            policy_version=payload.get("policy_version", "1"),
            assumptions=tuple(payload.get("assumptions", ())),
        )


@dataclass(frozen=True)
class ScoreComponent:
    """One term of the objective, with its provenance attached."""

    name: str
    value: float | None
    status: ComponentStatus
    source: str = ""
    calibration_verdict: CalibrationVerdict | None = None
    unit: str = ""
    assumptions: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ComponentStatus(self.status))
        if self.calibration_verdict is not None:
            object.__setattr__(
                self,
                "calibration_verdict",
                CalibrationVerdict(self.calibration_verdict),
            )
        if self.status is ComponentStatus.UNAVAILABLE and self.value is not None:
            raise ValueError(
                f"component {self.name!r} is UNAVAILABLE but carries a value; "
                f"that is exactly the silent substitution this type prevents"
            )
        if self.status is not ComponentStatus.UNAVAILABLE and self.value is None:
            raise ValueError(
                f"component {self.name!r} claims {self.status.value} but has no value"
            )
        if self.status is ComponentStatus.DEFAULTED and not str(self.detail).strip():
            raise ValueError(
                f"component {self.name!r} used a fallback without saying which; "
                f"a defaulted value must name the policy that supplied it"
            )
        object.__setattr__(self, "assumptions", tuple(self.assumptions))

    @property
    def is_usable(self) -> bool:
        return self.status is not ComponentStatus.UNAVAILABLE

    @property
    def degrades_score(self) -> bool:
        return self.status in (ComponentStatus.DEGRADED, ComponentStatus.DEFAULTED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COMPONENT_SCHEMA,
            "name": self.name,
            "value": self.value,
            "status": self.status.value,
            "source": self.source,
            "calibration_verdict": (
                self.calibration_verdict.value if self.calibration_verdict else None
            ),
            "unit": self.unit,
            "assumptions": list(self.assumptions),
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScoreComponent":
        require_schema(payload, COMPONENT_SCHEMA)
        return cls(
            name=payload["name"],
            value=payload.get("value"),
            status=ComponentStatus(payload["status"]),
            source=payload.get("source", ""),
            calibration_verdict=(
                CalibrationVerdict(payload["calibration_verdict"])
                if payload.get("calibration_verdict")
                else None
            ),
            unit=payload.get("unit", ""),
            assumptions=tuple(payload.get("assumptions", ())),
            detail=payload.get("detail", ""),
        )


@dataclass(frozen=True)
class CandidateScore:
    """The full, auditable score of one candidate."""

    action_id: str
    family: ActionFamily
    status: ScoreStatus
    total: float | None = None
    components: tuple[ScoreComponent, ...] = ()
    feasibility_reason: str = ""
    blocking_reason: str = ""
    is_composite: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", ActionFamily(self.family))
        object.__setattr__(self, "status", ScoreStatus(self.status))
        object.__setattr__(self, "components", tuple(self.components))
        if self.status in (ScoreStatus.SCORED, ScoreStatus.DEGRADED):
            if self.total is None:
                raise ValueError("a scored candidate must carry a total")
        elif self.total is not None:
            raise ValueError(
                f"candidate {self.action_id!r} is {self.status.value} but carries "
                f"a total; an unscorable candidate has no score"
            )

    @property
    def is_rankable(self) -> bool:
        return self.status in (ScoreStatus.SCORED, ScoreStatus.DEGRADED)

    @property
    def is_unresolved(self) -> bool:
        """Eligible but unevaluated — the distinction M4.1 turns on.

        NOT_SCORABLE means "we could not evaluate this", which is a different
        statement from "this is not worth buying". INFEASIBLE candidates are
        properly excluded and are not unresolved.
        """
        return self.status is ScoreStatus.NOT_SCORABLE

    @property
    def degraded_components(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.components if c.degrades_score)

    def component(self, name: str) -> ScoreComponent | None:
        for component in self.components:
            if component.name == name:
                return component
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCORE_SCHEMA,
            "action_id": self.action_id,
            "family": self.family.value,
            "status": self.status.value,
            "total": self.total,
            "components": [c.to_dict() for c in self.components],
            "feasibility_reason": self.feasibility_reason,
            "blocking_reason": self.blocking_reason,
            "is_composite": self.is_composite,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateScore":
        require_schema(payload, SCORE_SCHEMA)
        return cls(
            action_id=payload["action_id"],
            family=ActionFamily(payload["family"]),
            status=ScoreStatus(payload["status"]),
            total=payload.get("total"),
            components=tuple(
                ScoreComponent.from_dict(c) for c in payload.get("components", ())
            ),
            feasibility_reason=payload.get("feasibility_reason", ""),
            blocking_reason=payload.get("blocking_reason", ""),
            is_composite=bool(payload.get("is_composite", False)),
        )


# =====================================================================
# Supplier protocols — the engine never computes these itself
# =====================================================================

@runtime_checkable
class OutcomeModel(Protocol):
    """Campaign/domain supplied outcome expectations."""

    def conditional_success_utility_gain(
        self, candidate: CandidateAction, snapshot: BeliefSnapshot,
        objective: TerminalObjective,
    ) -> ScoreComponent:
        """E[Δu | the run executes successfully].

        Includes every scientific outcome — favourable, unfavourable,
        infeasible, hypothesis-contradicting. Those are results, not failures.
        """

    def conditional_failure_utility_gain(
        self, candidate: CandidateAction, snapshot: BeliefSnapshot,
        objective: TerminalObjective,
    ) -> ScoreComponent:
        """E[Δu | the run fails to execute].

        Conditional on failure, **not** probability-weighted — the engine
        applies ``p_cf`` itself so the conditioning cannot be double counted.
        """


@runtime_checkable
class CostSupplier(Protocol):
    """Expected cost in its own units, sourced from M2 calibration."""

    def expected_cost(
        self, candidate: CandidateAction, snapshot: BeliefSnapshot
    ) -> ScoreComponent:
        ...


@runtime_checkable
class FailureSupplier(Protocol):
    """p(computational execution failure), from M2 — or explicitly absent."""

    def computational_failure_probability(
        self, candidate: CandidateAction, snapshot: BeliefSnapshot
    ) -> ScoreComponent:
        ...


@dataclass(frozen=True)
class UtilityPolicy:
    """Declared scoring policy. Every fallback is declared, never assumed."""

    policy_id: str
    policy_version: str = "1"
    cost_tradeoff: CostTradeoff | None = None
    #: Explicit declaration that this campaign attaches no penalty to cost.
    zero_cost_penalty: bool = False
    #: When p_cf is unavailable, a campaign may declare a conservative default.
    default_failure_probability: float | None = None
    default_failure_rationale: str = ""

    def __post_init__(self) -> None:
        if not str(self.policy_id).strip():
            raise ValueError("utility policy requires a policy_id")
        if not isinstance(self.zero_cost_penalty, bool):
            raise ValueError("zero_cost_penalty must be an explicit bool")
        if self.cost_tradeoff is not None and self.zero_cost_penalty:
            raise ValueError(
                "declare either a cost tradeoff or an explicit zero cost "
                "penalty, not both"
            )
        if self.default_failure_probability is not None:
            value = float(self.default_failure_probability)
            if not 0.0 <= value <= 1.0:
                raise ValueError("default_failure_probability must lie in [0, 1]")
            if not str(self.default_failure_rationale).strip():
                raise ValueError(
                    "a declared p_cf fallback must state its rationale; an "
                    "undocumented default is indistinguishable from a guess"
                )
            object.__setattr__(self, "default_failure_probability", value)

    @property
    def cost_awareness_declared(self) -> bool:
        return self.cost_tradeoff is not None or self.zero_cost_penalty

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "cost_tradeoff": (
                self.cost_tradeoff.to_dict() if self.cost_tradeoff else None
            ),
            "zero_cost_penalty": self.zero_cost_penalty,
            "default_failure_probability": self.default_failure_probability,
            "default_failure_rationale": self.default_failure_rationale,
        }


def declared_failure_causes(candidate: CandidateAction) -> tuple[str, ...]:
    causes = {
        str(cause).lower()
        for member in candidate.members
        for cause in member.proposal.informative_failure_causes
    }
    if candidate.is_composite:
        causes |= {
            str(c).lower() for c in candidate.proposal.informative_failure_causes
        }
    return tuple(sorted(causes))


def informative_failure_causes(candidate: CandidateAction) -> tuple[str, ...]:
    """Declared causes that are genuine, informative *execution* failures."""
    return tuple(
        sorted(
            set(declared_failure_causes(candidate))
            & INFORMATIVE_COMPUTATIONAL_FAILURE_CAUSES
        )
    )


def excluded_failure_causes(candidate: CandidateAction) -> tuple[str, ...]:
    """Declared causes that earn nothing here."""
    return tuple(
        sorted(
            set(declared_failure_causes(candidate))
            - INFORMATIVE_COMPUTATIONAL_FAILURE_CAUSES
        )
    )


def misdeclared_scientific_outcomes(candidate: CandidateAction) -> tuple[str, ...]:
    """Scientific outcomes wrongly declared as computational failures."""
    return tuple(
        sorted(set(declared_failure_causes(candidate)) & SCIENTIFIC_OUTCOME_CAUSES)
    )


class UtilityEngine:
    """Scores every candidate with one objective. Selects nothing."""

    engine_version = UTILITY_ENGINE_VERSION

    def __init__(
        self,
        *,
        policy: UtilityPolicy,
        outcome_model: OutcomeModel,
        cost_supplier: CostSupplier,
        failure_supplier: FailureSupplier,
        feasibility_gate: HardFeasibilityGate | None = None,
    ) -> None:
        self._policy = policy
        self._outcome = outcome_model
        self._cost = cost_supplier
        self._failure = failure_supplier
        self._gate = feasibility_gate

    @property
    def policy(self) -> UtilityPolicy:
        return self._policy

    # ---- executable dependency identity (M4.2) --------------------------
    def dependency_identities(self) -> tuple[DependencyIdentity, ...]:
        """Everything whose fitted state could change this engine's answers.

        The policy, its tradeoff and the engine version are fully described by
        their own content, so they are pinned by digest. The suppliers and the
        outcome model are asked to identify themselves; one that cannot is
        recorded as unpinnable rather than assumed stable.
        """
        policy_identity = DependencyIdentity(
            dependency_id=self._policy.policy_id,
            kind=DependencyKind.UTILITY_POLICY,
            version=self._policy.policy_version,
            state_digest=canonical_digest(self._policy.to_dict()),
            detail="policy is fully described by its own content",
        )
        identities = [
            policy_identity,
            DependencyIdentity(
                dependency_id="sria.utility_engine",
                kind=DependencyKind.UTILITY_ENGINE,
                version=self.engine_version,
                state_digest=canonical_digest({"engine": self.engine_version}),
            ),
            identify(
                self._cost,
                kind=DependencyKind.COST_MODEL,
                fallback_id="cost_supplier",
            ),
            identify(
                self._failure,
                kind=DependencyKind.FAILURE_SOURCE,
                fallback_id="failure_supplier",
            ),
            identify(
                self._outcome,
                kind=DependencyKind.OUTCOME_MODEL,
                fallback_id="outcome_model",
            ),
        ]
        if self._policy.cost_tradeoff is not None:
            identities.append(
                DependencyIdentity(
                    dependency_id="cost_tradeoff",
                    kind=DependencyKind.COST_TRADEOFF,
                    version=self._policy.cost_tradeoff.policy_version,
                    state_digest=canonical_digest(
                        self._policy.cost_tradeoff.to_dict()
                    ),
                )
            )
        return tuple(identities)

    def _feasibility(self, candidate: CandidateAction) -> tuple[bool, str]:
        if self._gate is None:
            return True, "no hard constraints declared"
        for member in candidate.members:
            for verdict in self._gate.evaluate(member.action):
                if not verdict.feasible:
                    return False, f"{verdict.constraint_id}: {verdict.reason}"
        return True, "all hard constraints satisfied"

    def _unscorable(
        self, candidate, reason, *, components=(), feasibility=""
    ) -> CandidateScore:
        return CandidateScore(
            action_id=candidate.action_id,
            family=candidate.family,
            status=ScoreStatus.NOT_SCORABLE,
            components=tuple(components),
            feasibility_reason=feasibility,
            blocking_reason=reason,
            is_composite=candidate.is_composite,
        )

    def score(
        self,
        candidate: CandidateAction,
        snapshot: BeliefSnapshot,
        objective: TerminalObjective,
    ) -> CandidateScore:
        if not objective.is_available:
            return self._unscorable(
                candidate, f"terminal objective unavailable: {objective.reason}"
            )

        # A scientific outcome declared as an execution failure is a modelling
        # error, not something to silently ignore.
        misdeclared = misdeclared_scientific_outcomes(candidate)
        if misdeclared:
            raise MisusedFailureChannel(
                f"candidate {candidate.action_id!r} declares {list(misdeclared)} "
                f"as computational failure causes. Those are successful "
                f"executions with scientific outcomes and belong in the outcome "
                f"distribution, not in the execution-failure channel."
            )

        feasible, reason = self._feasibility(candidate)
        if not feasible:
            return CandidateScore(
                action_id=candidate.action_id,
                family=candidate.family,
                status=ScoreStatus.INFEASIBLE,
                feasibility_reason=reason,
                is_composite=candidate.is_composite,
            )

        if (
            candidate.is_composite
            and candidate.outcome_dependence is OutcomeDependence.UNDECLARED
        ):
            return self._unscorable(
                candidate,
                "composite outcome dependence is UNDECLARED; assuming "
                "independence would overstate the value of the batch",
                feasibility=reason,
            )

        if not self._policy.cost_awareness_declared:
            return self._unscorable(
                candidate,
                "no cost-to-utility tradeoff declared and zero cost penalty was "
                "not asserted; formal cost-aware VoI is unavailable",
                feasibility=reason,
            )

        gain = self._outcome.conditional_success_utility_gain(
            candidate, snapshot, objective
        )
        cost = self._cost.expected_cost(candidate, snapshot)
        p_fail = self._resolve_failure(candidate, snapshot)
        failure_voi = self._expected_failure_voi(
            candidate, snapshot, objective, p_fail
        )
        penalty = self._cost_penalty(cost)
        components = (gain, p_fail, failure_voi, cost, penalty)

        missing = [c.name for c in components if not c.is_usable]
        if missing:
            return self._unscorable(
                candidate,
                f"required component(s) unavailable: {sorted(missing)}; no "
                f"confident value was substituted",
                components=components,
                feasibility=reason,
            )

        total = (
            gain.value * (1.0 - p_fail.value)
            + failure_voi.value
            - penalty.value
        )
        degraded = any(c.degrades_score for c in components)
        return CandidateScore(
            action_id=candidate.action_id,
            family=candidate.family,
            status=ScoreStatus.DEGRADED if degraded else ScoreStatus.SCORED,
            total=total,
            components=components,
            feasibility_reason=reason,
            is_composite=candidate.is_composite,
        )

    # ---- components ------------------------------------------------------
    def _resolve_failure(
        self, candidate: CandidateAction, snapshot: BeliefSnapshot
    ) -> ScoreComponent:
        component = self._failure.computational_failure_probability(
            candidate, snapshot
        )
        if component.is_usable:
            return component
        if self._policy.default_failure_probability is None:
            return component
        return ScoreComponent(
            name=component.name,
            value=self._policy.default_failure_probability,
            status=ComponentStatus.DEFAULTED,
            source=f"policy:{self._policy.policy_id}",
            calibration_verdict=component.calibration_verdict,
            assumptions=(
                "p_computational_failure was not learned; a declared policy "
                "default was used",
            ),
            detail=self._policy.default_failure_rationale,
        )

    def _expected_failure_voi(
        self,
        candidate: CandidateAction,
        snapshot: BeliefSnapshot,
        objective: TerminalObjective,
        p_fail: ScoreComponent,
    ) -> ScoreComponent:
        """conditional gain given failure × p(failure) = expected failure VoI."""
        informative = informative_failure_causes(candidate)
        excluded = excluded_failure_causes(candidate)

        if not informative:
            return ScoreComponent(
                name="expected_failure_voi",
                value=0.0,
                status=ComponentStatus.AVAILABLE,
                source="declared informative execution-failure causes",
                assumptions=(
                    "no informative computational failure cause was declared",
                ),
                detail=(
                    f"non-informative causes earn nothing: {list(excluded)}"
                    if excluded
                    else "execution failure carries no declared information"
                ),
            )

        if not p_fail.is_usable:
            return ScoreComponent(
                name="expected_failure_voi",
                value=None,
                status=ComponentStatus.UNAVAILABLE,
                source="engine",
                detail=(
                    "expected failure VoI needs p_computational_failure, which "
                    "is unavailable"
                ),
            )

        conditional = self._outcome.conditional_failure_utility_gain(
            candidate, snapshot, objective
        )
        if not conditional.is_usable:
            return conditional
        if conditional.value < 0.0:
            raise ValueError(
                f"conditional failure utility gain for {candidate.action_id!r} "
                f"is negative; a failure cannot cost information"
            )

        expected = conditional.value * p_fail.value
        status = (
            ComponentStatus.DEGRADED
            if conditional.degrades_score or p_fail.degrades_score
            else ComponentStatus.AVAILABLE
        )
        return ScoreComponent(
            name="expected_failure_voi",
            value=expected,
            status=status,
            source=conditional.source,
            calibration_verdict=p_fail.calibration_verdict,
            assumptions=conditional.assumptions
            + (
                f"conditional gain {conditional.value:g} weighted by "
                f"p_computational_failure {p_fail.value:g}",
                f"credited only for informative causes {list(informative)}",
            ),
            detail=(
                "expected = conditional x p_cf"
                + (f"; ignored {list(excluded)}" if excluded else "")
            ),
        )

    def _cost_penalty(self, cost: ScoreComponent) -> ScoreComponent:
        policy = self._policy
        if policy.zero_cost_penalty:
            return ScoreComponent(
                name="cost_penalty",
                value=0.0,
                status=ComponentStatus.AVAILABLE,
                source=f"policy:{policy.policy_id}",
                unit=cost.unit,
                assumptions=("campaign declared zero cost penalty",),
                detail="cost carries no terminal-utility penalty by declaration",
            )
        if not cost.is_usable:
            return ScoreComponent(
                name="cost_penalty",
                value=None,
                status=ComponentStatus.UNAVAILABLE,
                source=f"policy:{policy.policy_id}",
                detail="cost is unavailable, so no penalty can be computed",
            )

        tradeoff = policy.cost_tradeoff
        try:
            value = tradeoff.penalty(cost.value, cost_unit=cost.unit)
        except ValueError as exc:
            # Raw, unconverted cost must never enter a formal score.
            return ScoreComponent(
                name="cost_penalty",
                value=None,
                status=ComponentStatus.UNAVAILABLE,
                source=f"policy:{policy.policy_id}",
                detail=str(exc),
            )
        return ScoreComponent(
            name="cost_penalty",
            value=value,
            status=(
                ComponentStatus.DEGRADED
                if cost.degrades_score
                else ComponentStatus.AVAILABLE
            ),
            source=f"{tradeoff.source} (policy {policy.policy_id})",
            calibration_verdict=cost.calibration_verdict,
            unit=tradeoff.utility_reference,
            assumptions=tradeoff.assumptions
            + (
                f"{tradeoff.rate:g} utility per {tradeoff.cost_unit}, scale "
                f"{tradeoff.utility_reference}",
            ),
            detail=f"converted {cost.value:g} {cost.unit} to utility",
        )
