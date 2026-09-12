"""Parts I and J: failure isolation, determinism, and memory behaviour.

The sweep in PART J's shape -- PASS PASS FAIL PASS FAIL -- run under both
declared policies, and under 1, 2 and 4 workers. Parallel execution is DEFERRED
this round, so "parallel" here means the thread option that ships; the point of
running it is that its failure semantics must be identical to sequential, not
that it is faster (it is not).
"""

from __future__ import annotations

import gc
import sys

import pytest

from engcore.execution.sweep import (
    CaseStatus,
    FailurePolicy,
    SharedContext,
    SweepCase,
    SweepDefinition,
    SweepError,
    run_sweep,
)


class PlantedFailure(RuntimeError):
    """Raised on purpose by the failing cases below."""


def pass_fail_pass(shared: SharedContext, case: SweepCase):
    """PASS PASS FAIL PASS FAIL, decided by the case's own declared input."""
    if case.inputs["outcome"] == "fail":
        raise PlantedFailure(f"planted failure in {case.case_id}")
    return {"case_id": case.case_id, "doubled": int(case.inputs["n"]) * 2}


PATTERN = ("pass", "pass", "fail", "pass", "fail")


def definition(policy=FailurePolicy.CONTINUE, sweep_id="j-isolation"):
    return SweepDefinition(
        sweep_id=sweep_id,
        operation=pass_fail_pass,
        cases=tuple(
            SweepCase(case_id=f"case-{i}", inputs={"outcome": o, "n": i})
            for i, o in enumerate(PATTERN)
        ),
        shared=SharedContext(),
        on_failure=policy,
    )


# =====================================================================
# J -- failure isolation
# =====================================================================

@pytest.mark.parametrize("workers", [1, 2, 4])
def test_failures_are_isolated_and_siblings_survive(workers):
    summary = run_sweep(definition(), workers=workers)

    assert summary.case_count == 5
    assert summary.succeeded == 3
    assert summary.failed == 2
    assert summary.not_run == 0

    statuses = [o.status for o in summary.outcomes]
    assert statuses == [
        CaseStatus.SUCCEEDED, CaseStatus.SUCCEEDED, CaseStatus.FAILED,
        CaseStatus.SUCCEEDED, CaseStatus.FAILED,
    ]


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_a_failed_case_keeps_its_identity(workers):
    """A failure that cannot say which case it was is a failure nobody can act on."""
    summary = run_sweep(definition(), workers=workers)
    failures = summary.failures()

    assert [f.case.case_id for f in failures] == ["case-2", "case-4"]
    for failure in failures:
        assert failure.case.identity, "a failed case lost its content digest"
        assert failure.error_type == "PlantedFailure"
        assert failure.case.case_id in failure.error_message
        assert failure.traceback_text, "a failure with no traceback cannot be diagnosed"


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_successful_siblings_are_uncontaminated(workers):
    """Each surviving case carries its OWN answer, not a neighbour's."""
    summary = run_sweep(definition(), workers=workers)
    values = {v["case_id"]: v["doubled"] for v in summary.values()}
    assert values == {"case-0": 0, "case-1": 2, "case-3": 6}


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_output_order_is_declaration_order_whatever_finished_first(workers):
    """The ordering the summary promises, held under concurrency."""
    summary = run_sweep(definition(), workers=workers)
    assert [o.case.case_id for o in summary.outcomes] == [
        "case-0", "case-1", "case-2", "case-3", "case-4"
    ]


def test_fail_fast_stops_and_marks_the_rest_not_run():
    """A different promise, and it must be kept exactly.

    FAIL_FAST does not turn later cases into failures -- it marks them NOT_RUN,
    which is a different claim: nobody asked them, so nothing is known about
    them.
    """
    summary = run_sweep(definition(policy=FailurePolicy.FAIL_FAST), workers=1)
    assert summary.succeeded == 2
    assert summary.failed == 1
    assert summary.not_run == 2
    assert [o.status for o in summary.outcomes][2:] == [
        CaseStatus.FAILED, CaseStatus.NOT_RUN, CaseStatus.NOT_RUN
    ]


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_the_summary_record_names_each_failed_case_identity(workers):
    """THE GAP PAR-2 FOUND.

    `test_the_aggregate_record_is_deterministic` compares two runs of the same
    sweep, so a field dropped from BOTH still compares equal -- the mutation
    that removed `case_identity` from the serialized summary survived it
    untouched. Determinism is not the same claim as completeness, and this
    asserts the second one: the record a reader actually gets must name which
    case each failure was, by content and not only by label.
    """
    summary = run_sweep(definition(), workers=workers)
    payload = summary.to_dict()

    assert len(payload["failures"]) == 2
    by_id = {f["case_id"]: f for f in payload["failures"]}
    assert set(by_id) == {"case-2", "case-4"}

    for case_id, entry in by_id.items():
        assert "case_identity" in entry, (
            "the serialized summary dropped case_identity; a failure known "
            "only by its label cannot be matched back to what was run"
        )
        source = next(o for o in summary.outcomes if o.case.case_id == case_id)
        assert entry["case_identity"] == source.case.identity
        assert len(entry["case_identity"]) == 64  # a sha256, not a label
        assert entry["error_type"] == "PlantedFailure"

    # and two different cases must not share an identity
    assert by_id["case-2"]["case_identity"] != by_id["case-4"]["case_identity"]


