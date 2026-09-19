from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .attempt import AttemptState
from .checkpoint import CheckpointReference
from .adaptive import RefinementDiagnostics
from .refinement import RefinementRequest
from .resources import ResourceUsage


@dataclass(frozen=True)
class AdvancedBackendOutcome:
    state: AttemptState
    usage: ResourceUsage
    diagnostics: RefinementDiagnostics = RefinementDiagnostics()
    failure_code: str = ""
    checkpoint: CheckpointReference | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", AttemptState(self.state))
        if not isinstance(self.usage, ResourceUsage):
            raise TypeError("advanced backend outcome usage must be ResourceUsage")
        if not isinstance(self.diagnostics, RefinementDiagnostics):
            raise TypeError(
                "advanced backend diagnostics must be RefinementDiagnostics"
            )
        if (
            self.state in {AttemptState.FAILED, AttemptState.DIVERGED}
            and not str(self.failure_code).strip()
        ):
            raise ValueError(
                "failed/diverged advanced backend outcome requires failure_code"
            )


class AdvancedSimulationBackend(Protocol):
    solver_id: str

    def run_advanced(
        self,
        *,
        attempt_id: str,
        deterministic_seed: int | None,
        checkpoint: CheckpointReference | None,
        refinement: RefinementRequest | None,
    ) -> AdvancedBackendOutcome: ...
