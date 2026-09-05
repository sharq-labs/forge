"""The confirmatory stress case. Declared before it was run.

VERIFICATION METHODOLOGY, NOT A RUNTIME CAPABILITY
---------------------------------------------------
This lives under ``tests/`` on purpose. It is a record of how the thermal
verification gate was checked, not something the thermal solver does. The
production domain has no dependency on it and must never acquire one: a
runtime import of this module would turn a one-off methodological artifact
into API that later code could come to rely on.

WHY IT EXISTS
-------------
``CONVERGENCE_MIN_CONTRACTION`` and ``ANALYTIC_REL_TOL`` were declared after an
exploratory calculation had already shown roughly where this method lands on
the nominal benchmark. They were not preregistered. Passing a gate on the case
that informed it is weak evidence, so the gate needs one case it was not chosen
from — that is this one.

The gates are frozen. Nothing here may change them, and if this case fails, the
correct response is to report the failure, not to widen a threshold.

WHAT CHANGES, AND WHAT DOES NOT
--------------------------------
Exactly one physical parameter: the diffusivity. Everything else is the nominal
benchmark unchanged — same PDE, same boundary and initial conditions, same slab
length, same end time, same backward-Euler/central-difference method, same
seven-rung ladder, same verification code, same two gates.

    alpha:  1.2e-5  ->  1.8e-5 m^2/s      (a 50% increase)

WHY THIS VALUE, AND WHY THIS DIRECTION
---------------------------------------
This choice needs justifying carefully, because the honest failure mode here is
picking whichever direction is known to pass.

For this single-mode benchmark the whole solution is ``exp(-lambda t)`` with
``lambda = alpha pi^2 / L^2``, so the dimensionless decay ``lambda*t_end`` is
the one number that characterises the regime. Backward Euler over ``N`` steps
gives a relative error in the decay factor of approximately

    rel_error  ~  (lambda*t_end)^2 / (2N)

which reproduces the nominal case closely: ``lambda*t_end = 0.7106`` and
``N = 640`` predict 3.95e-4 against an observed 3.965e-4.

That model says the error grows as the SQUARE of the decay, so raising alpha is
the direction that stresses the fixed ladder and lowering it is the direction
that makes the gate easy. Having derived which way is which, choosing the easy
direction would be precisely the self-serving move this case exists to rule
out. So the harder direction is taken.

At alpha = 1.8e-5 the decay becomes ``lambda*t_end = 1.0660`` and the model
predicts a finest relative error near 8.9e-4 against the frozen 1e-3 tolerance
— a margin of roughly 1.1x. That is deliberately tight. It is a real test of
whether the declared gate transfers, and it can genuinely fail.

This is a PREDECLARED CONFIRMATORY STRESS CASE on the same computational
benchmark. It is not independent physical validation, and no measurement of
anything physical is involved.

DECLARED LIMIT OF THE REGIME
----------------------------
The same model says a fixed seven-rung ladder cannot hold a 1e-3 tolerance for
arbitrarily large decay: it is exceeded once ``lambda*t_end`` passes about 1.13.
That is a property of the LADDER, not of the method — a longer ladder would
recover it — and it is recorded here so the gate is never quoted as if it held
for every regime. The nominal case and this stress case both sit below that
bound; neither establishes anything above it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.engcore.domains.thermal.conduction1d import (
    ConductionSlab,
    SlabDiscretization,
)
from src.engcore.scientific.units.quantity import Quantity

# --- the nominal case, for reference -----------------------------------------
NOMINAL_ALPHA_M2_S = 1.2e-5

# --- the stress-case declaration ---------------------------------------------
HOLDOUT_ID = "thermal.conduction1d.holdout.alpha_1p8e-5"
HOLDOUT_VERSION = "1.0.0"

#: The single changed parameter.
HOLDOUT_ALPHA_M2_S = 1.8e-5

#: Unchanged from the nominal benchmark.
HOLDOUT_LENGTH_M = 0.1
HOLDOUT_END_TIME_S = 60.0
HOLDOUT_CHANGED_PARAMETER = "diffusivity"

#: Predicted from the error model above, recorded BEFORE execution so the
#: result can be checked against a stated expectation rather than explained
#: afterwards.
PREDICTED_DECAY = 1.0660
PREDICTED_FINEST_REL_ERROR = 8.9e-4
PREDICTED_OUTCOME = "expected to pass, with a margin near 1.1x"

#: Above this decay a seven-rung ladder cannot hold a 1e-3 tolerance. Declared
#: so the gate is never quoted outside the regime it was demonstrated in.
DECLARED_REGIME_MAX_DECAY = 1.13


def holdout_slab(n_cells: int = 64, n_steps: int = 80) -> ConductionSlab:
    """The stress-case benchmark. Discretization is supplied by the ladder."""
    return ConductionSlab(
        slab_id="holdout-alpha-1p8e-5",
        length=Quantity(HOLDOUT_LENGTH_M, "meter"),
        diffusivity=Quantity(HOLDOUT_ALPHA_M2_S, "m**2/s"),
        end_time=Quantity(HOLDOUT_END_TIME_S, "second"),
        discretization=SlabDiscretization(n_cells, n_steps),
    )


def holdout_declaration() -> dict[str, Any]:
    """Everything fixed before the stress case ran."""
    from src.engcore.domains.thermal.conduction1d import (
        ANALYTIC_REL_TOL,
        CONVERGENCE_MIN_CONTRACTION,
        MIN_RUNGS,
        VERIFICATION_LADDER,
    )

    return {
        "holdout_id": HOLDOUT_ID,
        "holdout_version": HOLDOUT_VERSION,
        "changed_parameter": HOLDOUT_CHANGED_PARAMETER,
        "nominal_alpha_m2_s": NOMINAL_ALPHA_M2_S,
        "holdout_alpha_m2_s": HOLDOUT_ALPHA_M2_S,
        "unchanged": {
            "length_m": HOLDOUT_LENGTH_M,
            "end_time_s": HOLDOUT_END_TIME_S,
            "pde": "du/dt = alpha d2u/dx2",
            "boundary_conditions": "u(0,t) = u(L,t) = 0",
            "initial_condition": "u(x,0) = sin(pi x / L)",
            "method": "backward Euler + 2nd-order central differences",
            "ladder": [[r.n_cells, r.n_steps] for r in VERIFICATION_LADDER],
        },
        "frozen_gates": {
            "analytic_rel_tol": ANALYTIC_REL_TOL,
            "convergence_min_contraction": CONVERGENCE_MIN_CONTRACTION,
            "min_rungs": MIN_RUNGS,
            "status": (
                "declared after exploratory feasibility analysis on the "
                "nominal case; frozen and not retuned for this holdout"
            ),
        },
        "prediction_before_execution": {
            "decay_lambda_t": PREDICTED_DECAY,
            "finest_rel_error": PREDICTED_FINEST_REL_ERROR,
            "outcome": PREDICTED_OUTCOME,
            "error_model": "rel_error ~ (lambda*t_end)^2 / (2N)",
            "direction_rationale": (
                "alpha was RAISED because the error model shows error grows as "
                "the square of the decay; this is the direction that stresses "
                "the fixed ladder, and lowering alpha would have been the "
                "direction known in advance to pass easily"
            ),
        },
        "declared_regime_max_decay": DECLARED_REGIME_MAX_DECAY,
    }


def holdout_config_hash() -> str:
    """SHA-256 over the declaration. Computed before the stress case was run."""
    blob = json.dumps(
        holdout_declaration(), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
