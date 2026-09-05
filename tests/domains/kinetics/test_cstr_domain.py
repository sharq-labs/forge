"""Non-isothermal CSTR — solver contract, validity envelope, failure semantics.

The claim under test: a genuinely stiff, nonlinear, failure-prone kinetics
solver satisfies the frozen ``ScientificSolver`` contract, reports each
distinguishable failure through existing Core vocabulary without collapsing
any two, and earns a defensible verification result — with no change to the
Scientific Core.

These are domain tests only. No inference, no campaign, no certification.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

from src.engcore.domains.kinetics.cstr import (
    CA_FINAL_METRIC,
    CONVERSION_METRIC,
    CSTR_MODEL,
    INVARIANT_REL_TOL,
    KINETICS_CSTR_NONISOTHERMAL,
    MAX_VALID_TEMPERATURE_K,
    METRIC_UNITS,
    MIN_VALID_TEMPERATURE_K,
    MOLAR_GAS_CONSTANT,
    STEADY_STATE_REL_TOL,
    T_AT_MAX_METRIC,
    T_FINAL_METRIC,
    T_MAX_METRIC,
    CSTRSolver,
    IntegrationBudgetExceeded,
    IntegrationSettings,
    ReactorBindingError,
    ReactorChemistry,
    ReactorConfigurationError,
    ReactorOperation,
    ReactorRun,
    adiabatic_invariant_exact,
    arrhenius_rate_constant,
    build_cstr_problem,
    invariant_is_exact,
    measure_stiffness,
    run_verification_gate,
    solve_reactor,
    steady_state_residual,
    steady_states,
)

# White-box: `assemble` is an implementation detail deliberately kept off the
# package's public surface, so this test reaches into its own module.
from src.engcore.domains.kinetics.cstr.solver import assemble
from src.engcore.scientific.results.result import ScientificResult
from src.engcore.scientific.results.uncertainty import UncertaintyKind
from src.engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
)
from src.engcore.scientific.solvers.protocol import (
    ConvergenceState,
    ScientificSolver,
)
from src.engcore.scientific.units.quantity import Quantity
from src.engcore.scientific.errors import (
    ScientificValidationError,
    UnitCompatibilityError,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

Q = Quantity

CHEMISTRY = ReactorChemistry(
    k0=Q(7.2e10 / 60.0, "1/s"),
    activation_energy=Q(8750.0 * 8.314462618, "J/mol"),
    heat_of_reaction=Q(-5.0e4, "J/mol"),
    density=Q(1000.0, "kg/m**3"),
    heat_capacity=Q(239.0, "J/(kg*K)"),
)


def operation(
    *, tc=290.0, ua=5.0e4 / 60.0, tf=350.0, caf=1000.0, end=1800.0
) -> ReactorOperation:
    return ReactorOperation(
        volume=Q(0.1, "m**3"),
        flow_rate=Q(0.1 / 60.0, "m**3/s"),
        feed_concentration=Q(caf, "mol/m**3"),
        feed_temperature=Q(tf, "kelvin"),
        coolant_temperature=Q(tc, "kelvin"),
        ua=Q(ua, "W/K"),
        end_time=Q(end, "second"),
    )


def reactor(
    label="t", op=None, ca0=1000.0, t0=300.0, method="BDF", rtol=1e-8,
    budget=5_000_000, npts=2001,
) -> ReactorRun:
    return ReactorRun(
        run_label=label,
        chemistry=CHEMISTRY,
        operation=op if op is not None else operation(),
        initial_concentration=Q(ca0, "mol/m**3"),
        initial_temperature=Q(t0, "kelvin"),
        integration=IntegrationSettings(
            method=method, rtol=rtol, atol_concentration=rtol,
            atol_temperature=rtol, max_rhs_evaluations=budget,
            n_output_points=npts,
        ),
    )


BENIGN = reactor("benign")
ADIABATIC = reactor(
    "adiabatic", op=operation(ua=0.0, tf=340.0, end=600.0), t0=340.0
)


@pytest.fixture(scope="module")
def benign_result():
    return solve_reactor(BENIGN, run_id="benign-1")


@pytest.fixture(scope="module")
def adiabatic_gate():
    return run_verification_gate(ADIABATIC, run_id_prefix="adiabatic-gate")


# =====================================================================
# Contract conformance and construction
# =====================================================================

def test_solver_satisfies_the_frozen_protocol() -> None:
    assert isinstance(CSTRSolver(), ScientificSolver)


def test_the_five_stages_are_separable_and_ordered() -> None:
    solver = CSTRSolver()
    problem = build_cstr_problem(BENIGN, problem_id="stages")
    assert solver.supports(problem)
    solver.bind_run(BENIGN, problem.problem_id)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    report = solver.validate(prepared, raw)
    assert raw.convergence is ConvergenceState.CONVERGED
    assert set(metrics) == set(METRIC_UNITS)
    assert report.status is ValidationOutcome.PASS


def test_supports_answers_without_solving() -> None:
    """``supports`` must decide on declared capability, never by attempting."""
    solver = CSTRSolver()
    problem = build_cstr_problem(BENIGN, problem_id="unbound")
    # No run has been bound, so any attempt to solve would raise. supports()
    # must still answer.
    assert solver.supports(problem) is True
    with pytest.raises(ReactorConfigurationError):
        solver.prepare(problem)


def test_supports_refuses_a_foreign_problem() -> None:
    from src.engcore.domains.thermal.conduction1d import (
        ConductionSlab,
        SlabDiscretization,
        build_conduction_problem,
    )

    slab = ConductionSlab(
        slab_id="foreign",
        length=Q(0.1, "meter"),
        diffusivity=Q(1.2e-5, "m**2/s"),
        end_time=Q(60.0, "second"),
        discretization=SlabDiscretization(16, 20),
    )
    assert CSTRSolver().supports(build_conduction_problem(slab)) is False


def test_rebinding_different_physics_is_refused() -> None:
    solver = CSTRSolver()
    solver.bind_run(BENIGN, "shared-id")
    solver.bind_run(BENIGN, "shared-id")  # same physics: allowed
    other = reactor("other", op=operation(tc=305.0))
    with pytest.raises(ReactorBindingError):
        solver.bind_run(other, "shared-id")


def test_rebinding_the_same_physics_at_a_new_tolerance_is_allowed() -> None:
    """The tolerance ladder depends on this: numerics are not physics."""
    solver = CSTRSolver()
    solver.bind_run(BENIGN, "ladder")
    refined = BENIGN.with_integration(
        BENIGN.integration.with_tolerances(
            rtol=1e-12, atol_concentration=1e-12, atol_temperature=1e-12
        )
    )
    solver.bind_run(refined, "ladder")
    assert refined.physics_fingerprint() == BENIGN.physics_fingerprint()


def test_a_problem_paired_with_different_physics_is_refused() -> None:
    problem = build_cstr_problem(BENIGN, problem_id="mismatch")
    other = reactor("other", op=operation(tc=305.0))
    with pytest.raises(ReactorConfigurationError):
        solve_reactor(other, run_id="mismatch", problem=problem)


# =====================================================================
# Units — real physical dimensions, checked through Quantity
# =====================================================================

def test_every_metric_carries_its_declared_unit(benign_result) -> None:
    for name, unit in METRIC_UNITS.items():
        assert benign_result.value(name).is_compatible_with(unit), name


def test_metrics_carry_meaningful_units_not_dimensionless_placeholders(
    benign_result,
) -> None:
    assert benign_result.value(CA_FINAL_METRIC).dimensionality == str(
        Q(1.0, "mol/m**3").dimensionality
    )
    assert benign_result.value(T_FINAL_METRIC).dimensionality == str(
        Q(1.0, "kelvin").dimensionality
    )
    assert benign_result.value(T_AT_MAX_METRIC).dimensionality == str(
        Q(1.0, "second").dimensionality
    )
    # Conversion is genuinely dimensionless: it is a ratio of concentrations.
    assert benign_result.value(CONVERSION_METRIC).dimensionality == str(
        Q(1.0, "dimensionless").dimensionality
    )


def test_temperature_is_an_absolute_scale_not_a_relative_one(
    benign_result,
) -> None:
    """Kelvin, because it appears inside exp(-E/(R T))."""
    assert benign_result.value(T_FINAL_METRIC).units == "kelvin"
    assert benign_result.value(T_FINAL_METRIC).magnitude > 0.0


def test_the_governing_equation_is_dimensionally_homogeneous() -> None:
    """Both balances are checked as Quantity algebra, not as a comment."""
    run = BENIGN
    dilution = run.operation.flow_rate / run.operation.volume
    species_flow = dilution * run.operation.feed_concentration
    rate = Q(run.chemistry.rate_constant_per_s(350.0), "1/s")
    species_reaction = rate * run.operation.feed_concentration
    assert species_flow.is_compatible_with(species_reaction)
    assert species_flow.is_compatible_with("mol/(m**3*s)")

    beta = Q(run.chemistry.beta_m3_k_per_mol, "m**3*K/mol")
    energy_flow = dilution * Q(1.0, "kelvin")
    energy_reaction = beta * species_reaction
    energy_cooling = Q(run.gamma_per_s, "1/s") * Q(1.0, "kelvin")
    assert energy_flow.is_compatible_with(energy_reaction)
    assert energy_flow.is_compatible_with(energy_cooling)
    assert energy_flow.is_compatible_with("kelvin/second")


def test_beta_and_gamma_carry_the_dimensions_the_equations_need() -> None:
    beta = (
        Q(-CHEMISTRY.dh_j_per_mol, "J/mol")
        / (CHEMISTRY.density * CHEMISTRY.heat_capacity)
    )
    assert beta.is_compatible_with("m**3*K/mol")
    assert math.isclose(
        beta.magnitude_in("m**3*K/mol"),
        CHEMISTRY.beta_m3_k_per_mol,
        rel_tol=1e-12,
    )


def test_the_gas_constant_is_declared_as_a_quantity() -> None:
    assert MOLAR_GAS_CONSTANT.is_compatible_with("J/(mol*K)")
    assert math.isclose(
        MOLAR_GAS_CONSTANT.magnitude_in("J/(mol*K)"), 8.314462618, rel_tol=1e-15
    )


# =====================================================================
# Validity envelope — domain-owned, enforced at the boundary
# =====================================================================

def test_envelope_accepts_a_declaration_inside_it() -> None:
    inside = operation(tc=300.0, tf=350.0)
    assert inside.tf_k == 350.0 and inside.tc_k == 300.0


@pytest.mark.parametrize("kelvin", [MIN_VALID_TEMPERATURE_K, MAX_VALID_TEMPERATURE_K])
def test_envelope_accepts_its_own_boundary(kelvin: float) -> None:
    """The declared bounds are inclusive; a boundary value is inside."""
    operation(tf=kelvin, tc=kelvin)


@pytest.mark.parametrize(
    "kelvin",
    [
        MIN_VALID_TEMPERATURE_K - 1e-9,
        MAX_VALID_TEMPERATURE_K + 1e-9,
        0.0,
        -10.0,
    ],
)
def test_envelope_rejects_outside_and_just_outside(kelvin: float) -> None:
    with pytest.raises(ReactorConfigurationError):
        operation(tf=kelvin)


@pytest.mark.parametrize(
    "overrides",
    [
        {"feed_concentration": Q(-1.0, "mol/m**3")},
        {"volume": Q(0.0, "m**3")},
        {"flow_rate": Q(-1e-3, "m**3/s")},
        {"ua": Q(-100.0, "W/K")},
    ],
)
def test_operation_envelope_rejections(overrides) -> None:
    kwargs = {
        "volume": Q(0.1, "m**3"),
        "flow_rate": Q(0.1 / 60.0, "m**3/s"),
        "feed_concentration": Q(1000.0, "mol/m**3"),
        "feed_temperature": Q(350.0, "kelvin"),
        "coolant_temperature": Q(300.0, "kelvin"),
        "ua": Q(833.0, "W/K"),
        "end_time": Q(600.0, "second"),
    }
    kwargs.update(overrides)
    with pytest.raises(ReactorConfigurationError):
        ReactorOperation(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"k0": Q(0.0, "1/s")},
        {"k0": Q(-1.0, "1/s")},
        {"activation_energy": Q(-1e4, "J/mol")},
        {"density": Q(0.0, "kg/m**3")},
        {"heat_capacity": Q(0.0, "J/(kg*K)")},
    ],
)
def test_chemistry_envelope_rejections(overrides) -> None:
    kwargs = {
        "k0": CHEMISTRY.k0,
        "activation_energy": CHEMISTRY.activation_energy,
        "heat_of_reaction": CHEMISTRY.heat_of_reaction,
        "density": CHEMISTRY.density,
        "heat_capacity": CHEMISTRY.heat_capacity,
    }
    kwargs.update(overrides)
    with pytest.raises(ReactorConfigurationError):
        ReactorChemistry(**kwargs)


def test_a_bare_float_is_refused_where_a_quantity_is_required() -> None:
    kwargs = {
        "volume": Q(0.1, "m**3"),
        "flow_rate": Q(0.1 / 60.0, "m**3/s"),
        "feed_concentration": Q(1000.0, "mol/m**3"),
        "feed_temperature": 350.0,          # bare number
        "coolant_temperature": Q(300.0, "kelvin"),
        "ua": Q(833.0, "W/K"),
        "end_time": Q(600.0, "second"),
    }
    with pytest.raises(ReactorConfigurationError):
        ReactorOperation(**kwargs)


def test_a_wrong_dimension_is_refused() -> None:
    kwargs = {
        "volume": Q(0.1, "m**3"),
        "flow_rate": Q(0.1 / 60.0, "m**3/s"),
        "feed_concentration": Q(1000.0, "mol/m**3"),
        "feed_temperature": Q(350.0, "pascal"),   # a pressure
        "coolant_temperature": Q(300.0, "kelvin"),
        "ua": Q(833.0, "W/K"),
        "end_time": Q(600.0, "second"),
    }
    with pytest.raises(ReactorConfigurationError):
        ReactorOperation(**kwargs)


def test_lsoda_is_refused_because_its_work_count_is_unattributable() -> None:
    with pytest.raises(ReactorConfigurationError):
        IntegrationSettings(method="LSODA")


@pytest.mark.parametrize("rtol", [0.0, -1e-8, float("nan"), float("inf")])
def test_non_positive_or_non_finite_tolerance_is_refused(rtol) -> None:
    with pytest.raises(ReactorConfigurationError):
        IntegrationSettings(rtol=rtol)


def test_the_model_declares_its_own_validity_domain() -> None:
    names = {condition.name for condition in CSTR_MODEL.validity.conditions}
    assert {"temperature", "concentration", "k0", "activation_energy"} <= names


def test_the_scientific_core_owns_no_cstr_specific_rule() -> None:
    """F1: the Core must contain no branch on this domain.

    Matched on word boundaries rather than raw substrings — ``cstr`` occurs
    inside ``docstring``, and a naive search reports the Core as contaminated
    by its own comments.
    """
    import re

    core = REPO_ROOT / "src" / "engcore" / "scientific"
    pattern = re.compile(
        r"\b(cstr|arrhenius|reactor|kinetics|coolant|concentration)\b",
        re.IGNORECASE,
    )
    offenders = []
    for path in core.rglob("*.py"):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {match.group(0)}")
    assert offenders == [], offenders


# =====================================================================
# Easy and stiff solves
# =====================================================================

def test_benign_regime_converges_and_is_usable(benign_result) -> None:
    assert benign_result.convergence is ConvergenceState.CONVERGED
    assert benign_result.is_usable is True
    assert benign_result.validation_status is ValidationOutcome.PASS


def test_a_single_solve_claims_only_dimensional_validity(benign_result) -> None:
    """F3: success must not be promoted to a higher validation claim."""
    assert benign_result.attained_levels == frozenset(
        {ValidationLevel.DIMENSIONALLY_VALID}
    )
    assert not benign_result.validation.claims(
        ValidationLevel.NUMERICALLY_CONVERGED
    )
    assert not benign_result.validation.claims(
        ValidationLevel.ANALYTICALLY_VERIFIED
    )


def test_the_per_solve_report_says_what_it_cannot_establish(
    benign_result,
) -> None:
    not_run = {c.name for c in benign_result.validation.not_run}
    assert "tolerance_independence" in not_run
    assert "analytic_invariant_agreement" in not_run
    assert "independent_steady_state_agreement" in not_run


def test_a_single_solve_reports_no_uncertainty_rather_than_inventing_one(
    benign_result,
) -> None:
    for name in benign_result.values:
        assert benign_result.uncertainty_of(name).kind is UncertaintyKind.UNKNOWN


def test_the_benign_regime_is_measurably_not_stiff() -> None:
    measurement = measure_stiffness(BENIGN, run_id_prefix="benign-stiff")
    assert measurement.stiff_completed and measurement.explicit_completed
    assert measurement.work_ratio < 5.0


def test_the_adiabatic_regime_is_measurably_stiff() -> None:
    measurement = measure_stiffness(ADIABATIC, run_id_prefix="adiabatic-stiff")
    assert measurement.stiff_completed
    assert measurement.work_ratio > 20.0


def test_a_strongly_stiff_regime_defeats_the_explicit_probe() -> None:
    """The explicit arm cannot finish; the ratio is a lower bound."""
    strong = reactor(
        "strong",
        op=operation(ua=0.0, tf=350.0, caf=2600.0, end=600.0),
        ca0=2600.0, t0=350.0, budget=200_000,
    )
    measurement = measure_stiffness(strong, run_id_prefix="strong-stiff")
    assert measurement.stiff_completed is True
    assert measurement.explicit_completed is False
    assert measurement.is_lower_bound is True
    assert measurement.explicit_outcome == "rhs_budget_exhausted"


def test_an_analytic_jacobian_is_supplied_to_the_implicit_methods() -> None:
    system = assemble(BENIGN)
    jacobian = system.jacobian(0.0, system.initial_state)
    assert jacobian.shape == (2, 2)
    assert np.all(np.isfinite(jacobian))
    # Compared against a central difference of the right-hand side.
    state = system.initial_state
    numeric = np.zeros((2, 2))
    for column in range(2):
        step = np.zeros(2)
        step[column] = 1e-6 * max(abs(state[column]), 1.0)
        numeric[:, column] = (
            system.rhs(0.0, state + step) - system.rhs(0.0, state - step)
        ) / (2.0 * step[column])
    assert np.allclose(jacobian, numeric, rtol=1e-4, atol=1e-8)


# =====================================================================
# Independent verification
# =====================================================================

def test_the_reference_never_imports_the_solver() -> None:
    """A verifier that shares code with the verified tests only the shared code."""
    source = (
        REPO_ROOT
        / "src" / "engcore" / "domains" / "kinetics" / "cstr" / "reference.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any("solver" in name for name in imported), imported
    assert not any("validation" in name for name in imported), imported


def test_the_reference_arrhenius_agrees_with_the_declarations_own() -> None:
    """Two independent implementations of the same physical law."""
    for temperature in (250.0, 350.0, 500.0, 900.0):
        assert math.isclose(
            arrhenius_rate_constant(
                temperature,
                k0_per_s=CHEMISTRY.k0_per_s,
                activation_energy_j_per_mol=CHEMISTRY.e_j_per_mol,
            ),
            CHEMISTRY.rate_constant_per_s(temperature),
            rel_tol=1e-12,
        )


def test_each_reported_steady_state_actually_zeroes_the_residual() -> None:
    run = reactor("ss", op=operation(tc=300.0, end=3600.0))
    found = steady_states(
        dilution_rate_per_s=run.operation.dilution_rate_per_s,
        feed_concentration_mol_per_m3=run.operation.caf_mol_per_m3,
        feed_temperature_k=run.operation.tf_k,
        coolant_temperature_k=run.operation.tc_k,
        beta_m3_k_per_mol=run.chemistry.beta_m3_k_per_mol,
        gamma_per_s=run.gamma_per_s,
        k0_per_s=run.chemistry.k0_per_s,
        activation_energy_j_per_mol=run.chemistry.e_j_per_mol,
        search_min_k=MIN_VALID_TEMPERATURE_K,
        search_max_k=MAX_VALID_TEMPERATURE_K,
    )
    assert len(found) == 3, "Tc = 300 K is inside the multiplicity window"
    for state in found:
        residual = steady_state_residual(
            state.temperature_k,
            dilution_rate_per_s=run.operation.dilution_rate_per_s,
            feed_concentration_mol_per_m3=run.operation.caf_mol_per_m3,
            feed_temperature_k=run.operation.tf_k,
            coolant_temperature_k=run.operation.tc_k,
            beta_m3_k_per_mol=run.chemistry.beta_m3_k_per_mol,
            gamma_per_s=run.gamma_per_s,
            k0_per_s=run.chemistry.k0_per_s,
            activation_energy_j_per_mol=run.chemistry.e_j_per_mol,
        )
        assert abs(residual) < 1e-9, (state.temperature_k, residual)


def test_the_invariant_guard_is_exact_zero_not_a_tolerance() -> None:
    """A nearly-adiabatic reactor must not earn the analytic claim."""
    assert invariant_is_exact(0.0) is True
    assert invariant_is_exact(1e-300) is False


def test_the_gate_awards_the_analytic_level_only_on_an_adiabatic_reactor(
    adiabatic_gate,
) -> None:
    assert ADIABATIC.operation.is_adiabatic
    assert adiabatic_gate.invariant_verified is True
    assert adiabatic_gate.invariant_max_rel_error <= INVARIANT_REL_TOL
    assert ValidationLevel.ANALYTICALLY_VERIFIED in adiabatic_gate.levels_earned

    cooled = run_verification_gate(BENIGN, run_id_prefix="cooled-gate")
    assert cooled.invariant_verified is False
    assert cooled.invariant_max_rel_error is None
    assert ValidationLevel.ANALYTICALLY_VERIFIED not in cooled.levels_earned
    # But the independent steady state is still available to it.
    assert ValidationLevel.CROSS_SOLVER_VALIDATED in cooled.levels_earned
    assert cooled.steady_state_rel_error <= STEADY_STATE_REL_TOL


def test_the_exact_invariant_matches_a_hand_evaluation() -> None:
    """The closed form, checked against its own definition at two times."""
    run = ADIABATIC
    a = run.operation.dilution_rate_per_s
    beta = run.chemistry.beta_m3_k_per_mol
    z_feed = run.operation.tf_k + beta * run.operation.caf_mol_per_m3
    z_zero = run.t0_k + beta * run.ca0_mol_per_m3
    times = np.array([0.0, 37.0, 600.0])
    expected = z_feed + (z_zero - z_feed) * np.exp(-a * times)
    actual = adiabatic_invariant_exact(
        times,
        dilution_rate_per_s=a,
        beta_m3_k_per_mol=beta,
        feed_concentration_mol_per_m3=run.operation.caf_mol_per_m3,
        feed_temperature_k=run.operation.tf_k,
        initial_concentration_mol_per_m3=run.ca0_mol_per_m3,
        initial_temperature_k=run.t0_k,
    )
    assert np.allclose(actual, expected, rtol=0.0, atol=0.0)


def test_the_gate_withholds_reference_levels_without_tolerance_independence(
) -> None:
    """Agreement without a convergent sequence behind it is not verification."""
    oscillatory = reactor(
        "oscillatory", op=operation(tc=305.0, end=6000.0), t0=300.0, npts=20001
    )
    gate = run_verification_gate(oscillatory, run_id_prefix="osc-gate")
    assert gate.tolerance_independent is False
    assert gate.levels_earned == ()


def test_the_cross_method_comparison_establishes_no_level(
    adiabatic_gate,
) -> None:
    """BDF and Radau share the right-hand side; agreement is not validation."""
    assert adiabatic_gate.cross_method_agrees is True
    report = adiabatic_gate.to_report()
    check = next(
        c for c in report.checks if c.name == "cross_method_agreement"
    )
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is None


def test_numerical_convergence_comes_only_from_the_ladder(
    adiabatic_gate,
) -> None:
    """A8: no single solve may award it."""
    assert adiabatic_gate.tolerance_independent is True
    assert ValidationLevel.NUMERICALLY_CONVERGED in adiabatic_gate.levels_earned
    assert len(adiabatic_gate.rungs) >= 3
    # Work must rise as the tolerance tightens, or the ladder is not a ladder.
    evaluations = [rung.rhs_evaluations for rung in adiabatic_gate.rungs]
    assert evaluations == sorted(evaluations)
    assert evaluations[-1] > evaluations[0]


# =====================================================================
# Failure semantics — the five cases, each distinct
# =====================================================================

def test_case_a_computational_limit_reports_max_iterations() -> None:
    constrained = reactor(
        "budget",
        op=operation(ua=0.0, tf=350.0, caf=2600.0, end=600.0),
        ca0=2600.0, t0=350.0, budget=500,
    )
    result = solve_reactor(constrained, run_id="budget-1")
    assert result.convergence is ConvergenceState.MAX_ITERATIONS
    assert result.is_usable is False
    assert result.values == {}, "a partial integration has no final state"
    numerics = result.metadata["numerics"]
    assert numerics["outcome"] == "rhs_budget_exhausted"
    assert 0.0 < numerics["fraction_of_horizon_completed"] < 1.0


def test_case_a_is_not_reported_as_a_failed_method() -> None:
    """MAX_ITERATIONS and FAILED say different things and must stay apart."""
    constrained = reactor(
        "budget2", op=operation(ua=0.0, caf=2600.0, end=600.0),
        ca0=2600.0, t0=350.0, budget=500,
    )
    result = solve_reactor(constrained, run_id="budget-2")
    assert result.convergence is not ConvergenceState.FAILED


def test_the_budget_error_carries_where_it_stopped() -> None:
    """P3.2: completed work and the refused call are different numbers."""
    system = assemble(reactor("tiny", budget=3))
    with pytest.raises(IntegrationBudgetExceeded) as caught:
        for _ in range(10):
            system.rhs(0.0, system.initial_state)
    assert caught.value.budget == 3
    # Exactly three evaluations were admitted and carried out...
    assert caught.value.completed == 3
    # ...and the fourth was refused. It is recorded as evidence that the run
    # was stopped rather than finished, but it is not work that happened.
    assert caught.value.attempted == 4
    assert caught.value.completed <= caught.value.budget


def test_a_budget_admits_exactly_its_own_number_of_evaluations() -> None:
    """P3.2: a budget of N means N completed evaluations, never N+1."""
    for budget in (1, 2, 7, 50):
        system = assemble(reactor(f"b{budget}", budget=budget))
        for _ in range(budget):
            system.rhs(0.0, system.initial_state)
        assert system.counter.completed == budget
        with pytest.raises(IntegrationBudgetExceeded) as caught:
            system.rhs(0.0, system.initial_state)
        assert caught.value.completed == budget
        assert caught.value.attempted == budget + 1


def test_the_reported_cost_never_exceeds_the_budget() -> None:
    """P3.2: the count a caller reads as 'what this cost' is bounded."""
    constrained = reactor(
        "budget-report",
        op=operation(ua=0.0, tf=350.0, caf=2600.0, end=600.0),
        ca0=2600.0, t0=350.0, budget=500,
    )
    result = solve_reactor(constrained, run_id="budget-report-1")
    numerics = result.metadata["numerics"]
    assert numerics["rhs_evaluations"] == 500
    assert numerics["rhs_evaluations_completed"] == 500
    assert numerics["rhs_evaluations_attempted"] == 501
    assert result.metadata["iterations"] == 500


def test_a_completed_run_reports_equal_completed_and_attempted() -> None:
    """Nothing was refused, so the two counts coincide."""
    result = solve_reactor(BENIGN, run_id="counts-1")
    numerics = result.metadata["numerics"]
    assert (
        numerics["rhs_evaluations_completed"]
        == numerics["rhs_evaluations_attempted"]
        == numerics["rhs_evaluations"]
    )


def test_case_b_step_size_collapse_reports_not_converged() -> None:
    """Driven by an injected finite-time singularity, not by a mock."""
    solver = CSTRSolver()
    run = reactor("collapse", budget=200_000)
    problem = build_cstr_problem(run, problem_id="collapse")
    solver.bind_run(run, problem.problem_id)
    prepared = solver.prepare(problem)
    system = prepared.payload
    original = system.rhs

    def singular(t, y):
        return original(t, y) + np.array([0.0, float(y[1]) ** 2])

    object.__setattr__(system, "rhs", singular)
    raw = solver.solve(prepared)

    assert raw.convergence is ConvergenceState.NOT_CONVERGED
    assert raw.diagnostics["outcome"] == "step_size_collapse"
    assert raw.diagnostics["scipy_status"] == -1
    # F2: the partial trajectory is evidence and must survive.
    assert raw.diagnostics["partial_time_s"]
    assert raw.diagnostics["reached_time_s"] > 0.0
    assert solver.extract_metrics(prepared, raw) == {}


def test_case_c_invalid_input_never_becomes_a_convergence_state() -> None:
    """Nothing converged or failed to converge, because nothing ran."""
    with pytest.raises(ReactorConfigurationError):
        operation(tf=-10.0)


def test_case_d_a_flawless_solve_outside_the_envelope_is_not_usable() -> None:
    runaway = reactor(
        "runaway",
        op=operation(ua=0.0, tf=350.0, caf=4000.0, end=300.0),
        ca0=4000.0, t0=350.0,
    )
    result = solve_reactor(runaway, run_id="runaway-1")
    # Execution succeeded...
    assert result.convergence is ConvergenceState.CONVERGED
    assert result.values, "metrics were extracted"
    # ...and the answer is still not usable.
    assert result.is_usable is False
    failing = {c.name for c in result.validation.failures}
    assert "state_physically_admissible" in failing
    assert result.metadata["numerics"]["max_temperature_k"] > MAX_VALID_TEMPERATURE_K


def test_case_d_execution_success_and_usability_are_independent() -> None:
    """A4: the two verdicts must be able to disagree in both directions."""
    runaway = reactor(
        "runaway2", op=operation(ua=0.0, caf=4000.0, end=300.0),
        ca0=4000.0, t0=350.0,
    )
    unusable = solve_reactor(runaway, run_id="runaway-2")
    usable = solve_reactor(BENIGN, run_id="usable-1")
    assert unusable.convergence == usable.convergence
    assert unusable.is_usable != usable.is_usable


def test_case_e_a_valid_result_reports_no_failing_check(benign_result) -> None:
    assert benign_result.validation.failures == ()
    assert benign_result.is_usable is True


def test_the_five_cases_do_not_collapse_onto_one_state() -> None:
    """Each case must be distinguishable from every other on the contract."""
    signatures = set()

    budget = solve_reactor(
        reactor("s-a", op=operation(ua=0.0, caf=2600.0, end=600.0),
                ca0=2600.0, t0=350.0, budget=500),
        run_id="sig-a",
    )
    runaway = solve_reactor(
        reactor("s-d", op=operation(ua=0.0, caf=4000.0, end=300.0),
                ca0=4000.0, t0=350.0),
        run_id="sig-d",
    )
    benign = solve_reactor(BENIGN, run_id="sig-e")
    for result in (budget, runaway, benign):
        signatures.add(
            (result.convergence.value, result.is_usable, bool(result.values))
        )
    assert len(signatures) == 3, signatures


# =====================================================================
# Invalid results cannot enter admitted evidence
# =====================================================================

def test_a_non_finite_value_can_never_become_a_quantity() -> None:
    """F4: the finiteness invariant lives at the Quantity boundary."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(UnitCompatibilityError):
            Quantity(bad, "kelvin")


