"""Serializable records for deterministic engineering planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..claims._records import tagged_digest
from ..claims.capabilities import CapabilityRegistry
from ..design.fidelity import FidelityLadder
from ..scientific.models.registry import ModelRegistry
from ..scientific.multiphysics import (
    CouplingPlan,
    GraphInterfaceManifest,
    PortRef,
    coupling_value_from_dict,
    coupling_value_to_dict,
    PhysicsGraph,
    graph_interface_manifest,
)
from ..scientific.realizations.registry import RealizationRegistry
from ..scientific.serialization import require_schema, require_schema_any, schema_string
from ..scientific.solvers.registry import SolverRegistry
from ..scientific.units.quantity import Quantity
from ..scenarios import ScenarioSpecification
from .blueprint import BlueprintRegistry
from .clarification import ClarificationQuestion
from .verification import VerificationPlanningRegistry

SCIENTIFIC_PLAN_SCHEMA_V1 = schema_string("scientific_planning_record")
SCIENTIFIC_PLAN_SCHEMA = schema_string("scientific_planning_record", 2)
QOI_PLAN_SCHEMA = schema_string("scientific_qoi_plan")
MODEL_CHOICE_SCHEMA = schema_string("scientific_model_execution_choice")
PLANNING_GAP_SCHEMA = schema_string("scientific_planning_gap")
FIDELITY_DECISION_SCHEMA = schema_string("scientific_fidelity_decision")
RESOURCE_ESTIMATE_SCHEMA = schema_string("scientific_resource_estimate")
GRAPH_PLAN_SCHEMA_V1 = schema_string("scientific_graph_plan")
GRAPH_PLAN_SCHEMA_V2 = schema_string("scientific_graph_plan", 2)
GRAPH_PLAN_SCHEMA = schema_string("scientific_graph_plan", 3)
PLANNED_EXTERNAL_INPUT_SCHEMA = schema_string("planned_external_input")
_TAG_V1 = "forge.scientific_planning_record/1"
_TAG = "forge.scientific_planning_record/2"


class PlanningStatus(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


class ExecutionMode(str, Enum):
    CAPABILITY_ROUTE = "capability_route"
    MULTIPHYSICS_GRAPH = "multiphysics_graph"


class GapKind(str, Enum):
    MODEL_REGISTRY_MISSING = "model_registry_missing"
    MODEL_NOT_REGISTERED = "model_not_registered"
    REALIZATION_REGISTRY_MISSING = "realization_registry_missing"
    REALIZATION_NOT_FOUND = "realization_not_found"
    REALIZATION_AMBIGUOUS = "realization_ambiguous"
    REALIZATION_CAPABILITY_UNSATISFIED = (
        "realization_capability_unsatisfied"
    )
    SOLVER_REGISTRY_MISSING = "solver_registry_missing"
    SOLVER_NOT_FOUND = "solver_not_found"
    SOLVER_AMBIGUOUS = "solver_ambiguous"
    GRAPH_BLUEPRINT_UNAVAILABLE = "graph_blueprint_unavailable"
    GRAPH_BLUEPRINT_AMBIGUOUS = "graph_blueprint_ambiguous"
    COMPOSITION_PACK_AMBIGUOUS = "composition_pack_ambiguous"
    COUPLING_POLICY_AMBIGUOUS = "coupling_policy_ambiguous"
    COUPLING_POLICY_UNSATISFIED = "coupling_policy_unsatisfied"
    SIMULATION_HORIZON_REQUIRED = "simulation_horizon_required"
    EXECUTION_PACK_UNAVAILABLE = "execution_pack_unavailable"
    EXECUTION_PACK_AMBIGUOUS = "execution_pack_ambiguous"
    EXECUTION_FACTORY_UNAVAILABLE = "execution_factory_unavailable"
    GRAPH_EXTERNAL_INPUT_MISSING = "graph_external_input_missing"
    GRAPH_EXTERNAL_INPUT_INVALID = "graph_external_input_invalid"
    SYSTEM_APPLICABILITY_EVIDENCE_MISSING = (
        "system_applicability_evidence_missing"
    )
    SYSTEM_APPLICABILITY_UNKNOWN = "system_applicability_unknown"
    SYSTEM_APPLICABILITY_VIOLATED = "system_applicability_violated"
    SYSTEM_UNCERTAINTY_COMPOSITION_UNAVAILABLE = (
        "system_uncertainty_composition_unavailable"
    )
    FIDELITY_LADDER_MISSING = "fidelity_ladder_missing"
    FIDELITY_UNAVAILABLE = "fidelity_unavailable"
    EVIDENCE_GAP = "evidence_gap"
    UNCERTAINTY_GAP = "uncertainty_gap"
    RESOURCE_ESTIMATE_UNAVAILABLE = "resource_estimate_unavailable"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass(frozen=True)
class PlanningGap:
    kind: GapKind
    subject: str
    detail: str
    blocking: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", GapKind(self.kind))
        for label in ("subject", "detail"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"planning gap requires {label}")
            object.__setattr__(self, label, value)
        if not isinstance(self.blocking, bool):
            raise ValueError("planning gap blocking must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLANNING_GAP_SCHEMA,
            "kind": self.kind.value,
            "subject": self.subject,
            "detail": self.detail,
            "blocking": self.blocking,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlanningGap":
        require_schema(payload, PLANNING_GAP_SCHEMA)
        return cls(
            GapKind(payload["kind"]),
            payload["subject"],
            payload["detail"],
            payload["blocking"],
        )


@dataclass(frozen=True)
class ModelExecutionChoice:
    model_id: str
    model_version: str
    realization_candidates: tuple[str, ...]
    selected_realization: str | None
    solver_candidates: tuple[str, ...]
    selected_solver: str | None
    selected_realization_capabilities: tuple[str, ...] = ()
    selected_solver_capabilities: tuple[str, ...] = ()
    selection_basis: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label in ("model_id", "model_version"):
            if not str(getattr(self, label)).strip():
                raise ValueError(f"model choice requires {label}")
        for label in (
            "realization_candidates",
            "solver_candidates",
            "selected_realization_capabilities",
            "selected_solver_capabilities",
            "selection_basis",
        ):
            object.__setattr__(
                self,
                label,
                tuple(sorted(set(str(x) for x in getattr(self, label)))),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MODEL_CHOICE_SCHEMA,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "realization_candidates": list(self.realization_candidates),
            "selected_realization": self.selected_realization,
            "solver_candidates": list(self.solver_candidates),
            "selected_solver": self.selected_solver,
            "selected_realization_capabilities": list(
                self.selected_realization_capabilities
            ),
            "selected_solver_capabilities": list(
                self.selected_solver_capabilities
            ),
            "selection_basis": list(self.selection_basis),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelExecutionChoice":
        require_schema(payload, MODEL_CHOICE_SCHEMA)
        return cls(
            payload["model_id"],
            payload["model_version"],
            tuple(payload.get("realization_candidates", ())),
            payload.get("selected_realization"),
            tuple(payload.get("solver_candidates", ())),
            payload.get("selected_solver"),
            tuple(payload.get("selected_realization_capabilities", ())),
            tuple(payload.get("selected_solver_capabilities", ())),
            tuple(payload.get("selection_basis", ())),
        )


@dataclass(frozen=True)
class QOIPlan:
    qoi_id: str
    capability_id: str
    capability_version: str
    capability_digest: str
    execution_mode: ExecutionMode
    primary_route_id: str
    provided_capabilities: tuple[str, ...]
    model_choices: tuple[ModelExecutionChoice, ...]
    required_inputs: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    required_levels: tuple[str, ...]
    attainable_levels: tuple[str, ...]
    required_uncertainty: tuple[str, ...]
    quantified_uncertainty: tuple[str, ...]
    alternatives: tuple[str, ...]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "execution_mode", ExecutionMode(self.execution_mode)
        )
        for label in (
            "qoi_id",
            "capability_id",
            "capability_version",
            "capability_digest",
            "primary_route_id",
        ):
            if not str(getattr(self, label)).strip():
                raise ValueError(f"qoi plan requires {label}")
        object.__setattr__(
            self,
            "model_choices",
            tuple(sorted(self.model_choices, key=lambda x: x.model_id)),
        )
        for label in (
            "provided_capabilities",
            "required_inputs",
            "missing_inputs",
            "required_levels",
            "attainable_levels",
            "required_uncertainty",
            "quantified_uncertainty",
            "alternatives",
            "reasons",
        ):
            object.__setattr__(
                self,
                label,
                tuple(sorted(set(str(x) for x in getattr(self, label)))),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": QOI_PLAN_SCHEMA,
            "qoi_id": self.qoi_id,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "capability_digest": self.capability_digest,
            "execution_mode": self.execution_mode.value,
            "primary_route_id": self.primary_route_id,
            "provided_capabilities": list(self.provided_capabilities),
            "model_choices": [x.to_dict() for x in self.model_choices],
            "required_inputs": list(self.required_inputs),
            "missing_inputs": list(self.missing_inputs),
            "required_levels": list(self.required_levels),
            "attainable_levels": list(self.attainable_levels),
            "required_uncertainty": list(self.required_uncertainty),
            "quantified_uncertainty": list(self.quantified_uncertainty),
            "alternatives": list(self.alternatives),
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QOIPlan":
        require_schema(payload, QOI_PLAN_SCHEMA)
        return cls(
            qoi_id=payload["qoi_id"],
            capability_id=payload["capability_id"],
            capability_version=payload["capability_version"],
            capability_digest=payload["capability_digest"],
            execution_mode=ExecutionMode(payload["execution_mode"]),
            primary_route_id=payload["primary_route_id"],
            provided_capabilities=tuple(
                payload.get("provided_capabilities", ())
            ),
            model_choices=tuple(
                ModelExecutionChoice.from_dict(x)
                for x in payload.get("model_choices", ())
            ),
            required_inputs=tuple(payload.get("required_inputs", ())),
            missing_inputs=tuple(payload.get("missing_inputs", ())),
            required_levels=tuple(payload.get("required_levels", ())),
            attainable_levels=tuple(payload.get("attainable_levels", ())),
            required_uncertainty=tuple(
                payload.get("required_uncertainty", ())
            ),
            quantified_uncertainty=tuple(
                payload.get("quantified_uncertainty", ())
            ),
            alternatives=tuple(payload.get("alternatives", ())),
            reasons=tuple(payload.get("reasons", ())),
        )


@dataclass(frozen=True)
class FidelityDecision:
    ladder_id: str
    ladder_version: str
    minimum_rung: str | None
    preferred_rung: str | None
    selected_rung: str | None
    available_rungs: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIDELITY_DECISION_SCHEMA,
            "ladder_id": self.ladder_id,
            "ladder_version": self.ladder_version,
            "minimum_rung": self.minimum_rung,
            "preferred_rung": self.preferred_rung,
            "selected_rung": self.selected_rung,
            "available_rungs": list(self.available_rungs),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FidelityDecision":
        require_schema(payload, FIDELITY_DECISION_SCHEMA)
        return cls(
            payload["ladder_id"],
            payload["ladder_version"],
            payload.get("minimum_rung"),
            payload.get("preferred_rung"),
            payload.get("selected_rung"),
            tuple(payload.get("available_rungs", ())),
            payload["reason"],
        )


@dataclass(frozen=True)
class ResourceEstimate:
    solver_calls_lower_bound: int | None
    solver_calls_upper_bound: int | None
    wall_time: Quantity | None = None
    within_declared_budget: bool | None = None
    basis: str = ""

    def __post_init__(self) -> None:
        for label in (
            "solver_calls_lower_bound",
            "solver_calls_upper_bound",
        ):
            value = getattr(self, label)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{label} must be a non-negative int or None"
                )
        if (
            self.solver_calls_lower_bound is not None
            and self.solver_calls_upper_bound is not None
            and self.solver_calls_lower_bound
            > self.solver_calls_upper_bound
        ):
            raise ValueError(
                "resource estimate lower bound exceeds upper bound"
            )
        if self.wall_time is not None:
            if (
                not isinstance(self.wall_time, Quantity)
                or self.wall_time.dimensionality
                != Quantity(1.0, "second").dimensionality
            ):
                raise ValueError("wall_time must be a time Quantity")
            if self.wall_time.magnitude_in("second") < 0.0:
                raise ValueError("wall_time must be non-negative")
            object.__setattr__(
                self,
                "wall_time",
                self.wall_time.to("second"),
            )
        if (
            self.within_declared_budget is not None
            and not isinstance(self.within_declared_budget, bool)
        ):
            raise ValueError(
                "within_declared_budget must be bool or None"
            )
        object.__setattr__(self, "basis", str(self.basis).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RESOURCE_ESTIMATE_SCHEMA,
            "solver_calls_lower_bound": self.solver_calls_lower_bound,
            "solver_calls_upper_bound": self.solver_calls_upper_bound,
            "wall_time": (
                None if self.wall_time is None else self.wall_time.to_dict()
            ),
            "within_declared_budget": self.within_declared_budget,
            "basis": self.basis,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResourceEstimate":
        require_schema(payload, RESOURCE_ESTIMATE_SCHEMA)
        wall = payload.get("wall_time")
        return cls(
            payload.get("solver_calls_lower_bound"),
            payload.get("solver_calls_upper_bound"),
            None if wall is None else Quantity.from_dict(wall),
            payload.get("within_declared_budget"),
            payload.get("basis", ""),
        )


@dataclass(frozen=True)
class PlannedExternalInput:
    port: PortRef
    fact_path: str
    value: Any

    def __post_init__(self) -> None:
        if not isinstance(self.port, PortRef):
            raise TypeError("planned external input requires PortRef")
        path = str(self.fact_path).strip()
        if not path:
            raise ValueError("planned external input requires fact_path")
        object.__setattr__(self, "fact_path", path)

    @property
    def key(self) -> str:
        return self.port.key

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLANNED_EXTERNAL_INPUT_SCHEMA,
            "port": self.port.to_dict(),
            "fact_path": self.fact_path,
            "value": coupling_value_to_dict(self.value),
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "PlannedExternalInput":
        require_schema(payload, PLANNED_EXTERNAL_INPUT_SCHEMA)
        return cls(
            port=PortRef.from_dict(payload["port"]),
            fact_path=payload["fact_path"],
            value=coupling_value_from_dict(payload["value"]),
        )


@dataclass(frozen=True)
class GraphPlan:
    capability_id: str
    blueprint_id: str
    blueprint_version: str
    graph: PhysicsGraph
    coupling_plan: CouplingPlan | None
    resource_estimate: ResourceEstimate | None
    authority_pack_id: str = ""
    authority_pack_version: str = ""
    authority_pack_digest: str = ""
    coupling_policy_template_id: str = ""
    coupling_policy_template_version: str = ""
    execution_registry_fingerprint: str = ""
    execution_pack_id: str = ""
    execution_pack_version: str = ""
    execution_pack_digest: str = ""
    external_inputs: tuple[PlannedExternalInput, ...] = ()
    scenario: ScenarioSpecification | None = None

    def __post_init__(self) -> None:
        for label in (
            "capability_id",
            "blueprint_id",
            "blueprint_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"graph plan requires {label}")
            object.__setattr__(self, label, value)
        if not isinstance(self.graph, PhysicsGraph):
            raise TypeError("graph plan requires PhysicsGraph")
        if (
            self.coupling_plan is not None
            and not isinstance(self.coupling_plan, CouplingPlan)
        ):
            raise TypeError("graph plan coupling_plan must be CouplingPlan or None")
        if (
            self.resource_estimate is not None
            and not isinstance(self.resource_estimate, ResourceEstimate)
        ):
            raise TypeError(
                "graph plan resource_estimate must be ResourceEstimate or None"
            )
        if (self.coupling_plan is None) != (self.resource_estimate is None):
            raise ValueError(
                "graph plan coupling plan and resource estimate are both "
                "present or both absent"
            )
        external = tuple(self.external_inputs)
        if any(not isinstance(item, PlannedExternalInput) for item in external):
            raise TypeError(
                "graph plan external_inputs must contain PlannedExternalInput records"
            )
        keys = [item.key for item in external]
        if len(keys) != len(set(keys)):
            raise ValueError("graph plan external_inputs contain duplicate ports")
        object.__setattr__(
            self,
            "external_inputs",
            tuple(sorted(external, key=lambda item: item.key)),
        )
        if self.scenario is not None:
            if not isinstance(self.scenario, ScenarioSpecification):
                raise TypeError("graph plan scenario must be ScenarioSpecification or None")
            if self.coupling_plan is None:
                raise ValueError("graph plan scenario requires an executable coupling plan")
            if (
                self.scenario.start != self.coupling_plan.time.start
                or self.scenario.end != self.coupling_plan.time.end
            ):
                raise ValueError("graph plan scenario horizon must equal coupling-plan horizon")
            if self.scenario.unsupported_runtime_features:
                raise ValueError(
                    "graph plan refuses unsupported scenario runtime features: "
                    f"{list(self.scenario.unsupported_runtime_features)}"
                )
            scenario_inputs = {
                item.input_id
                for segment in self.scenario.segments
                for item in segment.inputs
            }
            planned_paths = {item.fact_path for item in self.external_inputs}
            unknown = sorted(scenario_inputs - planned_paths)
            if unknown:
                raise ValueError(
                    "scenario inputs have no exact GraphPlan external-input binding: "
                    f"{unknown}"
                )
            all_scenario_inputs = [
                item.input_id
                for segment in self.scenario.segments
                for item in segment.inputs
            ]
            if len(all_scenario_inputs) != len(set(all_scenario_inputs)):
                raise ValueError(
                    "scenario input ids may currently appear in one segment only; "
                    "cross-segment schedule merging is not implemented"
                )
        for label in (
            "authority_pack_id",
            "authority_pack_version",
            "authority_pack_digest",
            "coupling_policy_template_id",
            "coupling_policy_template_version",
            "execution_registry_fingerprint",
            "execution_pack_id",
            "execution_pack_version",
            "execution_pack_digest",
        ):
            object.__setattr__(
                self,
                label,
                str(getattr(self, label)).strip(),
            )

        composition_group = (
            self.authority_pack_id,
            self.authority_pack_version,
            self.authority_pack_digest,
        )
        if any(composition_group) and not all(composition_group):
            raise ValueError(
                "graph plan composition authority id/version/digest must be "
                "present together"
            )
        execution_group = (
            self.execution_pack_id,
            self.execution_pack_version,
            self.execution_pack_digest,
            self.execution_registry_fingerprint,
        )
        if any(execution_group) and not all(execution_group):
            raise ValueError(
                "graph plan execution authority id/version/digest/fingerprint "
                "must be present together"
            )
        policy_group = (
            self.coupling_policy_template_id,
            self.coupling_policy_template_version,
        )
        if any(policy_group) and not all(policy_group):
            raise ValueError(
                "graph plan coupling policy id/version must be present together"
            )
        for label in (
            "authority_pack_digest",
            "execution_pack_digest",
            "execution_registry_fingerprint",
        ):
            digest = getattr(self, label)
            if digest and (
                len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest.lower())
            ):
                raise ValueError(
                    f"graph plan {label} must be a sha256 hex digest"
                )

    @property
    def executable(self) -> bool:
        return self.coupling_plan is not None

    @property
    def interface_manifest(self) -> GraphInterfaceManifest:
        return graph_interface_manifest(self.graph)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GRAPH_PLAN_SCHEMA,
            "capability_id": self.capability_id,
            "blueprint_id": self.blueprint_id,
            "blueprint_version": self.blueprint_version,
            "graph": self.graph.to_dict(),
            "coupling_plan": (
                None
                if self.coupling_plan is None
                else self.coupling_plan.to_dict()
            ),
            "resource_estimate": (
                None
                if self.resource_estimate is None
                else self.resource_estimate.to_dict()
            ),
            "authority_pack_id": self.authority_pack_id,
            "authority_pack_version": self.authority_pack_version,
            "authority_pack_digest": self.authority_pack_digest,
            "coupling_policy_template_id": self.coupling_policy_template_id,
            "coupling_policy_template_version": (
                self.coupling_policy_template_version
            ),
            "execution_registry_fingerprint": (
                self.execution_registry_fingerprint
            ),
            "execution_pack_id": self.execution_pack_id,
            "execution_pack_version": self.execution_pack_version,
            "execution_pack_digest": self.execution_pack_digest,
            "external_inputs": [
                item.to_dict() for item in self.external_inputs
            ],
            "scenario": None if self.scenario is None else self.scenario.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GraphPlan":
        schema = require_schema_any(
            payload,
            (GRAPH_PLAN_SCHEMA_V1, GRAPH_PLAN_SCHEMA_V2, GRAPH_PLAN_SCHEMA),
        )
        raw_plan = payload.get("coupling_plan")
        raw_estimate = payload.get("resource_estimate")
        return cls(
            payload["capability_id"],
            payload["blueprint_id"],
            payload["blueprint_version"],
            PhysicsGraph.from_dict(payload["graph"]),
            None if raw_plan is None else CouplingPlan.from_dict(raw_plan),
            (
                None
                if raw_estimate is None
                else ResourceEstimate.from_dict(raw_estimate)
            ),
            authority_pack_id=payload.get("authority_pack_id", ""),
            authority_pack_version=payload.get(
                "authority_pack_version", ""
            ),
            authority_pack_digest=payload.get(
                "authority_pack_digest", ""
            ),
            coupling_policy_template_id=payload.get(
                "coupling_policy_template_id", ""
            ),
            coupling_policy_template_version=payload.get(
                "coupling_policy_template_version", ""
            ),
            execution_registry_fingerprint=payload.get(
                "execution_registry_fingerprint", ""
            ),
            execution_pack_id=payload.get("execution_pack_id", ""),
            execution_pack_version=payload.get(
                "execution_pack_version", ""
            ),
            execution_pack_digest=payload.get(
                "execution_pack_digest", ""
            ),
            external_inputs=tuple(
                PlannedExternalInput.from_dict(item)
                for item in payload.get("external_inputs", ())
            ),
            scenario=(
                None
                if schema != GRAPH_PLAN_SCHEMA or payload.get("scenario") is None
                else ScenarioSpecification.from_dict(payload["scenario"])
            ),
        )


@dataclass(frozen=True)
class ScientificPlanningRecord:
    intent_identity: str
    intent_record: str
    capability_registry_digest: str
    status: PlanningStatus
    qoi_plans: tuple[QOIPlan, ...]
    clarifications: tuple[ClarificationQuestion, ...]
    gaps: tuple[PlanningGap, ...]
    graph_plans: tuple[GraphPlan, ...] = ()
    fidelity: FidelityDecision | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", PlanningStatus(self.status))
        object.__setattr__(
            self,
            "qoi_plans",
            tuple(sorted(self.qoi_plans, key=lambda x: x.qoi_id)),
        )
        object.__setattr__(
            self,
            "clarifications",
            tuple(
                sorted(
                    self.clarifications,
                    key=lambda x: x.question_id,
                )
            ),
        )
        object.__setattr__(
            self,
            "gaps",
            tuple(
                sorted(
                    self.gaps,
                    key=lambda x: (
                        x.subject,
                        x.kind.value,
                        x.detail,
                    ),
                )
            ),
        )
        object.__setattr__(
            self,
            "graph_plans",
            tuple(
                sorted(
                    self.graph_plans,
                    key=lambda x: x.capability_id,
                )
            ),
        )

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema": SCIENTIFIC_PLAN_SCHEMA,
            "intent_identity": self.intent_identity,
            "intent_record": self.intent_record,
            "capability_registry_digest": self.capability_registry_digest,
            "status": self.status.value,
            "qoi_plans": [x.to_dict() for x in self.qoi_plans],
            "clarifications": [
                x.to_dict() for x in self.clarifications
            ],
            "gaps": [x.to_dict() for x in self.gaps],
            "graph_plans": [x.to_dict() for x in self.graph_plans],
            "fidelity": (
                None if self.fidelity is None else self.fidelity.to_dict()
            ),
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_TAG, self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._content_dict(),
            "record_digest": self.digest,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "ScientificPlanningRecord":
        version = require_schema_any(
            payload,
            (SCIENTIFIC_PLAN_SCHEMA_V1, SCIENTIFIC_PLAN_SCHEMA),
        )
        supplied_digest = payload.get("record_digest")
        if version == SCIENTIFIC_PLAN_SCHEMA_V1:
            raw_content = {
                key: value
                for key, value in payload.items()
                if key != "record_digest"
            }
            expected_legacy = tagged_digest(_TAG_V1, raw_content)
            if supplied_digest != expected_legacy:
                raise ValueError(
                    "legacy scientific planning record digest disagrees "
                    "with its serialized content"
                )
        raw_fidelity = payload.get("fidelity")
        made = cls(
            intent_identity=payload["intent_identity"],
            intent_record=payload["intent_record"],
            capability_registry_digest=payload[
                "capability_registry_digest"
            ],
            status=PlanningStatus(payload["status"]),
            qoi_plans=tuple(
                QOIPlan.from_dict(x)
                for x in payload.get("qoi_plans", ())
            ),
            clarifications=tuple(
                ClarificationQuestion.from_dict(x)
                for x in payload.get("clarifications", ())
            ),
            gaps=tuple(
                PlanningGap.from_dict(x)
                for x in payload.get("gaps", ())
            ),
            graph_plans=tuple(
                GraphPlan.from_dict(x)
                for x in payload.get("graph_plans", ())
            ),
            fidelity=(
                None
                if raw_fidelity is None
                else FidelityDecision.from_dict(raw_fidelity)
            ),
        )
        if (
            version == SCIENTIFIC_PLAN_SCHEMA
            and supplied_digest != made.digest
        ):
            raise ValueError(
                "scientific planning record digest disagrees with its content"
            )
        return made


@dataclass(frozen=True)
class PlanningRegistries:
    capabilities: CapabilityRegistry
    models: ModelRegistry | None = None
    realizations: RealizationRegistry | None = None
    solvers: SolverRegistry | None = None
    blueprints: BlueprintRegistry | None = None
    composition_packs: Any | None = None
    participant_factories: Any | None = None
    execution_packs: Any | None = None
    verification: VerificationPlanningRegistry | None = None
    fidelity_ladders: tuple[FidelityLadder, ...] = ()

    def fidelity(
        self,
        ladder_id: str,
        version: str,
    ) -> FidelityLadder | None:
        for ladder in self.fidelity_ladders:
            if (
                ladder.ladder_id == ladder_id
                and ladder.version == version
            ):
                return ladder
        return None


__all__ = [
    "ExecutionMode",
    "FidelityDecision",
    "GapKind",
    "GraphPlan",
    "GRAPH_PLAN_SCHEMA",
    "GRAPH_PLAN_SCHEMA_V1",
    "ModelExecutionChoice",
    "PlanningGap",
    "PlannedExternalInput",
    "PlanningRegistries",
    "PlanningStatus",
    "QOIPlan",
    "ResourceEstimate",
    "SCIENTIFIC_PLAN_SCHEMA",
    "SCIENTIFIC_PLAN_SCHEMA_V1",
    "ScientificPlanningRecord",
]
