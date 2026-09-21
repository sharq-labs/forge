"""The external-provider contract: what Forge asks, and what it accepts back.

`HETERO-NGSPICE` proved that an execution path Forge did not write can satisfy
`ScientificResult` and travel the same trust path as a native solve. Its module
docstring also named the condition for generalising what it did:

    "A second external provider whose process-execution needs actually overlap
    is the named trigger for generalising; until then a shared abstraction
    would be a guess with one member."

PyBaMM is the second provider, and its process-execution needs do **not**
overlap: ngspice is a subprocess fed a netlist on stdin, PyBaMM is an
in-process Python library. So this module deliberately does *not* generalise
execution. What it generalises is the four things that were the same in both,
and that are the same for every external provider there will ever be:

1. **identity** — which exact external implementation produced a number;
2. **the request** — what was asked, digested so two asks can be compared;
3. **the outcome vocabulary** — the difference between the provider failing
   and the science being refused;
4. **replay** — re-executing, rather than re-reading a stored answer.

What this module is not
-----------------------
Not a plugin framework. There is no discovery, no entry points, no registry, no
capability graph and no backend hierarchy. A provider is a class that satisfies
:class:`ScientificProvider`; the caller names it. `engcore.domainpacks` already
owns plugin discovery for the case where discovery is the problem, and a second
discovery mechanism for three hand-named libraries would be a guess.

Not a second result contract either. A provider that produces a scientific
answer produces a :class:`~engcore.scientific.results.result.ScientificResult`,
the same record the native solvers produce, so that everything downstream --
credibility, applicability, validation, uncertainty, claims, certification --
continues to work without knowing a provider exists. A provider that produces
something that is *not* an answer (a parameter fit, a sensitivity index)
produces evidence, and evidence is not a result.

THE SEPARATION THIS MODULE EXISTS FOR
--------------------------------------
``ExecutionOutcome`` has two halves and the property that divides them is
:attr:`ExecutionOutcome.is_provider_side`.

*Provider side* — the provider was asked and something happened to it.
``PROVIDER_UNAVAILABLE``, ``PROVIDER_ERROR``, ``NUMERICAL_FAILURE``. None of
these is a statement about nature. An unimportable package is not evidence
against a hypothesis.

*Forge side* — the provider delivered and Forge judged. ``MODEL_NOT_APPLICABLE``,
``FORGE_REFUSED``, ``MISSING_EVIDENCE``. None of these is a provider defect. A
model that ran perfectly and is not applicable here has not failed; it has been
correctly declined.

And ``OK`` means only that a result exists to be judged. It is the *beginning*
of the trust path, never a verdict from it. A provider cannot mint support.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable

from ..scientific.results.immutable import freeze
from ..scientific.results.result import ScientificResult
from ..scientific.serialization import require_schema, schema_string

PROVIDER_IDENTITY_SCHEMA = schema_string("provider_identity")
PROVIDER_REQUEST_SCHEMA = schema_string("provider_request")
PROVIDER_RECEIPT_SCHEMA = schema_string("provider_execution_receipt")
PROVIDER_REPLAY_SCHEMA = schema_string("provider_replay_report")


def digest_of(payload: Mapping[str, Any]) -> str:
    """SHA-256 over canonical bytes, the spelling the rest of the repo uses."""
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


# =====================================================================
# Failure — an execution concern, not a scientific one
# =====================================================================

class ProviderError(Exception):
    """Base for every way an external provider can fail to deliver.

    Inherits ``Exception`` and **not** ``ScientificCoreError``, for the reason
    ``NgspiceProviderError`` does and ``engcore.data`` does for
    ``BulkDataError``: a library being absent is not a scientific error.
    Collapsing them would make "PyBaMM is not installed" indistinguishable from
    "the science does not hold".
    """


class ProviderUnavailable(ProviderError):
    """The provider could not be reached at all -- typically not installed."""


class ProviderExecutionFailure(ProviderError):
    """The provider ran and did not deliver what was asked."""


# =====================================================================
# Identity
# =====================================================================

@dataclass(frozen=True)
class ProviderIdentity:
    """Which exact external scientific implementation produced a number.

    Six fields, and every one of them can change an answer:

    ``provider_name`` / ``provider_version``
        The library, at the version actually imported at run time. Read from
        the installed distribution, never hard-coded: a pinned string makes
        provenance lie the moment the environment changes.
    ``model_identity``
        Which of the provider's models. ``SPMe`` and ``DFN`` are different
        physics and must not share an identity.
    ``solver_identity``
        Which numerical solver inside the provider, at its settings.
    ``configuration_digest``
        Everything else the adapter chose -- discretisation, output set,
        tolerances -- as one digest, so a configuration change is visible
        without the record carrying a configuration schema.
    ``environment_identity``
        The interpreter and the dependency versions beneath the provider. A
        PyBaMM answer is a CasADi answer too.
    ``adapter_version``
        Forge's own translation layer. A bug fixed here changes numbers
        without any provider version moving, so it is part of identity.
    """

    provider_name: str
    provider_version: str
    model_identity: str
    solver_identity: str
    configuration_digest: str
    environment_identity: str
    adapter_version: str

    def __post_init__(self) -> None:
        for label in (
            "provider_name",
            "provider_version",
            "model_identity",
            "solver_identity",
            "configuration_digest",
            "environment_identity",
            "adapter_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ProviderError(
                    f"provider identity requires a non-empty {label}; an "
                    f"identity with a blank field cannot answer 'which exact "
                    f"implementation produced this number'"
                )
            object.__setattr__(self, label, value)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.provider_name, self.provider_version, self.model_identity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROVIDER_IDENTITY_SCHEMA,
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "model_identity": self.model_identity,
            "solver_identity": self.solver_identity,
            "configuration_digest": self.configuration_digest,
            "environment_identity": self.environment_identity,
            "adapter_version": self.adapter_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProviderIdentity":
        require_schema(payload, PROVIDER_IDENTITY_SCHEMA)
        return cls(
            provider_name=payload["provider_name"],
            provider_version=payload["provider_version"],
            model_identity=payload["model_identity"],
            solver_identity=payload["solver_identity"],
            configuration_digest=payload["configuration_digest"],
            environment_identity=payload["environment_identity"],
            adapter_version=payload["adapter_version"],
        )

    def digest(self) -> str:
        return digest_of(self.to_dict())


class ProviderCapability(str, Enum):
    """What a provider is being asked to do. Three, because three exist.

    Deliberately not a capability *graph*. A provider declares a set; a request
    names one; a mismatch is refused. That is the whole mechanism.
    """

    #: Advance a model over a protocol and return canonical time-series QoIs.
    TIME_SERIES_SIMULATION = "time_series_simulation"
    #: Fit declared parameters to a declared calibration dataset.
    PARAMETER_INFERENCE = "parameter_inference"
    #: Rank declared parameters by their influence on a declared QoI.
    SENSITIVITY_ANALYSIS = "sensitivity_analysis"


# =====================================================================
# The request
# =====================================================================

@dataclass(frozen=True)
class ProviderRequest:
    """What Forge asks, in Forge's vocabulary, digestible for comparison.

    ``qois`` are **canonical Forge names** -- ``terminal_voltage``, not
    ``"Voltage [V]"``. A request written in provider vocabulary would make the
    provider's naming part of the scientific question, and a second provider
    for the same physics could then not answer the same request.

    ``parameter_authority`` is a digest, not a parameter set. The authority
    itself is a record the caller holds (see
    :mod:`engcore.providers.pybamm_provider`); what the request carries is the
    statement that *this* authority governed *this* ask.
    """

    capability: ProviderCapability
    model_key: str
    parameter_authority: str
    qois: tuple[str, ...]
    inputs: Mapping[str, Any] = field(default_factory=dict)
    configuration: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.capability, ProviderCapability):
            raise ProviderError("request capability must be a ProviderCapability")
        for label in ("model_key", "parameter_authority"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ProviderError(f"a provider request requires a {label}")
            object.__setattr__(self, label, value)
        qois = tuple(str(name).strip() for name in self.qois)
        if not qois or any(not name for name in qois):
            raise ProviderError(
                "a provider request must name at least one canonical QoI; an "
                "ask with no QoI has nothing for Forge to judge"
            )
        if len(set(qois)) != len(qois):
            raise ProviderError(f"duplicate QoI in request: {qois}")
        object.__setattr__(self, "qois", qois)
        object.__setattr__(self, "inputs", freeze(dict(self.inputs)))
        object.__setattr__(self, "configuration", freeze(dict(self.configuration)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROVIDER_REQUEST_SCHEMA,
            "capability": self.capability.value,
            "model_key": self.model_key,
            "parameter_authority": self.parameter_authority,
            "qois": list(self.qois),
            "inputs": _plain(self.inputs),
            "configuration": _plain(self.configuration),
        }

    def digest(self) -> str:
        return digest_of(self.to_dict())


def _plain(value: Any) -> Any:
    """JSON-ready view of a frozen mapping tree, for digesting only."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in sorted(value.items(), key=lambda p: str(p[0]))}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# =====================================================================
