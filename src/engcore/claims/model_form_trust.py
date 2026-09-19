"""Repository trust boundary for model-form UQ producer qualifications.

A ProducerQualification is a signed-off *claim* that one statistical producer
has been validated and independently reviewed.  Its shape checks alone cannot
make that claim trustworthy: a caller can construct a perfectly well-formed
record.  This module therefore separates record validity from production trust.

There is deliberately no mutating registration API.  A production registry is
constructed whole from repository-owned pins, identified by its own digest, and
passed into the UQ runtime.  Until a real independent-review artifact is pinned,
the production registry is empty and model-form promotion remains UNKNOWN.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from ..uq.model_form.qualification import ProducerQualification

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ModelFormQualificationPin:
    qualification_digest: str
    curator: str
    rationale: str

    def __post_init__(self) -> None:
        digest = str(self.qualification_digest).strip().lower()
        curator = str(self.curator).strip()
        rationale = str(self.rationale).strip()
        if not _SHA256.fullmatch(digest):
            raise ValueError("qualification pin digest must be lowercase SHA-256")
        if not curator or not rationale:
            raise ValueError("qualification pin requires curator and rationale")
        object.__setattr__(self, "qualification_digest", digest)
        object.__setattr__(self, "curator", curator)
        object.__setattr__(self, "rationale", rationale)

    def to_dict(self) -> dict[str, str]:
        return {
            "qualification_digest": self.qualification_digest,
            "curator": self.curator,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ModelFormQualificationRegistry:
    """Immutable set of qualifications production is prepared to trust."""

    pins: tuple[ModelFormQualificationPin, ...] = ()

    def __post_init__(self) -> None:
        pins = tuple(sorted(self.pins, key=lambda p: p.qualification_digest))
        if any(not isinstance(item, ModelFormQualificationPin) for item in pins):
            raise ValueError("model-form qualification registry accepts pins only")
        digests = [item.qualification_digest for item in pins]
        if len(digests) != len(set(digests)):
            raise ValueError("duplicate model-form qualification digest")
        object.__setattr__(self, "pins", pins)

    def pin_for(
        self, qualification: ProducerQualification | str
    ) -> ModelFormQualificationPin | None:
        digest = (
            qualification.digest
            if isinstance(qualification, ProducerQualification)
            else str(qualification).strip().lower()
        )
        return next(
            (item for item in self.pins if item.qualification_digest == digest),
            None,
        )

    @property
    def digest(self) -> str:
        payload = json.dumps(
            [item.to_dict() for item in self.pins],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# No reviewed qualification artifact currently exists in the repository.
# Empty is a deliberate production state: callers may submit a qualification
# record for inspection, but it cannot promote held-out discrepancy into a
# MODEL_FORM uncertainty until a repository-owned independent review is pinned.
PRODUCTION_MODEL_FORM_QUALIFICATIONS = ModelFormQualificationRegistry()


__all__ = [
    "ModelFormQualificationPin",
    "ModelFormQualificationRegistry",
    "PRODUCTION_MODEL_FORM_QUALIFICATIONS",
]
