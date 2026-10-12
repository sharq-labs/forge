"""Provider qualification routes: a run binds the exact build, request and record; a qualification is admitted only
when every cited run resolves in the run ledger, passed, and no committed run of that route and build failed."""

from __future__ import annotations

import dataclasses
import types

import pytest

from engcore.providers import Availability, ProviderCapability, ProviderQualification, ProviderStatus, assess_health
from engcore.providers.health import ProviderHealth
from engcore.providers.identity import content_digest
from engcore.providers.qualification import (
    ReferenceRoute, RouteOutcome, RouteRun, RouteRunLedger, admitted_qualifications, qualification_problems, record_route_run,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity

CAP = ProviderCapability("demo", "multibody", "library", "demo", ("rigid_multibody_dynamics",))
STATUS = ProviderStatus(CAP, Availability.AVAILABLE, "10.0.0", "a" * 64, "/env")
ADAPTER = ("forge_demo", "0.2.0")
REQUEST = {"L": 1.0, "dt": 0.001}


def route(**kw):
    base = dict(route_id="demo.period", provider_id="demo", adapter=ADAPTER, scope=("passive_joint",), observable="period",
                reference=Quantity(2.0, "s"), reference_source="analytic", relative_tolerance=1e-3, case={"request": REQUEST},
                tolerance_basis="stated budget")
    base.update(kw)
    return ReferenceRoute(**base)


def record(value=2.0, *, succeeded=True, version="10.0.0", digest="a" * 64, adapter=ADAPTER, request=REQUEST, tag="e"):
    identity = types.SimpleNamespace(provider_id="demo", provider_version=version, provider_digest=digest, adapter_id=adapter[0],
                                     adapter_version=adapter[1], problem_digest=content_digest(request), digest=tag * 64)
    return types.SimpleNamespace(identity=identity, succeeded=succeeded, reason="" if succeeded else "solver diverged",
                                 value=value, digest=content_digest({"tag": tag, "value": value}))


def measure(rec):
    return None if rec.value is None else Quantity(rec.value, "s")


def qualification(refs, ledger, r=None, **kw):
    r = r or route()
    base = dict(provider_id="demo", provider_version="10.0.0", provider_digest="a" * 64, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1],
                scope=("passive_joint",), evidence_refs=tuple(refs), route="demo.period", issuer="reviewer:jdoe",
                route_digest=r.digest, ledger_head=ledger.head)
    base.update(kw)
    return ProviderQualification(**base)


def test_the_run_measures_the_observable_itself_and_decides_its_outcome():
    r = route()
    ok = record_route_run(r, STATUS, record(2.001), measure)
    assert ok.outcome is RouteOutcome.PASSED and ok.relative_error == pytest.approx(5e-4)
    assert ok.record_digest == record(2.001).digest and ok.route_digest == r.digest
    assert record_route_run(r, STATUS, record(2.01, tag="f"), measure).outcome is RouteOutcome.FAILED
    failed = record_route_run(r, STATUS, record(None, succeeded=False, tag="0"), measure)
    assert failed.outcome is RouteOutcome.PROVIDER_FAILED and failed.measured is None and "diverged" in failed.reason
    flat = record_route_run(r, STATUS, record(None, tag="1"), measure)  # ran, but no observable (e.g. it never swung)
    assert flat.outcome is RouteOutcome.NO_OBSERVABLE and "could not be measured" in flat.reason
    assert RouteRun.from_dict(ok.to_dict()) == ok
    with pytest.raises(InvalidScientificProblem, match="schema"):
        RouteRun.from_dict({**ok.to_dict(), "schema": "x"})


def test_a_forged_run_is_refused():
    r = route()
    ok = record_route_run(r, STATUS, record(2.001), measure)
    bad = record_route_run(r, STATUS, record(2.01, tag="f"), measure)
    with pytest.raises(InvalidScientificProblem, match="decided by its error"):
        dataclasses.replace(bad, outcome=RouteOutcome.PASSED)
    with pytest.raises(InvalidScientificProblem, match="recomputed"):  # a declared error that the values do not give
        dataclasses.replace(bad, relative_error=0.0, outcome=RouteOutcome.PASSED)
    with pytest.raises(InvalidScientificProblem, match="recomputed"):
        dataclasses.replace(ok, relative_error=-1.0)
    with pytest.raises(InvalidScientificProblem, match="recomputed"):
        RouteRun.from_dict({**ok.to_dict(), "measured": Quantity(99, "s").to_dict()})


