"""Typed execution evidence for scenario-driven transient runs.

These records are **execution evidence**, not scientific outputs.  A consumed
control input, an operating condition handed to a participant, the identity of
a participant's state either side of a coupling window, the condition that
stopped a run and the produced quantity a scenario asked for are all facts
about *what execution did*.  None of them is a computed scientific result, and
none of them may live in a run's output map, where a reader looking for a
solver's answer would find them.

Everything here is domain-independent.  A record names ids, ports, instants,
window boundaries, unit-bearing values, uncertainty and the scenario digest the
evidence is bound to.  It never names a physical quantity this core understands
the meaning of.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..ir.constraints import ConstraintCheck
from ..results.uncertainty import Uncertainty
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality, normalize_unit
from .ports import PortRef

STATE_VALUE_SCHEMA = schema_string("multiphysics_state_value")
SCENARIO_INPUT_RECEIPT_SCHEMA = schema_string("multiphysics_scenario_input_receipt")
OPERATING_CONDITION_RECEIPT_SCHEMA = schema_string(
    "multiphysics_operating_condition_receipt"
)
STATE_TRANSITION_RECEIPT_SCHEMA = schema_string(
    "multiphysics_state_transition_receipt"
)
TERMINATION_RECEIPT_SCHEMA = schema_string("multiphysics_termination_receipt")
QUANTITY_OF_INTEREST_RECORD_SCHEMA = schema_string(
    "multiphysics_quantity_of_interest_record"
)

_TIME_DIMENSION = dimensionality("second")


def require_digest(value: object, label: str) -> str:
    """A digest is a sha256 hex string or it is not a digest."""
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise InvalidScientificProblem(f"{label} must be a sha256 hex digest")
    return digest


def _optional_digest(value: object, label: str) -> str:
    text = str(value).strip().lower()
    return require_digest(text, label) if text else ""


def _identifier(value: object, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise InvalidScientificProblem(f"{label} must be non-empty")
    return text


def _instant(value: object, label: str) -> Quantity:
    if not isinstance(value, Quantity) or dimensionality(value.units) != _TIME_DIMENSION:
        raise InvalidScientificProblem(f"{label} must be a time Quantity")
    return value.to("second")


def _boundary_index(value: object, label: str) -> int:
    if isinstance(value, bool) or int(value) != value or int(value) < 0:
        raise InvalidScientificProblem(
            f"{label} must be a non-negative integer boundary index"
        )
    return int(value)


def _bounded_uncertainty(
    value: Quantity, uncertainty: Uncertainty, label: str
) -> Uncertainty:
    if not isinstance(uncertainty, Uncertainty):
        raise InvalidScientificProblem(f"{label} requires an Uncertainty record")
    for name in ("standard_uncertainty", "lower", "upper"):
        bound = getattr(uncertainty, name)
        if bound is not None:
            bound.require_compatible(value.units, context=f"{label} {name}")
    return uncertainty


@dataclass(frozen=True, order=True)
class StateVariableValue:
    """A state value a participant chose to expose publicly.

    A participant is never required to publish one.  Private solver internals
    stay private: what execution can always prove is the *identity* carried by
    :class:`StateTransitionReceipt`, and a value appears here only because the
    participant declared it as public state.
    """

    variable_id: str
    value: Quantity
    uncertainty: Uncertainty

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "variable_id", _identifier(self.variable_id, "state variable_id")
        )
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem("state value must be a Quantity")
        object.__setattr__(
            self,
            "uncertainty",
            _bounded_uncertainty(
                self.value, self.uncertainty, f"state value {self.variable_id!r}"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": STATE_VALUE_SCHEMA,
            "variable_id": self.variable_id,
            "value": self.value.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StateVariableValue":
        require_schema(payload, STATE_VALUE_SCHEMA)
        return cls(
            payload["variable_id"],
            Quantity.from_dict(payload["value"]),
            Uncertainty.from_dict(payload["uncertainty"]),
        )


@dataclass(frozen=True, order=True)
class ScenarioInputReceipt:
    """One time-varying scenario input, as execution actually consumed it.

    This is the record that keeps a consumed control input out of the output
    map.  It carries enough identity to say *which* declared input, *where* it
    was delivered, *when*, from which scenario segment and under which scenario.
    """

    input_id: str
    port: PortRef
    boundary_index: int
    instant: Quantity
    segment_id: str
    value: Quantity
    uncertainty: Uncertainty
    scenario_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_id", _identifier(self.input_id, "input_id"))
        if not isinstance(self.port, PortRef):
            raise InvalidScientificProblem("scenario input receipt requires a PortRef")
        object.__setattr__(
            self,
            "boundary_index",
            _boundary_index(self.boundary_index, "scenario input receipt boundary_index"),
        )
        object.__setattr__(
            self, "instant", _instant(self.instant, "scenario input receipt instant")
        )
        object.__setattr__(
            self, "segment_id", _identifier(self.segment_id, "scenario segment_id")
        )
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem(
                "scenario input receipt value must be a Quantity"
            )
        object.__setattr__(
            self,
            "uncertainty",
            _bounded_uncertainty(
                self.value, self.uncertainty, f"scenario input {self.input_id!r}"
            ),
        )
        object.__setattr__(
            self,
            "scenario_digest",
            require_digest(
                self.scenario_digest, "scenario input receipt scenario_digest"
            ),
        )

    @property
    def key(self) -> tuple[int, str, str]:
        return self.boundary_index, self.input_id, self.port.key

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCENARIO_INPUT_RECEIPT_SCHEMA,
            "classification": "consumed_scenario_input",
            "input_id": self.input_id,
            "port": self.port.to_dict(),
            "boundary_index": self.boundary_index,
            "instant": self.instant.to_dict(),
            "segment_id": self.segment_id,
            "value": self.value.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
            "scenario_digest": self.scenario_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScenarioInputReceipt":
        require_schema(payload, SCENARIO_INPUT_RECEIPT_SCHEMA)
        if payload.get("classification") != "consumed_scenario_input":
            raise InvalidScientificProblem(
                "scenario input receipt classification mismatch"
            )
        return cls(
            payload["input_id"],
            PortRef.from_dict(payload["port"]),
            payload["boundary_index"],
            Quantity.from_dict(payload["instant"]),
            payload["segment_id"],
            Quantity.from_dict(payload["value"]),
            Uncertainty.from_dict(payload["uncertainty"]),
            payload["scenario_digest"],
        )


@dataclass(frozen=True, order=True)
class OperatingConditionReceipt:
    """One declared operating condition, acknowledged by the participant that consumed it.

    Core transports the condition; it never interprets it.  The record proves
    an authorized consumer received the exact declared value and uncertainty.
    """

    condition_id: str
    participant_id: str
    boundary_index: int
    instant: Quantity
    segment_id: str
    value: Quantity
    uncertainty: Uncertainty
    scenario_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "condition_id", _identifier(self.condition_id, "condition_id")
        )
        object.__setattr__(
            self, "participant_id", _identifier(self.participant_id, "participant_id")
        )
        object.__setattr__(
            self,
            "boundary_index",
            _boundary_index(
                self.boundary_index, "operating condition receipt boundary_index"
            ),
        )
        object.__setattr__(
            self,
            "instant",
            _instant(self.instant, "operating condition receipt instant"),
        )
        object.__setattr__(
            self, "segment_id", _identifier(self.segment_id, "scenario segment_id")
        )
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem(
                "operating condition receipt value must be a Quantity"
            )
        object.__setattr__(
            self,
            "uncertainty",
            _bounded_uncertainty(
                self.value,
                self.uncertainty,
                f"operating condition {self.condition_id!r}",
            ),
        )
        object.__setattr__(
            self,
            "scenario_digest",
            require_digest(
                self.scenario_digest, "operating condition receipt scenario_digest"
            ),
        )

    @property
    def key(self) -> tuple[int, str, str]:
        return self.boundary_index, self.participant_id, self.condition_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": OPERATING_CONDITION_RECEIPT_SCHEMA,
            "classification": "consumed_operating_condition",
            "condition_id": self.condition_id,
            "participant_id": self.participant_id,
            "boundary_index": self.boundary_index,
            "instant": self.instant.to_dict(),
            "segment_id": self.segment_id,
            "value": self.value.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
            "scenario_digest": self.scenario_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OperatingConditionReceipt":
        require_schema(payload, OPERATING_CONDITION_RECEIPT_SCHEMA)
        if payload.get("classification") != "consumed_operating_condition":
            raise InvalidScientificProblem(
                "operating condition receipt classification mismatch"
            )
        return cls(
            payload["condition_id"],
            payload["participant_id"],
            payload["boundary_index"],
            Quantity.from_dict(payload["instant"]),
            payload["segment_id"],
            Quantity.from_dict(payload["value"]),
            Uncertainty.from_dict(payload["uncertainty"]),
            payload["scenario_digest"],
        )


@dataclass(frozen=True, order=True)
class StateTransitionReceipt:
    """The identity of one participant's state either side of a coupling window.

    This is what lets a run prove ``A -> B -> C`` without either pretending
    state never changed or inventing values for it.  ``start_state_digest`` and
    ``end_state_digest`` are the participant's own declared state identities.
    ``end_values`` is populated only by participants that declare public state;
    an empty tuple is a participant that keeps its internals private, never a
    claim that the state was empty.
    """

    participant_id: str
    window_index: int
    start: Quantity
    end: Quantity
    start_state_digest: str
    end_state_digest: str
    end_values: tuple[StateVariableValue, ...] = ()
    scenario_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "participant_id", _identifier(self.participant_id, "participant_id")
        )
        object.__setattr__(
            self,
            "window_index",
            _boundary_index(
                self.window_index, "state transition receipt window_index"
            ),
        )
        start = _instant(self.start, "state transition start")
        end = _instant(self.end, "state transition end")
        if end.magnitude_in("second") <= start.magnitude_in("second"):
            raise InvalidScientificProblem(
                "state transition end must be after its start"
            )
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(
            self,
            "start_state_digest",
            require_digest(self.start_state_digest, "start_state_digest"),
        )
        object.__setattr__(
            self,
            "end_state_digest",
            require_digest(self.end_state_digest, "end_state_digest"),
        )
        values = tuple(self.end_values)
        if any(not isinstance(item, StateVariableValue) for item in values):
            raise InvalidScientificProblem(
                "state transition end_values must be StateVariableValue records"
            )
        if len({item.variable_id for item in values}) != len(values):
            raise InvalidScientificProblem(
                "state transition end_values contain duplicate variables"
            )
        object.__setattr__(self, "end_values", tuple(sorted(values)))
        object.__setattr__(
            self,
            "scenario_digest",
            _optional_digest(
                self.scenario_digest, "state transition receipt scenario_digest"
            ),
        )

    @property
    def key(self) -> tuple[int, str]:
        return self.window_index, self.participant_id

    @property
    def state_changed(self) -> bool:
        """Whether the participant's own state identity moved across the window."""
        return self.start_state_digest != self.end_state_digest

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": STATE_TRANSITION_RECEIPT_SCHEMA,
            "classification": "participant_state_transition",
            "participant_id": self.participant_id,
            "window_index": self.window_index,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "start_state_digest": self.start_state_digest,
            "end_state_digest": self.end_state_digest,
            "end_values": [item.to_dict() for item in self.end_values],
            "scenario_digest": self.scenario_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StateTransitionReceipt":
        require_schema(payload, STATE_TRANSITION_RECEIPT_SCHEMA)
        if payload.get("classification") != "participant_state_transition":
            raise InvalidScientificProblem(
                "state transition receipt classification mismatch"
            )
        return cls(
            payload["participant_id"],
            payload["window_index"],
            Quantity.from_dict(payload["start"]),
            Quantity.from_dict(payload["end"]),
            payload["start_state_digest"],
            payload["end_state_digest"],
            tuple(
                StateVariableValue.from_dict(item)
                for item in payload.get("end_values", ())
            ),
            payload.get("scenario_digest", ""),
        )


