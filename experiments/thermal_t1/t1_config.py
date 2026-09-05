"""T1 preregistered configuration — decision-visible half.

Frozen BEFORE the scored run. The true diffusivity lives in :mod:`t1_truth`;
the preregistration hash over both halves is computed by the run module, so
nothing here has to import the truth.

THE ONE THING THAT VARIES
-------------------------
Three inferences, three fixed fidelity rungs, and NOTHING else different:

    same alpha_true, same observation model, same sigma, same observations,
    same prior, same grid, same QoI, same end time, same slab.

Only the resolution of the forward map changes. So any difference between the
three posteriors is attributable to discretization and to nothing else. That
is the whole design; everything below is bookkeeping for it.

WHY THE GRID IS WHERE IT IS
---------------------------
The coarse rung's discretization error biases the inferred alpha upward — the
solver over-predicts u at every alpha, so matching a lower observation requires
a higher alpha. The grid has to be wide enough to contain that biased posterior
without truncating it, or the truncation would flatter the coarse rung by
hiding how far off it went. It also has to be fine enough that the posterior is
resolved rather than collapsed onto two cells.

[1.15e-5, 1.30e-5] at 401 points satisfies both: the predicted coarse posterior
centre sits at 1.256e-5, comfortably inside, and the spacing 3.75e-9 gives
about 4.6 cells per posterior standard deviation.

A PREDICTION IS RECORDED, NOT A THRESHOLD
------------------------------------------
There is no pass/fail gate in this experiment, so there is nothing to tune.
What is recorded before execution is a *prediction* derived from the local
sensitivity du/dalpha and the frozen gate's measured discretization errors, so
the outcome can be checked against a stated expectation instead of explained
afterwards.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from experiments.shared.grid_inference import ParameterGrid

from . import BASE_COMMIT, T1_VERSION

EXPERIMENT_ID = "T1"
EXPERIMENT_NAME = "thermal_parameter_inference_at_fixed_fidelity"

#: The frozen thermal domain this experiment's forward map comes from, pinned
#: at ``BASE_COMMIT`` in the same way E2 pins E1 and E3 pins E2. A test
#: recomputes these; if the solver changes, T1's numbers stop being about the
#: solver that produced them and the test says so instead of silently drifting.
#:
#: These are deliberately NOT part of ``config_hash()``: the config hash covers
#: the experimental design, and the design is unchanged by which revision of the
#: solver it happens to be run against. The two are checked separately.
THERMAL_FROZEN_FILE_DIGESTS: dict[str, str] = {
    "src/engcore/domains/thermal/__init__.py":
        "8923de0cbe22ee4ab4ced90aa7e6b1d75529875673283f03c8ec3e2ccf9b64ef",
    "src/engcore/domains/thermal/conduction1d/__init__.py":
        "a8d6bd0c051d57d295857492fcc1b0cb8f967363f907ea9d58945ef5e75fe963",
    "src/engcore/domains/thermal/conduction1d/errors.py":
        "e9c6aab7564c582eb40a30caa5d34b30aec3cdc4181dad4d5ae3d0a2d1425c6b",
    "src/engcore/domains/thermal/conduction1d/problem.py":
        "54fb8d3f1d3890f5843f128eb0553dd8d117180bb9da82182b9c46adbc51e8cb",
    "src/engcore/domains/thermal/conduction1d/reference.py":
        "7e231b9f5adebc6c5e8b89f17cc885f325419d1d91bc3f56b3d9e2cb5e5ae23e",
    "src/engcore/domains/thermal/conduction1d/solver.py":
        "073321a1f967baf8a776a9282e875c2892b6c3e80f29736ec9282435013a38ce",
    "src/engcore/domains/thermal/conduction1d/validation.py":
        "84b798bdb8340b6e8cf8c286db8db3f7c025907e4dd666c932859f5ed441abca",
}

# --- the physical benchmark, inherited from the frozen thermal gate ----------
LENGTH_M = 0.1
END_TIME_S = 60.0
FIELD_UNIT = "dimensionless"
ALPHA_UNIT = "m**2/s"

# --- the parameter under inference -------------------------------------------
ALPHA_MIN = 1.15e-5
ALPHA_MAX = 1.30e-5
ALPHA_POINTS = 401
PRIOR = "uniform"

# --- the observation model ---------------------------------------------------
#: Gaussian, additive, on the midpoint field value. Injected by the benchmark;
#: the solver is deterministic and that is stated rather than blurred.
OBSERVATION_SIGMA = 1.0e-3
OBSERVATION_COUNT = 4
OBSERVATION_METRIC = "u:midpoint"
NOISE_SEED = 20260907

CREDIBLE_MASS = 0.95


# --- the fixed fidelity rungs ------------------------------------------------
@dataclass(frozen=True)
class FidelityRungSpec:
    """One fixed resolution. Nothing in T1 selects among these."""

    rung_id: str
    rank: int
    n_cells: int
    n_steps: int
    role: str

    @property
    def work_proxy(self) -> int:
        return self.n_cells * self.n_steps

    def to_dict(self) -> dict[str, Any]:
        return {
            "rung_id": self.rung_id,
            "rank": self.rank,
            "n_cells": self.n_cells,
            "n_steps": self.n_steps,
            "role": self.role,
            "work_proxy": self.work_proxy,
        }


RUNGS: tuple[FidelityRungSpec, ...] = (
    FidelityRungSpec(
        rung_id="coarse",
        rank=0,
        n_cells=8,
        n_steps=10,
        role=(
            "cheapest rung on the frozen verification ladder; converges and "
            "validates like any other, and is wrong by 3.3% on the QoI"
        ),
    ),
    FidelityRungSpec(
        rung_id="medium",
        rank=1,
        n_cells=64,
        n_steps=80,
        role="an unremarkable working resolution",
    ),
    FidelityRungSpec(
        rung_id="reference",
        rank=2,
        n_cells=512,
        n_steps=640,
        role=(
            "the finest rung of the frozen ladder — the one that earned "
            "ANALYTICALLY_VERIFIED at 3.97e-04 relative error"
        ),
    ),
)

#: Which rung supplies the reference QoI for prediction-error comparisons.
REFERENCE_RUNG_ID = "reference"

# --- recorded before execution ----------------------------------------------
#: Local sensitivity of the QoI to alpha at the true value, from the closed
#: form: du/dalpha = -u * pi^2 * t / L^2.
PREDICTED_SENSITIVITY = -29096.2
#: sigma / |du/dalpha| / sqrt(n)
PREDICTED_POSTERIOR_SD = 1.718e-8
PREDICTED_BIAS = {
    "coarse": {"alpha_bias": 5.596e-7, "relative": 0.0466, "in_sd": 32.6,
               "coverage": False},
    "medium": {"alpha_bias": 5.546e-8, "relative": 0.0046, "in_sd": 3.2,
               "coverage": False},
    "reference": {"alpha_bias": 6.696e-9, "relative": 0.0006, "in_sd": 0.4,
                  "coverage": True},
}
PREDICTION_BASIS = (
    "alpha_bias = discretization_error / |du/dalpha|, with the discretization "
    "errors taken from the frozen thermal verification gate at alpha = 1.2e-5. "
    "This is a prediction to be checked, not a threshold to be met: T1 has no "
    "pass/fail gate and therefore nothing to tune"
)

SCIENTIFIC_QUESTION = (
    "Can a numerically coarse but apparently converged solver produce a "
    "posterior over alpha that is confident yet systematically biased?"
)

NON_GOALS = (
    "no adaptive fidelity selection — nothing here chooses a rung",
    "no campaign, no EVPI, no EVSI, no certification, no model adequacy",
    "no physical validation; the hidden truth is synthetic and known",
    "no new inference framework beyond a grid posterior over one parameter",
)


def alpha_grid() -> ParameterGrid:
    step = (ALPHA_MAX - ALPHA_MIN) / (ALPHA_POINTS - 1)
    return ParameterGrid(
        name="alpha",
        unit=ALPHA_UNIT,
        values=tuple(ALPHA_MIN + i * step for i in range(ALPHA_POINTS)),
    )


def rung(rung_id: str) -> FidelityRungSpec:
    for spec in RUNGS:
        if spec.rung_id == rung_id:
            return spec
    raise KeyError(f"no declared rung {rung_id!r}")


def config_payload() -> dict[str, Any]:
    grid = alpha_grid()
    return {
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "experiment_version": T1_VERSION,
        "base_commit": BASE_COMMIT,
        "scientific_question": SCIENTIFIC_QUESTION,
        "benchmark": {
            "pde": "du/dt = alpha d2u/dx2",
            "length_m": LENGTH_M,
            "end_time_s": END_TIME_S,
            "boundary_conditions": "u(0,t) = u(L,t) = 0",
            "initial_condition": "u(x,0) = sin(pi x / L)",
            "field_unit": FIELD_UNIT,
            "qoi": OBSERVATION_METRIC,
        },
        "parameter": grid.to_dict(),
        "observation_model": {
            "distribution": "gaussian_additive",
            "sigma": OBSERVATION_SIGMA,
            "count": OBSERVATION_COUNT,
            "metric": OBSERVATION_METRIC,
            "noise_seed": NOISE_SEED,
            "note": (
                "noise is injected by the benchmark; the solver is "
                "deterministic and no measurement of anything physical occurs"
            ),
        },
        "fidelity_rungs": [spec.to_dict() for spec in RUNGS],
        "reference_rung_id": REFERENCE_RUNG_ID,
        "credible_mass": CREDIBLE_MASS,
        "held_constant_across_rungs": [
            "alpha_true",
            "observation model and sigma",
            "the observation values themselves",
            "prior and grid",
            "slab length, end time, boundary and initial conditions",
        ],
        "varied_across_rungs": ["forward-map resolution only"],
        "prediction_before_execution": {
            "sensitivity_du_dalpha": PREDICTED_SENSITIVITY,
            "posterior_sd": PREDICTED_POSTERIOR_SD,
            "per_rung": PREDICTED_BIAS,
            "basis": PREDICTION_BASIS,
        },
        "non_goals": list(NON_GOALS),
    }


def config_hash() -> str:
    blob = json.dumps(config_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
