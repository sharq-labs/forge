from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProblemKind(str, Enum):
    ALGEBRAIC = "algebraic"
    ODE = "ode"
    PDE = "pde"
    OPTIMIZATION = "optimization"
    MONTE_CARLO = "monte_carlo"
    GENERIC = "generic"


@dataclass(frozen=True)
class SimulationRequirements:
    problem_kind: ProblemKind
    required_features: tuple[str, ...] = ()
    require_checkpoint_resume: bool = False
    require_adaptive_refinement: bool = False
    minimum_precision_bits: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "problem_kind", ProblemKind(self.problem_kind))
        features = tuple(
            sorted(set(str(x).strip() for x in self.required_features))
        )
        if any(not x for x in features):
            raise ValueError("simulation required features must be non-empty")
        object.__setattr__(self, "required_features", features)
        if self.minimum_precision_bits is not None:
            bits = int(self.minimum_precision_bits)
            if bits < 16:
                raise ValueError("minimum_precision_bits must be >=16")
            object.__setattr__(self, "minimum_precision_bits", bits)


@dataclass(frozen=True)
class SolverCapability:
    solver_id: str
    problem_kinds: tuple[ProblemKind, ...]
    features: tuple[str, ...] = ()
    supports_checkpoint_resume: bool = False
    supports_adaptive_refinement: bool = False
    precision_bits: int = 53
    preference: int = 0

    def __post_init__(self) -> None:
        solver = str(self.solver_id).strip()
        kinds = tuple(sorted(
            set(ProblemKind(x) for x in self.problem_kinds),
            key=lambda x: x.value,
        ))
        features = tuple(sorted(set(str(x).strip() for x in self.features)))
        if not solver or not kinds or any(not x for x in features):
            raise ValueError("solver capability requires id, problem kinds and valid features")
        bits = int(self.precision_bits)
        if bits < 16:
            raise ValueError("solver precision_bits must be >=16")
        object.__setattr__(self, "solver_id", solver)
        object.__setattr__(self, "problem_kinds", kinds)
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "precision_bits", bits)
        object.__setattr__(self, "preference", int(self.preference))

    def satisfies(self, requirements: SimulationRequirements) -> bool:
        if requirements.problem_kind not in self.problem_kinds:
            return False
        if not set(requirements.required_features) <= set(self.features):
            return False
        if (
            requirements.require_checkpoint_resume
            and not self.supports_checkpoint_resume
        ):
            return False
        if (
            requirements.require_adaptive_refinement
            and not self.supports_adaptive_refinement
        ):
            return False
        if (
            requirements.minimum_precision_bits is not None
            and self.precision_bits < requirements.minimum_precision_bits
        ):
            return False
        return True


def rank_solver_capabilities(
    capabilities: tuple[SolverCapability, ...],
    requirements: SimulationRequirements,
) -> tuple[SolverCapability, ...]:
    candidates = [cap for cap in capabilities if cap.satisfies(requirements)]
    return tuple(
        sorted(
            candidates,
            key=lambda cap: (
                -cap.preference,
                -cap.precision_bits,
                cap.solver_id,
            ),
        )
    )
