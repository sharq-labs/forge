from __future__ import annotations

from ...scientific.discovery import (
    GeneratedHypothesis,
    GeneratedHypothesisKind,
)
from .hypotheses import Hypothesis


def generated_to_sria_hypothesis(
    generated: GeneratedHypothesis,
) -> Hypothesis:
    """Expose a generated scientific candidate to SRIA without promoting it.

    The model_ref is a content identity for the candidate hypothesis, not a
    claim that a production model already exists.
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
    )


__all__ = ["generated_to_sria_hypothesis"]
