from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..scientific.errors import InvalidScientificProblem
from ..scientific.measurements import (
    CalibratedExperimentalRun,
    CalibratedMeasurementObservation,
)
from .evidence_graph import EvidenceAuthority, EvidenceNode


class MeasurementEvidenceStanding(str, Enum):
    ADMISSIBLE = "admissible"
    CONTEXT_MISMATCH = "context_mismatch"
    TRACEABILITY_INCOMPLETE = "traceability_incomplete"


@dataclass(frozen=True)
class MeasurementEvidenceAdmission:
    observation_id: str
    standing: MeasurementEvidenceStanding
    reasons: tuple[str, ...]

    @property
    def admissible(self) -> bool:
        return self.standing is MeasurementEvidenceStanding.ADMISSIBLE


def assess_measurement_observation(
    observation: CalibratedMeasurementObservation,
    *,
    target_context_digest: str,
) -> MeasurementEvidenceAdmission:
    context = str(target_context_digest).strip().lower()
    if context != observation.context.digest:
        return MeasurementEvidenceAdmission(
            observation.observation_id,
            MeasurementEvidenceStanding.CONTEXT_MISMATCH,
            ("measurement context differs from target scientific context",),
        )
    # The typed observation constructor has already required a valid
    # calibration interval and a traceability chain reaching a reference
    # standard.  Admission never invents trust beyond those recorded facts.
    return MeasurementEvidenceAdmission(
        observation.observation_id,
        MeasurementEvidenceStanding.ADMISSIBLE,
        (),
    )


def measurement_evidence_node(
    observation: CalibratedMeasurementObservation,
    admission: MeasurementEvidenceAdmission,
) -> EvidenceNode:
    if not admission.admissible:
        raise InvalidScientificProblem(
            "only an admissible calibrated measurement may become evidence"
        )
    # EvidenceNode V1 is intentional here. Knowledge provenance is source-pin
    # provenance; calibrated measurement provenance is represented by the
    # observation object itself and its calibration/traceability chain rather
    # than being mislabelled as a literature/source pin.
    return EvidenceNode(
        f"measurement:{observation.observation_id}",
        EvidenceAuthority.MEASUREMENT,
        observation.digest,
        f"instrument:{observation.instrument.instrument_id}",
        observation.observed_at,
        observation.context.digest,
    )


def experimental_run_evidence(
    run: CalibratedExperimentalRun,
    *,
    target_context_digest: str,
) -> tuple[EvidenceNode, ...]:
    nodes = []
    for observation in run.observations:
        admission = assess_measurement_observation(
            observation,
            target_context_digest=target_context_digest,
        )
        if not admission.admissible:
            raise InvalidScientificProblem(
                f"experimental run observation {observation.observation_id!r} "
                "is not admissible for the target context"
            )
        nodes.append(measurement_evidence_node(observation, admission))
    return tuple(nodes)