def test_raw_output_may_carry_non_finite_diagnostics_but_metrics_may_not(
) -> None:
    """Raw backend output is the sanctioned home for non-finite values."""
    solver = CSTRSolver()
    run = reactor("nf", budget=200_000)
    problem = build_cstr_problem(run, problem_id="nf")
    solver.bind_run(run, problem.problem_id)
    prepared = solver.prepare(problem)
    original = prepared.payload.rhs

    def singular(t, y):
        return original(t, y) + np.array([0.0, float(y[1]) ** 2])

    object.__setattr__(prepared.payload, "rhs", singular)
    raw = solver.solve(prepared)
    assert not raw.succeeded
    assert solver.extract_metrics(prepared, raw) == {}


def test_an_unearned_validation_level_cannot_be_deserialized(
    benign_result,
) -> None:
    payload = benign_result.to_dict()
    payload["validation"]["attained_levels"].append("experimentally_validated")
    with pytest.raises(ScientificValidationError):
        ScientificResult.from_dict(payload)


def test_the_result_is_immutable(benign_result) -> None:
    assert dataclasses.is_dataclass(benign_result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        benign_result.convergence = ConvergenceState.FAILED  # type: ignore


# =====================================================================
# Provenance and replay
# =====================================================================

def test_provenance_records_everything_needed_to_reproduce(
    benign_result,
) -> None:
    provenance = benign_result.provenance
    assert provenance.run_id
    assert provenance.software_version
    assert provenance.models == (("kinetics.cstr.nonisothermal_first_order", "0.1.0"),)
    assert provenance.solvers == (("kinetics.cstr.scipy_implicit_ivp", "0.1.0"),)
    assert provenance.metadata["integration_method"] == "BDF"
    assert set(provenance.tolerances) >= {
        "rtol", "atol_concentration", "atol_temperature", "max_rhs_evaluations"
    }
    assert provenance.assumptions
    assert provenance.metadata["physics_fingerprint"]


def test_every_provenance_input_is_a_unit_carrying_quantity(
    benign_result,
) -> None:
    required = {
        "k0", "activation_energy", "heat_of_reaction", "density",
        "heat_capacity", "volume", "flow_rate", "feed_concentration",
        "feed_temperature", "coolant_temperature", "ua", "end_time",
        "initial_concentration", "initial_temperature", "molar_gas_constant",
    }
    assert required <= set(benign_result.provenance.inputs)
    for name, value in benign_result.provenance.inputs.items():
        assert isinstance(value, Quantity), name


def test_the_solver_backend_identity_records_the_library_version(
    benign_result,
) -> None:
    assert "scipy" in benign_result.solver.backend


def test_a_result_round_trips_through_serialization(benign_result) -> None:
    restored = ScientificResult.from_dict(benign_result.to_dict())
    assert restored.result_id == benign_result.result_id
    assert restored.convergence is benign_result.convergence
    assert restored.attained_levels == benign_result.attained_levels
    for name, value in benign_result.values.items():
        assert math.isclose(
            restored.value(name).magnitude, value.magnitude, rel_tol=0.0
        )
        assert restored.value(name).units == value.units


def test_the_run_is_deterministic() -> None:
    """No randomness anywhere: identical declarations give identical numbers."""
    first = solve_reactor(BENIGN, run_id="determinism-1")
    second = solve_reactor(BENIGN, run_id="determinism-2")
    for name in first.values:
        assert first.value(name).magnitude == second.value(name).magnitude
    assert (
        first.metadata["numerics"]["rhs_evaluations"]
        == second.metadata["numerics"]["rhs_evaluations"]
    )


def test_the_physics_fingerprint_ignores_numerics_and_tracks_physics() -> None:
    refined = BENIGN.with_integration(
        BENIGN.integration.with_tolerances(
            rtol=1e-12, atol_concentration=1e-12, atol_temperature=1e-12
        )
    )
    assert refined.physics_fingerprint() == BENIGN.physics_fingerprint()
    hotter = reactor("hot", op=operation(tc=305.0))
    assert hotter.physics_fingerprint() != BENIGN.physics_fingerprint()


# =====================================================================
# Adversarial
# =====================================================================

def test_output_density_does_not_change_the_integration_path() -> None:
    """t_eval must never steer the solver; only report it."""
    sparse = solve_reactor(
        BENIGN.with_integration(
            IntegrationSettings(
                method="BDF", rtol=1e-8, atol_concentration=1e-8,
                atol_temperature=1e-8, n_output_points=11,
            )
        ),
        run_id="sparse",
    )
    dense = solve_reactor(
        BENIGN.with_integration(
            IntegrationSettings(
                method="BDF", rtol=1e-8, atol_concentration=1e-8,
                atol_temperature=1e-8, n_output_points=20001,
            )
        ),
        run_id="dense",
    )
    assert (
        sparse.metadata["numerics"]["rhs_evaluations"]
        == dense.metadata["numerics"]["rhs_evaluations"]
    )
    assert (
        sparse.value(T_FINAL_METRIC).magnitude
        == dense.value(T_FINAL_METRIC).magnitude
    )


def test_the_peak_is_read_from_the_solvers_own_steps_not_a_uniform_grid() -> None:
    """A sharp ignition peak must not be missed by coarse reporting."""
    igniting = reactor(
        "peak", op=operation(tc=300.0, end=3600.0), t0=450.0, npts=11
    )
    result = solve_reactor(igniting, run_id="peak-1")
    peak = result.value(T_MAX_METRIC).magnitude
    # The peak is far above anything an 11-point uniform sample would see: the
    # excursion is over within a fraction of one sample interval.
    assert peak > 600.0
    assert result.value(T_AT_MAX_METRIC).magnitude < 1.0


def test_the_explicit_probe_is_never_given_the_analytic_jacobian() -> None:
    """The measuring instrument must not get an advantage the subject lacks."""
    probe = BENIGN.with_integration(BENIGN.integration.with_method("RK45"))
    result = solve_reactor(probe, run_id="probe-1")
    assert result.convergence is ConvergenceState.CONVERGED
    assert result.metadata["numerics"]["scipy_njev"] == 0


def test_a_reactor_that_cannot_react_still_solves_and_conserves() -> None:
    """Adversarial limiting case: k0 tiny, so the tank is a mixing vessel.

    With no reaction the concentration must relax to the feed value on the
    residence time, which is an elementary exponential the reactor cannot get
    wrong for an interesting reason — so getting it wrong would be a real bug.
    """
    inert = ReactorChemistry(
        k0=Q(1e-30, "1/s"),
        activation_energy=CHEMISTRY.activation_energy,
        heat_of_reaction=CHEMISTRY.heat_of_reaction,
        density=CHEMISTRY.density,
        heat_capacity=CHEMISTRY.heat_capacity,
    )
    run = ReactorRun(
        run_label="inert",
        chemistry=inert,
        operation=operation(ua=0.0, tf=350.0, caf=1000.0, end=600.0),
        initial_concentration=Q(0.0, "mol/m**3"),
        initial_temperature=Q(300.0, "kelvin"),
        integration=IntegrationSettings(rtol=1e-10, atol_concentration=1e-10,
                                        atol_temperature=1e-10),
    )
    result = solve_reactor(run, run_id="inert-1")
    a = run.operation.dilution_rate_per_s
    end = run.operation.end_time_s
    expected_c = 1000.0 * (1.0 - math.exp(-a * end))
    expected_t = 350.0 + (300.0 - 350.0) * math.exp(-a * end)
    assert math.isclose(
        result.value(CA_FINAL_METRIC).magnitude, expected_c, rel_tol=1e-8
    )
    assert math.isclose(
        result.value(T_FINAL_METRIC).magnitude, expected_t, rel_tol=1e-8
    )


def test_the_gate_refuses_a_ladder_too_short_to_show_a_trend() -> None:
    from src.engcore.domains.kinetics.cstr.validation import ToleranceRung

    with pytest.raises(ValueError):
        run_verification_gate(
            BENIGN, ladder=(ToleranceRung(1e-8, 1e-8, 1e-8),),
            run_id_prefix="short",
        )


def test_stationarity_is_required_before_a_steady_state_is_claimed() -> None:
    """A trajectory still moving cannot be compared to a steady state."""
    short = reactor("short-horizon", op=operation(tc=290.0, end=60.0))
    gate = run_verification_gate(short, run_id_prefix="short-horizon")
    assert gate.steady_state_verified is False
    assert gate.steady_state_rel_error is None
    assert "not settled" in gate.steady_state_detail


# =====================================================================
# P1.1 — the two commit identities must not be confusable
# =====================================================================

#: A stand-in for "the frozen Core baseline" and "the revision that ran".
#: Deliberately different strings: the whole point is that they are answers to
#: different questions and must never share a field.
_BASELINE = "0" * 40
_SOURCE = "f" * 40


def test_provenance_records_the_executing_revision_not_the_baseline() -> None:
    result = solve_reactor(
        BENIGN,
        run_id="commit-identity-1",
        source_commit=_SOURCE,
        core_baseline_commit=_BASELINE,
    )
    # git_commit answers "which revision produced this?"
    assert result.provenance.git_commit == _SOURCE
    # The baseline is context and lives under its own name.
    assert result.provenance.metadata["core_baseline_commit"] == _BASELINE
    assert result.provenance.git_commit != _BASELINE


def test_the_two_commit_identities_are_separate_fields() -> None:
    """Neither can be read out of the other's slot."""
    result = solve_reactor(
        BENIGN,
        run_id="commit-identity-2",
        source_commit=_SOURCE,
        core_baseline_commit=_BASELINE,
    )
    payload = result.provenance.to_dict()
    assert payload["git_commit"] == _SOURCE
    assert payload["metadata"]["core_baseline_commit"] == _BASELINE
    # The record states which is which, so a downstream reader cannot guess.
    assert "source revision" in payload["metadata"]["commit_identity_semantics"]


def test_an_omitted_source_revision_is_recorded_as_absent_not_invented() -> None:
    result = solve_reactor(
        BENIGN, run_id="commit-identity-3", core_baseline_commit=_BASELINE
    )
    assert result.provenance.git_commit is None
    assert result.provenance.metadata["core_baseline_commit"] == _BASELINE


def test_the_scientific_core_never_harvests_a_commit() -> None:
    """P1.1: the revision is caller-supplied; the core collects nothing."""
    import re

    core = REPO_ROOT / "src" / "engcore" / "scientific"
    pattern = re.compile(r"subprocess|rev-parse|GitPython|\bdulwich\b")
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in core.rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], offenders


