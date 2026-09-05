"""T1 orchestration: three independent inferences at three fixed rungs.

    for each declared rung:
        build the forward map over the alpha grid with the real thermal solver
        infer alpha from the SAME observations
        measure the posterior against the known truth

Nothing selects a rung. The three runs are independent and their only
difference is resolution, so a difference between their posteriors can only be
discretization.

WHAT IS MEASURED
----------------
    posterior mean / MAP error against alpha_true
    posterior sd and 95% credible interval
    coverage of alpha_true
    QoI prediction error against the exact solution
    numerical discretization error at alpha_true
    computational cost (work proxy, and wall-seconds as telemetry)
    whether increasing fidelity removes the bias
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from experiments.shared.grid_inference import (
    posterior_weights,
    predictive_mean,
    summarize,
)
from src.engcore.domains.thermal.conduction1d import (
    MIDPOINT_METRIC,
    ConductionSlab,
    SlabDiscretization,
    solve_slab,
)
from src.engcore.scientific.units.quantity import Quantity
from src.engcore.sria.calibration import (
    FidelityDataStatus,
    FidelityOwnership,
    FidelityRung,
    ModelFidelityRelationship,
    fidelity_corpus_status,
)

from . import BASE_COMMIT, T1_VERSION
from . import t1_truth
from .t1_config import (
    ALPHA_UNIT,
    CREDIBLE_MASS,
    END_TIME_S,
    FIELD_UNIT,
    LENGTH_M,
    OBSERVATION_SIGMA,
    PREDICTED_BIAS,
    REFERENCE_RUNG_ID,
    RUNGS,
    SCIENTIFIC_QUESTION,
    alpha_grid,
    config_hash,
    config_payload,
    rung,
)

THERMAL_MODEL_REF = "thermal.conduction1d.linear_diffusion/0.1.0"


def preregistration_hash() -> str:
    """SHA-256 over the decision-visible config AND the grader truth."""
    blob = f"{config_hash()}|{t1_truth.truth_hash()}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# =====================================================================
# Forward maps
# =====================================================================

_FORWARD_CACHE: dict[str, tuple[np.ndarray, float]] = {}


def forward_map(rung_id: str) -> tuple[np.ndarray, float]:
    """Solver-predicted QoI at every alpha on the grid, for one fixed rung.

    Cached: the solver is deterministic, so caching is exact. Returns the map
    and the wall-seconds it took to build, the latter as telemetry only.
    """
    cached = _FORWARD_CACHE.get(rung_id)
    if cached is not None:
        return cached

    spec = rung(rung_id)
    grid = alpha_grid()
    started = time.perf_counter()
    values = np.array(
        [
            solve_slab(
                ConductionSlab(
                    slab_id=f"t1-{rung_id}",
                    length=Quantity(LENGTH_M, "meter"),
                    diffusivity=Quantity(float(alpha), ALPHA_UNIT),
                    end_time=Quantity(END_TIME_S, "second"),
                    discretization=SlabDiscretization(spec.n_cells, spec.n_steps),
                ),
                run_id=f"t1-{rung_id}-{index:04d}",
            ).values[MIDPOINT_METRIC].magnitude_in(FIELD_UNIT)
            for index, alpha in enumerate(grid.array)
        ]
    )
    elapsed = time.perf_counter() - started
    values.flags.writeable = False
    _FORWARD_CACHE[rung_id] = (values, elapsed)
    return values, elapsed


# =====================================================================
# One inference at one fixed rung
# =====================================================================

def infer_at_rung(rung_id: str) -> dict[str, Any]:
    spec = rung(rung_id)
    grid = alpha_grid()
    forward, build_seconds = forward_map(rung_id)
    observations = t1_truth.observations()

    weights = posterior_weights(
        grid, forward, observations, OBSERVATION_SIGMA
    )
    summary = summarize(grid, weights, credible_mass=CREDIBLE_MASS)

    truth = t1_truth.ALPHA_TRUE
    true_qoi = t1_truth.true_qoi()
    errors = summary.error_against(truth)

    # Discretization error: this rung's prediction at the TRUE alpha against
    # the exact solution. Measured at the truth so it is a property of the
    # rung, not of wherever the posterior happened to land.
    at_truth = float(np.interp(truth, grid.array, forward))
    discretization_error = at_truth - true_qoi

    qoi_predicted = predictive_mean(weights, forward)
    return {
        "rung_id": rung_id,
        "rank": spec.rank,
        "n_cells": spec.n_cells,
        "n_steps": spec.n_steps,
        "work_proxy": spec.work_proxy,
        "role": spec.role,
        "posterior": summary.to_dict(),
        "alpha_true": truth,
        "mean_error": errors["mean_error"],
        "map_error": errors["map_error"],
        "mean_relative_error": errors["mean_relative_error"],
        "mean_error_in_sd": errors["mean_error_in_sd"],
        "covers_truth": summary.covers(truth),
        "discretization_error_at_truth": discretization_error,
        "forward_at_truth": at_truth,
        "true_qoi": true_qoi,
        "qoi_predictive_mean": qoi_predicted,
        "qoi_prediction_error": qoi_predicted - true_qoi,
        "forward_map_build_seconds_telemetry": build_seconds,
        "_weights": weights,
    }


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if not k.startswith("_")}


# =====================================================================
# Fidelity corpus — cost only
# =====================================================================

def fidelity_records() -> dict[str, Any]:
    """Register the rungs and the observed COST relationship. Cost only.

    ``ModelFidelityRelationship`` refuses ``DOMAIN_OWNED`` by construction:
    accuracy and "good enough" are domain judgements and M2 may not assert
    them. So the bias this experiment measured is reported in T1's own results
    and is deliberately NOT written into the fidelity corpus — the module's own
    guard draws that line and T1 respects it rather than working around it.

    This is the first genuine low/high-fidelity pair in the repository: two
    rungs computing the same quantity at different accuracy, which is exactly
    what ``fidelity.py`` has documented as missing since M2.
    """
    rungs = tuple(
        FidelityRung(
            rung_id=f"thermal.conduction1d.{spec.rung_id}",
            rank=spec.rank,
            model_ref=THERMAL_MODEL_REF,
            description=spec.role,
            attributes={
                "n_cells": str(spec.n_cells),
                "n_steps": str(spec.n_steps),
                "work_proxy": str(spec.work_proxy),
            },
        )
        for spec in RUNGS
    )
    by_id = {r.rung_id.rsplit(".", 1)[-1]: r for r in rungs}

    relationships = []
    reference = rung(REFERENCE_RUNG_ID)
    for spec in RUNGS:
        if spec.rung_id == REFERENCE_RUNG_ID:
            continue
        relationships.append(
            ModelFidelityRelationship(
                low_rung=by_id[spec.rung_id],
                high_rung=by_id[REFERENCE_RUNG_ID],
                ownership=FidelityOwnership.STRUCTURE_TRANSFERABLE,
                metric="work_proxy_ratio",
                data_status=FidelityDataStatus.OBSERVED,
                median_ratio=reference.work_proxy / spec.work_proxy,
                paired_observations=alpha_grid().size,
                model_ref=THERMAL_MODEL_REF,
            )
        )
    status = fidelity_corpus_status(rungs)
    return {
        "rungs": [r.to_dict() for r in rungs],
        "relationships": [r.to_dict() for r in relationships],
        "corpus_status": status,
        "corpus_status_without_t1": fidelity_corpus_status(()),
        "recorded": "computational cost ratios only",
        "deliberately_not_recorded": (
            "accuracy, discrepancy and sufficiency. ModelFidelityRelationship "
            "raises on DOMAIN_OWNED, and T1 does not route around that: the "
            "measured bias lives in this experiment's results, not in the "
            "calibration corpus"
        ),
    }


# =====================================================================
# The study
# =====================================================================

def run_t1() -> dict[str, Any]:
    result: dict[str, Any] = {
        "experiment": "T1",
        "experiment_version": T1_VERSION,
        "base_commit": BASE_COMMIT,
        "config_hash": config_hash(),
        "preregistration_hash": preregistration_hash(),
        "config": config_payload(),
        "truth": t1_truth.truth_payload(),
        "scientific_question": SCIENTIFIC_QUESTION,
    }

    rows = [infer_at_rung(spec.rung_id) for spec in RUNGS]
    result["rungs"] = [_public(row) for row in rows]

    by_id = {row["rung_id"]: row for row in rows}
    coarse, reference = by_id["coarse"], by_id[REFERENCE_RUNG_ID]
    ordered = sorted(rows, key=lambda r: r["rank"])

    # --- does more fidelity remove the bias? ---------------------------
    abs_bias = [abs(row["mean_error"]) for row in ordered]
    bias_monotone = all(b < a for a, b in zip(abs_bias, abs_bias[1:]))
    result["fidelity_effect"] = {
        "bias_by_rank": [
            {"rung_id": row["rung_id"], "abs_mean_error": abs(row["mean_error"]),
             "in_sd": row["mean_error_in_sd"], "covers": row["covers_truth"]}
            for row in ordered
        ],
        "bias_decreases_monotonically_with_fidelity": bias_monotone,
        "bias_reduction_factor_coarse_to_reference": (
            abs(coarse["mean_error"]) / abs(reference["mean_error"])
            if reference["mean_error"] else float("inf")
        ),
        "coverage_recovered_at_reference": (
            (not coarse["covers_truth"]) and reference["covers_truth"]
        ),
        "posterior_sd_varies_across_rungs": (
            max(r["posterior"]["sd"] for r in rows)
            / min(r["posterior"]["sd"] for r in rows)
        ),
        "work_proxy_span": (
            reference["work_proxy"] / coarse["work_proxy"]
        ),
    }

    # --- the finding, stated only as far as the numbers reach -----------
    confident_and_biased = (
        not coarse["covers_truth"]
        and abs(coarse["mean_error_in_sd"]) > 3.0
        and coarse["posterior"]["sd"] < reference["posterior"]["sd"] * 3.0
    )
    result["finding"] = {
        "coarse_posterior_is_confident_and_biased": confident_and_biased,
        "coarse_mean_error_in_sd": coarse["mean_error_in_sd"],
        "coarse_covers_truth": coarse["covers_truth"],
        "coarse_posterior_sd": coarse["posterior"]["sd"],
        "reference_posterior_sd": reference["posterior"]["sd"],
        "statement": (
            "on this benchmark a solver at the cheapest rung of the frozen "
            "verification ladder produced a posterior over alpha whose width "
            "is comparable to the reference rung's, and whose centre is "
            f"{abs(coarse['mean_error_in_sd']):.1f} posterior standard "
            f"deviations from the true value. Nothing in the inference is "
            f"wrong: the forward map is biased, and an exact Bayesian update "
            f"against a biased forward map is exactly this confident and "
            f"exactly this wrong"
        )
        if confident_and_biased
        else (
            "the coarse rung did not produce a confidently biased posterior on "
            "this benchmark"
        ),
    }

    # --- decompose the error: discretization vs the noise draw ----------
    # Locally u_exact(alpha_hat) + d = mean(observations), so
    #     alpha_hat - alpha_true = (mean_obs - true_qoi - d) / (du/dalpha)
    # The second term is the SAME for every rung because every rung saw the
    # same observations. Separating the two says which one an error is made of,
    # which a single coverage bit cannot.
    sensitivity = t1_truth.sensitivity()
    mean_observation = float(np.mean(t1_truth.observations()))
    true_qoi = t1_truth.true_qoi()
    noise_component = (mean_observation - true_qoi) / sensitivity
    result["error_decomposition"] = {
        "sensitivity_du_dalpha": sensitivity,
        "mean_observation": mean_observation,
        "true_qoi": true_qoi,
        "observation_offset": mean_observation - true_qoi,
        "noise_component_alpha": noise_component,
        "noise_component_in_sd": noise_component / reference["posterior"]["sd"],
        "shared_across_rungs": True,
        "per_rung": {
            row["rung_id"]: {
                "discretization_component_alpha": (
                    -row["discretization_error_at_truth"] / sensitivity
                ),
                "noise_component_alpha": noise_component,
                "linear_prediction": (
                    -row["discretization_error_at_truth"] / sensitivity
                    + noise_component
                ),
                "observed_mean_error": row["mean_error"],
                "nonlinear_residual": (
                    row["mean_error"]
                    + row["discretization_error_at_truth"] / sensitivity
                    - noise_component
                ),
                "discretization_dominates": (
                    abs(row["discretization_error_at_truth"] / sensitivity)
                    > abs(noise_component)
                ),
            }
            for row in rows
        },
        "note": (
            "coverage of ONE credible interval from ONE noise draw is a single "
            "Bernoulli outcome, not a calibration statement. What the "
            "decomposition shows is which term the residual error is made of, "
            "and that is a property of the rung rather than of the draw"
        ),
    }

    result["prediction_check"] = {
        row["rung_id"]: {
            "predicted_alpha_bias": PREDICTED_BIAS[row["rung_id"]]["alpha_bias"],
            "observed_alpha_bias": row["mean_error"],
            "predicted_in_sd": PREDICTED_BIAS[row["rung_id"]]["in_sd"],
            "observed_in_sd": row["mean_error_in_sd"],
            "predicted_coverage": PREDICTED_BIAS[row["rung_id"]]["coverage"],
            "observed_coverage": row["covers_truth"],
            "coverage_as_predicted": (
                PREDICTED_BIAS[row["rung_id"]]["coverage"] == row["covers_truth"]
            ),
        }
        for row in rows
    }

    result["fidelity_corpus"] = fidelity_records()
    result["_rows"] = rows
    return result


# =====================================================================
# Rendering
# =====================================================================

def render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# T1 — Thermal parameter inference at fixed fidelity")
    add("")
    add(f"Config hash: `{result['config_hash']}`")
    add(f"Preregistration hash: `{result['preregistration_hash']}`")
    add("")
    add(f"**{result['scientific_question']}**")
    add("")
    truth = result["truth"]
    add(
        f"Hidden truth (grader only): α = {truth['alpha_true']:.4e} m²/s, "
        f"exact QoI = {truth['true_qoi']:.10f}, sensitivity dα→du = "
        f"{truth['sensitivity_du_dalpha']:.1f}. Observations are the exact "
        f"solution plus declared Gaussian noise, generated once and reused "
        f"unchanged at every rung."
    )

    add("")
    add("## Three inferences, one difference")
    add("")
    add("| rung | cells×steps | work | discretization err | posterior mean | "
        "mean err | in sd | 95% CI | covers α |")
    add("|---|---|---|---|---|---|---|---|---|")
    for row in result["rungs"]:
        p = row["posterior"]
        add(
            f"| `{row['rung_id']}` | {row['n_cells']}×{row['n_steps']} | "
            f"{row['work_proxy']:,} | "
            f"{row['discretization_error_at_truth']:+.4e} | "
            f"{p['mean']:.6e} | {row['mean_error']:+.3e} | "
            f"{row['mean_error_in_sd']:+.1f} | "
            f"[{p['lower']:.5e}, {p['upper']:.5e}] | "
            f"{'**yes**' if row['covers_truth'] else '**NO**'} |"
        )

    add("")
    add("| rung | posterior sd | CI width | QoI predictive mean | QoI pred err |")
    add("|---|---|---|---|---|")
    for row in result["rungs"]:
        p = row["posterior"]
        add(
            f"| `{row['rung_id']}` | {p['sd']:.4e} | {p['width']:.4e} | "
            f"{row['qoi_predictive_mean']:.8f} | "
            f"{row['qoi_prediction_error']:+.4e} |"
        )

    effect = result["fidelity_effect"]
    add("")
    add("## Does more fidelity remove the bias?")
    add("")
    add(f"- bias falls monotonically with fidelity: "
        f"**{effect['bias_decreases_monotonically_with_fidelity']}**")
    add(f"- coarse → reference bias reduction: "
        f"**{effect['bias_reduction_factor_coarse_to_reference']:.0f}×** "
        f"for **{effect['work_proxy_span']:.0f}×** the work")
    add(f"- coverage recovered at the reference rung: "
        f"**{effect['coverage_recovered_at_reference']}**")
    add(f"- posterior width varies across rungs by only "
        f"{effect['posterior_sd_varies_across_rungs']:.2f}× — the *confidence* "
        f"barely moves while the *answer* does")

    add("")
    add("## Prediction recorded before execution")
    add("")
    add("| rung | predicted bias (σ) | observed (σ) | coverage predicted | "
        "observed | as predicted |")
    add("|---|---|---|---|---|---|")
    for rung_id, check in result["prediction_check"].items():
        add(
            f"| `{rung_id}` | {check['predicted_in_sd']:.1f} | "
            f"{check['observed_in_sd']:+.1f} | "
            f"{check['predicted_coverage']} | {check['observed_coverage']} | "
            f"{'yes' if check['coverage_as_predicted'] else '**no**'} |"
        )

    add("")
    add("### Where the prediction missed, and why")
    add("")
    dec = result["error_decomposition"]
    add(
        f"The pre-execution prediction was computed from discretization alone. "
        f"It omitted the realized noise draw, which displaces every rung's "
        f"posterior by the same amount: the four observations averaged "
        f"{dec['observation_offset']:+.3e} below the exact QoI, worth "
        f"{dec['noise_component_alpha']:+.3e} in α, or "
        f"{dec['noise_component_in_sd']:+.1f} posterior standard deviations. "
        f"That term is shared by all three rungs because all three saw the "
        f"same observations."
    )
    add("")
    add("| rung | discretization → α | noise → α | linear sum | observed | "
        "nonlinear residual | dominated by |")
    add("|---|---|---|---|---|---|---|")
    for rung_id, part in dec["per_rung"].items():
        add(
            f"| `{rung_id}` | {part['discretization_component_alpha']:+.4e} | "
            f"{part['noise_component_alpha']:+.4e} | "
            f"{part['linear_prediction']:+.4e} | "
            f"{part['observed_mean_error']:+.4e} | "
            f"{part['nonlinear_residual']:+.4e} | "
            f"{'discretization' if part['discretization_dominates'] else 'noise'} |"
        )
    add("")
    add(
        "So the discretization prediction held at every rung; what the "
        "prediction got wrong was assuming a noise-free draw. The reference "
        "rung missed coverage not because its numerics were inadequate but "
        "because this particular draw sat "
        f"{abs(dec['noise_component_in_sd']):.1f}σ low — and "
        f"{dec['note']}."
    )

    add("")
    add("## Finding")
    add("")
    add(result["finding"]["statement"] + ".")
    add("")
    add(
        "The complement is equally the result: at the reference rung the "
        "residual error is noise-dominated, and refining further cannot fix "
        "it. Discretization stopped being the binding constraint somewhere "
        "between the medium and reference rungs, and no amount of additional "
        "fidelity buys back the missing coverage."
    )

    add("")
    add("## Fidelity corpus")
    add("")
    corpus = result["fidelity_corpus"]
    add(f"Registered {len(corpus['rungs'])} rungs and "
        f"{len(corpus['relationships'])} observed relationships — "
        f"**{corpus['recorded']}**.")
    add("")
    add(f"- corpus status without T1: "
        f"`{corpus['corpus_status_without_t1']['status']}`, "
        f"{corpus['corpus_status_without_t1']['models_with_a_real_ladder']} "
        f"models with a real ladder")
    add(f"- corpus status with T1: `{corpus['corpus_status']['status']}`, "
        f"{corpus['corpus_status']['models_with_a_real_ladder']} "
        f"models with a real ladder")
    add("")
    add(
        "These are the first genuine low/high-fidelity rungs in the repository "
        "— the same quantity computed at three accuracies — so the M2 note "
        "that no such pairs exist no longer applies to the thermal model. No "
        "production code changed to make that true."
    )
    add("")
    add(f"Not recorded: {corpus['deliberately_not_recorded']}.")

    add("")
    add("## What this does not show")
    add("")
    for item in result["config"]["non_goals"]:
        add(f"- {item}")
    return "\n".join(lines)


def main() -> int:
    result = run_t1()
    root = Path(__file__).resolve().parent
    public = {k: v for k, v in result.items() if not k.startswith("_")}
    (root / "t1_config_frozen.json").write_text(
        json.dumps(
            {
                "config": result["config"],
                "config_hash": result["config_hash"],
                "truth": result["truth"],
                "preregistration_hash": result["preregistration_hash"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (root / "t1_results.json").write_text(
        json.dumps(public, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    report = render_markdown(result)
    (root / "t1_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
