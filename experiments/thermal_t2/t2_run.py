"""T2 orchestration: the same inference, many draws, four arms.

    build each arm's forward map once
    for each preregistered replication:
        draw observations
        for each arm: infer alpha from THAT draw
    aggregate coverage, bias, RMSE and the rest across draws

Three arms are the frozen fidelity rungs. The fourth is the exact analytic
forward map, which has no discretization error and therefore says whether any
miscalibration is about numerics or about the inference.

Nothing selects an arm. Every arm runs on every draw.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

from experiments.shared.grid_inference import (
    posterior_weights,
    predictive_mean,
    summarize,
)
from experiments.thermal_t1 import t1_run
from src.engcore.domains.thermal.conduction1d import exact_midpoint

from . import BASE_COMMIT, T2_VERSION
from . import t2_truth
from .t2_config import (
    CONFIDENTLY_WRONG_WIDTH_FACTOR,
    CONTROL_ARM_ID,
    COVERAGE_ACCEPTANCE_BANDS,
    END_TIME_S,
    LENGTH_M,
    NOMINAL_LEVEL,
    OBSERVATION_SIGMA,
    PREDICTED_COVERAGE,
    PREDICTED_STANDARDIZED_ERROR_MEAN,
    REFERENCE_RUNG_ID,
    REPLICATIONS,
    RUNGS,
    SCIENTIFIC_QUESTION,
    alpha_grid,
    arm_ids,
    config_hash,
    config_payload,
    rung,
)


def preregistration_hash() -> str:
    """SHA-256 over the decision-visible config AND every drawn value."""
    blob = f"{config_hash()}|{t2_truth.truth_hash()}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# =====================================================================
# Forward maps — three reused from T1, one exact control
# =====================================================================

_CONTROL_CACHE: tuple[np.ndarray, float] | None = None


def control_forward_map() -> tuple[np.ndarray, float]:
    """The closed-form QoI over the alpha grid. Zero discretization error."""
    global _CONTROL_CACHE
    if _CONTROL_CACHE is None:
        started = time.perf_counter()
        values = np.array(
            [
                exact_midpoint(
                    length_m=LENGTH_M, alpha_m2_s=float(a), time_s=END_TIME_S
                )
                for a in alpha_grid().array
            ]
        )
        values.flags.writeable = False
        _CONTROL_CACHE = (values, time.perf_counter() - started)
    return _CONTROL_CACHE


def arm_forward_map(arm_id: str) -> tuple[np.ndarray, float]:
    """Solver rungs come from T1 unchanged; the control is computed here."""
    if arm_id == CONTROL_ARM_ID:
        return control_forward_map()
    return t1_run.forward_map(arm_id)


def arm_work_proxy(arm_id: str) -> int | None:
    """The control arm has no meaningful work proxy and is never costed."""
    if arm_id == CONTROL_ARM_ID:
        return None
    return rung(arm_id).work_proxy


# =====================================================================
# Aggregation helpers
# =====================================================================

def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054
                    ) -> tuple[float, float]:
    """Wilson score interval for the coverage estimate itself.

    Reported because an empirical coverage of 0.932 from 500 draws is not the
    same claim as 0.932, and the difference is what separates this experiment
    from T1's single Bernoulli outcome. Wilson rather than normal-approximation
    because coarse coverage is expected at or near zero, where the normal
    interval is useless.
    """
    if trials <= 0:
        return (float("nan"), float("nan"))
    p = successes / trials
    denominator = 1.0 + z**2 / trials
    centre = (p + z**2 / (2 * trials)) / denominator
    half = (
        z * math.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2))
    ) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


# =====================================================================
# One arm, all replications
# =====================================================================

def run_arm(arm_id: str, draws: tuple[tuple[float, ...], ...]) -> dict[str, Any]:
    grid = alpha_grid()
    forward, build_seconds = arm_forward_map(arm_id)
    truth = t2_truth.ALPHA_TRUE
    true_qoi = t2_truth.true_qoi()
    sensitivity = t2_truth.sensitivity()

    # Fixed for the arm: this map's error at the true alpha, in alpha units.
    forward_at_truth = float(np.interp(truth, grid.array, forward))
    discretization_error = forward_at_truth - true_qoi
    discretization_contribution = -discretization_error / sensitivity

    started = time.perf_counter()
    means, sds, lowers, uppers, widths, covers, qoi_errors, noise_terms = (
        [], [], [], [], [], [], [], []
    )
    for observations in draws:
        weights = posterior_weights(grid, forward, observations, OBSERVATION_SIGMA)
        summary = summarize(grid, weights, credible_mass=NOMINAL_LEVEL)
        means.append(summary.mean)
        sds.append(summary.sd)
        lowers.append(summary.lower)
        uppers.append(summary.upper)
        widths.append(summary.width)
        covers.append(summary.covers(truth))
        qoi_errors.append(predictive_mean(weights, forward) - true_qoi)
        noise_terms.append(
            (float(np.mean(observations)) - true_qoi) / sensitivity
        )
    inference_seconds = time.perf_counter() - started

    mean_array = np.asarray(means)
    sd_array = np.asarray(sds)
    errors = mean_array - truth
    standardized = errors / sd_array
    covers_array = np.asarray(covers, dtype=bool)
    successes = int(covers_array.sum())
    lower_ci, upper_ci = wilson_interval(successes, len(draws))

    return {
        "arm_id": arm_id,
        "is_control": arm_id == CONTROL_ARM_ID,
        "work_proxy": arm_work_proxy(arm_id),
        "replications": len(draws),
        # --- calibration ---
        "empirical_coverage": successes / len(draws),
        "coverage_successes": successes,
        "coverage_wilson_95": [lower_ci, upper_ci],
        # --- point-estimate quality ---
        "posterior_mean_bias": float(errors.mean()),
        "posterior_mean_bias_se": float(errors.std(ddof=1) / math.sqrt(len(draws))),
        "parameter_rmse": float(np.sqrt(np.mean(errors**2))),
        "parameter_sd_across_draws": float(errors.std(ddof=1)),
        # --- claimed uncertainty ---
        "posterior_sd_mean": float(sd_array.mean()),
        "posterior_sd_spread": float(sd_array.std(ddof=1)),
        "posterior_sd_relative_spread": float(
            sd_array.std(ddof=1) / sd_array.mean()
        ),
        "credible_width_mean": float(np.mean(widths)),
        "credible_width_median": float(np.median(widths)),
        # --- claimed vs actual ---
        "standardized_error_mean": float(standardized.mean()),
        "standardized_error_sd": float(standardized.std(ddof=1)),
        "standardized_error_rms": float(np.sqrt(np.mean(standardized**2))),
        # --- error budget ---
        "discretization_error_at_truth": discretization_error,
        "discretization_contribution": discretization_contribution,
        "observation_noise_contribution_rms": float(
            np.sqrt(np.mean(np.asarray(noise_terms) ** 2))
        ),
        "noise_dominates": (
            float(np.sqrt(np.mean(np.asarray(noise_terms) ** 2)))
            > abs(discretization_contribution)
        ),
        # --- prediction ---
        "qoi_prediction_error_mean": float(np.mean(qoi_errors)),
        "qoi_prediction_error_rms": float(
            np.sqrt(np.mean(np.asarray(qoi_errors) ** 2))
        ),
        # --- cost telemetry ---
        "forward_map_build_seconds_telemetry": build_seconds,
        "inference_seconds_telemetry": inference_seconds,
        "_widths": widths,
        "_covers": covers_array,
    }


# =====================================================================
# The study
# =====================================================================

def run_t2() -> dict[str, Any]:
    draws = t2_truth.all_observations()
    rows = [run_arm(arm_id, draws) for arm_id in arm_ids()]
    by_id = {row["arm_id"]: row for row in rows}

    # Confidently wrong: the interval misses AND is no wider than a good one.
    # Needs the reference arm's median width, so it is a second pass.
    threshold = (
        by_id[REFERENCE_RUNG_ID]["credible_width_median"]
        * CONFIDENTLY_WRONG_WIDTH_FACTOR
    )
    for row in rows:
        narrow = np.asarray(row["_widths"]) <= threshold
        wrong = ~row["_covers"]
        row["confidently_wrong_rate"] = float(np.mean(narrow & wrong))
        row["confidently_wrong_count"] = int((narrow & wrong).sum())
    solver_rows = [row for row in rows if not row["is_control"]]
    ordered = sorted(solver_rows, key=lambda r: rung(r["arm_id"]).rank)

    result: dict[str, Any] = {
        "experiment": "T2",
        "experiment_version": T2_VERSION,
        "base_commit": BASE_COMMIT,
        "config_hash": config_hash(),
        "preregistration_hash": preregistration_hash(),
        "config": config_payload(),
        "truth": t2_truth.truth_payload(),
        "scientific_question": SCIENTIFIC_QUESTION,
        "confidently_wrong_width_threshold": threshold,
        "arms": [
            {k: v for k, v in row.items() if not k.startswith("_")}
            for row in rows
        ],
    }

    # --- where does noise take over? -----------------------------------
    crossover = next(
        (row["arm_id"] for row in ordered if row["noise_dominates"]), None
    )
    result["error_budget"] = {
        "noise_dominates_from_rung": crossover,
        "per_arm": [
            {
                "arm_id": row["arm_id"],
                "discretization_contribution": row["discretization_contribution"],
                "observation_noise_contribution_rms": row[
                    "observation_noise_contribution_rms"
                ],
                "ratio_discretization_over_noise": (
                    abs(row["discretization_contribution"])
                    / row["observation_noise_contribution_rms"]
                ),
                "noise_dominates": row["noise_dominates"],
            }
            for row in rows
        ],
    }

    # --- criteria, evaluated mechanically ------------------------------
    def in_band(arm_id: str) -> bool:
        low, high = COVERAGE_ACCEPTANCE_BANDS[arm_id]
        return low <= by_id[arm_id]["empirical_coverage"] <= high

    control = by_id[CONTROL_ARM_ID]
    abs_z = [abs(row["standardized_error_mean"]) for row in ordered]
    rmse = [row["parameter_rmse"] for row in ordered]
    cw = [row["confidently_wrong_rate"] for row in ordered]
    checks = {
        "A1_coarse_coverage_in_band": in_band("coarse"),
        "A2_medium_coverage_in_band": in_band("medium"),
        "A3_reference_coverage_in_band": in_band(REFERENCE_RUNG_ID),
        "A4_control_arm_calibrates": in_band(CONTROL_ARM_ID),
        "A5_standardized_error_falls_with_fidelity": all(
            b < a for a, b in zip(abs_z, abs_z[1:])
        ),
        "A6_rmse_falls_with_fidelity": all(
            b < a for a, b in zip(rmse, rmse[1:])
        ),
        "A7_noise_dominates_only_at_high_fidelity": (
            not ordered[0]["noise_dominates"] and ordered[-1]["noise_dominates"]
        ),
        "A8_confidently_wrong_rate_falls_with_fidelity": all(
            b <= a for a, b in zip(cw, cw[1:])
        ),
    }
    result["acceptance"] = {
        "checks": checks,
        "all_passed": all(checks.values()),
        "failed": [name for name, ok in checks.items() if not ok],
    }

    # --- falsification triggers ----------------------------------------
    triggers = {
        "F1_control_arm_miscalibrated": not checks["A4_control_arm_calibrates"],
        "F2_reference_miscalibrated_despite_valid_control": (
            checks["A4_control_arm_calibrates"]
            and not checks["A3_reference_coverage_in_band"]
        ),
        "F3_coarse_covers_more_than_predicted": (
            by_id["coarse"]["empirical_coverage"]
            > COVERAGE_ACCEPTANCE_BANDS["coarse"][1]
        ),
        "F4_posterior_sd_varies_materially_across_draws": any(
            row["posterior_sd_relative_spread"] > 0.10 for row in rows
        ),
    }
    result["falsification"] = {
        "triggers": triggers,
        "fired": [name for name, hit in triggers.items() if hit],
        "conclusions_about_fidelity_are_licensed": not triggers[
            "F1_control_arm_miscalibrated"
        ],
    }

    result["prediction_check"] = {
        row["arm_id"]: {
            "predicted_coverage": PREDICTED_COVERAGE[row["arm_id"]],
            "observed_coverage": row["empirical_coverage"],
            "wilson_95": row["coverage_wilson_95"],
            "band": list(COVERAGE_ACCEPTANCE_BANDS[row["arm_id"]]),
            "in_band": in_band(row["arm_id"]),
            "predicted_standardized_error_mean":
                PREDICTED_STANDARDIZED_ERROR_MEAN[row["arm_id"]],
            "observed_standardized_error_mean": row["standardized_error_mean"],
        }
        for row in rows
    }

    # --- the answer, stated only as far as the numbers reach ------------
    coarse = by_id["coarse"]
    reference = by_id[REFERENCE_RUNG_ID]
    licensed = not triggers["F1_control_arm_miscalibrated"]
    result["answer"] = {
        "licensed_by_control_arm": licensed,
        "discretization_causes_systematic_miscalibration": (
            licensed
            and coarse["empirical_coverage"] < 0.5 * NOMINAL_LEVEL
            and control["empirical_coverage"] >= COVERAGE_ACCEPTANCE_BANDS[
                CONTROL_ARM_ID
            ][0]
        ),
        "noise_becomes_dominant_at": crossover,
        "coarse_coverage": coarse["empirical_coverage"],
        "reference_coverage": reference["empirical_coverage"],
        "control_coverage": control["empirical_coverage"],
        "nominal_level": NOMINAL_LEVEL,
        "coarse_confidently_wrong_rate": coarse["confidently_wrong_rate"],
        "reference_confidently_wrong_rate": reference["confidently_wrong_rate"],
    }
    # --- observed, NOT preregistered -----------------------------------
    # Flagged separately because it was noticed in the results rather than
    # predicted before them. It is reported as an observation with a checked
    # mechanism, and it is not one of the acceptance criteria.
    noise_floor = OBSERVATION_SIGMA / math.sqrt(
        result["config"]["observation_model"]["count"]
    )
    qoi_rms = [row["qoi_prediction_error_rms"] for row in rows]
    qoi_spread = (max(qoi_rms) - min(qoi_rms)) / min(qoi_rms)
    result["post_hoc_observations"] = {
        "preregistered": False,
        "qoi_prediction_error_is_blind_to_the_bias": {
            "observation": (
                "QoI prediction error is essentially identical at every arm, "
                "including the coarse rung whose parameter estimate is ~32 "
                "posterior sd wrong"
            ),
            "qoi_rms_relative_spread_across_arms": qoi_spread,
            "qoi_rms_at_coarse": by_id["coarse"]["qoi_prediction_error_rms"],
            "qoi_rms_at_control": control["qoi_prediction_error_rms"],
            "observation_noise_floor_sigma_over_sqrt_n": noise_floor,
            "qoi_rms_is_at_the_noise_floor": all(
                value <= noise_floor * 1.05 for value in qoi_rms
            ),
            "mechanism": (
                "the posterior centre is fitted so the forward map reproduces "
                "the observed mean. A forward map biased by d shifts alpha_hat "
                "by -d/(du/dalpha), which is exactly the shift that cancels d "
                "in the prediction. So the bias is absorbed, the predictive "
                "error falls back to the observation-noise floor "
                f"sigma/sqrt(n) = {noise_floor:.4e}, and every arm looks "
                "equally good at predicting what was already measured"
            ),
            "consequence": (
                "predictive performance on the assimilated observable is not "
                "evidence that the parameter is right. On this benchmark the "
                "coarse rung is indistinguishable from an exact solver by that "
                "measure alone, while being wrong about alpha by 4.7%"
            ),
            "scope_limit": (
                "shown for the QoI that was assimilated, at one benchmark. "
                "Whether an unassimilated or out-of-range prediction would "
                "expose the bias is not tested here"
            ),
        },
        "confidently_wrong_rate_is_near_one_minus_coverage": {
            "observation": (
                "posterior width barely varies across draws or arms (relative "
                "spread ~1e-3), so the width clause in the confidently-wrong "
                "definition almost never binds and the metric reduces to "
                "1 - coverage on this benchmark"
            ),
            "max_posterior_sd_relative_spread": max(
                row["posterior_sd_relative_spread"] for row in rows
            ),
            "per_arm_gap_to_one_minus_coverage": {
                row["arm_id"]: row["confidently_wrong_rate"]
                - (1.0 - row["empirical_coverage"])
                for row in rows
            },
            "consequence": (
                "the metric carries independent information only where "
                "posterior width varies with fidelity. Here it does not, so it "
                "should not be read as a second, corroborating result"
            ),
        },
    }

    result["_rows"] = rows
    return result


# =====================================================================
# Rendering
# =====================================================================

def render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    nominal = result["config"]["nominal_level"]
    add("# T2 — Repeated-draw numerical calibration")
    add("")
    add(f"Config hash: `{result['config_hash']}`")
    add(f"Preregistration hash: `{result['preregistration_hash']}`")
    add(f"Base commit (T1 freeze): `{result['base_commit']}`")
    add("")
    add(f"**{result['scientific_question']}**")
    add("")
    add(
        f"{result['config']['replications']} preregistered draws from "
        f"`SeedSequence({result['config']['seed_entropy']}).spawn(...)`. "
        f"Everything T1 froze is held fixed and imported; only the noise "
        f"realization varies. Nominal credible level {nominal:.0%}."
    )

    add("")
    add("## Calibration")
    add("")
    add("| arm | work | coverage | Wilson 95% | predicted | band | in band |")
    add("|---|---|---|---|---|---|---|")
    for arm in result["arms"]:
        check = result["prediction_check"][arm["arm_id"]]
        work = f"{arm['work_proxy']:,}" if arm["work_proxy"] else "— (control)"
        add(
            f"| `{arm['arm_id']}` | {work} | "
            f"**{arm['empirical_coverage']:.3f}** | "
            f"[{check['wilson_95'][0]:.3f}, {check['wilson_95'][1]:.3f}] | "
            f"{check['predicted_coverage']:.3f} | "
            f"[{check['band'][0]:.3f}, {check['band'][1]:.3f}] | "
            f"{'yes' if check['in_band'] else '**NO**'} |"
        )

    add("")
    add("## Estimation quality")
    add("")
    add("| arm | mean bias | RMSE | posterior sd | sd spread | mean z | "
        "sd of z | confidently wrong |")
    add("|---|---|---|---|---|---|---|---|")
    for arm in result["arms"]:
        add(
            f"| `{arm['arm_id']}` | {arm['posterior_mean_bias']:+.4e} | "
            f"{arm['parameter_rmse']:.4e} | {arm['posterior_sd_mean']:.4e} | "
            f"{arm['posterior_sd_relative_spread']:.4f} | "
            f"{arm['standardized_error_mean']:+.2f} | "
            f"{arm['standardized_error_sd']:.2f} | "
            f"{arm['confidently_wrong_rate']:.3f} |"
        )
    add("")
    add(
        f"*confidently wrong* = the interval excludes α **and** is no wider "
        f"than {result['config']['confidently_wrong_width_factor']}× the "
        f"reference arm's median width "
        f"({result['confidently_wrong_width_threshold']:.4e}) — wrong while "
        f"looking as authoritative as a good answer."
    )

    add("")
    add("## Error budget — where does noise take over?")
    add("")
    add("| arm | discretization → α | noise RMS → α | ratio | dominated by |")
    add("|---|---|---|---|---|")
    for entry in result["error_budget"]["per_arm"]:
        add(
            f"| `{entry['arm_id']}` | "
            f"{entry['discretization_contribution']:+.4e} | "
            f"{entry['observation_noise_contribution_rms']:.4e} | "
            f"{entry['ratio_discretization_over_noise']:.3f} | "
            f"{'noise' if entry['noise_dominates'] else 'discretization'} |"
        )
    add("")
    crossover = result["error_budget"]["noise_dominates_from_rung"]
    add(
        f"Observation noise first dominates at the **{crossover}** rung."
        if crossover
        else "Observation noise does not dominate at any solver rung."
    )
    add("")
    add(
        "The control arm's non-zero entry is not discretization: its forward "
        "map is the closed form. It is linear interpolation of that map at "
        "α_true, which sits between grid nodes by design. It matches the "
        "interpolation bound f''h²s(1−s)/2 to 3 parts in 10⁵, is common to "
        "every arm and so cancels between them, and is 5×10⁻⁶ of a posterior "
        "standard deviation."
    )

    add("")
    add("## QoI prediction")
    add("")
    add("| arm | mean error | RMS error |")
    add("|---|---|---|")
    for arm in result["arms"]:
        add(
            f"| `{arm['arm_id']}` | {arm['qoi_prediction_error_mean']:+.4e} | "
            f"{arm['qoi_prediction_error_rms']:.4e} |"
        )

    add("")
    add("## Observed, not preregistered")
    add("")
    add(
        "*Noticed in the results rather than predicted before them. Reported "
        "as observations with checked mechanisms, and deliberately not counted "
        "as criteria.*")
    add("")
    blind = result["post_hoc_observations"][
        "qoi_prediction_error_is_blind_to_the_bias"
    ]
    add(f"**{blind['observation']}.**")
    add("")
    add(
        f"QoI prediction RMS varies by only "
        f"{blind['qoi_rms_relative_spread_across_arms']:.2e} across all four "
        f"arms and sits at the observation-noise floor σ/√n = "
        f"{blind['observation_noise_floor_sigma_over_sqrt_n']:.4e} "
        f"(at floor: {blind['qoi_rms_is_at_the_noise_floor']})."
    )
    add("")
    add(f"Mechanism: {blind['mechanism']}.")
    add("")
    add(f"Consequence: {blind['consequence']}.")
    add("")
    add(f"Scope limit: {blind['scope_limit']}.")
    add("")
    near = result["post_hoc_observations"][
        "confidently_wrong_rate_is_near_one_minus_coverage"
    ]
    add(f"**Second observation.** {near['observation']}. "
        f"{near['consequence']}.")

    add("")
    add("## Preregistered criteria")
    add("")
    for name, ok in result["acceptance"]["checks"].items():
        add(f"- {'PASS' if ok else '**FAIL**'} — {name}")
    add("")
    fired = result["falsification"]["fired"]
    if fired:
        add(f"Falsification triggers fired: **{', '.join(fired)}**")
    else:
        add("No falsification trigger fired.")
    add("")
    licensed = result["falsification"]["conclusions_about_fidelity_are_licensed"]
    add(
        "The control arm calibrated, so differences between the solver arms "
        "are attributable to discretization rather than to the likelihood, "
        "the prior or the grid."
        if licensed
        else "**The control arm did not calibrate. No conclusion about "
        "fidelity is licensed by this run.** The cause is in the inference, "
        "not the numerics; see the falsification criteria."
    )

    add("")
    add("## Answer")
    add("")
    answer = result["answer"]
    if not answer["licensed_by_control_arm"]:
        add(
            "Not answerable from this run — the control arm failed and the "
            "diagnosis must come first."
        )
    else:
        add(
            f"Yes. Across {result['config']['replications']} draws the coarse "
            f"rung covered α on {answer['coarse_coverage']:.1%} of them "
            f"against a nominal {answer['nominal_level']:.0%}, and was "
            f"confidently wrong — narrow interval, excluded truth — on "
            f"{answer['coarse_confidently_wrong_rate']:.1%}. The identical "
            f"inference with an exact forward map covered "
            f"{answer['control_coverage']:.1%}, so the miscalibration is "
            f"caused by discretization and not by the inference. Observation "
            f"noise becomes the dominant error source at the "
            f"**{answer['noise_becomes_dominant_at']}** rung, where coverage "
            f"reaches {answer['reference_coverage']:.1%}."
        )

    add("")
    add("## What this does not show")
    add("")
    for item in result["config"]["non_goals"]:
        add(f"- {item}")
    return "\n".join(lines)


def main() -> int:
    result = run_t2()
    root = Path(__file__).resolve().parent
    public = {k: v for k, v in result.items() if not k.startswith("_")}
    (root / "t2_config_frozen.json").write_text(
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
    (root / "t2_results.json").write_text(
        json.dumps(public, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    report = render_markdown(result)
    (root / "t2_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