# The outcome vocabulary — P12's separation, as a type
# =====================================================================

class ExecutionOutcome(str, Enum):
    """Why this request did or did not end in something Forge can judge.

    See the module docstring. The halves are distinguished by
    :attr:`is_provider_side`, and no member is a scientific verdict: ``OK``
    admits a result to the trust path and decides nothing there.
    """

    #: The provider delivered. Nothing more than that.
    OK = "ok"

    # --- provider side -------------------------------------------------
    #: The provider is not installed or cannot be imported.
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    #: The provider raised, or returned something the adapter cannot read.
    PROVIDER_ERROR = "provider_error"
    #: The provider ran and its numerics failed -- no convergence, non-finite.
    NUMERICAL_FAILURE = "numerical_failure"

    # --- Forge side ----------------------------------------------------
    #: The selected model does not claim the requested operating point.
    MODEL_NOT_APPLICABLE = "model_not_applicable"
    #: Forge declined on scientific grounds other than applicability.
    FORGE_REFUSED = "forge_refused"
    #: Evidence a decision needs was absent. Never a failure of anything.
    MISSING_EVIDENCE = "missing_evidence"

    @property
    def is_provider_side(self) -> bool:
        """Whether this outcome is a statement about the provider.

        ``OK`` is neither side: it is the handover.
        """
        return self in (
            ExecutionOutcome.PROVIDER_UNAVAILABLE,
            ExecutionOutcome.PROVIDER_ERROR,
            ExecutionOutcome.NUMERICAL_FAILURE,
        )

    @property
    def is_forge_side(self) -> bool:
        return self in (
            ExecutionOutcome.MODEL_NOT_APPLICABLE,
            ExecutionOutcome.FORGE_REFUSED,
            ExecutionOutcome.MISSING_EVIDENCE,
        )

    @property
    def delivered(self) -> bool:
        """Whether a result exists. Not whether it is trustworthy."""
        return self is ExecutionOutcome.OK


