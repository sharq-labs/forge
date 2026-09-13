"""Trusted cross-solver validation above the frozen consensus contract.

``CrossSolverConsensus`` already proves a great deal: route declarations are
pinned by the domain layer, outputs are complete, the comparison is recomputed
from recorded numbers, and the declared routes agree inside a domain-owned
threshold.  Its remaining documented limit is external to that record: a
correct declaration can still be wrong about which implementation/runtime
artifacts were actually used.

This module therefore adds, rather than replaces, a second gate.  A
``CROSS_SOLVER_VALIDATED`` level survives into the trusted check only when:

1. the ordinary consensus already earned that level; and
2. artifact evidence is complete, bound to the exact route dependency digests,
   and byte-disjoint across the compared routes.

Different artifact hashes are *not* proof of independent development.  The
extra gate is tamper-resistant identity evidence for the machinery the routes
claim to use, not a sociological or cryptographic proof of how it was created.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..scientific.consensus import CrossSolverConsensus
from ..scientific.errors import ScientificValidationError
from ..scientific.independence_evidence import (
    IndependenceEvidenceReport,
    RouteIndependenceEvidence,
    assess_independence_evidence,
)
from ..scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
)


def _artifact_evidence_lines(
    evidence: Sequence[RouteIndependenceEvidence],
) -> tuple[str, ...]:
    lines: list[str] = []
    for route in sorted(evidence, key=lambda item: item.route_id):
        lines.append(
            f"route {route.route_id} artifact evidence binds dependency "
            f"sha256:{route.dependency_digest}"
        )
        for dimension, artifacts in sorted(
            route.artifacts.items(), key=lambda item: item[0].value
        ):
            for artifact in sorted(artifacts):
                lines.append(
                    f"route {route.route_id} {dimension.value} artifact "
                    f"{artifact.kind}:{artifact.name} sha256:{artifact.digest}"
                )
    return tuple(lines)


@dataclass(frozen=True)
class TrustedConsensusDecision:
    """One consensus plus the external artifact-independence decision."""

    consensus: CrossSolverConsensus
    independence: IndependenceEvidenceReport
    check: ValidationCheck

    def __post_init__(self) -> None:
        if not isinstance(self.consensus, CrossSolverConsensus):
            raise ScientificValidationError(
                "trusted consensus decision requires CrossSolverConsensus"
            )
        if not isinstance(self.independence, IndependenceEvidenceReport):
            raise ScientificValidationError(
                "trusted consensus decision requires IndependenceEvidenceReport"
            )
        if not isinstance(self.check, ValidationCheck):
            raise ScientificValidationError(
                "trusted consensus decision requires ValidationCheck"
            )
        if (
            self.check.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
            and not (
                self.consensus.establishes
                is ValidationLevel.CROSS_SOLVER_VALIDATED
                and self.independence.strongly_independent
            )
        ):
            raise ScientificValidationError(
                "trusted consensus cannot declare CROSS_SOLVER_VALIDATED unless "
                "both the scientific consensus and artifact-independence gate earned it"
            )

    @property
    def validated(self) -> bool:
        return self.check.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED

    def require_validated(self) -> ValidationCheck:
        if not self.validated:
            raise ScientificValidationError(
                "trusted cross-solver validation was not established: "
                f"{self.check.detail}"
            )
        return self.check


class TrustedConsensusGate:
    """Combine declaration-level consensus with artifact-backed independence."""

    def assess(
        self,
        consensus: CrossSolverConsensus,
        evidence: Sequence[RouteIndependenceEvidence],
        *,
        name: str = "trusted_cross_solver_agreement",
    ) -> TrustedConsensusDecision:
        if not isinstance(consensus, CrossSolverConsensus):
            raise TypeError("consensus must be a CrossSolverConsensus")

        evidence = tuple(evidence)
        independence = assess_independence_evidence(consensus.routes, evidence)
        base = consensus.to_check(name=name)

        base_earned = (
            base.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
        )
        trusted_earned = base_earned and independence.strongly_independent

        if base_earned and not independence.strongly_independent:
            detail = (
                f"{base.detail}. Artifact-backed independence withheld the level: "
                f"{independence.reason}"
            )
        elif trusted_earned:
            detail = (
                f"{base.detail}. Artifact-backed independence also established: "
                f"{independence.reason}"
            )
        else:
            # Strong artifact evidence can never promote a consensus that did
            # not itself earn the scientific level.  Keep the original reason
            # first because it is the load-bearing scientific refusal.
            detail = (
                f"{base.detail}. Artifact evidence: {independence.reason}. "
                "Artifact identity cannot promote a consensus that did not "
                "already earn CROSS_SOLVER_VALIDATED."
            )

        check = ValidationCheck(
            name=base.name,
            outcome=base.outcome,
            detail=detail,
            establishes=(
                ValidationLevel.CROSS_SOLVER_VALIDATED if trusted_earned else None
            ),
            residual=base.residual,
            tolerance=base.tolerance,
            evidence=(
                *base.evidence,
                f"artifact independence: {independence.reason}",
                *_artifact_evidence_lines(evidence),
            ),
        )
        return TrustedConsensusDecision(
            consensus=consensus,
            independence=independence,
            check=check,
        )

    def require_validated(
        self,
        consensus: CrossSolverConsensus,
        evidence: Sequence[RouteIndependenceEvidence],
        *,
        name: str = "trusted_cross_solver_agreement",
    ) -> ValidationCheck:
        return self.assess(consensus, evidence, name=name).require_validated()


__all__ = ["TrustedConsensusDecision", "TrustedConsensusGate"]
