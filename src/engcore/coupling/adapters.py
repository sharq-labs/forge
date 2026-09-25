"""Participant and field adapters between providers and the multiphysics runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from ..data.field import FieldValue
from ..data.resolver import BulkDataResolver
from ..data.store import BulkDataStore
from ..execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult
from ..scientific.errors import InvalidScientificProblem
from ..scientific.fields import FieldDefinition, FieldLocation, FieldRecord
from ..scientific.multiphysics import (
    FieldAlgebra, ParticipantSpec, PortDefinition, PortDirection, PortKind,
)
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity
from ..spatial import Derivation, Location, Rank, SpatialField, SpatialFieldDefinition, SpatialMesh


class CouplingRefusal(InvalidScientificProblem):
    """A coupling step that cannot proceed without inventing or accepting something unsupported."""


# --------------------------------------------------------------------------
# Ports and field conversion
# --------------------------------------------------------------------------


def scalar_port(port_id: str, direction: str, quantity: str, unit: str) -> PortDefinition:
    return PortDefinition(port_id, PortDirection(direction), PortKind.SCALAR, quantity, unit)


def _core_definition(definition: SpatialFieldDefinition, mesh: SpatialMesh, store: BulkDataStore) -> FieldDefinition:
    if definition.location not in (Location.NODE, Location.CELL):
        raise CouplingRefusal("runtime field ports carry node or cell fields only")
    support = mesh.core_support(store)
    return FieldDefinition(definition.field_id, definition.unit, support.mesh_id, FieldLocation(definition.location.value),
                           definition.components(mesh.frame.dimension))


def field_port(port_id: str, direction: str, definition: SpatialFieldDefinition, mesh: SpatialMesh, store: BulkDataStore) -> PortDefinition:
    """A runtime field port bound to the exact core support of a BIG 7 mesh (and its frame for vectors)."""
    algebra = {Rank.SCALAR: FieldAlgebra.SCALAR, Rank.VECTOR: FieldAlgebra.VECTOR, Rank.TENSOR: FieldAlgebra.TENSOR_2}[definition.rank]
    frame = "" if definition.rank is Rank.SCALAR else mesh.frame.frame_id
    return PortDefinition(port_id, PortDirection(direction), PortKind.FIELD, definition.quantity_id, definition.unit,
                          field=_core_definition(definition, mesh, store), algebra=algebra, coordinate_frame=frame)


def spatial_to_record(field_value: SpatialField, store: BulkDataStore) -> FieldRecord:
    """Store a (COMPUTED/PRESCRIBED) BIG 7 field as the Core record a runtime port carries."""
    field_value.mesh.core_support(store)  # coordinates/connectivity bytes available to mappers
    record, _ = field_value.to_core().store(store)
    return record


def record_to_spatial(record: FieldRecord, definition: SpatialFieldDefinition, mesh: SpatialMesh,
                      resolver: BulkDataResolver, store: BulkDataStore) -> SpatialField:
    """A coupling input back as a BIG 7 field on the consumer's exact mesh.

    Refuses a record on another support, in another unit dimension, location
    or component count.  The consumed field keeps the record's content digest
    as provenance, so the consumer's problem identity binds EXACTLY what it read.
    """
    support = mesh.core_support(store)
    if record.definition.mesh_id != support.mesh_id or record.mesh_fingerprint != support.fingerprint():
        raise CouplingRefusal(f"field {record.definition.field_id!r} is on a different support than the consumer mesh")
    expected = _core_definition(definition, mesh, store)
    if record.definition.location != expected.location or record.definition.components != expected.components:
        raise CouplingRefusal("coupling field location/components do not match the consumer port")
    value = FieldValue.from_record(record, support, resolver).to_unit(definition.unit)
    # Transport does not change values: the field stays COMPUTED, and its
    # provenance names the exact record bytes and support it was read from.
    return SpatialField(definition, mesh, value.values, Derivation.COMPUTED,
                        (f"coupling_input:{record.reference.digest}", f"support:{record.mesh_fingerprint}"))


def mapped_input(record: FieldRecord, definition: SpatialFieldDefinition, source_mesh: SpatialMesh, target_mesh: SpatialMesh,
                 resolver: BulkDataResolver, store: BulkDataStore):
    """Read a coupling field on its SOURCE mesh and map it to the consumer mesh with BIG 7 P1 interpolation.

    Returns ``(mapped SpatialField, MappingRecord)``.  The mapping refuses
    extrapolation and frame mismatch, is labelled NOT_CONSERVATIVE with its
    integral diagnostics, and the mapped field's provenance carries the mapping
    record digest -- so the consumer's problem identity binds the exact mapping.
    """
    from ..spatial import interpolate_p1_to_mesh

    source = record_to_spatial(record, definition, source_mesh, resolver, store)
    return interpolate_p1_to_mesh(source, target_mesh)


# --------------------------------------------------------------------------
# Participant adapter
# --------------------------------------------------------------------------


@dataclass
class CouplingExecutionLog:
    """Every provider execution a participant performed, in order (replay/identity evidence only)."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def identities(self) -> list[str]:
        return [e["execution_identity"] for e in self.entries]