@dataclass(frozen=True)
class ProviderExecutionReceipt:
    """What actually ran, whether or not it produced anything.

    A receipt exists for every outcome, including ``PROVIDER_UNAVAILABLE``.
    That is the point: "we tried and the provider was absent" is a recorded
    fact, and a system that recorded only its successes could not tell it from
    "we never asked".
    """

    identity: ProviderIdentity | None
    request_digest: str
    outcome: ExecutionOutcome
    detail: str = ""
    wall_seconds: float | None = None
    started_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ExecutionOutcome):
            raise ProviderError("receipt outcome must be an ExecutionOutcome")
        digest = str(self.request_digest).strip()
        if not digest:
            raise ProviderError("a receipt requires the digest of the request it answers")
        object.__setattr__(self, "request_digest", digest)
        if self.outcome.delivered and self.identity is None:
            raise ProviderError(
                "a delivered result must carry the provider identity that "
                "produced it; an anonymous number has no provenance"
            )
        if self.wall_seconds is not None and self.wall_seconds < 0.0:
            raise ProviderError("wall_seconds must not be negative")
        object.__setattr__(self, "detail", str(self.detail))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROVIDER_RECEIPT_SCHEMA,
            "identity": None if self.identity is None else self.identity.to_dict(),
            "request_digest": self.request_digest,
            "outcome": self.outcome.value,
            "detail": self.detail,
            "wall_seconds": self.wall_seconds,
            "started_at": self.started_at,
        }


