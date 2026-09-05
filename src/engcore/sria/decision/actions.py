"""M4B — candidate actions: atomic, composite, and why they were proposed.

Wraps the frozen M1 :class:`~engcore.sria.actions.ResearchAction` rather than
replacing it, so feasibility gating and executor reservations keep working
unchanged.

Two things this module insists on.

**A proposal must explain itself.** :class:`ActionProposal` carries the
generating family, the belief or objective it targets, why it was proposed,
its assumptions, the fidelity it needs and the observable it expects. A
candidate that cannot say why it exists cannot be reviewed, and a ranking made
of such candidates is a black box regardless of how principled the arithmetic
looks.

**Composite outcomes are never assumed independent.** Greedy one-point VoI
misses paired designs — a discrimination pair, a low/high-fidelity pair, a
calibration-plus-target run — so composites are first-class. But their value
depends entirely on how their outcomes relate, and assuming independence is
the single easiest way to overstate the value of a batch. ``UNDECLARED`` is
the default, and the utility engine refuses to aggregate an undeclared
composite rather than quietly multiplying probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from ...scientific.serialization import require_schema, schema_string
from ..actions import ExecutorType, ResearchAction

PROPOSAL_SCHEMA = schema_string("sria_action_proposal")
ATOMIC_SCHEMA = schema_string("sria_atomic_action")
COMPOSITE_SCHEMA = schema_string("sria_composite_action")


class ActionFamily(str, Enum):
    """Which generator proposed a candidate.

    A *label on a proposal*, not a mode. There is no ``current_family``, no
    state machine, and no ordering between families: every candidate from
    every family is scored by the same engine, and a family that proposes
    nothing useful simply loses on score.
    """

    EXPLORE = "explore"
    CHARACTERIZE = "characterize"
    DISCRIMINATE = "discriminate"
    OPTIMIZE = "optimize"
    REDUCE_UNCERTAINTY = "reduce_uncertainty"
    VALIDATE = "validate"


class OutcomeDependence(str, Enum):
    """How a composite's member outcomes relate."""

    #: Declared independent by whoever built the composite, with a rationale.
    INDEPENDENT_DECLARED = "independent_declared"
    #: Declared dependent; joint semantics supplied by the proposer.
    DEPENDENT_DECLARED = "dependent_declared"
    #: Nobody said. The engine will not guess. Default on purpose.
    UNDECLARED = "undeclared"


class CostAggregation(str, Enum):
    """How member costs combine into the composite's cost."""

    SUM = "sum"                  # sequential execution
    MAX = "max"                  # fully parallel
    DECLARED = "declared"        # proposer supplies the total explicitly