def provider_participant(
    spec: ParticipantSpec,
    *,
    solve: Callable[[Mapping[str, Any], Quantity, Quantity, Mapping[str, Uncertainty], Mapping[str, Any]], tuple[Any, Mapping[str, Any]]],
    initial_outputs: Callable[[], Mapping[str, Any]],
    store: BulkDataStore,
    log: CouplingExecutionLog | None = None,
    output_uncertainty: str = "participant output uncertainty is not quantified by the provider",
    state_definitions: tuple = (),
) -> CallbackParticipant:
    """Wrap a provider solve into a runtime participant.

    ``solve(inputs, start, end, input_uncertainty, state) -> (record, outputs)``
    must build its provider problem from ``inputs`` (so each iterate is a new
    problem identity) and return the provider's execution record plus the
    output values (Quantity or SpatialField).  A record whose ``succeeded`` is
    False makes the participant refuse -- the runtime then refuses the window.

    ``initial_outputs`` are DECLARED initial iterates, used only to seed the
    first coupling iteration; they are labelled as such in diagnostics and are
    never reported as results.

    Output uncertainty is UNKNOWN: a provider's convergence says nothing about
    model or input uncertainty, and none is invented here.  Incoming
    uncertainty kinds are recorded, never upgraded.
    """
    log = log if log is not None else CouplingExecutionLog()
    held: dict[str, Any] = {"state": {}}
    unknown = Uncertainty.unknown(output_uncertainty)

    def to_runtime(values: Mapping[str, Any]) -> dict[str, Any]:
        out = {}
        for port in spec.outputs:
            if port.port_id not in values:
                raise CouplingRefusal(f"participant {spec.participant_id!r} produced no value for output {port.port_id!r}")
            v = values[port.port_id]
            if isinstance(v, SpatialField):
                if v.derivation not in (Derivation.COMPUTED, Derivation.PRESCRIBED):
                    raise CouplingRefusal(f"output {port.port_id!r} must be a computed or prescribed field")
                v = spatial_to_record(v, store)
            out[port.port_id] = v
        return out

    def initialize(_instant, _inputs, _uq):
        return InitializationResult(to_runtime(initial_outputs()), {p.port_id: unknown for p in spec.outputs},
                                    diagnostics={"classification": "declared_initial_iterate_not_a_result"})

    def advance(request):
        missing = [p.port_id for p in spec.inputs if p.port_id not in request.inputs]
        if missing:
            raise CouplingRefusal(f"participant {spec.participant_id!r} is missing coupling inputs {missing}; they are never zero")
        record, outputs = solve(dict(request.inputs), request.start, request.end, dict(request.input_uncertainty), dict(held["state"]))
        entry = {
            "participant": spec.participant_id, "start_s": request.start.magnitude_in("s"), "end_s": request.end.magnitude_in("s"),
            "execution_identity": getattr(record, "execution_identity", ""), "record_digest": getattr(record, "digest", ""),
            "succeeded": bool(getattr(record, "succeeded", False)), "reason": getattr(record, "reason", ""),
            "input_uncertainty_kinds": {k: u.kind.value for k, u in dict(request.input_uncertainty).items()},
        }
        log.entries.append(entry)
        if not entry["succeeded"]:
            raise CouplingRefusal(f"participant {spec.participant_id!r} execution failed: {entry['reason']}")
        return AdvanceResult(request.end, to_runtime(outputs), {p.port_id: unknown for p in spec.outputs}, 1, True,
                             diagnostics={k: v for k, v in entry.items() if k != "input_uncertainty_kinds"})

    import hashlib

    from ..execution.multiphysics import InitialStateReceipt
    from ..execution.multiphysics.participant import RuntimeCheckpoint
    from ..scientific.multiphysics.receipts import StateVariableValue
    from ..scientific.multiphysics.state import CheckpointRecord

    def state_digest() -> str:
        return hashlib.sha256(repr(sorted((k, v.value.to_dict()["magnitude"], v.value.units) for k, v in held["state"].items())).encode()).hexdigest()

    # Each solve is rebuilt from (coupling inputs, held state); the held state is
    # therefore the COMPLETE participant state, and a checkpoint of it restores
    # deterministically -- which is what implicit window replay requires.
    def checkpoint(instant):
        return RuntimeCheckpoint(CheckpointRecord(spec.participant_id, instant, state_digest(), True), dict(held["state"]))

    def restore(cp):
        held["state"] = dict(cp.token)

    if not state_definitions:
        return CallbackParticipant(spec, initialize=initialize, advance=advance, checkpoint=checkpoint, restore=restore,
                                   state_identity=lambda _t: state_digest())

    def initialize_state(instant, state, _inputs, _uq):
        held["state"] = dict(state)
        receipt = InitialStateReceipt(spec.participant_id, instant, tuple(state.values()), state_digest())
        result = initialize(instant, _inputs, _uq)
        return InitializationResult(result.outputs, result.uncertainty, result.diagnostics, initial_state_receipt=receipt)

    return CallbackParticipant(
        spec, initialize=lambda *a: (_ for _ in ()).throw(CouplingRefusal(f"{spec.participant_id} requires an explicit initial state")),
        advance=advance, initial_state_definitions=tuple(state_definitions), initialize_state=initialize_state,
        checkpoint=checkpoint, restore=restore,
        state_identity=lambda _t: state_digest(),
        public_state=lambda _t: tuple(StateVariableValue(k, v.value, v.uncertainty) for k, v in sorted(held["state"].items())),
    )