@dataclass(frozen=True)
class ProviderResult:
    """A receipt, and -- only when the provider delivered -- what it delivered.

    ``result`` is the scientific answer, as the same ``ScientificResult`` the
    native solvers produce. ``evidence`` is for providers whose product is not
    an answer: a fit, a sensitivity ranking. A provider result never carries
    both, because a record that was both an answer and evidence about answers
    would be admissible twice.
    """

    receipt: ProviderExecutionReceipt
    result: ScientificResult | None = None
    evidence: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        delivered = self.receipt.outcome.delivered
        if delivered and self.result is None and self.evidence is None:
            raise ProviderError(
                "outcome OK with nothing delivered. OK means a provider "
                "produced something; if it did not, the outcome is one of the "
                "provider-side members"
            )
        if not delivered and (self.result is not None or self.evidence is not None):
            raise ProviderError(
                f"outcome {self.receipt.outcome.value} carries a payload. A "
                f"non-delivering outcome has nothing to carry, and a payload "
                f"beside one is a result that would be read despite the refusal"
            )
        if self.result is not None and self.evidence is not None:
            raise ProviderError(
                "a provider result is an answer or evidence about answers, "
                "never both"
            )
        if self.evidence is not None:
            object.__setattr__(self, "evidence", freeze(dict(self.evidence)))

    @property
    def outcome(self) -> ExecutionOutcome:
        return self.receipt.outcome


@runtime_checkable
class ScientificProvider(Protocol):
    """What a provider adapter must offer. Four methods, no lifecycle.

    ``available()`` is separate from ``execute()`` on purpose: "is this
    provider installed" is a question a caller must be able to ask without
    running science, and an adapter that answered it by attempting a solve
    would make an availability probe cost a simulation.
    """

    @property
    def provider_name(self) -> str: ...

    def available(self) -> bool:
        """Whether the underlying library can be imported here."""
        ...

    def capabilities(self) -> frozenset[ProviderCapability]: ...

    def execute(self, request: ProviderRequest) -> ProviderResult: ...


def unavailable_result(
    request: ProviderRequest, detail: str
) -> ProviderResult:
    """The uniform answer to "the library is not installed here".

    A *result*, not an exception, because P17's rule is that a missing optional
    dependency produces a clear provider-unavailable result. An exception would
    make every caller write the same try/except and would tempt one of them to
    treat the absence as a scientific outcome.
    """
    return ProviderResult(
        receipt=ProviderExecutionReceipt(
            identity=None,
            request_digest=request.digest(),
            outcome=ExecutionOutcome.PROVIDER_UNAVAILABLE,
            detail=detail,
        )
    )


# =====================================================================
# Replay — re-execution, never re-reading
# =====================================================================

