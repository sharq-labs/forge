"""M4C — the immutable state a ranking is scored against.

Scoring against mutable global state makes a recommendation unreproducible: by
the time anyone asks "why did it choose that?", the state it chose from has
moved. A snapshot fixes the world for the duration of one ranking, and its
digest goes into the decision record so a replay can prove it saw the same
thing.

**Absent factors are represented, not invented.** The repository has admitted
evidence and computational calibration; it does not yet have posterior
parameter distributions or model probabilities from any real inference. Those
fields therefore default to
:class:`FactorAvailability.UNAVAILABLE` rather than being filled with a
plausible prior. A confident number nobody computed is worse than a gap,
because the gap is visible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ...scientific.serialization import require_schema, schema_string
from ..calibration.critic import CalibrationVerdict
from ..signatures import (
    ENVIRONMENT_SIGNATURE_VERSION,
    STRUCTURE_SIGNATURE_VERSION,
)
from .replay import DependencyIdentity

SNAPSHOT_SCHEMA = schema_string("sria_belief_snapshot")


class FactorAvailability(str, Enum):
    """Whether a belief factor genuinely exists in this repository yet."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"     # not computed — never silently defaulted
    DEGRADED = "degraded"           # present but its calibration is doubtful


@dataclass(frozen=True)
class CalibrationState:
    """What M2 said about the models a score depends on, *at snapshot time*.

    The version and dataset fields are the replay pins (M4.1). A score is only
    reproducible if the model that produced it can be identified; without them
    a later calibration update would silently change the recommendation for the
    same snapshot, and nobody could tell which run was which.

    The ``*_state_digest`` fields are the M4.3 addition, and they carry the
    lesson M4.2 learned the hard way: a version string and a dataset id survive
    a refit unchanged, so they identify a *label*, not a model. Only a digest
    over the fitted state can say that the model which would score this
    snapshot is the model the snapshot was taken against. Left empty, they mean
    "not pinned" — which yields
    :attr:`~engcore.sria.decision.coherence.CoherenceStatus.UNVERIFIED` rather
    than a false claim of coherence.
    """

    cost_model_id: str = ""
    cost_model_version: str = ""
    cost_dataset_id: str = ""
    cost_model_state_digest: str = ""
    cost_verdict: CalibrationVerdict | None = None
    failure_model_id: str = ""
    failure_model_version: str = ""
    failure_dataset_id: str = ""
    failure_model_state_digest: str = ""
    failure_verdict: CalibrationVerdict | None = None
    structure_signature_version: int = STRUCTURE_SIGNATURE_VERSION
    environment_signature_version: int = ENVIRONMENT_SIGNATURE_VERSION

    def __post_init__(self) -> None:
        for label in ("cost_verdict", "failure_verdict"):
            value = getattr(self, label)
            if value is not None:
                object.__setattr__(self, label, CalibrationVerdict(value))

    @property
    def cost_availability(self) -> FactorAvailability:
        return self._availability(self.cost_verdict)

    @property
    def failure_availability(self) -> FactorAvailability:
        return self._availability(self.failure_verdict)

    @staticmethod
    def _availability(verdict: CalibrationVerdict | None) -> FactorAvailability:
        if verdict is None or verdict is CalibrationVerdict.INSUFFICIENT_DATA:
            return FactorAvailability.UNAVAILABLE
        if verdict is CalibrationVerdict.TRUSTED:
            return FactorAvailability.AVAILABLE
        return FactorAvailability.DEGRADED

    @property
    def pin(self) -> tuple[str, str, str, str, str, str, int, int]:
        """The identity a replay must match to be *executable* rather than
        merely auditable."""
        return (
            self.cost_model_version,
            self.cost_dataset_id,
            self.cost_model_state_digest,
            self.failure_model_version,
            self.failure_dataset_id,
            self.failure_model_state_digest,
            self.structure_signature_version,
            self.environment_signature_version,
        )

    @property
    def pins_fitted_state(self) -> bool:
        """Whether this snapshot can prove which fitted models scored it."""
        return bool(self.cost_model_state_digest or self.failure_model_state_digest)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_model_id": self.cost_model_id,
            "cost_model_version": self.cost_model_version,
            "cost_dataset_id": self.cost_dataset_id,
            "cost_model_state_digest": self.cost_model_state_digest,
            "cost_verdict": self.cost_verdict.value if self.cost_verdict else None,
            "failure_model_id": self.failure_model_id,
            "failure_model_version": self.failure_model_version,
            "failure_dataset_id": self.failure_dataset_id,
            "failure_model_state_digest": self.failure_model_state_digest,
            "failure_verdict": (
                self.failure_verdict.value if self.failure_verdict else None
            ),
            "structure_signature_version": self.structure_signature_version,
            "environment_signature_version": self.environment_signature_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalibrationState":
        return cls(
            cost_model_id=payload.get("cost_model_id", ""),
            cost_model_version=payload.get("cost_model_version", ""),
            cost_dataset_id=payload.get("cost_dataset_id", ""),
            cost_model_state_digest=payload.get("cost_model_state_digest", ""),
            cost_verdict=(
                CalibrationVerdict(payload["cost_verdict"])
                if payload.get("cost_verdict")
                else None
            ),
            failure_model_id=payload.get("failure_model_id", ""),
            failure_model_version=payload.get("failure_model_version", ""),
            failure_dataset_id=payload.get("failure_dataset_id", ""),
            failure_model_state_digest=payload.get("failure_model_state_digest", ""),
            failure_verdict=(
                CalibrationVerdict(payload["failure_verdict"])
                if payload.get("failure_verdict")
                else None
            ),
            structure_signature_version=payload.get(
                "structure_signature_version", STRUCTURE_SIGNATURE_VERSION
            ),
            environment_signature_version=payload.get(
                "environment_signature_version", ENVIRONMENT_SIGNATURE_VERSION
            ),
        )


