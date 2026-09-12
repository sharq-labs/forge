"""Many cases, one operation, and nothing crossing between them.

Sprint 7, Phases 7, 8 and 18. A sweep exists to make repeated evaluation cheap,
and the whole risk of making it cheap is that the savings come from sharing
something that should not have been shared. So most of this file is about what
does *not* cross: a failure, a result, a mutable object, a solver.
"""

from __future__ import annotations

import threading

import pytest

from engcore.execution import (
    CaseStatus,
    FailurePolicy,
    SharedContext,
    SweepCase,
    SweepDefinition,
    SweepError,
    cases_from,
    rerun_failed,
    run_sweep,
)
from engcore.scientific.units.quantity import Quantity


def doubling(shared, case):
    return case.inputs["x"] * 2


def numbers(count: int, prefix: str = "n"):
    return cases_from(prefix, [{"x": i} for i in range(count)])


def sweep(operation=doubling, count=5, **changes):
    return SweepDefinition(
        sweep_id=changes.pop("sweep_id", "s"),
        operation=operation,
        cases=changes.pop("cases", numbers(count)),
        **changes,
    )


# ---- the ordinary path ----------------------------------------------------------
def test_every_case_runs_and_reports_its_own_value():
    summary = run_sweep(sweep(count=6))
    assert summary.case_count == 6
    assert summary.succeeded == 6 and summary.failed == 0
    assert summary.values() == (0, 2, 4, 6, 8, 10)


def test_outcomes_come_back_in_declaration_order():
    declared = numbers(20)
    summary = run_sweep(sweep(cases=declared))
    assert [o.case.case_id for o in summary.outcomes] == [
        case.case_id for case in declared
    ]
    for outcome in summary.outcomes:
        assert outcome.value == outcome.case.inputs["x"] * 2, (
            "a result drifted onto another case's inputs"
        )


def test_a_sweep_over_no_cases_is_refused():
    with pytest.raises(SweepError, match="reports success over nothing"):
        SweepDefinition(sweep_id="empty", operation=doubling, cases=())


# ---- identity ---------------------------------------------------------------------
def test_a_case_identity_is_its_own_content():
    one = SweepCase("a", {"x": 1})
    same = SweepCase("a", {"x": 1})
    other = SweepCase("a", {"x": 2})
    renamed = SweepCase("b", {"x": 1})
    assert one.identity == same.identity
    assert one.identity != other.identity
    assert one.identity != renamed.identity
    assert len(one.identity) == 64


def test_a_case_identity_does_not_depend_on_position():
    """Inserting a case before another must not change what the other is."""
    first = numbers(3)
    shifted = (SweepCase("extra", {"x": 99}),) + first
    assert [c.identity for c in first] == [c.identity for c in shifted[1:]]


def test_duplicate_case_ids_keep_distinct_records_and_are_reported():
    cases = (SweepCase("dup", {"x": 1}), SweepCase("dup", {"x": 2}))
    definition = SweepDefinition(sweep_id="d", operation=doubling, cases=cases)
    assert definition.duplicate_case_ids == ("dup",)
    assert cases[0].identity != cases[1].identity, "same name, different inputs"

    summary = run_sweep(definition)
    assert summary.values() == (2, 4), "the two cases were collapsed into one"


def test_two_identical_cases_are_two_cases():
    """No implicit deduplication: asking twice means running twice."""
    cases = (SweepCase("same", {"x": 3}), SweepCase("same", {"x": 3}))
    summary = run_sweep(SweepDefinition(sweep_id="d", operation=doubling, cases=cases))
    assert summary.case_count == 2
    assert summary.outcomes[0].case.identity == summary.outcomes[1].case.identity


def test_a_sweep_identity_covers_its_cases_and_their_order():
    base = sweep(count=4)
    reordered = SweepDefinition(
        sweep_id="s", operation=doubling, cases=tuple(reversed(base.cases))
    )
    assert base.identity != reordered.identity
    assert base.identity == sweep(count=4).identity