def test_the_two_policies_disagree_only_about_what_follows_a_failure():
    a = run_sweep(definition(FailurePolicy.CONTINUE), workers=1)
    b = run_sweep(definition(FailurePolicy.FAIL_FAST), workers=1)
    assert a.outcomes[:3] == b.outcomes[:3] or (
        [o.status for o in a.outcomes[:3]] == [o.status for o in b.outcomes[:3]]
    )
    assert a.failed == 2 and b.failed == 1


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_the_aggregate_record_is_deterministic(workers):
    """Same sweep, same record -- ordering, identities and counts."""
    first = run_sweep(definition(), workers=workers).to_dict()
    second = run_sweep(definition(), workers=workers).to_dict()
    for payload in (first, second):
        payload.pop("seconds")
        payload.pop("cases_per_second")
    assert first == second


def test_sequential_and_threaded_failure_semantics_are_identical():
    """The claim that matters if a parallel backend is ever shipped."""
    records = []
    for workers in (1, 2, 4):
        payload = run_sweep(definition(), workers=workers).to_dict()
        payload.pop("seconds")
        payload.pop("cases_per_second")
        payload.pop("workers")
        records.append(payload)
    assert records[0] == records[1] == records[2]


def test_no_stale_state_survives_between_sweeps():
    """Two runs of the same definition cannot influence each other."""
    first = run_sweep(definition(), workers=1)
    second = run_sweep(definition(), workers=1)
    assert first.values() == second.values()
    assert [f.case.identity for f in first.failures()] == [
        f.case.identity for f in second.failures()
    ]


def test_a_sweep_over_nothing_is_refused_rather_than_reporting_success():
    with pytest.raises(SweepError, match="declares no cases"):
        SweepDefinition(sweep_id="empty", operation=pass_fail_pass, cases=())


def test_zero_workers_is_refused():
    with pytest.raises(SweepError, match="at least one worker"):
        run_sweep(definition(), workers=0)


# =====================================================================
# I -- memory behaviour
# =====================================================================

def counting_operation(shared: SharedContext, case: SweepCase):
    return {"n": int(case.inputs["n"])}


def sized(count: int) -> SweepDefinition:
    return SweepDefinition(
        sweep_id=f"mem-{count}",
        operation=counting_operation,
        cases=tuple(
            SweepCase(case_id=f"c{i}", inputs={"n": i}) for i in range(count)
        ),
    )


@pytest.mark.expensive
def test_retained_memory_grows_linearly_with_case_count():
    """Linear, not quadratic: the failure this catches is accidental retention.

    Measured by the summed size of what the summary RETAINS rather than by a
    process RSS reading, which on Windows is dominated by allocator behaviour
    and would make this a test of the allocator.
    """
    sizes = {}
    for count in (1_000, 10_000):
        gc.collect()
        summary = run_sweep(sized(count), workers=1)
        retained = sum(
            sys.getsizeof(o.value) + sys.getsizeof(o.case.case_id)
            for o in summary.outcomes
        )
        sizes[count] = retained / count
        del summary
        gc.collect()

    # Per-case retention must not grow with the number of cases.
    assert sizes[10_000] <= sizes[1_000] * 1.10, sizes


@pytest.mark.expensive
def test_a_sweep_retains_nothing_globally_after_it_returns():
    """Per-run retained global state is the leak this looks for."""
    from engcore.scientific.units.quantity import unit_cache_stats

    gc.collect()
    before = unit_cache_stats()["currsize"]
    for _ in range(5):
        run_sweep(sized(2_000), workers=1)
    gc.collect()
    after = unit_cache_stats()["currsize"]

    # The unit memo is bounded and keyed on unit strings, of which this sweep
    # introduces none; five runs must not grow it.
    assert after == before, (before, after)


@pytest.mark.expensive
def test_failed_cases_do_not_retain_their_exception_objects():
    """A traceback is kept as TEXT, so a failure cannot pin a live frame.

    An exception object holds its traceback, which holds every frame, which
    holds every local -- so retaining one per failed case in a large sweep
    would retain the whole call stack of each failure.
    """
    summary = run_sweep(definition(), workers=1)
    for failure in summary.failures():
        assert isinstance(failure.traceback_text, str)
        assert not hasattr(failure, "exception")
        for value in vars(failure).values():
            assert not isinstance(value, BaseException), (
                "a sweep outcome retains a live exception object"
            )
