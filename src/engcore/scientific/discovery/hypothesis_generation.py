from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re

from ..errors import InvalidScientificProblem
from .candidate import DiscoveredEquationCandidate
from .regimes import RegimeBoundaryCandidate

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class GeneratedHypothesisKind(str, Enum):
    EQUATION = "equation"
    OUTLIER_PROCESS = "outlier_process"
    REGIME_CHANGE = "regime_change"


@dataclass(frozen=True)
class GeneratedHypothesis:
    hypothesis_id: str
    kind: GeneratedHypothesisKind
    statement: str
    context_digest: str
    evidence_digests: tuple[str, ...]
    candidate_fingerprint: str = ""

    def __post_init__(self) -> None:
        hypothesis_id = str(self.hypothesis_id).strip()
        statement = str(self.statement).strip()
        context = str(self.context_digest).strip().lower()
        evidence = tuple(
            sorted(set(str(x).strip().lower() for x in self.evidence_digests))
        )
        fingerprint = str(self.candidate_fingerprint).strip().lower()
        if not hypothesis_id or not statement:
            raise InvalidScientificProblem(
                "generated hypothesis requires id and statement"
            )
        if not _SHA256.fullmatch(context):
            raise InvalidScientificProblem(
                "generated hypothesis context_digest must be SHA-256"
            )
        if not evidence or any(not _SHA256.fullmatch(x) for x in evidence):
            raise InvalidScientificProblem(
                "generated hypothesis requires evidence digests"
            )
        if fingerprint and not _SHA256.fullmatch(fingerprint):
            raise InvalidScientificProblem(
                "candidate_fingerprint must be SHA-256 when supplied"
            )
        object.__setattr__(
            self, "kind", GeneratedHypothesisKind(self.kind)
        )
        object.__setattr__(self, "hypothesis_id", hypothesis_id)
        object.__setattr__(self, "statement", statement)
        object.__setattr__(self, "context_digest", context)
        object.__setattr__(self, "evidence_digests", evidence)
        object.__setattr__(self, "candidate_fingerprint", fingerprint)


def equation_hypothesis(
    candidate: DiscoveredEquationCandidate,
) -> GeneratedHypothesis:
    terms = " + ".join(
        f"({coefficient:.12g})*{feature}"
        for feature, coefficient in zip(
            candidate.feature_names,
            candidate.coefficients,
        )
    )
    statement = (
        "dimensionless target may be approximated by "
        f"{candidate.intercept:.12g}"
        + (f" + {terms}" if terms else "")
    )
    return GeneratedHypothesis(
        f"equation:{candidate.fingerprint[:20]}",
        GeneratedHypothesisKind.EQUATION,
        statement,
        candidate.context_digest,
        candidate.evidence_digests,
        candidate.fingerprint,
    )


def regime_hypothesis(
    boundary: RegimeBoundaryCandidate,
    *,
    context_digest: str,
    evidence_digests: tuple[str, ...],
) -> GeneratedHypothesis:
    payload = {
        "split": boundary.split_index,
        "shift": boundary.standardized_shift,
        "context": context_digest,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return GeneratedHypothesis(
        f"regime:{digest[:20]}",
        GeneratedHypothesisKind.REGIME_CHANGE,
        (
            "residual process may change regime near ordered index "
            f"{boundary.split_index}; standardized shift "
            f"{boundary.standardized_shift:.6g}"
        ),
        context_digest,
        evidence_digests,
    )
