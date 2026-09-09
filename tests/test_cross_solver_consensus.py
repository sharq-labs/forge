"""Cross-solver consensus: the mechanism, and the two domains that declare into it.

The claim under test is narrow and is the only one worth making: a level is
awarded when, and only when, the routes *declared* that they share nothing and
their answers agreed inside a threshold set the domain owns. Every other
combination is recorded in full and establishes nothing.

The two domains sit on opposite sides of that rule on purpose, and both are
exercised here rather than only the one that earns. A mechanism that has only
ever been seen to award is a mechanism nobody has watched refuse.
"""

from __future__ import annotations

import ast
import json
import pathlib

import pytest

from src.engcore.scientific.consensus import (
    CONSENSUS_SCHEMA,
    ComponentKind,
    CrossSolverConsensus,
    IndependenceVerdict,
    OutputCompleteness,
    RouteComparison,
    SharedComponent,
    SolveRoute,
    relative_difference,
)
from src.engcore.scientific.errors import ScientificValidationError
from src.engcore.scientific.results.thresholds import VerificationThresholds
from src.engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
)
from src.engcore.scientific.solvers.protocol import SolverIdentity

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

THRESHOLDS = VerificationThresholds(
    gate_id="test.consensus",
    version="0.1.0",
    values={"agreement_rel_tol": 1e-9},
    basis="a test fixture, not a scientific declaration",
)

ALPHA = SolverIdentity("solver.alpha", "1.0", backend="alpha")
BETA = SolverIdentity("solver.beta", "1.0", backend="beta")


def _component(name: str, kind: ComponentKind = ComponentKind.RESIDUAL):
    return SharedComponent(kind, name, f"detail for {name}")


def _route(route_id: str, solver: SolverIdentity, *names: str) -> SolveRoute:
    return SolveRoute(
        route_id=route_id,
        solver=solver,
        components=frozenset(_component(n) for n in names),
    )


def _consensus(
    routes, values, thresholds=THRESHOLDS, required_outputs=None
) -> CrossSolverConsensus:
    """A consensus fixture that declares its required outputs.

    ``required_outputs`` defaults to the quantities every route reported, so a
    fixture written to exercise independence or tolerance does not also have to
    restate the output contract. Tests ABOUT completeness pass it explicitly.

    The default is a fixture convenience and deliberately not the production
    rule: the record refuses to award anything on an undeclared set, and
    ``test_an_undeclared_required_output_set_earns_nothing`` pins that.
    """
    if required_outputs is None:
        common: set[str] | None = None
        for produced in values.values():
            common = set(produced) if common is None else common & set(produced)
        required_outputs = tuple(sorted(common or ()))
    return CrossSolverConsensus.over(
        consensus_id="test",
        routes=routes,
        values=values,
        thresholds=thresholds,
        tolerance_key="agreement_rel_tol",
        required_outputs=required_outputs,
    )


# =====================================================================
# The mechanism
# =====================================================================

def test_independent_routes_that_agree_earn_the_level():
    consensus = _consensus(
        (_route("a", ALPHA, "a:rhs"), _route("b", BETA, "b:rhs")),
        {"a": {"x": 1.0, "y": 2.0}, "b": {"x": 1.0, "y": 2.0}},
    )
    assert consensus.independence is IndependenceVerdict.INDEPENDENT
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    check = consensus.to_check()
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    # The level must be backed by an actual comparison, which is the core's own
    # rule for every check that declares one.
    assert check.earns_its_level


def test_one_shared_component_defeats_the_whole_consensus():
    """Agreement is unchanged; what changes is what it is evidence of."""
    consensus = _consensus(
        (
            _route("a", ALPHA, "shared:rhs", "a:kernel"),
            _route("b", BETA, "shared:rhs", "b:kernel"),
        ),
        {"a": {"x": 1.0}, "b": {"x": 1.0}},
    )
    assert consensus.comparison.agreed
    assert consensus.independence is IndependenceVerdict.SHARES_COMPONENTS
    assert consensus.establishes is None
    assert [c.label for c in consensus.shared_components] == ["residual:shared:rhs"]
    # PASS and no level: the sentence the platform previously could not write.
    check = consensus.to_check()
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is None
    assert "shared:rhs" in check.detail


def test_a_route_that_declares_nothing_earns_nothing():
    """The default is not independent, and silence is not a permission."""
    consensus = _consensus(
        (_route("a", ALPHA), _route("b", BETA, "b:rhs")),
        {"a": {"x": 1.0}, "b": {"x": 1.0}},
    )
    # The empty declaration intersects to nothing, which is exactly why this
    # has to be its own verdict rather than falling out of the intersection.
    assert not consensus.shared_components
    assert consensus.independence is IndependenceVerdict.UNDECLARED
    assert consensus.establishes is None
    assert "declare no components" in consensus.reason


