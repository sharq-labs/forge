"""T3 — Decision-aware fidelity escalation.

THE QUESTION
------------
Can a cost-aware decision rule determine when the current numerical fidelity is
sufficient for a downstream scientific decision, and when paying for higher
fidelity is necessary?

WHY THE TERMINAL QUANTITY CANNOT BE THE ASSIMILATED ONE
--------------------------------------------------------
T2 found, without predicting it, that prediction error on the assimilated QoI
is blind to discretization bias: every rung predicted it equally well while
being wrong about alpha by up to 4.7%. The reason is exact, and it decides
this experiment's design.

Backward Euler on a single decaying mode gives

    u_num = (1 + lambda dt)^(-M) = exp(-lambda_eff t)

so the discretization error is EXACTLY an effective-alpha shift. Fitting alpha
absorbs it completely. In Fourier number Fo = alpha pi^2 t / L^2, calibrating
at Fo_0 and predicting at Fo_1 = r Fo_0 with the same (n_cells, n_steps), the
terminal relative error is approximately

    r (r - 1) * eps_obs

which is identically zero at r = 1 and grows with r. A decision built on the
assimilated QoI is therefore a decision the numerics cannot lose, and it would
prove nothing.

T3 sets r = 3: calibrate on the observation at 60 s, decide on the slab's
state at 180 s. That condition is never assimilated, and the measured
separation between rungs is about a factor of ten per rung.

WHAT THIS DELIBERATELY DOES NOT DO
-----------------------------------
No generic FidelityPolicy, no new SRIA module, no commitment promotion, no
ObligationSet redesign, no certification change. The escalation logic is
experiment-side and is about forty lines. T3 is an experiment.

Module roles:

    t3_config.py  preregistration — scenarios, costs, rules, criteria
    t3_truth.py   GRADER ONLY — per-scenario alpha, thresholds and draws
    t3_run.py     the study, the policy, the baselines and the artifacts
"""

from __future__ import annotations

#: Modules that participate in the decision. None may import a grader truth;
#: a test parses the import graph.
DECISION_PATH_MODULES = ("t3_config",)

T3_VERSION = "1.0.0"

#: The frozen T2 commit this builds on.
BASE_COMMIT = "4da598d5994fae09b202727228eb5b302cb60c01"
