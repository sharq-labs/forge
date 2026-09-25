"""Participant and field adapters between providers and the multiphysics runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
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


class StateCompleteness(str, Enum):
    #: The participant's owner DECLARED that ``declared_state`` is everything a
    #: continuation needs (a declaration, recorded with its basis -- never
    #: inferred from object equality, serialization or attribute enumeration).
    DECLARED_COMPLETE = "declared_complete"
    #: Nobody has established what hidden state the provider keeps.  Normal
    #: execution may proceed; checkpoint-resume and deterministic-replay
    #: claims that need complete state are refused.
    NOT_ESTABLISHED = "not_established"


@dataclass(frozen=True)
class ParticipantStateContract:
    """Explicit checkpoint-completeness contract of one participant.

    ``declared_state`` names every authoritative variable a restart needs;
    ``evolved_state`` is the subset the participant's own solve advances
    (FAST state); the rest is held read-only during a solve (e.g. SLOW
    lifecycle state that only a degradation step may change).
    """

    participant_id: str
    declared_state: tuple[str, ...]
    evolved_state: tuple[str, ...]
    completeness: StateCompleteness
    basis: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "completeness", StateCompleteness(self.completeness))
        declared = tuple(sorted(str(v) for v in self.declared_state))
        evolved = tuple(sorted(str(v) for v in self.evolved_state))
        if len(set(declared)) != len(declared) or not set(evolved) <= set(declared):
            raise CouplingRefusal("evolved state must be a subset of unique declared state")
        if not str(self.basis or "").strip():
            raise CouplingRefusal("a state contract must state the basis of its completeness claim")
        object.__setattr__(self, "declared_state", declared)
        object.__setattr__(self, "evolved_state", evolved)

    @property
    def restartable(self) -> bool:
        return self.completeness is StateCompleteness.DECLARED_COMPLETE

    def to_dict(self) -> dict[str, Any]:
        return {"participant_id": self.participant_id, "declared_state": list(self.declared_state),
                "evolved_state": list(self.evolved_state), "completeness": self.completeness.value, "basis": self.basis}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "ParticipantStateContract":
        return cls(p["participant_id"], tuple(p["declared_state"]), tuple(p["evolved_state"]), p["completeness"], p["basis"])


@dataclass
class CouplingExecutionLog:
    """Every provider execution a participant performed, in order (replay/identity evidence only)."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def identities(self) -> list[str]:
        return [e["execution_identity"] for e in self.entries]


