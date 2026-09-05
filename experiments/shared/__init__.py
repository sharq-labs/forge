"""Shared machinery for experiments written AFTER the Electrical V0.1 freeze.

WHAT THIS IS NOT
----------------
It is not a refactor of E1, E2, E3 or the V0.1 demo, and it never will be.
Those four carry ~2,900 lines of near-identical harness wiring, and that
duplication is permanent and correct: each is a frozen scientific artifact,
pinned by digest from the next experiment in the chain
(``e2_config.E1_FROZEN_FILE_DIGESTS`` pins ``e1_harness.py``,
``e3_config.E2_FROZEN_FILE_DIGESTS`` pins ``e2_harness.py``). Touching them to
remove duplication would break the freeze chain, and tests enforce that. The
recorded experimental record must stay exactly as it was run.

So this package exists for the FIFTH experiment onward, and its only ambition
is that the fifth does not have to copy the fourth.

WHAT THIS IS
------------
The smallest pieces a new experiment actually needed, extracted when a real
second caller appeared — not designed in advance for callers that do not exist.
Currently one module:

    grid_inference.py   exact Bayesian inference for ONE parameter on a finite
                        grid: uniform prior, Gaussian likelihood, credible
                        interval, coverage.

There is deliberately no campaign harness, no executor protocol, no generator
base class and no utility engine here. Those differ enough between experiments
that a shared version would be a framework, and a framework written before the
third distinct use is a guess.
"""

from __future__ import annotations

SHARED_VERSION = "0.1.0"
