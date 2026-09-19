from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MigrationDecision(str, Enum):
    SAME_SCHEMA = "same_schema"
    EXPLICIT_MIGRATION_REQUIRED = "explicit_migration_required"
    REFUSED = "refused"


@dataclass(frozen=True)
class MigrationAssessment:
    decision: MigrationDecision
    reason: str


def assess_migration(source_schema: str, target_schema: str, *, migration_available: bool=False) -> MigrationAssessment:
    if source_schema == target_schema:
        return MigrationAssessment(MigrationDecision.SAME_SCHEMA, "schema identity matches")
    if migration_available:
        return MigrationAssessment(MigrationDecision.EXPLICIT_MIGRATION_REQUIRED, "schema differs and an explicit migration exists")
    return MigrationAssessment(MigrationDecision.REFUSED, "schema differs and no explicit migration was declared")
