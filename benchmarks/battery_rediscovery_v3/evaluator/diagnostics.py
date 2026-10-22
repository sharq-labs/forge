"""Preregistered degeneracy diagnostics of battery_rediscovery_v3 (frozen in PLAN.json; computed after the seal).

v2's Q1 optimum was physically degenerate (R1 on its 1 ohm bound, tau ~5200 s) while its predictive fit looked fine.
v3 therefore records, per problem, four INDEPENDENT evidence dimensions that are never collapsed into one score and
never change an axis truth:

* ``FIT_OK``: YES iff reference A's best start converged (status > 0) and the A and B optimal costs agree within
  ``FIT_AGREE_REL`` (relative).  A good fit is a precondition for reading the other dimensions.
* ``PARAMETER_DEGENERACY`` (the fitted point), flags:
  - ``PINNED_TO_BOUND:<p>``: a requested parameter within a factor ``1 + PINNED_REL`` of a declared bound (reference B);
  - ``TAU_EXCEEDS_HORIZON``: tau = R1 C1 longer than the longest calibration trajectory;
  - ``TAU_BELOW_SAMPLING``: tau shorter than the median calibration sampling interval;
  - ``EQUIVALENT_TAU_SET``: B's profile cost stays within 1 % of its minimum over more than ``FLAT_SPAN_LN`` (one decade)
    of ln tau, i.e. materially equivalent parameter sets;
  - ``MULTISTART_INSTABILITY``: a reference-A start within ``MULTISTART_REL`` of the best cost has a requested parameter
    more than ln(1.5) away (perturbation instability).
  ``unconstrained_nuisance`` lists parameters no scored sample depends on (e.g. an OCV knot outside the data).
* ``IDENTIFIABILITY_LIMIT`` (the information), flags: ``NEAR_STRUCTURAL`` (B), ``SINGULAR_INFORMATION`` (the constrained
  parameters' information is singular), ``REQUESTED_UNCONSTRAINED``, ``ILL_CONDITIONED`` (correlation-matrix condition
  number of the requested block of inv(J^T J) above the canonical 1e6) and ``HIGH_CORRELATION`` (|rho| above the canonical
  0.95).  These are sigma-free.  Value YES if any flag; else ``NOT_ESTABLISHED_NO_SIGMA`` when no noise is declared (a
  limit cannot be ruled out), else NO.
* ``MODEL_DISCREPANCY``: the problem's MODEL_DISCREPANCY truth (SUPPORTED / NOT_SUPPORTED / NOT_ASSESSABLE / None).

``candidate_degeneracy`` applies the pinned-bound and tau rules to the combined arm's own sealed parameter set, so a
candidate SUPPORTED answer on a degenerate fit is visible in the report (``DEGENERATE_SUPPORT``), never silently erased.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from engcore.hybrid_uq.identifiability import CANONICAL_IDENTIFIABILITY_THRESHOLDS

PINNED_REL = 0.01
FLAT_SPAN_LN = math.log(10.0)
FIT_AGREE_REL = 1e-3
MULTISTART_REL = 1e-3
MULTISTART_LN = math.log(1.5)
CONDITION_MAX = CANONICAL_IDENTIFIABILITY_THRESHOLDS["condition_threshold"]
CORRELATION_MAX = CANONICAL_IDENTIFIABILITY_THRESHOLDS["correlation_threshold"]
THRESHOLDS = {"PINNED_REL": PINNED_REL, "FLAT_SPAN_LN": FLAT_SPAN_LN, "FIT_AGREE_REL": FIT_AGREE_REL,
              "MULTISTART_REL": MULTISTART_REL, "MULTISTART_LN": MULTISTART_LN, "CONDITION_MAX": CONDITION_MAX,
              "CORRELATION_MAX": CORRELATION_MAX}


def _pinned(name: str, value: float, lo: float, hi: float) -> bool:
    return value <= lo * (1.0 + PINNED_REL) or value >= hi / (1.0 + PINNED_REL)


def _tau_flags(tau: float, horizon_s: float, median_dt_s: float) -> list[str]:
    out = []
    if tau > horizon_s:
        out.append("TAU_EXCEEDS_HORIZON")
    if tau < median_dt_s:
        out.append("TAU_BELOW_SAMPLING")
    return out


def evidence_dimensions(a: Mapping[str, Any], b: Mapping[str, Any], truth: Mapping[str, Mapping[str, Any]], *,
                        requested: Sequence[str]) -> dict[str, Any]:
    """``a``: reference-A summary (cost, parameters, best_status, starts_detail); ``b``: reference-B diagnostics."""
    b_cost = 0.5 * float(b["sse"])
    a_cost = float(a["cost"])
    rel = abs(a_cost - b_cost) / max(a_cost, b_cost, 1e-300)
    fit_ok = a.get("best_status", 1) > 0 and rel <= FIT_AGREE_REL
    flags = [f"PINNED_TO_BOUND:{n}" for n in requested if _pinned(n, b["parameters"][n], *b["bounds"][n])]
    flags += _tau_flags(float(b["tau"]), float(b["horizon_s"]), float(b["median_dt_s"]))
    if float(b["profile"]["ln_tau_span_within_1pct"]) > FLAT_SPAN_LN:
        flags.append("EQUIVALENT_TAU_SET")
    best = a_cost
    for s in a.get("starts_detail", ()):
        if s["cost"] - best <= MULTISTART_REL * best and any(
                abs(math.log(s["final"][n]) - math.log(a["parameters"][n])) > MULTISTART_LN for n in requested):
            flags.append("MULTISTART_INSTABILITY")
            break
    info = b["information"]
    lim = []
    if truth.get("IDENTIFIABILITY", {}).get("near_structural") or b.get("near_structural"):
        lim.append("NEAR_STRUCTURAL")
    if info.get("reduced_singular"):
        lim.append("SINGULAR_INFORMATION")
    if info.get("requested_unconstrained"):
        lim.append("REQUESTED_UNCONSTRAINED")
    cond, corr = info.get("condition_number"), info.get("max_abs_correlation")
    if cond is None and not info.get("reduced_singular") and not info.get("requested_unconstrained"):
        lim.append("ILL_CONDITIONED")  # infinite condition number serialised as null
    elif cond is not None and cond > CONDITION_MAX:
        lim.append("ILL_CONDITIONED")
    if corr is not None and corr > CORRELATION_MAX:
        lim.append("HIGH_CORRELATION")
    sigma_declared = truth.get("IDENTIFIABILITY", {}).get("sigma") is not None
    lim_value = "YES" if lim else ("NO" if sigma_declared else "NOT_ESTABLISHED_NO_SIGMA")
    return {"FIT_OK": {"value": "YES" if fit_ok else "NO", "a_cost": a_cost, "b_cost": b_cost, "relative_difference": rel,
                       "a_best_status": a.get("best_status")},
            "PARAMETER_DEGENERACY": {"value": "YES" if flags else "NO", "flags": flags,
                                     "unconstrained_nuisance": [n for n in info.get("unconstrained", []) if n not in requested],
                                     "tau_s": float(b["tau"]), "horizon_s": float(b["horizon_s"]),
                                     "parameters": {n: b["parameters"][n] for n in requested}},
            "IDENTIFIABILITY_LIMIT": {"value": lim_value, "flags": lim, "condition_number": cond,
                                      "max_abs_correlation": corr},
            "MODEL_DISCREPANCY": {"value": truth.get("MODEL_DISCREPANCY", {}).get("truth")}}


def candidate_degeneracy(parameter_set: Sequence[Mapping[str, Any]] | None, *, horizon_s: float,
                         median_dt_s: float, requested: Sequence[str] = ("R0", "R1", "C1")) -> dict[str, Any]:
    if not parameter_set:
        return {"value": "NOT_AVAILABLE", "flags": []}
    p = {e["name"]: e for e in parameter_set}
    if any(n not in p or p[n].get("estimate") is None for n in requested):
        return {"value": "NOT_AVAILABLE", "flags": []}
    flags = [f"PINNED_TO_BOUND:{n}" for n in requested
             if _pinned(n, float(p[n]["estimate"]), float(p[n]["low"]), float(p[n]["high"]))]
    if "R1" in p and "C1" in p:
        flags += _tau_flags(float(p["R1"]["estimate"]) * float(p["C1"]["estimate"]), horizon_s, median_dt_s)
    return {"value": "YES" if flags else "NO", "flags": flags}


__all__ = ["THRESHOLDS", "candidate_degeneracy", "evidence_dimensions"]
