"""Provider qualification routes: a run record binds the exact build; a qualification is admitted only on passed runs."""

from __future__ import annotations

import dataclasses
import types

import pytest

from engcore.providers import Availability, ProviderCapability, ProviderQualification, ProviderStatus, assess_health
from engcore.providers.health import ProviderHealth
from engcore.providers.qualification import (
    ReferenceRoute, RouteOutcome, RouteRun, admitted_qualifications, qualification_problems, record_route_run,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity

CAP = ProviderCapability("demo", "multibody", "library", "demo", ("rigid_multibody_dynamics",))
STATUS = ProviderStatus(CAP, Availability.AVAILABLE, "10.0.0", "a" * 64, "/env")
ADAPTER = ("forge_demo", "0.2.0")


def route(**kw):
    base = dict(route_id="demo.period", provider_id="demo", adapter=ADAPTER, scope=("passive_joint",), observable="period",
                reference=Quantity(2.0, "s"), reference_source="analytic", relative_tolerance=1e-3, case={"L": 1})
    base.update(kw)
    return ReferenceRoute(**base)


def record(succeeded=True, *, version="10.0.0", digest="a" * 64, adapter=ADAPTER, ident="e"):
    identity = types.SimpleNamespace(provider_id="demo", provider_version=version, provider_digest=digest, adapter_id=adapter[0],
                                     adapter_version=adapter[1], digest=ident * 64)
    return types.SimpleNamespace(identity=identity, succeeded=succeeded, reason="" if succeeded else "solver diverged")


def qualification(refs, **kw):
    base = dict(provider_id="demo", provider_version="10.0.0", provider_digest="a" * 64, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1],
                scope=("passive_joint",), evidence_refs=tuple(refs), route="demo.period", issuer="reviewer:jdoe")
    base.update(kw)
    return ProviderQualification(**base)


def test_a_route_run_is_decided_by_its_error_and_bound_to_the_build():
    r = route()
    ok = record_route_run(r, STATUS, record(), Quantity(2001, "ms"))
    assert ok.outcome is RouteOutcome.PASSED and ok.relative_error == pytest.approx(5e-4)
    assert ok.provider_digest == "a" * 64 and ok.execution_identity == "e" * 64 and ok.route_digest == r.digest
    bad = record_route_run(r, STATUS, record(ident="f"), Quantity(2.01, "s"))
    assert bad.outcome is RouteOutcome.FAILED
    failed = record_route_run(r, STATUS, record(False, ident="0"), None)
    assert failed.outcome is RouteOutcome.PROVIDER_FAILED and failed.measured is None and "diverged" in failed.reason
    assert RouteRun.from_dict(ok.to_dict()) == ok
    with pytest.raises(InvalidScientificProblem, match="decided by its error"):
        dataclasses.replace(bad, outcome=RouteOutcome.PASSED)  # a run cannot be declared passed
    with pytest.raises(InvalidScientificProblem, match="schema"):
        RouteRun.from_dict({**ok.to_dict(), "schema": "x"})


def test_a_run_of_another_build_or_adapter_is_refused():
    r = route()
    with pytest.raises(InvalidScientificProblem, match="discovered provider build"):
        record_route_run(r, STATUS, record(digest="b" * 64), Quantity(2, "s"))
    with pytest.raises(InvalidScientificProblem, match="one translation"):
        record_route_run(r, STATUS, record(adapter=("forge_demo", "0.1.0")), Quantity(2, "s"))
    with pytest.raises(InvalidScientificProblem, match="not an available build"):
        record_route_run(r, ProviderStatus(CAP, Availability.UNAVAILABLE, reason="python module 'demo' is not installed"), record(), Quantity(2, "s"))
    with pytest.raises(InvalidScientificProblem, match="tolerance"):
        route(relative_tolerance=0.0)
    with pytest.raises(InvalidScientificProblem, match="non-empty scope"):
        route(scope=())


def test_only_qualifications_backed_by_passed_runs_of_the_same_build_are_admitted():
    r = route()
    ok = record_route_run(r, STATUS, record(), Quantity(2001, "ms"))
    q = qualification([ok.digest])
    assert qualification_problems(q, [r], [ok]) == []
    assert admitted_qualifications([q], [r], [ok]) == (q,)
    report = assess_health(STATUS, qualifications=admitted_qualifications([q], [r], [ok]), scope=("passive_joint",), adapter=ADAPTER)
    assert report.health is ProviderHealth.QUALIFIED

    # an evidence reference that resolves to nothing is an assertion
    assert "resolves to no route run" in " ".join(qualification_problems(qualification(["9" * 64]), [r], [ok]))
    # a scope the route does not speak for
    assert "outside what route" in " ".join(qualification_problems(qualification([ok.digest], scope=("contact",)), [r], [ok]))
    # another build named by the qualification than the one that ran
    assert "another provider build" in " ".join(qualification_problems(qualification([ok.digest], provider_digest="c" * 64), [r], [ok]))
    # a failed run of the same route and build cannot be cited around
    bad = record_route_run(r, STATUS, record(ident="f"), Quantity(2.01, "s"))
    assert "did not pass" in " ".join(qualification_problems(q, [r], [ok, bad]))
    assert admitted_qualifications([q], [r], [ok, bad]) == ()
    unbacked = assess_health(STATUS, qualifications=admitted_qualifications([q], [r], [ok, bad]), scope=("passive_joint",), adapter=ADAPTER)
    assert unbacked.health is ProviderHealth.UNQUALIFIED
    # a changed route (other tolerance) is another route version
    looser = route(relative_tolerance=1e-2)
    assert "another version of route" in " ".join(qualification_problems(q, [looser], [ok]))
