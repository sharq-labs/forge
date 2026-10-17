"""Opt-in concurrent advance of independent participants inside a Jacobi coupling iteration.

In Jacobi semantics every participant of an iteration reads the SAME frozen
coupling values, so their advances are independent as far as the coupling is
concerned.  Whether two participant implementations may run at the same time
is a property of the implementations (shared solver handles, shared files, a
shared bulk store, non-reentrant libraries), which no record states -- so it is
DECLARED here, per participant, with a basis, and never inferred.

Only declared participants advance concurrently; an undeclared participant
advances alone, before them.  Results are applied in the plan's participant
order, so the coupling iterates, transfers and records are the ones sequential
Jacobi execution produces.  A failure is reported as the FIRST failing
participant in plan order, never in completion order.

This is an execution choice, not science: it changes wall time only.  It is
recorded in a run's outputs because execution provenance should say how a run
was executed.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence, TypeVar

from ...scientific.errors import InvalidScientificProblem

T = TypeVar("T")


@dataclass(frozen=True)
class ConcurrentAdvancePolicy:
    """Participants declared safe to advance at the same time, and why."""

    participants: tuple[str, ...]
    max_workers: int
    basis: str

    def __post_init__(self) -> None:
        ids = tuple(sorted(str(item).strip() for item in self.participants))
        if len(ids) < 2 or any(not item for item in ids) or len(set(ids)) != len(ids):
            raise InvalidScientificProblem(
                "concurrent advance names at least two distinct participants"
            )
        if (
            isinstance(self.max_workers, bool)
            or not isinstance(self.max_workers, int)
            or not 2 <= self.max_workers <= 64
        ):
            raise InvalidScientificProblem("max_workers must be an int in [2, 64]")
        if not str(self.basis).strip():
            raise InvalidScientificProblem(
                "concurrent advance states the basis of its thread-safety declaration"
            )
        object.__setattr__(self, "participants", ids)
        object.__setattr__(self, "basis", str(self.basis).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "concurrent_jacobi_advance",
            "participants": list(self.participants),
            "max_workers": self.max_workers,
            "basis": self.basis,
            "notice": "execution choice only; results are applied in plan order",
        }


def advance_in_plan_order(
    order: Sequence[str],
    declared: frozenset[str],
    max_workers: int,
    advance: Callable[[str], T],
) -> dict[str, T]:
    """Advance every participant of ``order``; declared ones concurrently.

    Undeclared participants run first, one at a time, in plan order (they are
    never run alongside anything).  Declared participants then run in a thread
    pool.  Every submitted advance is allowed to finish before a failure is
    raised, and the failure raised is the first in plan order.
    """
    concurrent = [pid for pid in order if pid in declared]
    if len(concurrent) < 2:
        return {pid: advance(pid) for pid in order}
    results: dict[str, T] = {}
    for pid in order:
        if pid not in declared:
            results[pid] = advance(pid)
    with ThreadPoolExecutor(
        max_workers=min(max_workers, len(concurrent)),
        thread_name_prefix="forge-jacobi",
    ) as pool:
        futures = {pid: pool.submit(advance, pid) for pid in concurrent}
    # the context manager has joined every worker: nothing is still running
    for pid in concurrent:
        failure = futures[pid].exception()
        if failure is not None:
            raise failure
    for pid in concurrent:
        results[pid] = futures[pid].result()
    return {pid: results[pid] for pid in order}


def validate_policy(
    policy: ConcurrentAdvancePolicy | None,
    *,
    participant_ids: Mapping[str, Any],
    jacobi: bool,
) -> None:
    if policy is None:
        return
    if not isinstance(policy, ConcurrentAdvancePolicy):
        raise InvalidScientificProblem("concurrency must be a ConcurrentAdvancePolicy")
    if not jacobi:
        raise InvalidScientificProblem(
            "concurrent advance applies to Jacobi iteration semantics only: a serial "
            "(Gauss-Seidel) participant reads the outputs of the one before it"
        )
    unknown = sorted(set(policy.participants) - set(participant_ids))
    if unknown:
        raise InvalidScientificProblem(
            f"concurrent advance names participants outside the graph: {unknown}"
        )
