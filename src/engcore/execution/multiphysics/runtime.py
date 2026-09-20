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
    MultiphysicsRunRecord,
    ParticipantStepRecord,
    PhysicsGraph,
    PortDirection,
    PortRef,
    TransferMeasure,
    WindowOutcome,
)
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.units.quantity import Quantity
from .convergence import ResidualCalculator
from .error import CouplingErrorBudget
from .factory import ParticipantFactoryRegistry
from .participant import (
    AdvanceRequest,
    AdvanceResult,
    CouplingValue,
    ExecutableParticipant,
    RuntimeCheckpoint,
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
        return cls(
            graph,
            plan,
            registry.build_graph(graph),
            resolver=resolver,
            store=store,
        )

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
    ) -> tuple[
        dict[str, dict[str, CouplingValue]],
        dict[str, dict[str, Uncertainty]],
    ]:
        outputs: dict[str, dict[str, CouplingValue]] = {}
        uncertainty: dict[str, dict[str, Uncertainty]] = {}
        for participant_id in self.plan.resolved_order(self.graph):
            participant = self.participants[participant_id]
            made = participant.initialize(
                start,
                external[participant_id],
                external_uncertainty[participant_id],
            )
            validate_outputs(
                participant.spec,
                made.outputs,
                made.uncertainty,
            )
            outputs[participant_id] = dict(made.outputs)
            uncertainty[participant_id] = dict(made.uncertainty)
        return outputs, uncertainty

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
    ) -> tuple[
        dict[str, CouplingValue],
        dict[str, Uncertainty],
        dict[str, TransferResult],
        dict[str, float],
    ]:
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
                residuals.append(
                    self.residuals.compare(
                        criterion,
                        edge_values[criterion.edge_id],
                        current_edges[criterion.edge_id],
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
            checks.append(balance.to_check().to_dict())

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

    def run(
        self,
        run_id: str,
        *,
        external_inputs: Mapping[PortRef, CouplingValue],
        external_uncertainty: Mapping[PortRef, Uncertainty] = {},
        initial_coupling_values: Mapping[str, CouplingValue] = {},
        initial_coupling_uncertainty: Mapping[str, Uncertainty] = {},
    ) -> MultiphysicsRunRecord:
        run_id = str(run_id).strip()
        if not run_id:
            raise InvalidScientificProblem("multiphysics run requires run_id")

        external, external_uq = self._external_by_participant(
            external_inputs,
            external_uncertainty,
        )
        start = self.plan.time.start
        outputs, output_uq = self._initialize(
            start,
            external,
            external_uq,
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
        end_time = self._seconds(self.plan.time.end)
        width = self._seconds(self.plan.time.coupling_window)
        index = 0
        last_conservation: tuple[dict[str, Any], ...] = ()

        try:
            while current_time < end_time - 1e-15:
                if index >= self.plan.time.max_windows:
                    raise MultiphysicsExecutionError(
                        f"run exceeded max_windows="
                        f"{self.plan.time.max_windows}"
                    )

                target = min(end_time, current_time + width)
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
                current_time = new_time
                index += 1
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

        return MultiphysicsRunRecord(
            run_id=run_id,
            graph=self.graph,
            plan=self.plan,
            started_at=start,
            ended_at=Quantity(current_time, "second"),
            external_inputs=external_records,
            initial_coupling=initial_records,
            windows=tuple(windows),
            final_outputs=final_outputs,
            coupling_error_bound=error_budget.relative_bound,
        )
