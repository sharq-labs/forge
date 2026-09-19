from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..results.uncertainty import Uncertainty, UncertaintySource
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension
from .calibration import CalibrationCertificate
from .context import ExperimentContext
from .instrument import InstrumentIdentity

MEASUREMENT_OBSERVATION_SCHEMA = schema_string("calibrated_measurement_observation")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CalibratedMeasurementObservation:
    observation_id: str
    quantity: str
    value: Quantity
    uncertainty: Uncertainty
    instrument: InstrumentIdentity
    calibration: CalibrationCertificate
    context: ExperimentContext
    raw_data_digest: str
    observed_at: str
    independence_group: str

    def __post_init__(self) -> None:
        observation_id = str(self.observation_id).strip()
        quantity = str(self.quantity).strip()
        independence_group = str(self.independence_group).strip()
        raw = str(self.raw_data_digest).strip().lower()
        if (
            not observation_id
            or not quantity
            or not independence_group
            or not _SHA256.fullmatch(raw)
        ):
            raise InvalidScientificProblem(
                "measurement observation requires identity, quantity, raw digest and independence group"
            )
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem(
                "measurement observation value must be Quantity"
            )
        if not isinstance(self.uncertainty, Uncertainty):
            raise InvalidScientificProblem(
                "measurement observation uncertainty must be Uncertainty"
            )
        if not self.uncertainty.is_quantified:
            raise InvalidScientificProblem(
                "measurement observation uncertainty must be quantified"
            )
        if (
            UncertaintySource(self.uncertainty.source_kind)
            is not UncertaintySource.MEASUREMENT
        ):
            raise InvalidScientificProblem(
                "measurement observation uncertainty must be MEASUREMENT"
            )
        if self.uncertainty.standard_uncertainty is not None:
            require_same_dimension(
                self.uncertainty.standard_uncertainty,
                self.value,
                context="measurement standard uncertainty",
            )
        if self.uncertainty.lower is not None:
            require_same_dimension(
                self.uncertainty.lower,
                self.value,
                context="measurement interval",
            )
        if not isinstance(self.instrument, InstrumentIdentity):
            raise InvalidScientificProblem(
                "measurement observation requires InstrumentIdentity"
            )
        if not isinstance(self.calibration, CalibrationCertificate):
            raise InvalidScientificProblem(
                "measurement observation requires CalibrationCertificate"
            )
        if self.calibration.instrument.digest != self.instrument.digest:
            raise InvalidScientificProblem(
                "measurement instrument differs from calibration instrument"
            )
        if self.calibration.quantity != quantity:
            raise InvalidScientificProblem(
                "measurement quantity differs from calibration quantity"
            )
        require_same_dimension(
            self.calibration.reference_value,
            self.value,
            context="measurement vs calibration quantity",
        )
        if not self.calibration.valid_at(self.observed_at):
            raise InvalidScientificProblem(
                "measurement was observed outside calibration validity interval"
            )
        if not isinstance(self.context, ExperimentContext):
            raise InvalidScientificProblem(
                "measurement observation requires ExperimentContext"
            )
        object.__setattr__(self, "observation_id", observation_id)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "raw_data_digest", raw)
        object.__setattr__(self, "observed_at", str(self.observed_at).strip())
        object.__setattr__(self, "independence_group", independence_group)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MEASUREMENT_OBSERVATION_SCHEMA,
            "observation_id": self.observation_id,
            "quantity": self.quantity,
            "value": self.value.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
            "instrument": self.instrument.to_dict(),
            "calibration": self.calibration.to_dict(),
            "context": self.context.to_dict(),
            "raw_data_digest": self.raw_data_digest,
            "observed_at": self.observed_at,
            "independence_group": self.independence_group,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "CalibratedMeasurementObservation":
        require_schema(payload, MEASUREMENT_OBSERVATION_SCHEMA)
        return cls(
            payload["observation_id"],
            payload["quantity"],
            Quantity.from_dict(payload["value"]),
            Uncertainty.from_dict(payload["uncertainty"]),
            InstrumentIdentity.from_dict(payload["instrument"]),
            CalibrationCertificate.from_dict(payload["calibration"]),
            ExperimentContext.from_dict(payload["context"]),
            payload["raw_data_digest"],
            payload["observed_at"],
            payload["independence_group"],
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
