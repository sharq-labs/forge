"""Research action contract.

An action is "a thing the campaign could do next". Simulations are the only
executor implemented in V0.1; ``PHYSICAL`` is reserved because a laboratory
action has properties a simulation does not — it consumes irreplaceable
material, it can injure someone, and it cannot be retried by re-running a
process.

That asymmetry is why the hard-feasibility hook exists *now*, before any
utility ranking does. Safety and feasibility are not low-priority objectives to
be traded off against expected information gain; they are filters applied
first. Building the ranking first and bolting constraints on afterwards is how
systems end up scoring an infeasible action highly and then explaining why it
was "optimal".

M1 implements the gate and leaves the ranking absent — deliberately. There is
no utility function here to be tempted into using.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from ..scientific.ir.values import ScientificValue, decode_value, encode_value
from ..scientific.serialization import require_schema, schema_string
from .errors import ActionContractError, FeasibilityViolation, ReservedNotImplemented

ACTION_SCHEMA = schema_string("sria_research_action")
FEASIBILITY_VERDICT_SCHEMA = schema_string("sria_feasibility_verdict")


class ExecutorType(str, Enum):
    SIMULATION = "simulation"
    PHYSICAL = "physical"    # reserved


IMPLEMENTED_EXECUTORS = frozenset({ExecutorType.SIMULATION})


@dataclass(frozen=True)
class ResearchAction:
    """A candidate next step, independent of who would execute it."""

    action_id: str
    executor_type: ExecutorType
    target_ref: str
    parameters: Mapping[str, ScientificValue] = field(default_factory=dict)
    expected_cost: Mapping[str, ScientificValue] = field(default_factory=dict)
    context_ref: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in ("action_id", "target_ref"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ActionContractError(f"research action requires {label}")
            object.__setattr__(self, label, value)
        object.__setattr__(self, "executor_type", ExecutorType(self.executor_type))

        for label in ("parameters", "expected_cost"):
            values = dict(getattr(self, label))
            for name, value in values.items():
                try:
                    encode_value(value)
                except Exception as exc:
                    raise ActionContractError(
                        f"action {self.action_id!r} {label}[{name!r}] must be a "
                        f"typed scientific value: {exc}"
                    ) from exc
            object.__setattr__(self, label, values)

        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ACTION_SCHEMA,
            "action_id": self.action_id,
            "executor_type": self.executor_type.value,
            "target_ref": self.target_ref,
            "parameters": {
                k: encode_value(self.parameters[k]) for k in sorted(self.parameters)
            },
            "expected_cost": {
                k: encode_value(self.expected_cost[k])
                for k in sorted(self.expected_cost)
            },
            "context_ref": self.context_ref,
            "metadata": dict(sorted(self.metadata.items(), key=lambda kv: kv[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResearchAction":
        require_schema(payload, ACTION_SCHEMA)
        return cls(
            action_id=payload["action_id"],
            executor_type=ExecutorType(payload["executor_type"]),
            target_ref=payload["target_ref"],
            parameters={
                k: decode_value(v)
                for k, v in (payload.get("parameters") or {}).items()
            },
            expected_cost={
                k: decode_value(v)
                for k, v in (payload.get("expected_cost") or {}).items()
            },
            context_ref=payload.get("context_ref", ""),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class FeasibilityVerdict:
    """Result of one hard constraint applied to one action."""

    constraint_id: str
    feasible: bool
    reason: str = ""

    def __post_init__(self) -> None:
        constraint_id = str(self.constraint_id).strip()
        if not constraint_id:
            raise ActionContractError("feasibility verdict requires a constraint_id")
        object.__setattr__(self, "constraint_id", constraint_id)
        if not isinstance(self.feasible, bool):
            raise ActionContractError("feasibility verdict must be an explicit bool")
        if not self.feasible and not str(self.reason).strip():
            raise ActionContractError(
                f"constraint {constraint_id!r} rejected an action without a "
                f"reason; an unexplained veto cannot be reviewed"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FEASIBILITY_VERDICT_SCHEMA,
            "constraint_id": self.constraint_id,
            "feasible": self.feasible,
            "reason": self.reason,
        }


@runtime_checkable
class HardConstraint(Protocol):
    """A safety/feasibility rule evaluated *before* any ranking."""

    constraint_id: str

    def evaluate(self, action: ResearchAction) -> FeasibilityVerdict:
        ...


class HardFeasibilityGate:
    """Applies every hard constraint, with no notion of score or trade-off.

    Kept separate from any future utility ranking so that the ordering —
    filter first, rank second — is a property of the architecture rather than
    a convention someone has to remember.
    """

    def __init__(self, constraints: Iterable[HardConstraint] = ()) -> None:
        self._constraints = tuple(constraints)
        for constraint in self._constraints:
            if not hasattr(constraint, "evaluate"):
                raise ActionContractError(
                    f"hard constraint {constraint!r} has no evaluate()"
                )

    @property
    def constraints(self) -> tuple[HardConstraint, ...]:
        return self._constraints

    def evaluate(self, action: ResearchAction) -> tuple[FeasibilityVerdict, ...]:
        return tuple(c.evaluate(action) for c in self._constraints)

    def is_feasible(self, action: ResearchAction) -> bool:
        return all(v.feasible for v in self.evaluate(action))

    def filter(self, actions: Iterable[ResearchAction]) -> tuple[ResearchAction, ...]:
        """Admissible actions only. Ranking is not implemented in M1."""
        return tuple(a for a in actions if self.is_feasible(a))

    def require_feasible(self, action: ResearchAction) -> None:
        for verdict in self.evaluate(action):
            if not verdict.feasible:
                raise FeasibilityViolation(
                    f"action {action.action_id!r} rejected by "
                    f"{verdict.constraint_id!r}: {verdict.reason}"
                )


def require_executable(action: ResearchAction) -> None:
    """Guard the execution path. Representing a reserved executor is allowed."""
    if action.executor_type not in IMPLEMENTED_EXECUTORS:
        raise ReservedNotImplemented(
            f"executor {action.executor_type.value!r} is reserved in SRIA V0.1; "
            f"physical execution is not implemented"
        )
