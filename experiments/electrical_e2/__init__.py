"""E2 — Model adequacy / predictive surprise.

E1 asked whether SRIA could compute a correct decision from a real solver. E2
asks the question that comes *after* a correct posterior: is the model family
the posterior is conditional on good enough to support the conclusion?

The circuit, the solver and the assumed model family are E1's. What changes is
that the grader-only truth is deliberately placed OUTSIDE the assumed family:
the hidden law makes the resistance depend on the operating condition, so no
single constant R2 can reproduce every measurement. The decision path is never
told. It keeps assuming a constant R2, keeps using the real
``ElectricalDCSolver``, and keeps computing an exact conditional posterior.

The experiment then makes the failure observable in the only way that is not
circular: predictions are computed and content-hashed BEFORE the observations
they predict exist, and are scored afterwards against a preregistered rule.

Module roles, enforced by test:

    e2_config.py     decision path — preregistered constants (no truth value)
    e2_model.py      decision path — forward map via the REAL solver, posterior,
                     predictive mixture, exact predictive tails, EVPI, EVSI
    e2_adequacy.py   decision path — predictive commitment ledger, surprise
                     metric, adequacy classifier, certification gate
    e2_truth.py      GRADER ONLY — misspecified truth law and analytic oracle
    e2_harness.py    grader+integration — executor, evidence, admission chain
    e2_run.py        orchestration, controls, adversarial injections, artifacts

The three central separations E2 exists to hold apart:

    EXECUTION VALIDITY   !=   MODEL ADEQUACY
    POSTERIOR CONFIDENCE !=   MODEL ADEQUACY
    LOW EVPI / EVSI      !=   MODEL ADEQUACY
"""

from __future__ import annotations

#: Modules that participate in inference, prediction and the adequacy verdict.
#: None may import the grader truth; a test parses their import graphs and
#: checks transitively that every sibling they reach is itself on this list.
DECISION_PATH_MODULES = ("e2_config", "e2_model", "e2_adequacy")

#: Must equal :data:`e2_config.EXPERIMENT_VERSION`. It is duplicated here only
#: so the package advertises its version without importing the config, and a
#: regression test asserts the two agree — a package that reported 1.0.0 while
#: the run it produced was 1.1.0 would misattribute a corrected result to the
#: superseded rule.
E2_VERSION = "1.1.0"
