"""Execution admission for a planned PhysicsGraph.

Admission is intentionally separate from execution. It proves that the
CouplingPlan is compatible with the graph and reports whether every declared
participant can be materialized by an exact execution factory.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from ...scientific.serialization import require_schema, schema_string
from ...scientific.multiphysics import (
    CouplingPlan,
    GraphInterfaceManifest,
    PhysicsGraph,
    graph_interface_manifest,
)
from .factory import ParticipantFactoryCoverage, ParticipantFactoryRegistry

MULTIPHYSICS_EXECUTION_ADMISSION_SCHEMA = schema_string(
    "multiphysics_execution_admission"
)


@dataclass(frozen=True)
class MultiphysicsExecutionAdmission:
    graph_interface: GraphInterfaceManifest
    plan_id: str
    plan_fingerprint: str
    factory_registry_fingerprint: str
    factory_coverage: tuple[ParticipantFactoryCoverage, ...]

    @property
    def executable(self) -> bool:
        return all(item.available for item in self.factory_coverage)

    @property
    def missing_participants(self) -> tuple[str, ...]:
        return tuple(
            item.participant_id
            for item in self.factory_coverage
            if not item.available
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MULTIPHYSICS_EXECUTION_ADMISSION_SCHEMA,
            "graph_interface": self.graph_interface.to_dict(),
            "plan_id": self.plan_id,
            "plan_fingerprint": self.plan_fingerprint,
            "factory_registry_fingerprint": self.factory_registry_fingerprint,
            "factory_coverage": [
                item.to_dict() for item in self.factory_coverage
            ],
            "executable": self.executable,
            "missing_participants": list(self.missing_participants),
            "record_fingerprint": self.fingerprint,
        }

    @property
    def fingerprint(self) -> str:
        payload = {
            key: value
            for key, value in self.to_dict().items()
            if key != "record_fingerprint"
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "MultiphysicsExecutionAdmission":
        require_schema(
            payload,
            MULTIPHYSICS_EXECUTION_ADMISSION_SCHEMA,
        )
        made = cls(
            graph_interface=GraphInterfaceManifest.from_dict(
                payload["graph_interface"]
            ),
            plan_id=payload["plan_id"],
            plan_fingerprint=payload["plan_fingerprint"],
            factory_registry_fingerprint=payload[
                "factory_registry_fingerprint"
            ],
            factory_coverage=tuple(
                ParticipantFactoryCoverage.from_dict(item)
                for item in payload.get("factory_coverage", ())
            ),
        )
        supplied = payload.get("record_fingerprint")
        if supplied is not None and supplied != made.fingerprint:
            raise ValueError(
                "multiphysics execution admission fingerprint "
                "disagrees with its content"
            )
        return made


def admit_multiphysics_execution(
    graph: PhysicsGraph,
    plan: CouplingPlan,
    registry: ParticipantFactoryRegistry,
) -> MultiphysicsExecutionAdmission:
    if not isinstance(graph, PhysicsGraph):
        raise TypeError("admission requires PhysicsGraph")
    if not isinstance(plan, CouplingPlan):
        raise TypeError("admission requires CouplingPlan")
    if not isinstance(registry, ParticipantFactoryRegistry):
        raise TypeError(
            "admission requires ParticipantFactoryRegistry"
        )

    # Fail closed on an invalid numerical/execution policy before checking
    # factories. This keeps topology/policy errors distinct from deployment
    # availability.
    plan.validate_against(graph)

    return MultiphysicsExecutionAdmission(
        graph_interface=graph_interface_manifest(graph),
        plan_id=plan.plan_id,
        plan_fingerprint=plan.fingerprint(),
        factory_registry_fingerprint=registry.fingerprint,
        factory_coverage=registry.coverage(graph),
    )


__all__ = [
    "MULTIPHYSICS_EXECUTION_ADMISSION_SCHEMA",
    "MultiphysicsExecutionAdmission",
    "admit_multiphysics_execution",
]
