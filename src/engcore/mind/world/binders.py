"""Binding world values to the owner records that state them.

A world never authors a current value of a state, a measurement or a nuisance: it copies it from its owner record and
embeds that record's own digest (:class:`~.base.RecordRef`).  These binders are the copy, and
:meth:`ScientificWorld.verify_bindings` re-reads the same records to confirm the copy.  BR1 reads the two owners whose
records carry a value and its uncertainty together:

* ``system_runtime.SystemState``: the committed state of a run (an ``InitialStateValue`` per owner and variable);
* ``scientific.measurements.CalibratedMeasurementObservation``: a calibrated observation (value, MEASUREMENT-sourced
  uncertainty).

Any other record kind is refused here, not guessed: a binder for it is a later, owner-specific addition.
"""

from __future__ import annotations

from typing import Any

from .base import RecordKind, RecordRef, WorldRefused
from .variables import ValueOrigin


def _state_value(state: Any, variable_id: str) -> Any:
    found = [v for owner in state.owners for v in owner.values if v.variable_id == variable_id]
    if len(found) != 1:
        raise WorldRefused(f"the system state holds {len(found)} values for {variable_id!r}; a binding needs exactly one")
    return found[0]


def read_bound(kind: RecordKind, record: Any, name: str) -> tuple[Any, Any]:
    """(value, uncertainty) as the owner record states them for world variable ``name``."""
    if kind is RecordKind.SYSTEM_STATE:
        v = _state_value(record, name)
        return v.value, v.uncertainty
    if kind is RecordKind.MEASUREMENT_OBSERVATION:
        return record.value, record.uncertainty
    raise WorldRefused(f"BR1 cannot read a {kind.value} record; its binder is not implemented")


def from_system_state(state: Any, variable_id: str, *, origin: ValueOrigin = ValueOrigin.OBSERVED) -> dict[str, Any]:
    """WorldVariable value fields copied from a committed ``SystemState`` (value, uncertainty, the state's digest)."""
    v = _state_value(state, variable_id)
    return {"value": v.value, "origin": origin, "source": RecordRef(RecordKind.SYSTEM_STATE, state.digest),
            "uncertainty": v.uncertainty}


def from_measurement(observation: Any) -> dict[str, Any]:
    """WorldVariable value fields copied from a ``CalibratedMeasurementObservation``."""
    return {"value": observation.value, "origin": ValueOrigin.OBSERVED,
            "source": RecordRef(RecordKind.MEASUREMENT_OBSERVATION, observation.digest),
            "uncertainty": observation.uncertainty}


__all__ = ["from_measurement", "from_system_state", "read_bound"]