# ---- failure isolation --------------------------------------------------------------
def exploding(shared, case):
    if case.inputs["x"] == 2:
        raise ValueError("case two is broken")
    return case.inputs["x"] * 2


def test_one_failing_case_does_not_stop_or_contaminate_the_others():
    summary = run_sweep(sweep(operation=exploding, count=5))
    assert summary.succeeded == 4 and summary.failed == 1
    assert summary.values() == (0, 2, 6, 8)

    (failure,) = summary.failures()
    assert failure.case.inputs["x"] == 2
    assert failure.error_type == "ValueError"
    assert "case two is broken" in failure.error_message
    assert "exploding" in failure.traceback_text

    for outcome in summary.outcomes:
        if outcome.ok:
            assert outcome.error_type == "" and outcome.error_message == ""


def test_fail_fast_stops_and_says_which_cases_did_not_run():
    summary = run_sweep(
        sweep(operation=exploding, count=5, on_failure=FailurePolicy.FAIL_FAST)
    )
    assert summary.succeeded == 2 and summary.failed == 1
    assert summary.not_run == 2
    assert [o.status for o in summary.outcomes] == [
        CaseStatus.SUCCEEDED, CaseStatus.SUCCEEDED, CaseStatus.FAILED,
        CaseStatus.NOT_RUN, CaseStatus.NOT_RUN,
    ]
    assert summary.case_count == 5, "a stopped sweep still accounts for every case"


def test_a_keyboard_interrupt_is_not_swallowed_as_a_case_failure():
    def interrupting(shared, case):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_sweep(sweep(operation=interrupting, count=2))


# ---- Phase 18: re-running failures ---------------------------------------------------
def test_rerunning_failed_cases_does_not_alter_the_successful_ones():
    attempts: dict[str, int] = {}

    def flaky(shared, case):
        attempts[case.case_id] = attempts.get(case.case_id, 0) + 1
        if case.inputs["x"] == 2 and attempts[case.case_id] == 1:
            raise RuntimeError("transient")
        return case.inputs["x"] * 2

    definition = sweep(operation=flaky, count=4)
    first = run_sweep(definition)
    assert first.failed == 1

    successful_before = {o.case.identity: o.value for o in first.outcomes if o.ok}
    retry = rerun_failed(definition, first)

    assert retry.case_count == 1 and retry.succeeded == 1
    assert retry.outcomes[0].case.identity == first.failures()[0].case.identity, (
        "a re-run case must be the same case, not a new one"
    )
    # The successful cases were not touched at all.
    assert {o.case.identity: o.value for o in first.outcomes if o.ok} == successful_before
    assert attempts["n-000000"] == 1, "a successful case was re-executed"


def test_rerunning_nothing_is_refused():
    summary = run_sweep(sweep(count=3))
    with pytest.raises(SweepError, match="no failures to re-run"):
        rerun_failed(sweep(count=3), summary)


# ---- Phase 8: what may be shared ------------------------------------------------------
class FakeSolver:
    def prepare(self, problem):  # pragma: no cover - never called
        return problem

    def solve(self, prepared):  # pragma: no cover - never called
        return prepared


def test_a_solver_may_not_be_shared():
    """Sprint 2's guarantee, defended where a sweep would break it."""
    with pytest.raises(SweepError, match="carries prepare/solve"):
        SharedContext({"solver": FakeSolver()})


@pytest.mark.parametrize(
    "value, expected",
    [
        ({"a": 1}, "can be changed by any case"),
        ([1, 2, 3], "can be changed by any case"),
        ({1, 2}, "can be changed by any case"),
        (bytearray(b"ab"), "can be changed by any case"),
    ],
)
def test_a_mutable_container_may_not_be_shared(value, expected):
    with pytest.raises(SweepError, match=expected):
        SharedContext({"thing": value})