def test_the_experiment_never_passes_the_baseline_as_the_source_revision(
) -> None:
    """The original defect, pinned so it cannot come back."""
    source = (
        REPO_ROOT / "experiments" / "kinetics_k1" / "k1_run.py"
    ).read_text(encoding="utf-8")
    assert "source_commit=BASE_COMMIT" not in source
    assert "git_commit=BASE_COMMIT" not in source
    assert "core_baseline_commit=BASE_COMMIT" in source


def test_the_resolved_source_revision_is_not_the_core_baseline() -> None:
    """Resolution happens at the experiment layer and returns a real answer."""
    from experiments.kinetics_k1 import BASE_COMMIT
    from experiments.kinetics_k1.k1_run import resolve_source_commit

    resolved = resolve_source_commit()
    assert resolved == "unknown" or re.fullmatch(r"[0-9a-f]{40}", resolved)
    # K1's own commits postdate the frozen Core baseline, so a correctly
    # resolved revision can never equal it.
    assert resolved != BASE_COMMIT


# =====================================================================
# P1.2 — an unusable result may not earn a validation level
# =====================================================================

def _runaway() -> ReactorRun:
    """R8's physics: a flawless integration that leaves the envelope."""
    return reactor(
        "gate-runaway",
        op=operation(ua=0.0, tf=350.0, caf=4000.0, end=300.0),
        ca0=4000.0, t0=350.0,
    )


