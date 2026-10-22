"""Binding world values to the owner records that state them.

A world never authors a current value of a state, a measurement or a nuisance: it copies it from its owner record and
embeds that record's own digest (:class:`~.base.RecordRef`).  These binders are the copy, and
:meth:`ScientificWorld.verify_bindings` re-reads the same records to confirm the copy.  BR1 reads the two owners whose
records carry a value and its uncertainty together:

* ``system_runtime.SystemState``: the committed state of a run (an ``InitialStateValue`` per owner and variable);
* ``scientific.measurements.CalibratedMeasurementObservation``: a calibrated observation (value, MEASUREMENT-sourced
  uncertainty) of the quantity it names.

A record is accepted only as exactly its owner's type (its digest is then the owner's own rule, never an attribute a
caller supplies).  A committed state that a supplied state supersedes is refused: which state is current is the state
owner's statement, supplied with the records.  An observation binds only the variable named by the quantity it states
it measured.  Any other record kind is refused, not guessed: a binder for it is a later, owner-specific addition.
"""

from __future__ import annotations

from typing import Any, Iterable

from engcore.scientific.measurements.observation import CalibratedMeasurementObservation
from engcore.system_runtime.state import SystemState

from .base import RecordKind, RecordRef, WorldRefused
from .variables import ValueOrigin

OWNER_TYPES = {RecordKind.SYSTEM_STATE: SystemState, RecordKind.MEASUREMENT_OBSERVATION: CalibratedMeasurementObservation}


def _owner_record(kind: RecordKind, record: Any) -> Any:
    owner = OWNER_TYPES.get(kind)
    if owner is None:
        raise WorldRefused(f"BR1 cannot read a {kind.value} record; its binder is not implemented")
    if type(record) is not owner:
        raise WorldRefused(f"a {kind.value} binding reads exactly a {owner.__name__}, not {type(record).__name__}")
    return record


def _state_value(state: SystemState, variable_id: str) -> Any:
    found = [v for owner in state.owners for v in owner.values if v.variable_id == variable_id]
    if len(found) != 1:
        raise WorldRefused(f"the system state holds {len(found)} values for {variable_id!r}; a binding needs exactly one")
    return found[0]


def read_bound(kind: RecordKind, record: Any, name: str, supplied: Iterable[Any] = ()) -> tuple[Any, Any]:
    """(value, uncertainty) as the owner record states them for world variable ``name``.

    ``supplied`` is every record the caller supplied; a committed state superseded by one of them is refused."""
    record = _owner_record(kind, record)
    if kind is RecordKind.SYSTEM_STATE:
        successors = [s for s in supplied if type(s) is SystemState and s.previous_digest == record.digest]
        if successors:
            raise WorldRefused(f"{name!r}: the bound state {record.digest[:12]} is superseded by the supplied state "
                               f"{successors[0].digest[:12]}; re-bind to the state owner's current state")
        v = _state_value(record, name)
        return v.value, v.uncertainty
    if record.quantity != name:
        raise WorldRefused(f"{name!r}: the observation states it measured {record.quantity!r}, not {name!r}")
    return record.value, record.uncertainty


def from_system_state(state: SystemState, variable_id: str, *,
                      origin: ValueOrigin = ValueOrigin.OBSERVED) -> dict[str, Any]:
    """WorldVariable value fields copied from a committed ``SystemState`` (value, uncertainty, the state's digest)."""
    state = _owner_record(RecordKind.SYSTEM_STATE, state)
    v = _state_value(state, variable_id)
    return {"value": v.value, "origin": origin, "source": RecordRef(RecordKind.SYSTEM_STATE, state.digest),
            "uncertainty": v.uncertainty}


def from_measurement(observation: CalibratedMeasurementObservation, variable: str) -> dict[str, Any]:
    """WorldVariable value fields copied from a ``CalibratedMeasurementObservation`` of ``variable``."""
    observation = _owner_record(RecordKind.MEASUREMENT_OBSERVATION, observation)
    if observation.quantity != variable:
        raise WorldRefused(f"the observation measured {observation.quantity!r}, not {variable!r}")
    return {"value": observation.value, "origin": ValueOrigin.OBSERVED,
            "source": RecordRef(RecordKind.MEASUREMENT_OBSERVATION, observation.digest),
            "uncertainty": observation.uncertainty}


__all__ = ["OWNER_TYPES", "from_measurement", "from_system_state", "read_bound"]
