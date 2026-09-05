"""E1 — Electrical quantitative verification.

The first real-domain integration proof: the existing Electrical DC solver
participates as the forward model in quantitative Bayesian inference, real
EVPI/EVSI are computed from its predictions, action selection runs through the
frozen M5 CampaignRunner, and the executed result reaches the posterior only
through the M1 evidence/admission path.

Module roles, enforced by test:

    e1_config.py   decision path — preregistered constants (no truth value)
    e1_model.py    decision path — forward map via the REAL solver, posterior,
                   predictive, EVPI, EVSI
    e1_truth.py    GRADER ONLY — true parameter and the analytic oracle
    e1_harness.py  grader+integration — executor, evidence, CampaignHarness
    e1_run.py      orchestration, verification gate, artifacts
"""

from __future__ import annotations

#: Modules that participate in choosing what to do next. None may import the
#: analytic oracle / true parameter; a test parses their import graphs.
DECISION_PATH_MODULES = ("e1_config", "e1_model")

E1_VERSION = "1.0.0"
