from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dataset import DiscoveryDataset
    from .final_evaluation import FrozenDiscoverySelection

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
    """A review decision, carrying the inputs it was decided from so a campaign can replay it.

    The replay inputs are not part of the decision's equality: a campaign re-runs
    :func:`review_discovery_candidate` on them and admits a promoting review only
    when the replay returns the same decision, reasons and verification digest.
    """
    candidate: DiscoveredEquationCandidate
    decision: DiscoveryDecision
    reasons: tuple[str, ...]
    verification_digest: str = ""
    final_selection: FrozenDiscoverySelection | None = field(default=None, compare=False, repr=False)
    final_data: DiscoveryDataset | None = field(default=None, compare=False, repr=False)
    verification: VerificationRunRecord | None = field(default=None, compare=False, repr=False)

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
    final_selection: FrozenDiscoverySelection | None = None,
    final_data: DiscoveryDataset | None = None,
) -> DiscoveryReview:
    if type(candidate) is not DiscoveredEquationCandidate:
        # a subclass could present another identity (e.g. a borrowed fingerprint) for different coefficients
        raise InvalidScientificProblem("review requires an exact DiscoveredEquationCandidate (no subclasses)")
    if verification is not None and type(verification) is not VerificationRunRecord:
        # the record re-derives its verdict from its observations; a look-alike only asserts one
        raise InvalidScientificProblem("verification must be a VerificationRunRecord; a look-alike object is not evidence")
    replay = {"final_selection": final_selection, "final_data": final_data, "verification": verification}
    has_replay = final_selection is not None and final_data is not None
    unbound = "candidate is not bound to the supplied replay inputs; unresolved"

    def review(decision: DiscoveryDecision, reasons: tuple[str, ...], digest: str = "") -> DiscoveryReview:
        return DiscoveryReview(candidate, decision, reasons, digest, **replay)

    if candidate.evaluation_role == "final_test":
        # a stored final-test status is never acted on before it is replayed, in either direction
        if not has_replay:
            return review(DiscoveryDecision.CANDIDATE,
                          ("a final-test record is not evidence until it is replayed; frozen selection and final data are required",))
        from .final_evaluation import evaluate_final_test
        replayed = evaluate_final_test(final_selection, final_data)
        if candidate != replayed or candidate.fingerprint != replayed.fingerprint:
            # the whole record and its identity must be the replay's (== alone accepts True/1, 1/1.0, -0.0/0.0);
            # a mismatch shows the inputs do not bind this record, not that the result is contradicted
            return review(DiscoveryDecision.CANDIDATE, (unbound,))
        if replayed.status is DiscoveryCandidateStatus.FAILED_HOLDOUT:
            return review(DiscoveryDecision.REJECTED, ("candidate failed the replayed final test",))
    else:
        if candidate.status is DiscoveryCandidateStatus.FAILED_HOLDOUT:
            return review(DiscoveryDecision.REJECTED, ("candidate failed the reserved holdout set",))
        if candidate.evaluation_role == "selection":
            return review(DiscoveryDecision.CANDIDATE,
                          ("selection score is not independent confirmation; freeze the winner and run a separate final test",))
        if candidate.status is not DiscoveryCandidateStatus.SURVIVED_HOLDOUT:
            return review(DiscoveryDecision.CANDIDATE, ("candidate has not survived the reserved holdout set",))
        # only a final-test record can match a replay, so any other role is unresolved
        return review(DiscoveryDecision.CANDIDATE, (unbound,) if has_replay else
                      ("a role or stored score is not final-test evidence; frozen selection and final data are required for replay",))
    if verification is None:
        return review(
            DiscoveryDecision.HOLDOUT_SURVIVOR,
            (
                "candidate survived holdout but lacks independent "
                "verification/reproduction",
            ),
        )
    if verification.subject_digest != candidate.fingerprint:
        return review(
            DiscoveryDecision.HOLDOUT_SURVIVOR,
            (
                "independent verification is not bound to this candidate's "
                "fingerprint; a successful verification of another subject "
                "cannot reproduce this one",
            ),
        )
    result = verification.result
    if (
        not result.complete
        or result.verification.decision is not VerificationDecision.VERIFIED
    ):
        return review(
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
    return review(
        DiscoveryDecision.INDEPENDENTLY_REPRODUCED,
        (
            "candidate survived reserved holdout and complete independent "
            "verification; scientific-law adoption remains a separate decision",
        ),
        digest,
    )
