"""Running one scientific operation over many cases, without letting them mix.

A parameter sweep, a calibration loop, a Monte Carlo sample and an optimiser's
objective evaluations are the same shape: one operation, many independent
inputs, results that must stay attached to the input that produced them. This
is the smallest abstraction that runs them and keeps the guarantees the earlier
sprints established.

**Why this is not called a campaign.** ``engcore.sria.campaign`` already is one,
and it is a different thing: an autonomous decision loop that chooses *which*
experiment to run next from a belief snapshot. A sweep does not choose
anything — it is handed the cases. Two things called Campaign in one codebase
would be exactly the ambiguity this repository refuses elsewhere, so this one
is named for what it does.

What it guarantees
------------------
* **Case isolation.** A case's inputs reach the operation and nothing else
  does. The shared context holds declarations and is refused anything mutable.
* **Deterministic identity.** A case's identity is a digest of its own
  content, so the same case is the same case in any run, in any order, in any
  process.
* **Deterministic ordering.** Outcomes come back in declaration order whatever
  order they were executed in, so a result cannot drift onto another case's
  inputs.
* **Failure isolation.** One case raising does not stop or contaminate the
  others; the failure is recorded against the case that produced it.
* **No shared mutable execution state.** Sprint 2 established that
  problem-specific execution state must never leak between independent solves.
  A sweep would be the natural place to break that by hoisting a solver out of
  the loop, so :class:`SharedContext` refuses to hold one.

What it deliberately is not
---------------------------
A workflow engine. There are no dependencies between cases, no retries, no
scheduling, no persistence and no distributed anything. Cases are independent
by construction; that is the only reason any of the above is cheap to promise.
"""

from __future__ import annotations

import hashlib
import json
import time
import traceback
from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..scientific.errors import ScientificCoreError

SWEEP_SCHEMA = "sweep_summary/1"

#: Types a shared context may hold directly. Everything else must be a frozen
#: dataclass or a container of admitted values -- see `_require_immutable`.
_ATOMS = (str, int, float, bool, bytes, type(None), complex)


class SweepError(ScientificCoreError):
    """A sweep could not be declared or run as specified."""


class FailurePolicy(str, Enum):
    """What a failing case does to the rest of the sweep."""

    #: Record the failure against its case and keep going. The default,
    #: because the point of a sweep is usually the cases that did work.
    CONTINUE = "continue_on_case_failure"
    #: Stop at the first failure. The remaining cases are reported as
    #: NOT_RUN rather than silently missing.
    FAIL_FAST = "fail_fast"


class CaseStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_RUN = "not_run"


# ---------------------------------------------------------------------------
def _canonical(value: Any) -> Any:
    """A JSON-comparable rendering of a case input, for identity only."""
    if isinstance(value, _ATOMS):
        return repr(value) if isinstance(value, (float, complex, bytes)) else value
    if hasattr(value, "to_dict"):
        try:
            return _canonical(value.to_dict())
        except Exception:  # pragma: no cover - a to_dict that needs arguments
            pass
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple, frozenset, set)):
        items = [_canonical(v) for v in value]
        return sorted(items, key=repr) if isinstance(value, (frozenset, set)) else items
    return f"{type(value).__module__}.{type(value).__qualname__}:{value!r}"


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=repr).encode(
            "utf-8"
        )
    ).hexdigest()


def _looks_like_a_solver(value: Any) -> bool:
    """Whether an object is a solver, by the protocol's own verbs.

    Structural rather than by type, because the check has to catch a solver
    from any domain and any future one. The verbs are the five stages of the
    solver protocol; an object carrying them is execution state whatever it is
    called.
    """
    return all(hasattr(value, verb) for verb in ("prepare", "solve"))


