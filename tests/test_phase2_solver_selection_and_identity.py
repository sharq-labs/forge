"""Phase 2 BR11 -- same-problem identity, honest corroboration, deterministic qualified selection.

NOT RUN (Phase 2 build phase): docs/work/DEFERRED_VALIDATION.md, DV-57, DV-58.
"""

from __future__ import annotations

import hashlib

import pytest

import engcore.providers.selection as selection_module
from engcore.providers import ComparisonDeclaration, compare_providers
from engcore.providers.catalog import Availability, ProviderCapability, ProviderStatus
from engcore.providers.compare import corroborate
from engcore.providers.health import ProviderQualification
from engcore.providers.identity import ProviderExecutionIdentity
from engcore.providers.problem_identity import (
    CanonicalProblem, ProblemAspect, ProblemBinding, ProblemIdentityVerdict, compare_problems,
)
from engcore.providers.records import ProviderExecutionRecord
from engcore.providers.selection import SolverRequirement, select_solvers
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity

ALL = {
    ProblemAspect.GOVERNING_EQUATIONS: "steady heat conduction: div(k grad T) + q = 0",
    ProblemAspect.MODEL_ASSUMPTIONS: ["isotropic k", "no radiation"],
    ProblemAspect.DOMAIN_GEOMETRY: {"kind": "slab", "thickness": Quantity(10.0, "mm")},
    ProblemAspect.MATERIALS: {"k": Quantity(15.0, "W/(m*K)")},
    ProblemAspect.INITIAL_CONDITIONS: "none (steady)",
    ProblemAspect.BOUNDARY_CONDITIONS: {"left": {"dirichlet": Quantity(300.0, "K")}, "right": {"dirichlet": Quantity(350.0, "K")}},
    ProblemAspect.SOURCES_AND_LOADS: {"q": Quantity(0.0, "W/m**3")},
    ProblemAspect.TIME_INTERVAL: "steady",
    ProblemAspect.QUANTITIES_OF_INTEREST: ["T(x=thickness/2)"],
    ProblemAspect.MODEL_VERSIONS: {"conduction": "1"},
}


def _problem(pid="slab", **changes):
    declarations = dict(ALL)
    for key, value in changes.items():
        if value is None:
            declarations.pop(ProblemAspect(key))
        else:
            declarations[ProblemAspect(key)] = value
    return CanonicalProblem(pid, declarations)


# ---- canonical problem identity ---------------------------------------------------------------------------


def test_one_geometry_in_two_units_is_one_declaration():
    a = _problem(domain_geometry={"kind": "slab", "thickness": Quantity(10.0, "mm")})
    b = _problem(domain_geometry={"kind": "slab", "thickness": Quantity(0.01, "m")})
    assert compare_problems(a, b).verdict is ProblemIdentityVerdict.SAME_PROBLEM


def test_an_absolute_value_and_a_difference_are_different_declarations():
    a = _problem(boundary_conditions={"rise": Quantity(5.0, "kelvin")})
    b = _problem(boundary_conditions={"rise": Quantity(5.0, "delta_degC")})
    assert compare_problems(a, b).verdict is ProblemIdentityVerdict.DIFFERENT_PROBLEM


def test_a_different_boundary_condition_is_a_different_problem_and_is_named():
    b = _problem(boundary_conditions={"left": {"dirichlet": Quantity(300.0, "K")}, "right": {"neumann": Quantity(0.0, "W/m**2")}})
    equivalence = compare_problems(_problem(), b)
    assert equivalence.verdict is ProblemIdentityVerdict.DIFFERENT_PROBLEM
    assert equivalence.differing == ("boundary_conditions",)


def test_a_missing_aspect_leaves_identity_undetermined_never_same():
    equivalence = compare_problems(_problem(), _problem(materials=None))
    assert equivalence.verdict is ProblemIdentityVerdict.UNDETERMINED and "materials" in equivalence.undeclared


