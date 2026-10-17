"""Phase 3.5 WS1 -- same-problem admission is mandatory for cross-provider corroboration.

* ``compare_providers`` alone is a DIAGNOSTIC (``diagnostic_numerical_comparison_not_corroboration``).
* Only ``corroborate`` (derived SAME_PROBLEM of two canonical problems, every aspect, one binding per record)
  yields ``solver_corroboration_not_validation``; DIFFERENT_PROBLEM and UNDETERMINED are refused.
* The verification ladder's level 5 and the bundle check re-derive admission from the RECORD: a stored
  record from before the rule, a relabelled diagnostic, or an admitted record relabelled as a diagnostic
  is refused; nothing stored is promoted.
* Equal provider-input digests and matching outputs are never admission.

NOT RUN (Phase 3.5 build phase): docs/work/DEFERRED_VALIDATION.md, DV-87.
"""

from __future__ import annotations

import hashlib

import pytest

from engcore.engineering import EvidenceLink, LevelEntry, LevelStatus
from engcore.engineering.ladder import check_provider_comparison
from engcore.providers import ComparisonDeclaration, compare_providers, corroborate, corroboration_admission_problems
from engcore.providers.catalog import Availability, ProviderCapability, ProviderStatus
from engcore.providers.identity import ProviderExecutionIdentity
from engcore.providers.problem_identity import CanonicalProblem, ProblemAspect, ProblemBinding
from engcore.providers.records import ProviderExecutionRecord
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
DECLARATION = ComparisonDeclaration("mid-plane temperature", "K", "identity", Quantity(0.01, "K"), 0.0, "slab")


def _problem(pid="slab", **changes):
    declarations = dict(ALL)
    for key, value in changes.items():
        if value is None:
            declarations.pop(ProblemAspect(key))
        else:
            declarations[ProblemAspect(key)] = value
    return CanonicalProblem(pid, declarations)


def _record(provider_id, value, problem):
    capability = ProviderCapability(provider_id, "demo_family", "library", provider_id, ("demo",))
    status = ProviderStatus(capability, Availability.AVAILABLE, "1.0", "c" * 64, "/x",
                            dependencies=(("python-environment", "1", hashlib.sha256(provider_id.encode()).hexdigest()),))
    identity = ProviderExecutionIdentity.from_content(status, adapter_id="a", adapter_version="1", problem=problem,
                                                      configuration={}, output_request=("t",))
    return ProviderExecutionRecord(identity, True, "", scalars={"t": Quantity(value, "K")})


def _pair(problem_a=None, problem_b=None):
    a, b = _record("alpha", 325.0, {"same": "input"}), _record("beta", 325.004, {"same": "input"})
    pa, pb = problem_a or _problem("slab-a"), problem_b or _problem("slab-b")
    bindings = (ProblemBinding(a.identity.digest, pa.digest, "adapter-a@1"), ProblemBinding(b.identity.digest, pb.digest, "adapter-b@1"))
    return a, b, pa, pb, bindings


def test_a_plain_comparison_is_a_diagnostic_even_when_inputs_and_outputs_match():
    a, b, *_ = _pair()
    # identical provider-input payloads and agreeing outputs: still no admission
    made = compare_providers(DECLARATION, a, "t", b, "t")
    assert made.within_tolerance and not made.same_problem_established
    assert made.classification == "diagnostic_numerical_comparison_not_corroboration"
    assert made.to_dict()["same_problem_established"] is False
    assert corroboration_admission_problems(made.to_dict())


def test_corroboration_after_admission_and_the_record_re_checks():
    a, b, pa, pb, bindings = _pair()
    made = corroborate(DECLARATION, a, "t", b, "t", problems=(pa, pb), bindings=bindings)
    assert made.classification == "solver_corroboration_not_validation"
    assert corroboration_admission_problems(made.to_dict()) == []


