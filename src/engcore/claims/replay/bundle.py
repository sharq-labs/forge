"""Portable deterministic assessment bundle: verify it without physics, replay it with physics.

A bundle carries everything needed to re-check one assessed claim:

* the assessment record itself -- claim, plan (exact case, models, solvers,
  charter), credibility report, evidence, uncertainty studies, validation,
  external evidence, decision context and policy, verdict, gaps;
* the declaration of the capability that ran (so a changed registry is
  *reported*, not mistaken for tampering);
* the trusted-external registry the record was judged under;
* the environment it was produced in (for the reader; never used to decide);
* a digest over all of it.

:func:`verify_bundle` executes nothing. It checks the digest, then re-derives
the whole record against the current registry (:func:`verify_assessment`),
which re-reads the report and re-derives every verdict, level, estimate,
standing, gap and recommendation. :func:`replay_bundle` executes the claim
again and compares: identities must be identical, numbers equal within the
declared tolerances, verdicts identical.

A view, never a source: like ``engcore.mcp.bundle``, nothing in the runtime
imports this module (``tests/mcp/test_bundle.py`` pins it), so a bundle can be
checked against the runtime but can never influence what the runtime concludes.
"""

from __future__ import annotations

import json
import math
import platform
import subprocess
from importlib import metadata as importlib_metadata
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ...scientific.serialization import schema_string
from ...sria.evidence import SourceClass
from .._records import canonical_json, tagged_digest
from ..capabilities import CapabilityDeclaration, CapabilityRegistry
from ..errors import ClaimLayerError
from ..external_evidence import TrustedExternalRegistry, TrustedPin, read_external_record

BUNDLE_SCHEMA = schema_string("claim_assessment_bundle")
ENVIRONMENT_SCHEMA = schema_string("claim_replay_environment")
_TAG = "crafty.claims.bundle/1"
_ENVIRONMENT_TAG = "crafty.claims.environment/1"


class BundleError(ClaimLayerError):
    """A bundle is not readable."""


class BundleStatus(str, Enum):
    VERIFIED = "verified"
    TAMPERED = "tampered"
    REGISTRY_CHANGED = "registry_changed"
    NOT_REPRODUCIBLE = "not_reproducible"


def _distribution_version(name: str) -> str:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return "not-installed"


