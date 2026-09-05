"""M5D/M5E — the simulation executor contract.

The executor runs one selected action and reports what happened. It is
deliberately the *only* component in M5 that knows how a solver works, and
deliberately incapable of doing anything with the answer.

**An execution record cannot write belief.** It is a frozen dataclass holding a
result and some telemetry. It has no gateway, no admission declaration, no
`submit`, and no path to one. The route from a number to a belief runs
Execution -> ScientificResult -> candidate Evidence -> Critics -> Arbiter ->
AdmissionAuthority -> Gateway, and every one of those steps can refuse. Letting
an executor shortcut that would mean a solver's opinion of its own output became
scientific fact.

**PHYSICAL stays closed.** :func:`require_simulation` refuses any action whose
executor type is not SIMULATION, using the frozen M1
:class:`ReservedNotImplemented`. A laboratory action consumes irreplaceable
material and can injure someone; it is not something to leave half-wired.

**Composites execute as one selected action.** A composite's members run under
its declared ordering, and its realized cost aggregates under its declared
:class:`CostAggregation` — the frozen M4 semantics, not a new rule invented
here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ...scientific.serialization import require_schema, schema_string
from ..actions import ExecutorType, IMPLEMENTED_EXECUTORS
from ..decision.actions import CandidateAction, CostAggregation
from ..errors import ReservedNotImplemented
from ..outcomes import Disposition, RunOutcome
from ..signatures import EnvironmentSignature, StructureSignature

EXECUTION_SCHEMA = schema_string("sria_campaign_execution_record")


def require_simulation(action: CandidateAction) -> None:
    """Refuse anything that is not a simulation. Reserved means unavailable."""
    for member in action.members:
        executor_type = ExecutorType(member.action.executor_type)
        if executor_type not in IMPLEMENTED_EXECUTORS:
            raise ReservedNotImplemented(
                f"action {member.action_id!r} declares executor "
                f"{executor_type.value!r}; only SIMULATION is implemented in "
                f"SRIA V0.1 and physical execution is not wired at all"
            )


@dataclass(frozen=True)
class MemberExecution:
    """What one member of the selected action consumed and produced."""

    action_id: str
    realized_cost: float
    outcome: RunOutcome
    result_ref: str = ""
    result: Any | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.realized_cost < 0.0:
            raise ValueError("realized cost must be non-negative")
        object.__setattr__(self, "diagnostics", dict(self.diagnostics))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "realized_cost": self.realized_cost,
            "outcome": self.outcome.to_dict(),
            "result_ref": self.result_ref,
            "diagnostics": dict(sorted(self.diagnostics.items())),
        }


@dataclass(frozen=True)
class ExecutionRecord:
    """Typed execution information. Telemetry and a result, nothing more."""

    execution_id: str
    action_id: str
    run_evaluation_id: str
    solver_identity: tuple[str, str]
    structure: StructureSignature
    environment: EnvironmentSignature
    realized_cost: float
    outcome: RunOutcome
    cost_unit: str = "hour"
    result: Any | None = None
    result_ref: str = ""
    members: tuple[MemberExecution, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    provenance_ref: str = ""
    started_at: str = ""
    ended_at: str = ""
    fidelity_rung: str = ""

    def __post_init__(self) -> None:
        for label in ("execution_id", "action_id"):
            if not str(getattr(self, label)).strip():
                raise ValueError(f"execution record requires {label}")
        identity = tuple(self.solver_identity)
        if len(identity) != 2 or not all(str(p).strip() for p in identity):
            raise ValueError(
                "solver_identity must be (id, version); an unattributed run "
                "cannot be calibrated against or reproduced"
            )
        object.__setattr__(self, "solver_identity", identity)
        if self.realized_cost < 0.0:
            raise ValueError("realized cost must be non-negative")
        object.__setattr__(self, "members", tuple(self.members))
        object.__setattr__(self, "diagnostics", dict(self.diagnostics))

    @property
    def succeeded(self) -> bool:
        return self.outcome.disposition is Disposition.SUCCESS

    @property
    def yielded_result(self) -> bool:
        """Whether there is anything for the evidence pipeline to work on."""
        return self.result is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXECUTION_SCHEMA,
            "execution_id": self.execution_id,
            "action_id": self.action_id,
            "run_evaluation_id": self.run_evaluation_id,
            "solver_identity": list(self.solver_identity),
            "structure_digest": self.structure.digest,
            "environment_digest": self.environment.digest,
            "realized_cost": self.realized_cost,
            "cost_unit": self.cost_unit,
            "outcome": self.outcome.to_dict(),
            "result_ref": self.result_ref,
            "members": [m.to_dict() for m in self.members],
            "diagnostics": dict(sorted(self.diagnostics.items())),
            "provenance_ref": self.provenance_ref,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "fidelity_rung": self.fidelity_rung,
        }


def aggregate_member_cost(
    action: CandidateAction, members: Sequence[MemberExecution]
) -> float:
    """Combine realized member costs under the composite's frozen semantics."""
    costs = {m.action_id: m.realized_cost for m in members}
    if not action.is_composite:
        return float(sum(costs.values()))
    if action.cost_aggregation is CostAggregation.DECLARED:
        # A declared total is a *prediction*; realized cost is what happened.
        # Summing what actually ran is the honest realization of a declared
        # aggregate, and the difference shows up as an overrun.
        return float(sum(costs.values()))
    if action.cost_aggregation is CostAggregation.MAX:
        return float(max(costs.values())) if costs else 0.0
    return float(sum(costs.values()))


@runtime_checkable
class SimulationExecutor(Protocol):
    """Runs one action. Knows solvers; knows nothing about belief."""

    executor_id: str
    executor_version: str

    def execute(
        self, action: CandidateAction, *, execution_id: str, context: Any = None
    ) -> ExecutionRecord:
        ...

    def fetch_execution(self, execution_id: str) -> ExecutionRecord | None:
        """Return a completed execution, or ``None`` if it cannot be found.

        Optional but strongly recommended. A campaign interrupted after a run
        completed needs the result back, and the one thing it must not do is
        re-run the solver to get it. An executor that cannot answer this leaves
        the campaign paused for an operator, which is the honest outcome.
        """
        ...
