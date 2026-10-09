"""Qualification ROUTES: declared reference runs whose records a provider qualification must cite.

A :class:`~engcore.providers.health.ProviderQualification` references
evidence; it is not evidence.  This module is where that evidence comes from,
and :func:`~engcore.providers.health.assess_health` admits a qualification
ONLY through :func:`qualification_problems`:

* a :class:`ReferenceRoute` declares, for one provider and one adapter
  version, the exact request the provider is asked (``case["request"]``), an
  observable, a reference value with its source, a tolerance and the scope the
  route speaks for.  Routes are declared by the ADAPTER (e.g.
  ``forge_chrono.routes.declared_routes()``), and a qualification binds the
  route's digest, so a look-alike route with a looser tolerance is another route;
* :func:`record_route_run` turns ONE provider execution record into a
  :class:`RouteRun`: it checks the record ran the route's exact request on the
  discovered build through the route's adapter, MEASURES the observable itself
  with the route's extractor, and binds the full execution record digest.  The
  outcome is computed from the measured error, never declared;
* a :class:`RouteRunLedger` is a hash chain of every run recorded.  A
  qualification binds a ledger head; every run in the chain up to that head is
  scanned, so a FAILED run of the same route and build cannot be omitted
  without changing the head (removing evidence never increases assurance).

Nothing here issues a qualification.  An issuer does, citing run digests and
the ledger head.  A green route says the translation reproduced ONE declared
reference on ONE build; it is not validation of any product model and never
makes a model applicable.  Deferred: the ledger is a record, not a persisted
store; it is as trustworthy as where it is kept.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity
from .catalog import ProviderStatus
from .health import ProviderQualification
from .identity import content_digest

ROUTE_SCHEMA = "engcore.providers.reference_route/1"
ROUTE_RUN_SCHEMA = "engcore.providers.route_run/1"
LEDGER_SCHEMA = "engcore.providers.route_run_ledger/1"
GENESIS = "0" * 64
_HEX64 = re.compile(r"[0-9a-f]{64}")
#: a recomputed relative error must equal the recorded one to this (float round-trip), or the run is refused
_ERROR_RECOMPUTE = 1e-12


class RouteOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"                    # outside tolerance
    NO_OBSERVABLE = "no_observable"      # the provider ran, but the observable could not be measured from its record
    PROVIDER_FAILED = "provider_failed"  # the provider run itself failed


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
    tolerance_basis: str = ""

    def __post_init__(self) -> None:
        for label in ("route_id", "provider_id", "observable", "reference_source", "tolerance_basis"):
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
        case = dict(self.case)
        if "request" not in case:
            raise InvalidScientificProblem("a route case names the exact request the provider is asked (case['request'])")
        object.__setattr__(self, "case", case)

    @property
    def problem_digest(self) -> str:
        """The digest an execution identity carries for this route's request."""
        return content_digest(self.case["request"])

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ROUTE_SCHEMA, "route_id": self.route_id, "provider_id": self.provider_id, "adapter": list(self.adapter),
                "scope": list(self.scope), "observable": self.observable, "reference": self.reference.to_dict(),
                "reference_source": self.reference_source, "relative_tolerance": self.relative_tolerance,
                "tolerance_basis": self.tolerance_basis, "case": dict(self.case)}

    @property
    def digest(self) -> str:
        return content_digest(self.to_dict())