def _require_immutable(name: str, value: Any, *, path: str = "") -> None:
    """Refuse anything a sweep must not carry across its cases.

    The rule this enforces is Sprint 5's, stated one layer up: immutable
    scientific declarations may be reused; request-specific execution state may
    not. A mutable container shared across cases is the mechanism by which one
    case's state reaches another, and a solver is that mechanism with a name.
    """
    where = f"{name}{path}"
    if _looks_like_a_solver(value):
        raise SweepError(
            f"shared context entry {where!r} is a solver "
            f"({type(value).__name__}): it carries prepare/solve, which is "
            f"request-specific execution state. Sprint 2 established that such "
            f"state must never leak between independent solves, and hoisting a "
            f"solver out of a loop is exactly how it would. Build one per case, "
            f"or share the declaration it is built from"
        )
    if isinstance(value, _ATOMS):
        return
    if isinstance(value, (tuple, frozenset)):
        for index, item in enumerate(value):
            _require_immutable(name, item, path=f"{path}[{index}]")
        return
    if isinstance(value, (list, set, bytearray)):
        raise SweepError(
            f"shared context entry {where!r} is a {type(value).__name__}, which "
            f"can be changed by any case that reaches it. Use a tuple, a "
            f"frozenset, or a frozen record"
        )
    if isinstance(value, Mapping):
        # The core's own frozen mapping is admitted; a plain dict is not.
        if type(value).__name__ not in ("FrozenMapping", "mappingproxy"):
            raise SweepError(
                f"shared context entry {where!r} is a {type(value).__name__}, "
                f"which can be changed by any case that reaches it. Freeze it "
                f"first"
            )
        for key, item in value.items():
            _require_immutable(name, item, path=f"{path}[{key!r}]")
        return
    parameters = getattr(type(value), "__dataclass_params__", None)
    if parameters is not None:
        if not parameters.frozen:
            raise SweepError(
                f"shared context entry {where!r} is a mutable dataclass "
                f"({type(value).__name__})"
            )
        return
    if callable(value):
        return
    # Anything else is accepted only if it cannot be written to.
    if hasattr(value, "__dict__") and not hasattr(value, "__slots__"):
        raise SweepError(
            f"shared context entry {where!r} is a {type(value).__name__} with a "
            f"writable instance dictionary, so a case could change what the "
            f"next case sees. Share a frozen record instead"
        )


# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SharedContext:
    """Declarations every case may read, and nothing a case may write.

    Every entry is checked on construction, and what is admitted is recorded in
    :attr:`entries` so a summary can say exactly what was reused rather than
    leaving a reader to guess.
    """

    entries: Mapping[str, Any] = dataclass_field(default_factory=dict)

    def __post_init__(self) -> None:
        from ..scientific.results.immutable import freeze

        admitted = dict(self.entries)
        for name, value in admitted.items():
            _require_immutable(name, value)
        object.__setattr__(self, "entries", freeze(admitted))

    def __getitem__(self, name: str) -> Any:
        try:
            return self.entries[name]
        except KeyError:
            raise SweepError(
                f"the shared context holds no {name!r}; it holds "
                f"{sorted(self.entries)}"
            ) from None

    def get(self, name: str, default: Any = None) -> Any:
        return self.entries.get(name, default)

    @property
    def identity(self) -> str:
        """A digest over what is shared, so two sweeps can be compared."""
        return _digest(
            {name: _canonical(value) for name, value in sorted(self.entries.items())}
        )

    def describe(self) -> dict[str, str]:
        """What is being reused, by name and type. Recorded in every summary."""
        return {
            name: f"{type(value).__module__}.{type(value).__qualname__}"
            for name, value in sorted(self.entries.items())
        }


@dataclass(frozen=True)
class SweepCase:
    """One case's own inputs, and nothing shared."""

    case_id: str
    inputs: Mapping[str, Any] = dataclass_field(default_factory=dict)

    def __post_init__(self) -> None:
        from ..scientific.results.immutable import freeze

        case_id = str(self.case_id).strip()
        if not case_id:
            raise SweepError("a sweep case requires a non-empty case_id")
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "inputs", freeze(dict(self.inputs)))

    @property
    def identity(self) -> str:
        """A digest of this case's own content.

        Deterministic across runs and processes, and independent of position:
        a case's identity does not change because another case was inserted
        before it.
        """
        return _digest({"case_id": self.case_id, "inputs": _canonical(dict(self.inputs))})


