"""Explicit migrations for Composition/Execution multiphysics authority.

Migration is intentionally conservative: schema shape may be upgraded when the
old record contains enough information. Scientific authority that did not exist
in the source record is never invented; such migrations are marked not ready
for production certification until re-admitted against current providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..executionpacks.manifest import (
    EXECUTION_PACK_SCHEMA,
    EXECUTION_PACK_SCHEMA_V1,
    ExecutionPackManifest,
)
from ..executionpacks.snapshot import (
    EXECUTION_SNAPSHOT_SCHEMA,
    EXECUTION_SNAPSHOT_SCHEMA_V1,
    ExecutionPackSnapshot,
)
from ..scientific.multiphysics import (
    PARTICIPANT_SCHEMA,
    PARTICIPANT_SCHEMA_V1,
    ParticipantSpec,
)
from ..scientific.results.uncertainty import UncertaintySource
from .blueprint import (
    COUPLING_POLICY_TEMPLATE_SCHEMA,
    COUPLING_POLICY_TEMPLATE_SCHEMA_V1,
    CouplingPolicyTemplate,
)
from .manifest import (
    COMPOSITION_PACK_SCHEMA,
    COMPOSITION_PACK_SCHEMA_V1,
    CompositionPackManifest,
)
from .snapshot import (
    COMPOSITION_SNAPSHOT_SCHEMA,
    COMPOSITION_SNAPSHOT_SCHEMA_V1,
    COMPOSITION_SNAPSHOT_SCHEMA_V2,
    CompositionPackSnapshot,
)


@dataclass(frozen=True)
class MigrationResult:
    source_schema: str
    target_schema: str
    payload: dict[str, Any]
    production_ready: bool
    notes: tuple[str, ...] = ()


def _schema(payload: Mapping[str, Any]) -> str:
    value = str(payload.get("schema", "")).strip()
    if not value:
        raise ValueError("migration source record has no schema")
    return value


def migrate_composition_manifest(
    payload: Mapping[str, Any],
) -> MigrationResult:
    source = _schema(payload)
    if source not in (
        COMPOSITION_PACK_SCHEMA_V1,
        COMPOSITION_PACK_SCHEMA,
    ):
        raise ValueError(
            f"unsupported CompositionPack migration source {source!r}"
        )
    made = CompositionPackManifest.from_dict(payload)
    upgraded = made.to_dict()
    missing_current_authority = (
        not upgraded["uncertainty_protocols"]
        or not upgraded["verification_protocols"]
    )
    return MigrationResult(
        source_schema=source,
        target_schema=COMPOSITION_PACK_SCHEMA,
        payload=upgraded,
        production_ready=not missing_current_authority,
        notes=(
            (
                "v1 did not carry system UQ/verification protocol pins; "
                "re-register the live provider under current admission to "
                "supply those authorities"
            ),
        )
        if missing_current_authority
        else (),
    )


def migrate_execution_manifest(
    payload: Mapping[str, Any],
) -> MigrationResult:
    source = _schema(payload)
    if source not in (
        EXECUTION_PACK_SCHEMA_V1,
        EXECUTION_PACK_SCHEMA,
    ):
        raise ValueError(
            f"unsupported ExecutionPack migration source {source!r}"
        )
    made = ExecutionPackManifest.from_dict(payload)
    upgraded = made.to_dict()
    legacy = source == EXECUTION_PACK_SCHEMA_V1
    return MigrationResult(
        source_schema=source,
        target_schema=EXECUTION_PACK_SCHEMA,
        payload=upgraded,
        production_ready=not legacy,
        notes=(
            (
                "v1 factory records identify only one model. The migration "
                "preserves that exact single-model meaning; re-admit against "
                "a current CompositionPack before production use so any "
                "multi-model subsystem assembly is explicit."
            ),
        )
        if legacy
        else (),
    )


def migrate_execution_snapshot(
    payload: Mapping[str, Any],
) -> MigrationResult:
    source = _schema(payload)
    if source not in (
        EXECUTION_SNAPSHOT_SCHEMA_V1,
        EXECUTION_SNAPSHOT_SCHEMA,
    ):
        raise ValueError(
            f"unsupported ExecutionPackSnapshot migration source {source!r}"
        )
    made = ExecutionPackSnapshot.from_dict(payload)
    upgraded = made.to_dict()
    legacy = source == EXECUTION_SNAPSHOT_SCHEMA_V1
    return MigrationResult(
        source_schema=source,
        target_schema=EXECUTION_SNAPSHOT_SCHEMA,
        payload=upgraded,
        production_ready=not legacy,
        notes=(
            (
                "legacy execution snapshot predates explicit participant "
                "model assemblies; preserve it as historical provenance and "
                "regenerate from the admitted ExecutionPack for certification"
            ),
        )
        if legacy
        else (),
    )


def migrate_participant_spec(
    payload: Mapping[str, Any],
) -> MigrationResult:
    source = _schema(payload)
    if source not in (PARTICIPANT_SCHEMA_V1, PARTICIPANT_SCHEMA):
        raise ValueError(
            f"unsupported ParticipantSpec migration source {source!r}"
        )
    made = ParticipantSpec.from_dict(payload)
    return MigrationResult(
        source_schema=source,
        target_schema=PARTICIPANT_SCHEMA,
        payload=made.to_dict(),
        production_ready=True,
        notes=(
            (
                "legacy one-model participant was preserved exactly as a "
                "one-member model assembly"
            ),
        )
        if source == PARTICIPANT_SCHEMA_V1
        else (),
    )


def migrate_coupling_policy(
    payload: Mapping[str, Any],
) -> MigrationResult:
    source = _schema(payload)
    if source not in (
        COUPLING_POLICY_TEMPLATE_SCHEMA_V1,
        COUPLING_POLICY_TEMPLATE_SCHEMA,
    ):
        raise ValueError(
            f"unsupported CouplingPolicy migration source {source!r}"
        )
    made = CouplingPolicyTemplate.from_dict(payload)
    return MigrationResult(
        source_schema=source,
        target_schema=COUPLING_POLICY_TEMPLATE_SCHEMA,
        payload=made.to_dict(),
        production_ready=True,
        notes=(
            (
                "legacy fixed coupling_window is preserved as an explicit "
                "FIXED CouplingWindowRule; no new timestep rationale is "
                "invented by migration"
            ),
        )
        if source == COUPLING_POLICY_TEMPLATE_SCHEMA_V1
        else (),
    )


def migrate_composition_snapshot(
    payload: Mapping[str, Any],
) -> MigrationResult:
    source = _schema(payload)
    if source not in (
        COMPOSITION_SNAPSHOT_SCHEMA_V1,
        COMPOSITION_SNAPSHOT_SCHEMA_V2,
        COMPOSITION_SNAPSHOT_SCHEMA,
    ):
        raise ValueError(
            f"unsupported CompositionPackSnapshot migration source {source!r}"
        )
    made = CompositionPackSnapshot.from_dict(payload)
    upgraded = made.to_dict()
    ready = bool(upgraded.get("semantic_authority"))
    return MigrationResult(
        source_schema=source,
        target_schema=COMPOSITION_SNAPSHOT_SCHEMA,
        payload=upgraded,
        production_ready=ready,
        notes=(
            ()
            if ready
            else (
                "legacy snapshot has no canonical composition semantic "
                "authority; regenerate it by re-registering the exact live "
                "CompositionPack rather than inventing semantic provenance",
            )
        ),
    )


def migrate_authorized_run(
    payload: Mapping[str, Any],
) -> MigrationResult:
    from ..assembly.multiphysics import AuthorizedMultiphysicsRun

    source = _schema(payload)
    made = AuthorizedMultiphysicsRun.from_dict(payload)
    upgraded = made.to_dict()
    parameter_uq_requested = any(
        item.uncertainty.is_quantified
        and item.uncertainty.source_kind is UncertaintySource.PARAMETER
        for item in made.run.external_inputs
    )
    ready = bool(
        made.system_verification
        and made.composition_snapshot.semantic_authority
        and (
            not parameter_uq_requested
            or made.system_uncertainty
        )
    )
    return MigrationResult(
        source_schema=source,
        target_schema=upgraded["schema"],
        payload=upgraded,
        production_ready=ready,
        notes=(
            ()
            if ready
            else (
                "legacy authorized run lacks one or more current production "
                "authorities (required system UQ, independent verification, "
                "semantic snapshot); preserve it as historical evidence and re-run "
                "under current authority for certification",
            )
        ),
    )


__all__ = [
    "MigrationResult",
    "migrate_authorized_run",
    "migrate_composition_manifest",
    "migrate_composition_snapshot",
    "migrate_coupling_policy",
    "migrate_execution_manifest",
    "migrate_execution_snapshot",
    "migrate_participant_spec",
]