def _relative_error(measured: Quantity, reference: Quantity) -> float:
    unit = str(reference.units)
    ref, value = reference.magnitude_in(unit), measured.magnitude_in(unit)
    if not math.isfinite(value) or ref == 0:
        raise InvalidScientificProblem("a route compares a finite value against a non-zero reference")
    return abs(value - ref) / abs(ref)


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
    record_digest: str
    outcome: RouteOutcome
    measured: Quantity | None
    reference: Quantity
    relative_error: float | None
    relative_tolerance: float
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", RouteOutcome(self.outcome))
        object.__setattr__(self, "adapter", tuple(self.adapter))
        for label in ("route_digest", "provider_digest", "execution_identity", "record_digest"):
            if not _HEX64.fullmatch(str(getattr(self, label))):
                raise InvalidScientificProblem(f"a route run binds {label} (sha256)")
        if self.outcome in (RouteOutcome.PROVIDER_FAILED, RouteOutcome.NO_OBSERVABLE):
            if self.measured is not None or self.relative_error is not None:
                raise InvalidScientificProblem("a run without a measured observable records no value and no error")
            if not str(self.reason).strip():
                raise InvalidScientificProblem("a run without a measured observable says why")
            return
        if not isinstance(self.measured, Quantity) or self.relative_error is None:
            raise InvalidScientificProblem("a completed route run records the measured value and its error")
        recomputed = _relative_error(self.measured, self.reference)
        if not abs(recomputed - float(self.relative_error)) <= _ERROR_RECOMPUTE * max(1.0, recomputed):
            raise InvalidScientificProblem("a route run's error is recomputed from its measured and reference values; it is not declared")
        passed = recomputed <= self.relative_tolerance
        if passed != (self.outcome is RouteOutcome.PASSED):
            raise InvalidScientificProblem("a route run's outcome is decided by its error and tolerance, not declared")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ROUTE_RUN_SCHEMA, "classification": "reference_route_run_not_validation", "route_id": self.route_id,
                "route_digest": self.route_digest, "provider_id": self.provider_id, "provider_version": self.provider_version,
                "provider_digest": self.provider_digest, "adapter": list(self.adapter), "execution_identity": self.execution_identity,
                "record_digest": self.record_digest, "outcome": self.outcome.value,
                "measured": None if self.measured is None else self.measured.to_dict(), "reference": self.reference.to_dict(),
                "relative_error": self.relative_error, "relative_tolerance": self.relative_tolerance, "reason": self.reason}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RouteRun":
        if payload.get("schema") != ROUTE_RUN_SCHEMA:
            raise InvalidScientificProblem(f"not a route run record (schema {payload.get('schema')!r})")
        m = payload.get("measured")
        return cls(payload["route_id"], payload["route_digest"], payload["provider_id"], payload["provider_version"],
                   payload["provider_digest"], tuple(payload["adapter"]), payload["execution_identity"], payload["record_digest"],
                   RouteOutcome(payload["outcome"]), None if m is None else Quantity.from_dict(m), Quantity.from_dict(payload["reference"]),
                   payload["relative_error"], float(payload["relative_tolerance"]), payload.get("reason", ""))

    @property
    def digest(self) -> str:
        return content_digest(self.to_dict())


def record_route_run(route: ReferenceRoute, status: ProviderStatus, record: Any,
                     measure: Callable[[Any], Quantity | None]) -> RouteRun:
    """Record one provider run of ``route``.  ``measure`` is the route's extractor: the observable is measured
    from ``record`` here, never supplied.  A run of another request, build or adapter is refused."""
    if not status.available or status.capability.provider_id != route.provider_id:
        raise InvalidScientificProblem(f"route {route.route_id!r} runs {route.provider_id!r}; the status is not an available build of it")
    ident = record.identity
    if (ident.provider_id, ident.provider_version, ident.provider_digest) != (route.provider_id, status.version, status.digest):
        raise InvalidScientificProblem("the execution record was not produced by the discovered provider build")
    if (ident.adapter_id, ident.adapter_version) != route.adapter:
        raise InvalidScientificProblem(f"the execution record used adapter {(ident.adapter_id, ident.adapter_version)}, "
                                       f"not the route's {route.adapter}; a route checks one translation")
    if ident.problem_digest != route.problem_digest:
        raise InvalidScientificProblem("the execution record ran another request than the route's case; it is not a run of this route")
    common = dict(route_id=route.route_id, route_digest=route.digest, provider_id=route.provider_id, provider_version=status.version,
                  provider_digest=status.digest, adapter=route.adapter, execution_identity=ident.digest, record_digest=record.digest,
                  reference=route.reference, relative_tolerance=route.relative_tolerance)
    if not record.succeeded:
        return RouteRun(**common, outcome=RouteOutcome.PROVIDER_FAILED, measured=None, relative_error=None,
                        reason=str(getattr(record, "reason", "") or "the provider run failed"))
    measured = measure(record)
    if measured is None:
        return RouteRun(**common, outcome=RouteOutcome.NO_OBSERVABLE, measured=None, relative_error=None,
                        reason=f"the provider ran but {route.observable!r} could not be measured from its record")
    err = _relative_error(measured, route.reference)
    outcome = RouteOutcome.PASSED if err <= route.relative_tolerance else RouteOutcome.FAILED
    return RouteRun(**common, outcome=outcome, measured=measured, relative_error=err)


def _link(previous: str, run_digest: str) -> str:
    return hashlib.sha256(f"{previous}\n{run_digest}".encode()).hexdigest()


