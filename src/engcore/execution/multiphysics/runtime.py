"""General transient multiphysics coupling runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ...data.resolver import BulkDataResolver
from ...data.store import BulkDataStore
from ...scientific.conservation import BalanceTerm, ConservationBalance
from ...scientific.errors import InvalidScientificProblem, ScientificCoreError
from ...scientific.multiphysics import (
    BalanceSide,
    CouplingIterationRecord,
    CouplingPlan,
    CouplingScheme,
    CouplingWindowRecord,
    ExternalInputRecord,
    InitialCouplingRecord,
    InitialStateReceipt,
    InitialStateValue,
    MultiphysicsRunRecord,
    ParticipantStepRecord,
    PhysicsGraph,
    PortDirection,
    PortRef,
    ReachedScheduledEvent,
    ScheduledEventRecord,
    TransferMeasure,
    WindowOutcome,
)
from ...scientific.multiphysics.receipts import (
    OperatingConditionReceipt,
    QuantityOfInterestRecord,
    ScenarioInputReceipt,
    StateTransitionReceipt,
    TerminationReceipt,
)
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.units.quantity import Quantity
from ...scenarios import (
    ComposedInputSchedule,
    ComposedOperatingCondition,
    InterpolationKind,
    QuantityOfInterest,
    ScenarioEvent,
    TerminationCondition,
)
from .convergence import ResidualCalculator
from .error import CouplingErrorBudget
from .factory import ParticipantFactoryRegistry
from .participant import (
    AdvanceRequest,
    AdvanceResult,
    CouplingValue,
    ExecutableParticipant,
    OperatingConditionValue,
    ParameterValue,
    RuntimeCheckpoint,
    apply_operating_conditions,
    apply_parameters,
    operating_condition_definitions,
    public_state,
    state_identity,
    validate_outputs,
    validate_port_value,
    validate_uncertainty,
)
from .relaxation import RelaxationController, relax_uncertainty
from .transfer import (
    TransferEngine,
    TransferResult,
    combine_fan_in_uncertainty,
)


class MultiphysicsExecutionError(ScientificCoreError):
    """A coupled execution cannot continue without inventing state or science."""


@dataclass(frozen=True)
class _IterationOutcome:
    edge_values: Mapping[str, CouplingValue]
    edge_uncertainty: Mapping[str, Uncertainty]
    transfers: Mapping[str, TransferResult]
    outputs: Mapping[str, Mapping[str, CouplingValue]]
    output_uncertainty: Mapping[str, Mapping[str, Uncertainty]]
    record: CouplingIterationRecord
    event: Mapping[str, Any] | None = None


class MultiphysicsRuntime:
    @classmethod
    def from_factory_registry(
        cls,
        graph: PhysicsGraph,
        plan: CouplingPlan,
        registry: ParticipantFactoryRegistry,
        *,
        resolver: BulkDataResolver,
        store: BulkDataStore,
    ) -> "MultiphysicsRuntime":
        """Materialize exact graph participants and construct the runtime."""
        if not isinstance(registry, ParticipantFactoryRegistry):
            raise TypeError(
                "from_factory_registry requires ParticipantFactoryRegistry"
            )

        # Validate graph/policy before factories allocate solver/provider state.
        plan.validate_against(graph)
        participants = registry.build_graph(graph)
        try:
            return cls(
                graph,
                plan,
                participants,
                resolver=resolver,
                store=store,
            )
        except Exception:
            for participant_id in sorted(participants, reverse=True):
                try:
                    participants[participant_id].finalize()
                except Exception:
                    pass
            raise

    @classmethod
    def from_record_with_factory_registry(
        cls,
        record: MultiphysicsRunRecord,
        registry: ParticipantFactoryRegistry,
        *,
        resolver: BulkDataResolver,
        store: BulkDataStore,
    ) -> "MultiphysicsRuntime":
        """Rebuild a runtime from an evidence record without manual wiring."""
        if not isinstance(record, MultiphysicsRunRecord):
            raise InvalidScientificProblem(
                "multiphysics replay requires MultiphysicsRunRecord"
            )
        return cls.from_factory_registry(
            record.graph,
            record.plan,
            registry,
            resolver=resolver,
            store=store,
        )

    @classmethod
    def replay_with_factory_registry(
        cls,
        record: MultiphysicsRunRecord,
        registry: ParticipantFactoryRegistry,
        *,
        replay_run_id: str,
        resolver: BulkDataResolver,
        store: BulkDataStore,
    ) -> MultiphysicsRunRecord:
        """Replay a recorded graph using exact registered execution factories."""
        # SCENARIO IDENTITY, NOT EVENT PRESENCE, DECIDES THIS.
        #
        # The refusal used to test for consumed inputs, scheduled events or an
        # initial-state receipt, so a run driven by a scenario's operating
        # conditions or stop condition and nothing else replayed happily
        # WITHOUT that scenario. The digest is on the record exactly when a
        # scenario participated, so it is the one thing worth asking.
        if record.scenario_digest:
            raise InvalidScientificProblem(
                "scenario-driven replay requires its authorized scenario: this "
                f"run is bound to scenario {record.scenario_digest[:12]}..., "
                "which cannot be reconstructed from the run record alone"
            )
        runtime = cls.from_record_with_factory_registry(
            record,
            registry,
            resolver=resolver,
            store=store,
        )
        return runtime.run(
            replay_run_id,
            external_inputs={
                item.port: item.value
                for item in record.external_inputs
            },
            external_uncertainty={
                item.port: item.uncertainty
                for item in record.external_inputs
            },
            initial_coupling_values={
                item.edge_id: item.value
                for item in record.initial_coupling
            },
            initial_coupling_uncertainty={
                item.edge_id: item.uncertainty
                for item in record.initial_coupling
            },
        )

    @classmethod
    def from_record(
        cls,
        record: MultiphysicsRunRecord,
        participants: Mapping[str, ExecutableParticipant],
        *,
        resolver: BulkDataResolver,
        store: BulkDataStore,
    ) -> "MultiphysicsRuntime":
        if not isinstance(record, MultiphysicsRunRecord):
            raise InvalidScientificProblem(
                "multiphysics replay requires MultiphysicsRunRecord"
            )
        return cls(
            record.graph,
            record.plan,
            participants,
            resolver=resolver,
            store=store,
        )

    @classmethod
    def replay(
        cls,
        record: MultiphysicsRunRecord,
        participants: Mapping[str, ExecutableParticipant],
        *,
        replay_run_id: str,
        resolver: BulkDataResolver,
        store: BulkDataStore,
    ) -> MultiphysicsRunRecord:
        # SCENARIO IDENTITY, NOT EVENT PRESENCE, DECIDES THIS.
        #
        # The refusal used to test for consumed inputs, scheduled events or an
        # initial-state receipt, so a run driven by a scenario's operating
        # conditions or stop condition and nothing else replayed happily
        # WITHOUT that scenario. The digest is on the record exactly when a
        # scenario participated, so it is the one thing worth asking.
        if record.scenario_digest:
            raise InvalidScientificProblem(
                "scenario-driven replay requires its authorized scenario: this "
                f"run is bound to scenario {record.scenario_digest[:12]}..., "
                "which cannot be reconstructed from the run record alone"
            )
        runtime = cls.from_record(
            record,
            participants,
            resolver=resolver,
            store=store,
        )
        return runtime.run(
            replay_run_id,
            external_inputs={
                item.port: item.value
                for item in record.external_inputs
            },
            external_uncertainty={
                item.port: item.uncertainty
                for item in record.external_inputs
            },
            initial_coupling_values={
                item.edge_id: item.value
                for item in record.initial_coupling
            },
            initial_coupling_uncertainty={
                item.edge_id: item.uncertainty
                for item in record.initial_coupling
            },
        )

    def __init__(
        self,
        graph: PhysicsGraph,
        plan: CouplingPlan,
        participants: Mapping[str, ExecutableParticipant],
        *,
        resolver: BulkDataResolver,
        store: BulkDataStore,
    ) -> None:
        plan.validate_against(graph)
        self.graph = graph
        self.plan = plan
        self.participants = dict(participants)
        self.resolver = resolver
        self.store = store
        self.meshes = {
            support.mesh_id: support
            for support in graph.supports
        }

        expected = {p.participant_id for p in graph.participants}
        actual = set(self.participants)
        if actual != expected:
            raise InvalidScientificProblem(
                f"runtime participants mismatch graph; "
                f"missing={sorted(expected-actual)}, extra={sorted(actual-expected)}"
            )
        for spec in graph.participants:
            if self.participants[spec.participant_id].spec != spec:
                raise InvalidScientificProblem(
                    f"runtime participant {spec.participant_id!r} spec differs from PhysicsGraph"
                )

        self.transfer = TransferEngine(
            graph,
            resolver=resolver,
            store=store,
        )
        self.residuals = ResidualCalculator(resolver, self.meshes)
        self.relaxation = RelaxationController(
            plan.relaxation, resolver, store, self.meshes
        )

    def _external_by_participant(
        self,
        external: Mapping[PortRef, CouplingValue],
        uncertainty: Mapping[PortRef, Uncertainty],
    ) -> tuple[
        dict[str, dict[str, CouplingValue]],
        dict[str, dict[str, Uncertainty]],
    ]:
        connected = {edge.target for edge in self.graph.edges}
        grouped = {p.participant_id: {} for p in self.graph.participants}
        grouped_uncertainty = {
            p.participant_id: {} for p in self.graph.participants
        }
        extra_uncertainty = sorted(
            ref.key for ref in set(uncertainty) - set(external)
        )
        if extra_uncertainty:
            raise InvalidScientificProblem(
                f"external uncertainty has no matching value for {extra_uncertainty}"
            )

        for ref, value in external.items():
            if not isinstance(ref, PortRef):
                raise InvalidScientificProblem("external input keys must be PortRef")
            spec = self.graph.participant(ref.participant_id)
            port = spec.port(ref.port_id)
            if port.direction is not PortDirection.INPUT:
                raise InvalidScientificProblem(
                    f"external input {ref.key} is not an input port"
                )
            if ref in connected:
                raise InvalidScientificProblem(
                    f"input {ref.key} is supplied by PhysicsGraph and cannot also be external"
                )
            validate_port_value(spec, ref.port_id, value, output=False)
            grouped[ref.participant_id][ref.port_id] = value
            grouped_uncertainty[ref.participant_id][ref.port_id] = uncertainty.get(
                ref,
                Uncertainty.unknown(
                    f"no uncertainty was supplied for external input {ref.key}"
                ),
            )

        for spec in self.graph.participants:
            for port in spec.inputs:
                ref = PortRef(spec.participant_id, port.port_id)
                if (
                    ref not in connected
                    and port.port_id not in grouped[spec.participant_id]
                ):
                    raise InvalidScientificProblem(
                        f"externally imposed input {ref.key} has no value"
                    )
        return grouped, grouped_uncertainty

    def _initialize(
        self,
        start: Quantity,
        external: Mapping[str, Mapping[str, CouplingValue]],
        external_uncertainty: Mapping[str, Mapping[str, Uncertainty]],
        initial_state: Mapping[str, Mapping[str, InitialStateValue]],
    ) -> tuple[
        dict[str, dict[str, CouplingValue]],
        dict[str, dict[str, Uncertainty]],
        tuple[InitialStateReceipt, ...],
    ]:
        outputs: dict[str, dict[str, CouplingValue]] = {}
        uncertainty: dict[str, dict[str, Uncertainty]] = {}
        receipts: list[InitialStateReceipt] = []
        for participant_id in self.plan.resolved_order(self.graph):
            participant = self.participants[participant_id]
            state = initial_state.get(participant_id, {})
            if state:
                made = participant.initialize_state(
                    start, state, external[participant_id], external_uncertainty[participant_id]
                )
                receipts.append(made.initial_state_receipt)
            else:
                made = participant.initialize(start, external[participant_id], external_uncertainty[participant_id])
            validate_outputs(
                participant.spec,
                made.outputs,
                made.uncertainty,
            )
            outputs[participant_id] = dict(made.outputs)
            uncertainty[participant_id] = dict(made.uncertainty)
        return outputs, uncertainty, tuple(receipts)

    def _initial_transfers(
        self,
        outputs: Mapping[str, Mapping[str, CouplingValue]],
        output_uncertainty: Mapping[str, Mapping[str, Uncertainty]],
        initial: Mapping[str, CouplingValue],
        initial_uncertainty: Mapping[str, Uncertainty],
        instant: Quantity,
    ) -> tuple[
        dict[str, CouplingValue],
        dict[str, Uncertainty],
        dict[str, TransferResult],
    ]:
        values: dict[str, CouplingValue] = {}
        uncertainty: dict[str, Uncertainty] = {}
        transfers: dict[str, TransferResult] = {}
        edge_ids = {edge.edge_id for edge in self.graph.edges}
        unknown = sorted(set(initial) - edge_ids)
        unknown_uq = sorted(set(initial_uncertainty) - edge_ids)
        if unknown or unknown_uq:
            raise InvalidScientificProblem(
                f"initial coupling data names unknown edges "
                f"values={unknown}, uncertainty={unknown_uq}"
            )

        instant_text = f"{self._seconds(instant):.17g} second"
        for edge in self.graph.edges:
            if edge.edge_id in initial:
                value = initial[edge.edge_id]
                target_spec = self.graph.participant(edge.target.participant_id)
                validate_port_value(
                    target_spec, edge.target.port_id, value, output=False
                )
                values[edge.edge_id] = value
                initial_uq = initial_uncertainty.get(
                    edge.edge_id,
                    Uncertainty.unknown(
                        f"initial coupling value for edge {edge.edge_id} has no "
                        f"declared uncertainty"
                    ),
                )
                validate_uncertainty(
                    target_spec,
                    edge.target.port_id,
                    initial_uq,
                    output=False,
                )
                uncertainty[edge.edge_id] = initial_uq
                continue

            source = outputs.get(edge.source.participant_id, {}).get(
                edge.source.port_id
            )
            source_uq = output_uncertainty.get(
                edge.source.participant_id, {}
            ).get(edge.source.port_id)
            if source is None or source_uq is None:
                raise MultiphysicsExecutionError(
                    f"edge {edge.edge_id!r} has no initial source output/uncertainty "
                    f"and no initial coupling value"
                )
            transfer = self.transfer.transfer(
                edge,
                source,
                source_uq,
                instant=instant_text,
            )
            transfers[edge.edge_id] = transfer
            values[edge.edge_id] = transfer.value
            uncertainty[edge.edge_id] = transfer.uncertainty

        return values, uncertainty, transfers

    def _inputs_for(
        self,
        participant_id: str,
        edge_values: Mapping[str, CouplingValue],
        edge_uncertainty: Mapping[str, Uncertainty],
        external: Mapping[str, Mapping[str, CouplingValue]],
        external_uncertainty: Mapping[str, Mapping[str, Uncertainty]],
    ) -> tuple[dict[str, CouplingValue], dict[str, Uncertainty]]:
        result = dict(external[participant_id])
        uncertainty = dict(external_uncertainty[participant_id])
        by_target: dict[str, list] = {}
        for edge in self.graph.incoming(participant_id):
            by_target.setdefault(edge.target.port_id, []).append(edge)

        for port_id, edges in by_target.items():
            edge_tuple = tuple(sorted(edges, key=lambda e: e.edge_id))
            result[port_id] = self.transfer.reduce_for_target(
                edge_tuple, edge_values
            )
            uncertainty[port_id] = combine_fan_in_uncertainty(
                self.graph,
                edge_tuple,
                edge_uncertainty,
            )
        return result, uncertainty

    @staticmethod
    def _seconds(value: Quantity) -> float:
        return value.magnitude_in("second")

    def _maximum_step(
        self, participant_id: str, start: Quantity, end: Quantity
    ) -> Quantity:
        spec = self.graph.participant(participant_id)
        window = self._seconds(end) - self._seconds(start)
        candidates = [window]
        if spec.maximum_time_step is not None:
            candidates.append(spec.maximum_time_step.magnitude_in("second"))
        if spec.preferred_time_step is not None:
            candidates.append(spec.preferred_time_step.magnitude_in("second"))
        return Quantity(min(candidates), "second")

    def _advance_one(
        self,
        participant_id: str,
        start: Quantity,
        end: Quantity,
        inputs: Mapping[str, CouplingValue],
        input_uncertainty: Mapping[str, Uncertainty],
    ) -> AdvanceResult:
        participant = self.participants[participant_id]
        result = participant.advance(
            AdvanceRequest(
                start=start,
                end=end,
                inputs=inputs,
                input_uncertainty=input_uncertainty,
                maximum_step=self._maximum_step(participant_id, start, end),
            )
        )
        validate_outputs(
            participant.spec,
            result.outputs,
            result.uncertainty,
        )
        if result.events and not participant.spec.event_capable:
            # Only declared event-capable participants are checkpointed for
            # event alignment; an undeclared event would be aligned by
            # re-advancing an already-advanced participant.
            raise MultiphysicsExecutionError(
                f"participant {participant_id!r} emitted events but is not "
                f"declared event_capable"
            )

        actual = self._seconds(result.end)
        requested = self._seconds(end)
        tolerance = 1e-12 * max(1.0, abs(requested))
        if actual > requested + tolerance:
            raise MultiphysicsExecutionError(
                f"participant {participant_id!r} advanced beyond synchronization time"
            )
        if not result.internal_converged:
            raise MultiphysicsExecutionError(
                f"participant {participant_id!r} did not converge internally"
            )
        if actual < requested - tolerance:
            terminal = [
                event
                for event in result.events
                if event.terminal
                and abs(self._seconds(event.instant) - actual) <= tolerance
            ]
            if not terminal:
                raise MultiphysicsExecutionError(
                    f"participant {participant_id!r} stopped early without terminal event"
                )
        return result

    def _checkpoint_all(self, instant: Quantity) -> dict[str, RuntimeCheckpoint]:
        checkpoints: dict[str, RuntimeCheckpoint] = {}
        expected = self._seconds(instant)
        for spec in self.graph.participants:
            if not spec.checkpointable:
                continue
            checkpoint = self.participants[spec.participant_id].checkpoint(
                instant
            )
            actual = self._seconds(checkpoint.record.instant)
            if abs(actual - expected) > 1e-12 * max(1.0, abs(expected)):
                raise MultiphysicsExecutionError(
                    f"participant {spec.participant_id!r} checkpoint is at "
                    f"{actual:g}s, requested {expected:g}s"
                )
            if (
                spec.deterministic_restore
                and not checkpoint.record.deterministic_restore
            ):
                raise MultiphysicsExecutionError(
                    f"participant {spec.participant_id!r} declared deterministic "
                    f"restore but its checkpoint record does not"
                )
            checkpoints[spec.participant_id] = checkpoint
        return checkpoints

    def _restore_all(
        self, checkpoints: Mapping[str, RuntimeCheckpoint]
    ) -> None:
        for participant_id in sorted(checkpoints):
            participant = self.participants[participant_id]
            checkpoint = checkpoints[participant_id]
            participant.restore(checkpoint)
            if participant.spec.deterministic_restore:
                replay = participant.checkpoint(checkpoint.record.instant)
                if replay.record.state_digest != checkpoint.record.state_digest:
                    raise MultiphysicsExecutionError(
                        f"participant {participant_id!r} restore is not "
                        f"deterministic: state digest "
                        f"{checkpoint.record.state_digest[:12]}... became "
                        f"{replay.record.state_digest[:12]}..."
                    )

    def _terminal_event(
        self,
        results: Mapping[str, AdvanceResult],
        requested_end: Quantity,
    ) -> Mapping[str, Any] | None:
        end_seconds = self._seconds(requested_end)
        tolerance = 1e-12 * max(1.0, abs(end_seconds))
        candidates: list[tuple[float, str, Any]] = []
        for participant_id, result in results.items():
            for event in result.events:
                when = self._seconds(event.instant)
                if event.terminal and when < end_seconds - tolerance:
                    candidates.append((when, participant_id, event))
        if not candidates:
            return None
        when, participant_id, event = min(
            candidates, key=lambda item: (item[0], item[1], item[2].event_id)
        )
        return {"participant_id": participant_id, **event.to_dict()}

    def _transfer_outgoing(
        self,
        participant_id: str,
        outputs: Mapping[str, Mapping[str, CouplingValue]],
        output_uncertainty: Mapping[str, Mapping[str, Uncertainty]],
        previous: Mapping[str, CouplingValue],
        previous_uncertainty: Mapping[str, Uncertainty],
        *,
        implicit: bool,
        instant: Quantity,
        raw_out: dict[str, CouplingValue] | None = None,
    ) -> tuple[
        dict[str, CouplingValue],
        dict[str, Uncertainty],
        dict[str, TransferResult],
        dict[str, float],
    ]:
        # ``raw_out`` receives each edge's UNRELAXED transferred value H(x_k):
        # the fixed-point residual is measured on it, never on the relaxed
        # increment (which would shrink the residual by the relaxation factor).
        made_values: dict[str, CouplingValue] = {}
        made_uncertainty: dict[str, Uncertainty] = {}
        made_transfers: dict[str, TransferResult] = {}
        factors: dict[str, float] = {}
        instant_text = f"{self._seconds(instant):.17g} second"

        for edge in self.graph.outgoing(participant_id):
            source = outputs[participant_id][edge.source.port_id]
            source_uq = output_uncertainty[participant_id][edge.source.port_id]
            transfer = self.transfer.transfer(
                edge,
                source,
                source_uq,
                instant=instant_text,
            )
            value = transfer.value
            uncertainty = transfer.uncertainty
            if raw_out is not None:
                raw_out[edge.edge_id] = value

            if implicit and edge.edge_id in previous:
                target_port = self.graph.participant(
                    edge.target.participant_id
                ).port(edge.target.port_id)
                value, factor = self.relaxation.relax(
                    edge.edge_id,
                    previous[edge.edge_id],
                    value,
                    unit=target_port.unit,
                )
                uncertainty = relax_uncertainty(
                    previous_uncertainty[edge.edge_id],
                    uncertainty,
                    factor=factor,
                    unit=target_port.unit,
                    edge_id=edge.edge_id,
                )
                factors[edge.edge_id] = factor
                transfer = TransferResult(
                    transfer.edge_id,
                    value,
                    transfer.source_value,
                    transfer.losses,
                    uncertainty,
                    transfer.mapping,
                )

            made_values[edge.edge_id] = value
            made_uncertainty[edge.edge_id] = uncertainty
            made_transfers[edge.edge_id] = transfer

        return made_values, made_uncertainty, made_transfers, factors

    @staticmethod
    def _step_record(
        participant_id: str,
        start: Quantity,
        result: AdvanceResult,
    ) -> ParticipantStepRecord:
        return ParticipantStepRecord(
            participant_id=participant_id,
            start=start,
            end=result.end,
            substeps=result.substeps,
            internal_converged=result.internal_converged,
            events=tuple(event.to_dict() for event in result.events),
            diagnostics=result.diagnostics,
        )

    def _iteration(
        self,
        iteration: int,
        start: Quantity,
        end: Quantity,
        edge_values: Mapping[str, CouplingValue],
        edge_uncertainty: Mapping[str, Uncertainty],
        outputs: Mapping[str, Mapping[str, CouplingValue]],
        output_uncertainty: Mapping[str, Mapping[str, Uncertainty]],
        external: Mapping[str, Mapping[str, CouplingValue]],
        external_uncertainty: Mapping[str, Mapping[str, Uncertainty]],
        previous_transfers: Mapping[str, TransferResult],
        checkpoints: Mapping[str, RuntimeCheckpoint],
    ) -> _IterationOutcome:
        implicit = self.plan.scheme is CouplingScheme.IMPLICIT
        if implicit:
            self._restore_all(checkpoints)

        current_edges = dict(edge_values)
        current_edge_uncertainty = dict(edge_uncertainty)
        current_outputs = {
            pid: dict(values) for pid, values in outputs.items()
        }
        current_output_uncertainty = {
            pid: dict(values)
            for pid, values in output_uncertainty.items()
        }
        current_transfers = dict(previous_transfers)
        steps: list[ParticipantStepRecord] = []
        factors: dict[str, float] = {}
        results: dict[str, AdvanceResult] = {}
        unrelaxed: dict[str, CouplingValue] = {}
        order = self.plan.resolved_order(self.graph)

        if self.plan.iteration_semantics.value == "jacobi":
            frozen_edges = dict(current_edges)
            frozen_uncertainty = dict(current_edge_uncertainty)

            for participant_id in order:
                inputs, input_uncertainty = self._inputs_for(
                    participant_id,
                    frozen_edges,
                    frozen_uncertainty,
                    external,
                    external_uncertainty,
                )
                result = self._advance_one(
                    participant_id,
                    start,
                    end,
                    inputs,
                    input_uncertainty,
                )
                results[participant_id] = result
                current_outputs[participant_id] = dict(result.outputs)
                current_output_uncertainty[participant_id] = dict(
                    result.uncertainty
                )
                steps.append(
                    self._step_record(participant_id, start, result)
                )

            raw_values: dict[str, CouplingValue] = {}
            raw_uncertainty: dict[str, Uncertainty] = {}
            raw_transfers: dict[str, TransferResult] = {}
            for participant_id in order:
                (
                    values,
                    uncertainty,
                    transfers,
                    _,
                ) = self._transfer_outgoing(
                    participant_id,
                    current_outputs,
                    current_output_uncertainty,
                    edge_values,
                    edge_uncertainty,
                    implicit=False,
                    instant=end,
                )
                raw_values.update(values)
                raw_uncertainty.update(uncertainty)
                raw_transfers.update(transfers)

            for edge in self.graph.edges:
                value = raw_values[edge.edge_id]
                uncertainty = raw_uncertainty[edge.edge_id]
                transfer = raw_transfers[edge.edge_id]
                unrelaxed[edge.edge_id] = value
                if implicit:
                    target_port = self.graph.participant(
                        edge.target.participant_id
                    ).port(edge.target.port_id)
                    value, factor = self.relaxation.relax(
                        edge.edge_id,
                        edge_values[edge.edge_id],
                        value,
                        unit=target_port.unit,
                    )
                    uncertainty = relax_uncertainty(
                        edge_uncertainty[edge.edge_id],
                        uncertainty,
                        factor=factor,
                        unit=target_port.unit,
                        edge_id=edge.edge_id,
                    )
                    factors[edge.edge_id] = factor
                    transfer = TransferResult(
                        transfer.edge_id,
                        value,
                        transfer.source_value,
                        transfer.losses,
                        uncertainty,
                        transfer.mapping,
                    )
                current_edges[edge.edge_id] = value
                current_edge_uncertainty[edge.edge_id] = uncertainty
                current_transfers[edge.edge_id] = transfer
        else:
            for participant_id in order:
                inputs, input_uncertainty = self._inputs_for(
                    participant_id,
                    current_edges,
                    current_edge_uncertainty,
                    external,
                    external_uncertainty,
                )
                result = self._advance_one(
                    participant_id,
                    start,
                    end,
                    inputs,
                    input_uncertainty,
                )
                results[participant_id] = result
                current_outputs[participant_id] = dict(result.outputs)
                current_output_uncertainty[participant_id] = dict(
                    result.uncertainty
                )
                steps.append(
                    self._step_record(participant_id, start, result)
                )
                (
                    values,
                    uncertainty,
                    transfers,
                    local_factors,
                ) = self._transfer_outgoing(
                    participant_id,
                    current_outputs,
                    current_output_uncertainty,
                    current_edges,
                    current_edge_uncertainty,
                    implicit=implicit,
                    instant=end,
                    raw_out=unrelaxed,
                )
                current_edges.update(values)
                current_edge_uncertainty.update(uncertainty)
                current_transfers.update(transfers)
                factors.update(local_factors)

        event = self._terminal_event(results, end)
        residuals = []
        if implicit and event is None:
            for criterion in self.plan.criteria:
                edge = self.graph.edge(criterion.edge_id)
                target_port = self.graph.participant(
                    edge.target.participant_id
                ).port(edge.target.port_id)
                # Fixed-point residual r_k = H(x_k) - x_k on the UNRELAXED
                # transfer.  Comparing against the relaxed iterate would
                # report omega * r_k and label a window CONVERGED while the
                # coupled equations are still unsatisfied.
                if criterion.edge_id not in unrelaxed:
                    raise MultiphysicsExecutionError(
                        f"no unrelaxed transfer recorded for criterion edge "
                        f"{criterion.edge_id!r}; the fixed-point residual "
                        f"cannot be measured"
                    )
                residuals.append(
                    self.residuals.compare(
                        criterion,
                        edge_values[criterion.edge_id],
                        unrelaxed[criterion.edge_id],
                        unit=target_port.unit,
                    )
                )

        mapping_diagnostics = [
            {"edge_id": edge_id, "mapping": transfer.mapping.to_dict()}
            for edge_id, transfer in sorted(current_transfers.items())
            if transfer.mapping is not None
        ]
        transfer_diagnostics = [
            transfer.diagnostics()
            for _, transfer in sorted(current_transfers.items())
        ]
        record = CouplingIterationRecord(
            iteration=iteration,
            participant_steps=tuple(steps),
            residuals=tuple(residuals),
            relaxation_factors=factors,
            mapping_diagnostics=tuple(mapping_diagnostics),
            transfer_diagnostics=tuple(transfer_diagnostics),
        )
        return _IterationOutcome(
            edge_values=current_edges,
            edge_uncertainty=current_edge_uncertainty,
            transfers=current_transfers,
            outputs=current_outputs,
            output_uncertainty=current_output_uncertainty,
            record=record,
            event=event,
        )

    def _audit_conservation(
        self, transfers: Mapping[str, TransferResult]
    ) -> tuple[dict[str, Any], ...]:
        checks: list[dict[str, Any]] = []
        for definition in self.graph.conservation:
            left: list[BalanceTerm] = []
            right: list[BalanceTerm] = []

            for binding in definition.terms:
                transfer = transfers.get(binding.edge_id)
                if transfer is None:
                    raise MultiphysicsExecutionError(
                        f"conservation {definition.balance_id!r} references "
                        f"unexecuted edge {binding.edge_id!r}"
                    )

                if binding.measure is TransferMeasure.SOURCE:
                    value = transfer.source_value
                elif binding.measure is TransferMeasure.RECEIVED:
                    value = transfer.value
                else:
                    value = transfer.losses.get(binding.loss_form)
                    if value is None:
                        raise MultiphysicsExecutionError(
                            f"conservation term {binding.name!r} requires loss "
                            f"{binding.loss_form!r} absent from {binding.edge_id!r}"
                        )

                if not isinstance(value, Quantity):
                    raise MultiphysicsExecutionError(
                        f"conservation term {binding.name!r} is field-valued; "
                        f"field conservation is measured by mapping diagnostics"
                    )

                term = BalanceTerm(
                    binding.name,
                    value,
                    evidence=(
                        f"edge:{binding.edge_id}:{binding.measure.value}"
                    ),
                )
                if binding.side is BalanceSide.LEFT:
                    left.append(term)
                else:
                    right.append(term)

            balance = ConservationBalance(
                definition.balance_id,
                tuple(left),
                tuple(right),
                definition.tolerance,
                definition.description,
                reference=f"physics_graph:{self.graph.graph_id}",
            )
            checks.append(balance.to_validation_check().to_dict())

        return tuple(checks)

    def _window(
        self,
        index: int,
        start: Quantity,
        end: Quantity,
        edge_values: Mapping[str, CouplingValue],
        edge_uncertainty: Mapping[str, Uncertainty],
        outputs: Mapping[str, Mapping[str, CouplingValue]],
        output_uncertainty: Mapping[str, Mapping[str, Uncertainty]],
        external: Mapping[str, Mapping[str, CouplingValue]],
        external_uncertainty: Mapping[str, Mapping[str, Uncertainty]],
        transfers: Mapping[str, TransferResult],
    ) -> tuple[
        CouplingWindowRecord,
        dict[str, CouplingValue],
        dict[str, Uncertainty],
        dict[str, dict[str, CouplingValue]],
        dict[str, dict[str, Uncertainty]],
        dict[str, TransferResult],
    ]:
        needs_checkpoint = (
            self.plan.scheme is CouplingScheme.IMPLICIT
            or (
                self.plan.time.align_events
                and any(
                    participant.event_capable
                    for participant in self.graph.participants
                )
            )
        )
        checkpoints = (
            self._checkpoint_all(start) if needs_checkpoint else {}
        )
        self.relaxation.reset_window()

        iterations: list[CouplingIterationRecord] = []
        current_edges = dict(edge_values)
        current_edge_uncertainty = dict(edge_uncertainty)
        current_outputs = {
            pid: dict(values) for pid, values in outputs.items()
        }
        current_output_uncertainty = {
            pid: dict(values)
            for pid, values in output_uncertainty.items()
        }
        current_transfers = dict(transfers)

        for iteration in range(1, self.plan.max_iterations + 1):
            outcome = self._iteration(
                iteration,
                start,
                end,
                current_edges,
                current_edge_uncertainty,
                current_outputs,
                current_output_uncertainty,
                external,
                external_uncertainty,
                current_transfers,
                checkpoints,
            )
            iterations.append(outcome.record)

            if outcome.event is not None and self.plan.time.align_events:
                event_time = Quantity.from_dict(outcome.event["instant"])
                if self._seconds(event_time) <= self._seconds(start):
                    raise MultiphysicsExecutionError(
                        f"terminal event {outcome.event.get('event_id')!r} "
                        f"did not advance beyond coupling-window start"
                    )
                uncovered = sorted(
                    spec.participant_id
                    for spec in self.graph.participants
                    if spec.participant_id not in checkpoints
                    or not spec.deterministic_restore
                )
                if uncovered:
                    # Re-running [start, event] needs every participant back
                    # at ``start``; without a deterministic checkpoint it
                    # would advance twice and be recorded as a clean window.
                    raise MultiphysicsExecutionError(
                        f"event alignment requires deterministic checkpoints of "
                        f"every participant; missing for {uncovered}"
                    )
                self._restore_all(checkpoints)
                (
                    aligned,
                    edges2,
                    edge_uq2,
                    outputs2,
                    output_uq2,
                    transfers2,
                ) = self._window(
                    index,
                    start,
                    event_time,
                    edge_values,
                    edge_uncertainty,
                    outputs,
                    output_uncertainty,
                    external,
                    external_uncertainty,
                    transfers,
                )
                return (
                    CouplingWindowRecord(
                        index=aligned.index,
                        start=aligned.start,
                        end=aligned.end,
                        outcome=WindowOutcome.EVENT_ALIGNED,
                        iterations=aligned.iterations,
                        event=aligned.event or outcome.event,
                    ),
                    edges2,
                    edge_uq2,
                    outputs2,
                    output_uq2,
                    transfers2,
                )

            current_edges = dict(outcome.edge_values)
            current_edge_uncertainty = dict(outcome.edge_uncertainty)
            current_outputs = {
                pid: dict(values)
                for pid, values in outcome.outputs.items()
            }
            current_output_uncertainty = {
                pid: dict(values)
                for pid, values in outcome.output_uncertainty.items()
            }
            current_transfers = dict(outcome.transfers)

            if self.plan.scheme is CouplingScheme.EXPLICIT:
                return (
                    CouplingWindowRecord(
                        index,
                        start,
                        end,
                        WindowOutcome.EXPLICIT_COMPLETED,
                        tuple(iterations),
                    ),
                    current_edges,
                    current_edge_uncertainty,
                    current_outputs,
                    current_output_uncertainty,
                    current_transfers,
                )

            if outcome.record.converged:
                return (
                    CouplingWindowRecord(
                        index,
                        start,
                        end,
                        WindowOutcome.CONVERGED,
                        tuple(iterations),
                    ),
                    current_edges,
                    current_edge_uncertainty,
                    current_outputs,
                    current_output_uncertainty,
                    current_transfers,
                )

        window = CouplingWindowRecord(
            index,
            start,
            end,
            WindowOutcome.ITERATION_LIMIT,
            tuple(iterations),
        )
        if self.plan.fail_on_nonconvergence:
            raise MultiphysicsExecutionError(
                f"coupling window {index} [{start}, {end}] reached "
                f"{self.plan.max_iterations} iterations without convergence"
            )
        return (
            window,
            current_edges,
            current_edge_uncertainty,
            current_outputs,
            current_output_uncertainty,
            current_transfers,
        )

    # =================================================================
    # SCENARIO-DRIVEN EXECUTION
    #
    # Everything below routes DECLARED scenario authority to participants
    # that declared they consume it, and records what was actually
    # delivered as typed evidence.  Three rules hold throughout:
    #
    #   * the scenario digest binds the run whenever ANY scenario-sourced
    #     value reaches it -- an input, an operating condition, an initial
    #     state, an event, a requested quantity or a stop condition;
    #   * a value is delivered only to a consumer that declared it, and a
    #     declared consumer with no value is a refusal rather than a
    #     default;
    #   * consumed inputs are receipts, never outputs.
    # =================================================================

    def _scenario_schedules(
        self,
        schedules: Mapping[PortRef, ComposedInputSchedule],
    ) -> dict[PortRef, ComposedInputSchedule]:
        start_seconds = self._seconds(self.plan.time.start)
        end_seconds = self._seconds(self.plan.time.end)
        width_seconds = self._seconds(self.plan.time.coupling_window)
        for ref, item in schedules.items():
            if not isinstance(ref, PortRef):
                raise InvalidScientificProblem(
                    "scenario input schedule keys must be PortRef"
                )
            if not isinstance(item, ComposedInputSchedule):
                raise InvalidScientificProblem(
                    "scenario input schedules must be ComposedInputSchedule records"
                )
            if item.interpolation is not InterpolationKind.STEP:
                raise InvalidScientificProblem(
                    "runtime currently supports STEP external input series only"
                )
            series = item.series
            if (
                series.samples[0].instant != self.plan.time.start
                or series.samples[-1].instant != self.plan.time.end
            ):
                raise InvalidScientificProblem(
                    "external input series must cover the coupling-plan horizon"
                )
            for sample in series.samples:
                offset = self._seconds(sample.instant) - start_seconds
                aligned = (
                    abs(offset / width_seconds - round(offset / width_seconds)) <= 1e-12
                )
                if not aligned and self._seconds(sample.instant) != end_seconds:
                    raise InvalidScientificProblem(
                        f"STEP input {item.input_id!r} changes away from a "
                        f"coupling-window boundary"
                    )
        return dict(schedules)

    def _operating_condition_plan(
        self,
        conditions: tuple[ComposedOperatingCondition, ...],
    ) -> dict[str, tuple[str, ...]]:
        """Which declared operating conditions each participant consumes.

        Refuses in both directions: a scenario condition nobody declared, and
        a participant declaration the scenario does not supply.  Neither can be
        resolved by assuming a value.
        """
        supplied = {item.condition_id: item for item in conditions}
        consumed: set[str] = set()
        routed: dict[str, tuple[str, ...]] = {}
        for participant_id in sorted(self.participants):
            participant = self.participants[participant_id]
            declared = operating_condition_definitions(participant)
            for definition in declared:
                composed = supplied.get(definition.condition_id)
                if composed is None:
                    raise InvalidScientificProblem(
                        f"participant {participant_id!r} declares operating "
                        f"condition {definition.condition_id!r}, which this "
                        f"scenario does not supply"
                    )
                for _, condition in composed.values:
                    condition.value.require_compatible(
                        definition.unit,
                        context=(
                            f"operating condition {definition.condition_id!r} for "
                            f"{participant_id!r}"
                        ),
                    )
                consumed.add(definition.condition_id)
            if declared:
                routed[participant_id] = tuple(
                    item.condition_id for item in declared
                )
        unconsumed = sorted(set(supplied) - consumed)
        if unconsumed:
            raise InvalidScientificProblem(
                f"scenario operating conditions {unconsumed} reach no authorized "
                f"consumer; an unconsumed condition did not affect execution"
            )
        return routed

    def _bind_parameters(
        self,
        parameter_bindings: Mapping[str, Mapping[str, ParameterValue]],
    ) -> None:
        unknown = sorted(set(parameter_bindings) - set(self.participants))
        if unknown:
            raise InvalidScientificProblem(
                f"parameter bindings name participants outside the execution "
                f"graph: {unknown}"
            )
        for participant_id in sorted(parameter_bindings):
            apply_parameters(
                self.participants[participant_id],
                parameter_bindings[participant_id],
            )

    def _quantity_at(
        self,
        quantity_id: str,
        port: PortRef,
        outputs: Mapping[str, Mapping[str, CouplingValue]],
    ) -> Quantity:
        value = outputs.get(port.participant_id, {}).get(port.port_id)
        if value is None:
            raise MultiphysicsExecutionError(
                f"quantity {quantity_id!r} is bound to {port.key}, which produced "
                f"no value"
            )
        if not isinstance(value, Quantity):
            raise InvalidScientificProblem(
                f"quantity {quantity_id!r} is bound to field-valued output "
                f"{port.key}; a scalar observable is required"
            )
        return value

    def _validate_quantity_bindings(
        self,
        quantity_bindings: Mapping[str, PortRef],
        quantities_of_interest: tuple[QuantityOfInterest, ...],
        termination_conditions: tuple[TerminationCondition, ...],
    ) -> None:
        for quantity_id, port in sorted(
            quantity_bindings.items(), key=lambda item: item[0]
        ):
            if not isinstance(port, PortRef):
                raise InvalidScientificProblem("quantity bindings must map to PortRef")
            spec = self.graph.participant(port.participant_id)
            definition = spec.port(port.port_id)
            if definition.direction is not PortDirection.OUTPUT:
                raise InvalidScientificProblem(
                    f"quantity {quantity_id!r} is bound to {port.key}, which is not "
                    f"a produced output"
                )
        for qoi in quantities_of_interest:
            port = quantity_bindings.get(qoi.quantity_id)
            if port is None:
                raise InvalidScientificProblem(
                    f"requested quantity of interest {qoi.qoi_id!r} names "
                    f"{qoi.quantity_id!r}, which no authorized output produces"
                )
            definition = self.graph.participant(port.participant_id).port(port.port_id)
            Quantity(1.0, definition.unit).require_compatible(
                qoi.unit, context=f"quantity of interest {qoi.qoi_id!r}"
            )
        for condition in termination_conditions:
            metric = condition.constraint.metric
            port = quantity_bindings.get(metric)
            if port is None:
                raise InvalidScientificProblem(
                    f"termination condition {condition.condition_id!r} watches "
                    f"{metric!r}, which no authorized output produces"
                )
            definition = self.graph.participant(port.participant_id).port(port.port_id)
            Quantity(1.0, definition.unit).require_compatible(
                condition.constraint.unit,
                context=f"termination condition {condition.condition_id!r}",
            )

    def _evaluate_termination(
        self,
        conditions: tuple[TerminationCondition, ...],
        quantity_bindings: Mapping[str, PortRef],
        outputs: Mapping[str, Mapping[str, CouplingValue]],
        *,
        boundary_index: int,
        instant: Quantity,
        scenario_digest: str,
    ) -> TerminationReceipt | None:
        """The first declared condition met at this boundary, in id order.

        Deterministic by construction: conditions are sorted, evaluated against
        the values this boundary actually produced, and the winning check is
        carried into the receipt so the stop can be re-derived rather than
        taken on trust.
        """
        for condition in sorted(conditions):
            value = self._quantity_at(
                condition.constraint.metric,
                quantity_bindings[condition.constraint.metric],
                outputs,
            )
            check = condition.constraint.check(value)
            if check.satisfied:
                constraint = condition.constraint
                return TerminationReceipt(
                    condition_id=condition.condition_id,
                    boundary_index=boundary_index,
                    instant=instant,
                    check=check,
                    reason=(
                        f"{constraint.metric} {constraint.operator.value} "
                        f"{constraint.bound.magnitude:.17g} {constraint.bound.units}"
                    ),
                    scenario_digest=scenario_digest,
                )
        return None

    def _state_identities(self, instant: Quantity) -> dict[str, str]:
        found: dict[str, str] = {}
        for participant_id in sorted(self.participants):
            digest = state_identity(self.participants[participant_id], instant)
            if digest is not None:
                found[participant_id] = digest
        return found

    def run(
        self,
        run_id: str,
        *,
        external_inputs: Mapping[PortRef, CouplingValue],
        external_uncertainty: Mapping[PortRef, Uncertainty] = {},
        initial_coupling_values: Mapping[str, CouplingValue] = {},
        initial_coupling_uncertainty: Mapping[str, Uncertainty] = {},
        external_input_schedules: Mapping[PortRef, ComposedInputSchedule] | None = None,
        operating_conditions: tuple[ComposedOperatingCondition, ...] = (),
        initial_state: Mapping[str, Mapping[str, InitialStateValue]] | None = None,
        parameter_bindings: Mapping[str, Mapping[str, ParameterValue]] | None = None,
        scheduled_events: tuple[ScenarioEvent, ...] = (),
        termination_conditions: tuple[TerminationCondition, ...] = (),
        quantity_bindings: Mapping[str, PortRef] | None = None,
        quantities_of_interest: tuple[QuantityOfInterest, ...] = (),
        scenario_digest: str = "",
    ) -> MultiphysicsRunRecord:
        run_id = str(run_id).strip()
        if not run_id:
            raise InvalidScientificProblem("multiphysics run requires run_id")

        requested_state = {} if initial_state is None else dict(initial_state)
        unknown_state_owners = set(requested_state) - set(self.participants)
        if unknown_state_owners:
            raise InvalidScientificProblem(
                "initial state names participants outside the execution graph: "
                f"{sorted(unknown_state_owners)}"
            )

        events = tuple(sorted(scheduled_events))
        if any(not isinstance(item, ScenarioEvent) for item in events):
            raise InvalidScientificProblem(
                "scheduled events must contain ScenarioEvent records"
            )
        if len({item.event_id for item in events}) != len(events):
            raise InvalidScientificProblem("scheduled event ids must be unique")

        schedules = self._scenario_schedules(
            {} if external_input_schedules is None else dict(external_input_schedules)
        )
        conditions = tuple(operating_conditions)
        if any(
            not isinstance(item, ComposedOperatingCondition) for item in conditions
        ):
            raise InvalidScientificProblem(
                "operating conditions must be ComposedOperatingCondition records"
            )
        terminations = tuple(termination_conditions)
        if any(not isinstance(item, TerminationCondition) for item in terminations):
            raise InvalidScientificProblem(
                "termination conditions must be TerminationCondition records"
            )
        if len({item.condition_id for item in terminations}) != len(terminations):
            raise InvalidScientificProblem("termination condition ids must be unique")
        qois = tuple(quantities_of_interest)
        if any(not isinstance(item, QuantityOfInterest) for item in qois):
            raise InvalidScientificProblem(
                "quantities of interest must be QuantityOfInterest records"
            )
        if len({item.qoi_id for item in qois}) != len(qois):
            raise InvalidScientificProblem("quantity of interest ids must be unique")
        bindings = {} if quantity_bindings is None else dict(quantity_bindings)
        self._validate_quantity_bindings(bindings, qois, terminations)

        # SCENARIO IDENTITY, BOUND TO THE RUN RATHER THAN TO ITS EVENTS.
        scenario_digest = str(scenario_digest).strip().lower()
        scenario_bound = bool(
            events
            or schedules
            or conditions
            or terminations
            or qois
            or requested_state
        )
        if scenario_bound and (
            len(scenario_digest) != 64
            or any(char not in "0123456789abcdef" for char in scenario_digest)
        ):
            raise InvalidScientificProblem(
                "scenario-driven execution requires the authorized scenario "
                "sha256 digest; a scenario that supplies state, inputs, "
                "operating conditions, events, quantities of interest or a "
                "termination condition materially participates in the run"
            )
        if scenario_digest and (
            len(scenario_digest) != 64
            or any(char not in "0123456789abcdef" for char in scenario_digest)
        ):
            raise InvalidScientificProblem(
                "scenario digest must be a sha256 hex digest"
            )

        if set(schedules) - set(external_inputs):
            raise InvalidScientificProblem(
                "time-varying external inputs must override declared external ports"
            )
        start_seconds = self._seconds(self.plan.time.start)
        end_seconds = self._seconds(self.plan.time.end)
        width_seconds = self._seconds(self.plan.time.coupling_window)
        event_seconds = tuple(self._seconds(item.instant) for item in events)
        if any(item < start_seconds or item > end_seconds for item in event_seconds):
            raise InvalidScientificProblem(
                "scheduled event lies outside the coupling-plan horizon"
            )

        condition_consumers = self._operating_condition_plan(conditions)
        composed_conditions = {item.condition_id: item for item in conditions}
        # Every instant at which a declared STEP input or operating condition
        # changes is a window boundary, exactly like a scheduled event: a
        # window whose grid was shifted by an event would otherwise deliver
        # the change late, at its next boundary.
        change_seconds = tuple(sorted(
            {self._seconds(sample.instant) for item in schedules.values() for sample in item.series.samples}
            | {self._seconds(contribution.start) for item in conditions for contribution, _ in item.values}
        ))
        if parameter_bindings:
            self._bind_parameters(parameter_bindings)

        def values_at(instant: Quantity):
            values = dict(external_inputs)
            for ref, item in schedules.items():
                values[ref] = item.value_at(instant)
            return values

        external, external_uq = self._external_by_participant(
            values_at(self.plan.time.start),
            external_uncertainty,
        )
        start = self.plan.time.start
        outputs, output_uq, initial_state_receipts = self._initialize(
            start,
            external,
            external_uq,
            requested_state,
        )
        (
            edge_values,
            edge_uq,
            transfers,
        ) = self._initial_transfers(
            outputs,
            output_uq,
            initial_coupling_values,
            initial_coupling_uncertainty,
            start,
        )

        # A run whose stop condition already holds at its start would produce a
        # trajectory of zero windows. Refused, rather than recorded as one.
        opening = self._evaluate_termination(
            terminations,
            bindings,
            outputs,
            boundary_index=0,
            instant=start,
            scenario_digest=scenario_digest,
        )
        if opening is not None:
            for participant_id in sorted(self.participants):
                self.participants[participant_id].finalize()
            raise InvalidScientificProblem(
                f"termination condition {opening.condition_id!r} is already "
                f"satisfied at the scenario start ({opening.reason}); executing "
                f"would record a trajectory the scenario forbids"
            )

        external_records = tuple(
            ExternalInputRecord(
                port=PortRef(participant_id, port_id),
                value=value,
                uncertainty=external_uq[participant_id][port_id],
            )
            for participant_id, values in sorted(external.items())
            for port_id, value in sorted(values.items())
        )
        initial_records = tuple(
            InitialCouplingRecord(
                edge_id=edge_id,
                value=value,
                uncertainty=edge_uq[edge_id],
            )
            for edge_id, value in sorted(
                initial_coupling_values.items()
            )
        )

        windows: list[CouplingWindowRecord] = []
        current_time = self._seconds(start)
        end_time = end_seconds
        width = width_seconds
        index = 0
        last_conservation: tuple[dict[str, Any], ...] = ()
        input_receipts: list[ScenarioInputReceipt] = []
        condition_receipts: list[OperatingConditionReceipt] = []
        transitions: list[StateTransitionReceipt] = []
        termination: TerminationReceipt | None = None
        identities = self._state_identities(start)

        try:
            while current_time < end_time - 1e-15:
                if index >= self.plan.time.max_windows:
                    raise MultiphysicsExecutionError(
                        f"run exceeded max_windows="
                        f"{self.plan.time.max_windows}"
                    )

                next_events = tuple(
                    item for item in event_seconds
                    if item > current_time + 1e-15
                )
                grid_target = current_time + width
                snap = 1e-12 * max(1.0, abs(grid_target))
                next_changes = tuple(
                    item for item in change_seconds
                    if item > current_time + snap
                )
                if next_changes and abs(next_changes[0] - grid_target) <= snap:
                    # the change IS on the grid; land on its exact instant
                    # rather than leave a floating-point sliver window
                    grid_target = next_changes[0]
                target = min(
                    end_time,
                    grid_target,
                    *(next_events[:1]),
                    *(next_changes[:1]),
                )
                instant = Quantity(current_time, "second")
                window_values = values_at(instant)
                external, external_uq = self._external_by_participant(
                    window_values, external_uncertainty
                )
                for ref in sorted(schedules, key=lambda item: item.key):
                    schedule = schedules[ref]
                    input_receipts.append(
                        ScenarioInputReceipt(
                            input_id=schedule.input_id,
                            port=ref,
                            boundary_index=index,
                            instant=instant,
                            segment_id=schedule.segment_at(instant),
                            value=window_values[ref],
                            uncertainty=external_uq[ref.participant_id][ref.port_id],
                            scenario_digest=scenario_digest,
                        )
                    )
                in_force = {
                    condition_id: composed.value_at(instant)
                    for condition_id, composed in composed_conditions.items()
                }
                for participant_id in sorted(condition_consumers):
                    acknowledged = apply_operating_conditions(
                        self.participants[participant_id],
                        instant,
                        {
                            condition_id: OperatingConditionValue(
                                condition_id,
                                in_force[condition_id].value,
                                in_force[condition_id].uncertainty,
                            )
                            for condition_id in condition_consumers[participant_id]
                        },
                    )
                    for accepted in acknowledged:
                        condition_receipts.append(
                            OperatingConditionReceipt(
                                condition_id=accepted.condition_id,
                                participant_id=participant_id,
                                boundary_index=index,
                                instant=instant,
                                segment_id=composed_conditions[
                                    accepted.condition_id
                                ].segment_at(instant),
                                value=accepted.value,
                                uncertainty=accepted.uncertainty,
                                scenario_digest=scenario_digest,
                            )
                        )
                (
                    window,
                    edge_values,
                    edge_uq,
                    outputs,
                    output_uq,
                    transfers,
                ) = self._window(
                    index,
                    Quantity(current_time, "second"),
                    Quantity(target, "second"),
                    edge_values,
                    edge_uq,
                    outputs,
                    output_uq,
                    external,
                    external_uq,
                    transfers,
                )
                last_conservation = self._audit_conservation(transfers)
                windows.append(window)

                new_time = self._seconds(window.end)
                if new_time <= current_time:
                    raise MultiphysicsExecutionError(
                        "coupling window made no time progress"
                    )
                after = self._state_identities(window.end)
                for participant_id in sorted(set(identities) & set(after)):
                    transitions.append(
                        StateTransitionReceipt(
                            participant_id=participant_id,
                            window_index=window.index,
                            start=window.start,
                            end=window.end,
                            start_state_digest=identities[participant_id],
                            end_state_digest=after[participant_id],
                            end_values=public_state(
                                self.participants[participant_id], window.end
                            ),
                            scenario_digest=scenario_digest,
                        )
                    )
                identities = after
                current_time = new_time
                index += 1

                termination = self._evaluate_termination(
                    terminations,
                    bindings,
                    outputs,
                    boundary_index=index,
                    instant=window.end,
                    scenario_digest=scenario_digest,
                )
                if termination is not None:
                    # A mandatory stop is mandatory: nothing continues past it.
                    break
        finally:
            for participant_id in sorted(self.participants):
                self.participants[participant_id].finalize()

        mapping_diagnostics = [
            item
            for window in windows
            for iteration in window.iterations[-1:]
            for item in iteration.mapping_diagnostics
        ]
        error_budget = CouplingErrorBudget.from_mapping_diagnostics(
            mapping_diagnostics
        )

        final_outputs: dict[str, Any] = {
            f"{participant_id}.{port_id}": value.to_dict()
            for participant_id, values in sorted(outputs.items())
            for port_id, value in sorted(values.items())
        }
        final_outputs["_uncertainty"] = {
            f"{participant_id}.{port_id}": uncertainty.to_dict()
            for participant_id, values in sorted(output_uq.items())
            for port_id, uncertainty in sorted(values.items())
        }
        final_outputs["_edge_uncertainty"] = {
            edge_id: uncertainty.to_dict()
            for edge_id, uncertainty in sorted(edge_uq.items())
        }
        final_outputs["_conservation"] = list(last_conservation)
        final_outputs["_coupling_error"] = error_budget.to_dict()

        ended_at = Quantity(current_time, "second")
        qoi_records = tuple(
            QuantityOfInterestRecord(
                qoi_id=qoi.qoi_id,
                quantity_id=qoi.quantity_id,
                port=bindings[qoi.quantity_id],
                instant=ended_at,
                value=self._quantity_at(
                    qoi.quantity_id, bindings[qoi.quantity_id], outputs
                ),
                uncertainty=output_uq[bindings[qoi.quantity_id].participant_id][
                    bindings[qoi.quantity_id].port_id
                ],
                scenario_digest=scenario_digest,
            )
            for qoi in sorted(qois)
        )
        for record, qoi in zip(qoi_records, sorted(qois)):
            record.require_unit(qoi.unit)

        scheduled_records = tuple(
            ScheduledEventRecord(item.event_id, item.instant) for item in events
        )
        reached_records: list[ReachedScheduledEvent] = []
        boundaries = ((0, start),) + tuple(
            (window.index + 1, window.end) for window in windows
        )
        for item in scheduled_records:
            match = next(
                (
                    boundary_index for boundary_index, instant in boundaries
                    if abs(self._seconds(instant) - self._seconds(item.instant)) <= 1e-12
                ),
                None,
            )
            if match is not None:
                reached_records.append(
                    ReachedScheduledEvent(item.event_id, item.instant, match)
                )

        return MultiphysicsRunRecord(
            run_id=run_id,
            graph=self.graph,
            plan=self.plan,
            started_at=start,
            ended_at=ended_at,
            external_inputs=external_records,
            initial_coupling=initial_records,
            windows=tuple(windows),
            final_outputs=final_outputs,
            coupling_error_bound=error_budget.relative_bound,
            initial_state_receipts=initial_state_receipts,
            scheduled_events=scheduled_records,
            reached_scheduled_events=tuple(reached_records),
            scenario_digest=scenario_digest,
            scenario_input_receipts=tuple(input_receipts),
            operating_condition_receipts=tuple(condition_receipts),
            state_transitions=tuple(transitions),
            termination=termination,
            quantities_of_interest=qoi_records,
        )