def test_the_gate_awards_nothing_to_a_converged_but_unusable_run() -> None:
    """P1.2: metrics present is not the same as evidence about accuracy."""
    runaway = _runaway()
    # Precondition: every rung really does converge and produce metrics.
    single = solve_reactor(runaway, run_id="gate-runaway-single")
    assert single.convergence is ConvergenceState.CONVERGED
    assert single.values
    assert single.is_usable is False

    gate = run_verification_gate(runaway, run_id_prefix="gate-runaway")
    assert gate.tolerance_independent is False
    assert gate.levels_earned == ()
    assert gate.invariant_verified is False
    assert gate.steady_state_verified is False


def test_the_gate_records_why_an_unusable_rung_was_withheld() -> None:
    gate = run_verification_gate(_runaway(), run_id_prefix="gate-runaway-why")
    assert "not usable" in gate.tolerance_detail
    assert "validity envelope" in gate.tolerance_detail

    # Withheld, not relabelled as a failure. Most rungs converge perfectly well
    # and are refused only because the trajectory leaves the model's envelope,
    # which is the distinction P1.2 exists to preserve.
    completed_but_refused = [
        rung for rung in gate.rungs if rung.converged and not rung.usable
    ]
    assert completed_but_refused, "no rung exercised the converged/unusable case"
    assert all(rung.unusable_reason for rung in completed_but_refused)

    # Not one rung, by either route, may count as evidence about accuracy.
    assert all(not rung.counts_toward_verification for rung in gate.rungs)