@dataclass(frozen=True)
class BeliefSnapshot:
    """Immutable reference state for one ranking."""

    snapshot_id: str
    campaign_id: str
    charter_version: str = ""
    #: Evidence ids currently ACTIVE in belief, from the M1 Gateway.
    active_evidence: tuple[str, ...] = ()
    belief_snapshot_ref: str = ""          # Gateway's own digest
    #: Hypothesis id -> weight. Only when a real inference produced them.
    hypothesis_weights: Mapping[str, float] = field(default_factory=dict)
    hypothesis_availability: FactorAvailability = FactorAvailability.UNAVAILABLE
    #: Reference to a parameter-uncertainty representation, when one exists.
    parameter_uncertainty_ref: str = ""
    parameter_availability: FactorAvailability = FactorAvailability.UNAVAILABLE
    calibration: CalibrationState = field(default_factory=CalibrationState)
    #: M4.4 — pinned identities of *every* executable dependency that can
    #: contribute to a formal score, not only the calibration models. A
    #: terminal utility, an outcome model, a cost tradeoff and a utility policy
    #: are all mutable and all change the answer; pinning calibration alone
    #: leaves the decision-theoretic half of the basis unverifiable.
    #:
    #: Empty means the basis was never pinned, which makes formal scoring
    #: unavailable rather than merely caveated.
    decision_basis: tuple[DependencyIdentity, ...] = ()
    #: Obligation id -> satisfied, as last assessed by the Arbiter.
    obligation_state: Mapping[str, bool] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in ("snapshot_id", "campaign_id"):
            if not str(getattr(self, label)).strip():
                raise ValueError(f"belief snapshot requires {label}")
        object.__setattr__(self, "active_evidence", tuple(self.active_evidence))
        basis = tuple(self.decision_basis)
        keys = [d.key for d in basis]
        # One pass, not one scan per key. The reported set is the same set --
        # a key is a duplicate exactly when it is seen a second time -- and the
        # message sorts it, so the refusal text is unchanged. The previous
        # `keys.count(k)` form was quadratic: measured at 7 us for a 10-entry
        # basis but 22 ms at 1600, which is a scaling trap sitting in a
        # constructor rather than a cost anyone pays today.
        seen: set[str] = set()
        duplicates: set[str] = set()
        for key in keys:
            if key in seen:
                duplicates.add(key)
            else:
                seen.add(key)
        if duplicates:
            raise ValueError(
                f"decision basis has duplicate dependency keys: {sorted(duplicates)}"
            )
        object.__setattr__(self, "decision_basis", basis)
        object.__setattr__(
            self,
            "hypothesis_availability",
            FactorAvailability(self.hypothesis_availability),
        )
        object.__setattr__(
            self,
            "parameter_availability",
            FactorAvailability(self.parameter_availability),
        )

        weights = {str(k): float(v) for k, v in self.hypothesis_weights.items()}
        if weights and self.hypothesis_availability is FactorAvailability.UNAVAILABLE:
            raise ValueError(
                "hypothesis weights were supplied but availability says "
                "UNAVAILABLE; a weight nobody computed must not appear here"
            )
        if self.hypothesis_availability is FactorAvailability.AVAILABLE and not weights:
            raise ValueError(
                "hypothesis availability is AVAILABLE but no weights are present"
            )
        object.__setattr__(self, "hypothesis_weights", weights)
        object.__setattr__(
            self, "obligation_state", {str(k): bool(v) for k, v in self.obligation_state.items()}
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def pins_decision_basis(self) -> bool:
        """Whether this snapshot can identify what would score it."""
        return bool(self.decision_basis)

    def basis_identity(self, key: str) -> DependencyIdentity | None:
        for dependency in self.decision_basis:
            if dependency.key == key:
                return dependency
        return None

    @property
    def unmet_obligations(self) -> tuple[str, ...]:
        return tuple(
            sorted(k for k, satisfied in self.obligation_state.items() if not satisfied)
        )

    @property
    def digest(self) -> str:
        """Content digest — what a replay compares to prove state equality."""
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "snapshot_id": self.snapshot_id,
            "campaign_id": self.campaign_id,
            "charter_version": self.charter_version,
            "active_evidence": list(self.active_evidence),
            "belief_snapshot_ref": self.belief_snapshot_ref,
            "hypothesis_weights": dict(sorted(self.hypothesis_weights.items())),
            "hypothesis_availability": self.hypothesis_availability.value,
            "parameter_uncertainty_ref": self.parameter_uncertainty_ref,
            "parameter_availability": self.parameter_availability.value,
            "calibration": self.calibration.to_dict(),
            "decision_basis": [
                d.to_dict() for d in sorted(self.decision_basis, key=lambda d: d.key)
            ],
            "obligation_state": dict(sorted(self.obligation_state.items())),
            "metadata": dict(sorted(self.metadata.items(), key=lambda kv: kv[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BeliefSnapshot":
        require_schema(payload, SNAPSHOT_SCHEMA)
        return cls(
            snapshot_id=payload["snapshot_id"],
            campaign_id=payload["campaign_id"],
            charter_version=payload.get("charter_version", ""),
            active_evidence=tuple(payload.get("active_evidence", ())),
            belief_snapshot_ref=payload.get("belief_snapshot_ref", ""),
            hypothesis_weights=payload.get("hypothesis_weights", {}),
            hypothesis_availability=FactorAvailability(
                payload.get("hypothesis_availability", "unavailable")
            ),
            parameter_uncertainty_ref=payload.get("parameter_uncertainty_ref", ""),
            parameter_availability=FactorAvailability(
                payload.get("parameter_availability", "unavailable")
            ),
            calibration=CalibrationState.from_dict(payload.get("calibration", {})),
            decision_basis=tuple(
                DependencyIdentity.from_dict(d)
                for d in payload.get("decision_basis", ())
            ),
            obligation_state=payload.get("obligation_state", {}),
            metadata=payload.get("metadata", {}),
        )


def snapshot_from_gateway(
    *,
    snapshot_id: str,
    campaign_id: str,
    gateway: Any,
    calibration: CalibrationState | None = None,
    obligation_state: Mapping[str, bool] | None = None,
    charter_version: str = "",
) -> BeliefSnapshot:
    """Build a snapshot from the live M1 belief, read-only."""
    belief = gateway.belief
    return BeliefSnapshot(
        snapshot_id=snapshot_id,
        campaign_id=campaign_id,
        charter_version=charter_version,
        active_evidence=tuple(sorted(belief.active_view())),
        belief_snapshot_ref=belief.snapshot_ref(),
        calibration=calibration or CalibrationState(),
        obligation_state=obligation_state or {},
    )
