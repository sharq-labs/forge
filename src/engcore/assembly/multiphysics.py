"""Execute a planned multiphysics graph against exact registered authority."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping
from ..scientific.twins import ScientificTwin

from ..compositionpacks.contracts import SystemValidationResult
from ..compositionpacks.applicability import (
    ApplicabilityState,
    evaluate_applicability_predicate,
)
from ..compositionpacks.uncertainty import SystemUncertaintyResult
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
    ParameterValue,
    ParticipantFactoryRegistry,
)
from ..executionpacks.registry import ExecutionPackRegistry
from ..executionpacks.snapshot import (
    ExecutionPackSnapshot,
    snapshot_execution_pack,
)
from ..planning.records import GraphPlan
from ..scenarios import ScenarioSpecification
from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics import (
    InitialStateValue,
    MultiphysicsRunRecord,
    PortRef,
)
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.serialization import (
    require_schema_any,
    schema_string,
)
from ..scientific.verification.dependencies import (
    DependencyComponent,
    DependencyRole,
    RouteDependencyManifest,
)
from ..scientific.verification.route import (
    VerificationRoute,
    VerificationRouteKind,
)
from ..scientific.verification.run_record import VerificationRunRecord

AUTHORIZED_RUN_SCHEMA_V1 = schema_string("authorized_multiphysics_run")
AUTHORIZED_RUN_SCHEMA_V2 = schema_string("authorized_multiphysics_run", 2)
AUTHORIZED_RUN_SCHEMA = schema_string("authorized_multiphysics_run", 3)


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

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "AuthorizedSystemValidation":
        return cls(
            protocol_id=payload["protocol_id"],
            protocol_version=payload["protocol_version"],
            result=SystemValidationResult.from_dict(payload["result"]),
        )


@dataclass(frozen=True)
class AuthorizedSystemUncertainty:
    protocol_id: str
    protocol_version: str
    result: SystemUncertaintyResult

    def __post_init__(self) -> None:
        for label in ("protocol_id", "protocol_version"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"authorized system uncertainty requires {label}"
                )
            object.__setattr__(self, label, value)
        if not isinstance(self.result, SystemUncertaintyResult):
            raise InvalidScientificProblem(
                "authorized system uncertainty requires SystemUncertaintyResult"
            )

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.protocol_id,
            self.protocol_version,
            self.result.quantity,
            self.result.channel.value,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "result": self.result.to_dict(),
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "AuthorizedSystemUncertainty":
        return cls(
            protocol_id=payload["protocol_id"],
            protocol_version=payload["protocol_version"],
            result=SystemUncertaintyResult.from_dict(payload["result"]),
        )


@dataclass(frozen=True)
class AuthorizedSystemVerification:
    protocol_id: str
    protocol_version: str
    quantity: str
    run: VerificationRunRecord

    def __post_init__(self) -> None:
        for label in (
            "protocol_id",
            "protocol_version",
            "quantity",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"authorized system verification requires {label}"
                )
            object.__setattr__(self, label, value)
        if not isinstance(self.run, VerificationRunRecord):
            raise InvalidScientificProblem(
                "authorized system verification requires VerificationRunRecord"
            )

    @property
    def key(self) -> tuple[str, str, str]:
        return (
            self.protocol_id,
            self.protocol_version,
            self.quantity,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "quantity": self.quantity,
            "run": self.run.to_dict(),
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "AuthorizedSystemVerification":
        return cls(
            protocol_id=payload["protocol_id"],
            protocol_version=payload["protocol_version"],
            quantity=payload["quantity"],
            run=VerificationRunRecord.from_dict(payload["run"]),
        )


@dataclass(frozen=True)
class AuthorizedMultiphysicsRun:
    graph_plan: GraphPlan
    composition_snapshot: CompositionPackSnapshot
    execution_snapshot: ExecutionPackSnapshot
    run: MultiphysicsRunRecord
    system_validation: tuple[AuthorizedSystemValidation, ...]
    system_uncertainty: tuple[AuthorizedSystemUncertainty, ...] = ()
    system_verification: tuple[AuthorizedSystemVerification, ...] = ()

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
        self._bind_scenario()
        validations = tuple(self.system_validation)
        if any(
            not isinstance(item, AuthorizedSystemValidation)
            for item in validations
        ):
            raise TypeError(
                "system_validation must contain AuthorizedSystemValidation"
            )
        validation_keys = [
            (item.protocol_id, item.protocol_version)
            for item in validations
        ]
        if len(validation_keys) != len(set(validation_keys)):
            raise InvalidScientificProblem(
                "authorized run contains duplicate system validation results"
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

        uncertainties = tuple(self.system_uncertainty)
        if any(
            not isinstance(item, AuthorizedSystemUncertainty)
            for item in uncertainties
        ):
            raise TypeError(
                "system_uncertainty must contain AuthorizedSystemUncertainty"
            )
        uncertainty_keys = [item.key for item in uncertainties]
        if len(uncertainty_keys) != len(set(uncertainty_keys)):
            raise InvalidScientificProblem(
                "authorized run contains duplicate system uncertainty results"
            )
        object.__setattr__(
            self,
            "system_uncertainty",
            tuple(sorted(uncertainties, key=lambda item: item.key)),
        )

        verifications = tuple(self.system_verification)
        if any(
            not isinstance(item, AuthorizedSystemVerification)
            for item in verifications
        ):
            raise TypeError(
                "system_verification must contain AuthorizedSystemVerification"
            )
        verification_keys = [item.key for item in verifications]
        if len(verification_keys) != len(set(verification_keys)):
            raise InvalidScientificProblem(
                "authorized run contains duplicate system verification results"
            )
        object.__setattr__(
            self,
            "system_verification",
            tuple(sorted(verifications, key=lambda item: item.key)),
        )

        if self.graph_plan.graph != self.run.graph:
            raise InvalidScientificProblem(
                "authorized run graph differs from its GraphPlan"
            )
        if self.graph_plan.coupling_plan != self.run.plan:
            raise InvalidScientificProblem(
                "authorized run coupling plan differs from its GraphPlan"
            )
        if (
            self.graph_plan.authority_pack_id,
            self.graph_plan.authority_pack_version,
            self.graph_plan.authority_pack_digest,
        ) != (
            self.composition_snapshot.pack_id,
            self.composition_snapshot.pack_version,
            self.composition_snapshot.authority_digest,
        ):
            raise InvalidScientificProblem(
                "GraphPlan composition authority differs from its snapshot"
            )
        if (
            self.graph_plan.execution_pack_id,
            self.graph_plan.execution_pack_version,
            self.graph_plan.execution_pack_digest,
        ) != (
            self.execution_snapshot.pack_id,
            self.execution_snapshot.pack_version,
            self.execution_snapshot.authority_digest,
        ):
            raise InvalidScientificProblem(
                "GraphPlan execution authority differs from its snapshot"
            )
        if (
            self.execution_snapshot.composition_pack_id,
            self.execution_snapshot.composition_pack_version,
            self.execution_snapshot.composition_manifest_digest,
            self.execution_snapshot.composition_authority_digest,
        ) != (
            self.composition_snapshot.pack_id,
            self.composition_snapshot.pack_version,
            self.composition_snapshot.manifest_digest,
            self.composition_snapshot.authority_digest,
        ):
            raise InvalidScientificProblem(
                "ExecutionPack snapshot is not bound to the "
                "CompositionPack snapshot"
            )

        def declared(items):
            return {
                (str(item["artifact_id"]), str(item["version"]))
                for item in items
            }

        validation_authority = declared(
            self.composition_snapshot.validation_implementations
        )
        if any(key not in validation_authority for key in validation_keys):
            raise InvalidScientificProblem(
                "system validation result is not bound to a pinned implementation"
            )
        uncertainty_authority = declared(
            self.composition_snapshot.uncertainty_implementations
        )
        if any(
            (item.protocol_id, item.protocol_version)
            not in uncertainty_authority
            for item in uncertainties
        ):
            raise InvalidScientificProblem(
                "system uncertainty result is not bound to a pinned implementation"
            )
        verification_authority = declared(
            self.composition_snapshot.verification_implementations
        )
        if any(
            (item.protocol_id, item.protocol_version)
            not in verification_authority
            for item in verifications
        ):
            raise InvalidScientificProblem(
                "system verification result is not bound to a pinned implementation"
            )

    def _bind_scenario(self) -> None:
        """Bind the run to the exact scenario, whether or not it declares events.

        THE RULE THIS REPLACES. The digest was required when, and only when,
        the scenario declared scheduled events -- so a mission whose phases
        differ by their time-varying inputs, their operating conditions, their
        initial state or their stop condition, and which declares no event at
        all, was authorized with `scenario_digest == ""`. Nothing in the run
        then said which scenario produced it, and two different scenarios over
        the same graph and plan produced indistinguishable records.

        Scenario identity does not depend on whether events happen to exist.
        A GraphPlan carrying a scenario executed in that scenario's world, so
        the run carries that scenario's digest; a GraphPlan carrying none
        carries no digest, and a run that claims one is refused.
        """
        scenario = self.graph_plan.scenario
        run = self.run

        expected_events = (
            () if scenario is None else tuple(
                (item.event_id, item.instant) for item in scenario.events
            )
        )
        recorded_events = tuple(
            (item.event_id, item.instant) for item in run.scheduled_events
        )
        if recorded_events != expected_events:
            raise InvalidScientificProblem(
                "authorized run scheduled events differ from its GraphPlan scenario"
            )

        expected_digest = "" if scenario is None else scenario.digest
        if run.scenario_digest != expected_digest:
            raise InvalidScientificProblem(
                "authorized run is not bound to its GraphPlan scenario digest: "
                f"expected {expected_digest[:12] or '(none)'}..., recorded "
                f"{run.scenario_digest[:12] or '(none)'}..."
            )
        if scenario is None:
            if (
                run.scenario_input_receipts
                or run.operating_condition_receipts
                or run.quantities_of_interest
                or run.termination is not None
            ):
                raise InvalidScientificProblem(
                    "authorized run carries scenario evidence but its GraphPlan "
                    "declares no scenario"
                )
            return

        declared_inputs = {
            item.input_id for item in scenario.composed_input_schedules()
        }
        recorded_inputs = {item.input_id for item in run.scenario_input_receipts}
        if not recorded_inputs <= declared_inputs:
            raise InvalidScientificProblem(
                "authorized run consumed inputs its GraphPlan scenario does not "
                f"declare: {sorted(recorded_inputs - declared_inputs)}"
            )
        declared_conditions = {
            item.condition_id for item in scenario.composed_operating_conditions()
        }
        recorded_conditions = {
            item.condition_id for item in run.operating_condition_receipts
        }
        if not recorded_conditions <= declared_conditions:
            raise InvalidScientificProblem(
                "authorized run delivered operating conditions its GraphPlan "
                f"scenario does not declare: "
                f"{sorted(recorded_conditions - declared_conditions)}"
            )
        requested = {item.qoi_id for item in scenario.quantities_of_interest}
        produced = {item.qoi_id for item in run.quantities_of_interest}
        if produced != requested:
            raise InvalidScientificProblem(
                "authorized run quantities of interest do not answer the scenario "
                f"request exactly; missing={sorted(requested - produced)}, "
                f"unrequested={sorted(produced - requested)}"
            )
        if run.termination is not None and run.termination.condition_id not in {
            item.condition_id for item in scenario.termination_conditions
        }:
            raise InvalidScientificProblem(
                "authorized run stopped on a condition its GraphPlan scenario "
                "does not declare"
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
            "system_uncertainty": [
                item.to_dict() for item in self.system_uncertainty
            ],
            "system_verification": [
                item.to_dict() for item in self.system_verification
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

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "AuthorizedMultiphysicsRun":
        schema = require_schema_any(
            payload,
            (
                AUTHORIZED_RUN_SCHEMA_V1,
                AUTHORIZED_RUN_SCHEMA_V2,
                AUTHORIZED_RUN_SCHEMA,
            ),
        )
        supplied = payload.get("record_digest")
        if schema in (
            AUTHORIZED_RUN_SCHEMA_V1,
            AUTHORIZED_RUN_SCHEMA_V2,
        ):
            raw = {
                key: value
                for key, value in payload.items()
                if key != "record_digest"
            }
            expected = hashlib.sha256(
                json.dumps(
                    raw,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            if supplied != expected:
                raise InvalidScientificProblem(
                    "legacy authorized multiphysics run digest disagrees "
                    "with its original wire content"
                )

        made = cls(
            graph_plan=GraphPlan.from_dict(payload["graph_plan"]),
            composition_snapshot=CompositionPackSnapshot.from_dict(
                payload["composition_snapshot"]
            ),
            execution_snapshot=ExecutionPackSnapshot.from_dict(
                payload["execution_snapshot"]
            ),
            run=MultiphysicsRunRecord.from_dict(payload["run"]),
            system_validation=tuple(
                AuthorizedSystemValidation.from_dict(item)
                for item in payload.get("system_validation", ())
            ),
            system_uncertainty=(
                ()
                if schema == AUTHORIZED_RUN_SCHEMA_V1
                else tuple(
                    AuthorizedSystemUncertainty.from_dict(item)
                    for item in payload.get("system_uncertainty", ())
                )
            ),
            system_verification=(
                ()
                if schema == AUTHORIZED_RUN_SCHEMA_V1
                else tuple(
                    AuthorizedSystemVerification.from_dict(item)
                    for item in payload.get("system_verification", ())
                )
            ),
        )
        if schema == AUTHORIZED_RUN_SCHEMA and supplied != made.digest:
            raise InvalidScientificProblem(
                "authorized multiphysics run digest disagrees with content"
            )
        return made


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
    facts = {
        item.fact_path: item.value
        for item in graph_plan.external_inputs
    }
    expected_plan = policies[0].materialize(
        start=graph_plan.coupling_plan.time.start,
        end=graph_plan.coupling_plan.time.end,
        plan_id=graph_plan.coupling_plan.plan_id,
        facts=facts,
    )
    if expected_plan != graph_plan.coupling_plan:
        raise InvalidScientificProblem(
            "GraphPlan CouplingPlan differs from its authoritative "
            "CouplingPolicyTemplate"
        )


def _authorized_execution_verification_authority(
    execution_snapshot: ExecutionPackSnapshot,
) -> tuple[VerificationRoute, RouteDependencyManifest]:
    """Describe the exact primary execution stack for independence analysis."""

    route_id = (
        f"authorized_execution.{execution_snapshot.pack_id}."
        f"{execution_snapshot.pack_version}"
    )
    route = VerificationRoute(
        route_id=route_id,
        kind=VerificationRouteKind.DIFFERENT_IMPLEMENTATION,
        implementation_digest=execution_snapshot.authority_digest,
    )

    components = [
        DependencyComponent(
            family_id=(
                f"composition_authority."
                f"{execution_snapshot.composition_pack_id}"
            ),
            implementation_digest=(
                execution_snapshot.composition_authority_digest
            ),
            role=DependencyRole.MODEL,
        ),
        DependencyComponent(
            family_id=(
                f"execution_pack.{execution_snapshot.pack_id}"
            ),
            implementation_digest=execution_snapshot.authority_digest,
            role=DependencyRole.RUNTIME,
        ),
    ]
    seen_adapter_families = set()
    for item in execution_snapshot.participant_factories:
        family = (
            f"adapter.{item['adapter_id']}@"
            f"{item['adapter_version']}"
        )
        if family in seen_adapter_families:
            continue
        seen_adapter_families.add(family)
        components.append(
            DependencyComponent(
                family_id=family,
                implementation_digest=item["implementation_digest"],
                role=DependencyRole.SOLVER,
            )
        )

    dependencies = RouteDependencyManifest(
        route_id=route_id,
        components=tuple(components),
        authority_id=(
            f"execution:{execution_snapshot.pack_id}@"
            f"{execution_snapshot.pack_version}"
        ),
        externally_operated=False,
    )
    return route, dependencies


def _initial_state_by_owner(
    scenario: ScenarioSpecification,
    state_owners: Mapping[str, str],
) -> dict[str, dict[str, InitialStateValue]]:
    """Group a scenario's initial state by the participant that owns each variable.

    A topology StateBinding, when one exists, is the owning authority; otherwise
    the scenario's own ``owner_id`` is. GraphPlan has already refused the case
    where the two disagree, so this cannot silently pick a side.
    """
    values = {item.quantity_id: item for item in scenario.initial_state.values}
    grouped: dict[str, dict[str, InitialStateValue]] = {}
    for variable in scenario.state_variables:
        owner = state_owners.get(variable.variable_id, variable.owner_id)
        declared = values[variable.variable_id]
        grouped.setdefault(owner, {})[variable.variable_id] = InitialStateValue(
            variable.variable_id, declared.value, declared.uncertainty
        )
    return grouped


def execute_authorized_graph_plan(
    graph_plan: GraphPlan,
    *,
    run_id: str,
    compositions: CompositionPackRegistry,
    executions: ExecutionPackRegistry,
    resolver: BulkDataResolver,
    store: BulkDataStore,
    external_uncertainty: Mapping[PortRef, Uncertainty] | None = None,
    topology_twins: Mapping[tuple[str, str], ScientificTwin] | None = None,
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
    if graph_plan.system_definition is not None:
        if topology_twins is None:
            raise InvalidScientificProblem(
                "GraphPlan topology requires exact ScientificTwin authorities"
            )
        graph_plan.system_definition.validate_against(
            graph_plan.graph, topology_twins
        )

    scenario = graph_plan.scenario
    scenario_schedules = {
        item.input_id: item
        for item in (
            () if scenario is None else scenario.composed_input_schedules()
        )
    }
    scenario_conditions = (
        () if scenario is None else scenario.composed_operating_conditions()
    )
    base_facts = {
        item.fact_path: item.value for item in graph_plan.external_inputs
    }
    if scenario is not None and scenario.initial_state is not None:
        base_facts.update({item.quantity_id: item.value for item in scenario.initial_state.values})
    applicability_fact_sets = [base_facts]
    for input_id, schedule in sorted(scenario_schedules.items()):
        for sample in schedule.series.samples:
            applicability_fact_sets.append({**base_facts, input_id: sample.value})
    for rule in composition.applicability_rules:
        if rule.blueprint_id != graph_plan.blueprint_id:
            continue
        for predicate in rule.predicates:
            for facts in applicability_fact_sets:
                evaluation = evaluate_applicability_predicate(
                    predicate,
                    facts=facts,
                    static_external_inputs=not bool(scenario_schedules),
                )
                if evaluation.state is not ApplicabilityState.SATISFIED:
                    raise InvalidScientificProblem(
                        "scenario applicability preflight refused execution: "
                        f"{evaluation.reason}"
                    )

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
    planned_ports = {
        item.port for item in graph_plan.external_inputs
    }
    external_uncertainty = (
        {}
        if external_uncertainty is None
        else dict(external_uncertainty)
    )
    unknown_uq_ports = sorted(
        ref.key
        for ref in set(external_uncertainty) - planned_ports
    )
    if unknown_uq_ports:
        raise InvalidScientificProblem(
            "external uncertainty names ports outside GraphPlan inputs: "
            f"{unknown_uq_ports}"
        )
    topology = graph_plan.system_definition
    parameter_bindings = (
        {}
        if topology is None or not topology.parameter_bindings
        else {
            participant_id: {
                target_path: ParameterValue(target_path, value)
                for target_path, value in sorted(targets.items())
            }
            for participant_id, targets in sorted(
                topology.parameter_values(topology_twins or {}).items()
            )
        }
    )
    state_owners = {} if topology is None else topology.state_variable_owners()
    run = runtime.run(
        run_id,
        external_inputs={
            item.port: item.value
            for item in graph_plan.external_inputs
        },
        external_uncertainty=external_uncertainty,
        external_input_schedules={
            item.port: scenario_schedules[item.fact_path]
            for item in graph_plan.external_inputs
            if item.fact_path in scenario_schedules
        },
        operating_conditions=scenario_conditions,
        initial_state=(
            {}
            if scenario is None or scenario.initial_state is None
            else _initial_state_by_owner(scenario, state_owners)
        ),
        parameter_bindings=parameter_bindings,
        scheduled_events=(() if scenario is None else scenario.events),
        termination_conditions=(
            () if scenario is None else scenario.termination_conditions
        ),
        quantity_bindings={
            item.quantity_id: item.port for item in graph_plan.quantity_bindings
        },
        quantities_of_interest=(
            () if scenario is None else scenario.quantities_of_interest
        ),
        # SCENARIO IDENTITY IS NOT CONDITIONAL ON EVENTS (Sprint 1 P0).
        scenario_digest="" if scenario is None else scenario.digest,
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

    uncertainty_results: list[AuthorizedSystemUncertainty] = []
    for producer in composition.uncertainty_producers:
        if producer.blueprint_id != graph_plan.blueprint_id:
            continue
        produced = tuple(producer.implementation(run))
        seen = set()
        for result in produced:
            if not isinstance(result, SystemUncertaintyResult):
                raise InvalidScientificProblem(
                    f"composition uncertainty {producer.ref.artifact_id}@"
                    f"{producer.ref.version} returned "
                    f"{type(result).__name__}, expected SystemUncertaintyResult"
                )
            if result.quantity not in producer.quantities:
                raise InvalidScientificProblem(
                    f"composition uncertainty producer emitted undeclared "
                    f"quantity {result.quantity!r}"
                )
            if result.channel not in producer.channels:
                raise InvalidScientificProblem(
                    f"composition uncertainty producer emitted undeclared "
                    f"channel {result.channel.value!r}"
                )
            if result.key in seen:
                raise InvalidScientificProblem(
                    "composition uncertainty producer emitted duplicate result "
                    f"{result.key}"
                )
            seen.add(result.key)
            uncertainty_results.append(
                AuthorizedSystemUncertainty(
                    producer.ref.artifact_id,
                    producer.ref.version,
                    result,
                )
            )

    execution_snapshot = snapshot_execution_pack(execution)
    primary_route, primary_dependencies = (
        _authorized_execution_verification_authority(
            execution_snapshot
        )
    )
    verification_results: list[AuthorizedSystemVerification] = []
    for protocol in composition.verification_protocols:
        if protocol.blueprint_id != graph_plan.blueprint_id:
            continue
        verification_results.append(
            AuthorizedSystemVerification(
                protocol.ref.artifact_id,
                protocol.ref.version,
                protocol.quantity,
                protocol.execute(
                    run,
                    primary_route,
                    primary_dependencies,
                ),
            )
        )
    if not verification_results:
        raise InvalidScientificProblem(
            "selected CompositionPack has no executable independent "
            "verification protocol for the executed blueprint"
        )

    return AuthorizedMultiphysicsRun(
        graph_plan=graph_plan,
        composition_snapshot=snapshot_composition_pack(composition),
        execution_snapshot=execution_snapshot,
        run=run,
        system_validation=tuple(validation),
        system_uncertainty=tuple(uncertainty_results),
        system_verification=tuple(verification_results),
    )


__all__ = [
    "AUTHORIZED_RUN_SCHEMA",
    "AUTHORIZED_RUN_SCHEMA_V1",
    "AUTHORIZED_RUN_SCHEMA_V2",
    "AuthorizedMultiphysicsRun",
    "AuthorizedSystemUncertainty",
    "AuthorizedSystemValidation",
    "AuthorizedSystemVerification",
    "execute_authorized_graph_plan",
]
