"""Adversarial cases at and beyond each model's true scientific boundary.

Every case here is *physically valid as a declaration* -- the numbers are real
numbers a real caller could write down, and the runtime accepts them. The
question each case asks is the one this round exists for: given that the record
and the runtime agree, and the tests pass, is the answer scientifically
trustworthy in this regime?

Each case names an oracle that does not share code with the model under test,
because a model cannot be its own evidence. The oracle types used:

INVARIANT       an exact conserved quantity of the same equations, derived by
                hand and independent of the implementation
SIGN/DOMAIN     the physical admissibility of the quantity itself -- a
                resistance is positive, an elapsed time to a future event is
                non-negative
SIBLING_RECORD  a bound the repository itself declares elsewhere for the same
                physics, which is evidence of intent rather than of physics
                and is cited as such

Runtime response is classified exactly as the round specifies:

A  REFUSE          the declaration is rejected
B  UNKNOWN         the model declines to answer
C  WARNED NUMBER   a number, with the limitation visible on the result
D  SUPPORTED       a normal-looking supported result
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent
REPO = ROUND.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from engcore.scientific.units.quantity import Quantity as Q  # noqa: E402

REFUSE, UNKNOWN, WARNED, SUPPORTED = "A_REFUSE", "B_UNKNOWN", "C_WARNED_NUMBER", "D_SUPPORTED"


def _status(assessment) -> str:
    name = assessment.status.name
    if name == "OUTSIDE_VALIDATED_DOMAIN":
        return REFUSE
    if name == "UNKNOWN":
        return UNKNOWN
    return SUPPORTED


# ---------------------------------------------------------------------
# CB-1  electrical.material.linear_tcr_resistance
# ---------------------------------------------------------------------
def case_tcr_zero_crossing() -> dict:
    """A line that crosses zero inside the model's own declared 200-450 K band.

    The declaration is the one the record's own input description invites: a
    semiconductor or alloy read off a local tangent, with a negative alpha.
    """
    from engcore.domains.electrical import material as M

    conductor = M.TemperatureDependentConductor(
        component_id="S1",
        reference_resistance=Q(1000.0, "ohm"),
        temperature_coefficient=Q(-0.01, "1 / kelvin"),
        reference_temperature=Q(300.0, "kelvin"),
        limits=M.MaterialLimits(),
    )
    problem = M.build_resistance_problem(conductor)
    probes = []
    for kelvin in (380.0, 400.0, 420.0):
        assessment = M.assess_resistance_validity(problem, Q(kelvin, "kelvin"))
        solver = M.ResistancePropertySolver()
        solver.bind_conductor(conductor, problem.problem_id, temperature=Q(kelvin, "kelvin"))
        prepared = solver.prepare(problem)
        raw = solver.solve(prepared)
        metrics = solver.extract_metrics(prepared, raw)
        report = solver.validate(prepared, raw)
        probes.append(
            {
                "temperature_K": kelvin,
                "multiplier_1_plus_alpha_dT": 1.0 + (-0.01) * (kelvin - 300.0),
                "resistance_ohm": metrics["resistance"].magnitude_in("ohm"),
                "model_validity": assessment.status.name,
                "conditions_violated": list(assessment.violated),
                "solver_report": report.status.value,
                "response": _status(assessment),
            }
        )
    worst = probes[-1]
    return {
        "id": "CB-1",
        "as_found": {
            "verdict": "IN_DOMAIN",
            "response_class": SUPPORTED,
            "detail": (
                "before the fix, all conditions SATISFIED at 380 K, 400 K "
                "and 420 K, including the two where the model's own "
                "expression returns 0.0 and -200.0 ohm"
            ),
        },
        "fix": (
            "a linear_resistance_ratio > 0 condition on the unrated "
            "record, reserved as a derived quantity and assembled from "
            "the three inputs the record already requires. The rated "
            "sibling already stated the same bound; the derivation "
            "function already existed. UNKNOWN unless a temperature is "
            "supplied."
        ),
        "regression_guard": (
            "benchmarks/capability_boundary/tests/test_capability_boundary.py"
            "::test_the_linear_tcr_model_refuses_a_line_that_has_crossed_zero"
        ),
        "model": "electrical.material.linear_tcr_resistance",
        "physically_valid_input": (
            "R_ref = 1000 ohm at T_ref = 300 K, alpha = -0.01 /K, evaluated at "
            "T = 420 K. Every value is inside the model's own declared "
            "200-450 K range, and a negative alpha is a case the record's "
            "input description explicitly admits and describes."
        ),
        "why_out_of_regime": (
            "R(T) = R_ref (1 + alpha (T - T_ref)) is a straight line, and every "
            "straight line with a non-zero slope crosses zero. Past the "
            "crossing the expression does not describe a poor conductor but a "
            "negative one, which is not a conductor resistance at all."
        ),
        "oracle": {
            "type": "SIGN/DOMAIN, corroborated by SIBLING_RECORD",
            "independence": (
                "The sign constraint is a property of the quantity, not of any "
                "implementation, and is evaluated here in arithmetic that does "
                "not call the model. The sibling record "
                "electrical.material.rated_linear_tcr_resistance independently "
                "declares the same bound and states its own reason for it."
            ),
            "domain_of_validity": "every temperature and every material",
            "expected": "R > 0, or a refusal",
            "sibling_quote": (
                "'1 + alpha (T - T_ref) > 0. Every straight line with a "
                "non-zero slope crosses zero; past the crossing the form does "
                "not describe a poor conductor but a negative one. The bound "
                "is the physics of the quantity, not a tolerance.'"
            ),
        },
        "probes": probes,
        "runtime_result": f"R = {worst['resistance_ohm']:.1f} ohm",
        "verdict": worst["model_validity"],
        "reason_text": "every condition SATISFIED; no condition names the multiplier",
        "response_class": worst["response"],
        "expected_safe_behavior": (
            "OUTSIDE_VALIDATED_DOMAIN on a condition over 1 + alpha (T - T_ref), "
            "the same bound the rated sibling already declares."
        ),
        "mitigation_present": (
            "The solver's own admissibility check does report FAIL on the "
            "computed number, so this is not a silent wrong answer. What is "
            "wrong is the applicability verdict, which a caller uses to decide "
            "whether to run at all -- the module's own comment draws exactly "
            "that distinction."
        ),
    }


# ---------------------------------------------------------------------
# CB-2  kinetics.cstr.nonisothermal_first_order_constant_rate
# ---------------------------------------------------------------------
def case_cstr_constant_rate_ceiling() -> dict:
    """A declaration whose exact invariant ceiling is far outside the envelope."""
    from engcore.domains.kinetics.cstr.alternatives import CONSTANT_RATE_CSTR_MODEL as K4
    from engcore.domains.kinetics.cstr.problem import (
        CSTR_MODEL,
        ReactorChemistry,
        ReactorOperation,
        ReactorRun,
    )

    chemistry = ReactorChemistry(
        k0=Q(0.05, "1 / second"),
        activation_energy=Q(0.0, "joule / mole"),
        heat_of_reaction=Q(-5.0e5, "joule / mole"),
        density=Q(1000.0, "kilogram / meter ** 3"),
        heat_capacity=Q(239.0, "joule / kelvin / kilogram"),
    )
    operation = ReactorOperation(
        volume=Q(0.1, "meter ** 3"),
        flow_rate=Q(0.1 / 60.0, "meter ** 3 / second"),
        feed_concentration=Q(1000.0, "mole / meter ** 3"),
        feed_temperature=Q(350.0, "kelvin"),
        coolant_temperature=Q(300.0, "kelvin"),
        ua=Q(5.0e4, "watt / kelvin"),
        end_time=Q(600.0, "second"),
    )
    run = ReactorRun(
        run_label="R",
        chemistry=chemistry,
        operation=operation,
        initial_concentration=Q(1000.0, "mole / meter ** 3"),
        initial_temperature=Q(350.0, "kelvin"),
    )
    context = run.validity_context()
    ceiling = context.assembled["adiabatic_ceiling_temperature"].magnitude_in("kelvin")

    primary = context.assess(CSTR_MODEL)
    # Everything the constant-rate record can see, supplied in full so that no
    # condition is UNKNOWN by omission.
    k4 = K4.assess_validity(
        declared={
            "k_const": Q(0.05, "1 / second"),
            "residence_time": Q(360.0, "second"),
        },
        assembled={
            key: value
            for key, value in context.assembled.items()
            if key in K4.derived_quantities
        },
    )

    # Independent oracle, computed here without calling either model.
    beta = 5.0e5 / (1000.0 * 239.0)
    hand_ceiling = max(350.0, 350.0, 300.0) + beta * max(1000.0, 1000.0)
    return {
        "id": "CB-2",
        "as_found": {
            "verdict": "IN_DOMAIN",
            "response_class": SUPPORTED,
            "detail": (
                "before the fix, all four conditions SATISFIED for a "
                "declaration whose exact invariant ceiling is 2442 K, "
                "while the primary model refused the identical one"
            ),
        },
        "fix": (
            "an adiabatic_ceiling_temperature <= 1000 K condition on the "
            "constant-rate record, reserved as a derived quantity. The "
            "CSTR assembler already computed the value and already placed "
            "it in the context this model is assessed against; the model "
            "simply did not reserve it and so could never read it."
        ),
        "regression_guard": (
            "benchmarks/capability_boundary/tests/test_capability_boundary.py"
            "::test_both_cstr_models_refuse_a_declaration_whose_ceiling_"
            "leaves_the_envelope"
        ),
        "model": "kinetics.cstr.nonisothermal_first_order_constant_rate",
        "physically_valid_input": (
            "A strongly exothermic liquid-phase feed: dH = -500 kJ/mol, "
            "C_A0 = C_Af = 1000 mol/m3, rho = 1000 kg/m3, c_p = 239 J/kg/K, "
            "T_0 = T_f = 350 K, T_c = 300 K, k_const = 0.05 /s. Every declared "
            "value is ordinary and every one of the model's own conditions is "
            "satisfied."
        ),
        "why_out_of_regime": (
            f"The reactor's exact invariant guarantees the contents can reach "
            f"{hand_ceiling:.0f} K. The model's own temperature condition "
            f"declares 250-1000 K, its assumptions declare a single liquid "
            f"phase with no boiling, and its validity description claims the "
            f"'Same single-phase CSTR envelope as the primary model'."
        ),
        "oracle": {
            "type": "INVARIANT",
            "independence": (
                "Z = T + beta C_A is derived by hand from the two balances and "
                "evaluated here in plain arithmetic. Adding beta times the "
                "species balance to the energy balance cancels the reaction "
                "term identically -- dZ/dt = (Z_f - Z)/tau - gamma (T - T_c) "
                "contains no k -- so the bound holds for ANY rate law, "
                "Arrhenius or constant, and does not depend on either model's "
                "implementation."
            ),
            "domain_of_validity": (
                "exact for these balances, with or without cooling, because "
                "C_A >= 0 and C_A <= max(C_A0, C_Af)"
            ),
            "expected": "T <= max(T_0, T_f, T_c) + beta max(C_A0, C_Af)",
            "hand_computed_ceiling_K": hand_ceiling,
            "runtime_computed_ceiling_K": ceiling,
            "agreement": abs(hand_ceiling - ceiling) < 1.0,
        },
        "probes": [
            {
                "model": "kinetics.cstr.nonisothermal_first_order",
                "model_validity": primary.status.name,
                "conditions_violated": list(primary.violated),
                "response": _status(primary),
            },
            {
                "model": "kinetics.cstr.nonisothermal_first_order_constant_rate",
                "model_validity": k4.status.name,
                "conditions_satisfied": list(k4.satisfied),
                "conditions_violated": list(k4.violated),
                "response": _status(k4),
            },
        ],
        "runtime_result": (
            f"primary model refuses on adiabatic_ceiling_temperature; the "
            f"constant-rate sibling reports {k4.status.name} on the identical "
            f"declaration"
        ),
        "verdict": k4.status.name,
        "reason_text": "all four conditions SATISFIED; the ceiling is not among them",
        "response_class": _status(k4),
        "expected_safe_behavior": (
            "the same OUTSIDE_VALIDATED_DOMAIN the primary model returns; the "
            "quantity is already computed and already present in the context "
            "this model is assessed against"
        ),
        "mitigation_present": "none on the validity surface",
    }


# ---------------------------------------------------------------------
# CB-3  battery.cell.constant_current_runtime
# ---------------------------------------------------------------------
def case_runtime_cutoff_behind_start() -> dict:
    """A cutoff declared above the starting state of charge."""
    from engcore.domains.battery.cell import (
        CellSpecification,
        DischargeLoad,
        assess_runtime_validity,
        build_battery_problem,
    )
    from engcore.domains.battery.context import CellLimits
    from engcore.domains.battery.solver import evaluate_step

    limits = CellLimits(
        usable_soc_minimum=Q(0.05, "dimensionless"),
        usable_soc_maximum=Q(0.95, "dimensionless"),
        continuous_discharge_c_rate=Q(2.0, "1 / hour"),
    )
    cell = CellSpecification(
        cell_id="C",
        nominal_capacity=Q(2.5, "ampere_hour"),
        internal_resistance=Q(0.035, "ohm"),
        open_circuit_voltage_at_full=Q(4.2, "volt"),
        open_circuit_voltage_at_empty=Q(3.0, "volt"),
        coulombic_efficiency=Q(1.0, "dimensionless"),
        limits=limits,
    )
    load = DischargeLoad(
        load_id="L",
        current=Q(1.0, "ampere"),
        initial_state_of_charge=Q(0.3, "dimensionless"),
        cell_temperature=Q(298.15, "kelvin"),
        duration=Q(600.0, "second"),
        cutoff_state_of_charge=Q(0.8, "dimensionless"),
        cutoff_voltage=Q(3.0, "volt"),
    )
    problem = build_battery_problem(cell, load)
    assessment = assess_runtime_validity(
        problem,
        state_of_charge=Q(0.3, "dimensionless"),
        discharge_current=Q(1.0, "ampere"),
        cell_temperature=Q(298.15, "kelvin"),
    )
    step = evaluate_step(cell, load)
    hand = (0.3 - 0.8) * 1.0 * 2.5 / 1.0 * 3600.0
    return {
        "id": "CB-3",
        "as_found": {
            "verdict": "IN_DOMAIN",
            "response_class": SUPPORTED,
            "detail": (
                "before the fix, all three conditions SATISFIED while the "
                "solver emitted runtime_to_cutoff = -4500 s"
            ),
        },
        "fix": (
            "a cutoff_reachability_margin >= 0 condition on the runtime "
            "record, with the derivation z_0 - z_stop added beside the "
            "consistency margin it complements. UNKNOWN unless the "
            "starting state of charge and at least one cutoff are "
            "declared."
        ),
        "regression_guard": (
            "benchmarks/capability_boundary/tests/test_capability_boundary.py"
            "::test_the_runtime_model_refuses_a_cutoff_above_where_the_"
            "discharge_starts"
        ),
        "model": "battery.cell.constant_current_runtime",
        "physically_valid_input": (
            "A 2.5 Ah cell at 30% state of charge, discharged at 1 A, with a "
            "declared SOC cutoff of 0.8 and a declared 3.0 V cutoff. Both "
            "cutoffs sit inside the declared 0.05-0.95 usable window and the "
            "current is inside the declared continuous rating."
        ),
        "why_out_of_regime": (
            "A discharge at constant current walks the state of charge "
            "monotonically DOWN -- 'discharge only' is the record's own first "
            "assumption -- so a cutoff declared ABOVE the starting state is "
            "never reached. The published equation returns the time to reach "
            "it anyway, and that time is negative."
        ),
        "oracle": {
            "type": "SIGN/DOMAIN, on the model's own monotonicity assumption",
            "independence": (
                "Computed here in plain arithmetic from the published formula "
                "without calling the solver. The reasoning is the record's own: "
                "discharge is monotone in z, so the first crossing of a cutoff "
                "above z_0 does not exist, and an elapsed time to an event "
                "that does not occur is not a number the model may report."
            ),
            "domain_of_validity": "every constant-current discharge",
            "expected": "t >= 0, or a refusal",
            "hand_computed_runtime_s": hand,
            "runtime_computed_runtime_s": step.runtime_to_cutoff,
            "agreement": abs(hand - step.runtime_to_cutoff) < 1e-6,
        },
        "probes": [
            {
                "model_validity": assessment.status.name,
                "conditions_satisfied": list(assessment.satisfied),
                "conditions_violated": list(assessment.violated),
                "runtime_to_cutoff_s": step.runtime_to_cutoff,
                "binding_cutoff_state_of_charge": step.binding_cutoff_state_of_charge,
                "response": _status(assessment),
            }
        ],
        "runtime_result": f"runtime_to_cutoff = {step.runtime_to_cutoff:.0f} s ({step.runtime_to_cutoff/3600.0:.2f} h)",
        "verdict": assessment.status.name,
        "reason_text": "all three conditions SATISFIED",
        "response_class": _status(assessment),
        "expected_safe_behavior": (
            "OUTSIDE_VALIDATED_DOMAIN on a condition comparing the binding "
            "cutoff against the starting state of charge"
        ),
        "mitigation_present": (
            "none. The solver's own comment says the negative value is "
            "'reported rather than clipped: the runtime model's own conditions "
            "are where that is judged' -- and they do not judge it."
        ),
    }


# ---------------------------------------------------------------------
# Cases examined and found safe. Kept because a boundary that holds is
# evidence too, and because an audit that reports only its hits is not
# reporting its denominator.
# ---------------------------------------------------------------------
def case_conduction_coarse_mesh() -> dict:
    """A backward-Euler solve far too coarse to resolve the physics."""
    from engcore.domains.thermal.conduction1d import reference
    from engcore.domains.thermal.conduction1d.problem import (
        MIDPOINT_METRIC,
        ConductionSlab,
        SlabDiscretization,
    )
    from engcore.domains.thermal.conduction1d.solver import solve_slab

    length, alpha, end = 0.1, 1e-5, 600.0
    slab = ConductionSlab(
        slab_id="coarse",
        length=Q(length, "meter"),
        diffusivity=Q(alpha, "meter ** 2 / second"),
        end_time=Q(end, "second"),
        discretization=SlabDiscretization(n_cells=4, n_steps=2),
    )
    result = solve_slab(slab, run_id="cb-probe")
    got = result.values[MIDPOINT_METRIC].magnitude_in("dimensionless")
    exact = reference.exact_midpoint(length_m=length, alpha_m2_s=alpha, time_s=end)
    return {
        "id": "CB-N1",
        "model": "thermal.conduction1d.linear_diffusion",
        "physically_valid_input": "4 cells and 2 time steps over 600 s, Fo = 4.8",
        "why_out_of_regime": (
            "Backward Euler is unconditionally stable but first-order "
            "accurate; at this resolution the answer is 25 times the true one."
        ),
        "oracle": {
            "type": "ANALYTIC closed form",
            "independence": (
                "engcore.domains.thermal.conduction1d.reference implements "
                "u = sin(pi x/L) exp(-alpha pi^2 t/L^2) and a test asserts it "
                "never imports the solver. The single-mode initial condition "
                "collapses the series, so the reference is exact to rounding."
            ),
            "domain_of_validity": "exact for this initial and boundary condition",
            "expected": exact,
            "observed": got,
            "relative_error": abs(got - exact) / abs(exact),
        },
        "probes": [
            {
                "attained_levels": sorted(level.value for level in result.attained_levels),
                "not_run_checks": [check.name for check in result.validation.not_run],
                "uncertainty_kind": result.uncertainty[MIDPOINT_METRIC].kind.value,
                "response": WARNED,
            }
        ],
        "runtime_result": f"midpoint = {got:.6g} against an exact {exact:.6g}",
        "verdict": "NOT A FINDING",
        "reason_text": (
            "the result attains DIMENSIONALLY_VALID and nothing more; "
            "discretization_convergence and analytic_reference_agreement are "
            "both reported NOT_RUN with their reasons, and every metric's "
            "uncertainty is UNKNOWN with the reason stated"
        ),
        "response_class": WARNED,
        "expected_safe_behavior": "exactly what it does: a number whose accuracy is explicitly not claimed",
        "mitigation_present": (
            "the result contract itself. A caller who reads attained_levels "
            "cannot mistake this for a verified answer, and the explicit "
            "FTCS realization carries a von Neumann stability condition of "
            "its own."
        ),
    }


def case_coulomb_counting_past_empty() -> dict:
    """A discharge that walks the state of charge below zero."""
    from engcore.domains.battery.cell import (
        CellSpecification,
        DischargeLoad,
        assess_coulomb_counting_validity,
        build_battery_problem,
    )
    from engcore.domains.battery.context import CellLimits

    probes = []
    for label, limits in (
        ("no window declared", CellLimits()),
        (
            "window declared",
            CellLimits(
                usable_soc_minimum=Q(0.05, "dimensionless"),
                usable_soc_maximum=Q(0.95, "dimensionless"),
            ),
        ),
    ):
        cell = CellSpecification(
            cell_id="C",
            nominal_capacity=Q(2.5, "ampere_hour"),
            internal_resistance=Q(0.035, "ohm"),
            open_circuit_voltage_at_full=Q(4.2, "volt"),
            open_circuit_voltage_at_empty=Q(3.0, "volt"),
            coulombic_efficiency=Q(1.0, "dimensionless"),
            limits=limits,
        )
        load = DischargeLoad(
            load_id="L",
            current=Q(2.5, "ampere"),
            initial_state_of_charge=Q(0.9, "dimensionless"),
            cell_temperature=Q(298.15, "kelvin"),
            duration=Q(7200.0, "second"),
        )
        problem = build_battery_problem(cell, load)
        assessment = assess_coulomb_counting_validity(
            problem,
            state_of_charge=Q(0.9, "dimensionless"),
            discharge_current=Q(2.5, "ampere"),
            cell_temperature=Q(298.15, "kelvin"),
        )
        probes.append(
            {
                "declaration": label,
                "model_validity": assessment.status.name,
                "conditions_violated": list(assessment.violated),
                "response": _status(assessment),
            }
        )
    return {
        "id": "CB-N2",
        "model": "battery.cell.coulomb_counting",
        "physically_valid_input": "2.5 Ah cell at z = 0.9, discharged at 2.5 A for two hours",
        "why_out_of_regime": "the exact integral gives z_end = -1.1; a state of charge below zero is not a state of charge",
        "oracle": {
            "type": "SIGN/DOMAIN",
            "independence": "z_end computed here in arithmetic, not by the solver",
            "domain_of_validity": "every cell",
            "expected": "0 <= z <= 1, or a refusal",
            "hand_computed_z_end": 0.9 - 2.5 * 2.0 / (1.0 * 2.5),
        },
        "probes": probes,
        "runtime_result": "UNKNOWN without a declared window; OUTSIDE_VALIDATED_DOMAIN with one",
        "verdict": "NOT A FINDING",
        "reason_text": "the model never reaches IN_DOMAIN on this declaration",
        "response_class": UNKNOWN,
        "expected_safe_behavior": "exactly what it does",
        "mitigation_present": "soc_window_margin, which is UNKNOWN unless both edges are declared",
    }


def case_rint_past_the_chord() -> dict:
    """A discharge that walks past the end of the OCV chord."""
    from engcore.domains.battery.cell import (
        CellSpecification,
        DischargeLoad,
        assess_rint_validity,
        build_battery_problem,
    )
    from engcore.domains.battery.context import CellLimits
    from engcore.domains.battery.solver import evaluate_step

    limits = CellLimits(
        usable_soc_minimum=Q(0.0, "dimensionless"),
        usable_soc_maximum=Q(1.0, "dimensionless"),
        continuous_discharge_c_rate=Q(4.0, "1 / hour"),
        minimum_discharge_temperature=Q(253.15, "kelvin"),
        maximum_discharge_temperature=Q(333.15, "kelvin"),
        resistance_reference_temperature=Q(298.15, "kelvin"),
        resistance_temperature_span=Q(40.0, "kelvin"),
        cell_thermal_conductance=Q(0.5, "watt / kelvin"),
        self_heating_rise_bound=Q(5.0, "kelvin"),
    )
    cell = CellSpecification(
        cell_id="C",
        nominal_capacity=Q(2.5, "ampere_hour"),
        internal_resistance=Q(0.035, "ohm"),
        open_circuit_voltage_at_full=Q(4.2, "volt"),
        open_circuit_voltage_at_empty=Q(3.0, "volt"),
        coulombic_efficiency=Q(1.0, "dimensionless"),
        limits=limits,
    )
    load = DischargeLoad(
        load_id="L",
        current=Q(1.0, "ampere"),
        initial_state_of_charge=Q(0.9, "dimensionless"),
        cell_temperature=Q(298.15, "kelvin"),
        duration=Q(9000.0, "second"),
    )
    problem = build_battery_problem(cell, load)
    assessment = assess_rint_validity(
        problem,
        state_of_charge=Q(0.9, "dimensionless"),
        discharge_current=Q(1.0, "ampere"),
        cell_temperature=Q(298.15, "kelvin"),
    )
    step = evaluate_step(cell, load)
    return {
        "id": "CB-N3",
        "model": "battery.cell.rint_ocv",
        "physically_valid_input": "2.5 Ah cell at z = 0.9, 1 A for 2.5 hours",
        "why_out_of_regime": (
            "z_end = -0.1 walks off the end of the affine OCV chord, where the "
            "record itself says the chord fails against a real curve's knee"
        ),
        "oracle": {
            "type": "SIGN/DOMAIN",
            "independence": "the chord's own endpoints bound OCV; computed here, not by the solver",
            "domain_of_validity": "every cell",
            "expected": "0 <= z <= 1, or a refusal",
            "observed_z_end": step.final_state_of_charge,
        },
        "probes": [
            {
                "model_validity": assessment.status.name,
                "conditions_violated": list(assessment.violated),
                "response": _status(assessment),
            }
        ],
        "runtime_result": f"z_end = {step.final_state_of_charge:.3f}, refused",
        "verdict": "NOT A FINDING",
        "reason_text": "soc_window_margin is VIOLATED",
        "response_class": REFUSE,
        "expected_safe_behavior": "exactly what it does",
        "mitigation_present": "soc_window_margin",
    }


def case_lumped_bare_declaration() -> dict:
    """The lumped model with nothing declared about its regime."""
    from engcore.domains.thermal_models.lumped import LUMPED_CAPACITY_MODEL

    assessment = LUMPED_CAPACITY_MODEL.assess_validity(
        declared={
            "heat_capacity": Q(900.0, "joule / kelvin"),
            "ambient_conductance": Q(0.8, "watt / kelvin"),
        },
        assembled={},
    )
    return {
        "id": "CB-N4",
        "model": "thermal.lumped.first_order_capacity",
        "physically_valid_input": "a complete, buildable body: C and hA and nothing else",
        "why_out_of_regime": (
            "nothing states the Biot number, the radiation ratio, the "
            "geometry, the melting point or the correlation ranges, so "
            "nothing establishes that a lumped description applies"
        ),
        "oracle": {
            "type": "SIGN/DOMAIN (fail-closed expectation)",
            "independence": "structural: counted from the assessment, not from any computed value",
            "domain_of_validity": "n/a",
            "expected": "UNKNOWN rather than IN_DOMAIN",
        },
        "probes": [
            {
                "model_validity": assessment.status.name,
                "conditions_satisfied": list(assessment.satisfied),
                "conditions_unknown": list(assessment.unknown),
                "response": _status(assessment),
            }
        ],
        "runtime_result": f"UNKNOWN with {len(assessment.unknown)} of 12 conditions unanswered",
        "verdict": "NOT A FINDING",
        "reason_text": "fail-closed; the model cannot reach IN_DOMAIN without the caller stating the regime",
        "response_class": UNKNOWN,
        "expected_safe_behavior": "exactly what it does",
        "mitigation_present": "ten UNKNOWN conditions",
    }


CASES = (
    case_tcr_zero_crossing,
    case_cstr_constant_rate_ceiling,
    case_runtime_cutoff_behind_start,
    case_conduction_coarse_mesh,
    case_coulomb_counting_past_empty,
    case_rint_past_the_chord,
    case_lumped_bare_declaration,
)


def run() -> dict:
    rows = [case() for case in CASES]
    findings = [row for row in rows if row.get("as_found")]
    # As the round defines it: a case that RECEIVED a normal-looking supported
    # result. Recorded from how the case was found, not from how it behaves
    # after the repair, because the repair is what this column is evidence for.
    false_confidence = [
        row
        for row in rows
        if row.get("as_found", {}).get("response_class") == SUPPORTED
    ]
    still_supported = [row for row in rows if row["response_class"] == SUPPORTED]
    counts: dict[str, int] = {}
    as_found_counts: dict[str, int] = {}
    for row in rows:
        counts[row["response_class"]] = counts.get(row["response_class"], 0) + 1
        found = row.get("as_found", {}).get("response_class", row["response_class"])
        as_found_counts[found] = as_found_counts.get(found, 0) + 1
    return {
        "schema": "capability_boundary_false_confidence/1",
        "what_this_is": (
            "Adversarial cases at and beyond each model's true scientific "
            "boundary. Every declaration here is physically valid and "
            "accepted by the runtime; the question is whether the answer can "
            "be trusted in that regime."
        ),
        "response_legend": {
            "A_REFUSE": "the declaration is rejected",
            "B_UNKNOWN": "the model declines to answer",
            "C_WARNED_NUMBER": "a number, with the limitation visible on the result",
            "D_SUPPORTED": "a normal-looking supported result — the dangerous case",
        },
        "cases_run": len(rows),
        "response_counts_as_found": dict(sorted(as_found_counts.items())),
        "response_counts_after_repair": dict(sorted(counts.items())),
        "findings": [row["id"] for row in findings],
        "false_confidence_cases": [row["id"] for row in false_confidence],
        "false_confidence_cases_still_open": [row["id"] for row in still_supported],
        "cases": rows,
    }


def main() -> int:
    payload = run()
    (ROUND / "FALSE_CONFIDENCE_CASES.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"{payload['cases_run']} cases")
    print("as found:     ", json.dumps(payload["response_counts_as_found"]))
    print("after repair: ", json.dumps(payload["response_counts_after_repair"]))
    print("still open:   ", payload["false_confidence_cases_still_open"])
    for row in payload["cases"]:
        print(f"  {row['id']:6s} {row['response_class']:16s} {row['verdict']:26s} {row['model']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
