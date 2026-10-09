from __future__ import annotations

from ...scientific.discovery import (
    GeneratedHypothesis,
    GeneratedHypothesisKind,
)
from .hypotheses import Hypothesis, HypothesisKind, ProposalProvenance, ProposerKind

#: GeneratedHypothesisKind (certified scientific.discovery record) -> canonical kind.  An outlier-process
#: hypothesis is a claim about the data's generating structure, not a mechanism.
KIND_OF_GENERATED = {
    GeneratedHypothesisKind.EQUATION: HypothesisKind.EQUATION,
    GeneratedHypothesisKind.REGIME_CHANGE: HypothesisKind.REGIME_BOUNDARY,
    GeneratedHypothesisKind.OUTLIER_PROCESS: HypothesisKind.MODEL_STRUCTURE,
}


def generated_to_sria_hypothesis(
    generated: GeneratedHypothesis,
) -> Hypothesis:
    """Expose a generated scientific candidate to SRIA without promoting it.

    The model_ref is a content identity for the candidate hypothesis, not a
    claim that a production model already exists.  The kind is kept (Roadmap V2);
    the status is PROPOSED whatever the legacy candidate's holdout status was: a
    holdout scored inside the search that produced the candidate is not a sealed
    falsifier verdict.
    """
    model_ref = (
        f"discovery-candidate:{generated.candidate_fingerprint}"
        if generated.candidate_fingerprint
        else f"generated-hypothesis:{generated.hypothesis_id}"
    )
    return Hypothesis(
        hypothesis_id=generated.hypothesis_id,
        model_ref=model_ref,
        description=generated.statement,
        weight=None,
        scope_ref=generated.context_digest,
        evidence_links=generated.evidence_digests,
        kind=KIND_OF_GENERATED[generated.kind],
        statement=generated.statement,
        structure_digest=generated.candidate_fingerprint,
        proposal=ProposalProvenance(ProposerKind.LEGACY_ADAPTER, "scientific.discovery.hypothesis_generation",
                                    note="adapted from GeneratedHypothesis; legacy holdout status is not a V2 verdict"),
    )


__all__ = ["KIND_OF_GENERATED", "generated_to_sria_hypothesis"]
