"""T2 hidden truth — GRADER ONLY.

**No decision-path module may import this**, enforced by an AST test.

The truth is T1's truth, imported rather than restated: same alpha_true, same
exact QoI, same sensitivity, same closed-form reference. T2 adds exactly one
thing — repeated draws from the same declared observation model.

WHY THE DRAWS LIVE HERE AND NOT IN THE CONFIG
----------------------------------------------
Which replications happen, and from which seeds, is part of the preregistered
design and lives in :mod:`t2_config`. What those draws contain depends on
alpha_true and therefore belongs on the grader side. The split is the same one
T1 made, and it is what lets an AST test prove the inference never saw the
answer.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from experiments.thermal_t1.t1_truth import ALPHA_TRUE, sensitivity, true_qoi

from .t2_config import (
    OBSERVATION_COUNT,
    OBSERVATION_SIGMA,
    REPLICATIONS,
    seed_sequences,
)

__all__ = [
    "ALPHA_TRUE",
    "sensitivity",
    "true_qoi",
    "replication_observations",
    "all_observations",
    "truth_payload",
    "truth_hash",
]


def replication_observations(index: int) -> tuple[float, ...]:
    """The OBSERVATION_COUNT measurements for one replication.

    Centred on the exact solution at alpha_true, never on a solve: every arm is
    compared against the same truth, so "discretization error" means the same
    thing for all of them. That is T1's rule, unchanged.
    """
    if not 0 <= index < REPLICATIONS:
        raise IndexError(
            f"replication {index} is outside the preregistered "
            f"{REPLICATIONS} draws"
        )
    rng = np.random.default_rng(seed_sequences()[index])
    centre = true_qoi()
    return tuple(
        float(centre + rng.normal(0.0, OBSERVATION_SIGMA))
        for _ in range(OBSERVATION_COUNT)
    )


def all_observations() -> tuple[tuple[float, ...], ...]:
    """Every replication's draw, generated once and reused by every arm.

    Reused across arms for the same reason T1 reused one draw across rungs: if
    each arm saw different noise, a difference between arms could be noise
    rather than discretization, and the experiment would answer nothing.
    """
    return tuple(replication_observations(i) for i in range(REPLICATIONS))


def truth_payload() -> dict[str, Any]:
    draws = all_observations()
    flat = np.asarray(draws, dtype=np.float64)
    return {
        "alpha_true": ALPHA_TRUE,
        "true_qoi": true_qoi(),
        "sensitivity_du_dalpha": sensitivity(),
        "replications": REPLICATIONS,
        "observations_per_replication": OBSERVATION_COUNT,
        "draw_mean": float(flat.mean()),
        "draw_sd": float(flat.std(ddof=1)),
        "declared_sigma": OBSERVATION_SIGMA,
        "truth_source": "exact analytic solution + declared Gaussian noise",
        "scope": (
            "synthetic hidden truth with a known alpha; no physical validation "
            "and no real measurement is involved"
        ),
        "note": (
            "the full draw table is not inlined here; draw_mean and draw_sd "
            "summarize it and the seed rule reproduces it exactly"
        ),
    }


def truth_hash() -> str:
    """Covers every drawn value, not just the summary."""
    blob = json.dumps(
        {
            "summary": truth_payload(),
            "draws": [list(draw) for draw in all_observations()],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