def provider_participant(
    spec: ParticipantSpec,
    *,
    solve: Callable[..., tuple],
    initial_outputs: Callable[[], Mapping[str, Any]],
    store: BulkDataStore,
    log: CouplingExecutionLog | None = None,
    output_uncertainty: str = "participant output uncertainty is not quantified by the provider",
    state_definitions: tuple = (),
    evolved_state: tuple[str, ...] = (),
    state_contract: ParticipantStateContract | None = None,
) -> CallbackParticipant:
    """Wrap a provider solve into a runtime participant.

    ``solve(inputs, start, end, input_uncertainty, state)`` must build its
    provider problem from ``inputs`` and ``state`` (so each iterate is a new
    problem identity) and return ``(record, outputs)`` or, when the
    participant evolves state, ``(record, outputs, next_state)``.  A record
    whose ``succeeded`` is False makes the participant refuse -- the runtime
    then refuses the window.

    State progression: ``evolved_state`` names the declared variables the
    solve advances (FAST state); ``next_state`` must carry exactly those, and
    the participant then holds them, publishes them in its state-transition
    receipt and checkpoints them.  Every other declared variable is held
    read-only for the solve: a solve that tries to return it is refused,
    because only an explicit lifecycle/state-transition step may change
    SLOW state.

    ``state_contract`` is the explicit checkpoint-completeness declaration.
    Without one the participant is ``NOT_ESTABLISHED``: it runs, but callers
    that need complete state for resume/replay must refuse it.

    ``initial_outputs`` are DECLARED initial iterates, used only to seed the
    first coupling iteration; they are labelled as such in diagnostics and are
    never reported as results.

    Output uncertainty is UNKNOWN: a provider's convergence says nothing about
    model or input uncertainty, and none is invented here.  Incoming
    uncertainty kinds are recorded, never upgraded.
    """
    import hashlib
    import json

    from ..execution.multiphysics import InitialStateReceipt, InitialStateValue
    from ..execution.multiphysics.participant import RuntimeCheckpoint
    from ..scientific.multiphysics.receipts import StateVariableValue
    from ..scientific.multiphysics.state import CheckpointRecord

    log = log if log is not None else CouplingExecutionLog()
    held: dict[str, Any] = {"state": {}}
    unknown = Uncertainty.unknown(output_uncertainty)
    definitions = {d.variable_id: d for d in state_definitions}
    evolved = tuple(sorted(evolved_state))
    if not set(evolved) <= set(definitions):
        raise CouplingRefusal(f"participant {spec.participant_id!r} evolves undeclared state {sorted(set(evolved) - set(definitions))}")
    contract = state_contract if state_contract is not None else ParticipantStateContract(
        spec.participant_id, tuple(definitions), evolved, StateCompleteness.NOT_ESTABLISHED,
        "no checkpoint-completeness declaration was made for this participant")
    if (contract.participant_id, contract.declared_state, contract.evolved_state) != (spec.participant_id, tuple(sorted(definitions)), evolved):
        raise CouplingRefusal(f"state contract of {spec.participant_id!r} does not match its declared/evolved state")

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

    def next_state_values(next_state: Mapping[str, Any]) -> dict[str, Any]:
        returned = set(next_state)
        if returned - set(evolved):
            raise CouplingRefusal(
                f"participant {spec.participant_id!r} solve returned held (non-evolved) state "
                f"{sorted(returned - set(evolved))}; only an explicit state transition may change it")
        if returned != set(evolved):
            raise CouplingRefusal(f"participant {spec.participant_id!r} solve omitted evolved state {sorted(set(evolved) - returned)}")
        made = {}
        for k in evolved:
            v = next_state[k]
            if isinstance(v, (StateVariableValue, InitialStateValue)):
                value, uq = v.value, v.uncertainty
            elif isinstance(v, Quantity):
                value, uq = v, Uncertainty.unknown(f"state {k!r} advanced by the provider; its uncertainty is not quantified")
            else:
                raise CouplingRefusal(f"evolved state {k!r} must be a Quantity or state value")
            value.require_compatible(definitions[k].unit, context=f"evolved state {k!r}")
            made[k] = InitialStateValue(k, value, uq)
        return made

    def initialize(_instant, _inputs, _uq):
        return InitializationResult(to_runtime(initial_outputs()), {p.port_id: unknown for p in spec.outputs},
                                    diagnostics={"classification": "declared_initial_iterate_not_a_result"})

    def advance(request):
        missing = [p.port_id for p in spec.inputs if p.port_id not in request.inputs]
        if missing:
            raise CouplingRefusal(f"participant {spec.participant_id!r} is missing coupling inputs {missing}; they are never zero")
        produced = solve(dict(request.inputs), request.start, request.end, dict(request.input_uncertainty), dict(held["state"]))
        if not isinstance(produced, tuple) or len(produced) not in (2, 3):
            raise CouplingRefusal("solve must return (record, outputs) or (record, outputs, next_state)")
        record, outputs = produced[0], produced[1]
        next_state = produced[2] if len(produced) == 3 else {}
        entry = {
            "participant": spec.participant_id, "start_s": request.start.magnitude_in("s"), "end_s": request.end.magnitude_in("s"),
            "execution_identity": getattr(record, "execution_identity", ""), "record_digest": getattr(record, "digest", ""),
            "succeeded": bool(getattr(record, "succeeded", False)), "reason": getattr(record, "reason", ""),
            "input_uncertainty_kinds": {k: u.kind.value for k, u in dict(request.input_uncertainty).items()},
        }
        log.entries.append(entry)
        if not entry["succeeded"]:
            raise CouplingRefusal(f"participant {spec.participant_id!r} execution failed: {entry['reason']}")
        if evolved or next_state:
            held["state"] = {**held["state"], **next_state_values(next_state)}
        return AdvanceResult(request.end, to_runtime(outputs), {p.port_id: unknown for p in spec.outputs}, 1, True,
                             diagnostics={k: v for k, v in entry.items() if k != "input_uncertainty_kinds"})

    def state_digest() -> str:
        # value, unit AND uncertainty: a changed uncertainty is a changed state
        payload = [held["state"][k].to_dict() for k in sorted(held["state"])]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def checkpoint(instant):
        return RuntimeCheckpoint(
            CheckpointRecord(spec.participant_id, instant, state_digest(), spec.deterministic_restore,
                             provider_state_id=f"completeness:{contract.completeness.value}"),
            dict(held["state"]))

    def restore(cp):
        if cp.record.participant_id != spec.participant_id:
            raise CouplingRefusal("checkpoint belongs to another participant")
        held["state"] = dict(cp.token)

    if not state_definitions:
        participant = CallbackParticipant(spec, initialize=initialize, advance=advance, checkpoint=checkpoint, restore=restore,
                                          state_identity=lambda _t: state_digest())
        participant.state_contract = contract
        return participant

    def initialize_state(instant, state, _inputs, _uq):
        held["state"] = dict(state)
        receipt = InitialStateReceipt(spec.participant_id, instant, tuple(state[k] for k in sorted(state)), state_digest())
        result = initialize(instant, _inputs, _uq)
        return InitializationResult(result.outputs, result.uncertainty, result.diagnostics, initial_state_receipt=receipt)

    participant = CallbackParticipant(
        spec, initialize=lambda *a: (_ for _ in ()).throw(CouplingRefusal(f"{spec.participant_id} requires an explicit initial state")),
        advance=advance, initial_state_definitions=tuple(state_definitions), initialize_state=initialize_state,
        checkpoint=checkpoint, restore=restore,
        state_identity=lambda _t: state_digest(),
        public_state=lambda _t: tuple(StateVariableValue(k, v.value, v.uncertainty) for k, v in sorted(held["state"].items())),
    )
    participant.state_contract = contract
    return participant
