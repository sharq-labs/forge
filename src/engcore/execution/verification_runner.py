"""Execution-only backend runner for scientific verification plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from engcore.scientific.verification.observations import VerificationObservation
from engcore.scientific.verification.planning import VerificationPlan


class VerificationBackend(Protocol):
    route_id:str
    def run(self)->VerificationObservation: ...


@dataclass(frozen=True)
class VerificationBackendRun:
    observations:tuple[VerificationObservation,...]
    problems:tuple[str,...]


def execute_verification_plan(plan:VerificationPlan,backends:dict[str,VerificationBackend])->VerificationBackendRun:
    observations=[];problems=[]
    for item in plan.selected:
        route_id=item.candidate.route.route_id
        backend=backends.get(route_id)
        if backend is None:
            problems.append(f"{route_id}:backend_missing");continue
        if str(getattr(backend,"route_id",""))!=route_id:
            problems.append(f"{route_id}:backend_route_identity_mismatch");continue
        try:
            observation=backend.run()
        except Exception as exc:
            problems.append(f"{route_id}:backend_exception:{type(exc).__name__}");continue
        if not isinstance(observation,VerificationObservation):
            problems.append(f"{route_id}:backend_returned_untyped_observation");continue
        if observation.route_id!=route_id:
            problems.append(f"{route_id}:observation_route_identity_mismatch");continue
        observations.append(observation)
    return VerificationBackendRun(tuple(observations),tuple(problems))
