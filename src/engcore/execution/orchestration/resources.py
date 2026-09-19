from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ResourceBudget:
    max_wall_seconds: float | None = None
    max_cpu_seconds: float | None = None
    max_peak_memory_bytes: int | None = None
    max_function_evaluations: int | None = None

    def __post_init__(self) -> None:
        for name in ("max_wall_seconds", "max_cpu_seconds"):
            value = getattr(self, name)
            if value is not None:
                value = float(value)
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f"{name} must be finite and positive")
                object.__setattr__(self, name, value)
        for name in ("max_peak_memory_bytes", "max_function_evaluations"):
            value = getattr(self, name)
            if value is not None:
                if isinstance(value, bool) or int(value) <= 0:
                    raise ValueError(f"{name} must be a positive integer")
                object.__setattr__(self, name, int(value))


@dataclass(frozen=True)
class ResourceUsage:
    wall_seconds: float = 0.0
    cpu_seconds: float = 0.0
    peak_memory_bytes: int = 0
    function_evaluations: int = 0

    def __post_init__(self) -> None:
        wall = float(self.wall_seconds)
        cpu = float(self.cpu_seconds)
        peak = int(self.peak_memory_bytes)
        evaluations = int(self.function_evaluations)
        if (
            not math.isfinite(wall)
            or not math.isfinite(cpu)
            or wall < 0
            or cpu < 0
            or peak < 0
            or evaluations < 0
        ):
            raise ValueError("resource usage values must be finite and non-negative")
        object.__setattr__(self, "wall_seconds", wall)
        object.__setattr__(self, "cpu_seconds", cpu)
        object.__setattr__(self, "peak_memory_bytes", peak)
        object.__setattr__(self, "function_evaluations", evaluations)

    def plus(self, other: "ResourceUsage") -> "ResourceUsage":
        if not isinstance(other, ResourceUsage):
            raise TypeError("resource usage can only be combined with ResourceUsage")
        return ResourceUsage(
            self.wall_seconds + other.wall_seconds,
            self.cpu_seconds + other.cpu_seconds,
            max(self.peak_memory_bytes, other.peak_memory_bytes),
            self.function_evaluations + other.function_evaluations,
        )

    def exceeded(self, budget: ResourceBudget) -> tuple[str, ...]:
        problems: list[str] = []
        if (
            budget.max_wall_seconds is not None
            and self.wall_seconds > budget.max_wall_seconds
        ):
            problems.append("wall_seconds")
        if (
            budget.max_cpu_seconds is not None
            and self.cpu_seconds > budget.max_cpu_seconds
        ):
            problems.append("cpu_seconds")
        if (
            budget.max_peak_memory_bytes is not None
            and self.peak_memory_bytes > budget.max_peak_memory_bytes
        ):
            problems.append("peak_memory_bytes")
        if (
            budget.max_function_evaluations is not None
            and self.function_evaluations > budget.max_function_evaluations
        ):
            problems.append("function_evaluations")
        return tuple(problems)
