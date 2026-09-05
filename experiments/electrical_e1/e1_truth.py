"""E1 hidden truth and analytic oracle — GRADER ONLY.

**No decision-path module may import this**, enforced by an AST test. The two
legitimate consumers are:

* the executor (the "instrument"), which plays the role of reality by
  evaluating the real solver at the true parameter and adding the declared
  benchmark noise; and
* the grader, which checks the solver against the closed form and scores the
  terminal decision.

The analytic voltage-divider relation is derived independently of the MNA
path: for the declared topology, KVL/KCL give

    V_mid = Vs * R2 / (R1 + R2)
    I     = Vs / (R1 + R2)

The decision path's forward model is the *solver*, never these formulas; they
exist so the solver can be checked against something it did not produce.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .e1_config import R1_OHM, THRESHOLD_OHM

#: The unknown resistance "reality" holds. Inside the prior support
#: [500, 2500], deliberately off the 20-ohm grid spacing, and above the
#: decision threshold — so the correct terminal decision is A.
TRUE_R2_OHM = 1378.0


def analytic_vmid(source_voltage_volt: float, r2_ohm: float) -> float:
    """Closed-form divider voltage. Grader-only."""
    return float(source_voltage_volt) * float(r2_ohm) / (R1_OHM + float(r2_ohm))


def analytic_source_current(source_voltage_volt: float, r2_ohm: float) -> float:
    """Closed-form loop current, positive in the divider direction."""
    return float(source_voltage_volt) / (R1_OHM + float(r2_ohm))


def oracle_decision(true_r2_ohm: float = TRUE_R2_OHM) -> str:
    return "A" if float(true_r2_ohm) > THRESHOLD_OHM else "B"


def truth_payload() -> dict[str, Any]:
    return {
        "true_r2_ohm": TRUE_R2_OHM,
        "oracle_decision": oracle_decision(),
        "analytic_relation": "V_mid = Vs * R2 / (R1 + R2)",
    }


def truth_hash() -> str:
    blob = json.dumps(truth_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
