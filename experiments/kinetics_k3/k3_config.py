"""Frozen K3 scientific configuration.

Values mirror docs/kinetics-k3-quantified-uncertainty-prereg.md.  Changing
these declarations after a scored run is a preregistration deviation.
"""

from __future__ import annotations

from experiments.kinetics_k1.k1_config import (
    FLOW_M3_PER_S,
    NOMINAL_FEED_CONCENTRATION,
    NOMINAL_UA_W_PER_K,
    VOLUME_M3,
)
from experiments.kinetics_k2.k2_config import (
    K2Condition,
    SIGMA_CONCENTRATION,
    SIGMA_TEMPERATURE,
)
from src.engcore.domains.kinetics.cstr.problem import CSTR_MODEL
from src.engcore.scientific import (
    ModelReference,
    Quantity,
    ScientificTwin,
    TwinDatum,
    TwinDatumRole,
    TwinKind,
)

PREREG_COMMIT = "c640af0f9a436b9efb5828b7e4d0caba07d67882"
K2_SCIENTIFIC_SOURCE_COMMIT = "eab5879e8c17d5c1cf8f697f0eb2e57816cc99b5"
K2_PREREG_COMMIT = "824a4167a7ebead813dc3b023b9ace31742e3789"

PRIMARY_HOLDOUT_SEED = 20260909
REPEATED_HOLDOUT_SEEDS = tuple(range(20260910, 20260930))

HOLDOUT_CONDITIONS: tuple[K2Condition, ...] = (
    K2Condition(
        condition_id="H1",
        coolant_temperature_k=307.5,
        feed_temperature_k=360.0,
        initial_temperature_k=315.0,
    ),
    K2Condition(
        condition_id="H2",
        coolant_temperature_k=292.5,
        feed_temperature_k=340.0,
        initial_temperature_k=305.0,
    ),
)
HOLDOUT_BY_ID = {item.condition_id: item for item in HOLDOUT_CONDITIONS}
HOLDOUT_IDS = tuple(item.condition_id for item in HOLDOUT_CONDITIONS)


def k3_reference_twin() -> ScientificTwin:
    """System identity used by K3 without pretending the posterior is a point.

    Known fixed reactor declarations live on the Twin.  The uncertain
    Arrhenius pair remains in the K2 posterior and is intentionally not
    collapsed into a single Twin datum.
    """

    return ScientificTwin(
        twin_id="kinetics-cstr-k3-reference",
        version="0.1",
        kind=TwinKind.REFERENCE,
        name="K3 non-isothermal CSTR reference system",
        models=(ModelReference(CSTR_MODEL.model_id, CSTR_MODEL.version),),
        declarations=(
            TwinDatum(
                "volume",
                Quantity(VOLUME_M3, "m**3"),
                TwinDatumRole.PARAMETER,
            ),
            TwinDatum(
                "flow_rate",
                Quantity(FLOW_M3_PER_S, "m**3/s"),
                TwinDatumRole.PARAMETER,
            ),
            TwinDatum(
                "feed_concentration",
                Quantity(NOMINAL_FEED_CONCENTRATION, "mol/m**3"),
                TwinDatumRole.PARAMETER,
            ),
            TwinDatum(
                "ua",
                Quantity(NOMINAL_UA_W_PER_K, "W/K"),
                TwinDatumRole.PARAMETER,
            ),
        ),
        evidence_refs=(
            f"k2-prereg:{K2_PREREG_COMMIT}",
            f"k2-scientific-source:{K2_SCIENTIFIC_SOURCE_COMMIT}",
        ),
        assumptions=(
            "Arrhenius parameters are represented by the K2 posterior rather than a point-valued Twin datum",
        ),
    )


def sigma_for_observable(observable_name: str) -> Quantity:
    from src.engcore.domains.kinetics.cstr.problem import CA_FINAL_METRIC, T_FINAL_METRIC

    if observable_name == CA_FINAL_METRIC:
        return SIGMA_CONCENTRATION
    if observable_name == T_FINAL_METRIC:
        return SIGMA_TEMPERATURE
    raise ValueError(f"K3 has no noise declaration for observable {observable_name!r}")