def test_a_run_of_another_request_build_or_adapter_is_not_a_run_of_the_route():
    r = route()
    with pytest.raises(InvalidScientificProblem, match="another request"):
        record_route_run(r, STATUS, record(request={"L": 1.5, "dt": 0.001}), measure)
    with pytest.raises(InvalidScientificProblem, match="discovered provider build"):
        record_route_run(r, STATUS, record(digest="b" * 64), measure)
    with pytest.raises(InvalidScientificProblem, match="one translation"):
        record_route_run(r, STATUS, record(adapter=("forge_demo", "0.1.0")), measure)
    with pytest.raises(InvalidScientificProblem, match="not an available build"):
        record_route_run(r, ProviderStatus(CAP, Availability.UNAVAILABLE, reason="python module 'demo' is not installed"), record(), measure)
    with pytest.raises(InvalidScientificProblem, match="tolerance"):
        route(relative_tolerance=0.0)
    with pytest.raises(InvalidScientificProblem, match="request"):
        route(case={"L": 1})
    with pytest.raises(InvalidScientificProblem, match="tolerance_basis"):
        route(tolerance_basis="")


def test_only_qualifications_backed_by_the_ledger_are_admitted_by_assess_health():
    r = route()
    ok = record_route_run(r, STATUS, record(2.001), measure)
    ledger = RouteRunLedger().append(ok)
    q = qualification([ok.digest], ledger)
    assert qualification_problems(q, [r], ledger) == []
    assert admitted_qualifications([q], [r], ledger) == (q,)
    health = assess_health(STATUS, qualifications=(q,), scope=("passive_joint",), adapter=ADAPTER, routes=(r,), ledger=ledger)
    assert health.health is ProviderHealth.QUALIFIED
    # assess_health itself refuses an unbacked qualification (no routes, no ledger): bare strings are an assertion
    bare = assess_health(STATUS, qualifications=(q,), scope=("passive_joint",), adapter=ADAPTER)
    assert bare.health is ProviderHealth.UNQUALIFIED and "not backed" in bare.reason
    legacy = dataclasses.replace(q, route_digest="", ledger_head="")
    assert "cites nothing a reader can check" in qualification_problems(legacy, [r], ledger)[0]
    # a cited digest that is not in the ledger, a scope the route does not speak for, another build
    assert "not a run committed" in " ".join(qualification_problems(qualification(["9" * 64], ledger), [r], ledger))
    assert "outside what route" in " ".join(qualification_problems(qualification([ok.digest], ledger, scope=("contact",)), [r], ledger))
    assert "another provider build" in " ".join(qualification_problems(qualification([ok.digest], ledger, provider_digest="c" * 64), [r], ledger))


def test_a_failed_run_cannot_be_hidden_and_a_lookalike_route_is_another_route():
    r = route()
    ok = record_route_run(r, STATUS, record(2.001), measure)
    bad = record_route_run(r, STATUS, record(2.01, tag="f"), measure)
    full = RouteRunLedger().append(ok).append(bad)
    q = qualification([ok.digest], full)
    assert "did not pass" in " ".join(qualification_problems(q, [r], full))
    assert assess_health(STATUS, qualifications=(q,), scope=("passive_joint",), adapter=ADAPTER, routes=(r,), ledger=full).health \
        is ProviderHealth.UNQUALIFIED
    # dropping the failed run from the ledger changes its head: the qualification no longer resolves
    trimmed = RouteRunLedger((ok,))
    assert "not a head of the supplied run ledger" in " ".join(qualification_problems(q, [r], trimmed))
    with pytest.raises(InvalidScientificProblem, match="does not hash"):
        RouteRunLedger.from_dict({**full.to_dict(), "runs": [ok.to_dict()]})
    # a look-alike route (same id, looser tolerance) is not the declared route: its digest differs
    loose = route(relative_tolerance=0.9)
    lq = qualification([ok.digest], full, r=loose)
    assert "not one of the adapter's declared routes" in qualification_problems(lq, [r], full)[0]
    # a run carrying the route digest but other reference/tolerance values is not a run of the route as declared
    tampered = dataclasses.replace(ok, relative_tolerance=0.5)
    tl = RouteRunLedger((tampered,))
    assert "as declared" in " ".join(qualification_problems(qualification([tampered.digest], tl), [r], tl))