class ExecutionOrder(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    UNSPECIFIED = "unspecified"


@dataclass(frozen=True)
class ActionProposal:
    """Typed provenance for why a candidate exists."""

    family: ActionFamily
    target_ref: str                     # belief key, hypothesis, obligation…
    rationale: str
    assumptions: tuple[str, ...] = ()
    required_fidelity: str = ""         # a Domain-Pack rung id, or empty
    expected_observable: str = ""       # the QoI this is expected to inform
    informative_failure_causes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", ActionFamily(self.family))
        for label in ("target_ref", "rationale"):
            if not str(getattr(self, label)).strip():
                raise ValueError(
                    f"action proposal requires {label}; a candidate that cannot "
                    f"say what it targets or why cannot be reviewed"
                )
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(
            self, "informative_failure_causes", tuple(self.informative_failure_causes)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROPOSAL_SCHEMA,
            "family": self.family.value,
            "target_ref": self.target_ref,
            "rationale": self.rationale,
            "assumptions": list(self.assumptions),
            "required_fidelity": self.required_fidelity,
            "expected_observable": self.expected_observable,
            "informative_failure_causes": list(self.informative_failure_causes),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ActionProposal":
        require_schema(payload, PROPOSAL_SCHEMA)
        return cls(
            family=ActionFamily(payload["family"]),
            target_ref=payload["target_ref"],
            rationale=payload["rationale"],
            assumptions=tuple(payload.get("assumptions", ())),
            required_fidelity=payload.get("required_fidelity", ""),
            expected_observable=payload.get("expected_observable", ""),
            informative_failure_causes=tuple(
                payload.get("informative_failure_causes", ())
            ),
        )


@dataclass(frozen=True)
class AtomicAction:
    """One M1 ResearchAction plus the proposal that produced it."""

    action: ResearchAction
    proposal: ActionProposal

    def __post_init__(self) -> None:
        if not isinstance(self.action, ResearchAction):
            raise TypeError("AtomicAction wraps an M1 ResearchAction")
        if not isinstance(self.proposal, ActionProposal):
            raise TypeError("AtomicAction requires an ActionProposal")

    @property
    def action_id(self) -> str:
        return self.action.action_id

    @property
    def family(self) -> ActionFamily:
        return self.proposal.family

    @property
    def is_composite(self) -> bool:
        return False

    @property
    def members(self) -> tuple["AtomicAction", ...]:
        return (self,)

    @property
    def executor_types(self) -> tuple[ExecutorType, ...]:
        return (self.action.executor_type,)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ATOMIC_SCHEMA,
            "action": self.action.to_dict(),
            "proposal": self.proposal.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AtomicAction":
        require_schema(payload, ATOMIC_SCHEMA)
        return cls(
            action=ResearchAction.from_dict(payload["action"]),
            proposal=ActionProposal.from_dict(payload["proposal"]),
        )


@dataclass(frozen=True)
class CompositeAction:
    """Several actions bought together, with their relationship declared."""

    composite_id: str
    proposal: ActionProposal
    members: tuple[AtomicAction, ...]
    order: ExecutionOrder = ExecutionOrder.UNSPECIFIED
    cost_aggregation: CostAggregation = CostAggregation.SUM
    declared_total_cost: float | None = None
    outcome_dependence: OutcomeDependence = OutcomeDependence.UNDECLARED
    dependence_rationale: str = ""
    failure_dependencies: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not str(self.composite_id).strip():
            raise ValueError("composite action requires an id")
        object.__setattr__(self, "members", tuple(self.members))
        if len(self.members) < 2:
            raise ValueError(
                "a composite with fewer than two members is an atomic action"
            )
        object.__setattr__(self, "order", ExecutionOrder(self.order))
        object.__setattr__(
            self, "cost_aggregation", CostAggregation(self.cost_aggregation)
        )
        object.__setattr__(
            self, "outcome_dependence", OutcomeDependence(self.outcome_dependence)
        )
        object.__setattr__(
            self, "failure_dependencies", tuple(self.failure_dependencies)
        )

        if (
            self.cost_aggregation is CostAggregation.DECLARED
            and self.declared_total_cost is None
        ):
            raise ValueError(
                "DECLARED cost aggregation requires declared_total_cost"
            )
        if (
            self.outcome_dependence is not OutcomeDependence.UNDECLARED
            and not str(self.dependence_rationale).strip()
        ):
            raise ValueError(
                "declaring outcome dependence requires a rationale; "
                "'independent' is a modelling claim, not a formatting choice"
            )
        if (
            self.cost_aggregation is CostAggregation.MAX
            and self.order is ExecutionOrder.SEQUENTIAL
        ):
            raise ValueError(
                "MAX cost aggregation assumes parallel execution but the order "
                "is declared SEQUENTIAL"
            )

    @property
    def action_id(self) -> str:
        return self.composite_id

    @property
    def family(self) -> ActionFamily:
        return self.proposal.family

    @property
    def is_composite(self) -> bool:
        return True

    @property
    def executor_types(self) -> tuple[ExecutorType, ...]:
        return tuple(m.action.executor_type for m in self.members)

    @property
    def assumes_independence(self) -> bool:
        return self.outcome_dependence is OutcomeDependence.INDEPENDENT_DECLARED

    def aggregate_cost(self, member_costs: Mapping[str, float]) -> float:
        """Combine member costs under the declared rule."""
        if self.cost_aggregation is CostAggregation.DECLARED:
            return float(self.declared_total_cost)
        values = [float(member_costs[m.action_id]) for m in self.members]
        if self.cost_aggregation is CostAggregation.MAX:
            return max(values)
        return sum(values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COMPOSITE_SCHEMA,
            "composite_id": self.composite_id,
            "proposal": self.proposal.to_dict(),
            "members": [m.to_dict() for m in self.members],
            "order": self.order.value,
            "cost_aggregation": self.cost_aggregation.value,
            "declared_total_cost": self.declared_total_cost,
            "outcome_dependence": self.outcome_dependence.value,
            "dependence_rationale": self.dependence_rationale,
            "failure_dependencies": [list(d) for d in self.failure_dependencies],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CompositeAction":
        require_schema(payload, COMPOSITE_SCHEMA)
        return cls(
            composite_id=payload["composite_id"],
            proposal=ActionProposal.from_dict(payload["proposal"]),
            members=tuple(AtomicAction.from_dict(m) for m in payload["members"]),
            order=ExecutionOrder(payload.get("order", "unspecified")),
            cost_aggregation=CostAggregation(payload.get("cost_aggregation", "sum")),
            declared_total_cost=payload.get("declared_total_cost"),
            outcome_dependence=OutcomeDependence(
                payload.get("outcome_dependence", "undeclared")
            ),
            dependence_rationale=payload.get("dependence_rationale", ""),
            failure_dependencies=tuple(
                tuple(d) for d in payload.get("failure_dependencies", ())
            ),
        )


#: Either kind of candidate.
CandidateAction = AtomicAction | CompositeAction


def candidate_actions(items: Iterable[Any]) -> tuple[CandidateAction, ...]:
    out: list[CandidateAction] = []
    for item in items:
        if not isinstance(item, (AtomicAction, CompositeAction)):
            raise TypeError(
                f"candidate must be an AtomicAction or CompositeAction, got "
                f"{type(item).__name__}"
            )
        out.append(item)
    return tuple(out)
