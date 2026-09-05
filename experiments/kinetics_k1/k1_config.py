"""K1 preregistered configuration.

Frozen BEFORE the scored run. Everything the study is allowed to depend on is
declared here: the chemistry, the regimes, the integration declarations, the
predictions, the acceptance bands and the falsification triggers.

THE PARAMETERIZATION AND WHAT IS AND IS NOT CLAIMED FOR IT
------------------------------------------------------------
The chemistry and operating point are the widely used textbook non-isothermal
CSTR example (Seborg/Edgar/Mellichamp/Doyle, in the Aris-Amundson tradition),
converted from the customary litre/minute units to SI here so that every
declared quantity carries a coherent unit.

What is claimed: these are the declared inputs, they are frozen, and every
number in the results follows from them by computation.

What is NOT claimed: that this transcription has been checked against the
printed source. It has not, and no conclusion in K1 depends on it having been —
K1 asks whether the contracts can carry a stiff kinetics solver, and that
question is answered identically whichever defensible parameter set is used.
Nothing here has been compared against a measurement of a real reactor, and no
result in this experiment is evidence about one.

WHY THESE REGIMES
-----------------
The set is chosen to force each distinguishable outcome to occur at least once
through a genuine mechanism rather than a mock:

    R1  clean convergence, low conversion, no stiffness
    R2  materially stiff, with an exact analytic reference available
    R3  strongly stiff — the explicit probe cannot finish at all
    R4  declarations outside the validity envelope, rejected before any solve
    R5  a genuine computational limit, exhausted while still making progress
    R6  three algebraic steady states, one dynamical attractor
    R7  no stable steady state at all: sustained oscillation
    R8  a flawless integration whose answer is outside the model's envelope

R8 is the regime this milestone exists for. It is numerically impeccable and
scientifically unusable, and a contract that cannot tell those apart would have
to lie about one of them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from src.engcore.domains.kinetics.cstr import (
    INVARIANT_REL_TOL,
    STATIONARITY_REL_TOL,
    STEADY_STATE_REL_TOL,
    TOLERANCE_LADDER,
    TOLERANCE_REL_TOL,
    IntegrationSettings,
    ReactorChemistry,
    ReactorOperation,
    ReactorRun,
)
from src.engcore.scientific.units.quantity import Quantity

from . import BASE_COMMIT, K1_VERSION

EXPERIMENT_ID = "K1"
EXPERIMENT_NAME = "kinetics_cstr_solver_admission_gate"

SCIENTIFIC_QUESTION = (
    "Can the frozen Core V0.2 contracts honestly represent and execute a "
    "stiff, nonlinear, failure-prone kinetics/CSTR solver — including "
    "distinguishing execution failure, non-convergence, invalid input, "
    "successful-but-unusable results and valid results — without speculative "
    "Core expansion?"
)

# =====================================================================
# 1. The chemistry and the base operating point
# =====================================================================

#: Customary-unit values as tabulated, kept beside the SI conversion so the
#: transcription is auditable rather than asserted.
CUSTOMARY_PARAMETERS = {
    "q_L_per_min": 100.0,
    "V_L": 100.0,
    "rho_g_per_L": 1000.0,
    "cp_J_per_g_K": 0.239,
    "delta_H_J_per_mol": -5.0e4,
    "E_over_R_K": 8750.0,
    "k0_per_min": 7.2e10,
    "UA_J_per_min_K": 5.0e4,
    "T_feed_K": 350.0,
    "C_Af_mol_per_L": 1.0,
}

#: The activation energy is derived from the tabulated E/R group and the SI
#: molar gas constant, so that the exponent reproduces the published group
#: exactly rather than being restated to a rounded number of digits.
MOLAR_GAS_CONSTANT_J_PER_MOL_K = 8.314462618
ACTIVATION_ENERGY_J_PER_MOL = (
    CUSTOMARY_PARAMETERS["E_over_R_K"] * MOLAR_GAS_CONSTANT_J_PER_MOL_K
)

CHEMISTRY = ReactorChemistry(
    k0=Quantity(CUSTOMARY_PARAMETERS["k0_per_min"] / 60.0, "1/s"),
    activation_energy=Quantity(ACTIVATION_ENERGY_J_PER_MOL, "J/mol"),
    heat_of_reaction=Quantity(CUSTOMARY_PARAMETERS["delta_H_J_per_mol"], "J/mol"),
    density=Quantity(CUSTOMARY_PARAMETERS["rho_g_per_L"], "kg/m**3"),
    heat_capacity=Quantity(
        CUSTOMARY_PARAMETERS["cp_J_per_g_K"] * 1000.0, "J/(kg*K)"
    ),
)

VOLUME_M3 = CUSTOMARY_PARAMETERS["V_L"] / 1000.0
FLOW_M3_PER_S = CUSTOMARY_PARAMETERS["q_L_per_min"] / 1000.0 / 60.0
NOMINAL_UA_W_PER_K = CUSTOMARY_PARAMETERS["UA_J_per_min_K"] / 60.0
NOMINAL_FEED_CONCENTRATION = CUSTOMARY_PARAMETERS["C_Af_mol_per_L"] * 1000.0
NOMINAL_FEED_TEMPERATURE = CUSTOMARY_PARAMETERS["T_feed_K"]

# =====================================================================
# 2. The production integration declaration
# =====================================================================

#: BDF is the production method for every scored regime. Variable-order
#: backward differentiation with an analytic Jacobian: the standard choice for
#: stiff chemical kinetics because it is *stiffly stable* in Gear's sense — its
#: stability region contains the whole negative real axis and a wedge around it,
#: so a strongly damped mode does not dictate the step size. It is A-stable only
#: at orders 1-2 and A(alpha)-stable above that; it is NOT L-stable at every
#: order it uses. See PREREGISTRATION_ERRATA below.
PRODUCTION_METHOD = "BDF"

#: Radau (5th-order Radau IIA, fully implicit Runge-Kutta) is the cross-method
#: arm — a different family, and genuinely A-stable and L-stable. The
#: comparison is preregistered HERE, before any run, and it awards no validation
#: level: both arms share the domain's right-hand side, its Jacobian and SciPy's
#: step control.
CROSS_METHOD = "Radau"

#: RK45 is the stiffness probe. Never a production method; its only role is to
#: make stiffness a measurement rather than an assertion.
STIFFNESS_PROBE_METHOD = "RK45"

#: The scored tolerance. Every regime is run here, and the verification gate
#: then walks the frozen ladder around it.
PRODUCTION_RTOL = 1.0e-8
PRODUCTION_ATOL_CONCENTRATION = 1.0e-8   # mol/m**3
PRODUCTION_ATOL_TEMPERATURE = 1.0e-8     # K

#: The generous budget every regime except R5 receives. Large enough that no
#: stiff-method regime in this study can reach it, so budget exhaustion in the
#: production arm would itself be a finding.
STANDARD_RHS_BUDGET = 5_000_000

#: R5's deliberately tight budget. Set below the ~1,563 evaluations the
#: exploratory pass observed R3 needing, and far above the ~100 an aborted
#: start would use, so exhaustion happens with the integration mid-flight
#: rather than at the first step.
CONSTRAINED_RHS_BUDGET = 500

#: The stiffness probe's budget. Exhausting it is a valid measurement — it
#: bounds the work ratio from below — and 5e6 is large enough that reaching it
#: is a statement about the problem rather than about the budget.
STIFFNESS_PROBE_BUDGET = 5_000_000


def _integration(
    *, budget: int = STANDARD_RHS_BUDGET, n_output_points: int = 2001
) -> IntegrationSettings:
    return IntegrationSettings(
        method=PRODUCTION_METHOD,
        rtol=PRODUCTION_RTOL,
        atol_concentration=PRODUCTION_ATOL_CONCENTRATION,
        atol_temperature=PRODUCTION_ATOL_TEMPERATURE,
        max_rhs_evaluations=budget,
        n_output_points=n_output_points,
    )


def _operation(
    *,
    coolant_temperature_k: float,
    ua_w_per_k: float,
    feed_temperature_k: float,
    feed_concentration_mol_per_m3: float,
    end_time_s: float,
) -> ReactorOperation:
    return ReactorOperation(
        volume=Quantity(VOLUME_M3, "m**3"),
        flow_rate=Quantity(FLOW_M3_PER_S, "m**3/s"),
        feed_concentration=Quantity(
            feed_concentration_mol_per_m3, "mol/m**3"
        ),
        feed_temperature=Quantity(feed_temperature_k, "kelvin"),
        coolant_temperature=Quantity(coolant_temperature_k, "kelvin"),
        ua=Quantity(ua_w_per_k, "W/K"),
        end_time=Quantity(end_time_s, "second"),
    )


# =====================================================================
# 3. The regimes
# =====================================================================

@dataclass(frozen=True)
class RegimeSpec:
    """One preregistered regime and everything predicted about it."""

    regime_id: str
    name: str
    category: str
    rationale: str
    coolant_temperature_k: float
    ua_w_per_k: float
    feed_temperature_k: float
    feed_concentration_mol_per_m3: float
    initial_concentration_mol_per_m3: float
    initial_temperature_k: float
    end_time_s: float
    rhs_budget: int = STANDARD_RHS_BUDGET
    n_output_points: int = 2001
    #: Predicted ConvergenceState value.
    predicted_convergence: str = "converged"
    #: Predicted ScientificResult.is_usable.
    predicted_usable: bool = True
    #: Predicted ValidationLevel values from the verification gate. Empty means
    #: the gate is predicted to award nothing, which is a real prediction.
    predicted_levels: tuple[str, ...] = ()
    #: Whether the verification gate is run for this regime at all.
    run_verification_gate: bool = True
    #: Whether the stiffness probe is run for this regime.
    measure_stiffness: bool = False
    #: Inclusive acceptance band on the RK45/BDF evaluation ratio, when
    #: measured. ``None`` on either side means unbounded.
    stiffness_ratio_band: tuple[float | None, float | None] | None = None
    #: Which failure-semantics case (A-E) this regime is meant to exercise.
    failure_case: str = "E"
    prediction_note: str = ""

    def build(self) -> ReactorRun:
        return ReactorRun(
            run_label=self.regime_id,
            chemistry=CHEMISTRY,
            operation=_operation(
                coolant_temperature_k=self.coolant_temperature_k,
                ua_w_per_k=self.ua_w_per_k,
                feed_temperature_k=self.feed_temperature_k,
                feed_concentration_mol_per_m3=(
                    self.feed_concentration_mol_per_m3
                ),
                end_time_s=self.end_time_s,
            ),
            initial_concentration=Quantity(
                self.initial_concentration_mol_per_m3, "mol/m**3"
            ),
            initial_temperature=Quantity(self.initial_temperature_k, "kelvin"),
            integration=_integration(
                budget=self.rhs_budget, n_output_points=self.n_output_points
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_id": self.regime_id,
            "name": self.name,
            "category": self.category,
            "rationale": self.rationale,
            "coolant_temperature_k": self.coolant_temperature_k,
            "ua_w_per_k": self.ua_w_per_k,
            "feed_temperature_k": self.feed_temperature_k,
            "feed_concentration_mol_per_m3":
                self.feed_concentration_mol_per_m3,
            "initial_concentration_mol_per_m3":
                self.initial_concentration_mol_per_m3,
            "initial_temperature_k": self.initial_temperature_k,
            "end_time_s": self.end_time_s,
            "rhs_budget": self.rhs_budget,
            "n_output_points": self.n_output_points,
            "predicted_convergence": self.predicted_convergence,
            "predicted_usable": self.predicted_usable,
            "predicted_levels": list(self.predicted_levels),
            "run_verification_gate": self.run_verification_gate,
            "measure_stiffness": self.measure_stiffness,
            "stiffness_ratio_band": (
                list(self.stiffness_ratio_band)
                if self.stiffness_ratio_band
                else None
            ),
            "failure_case": self.failure_case,
            "prediction_note": self.prediction_note,
        }


NUM = "numerically_converged"
ANA = "analytically_verified"
XSOL = "cross_solver_validated"

REGIMES: tuple[RegimeSpec, ...] = (
    RegimeSpec(
        regime_id="R1",
        name="benign cooled operation",
        category="easy",
        rationale=(
            "Well-cooled at Tc = 290 K, far below the ignition window. A single "
            "stable steady state at low conversion, approached monotonically. "
            "The horizon is 30 residence times so the trajectory actually "
            "settles and the steady-state comparison can engage."
        ),
        coolant_temperature_k=290.0,
        ua_w_per_k=NOMINAL_UA_W_PER_K,
        feed_temperature_k=NOMINAL_FEED_TEMPERATURE,
        feed_concentration_mol_per_m3=NOMINAL_FEED_CONCENTRATION,
        initial_concentration_mol_per_m3=NOMINAL_FEED_CONCENTRATION,
        initial_temperature_k=300.0,
        end_time_s=1800.0,
        predicted_convergence="converged",
        predicted_usable=True,
        # The reactor is cooled, so the reaction-free invariant has no closed
        # form and ANALYTICALLY_VERIFIED is unavailable at any tolerance. That
        # is a prediction about the physics, not about the integrator.
        predicted_levels=(NUM, XSOL),
        measure_stiffness=True,
        # Predicted NOT stiff. Exploration measured 0.8; a benign regime where
        # an explicit method is no more expensive than an implicit one is the
        # control that makes the stiff regimes' ratios mean something.
        stiffness_ratio_band=(None, 5.0),
        failure_case="E",
        prediction_note=(
            "clean convergence in a few hundred evaluations; the explicit "
            "probe is no more expensive than BDF because the regime is not "
            "stiff"
        ),
    ),
    RegimeSpec(
        regime_id="R2",
        name="moderately stiff adiabatic ignition",
        category="moderately_stiff",
        rationale=(
            "Adiabatic (UA = 0) with a 340 K feed. The reaction runs away to "
            "about 549 K, making the chemical mode orders of magnitude faster "
            "than the flow mode. Adiabatic operation also makes the "
            "reaction-free invariant an exact closed form, so this regime "
            "carries the only genuinely analytic reference in the study."
        ),
        coolant_temperature_k=300.0,   # unused: UA = 0
        ua_w_per_k=0.0,
        feed_temperature_k=340.0,
        feed_concentration_mol_per_m3=NOMINAL_FEED_CONCENTRATION,
        initial_concentration_mol_per_m3=NOMINAL_FEED_CONCENTRATION,
        initial_temperature_k=340.0,
        end_time_s=600.0,
        predicted_convergence="converged",
        predicted_usable=True,
        predicted_levels=(NUM, ANA, XSOL),
        measure_stiffness=True,
        stiffness_ratio_band=(20.0, None),
        failure_case="E",
        prediction_note=(
            "materially stiff: the explicit probe needs at least twenty times "
            "the work of BDF while both complete"
        ),
    ),
    RegimeSpec(
        regime_id="R3",
        name="strongly stiff adiabatic ignition",
        category="strongly_stiff",
        rationale=(
            "Adiabatic at a 2.6 mol/L feed. The adiabatic rise is about 544 K, "
            "taking the reactor to roughly 894 K — inside the model's declared "
            "1000 K envelope, but with a rate constant many orders above the "
            "flow rate. A scientifically valid problem that is numerically "
            "punishing."
        ),
        coolant_temperature_k=300.0,   # unused: UA = 0
        ua_w_per_k=0.0,
        feed_temperature_k=NOMINAL_FEED_TEMPERATURE,
        feed_concentration_mol_per_m3=2600.0,
        initial_concentration_mol_per_m3=2600.0,
        initial_temperature_k=NOMINAL_FEED_TEMPERATURE,
        end_time_s=600.0,
        predicted_convergence="converged",
        predicted_usable=True,
        predicted_levels=(NUM, ANA, XSOL),
        measure_stiffness=True,
        # A lower bound only: the probe is predicted to exhaust its budget, so
        # the true ratio is unbounded above and the measurement is a floor.
        stiffness_ratio_band=(200.0, None),
        failure_case="E",
        prediction_note=(
            "strongly stiff: BDF completes in a few thousand evaluations while "
            "the explicit probe exhausts a five-million-evaluation budget "
            "without finishing, so the measured ratio is a lower bound"
        ),
    ),
    RegimeSpec(
        regime_id="R5",
        name="computational limit exhausted mid-integration",
        category="failure_prone",
        rationale=(
            "R3's physics under a deliberately tight 500-evaluation budget. "
            "Nothing is wrong with the problem or the method; the run is "
            "stopped by an explicit computational limit while still making "
            "progress. This must be distinguishable from a method that failed."
        ),
        coolant_temperature_k=300.0,
        ua_w_per_k=0.0,
        feed_temperature_k=NOMINAL_FEED_TEMPERATURE,
        feed_concentration_mol_per_m3=2600.0,
        initial_concentration_mol_per_m3=2600.0,
        initial_temperature_k=NOMINAL_FEED_TEMPERATURE,
        end_time_s=600.0,
        rhs_budget=CONSTRAINED_RHS_BUDGET,
        predicted_convergence="max_iterations",
        predicted_usable=False,
        predicted_levels=(),
        run_verification_gate=False,
        failure_case="A",
        prediction_note=(
            "MAX_ITERATIONS, no metrics extracted, the partial trajectory "
            "preserved in the raw diagnostics, and the fraction of the horizon "
            "completed recorded"
        ),
    ),
    RegimeSpec(
        regime_id="R6a",
        name="steady-state multiplicity, cold start",
        category="branch_sensitive",
        rationale=(
            "Tc = 300 K sits inside the multiplicity window: the independent "
            "algebraic solver finds three steady states. Started cold."
        ),
        coolant_temperature_k=300.0,
        ua_w_per_k=NOMINAL_UA_W_PER_K,
        feed_temperature_k=NOMINAL_FEED_TEMPERATURE,
        feed_concentration_mol_per_m3=NOMINAL_FEED_CONCENTRATION,
        initial_concentration_mol_per_m3=NOMINAL_FEED_CONCENTRATION,
        initial_temperature_k=300.0,
        end_time_s=3600.0,
        predicted_convergence="converged",
        predicted_usable=True,
        predicted_levels=(NUM, XSOL),
        failure_case="E",
        prediction_note=(
            "three algebraic steady states exist; the trajectory settles on "
            "the low-conversion branch"
        ),
    ),
    RegimeSpec(
        regime_id="R6b",
        name="steady-state multiplicity, hot start",
        category="branch_sensitive",
        rationale=(
            "Identical physics to R6a from a 450 K start. The pair is the test "
            "of whether the initial condition selects a different branch."
        ),
        coolant_temperature_k=300.0,
        ua_w_per_k=NOMINAL_UA_W_PER_K,
        feed_temperature_k=NOMINAL_FEED_TEMPERATURE,
        feed_concentration_mol_per_m3=NOMINAL_FEED_CONCENTRATION,
        initial_concentration_mol_per_m3=NOMINAL_FEED_CONCENTRATION,
        initial_temperature_k=450.0,
        end_time_s=3600.0,
        predicted_convergence="converged",
        predicted_usable=True,
        predicted_levels=(NUM, XSOL),
        failure_case="E",
        prediction_note=(
            "the hot start overshoots hard and then falls to the SAME "
            "low-conversion branch as R6a: in this parameterization the upper "
            "algebraic branch is unstable, so three steady states do not mean "
            "two attractors"
        ),
    ),
    RegimeSpec(
        regime_id="R7",
        name="sustained oscillation, no stable steady state",
        category="branch_sensitive",
        rationale=(
            "At Tc = 305 K the single algebraic steady state has a positive "
            "Jacobian trace with a positive determinant — an unstable focus. "
            "The reactor has no stable steady state and cycles indefinitely. "
            "The end state of a successful integration is therefore not an "
            "answer to 'what does this reactor do', and the study records "
            "whether the contracts notice."
        ),
        coolant_temperature_k=305.0,
        ua_w_per_k=NOMINAL_UA_W_PER_K,
        feed_temperature_k=NOMINAL_FEED_TEMPERATURE,
        feed_concentration_mol_per_m3=NOMINAL_FEED_CONCENTRATION,
        initial_concentration_mol_per_m3=NOMINAL_FEED_CONCENTRATION,
        initial_temperature_k=300.0,
        end_time_s=6000.0,
        n_output_points=20001,
        predicted_convergence="converged",
        # The per-solve report cannot see the problem: the trajectory is finite,
        # inside the envelope, and the integrator succeeded. is_usable is
        # predicted TRUE, and the gate is predicted to award nothing.
        predicted_usable=True,
        predicted_levels=(),
        failure_case="D",
        prediction_note=(
            "the per-solve report passes and the verification gate awards "
            "NOTHING: the reported end state is a phase of a limit cycle, so "
            "it is not tolerance independent and the trajectory is not "
            "stationary. Execution success and scientific usability separate "
            "here without any numerical fault"
        ),
    ),
    RegimeSpec(
        regime_id="R8",
        name="flawless integration outside the model envelope",
        category="unusable_result",
        rationale=(
            "Adiabatic at a 4 mol/L feed. The adiabatic rise is about 837 K, "
            "taking the reactor past 1180 K — outside the model's declared "
            "250-1000 K validity envelope, where the constant-property, "
            "single-phase, no-boiling assumptions do not hold. The integration "
            "is impeccable; the answer is not usable."
        ),
        coolant_temperature_k=300.0,
        ua_w_per_k=0.0,
        feed_temperature_k=NOMINAL_FEED_TEMPERATURE,
        feed_concentration_mol_per_m3=4000.0,
        initial_concentration_mol_per_m3=4000.0,
        initial_temperature_k=NOMINAL_FEED_TEMPERATURE,
        end_time_s=300.0,
        predicted_convergence="converged",
        predicted_usable=False,
        predicted_levels=(),
        run_verification_gate=False,
        failure_case="D",
        prediction_note=(
            "CONVERGED with a FAILing state_physically_admissible check, so "
            "is_usable is False while convergence correctly remains CONVERGED. "
            "The two statements are independent and both are true"
        ),
    ),
)


# =====================================================================
# 4. R4 — declarations that must never reach a solver
# =====================================================================

@dataclass(frozen=True)
class InvalidDeclaration:
    """One declaration expected to be refused at the envelope boundary."""

    label: str
    kind: str            # "chemistry" | "operation" | "run" | "integration"
    overrides: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "kind": self.kind,
            "overrides": {k: repr(v) for k, v in self.overrides.items()},
            "reason": self.reason,
        }


#: R4. Each of these must raise ReactorConfigurationError at construction —
#: BEFORE any integration is attempted. An input outside the envelope is not a
#: solve that failed; it is a solve that must never run.
INVALID_DECLARATIONS: tuple[InvalidDeclaration, ...] = (
    InvalidDeclaration(
        label="negative_absolute_temperature",
        kind="operation",
        overrides={"feed_temperature": Quantity(-10.0, "kelvin")},
        reason=(
            "exp(-E/(R T)) has an essential singularity at T = 0 and no "
            "meaning below it"
        ),
    ),
    InvalidDeclaration(
        label="temperature_above_envelope",
        kind="operation",
        overrides={"feed_temperature": Quantity(1500.0, "kelvin")},
        reason=(
            "outside the model's declared 250-1000 K single-phase "
            "constant-property envelope"
        ),
    ),
    InvalidDeclaration(
        label="temperature_below_envelope",
        kind="operation",
        overrides={"coolant_temperature": Quantity(200.0, "kelvin")},
        reason="below the declared envelope; the liquid phase is not assured",
    ),
    InvalidDeclaration(
        label="negative_feed_concentration",
        kind="operation",
        overrides={"feed_concentration": Quantity(-1.0, "mol/m**3")},
        reason="a negative concentration is not a state of the system",
    ),
    InvalidDeclaration(
        label="zero_volume",
        kind="operation",
        overrides={"volume": Quantity(0.0, "m**3")},
        reason="a zero-volume tank has no residence time",
    ),
    InvalidDeclaration(
        label="negative_flow_rate",
        kind="operation",
        overrides={"flow_rate": Quantity(-1.0e-3, "m**3/s")},
        reason="reversed flow is not the modelled configuration",
    ),
    InvalidDeclaration(
        label="negative_ua",
        kind="operation",
        overrides={"ua": Quantity(-100.0, "W/K")},
        reason="a negative UA would pump heat up its own gradient",
    ),
    InvalidDeclaration(
        label="non_positive_k0",
        kind="chemistry",
        overrides={"k0": Quantity(0.0, "1/s")},
        reason="a zero pre-exponential factor is not an Arrhenius rate",
    ),
    InvalidDeclaration(
        label="negative_activation_energy",
        kind="chemistry",
        overrides={"activation_energy": Quantity(-1.0e4, "J/mol")},
        reason=(
            "a negative barrier makes the rate fall with temperature, which "
            "is not the Arrhenius model"
        ),
    ),
    InvalidDeclaration(
        label="non_positive_density",
        kind="chemistry",
        overrides={"density": Quantity(0.0, "kg/m**3")},
        reason="a zero density gives an infinite temperature response",
    ),
    InvalidDeclaration(
        label="negative_initial_concentration",
        kind="run",
        overrides={"initial_concentration": Quantity(-5.0, "mol/m**3")},
        reason="a negative initial concentration is not a state of the system",
    ),
    InvalidDeclaration(
        label="initial_temperature_outside_envelope",
        kind="run",
        overrides={"initial_temperature": Quantity(1200.0, "kelvin")},
        reason="starting outside the envelope the model does not cover",
    ),
    InvalidDeclaration(
        label="bare_number_instead_of_quantity",
        kind="operation",
        overrides={"feed_temperature": 350.0},
        reason=(
            "a bare number is not a declaration: it carries no unit and "
            "cannot be dimension-checked"
        ),
    ),
    InvalidDeclaration(
        label="wrong_dimension_for_temperature",
        kind="operation",
        overrides={"feed_temperature": Quantity(350.0, "pascal")},
        reason="a pressure is not a temperature",
    ),
    InvalidDeclaration(
        label="unknown_integration_method",
        kind="integration",
        overrides={"method": "LSODA"},
        reason=(
            "LSODA switches between stiff and non-stiff internally, so a work "
            "count from it cannot be attributed to one method and would "
            "corrupt the stiffness measurement"
        ),
    ),
    InvalidDeclaration(
        label="non_positive_rtol",
        kind="integration",
        overrides={"rtol": 0.0},
        reason="a zero relative tolerance is not achievable",
    ),
)


# =====================================================================
# 5. Metrics recorded for every regime
# =====================================================================

METRICS = (
    "solver_id",
    "solver_version",
    "solver_backend",
    "integration_method",
    "convergence_state",
    "is_usable",
    "validation_status",
    "attained_levels_per_solve",
    "attained_levels_gate",
    "failure_classification",
    "rhs_evaluations",
    "scipy_nfev",
    "scipy_njev",
    "scipy_nlu",
    "accepted_steps",
    "wall_seconds_telemetry",
    "fraction_of_horizon_completed",
    "final_concentration_mol_per_m3",
    "final_temperature_k",
    "peak_temperature_k",
    "conversion",
    "min_concentration_mol_per_m3",
    "max_temperature_k",
    "rtol",
    "atol_concentration",
    "atol_temperature",
    "rhs_budget",
    "tolerance_ladder_final_relative_change",
    "invariant_max_relative_error",
    "steady_state_relative_error",
    "steady_states_found",
    "cross_method_max_relative_difference",
    "stiffness_work_ratio",
    "physics_fingerprint",
    "provenance_run_id",
)

#: Wall-clock is recorded as telemetry and is never a scientific score. The
#: reproducible cost figure in this domain is the right-hand-side evaluation
#: count, which is deterministic for a fixed declaration.
COST_MEASURE = "rhs_evaluations"

# =====================================================================
# 6. The failure-semantics matrix — the actual subject of K1
# =====================================================================

#: Each distinguishable outcome, the regime that produces it, and the existing
#: Core vocabulary it is predicted to map onto. A case that cannot be
#: represented without discarding evidence is a Core finding; this table is
#: what makes that checkable rather than a matter of opinion.
FAILURE_SEMANTICS_MATRIX = {
    "A_solver_execution_failure": {
        "regime": "R5",
        "predicted_convergence": "max_iterations",
        "predicted_is_usable": False,
        "predicted_metrics_present": False,
        "why_this_enum": (
            "MAX_ITERATIONS means the backend stopped at a work cap. An "
            "explicit right-hand-side evaluation budget is exactly that, and "
            "FAILED would wrongly imply the method or the problem was at "
            "fault when neither was"
        ),
    },
    "B_numerical_non_convergence": {
        "regime": "not produced by any preregistered regime",
        "predicted_convergence": "not_converged",
        "predicted_is_usable": False,
        "predicted_metrics_present": False,
        "why_this_enum": (
            "reserved for SciPy status -1, step-size collapse. NO regime in "
            "this study can reach it, and that is a result rather than a gap: "
            "the CSTR system is globally bounded, because the Arrhenius factor "
            "saturates at k0 and the reactant is consumed, so the model "
            "contains no finite-time singularity for any admissible "
            "parameters. The adapter's classification is therefore exercised "
            "directly, by injecting a genuine finite-time singularity "
            "(dT/dt += T**2) into the right-hand side. Claiming a regime "
            "produced case B when none did would be the dishonest option"
        ),
    },
    "C_physically_invalid_input": {
        "regime": "R4",
        "predicted_convergence": "no solve is attempted",
        "predicted_is_usable": False,
        "predicted_metrics_present": False,
        "why_this_enum": (
            "refused by the domain at the declaration boundary. This must NOT "
            "become a ConvergenceState: nothing converged or failed to "
            "converge, because nothing ran"
        ),
    },
    "D_successful_but_unusable": {
        "regime": "R8 (envelope exit) and R7 (no stable steady state)",
        "predicted_convergence": "converged",
        "predicted_is_usable": "False for R8, True for R7",
        "predicted_metrics_present": True,
        "why_this_enum": (
            "the two are deliberately different. R8's trajectory leaves the "
            "model's envelope, which a single solve CAN see, so its per-solve "
            "check fails and is_usable goes False. R7's trajectory is "
            "impeccable point by point and only the verification gate can see "
            "that its end state means nothing, so is_usable stays True and "
            "the gate awards no level. If these collapsed into one state, one "
            "of them would be a lie"
        ),
    },
    "E_valid_result": {
        "regime": "R1, R2, R3, R6a, R6b",
        "predicted_convergence": "converged",
        "predicted_is_usable": True,
        "predicted_metrics_present": True,
        "why_this_enum": "converged, inside the envelope, no failing check",
    },
}

# =====================================================================
# 7. Acceptance criteria
# =====================================================================

ACCEPTANCE_CRITERIA = (
    "A1 R1 completes through the full five-stage contract with CONVERGED, "
    "is_usable True, and metrics carrying mol/m**3, kelvin, seconds and "
    "dimensionless",
    "A2 R2 and R3 complete and are shown to be materially stiff by measurement: "
    "their RK45/BDF evaluation ratios fall inside their preregistered bands, "
    "and R1's ratio falls inside its band showing it is NOT stiff",
    "A3 R5 ends as MAX_ITERATIONS with no metrics extracted and its partial "
    "trajectory preserved, through a genuine computational limit rather than a "
    "mocked failure",
    "A4 every regime's convergence state and its is_usable verdict are "
    "independent: R8 is CONVERGED and not usable, and R7 is CONVERGED and "
    "usable while its verification gate awards nothing",
    "A5 every declaration in R4 is refused by the domain before any solve, and "
    "the Scientific Core contains no CSTR-specific validity rule",
    "A6 the verification gate awards ANALYTICALLY_VERIFIED on at least one "
    "regime from the exact reaction-free invariant, and CROSS_SOLVER_VALIDATED "
    "on at least one regime from the independent algebraic steady state",
    "A7 the five failure-semantics cases A-E are each represented by a "
    "distinct combination of existing Core states, with no two collapsed",
    "A8 no regime is awarded NUMERICALLY_CONVERGED by a single solve; every "
    "such award comes from the tolerance ladder",
    "A9 R6a and R6b reach the same attractor despite three algebraic steady "
    "states existing, and the independent solver reports all three",
    "A10 every result carries a complete provenance record: model identity and "
    "version, solver identity and version, method, tolerances, every input as "
    "a Quantity, and the physics fingerprint",
)

FALSIFICATION_CRITERIA = (
    "F1 if the Scientific Core requires any CSTR-specific branching, K1 is at "
    "best PASS WITH CORE CORRECTION and the branch must be reported",
    "F2 if a meaningful scientific failure cannot be represented without "
    "discarding evidence — in particular if R5's partial trajectory or R8's "
    "envelope violation has nowhere honest to live — that is a Core finding",
    "F3 if a successful solve is automatically promoted to any validation "
    "level above DIMENSIONALLY_VALID, the validation contract is unsound",
    "F4 if an invalid physical state can enter an admitted ScientificResult — "
    "for example if R8 were reported usable, or if a non-finite value reached "
    "a Quantity — that is a Core finding",
    "F5 if any historical frozen artifact must be changed, K1 fails",
    "F6 if the domain requires a large generic framework invented before the "
    "evidence for it, K1 fails on architecture creep",
    "F7 if the independent algebraic steady state materially disagrees with a "
    "converged, stationary production result, the production path is wrong "
    "and must be reported as wrong",
    "F8 if the experiment cannot be reproduced from a clean clone, K1 fails",
)

NO_TUNING_AFTER_RESULTS = (
    "the chemistry, regimes, initial conditions, horizons, method, tolerances, "
    "budgets, verification-gate thresholds, predictions and acceptance bands "
    "above are fixed before the scored execution and are not adjusted "
    "afterwards. A missed band is reported as a missed band. If a setup bug is "
    "found, the run is invalidated, the bug and the correction are documented, "
    "the experiment version is incremented, and the study is rerun from "
    "scratch — never silently patched"
)

NON_GOALS = (
    "no inference of any kind: no Bayesian posterior, no MCMC, no variational "
    "inference, no parameter estimation",
    "no optimization, no acquisition function, no experiment selection",
    "no generic chemistry ontology, no generic uncertainty engine, no generic "
    "domain framework, no surrogate model",
    "no multiphysics coupling, no digital twin, no visualization",
    "no modification to T1, T2, T3, E1, E2, E3, S11 or any other frozen "
    "experiment, all of which are pinned by digest and are not re-run here",
    "no physical validation: nothing in K1 is compared against a measurement "
    "of a real reactor, and no claim about one is made",
    "no LLM-supplied numerical result: every number in the results is produced "
    "by the code in this repository from the declarations above",
)

# =====================================================================
# 8. Verification-gate thresholds, restated for the record
# =====================================================================

#: Imported from the domain rather than restated as literals, so the
#: preregistration hash changes if the gate changes. These are DECLARED
#: thresholds informed by exploratory analysis, not preregistered ones — see
#: the domain's validation module docstring and this package's __init__.
GATE_THRESHOLDS = {
    "tolerance_rel_tol": TOLERANCE_REL_TOL,
    "invariant_rel_tol": INVARIANT_REL_TOL,
    "steady_state_rel_tol": STEADY_STATE_REL_TOL,
    "stationarity_rel_tol": STATIONARITY_REL_TOL,
    "tolerance_ladder": [rung.to_dict() for rung in TOLERANCE_LADDER],
    "provenance": (
        "declared after exploratory feasibility analysis; the invariant and "
        "steady-state tolerances were TIGHTENED from 1e-6 to 1e-9 because "
        "exploration showed the residuals sit near 1e-15 and a 1e-6 gate "
        "could not have failed"
    ),
}


# =====================================================================
# 9. Errata against the frozen preregistration
# =====================================================================

#: Corrections to text that is INSIDE the hashed preregistration payload and
#: therefore cannot be edited without breaking the freeze.
#:
#: This constant is deliberately NOT referenced by :func:`config_payload`. If it
#: were, recording an erratum would change the preregistration hash, which is
#: the one thing a frozen artifact must never do. The frozen text stays wrong
#: and stays hashed; the correction lives beside it and is carried into the
#: report. A test asserts the hash is unaffected by this constant existing.
#:
#: Nothing here changes a number, a threshold, a regime or a result. Every
#: erratum is a statement about wording.
PREREGISTRATION_ERRATA = (
    {
        "field": "integration.method_justification",
        "frozen_text_says": (
            "BDF: ... L-stable, the standard choice for stiff chemical "
            "kinetics"
        ),
        "correction": (
            "BDF is A-stable only at orders 1-2 and A(alpha)-stable at the "
            "higher orders SciPy uses, so it is NOT L-stable at every order it "
            "runs at. The accurate justification is that BDF is stiffly stable "
            "in Gear's sense: its stability region contains the whole negative "
            "real axis and a wedge around it, which is why it is the standard "
            "choice for stiff chemical kinetics. Radau IIA is A-stable and "
            "L-stable, so that half of the frozen sentence is correct."
        ),
        "affects_any_result": False,
        "why_not_rewritten": (
            "the sentence is inside the hashed preregistration payload; "
            "editing it would change config_hash and break the freeze that "
            "makes 'these results came from that configuration' checkable"
        ),
    },
)


def config_payload() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "experiment_version": K1_VERSION,
        "base_commit": BASE_COMMIT,
        "scientific_question": SCIENTIFIC_QUESTION,
        "preregistration_kind": (
            "feasibility-informed: an exploratory pass established which "
            "regimes exist and the scale of every residual before these "
            "numbers were written down. The bands were then set outside those "
            "observations and frozen. The discipline that carries weight here "
            "is the no-tuning rule, not blindness"
        ),
        "customary_parameters": dict(CUSTOMARY_PARAMETERS),
        "parameter_provenance": (
            "the widely used textbook non-isothermal CSTR parameterization, "
            "transcribed to SI here. The transcription has NOT been checked "
            "against the printed source, and no K1 conclusion depends on it "
            "having been: these are simply the declared, frozen inputs"
        ),
        "chemistry": CHEMISTRY.to_dict(),
        "base_operation": {
            "volume_m3": VOLUME_M3,
            "flow_m3_per_s": FLOW_M3_PER_S,
            "nominal_ua_w_per_k": NOMINAL_UA_W_PER_K,
            "nominal_feed_concentration_mol_per_m3":
                NOMINAL_FEED_CONCENTRATION,
            "nominal_feed_temperature_k": NOMINAL_FEED_TEMPERATURE,
            "residence_time_s": VOLUME_M3 / FLOW_M3_PER_S,
        },
        "integration": {
            "production_method": PRODUCTION_METHOD,
            "cross_method": CROSS_METHOD,
            "stiffness_probe_method": STIFFNESS_PROBE_METHOD,
            "production_rtol": PRODUCTION_RTOL,
            "production_atol_concentration": PRODUCTION_ATOL_CONCENTRATION,
            "production_atol_temperature": PRODUCTION_ATOL_TEMPERATURE,
            "standard_rhs_budget": STANDARD_RHS_BUDGET,
            "constrained_rhs_budget": CONSTRAINED_RHS_BUDGET,
            "stiffness_probe_budget": STIFFNESS_PROBE_BUDGET,
            "method_justification": (
                "BDF: variable-order backward differentiation with an analytic "
                "Jacobian, L-stable, the standard choice for stiff chemical "
                "kinetics. Radau: 5th-order Radau IIA, a different (one-step, "
                "fully implicit) family, also L-stable, used as the "
                "cross-method arm. RK45: explicit, used ONLY as a measuring "
                "instrument for stiffness. LSODA is excluded because its "
                "internal stiff/non-stiff switching makes its work count "
                "unattributable"
            ),
        },
        "regimes": [regime.to_dict() for regime in REGIMES],
        "invalid_declarations": [d.to_dict() for d in INVALID_DECLARATIONS],
        "failure_semantics_matrix": FAILURE_SEMANTICS_MATRIX,
        "metrics": list(METRICS),
        "cost_measure": COST_MEASURE,
        "gate_thresholds": GATE_THRESHOLDS,
        "acceptance_criteria": list(ACCEPTANCE_CRITERIA),
        "falsification_criteria": list(FALSIFICATION_CRITERIA),
        "no_tuning_after_results": NO_TUNING_AFTER_RESULTS,
        "non_goals": list(NON_GOALS),
        "randomness": (
            "none. K1 contains no stochastic component, so there is no seed to "
            "declare. Every number is a deterministic function of the "
            "declarations above and the pinned library versions"
        ),
    }


def config_hash() -> str:
    blob = json.dumps(config_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def regime(regime_id: str) -> RegimeSpec:
    for spec in REGIMES:
        if spec.regime_id == regime_id:
            return spec
    raise KeyError(f"no regime {regime_id!r}")
