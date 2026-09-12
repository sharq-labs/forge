"""Study-bounded scientific model adequacy and comparison capabilities.

STATUS: NOT ON THE VERIFICATION PATH, AND IMPORTED BY NOTHING IN ``src/``.
=============================================================================
The same condition as ``src/engcore/sria/``, at 579 lines across two modules
instead of 19,887 across 53, and stated here for the same reason: a reader
meeting this package has no other way to find out.

**Direction of the dependency.** Nothing under ``src/`` imports
``engcore.adequacy``. Its only consumer in the repository is
``tests/test_k4_model_adequacy.py``, which exercises it directly. No verdict,
no validity assessment and no credibility evidence report passes through it,
so nothing this repository publishes would move if it were absent.

**Not the same thing as the word "adequacy" elsewhere.** ``domains/kinetics``,
``inference/`` and ``sria/campaign`` all discuss *numerical* adequacy — whether
a tolerance supports a claim — and none of them imports this package. What
lives here is *model* adequacy: comparing candidate models by log predictive
score over a study's own observations. The shared word is why grepping for
"adequacy" makes this look connected when it is not.

**Why it is still here, and how it differs from ``sria/``.** Unlike SRIA, no
byte-pinned module imports it, so moving this package would break no frozen
experiment — the obstacle is not a pin but the absence of a decision about
where a non-platform capability should live. It is left in place and labelled
rather than moved on one round's initiative.
=============================================================================
"""

from .predictive import (
    EVIDENCE_IDENTITY_FIELDS,
    ModelAdequacyError,
    ModelScoreComparison,
    PredictiveEvidenceIdentity,
    PredictiveObservationAssessment,
    StudyAdequacyStatus,
    assess_predictive_observation,
    compare_log_predictive_scores,
)

__all__ = [
    "EVIDENCE_IDENTITY_FIELDS",
    "ModelAdequacyError",
    "ModelScoreComparison",
    "PredictiveEvidenceIdentity",
    "PredictiveObservationAssessment",
    "StudyAdequacyStatus",
    "assess_predictive_observation",
    "compare_log_predictive_scores",
]