def test_an_unusable_rung_never_becomes_the_reference_for_a_comparison(
) -> None:
    """The reference comparisons must not be taken against a refused result."""
    gate = run_verification_gate(_runaway(), run_id_prefix="gate-runaway-ref")
    assert gate.invariant_max_rel_error is None
    assert gate.steady_state_rel_error is None
    assert gate.cross_method_agrees is None


def test_a_usable_run_still_earns_its_levels() -> None:
    """P1.2 must not have made the gate unable to award anything."""
    gate = run_verification_gate(ADIABATIC, run_id_prefix="gate-usable")
    assert all(rung.counts_toward_verification for rung in gate.rungs)
    assert ValidationLevel.NUMERICALLY_CONVERGED in gate.levels_earned


# =====================================================================
# P2.1 — the envelope is assessed over dense samples too
# =====================================================================

def test_the_envelope_bound_is_never_looser_than_the_nodes_alone() -> None:
    """The union can only tighten the reported excursion."""
    for label, run in (
        ("benign", BENIGN),
        ("adiabatic", ADIABATIC),
        ("runaway", _runaway()),
    ):
        solver = CSTRSolver()
        problem = build_cstr_problem(run, problem_id=f"env-{label}")
        solver.bind_run(run, problem.problem_id)
        raw = solver.solve(solver.prepare(problem))
        d = raw.diagnostics
        assert d["max_temperature_k"] >= d["max_temperature_k_nodes_only"], label
        assert (
            d["min_concentration_mol_per_m3"]
            <= d["min_concentration_mol_per_m3_nodes_only"]
        ), label
        # Strictly more evidence than the nodes alone.
        assert d["envelope_sample_count"] > d["accepted_steps"] + 1, label


