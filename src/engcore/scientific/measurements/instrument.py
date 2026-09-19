from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string

INSTRUMENT_IDENTITY_SCHEMA = schema_string("measurement_instrument_identity")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class InstrumentIdentity:
    instrument_id: str
    manufacturer: str
    model: str
    serial_number: str
    firmware: str = ""
    configuration_digest: str | None = None

    def __post_init__(self) -> None:
        for name in ("instrument_id", "manufacturer", "model", "serial_number"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"measurement instrument {name} must be non-empty"
                )
            object.__setattr__(self, name, value)
        object.__setattr__(self, "firmware", str(self.firmware).strip())
        if self.configuration_digest is not None:
            digest = str(self.configuration_digest).strip().lower()
            if not _SHA256.fullmatch(digest):
                raise InvalidScientificProblem(
                    "instrument configuration_digest must be lowercase SHA-256"
                )
            object.__setattr__(self, "configuration_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": INSTRUMENT_IDENTITY_SCHEMA,
            "instrument_id": self.instrument_id,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "firmware": self.firmware,
            "configuration_digest": self.configuration_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InstrumentIdentity":
        require_schema(payload, INSTRUMENT_IDENTITY_SCHEMA)
        return cls(
            payload["instrument_id"],
            payload["manufacturer"],
            payload["model"],
            payload["serial_number"],
            payload.get("firmware", ""),
            payload.get("configuration_digest"),
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