@dataclass(frozen=True)
class TerminationReceipt:
    """Why a run stopped before its planned horizon, and on which numbers.

    A run that ends early without one of these is refused: an early end with no
    stated cause is silent clipping.  The :class:`ConstraintCheck` carries the
    measured value and margin the decision was made from, so the stop is
    re-derivable rather than asserted.
    """

    condition_id: str
    boundary_index: int
    instant: Quantity
    check: ConstraintCheck
    reason: str
    scenario_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "condition_id", _identifier(self.condition_id, "condition_id")
        )
        object.__setattr__(
            self,
            "boundary_index",
            _boundary_index(self.boundary_index, "termination receipt boundary_index"),
        )
        object.__setattr__(
            self, "instant", _instant(self.instant, "termination receipt instant")
        )
        if not isinstance(self.check, ConstraintCheck):
            raise InvalidScientificProblem(
                "termination receipt requires the ConstraintCheck it stopped on"
            )
        if not self.check.satisfied:
            raise InvalidScientificProblem(
                "a termination receipt records a condition that was met; an "
                "unsatisfied check did not stop anything"
            )
        if self.check.constraint != self.condition_id:
            raise InvalidScientificProblem(
                "termination receipt check names a different condition"
            )
        object.__setattr__(
            self, "reason", _identifier(self.reason, "termination receipt reason")
        )
        object.__setattr__(
            self,
            "scenario_digest",
            require_digest(
                self.scenario_digest, "termination receipt scenario_digest"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TERMINATION_RECEIPT_SCHEMA,
            "classification": "scenario_termination",
            "condition_id": self.condition_id,
            "boundary_index": self.boundary_index,
            "instant": self.instant.to_dict(),
            "check": self.check.to_dict(),
            "reason": self.reason,
            "scenario_digest": self.scenario_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TerminationReceipt":
        require_schema(payload, TERMINATION_RECEIPT_SCHEMA)
        if payload.get("classification") != "scenario_termination":
            raise InvalidScientificProblem("termination receipt classification mismatch")
        return cls(
            payload["condition_id"],
            payload["boundary_index"],
            Quantity.from_dict(payload["instant"]),
            ConstraintCheck.from_dict(payload["check"]),
            payload["reason"],
            payload["scenario_digest"],
        )


@dataclass(frozen=True, order=True)
class QuantityOfInterestRecord:
    """A requested quantity of interest, bound to the output that produced it.

    Core computes nothing here.  The record says which authorized participant
    output answered the request, with what value and uncertainty, and when.  A
    requested quantity with no producing output is a refusal, never an absent
    record.
    """

    qoi_id: str
    quantity_id: str
    port: PortRef
    instant: Quantity
    value: Quantity
    uncertainty: Uncertainty
    scenario_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "qoi_id", _identifier(self.qoi_id, "qoi_id"))
        object.__setattr__(
            self, "quantity_id", _identifier(self.quantity_id, "qoi quantity_id")
        )
        if not isinstance(self.port, PortRef):
            raise InvalidScientificProblem(
                "quantity of interest record requires a producing PortRef"
            )
        object.__setattr__(
            self, "instant", _instant(self.instant, "quantity of interest instant")
        )
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem(
                "quantity of interest value must be a scalar Quantity"
            )
        object.__setattr__(
            self,
            "uncertainty",
            _bounded_uncertainty(
                self.value, self.uncertainty, f"quantity of interest {self.qoi_id!r}"
            ),
        )
        object.__setattr__(
            self,
            "scenario_digest",
            require_digest(
                self.scenario_digest, "quantity of interest scenario_digest"
            ),
        )

    def require_unit(self, unit: str) -> None:
        self.value.require_compatible(
            normalize_unit(unit),
            context=f"quantity of interest {self.qoi_id!r}",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": QUANTITY_OF_INTEREST_RECORD_SCHEMA,
            "classification": "requested_quantity_of_interest",
            "qoi_id": self.qoi_id,
            "quantity_id": self.quantity_id,
            "port": self.port.to_dict(),
            "instant": self.instant.to_dict(),
            "value": self.value.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
            "scenario_digest": self.scenario_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QuantityOfInterestRecord":
        require_schema(payload, QUANTITY_OF_INTEREST_RECORD_SCHEMA)
        if payload.get("classification") != "requested_quantity_of_interest":
            raise InvalidScientificProblem(
                "quantity of interest record classification mismatch"
            )
        return cls(
            payload["qoi_id"],
            payload["quantity_id"],
            PortRef.from_dict(payload["port"]),
            Quantity.from_dict(payload["instant"]),
            Quantity.from_dict(payload["value"]),
            Uncertainty.from_dict(payload["uncertainty"]),
            payload["scenario_digest"],
        )


__all__ = [
    "OPERATING_CONDITION_RECEIPT_SCHEMA",
    "QUANTITY_OF_INTEREST_RECORD_SCHEMA",
    "SCENARIO_INPUT_RECEIPT_SCHEMA",
    "STATE_TRANSITION_RECEIPT_SCHEMA",
    "STATE_VALUE_SCHEMA",
    "TERMINATION_RECEIPT_SCHEMA",
    "OperatingConditionReceipt",
    "QuantityOfInterestRecord",
    "ScenarioInputReceipt",
    "StateTransitionReceipt",
    "StateVariableValue",
    "TerminationReceipt",
    "require_digest",
]
