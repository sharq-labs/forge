from __future__ import annotations

from dataclasses import dataclass
import re


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CertificationGateResult:
    gate_id: str
    passed: bool
    evidence_digest: str

    def __post_init__(self) -> None:
        gate = str(self.gate_id).strip()
        digest = str(self.evidence_digest).strip().lower()
        if not gate or not _SHA256.fullmatch(digest):
            raise ValueError(
                "certification gate requires id and lowercase SHA-256 evidence_digest"
            )
        if not isinstance(self.passed, bool):
            raise ValueError("certification gate passed must be bool")
        object.__setattr__(self, "gate_id", gate)
        object.__setattr__(self, "evidence_digest", digest)
