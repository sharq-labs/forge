"""1D transient conduction — a time-dependent PDE domain on the frozen contracts.

The second scientific domain. It exists to answer one question: can a genuine
time-dependent PDE satisfy the existing ``ScientificSolver`` contract and earn a
defensible verification result without changing SRIA core architecture?

    du/dt = alpha d2u/dx2        x in [0, L]
    u(0,t) = u(L,t) = 0
    u(x,0) = sin(pi x / L)

``u`` is a NORMALIZED DIMENSIONLESS field. It is never reported as kelvin: no
absolute scale, no reference state and no material are claimed anywhere in this
package.

WHAT THIS DOMAIN ADDS THAT ELECTRICAL COULD NOT
------------------------------------------------
Electrical DC is a direct linear solve whose numerical error sits at 1e-16 —
negligible against any observation noise by fourteen orders of magnitude, so
convergence was ``NOT_APPLICABLE`` and ``ANALYTICALLY_VERIFIED`` was correctly
declined. Here the discretization error is real, controllable and large enough
to matter, so the domain can support a refinement study, an independent
closed-form comparison, and a fidelity/cost trade — none of which the first
domain had anything to exercise.

Module roles:

    problem.py     slab and discretization declarations, the diffusion model,
                   the domain capability, and the universal problem statement
    reference.py   the closed-form solution — verification side only, and it
                   never imports the solver
    solver.py      Conduction1DSolver (the five-stage lifecycle) and the
                   solve_slab wrapper
    validation.py  per-solve checks, and separately the refinement gate that
                   is the only thing allowed to award NUMERICALLY_CONVERGED or
                   ANALYTICALLY_VERIFIED

THE PUBLIC SURFACE IS DELIBERATELY SMALL
-----------------------------------------
``__all__`` is what a *consumer of this domain* needs: declare a slab, build a
problem, solve it, read the metrics, run the verification gate, catch the
errors. Everything else — the assembled system, the assembly routine, the
per-solve report builder, the problem/slab integrity check, the capability
helper, the reference's own identity constants — is an implementation detail
and is reachable from its own module when a white-box test genuinely needs it.

Re-exporting internals would make every one of them a compatibility promise,
which is a cost paid forever for a convenience used once.
"""

from __future__ import annotations

from .errors import (
    SlabBindingError,
    SlabConfigurationError,
    ThermalConduction1DError,
)
from .problem import (
    CONDUCTION_MODELS,
    DIFFUSION_MODEL,
    DIFFUSIVITY_UNIT,
    FIELD_UNIT,
    LEFT_METRIC,
    LENGTH_UNIT,
    MAX_METRIC,
    MIDPOINT_METRIC,
    RIGHT_METRIC,
    THERMAL_CONDUCTION_1D,
    TIME_UNIT,
    ConductionSlab,
    SlabDiscretization,
    build_conduction_problem,
)
from .reference import decay_factor, exact_field, exact_midpoint
from .solver import (
    BACKEND,
    SOLVER_ID,
    SOLVER_VERSION,
    Conduction1DSolver,
    solve_slab,
)
from .validation import (
    ANALYTIC_REL_TOL,
    CONVERGENCE_MIN_CONTRACTION,
    MIN_RUNGS,
    VERIFICATION_LADDER,
    ConductionValidationSettings,
    RefinementRung,
    VerificationReport,
    run_verification_gate,
)

__all__ = [
    # declarations
    "ConductionSlab",
    "SlabDiscretization",
    # problem statement
    "build_conduction_problem",
    "CONDUCTION_MODELS",
    "DIFFUSION_MODEL",
    "THERMAL_CONDUCTION_1D",
    # solving
    "Conduction1DSolver",
    "solve_slab",
    "SOLVER_ID",
    "SOLVER_VERSION",
    "BACKEND",
    # the closed-form reference
    "decay_factor",
    "exact_field",
    "exact_midpoint",
    # verification
    "run_verification_gate",
    "VerificationReport",
    "RefinementRung",
    "VERIFICATION_LADDER",
    "ANALYTIC_REL_TOL",
    "CONVERGENCE_MIN_CONTRACTION",
    "MIN_RUNGS",
    "ConductionValidationSettings",
    # metric names and units
    "MIDPOINT_METRIC",
    "MAX_METRIC",
    "LEFT_METRIC",
    "RIGHT_METRIC",
    "FIELD_UNIT",
    "LENGTH_UNIT",
    "TIME_UNIT",
    "DIFFUSIVITY_UNIT",
    # errors
    "ThermalConduction1DError",
    "SlabConfigurationError",
    "SlabBindingError",
]