def test_a_mutable_object_may_not_be_shared():
    class Counter:
        def __init__(self):
            self.count = 0

    with pytest.raises(SweepError, match="writable instance dictionary"):
        SharedContext({"counter": Counter()})


def test_a_nested_mutable_is_caught_too():
    with pytest.raises(SweepError, match=r"thing\[1\]"):
        SharedContext({"thing": (1, [2, 3])})


def test_frozen_records_and_atoms_are_admitted():
    context = SharedContext(
        {
            "quantity": Quantity(3.0, "kohm"),
            "count": 7,
            "name": "plate",
            "tuple": (1, 2, 3),
            "frozen": frozenset({"a", "b"}),
            "none": None,
        }
    )
    assert context["count"] == 7
    assert len(context.identity) == 64
    assert context.describe()["quantity"].endswith("Quantity")


def test_the_shared_context_reports_what_it_holds():
    context = SharedContext({"r2": Quantity(3.0, "kohm")})
    assert context.describe() == {
        "r2": "engcore.scientific.units.quantity.Quantity"
    }
    summary = run_sweep(sweep(count=2, shared=context))
    assert summary.shared_entries == context.describe()
    assert summary.shared_identity == context.identity


def test_asking_for_something_not_shared_says_what_is():
    context = SharedContext({"a": 1})
    with pytest.raises(SweepError, match=r"holds \['a'\]"):
        context["b"]


def test_two_shared_contexts_with_different_values_have_different_identities():
    assert SharedContext({"a": 1}).identity != SharedContext({"a": 2}).identity
    assert SharedContext({"a": 1}).identity == SharedContext({"a": 1}).identity


# ---- isolation under concurrency -------------------------------------------------------
def test_results_stay_with_their_inputs_when_cases_interleave():
    """Threads execute in an arbitrary order; association must not depend on it."""
    barrier = threading.Barrier(4, timeout=30)

    def interleaved(shared, case):
        # Force every worker to be inside the operation at the same time.
        if case.inputs["x"] < 4:
            barrier.wait()
        return case.inputs["x"] * 2

    summary = run_sweep(sweep(operation=interleaved, count=16), workers=4)
    assert summary.succeeded == 16
    assert summary.values() == tuple(i * 2 for i in range(16))
    for outcome in summary.outcomes:
        assert outcome.value == outcome.case.inputs["x"] * 2


def test_a_failure_under_threads_is_still_isolated():
    summary = run_sweep(sweep(operation=exploding, count=8), workers=4)
    assert summary.failed == 1 and summary.succeeded == 7
    (failure,) = summary.failures()
    assert failure.case.inputs["x"] == 2


def test_fail_fast_is_refused_with_more_than_one_worker():
    with pytest.raises(SweepError, match="already in flight"):
        run_sweep(
            sweep(count=4, on_failure=FailurePolicy.FAIL_FAST), workers=2
        )


def test_zero_workers_is_refused():
    with pytest.raises(SweepError, match="at least one worker"):
        run_sweep(sweep(count=2), workers=0)


# ---- the summary ------------------------------------------------------------------------
def test_the_summary_holds_counts_and_failures_not_results():
    summary = run_sweep(sweep(operation=exploding, count=5))
    payload = summary.to_dict()
    assert payload["case_count"] == 5 and payload["succeeded"] == 4
    assert payload["failures"][0]["error_type"] == "ValueError"
    assert "values" not in payload and "outcomes" not in payload
    assert len(payload["identity"]) == 64
    assert payload["shared_identity"] == summary.shared_identity


def test_the_summary_stays_small_as_the_sweep_grows():
    """A summary is bookkeeping; results stay individual records."""
    small = run_sweep(sweep(count=10)).to_dict()
    large = run_sweep(sweep(count=2000)).to_dict()
    assert len(str(large)) < 2 * len(str(small)), (
        "the summary grows with the case count, so it is carrying results"
    )
