"""M4.2 — executable dependency identity and the two replay modes.

M4.1 pinned *which model* a decision claimed to use. It did not stop a frozen
snapshot from being re-scored against whatever the live supplier happened to
hold. Measured before this module existed: the same snapshot digest, the same
candidates and the same policy produced a cost of 4.0 and then 400.0 after a
refit — silently, with nothing in the output indicating that the world had
moved. That is the defect this module closes.

The invariant now enforced:

    A frozen decision snapshot never silently consumes a newer or different
    computational model. Either every pinned executable dependency resolves
    exactly and the decision re-executes deterministically, or executable
    replay is refused.

Two modes, deliberately named apart because they promise different things:

``AUDIT_REPLAY``
    Returns the stored recommendation and its recorded basis. It recomputes
    **nothing**. This is durable indefinitely and is what makes a past decision
    reviewable.

``EXECUTABLE_REPLAY``
    Recomputes only when the current dependency manifest matches the pinned one
    exactly. Otherwise it returns ``REPLAY_DEPENDENCY_UNAVAILABLE`` naming the
    dependencies that moved. It never falls back to current models.

**Why a version label is not enough.** Two fitted estimators can share model
type, version string and training-dataset id while holding different fitted
parameters — a refit on different rows under the same dataset label is exactly
that. So a dependency is identified by a ``state_digest`` computed over the
*decision-relevant fitted state*, not over a label and not over anything
process-local. No memory addresses, no ``id()``, nothing that changes between
runs of identical work.

**Unpinnable dependencies are declared, not faked.** A terminal utility is a
live callable; it cannot be serialized and restored, and inventing a hash for
it would manufacture false confidence. Such a dependency is marked
``restorable=False``, which makes executable replay unavailable while leaving
audit replay fully intact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from ...scientific.serialization import require_schema, schema_string

DEPENDENCY_SCHEMA = schema_string("sria_dependency_identity")
MANIFEST_SCHEMA = schema_string("sria_execution_dependency_manifest")

#: Marker used when a dependency's fitted state cannot be summarised.
UNPINNABLE = ""


def canonical_digest(payload: Any) -> str:
    """SHA-256 over canonical JSON. Deterministic across processes."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class DependencyKind(str, Enum):
    COST_MODEL = "cost_model"
    FAILURE_SOURCE = "failure_source"
    OUTCOME_MODEL = "outcome_model"
    TERMINAL_UTILITY = "terminal_utility"
    COST_TRADEOFF = "cost_tradeoff"
    UTILITY_POLICY = "utility_policy"
    UTILITY_ENGINE = "utility_engine"


