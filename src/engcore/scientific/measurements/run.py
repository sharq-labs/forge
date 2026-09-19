from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .context import ExperimentContext
from .observation import CalibratedMeasurementObservation

EXPERIMENTAL_RUN_SCHEMA = schema_string("calibrated_experimental_run")


@dataclass(frozen=True)
class CalibratedExperimentalRun:
    run_id: str
    context: ExperimentContext
    observations: tuple[CalibratedMeasurementObservation, ...]
    facility: str
    operator_id: str = ""

    def __post_init__(self) -> None:
        run_id = str(self.run_id).strip()
        facility = str(self.facility).strip()
        if not run_id or not facility:
            raise InvalidScientificProblem(
                "experimental run requires run_id and facility"
            )
        if not isinstance(self.context, ExperimentContext):
            raise InvalidScientificProblem(
                "experimental run requires ExperimentContext"
            )
        observations = tuple(self.observations)
        if not observations or any(
            not isinstance(obs, CalibratedMeasurementObservation)
            for obs in observations
        ):
            raise InvalidScientificProblem(
                "experimental run requires calibrated measurement observations"
            )
        ids = [obs.observation_id for obs in observations]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem(
                "experimental run contains duplicate observation ids"
            )
        for observation in observations:
            if observation.context.digest != self.context.digest:
                raise InvalidScientificProblem(
                    "experimental observation context differs from run context"
                )
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "facility", facility)
        object.__setattr__(self, "operator_id", str(self.operator_id).strip())
        object.__setattr__(self, "observations", observations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXPERIMENTAL_RUN_SCHEMA,
            "run_id": self.run_id,
            "context": self.context.to_dict(),
            "observations": [
                observation.to_dict()
                for observation in self.observations
            ],
            "facility": self.facility,
            "operator_id": self.operator_id,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "CalibratedExperimentalRun":
        require_schema(payload, EXPERIMENTAL_RUN_SCHEMA)
        return cls(
            payload["run_id"],
            ExperimentContext.from_dict(payload["context"]),
            tuple(
                CalibratedMeasurementObservation.from_dict(item)
                for item in payload.get("observations", ())
            ),
            payload["facility"],
            payload.get("operator_id", ""),
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
