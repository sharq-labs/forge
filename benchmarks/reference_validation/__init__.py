"""External-reference validation campaign infrastructure.

This package is intentionally outside ``engcore.scientific``.  The Scientific
Core remains offline and only consumes frozen, content-addressed oracle
evidence after review.
"""

from .catalog import (
    FIRST_FOUR_SOURCES,
    NASA_BATTERY_AGING,
    NAFEMS_THERMAL,
    NIST_CHEMICAL_KINETICS,
    NIST_SRD69,
    source_by_id,
)
from .contracts import (
    ReferenceCondition,
    ReferenceDataset,
    ReferencePoint,
    ReferenceSourceSpec,
    ToleranceSpec,
)
from .metrics import (
    CampaignCaseResult,
    CampaignReport,
    CampaignStatus,
    score_reference_dataset,
)
from .snapshot import SnapshotManifest, acquire_snapshot, load_snapshot

__all__ = [
    "CampaignCaseResult",
    "CampaignReport",
    "CampaignStatus",
    "FIRST_FOUR_SOURCES",
    "NASA_BATTERY_AGING",
    "NAFEMS_THERMAL",
    "NIST_CHEMICAL_KINETICS",
    "NIST_SRD69",
    "ReferenceCondition",
    "ReferenceDataset",
    "ReferencePoint",
    "ReferenceSourceSpec",
    "SnapshotManifest",
    "ToleranceSpec",
    "acquire_snapshot",
    "load_snapshot",
    "score_reference_dataset",
    "source_by_id",
]