@dataclass(frozen=True)
class DependencyIdentity:
    """Identity of one executable dependency of a decision."""

    dependency_id: str
    kind: DependencyKind
    version: str = ""
    dataset_id: str = ""
    #: Digest over the decision-relevant fitted state. Empty means the state
    #: could not be summarised — the dependency is then unpinnable.
    state_digest: str = UNPINNABLE
    #: Whether this dependency could be restored for a re-execution at all.
    restorable: bool = True
    detail: str = ""

    def __post_init__(self) -> None:
        if not str(self.dependency_id).strip():
            raise ValueError("dependency identity requires a dependency_id")
        object.__setattr__(self, "kind", DependencyKind(self.kind))
        if not isinstance(self.restorable, bool):
            raise ValueError("restorable must be an explicit bool")

    @property
    def is_pinned(self) -> bool:
        """Pinned means: restorable *and* its fitted state is identified."""
        return self.restorable and bool(self.state_digest)

    @property
    def key(self) -> str:
        return f"{self.kind.value}:{self.dependency_id}"

    def matches(self, other: "DependencyIdentity") -> bool:
        return (
            self.key == other.key
            and self.version == other.version
            and self.dataset_id == other.dataset_id
            and self.state_digest == other.state_digest
            and self.state_digest != UNPINNABLE
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DEPENDENCY_SCHEMA,
            "dependency_id": self.dependency_id,
            "kind": self.kind.value,
            "version": self.version,
            "dataset_id": self.dataset_id,
            "state_digest": self.state_digest,
            "restorable": self.restorable,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DependencyIdentity":
        require_schema(payload, DEPENDENCY_SCHEMA)
        return cls(
            dependency_id=payload["dependency_id"],
            kind=DependencyKind(payload["kind"]),
            version=payload.get("version", ""),
            dataset_id=payload.get("dataset_id", ""),
            state_digest=payload.get("state_digest", UNPINNABLE),
            restorable=bool(payload.get("restorable", True)),
            detail=payload.get("detail", ""),
        )


@runtime_checkable
class HasDependencyIdentity(Protocol):
    """Anything that can name its own executable state."""

    def dependency_identity(self) -> DependencyIdentity:
        ...


def identify(
    component: Any, *, kind: DependencyKind, fallback_id: str
) -> DependencyIdentity:
    """Ask a component for its identity, or declare it unpinnable.

    A component that cannot describe its fitted state does not get a
    manufactured digest — it gets ``restorable=False``, which fails executable
    replay closed.
    """
    if isinstance(component, HasDependencyIdentity):
        return component.dependency_identity()
    return DependencyIdentity(
        dependency_id=getattr(component, "__class__", type(component)).__name__
        or fallback_id,
        kind=kind,
        restorable=False,
        detail=(
            "component does not expose dependency_identity(); its fitted state "
            "cannot be pinned, so executable replay is unavailable"
        ),
    )


def cost_model_state_digest(model: Any) -> str:
    """Digest the fitted state of an M2 cost model.

    Covers every fitted cell — key, level, median, MAD, support and censored
    count — so a refit that changes any prediction changes this digest. Built
    from the model's public accessors, so M2 stays frozen.
    """
    cells = getattr(model, "cells", None)
    if not callable(cells):
        return UNPINNABLE
    try:
        state = [
            {
                "key": c.key,
                "level": c.level,
                "median_log10": c.median_log10,
                "mad_log10": c.mad_log10,
                "support": c.support,
                "censored": c.censored,
            }
            for c in cells()
        ]
    except Exception:  # a model that cannot describe itself is unpinnable
        return UNPINNABLE
    if not state:
        return UNPINNABLE
    return canonical_digest(
        {"model_version": getattr(model, "model_version", ""), "cells": state}
    )


@dataclass(frozen=True)
class ExecutionDependencyManifest:
    """Everything a decision would need to re-execute deterministically."""

    dependencies: tuple[DependencyIdentity, ...] = ()
    snapshot_digest: str = ""
    charter_version: str = ""
    candidate_set_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        keys = [d.key for d in self.dependencies]
        duplicates = {k for k in keys if keys.count(k) > 1}
        if duplicates:
            raise ValueError(f"duplicate dependency keys: {sorted(duplicates)}")

    @property
    def is_executable(self) -> bool:
        """True only when every dependency is pinned to a fitted state."""
        return bool(self.dependencies) and all(d.is_pinned for d in self.dependencies)

    @property
    def unpinnable(self) -> tuple[str, ...]:
        return tuple(sorted(d.key for d in self.dependencies if not d.is_pinned))

    @property
    def manifest_digest(self) -> str:
        return canonical_digest(self.to_dict())

    def mismatches(
        self, other: "ExecutionDependencyManifest"
    ) -> tuple[str, ...]:
        """Which dependencies differ from a stored manifest."""
        out: list[str] = []
        mine = {d.key: d for d in self.dependencies}
        theirs = {d.key: d for d in other.dependencies}
        for key in sorted(set(mine) | set(theirs)):
            a, b = mine.get(key), theirs.get(key)
            if a is None:
                out.append(f"{key}: absent in stored manifest")
            elif b is None:
                out.append(f"{key}: no longer present")
            elif not a.matches(b):
                if not a.is_pinned or not b.is_pinned:
                    out.append(f"{key}: fitted state is not pinnable")
                else:
                    out.append(
                        f"{key}: state {b.state_digest[:12]}… -> "
                        f"{a.state_digest[:12]}…"
                    )
        if self.snapshot_digest != other.snapshot_digest:
            out.append("belief snapshot differs")
        if self.charter_version != other.charter_version:
            out.append("campaign charter version differs")
        if self.candidate_set_digest != other.candidate_set_digest:
            out.append("candidate set differs")
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "dependencies": [
                d.to_dict() for d in sorted(self.dependencies, key=lambda d: d.key)
            ],
            "snapshot_digest": self.snapshot_digest,
            "charter_version": self.charter_version,
            "candidate_set_digest": self.candidate_set_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionDependencyManifest":
        require_schema(payload, MANIFEST_SCHEMA)
        return cls(
            dependencies=tuple(
                DependencyIdentity.from_dict(d)
                for d in payload.get("dependencies", ())
            ),
            snapshot_digest=payload.get("snapshot_digest", ""),
            charter_version=payload.get("charter_version", ""),
            candidate_set_digest=payload.get("candidate_set_digest", ""),
        )


#: Fields excluded from a candidate's decision identity, keyed by the schema
#: they appear in. These are narrative only: nothing in scoring, feasibility,
#: cost aggregation or VoI reads them, so two candidates differing only in this
#: prose would score identically and *are* the same decision.
#:
#: This is deliberately a deny-list rather than an allow-list. A field added to
#: an action or proposal later is included in the identity automatically, so
#: forgetting to update this table makes the digest *over*-sensitive — a
#: spurious replay refusal, which is safe. An allow-list would fail the other
#: way and silently stop noticing a field that scoring had begun to use.
#:
#: The schema versions are written out rather than imported from the action
#: module for the same reason: if a schema is bumped to /2, this table stops
#: matching, every field is hashed, and the digest becomes conservative until
#: someone re-audits which fields are narrative. Staying in sync automatically
#: would fail silently in the unsafe direction.
NON_DECISION_FIELDS: Mapping[str, tuple[str, ...]] = {
    schema_string("sria_action_proposal", 1): ("rationale",),
    schema_string("sria_composite_action", 1): ("dependence_rationale",),
}


def _strip_narrative(payload: Any) -> Any:
    """Recursively drop deny-listed fields, keyed by each node's schema."""
    if isinstance(payload, Mapping):
        excluded = NON_DECISION_FIELDS.get(str(payload.get("schema", "")), ())
        return {
            key: _strip_narrative(value)
            for key, value in payload.items()
            if key not in excluded
        }
    if isinstance(payload, (list, tuple)):
        return [_strip_narrative(item) for item in payload]
    return payload


def candidate_decision_identity(candidate: Any) -> dict[str, Any]:
    """The decision-relevant content of one candidate.

    Everything scoring can read: action id, executor type, target ref, typed
    parameters, declared costs, context ref and metadata; the proposal's family,
    target, assumptions, required fidelity, expected observable and informative
    failure causes; and for a composite its members *in order*, execution
    order, cost aggregation, declared total, outcome dependence and failure
    dependencies.

    Member order is kept even where the current engine happens to be
    order-insensitive. The two error directions are not symmetric: an identity
    that is too coarse produces a false ``REPRODUCED``, an identity that is too
    fine produces a refusal that a human can inspect. Only the second is
    recoverable, so ordering stays in.
    """
    return _strip_narrative(candidate.to_dict())


def candidate_set_digest(candidates: Sequence[Any]) -> str:
    """Order-independent digest over decision-relevant candidate content.

    The *set* order is irrelevant because ranking is order-independent (ties
    break on action id), so the identities are sorted before hashing. What is
    inside each identity is not: reusing an ``action_id`` for different content
    yields a different digest, which is the property that stops two distinct
    actions from sharing one replay identity.
    """
    identities = [candidate_decision_identity(c) for c in candidates]
    return canonical_digest(
        sorted(identities, key=lambda d: json.dumps(d, sort_keys=True))
    )


# =====================================================================
# Replay
# =====================================================================

class ReplayMode(str, Enum):
    AUDIT_REPLAY = "audit_replay"
    EXECUTABLE_REPLAY = "executable_replay"


class ReplayOutcome(str, Enum):
    #: The stored record was returned. Nothing was recomputed.
    AUDIT_ONLY = "audit_only"
    #: Every dependency resolved and the decision re-executed identically.
    REPRODUCED = "reproduced"
    #: A dependency moved or cannot be restored. Nothing was recomputed.
    REPLAY_DEPENDENCY_UNAVAILABLE = "replay_dependency_unavailable"
    #: Dependencies matched but re-execution produced a different result. A
    #: genuine defect, surfaced rather than smoothed over.
    NONDETERMINISM_DETECTED = "nondeterminism_detected"


@dataclass(frozen=True)
class ReplayResult:
    """The outcome of a replay attempt, and what it is entitled to claim."""

    mode: ReplayMode
    outcome: ReplayOutcome
    stored: Any
    recomputed: Any | None = None
    mismatches: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", ReplayMode(self.mode))
        object.__setattr__(self, "outcome", ReplayOutcome(self.outcome))
        object.__setattr__(self, "mismatches", tuple(self.mismatches))
        if (
            self.outcome is not ReplayOutcome.REPRODUCED
            and self.outcome is not ReplayOutcome.NONDETERMINISM_DETECTED
            and self.recomputed is not None
        ):
            raise ValueError(
                f"{self.outcome.value} must not carry a recomputed result; "
                f"nothing was recomputed"
            )

    @property
    def was_recomputed(self) -> bool:
        """Whether the values came from a fresh execution or from storage."""
        return self.recomputed is not None

    @property
    def scores_are_historical(self) -> bool:
        """True when the returned scores are the stored ones, not fresh."""
        return not self.was_recomputed


def audit_replay(stored: Any) -> ReplayResult:
    """Return the stored decision and its basis. Recomputes nothing.

    Durable regardless of what has happened to the models since — which is the
    point: a past decision must stay reviewable even when it can no longer be
    re-executed.
    """
    return ReplayResult(
        mode=ReplayMode.AUDIT_REPLAY,
        outcome=ReplayOutcome.AUDIT_ONLY,
        stored=stored,
        detail=(
            "historical record returned verbatim; no scientific value was "
            "recomputed"
        ),
    )


def executable_replay(
    stored: Any,
    *,
    evaluator: Any,
    candidates: Sequence[Any],
    snapshot: Any,
    objective: Any,
    budget: Any = None,
    charter_version: str = "",
) -> ReplayResult:
    """Re-execute only if every pinned dependency resolves exactly."""
    stored_manifest = getattr(stored, "dependency_manifest", None)
    if stored_manifest is None:
        return ReplayResult(
            mode=ReplayMode.EXECUTABLE_REPLAY,
            outcome=ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE,
            stored=stored,
            detail=(
                "the stored recommendation carries no dependency manifest, so "
                "there is nothing to verify against"
            ),
        )

    current = evaluator.build_manifest(
        candidates=candidates,
        snapshot=snapshot,
        objective=objective,
        charter_version=charter_version or stored_manifest.charter_version,
    )

    if not current.is_executable:
        return ReplayResult(
            mode=ReplayMode.EXECUTABLE_REPLAY,
            outcome=ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE,
            stored=stored,
            mismatches=current.unpinnable,
            detail=(
                f"dependencies {list(current.unpinnable)} cannot be pinned to a "
                f"fitted state; executable replay is unavailable. Audit replay "
                f"remains available."
            ),
        )

    differences = current.mismatches(stored_manifest)
    if differences:
        # The whole point: no silent fallback to the current model.
        return ReplayResult(
            mode=ReplayMode.EXECUTABLE_REPLAY,
            outcome=ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE,
            stored=stored,
            mismatches=differences,
            detail=(
                "one or more executable dependencies changed since the decision "
                "was recorded; refusing to recompute against different models"
            ),
        )

    recomputed = evaluator.evaluate(
        recommendation_id=stored.recommendation_id,
        candidates=candidates,
        snapshot=snapshot,
        objective=objective,
        budget=budget,
        decided_at=stored.decided_at,
        charter_version=charter_version or stored_manifest.charter_version,
    )
    if _decision_equal(stored, recomputed):
        return ReplayResult(
            mode=ReplayMode.EXECUTABLE_REPLAY,
            outcome=ReplayOutcome.REPRODUCED,
            stored=stored,
            recomputed=recomputed,
            detail="all pinned dependencies resolved; result reproduced exactly",
        )
    return ReplayResult(
        mode=ReplayMode.EXECUTABLE_REPLAY,
        outcome=ReplayOutcome.NONDETERMINISM_DETECTED,
        stored=stored,
        recomputed=recomputed,
        detail=(
            "dependencies matched but the recomputed decision differs; this is "
            "a determinism defect, not an acceptable replay"
        ),
    )


def _decision_equal(a: Any, b: Any) -> bool:
    """Compare two recommendations on everything except the manifest itself."""
    def strip(record: Any) -> dict[str, Any]:
        payload = dict(record.to_dict())
        payload.pop("dependency_manifest", None)
        return payload

    return strip(a) == strip(b)
