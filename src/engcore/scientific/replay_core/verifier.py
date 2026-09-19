from __future__ import annotations

from dataclasses import dataclass

from .bundle import ReplayBundle


@dataclass(frozen=True)
class ReplayVerification:
    verified: bool
    problems: tuple[str, ...]


def verify_replay_bundle(expected: ReplayBundle, actual: ReplayBundle) -> ReplayVerification:
    problems=[]
    if expected.run_id != actual.run_id:
        problems.append("run_id differs")
    if expected.environment != actual.environment:
        problems.append("runtime environment differs")
    if expected.random_seed != actual.random_seed:
        problems.append("random seed differs")
    if expected.artifacts != actual.artifacts:
        problems.append("artifact identity set differs")
    return ReplayVerification(not problems, tuple(problems))
