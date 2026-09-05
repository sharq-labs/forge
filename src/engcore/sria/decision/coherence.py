"""M4.3 — snapshot/dependency coherence at the *normal* scoring boundary.

M4.2 stopped a frozen decision from being silently re-executed against a moved
model. It guarded the replay boundary only, and the M4.2 report said so
explicitly: ``evaluate()`` remained free to score a stale snapshot against a
newer live model. Measured before this module existed — same snapshot digest,
same candidates, same policy, same charter version, one refit in between:

    R1  cost(good) = 4.0    total = +0.0
    R2  cost(good) = 400.0  total = -396.0

Both were emitted as ordinary, formally valid recommendations. Nothing marked
R2 as resting on a different computational world than the snapshot described.

The invariant this module adds:

    A belief snapshot used for formal decision scoring must be internally
    coherent with the executable dependencies actually used to score it. A
    snapshot that pins a model state may not be scored against a different
    one.

**What a legitimate new decision looks like.** Current belief-calibration
snapshot + current executable dependencies -> new recommendation. That is
always allowed, and :func:`calibration_state_for` makes it a one-liner. What is
not allowed is an old frozen snapshot + arbitrarily newer dependencies ->
"new" recommendation: that record would claim a computational basis that never
jointly existed.

**Why an unpinned snapshot is not a refusal.** A snapshot that declares no
fitted state cannot contradict anything, and refusing it would mean SRIA could
not score at all until every producer of snapshots was rewritten. It is instead
reported as :attr:`CoherenceStatus.UNVERIFIED` and surfaced in the
recommendation's degraded assumptions. Unverified is not silent, and it is not
the same word as coherent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ...scientific.serialization import require_schema, schema_string
from ..signatures import (
    ENVIRONMENT_SIGNATURE_VERSION,
    STRUCTURE_SIGNATURE_VERSION,
)
from .belief_snapshot import BeliefSnapshot
from .replay import DependencyKind, ExecutionDependencyManifest

COHERENCE_SCHEMA = schema_string("sria_coherence_report")
CONFLICT_SCHEMA = schema_string("sria_coherence_conflict")


class CoherenceStatus(str, Enum):
    """Whether the decision basis and the executed dependencies are one world."""

    #: Every dependency that can contribute to a formal score was pinned by the
    #: basis and confirmed against what would run.
    COHERENT = "coherent"
    #: The basis cannot verify at least one dependency that contributes to a
    #: formal score — it was never pinned, or the live provider cannot identify
    #: its own executable semantics. No contradiction was found, but none could
    #: have been: formal decision-theoretic scoring is unavailable (M4.4).
    BASIS_UNVERIFIED = "basis_unverified"
    #: The basis pinned a fitted state; the live dependency holds another.
    STALE_SNAPSHOT = "stale_snapshot"
    #: The basis and the manifest disagree about *which* dependency was used,
    #: or about a version, dataset, signature or charter identity.
    DEPENDENCY_MISMATCH = "dependency_mismatch"


#: Statuses that must never yield an ordinary formal recommendation.
REFUSING_STATUSES = frozenset(
    {
        CoherenceStatus.BASIS_UNVERIFIED,
        CoherenceStatus.STALE_SNAPSHOT,
        CoherenceStatus.DEPENDENCY_MISMATCH,
    }
)

#: Refusals that rest on a concrete contradiction rather than on absence.
CONFLICT_STATUSES = frozenset(
    {CoherenceStatus.STALE_SNAPSHOT, CoherenceStatus.DEPENDENCY_MISMATCH}
)

#: Reserved, deliberately not implemented in V0.1. A campaign may one day want
#: an explicitly PROVISIONAL or EXPLORATORY ranking computed on an unverifiable
#: basis and labelled as such. That is a different product decision with its own
#: semantics, and inventing it here would immediately become the escape hatch
#: that makes BASIS_UNVERIFIED meaningless.
PROVISIONAL_DECISION_MODE_RESERVED = True


@dataclass(frozen=True)
class CoherenceConflict:
    """One concrete contradiction, with both sides shown."""

    field: str
    snapshot_value: str
    executed_value: str
    kind: CoherenceStatus
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", CoherenceStatus(self.kind))
        if self.kind not in CONFLICT_STATUSES:
            raise ValueError(
                f"a conflict must name a contradiction, got {self.kind.value}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONFLICT_SCHEMA,
            "field": self.field,
            "snapshot_value": self.snapshot_value,
            "executed_value": self.executed_value,
            "kind": self.kind.value,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CoherenceConflict":
        require_schema(payload, CONFLICT_SCHEMA)
        return cls(
            field=payload["field"],
            snapshot_value=payload.get("snapshot_value", ""),
            executed_value=payload.get("executed_value", ""),
            kind=CoherenceStatus(payload["kind"]),
            detail=payload.get("detail", ""),
        )


@dataclass(frozen=True)
class CoherenceReport:
    """The verdict, what it rests on, and what it could not check."""

    status: CoherenceStatus
    checked: tuple[str, ...] = ()
    conflicts: tuple[CoherenceConflict, ...] = ()
    #: Dependencies that *block* verification: never pinned by the basis, or
    #: live providers that cannot identify their own executable semantics.
    unverified: tuple[str, ...] = ()
    #: Optional labels neither side declared. Informational, never blocking —
    #: kept separate so "nobody filled in a version string" is not confused
    #: with "this score rests on something nobody can identify".
    not_declared: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", CoherenceStatus(self.status))
        object.__setattr__(self, "checked", tuple(self.checked))
        object.__setattr__(self, "conflicts", tuple(self.conflicts))
        object.__setattr__(self, "unverified", tuple(self.unverified))
        object.__setattr__(self, "not_declared", tuple(self.not_declared))
        if self.status in CONFLICT_STATUSES and not self.conflicts:
            raise ValueError(
                f"{self.status.value} must name the conflicts it rests on"
            )
        if self.status not in CONFLICT_STATUSES and self.conflicts:
            raise ValueError(
                f"{self.status.value} must not carry conflicts; a contradiction "
                f"that does not refuse is a contradiction nobody acted on"
            )
        if self.status is CoherenceStatus.BASIS_UNVERIFIED and not self.unverified:
            raise ValueError(
                "basis_unverified must name what it could not verify"
            )
        if self.status is CoherenceStatus.COHERENT and self.unverified:
            raise ValueError(
                f"coherent must not leave blocking dependencies unverified: "
                f"{list(self.unverified)}"
            )

    @property
    def is_refusal(self) -> bool:
        return self.status in REFUSING_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COHERENCE_SCHEMA,
            "status": self.status.value,
            "checked": list(self.checked),
            "conflicts": [c.to_dict() for c in self.conflicts],
            "unverified": list(self.unverified),
            "not_declared": list(self.not_declared),
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CoherenceReport":
        require_schema(payload, COHERENCE_SCHEMA)
        return cls(
            status=CoherenceStatus(payload["status"]),
            checked=tuple(payload.get("checked", ())),
            conflicts=tuple(
                CoherenceConflict.from_dict(c) for c in payload.get("conflicts", ())
            ),
            unverified=tuple(payload.get("unverified", ())),
            not_declared=tuple(payload.get("not_declared", ())),
            detail=payload.get("detail", ""),
        )


def _dependency(
    manifest: ExecutionDependencyManifest, kind: DependencyKind
) -> Any | None:
    for dependency in manifest.dependencies:
        if dependency.kind is kind:
            return dependency
    return None


def _declared(value: Any) -> str:
    """Normalise a pin to text, distinguishing "absent" from "zero".

    ``0`` is a legitimate signature version, so falsiness is the wrong test —
    only ``None`` and blank text mean the field was never declared.
    """
    if value is None:
        return ""
    text = str(value)
    return text if text.strip() else ""


class _Checker:
    """Accumulates checked fields, conflicts and unverifiable fields."""

    def __init__(self) -> None:
        self.checked: list[str] = []
        self.conflicts: list[CoherenceConflict] = []
        self.unverified: list[str] = []
        self.not_declared: list[str] = []

    def compare(
        self,
        field: str,
        snapshot_value: Any,
        executed_value: Any,
        *,
        kind: CoherenceStatus,
        detail: str = "",
    ) -> None:
        """Compare one field, but only when both sides actually declare it.

        A blank on either side is *not* treated as a match — it is recorded as
        unverified. Silence is not agreement.
        """
        declared = _declared(snapshot_value)
        executed = _declared(executed_value)
        if not declared or not executed:
            self.not_declared.append(field)
            return
        self.checked.append(field)
        if declared != executed:
            self.conflicts.append(
                CoherenceConflict(
                    field=field,
                    snapshot_value=declared,
                    executed_value=executed,
                    kind=kind,
                    detail=detail,
                )
            )

    def require_confirmable(
        self, field: str, snapshot_value: Any, executed_value: Any, *, detail: str
    ) -> None:
        """The snapshot claims a state the manifest cannot confirm.

        Fails closed: a pin nobody can check is a mismatch, not a pass.
        """
        declared = _declared(snapshot_value)
        if not declared:
            return
        if _declared(executed_value):
            return
        self.checked.append(field)
        self.conflicts.append(
            CoherenceConflict(
                field=field,
                snapshot_value=declared,
                executed_value="<unpinnable>",
                kind=CoherenceStatus.DEPENDENCY_MISMATCH,
                detail=detail,
            )
        )


def _check_decision_basis(
    check: _Checker,
    snapshot: BeliefSnapshot,
    manifest: ExecutionDependencyManifest,
) -> None:
    """Every dependency that can move a formal score must be pinned and match.

    This is the M4.4 core. Calibration models are only half the basis: the
    terminal utility, the outcome model, the cost tradeoff and the utility
    policy all change the answer, and all are mutable. Measured before this
    check existed, with the snapshot, candidates, charter version and
    policy_id/policy_version all held fixed:

        tampered terminal utility  ->  total   +0.0  became  +891.0
        tampered outcome model     ->  total   +0.0  became   +36.0
        changed cost tradeoff      ->  total   +0.0  became   +3.996
        mutated policy state       ->  total   +0.0  became    +4.0

    Every one of those was emitted as an ordinary recommendation, and every one
    reported ``coherence=coherent``.
    """
    basis = {d.key: d for d in snapshot.decision_basis}
    live = {d.key: d for d in manifest.dependencies}

    if not basis:
        check.unverified.append("decision_basis: never pinned")
        for key in sorted(live):
            check.unverified.append(f"{key}: absent from the decision basis")
        return

    for key in sorted(live):
        dependency = live[key]
        if not dependency.is_pinned:
            # Fails closed by design: a provider that cannot state its own
            # executable semantics cannot support formal decision theory. No
            # identity is fabricated for it.
            check.unverified.append(
                f"{key}: the live provider cannot identify its executable "
                f"semantics"
            )
            continue
        pinned = basis.get(key)
        if pinned is None:
            check.unverified.append(f"{key}: absent from the decision basis")
            continue
        check.checked.append(key)
        if dependency.matches(pinned):
            continue
        same_identity = (
            dependency.version == pinned.version
            and dependency.dataset_id == pinned.dataset_id
        )
        check.conflicts.append(
            CoherenceConflict(
                field=key,
                snapshot_value=pinned.state_digest or "<unpinned>",
                executed_value=dependency.state_digest or "<unpinnable>",
                kind=(
                    CoherenceStatus.STALE_SNAPSHOT
                    if same_identity
                    else CoherenceStatus.DEPENDENCY_MISMATCH
                ),
                detail=(
                    "the provider's executable state changed after this "
                    "decision basis was pinned"
                    if same_identity
                    else "a different provider identity than the basis pinned"
                ),
            )
        )

    for key in sorted(set(basis) - set(live)):
        check.checked.append(key)
        check.conflicts.append(
            CoherenceConflict(
                field=key,
                snapshot_value=basis[key].state_digest or "<pinned>",
                executed_value="<absent>",
                kind=CoherenceStatus.DEPENDENCY_MISMATCH,
                detail="pinned by the decision basis but not used to score",
            )
        )


def check_state_coherence(
    snapshot: BeliefSnapshot,
    manifest: ExecutionDependencyManifest,
) -> CoherenceReport:
    """Verify that the decision basis and the executed dependencies agree.

    Two layers. The M4.4 layer compares every pinned executable dependency —
    cost model, failure source, outcome model, terminal utility, cost tradeoff,
    utility policy, utility engine — against what would actually score. The
    M4.3 layer additionally cross-checks the calibration state the snapshot
    declares, the signature versions, the charter version, and that the
    manifest was in fact built for this snapshot.
    """
    check = _Checker()
    calibration = snapshot.calibration

    _check_decision_basis(check, snapshot, manifest)

    # -- the manifest must belong to this snapshot -------------------------
    check.compare(
        "snapshot_digest",
        snapshot.digest,
        manifest.snapshot_digest,
        kind=CoherenceStatus.DEPENDENCY_MISMATCH,
        detail="the manifest was built for a different belief snapshot",
    )

    # -- cost --------------------------------------------------------------
    cost = _dependency(manifest, DependencyKind.COST_MODEL)
    cost_pins = (
        calibration.cost_model_id,
        calibration.cost_model_version,
        calibration.cost_dataset_id,
        calibration.cost_model_state_digest,
    )
    if cost is None:
        if any(cost_pins):
            check.checked.append("cost_model")
            check.conflicts.append(
                CoherenceConflict(
                    field="cost_model",
                    snapshot_value=calibration.cost_model_id or "<pinned>",
                    executed_value="<absent>",
                    kind=CoherenceStatus.DEPENDENCY_MISMATCH,
                    detail=(
                        "the snapshot pins a cost model but none was used to "
                        "score"
                    ),
                )
            )
        else:
            check.unverified.append("cost_model")
    else:
        check.compare(
            "cost_model_id",
            calibration.cost_model_id,
            cost.dependency_id,
            kind=CoherenceStatus.DEPENDENCY_MISMATCH,
            detail="a different cost model was used than the snapshot names",
        )
        check.compare(
            "cost_model_version",
            calibration.cost_model_version,
            cost.version,
            kind=CoherenceStatus.DEPENDENCY_MISMATCH,
        )
        check.compare(
            "cost_dataset_id",
            calibration.cost_dataset_id,
            cost.dataset_id,
            kind=CoherenceStatus.DEPENDENCY_MISMATCH,
            detail="the cost model was trained on a different dataset",
        )
        check.compare(
            "cost_model_state_digest",
            calibration.cost_model_state_digest,
            cost.state_digest,
            kind=CoherenceStatus.STALE_SNAPSHOT,
            detail=(
                "the cost model was refit after this snapshot was taken; the "
                "snapshot no longer describes the model that would score it"
            ),
        )
        check.require_confirmable(
            "cost_model_state_digest",
            calibration.cost_model_state_digest,
            cost.state_digest,
            detail=(
                "the snapshot pins a cost model state but the live cost "
                "supplier cannot identify its fitted state"
            ),
        )

    # -- failure -----------------------------------------------------------
    failure = _dependency(manifest, DependencyKind.FAILURE_SOURCE)
    failure_pins = (
        calibration.failure_model_id,
        calibration.failure_model_version,
        calibration.failure_dataset_id,
        calibration.failure_model_state_digest,
    )
    if failure is None:
        if any(failure_pins):
            check.checked.append("failure_source")
            check.conflicts.append(
                CoherenceConflict(
                    field="failure_source",
                    snapshot_value=calibration.failure_model_id or "<pinned>",
                    executed_value="<absent>",
                    kind=CoherenceStatus.DEPENDENCY_MISMATCH,
                    detail=(
                        "the snapshot pins a failure source but none was used "
                        "to score"
                    ),
                )
            )
        else:
            check.unverified.append("failure_source")
    else:
        check.compare(
            "failure_model_id",
            calibration.failure_model_id,
            failure.dependency_id,
            kind=CoherenceStatus.DEPENDENCY_MISMATCH,
            detail="a different failure source was used than the snapshot names",
        )
        check.compare(
            "failure_model_version",
            calibration.failure_model_version,
            failure.version,
            kind=CoherenceStatus.DEPENDENCY_MISMATCH,
        )
        check.compare(
            "failure_dataset_id",
            calibration.failure_dataset_id,
            failure.dataset_id,
            kind=CoherenceStatus.DEPENDENCY_MISMATCH,
        )
        check.compare(
            "failure_model_state_digest",
            calibration.failure_model_state_digest,
            failure.state_digest,
            kind=CoherenceStatus.STALE_SNAPSHOT,
            detail="the failure source changed after this snapshot was taken",
        )
        check.require_confirmable(
            "failure_model_state_digest",
            calibration.failure_model_state_digest,
            failure.state_digest,
            detail=(
                "the snapshot pins a failure state but the live failure "
                "supplier cannot identify its own state"
            ),
        )

    # -- signature versions ------------------------------------------------
    # These are code-version facts, so the live constants are the other side.
    check.compare(
        "structure_signature_version",
        calibration.structure_signature_version,
        STRUCTURE_SIGNATURE_VERSION,
        kind=CoherenceStatus.DEPENDENCY_MISMATCH,
        detail=(
            "the snapshot was built under a different structure signature "
            "version; calibration keys are not comparable across versions"
        ),
    )
    check.compare(
        "environment_signature_version",
        calibration.environment_signature_version,
        ENVIRONMENT_SIGNATURE_VERSION,
        kind=CoherenceStatus.DEPENDENCY_MISMATCH,
        detail="the snapshot was built under a different environment signature",
    )

    # -- charter -----------------------------------------------------------
    check.compare(
        "charter_version",
        snapshot.charter_version,
        manifest.charter_version,
        kind=CoherenceStatus.DEPENDENCY_MISMATCH,
        detail=(
            "the snapshot was taken under a different charter version than the "
            "one this ranking is being recorded against"
        ),
    )

    return _verdict(check)


def _verdict(check: _Checker) -> CoherenceReport:
    """Resolve accumulated findings into one status.

    A concrete contradiction is reported ahead of an absence, because it names
    the thing that moved. Both lists travel on the report either way, so a
    refusal never hides the other half of the story. A structural mismatch in
    turn outranks staleness: if the basis and the manifest disagree about
    *which* provider was used, whether it was also refit is secondary.
    """
    conflicts = tuple(check.conflicts)
    checked = tuple(sorted(set(check.checked)))
    unverified = tuple(sorted(set(check.unverified)))
    not_declared = tuple(sorted(set(check.not_declared)))

    if conflicts:
        status = (
            CoherenceStatus.DEPENDENCY_MISMATCH
            if any(c.kind is CoherenceStatus.DEPENDENCY_MISMATCH for c in conflicts)
            else CoherenceStatus.STALE_SNAPSHOT
        )
        return CoherenceReport(
            status=status,
            checked=checked,
            conflicts=conflicts,
            unverified=unverified,
            not_declared=not_declared,
            detail=(
                f"{len(conflicts)} contradiction(s) between the decision basis "
                f"and the dependencies that would score it: "
                f"{[c.field for c in conflicts]}"
            ),
        )

    if unverified:
        return CoherenceReport(
            status=CoherenceStatus.BASIS_UNVERIFIED,
            checked=checked,
            unverified=unverified,
            not_declared=not_declared,
            detail=(
                f"the decision basis cannot verify {len(unverified)} dependency "
                f"(dependencies) that contribute to a formal score: "
                f"{list(unverified)}. Formal decision-theoretic scoring is "
                f"unavailable; no contradiction was found because none could be"
            ),
        )

    return CoherenceReport(
        status=CoherenceStatus.COHERENT,
        checked=checked,
        not_declared=not_declared,
        detail=(
            f"the decision basis and the executed dependencies agree on "
            f"{len(checked)} identity field(s); every dependency that can move "
            f"a formal score is pinned and confirmed"
        ),
    )


def pin_decision_basis(
    snapshot: BeliefSnapshot, manifest: ExecutionDependencyManifest
) -> BeliefSnapshot:
    """Return the snapshot pinned to the dependencies that would score it.

    This is the legitimate way to make a decision on current models: pin a
    *new* basis to them. It is what a caller must do after any dependency
    changes, instead of reusing an old basis — and it is a one-liner precisely
    so that refusing the alternative is reasonable rather than obstructive.

    An unpinnable live dependency is copied through as-is, so the resulting
    snapshot still fails verification. Pinning cannot manufacture an identity
    that the provider itself could not supply.
    """
    import dataclasses

    return dataclasses.replace(
        snapshot,
        calibration=calibration_state_for(
            manifest,
            cost_verdict=snapshot.calibration.cost_verdict,
            failure_verdict=snapshot.calibration.failure_verdict,
        ),
        decision_basis=tuple(manifest.dependencies),
    )


def calibration_state_for(
    manifest: ExecutionDependencyManifest,
    *,
    cost_verdict: Any = None,
    failure_verdict: Any = None,
):
    """Mint a :class:`CalibrationState` pinned to what would actually run.

    The calibration half of a decision basis. Most callers want
    :func:`pin_decision_basis`, which pins this *and* every decision-theoretic
    provider. Importing here keeps the module import graph acyclic.
    """
    from .belief_snapshot import CalibrationState

    cost = _dependency(manifest, DependencyKind.COST_MODEL)
    failure = _dependency(manifest, DependencyKind.FAILURE_SOURCE)
    return CalibrationState(
        cost_model_id=cost.dependency_id if cost else "",
        cost_model_version=cost.version if cost else "",
        cost_dataset_id=cost.dataset_id if cost else "",
        cost_model_state_digest=cost.state_digest if cost else "",
        cost_verdict=cost_verdict,
        failure_model_id=failure.dependency_id if failure else "",
        failure_model_version=failure.version if failure else "",
        failure_dataset_id=failure.dataset_id if failure else "",
        failure_model_state_digest=failure.state_digest if failure else "",
        failure_verdict=failure_verdict,
    )
