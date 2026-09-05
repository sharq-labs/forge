"""Frozen K2 scientific configuration.

All scored declarations mirror docs/kinetics-k2-multiparameter-inference-prereg.md.
Changing values here after a scored run would be a preregistration deviation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from experiments.kinetics_k1.k1_config import (
    CHEMISTRY,
    FLOW_M3_PER_S,
    NOMINAL_FEED_CONCENTRATION,
    NOMINAL_UA_W_PER_K,
    PRODUCTION_ATOL_CONCENTRATION,
    PRODUCTION_ATOL_TEMPERATURE,
    PRODUCTION_METHOD,
    PRODUCTION_RTOL,
    STANDARD_RHS_BUDGET,
    VOLUME_M3,
)
from src.engcore.domains.kinetics.cstr import (
    IntegrationSettings,
    ReactorChemistry,
    ReactorOperation,
    ReactorRun,
)
from src.engcore.domains.kinetics.cstr.problem import (
    CA_FINAL_METRIC,
    GAS_CONSTANT_UNIT,
    MOLAR_GAS_CONSTANT,
    T_FINAL_METRIC,
)
from src.engcore.scientific.units.quantity import Quantity

from . import EXPERIMENT_ID

PARAMETER_NAMES = ("log_k0", "e_over_r_k")

TRUTH_LOG_K0 = math.log(CHEMISTRY.k0_per_s)
TRUTH_E_OVER_R_K = CHEMISTRY.e_over_r_k
TRUTH_COORDINATES = (TRUTH_LOG_K0, TRUTH_E_OVER_R_K)

LOG_K0_BOUNDS = (math.log(1.0e8), math.log(1.0e10))
E_OVER_R_BOUNDS_K = (7500.0, 10000.0)
REFERENCE_GRID_SIZE = 61

PRIMARY_SEED = 20260809
RECOVERY_SEEDS = tuple(range(20260810, 20260830))
SIGMA_CONCENTRATION = Quantity(2.0, "mol/m**3")
SIGMA_TEMPERATURE = Quantity(0.20, "kelvin")

OBSERVABLE_NAMES = (CA_FINAL_METRIC, T_FINAL_METRIC)


@dataclass(frozen=True)
class K2Condition:
    condition_id: str
    coolant_temperature_k: float
    feed_temperature_k: float
    initial_temperature_k: float
    initial_concentration_mol_per_m3: float = 1000.0
    end_time_s: float = 1800.0

    def build(self, chemistry: ReactorChemistry = CHEMISTRY) -> ReactorRun:
        operation = ReactorOperation(
            volume=Quantity(VOLUME_M3, "m**3"),
            flow_rate=Quantity(FLOW_M3_PER_S, "m**3/s"),
            feed_concentration=Quantity(NOMINAL_FEED_CONCENTRATION, "mol/m**3"),
            feed_temperature=Quantity(self.feed_temperature_k, "kelvin"),
            coolant_temperature=Quantity(self.coolant_temperature_k, "kelvin"),
            ua=Quantity(NOMINAL_UA_W_PER_K, "W/K"),
            end_time=Quantity(self.end_time_s, "second"),
        )
        integration = IntegrationSettings(
            method=PRODUCTION_METHOD,
            rtol=PRODUCTION_RTOL,
            atol_concentration=PRODUCTION_ATOL_CONCENTRATION,
            atol_temperature=PRODUCTION_ATOL_TEMPERATURE,
            max_rhs_evaluations=STANDARD_RHS_BUDGET,
            n_output_points=2001,
        )
        return ReactorRun(
            run_label=f"{EXPERIMENT_ID}-{self.condition_id}",
            chemistry=chemistry,
            operation=operation,
            initial_concentration=Quantity(
                self.initial_concentration_mol_per_m3, "mol/m**3"
            ),
            initial_temperature=Quantity(self.initial_temperature_k, "kelvin"),
            integration=integration,
        )


CONDITIONS: tuple[K2Condition, ...] = (
    K2Condition(
        condition_id="C1",
        coolant_temperature_k=285.0,
        feed_temperature_k=330.0,
        initial_temperature_k=300.0,
    ),
    K2Condition(
        condition_id="C2",
        coolant_temperature_k=300.0,
        feed_temperature_k=350.0,
        initial_temperature_k=310.0,
    ),
    K2Condition(
        condition_id="C3",
        coolant_temperature_k=315.0,
        feed_temperature_k=370.0,
        initial_temperature_k=320.0,
    ),
)

CONDITION_BY_ID = {item.condition_id: item for item in CONDITIONS}
WEAK_CONDITION_IDS = ("C2",)
MULTI_CONDITION_IDS = tuple(item.condition_id for item in CONDITIONS)


def chemistry_from_coordinates(log_k0: float, e_over_r_k: float) -> ReactorChemistry:
    log_k0 = float(log_k0)
    e_over_r_k = float(e_over_r_k)
    if not (LOG_K0_BOUNDS[0] <= log_k0 <= LOG_K0_BOUNDS[1]):
        raise ValueError(f"log_k0 {log_k0!r} outside frozen K2 prior bounds")
    if not (E_OVER_R_BOUNDS_K[0] <= e_over_r_k <= E_OVER_R_BOUNDS_K[1]):
        raise ValueError(f"e_over_r_k {e_over_r_k!r} outside frozen K2 prior bounds")
    gas_constant = MOLAR_GAS_CONSTANT.magnitude_in(GAS_CONSTANT_UNIT)
    return replace(
        CHEMISTRY,
        k0=Quantity(math.exp(log_k0), "1/s"),
        activation_energy=Quantity(e_over_r_k * gas_constant, "J/mol"),
    )


def parameter_grid(size: int = REFERENCE_GRID_SIZE) -> np.ndarray:
    size = int(size)
    if size < 2:
        raise ValueError("K2 parameter grid requires at least two points per axis")
    log_axis = np.linspace(LOG_K0_BOUNDS[0], LOG_K0_BOUNDS[1], size, dtype=np.float64)
    e_axis = np.linspace(E_OVER_R_BOUNDS_K[0], E_OVER_R_BOUNDS_K[1], size, dtype=np.float64)
    log_mesh, e_mesh = np.meshgrid(log_axis, e_axis, indexing="ij")
    result = np.column_stack((log_mesh.ravel(), e_mesh.ravel()))
    result.setflags(write=False)
    return result
