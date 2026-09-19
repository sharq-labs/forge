from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re

from ..errors import InvalidScientificProblem
from .candidate import DiscoveredEquationCandidate, DiscoveryCandidateStatus
from .campaign import DiscoveryDecision, DiscoveryReview

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DiscoveryCampaignStage(str, Enum):
    CANDIDATE_GENERATION = "candidate_generation"
    FALSIFICATION = "falsification"
    HOLDOUT_REVIEW = "holdout_review"
    INDEPENDENT_REPRODUCTION = "independent_reproduction"
    COMPLETE = "complete"


@dataclass(frozen=True)
class FalsificationRecord:
    candidate_fingerprint: str
    challenge_id: str
    evidence_digest: str
    survived: bool
    reason: str

    def __post_init__(self) -> None:
        fingerprint = str(self.candidate_fingerprint).strip().lower()
        challenge = str(self.challenge_id).strip()
        evidence = str(self.evidence_digest).strip().lower()
        reason = str(self.reason).strip()
        if (
            not _SHA256.fullmatch(fingerprint)
            or not challenge
            or not _SHA256.fullmatch(evidence)
            or not reason
        ):
            raise InvalidScientificProblem(
                "falsification record requires candidate/evidence identity, "
                "challenge id and reason"
            )
        if not isinstance(self.survived, bool):
            raise InvalidScientificProblem(
                "falsification survived must be explicit bool"
            )
        object.__setattr__(self, "candidate_fingerprint", fingerprint)
        object.__setattr__(self, "challenge_id", challenge)
        object.__setattr__(self, "evidence_digest", evidence)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class ClosedLoopDiscoveryCampaign:
    campaign_id: str
    context_digest: str
    candidates: tuple[DiscoveredEquationCandidate, ...] = ()
    falsification_records: tuple[FalsificationRecord, ...] = ()
    reviews: tuple[DiscoveryReview, ...] = ()

    def __post_init__(self) -> None:
        campaign_id = str(self.campaign_id).strip()
        context = str(self.context_digest).strip().lower()
        candidates = tuple(self.candidates)
        records = tuple(self.falsification_records)
        reviews = tuple(self.reviews)
        if not campaign_id or not _SHA256.fullmatch(context):
            raise InvalidScientificProblem(
                "discovery campaign requires id and context digest"
            )
        if any(
            not isinstance(candidate, DiscoveredEquationCandidate)
            for candidate in candidates
        ):
            raise InvalidScientificProblem(
                "discovery campaign candidates must be typed"
            )
        if any(
            candidate.context_digest != context for candidate in candidates
        ):
            raise InvalidScientificProblem(
                "discovery candidate context differs from campaign context"
            )
        fingerprints = [candidate.fingerprint for candidate in candidates]
        if len(fingerprints) != len(set(fingerprints)):
            raise InvalidScientificProblem(
                "discovery campaign contains duplicate candidates"
            )
        known = set(fingerprints)
        if any(
            not isinstance(record, FalsificationRecord)
            or record.candidate_fingerprint not in known
            for record in records
        ):
            raise InvalidScientificProblem(
                "falsification records must bind campaign candidates"
            )
        review_fingerprints = [
            review.candidate.fingerprint for review in reviews
        ]
        if any(
            not isinstance(review, DiscoveryReview)
            or review.candidate.fingerprint not in known
            for review in reviews
        ):
            raise InvalidScientificProblem(
                "discovery reviews must bind campaign candidates"
            )
        if len(review_fingerprints) != len(set(review_fingerprints)):
            raise InvalidScientificProblem(
                "discovery campaign records more than one final review per candidate"
            )

        # A candidate cannot reach holdout/reproduction review without at least
        # one explicit falsification challenge that it survived.
        survived = {
            record.candidate_fingerprint
            for record in records
            if record.survived
        }
        for review in reviews:
            if (
                review.decision
                in {
                    DiscoveryDecision.HOLDOUT_SURVIVOR,
                    DiscoveryDecision.INDEPENDENTLY_REPRODUCED,
                }
                and review.candidate.fingerprint not in survived
            ):
                raise InvalidScientificProblem(
                    "discovery review skipped explicit falsification stage"
                )

        object.__setattr__(self, "campaign_id", campaign_id)
        object.__setattr__(self, "context_digest", context)
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "falsification_records", records)
        object.__setattr__(self, "reviews", reviews)

    @property
    def stage(self) -> DiscoveryCampaignStage:
        if not self.candidates:
            return DiscoveryCampaignStage.CANDIDATE_GENERATION
        candidate_ids = {candidate.fingerprint for candidate in self.candidates}
        challenged = {
            record.candidate_fingerprint
            for record in self.falsification_records
        }
        if challenged != candidate_ids:
            return DiscoveryCampaignStage.FALSIFICATION
        review_by = {
            review.candidate.fingerprint: review for review in self.reviews
        }
        surviving = {
            record.candidate_fingerprint
            for record in self.falsification_records
            if record.survived
        }
        if not surviving <= set(review_by):
            return DiscoveryCampaignStage.HOLDOUT_REVIEW
        pending_independent = [
            review
            for review in review_by.values()
            if review.decision is DiscoveryDecision.HOLDOUT_SURVIVOR
        ]
        if pending_independent:
            return DiscoveryCampaignStage.INDEPENDENT_REPRODUCTION
        return DiscoveryCampaignStage.COMPLETE

    @property
    def independently_reproduced(self) -> tuple[DiscoveryReview, ...]:
        return tuple(
            review
            for review in self.reviews
            if review.decision
            is DiscoveryDecision.INDEPENDENTLY_REPRODUCED
        )

    def with_candidates(
        self,
        candidates: tuple[DiscoveredEquationCandidate, ...],
    ) -> "ClosedLoopDiscoveryCampaign":
        if self.candidates:
            raise InvalidScientificProblem(
                "campaign candidates are immutable once generation is recorded"
            )
        return ClosedLoopDiscoveryCampaign(
            self.campaign_id,
            self.context_digest,
            tuple(candidates),
            self.falsification_records,
            self.reviews,
        )

    def with_falsification(
        self,
        record: FalsificationRecord,
    ) -> "ClosedLoopDiscoveryCampaign":
        if record.candidate_fingerprint not in {
            candidate.fingerprint for candidate in self.candidates
        }:
            raise InvalidScientificProblem(
                "falsification record references candidate outside campaign"
            )
        if any(
            item.candidate_fingerprint == record.candidate_fingerprint
            and item.challenge_id == record.challenge_id
            for item in self.falsification_records
        ):
            raise InvalidScientificProblem(
                "duplicate falsification challenge for candidate"
            )
        return ClosedLoopDiscoveryCampaign(
            self.campaign_id,
            self.context_digest,
            self.candidates,
            self.falsification_records + (record,),
            self.reviews,
        )

    def with_review(
        self,
        review: DiscoveryReview,
    ) -> "ClosedLoopDiscoveryCampaign":
        fingerprint = review.candidate.fingerprint
        if fingerprint not in {
            candidate.fingerprint for candidate in self.candidates
        }:
            raise InvalidScientificProblem(
                "discovery review references candidate outside campaign"
            )
        if any(
            existing.candidate.fingerprint == fingerprint
            for existing in self.reviews
        ):
            raise InvalidScientificProblem(
                "candidate already has a discovery review"
            )
        return ClosedLoopDiscoveryCampaign(
            self.campaign_id,
            self.context_digest,
            self.candidates,
            self.falsification_records,
            self.reviews + (review,),
        )

    @property
    def digest(self) -> str:
        payload = {
            "campaign_id": self.campaign_id,
            "context_digest": self.context_digest,
            "candidate_fingerprints": sorted(
                candidate.fingerprint for candidate in self.candidates
            ),
            "falsification": [
                {
                    "candidate": record.candidate_fingerprint,
                    "challenge_id": record.challenge_id,
                    "evidence": record.evidence_digest,
                    "survived": record.survived,
                    "reason": record.reason,
                }
                for record in sorted(
                    self.falsification_records,
                    key=lambda item: (
                        item.candidate_fingerprint,
                        item.challenge_id,
                    ),
                )
            ],
            "reviews": [
                {
                    "candidate": review.candidate.fingerprint,
                    "decision": review.decision.value,
                    "verification_digest": review.verification_digest,
                    "reasons": list(review.reasons),
                }
                for review in sorted(
                    self.reviews,
                    key=lambda item: item.candidate.fingerprint,
                )
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
