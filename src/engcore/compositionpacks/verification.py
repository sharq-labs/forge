"""Independent system-verification authority for Composition Packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domainpacks.manifest import ArtifactRef
from ..scientific.verification.dependencies import RouteDependencyManifest
from ..scientific.verification.planning import (
    VerificationCandidate,
    VerificationPolicy,
    plan_verification,
)
from ..scientific.verification.route import VerificationRoute
from ..scientific.verification.run_record import VerificationRunRecord
from .errors import InvalidCompositionPackProvider


@dataclass(frozen=True)
class ProvidedCompositionVerification:
    blueprint_id: str
    ref: ArtifactRef
    quantity: str
    primary_route: VerificationRoute
    primary_dependencies: RouteDependencyManifest
    candidates: tuple[VerificationCandidate, ...]
    policy: VerificationPolicy
    implementation: Any

    def __post_init__(self) -> None:
        blueprint = str(self.blueprint_id).strip()
        quantity = str(self.quantity).strip()
        if not blueprint or not quantity:
            raise InvalidCompositionPackProvider(
                "composition verification requires blueprint_id and quantity"
            )
        object.__setattr__(self, "blueprint_id", blueprint)
        object.__setattr__(self, "quantity", quantity)
        if not isinstance(self.ref, ArtifactRef):
            raise InvalidCompositionPackProvider(
                "composition verification ref must be ArtifactRef"
            )
        if not isinstance(self.primary_route, VerificationRoute):
            raise InvalidCompositionPackProvider(
                "composition verification requires primary VerificationRoute"
            )
        if not isinstance(
            self.primary_dependencies, RouteDependencyManifest
        ):
            raise InvalidCompositionPackProvider(
                "composition verification requires primary dependency manifest"
            )
        candidates = tuple(self.candidates)
        if not candidates or any(
            not isinstance(item, VerificationCandidate)
            for item in candidates
        ):
            raise InvalidCompositionPackProvider(
                "composition verification requires VerificationCandidate records"
            )
        object.__setattr__(self, "candidates", candidates)
        if not isinstance(self.policy, VerificationPolicy):
            raise InvalidCompositionPackProvider(
                "composition verification requires VerificationPolicy"
            )
        plan = plan_verification(
            self.primary_route,
            self.primary_dependencies,
            candidates,
            self.policy,
        )
        if not plan.complete:
            raise InvalidCompositionPackProvider(
                "composition verification declaration has no complete "
                f"independent plan; rejected={plan.rejected}"
            )
        if not callable(self.implementation):
            raise InvalidCompositionPackProvider(
                "composition verification implementation must be callable"
            )

    @property
    def key(self) -> tuple[str, str]:
        return self.blueprint_id, self.ref.artifact_id

    def plan(self):
        return plan_verification(
            self.primary_route,
            self.primary_dependencies,
            self.candidates,
            self.policy,
        )

    def execute(self, record) -> VerificationRunRecord:
        made = self.implementation(record, self.plan())
        if not isinstance(made, VerificationRunRecord):
            raise InvalidCompositionPackProvider(
                f"verification {self.ref.artifact_id}@{self.ref.version} "
                f"returned {type(made).__name__}, expected VerificationRunRecord"
            )
        return made


__all__ = ["ProvidedCompositionVerification"]
