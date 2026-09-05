"""1D transient conduction — solver contract and verification gate.

The claim under test: a genuine time-dependent PDE satisfies the frozen
``ScientificSolver`` contract and earns a defensible verification result
without any change to SRIA core.

These are domain tests only. No inference, no campaign, no certification.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

from src.engcore.domains.thermal.conduction1d import (
    ANALYTIC_REL_TOL,
    CONVERGENCE_MIN_CONTRACTION,
    LEFT_METRIC,
    MAX_METRIC,
    MIDPOINT_METRIC,
    RIGHT_METRIC,
    VERIFICATION_LADDER,
    Conduction1DSolver,
    ConductionSlab,
    RefinementRung,
    SlabBindingError,
    SlabConfigurationError,
    SlabDiscretization,
    ThermalConduction1DError,
    build_conduction_problem,
    exact_field,
    exact_midpoint,
    run_verification_gate,
    solve_slab,
)

# White-box: `assemble` is an implementation detail and is deliberately not on
# the package's public surface, so this test reaches into its own module.
from src.engcore.domains.thermal.conduction1d.solver import assemble
from src.engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
)
from src.engcore.scientific.solvers.protocol import (
    ConvergenceState,
    ScientificSolver,
)
from src.engcore.scientific.units.quantity import Quantity

LENGTH = Quantity(0.1, "meter")
ALPHA = Quantity(1.2e-5, "m**2/s")
END_TIME = Quantity(60.0, "second")
FIELD = "dimensionless"


def make_slab(n_cells: int = 64, n_steps: int = 80, slab_id: str = "test") -> ConductionSlab:
    return ConductionSlab(
        slab_id=slab_id,
        length=LENGTH,
        diffusivity=ALPHA,
        end_time=END_TIME,
        discretization=SlabDiscretization(n_cells, n_steps),
    )


def analytic_qoi() -> float:
    return exact_midpoint(length_m=0.1, alpha_m2_s=1.2e-5, time_s=60.0)


# =====================================================================
# 1-2. Contract and determinism
# =====================================================================

def test_1_satisfies_the_scientific_solver_protocol():
    solver = Conduction1DSolver()
    assert isinstance(solver, ScientificSolver)
    for stage in ("supports", "prepare", "solve", "validate", "extract_metrics"):
        assert callable(getattr(solver, stage))
    assert solver.identity.solver_id == "thermal.conduction1d.backward_euler_fd"
    assert solver.identity.backend == "scipy.sparse.linalg.splu"

    slab = make_slab()
    problem = build_conduction_problem(slab)
    assert solver.supports(problem) is True
    # supports() is a capability question and must not need a binding.
    assert solver.bound_slab(problem.problem_id) is None
    # ...and prepare without one is an error, not a claim of incompatibility.
    with pytest.raises(ThermalConduction1DError):
        solver.prepare(problem)


def test_1b_rejects_a_problem_from_another_domain():
    from src.engcore.domains.electrical.dc import DCCircuit, ElectricalNode, Resistor
    from src.engcore.domains.electrical.dc import DCVoltageSource, build_dc_problem

    circuit = DCCircuit(
        circuit_id="foreign",
        nodes=(
            ElectricalNode(node_id="a"),
            ElectricalNode(node_id="gnd", is_reference=True),
        ),
        resistors=(
            Resistor(
                component_id="R1",
                node_a="a",
                node_b="gnd",
                resistance=Quantity(1000.0, "ohm"),
            ),
        ),
        voltage_sources=(
            DCVoltageSource(
                component_id="V1",
                positive_node="a",
                negative_node="gnd",
                voltage=Quantity(1.0, "volt"),
            ),
        ),
    )
    assert Conduction1DSolver().supports(build_dc_problem(circuit)) is False
    assert Conduction1DSolver().supports(object()) is False


def test_2_solve_is_deterministic():
    first = solve_slab(make_slab(), run_id="det-a")
    second = solve_slab(make_slab(), run_id="det-b")
    for name in (MIDPOINT_METRIC, MAX_METRIC, LEFT_METRIC, RIGHT_METRIC):
        assert first.values[name].magnitude_in(FIELD) == (
            second.values[name].magnitude_in(FIELD)
        )
    assert first.metadata["numerics"] == second.metadata["numerics"]


# =====================================================================
# 3-5. The physics the benchmark declares
# =====================================================================

def test_3_boundary_conditions_are_respected():
    result = solve_slab(make_slab(), run_id="bc")
    assert result.values[LEFT_METRIC].magnitude_in(FIELD) == 0.0
    assert result.values[RIGHT_METRIC].magnitude_in(FIELD) == 0.0
    check = next(
        c for c in result.validation.checks if c.name == "boundary_conditions_held"
    )
    assert check.outcome is ValidationOutcome.PASS


def test_4_initial_condition_is_represented_correctly():
    slab = make_slab(n_cells=32, n_steps=40)
    system = assemble(slab)
    interior = system.x_nodes[1:-1]
    expected = np.sin(np.pi * interior / slab.length_m)
    assert np.allclose(system.initial_interior, expected, rtol=0.0, atol=1e-15)
    # The midpoint really is a node, so the QoI needs no interpolation.
    assert system.x_nodes[system.midpoint_index] == pytest.approx(
        slab.length_m / 2.0, abs=1e-15
    )
    assert system.initial_interior.max() == pytest.approx(1.0, abs=1e-12)


def test_5_solution_decays_as_this_benchmark_requires():
    result = solve_slab(make_slab(), run_id="decay")
    final_max = result.values[MAX_METRIC].magnitude_in(FIELD)
    assert 0.0 < final_max < 1.0
    check = next(
        c for c in result.validation.checks if c.name == "amplitude_decay"
    )
    assert check.outcome is ValidationOutcome.PASS
    # Longer time must decay further; the sign of the exponent is not free.
    longer = ConductionSlab(
        slab_id="longer",
        length=LENGTH,
        diffusivity=ALPHA,
        end_time=Quantity(120.0, "second"),
        discretization=SlabDiscretization(64, 160),
    )
    later = solve_slab(longer, run_id="decay-2")
    assert later.values[MAX_METRIC].magnitude_in(FIELD) < final_max


def test_5b_reference_is_independent_of_the_solver():
    """A verification that shares code with the solver verifies nothing."""
    import src.engcore.domains.thermal.conduction1d.reference as reference

    tree = ast.parse(Path(reference.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("solver" in name for name in imported), imported
    assert not any("validation" in name for name in imported), imported

    # And it satisfies the PDE it claims to solve, checked numerically.
    x = np.linspace(0.0, 0.1, 2001)[1:-1]
    t, dt, dx = 30.0, 1e-4, 0.1 / 2000
    u = exact_field(x, length_m=0.1, alpha_m2_s=1.2e-5, time_s=t)
    u_next = exact_field(x, length_m=0.1, alpha_m2_s=1.2e-5, time_s=t + dt)
    du_dt = (u_next - u) / dt
    d2u_dx2 = (u[2:] - 2.0 * u[1:-1] + u[:-2]) / dx**2
    assert np.allclose(du_dt[1:-1], 1.2e-5 * d2u_dx2, rtol=1e-4, atol=1e-9)


# =====================================================================
# 6-8. Convergence toward the independent reference
# =====================================================================

def test_6_qoi_converges_toward_the_analytic_reference():
    analytic = analytic_qoi()
    errors = []
    for rung in (RefinementRung(8, 10), RefinementRung(64, 80), RefinementRung(256, 320)):
        slab = make_slab(rung.n_cells, rung.n_steps)
        result = solve_slab(slab, run_id=f"conv-{rung.n_cells}")
        qoi = result.values[MIDPOINT_METRIC].magnitude_in(FIELD)
        errors.append(abs(qoi - analytic))
    assert errors[0] > errors[1] > errors[2]
    assert errors[-1] < 1e-3


def test_7_combined_refinement_error_decreases_monotonically():
    report = run_verification_gate(make_slab(), run_id_prefix="mono")
    errors = [r.abs_error for r in report.rungs]
    assert len(errors) == len(VERIFICATION_LADDER)
    assert all(b < a for a, b in zip(errors, errors[1:]))
    ratios = [r.error_ratio for r in report.rungs if r.error_ratio is not None]
    assert all(ratio > CONVERGENCE_MIN_CONTRACTION for ratio in ratios)
    # Work grows while error falls — the trade the ladder exists to expose.
    work = [r.work_proxy for r in report.rungs]
    assert all(b > a for a, b in zip(work, work[1:]))


def test_8_finest_analytic_error_is_below_the_declared_tolerance():
    report = run_verification_gate(make_slab(), run_id_prefix="tol")
    finest = report.rungs[-1]
    assert finest.rel_error < ANALYTIC_REL_TOL
    assert finest.analytic == pytest.approx(analytic_qoi(), rel=0.0, abs=0.0)


# =====================================================================
# 9-11. The levels are earned, never assumed
# =====================================================================

def test_9_analytically_verified_requires_the_full_gate():
    report = run_verification_gate(make_slab(), run_id_prefix="earn")
    assert report.numerically_converged is True
    assert report.analytically_verified is True
    assert ValidationLevel.ANALYTICALLY_VERIFIED in report.levels_earned

    # Tolerance alone is not enough: with convergence made unreachable, the
    # finest rung still agrees with the reference and the level is WITHHELD.
    strict = run_verification_gate(
        make_slab(), run_id_prefix="earn-b", min_contraction=10.0
    )
    assert strict.rungs[-1].rel_error < ANALYTIC_REL_TOL
    assert strict.numerically_converged is False
    assert strict.analytically_verified is False
    assert strict.levels_earned == ()
    assert "not verification" in strict.analytic_detail


def test_10_numerically_converged_requires_the_convergence_gate():
    report = run_verification_gate(make_slab(), run_id_prefix="numconv")
    assert ValidationLevel.NUMERICALLY_CONVERGED in report.levels_earned

    # A ladder too short to show a trend earns nothing.
    short = run_verification_gate(
        make_slab(),
        run_id_prefix="numconv-short",
        ladder=(RefinementRung(8, 10), RefinementRung(16, 20)),
    )
    assert short.numerically_converged is False
    assert short.analytically_verified is False
    assert "rungs" in short.convergence_detail

    # Converged but not accurate enough: only the weaker level is earned.
    tight = run_verification_gate(
        make_slab(), run_id_prefix="numconv-tight", analytic_rel_tol=1e-9
    )
    assert tight.numerically_converged is True
    assert tight.analytically_verified is False
    assert tight.levels_earned == (ValidationLevel.NUMERICALLY_CONVERGED,)


def test_11_a_single_coarse_solve_never_receives_the_strongest_levels():
    coarse = solve_slab(make_slab(8, 10), run_id="coarse")
    fine = solve_slab(make_slab(512, 640), run_id="fine")
    analytic = analytic_qoi()
    coarse_error = abs(coarse.values[MIDPOINT_METRIC].magnitude_in(FIELD) - analytic)
    assert coarse_error > 1e-2      # genuinely inaccurate

    for result in (coarse, fine):
        levels = {c.establishes for c in result.validation.checks if c.establishes}
        assert levels == {ValidationLevel.DIMENSIONALLY_VALID}
        assert ValidationLevel.NUMERICALLY_CONVERGED not in levels
        assert ValidationLevel.ANALYTICALLY_VERIFIED not in levels
        # ...and the report says so rather than staying silent.
        for name in ("discretization_convergence", "analytic_reference_agreement"):
            check = next(c for c in result.validation.checks if c.name == name)
            assert check.outcome is ValidationOutcome.NOT_RUN

    # The coarse solve is nonetheless a valid solve: its linear algebra is fine.
    residual = next(
        c for c in coarse.validation.checks if c.name == "linear_system_residual"
    )
    assert residual.outcome is ValidationOutcome.PASS
    assert residual.establishes is None


# =====================================================================
# 12. Diagnostics survive
# =====================================================================

def test_12_diagnostics_survive_into_the_scientific_result():
    slab = make_slab(128, 160)
    result = solve_slab(slab, run_id="diag")
    numerics = result.metadata["numerics"]
    for key in (
        "n_cells",
        "n_steps",
        "dx_m",
        "dt_s",
        "work_proxy",
        "fourier_number",
        "r_coefficient",
    ):
        assert key in numerics, key
    assert numerics["n_cells"] == 128
    assert numerics["n_steps"] == 160
    assert numerics["work_proxy"] == 128 * 160
    assert numerics["dx_m"] == pytest.approx(0.1 / 128)
    assert numerics["dt_s"] == pytest.approx(60.0 / 160)
    assert result.metadata["residuals"]["final_step_linear_system"] < 1e-10
    assert result.metadata["iterations"] == 160
    assert result.metadata["wall_seconds_telemetry"] > 0.0
    # The field array is not smuggled into the result surface.
    assert "field" not in numerics
    # E1's diagnostic loss is not repeated: no second solve was needed.
    assert result.provenance.metadata["backend"] == "scipy.sparse.linalg.splu"
    assert result.convergence is ConvergenceState.CONVERGED


def test_12b_field_is_dimensionless_and_never_kelvin():
    result = solve_slab(make_slab(), run_id="units")
    for name, value in result.values.items():
        assert value.magnitude_in("dimensionless") == value.magnitude_in("1")
        with pytest.raises(Exception):
            value.magnitude_in("kelvin")
    text = " ".join(
        [result.provenance.metadata.get("time_integration", "")]
        + [c.detail for c in result.validation.checks]
    ).lower()
    assert "kelvin" not in text


# =====================================================================
# 13. Fail closed
# =====================================================================

@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda: SlabDiscretization(1, 10), id="n_cells_too_small"),
        pytest.param(lambda: SlabDiscretization(7, 10), id="n_cells_odd"),
        pytest.param(lambda: SlabDiscretization(8, 0), id="n_steps_zero"),
        pytest.param(lambda: SlabDiscretization(8, -1), id="n_steps_negative"),
        pytest.param(lambda: SlabDiscretization(8.0, 10), id="n_cells_not_int"),
    ],
)
def test_13_invalid_discretization_fails_closed(factory):
    with pytest.raises(SlabConfigurationError):
        factory()


@pytest.mark.parametrize(
    "length,alpha,end_time,label",
    [
        (Quantity(-0.1, "meter"), ALPHA, END_TIME, "negative_length"),
        (Quantity(0.0, "meter"), ALPHA, END_TIME, "zero_length"),
        (LENGTH, Quantity(-1e-5, "m**2/s"), END_TIME, "negative_alpha"),
        (LENGTH, Quantity(0.0, "m**2/s"), END_TIME, "zero_alpha"),
        (LENGTH, ALPHA, Quantity(0.0, "second"), "zero_end_time"),
        (LENGTH, ALPHA, Quantity(-1.0, "second"), "negative_end_time"),
    ],
)
def test_13b_invalid_physical_declaration_fails_closed(
    length, alpha, end_time, label
):
    with pytest.raises(SlabConfigurationError):
        ConductionSlab(
            slab_id=label,
            length=length,
            diffusivity=alpha,
            end_time=end_time,
            discretization=SlabDiscretization(8, 10),
        )


def test_13c_bare_numbers_are_not_declarations():
    with pytest.raises(SlabConfigurationError):
        ConductionSlab(
            slab_id="bare",
            length=0.1,
            diffusivity=ALPHA,
            end_time=END_TIME,
            discretization=SlabDiscretization(8, 10),
        )
    with pytest.raises(SlabConfigurationError):
        ConductionSlab(
            slab_id="",
            length=LENGTH,
            diffusivity=ALPHA,
            end_time=END_TIME,
            discretization=SlabDiscretization(8, 10),
        )


def test_13d_rebinding_different_physics_is_refused():
    solver = Conduction1DSolver()
    slab = make_slab(slab_id="bound")
    problem = build_conduction_problem(slab)
    solver.bind_slab(slab, problem.problem_id)
    # Same physics at a different resolution is fine — that is a refinement.
    solver.bind_slab(
        slab.with_discretization(SlabDiscretization(16, 20)), problem.problem_id
    )
    other = ConductionSlab(
        slab_id="bound",
        length=Quantity(0.2, "meter"),
        diffusivity=ALPHA,
        end_time=END_TIME,
        discretization=SlabDiscretization(8, 10),
    )
    with pytest.raises(SlabBindingError):
        solver.bind_slab(other, problem.problem_id)


def test_13e_mismatched_problem_and_slab_is_refused():
    slab = make_slab(slab_id="one")
    problem = build_conduction_problem(slab)
    other = ConductionSlab(
        slab_id="two",
        length=Quantity(0.25, "meter"),
        diffusivity=ALPHA,
        end_time=END_TIME,
        discretization=SlabDiscretization(8, 10),
    )
    with pytest.raises(SlabConfigurationError):
        solve_slab(other, run_id="mismatch", problem=problem)


def test_13f_non_finite_solution_is_reported_not_hidden():
    """A corrupted system must yield a failed result, never a plausible one."""
    slab = make_slab(16, 20)
    solver = Conduction1DSolver()
    problem = build_conduction_problem(slab)
    solver.bind_slab(slab, problem.problem_id)
    prepared = solver.prepare(problem)

    system = prepared.payload
    poisoned = sp.csc_matrix(system.matrix.toarray() * np.nan)
    broken = type(system)(
        slab=system.slab,
        matrix=poisoned,
        x_nodes=system.x_nodes,
        initial_interior=system.initial_interior,
        r=system.r,
    )
    from src.engcore.scientific.solvers.protocol import PreparedSolve

    raw = solver.solve(
        PreparedSolve(
            problem=prepared.problem,
            solver=prepared.solver,
            settings=prepared.settings,
            payload=broken,
        )
    )
    assert raw.succeeded is False
    assert raw.convergence in (
        ConvergenceState.DIVERGED,
        ConvergenceState.FAILED,
    )
    assert solver.extract_metrics(prepared, raw) == {}
    report = solver.validate(
        PreparedSolve(
            problem=prepared.problem,
            solver=prepared.solver,
            settings=prepared.settings,
            payload=broken,
        ),
        raw,
    )
    assert any(c.outcome is ValidationOutcome.FAIL for c in report.checks)
    assert not any(c.establishes for c in report.checks)


def test_13g_a_gate_needs_something_to_compare():
    with pytest.raises(SlabConfigurationError):
        run_verification_gate(
            make_slab(), ladder=(RefinementRung(8, 10),), run_id_prefix="single"
        )


def test_13h_reference_rejects_impossible_arguments():
    with pytest.raises(SlabConfigurationError):
        exact_midpoint(length_m=0.0, alpha_m2_s=1e-5, time_s=1.0)
    with pytest.raises(SlabConfigurationError):
        exact_midpoint(length_m=0.1, alpha_m2_s=-1e-5, time_s=1.0)
    with pytest.raises(SlabConfigurationError):
        exact_midpoint(length_m=0.1, alpha_m2_s=1e-5, time_s=-1.0)
    with pytest.raises(SlabConfigurationError):
        exact_field([0.5], length_m=0.1, alpha_m2_s=1e-5, time_s=1.0)


# =====================================================================
# The gate rendered in the universal vocabulary
# =====================================================================

def test_gate_report_uses_the_universal_validation_vocabulary():
    report = run_verification_gate(make_slab(), run_id_prefix="vocab")
    universal = report.to_report()
    names = {c.name for c in universal.checks}
    assert names == {"discretization_convergence", "analytic_reference_agreement"}
    established = {c.establishes for c in universal.checks if c.establishes}
    assert established == {
        ValidationLevel.NUMERICALLY_CONVERGED,
        ValidationLevel.ANALYTICALLY_VERIFIED,
    }
    assert "NOT separately identified" in universal.notes
    payload = report.to_dict()
    assert payload["levels_earned"] == [
        "numerically_converged",
        "analytically_verified",
    ]
    assert len(payload["rungs"]) == len(VERIFICATION_LADDER)


def test_claim_does_not_assert_independent_spatial_order():
    report = run_verification_gate(make_slab(), run_id_prefix="claim")
    claim = report.claim.lower()
    assert "first-order temporal error dominating" in claim
    assert "not separately identified" in claim
    assert "second-order spatial" not in claim