def test_dense_sampling_catches_an_excursion_the_nodes_miss() -> None:
    """P2.1 adversarial: a case where the node hull is genuinely not enough.

    Radau's collocation interpolant is a polynomial through the stage values,
    and at a loose tolerance it leaves the hull of the accepted nodes. The
    excursion is small here, but it is real and reproducible, and it is exactly
    the class of event an accepted-nodes-only envelope cannot see.
    """
    run = reactor(
        "radau-interp",
        op=operation(ua=0.0, tf=350.0, caf=2600.0, end=600.0),
        ca0=2600.0, t0=350.0, method="Radau", rtol=1e-3, npts=200001,
    )
    run = run.with_integration(
        run.integration.with_tolerances(
            rtol=1e-3, atol_concentration=1e-1, atol_temperature=1e-1
        )
    )
    solver = CSTRSolver()
    problem = build_cstr_problem(run, problem_id="radau-interp")
    solver.bind_run(run, problem.problem_id)
    raw = solver.solve(solver.prepare(problem))
    d = raw.diagnostics
    assert raw.convergence is ConvergenceState.CONVERGED
    # The dense sample finds state the accepted nodes never reported.
    assert (
        d["min_concentration_mol_per_m3"]
        < d["min_concentration_mol_per_m3_nodes_only"]
    )