def test_a_difference_outranks_an_undeclared_aspect():
    b = _problem(materials=None, sources_and_loads={"q": Quantity(1.0, "W/m**3")})
    assert compare_problems(_problem(), b).verdict is ProblemIdentityVerdict.DIFFERENT_PROBLEM


@pytest.mark.parametrize("excluded", ["discretization", "mesh", "solver_configuration", "provider_input"])
def test_how_a_problem_is_solved_is_never_an_aspect_of_it(excluded):
    with pytest.raises(InvalidScientificProblem, match="not an aspect"):
        CanonicalProblem("p", {excluded: "anything"})


def test_unknown_aspects_and_unknown_values_are_refused():
    with pytest.raises(InvalidScientificProblem):
        CanonicalProblem("p", {"colour": "blue"})
    with pytest.raises(InvalidScientificProblem):
        CanonicalProblem("p", {ProblemAspect.MATERIALS: object()})


# ---- corroboration only after same-problem admission ------------------------------------------------------


def _record(provider_id, outputs, problem):
    capability = ProviderCapability(provider_id, "demo_family", "library", provider_id, ("demo",))
    status = ProviderStatus(capability, Availability.AVAILABLE, "1.0", "c" * 64, "/x",
                            dependencies=(("python-environment", "1", hashlib.sha256(provider_id.encode()).hexdigest()),))
    identity = ProviderExecutionIdentity.from_content(status, adapter_id="a", adapter_version="1", problem=problem,
                                                      configuration={}, output_request=tuple(outputs))
    return ProviderExecutionRecord(identity, True, "", scalars=dict(outputs))


DECLARATION = ComparisonDeclaration("mid-plane temperature", "K", "identity", Quantity(0.01, "K"), 0.0, "slab")


def _bindings(a, b, pa, pb):
    return (ProblemBinding(a.identity.digest, pa.digest, "adapter-a@1"), ProblemBinding(b.identity.digest, pb.digest, "adapter-b@1"))


def test_corroboration_on_one_problem_records_what_it_does_and_does_not_establish():
    pa, pb = _problem("slab-a"), _problem("slab-b")
    a = _record("alpha", {"t": Quantity(325.0, "K")}, {"alpha-mesh": 40})
    b = _record("beta", {"t": Quantity(325.004, "K")}, {"beta-grid": [11, 11]})
    made = corroborate(DECLARATION, a, "t", b, "t", problems=(pa, pb), bindings=_bindings(a, b, pa, pb))
    assert made.same_problem_established and made.within_tolerance
    payload = made.to_dict()
    assert "validation" in payload["does_not_establish"] and payload["problem_equivalence"]["verdict"] == "same_problem"


def test_equal_provider_problem_digests_do_not_make_two_problems_the_same():
    pa, pb = _problem(), _problem(sources_and_loads={"q": Quantity(5.0, "W/m**3")})
    a = _record("alpha", {"t": Quantity(325.0, "K")}, {"p": 1})
    b = _record("beta", {"t": Quantity(325.0, "K")}, {"p": 1})
    assert a.identity.problem_digest == b.identity.problem_digest
    with pytest.raises(InvalidScientificProblem, match="not admitted as solving one problem"):
        corroborate(DECLARATION, a, "t", b, "t", problems=(pa, pb), bindings=_bindings(a, b, pa, pb))


def test_undetermined_identity_refuses_corroboration():
    pa, pb = _problem(), _problem(model_versions=None)
    a = _record("alpha", {"t": Quantity(325.0, "K")}, {"a": 1})
    b = _record("beta", {"t": Quantity(325.0, "K")}, {"b": 1})
    with pytest.raises(InvalidScientificProblem, match="undetermined"):
        corroborate(DECLARATION, a, "t", b, "t", problems=(pa, pb), bindings=_bindings(a, b, pa, pb))


