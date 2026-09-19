from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re

from ..errors import InvalidScientificProblem

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DiscoveryCandidateStatus(str, Enum):
    GENERATED = "generated"
    CALIBRATED = "calibrated"
    SURVIVED_HOLDOUT = "survived_holdout"
    FAILED_HOLDOUT = "failed_holdout"
    INDEPENDENTLY_VERIFIED = "independently_verified"
    REJECTED = "rejected"


@dataclass(frozen=True)
class DiscoveredEquationCandidate:
    candidate_id: str
    feature_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    calibration_rmse: float
    holdout_rmse: float | None
    complexity: int
    context_digest: str
    evidence_digests: tuple[str, ...]
    status: DiscoveryCandidateStatus = DiscoveryCandidateStatus.CALIBRATED

    def __post_init__(self) -> None:
        candidate_id = str(self.candidate_id).strip()
        features = tuple(str(x).strip() for x in self.feature_names)
        coefficients = tuple(float(x) for x in self.coefficients)
        context = str(self.context_digest).strip().lower()
        evidence = tuple(
            sorted(set(str(x).strip().lower() for x in self.evidence_digests))
        )
        if not candidate_id or not features or len(features) != len(coefficients):
            raise InvalidScientificProblem(
                "discovered equation candidate requires aligned features and coefficients"
            )
        if any(not x for x in features) or len(features) != len(set(features)):
            raise InvalidScientificProblem(
                "discovered equation feature names must be unique and non-empty"
            )
        numeric = coefficients + (
            float(self.intercept),
            float(self.calibration_rmse),
        )
        if any(not math.isfinite(x) for x in numeric):
            raise InvalidScientificProblem(
                "discovered equation candidate contains non-finite values"
            )
        if self.calibration_rmse < 0:
            raise InvalidScientificProblem(
                "calibration RMSE must be non-negative"
            )
        if self.holdout_rmse is not None:
            holdout = float(self.holdout_rmse)
            if not math.isfinite(holdout) or holdout < 0:
                raise InvalidScientificProblem(
                    "holdout RMSE must be finite and non-negative"
                )
            object.__setattr__(self, "holdout_rmse", holdout)
        if int(self.complexity) < 1:
            raise InvalidScientificProblem(
                "discovered equation complexity must be positive"
            )
        if not _SHA256.fullmatch(context):
            raise InvalidScientificProblem(
                "discovered equation context_digest must be SHA-256"
            )
        if not evidence or any(not _SHA256.fullmatch(x) for x in evidence):
            raise InvalidScientificProblem(
                "discovered equation requires evidence digest identities"
            )
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "feature_names", features)
        object.__setattr__(self, "coefficients", coefficients)
        object.__setattr__(self, "context_digest", context)
        object.__setattr__(self, "evidence_digests", evidence)
        object.__setattr__(
            self, "status", DiscoveryCandidateStatus(self.status)
        )

    @property
    def fingerprint(self) -> str:
        payload = {
            "feature_names": list(self.feature_names),
            "coefficients": list(self.coefficients),
            "intercept": self.intercept,
            "context_digest": self.context_digest,
            "evidence_digests": list(self.evidence_digests),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
