"""Engineering output layer (BIG 13): references, verification ladder, engineering summary, run bundle, viewable fields.

Sits above :mod:`engcore.system_runtime` and adds no execution, no solver and no trust vocabulary.  The
scientific status shown in a summary is the existing credibility verdict; a verification ladder is a report
of where evidence stops, not a validation grant.
"""

from .bundle import BundleManifest, BundleRefused, verify_bundle, write_bundle
from .fieldio import extrema, l2_norm, values_digest, write_vtu
from .ladder import EvidenceLink, LevelEntry, LevelStatus, VerificationLadder
from .reference import (
    EnvelopeBound, PredeclaredCriterion, ReferenceApplicability, ReferenceComparison, ReferenceCondition, ReferenceRecord, compare_to_reference,
)
from .summary import ConstraintLine, EngineeringSummary, KeyOutput, UncertaintyStatement, build_summary

__all__ = [
    "BundleManifest", "BundleRefused", "verify_bundle", "write_bundle", "extrema", "l2_norm", "values_digest", "write_vtu",
    "EvidenceLink", "LevelEntry", "LevelStatus", "VerificationLadder",
    "EnvelopeBound", "PredeclaredCriterion", "ReferenceApplicability", "ReferenceComparison", "ReferenceCondition", "ReferenceRecord",
    "compare_to_reference", "ConstraintLine", "EngineeringSummary", "KeyOutput", "UncertaintyStatement", "build_summary",
]