def test_independence_is_never_inferred_from_the_solver_identity():
    """Two different backends, one declared component, no level.

    The identities differ in every field. If independence were inferred from
    anything about the solvers rather than read from the declaration, this
    would award.
    """
    consensus = _consensus(
        (_route("a", ALPHA, "one:thing"), _route("b", BETA, "one:thing")),
        {"a": {"x": 1.0}, "b": {"x": 1.0}},
    )
    assert consensus.routes[0].solver != consensus.routes[1].solver
    assert consensus.establishes is None


def test_the_same_component_described_differently_is_still_shared():
    """Prose cannot buy independence."""
    a = SolveRoute("a", ALPHA, frozenset({
        SharedComponent(ComponentKind.JACOBIAN, "j", "our analytic Jacobian"),
    }))
    b = SolveRoute("b", BETA, frozenset({
        SharedComponent(ComponentKind.JACOBIAN, "j", "the derivative matrix"),
    }))
    consensus = _consensus((a, b), {"a": {"x": 1.0}, "b": {"x": 1.0}})
    assert consensus.independence is IndependenceVerdict.SHARES_COMPONENTS


def test_the_same_name_under_a_different_kind_is_not_shared():
    """Identity is the pair, so a kind is part of what is being named."""
    a = SolveRoute("a", ALPHA, frozenset({
        SharedComponent(ComponentKind.RESIDUAL, "f"),
    }))
    b = SolveRoute("b", BETA, frozenset({
        SharedComponent(ComponentKind.JACOBIAN, "f"),
    }))
    consensus = _consensus((a, b), {"a": {"x": 1.0}, "b": {"x": 1.0}})
    assert consensus.independence is IndependenceVerdict.INDEPENDENT


def test_independent_routes_that_disagree_fail_rather_than_warn():
    consensus = _consensus(
        (_route("a", ALPHA, "a:rhs"), _route("b", BETA, "b:rhs")),
        {"a": {"x": 1.0}, "b": {"x": 1.5}},
    )
    assert consensus.establishes is None
    check = consensus.to_check()
    assert check.outcome is ValidationOutcome.FAIL
    assert check.residual == pytest.approx(1.0 / 3.0)


def test_dependent_routes_that_disagree_warn_rather_than_fail():
    """A comparison denied authority to award cannot be given authority to condemn."""
    consensus = _consensus(
        (_route("a", ALPHA, "shared"), _route("b", BETA, "shared")),
        {"a": {"x": 1.0}, "b": {"x": 1.5}},
    )
    assert consensus.to_check().outcome is ValidationOutcome.WARNING


def test_nothing_compared_is_not_agreement():
    consensus = _consensus(
        (_route("a", ALPHA, "a:rhs"), _route("b", BETA, "b:rhs")),
        {"a": {"x": 1.0}, "b": {"y": 1.0}},
    )
    assert consensus.routes_are_independent
    assert not consensus.comparison.compared_anything
    assert not consensus.comparison.agreed
    assert consensus.establishes is None
    assert consensus.to_check().outcome is ValidationOutcome.NOT_RUN


def test_a_single_route_is_not_a_consensus():
    consensus = _consensus((_route("a", ALPHA, "a:rhs"),), {"a": {"x": 1.0}})
    assert consensus.independence is IndependenceVerdict.TOO_FEW_ROUTES
    assert consensus.establishes is None


def test_only_quantities_every_route_reported_are_compared():
    """An absence is still not a disagreement, and is still not compared.

    **The award half of this test changed deliberately.** It used to assert
    that these two routes -- one reporting ``x`` and ``only_a``, the other
    ``x`` and ``only_b`` -- earned CROSS_SOLVER_VALIDATED on the strength of
    agreeing about ``x``. That was the defect: agreement on the one quantity
    two routes happened to share bought the same level as agreement on all of
    them, and nothing in the record said which quantities SHOULD have been
    compared.

    What has not changed is the comparison itself. ``only_a`` and ``only_b``
    are absences, not disagreements, and scoring them as either would invent a
    comparison nobody made.
    """
    consensus = _consensus(
        (_route("a", ALPHA, "a:rhs"), _route("b", BETA, "b:rhs")),
        {"a": {"x": 1.0, "only_a": 99.0}, "b": {"x": 1.0, "only_b": -99.0}},
        required_outputs=("x", "only_a", "only_b"),
    )
    assert consensus.comparison.quantities == ("x",)
    assert consensus.comparison.agreed is True
    # ...and it establishes nothing, because neither route answered the whole
    # question. Both are named, so a reader can see who was short of what.
    assert consensus.output_completeness is OutputCompleteness.INCOMPLETE
    assert consensus.missing_outputs == (("a", "only_b"), ("b", "only_a"))
    assert consensus.establishes is None
    assert "only_b" in consensus.reason


