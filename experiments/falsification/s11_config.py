"""S1.1 — pre-registered configuration for the transport-guard sweep.

Frozen BEFORE any scored run. The hash of :func:`config_payload` is written
into every result artifact, so a scored run can always be traced to the exact
configuration that produced it.

If a defect invalidates a run, the rule is: document the defect, invalidate the
run, fix it, and start a new explicitly versioned experiment. These values are
not adjusted to improve results.

Design notes worth stating up front, because they bound what the sweep can
mean:

* Every truth family agrees **exactly** on the observed region ``x <= 8``.
  The correction term is ``max(0, x - 8)``-based, so at every observation it is
  identically zero. All families therefore produce identical observations for a
  given seed, which is what makes the no-leakage property structural rather
  than incidental: the posterior is a function of the seed alone.
* The decision threshold is placed a fixed ``THRESHOLD_OFFSET`` below the
  nominal linear response at ``x*``. Under the assumed model the answer is
  therefore "above" with high confidence at every ``x*``; whether that is
  *correct* depends only on whether the hidden correction at ``x*`` exceeds the
  offset. This isolates the effect under study — model error outside support —
  from every other source of difficulty.
* In 1-D with a fixed observation set, the support rule reduces to a distance
  threshold. The sweep therefore measures the cost of choosing how far to trust
  extrapolation; it cannot say anything about support geometry in general.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

EXPERIMENT_ID = "S1.1"
EXPERIMENT_NAME = "transport_guard_calibration"
EXPERIMENT_VERSION = "1.0.0"
BASE_COMMIT = "061ee7e75f715db3eec4d592063ba171157af545"

# --- model space and inference ----------------------------------------------
GRID_A_RANGE = (0.5, 1.5)
GRID_A_POINTS = 121
GRID_B_RANGE = (0.40, 0.60)
GRID_B_POINTS = 121
PRIOR = "uniform"

# --- observations ------------------------------------------------------------
OBSERVATION_XS = tuple(float(x) for x in range(9))       # 0..8
OBSERVATION_SIGMA = 0.05
#: Frozen replication seeds. Contiguous and declared here, not chosen later.
SEEDS = tuple(range(20260801, 20260801 + 50))            # 50 replications

# --- terminal decision -------------------------------------------------------
#: tau(x*) = NOMINAL_INTERCEPT + NOMINAL_SLOPE * x* - THRESHOLD_OFFSET
NOMINAL_INTERCEPT = 1.0
NOMINAL_SLOPE = 0.5
THRESHOLD_OFFSET = 0.30
LOSS_A_ABOVE = 0.0
LOSS_A_BELOW = 10.0
LOSS_B_ABOVE = 1.0
LOSS_B_BELOW = 0.0

# --- terminal condition sweep ------------------------------------------------
#: 2/4/6/8 are clearly inside support; 8.5 sits on the boundary; 9/9.5/10 are
#: modest extrapolation; 11/12 are farther. Four in-domain points are included
#: deliberately so the cost of the guard can be estimated, not just its benefit.
X_STAR_GRID = (2.0, 4.0, 6.0, 8.0, 8.5, 9.0, 9.5, 10.0, 11.0, 12.0)

# --- support margin sweep ----------------------------------------------------
#: ``None`` disables the guard entirely (the S1 naive policy).
MARGIN_POLICIES = (
    ("very_strict", 0.0),
    ("strict", 0.5),
    ("moderate", 1.5),
    ("permissive", 3.0),
    ("no_guard", None),
)

# --- acquisition -------------------------------------------------------------
EXPENSIVE_COST = 0.5      # measuring at the terminal condition
CHEAP_COST = 0.01         # measuring inside the observed region
CHEAP_ACTION_X = 8.0

# --- truth families (grader only; see s11_truths.py) -------------------------
#: (family_id, class) where class is BENIGN or REGIME_CHANGE.
TRUTH_FAMILIES = (
    ("linear_exact", "BENIGN"),
    ("mild_quadratic", "BENIGN"),
    ("mild_kink", "BENIGN"),
    ("regime_moderate", "REGIME_CHANGE"),
    ("regime_strong", "REGIME_CHANGE"),
    ("regime_step", "REGIME_CHANGE"),
)
TRUTH_BREAK_POINT = 8.0

# --- quadrature --------------------------------------------------------------
Y_NODES = 121
Y_SPAN_SIGMAS = 7.0

#: Rates are conditional on this mixture. Three benign and three regime-change
#: families are weighted equally; no claim is made that this reflects any real
#: prior over how often models fail outside their support.
TRUTH_FAMILY_WEIGHTING = "uniform over the six declared families"


def config_payload() -> dict[str, Any]:
    """The frozen configuration, in a canonical form suitable for hashing."""
    return {
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "experiment_version": EXPERIMENT_VERSION,
        "base_commit": BASE_COMMIT,
        "model_grid": {
            "a_range": list(GRID_A_RANGE),
            "a_points": GRID_A_POINTS,
            "b_range": list(GRID_B_RANGE),
            "b_points": GRID_B_POINTS,
            "prior": PRIOR,
        },
        "observations": {
            "xs": list(OBSERVATION_XS),
            "sigma": OBSERVATION_SIGMA,
            "seeds": list(SEEDS),
            "replications": len(SEEDS),
        },
        "terminal_decision": {
            "threshold_rule": (
                "tau(x*) = 1.0 + 0.5*x* - 0.30 (nominal response minus offset)"
            ),
            "nominal_intercept": NOMINAL_INTERCEPT,
            "nominal_slope": NOMINAL_SLOPE,
            "threshold_offset": THRESHOLD_OFFSET,
            "loss": {
                "A_above": LOSS_A_ABOVE,
                "A_below": LOSS_A_BELOW,
                "B_above": LOSS_B_ABOVE,
                "B_below": LOSS_B_BELOW,
            },
        },
        "x_star_grid": list(X_STAR_GRID),
        "margin_policies": [
            {"name": name, "margin": margin} for name, margin in MARGIN_POLICIES
        ],
        "acquisition": {
            "expensive_cost": EXPENSIVE_COST,
            "cheap_cost": CHEAP_COST,
            "cheap_action_x": CHEAP_ACTION_X,
        },
        "truth_families": [
            {"family_id": fid, "class": cls} for fid, cls in TRUTH_FAMILIES
        ],
        "truth_break_point": TRUTH_BREAK_POINT,
        "truth_family_weighting": TRUTH_FAMILY_WEIGHTING,
        "quadrature": {"y_nodes": Y_NODES, "y_span_sigmas": Y_SPAN_SIGMAS},
        "classification_rules": {
            "NOT_APPLICABLE_CONTINUE": (
                "the decision-theoretic condition itself said continue, so no "
                "certification was sought under either policy; excluded from "
                "the confusion matrix and reported separately"
            ),
            "GOOD_ALLOW": "certification allowed and the decision is correct",
            "GOOD_BLOCK": (
                "naive stopping would have certified a wrong decision and the "
                "guard blocked it"
            ),
            "FALSE_REFUSAL": (
                "the decision is correct but the guard blocked certification"
            ),
            "DANGEROUS_MISS": (
                "the decision is wrong and the guard allowed certification"
            ),
        },
        "primary_metrics": {
            "dangerous_miss_rate": (
                "DANGEROUS_MISS / (DANGEROUS_MISS + GOOD_BLOCK); denominator is "
                "cases where certification would be scientifically wrong"
            ),
            "false_refusal_rate": (
                "FALSE_REFUSAL / (FALSE_REFUSAL + GOOD_ALLOW); denominator is "
                "cases where certification would be correct"
            ),
            "good_block_rate": "GOOD_BLOCK / (DANGEROUS_MISS + GOOD_BLOCK)",
            "good_allow_rate": "GOOD_ALLOW / (FALSE_REFUSAL + GOOD_ALLOW)",
            "naive_wrong_stop_rate": (
                "(DANGEROUS_MISS + GOOD_BLOCK) / all classified cases; the "
                "danger that existed before any guard"
            ),
        },
    }


def config_hash() -> str:
    blob = json.dumps(config_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def threshold_for(x_star: float) -> float:
    """The predeclared decision threshold at a terminal condition."""
    return NOMINAL_INTERCEPT + NOMINAL_SLOPE * float(x_star) - THRESHOLD_OFFSET


def scored_case_count() -> int:
    return (
        len(TRUTH_FAMILIES)
        * len(X_STAR_GRID)
        * len(SEEDS)
        * len(MARGIN_POLICIES)
    )