def test_the_envelope_does_not_claim_an_exact_continuous_extremum() -> None:
    """A sampled bound must say it is one."""
    solver = CSTRSolver()
    problem = build_cstr_problem(BENIGN, problem_id="env-claim")
    solver.bind_run(BENIGN, problem.problem_id)
    raw = solver.solve(solver.prepare(problem))
    sampling = raw.diagnostics["envelope_sampling"]
    assert "sampled bound" in sampling
    assert "not an exact continuous extremum" in sampling


# =====================================================================
# P2.2 — the steady-state search promises transversal roots only
# =====================================================================

def _find_states(tc: float, **kwargs):
    run = reactor("ss-scan", op=operation(tc=tc, end=3600.0))
    return steady_states(
        dilution_rate_per_s=run.operation.dilution_rate_per_s,
        feed_concentration_mol_per_m3=run.operation.caf_mol_per_m3,
        feed_temperature_k=run.operation.tf_k,
        coolant_temperature_k=run.operation.tc_k,
        beta_m3_k_per_mol=run.chemistry.beta_m3_k_per_mol,
        gamma_per_s=run.gamma_per_s,
        k0_per_s=run.chemistry.k0_per_s,
        activation_energy_j_per_mol=run.chemistry.e_j_per_mol,
        search_min_k=MIN_VALID_TEMPERATURE_K,
        search_max_k=MAX_VALID_TEMPERATURE_K,
        **kwargs,
    ), run