@pytest.mark.parametrize("changes", [
    {"sources_and_loads": {"q": Quantity(5.0, "W/m**3")}},       # DIFFERENT_PROBLEM
    {"materials": None},                                           # UNDETERMINED (one side does not declare it)
])
def test_different_or_undetermined_problems_are_refused(changes):
    a, b, pa, _, _ = _pair()
    pb = _problem("slab-b", **changes)
    bindings = (ProblemBinding(a.identity.digest, pa.digest, "a@1"), ProblemBinding(b.identity.digest, pb.digest, "b@1"))
    with pytest.raises(InvalidScientificProblem, match="not admitted as solving one problem"):
        corroborate(DECLARATION, a, "t", b, "t", problems=(pa, pb), bindings=bindings)


def _link(record, classification=None):
    cls = classification or record["classification"]
    return EvidenceLink.of_record("provider_comparison", record, cls, "met" if record["within_tolerance"] else "not_met")


def test_a_stored_pre_admission_corroboration_record_is_refused_at_level_five_never_promoted():
    a, b, *_ = _pair()
    legacy = compare_providers(DECLARATION, a, "t", b, "t").to_dict()
    # the shape of a record written before mandatory admission: corroboration class, no admission keys
    legacy["classification"] = "solver_corroboration_not_validation"
    legacy.pop("same_problem_established")
    with pytest.raises(InvalidScientificProblem, match="same-problem"):
        LevelEntry(5, LevelStatus.REACHED, (_link(legacy),))
    # it may still be recorded beside a level that is not reached
    LevelEntry(5, LevelStatus.ATTEMPTED_NOT_REACHED, (_link(legacy),))


def test_a_diagnostic_cannot_be_relabelled_as_corroboration_nor_an_admitted_record_as_a_diagnostic():
    a, b, pa, pb, bindings = _pair()
    ids = {a.identity.digest: "alpha", b.identity.digest: "beta"}
    diagnostic = compare_providers(DECLARATION, a, "t", b, "t").to_dict()
    check_provider_comparison(diagnostic, ids)
    with pytest.raises(InvalidScientificProblem, match="no valid same-problem admission"):
        check_provider_comparison({**diagnostic, "classification": "solver_corroboration_not_validation"}, ids)
    admitted = corroborate(DECLARATION, a, "t", b, "t", problems=(pa, pb), bindings=bindings).to_dict()
    check_provider_comparison(admitted, ids)
    with pytest.raises(InvalidScientificProblem, match="does not follow"):
        check_provider_comparison({**admitted, "classification": "diagnostic_numerical_comparison_not_corroboration"}, ids)


@pytest.mark.parametrize("tamper", [
    lambda r: r["problem_equivalence"].update(verdict="undetermined"),
    lambda r: r["problem_equivalence"].update(required=["governing_equations"]),
    lambda r: r["problem_equivalence"].update(b_problem="f" * 64),
    lambda r: r["problem_bindings"].pop(),
    lambda r: r["problem_bindings"][0].update(execution_identity="e" * 64),
    lambda r: r["problem_bindings"][1].update(problem_digest="e" * 64),
    lambda r: r.update(same_problem_established=False),
])
def test_a_tampered_admission_is_refused(tamper):
    a, b, pa, pb, bindings = _pair()
    record = corroborate(DECLARATION, a, "t", b, "t", problems=(pa, pb), bindings=bindings).to_dict()
    tamper(record)
    assert corroboration_admission_problems(record)
    with pytest.raises(InvalidScientificProblem):
        LevelEntry(5, LevelStatus.REACHED, (_link(record),))


def test_an_admitted_corroboration_reaches_level_five():
    a, b, pa, pb, bindings = _pair()
    record = corroborate(DECLARATION, a, "t", b, "t", problems=(pa, pb), bindings=bindings).to_dict()
    assert LevelEntry(5, LevelStatus.REACHED, (_link(record),)).status is LevelStatus.REACHED