def test_a_caller_supplied_threshold_awards_nothing():
    """The rule every gate in this platform obeys, applied to consensus."""
    widened = THRESHOLDS.derive(agreement_rel_tol=1.0)
    consensus = _consensus(
        (_route("a", ALPHA, "a:rhs"), _route("b", BETA, "b:rhs")),
        {"a": {"x": 1.0}, "b": {"x": 1.2}},
        thresholds=widened,
    )
    # The comparison passes at the caller's number and the claim is withheld.
    assert consensus.comparison.agreed
    assert consensus.routes_are_independent
    assert consensus.earned
    assert consensus.establishes is None
    assert "is not this gate's declared threshold set" in consensus.reason


def test_values_from_an_undeclared_route_are_refused():
    with pytest.raises(ScientificValidationError, match="undeclared route"):
        _consensus(
            (_route("a", ALPHA, "a:rhs"),),
            {"a": {"x": 1.0}, "ghost": {"x": 1.0}},
        )


def test_duplicate_route_ids_are_refused():
    with pytest.raises(ScientificValidationError, match="duplicate route ids"):
        CrossSolverConsensus(
            consensus_id="test",
            routes=(_route("a", ALPHA, "one"), _route("a", BETA, "two")),
            comparison=RouteComparison((), "", None, 1e-9),
            thresholds=THRESHOLDS,
        )


def test_a_non_finite_worst_difference_is_refused():
    """A NaN satisfies every tolerance ever written against it."""
    with pytest.raises(ScientificValidationError, match="non-finite"):
        RouteComparison(("x",), "x", float("nan"), 1e-9)


def test_a_non_finite_tolerance_is_refused():
    with pytest.raises(ScientificValidationError, match="finite"):
        RouteComparison(("x",), "x", 0.0, float("inf"))


def test_relative_difference_is_symmetric_and_handles_two_zeros():
    assert relative_difference(1.0, 2.0) == relative_difference(2.0, 1.0)
    assert relative_difference(0.0, 0.0) == 0.0


# =====================================================================
# Serialization
# =====================================================================

def test_the_record_round_trips_and_carries_its_declaration():
    consensus = _consensus(
        (_route("a", ALPHA, "a:rhs"), _route("b", BETA, "b:rhs")),
        {"a": {"x": 1.0}, "b": {"x": 1.0}},
    )
    payload = json.loads(json.dumps(consensus.to_dict()))
    assert payload["schema"] == CONSENSUS_SCHEMA
    assert payload["independence"] == "independent"
    assert payload["establishes"] == "cross_solver_validated"
    # the declaration itself, not only its conclusion
    declared = {c["name"] for r in payload["routes"] for c in r["components"]}
    assert declared == {"a:rhs", "b:rhs"}
    assert CrossSolverConsensus.from_dict(payload) == consensus


def test_a_hand_edited_payload_cannot_smuggle_in_a_level():
    """The rule ``ValidationReport.from_dict`` applies to attained levels."""
    consensus = _consensus(
        (_route("a", ALPHA, "shared"), _route("b", BETA, "shared")),
        {"a": {"x": 1.0}, "b": {"x": 1.0}},
    )
    payload = dict(consensus.to_dict())
    assert payload["establishes"] is None
    payload["establishes"] = "cross_solver_validated"
    with pytest.raises(ScientificValidationError, match="may not assert one"):
        CrossSolverConsensus.from_dict(payload)


def test_deleting_a_shared_component_from_a_payload_is_visible():
    """Editing the declaration changes the level, and the level is rechecked."""
    consensus = _consensus(
        (_route("a", ALPHA, "shared"), _route("b", BETA, "shared")),
        {"a": {"x": 1.0}, "b": {"x": 1.0}},
    )
    payload = json.loads(json.dumps(consensus.to_dict()))
    payload["routes"][0]["components"] = []
    # Not silently promoted to independent: an empty declaration is UNDECLARED.
    restored = CrossSolverConsensus.from_dict(payload)
    assert restored.independence is IndependenceVerdict.UNDECLARED
    assert restored.establishes is None


# =====================================================================
# The core stays a core
# =====================================================================

