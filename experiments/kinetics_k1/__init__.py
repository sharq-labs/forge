"""K1 — Kinetics/CSTR solver admission gate.

THE QUESTION
------------
Can the frozen Core V0.2 contracts honestly represent and execute a stiff,
nonlinear, failure-prone kinetics solver — including its failures — without
speculative Core expansion?

This is a DOMAIN ADMISSION experiment, not a chemistry milestone. Nothing here
infers a parameter, selects an experiment, or optimizes anything. The reactor
exists to put pressure on the contracts, and the result of interest is what the
contracts did under that pressure.

WHAT KIND OF PREREGISTRATION THIS IS — READ THIS FIRST
-------------------------------------------------------
This is a **feasibility-informed preregistration**, not a blind one, and saying
otherwise would misrepresent it.

An exploratory pass ran before these numbers were written down. It established
which regimes exist in this parameterization, roughly what they cost, and the
scale of every residual the verification gate measures. The acceptance bands
below were then set comfortably outside those observations and frozen, and the
two reference tolerances in the domain's verification gate were *tightened*
from 1e-6 to 1e-9 as a direct consequence — exploration showed the residuals
sit near 1e-15, which would have made a 1e-6 gate unfailable and therefore
worthless as evidence.

What that costs, stated plainly: the predictions below are not discoveries.
Their scientific function is to fix the criteria before the scored run so that
a missed band must be reported as a missed band rather than explained away. The
discipline that carries weight here is the no-tuning rule, not surprise.

What exploration did NOT fix, and which is therefore genuinely open: every
level award below is re-derived under the tightened 1e-9 gates that exploration
never ran, and the whole failure-semantics question — which is the actual
subject of K1 — was never scored before this preregistration was frozen.

Module roles:

    k1_config.py  preregistration — chemistry, regimes, predictions, criteria
    k1_run.py     the scored study and the artifacts it writes

VERSION HISTORY — INVALIDATED RUNS ARE RECORDED, NOT ERASED
------------------------------------------------------------
**1.0.0 — INVALIDATED. Apparatus bug, not a scientific result.**

The scored run at 1.0.0 completed and met every one of its eight regime
predictions, but acceptance criterion A7 failed: failure-semantics case B
(numerical non-convergence) was not represented.

The cause was in the runner's case-B probe, which is test apparatus rather
than a preregistered regime. The probe injected a discontinuous sign flip into
the right-hand side, expecting SciPy to give up on the step. It did not give
up: it ground the step size down and kept going, exhausting the 5,000,000
evaluation budget and classifying — correctly — as MAX_ITERATIONS. The
adapter behaved properly; the probe simply did not test what it claimed to.

Correction at 1.0.1: the probe now injects a genuine finite-time singularity
(``dT/dt += T**2``, a Riccati blowup), for which no step size can satisfy the
error test. SciPy returns status -1 with "Required step size is less than
spacing between numbers", and the adapter classifies NOT_CONVERGED while
preserving the partial trajectory.

Nothing about the eight scientific regimes changed. The correction touches
only the apparatus for a case the preregistration already stated no regime
would produce. The whole study was rerun from scratch under 1.0.1 rather than
patched, and the 1.0.0 numbers are superseded rather than reported.
"""

from __future__ import annotations

K1_VERSION = "1.0.1"

#: The frozen Core V0.2 commit this builds on. Nothing under experiments/ that
#: predates it is read, written or re-run by K1.
BASE_COMMIT = "0d0f1990b92a1ec68b86f315ef8c1a9a40d54085"
