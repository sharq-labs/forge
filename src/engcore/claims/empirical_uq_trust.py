"""Trust registry for empirical observations admitted to scientific UQ.

DatasetObservation is a structured record, not proof that the row exists in a
curated dataset.  Aleatoric and model-form UQ therefore require an immutable
repository pin over the exact observation record before it may contribute to a
production estimate.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from ..scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from ..scientific.units.quantity import Quantity
from .measurement_dataset import DatasetObservation, DatasetSplit

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class EmpiricalObservationPin:
    observation_digest: str
    curator: str
    rationale: str

    def __post_init__(self) -> None:
        digest = str(self.observation_digest).strip().lower()
        curator = str(self.curator).strip()
        rationale = str(self.rationale).strip()
        if not _SHA256.fullmatch(digest):
            raise ValueError("empirical observation pin digest must be lowercase SHA-256")
        if not curator or not rationale:
            raise ValueError("empirical observation pin requires curator and rationale")
        object.__setattr__(self, "observation_digest", digest)
        object.__setattr__(self, "curator", curator)
        object.__setattr__(self, "rationale", rationale)

    def to_dict(self) -> dict[str, str]:
        return {
            "observation_digest": self.observation_digest,
            "curator": self.curator,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class EmpiricalObservationRegistry:
    pins: tuple[EmpiricalObservationPin, ...] = ()

    def __post_init__(self) -> None:
        pins = tuple(sorted(self.pins, key=lambda p: p.observation_digest))
        if any(not isinstance(item, EmpiricalObservationPin) for item in pins):
            raise ValueError("empirical observation registry accepts pins only")
        digests = [item.observation_digest for item in pins]
        if len(digests) != len(set(digests)):
            raise ValueError("duplicate empirical observation digest")
        object.__setattr__(self, "pins", pins)

    def pin_for(
        self, observation: DatasetObservation | str
    ) -> EmpiricalObservationPin | None:
        digest = (
            observation.digest
            if isinstance(observation, DatasetObservation)
            else str(observation).strip().lower()
        )
        return next(
            (item for item in self.pins if item.observation_digest == digest),
            None,
        )

    @property
    def digest(self) -> str:
        payload = json.dumps(
            [item.to_dict() for item in self.pins],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_S_OCV_SOURCE_SHA256 = (
    "9b8c541675256c08c24cc6ebeb486a46"
    "d07c533a70bf4dabcca4955dba90e08a"
)
_S_OCV_DATASET_VERSION = "DOI:10.21227/651q-8v82:v1"
_S_OCV_CALIBRATION = "model_measurement_validation:S-OCV:uncertainty-budget-v1"


def _measurement_interval(
    value_v: float,
    expanded_half_width_v: float,
    *,
    cell: str,
    soc: float,
) -> Uncertainty:
    """The frozen k=2 voltage budget from model_measurement_validation."""
    return Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=Quantity(value_v - expanded_half_width_v, "volt"),
        upper=Quantity(value_v + expanded_half_width_v, "volt"),
        source=(
            f"S-OCV DOI 10.21227/651q-8v82; {cell}; "
            f"charge-conditioned SOC={soc:g}; 24 h relaxation"
        ),
        method=(
            "expanded k=2 acquisition + SOC + temperature + residual-relaxation "
            "budget frozen in benchmarks/model_measurement_validation/"
            "VALIDATION_RESULTS.json"
        ),
        notes=(
            "Published LiFePO4 measurement. The interval is the audit's frozen "
            "measurement budget; it is not model-form allowance."
        ),
        source_kind=UncertaintySource.MEASUREMENT,
    )


def _s_ocv_observation(
    *,
    cell: str,
    soc: float,
    voltage_v: float,
    expanded_half_width_v: float,
    split: DatasetSplit,
) -> DatasetObservation:
    """One repository-curated 24 h charge-conditioned S-OCV observation.

    Only SOC and cell temperature override the scientific claim. Other required
    Battery inputs remain the claim's declared context. This is intentional:
    the observed quantity is open-circuit voltage, not loaded terminal voltage,
    and the production OCV law depends on SOC rather than on the discharge
    current used by the surrounding battery march.
    """
    soc_tag = f"{soc:.1f}".rstrip("0").rstrip(".")
    return DatasetObservation(
        manifest_digest=_S_OCV_SOURCE_SHA256,
        observation_id=f"S-OCV:{cell}:charge:soc={soc_tag}:24h",
        independence_group=f"cell:{cell}",
        split=split,
        quantity="open_circuit_voltage",
        value=Quantity(voltage_v, "volt"),
        conditions={
            "load.state_of_charge": Quantity(soc, "dimensionless"),
            # Source states ambient 23 +/- 2 degC. 296.15 K is the declared
            # setpoint used to bind the observation context; its contribution
            # to the measurement budget is already carried above.
            "load.cell_temperature": Quantity(296.15, "kelvin"),
        },
        uncertainty=_measurement_interval(
            voltage_v,
            expanded_half_width_v,
            cell=cell,
            soc=soc,
        ),
        calibration_ref=_S_OCV_CALIBRATION,
        provenance_ref=(
            f"S-OCV:sha256:{_S_OCV_SOURCE_SHA256}:{cell}:"
            f"charge:soc={soc_tag}:24h"
        ),
        dataset_version=_S_OCV_DATASET_VERSION,
        observed_at="24 h open-circuit relaxation",
        missing_context=(),
    )


# Frozen production empirical catalog.  BATT_001 and BATT_002 are different
# LiFePO4 cells and therefore different independence groups.  The 100% points
# are calibration observations; 50% and 60% are held-out validation points.
# These records satisfy model-form split/group admission, but they DO NOT by
# themselves satisfy the 95/95 two-sided Wilks replicate count used by the
# ALEATORIC producer: there are only two independent cells at each exact SOC.
PRODUCTION_EMPIRICAL_RECORDS = (
    _s_ocv_observation(
        cell="BATT_001",
        soc=1.0,
        voltage_v=3.389,
        expanded_half_width_v=0.008438195067666961,
        split=DatasetSplit.CALIBRATION,
    ),
    _s_ocv_observation(
        cell="BATT_002",
        soc=1.0,
        voltage_v=3.351,
        expanded_half_width_v=0.003924735022902993,
        split=DatasetSplit.CALIBRATION,
    ),
    _s_ocv_observation(
        cell="BATT_001",
        soc=0.5,
        voltage_v=3.299,
        expanded_half_width_v=0.0008329231657241884,
        split=DatasetSplit.VALIDATION,
    ),
    _s_ocv_observation(
        cell="BATT_002",
        soc=0.5,
        voltage_v=3.302,
        expanded_half_width_v=0.0008562336129818662,
        split=DatasetSplit.VALIDATION,
    ),
    _s_ocv_observation(
        cell="BATT_001",
        soc=0.6,
        voltage_v=3.302,
        expanded_half_width_v=0.0021919708027252688,
        split=DatasetSplit.VALIDATION,
    ),
    _s_ocv_observation(
        cell="BATT_002",
        soc=0.6,
        voltage_v=3.304,
        expanded_half_width_v=0.0027847498990039776,
        split=DatasetSplit.VALIDATION,
    ),
)

PRODUCTION_EMPIRICAL_OBSERVATIONS = EmpiricalObservationRegistry(
    tuple(
        EmpiricalObservationPin(
            observation_digest=observation.digest,
            curator="forge:model_measurement_validation",
            rationale=(
                "S-OCV published experimental observation frozen from DOI "
                "10.21227/651q-8v82 with repository-pinned source bytes, "
                "explicit calibration/validation role and k=2 measurement budget"
            ),
        )
        for observation in PRODUCTION_EMPIRICAL_RECORDS
    )
)


__all__ = [
    "EmpiricalObservationPin",
    "EmpiricalObservationRegistry",
    "PRODUCTION_EMPIRICAL_RECORDS",
    "PRODUCTION_EMPIRICAL_OBSERVATIONS",
]
