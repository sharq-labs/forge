"""Execute a planned multiphysics graph against exact registered authority."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from ..compositionpacks.contracts import SystemValidationResult
from ..compositionpacks.participant import ParticipantBinding
from ..compositionpacks.registry import CompositionPackRegistry
from ..compositionpacks.snapshot import (
    CompositionPackSnapshot,
    snapshot_composition_pack,
)
from ..data.resolver import BulkDataResolver
from ..data.store import BulkDataStore
from ..execution.multiphysics import (
    MultiphysicsRuntime,
    ParticipantFactoryRegistry,
)
from ..executionpacks.registry import ExecutionPackRegistry
from ..executionpacks.snapshot import (
    ExecutionPackSnapshot,
    snapshot_execution_pack,
)
from ..planning.records import GraphPlan
from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics import MultiphysicsRunRecord
from ..scientific.serialization import schema_string

AUTHORIZED_RUN_SCHEMA = schema_string("authorized_multiphysics_run")


@dataclass(frozen=True)
class AuthorizedSystemValidation:
    protocol_id: str
    protocol_version: str
    result: SystemValidationResult

    def __post_init__(self) -> None:
        for label in ("protocol_id", "protocol_version"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"authorized system validation requires {label}"
                )
            object.__setattr__(self, label, value)
        if not isinstance(self.result, SystemValidationResult):
            raise InvalidScientificProblem(
                "authorized system validation requires SystemValidationResult"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "result": self.result.to_dict(),
        }


@dataclass(frozen=True)
class AuthorizedMultiphysicsRun:
    graph_plan: GraphPlan
    composition_snapshot: CompositionPackSnapshot
    execution_snapshot: ExecutionPackSnapshot
    run: MultiphysicsRunRecord
    system_validation: tuple[AuthorizedSystemValidation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.graph_plan, GraphPlan):
            raise TypeError("authorized run requires GraphPlan")
        if not isinstance(
            self.composition_snapshot,
            CompositionPackSnapshot,
        ):
            raise TypeError(
                "authorized run requires CompositionPackSnapshot"
            )
        if not isinstance(
            self.execution_snapshot,
            ExecutionPackSnapshot,
        ):
            raise TypeError(
                "authorized run requires ExecutionPackSnapshot"
            )
        if not isinstance(self.run, MultiphysicsRunRecord):
            raise TypeError(
                "authorized run requires MultiphysicsRunRecord"
            )
        validations = tuple(self.system_validation)
        if any(
            not isinstance(item, AuthorizedSystemValidation)
            for item in validations
        ):
            raise TypeError(
                "system_validation must contain AuthorizedSystemValidation"
            )
        object.__setattr__(
            self,
            "system_validation",
            tuple(
                sorted(
                    validations,
                    key=lambda item: (
                        item.protocol_id,
                        item.protocol_version,
                    ),
                )
            ),
        )

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema": AUTHORIZED_RUN_SCHEMA,
            "graph_plan": self.graph_plan.to_dict(),
            "composition_snapshot": self.composition_snapshot.to_dict(),
            "execution_snapshot": self.execution_snapshot.to_dict(),
            "run": self.run.to_dict(),
            "system_validation": [
                item.to_dict() for item in self.system_validation
            ],
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self._content_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._content_dict(),
            "record_digest": self.digest,
        }


def _composition_blueprint(registration, graph_plan: GraphPlan):
    matches = tuple(
        item
        for item in registration.blueprints
        if (
            item.blueprint_id == graph_plan.blueprint_id
            and item.version == graph_plan.blueprint_version
        )
    )
    if len(matches) != 1:
        raise InvalidScientificProblem(
            "GraphPlan blueprint does not resolve to one exact "
            "CompositionPack blueprint"
        )
    return matches[0]


def _verify_graph_authority(registration, graph_plan: GraphPlan) -> None:
    blueprint = _composition_blueprint(registration, graph_plan)
    bindings = {
        participant.participant_id: ParticipantBinding(
            participant_id=participant.participant_id,
            realization_id=participant.realization_id,
            realization_version=participant.realization_version,
            solver_id=participant.solver_id,
            solver_version=participant.solver_version,
        )
        for participant in graph_plan.graph.participants
    }
    expected = blueprint.materialize(
        bindings,
        graph_id=graph_plan.graph.graph_id,
    )
    if expected != graph_plan.graph:
        raise InvalidScientificProblem(
            "GraphPlan PhysicsGraph differs from the selected "
            "CompositionPack topology"
        )

    policies = tuple(
        item
        for item in registration.coupling_policy_templates
        if (
            item.template_id
            == graph_plan.coupling_policy_template_id
            and item.version
            == graph_plan.coupling_policy_template_version
            and item.blueprint_id == graph_plan.blueprint_id
        )
    )
    if len(policies) != 1:
        raise InvalidScientificProblem(
            "GraphPlan coupling policy does not resolve to one exact "
            "CompositionPack policy template"
        )
    if graph_plan.coupling_plan is None:
        raise InvalidScientificProblem(
            "GraphPlan has no materialized CouplingPlan"
        )
    expected_plan = policies[0].materialize(
        start=graph_plan.coupling_plan.time.start,
        end=graph_plan.coupling_plan.time.end,
        plan_id=graph_plan.coupling_plan.plan_id,
    )
    if expected_plan != graph_plan.coupling_plan:
        raise InvalidScientificProblem(
            "GraphPlan CouplingPlan differs from its authoritative "
            "CouplingPolicyTemplate"
        )


def execute_authorized_graph_plan(
    graph_plan: GraphPlan,
    *,
    run_id: str,
    compositions: CompositionPackRegistry,
    executions: ExecutionPackRegistry,
    resolver: BulkDataResolver,
    store: BulkDataStore,
) -> AuthorizedMultiphysicsRun:
    """Execute one ready GraphPlan without re-selecting scientific authority."""

    if not isinstance(graph_plan, GraphPlan):
        raise TypeError("execute_authorized_graph_plan requires GraphPlan")
    if not graph_plan.executable:
        raise InvalidScientificProblem(
            "GraphPlan is not executable; resolve its planning gaps first"
        )
    if not graph_plan.authority_pack_id:
        raise InvalidScientificProblem(
            "GraphPlan has no CompositionPack authority"
        )
    if not graph_plan.execution_pack_id:
        raise InvalidScientificProblem(
            "GraphPlan has no ExecutionPack authority"
        )

    composition = compositions.get(
        graph_plan.authority_pack_id,
        graph_plan.authority_pack_version,
        require_enabled=True,
    )
    if composition.authority_digest != graph_plan.authority_pack_digest:
        raise InvalidScientificProblem(
            "CompositionPack authority digest changed since planning"
        )

    execution = executions.get(
        graph_plan.execution_pack_id,
        graph_plan.execution_pack_version,
        require_enabled=True,
    )
    if execution.authority_digest != graph_plan.execution_pack_digest:
        raise InvalidScientificProblem(
            "ExecutionPack authority digest changed since planning"
        )
    if (
        execution.composition_authority_digest
        != composition.authority_digest
    ):
        raise InvalidScientificProblem(
            "ExecutionPack was admitted against another CompositionPack "
            "authority snapshot"
        )

    _verify_graph_authority(composition, graph_plan)

    factories = ParticipantFactoryRegistry(
        execution.participant_factories
    )
    if factories.fingerprint != graph_plan.execution_registry_fingerprint:
        raise InvalidScientificProblem(
            "participant factory registry fingerprint changed since planning"
        )
    missing = factories.missing(graph_plan.graph)
    if missing:
        raise InvalidScientificProblem(
            "ExecutionPack no longer covers GraphPlan participants "
            f"{[item.participant_id for item in missing]}"
        )

    runtime = MultiphysicsRuntime.from_factory_registry(
        graph_plan.graph,
        graph_plan.coupling_plan,
        factories,
        resolver=resolver,
        store=store,
    )
    run = runtime.run(
        run_id,
        external_inputs={
            item.port: item.value
            for item in graph_plan.external_inputs
        },
    )

    validation: list[AuthorizedSystemValidation] = []
    for protocol in composition.validation_protocols:
        if protocol.blueprint_id != graph_plan.blueprint_id:
            continue
        result = protocol.implementation(run)
        if not isinstance(result, SystemValidationResult):
            raise InvalidScientificProblem(
                f"composition validation {protocol.ref.artifact_id}@"
                f"{protocol.ref.version} returned "
                f"{type(result).__name__}, expected SystemValidationResult"
            )
        validation.append(
            AuthorizedSystemValidation(
                protocol.ref.artifact_id,
                protocol.ref.version,
                result,
            )
        )
    if not validation:
        raise InvalidScientificProblem(
            "selected CompositionPack has no validation protocol for "
            "the executed blueprint"
        )

    return AuthorizedMultiphysicsRun(
        graph_plan=graph_plan,
        composition_snapshot=snapshot_composition_pack(composition),
        execution_snapshot=snapshot_execution_pack(execution),
        run=run,
        system_validation=tuple(validation),
    )


__all__ = [
    "AUTHORIZED_RUN_SCHEMA",
    "AuthorizedMultiphysicsRun",
    "AuthorizedSystemValidation",
    "execute_authorized_graph_plan",
]
