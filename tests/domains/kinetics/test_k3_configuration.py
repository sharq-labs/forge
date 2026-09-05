from __future__ import annotations

from experiments.kinetics_k2.k2_config import OBSERVABLE_NAMES
from experiments.kinetics_k3.k3_config import (
    HOLDOUT_BY_ID,
    HOLDOUT_IDS,
    PRIMARY_HOLDOUT_SEED,
    REPEATED_HOLDOUT_SEEDS,
    k3_reference_twin,
)
from experiments.kinetics_k3.k3_forward import holdout_truth_means
from src.engcore.domains.kinetics.cstr.problem import CSTR_MODEL
from src.engcore.scientific import TwinKind


def test_k3_holdouts_match_frozen_preregistration() -> None:
    assert HOLDOUT_IDS == ("H1", "H2")

    h1 = HOLDOUT_BY_ID["H1"]
    assert h1.coolant_temperature_k == 307.5
    assert h1.feed_temperature_k == 360.0
    assert h1.initial_temperature_k == 315.0
    assert h1.initial_concentration_mol_per_m3 == 1000.0
    assert h1.end_time_s == 1800.0

    h2 = HOLDOUT_BY_ID["H2"]
    assert h2.coolant_temperature_k == 292.5
    assert h2.feed_temperature_k == 340.0
    assert h2.initial_temperature_k == 305.0
    assert h2.initial_concentration_mol_per_m3 == 1000.0
    assert h2.end_time_s == 1800.0

    assert PRIMARY_HOLDOUT_SEED == 20260909
    assert REPEATED_HOLDOUT_SEEDS == tuple(range(20260910, 20260930))


def test_k3_reference_twin_binds_model_without_collapsing_posterior() -> None:
    twin = k3_reference_twin()

    assert twin.kind is TwinKind.REFERENCE
    assert twin.models[0].key == (CSTR_MODEL.model_id, CSTR_MODEL.version)
    assert {datum.name for datum in twin.declarations} == {
        "volume",
        "flow_rate",
        "feed_concentration",
        "ua",
    }
    assert "k0" not in twin.scientific_context()
    assert "activation_energy" not in twin.scientific_context()
    assert any(ref.startswith("k2-prereg:") for ref in twin.evidence_refs)


def test_k3_truth_holdouts_cross_k15_admissibility_boundary() -> None:
    means = holdout_truth_means()

    assert set(means) == {
        f"{condition_id}:{observable_name}"
        for condition_id in HOLDOUT_IDS
        for observable_name in OBSERVABLE_NAMES
    }
    for value in means.values():
        assert value.magnitude == value.magnitude  # finite Quantity boundary