def test_a_binding_of_another_execution_is_refused():
    pa, pb = _problem("a"), _problem("b")
    a = _record("alpha", {"t": Quantity(325.0, "K")}, {"a": 1})
    b = _record("beta", {"t": Quantity(325.0, "K")}, {"b": 1})
    other = _record("gamma", {"t": Quantity(1.0, "K")}, {"g": 1})
    with pytest.raises(InvalidScientificProblem, match="another execution"):
        corroborate(DECLARATION, a, "t", b, "t", problems=(pa, pb), bindings=_bindings(other, b, pa, pb))


def test_a_plain_comparison_does_not_claim_one_problem_and_keeps_its_serialized_form():
    a = _record("alpha", {"t": Quantity(325.0, "K")}, {"a": 1})
    b = _record("beta", {"t": Quantity(325.0, "K")}, {"b": 1})
    made = compare_providers(DECLARATION, a, "t", b, "t")
    assert not made.same_problem_established
    assert "problem_equivalence" not in made.to_dict()


# ---- deterministic, qualified selection ------------------------------------------------------------------------


def _status(pid, physics=("heat",), available=True, version="1.0", digest="d" * 64):
    capability = ProviderCapability(pid, "f", "library", pid, physics, dimensions=(1, 2), time_modes=("steady",))
    return ProviderStatus(capability, Availability.AVAILABLE if available else Availability.UNAVAILABLE, version,
                          digest, "/x", reason="" if available else "not installed")


def _qualification(pid, scope=("heat.conduction.steady",), version="1.0", digest="d" * 64):
    return ProviderQualification(pid, version, digest, "adapter", "1", scope, ("e" * 64,), "route", "issuer")


REQUIREMENT = SolverRequirement(("heat",), ("heat.conduction.steady",), dimension=2, time_mode="steady")


def _select(statuses, qualifications, monkeypatch, preference=()):
    # the admission of a qualification through its routes and ledger is qualification.py's; here it is given
    monkeypatch.setattr(selection_module, "admitted_qualifications", lambda q, routes, ledger: tuple(q))
    adapters = {s.capability.provider_id: ("adapter", "1") for s in statuses}
    return select_solvers(REQUIREMENT, statuses, qualifications=qualifications, routes=(), ledger=None,
                          adapters=adapters, preference=preference)


def test_an_available_unqualified_provider_is_never_selected(monkeypatch):
    chosen = _select([_status("alpha"), _status("beta")], [_qualification("beta")], monkeypatch)
    assert chosen.order == ("beta",)
    alpha = next(e for e in chosen.entries if e.provider_id == "alpha")
    assert not alpha.eligible and "no admitted qualification" in alpha.reasons[0]


def test_a_qualification_of_another_build_does_not_qualify_this_one(monkeypatch):
    chosen = _select([_status("alpha", version="2.0")], [_qualification("alpha", version="1.0")], monkeypatch)
    assert chosen.order == ()


def test_applicability_is_checked_before_order(monkeypatch):
    chosen = _select([_status("alpha", physics=("fluid",)), _status("beta", available=False)],
                     [_qualification("alpha"), _qualification("beta")], monkeypatch)
    reasons = {e.provider_id: e.reasons for e in chosen.entries}
    assert chosen.order == () and any("physics" in r for r in reasons["alpha"]) and "unavailable" in reasons["beta"][0]


def test_order_is_the_explicit_preference_then_provider_id(monkeypatch):
    statuses = [_status("gamma"), _status("alpha"), _status("beta")]
    qualifications = [_qualification(p) for p in ("alpha", "beta", "gamma")]
    assert _select(statuses, qualifications, monkeypatch).order == ("alpha", "beta", "gamma")
    assert _select(statuses, qualifications, monkeypatch, preference=("gamma",)).order == ("gamma", "alpha", "beta")
    first = _select(statuses, qualifications, monkeypatch)
    assert first.digest == _select(list(reversed(statuses)), qualifications, monkeypatch).digest


def test_a_requirement_without_a_qualification_scope_is_refused():
    with pytest.raises(InvalidScientificProblem, match="qualification scope"):
        SolverRequirement(("heat",), ())
