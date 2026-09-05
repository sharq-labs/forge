"""E2 hidden truth and analytic oracle — GRADER ONLY.

**No decision-path module may import this**, enforced by a transitive AST test.
The two legitimate consumers are the executor (which plays the role of reality)
and the grader (which checks the solver against the closed form and scores the
result).

THE MISSPECIFICATION IS SYNTHETIC AND MAKES NO PHYSICAL CLAIM
-------------------------------------------------------------
The hidden law below is a deliberate, declared benchmark construct. It is NOT
thermal physics, NOT a self-heating model, NOT a hardware effect and NOT a
claim that any real resistor behaves this way. It exists for exactly one
reason: to place the truth outside the assumed constant-R family in a way that
is smooth, bounded, and locally indistinguishable from a constant.

    R_eff(Vs) = R0 * [ 1 + kappa * tanh( (Vs - Vref) / Vref ) ]

Three properties earn each part of that form:

* it is EXACTLY R0 at Vs = Vref, so a campaign that calibrates at Vref sees a
  perfectly well-behaved constant-R world and has no local reason to doubt it;
* tanh is smooth and bounded by kappa, so the deviation stays mild (under 10%)
  rather than becoming an obvious discontinuity a residual check would catch;
* it is monotone in Vs, so the failure is systematic and directional rather
  than noise-like — which is what separates a wrong model from an unlucky draw.

The consequence for the assumed family: under M_const the observed V_mid must
be exactly proportional to Vs. Under this law it is not. No single constant can
satisfy every condition, and the more sharply the constant is pinned down at
one condition, the more decisively it fails at the others.

The instrument runs the REAL solver at R_eff — these are genuine, valid
computational executions with real provenance and real residuals. Nothing about
the misspecification makes the resulting evidence computationally invalid, and
E2's central assertion is that it must not be treated as if it did.

The closed-form divider relation stays here as the grader's independent check
on the solver, exactly as in E1. It is derived from KVL/KCL, not from the MNA
path, so the solver can be checked against something it did not produce.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from .e2_config import R1_OHM, THRESHOLD_OHM

# --- the hidden parameters ---------------------------------------------------
#: Base resistance. Same value E1 hid, so the two experiments are comparable:
#: inside the prior support, off the grid spacing, above the decision threshold.
TRUE_R0_OHM = 1378.0
#: Deviation amplitude. |R_eff/R0 - 1| < 0.10 everywhere — mild by construction.
MISSPEC_KAPPA = 0.10
#: The condition at which the law is exactly constant, and at which Phase 1
#: calibrates. Chosen to be the calibration voltage precisely so that the
#: calibration phase cannot reveal the problem.
MISSPEC_VREF_VOLT = 10.0
MISSPEC_LAW = "R_eff(Vs) = R0 * (1 + kappa * tanh((Vs - Vref) / Vref))"

# --- Control B: one isolated outlier under an otherwise correct model --------
#: A declared single-condition instrument fault, preregistered before the run.
#: The truth in Control B is a genuine constant, so the family is CORRECT; this
#: offset exists only to test that one extreme point cannot condemn it.
OUTLIER_ACTION_ID = "challenge_vmid_24V"
OUTLIER_OFFSET_VOLT = 0.50


@dataclass(frozen=True)
class TruthSpec:
    """One hidden world. The decision path never sees an instance of this."""

    spec_id: str
    r0_ohm: float
    kappa: float
    vref_volt: float
    outlier_action_id: str | None = None
    outlier_offset_volt: float = 0.0
    description: str = ""

    @property
    def is_well_specified(self) -> bool:
        """True when the truth lies inside the assumed constant-R family."""
        return self.kappa == 0.0

    def effective_resistance(self, source_voltage_volt: float) -> float:
        """The resistance reality uses at this operating condition."""
        if self.kappa == 0.0:
            return float(self.r0_ohm)
        deviation = math.tanh(
            (float(source_voltage_volt) - self.vref_volt) / self.vref_volt
        )
        return float(self.r0_ohm) * (1.0 + self.kappa * deviation)

    def outlier_for(self, action_id: str) -> float:
        if self.outlier_action_id is not None and action_id == self.outlier_action_id:
            return float(self.outlier_offset_volt)
        return 0.0

    def payload(self) -> dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "r0_ohm": self.r0_ohm,
            "kappa": self.kappa,
            "vref_volt": self.vref_volt,
            "law": MISSPEC_LAW if self.kappa else "R_eff(Vs) = R0 (constant)",
            "in_assumed_family": self.is_well_specified,
            "outlier_action_id": self.outlier_action_id,
            "outlier_offset_volt": self.outlier_offset_volt,
            "description": self.description,
        }


#: Control C / the scored run: the truth is OUTSIDE the assumed family.
MISSPECIFIED_TRUTH = TruthSpec(
    spec_id="C_systematic_misspecification",
    r0_ohm=TRUE_R0_OHM,
    kappa=MISSPEC_KAPPA,
    vref_volt=MISSPEC_VREF_VOLT,
    description=(
        "condition-dependent effective resistance; no constant R2 reproduces "
        "every preregistered condition"
    ),
)

#: Control A: the truth IS a constant inside model support — E1's world.
WELL_SPECIFIED_TRUTH = TruthSpec(
    spec_id="A_well_specified",
    r0_ohm=TRUE_R0_OHM,
    kappa=0.0,
    vref_volt=MISSPEC_VREF_VOLT,
    description="a genuine constant inside the assumed family and the prior",
)

#: Control B: correct family, one preregistered isolated instrument outlier.
SINGLE_OUTLIER_TRUTH = TruthSpec(
    spec_id="B_single_outlier",
    r0_ohm=TRUE_R0_OHM,
    kappa=0.0,
    vref_volt=MISSPEC_VREF_VOLT,
    outlier_action_id=OUTLIER_ACTION_ID,
    outlier_offset_volt=OUTLIER_OFFSET_VOLT,
    description=(
        "the assumed family is correct; exactly one condition carries a "
        "declared instrument offset"
    ),
)


# --- the analytic oracle (independent of the MNA path) -----------------------

def analytic_vmid(source_voltage_volt: float, r2_ohm: float) -> float:
    """Closed-form divider voltage. Grader-only."""
    return float(source_voltage_volt) * float(r2_ohm) / (R1_OHM + float(r2_ohm))


def analytic_source_current(source_voltage_volt: float, r2_ohm: float) -> float:
    """Closed-form loop current, positive in the divider direction."""
    return float(source_voltage_volt) / (R1_OHM + float(r2_ohm))


def truth_vmid(source_voltage_volt: float, spec: TruthSpec) -> float:
    """What reality would show, by the closed form. Used for grading only —
    the instrument itself runs the real solver."""
    return analytic_vmid(
        source_voltage_volt, spec.effective_resistance(source_voltage_volt)
    )


def best_constant_fit(
    spec: TruthSpec, source_voltages: tuple[float, ...]
) -> dict[str, float]:
    """How well the BEST constant R could do across these conditions.

    Grader-only diagnostic. Under a well-specified truth the residual is
    exactly zero; under the misspecified law it is bounded away from zero for
    every constant, which is what "outside the model family" means
    quantitatively rather than rhetorically.
    """
    best_r = 0.0
    best_cost = float("inf")
    targets = [truth_vmid(v, spec) for v in source_voltages]
    lo, hi = 500.0, 2500.0
    for _ in range(60):                      # golden-section-free bisection scan
        candidates = [lo + (hi - lo) * i / 40.0 for i in range(41)]
        for r in candidates:
            cost = sum(
                (analytic_vmid(v, r) - t) ** 2
                for v, t in zip(source_voltages, targets)
            )
            if cost < best_cost:
                best_cost = cost
                best_r = r
        span = (hi - lo) / 8.0
        lo, hi = max(500.0, best_r - span), min(2500.0, best_r + span)
        if hi - lo < 1e-9:
            break
    worst = max(
        abs(analytic_vmid(v, best_r) - t)
        for v, t in zip(source_voltages, targets)
    )
    return {
        "best_constant_r_ohm": best_r,
        "sum_squared_residual_volt2": best_cost,
        "worst_abs_residual_volt": worst,
    }


def oracle_decision(spec: TruthSpec = MISSPECIFIED_TRUTH) -> str:
    """The terminal decision the base resistance implies.

    Reported for completeness, and read with care: under a misspecified family
    "the correct answer" is itself model-relative. R0 is above the threshold,
    and so is every R_eff this law produces, so the classification question has
    an unambiguous answer here even though the family does not.
    """
    return "A" if float(spec.r0_ohm) > THRESHOLD_OHM else "B"


def truth_payload() -> dict[str, Any]:
    return {
        "scored_truth": MISSPECIFIED_TRUTH.payload(),
        "control_a_truth": WELL_SPECIFIED_TRUTH.payload(),
        "control_b_truth": SINGLE_OUTLIER_TRUTH.payload(),
        "analytic_relation": "V_mid = Vs * R2 / (R1 + R2)",
        "oracle_decision": oracle_decision(),
        "misspecification_magnitude": {
            "kappa": MISSPEC_KAPPA,
            "max_fractional_deviation": MISSPEC_KAPPA,
            "statement": (
                "bounded by kappa at every condition; the deviation is exactly "
                "zero at the calibration condition by construction"
            ),
        },
        "scope": (
            "synthetic grader-only misspecification; no physical mechanism is "
            "claimed and no hardware is involved"
        ),
    }


def truth_hash() -> str:
    blob = json.dumps(truth_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
