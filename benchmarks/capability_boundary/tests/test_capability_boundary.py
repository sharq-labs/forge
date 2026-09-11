"""Scientific boundary guards.

Contract Guard asks whether the record matches the runtime. These ask a
different question, and a model can pass every Contract Guard test while
failing every test here: *is the matched behaviour scientifically valid in
this regime?*

Each guard below encodes a boundary rather than a string. It fails if the
published claim widens past the physics, if a validity boundary disappears,
or if the runtime starts reporting IN_DOMAIN for a case its own equations
cannot represent.
"""

from engcore.scientific.units.quantity import Quantity as Q


# =====================================================================
# CB-1 — a straight line that crosses zero is not a conductor resistance
# =====================================================================
def test_the_linear_tcr_model_refuses_a_line_that_has_crossed_zero():
    """R(T) = R_ref (1 + alpha (T - T_ref)) goes negative past the crossing.

    The record's own input description admits a negative alpha and justifies
    it by "the band is how far that tangent is claimed to carry". Past the
    zero crossing the expression does not describe a poor conductor but a
    negative one, which is not a resistance at all.

    The rated sibling already declares this bound and states the reason: "The
    bound is the physics of the quantity, not a tolerance." Nothing extra has
    to be declared for it — the multiplier is computable from the three inputs
    this record already requires.
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

    # Comfortably inside the line's positive half: applicable.
    inside = M.assess_resistance_validity(problem, Q(380.0, "kelvin"))
    assert inside.status.name == "IN_DOMAIN", inside.status

    # On the crossing and past it: the model must not call itself applicable.
    for kelvin in (400.0, 420.0, 449.0):
        assessment = M.assess_resistance_validity(problem, Q(kelvin, "kelvin"))
        assert assessment.status.name != "IN_DOMAIN", (
            f"at {kelvin} K the model reports {assessment.status.name} while "
            f"its own expression yields "
            f"{1000.0 * (1.0 + -0.01 * (kelvin - 300.0)):.1f} ohm"
        )


def test_the_linear_tcr_bound_is_unknown_rather_than_satisfied_without_a_temperature():
    """A bound nobody can evaluate must not be awarded by default."""
    from engcore.domains.electrical.material import LINEAR_TCR_MODEL

    assessment = LINEAR_TCR_MODEL.assess_validity(
        declared={"reference_resistance": Q(100.0, "ohm")}, assembled={}
    )
    assert "linear_resistance_ratio" in assessment.unknown, assessment.unknown


# =====================================================================
# CB-2 — the CSTR invariant ceiling does not depend on the rate law
# =====================================================================
def _over_ceiling_run():
    from engcore.domains.kinetics.cstr.problem import (
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
    return ReactorRun(
        run_label="R",
        chemistry=chemistry,
        operation=operation,
        initial_concentration=Q(1000.0, "mole / meter ** 3"),
        initial_temperature=Q(350.0, "kelvin"),
    )


def test_both_cstr_models_refuse_a_declaration_whose_ceiling_leaves_the_envelope():
    """Z = T + beta C_A is an invariant of the balances, not of the rate law.

    Adding beta times the species balance to the energy balance cancels the
    reaction term identically: dZ/dt = (Z_f - Z)/tau - gamma (T - T_c) carries
    no k. The ceiling therefore bounds the constant-rate model exactly as it
    bounds the Arrhenius one, and the constant-rate record claims the "Same
    single-phase CSTR envelope as the primary model".
    """
    from engcore.domains.kinetics.cstr.alternatives import CONSTANT_RATE_CSTR_MODEL
    from engcore.domains.kinetics.cstr.problem import CSTR_MODEL

    context = _over_ceiling_run().validity_context()
    ceiling = context.assembled["adiabatic_ceiling_temperature"].magnitude_in("kelvin")
    assert ceiling > 1000.0, ceiling

    primary = context.assess(CSTR_MODEL)
    assert primary.status.name == "OUTSIDE_VALIDATED_DOMAIN"
    assert "adiabatic_ceiling_temperature" in primary.violated

    constant_rate = context.assess(CONSTANT_RATE_CSTR_MODEL)
    assert "adiabatic_ceiling_temperature" in constant_rate.violated, (
        f"the constant-rate model reports {constant_rate.status.name} with "
        f"violated={constant_rate.violated} for a declaration whose exact "
        f"invariant ceiling is {ceiling:.0f} K, while its own temperature "
        f"condition declares 250-1000 K and its validity description claims "
        f"the same envelope as the primary model"
    )

    # ... and the whole set the model can see, with nothing UNKNOWN by
    # omission, must not come back applicable either.
    full = CONSTANT_RATE_CSTR_MODEL.assess_validity(
        declared={
            "k_const": Q(0.05, "1 / second"),
            "residence_time": Q(360.0, "second"),
        },
        assembled={
            "temperature": context.assembled["temperature"],
            "concentration": context.assembled["concentration"],
            "adiabatic_ceiling_temperature": context.assembled[
                "adiabatic_ceiling_temperature"
            ],
        },
    )
    assert full.status.name == "OUTSIDE_VALIDATED_DOMAIN", (
        f"{full.status.name}; satisfied={full.satisfied}"
    )


def test_the_constant_rate_cstr_reserves_the_ceiling_its_sibling_computes():
    """A quantity a model does not reserve is a quantity it can never read."""
    from engcore.domains.kinetics.cstr.alternatives import CONSTANT_RATE_CSTR_MODEL

    assert (
        "adiabatic_ceiling_temperature" in CONSTANT_RATE_CSTR_MODEL.derived_quantities
    ), sorted(CONSTANT_RATE_CSTR_MODEL.derived_quantities)


# =====================================================================
# CB-3 — a discharge does not reach a cutoff behind where it started
# =====================================================================
def _runtime_declaration(cutoff_soc: float, initial_soc: float):
    from engcore.domains.battery.cell import (
        CellSpecification,
        DischargeLoad,
        build_battery_problem,
    )
    from engcore.domains.battery.context import CellLimits

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
        initial_state_of_charge=Q(initial_soc, "dimensionless"),
        cell_temperature=Q(298.15, "kelvin"),
        duration=Q(600.0, "second"),
        cutoff_state_of_charge=Q(cutoff_soc, "dimensionless"),
        cutoff_voltage=Q(3.0, "volt"),
    )
    return cell, load, build_battery_problem(cell, load)


def test_the_runtime_model_refuses_a_cutoff_above_where_the_discharge_starts():
    """t = (z_0 - z_stop) eta Q_nom / I is negative when z_stop > z_0.

    A discharge at constant current walks z monotonically down -- the record's
    own first assumption is "discharge only" -- so a cutoff above the starting
    state is never reached, and the time to reach it is not a number this
    model may report as applicable.
    """
    from engcore.domains.battery.cell import assess_runtime_validity
    from engcore.domains.battery.solver import evaluate_step

    cell, load, problem = _runtime_declaration(cutoff_soc=0.8, initial_soc=0.3)
    step = evaluate_step(cell, load)
    assert step.runtime_to_cutoff < 0.0, step.runtime_to_cutoff

    assessment = assess_runtime_validity(
        problem,
        state_of_charge=Q(0.3, "dimensionless"),
        discharge_current=Q(1.0, "ampere"),
        cell_temperature=Q(298.15, "kelvin"),
    )
    assert assessment.status.name != "IN_DOMAIN", (
        f"the model reports {assessment.status.name} for a declaration whose "
        f"own equation yields a runtime of {step.runtime_to_cutoff:.0f} s"
    )


def test_the_runtime_model_still_accepts_an_ordinary_discharge():
    """The boundary must refuse the badly posed case and nothing else."""
    from engcore.domains.battery.cell import assess_runtime_validity
    from engcore.domains.battery.solver import evaluate_step

    cell, load, problem = _runtime_declaration(cutoff_soc=0.1, initial_soc=0.9)
    step = evaluate_step(cell, load)
    assert step.runtime_to_cutoff > 0.0

    assessment = assess_runtime_validity(
        problem,
        state_of_charge=Q(0.9, "dimensionless"),
        discharge_current=Q(1.0, "ampere"),
        cell_temperature=Q(298.15, "kelvin"),
    )
    assert assessment.status.name == "IN_DOMAIN", (
        f"{assessment.status.name}; violated={assessment.violated}; "
        f"unknown={assessment.unknown}"
    )


# =====================================================================
# Boundaries that already hold. These are regression guards for the
# capability boundaries this round examined and found sound.
# =====================================================================
def test_a_coarse_diffusion_solve_claims_no_accuracy_it_has_not_earned():
    """Stable is not accurate, and the result contract must not conflate them."""
    from engcore.domains.thermal.conduction1d import reference
    from engcore.domains.thermal.conduction1d.problem import (
        MIDPOINT_METRIC,
        ConductionSlab,
        SlabDiscretization,
    )
    from engcore.domains.thermal.conduction1d.solver import solve_slab

    slab = ConductionSlab(
        slab_id="coarse",
        length=Q(0.1, "meter"),
        diffusivity=Q(1e-5, "meter ** 2 / second"),
        end_time=Q(600.0, "second"),
        discretization=SlabDiscretization(n_cells=4, n_steps=2),
    )
    result = solve_slab(slab, run_id="cb-guard")
    got = result.values[MIDPOINT_METRIC].magnitude_in("dimensionless")
    exact = reference.exact_midpoint(length_m=0.1, alpha_m2_s=1e-5, time_s=600.0)

    # The answer really is this bad, which is what makes the next assertions
    # the ones that matter.
    assert abs(got - exact) / abs(exact) > 1.0

    levels = {level.value for level in result.attained_levels}
    assert levels == {"dimensionally_valid"}, levels
    not_run = {check.name for check in result.validation.not_run}
    assert "discretization_convergence" in not_run
    assert "analytic_reference_agreement" in not_run
    assert result.uncertainty[MIDPOINT_METRIC].kind.value == "unknown"


def test_the_lumped_model_cannot_reach_in_domain_without_stating_its_regime():
    """Fail-closed: a buildable body is not an applicable body."""
    from engcore.domains.thermal_models.lumped import LUMPED_CAPACITY_MODEL

    assessment = LUMPED_CAPACITY_MODEL.assess_validity(
        declared={
            "heat_capacity": Q(900.0, "joule / kelvin"),
            "ambient_conductance": Q(0.8, "watt / kelvin"),
        },
        assembled={},
    )
    assert assessment.status.name == "UNKNOWN"
    assert len(assessment.unknown) >= 10, assessment.unknown


def test_coulomb_counting_never_reports_in_domain_past_empty():
    from engcore.domains.battery.cell import (
        CellSpecification,
        DischargeLoad,
        assess_coulomb_counting_validity,
        build_battery_problem,
    )
    from engcore.domains.battery.context import CellLimits

    for limits in (
        CellLimits(),
        CellLimits(
            usable_soc_minimum=Q(0.05, "dimensionless"),
            usable_soc_maximum=Q(0.95, "dimensionless"),
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
        assessment = assess_coulomb_counting_validity(
            build_battery_problem(cell, load),
            state_of_charge=Q(0.9, "dimensionless"),
            discharge_current=Q(2.5, "ampere"),
            cell_temperature=Q(298.15, "kelvin"),
        )
        assert assessment.status.name != "IN_DOMAIN", assessment.status


def test_the_lumped_model_refuses_a_body_its_own_run_would_melt():
    """A phase change is excluded by the record and bounded by a condition.

    "no radiation, no phase change, no mass transport" is an assumption of the
    lumped energy balance, and a body driven past its melting point is a body
    the balance stops describing: the latent heat is absent from C dT/dt and
    the temperature it predicts beyond the transition is not a temperature the
    body has. This is the boundary that plant CBP-7 removes.
    """
    from engcore.domains.thermal_models import context as ctx
    from engcore.domains.thermal_models.lumped import LUMPED_CAPACITY_MODEL

    reserved = LUMPED_CAPACITY_MODEL.derived_quantities
    declared = {
        ctx.MELTING_TEMPERATURE: Q(500.0, "kelvin"),
        "ambient_conductance": Q(0.8, "watt / kelvin"),
        "heat_capacity": Q(900.0, "joule / kelvin"),
        "duration": Q(5000.0, "second"),
    }

    def assess(heat_watts: float):
        assembled = ctx.derived_lumped_quantities(
            declared,
            initial_temperature=Q(300.0, "kelvin"),
            ambient_temperature=Q(295.0, "kelvin"),
            heat_input=Q(heat_watts, "watt"),
        )
        return LUMPED_CAPACITY_MODEL.assess_validity(
            declared=declared,
            assembled={k: v for k, v in assembled.items() if k in reserved},
        )

    # T_ss = 295 + Q/hA. At 5 W the body settles at 301 K, well below the
    # 500 K melting point, and the phase-change condition is satisfied.
    modest = assess(5.0)
    assert ctx.MELTING_TEMPERATURE_UTILIZATION in modest.satisfied

    # At 400 W it settles at 795 K, which is 295 K past melting.
    melted = assess(400.0)
    assert melted.status.name == "OUTSIDE_VALIDATED_DOMAIN", melted.status
    assert ctx.MELTING_TEMPERATURE_UTILIZATION in melted.violated


def test_the_reachability_bound_keeps_the_unknown_promise_its_record_makes():
    """Withholding must not buy a verdict, and either cutoff alone must serve.

    The claim-map supplement this round registers says the two cutoffs are
    ALTERNATIVE routes: drop both and the condition is UNKNOWN because there is
    no runtime to bound; drop one and the other still determines z_stop. This
    exercises that reading rather than leaving it as an unexecuted mapping,
    which is what the sibling cutoff_consistency_margin -- which genuinely
    needs both -- would otherwise be confused with.
    """
    from engcore.domains.battery.cell import (
        CellSpecification,
        DischargeLoad,
        assess_runtime_validity,
        build_battery_problem,
    )
    from engcore.domains.battery.context import (
        CUTOFF_REACHABILITY_MARGIN,
        CellLimits,
    )

    def assess(cutoff_voltage, cutoff_soc):
        cell = CellSpecification(
            cell_id="C",
            nominal_capacity=Q(2.5, "ampere_hour"),
            internal_resistance=Q(0.035, "ohm"),
            open_circuit_voltage_at_full=Q(4.2, "volt"),
            open_circuit_voltage_at_empty=Q(3.0, "volt"),
            coulombic_efficiency=Q(1.0, "dimensionless"),
            limits=CellLimits(
                usable_soc_minimum=Q(0.05, "dimensionless"),
                usable_soc_maximum=Q(0.95, "dimensionless"),
                continuous_discharge_c_rate=Q(2.0, "1 / hour"),
            ),
        )
        load = DischargeLoad(
            load_id="L",
            current=Q(1.0, "ampere"),
            initial_state_of_charge=Q(0.9, "dimensionless"),
            cell_temperature=Q(298.15, "kelvin"),
            duration=Q(600.0, "second"),
            cutoff_voltage=cutoff_voltage,
            cutoff_state_of_charge=cutoff_soc,
        )
        return assess_runtime_validity(
            build_battery_problem(cell, load),
            state_of_charge=Q(0.9, "dimensionless"),
            discharge_current=Q(1.0, "ampere"),
            cell_temperature=Q(298.15, "kelvin"),
        )

    # Neither cutoff: no runtime exists, so the bound is UNKNOWN, not satisfied.
    both_withheld = assess(None, None)
    assert CUTOFF_REACHABILITY_MARGIN in both_withheld.unknown

    # Either alone determines the binding cutoff, so the question is answered.
    for voltage, soc in (
        (Q(3.0, "volt"), None),
        (None, Q(0.1, "dimensionless")),
    ):
        answered = assess(voltage, soc)
        assert CUTOFF_REACHABILITY_MARGIN in answered.satisfied, (
            voltage,
            soc,
            answered.unknown,
        )


# =====================================================================
# The property that makes all three repairs safe to ship
# =====================================================================
def test_no_repair_turned_a_decided_verdict_into_an_undecided_one():
    """Each new condition is UNKNOWN only where a sibling already was.

    A validity condition added to a shipped record can go wrong in two
    directions. It can fail to bite, which is what the guards above are for.
    It can also bite too widely -- leaving a model UNKNOWN for want of a
    declaration nobody used to have to make, which re-judges every result that
    cited the record without any of its inputs having changed.

    Each of the three conditions added in this round is derived from
    declarations a sibling condition on the SAME record already required, so a
    context that could decide the record before can decide it now. That is
    checked here rather than argued: 1680 benchmark cases re-scored
    bit-identical across these changes, and this is the reason why.
    """
    # -- electrical.material: the multiplier needs the temperature its own
    #    range condition already needed.
    from engcore.domains.electrical.material import LINEAR_TCR_MODEL

    withheld = LINEAR_TCR_MODEL.assess_validity(
        declared={"reference_resistance": Q(100.0, "ohm")}, assembled={}
    )
    assert ("linear_resistance_ratio" in withheld.unknown) == (
        "temperature" in withheld.unknown
    ), withheld.unknown

    # -- battery.cell: the reachability margin needs a cutoff, and the
    #    consistency margin already needed two.
    from engcore.domains.battery.cell import (
        CellSpecification,
        DischargeLoad,
        assess_runtime_validity,
        build_battery_problem,
    )
    from engcore.domains.battery.context import CellLimits

    cell = CellSpecification(
        cell_id="C",
        nominal_capacity=Q(2.5, "ampere_hour"),
        internal_resistance=Q(0.035, "ohm"),
        open_circuit_voltage_at_full=Q(4.2, "volt"),
        open_circuit_voltage_at_empty=Q(3.0, "volt"),
        coulombic_efficiency=Q(1.0, "dimensionless"),
        limits=CellLimits(
            usable_soc_minimum=Q(0.05, "dimensionless"),
            usable_soc_maximum=Q(0.95, "dimensionless"),
            continuous_discharge_c_rate=Q(2.0, "1 / hour"),
        ),
    )
    load = DischargeLoad(
        load_id="L",
        current=Q(1.0, "ampere"),
        initial_state_of_charge=Q(0.9, "dimensionless"),
        cell_temperature=Q(298.15, "kelvin"),
        duration=Q(600.0, "second"),
    )
    bare = assess_runtime_validity(
        build_battery_problem(cell, load),
        state_of_charge=Q(0.9, "dimensionless"),
        discharge_current=Q(1.0, "ampere"),
        cell_temperature=Q(298.15, "kelvin"),
    )
    assert ("cutoff_reachability_margin" in bare.unknown) == (
        "cutoff_consistency_margin" in bare.unknown
    ), bare.unknown

    # -- kinetics.cstr: an ordinary run decides the ceiling, so the record is
    #    no less decidable than it was.
    from engcore.domains.kinetics.cstr.alternatives import CONSTANT_RATE_CSTR_MODEL

    ordinary = _ordinary_run().validity_context().assess(CONSTANT_RATE_CSTR_MODEL)
    assert "adiabatic_ceiling_temperature" in ordinary.satisfied, ordinary.unknown


def _ordinary_run():
    from engcore.domains.kinetics.cstr.problem import (
        ReactorChemistry,
        ReactorOperation,
        ReactorRun,
    )

    chemistry = ReactorChemistry(
        k0=Q(0.05, "1 / second"),
        activation_energy=Q(0.0, "joule / mole"),
        heat_of_reaction=Q(-5.0e4, "joule / mole"),
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
    return ReactorRun(
        run_label="R",
        chemistry=chemistry,
        operation=operation,
        initial_concentration=Q(500.0, "mole / meter ** 3"),
        initial_temperature=Q(350.0, "kelvin"),
    )
