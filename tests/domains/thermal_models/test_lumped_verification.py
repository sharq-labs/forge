"""What the lumped solver's reference comparison earns, and what it refuses to.

The claim under test is narrow and should stay narrow: the emitted closed form
agrees with a reconstruction of the same solution built from the governing
equation's own coefficients, so ``ANALYTICALLY_VERIFIED`` is attained. The
tests below are arranged around the three ways that claim could be made
dishonestly —

1. by awarding the level without the comparison having happened
   (``test_the_level_is_withheld_when_the_reference_cannot_be_built``),
2. by letting a disagreement degrade into a level-free pass instead of a
   failure (``test_a_disagreement_fails_rather_than_quietly_dropping_the_level``
   and its sibling that perturbs the reference rather than the solution),
3. by the "independent" reference not being independent
   (``test_the_reference_shares_no_code_with_the_solver`` and
   ``test_the_reference_satisfies_the_equation_it_claims_to_solve``).

The end-to-end consequence — a real applicable electro-thermal run reaching
``SUPPORTED`` — is asserted here on the MCP boundary and again, on a
hand-assembled coupled run, by
``tests/mcp/test_evidence.py::test_a_real_run_of_an_applicable_body_is_supported``.
"""

from __future__ import annotations

import ast
import dataclasses
import decimal
import math
from pathlib import Path

import pytest

from src.engcore.domains.thermal_models import context as ctx
from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.domains.thermal_models import lumped_reference as ref
from src.engcore.mcp import (
    CredibilityVerdict,
    derive_verdict,
    example_electrothermal_payload,
    run_electrothermal_case,
)
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
)
from src.engcore.scientific.units.quantity import Quantity

K = "kelvin"

#: The same declaration the applicability tests use, so a body that is
#: IN_DOMAIN there is IN_DOMAIN here and the two milestones cannot drift apart.
FULLY_DECLARED = ctx.LumpedApplicabilityDeclaration(
    characteristic_length=Quantity(0.002, "meter"),
    surface_area=Quantity(0.01, "meter**2"),
    body_conductivity=Quantity(200.0, "watt/meter/kelvin"),
    surface_emissivity=Quantity(0.05, "dimensionless"),
    convection_regime=ctx.FORCED_CONVECTION,
    conductance_excursion_bound=Quantity(60.0, K),
    capacity_excursion_bound=Quantity(100.0, K),
    melting_temperature=Quantity(900.0, K),
    fluid_conductivity=Quantity(0.0261, "watt/meter/kelvin"),
    fluid_kinematic_viscosity=Quantity(1.589e-5, "meter**2/second"),
    fluid_prandtl_number=Quantity(0.707, "dimensionless"),
    fluid_velocity=Quantity(1.0, "meter/second"),
    convection_length=Quantity(0.6, "meter"),
)

HEAT_INPUT = Quantity(1.0, "watt")


def body(*, duration=120.0, capacity=2.5, conductance=0.05):
    return lump.ThermalBody(
        body_id="B1",
        heat_capacity=Quantity(capacity, "joule/kelvin"),
        ambient_conductance=Quantity(conductance, "watt/kelvin"),
        ambient_temperature=Quantity(300.0, K),
        initial_temperature=Quantity(300.0, K),
        duration=Quantity(duration, "second"),
        applicability=FULLY_DECLARED,
    )


def solved(thermal_body, *, heat_input=HEAT_INPUT):
    """Prepare, solve and validate one body. Returns (report, prepared, raw)."""
    problem = lump.build_lumped_thermal_problem(thermal_body)
    solver = lump.LumpedThermalSolver()
    solver.bind_body(thermal_body, problem.problem_id, heat_input=heat_input)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    return solver.validate(prepared, raw), solver, prepared, raw


def check(report, name):
    return next(c for c in report.checks if c.name == name)


def reference_for(thermal_body, *, heat_input=HEAT_INPUT):
    return ref.series_reference_temperature(
        capacity_j_per_k=thermal_body.capacity_j_per_k,
        conductance_w_per_k=thermal_body.conductance_w_per_k,
        heat_input_w=heat_input.magnitude_in("watt"),
        ambient_k=thermal_body.ambient_k,
        initial_k=thermal_body.initial_k,
        duration_s=thermal_body.duration_s,
    )


# =====================================================================
# The reference is independent of the thing it verifies
# =====================================================================

