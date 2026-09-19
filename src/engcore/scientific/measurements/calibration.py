from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..results.uncertainty import Uncertainty, UncertaintySource
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension
from .instrument import InstrumentIdentity
from .traceability import MeasurementTraceabilityChain

CALIBRATION_CERTIFICATE_SCHEMA = schema_string("measurement_calibration_certificate")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidScientificProblem(
            f"{label} must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None:
        raise InvalidScientificProblem(
            f"{label} must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class CalibrationCertificate:
    certificate_id: str
    instrument: InstrumentIdentity
    issuer: str
    certificate_digest: str
    quantity: str
    reference_value: Quantity
    calibration_uncertainty: Uncertainty
    calibrated_at: str
    valid_until: str
    traceability: MeasurementTraceabilityChain

    def __post_init__(self) -> None:
        certificate_id = str(self.certificate_id).strip()
        issuer = str(self.issuer).strip()
        quantity = str(self.quantity).strip()
        digest = str(self.certificate_digest).strip().lower()
        if (
            not certificate_id
            or not issuer
            or not quantity
            or not _SHA256.fullmatch(digest)
        ):
            raise InvalidScientificProblem(
                "calibration certificate requires identity, issuer, quantity and digest"
            )
        if not isinstance(self.instrument, InstrumentIdentity):
            raise InvalidScientificProblem(
                "calibration certificate requires InstrumentIdentity"
            )
        if not isinstance(self.reference_value, Quantity):
            raise InvalidScientificProblem(
                "calibration reference_value must be Quantity"
            )
        if not isinstance(self.calibration_uncertainty, Uncertainty):
            raise InvalidScientificProblem(
                "calibration uncertainty must be Uncertainty"
            )
        if not self.calibration_uncertainty.is_quantified:
            raise InvalidScientificProblem(
                "calibration uncertainty must be quantified"
            )
        if (
            UncertaintySource(self.calibration_uncertainty.source_kind)
            is not UncertaintySource.MEASUREMENT
        ):
            raise InvalidScientificProblem(
                "calibration uncertainty must be attributed to MEASUREMENT"
            )
        if self.calibration_uncertainty.standard_uncertainty is not None:
            require_same_dimension(
                self.calibration_uncertainty.standard_uncertainty,
                self.reference_value,
                context="calibration standard uncertainty",
            )
        if self.calibration_uncertainty.lower is not None:
            require_same_dimension(
                self.calibration_uncertainty.lower,
                self.reference_value,
                context="calibration interval",
            )
            require_same_dimension(
                self.calibration_uncertainty.upper,
                self.reference_value,
                context="calibration interval",
            )
        calibrated = _time(self.calibrated_at, "calibrated_at")
        valid_until = _time(self.valid_until, "valid_until")
        if valid_until <= calibrated:
            raise InvalidScientificProblem(
                "calibration valid_until must be after calibrated_at"
            )
        if not isinstance(self.traceability, MeasurementTraceabilityChain):
            raise InvalidScientificProblem(
                "calibration certificate requires measurement traceability chain"
            )
        object.__setattr__(self, "certificate_id", certificate_id)
        object.__setattr__(self, "issuer", issuer)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "certificate_digest", digest)

    def valid_at(self, observed_at: str) -> bool:
        instant = _time(observed_at, "measurement observed_at")
        return (
            _time(self.calibrated_at, "calibrated_at")
            <= instant
            <= _time(self.valid_until, "valid_until")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CALIBRATION_CERTIFICATE_SCHEMA,
            "certificate_id": self.certificate_id,
            "instrument": self.instrument.to_dict(),
            "issuer": self.issuer,
            "certificate_digest": self.certificate_digest,
            "quantity": self.quantity,
            "reference_value": self.reference_value.to_dict(),
            "calibration_uncertainty": self.calibration_uncertainty.to_dict(),
            "calibrated_at": self.calibrated_at,
            "valid_until": self.valid_until,
            "traceability": self.traceability.to_dict(),
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "CalibrationCertificate":
        require_schema(payload, CALIBRATION_CERTIFICATE_SCHEMA)
        return cls(
            payload["certificate_id"],
            InstrumentIdentity.from_dict(payload["instrument"]),
            payload["issuer"],
            payload["certificate_digest"],
            payload["quantity"],
            Quantity.from_dict(payload["reference_value"]),
            Uncertainty.from_dict(payload["calibration_uncertainty"]),
            payload["calibrated_at"],
            payload["valid_until"],
            MeasurementTraceabilityChain.from_dict(payload["traceability"]),
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
