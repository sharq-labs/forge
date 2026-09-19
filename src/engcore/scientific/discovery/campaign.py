from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re

from ..errors import InvalidScientificProblem
from ..verification import VerificationDecision, VerificationRunRecord
from .candidate import (
    DiscoveredEquationCandidate,
    DiscoveryCandidateStatus,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DiscoveryDecision(str, Enum):
    CANDIDATE = "candidate"
    REJECTED = "rejected"
    HOLDOUT_SURVIVOR = "holdout_survivor"
    INDEPENDENTLY_REPRODUCED = "independently_reproduced"


@dataclass(frozen=True)
class DiscoveryReview:
    candidate: DiscoveredEquationCandidate
    decision: DiscoveryDecision
    reasons: tuple[str, ...]
    verification_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "decision", DiscoveryDecision(self.decision)
        )
        reasons = tuple(str(x).strip() for x in self.reasons)
        if any(not x for x in reasons):
            raise InvalidScientificProblem(
                "discovery review reasons must be non-empty"
            )
        digest = str(self.verification_digest).strip().lower()
        if digest and not _SHA256.fullmatch(digest):
            raise InvalidScientificProblem(
                "discovery verification_digest must be SHA-256"
            )
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "verification_digest", digest)


def review_discovery_candidate(
    candidate: DiscoveredEquationCandidate,
    *,
    verification: VerificationRunRecord | None = None,
) -> DiscoveryReview:
    if candidate.status is DiscoveryCandidateStatus.FAILED_HOLDOUT:
        return DiscoveryReview(
            candidate,
            DiscoveryDecision.REJECTED,
            ("candidate failed the reserved holdout set",),
        )
    if candidate.status is not DiscoveryCandidateStatus.SURVIVED_HOLDOUT:
        return DiscoveryReview(
            candidate,
            DiscoveryDecision.CANDIDATE,
            ("candidate has not survived the reserved holdout set",),
        )
    if verification is None:
        return DiscoveryReview(
            candidate,
            DiscoveryDecision.HOLDOUT_SURVIVOR,
            (
                "candidate survived holdout but lacks independent "
                "verification/reproduction",
            ),
        )
    result = verification.result
    if (
        not result.complete
        or result.verification.decision is not VerificationDecision.VERIFIED
    ):
        return DiscoveryReview(
            candidate,
            DiscoveryDecision.REJECTED,
            (
                "candidate did not obtain complete independent "
                "verification",
            ),
        )
    digest = hashlib.sha256(
        json.dumps(
            verification.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return DiscoveryReview(
        candidate,
        DiscoveryDecision.INDEPENDENTLY_REPRODUCED,
        (
            "candidate survived reserved holdout and complete independent "
            "verification; scientific-law adoption remains a separate decision",
        ),
        digest,
    )
