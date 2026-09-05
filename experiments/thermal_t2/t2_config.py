"""T2 preregistered configuration — decision-visible half.

Frozen BEFORE the scored run. Everything T1 fixed stays fixed and is imported
from :mod:`t1_config` rather than restated, so it cannot drift: the alpha grid,
the prior, sigma, the observation count and metric, the credible level, the
benchmark, and the three rungs all come from T1 by import.

WHAT VARIES
-----------
The observation-noise realization, and nothing else.

THE PREDICTION, AND WHY IT IS A NUMBER
---------------------------------------
Under a correctly specified model the posterior centre over repeated draws is

    alpha_hat ~ Normal(alpha_true + b, s^2)

where ``b`` is the rung's fixed discretization-induced bias and ``s`` is the
posterior sd. The two coincide here for a reason worth stating: T1 measured
posterior sd 1.7235e-08 against sigma/(|du/dalpha| sqrt(n)) = 1.7184e-08, so
the posterior width really is the sampling width of the estimator, and the only
thing that can break coverage is ``b``. That makes coverage predictable in
closed form:

    coverage = Phi(q - b/s) - Phi(-q - b/s),  q = 1.95996

evaluated at T1's MEASURED per-rung bias. The predictions below are that
formula's output, not a guess, which is what makes them falsifiable.

WHAT WOULD MAKE THE PREDICTION WRONG FOR THE RIGHT REASON
----------------------------------------------------------
The credible interval is equal-tailed on a discrete grid, so it can only widen
to the next grid point, never narrow. One spacing is 0.218 posterior sd, so the
interval is conservative by up to that much and measured coverage may sit
slightly ABOVE the closed-form value. That is a known property of the frozen
harness, declared here rather than discovered afterwards, and it is why the
acceptance bands are two-sided rather than "at least".

THE CONTROL ARM DECIDES WHAT A FAILURE MEANS
---------------------------------------------
If the reference rung miscalibrates, that is only evidence about fidelity if
the exact-forward-map arm calibrates. The control is preregistered here for
exactly that reason, so the diagnosis is not invented after seeing the number.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from experiments.shared.grid_inference import ParameterGrid
from experiments.thermal_t1.t1_config import (
    ALPHA_UNIT,
    CREDIBLE_MASS,
    END_TIME_S,
    FIELD_UNIT,
    LENGTH_M,
    OBSERVATION_COUNT,
    OBSERVATION_METRIC,
    OBSERVATION_SIGMA,
    PRIOR,
    REFERENCE_RUNG_ID,
    RUNGS,
    alpha_grid,
    rung,
)
from experiments.thermal_t1.t1_config import config_hash as t1_config_hash

from . import BASE_COMMIT, T2_VERSION

EXPERIMENT_ID = "T2"
EXPERIMENT_NAME = "repeated_draw_numerical_calibration"

# Re-exported so t2_run and the tests read the fixed design from one place.
__all__ = [
    "ALPHA_UNIT",
    "CREDIBLE_MASS",
    "END_TIME_S",
    "FIELD_UNIT",
    "LENGTH_M",
    "OBSERVATION_COUNT",
    "OBSERVATION_METRIC",
    "OBSERVATION_SIGMA",
    "PRIOR",
    "REFERENCE_RUNG_ID",
    "RUNGS",
    "alpha_grid",
    "rung",
]

# =====================================================================
# 1. Replication count and seed rule
# =====================================================================

#: Number of independent observation draws. Chosen from the binomial standard
#: error of an empirical coverage estimate: at p = 0.93, se = 0.0114 and
#: 3 se = 0.034, which separates the predicted 0.932 from the predicted 0.105
#: by far more than sampling noise while leaving the reference band tight
#: enough to fail. The forward maps are built once and cached, so a replication
#: costs a reweighting over 401 grid points and nothing else; R is set by the
#: precision the question needs, not by what the budget allows.
REPLICATIONS = 500

#: Root entropy for the draw streams. Deliberately NOT T1's 20260907, so T1's
#: single draw is not one of T2's replications and the two results stay
#: independent.
SEED_ENTROPY = 20260908

#: How the per-replication streams are derived. ``SeedSequence.spawn`` is used
#: rather than seed+i because it is the documented way to obtain independent
#: streams; sequential integer seeds are not guaranteed to be independent.
#: A test asserts the resulting draws are distinct.
SEED_RULE = (
    "numpy.random.SeedSequence(SEED_ENTROPY).spawn(REPLICATIONS); replication "
    "i uses default_rng(children[i]) and draws OBSERVATION_COUNT normal "
    "deviates. Deterministic and reproducible from SEED_ENTROPY alone"
)

# =====================================================================
# 2. Nominal credible-interval level
# =====================================================================

#: Imported from T1, restated here as the nominal level under test.
NOMINAL_LEVEL = CREDIBLE_MASS          # 0.95
#: Two-sided normal quantile for NOMINAL_LEVEL, used only for the prediction.
NOMINAL_QUANTILE = 1.959963984540054

# =====================================================================
# 3. Metrics
# =====================================================================

METRICS = (
    "empirical_coverage",
    "posterior_mean_bias",
    "parameter_rmse",
    "posterior_sd",
    "standardized_estimation_error",
    "confidently_wrong_rate",
    "qoi_prediction_error",
    "discretization_contribution",
    "observation_noise_contribution",
    "work_proxy",
)

#: A posterior counts as CONFIDENTLY WRONG when it is both wrong and narrow:
#: its credible interval excludes alpha_true, AND its width is no more than
#: this multiple of the median interval width at the reference rung. The second
#: clause is what distinguishes "wrong because it admitted it did not know"
#: from "wrong while looking exactly as authoritative as a good answer", and
#: only the latter is the failure mode T1 exposed.
CONFIDENTLY_WRONG_WIDTH_FACTOR = 1.5

# =====================================================================
# 4. The control arm
# =====================================================================

#: The exact analytic forward map: same inference, zero discretization error.
#: NOT a fidelity rung. Its job is to decide whether a miscalibration at the
#: solver rungs is about numerics or about the inference.
CONTROL_ARM_ID = "exact"
CONTROL_ARM_ROLE = (
    "zero-discretization control. Same grid, prior, sigma, observations and "
    "inference; the forward map is the closed-form solution instead of a "
    "solve. Not a fidelity rung and never compared on cost"
)

# =====================================================================
# 5. Predictions, recorded before execution
# =====================================================================

#: T1's MEASURED per-rung bias (the repeatable part: total mean error minus the
#: noise term of T1's own draw) and posterior sd, from t1_results.json.
T1_MEASURED = {
    "coarse": {"bias": 6.0044e-07, "posterior_sd": 1.8726e-08},
    "medium": {"bias": 5.6207e-08, "posterior_sd": 1.7373e-08},
    "reference": {"bias": 6.7899e-09, "posterior_sd": 1.7235e-08},
}

#: coverage = Phi(q - b/s) - Phi(-q - b/s), evaluated at T1_MEASURED.
PREDICTED_COVERAGE = {
    "coarse": 0.000,
    "medium": 0.101,
    "reference": 0.932,
    CONTROL_ARM_ID: 0.950,
}

PREDICTED_STANDARDIZED_ERROR_MEAN = {
    "coarse": 32.06,
    "medium": 3.24,
    "reference": 0.39,
    CONTROL_ARM_ID: 0.00,
}

QUALITATIVE_PREDICTION = (
    "coarse: severe undercoverage driven by discretization bias. medium: "
    "materially improved but still biased and still undercovering. reference: "
    "coverage approaches the nominal level because discretization error has "
    "become small relative to observation noise"
)

# =====================================================================
# 6. Acceptance and falsification criteria
# =====================================================================

#: Two-sided acceptance bands on empirical coverage. Widths are about four
#: binomial standard errors plus room for the discrete-interval conservatism
#: declared above. Wide enough not to fail on sampling noise, narrow enough
#: that a wrong mechanism cannot pass.
COVERAGE_ACCEPTANCE_BANDS = {
    "coarse": (0.000, 0.020),
    "medium": (0.055, 0.155),
    "reference": (0.880, 0.980),
    CONTROL_ARM_ID: (0.920, 0.985),
}

ACCEPTANCE_CRITERIA = (
    "A1 coarse empirical coverage falls inside its band, confirming that "
    "discretization bias destroys coverage rather than merely degrading it",
    "A2 medium coverage falls inside its band: materially better than coarse "
    "and still materially below nominal",
    "A3 reference coverage falls inside its band, approaching nominal",
    "A4 the control arm calibrates, which is what makes A1-A3 statements "
    "about numerics rather than about the inference",
    "A5 |mean standardized estimation error| decreases monotonically with "
    "fidelity",
    "A6 parameter RMSE decreases monotonically with fidelity",
    "A7 at the reference rung the observation-noise contribution exceeds the "
    "discretization contribution, and at the coarse rung it does not; the "
    "crossover is the answer to the second half of the question",
    "A8 the confidently-wrong rate decreases monotonically with fidelity",
)

FALSIFICATION_CRITERIA = (
    "F1 if the CONTROL ARM misses its band, no conclusion about fidelity may "
    "be drawn from this run at all. Investigate in this order: the discrete "
    "equal-tailed interval on a 401-point grid, the Gaussian likelihood and "
    "whether sigma is the sigma actually used to draw, prior truncation at the "
    "grid edges, and the normal approximation behind the prediction. Report "
    "the diagnosis; do not adjust the rungs",
    "F2 if the reference rung misses its band while the control arm passes, "
    "the reference rung's discretization is NOT negligible relative to "
    "observation noise, and T1's reading of it was wrong. Report that",
    "F3 if the coarse rung covers materially more often than its band, the "
    "discretization-bias mechanism T1 claimed is not what is happening",
    "F4 if posterior sd varies materially across draws at a fixed rung, the "
    "claim that confidence is draw-independent fails and the confidently-wrong "
    "rate must be re-read",
)

#: Explicit, because it is the whole discipline of this experiment.
NO_TUNING_AFTER_RESULTS = (
    "the rungs, prior, sigma, grid, observation design, replication count, "
    "seed rule, credible level, acceptance bands and predictions above are "
    "fixed before execution and are not adjusted afterwards. A missed band is "
    "reported as a missed band"
)

SCIENTIFIC_QUESTION = (
    "Does numerical discretization error cause systematic posterior "
    "miscalibration and confident parameter bias across repeated observations, "
    "and at what fidelity does observation noise become the dominant error "
    "source?"
)

NON_GOALS = (
    "no adaptive fidelity selection and no fidelity policy — nothing here "
    "chooses a rung",
    "no new EVSI machinery, no commitment promotion, no ObligationSet change, "
    "no certification change",
    "no production SRIA change of any kind",
    "no physical validation; the hidden truth is synthetic and known",
    "no modification to T1's preregistration or results, which are pinned by "
    "digest",
)

# =====================================================================
# Pins
# =====================================================================

#: T1 and the shared harness, pinned at BASE_COMMIT. T2 reuses them read-only;
#: if either moves, T2's numbers are no longer about the thing T1 froze.
T1_FROZEN_FILE_DIGESTS: dict[str, str] = {
    "experiments/thermal_t1/__init__.py":
        "68d0c56658b3c00c20fb773f63f95a6b18f2cc3996236484672b036e68ec93ce",
    "experiments/thermal_t1/t1_config.py":
        "fa2de63a80b97c8803821326a46fdcb27bc7b3a335f7fbb8178a6c75ff36e5ef",
    "experiments/thermal_t1/t1_run.py":
        "2c461d4f459b49822d28599f5e6aed497f7e6128933546d6a17ecc653850d029",
    "experiments/thermal_t1/t1_truth.py":
        "9dd9e3c0fffc52d6ce4704544868ae2631ce49515c117a14c84ca55b1a63b9e9",
    "experiments/shared/__init__.py":
        "3bb10216a0a4c446f3feffdf3c25ea7c903b41c025b07ee5d7e3058a925e039e",
    "experiments/shared/grid_inference.py":
        "f192c862f9afb0e4edd0dd6a65fa551477025d77d853c2c2ab3a97018de7b467",
}


def seed_sequences() -> tuple[np.random.SeedSequence, ...]:
    """The preregistered per-replication streams. Decision-visible: which
    draws happen is part of the design, what they contain is not."""
    return tuple(np.random.SeedSequence(SEED_ENTROPY).spawn(REPLICATIONS))


def arm_ids() -> tuple[str, ...]:
    """Every arm the study runs, control last."""
    return tuple(spec.rung_id for spec in RUNGS) + (CONTROL_ARM_ID,)


def config_payload() -> dict[str, Any]:
    grid: ParameterGrid = alpha_grid()
    return {
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "experiment_version": T2_VERSION,
        "base_commit": BASE_COMMIT,
        "scientific_question": SCIENTIFIC_QUESTION,
        "inherited_from_t1": {
            "t1_config_hash": t1_config_hash(),
            "held_fixed": [
                "alpha_true",
                "prior and grid",
                "observation model, count, metric and location",
                "sigma",
                "coarse / medium / reference rungs",
                "inference implementation",
            ],
            "varied": ["observation-noise realization only"],
        },
        "replications": REPLICATIONS,
        "seed_entropy": SEED_ENTROPY,
        "seed_rule": SEED_RULE,
        "nominal_level": NOMINAL_LEVEL,
        "parameter": grid.to_dict(),
        "observation_model": {
            "distribution": "gaussian_additive",
            "sigma": OBSERVATION_SIGMA,
            "count": OBSERVATION_COUNT,
            "metric": OBSERVATION_METRIC,
        },
        "arms": {
            "fidelity_rungs": [spec.to_dict() for spec in RUNGS],
            "control_arm_id": CONTROL_ARM_ID,
            "control_arm_role": CONTROL_ARM_ROLE,
        },
        "metrics": list(METRICS),
        "confidently_wrong_width_factor": CONFIDENTLY_WRONG_WIDTH_FACTOR,
        "prediction_before_execution": {
            "t1_measured_inputs": T1_MEASURED,
            "coverage": PREDICTED_COVERAGE,
            "standardized_error_mean": PREDICTED_STANDARDIZED_ERROR_MEAN,
            "qualitative": QUALITATIVE_PREDICTION,
            "basis": (
                "coverage = Phi(q - b/s) - Phi(-q - b/s) with b and s taken "
                "from T1's measured results, q = 1.95996"
            ),
        },
        "coverage_acceptance_bands": {
            key: list(value) for key, value in COVERAGE_ACCEPTANCE_BANDS.items()
        },
        "acceptance_criteria": list(ACCEPTANCE_CRITERIA),
        "falsification_criteria": list(FALSIFICATION_CRITERIA),
        "no_tuning_after_results": NO_TUNING_AFTER_RESULTS,
        "non_goals": list(NON_GOALS),
    }


def config_hash() -> str:
    blob = json.dumps(config_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
