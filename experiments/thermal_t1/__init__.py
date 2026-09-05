"""T1 — Thermal parameter inference over alpha, at fixed fidelity rungs.

THE QUESTION
------------
Can a numerically coarse but apparently converged solver produce a posterior
over alpha that is confident yet systematically biased?

Every earlier experiment had a forward map whose numerical error was
negligible: Electrical DC solves a 3x3 system directly, to 1.85e-16, which is
fourteen orders below any observation noise. So E1, E2 and E3 could never ask
this. The frozen thermal gate changed that — its discretization error spans
1.6e-02 down to 1.9e-04 and is controllable — and this is the first experiment
that can put the question.

The failure mode being looked for is new:

    the physics is right, the implementation is right, the inference is right,
    and the answer is wrong — because the numerics were cheap.

WHAT THIS DELIBERATELY DOES NOT DO
-----------------------------------
No adaptive fidelity selection. Nothing here chooses a rung. Three independent,
preregistered inferences run at three FIXED rungs with the same truth, the same
observation model, the same prior and the same observations, and the results
are compared. Whether a campaign should ever be allowed to choose a rung is a
question for a later milestone, and only if this one produces evidence that
fidelity affects inference enough to be worth choosing.

No campaign, no EVPI/EVSI, no certification, no model adequacy. This is
inference under a fixed forward map, three times.

Module roles:

    t1_config.py  preregistered constants, rungs, and the config hash
    t1_truth.py   GRADER ONLY — alpha_true and the observation generator
    t1_run.py     the study, its measurements and its artifacts
"""

from __future__ import annotations

#: Modules that participate in inference. Neither may import the grader truth;
#: a test parses the import graph.
DECISION_PATH_MODULES = ("t1_config",)

T1_VERSION = "1.0.0"

#: The frozen thermal solver gate this builds on.
BASE_COMMIT = "2733612b8c092e21c2cba70ce653b95a97aba6b7"
