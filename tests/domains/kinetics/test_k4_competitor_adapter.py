from __future__ import annotations

import pytest

from src.engcore.domains.kinetics.cstr.alternative_inference import (
    CONSTANT_RATE_INFERENCE_ADAPTER_ID,
    derive_constant_rate_source_result,
)
from src.engcore.domains.kinetics.cstr.alternatives import CONSTANT_RATE_CSTR_MODEL
from src.engcore.domains.kinetics.cstr.problem import CSTR_MODEL
from src.engcore.scientific import (
    ConvergenceState,
    ProvenanceRecord,
    Quantity,
    ScientificResult,
    Uncertainty,
    unverified_report,
)
from src.engcore.inference import InferenceAdmissibilityError


PRIMARY_KEY = (CSTR_MODEL.model_id, CSTR_MODEL.version)
CONSTANT_KEY = (
    CONSTANT_RATE_CSTR_MODEL.model_id,
    CONSTANT_RATE_CSTR_MODEL.version,
)


def _source(*, activation_energy_j_per_mol: float = 0.0) -> ScientificResult:
    provenance = ProvenanceRecord(
        run_id="kernel-source",
        software_version="kernel",
        git_commit="abc",
        models=(PRIMARY_KEY,),
        solvers=(("solver", "1"),),
        inputs={
            "k0": Quantity(0.01, "1/s"),
            "activation_energy": Quantity(activation_energy_j_per_mol, "J/mol"),
            "heat_of_reaction": Quantity(-5.0e4, "J/mol"),
            "molar_gas_constant": Quantity(8.314462618, "J/(mol*K)"),
        },
        assumptions=("primary",),
    )
    return ScientificResult(
        result_id="kernel-source",
        problem_id="p",
        values={
            "C_A:final": Quantity(123.0, "mol/m**3"),
            "T:final": Quantity(345.0, "kelvin"),
        },
        provenance=provenance,
        models=(PRIMARY_KEY,),
        convergence=ConvergenceState.CONVERGED,
        validation=unverified_report("test source"),
        uncertainty={
            "C_A:final": Uncertainty.unknown(),
            "T:final": Uncertainty.unknown(),
        },
        assumptions=("primary",),
    )


def test_constant_rate_derivation_changes_only_scientific_model_binding() -> None:
    source = _source()
    derived = derive_constant_rate_source_result(source)

    assert derived.values == source.values
    assert derived.convergence == source.convergence
    assert derived.validation == source.validation
    assert derived.uncertainty == source.uncertainty

    assert derived.models == (CONSTANT_KEY,)
    assert derived.provenance.models == (CONSTANT_KEY,)
    assert PRIMARY_KEY not in derived.models
    assert PRIMARY_KEY not in derived.provenance.models

    assert "k_const" in derived.provenance.inputs
    assert derived.provenance.inputs["k_const"] == Quantity(0.01, "1/s")
    assert "k0" not in derived.provenance.inputs
    assert "activation_energy" not in derived.provenance.inputs
    assert "molar_gas_constant" not in derived.provenance.inputs
    assert derived.provenance.parent_run_id == source.result_id
    assert derived.provenance.software_version == CONSTANT_RATE_INFERENCE_ADAPTER_ID
    assert derived.metadata["scientific_model_id"] == CONSTANT_RATE_CSTR_MODEL.model_id


def test_constant_rate_derivation_refuses_nonzero_activation_energy() -> None:
    with pytest.raises(
        InferenceAdmissibilityError,
        match="activation energy is non-zero",
    ):
        derive_constant_rate_source_result(_source(activation_energy_j_per_mol=1.0))
