"""Qualification ROUTES: declared reference runs whose records a provider qualification may cite.

A :class:`~engcore.providers.health.ProviderQualification` references
evidence; it is not evidence.  This module is where that evidence comes from:

* a :class:`ReferenceRoute` declares, for one provider and one adapter
  version, an observable, a reference value with its source, a tolerance and
  the scope the route speaks for;
* :func:`record_route_run` turns ONE executed provider run into a
  :class:`RouteRun` bound to the exact provider build (version + digest), the
  adapter version, the provider execution identity and the measured value.
  A run is PASSED only when the measured value is within the declared
  tolerance; a failed provider run is recorded as FAILED, never dropped;
* :func:`admitted_qualifications` keeps only qualifications whose every
  evidence reference resolves to a PASSED run of the same provider build,
  adapter version and route, and whose scope the route's scope covers.

Nothing here issues a qualification.  An issuer (a person or a declared
authority) does, citing run digests.  A green route says the translation
reproduced ONE declared reference on ONE build; it is not validation of any
product model and it never makes a model applicable.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity
from .catalog import ProviderStatus
from .health import ProviderQualification
from .identity import content_digest

ROUTE_SCHEMA = "engcore.providers.reference_route/1"
ROUTE_RUN_SCHEMA = "engcore.providers.route_run/1"
_HEX64 = re.compile(r"[0-9a-f]{64}")


class RouteOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"            # outside tolerance
    PROVIDER_FAILED = "provider_failed"  # the provider run itself failed; no value was produced


@dataclass(frozen=True)
class ReferenceRoute:
    """A declared reference case for one provider + adapter version."""

    route_id: str
    provider_id: str
    adapter: tuple[str, str]
    scope: tuple[str, ...]
    observable: str
    reference: Quantity
    reference_source: str
    relative_tolerance: float
    case: Mapping[str, Any]

    def __post_init__(self) -> None:
        for label in ("route_id", "provider_id", "observable", "reference_source"):
            if not str(getattr(self, label) or "").strip():
                raise InvalidScientificProblem(f"a reference route requires {label}")
        adapter = tuple(self.adapter)
        if len(adapter) != 2 or not all(str(a).strip() for a in adapter):
            raise InvalidScientificProblem("a reference route names the adapter (id, version) whose translation it checks")
        object.__setattr__(self, "adapter", (str(adapter[0]), str(adapter[1])))
        scope = tuple(sorted({str(s).strip() for s in self.scope}))
        if not scope or "" in scope:
            raise InvalidScientificProblem("a reference route states a non-empty scope")
        object.__setattr__(self, "scope", scope)
        if not isinstance(self.reference, Quantity):
            raise InvalidScientificProblem("a route reference is a Quantity (value and unit)")
        tol = float(self.relative_tolerance)
        if not (math.isfinite(tol) and 0 < tol < 1):
            raise InvalidScientificProblem("a route tolerance is a finite relative tolerance in (0, 1); none is never implied")
        object.__setattr__(self, "relative_tolerance", tol)
        object.__setattr__(self, "case", dict(self.case))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ROUTE_SCHEMA, "route_id": self.route_id, "provider_id": self.provider_id, "adapter": list(self.adapter),
                "scope": list(self.scope), "observable": self.observable, "reference": self.reference.to_dict(),
                "reference_source": self.reference_source, "relative_tolerance": self.relative_tolerance, "case": dict(self.case)}

    @property
    def digest(self) -> str:
        return content_digest(self.to_dict())


@dataclass(frozen=True)
class RouteRun:
    """One executed run of a route against an exact provider build.  A record of a check, not validation."""

    route_id: str
    route_digest: str
    provider_id: str
    provider_version: str
    provider_digest: str
    adapter: tuple[str, str]
    execution_identity: str
    outcome: RouteOutcome
    measured: Quantity | None
    reference: Quantity
    relative_error: float | None
    relative_tolerance: float
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", RouteOutcome(self.outcome))
        object.__setattr__(self, "adapter", tuple(self.adapter))
        for label in ("route_digest", "provider_digest", "execution_identity"):
            if not _HEX64.fullmatch(str(getattr(self, label))):
                raise InvalidScientificProblem(f"a route run binds {label} (sha256)")
        if self.outcome is RouteOutcome.PROVIDER_FAILED:
            if self.measured is not None or self.relative_error is not None:
                raise InvalidScientificProblem("a failed provider run produced no value; none is recorded")
        else:
            if not isinstance(self.measured, Quantity) or self.relative_error is None:
                raise InvalidScientificProblem("a completed route run records the measured value and its error")
            passed = self.relative_error <= self.relative_tolerance
            if passed != (self.outcome is RouteOutcome.PASSED):
                raise InvalidScientificProblem("a route run's outcome is decided by its error and tolerance, not declared")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ROUTE_RUN_SCHEMA, "classification": "reference_route_run_not_validation", "route_id": self.route_id,
                "route_digest": self.route_digest, "provider_id": self.provider_id, "provider_version": self.provider_version,
                "provider_digest": self.provider_digest, "adapter": list(self.adapter), "execution_identity": self.execution_identity,
                "outcome": self.outcome.value, "measured": None if self.measured is None else self.measured.to_dict(),
                "reference": self.reference.to_dict(), "relative_error": self.relative_error,
                "relative_tolerance": self.relative_tolerance, "reason": self.reason}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RouteRun":
        if payload.get("schema") != ROUTE_RUN_SCHEMA:
            raise InvalidScientificProblem(f"not a route run record (schema {payload.get('schema')!r})")
        m = payload.get("measured")
        return cls(payload["route_id"], payload["route_digest"], payload["provider_id"], payload["provider_version"],
                   payload["provider_digest"], tuple(payload["adapter"]), payload["execution_identity"], RouteOutcome(payload["outcome"]),
                   None if m is None else Quantity.from_dict(m), Quantity.from_dict(payload["reference"]), payload["relative_error"],
                   float(payload["relative_tolerance"]), payload.get("reason", ""))

    @property
    def digest(self) -> str:
        return content_digest(self.to_dict())


def record_route_run(route: ReferenceRoute, status: ProviderStatus, record: Any, measured: Quantity | None) -> RouteRun:
    """Record one provider run of ``route``.  ``record`` is the provider's execution record; ``measured`` is the
    observable extracted from it (None when the run failed).  A run of another provider or adapter is refused."""
    if not status.available or status.capability.provider_id != route.provider_id:
        raise InvalidScientificProblem(f"route {route.route_id!r} runs {route.provider_id!r}; the status is not an available build of it")
    ident = record.identity
    if (ident.provider_id, ident.provider_version, ident.provider_digest) != (route.provider_id, status.version, status.digest):
        raise InvalidScientificProblem("the execution record was not produced by the discovered provider build")
    if (ident.adapter_id, ident.adapter_version) != route.adapter:
        raise InvalidScientificProblem(f"the execution record used adapter {(ident.adapter_id, ident.adapter_version)}, "
                                       f"not the route's {route.adapter}; a route checks one translation")
    common = dict(route_id=route.route_id, route_digest=route.digest, provider_id=route.provider_id, provider_version=status.version,
                  provider_digest=status.digest, adapter=route.adapter, execution_identity=ident.digest, reference=route.reference,
                  relative_tolerance=route.relative_tolerance)
    if not record.succeeded or measured is None:
        return RouteRun(**common, outcome=RouteOutcome.PROVIDER_FAILED, measured=None, relative_error=None,
                        reason=str(getattr(record, "reason", "") or "no value"))
    unit = str(route.reference.units)
    ref = route.reference.magnitude_in(unit)
    value = measured.magnitude_in(unit)
    if not math.isfinite(value) or ref == 0:
        raise InvalidScientificProblem("a route compares a finite value against a non-zero reference")
    err = abs(value - ref) / abs(ref)
    outcome = RouteOutcome.PASSED if err <= route.relative_tolerance else RouteOutcome.FAILED
    return RouteRun(**common, outcome=outcome, measured=measured, relative_error=err)


def qualification_problems(q: ProviderQualification, routes: Iterable[ReferenceRoute], runs: Iterable[RouteRun]) -> list[str]:
    """Why ``q`` is not backed by passed route runs of its exact build and adapter (empty when it is)."""
    by_route = {r.route_id: r for r in routes}
    by_digest = {r.digest: r for r in runs}
    problems = []
    route = by_route.get(q.route)
    if route is None:
        return [f"route {q.route!r} is not a declared reference route"]
    if route.provider_id != q.provider_id or route.adapter != (q.adapter_id, q.adapter_version):
        problems.append(f"route {q.route!r} checks {route.provider_id} through {route.adapter}, not this provider/adapter")
    if not set(q.scope) <= set(route.scope):
        problems.append(f"scope {sorted(set(q.scope) - set(route.scope))} is outside what route {q.route!r} speaks for")
    for ref in q.evidence_refs:
        run = by_digest.get(ref)
        if run is None:
            problems.append(f"evidence reference {ref[:16]} resolves to no route run")
            continue
        if run.outcome is not RouteOutcome.PASSED:
            problems.append(f"route run {ref[:16]} did not pass ({run.outcome.value})")
        if run.route_digest != route.digest:
            problems.append(f"route run {ref[:16]} ran another version of route {q.route!r}")
        if (run.provider_id, run.provider_version, run.provider_digest) != (q.provider_id, q.provider_version, q.provider_digest):
            problems.append(f"route run {ref[:16]} ran another provider build")
        if run.adapter != (q.adapter_id, q.adapter_version):
            problems.append(f"route run {ref[:16]} ran another adapter version")
    # a failed run of the same route on the same build is a contradiction the issuer cannot cite around
    for run in by_digest.values():
        if (run.route_digest == route.digest and run.provider_digest == q.provider_digest and run.adapter == (q.adapter_id, q.adapter_version)
                and run.outcome is not RouteOutcome.PASSED):
            problems.append(f"route run {run.digest[:16]} of the same route and build did not pass ({run.outcome.value})")
    return problems


def admitted_qualifications(qualifications: Iterable[ProviderQualification], routes: Iterable[ReferenceRoute],
                            runs: Iterable[RouteRun]) -> tuple[ProviderQualification, ...]:
    """The qualifications backed by passed route runs; the rest are dropped (an unbacked one is an assertion)."""
    routes, runs = tuple(routes), tuple(runs)
    return tuple(q for q in qualifications if not qualification_problems(q, routes, runs))


__all__ = ["ROUTE_RUN_SCHEMA", "ROUTE_SCHEMA", "ReferenceRoute", "RouteOutcome", "RouteRun", "admitted_qualifications",
           "qualification_problems", "record_route_run"]
