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


#: Audit CAP-01. The CSTR's single-liquid-phase conditions read the fluid's own
#: boiling and freezing temperatures and are UNKNOWN until they are declared.
#: The frozen K-series parameterization (the Seborg textbook liquid) declares
#: neither, so its runs are no longer IN_DOMAIN and the inference boundary
#: refuses them on applicability -- that refusal is asserted below, and is the
#: correct behaviour. To keep exercising the admission path itself, the
#: positive tests declare a liquid range HERE: a hypothetical pressurised liquid
#: that stays liquid between 260 K and 650 K. It is this test's declaration,
#: not a property of the textbook parameterization, and it clears every K-series
#: adiabatic ceiling (at most 579.2 K) and floor (at least 285 K).
DECLARED_BOILING = Quantity(650.0, "kelvin")
DECLARED_FREEZING = Quantity(260.0, "kelvin")
PHASE_CONDITIONS = (
    "declared_temperature_to_boiling_ratio",
    "adiabatic_ceiling_to_boiling_ratio",
    "adiabatic_floor_to_freezing_ratio",
)


def declared_liquid(chemistry):
    from dataclasses import replace

    return replace(
        chemistry,
        boiling_temperature=DECLARED_BOILING,
        freezing_temperature=DECLARED_FREEZING,
    )


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
    # applicability; the same holdouts with a declared liquid range still cross.
    with pytest.raises(InferenceAdmissibilityError, match="applicability"):
        holdout_truth_means()

    liquid = declared_liquid(chemistry_from_coordinates(*TRUTH_COORDINATES))
    adapter = CSTRInferenceForwardAdapter()
    means = {}
    for condition_id in HOLDOUT_IDS:
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
        for condition_id in HOLDOUT_IDS
        for observable_name in OBSERVABLE_NAMES
    }
    for value in means.values():
        assert value.magnitude == value.magnitude  # finite Quantity boundary