@dataclass(frozen=True)
class ProviderReplayReport:
    """The outcome of re-running a request and comparing canonical outputs.

    ``reproduced`` is three-valued through its companions rather than through a
    third state: ``executed`` says a second run happened at all, and
    ``identity_matched`` says it happened under the same provider identity. A
    run that reproduced the numbers under a *different* PyBaMM version has not
    demonstrated determinism, and a report that collapsed those into one
    boolean would say it had.

    ``drift`` is where an environment that moved is written down rather than
    hidden, which P11 requires explicitly.
    """

    request_digest: str
    executed: bool
    identity_matched: bool
    reproduced: bool
    compared_qois: tuple[str, ...]
    max_absolute_difference: float | None
    tolerance: float
    drift: tuple[str, ...] = ()
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROVIDER_REPLAY_SCHEMA,
            "request_digest": self.request_digest,
            "executed": self.executed,
            "identity_matched": self.identity_matched,
            "reproduced": self.reproduced,
            "compared_qois": list(self.compared_qois),
            "max_absolute_difference": self.max_absolute_difference,
            "tolerance": self.tolerance,
            "drift": list(self.drift),
            "detail": self.detail,
        }


def replay_provider_request(
    provider: ScientificProvider,
    request: ProviderRequest,
    original: ProviderResult,
    *,
    tolerance: float = 0.0,
) -> ProviderReplayReport:
    """Execute ``request`` again and compare against ``original``.

    Re-execution, not re-reading. The distinction is the whole of P11: loading
    a stored payload and comparing it to itself demonstrates that a file is
    stable, which nobody doubted. What is in doubt is whether the same ask,
    against the same provider, still produces the same numbers -- and the only
    way to learn that is to ask again.

    ``tolerance`` defaults to ``0.0``: bit-identical. A provider that is
    deterministic should be held to it, and a tolerance chosen to make a
    comparison pass is a tolerance that has stopped testing anything.
    """
    if original.result is None:
        raise ProviderError(
            "replay needs an original result to compare against; a receipt "
            "with no payload has no numbers to reproduce"
        )
    repeat = provider.execute(request)
    if not repeat.outcome.delivered:
        return ProviderReplayReport(
            request_digest=request.digest(),
            executed=False,
            identity_matched=False,
            reproduced=False,
            compared_qois=(),
            max_absolute_difference=None,
            tolerance=tolerance,
            drift=(f"re-execution did not deliver: {repeat.outcome.value}",),
            detail=repeat.receipt.detail,
        )

    drift: list[str] = []
    before = original.receipt.identity
    after = repeat.receipt.identity
    identity_matched = before == after
    if not identity_matched and before is not None and after is not None:
        for label in (
            "provider_version",
            "model_identity",
            "solver_identity",
            "configuration_digest",
            "environment_identity",
            "adapter_version",
        ):
            old = getattr(before, label)
            new = getattr(after, label)
            if old != new:
                drift.append(f"{label}: {old} -> {new}")

    compared: list[str] = []
    worst: float | None = None
    for name in sorted(request.qois):
        first = original.result.values.get(name)
        second = repeat.result.values.get(name) if repeat.result else None
        if first is None or second is None:
            drift.append(f"{name}: present in one run and not the other")
            continue
        compared.append(name)
        unit = first.units
        difference = abs(second.magnitude_in(unit) - first.magnitude_in(unit))
        worst = difference if worst is None else max(worst, difference)

    reproduced = (
        identity_matched
        and bool(compared)
        and worst is not None
        and worst <= tolerance
        and not drift
    )
    return ProviderReplayReport(
        request_digest=request.digest(),
        executed=True,
        identity_matched=identity_matched,
        reproduced=reproduced,
        compared_qois=tuple(compared),
        max_absolute_difference=worst,
        tolerance=tolerance,
        drift=tuple(drift),
    )




def canonical_qoi_names(values: Mapping[str, Any]) -> tuple[str, ...]:
    """The QoI names a result carries, sorted. Used by guards and reports."""
    return tuple(sorted(str(name) for name in values))


__all__ = [
    "ExecutionOutcome",
    "ProviderCapability",
    "ProviderError",
    "ProviderExecutionFailure",
    "ProviderExecutionReceipt",
    "ProviderIdentity",
    "ProviderReplayReport",
    "ProviderRequest",
    "ProviderResult",
    "ProviderUnavailable",
    "ScientificProvider",
    "canonical_qoi_names",
    "digest_of",
    "replay_provider_request",
    "unavailable_result",
]