def test_the_consensus_module_names_no_domain_and_no_backend():
    """Layering: nothing domain-specific in ``scientific/``.

    Checked over the code with string constants blanked, on the same reasoning
    ``tests/test_heterogeneous_ngspice.py`` gives: a docstring may name an
    example, and the rule is about what the code does.
    """
    source = (
        REPO_ROOT / "src/engcore/scientific/consensus.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    code = ast.unparse(tree).lower()
    for forbidden in (
        "electrical", "kinetics", "thermal", "battery", "cstr", "circuit",
        "scipy", "numpy", "radau", "bdf", "mna",
    ):
        assert forbidden not in code, f"{forbidden!r} leaked into the core"
    # and it imports nothing outside the core
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("engcore.domains")
            assert "domains" not in (node.module or "")


# =====================================================================
# Kinetics: the refusal, which must survive the migration exactly
# =====================================================================

def test_the_two_integrator_routes_declare_the_same_machinery():
    from src.engcore.domains.kinetics.cstr.validation import integration_route

    solver = SolverIdentity("kinetics.cstr.scipy_implicit_ivp", "0.1.0")
    bdf = integration_route("BDF", solver)
    radau = integration_route("Radau", solver)
    consensus = CrossSolverConsensus.over(
        consensus_id="k",
        routes=(bdf, radau),
        values={bdf.route_id: {"x": 1.0}, radau.route_id: {"x": 1.0}},
        thresholds=VerificationThresholds(
            gate_id="kinetics.cstr.verification_gate",
            version="0.1.0",
            values={"tolerance_rel_tol": 1e-6},
        ),
        tolerance_key="tolerance_rel_tol",
    )
    assert consensus.comparison.agreed
    assert consensus.independence is IndependenceVerdict.SHARES_COMPONENTS
    assert consensus.establishes is None
    shared = {c.kind for c in consensus.shared_components}
    assert shared == {
        ComponentKind.RESIDUAL,
        ComponentKind.JACOBIAN,
        ComponentKind.STEP_CONTROL,
        ComponentKind.LIBRARY,
    }


@pytest.mark.expensive
def test_the_kinetics_gate_still_refuses_to_award_for_the_cross_method_arm():
    """End to end, on a real regime: the arm agrees and establishes nothing."""
    from experiments.kinetics_k1.k1_config import regime
    from src.engcore.domains.kinetics.cstr.validation import run_verification_gate

    report = run_verification_gate(regime("R1").build(), run_id_prefix="consensus")
    consensus = report.cross_method_consensus
    assert consensus is not None
    assert consensus.independence is IndependenceVerdict.SHARES_COMPONENTS
    assert consensus.establishes is None

    check = next(
        c for c in report.to_report().checks if c.name == "cross_method_agreement"
    )
    # Unchanged from before the migration: it agrees, it passes, it earns
    # nothing. What is new is that the refusal is a declaration in the record.
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is None
    assert report.cross_method_agrees is True
    assert any("declares [" in line for line in check.evidence)

    # And the arm that IS independent still awards, so the migration did not
    # cost the domain the level it had earned.
    steady = next(
        c
        for c in report.to_report().checks
        if c.name == "independent_steady_state_agreement"
    )
    assert steady.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


# =====================================================================
# Electrical: the earner
# =====================================================================

def test_the_two_dc_routes_declare_no_component_in_common():
    from src.engcore.domains.electrical.dc_consensus import (
        external_route,
        native_route,
    )

    native = native_route(SolverIdentity("electrical.dc.mna", "0.1.0"))
    external = external_route(
        SolverIdentity("electrical.dc.external", "0.1.0", backend="sim-1.2")
    )
    assert native.components & external.components == frozenset()
    # Both are declared, and neither is empty: the level is available to them.
    assert not native.declares_nothing and not external.declares_nothing


@pytest.mark.expensive
def test_the_dc_routes_earn_the_level_on_a_real_circuit():
    from src.engcore.domains.electrical import ngspice as ng
    from src.engcore.domains.electrical.dc import solve_circuit
    from src.engcore.domains.electrical.dc.solver import ElectricalDCSolver
    from src.engcore.domains.electrical.dc_consensus import dc_consensus
    from tests.test_heterogeneous_ngspice import divider

    circuit = divider()
    consensus = dc_consensus(
        native=solve_circuit(circuit, run_id="consensus-native"),
        native_solver=ElectricalDCSolver().identity,
        external=ng.solve_circuit_with_ngspice(circuit, run_id="consensus-ext"),
        external_solver=ng.NgspiceDCSolver().identity,
    )
    assert consensus.independence is IndependenceVerdict.INDEPENDENT
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    # Every metric both routes produced, not a chosen one.
    assert len(consensus.comparison.quantities) >= 13
    # measured at machine epsilon, seven orders inside the declared bound
    assert consensus.comparison.worst_relative_difference < 1e-14
    check = consensus.to_check()
    assert check.outcome is ValidationOutcome.PASS
    assert check.earns_its_level