def test_a_coarse_scan_misses_a_close_pair_rather_than_inventing_one() -> None:
    """P2.2: the documented shortfall is real, and it fails safely."""
    coarse, run = _find_states(300.0, scan_points=11)
    dense, _ = _find_states(300.0)
    assert len(dense) == 3
    # The upper pair sits ~20 K apart; an 11-point scan over 750 K steps over
    # them. Fewer roots, never a spurious one.
    assert len(coarse) < len(dense)
    for state in coarse:
        residual = steady_state_residual(
            state.temperature_k,
            dilution_rate_per_s=run.operation.dilution_rate_per_s,
            feed_concentration_mol_per_m3=run.operation.caf_mol_per_m3,
            feed_temperature_k=run.operation.tf_k,
            coolant_temperature_k=run.operation.tc_k,
            beta_m3_k_per_mol=run.chemistry.beta_m3_k_per_mol,
            gamma_per_s=run.gamma_per_s,
            k0_per_s=run.chemistry.k0_per_s,
            activation_energy_j_per_mol=run.chemistry.e_j_per_mol,
        )
        assert abs(residual) < 1e-9


def test_the_search_states_that_it_finds_transversal_roots_only() -> None:
    from src.engcore.domains.kinetics.cstr.reference import SEARCH_SEMANTICS

    assert "transversal" in SEARCH_SEMANTICS
    assert "does not change sign" in SEARCH_SEMANTICS
    assert "Never reports a root that is not one" in SEARCH_SEMANTICS
    # The docstring must promise transversal roots and explicitly disclaim the
    # stronger reading, rather than silently omitting it.
    assert "transversal" in steady_states.__doc__
    assert "NOT a promise to return every stationary point" in (
        steady_states.__doc__
    )


def test_the_gate_carries_the_search_semantics_into_its_record() -> None:
    """A stored count must not be readable as 'all steady states'."""
    gate = run_verification_gate(BENIGN, run_id_prefix="ss-semantics")
    payload = gate.to_dict()
    assert "transversal" in payload["steady_state_search_semantics"]


# =====================================================================
# P3.1 — the two inaccurate scientific claims must not reappear
# =====================================================================

#: Words that mark a nearby mention of a wrong claim as a *correction* of it
#: rather than an assertion of it. Checked on a normalized window, because the
#: corrections are wrapped across comment lines and carry markdown emphasis, so
#: an exact-substring negation check misses them.
_NEGATION = re.compile(r"\b(not|never|false|wrong|incorrect|rules out)\b", re.I)


def _affirmative_claims(phrase: str, *, skip_names: frozenset[str]) -> list[str]:
    """Files asserting ``phrase`` without a negation in its neighbourhood.

    The scan deliberately skips this test module: it necessarily contains every
    phrase it is looking for, as the pattern it searches with.
    """
    offenders: list[str] = []
    pattern = re.compile(re.escape(phrase))
    for root in ("src", "tests", "experiments", "docs"):
        for path in (REPO_ROOT / root).rglob("*"):
            if path.suffix not in (".py", ".md") or not path.is_file():
                continue
            if path.name in skip_names:
                continue
            text = path.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                window = text[max(0, match.start() - 260):match.end() + 260]
                # Collapse comment prefixes, line breaks and markdown emphasis
                # so "**not**\n    #: L-stable" reads as ordinary prose.
                normalized = re.sub(r"[*`]|\n\s*#:?", " ", window)
                if _NEGATION.search(normalized):
                    continue
                offenders.append(str(path.relative_to(REPO_ROOT)))
    return offenders


def test_no_source_file_claims_the_arrhenius_derivative_is_unbounded() -> None:
    """As T -> infinity, k -> k0 and dk/dT -> 0. It is not unbounded."""
    offenders = _affirmative_claims(
        "grows without bound", skip_names=frozenset({Path(__file__).name})
    )
    assert offenders == [], offenders


def test_no_source_file_claims_bdf_is_l_stable_at_every_order() -> None:
    """BDF is A-stable only at orders 1-2; L-stability does not hold above it."""
    offenders = _affirmative_claims(
        "L-stable at every order",
        # The frozen preregistration JSON is hashed and cannot be edited; its
        # erratum lives in k1_config.PREREGISTRATION_ERRATA instead.
        skip_names=frozenset({Path(__file__).name, "k1_config_frozen.json"}),
    )
    assert offenders == [], offenders


def test_the_frozen_preregistration_erratum_is_recorded() -> None:
    """The one wrong claim that cannot be edited must be corrected beside it."""
    from experiments.kinetics_k1.k1_config import (
        PREREGISTRATION_ERRATA,
        config_hash,
        config_payload,
    )

    assert PREREGISTRATION_ERRATA
    erratum = PREREGISTRATION_ERRATA[0]
    assert erratum["field"] == "integration.method_justification"
    assert "A-stable only at orders 1-2" in erratum["correction"]
    assert erratum["affects_any_result"] is False
    # Recording an erratum must not disturb the freeze it is an erratum about.
    payload = json.dumps(config_payload(), sort_keys=True, separators=(",", ":"))
    assert "PREREGISTRATION_ERRATA" not in payload
    assert hashlib.sha256(payload.encode("utf-8")).hexdigest() == config_hash()


def test_the_stiff_method_note_states_bdf_stability_accurately() -> None:
    from src.engcore.domains.kinetics.cstr import problem as problem_module

    source = Path(problem_module.__file__).read_text(encoding="utf-8")
    assert "stiffly stable" in source
    assert "A-stable only at" in source
    # Radau IIA genuinely is L-stable, and that claim stays.
    assert "Radau IIA (order 5) is A-stable AND L-stable" in source


# =====================================================================
# P3.3 — counts must be declared as genuine integers
# =====================================================================

@pytest.mark.parametrize("field", ["max_rhs_evaluations", "n_output_points"])
@pytest.mark.parametrize(
    "value",
    [
        500.9,                 # fractional: would silently truncate to 500
        2000.7,
        500.0,                 # integral float is still not an int declaration
        "500",
        True,                  # bool is an int subclass and would read as 1
        False,
        float("nan"),
        float("inf"),
        None,
    ],
)
def test_a_count_must_be_declared_as_an_integer(field, value) -> None:
    with pytest.raises(ReactorConfigurationError):
        IntegrationSettings(**{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_rhs_evaluations", 0),
        ("max_rhs_evaluations", -1),
        ("n_output_points", 0),
        ("n_output_points", 1),
        ("n_output_points", -5),
    ],
)
def test_an_out_of_range_count_is_refused(field, value) -> None:
    with pytest.raises(ReactorConfigurationError):
        IntegrationSettings(**{field: value})


@pytest.mark.parametrize(
    "field,value",
    [("max_rhs_evaluations", 1), ("max_rhs_evaluations", 500),
     ("n_output_points", 2), ("n_output_points", 2001)],
)
def test_a_valid_integer_count_is_accepted(field, value) -> None:
    settings = IntegrationSettings(**{field: value})
    assert getattr(settings, field) == value
    assert isinstance(getattr(settings, field), int)
