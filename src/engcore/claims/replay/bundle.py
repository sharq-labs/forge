"""Portable deterministic assessment bundle: verify it without physics, replay it with physics.

A bundle carries everything needed to re-check one assessed claim:

* the assessment record itself -- claim, plan (exact case, models, solvers,
  charter), credibility report, evidence, uncertainty studies, validation,
  external evidence, decision context and policy, verdict, gaps;
* the declaration of the capability that ran (so a changed registry is
  *reported*, not mistaken for tampering);
* the trusted-external registry the record was judged under;
* the environment it was produced in (never grants scientific standing, but exact replay requires it);
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

import hashlib
import json
import math
import platform
import re
import subprocess
from pathlib import Path
from importlib import metadata as importlib_metadata
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ...scientific.serialization import schema_string
from ...sria.evidence import SourceClass
from .._records import canonical_json, tagged_digest
from ..capabilities import CapabilityDeclaration, CapabilityRegistry
from ..errors import ClaimLayerError
from ..external_evidence import (
    PRODUCTION_EXTERNAL_REGISTRY,
    TrustedExternalRegistry,
    TrustedPin,
    read_external_record,
)
from ..measurement_dataset import DatasetObservation
from ...uq.model_form.qualification import ProducerQualification

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


def _git_bytes(*args: str) -> bytes | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _digest_bytes(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def _untracked_manifest(root: Path | None, names: bytes | None) -> bytes | None:
    if root is None or names is None:
        return None
    rows: list[bytes] = []
    for raw in sorted(name for name in names.split(b"\0") if name):
        relative = raw.decode("utf-8", errors="surrogateescape")
        path = root / relative
        try:
            if path.is_symlink():
                content_digest = hashlib.sha256(str(path.readlink()).encode("utf-8", errors="surrogateescape")).hexdigest()
            elif path.is_file():
                content_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                content_digest = "non-file"
        except OSError:
            content_digest = "unreadable"
        rows.append(raw + b"\0" + content_digest.encode("ascii"))
    return b"\n".join(rows)


def _git_identity() -> dict[str, Any]:
    """Best-effort source identity including the exact dirty-tree content."""

    commit_raw = _git_bytes("rev-parse", "HEAD")
    status = _git_bytes("status", "--porcelain")
    diff = _git_bytes("diff", "--binary", "HEAD")
    root_raw = _git_bytes("rev-parse", "--show-toplevel")
    untracked = _git_bytes("ls-files", "--others", "--exclude-standard", "-z")
    root = None
    if root_raw:
        root = Path(root_raw.decode("utf-8", errors="surrogateescape").strip())
    manifest = _untracked_manifest(root, untracked)
    return {
        "commit": "unknown" if not commit_raw else commit_raw.decode("ascii", errors="replace").strip(),
        "dirty": None if status is None else bool(status),
        "tracked_diff_digest": _digest_bytes(diff),
        "untracked_manifest_digest": _digest_bytes(manifest),
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


def _environment_problem(environment: Any) -> str | None:
    if not isinstance(environment, Mapping):
        return "bundle environment is not a mapping"
    if environment.get("schema") != ENVIRONMENT_SCHEMA:
        return f"bundle environment uses unexpected schema {environment.get('schema')!r}"
    body = {k: v for k, v in environment.items() if k != "fingerprint"}
    if tagged_digest(_ENVIRONMENT_TAG, body) != environment.get("fingerprint"):
        return "bundle environment fingerprint does not match its content"
    return None


def _environment_replay_problem(environment: Mapping[str, Any]) -> str | None:
    git = environment.get("git")
    if not isinstance(git, Mapping):
        return "source-control identity is absent from the replay environment"
    commit = str(git.get("commit") or "").strip().lower()
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
        return "source-control commit identity is unavailable"
    if not isinstance(git.get("dirty"), bool):
        return "source-control dirty-tree state is unavailable"
    for field in ("tracked_diff_digest", "untracked_manifest_digest"):
        value = str(git.get(field) or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            return f"source-control {field} is unavailable"
    return None


def verify_bundle(
    bundle: Mapping[str, Any],
    registry: CapabilityRegistry,
    *,
    trust: TrustedExternalRegistry | None = None,
) -> BundleCheck:
    """Re-verify a bundle without executing physics.

    The trust registry carried by the bundle is evidence of what the historical
    assessment used, never authority to trust itself.  It must match the
    caller's authoritative registry (production by default).
    """
    trust = PRODUCTION_EXTERNAL_REGISTRY if trust is None else trust
    from ..assessment import AssessmentForgeryError, verify_assessment

    try:
        body = {k: v for k, v in bundle.items() if k != "bundle_digest"}
        if bundle.get("schema") != BUNDLE_SCHEMA:
            return BundleCheck(BundleStatus.TAMPERED, (f"not a bundle: schema {bundle.get('schema')!r}",))
        if tagged_digest(_TAG, body) != bundle.get("bundle_digest"):
            return BundleCheck(BundleStatus.TAMPERED, ("the bundle digest does not match its content",))
        environment_problem = _environment_problem(bundle.get("environment"))
        if environment_problem is not None:
            return BundleCheck(BundleStatus.TAMPERED, (environment_problem,))
        record = bundle["record"]
        carried_trust = _trust_of(bundle)
        if record.get("external_trust_registry") != carried_trust.digest:
            return BundleCheck(BundleStatus.TAMPERED, ("the carried trust pins are not the registry the record was judged under",))
        if carried_trust.digest != trust.digest:
            return BundleCheck(
                BundleStatus.REGISTRY_CHANGED,
                (
                    "the bundle was judged under a different external trust registry; "
                    "carried trust pins cannot authorize themselves",
                ),
                record.get("verdict"),
            )
        if bundle.get("registry_digest") != registry.digest:
            return BundleCheck(
                BundleStatus.REGISTRY_CHANGED,
                (
                    "the capability registry digest differs from the registry that produced the bundle",
                ),
                record.get("verdict"),
            )
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
    """How far a replayed result number may move and still be the same result."""

    relative: float = 0.0
    absolute: float = 0.0

    def __post_init__(self) -> None:
        relative = float(self.relative)
        absolute = float(self.absolute)
        if (
            not math.isfinite(relative)
            or not math.isfinite(absolute)
            or relative < 0.0
            or absolute < 0.0
        ):
            raise ValueError("replay tolerances must be finite and non-negative")
        object.__setattr__(self, "relative", relative)
        object.__setattr__(self, "absolute", absolute)

    def same(self, a: float, b: float) -> bool:
        return math.isclose(a, b, rel_tol=self.relative, abs_tol=self.absolute)


def _study_replay_inputs(
    record: Mapping[str, Any],
) -> tuple[tuple[DatasetObservation, ...], ProducerQualification | None, tuple[str, ...]]:
    observations: list[DatasetObservation] = []
    observation_digests: set[str] = set()
    qualification: ProducerQualification | None = None
    problems: list[str] = []
    for index, study in enumerate(record.get("uncertainty_studies") or ()):
        if not isinstance(study, Mapping):
            problems.append(f"/uncertainty_studies/{index}: study is not a mapping")
            continue
        for raw in study.get("source_observations") or ():
            try:
                observation = DatasetObservation.from_dict(raw)
            except Exception as exc:
                problems.append(
                    f"/uncertainty_studies/{index}/source_observations: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            if observation.digest not in observation_digests:
                observations.append(observation)
                observation_digests.add(observation.digest)
        raw_qualification = study.get("qualification")
        if raw_qualification is None:
            continue
        try:
            candidate = ProducerQualification.from_dict(raw_qualification)
        except Exception as exc:
            problems.append(
                f"/uncertainty_studies/{index}/qualification: "
                f"{type(exc).__name__}: {exc}"
            )
            continue
        if qualification is not None and candidate.digest != qualification.digest:
            problems.append(
                "uncertainty studies carry more than one model-form producer qualification"
            )
        else:
            qualification = candidate
    return (
        tuple(observations),
        qualification,
        tuple(problems),
    )


def _tolerates_numeric(path: str) -> bool:
    parts = tuple(part for part in path.split("/") if part)
    if parts[:2] == ("result", "value"):
        return True
    if parts[:1] == ("comparison",):
        return True
    if parts[:3] in {
        ("credibility", "report", "values"),
        ("credibility", "report", "uncertainty"),
    }:
        return True
    if parts[:1] == ("uncertainty_studies",):
        return any(
            part in {
                "runs",
                "pairs",
                "estimate",
                "uncertainty",
                "discrepancy",
                "model_form_estimate",
            }
            for part in parts[2:]
        )
    return False


def _tolerance_derived_identity(
    path: str,
    before: Any,
    after: Any,
    tolerance: ReplayTolerance,
) -> bool:
    """Whether an identity is deterministically downstream of tolerated numerics.

    Replay tolerance applies to scientific result/estimate leaves, never to
    authority, configuration, input, model, solver, capability or trust
    identities. Some public fields are content-addresses of those tolerated
    leaves, though. Requiring those hashes to stay byte-identical would make
    a non-zero numeric tolerance impossible to use.

    The whitelist is intentionally structural and value-aware. It recognizes
    only SRIA evidence content/record hashes, refinement-run report digests,
    and refinement-study source labels emitted by numerical UQ.
    """
    if tolerance.relative == 0.0 and tolerance.absolute == 0.0:
        return False

    parts = tuple(part for part in path.split("/") if part)
    if parts in {
        ("evidence", "content_hash"),
        ("evidence", "record_hash"),
    }:
        return (
            isinstance(before, str)
            and isinstance(after, str)
            and re.fullmatch(r"[0-9a-f]{64}", before) is not None
            and re.fullmatch(r"[0-9a-f]{64}", after) is not None
        )

    if (
        parts[:1] == ("uncertainty_studies",)
        and parts[-1:] == ("report_digest",)
    ):
        return (
            isinstance(before, str)
            and isinstance(after, str)
            and re.fullmatch(r"[0-9a-f]{64}", before) is not None
            and re.fullmatch(r"[0-9a-f]{64}", after) is not None
        )

    if parts[-1:] == ("source",):
        return (
            isinstance(before, str)
            and isinstance(after, str)
            and before.startswith("refinement_study:")
            and after.startswith("refinement_study:")
        )

    return False

def _compare_replay_nodes(
    before: Any,
    after: Any,
    tolerance: ReplayTolerance,
    *,
    path: str = "",
    differences: list[str] | None = None,
    tolerated_numeric_drift: list[str] | None = None,
    derived_identity_drift: list[str] | None = None,
) -> int:
    """Compare the complete public assessment record.

    Configuration, inputs, authoritative identities, trust, checks and policy
    are exact. The declared tolerance is used only for scientific
    result/estimate leaves plus the narrowly recognized content-addressed
    identities derived from those leaves; it can never blur a changed
    threshold, input, model, solver, capability or trust decision.
    """
    differences = [] if differences is None else differences
    tolerated_numeric_drift = (
        [] if tolerated_numeric_drift is None else tolerated_numeric_drift
    )
    derived_identity_drift = (
        [] if derived_identity_drift is None else derived_identity_drift
    )
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        before_keys, after_keys = set(before), set(after)
        missing = sorted(before_keys - after_keys)
        extra = sorted(after_keys - before_keys)
        if missing:
            differences.append(f"{path or '/'}: missing fields {missing}")
        if extra:
            differences.append(f"{path or '/'}: unexpected fields {extra}")
        compared = 0
        for key in sorted(before_keys & after_keys):
            compared += _compare_replay_nodes(
                before[key],
                after[key],
                tolerance,
                path=f"{path}/{key}",
                differences=differences,
                tolerated_numeric_drift=tolerated_numeric_drift,
                derived_identity_drift=derived_identity_drift,
            )
        return compared
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            differences.append(
                f"{path or '/'}: list length {len(before)} -> {len(after)}"
            )
        compared = 0
        for index, (left, right) in enumerate(zip(before, after)):
            compared += _compare_replay_nodes(
                left,
                right,
                tolerance,
                path=f"{path}/{index}",
                differences=differences,
                tolerated_numeric_drift=tolerated_numeric_drift,
                derived_identity_drift=derived_identity_drift,
            )
        return compared
    if isinstance(before, bool) or isinstance(after, bool):
        if type(before) is not type(after) or before != after:
            differences.append(f"{path or '/'}: {before!r} -> {after!r}")
        return 0
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        if _tolerates_numeric(path):
            if not tolerance.same(float(before), float(after)):
                differences.append(f"{path or '/'}: {before!r} -> {after!r}")
            elif float(before) != float(after):
                tolerated_numeric_drift.append(path or "/")
        elif type(before) is not type(after) or before != after:
            differences.append(f"{path or '/'}: {before!r} -> {after!r}")
        return 1
    if type(before) is not type(after) or before != after:
        change = f"{path or '/'}: {before!r} -> {after!r}"
        if _tolerance_derived_identity(path, before, after, tolerance):
            derived_identity_drift.append(change)
        else:
            differences.append(change)
    return 0


@dataclass(frozen=True)
class ReplayResult:
    status: BundleStatus
    differences: tuple[str, ...]
    compared_numbers: int

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "differences": list(self.differences), "compared_numbers": self.compared_numbers}


def replay_bundle(
    bundle: Mapping[str, Any],
    registry: CapabilityRegistry,
    *,
    tolerance: ReplayTolerance = ReplayTolerance(),
    trust: TrustedExternalRegistry | None = None,
    require_same_environment: bool = True,
) -> ReplayResult:
    """Execute the bundled claim again and compare the complete assessment record.

    Exact replay is fail-closed on the authoritative trust registry, registry
    identity and (by default) runtime/source environment.  Empirical replicate
    observations and the reviewed model-form qualification are reconstructed
    from the study records and supplied to the fresh assessment rather than
    silently disappearing during replay.
    """
    trust = PRODUCTION_EXTERNAL_REGISTRY if trust is None else trust
    # Imported lazily so the replay view can call the assessment runtime
    # without creating a module-import cycle.
    from ..assessment import assess_claim

    check = verify_bundle(bundle, registry, trust=trust)
    if check.status is not BundleStatus.VERIFIED:
        return ReplayResult(check.status, check.problems, 0)
    if require_same_environment:
        current_environment = _environment()
        stored_environment = bundle["environment"]
        for label, environment in (
            ("stored", stored_environment),
            ("current", current_environment),
        ):
            problem = _environment_replay_problem(environment)
            if problem is not None:
                return ReplayResult(
                    BundleStatus.NOT_REPRODUCIBLE,
                    (f"{label} replay environment: {problem}",),
                    0,
                )
        if stored_environment.get("fingerprint") != current_environment.get("fingerprint"):
            return ReplayResult(
                BundleStatus.NOT_REPRODUCIBLE,
                (
                    "runtime/source environment differs from the bundle: "
                    f"{stored_environment.get('fingerprint')} -> "
                    f"{current_environment.get('fingerprint')}",
                ),
                0,
            )
    record = bundle["record"]
    external = tuple(
        read_external_record(a["record"])
        for a in record.get("external_evidence_assessments", [])
        if a.get("source_class") in ("measurement", "literature")
    )
    empirical, qualification, study_problems = _study_replay_inputs(record)
    if study_problems:
        return ReplayResult(BundleStatus.NOT_REPRODUCIBLE, study_problems, 0)
    replayed = assess_claim(
        record["claim"],
        registry,
        external=external,
        empirical_observations=empirical,
        model_form_qualification=qualification,
        trust=trust,
    ).to_dict()
    differences: list[str] = []
    tolerated_numeric_drift: list[str] = []
    derived_identity_drift: list[str] = []
    compared = _compare_replay_nodes(
        record,
        replayed,
        tolerance,
        differences=differences,
        tolerated_numeric_drift=tolerated_numeric_drift,
        derived_identity_drift=derived_identity_drift,
    )
    # Content-addressed identities may move only as a consequence of an
    # actually observed numeric drift that the caller's tolerance accepted.
    # A non-zero tolerance by itself is not permission to ignore identity
    # changes in an otherwise byte-identical scientific result.
    if derived_identity_drift and not tolerated_numeric_drift:
        differences.extend(derived_identity_drift)
    return ReplayResult(
        BundleStatus.VERIFIED if not differences else BundleStatus.NOT_REPRODUCIBLE,
        tuple(differences),
        compared,
    )


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