def test_the_reference_shares_no_code_with_the_solver():
    """A verification that shares code with the solver verifies nothing.

    The same check the frozen conduction reference is held to. It is a real
    constraint here rather than a formality: the reference lives in the same
    package as the solver, one import away.
    """
    tree = ast.parse(Path(ref.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("lumped" in name for name in imported), imported
    assert imported <= {
        "__future__",
        "__future__.annotations",
        "math",
        "sys",
        "dataclasses",
        "dataclasses.dataclass",
    }


def test_the_reference_never_forms_the_solvers_derived_quantities():
    """The independence claim is about intermediates, not only about imports.

    The solver's route needs two quantities the equation does not contain — the
    steady state and the time constant — and it evaluates ``exp``. If the
    reference reached for any of them the comparison would stop being a second
    route and become a second copy of the first.

    Read off the syntax tree rather than the text, so the prose above and in
    the reference — which has to name these quantities in order to disclaim
    them — cannot trip it, and a renamed local cannot hide behind a comment.
    """
    tree = ast.parse(Path(ref.__file__).read_text(encoding="utf-8"))
    names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        node.arg for node in ast.walk(tree) if isinstance(node, ast.arg)
    }
    assert "exp" not in names
    assert not any(
        marker in name
        for name in names
        for marker in ("steady", "tau", "time_constant", "decay")
    ), sorted(names)


def test_the_reference_satisfies_the_equation_it_claims_to_solve():
    """Checked numerically against the ODE, not against the solver.

    Mirrors the frozen conduction test that differentiates its closed form and
    substitutes it back. If this passes and the comparison in the solver also
    passes, the closed form solves this equation too.
    """
    capacity, conductance, heat, ambient, initial = 2.5, 0.05, 1.0, 300.0, 300.0
    t, dt = 37.0, 1e-5
    kwargs = dict(
        capacity_j_per_k=capacity,
        conductance_w_per_k=conductance,
        heat_input_w=heat,
        ambient_k=ambient,
        initial_k=initial,
    )
    now = ref.series_reference_temperature(duration_s=t, **kwargs).value_k
    later = ref.series_reference_temperature(duration_s=t + dt, **kwargs).value_k
    derivative = (later - now) / dt
    assert capacity * derivative == pytest.approx(
        heat - conductance * (now - ambient), rel=1e-6
    )


def test_the_reported_error_bound_is_an_upper_bound_on_the_true_error():
    """The bound is the reason the tolerance means anything.

    Arbitrated by a 50-digit ``Decimal`` evaluation, which is neither route's
    arithmetic. This does not make the reference independent — it is the same
    mathematics at more digits — it only establishes that the bound the
    reference reports about *itself* is honest.
    """
    with decimal.localcontext() as context:
        context.prec = 50
        for capacity, conductance, heat, duration in (
            (2.5, 0.05, 1.0, 120.0),
            (2.5, 0.05, 2.121, 600.0),
            (900.0, 3.0, 40.0, 4000.0),
            (0.1, 0.02, 0.5, 30.0),
        ):
            exact = decimal.Decimal(300) + (
                decimal.Decimal(repr(heat)) / decimal.Decimal(repr(conductance))
            ) * (
                1
                - (
                    -decimal.Decimal(repr(conductance))
                    * decimal.Decimal(repr(duration))
                    / decimal.Decimal(repr(capacity))
                ).exp()
            )
            result = ref.series_reference_temperature(
                capacity_j_per_k=capacity,
                conductance_w_per_k=conductance,
                heat_input_w=heat,
                ambient_k=300.0,
                initial_k=300.0,
                duration_s=duration,
            )
            assert result.available
            error = abs(decimal.Decimal(repr(result.value_k)) - exact)
            assert error <= decimal.Decimal(repr(result.error_bound_k))


# =====================================================================
# The level is awarded where it is earned
# =====================================================================

def test_a_body_whose_solution_matches_the_reference_earns_the_level():
    report, _, _, _ = solved(body())
    agreement = check(report, "analytic_reference_agreement")
    assert agreement.outcome is ValidationOutcome.PASS
    assert agreement.establishes is ValidationLevel.ANALYTICALLY_VERIFIED
    assert report.attained_levels == frozenset(
        {ValidationLevel.ANALYTICALLY_VERIFIED}
    )
    # and the comparison was tight, not permissive: the two routes agree far
    # inside a tolerance that is itself round-off scale.
    assert agreement.residual <= agreement.tolerance
    assert agreement.tolerance < 1e-8


def test_the_balance_residual_still_establishes_nothing():
    """The level came from the new check, not from relabelling the old one.

    ``lumped_balance_residual`` compares the closed form against the equation
    it was derived from and has no independent reference behind it. Moving the
    level onto it would improve the verdict without any new evidence existing.
    """
    report, _, _, _ = solved(body())
    residual = check(report, "lumped_balance_residual")
    assert residual.outcome is ValidationOutcome.PASS
    assert residual.establishes is None


@pytest.mark.parametrize(
    "capacity,conductance,duration,heat",
    [
        (2.5, 0.05, 1.0, 1.0),        # far short of one time constant
        (2.5, 0.05, 5000.0, 1.0),     # a hundred time constants, sub-stepped
        (1e4, 2.0, 900.0, 250.0),     # a large body under a large input
        (0.05, 0.4, 3.0, 0.02),       # a small fast body
    ],
)
def test_the_level_is_earned_across_the_operating_range_not_one_lucky_point(
    capacity, conductance, duration, heat
):
    report, _, _, _ = solved(
        body(capacity=capacity, conductance=conductance, duration=duration),
        heat_input=Quantity(heat, "watt"),
    )
    assert check(
        report, "analytic_reference_agreement"
    ).establishes is ValidationLevel.ANALYTICALLY_VERIFIED


# =====================================================================
# ... and refused where it is not
# =====================================================================

def test_a_disagreement_fails_rather_than_quietly_dropping_the_level():
    """Perturb the emitted solution. The check must FAIL, not go level-free.

    A level-free pass would let a wrong closed form travel inside a report
    whose only visible defect is that it establishes nothing — which is a
    condition this repository has several honest examples of, so it would not
    look wrong.
    """
    _, solver, prepared, raw = solved(body())
    perturbed = dataclasses.replace(
        raw,
        values={**raw.values, lump.TEMPERATURE_METRIC: raw.values[
            lump.TEMPERATURE_METRIC
        ] + 1e-6},
    )
    report = solver.validate(prepared, perturbed)
    agreement = check(report, "analytic_reference_agreement")
    assert agreement.outcome is ValidationOutcome.FAIL
    assert agreement.establishes is None
    assert report.attained_levels == frozenset()


def test_the_tolerance_is_a_real_edge_and_not_a_rubber_band():
    """Just inside passes, an order of magnitude outside fails.

    Without this, a tolerance that silently widened with the perturbation
    would pass both halves of the test above.
    """
    report, solver, prepared, raw = solved(body())
    tolerance = check(report, "analytic_reference_agreement").tolerance
    final = raw.values[lump.TEMPERATURE_METRIC]

    def outcome_at(offset):
        perturbed = dataclasses.replace(
            raw, values={**raw.values, lump.TEMPERATURE_METRIC: final + offset}
        )
        return check(
            solver.validate(prepared, perturbed), "analytic_reference_agreement"
        )

    assert outcome_at(0.4 * tolerance).outcome is ValidationOutcome.PASS
    assert outcome_at(10.0 * tolerance).outcome is ValidationOutcome.FAIL
    assert outcome_at(10.0 * tolerance).tolerance == pytest.approx(tolerance)


def test_a_wrong_reference_fails_the_comparison_and_nothing_else(monkeypatch):
    """The two checks measure different things, shown by moving only one.

    The reference is displaced by a millikelvin while the solver's arithmetic
    is untouched. ``lumped_balance_residual`` cannot see it — it never consults
    the reference — and still passes; the comparison fails and the level is
    gone. That is what says the level rests on the reference rather than on the
    residual that was already there.
    """
    real = ref.series_reference_temperature

    def displaced(**kwargs):
        result = real(**kwargs)
        return dataclasses.replace(result, value_k=result.value_k + 1e-3)

    monkeypatch.setattr(lump, "series_reference_temperature", displaced)
    report, _, _, _ = solved(body())
    assert check(report, "lumped_balance_residual").outcome is ValidationOutcome.PASS
    agreement = check(report, "analytic_reference_agreement")
    assert agreement.outcome is ValidationOutcome.FAIL
    assert agreement.establishes is None


def test_the_level_is_withheld_when_the_reference_cannot_be_built():
    """No reference, no comparison, no level — and NOT_RUN says which.

    The interval spans more of the equation's own decay argument than the
    declared sub-step budget covers. The solver's answer is unaffected: the
    closed form does not care how long the interval is. What is missing is the
    thing that would have checked it, and the report has to distinguish that
    from a comparison that was made and passed.
    """
    long_run = body(capacity=1.0, conductance=1.0, duration=3000.0)
    assert not reference_for(long_run).available

    report, _, _, raw = solved(long_run)
    agreement = check(report, "analytic_reference_agreement")
    assert agreement.outcome is ValidationOutcome.NOT_RUN
    assert agreement.establishes is None
    assert report.attained_levels == frozenset()
    assert "unavailable" in agreement.detail
    # the solve itself is untouched and still succeeded
    assert math.isfinite(raw.values[lump.TEMPERATURE_METRIC])
    assert check(report, "lumped_balance_residual").outcome is ValidationOutcome.PASS


def test_an_unavailable_reference_reads_as_a_gap_not_as_a_disagreement():
    """The two refusals are different findings and must not be confused.

    NOT_RUN sends a reader to widen the reference's budget. FAIL sends them to
    the closed form. Collapsing either into the other points at the wrong
    repair, which is the same argument the evidence layer makes for keeping
    NOT_SUPPORTED and INSUFFICIENT_EVIDENCE apart.
    """
    unavailable, _, _, _ = solved(
        body(capacity=1.0, conductance=1.0, duration=3000.0)
    )
    _, solver, prepared, raw = solved(body())
    disagreeing = solver.validate(
        prepared,
        dataclasses.replace(
            raw,
            values={
                **raw.values,
                lump.TEMPERATURE_METRIC: raw.values[lump.TEMPERATURE_METRIC] + 1.0,
            },
        ),
    )
    assert check(unavailable, "analytic_reference_agreement").outcome is (
        ValidationOutcome.NOT_RUN
    )
    assert check(disagreeing, "analytic_reference_agreement").outcome is (
        ValidationOutcome.FAIL
    )


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"capacity_j_per_k": 0.0}, "positive capacity"),
        ({"conductance_w_per_k": -1.0}, "positive capacity"),
        ({"heat_input_w": float("nan")}, "not finite"),
        ({"duration_s": float("inf")}, "not finite"),
    ],
)
def test_the_reference_refuses_coefficients_it_cannot_bound(kwargs, reason):
    base = dict(
        capacity_j_per_k=2.5,
        conductance_w_per_k=0.05,
        heat_input_w=1.0,
        ambient_k=300.0,
        initial_k=300.0,
        duration_s=120.0,
    )
    result = ref.series_reference_temperature(**{**base, **kwargs})
    assert not result.available
    assert result.value_k is None and result.error_bound_k is None
    assert reason in result.unavailable_reason