@dataclass(frozen=True)
class SweepOutcome:
    """What one case produced, or why it produced nothing."""

    case: SweepCase
    status: CaseStatus
    value: Any = None
    error_type: str = ""
    error_message: str = ""
    traceback_text: str = ""
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status is CaseStatus.SUCCEEDED


@dataclass(frozen=True)
class SweepDefinition:
    """One operation, the declarations it shares, and the cases to run it on."""

    sweep_id: str
    operation: Callable[[SharedContext, SweepCase], Any]
    cases: tuple[SweepCase, ...]
    shared: SharedContext = dataclass_field(default_factory=SharedContext)
    on_failure: FailurePolicy = FailurePolicy.CONTINUE
    description: str = ""

    def __post_init__(self) -> None:
        sweep_id = str(self.sweep_id).strip()
        if not sweep_id:
            raise SweepError("a sweep requires a non-empty sweep_id")
        object.__setattr__(self, "sweep_id", sweep_id)
        if not callable(self.operation):
            raise SweepError("a sweep's operation must be callable")
        cases = tuple(self.cases)
        if not cases:
            raise SweepError(
                f"sweep {sweep_id!r} declares no cases; a sweep over nothing "
                f"reports success over nothing"
            )
        for case in cases:
            if not isinstance(case, SweepCase):
                raise SweepError(
                    f"sweep {sweep_id!r} was given a {type(case).__name__} where "
                    f"a SweepCase was required"
                )
        object.__setattr__(self, "cases", cases)
        object.__setattr__(self, "on_failure", FailurePolicy(self.on_failure))
        if not isinstance(self.shared, SharedContext):
            raise SweepError("a sweep's shared context must be a SharedContext")

    @property
    def identity(self) -> str:
        """Identity of the whole declaration: shared context and every case.

        **Position-sensitive**, unlike a case's own identity: two sweeps over
        the same cases in a different order are the same science and are not
        the same run, and a summary that could not tell them apart would be
        unable to say which result belongs where.
        """
        return _digest(
            {
                "sweep_id": self.sweep_id,
                "shared": self.shared.identity,
                "cases": [case.identity for case in self.cases],
            }
        )

    @property
    def duplicate_case_ids(self) -> tuple[str, ...]:
        """Case ids used more than once, which is allowed and worth reporting."""
        seen: dict[str, int] = {}
        for case in self.cases:
            seen[case.case_id] = seen.get(case.case_id, 0) + 1
        return tuple(sorted(name for name, count in seen.items() if count > 1))


@dataclass(frozen=True)
class SweepSummary:
    """What a sweep did, small enough to keep however many cases it ran.

    Deliberately **not** one nested scientific record. Individual results stay
    individual records and are reachable through their outcomes; this is the
    run's own bookkeeping.
    """

    sweep_id: str
    identity: str
    shared_identity: str
    shared_entries: Mapping[str, str]
    outcomes: tuple[SweepOutcome, ...]
    seconds: float
    policy: FailurePolicy
    workers: int = 1

    @property
    def case_count(self) -> int:
        return len(self.outcomes)

    @property
    def succeeded(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status is CaseStatus.SUCCEEDED)

    @property
    def failed(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status is CaseStatus.FAILED)

    @property
    def not_run(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status is CaseStatus.NOT_RUN)

    @property
    def cases_per_second(self) -> float:
        return self.case_count / self.seconds if self.seconds > 0 else float("inf")

    def failures(self) -> tuple[SweepOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status is CaseStatus.FAILED)

    def values(self) -> tuple[Any, ...]:
        """Successful results, in declaration order."""
        return tuple(o.value for o in self.outcomes if o.status is CaseStatus.SUCCEEDED)

    def to_dict(self) -> dict[str, Any]:
        """The summary without the results: counts, identities and failures."""
        return {
            "schema": SWEEP_SCHEMA,
            "sweep_id": self.sweep_id,
            "identity": self.identity,
            "shared_identity": self.shared_identity,
            "shared_entries": dict(self.shared_entries),
            "policy": self.policy.value,
            "workers": self.workers,
            "case_count": self.case_count,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "not_run": self.not_run,
            "seconds": self.seconds,
            "cases_per_second": self.cases_per_second,
            "failures": [
                {
                    "case_id": o.case.case_id,
                    "case_identity": o.case.identity,
                    "error_type": o.error_type,
                    "error_message": o.error_message,
                }
                for o in self.failures()
            ],
        }


