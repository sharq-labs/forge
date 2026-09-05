"""T2 — repeated-draw numerical calibration of the thermal fidelity ladder.

THE QUESTION
------------
Does numerical discretization error cause systematic posterior miscalibration
and confident parameter bias across repeated observations, and at what fidelity
does observation noise become the dominant error source?

WHY T1 COULD NOT ANSWER THIS
-----------------------------
T1 ran one noise draw. It measured a bias, and it was careful to say that
covering or missing on a single draw is one Bernoulli outcome and not a
calibration statement. T2 is that missing statement: the same inference, over
many preregistered draws, so coverage becomes a frequency instead of an
anecdote.

WHAT IS HELD FIXED — EVERYTHING T1 FROZE
-----------------------------------------
    alpha_true, prior, grid, observation model, observation count and location,
    sigma, the coarse/medium/reference rungs, and the inference implementation.

The ONLY thing that varies is the observation-noise realization. T1's modules
are imported read-only and pinned by digest; nothing here edits T1's
preregistration or its results.

THE CONTROL ARM
---------------
Alongside the three solver rungs, the identical inference runs against the
EXACT analytic forward map. That arm has zero discretization error by
construction, so it isolates the likelihood, the prior and the grid from the
numerics. It is a calibration control, NOT a fidelity rung, and it is what
licenses attributing any solver-rung miscalibration to discretization: if the
exact arm also miscalibrates, the cause is the inference and not the fidelity.

WHAT THIS DELIBERATELY DOES NOT DO
-----------------------------------
No adaptive fidelity selection, no fidelity policy, no EVSI machinery, no
commitment promotion, no ObligationSet change, no certification change. T2 is
an experiment. Whether a campaign should ever choose a rung is a later
decision, and one that this evidence is meant to inform rather than pre-empt.

Module roles:

    t2_config.py  preregistration — replications, seed rule, metrics, criteria
    t2_truth.py   GRADER ONLY — the per-replication observation draws
    t2_run.py     the study, its measurements and its artifacts
"""

from __future__ import annotations

#: Modules that participate in inference. None may import a grader truth;
#: a test parses the import graph.
DECISION_PATH_MODULES = ("t2_config",)

T2_VERSION = "1.0.0"

#: The frozen T1 commit this builds on.
BASE_COMMIT = "3e2ca40cfa69a591896dba45620e449c5a0651cf"