# =====================================================================
# End to end
# =====================================================================

def test_a_real_applicable_electrothermal_run_earns_its_level():
    """The consequence the whole task exists for, at the outermost boundary.

    Before this round the same payload attained **nothing** — in domain,
    converged, nothing failed, nothing established — and no verdict rule could
    rescue that. What changed is that a check now establishes something.

    **The report's own verdict is no longer the way to say so**, and that is a
    later change rather than a retreat from this one. The credibility report is
    now assembled over the dependency closure of the values it reports, so it
    covers the electrical models too, and nothing in this payload declares a
    resistor's rated dissipation or a source's current limit. Those gaps are
    real and the report is right to carry them; they are also nothing to do
    with the lumped model's verification, which is what this module is about.

    So the claim is made where it lives: the level is attained, the thermal
    model is in domain, no check failed or was skipped — and the same verdict
    function, over the thermal evidence alone, returns SUPPORTED. The level is
    genuinely earned, and the report's INSUFFICIENT_EVIDENCE is entirely
    somebody else's missing declaration.
    """
    outcome = run_electrothermal_case(
        example_electrothermal_payload(), run_id="verification-supported"
    )
    report = outcome.reports[0]
    assert report.attained_levels == frozenset(
        {ValidationLevel.ANALYTICALLY_VERIFIED}
    )
    assert report.failed_checks == () and report.not_run_checks == ()

    thermal = next(
        record for record in report.validity
        if record.model_id == lump.LUMPED_CAPACITY_MODEL.model_id
    )
    assert thermal.status is ValidityStatus.IN_DOMAIN
    assert derive_verdict(
        validity=(thermal,),
        validation=report.validation,
        coupling=report.coupling,
    ) is CredibilityVerdict.SUPPORTED