# ---------------------------------------------------------------------------
def _run_case(definition: SweepDefinition, case: SweepCase) -> SweepOutcome:
    started = time.perf_counter()
    try:
        value = definition.operation(definition.shared, case)
    except BaseException as exc:  # noqa: BLE001 - a case's failure is data
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return SweepOutcome(
            case=case,
            status=CaseStatus.FAILED,
            error_type=type(exc).__name__,
            error_message=str(exc),
            traceback_text="".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
            seconds=time.perf_counter() - started,
        )
    return SweepOutcome(
        case=case,
        status=CaseStatus.SUCCEEDED,
        value=value,
        seconds=time.perf_counter() - started,
    )


def run_sweep(definition: SweepDefinition, *, workers: int = 1) -> SweepSummary:
    """Run every case and report what each one did.

    Sequential by default. ``workers`` above one uses threads, which help only
    where the operation releases the GIL; the sprint's own measurements are in
    ``benchmarks/performance_campaign``. Outcomes are returned in **declaration
    order** whatever order they completed in.
    """
    if workers < 1:
        raise SweepError(f"a sweep needs at least one worker, got {workers}")

    started = time.perf_counter()
    outcomes: list[SweepOutcome] = []

    if workers == 1:
        for position, case in enumerate(definition.cases):
            outcome = _run_case(definition, case)
            outcomes.append(outcome)
            if (
                outcome.status is CaseStatus.FAILED
                and definition.on_failure is FailurePolicy.FAIL_FAST
            ):
                outcomes.extend(
                    SweepOutcome(case=remaining, status=CaseStatus.NOT_RUN)
                    for remaining in definition.cases[position + 1 :]
                )
                break
    else:
        from concurrent.futures import ThreadPoolExecutor

        # Submitted in order and collected by position, so the returned order is
        # the declared order however the pool completed them. FAIL_FAST is not
        # offered here: with work already in flight "stop at the first failure"
        # would mean a different set of cases each run.
        if definition.on_failure is FailurePolicy.FAIL_FAST:
            raise SweepError(
                "FAIL_FAST is not available with more than one worker: cases are "
                "already in flight when the first failure lands, so which ones "
                "ran would differ between runs of the same sweep"
            )
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_run_case, definition, case) for case in definition.cases
            ]
            outcomes = [future.result() for future in futures]

    return SweepSummary(
        sweep_id=definition.sweep_id,
        identity=definition.identity,
        shared_identity=definition.shared.identity,
        shared_entries=definition.shared.describe(),
        outcomes=tuple(outcomes),
        seconds=time.perf_counter() - started,
        policy=definition.on_failure,
        workers=workers,
    )


def rerun_failed(
    definition: SweepDefinition, summary: SweepSummary, *, workers: int = 1
) -> SweepSummary:
    """Run only the cases that failed, as a sweep in its own right.

    The re-run's cases are the *same* case records, so their identities are
    unchanged — which is what makes it possible to say a case that failed and
    then succeeded is one case with two outcomes rather than two cases.
    """
    failed = tuple(outcome.case for outcome in summary.failures())
    if not failed:
        raise SweepError(
            f"sweep {summary.sweep_id!r} recorded no failures to re-run"
        )
    retry = SweepDefinition(
        sweep_id=f"{definition.sweep_id}:retry",
        operation=definition.operation,
        cases=failed,
        shared=definition.shared,
        on_failure=definition.on_failure,
        description=f"re-run of {summary.failed} failed case(s)",
    )
    return run_sweep(retry, workers=workers)


def cases_from(
    prefix: str, varying: Iterable[Mapping[str, Any]]
) -> tuple[SweepCase, ...]:
    """Build numbered cases from a sequence of input mappings."""
    return tuple(
        SweepCase(case_id=f"{prefix}-{position:06d}", inputs=dict(inputs))
        for position, inputs in enumerate(varying)
    )
