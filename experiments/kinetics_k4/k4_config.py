"""Frozen K4 scientific configuration.

Values mirror docs/kinetics-k4-model-adequacy-competition-prereg.md.
Changing them after a scored run is a preregistration deviation.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from experiments.kinetics_k1.k1_config import CHEMISTRY
from experiments.kinetics_k3.k3_config import k3_reference_twin
from src.engcore.domains.kinetics.cstr.alternatives import CONSTANT_RATE_CSTR_MODEL
from src.engcore.domains.kinetics.cstr.problem import CSTR_MODEL
from src.engcore.scientific import ModelReference, Quantity, ScientificTwin, TwinKind

PREREG_COMMIT = "3e685454d44d81e3fa446f41bcc26160eb11c372"
K31_FROZEN_COMMIT = "f5a932c03a35cb45e661d03d725ea96aecb2f974"
K31_PREREG_COMMIT = "bfb2439fdea769779ea0aaec747353708146add6"
K3_CACHE_PRODUCER_COMMIT = "68fcc6a6a9ea305016119a86238aa9329ef33b9c"

ARRHENIUS_MODEL_REF = ModelReference(CSTR_MODEL.model_id, CSTR_MODEL.version)
CONSTANT_RATE_MODEL_REF = ModelReference(
    CONSTANT_RATE_CSTR_MODEL.model_id,
    CONSTANT_RATE_CSTR_MODEL.version,
)

LOG_K_CONST_BOUNDS = (math.log(1.0e-5), math.log(1.0))
CONSTANT_RATE_GRID_SIZE = 121
MAX_UNSUPPORTED_POSTERIOR_MASS = 1.0e-12
CREDIBLE_MASS = 0.95


def constant_rate_grid(size: int = CONSTANT_RATE_GRID_SIZE) -> np.ndarray:
    size = int(size)
    if size < 2:
        raise ValueError("K4 constant-rate grid requires at least two points")
    values = np.linspace(
        LOG_K_CONST_BOUNDS[0], LOG_K_CONST_BOUNDS[1], size, dtype=np.float64
    )
    result = values[:, None]
    result.setflags(write=False)
    return result


def chemistry_from_log_k_const(log_k_const: float):
    value = float(log_k_const)
    if not LOG_K_CONST_BOUNDS[0] <= value <= LOG_K_CONST_BOUNDS[1]:
        raise ValueError("log_k_const outside frozen K4 prior bounds")
    return replace(
        CHEMISTRY,
        k0=Quantity(math.exp(value), "1/s"),
        activation_energy=Quantity(0.0, "J/mol"),
    )


def k4_ensemble_twin() -> ScientificTwin:
    """Same declared reactor system represented by two competing models."""
    base = k3_reference_twin()
    return ScientificTwin(
        twin_id="kinetics-cstr-k4-ensemble",
        version="0.1",
        kind=TwinKind.ENSEMBLE,
        name="K4 CSTR competing scientific representations",
        description=(
            "One declared reactor system with Arrhenius and constant-rate "
            "first-order model representations for held-out comparison."
        ),
        models=(ARRHENIUS_MODEL_REF, CONSTANT_RATE_MODEL_REF),
        declarations=base.declarations,
        assumptions=base.assumptions + (
            "ensemble membership records competing models and does not imply model averaging",
        ),
        evidence_refs=base.evidence_refs + (
            f"k31-frozen:{K31_FROZEN_COMMIT}",
            f"k4-prereg:{PREREG_COMMIT}",
        ),
    )
