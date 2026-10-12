"""Provider health, qualification and executable-probe receipts (fail-closed).

The registry (:mod:`.catalog`) answers ONE question: can this provider be
identified and run here (AVAILABLE / UNAVAILABLE)?  This module keeps that
answer and adds the distinctions an engineering platform needs, as a derived
view rather than a second registry:

=============  ===============================================================
NOT_INSTALLED  nothing to run was found
BROKEN         something was found but could not be identified or run
               (failed version probe, unparseable version, adapter import error)
AVAILABLE      identified and runnable; qualification NOT ASKED
UNQUALIFIED    identified and runnable, but no qualification record covers the
               requested scope at this exact version + digest
QUALIFIED      a qualification record names this exact provider version +
               digest AND the requested scope, with evidence references
=============  ===============================================================

Installed is not qualified, and qualified is not validated: a qualification
record says a declared route (benchmark suite, reference cases) was run for
a declared scope.  It is a reference to evidence held elsewhere, never
evidence itself, and it never makes a model applicable.

:func:`probe_executable` is the general executable probe with a full
receipt (command identity, argv, exit status, timeout, environment digest,
output digests, parsed version).  :func:`solver_identity_from_probe` is the
only path from a probe to a :class:`~engcore.scientific.solvers.protocol.SolverIdentity`
here, and it refuses any probe that did not succeed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import os
import re
import shutil
import time
from typing import Any, Callable, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.solvers.protocol import SolverIdentity
from .catalog import Availability, ProviderCapability, ProviderStatus
from .identity import content_digest
from .records import ProviderRefusal

PROBE_RECEIPT_SCHEMA = "engcore.providers.probe_receipt/1"
QUALIFICATION_SCHEMA = "engcore.providers.qualification/1"
HEALTH_SCHEMA = "engcore.providers.health/1"


class ProviderHealth(str, Enum):
    NOT_INSTALLED = "not_installed"
    BROKEN = "broken"
    AVAILABLE = "available"
    UNQUALIFIED = "unqualified"
    QUALIFIED = "qualified"


@dataclass(frozen=True)
class ProbeReceipt:
    """Everything an executable probe did, by content.  Operational record, not evidence."""

    command: str
    resolved_path: str
    executable_digest: str
    argv: tuple[str, ...]
    environment_digest: str
    exit_code: int | None
    timed_out: bool
    stdout_digest: str
    stderr_digest: str
    output_tail: str
    parsed_version: str
    accepted_exit_codes: tuple[int, ...]
    duration_s: float
    failure: str = ""

    @property
    def succeeded(self) -> bool:
        return (not self.failure and not self.timed_out and self.exit_code in self.accepted_exit_codes
                and bool(self.parsed_version) and bool(self.executable_digest))

    def to_dict(self) -> dict[str, Any]:
        # path and duration are operational; everything else is identity
        return {"schema": PROBE_RECEIPT_SCHEMA, "classification": "probe_not_evidence", "command": self.command,
                "executable_digest": self.executable_digest, "argv": list(self.argv), "environment_digest": self.environment_digest,
                "exit_code": self.exit_code, "timed_out": self.timed_out, "stdout_digest": self.stdout_digest,
                "stderr_digest": self.stderr_digest, "parsed_version": self.parsed_version,
                "accepted_exit_codes": list(self.accepted_exit_codes), "failure": self.failure}

    @property
    def digest(self) -> str:
        return content_digest(self.to_dict())


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def probe_executable(command: str, version_argv: tuple[str, ...], parse_version: Callable[[str], str], *,
                     search_path: str | None = None, timeout_s: float = 30.0, accepted_exit_codes: tuple[int, ...] = (0,),
                     environment: Mapping[str, str] | None = None) -> ProbeReceipt:
    """Run ``command version_argv`` with an explicit minimal environment and record exactly what happened.

    Never raises for an absent/broken tool: the receipt says why it failed.
    """
    codes = tuple(accepted_exit_codes)
    if not codes or any(isinstance(c, bool) or not isinstance(c, int) or c < 0 for c in codes):
        raise InvalidScientificProblem(f"accepted_exit_codes must be non-negative ints, got {accepted_exit_codes!r}")
    if not float(timeout_s) > 0:
        raise InvalidScientificProblem("a probe needs a positive timeout")
    argv = tuple(str(a) for a in version_argv)
    path = shutil.which(command, path=search_path)
    if path is None:
        return ProbeReceipt(command, "", "", argv, "", None, False, "", "", "", "", codes, 0.0, failure="not_found")
    real = os.path.realpath(path)
    env = {"PATH": os.path.dirname(real), "HOME": os.environ.get("HOME", "/tmp"), "LC_ALL": "C"}
    env.update(dict(environment or {}))
    # PATH and HOME are install/host locations: their NAMES are identity, their values are operational
    env_digest = content_digest(sorted((k, "<location>" if k in ("PATH", "HOME") else v) for k, v in env.items()))
    try:
        with open(real, "rb") as fh:
            exe_digest = _sha(fh.read())
    except OSError as exc:
        return ProbeReceipt(command, real, "", argv, env_digest, None, False, "", "", "", "", codes, 0.0,
                            failure=f"unreadable_executable: {type(exc).__name__}")
    from .process import run_bounded  # the process boundary: a timeout ends the probe's whole tree

    start = time.perf_counter()
    try:
        code, timed_out, so, se = run_bounded([real, *argv], timeout_s=float(timeout_s), env=env)
    except ProviderRefusal as exc:
        cause = exc.__cause__ if isinstance(exc.__cause__, OSError) else exc
        return ProbeReceipt(command, real, exe_digest, argv, env_digest, None, False, "", "", "", "", codes,
                            time.perf_counter() - start, failure=f"launch_failed: {type(cause).__name__}: {cause}")
    if timed_out:
        return ProbeReceipt(command, real, exe_digest, argv, env_digest, None, True, _sha(so), _sha(se),
                            (so + se)[-2000:].decode("utf-8", "replace"), "", codes, time.perf_counter() - start, failure="timeout")
    text = so.decode("utf-8", "replace") + se.decode("utf-8", "replace")
    try:
        version = str(parse_version(text) or "").strip()
    except Exception as exc:  # a parser bug is a broken probe, never a version
        version, failure = "", f"version_parse_error: {type(exc).__name__}"
    else:
        failure = ""
    if code not in codes:
        failure = failure or f"exit_code_{code}"
    elif not version:
        failure = failure or "version_unparsed"
    return ProbeReceipt(command, real, exe_digest, argv, env_digest, code, False, _sha(so),
                        _sha(se), text[-2000:], version, codes, time.perf_counter() - start, failure=failure)


def status_from_probe(capability: ProviderCapability, receipt: ProbeReceipt) -> ProviderStatus:
    """The registry status a probe receipt supports.  Only a succeeded probe yields AVAILABLE."""
    if receipt.succeeded:
        return ProviderStatus(capability, Availability.AVAILABLE, receipt.parsed_version, receipt.executable_digest,
                              receipt.resolved_path, executable_digest=receipt.executable_digest)
    if receipt.failure == "not_found":
        return ProviderStatus(capability, Availability.UNAVAILABLE, reason=f"executable {receipt.command!r} not found")
    if receipt.failure in ("version_unparsed",) or receipt.failure.startswith("version_parse_error"):
        reason = f"could not establish the version of {receipt.resolved_path}"
    else:
        reason = f"version probe of {receipt.resolved_path} failed ({receipt.failure})"
    return ProviderStatus(capability, Availability.UNAVAILABLE, location=receipt.resolved_path, reason=reason)


def solver_identity_from_probe(receipt: ProbeReceipt, solver_id: str) -> SolverIdentity:
    """A SolverIdentity bound to the probed executable digest.  Refused for any probe that did not succeed."""
    if not isinstance(receipt, ProbeReceipt) or not receipt.succeeded:
        why = receipt.failure if isinstance(receipt, ProbeReceipt) else "not a probe receipt"
        raise InvalidScientificProblem(f"no solver identity without a valid probe ({why}); an executable that did not "
                                       "answer its version probe cannot be identified")
    return SolverIdentity(solver_id, receipt.parsed_version, f"exe-sha256:{receipt.executable_digest}")


@dataclass(frozen=True)
class ProviderQualification:
    """A declared qualification route run for an exact provider build and scope.  References evidence; is not evidence."""

    provider_id: str
    provider_version: str
    provider_digest: str
    adapter_id: str
    adapter_version: str
    scope: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    route: str
    issuer: str
    notes: str = ""
    #: the digest of the adapter-declared ReferenceRoute and the RouteRunLedger head the cited runs are committed to
    #: (:mod:`.qualification`).  Without both, :func:`assess_health` never admits the qualification.
    route_digest: str = ""
    ledger_head: str = ""

    def __post_init__(self) -> None:
        for label in ("provider_id", "provider_version", "adapter_id", "adapter_version", "route", "issuer"):
            if not str(getattr(self, label) or "").strip():
                raise InvalidScientificProblem(f"a qualification requires {label}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(self.provider_digest)):
            raise InvalidScientificProblem("a qualification binds the exact provider digest (sha256)")
        scope = tuple(sorted({str(s).strip() for s in self.scope}))
        refs = tuple(sorted({str(s).strip() for s in self.evidence_refs}))
        if not scope or "" in scope:
            raise InvalidScientificProblem("a qualification states a non-empty scope; 'everything' is not a scope")
        if not refs or "" in refs:
            raise InvalidScientificProblem("a qualification without evidence references is an assertion, not a qualification")
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "evidence_refs", refs)

    def covers(self, status: ProviderStatus, scope: tuple[str, ...], adapter: tuple[str, str]) -> bool:
        """Exact provider build AND exact adapter (translation) version AND the requested scope."""
        return (status.available and status.capability.provider_id == self.provider_id and status.version == self.provider_version
                and status.digest == self.provider_digest and tuple(adapter) == (self.adapter_id, self.adapter_version)
                and set(scope) <= set(self.scope))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": QUALIFICATION_SCHEMA, "classification": "qualification_reference_not_evidence", "provider_id": self.provider_id,
                "provider_version": self.provider_version, "provider_digest": self.provider_digest, "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version, "scope": list(self.scope),
                "evidence_refs": list(self.evidence_refs), "route": self.route, "issuer": self.issuer,
                "route_digest": self.route_digest, "ledger_head": self.ledger_head}

    @property
    def digest(self) -> str:
        return content_digest(self.to_dict())


@dataclass(frozen=True)
class ProviderHealthReport:
    provider_id: str
    health: ProviderHealth
    reason: str
    status_digest: str
    requested_scope: tuple[str, ...] = ()
    qualification_digest: str = ""
    probe_digest: str = ""

    @property
    def executable(self) -> bool:
        """True for AVAILABLE, UNQUALIFIED and QUALIFIED: the provider may run.  Running is not trusting."""
        return self.health in (ProviderHealth.AVAILABLE, ProviderHealth.UNQUALIFIED, ProviderHealth.QUALIFIED)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": HEALTH_SCHEMA, "provider_id": self.provider_id, "health": self.health.value, "reason": self.reason,
                "status_digest": self.status_digest, "requested_scope": list(self.requested_scope),
                "qualification_digest": self.qualification_digest, "probe_digest": self.probe_digest}


#: The ONLY reasons read as "nothing is installed".  Anything else unavailable is BROKEN (fail closed).
_NOT_FOUND = (re.compile(r"^executable '[^']*' not found$"), re.compile(r"^python module '[^']*' is not installed$"),
              re.compile(r"^adapter package '[^']*' is not importable here \(ModuleNotFoundError: No module named '[^']*'\)$"))


def _nothing_found(status: ProviderStatus, probe: ProbeReceipt | None) -> bool:
    if status.location or (probe is not None and probe.failure != "not_found"):
        return False
    return any(p.match(status.reason or "") for p in _NOT_FOUND)


def assess_health(status: ProviderStatus, *, qualifications: tuple[ProviderQualification, ...] = (),
                  scope: tuple[str, ...] = (), adapter: tuple[str, str] | None = None,
                  probe: ProbeReceipt | None = None, routes: tuple = (), ledger: Any = None) -> ProviderHealthReport:
    """Classify one provider status.  With a ``scope``, the answer is QUALIFIED or UNQUALIFIED, never AVAILABLE.

    Fail-closed: an unavailable provider is NOT_INSTALLED only for an exact
    nothing-found reason; every other unavailable status is BROKEN.  A probe
    that disagrees with the status makes the provider BROKEN.  Qualification
    needs the exact provider build and the exact adapter (translation)
    version, because a changed adapter changes what the provider is asked.
    A qualification counts only when :func:`.qualification.qualification_problems`
    finds it backed by passed runs of an adapter-declared route (``routes``)
    committed to the run ``ledger``; a qualification with bare evidence
    strings is an assertion and leaves the provider UNQUALIFIED.
    """
    pid = status.capability.provider_id
    sdigest = content_digest({k: v for k, v in status.to_dict().items() if k != "location"})
    pdig = probe.digest if probe is not None else ""
    scope = tuple(sorted({str(s).strip() for s in scope if str(s).strip()}))
    if probe is not None:
        disagree = probe.succeeded != status.available or (
            status.available and status.executable_digest and probe.executable_digest != status.executable_digest)
        if disagree:
            return ProviderHealthReport(pid, ProviderHealth.BROKEN, "the probe receipt and the registry status disagree", sdigest, scope,
                                        probe_digest=pdig)
    if not status.available:
        health = ProviderHealth.NOT_INSTALLED if _nothing_found(status, probe) else ProviderHealth.BROKEN
        return ProviderHealthReport(pid, health, status.reason or "unavailable", sdigest, scope, probe_digest=pdig)
    if not scope:
        return ProviderHealthReport(pid, ProviderHealth.AVAILABLE, "identified and runnable; qualification not requested",
                                    sdigest, probe_digest=pdig)
    if adapter is None or len(tuple(adapter)) != 2:
        raise InvalidScientificProblem("a qualification question names the adapter (id, version) that would translate the request")
    from .qualification import qualification_problems

    unbacked = []
    for q in qualifications:
        if q.covers(status, scope, tuple(adapter)):
            problems = qualification_problems(q, tuple(routes), ledger)
            if not problems:
                return ProviderHealthReport(pid, ProviderHealth.QUALIFIED, f"qualification {q.route!r} by {q.issuer} covers {list(scope)}",
                                            sdigest, scope, q.digest, pdig)
            unbacked.append(f"{q.route!r}: {problems[0]}")
    if unbacked:
        return ProviderHealthReport(pid, ProviderHealth.UNQUALIFIED, "a qualification names this build but is not backed by passed "
                                    f"route runs ({'; '.join(unbacked)})", sdigest, scope, probe_digest=pdig)
    stale = [q for q in qualifications if q.provider_id == pid and (
        q.provider_version != status.version or q.provider_digest != status.digest or (q.adapter_id, q.adapter_version) != tuple(adapter))]
    why = ("a qualification exists for another provider build or adapter version; it does not transfer" if stale
           else f"no qualification covers {list(scope)} for {pid} {status.version}")
    return ProviderHealthReport(pid, ProviderHealth.UNQUALIFIED, why, sdigest, scope, probe_digest=pdig)