def _git_identity() -> dict[str, Any]:
    """Best-effort source identity. Missing Git metadata never becomes authority."""

    def run(*args: str) -> str | None:
        try:
            proc = subprocess.run(
                ["git", *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return proc.stdout.strip() if proc.returncode == 0 else None

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {
        "commit": commit or "unknown",
        "dirty": None if status is None else bool(status),
    }


def _environment() -> dict[str, Any]:
    """Reproducibility metadata only; it never grants scientific standing."""

    import engcore

    body: dict[str, Any] = {
        "schema": ENVIRONMENT_SCHEMA,
        "engcore": str(getattr(engcore, "__version__", "unknown")),
        "distribution": {
            "crafty": _distribution_version("crafty"),
            "numpy": _distribution_version("numpy"),
            "scipy": _distribution_version("scipy"),
            "pint": _distribution_version("pint"),
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "git": _git_identity(),
    }
    return {**body, "fingerprint": tagged_digest(_ENVIRONMENT_TAG, body)}


def make_bundle(assessment: Any, registry: CapabilityRegistry, *, trust: TrustedExternalRegistry | None = None) -> dict[str, Any]:
    """The bundle of one assessment. ``trust`` must be the registry it was assessed under (default: production)."""
    from ..external_evidence import PRODUCTION_EXTERNAL_REGISTRY

    trust = PRODUCTION_EXTERNAL_REGISTRY if trust is None else trust
    record = assessment.to_dict()
    if record.get("external_trust_registry") != trust.digest:
        raise BundleError("the trust registry given is not the one the assessment was judged under")
    capability = None
    if assessment.plan is not None:
        capability = registry.get(assessment.plan.capability_id).to_dict()
    body = {
        "schema": BUNDLE_SCHEMA,
        "record": record,
        "capability": capability,
        "registry_digest": registry.digest,
        "trust_pins": [p.to_dict() for p in trust.pins],
        "environment": _environment(),
    }
    return {**body, "bundle_digest": tagged_digest(_TAG, body)}


def _trust_of(bundle: Mapping[str, Any]) -> TrustedExternalRegistry:
    return TrustedExternalRegistry(tuple(
        TrustedPin(p["record_digest"], SourceClass(p["source_class"]), p["curator"], p["rationale"]) for p in bundle.get("trust_pins", [])
    ))


@dataclass(frozen=True)
class BundleCheck:
    status: BundleStatus
    problems: tuple[str, ...]
    verdict: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "problems": list(self.problems), "verdict": self.verdict}


def verify_bundle(bundle: Mapping[str, Any], registry: CapabilityRegistry) -> BundleCheck:
    """Re-verify a bundle without executing physics."""
    from ..assessment import AssessmentForgeryError, verify_assessment

    try:
        body = {k: v for k, v in bundle.items() if k != "bundle_digest"}
        if bundle.get("schema") != BUNDLE_SCHEMA:
            return BundleCheck(BundleStatus.TAMPERED, (f"not a bundle: schema {bundle.get('schema')!r}",))
        if tagged_digest(_TAG, body) != bundle.get("bundle_digest"):
            return BundleCheck(BundleStatus.TAMPERED, ("the bundle digest does not match its content",))
        record = bundle["record"]
        trust = _trust_of(bundle)
        if record.get("external_trust_registry") != trust.digest:
            return BundleCheck(BundleStatus.TAMPERED, ("the carried trust pins are not the registry the record was judged under",))
        capability = bundle.get("capability")
        if capability is not None:
            carried = CapabilityDeclaration.from_dict(capability)
            plan_cap = record["plan"]["content"]["capability"]
            if carried.digest != plan_cap["digest"]:
                return BundleCheck(BundleStatus.TAMPERED, ("the carried capability is not the one the plan ran",))
            if carried.capability_id not in registry or registry.get(carried.capability_id).digest != carried.digest:
                return BundleCheck(BundleStatus.REGISTRY_CHANGED, (
                    f"{carried.capability_id} is no longer registered with digest {carried.digest[:16]}; the bundle is intact but "
                    f"cannot be re-derived against today's registry (see impact analysis)",
                ), record.get("verdict"))
        rebuilt = verify_assessment(record, registry, trust=trust)
    except AssessmentForgeryError as exc:
        return BundleCheck(BundleStatus.TAMPERED, (str(exc),))
    except (KeyError, TypeError, ValueError, ClaimLayerError) as exc:
        return BundleCheck(BundleStatus.TAMPERED, (f"unreadable: {type(exc).__name__}: {exc}",))
    return BundleCheck(BundleStatus.VERIFIED, (), rebuilt.verdict.value)


@dataclass(frozen=True)
class ReplayTolerance:
    """How far a replayed number may move and still be the same result. Declared by the replayer."""

    relative: float = 0.0
    absolute: float = 0.0

    def same(self, a: float, b: float) -> bool:
        return math.isclose(a, b, rel_tol=self.relative, abs_tol=self.absolute)


def _numbers(node: Any, prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(node, Mapping):
        for k, v in node.items():
            out.update(_numbers(v, f"{prefix}/{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.update(_numbers(v, f"{prefix}/{i}"))
    elif isinstance(node, float):
        out[prefix] = node
    return out


_IDENTITY_FIELDS = (
    ("/compilation/claim_identity", ("compilation", "claim_identity")),
    ("/plan/content/core_digest", ("plan", "content", "core_digest")),
    ("/plan/content/run_id", ("plan", "content", "run_id")),
    ("/plan/content/capability", ("plan", "content", "capability")),
    ("/plan/content/models", ("plan", "content", "models")),
    ("/plan/content/solvers", ("plan", "content", "solvers")),
    ("/plan/content/case_digest", ("plan", "content", "case_digest")),
    ("/plan/content/decision", ("plan", "content", "decision")),
    ("/verdict", ("verdict",)),
    ("/credibility/verdict", ("credibility", "verdict")),
    ("/validation/attained", ("validation", "attained")),
    ("/verification/attained", ("verification", "attained")),
    ("/assurance/verdict", ("assurance", "verdict")),
    ("/comparison/outcome", ("comparison", "outcome")),
    ("/uncertainty/channels", ("uncertainty", "channels")),
)


def _at(record: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = record
    for key in path:
        if node is None:
            return None
        node = node.get(key)
    return node


@dataclass(frozen=True)
class ReplayResult:
    status: BundleStatus
    differences: tuple[str, ...]
    compared_numbers: int

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "differences": list(self.differences), "compared_numbers": self.compared_numbers}


def replay_bundle(bundle: Mapping[str, Any], registry: CapabilityRegistry, *, tolerance: ReplayTolerance = ReplayTolerance()) -> ReplayResult:
    """Execute the bundled claim again and compare identities exactly and numbers within ``tolerance``."""
    from ..assessment import assess_claim

    check = verify_bundle(bundle, registry)
    if check.status is not BundleStatus.VERIFIED:
        return ReplayResult(check.status, check.problems, 0)
    record = bundle["record"]
    external = tuple(
        read_external_record(a["record"]) for a in record.get("external_evidence_assessments", [])
        if a.get("source_class") in ("measurement", "literature")
    )
    replayed = assess_claim(record["claim"], registry, external=external, trust=_trust_of(bundle)).to_dict()
    differences = []
    for label, path in _IDENTITY_FIELDS:
        if canonical_json(_at(record, path)) != canonical_json(_at(replayed, path)):
            differences.append(f"{label}: {_at(record, path)!r} -> {_at(replayed, path)!r}")
    # Numbers: the reported values, the study estimates and the comparison band.
    compared = 0
    for section in ("result", "uncertainty_studies", "comparison"):
        before, after = _numbers(record.get(section), f"/{section}"), _numbers(replayed.get(section), f"/{section}")
        if set(before) != set(after):
            differences.append(f"/{section}: the replay carries different numeric fields")
            continue
        for key in sorted(before):
            compared += 1
            if not tolerance.same(before[key], after[key]):
                differences.append(f"{key}: {before[key]!r} -> {after[key]!r}")
    return ReplayResult(BundleStatus.VERIFIED if not differences else BundleStatus.NOT_REPRODUCIBLE, tuple(differences), compared)


def bundle_to_json(bundle: Mapping[str, Any]) -> str:
    return canonical_json(bundle)


def bundle_from_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise BundleError(f"not a bundle: {exc}") from exc


__all__ = [
    "BUNDLE_SCHEMA",
    "BundleCheck",
    "BundleError",
    "BundleStatus",
    "ENVIRONMENT_SCHEMA",
    "ReplayResult",
    "ReplayTolerance",
    "bundle_from_json",
    "bundle_to_json",
    "make_bundle",
    "replay_bundle",
    "verify_bundle",
]