@dataclass(frozen=True)
class RouteRunLedger:
    """Append-only hash chain of route runs.  ``heads[i]`` commits to runs[0..i]."""

    runs: tuple[RouteRun, ...] = ()

    def __post_init__(self) -> None:
        if any(not isinstance(r, RouteRun) for r in self.runs):
            raise InvalidScientificProblem("a route run ledger holds RouteRun records")
        object.__setattr__(self, "runs", tuple(self.runs))

    @property
    def heads(self) -> tuple[str, ...]:
        out, h = [], GENESIS
        for r in self.runs:
            h = _link(h, r.digest)
            out.append(h)
        return tuple(out)

    @property
    def head(self) -> str:
        return self.heads[-1] if self.runs else GENESIS

    def append(self, run: RouteRun) -> "RouteRunLedger":
        return RouteRunLedger(self.runs + (run,))

    def prefix(self, head: str) -> tuple[RouteRun, ...] | None:
        """The runs committed to by ``head`` (None when ``head`` is not a head of this chain)."""
        if head == GENESIS:
            return ()
        heads = self.heads
        return self.runs[: heads.index(head) + 1] if head in heads else None

    def to_dict(self) -> dict[str, Any]:
        return {"schema": LEDGER_SCHEMA, "runs": [r.to_dict() for r in self.runs], "head": self.head}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, expected_head: str | None = None) -> "RouteRunLedger":
        if payload.get("schema") != LEDGER_SCHEMA:
            raise InvalidScientificProblem(f"not a route run ledger (schema {payload.get('schema')!r})")
        ledger = cls(tuple(RouteRun.from_dict(r) for r in payload.get("runs", ())))
        if ledger.head != payload.get("head") or (expected_head is not None and ledger.head != expected_head):
            raise InvalidScientificProblem("the route run ledger does not hash to its recorded (or expected) head")
        return ledger


def qualification_problems(q: ProviderQualification, routes: Iterable[ReferenceRoute], ledger: RouteRunLedger | None) -> list[str]:
    """Why ``q`` is not backed by passed route runs of its exact build, adapter and route version (empty when it is).

    ``routes`` are the ADAPTER's declared routes; ``ledger`` is the run ledger the qualification's head commits into."""
    if not q.route_digest or not q.ledger_head:
        return ["the qualification binds no route digest and ledger head; it cites nothing a reader can check"]
    route = next((r for r in routes if r.digest == q.route_digest), None)
    if route is None:
        return [f"route digest {q.route_digest[:16]} is not one of the adapter's declared routes"]
    problems = []
    if route.route_id != q.route:
        problems.append(f"the qualification names route {q.route!r} but binds the digest of {route.route_id!r}")
    if route.provider_id != q.provider_id or route.adapter != (q.adapter_id, q.adapter_version):
        problems.append(f"route {route.route_id!r} checks {route.provider_id} through {route.adapter}, not this provider/adapter")
    if not set(q.scope) <= set(route.scope):
        problems.append(f"scope {sorted(set(q.scope) - set(route.scope))} is outside what route {route.route_id!r} speaks for")
    runs = None if ledger is None else ledger.prefix(q.ledger_head)
    if runs is None:
        return problems + [f"ledger head {q.ledger_head[:16]} is not a head of the supplied run ledger"]
    by_digest = {r.digest: r for r in runs}
    build = (q.provider_id, q.provider_version, q.provider_digest)
    for ref in q.evidence_refs:
        run = by_digest.get(ref)
        if run is None:
            problems.append(f"evidence reference {ref[:16]} is not a run committed to by the ledger head")
            continue
        if run.outcome is not RouteOutcome.PASSED:
            problems.append(f"route run {ref[:16]} did not pass ({run.outcome.value})")
        if run.route_digest != route.digest or run.reference != route.reference or run.relative_tolerance != route.relative_tolerance:
            problems.append(f"route run {ref[:16]} is not a run of route {route.route_id!r} as declared")
        if (run.provider_id, run.provider_version, run.provider_digest) != build:
            problems.append(f"route run {ref[:16]} ran another provider build")
        if run.adapter != (q.adapter_id, q.adapter_version):
            problems.append(f"route run {ref[:16]} ran another adapter version")
    # every committed run of this route on this build and adapter counts, cited or not
    for run in runs:
        if (run.route_digest == route.digest and (run.provider_id, run.provider_version, run.provider_digest) == build
                and run.adapter == (q.adapter_id, q.adapter_version) and run.outcome is not RouteOutcome.PASSED):
            problems.append(f"route run {run.digest[:16]} of the same route and build did not pass ({run.outcome.value})")
    return problems


def admitted_qualifications(qualifications: Iterable[ProviderQualification], routes: Iterable[ReferenceRoute],
                            ledger: RouteRunLedger | None) -> tuple[ProviderQualification, ...]:
    """The qualifications backed by passed route runs; the rest are dropped (an unbacked one is an assertion)."""
    routes = tuple(routes)
    return tuple(q for q in qualifications if not qualification_problems(q, routes, ledger))


__all__ = ["GENESIS", "LEDGER_SCHEMA", "ROUTE_RUN_SCHEMA", "ROUTE_SCHEMA", "ReferenceRoute", "RouteOutcome", "RouteRun", "RouteRunLedger",
           "admitted_qualifications", "qualification_problems", "record_route_run"]
