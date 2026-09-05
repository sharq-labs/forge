"""SRIA falsification phase — transport-aware stopping.

An isolated harness, deliberately outside ``src/engcore``. It tests one claim
and nothing else:

    Low model-based EVSI can incorrectly support stopping outside the
    empirically justified support region, and a separate transport/support
    requirement prevents scientific certification of that stop.

Module roles, which the tests enforce:

    inference.py   decision path — exact grid Bayes
    decision.py    decision path — terminal decision, EVPI, real EVSI
    support.py     decision path — support rule and the two stop policies
    truth.py       GRADER ONLY — the hidden ground truth
    benchmark.py   harness and grader; the only module that may see truth.py
"""

from __future__ import annotations

#: Modules that participate in choosing what to do next. None of them may
#: import the hidden truth, and ``test_truth_generator_is_inaccessible``
#: verifies it by parsing their import graphs rather than trusting this list.
DECISION_PATH_MODULES = ("inference", "decision", "support")

FALSIFICATION_VERSION = "0.1.0-transport-stop"
