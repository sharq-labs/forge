"""Trust registry for empirical observations admitted to scientific UQ.

DatasetObservation is a structured record, not proof that the row exists in a
curated dataset.  Aleatoric and model-form UQ therefore require an immutable
repository pin over the exact observation record before it may contribute to a
production estimate.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from .measurement_dataset import DatasetObservation

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class EmpiricalObservationPin:
    observation_digest: str
    curator: str
    rationale: str

    def __post_init__(self) -> None:
        digest = str(self.observation_digest).strip().lower()
        curator = str(self.curator).strip()
        rationale = str(self.rationale).strip()
        if not _SHA256.fullmatch(digest):
            raise ValueError("empirical observation pin digest must be lowercase SHA-256")
        if not curator or not rationale:
            raise ValueError("empirical observation pin requires curator and rationale")
        object.__setattr__(self, "observation_digest", digest)
        object.__setattr__(self, "curator", curator)
        object.__setattr__(self, "rationale", rationale)

    def to_dict(self) -> dict[str, str]:
        return {
            "observation_digest": self.observation_digest,
            "curator": self.curator,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class EmpiricalObservationRegistry:
    pins: tuple[EmpiricalObservationPin, ...] = ()

    def __post_init__(self) -> None:
        pins = tuple(sorted(self.pins, key=lambda p: p.observation_digest))
        if any(not isinstance(item, EmpiricalObservationPin) for item in pins):
            raise ValueError("empirical observation registry accepts pins only")
        digests = [item.observation_digest for item in pins]
        if len(digests) != len(set(digests)):
            raise ValueError("duplicate empirical observation digest")
        object.__setattr__(self, "pins", pins)

    def pin_for(
        self, observation: DatasetObservation | str
    ) -> EmpiricalObservationPin | None:
        digest = (
            observation.digest
            if isinstance(observation, DatasetObservation)
            else str(observation).strip().lower()
        )
        return next(
            (item for item in self.pins if item.observation_digest == digest),
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


# Deliberately empty until an empirical-UQ dataset round freezes exact
# DatasetObservation records. Existing benchmark measurements remain usable as
# validation evidence, but they are not silently upgraded into replicate or
# held-out UQ datasets.
PRODUCTION_EMPIRICAL_OBSERVATIONS = EmpiricalObservationRegistry()


__all__ = [
    "EmpiricalObservationPin",
    "EmpiricalObservationRegistry",
    "PRODUCTION_EMPIRICAL_OBSERVATIONS",
]
