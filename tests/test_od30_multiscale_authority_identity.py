"""OD-30: a ``MultiscaleAuthority`` identity states the fast state its runs declare, and nothing else.

The identity payload embedded ``runtime.identities()["declared_fast_state"]`` as it stood at construction: the empty
declaration on a fresh runtime, or whatever the runtime last ran with. So two authorities that differ only in
``initial_fast_state`` shared one ``identity_digest`` -- one request digest, one plan digest, one replay identity --
and an authority built on a runtime that had already run inherited that run's fast state. The payload keeps its shape;
the value is now the authority's own declaration (``MultiTimescaleRuntime.declared_fast_state_digest``).

The toy runtime (``tests/test_multiscale_review_fixes.py``) has a genuine FAST variable (``thermal.core_temperature``).

2026-10-18 remediation, Batch B. Written, NOT RUN.
"""

from __future__ import annotations

import pytest

from engcore.multiscale import FastStateAtMacroStart, MultiTimescaleRuntime
from engcore.scientific.errors import InvalidScientificProblem
from engcore.system_runtime import MultiscaleAuthority
from tests import test_multiscale_review_fixes as RF


def _environment():
    env, _ = RF.R.build_environment(4)
    return env


def _runtime(env):
    return RF._toy_runtime(env, FastStateAtMacroStart.DECLARED_INITIAL)


def _authority(runtime, fast, authority_id="toy-aging"):
    slow, _ = RF._toy_state()
    return MultiscaleAuthority(authority_id, runtime, initial_slow_state=slow, initial_fast_state=fast, extractors={})


def test_two_authorities_differing_only_in_initial_fast_state_have_different_identities():
    env = _environment()
    _, at_300 = RF._toy_state(300.0)
    _, at_310 = RF._toy_state(310.0)
    a, b = _authority(_runtime(env), at_300), _authority(_runtime(env), at_310)
    assert a.identity_digest != b.identity_digest       # equal before OD-30: both read the fresh runtime's empty state
    assert a.identity_digest == _authority(_runtime(env), RF._toy_state(300.0)[1]).identity_digest  # and deterministic


def test_the_identity_does_not_depend_on_whether_a_shared_runtime_ran_before_construction():
    env = _environment()
    slow, at_300 = RF._toy_state(300.0)
    _, at_310 = RF._toy_state(310.0)
    runtime = _runtime(env)
    before = _authority(runtime, at_300)
    ran = runtime.run(initial_slow_state=slow, initial_fast_state=at_310, until=RF.R.p(RF.DAY))
    assert ran.status in ("completed", "paused"), ran.reason
    after = _authority(runtime, at_300)
    assert after.identity_digest == before.identity_digest  # before OD-30 `after` carried the 310 K run's fast state


def test_the_stated_fast_state_identity_is_the_one_the_runtime_records_for_that_declaration():
    """The authority's value and the runtime's own derivation cannot drift: same normalization, same digest."""
    env = _environment()
    slow, at_310 = RF._toy_state(310.0)
    runtime = _runtime(env)
    record = runtime.run(initial_slow_state=slow, initial_fast_state=at_310, until=RF.R.p(RF.DAY))
    expected = MultiTimescaleRuntime.declared_fast_state_digest(at_310)
    assert runtime.identities()["declared_fast_state"] == expected
    assert record.identities["declared_fast_state"] == expected


def test_no_declared_fast_state_over_a_runtime_that_never_ran_keeps_the_pre_od30_value():
    """Compatibility: for this case the payload entry is byte-for-byte what it was, so the digest does not move."""
    env = _environment()
    fresh = _runtime(env)
    assert MultiTimescaleRuntime.declared_fast_state_digest(None) == fresh.identities()["declared_fast_state"]
    assert MultiTimescaleRuntime.declared_fast_state_digest({}) == fresh.identities()["declared_fast_state"]


def test_the_digest_validates_nothing_and_a_run_still_refuses_an_incomplete_fast_state():
    """Pins a boundary, not the defect: this passes on the pre-OD-30 code too (the refusal is the runtime's)."""
    env = _environment()
    slow, _ = RF._toy_state()
    runtime = _runtime(env)
    authority = _authority(runtime, None)                    # constructs: the identity states the empty declaration
    assert isinstance(authority.identity_digest, str)
    with pytest.raises(InvalidScientificProblem, match="fast state must supply exactly"):
        runtime.run(initial_slow_state=slow, initial_fast_state=None, until=RF.R.p(RF.DAY))


def test_a_runtime_that_cannot_state_a_declared_fast_state_identity_is_refused():
    class Legacy:
        run_id = "legacy"

        def identities(self):
            return {"scenario": "a" * 64, "timeline": "b" * 64, "environment": "c" * 64, "declared_fast_state": "d" * 64}

    with pytest.raises(InvalidScientificProblem, match="never taken from the runtime's last run"):
        _authority(Legacy(), None)


# ---- review MINOR 1: the stated fast state is bound to the runs, not only to the digest ----------------------------


def _authorized(runtime):
    ids = runtime.identities()
    return {k: ids[k] for k in ("scenario", "timeline", "environment")}


def test_a_record_of_the_stated_fast_state_is_admitted():
    env = _environment()
    slow, at_310 = RF._toy_state(310.0)
    runtime = _runtime(env)
    authority = _authority(runtime, at_310)
    record = runtime.run(initial_slow_state=slow, initial_fast_state=at_310, until=RF.R.p(RF.DAY))
    assert authority._record_refusal(record, _authorized(runtime)) == ""


def test_a_record_whose_run_declared_another_fast_state_than_the_identity_states_is_refused():
    """A runtime that misstates the digest (here: an instance override) makes the identity name a fast state its runs
    never declare. Before the review fix nothing compared the two, so the record was admitted."""
    env = _environment()
    slow, at_310 = RF._toy_state(310.0)
    runtime = _runtime(env)
    runtime.declared_fast_state_digest = lambda state: "0" * 64
    authority = _authority(runtime, at_310)
    record = runtime.run(initial_slow_state=slow, initial_fast_state=at_310, until=RF.R.p(RF.DAY))
    assert "another initial fast state" in authority._record_refusal(record, _authorized(runtime))


def test_changing_the_callers_fast_state_mapping_after_construction_changes_nothing_the_authority_runs():
    env = _environment()
    _, at_300 = RF._toy_state(300.0)
    _, at_310 = RF._toy_state(310.0)
    authority = _authority(_runtime(env), at_300)
    at_300["thermal"]["core_temperature"] = at_310["thermal"]["core_temperature"]   # the caller's mapping, mutated
    held = authority._fast["thermal"]["core_temperature"].value.magnitude_in("K")
    assert held == 300.0
