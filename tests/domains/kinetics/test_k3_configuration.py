from __future__ import annotations

import pytest

from experiments.kinetics_k2.k2_config import (
    OBSERVABLE_NAMES,
    TRUTH_COORDINATES,
    chemistry_from_coordinates,
)
from experiments.kinetics_k3.k3_config import (
    HOLDOUT_BY_ID,
    HOLDOUT_IDS,
    PRIMARY_HOLDOUT_SEED,
    REPEATED_HOLDOUT_SEEDS,
    k3_reference_twin,
)
from experiments.kinetics_k3.k3_forward import holdout_truth_means
from engcore.domains.kinetics.cstr.inference import CSTRInferenceForwardAdapter
from engcore.domains.kinetics.cstr.problem import CSTR_MODEL
from engcore.inference import InferenceAdmissibilityError
from engcore.scientific import TwinKind
from engcore.scientific.units.quantity import Quantity
from engcore.domains.kinetics.cstr.fluids import SEBORG_TEXTBOOK_LIQUID, declare_fluid


#: Audit CAP-01, lead decision. The CSTR's single-liquid-phase conditions read
#: the fluid's own boiling and freezing temperatures and are UNKNOWN until they
#: are declared, so the frozen K-series code -- which declares none -- is
#: refused on applicability. The textbook liquid's real range is declared once,
#: in the domain (``engcore.domains.kinetics.cstr.fluids.SEBORG_TEXTBOOK_LIQUID``:
#: a dilute aqueous liquid at an assumed 101.325 kPa, 273.15-373.124 K), and a
#: solved run is assessed at the temperatures it actually reached. Runs that
#: stay liquid are admitted; runs that truly boil stay refused.
PHASE_CONDITIONS = (
    "declared_temperature_to_boiling_ratio",
    "reachable_maximum_to_boiling_ratio",
    "reachable_minimum_to_freezing_ratio",
)


def declared_liquid(chemistry):
    return declare_fluid(chemistry, SEBORG_TEXTBOOK_LIQUID)


def with_declared_liquid(run):
    from dataclasses import replace

    return replace(run, chemistry=declared_liquid(run.chemistry))


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
    # Audit CAP-01: the frozen truth declares no liquid range and is refused on
    # applicability. With the textbook liquid's real range declared, H1 truly
    # boils (truth peak 507 K against 373.124 K) and stays refused, so K3 as
    # preregistered cannot be re-derived (experiments/kinetics_k3/
    # SUPERSEDED_CAP01.md); H2 stays liquid and still crosses.
    with pytest.raises(InferenceAdmissibilityError, match="applicability"):
        holdout_truth_means()

    liquid = declared_liquid(chemistry_from_coordinates(*TRUTH_COORDINATES))
    adapter = CSTRInferenceForwardAdapter()
    with pytest.raises(InferenceAdmissibilityError, match="applicability"):
        adapter.evaluate(
            HOLDOUT_BY_ID["H1"].build(liquid),
            observable_names=OBSERVABLE_NAMES,
            run_id_prefix="k3-truth-H1",
        )
    liquid_ids = ("H2",)
    means = {}
    for condition_id in liquid_ids:
        prediction = adapter.evaluate(
            HOLDOUT_BY_ID[condition_id].build(liquid),
            observable_names=OBSERVABLE_NAMES,
            run_id_prefix=f"k3-truth-{condition_id}",
        )
        for observable_name in OBSERVABLE_NAMES:
            means[f"{condition_id}:{observable_name}"] = prediction.value(
                observable_name
            )

    assert set(means) == {
        f"{condition_id}:{observable_name}"
        for condition_id in liquid_ids
        for observable_name in OBSERVABLE_NAMES
    }
    for value in means.values():
        assert value.magnitude == value.magnitude  # finite Quantity boundary
