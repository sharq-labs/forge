"""Regression tests for the Phase 2 static-review MAJOR findings (fixed in the review-fix commit).

1. A forward ("redundant") tear is refused by the electrothermal runtime build.
2. Corroboration derives problem identity itself; a hand-built or narrowed equivalence does not establish it.
3. Plain numbers in a canonical problem: 1 and 1.0 agree, the text "1.0" does not.
4. A fresh provider participant that restores a checkpoint must then execute on the build that wrote it.

NOT RUN (Phase 2 build phase): docs/work/DEFERRED_VALIDATION.md, DV-64.
"""

from __future__ import annotations

import dataclasses
import hashlib
from types import SimpleNamespace

import pytest

from engcore.data import InMemoryBulkStore
from engcore.domains.electrical import material as mat
from engcore.domains.thermal_models import lumped as lump
from engcore.providers import ComparisonDeclaration
from engcore.providers.catalog import Availability, ProviderCapability, ProviderStatus
from engcore.providers.compare import corroborate
from engcore.providers.identity import ProviderExecutionIdentity
from engcore.providers.problem_identity import (
    CanonicalProblem, ProblemAspect, ProblemBinding, ProblemEquivalence, ProblemIdentityVerdict, compare_problems,
)
from engcore.providers.records import ProviderExecutionRecord
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity
from engcore.systems.electrothermal import coupled as cp
from engcore.systems.electrothermal.runtime_adapter import runtime_equivalent


# ---- 1. forward tears ---------------------------------------------------------------------------------------------


def test_a_redundant_forward_tear_is_refused():
    conductor = mat.TemperatureDependentConductor(
        component_id="R1", reference_resistance=Quantity(10.0, "ohm"),
        temperature_coefficient=Quantity(0.00393, "1/kelvin"), reference_temperature=Quantity(293.15, "kelvin"))
    body = lump.ThermalBody(body_id="R1", heat_capacity=Quantity(2.5, "joule/kelvin"),
                            ambient_conductance=Quantity(0.05, "watt/kelvin"), ambient_temperature=Quantity(300.0, "kelvin"),
                            initial_temperature=Quantity(300.0, "kelvin"), duration=Quantity(120.0, "second"))
    system = cp.CoupledElectroThermalSystem(stages=(cp.CoupledStage(conductor, body),), source_voltage=Quantity(5.0, "volt"))
    problems = cp.coupled_problems(system, {"R1": conductor.reference_resistance})
    dependencies = cp.coupled_dependencies(system, problems, temperature_metric=lump.TEMPERATURE_METRIC)
    plan = cp.nominal_plan(system, dependencies, seed=Quantity(300.0, "kelvin"))
    torn_keys = {cp.edge_key(t.dependency) for t in plan.torn}
    extra = next(d for d in dependencies if cp.edge_key(d) not in torn_keys)  # an edge the order already runs forward
    redundant = dataclasses.replace(
        plan, torn=plan.torn + (cp.TornEndpoint(dependency=extra, initial_value=_seed_for(extra)),))
    with pytest.raises(InvalidScientificProblem, match="run forward"):
        runtime_equivalent(system, redundant)


def _seed_for(dependency):
    return Quantity(1.0, dependency.unit_exemplar)


# ---- 2. problem identity cannot be asserted ------------------------------------------------------------------


def _problem(pid, **declarations):
    base = {aspect: f"declared {aspect.value}" for aspect in ProblemAspect}
    base.update({ProblemAspect(k): v for k, v in declarations.items()})
    return CanonicalProblem(pid, base)


def _record(pid, value):
    capability = ProviderCapability(pid, "f", "library", pid, ("demo",))
    status = ProviderStatus(capability, Availability.AVAILABLE, "1.0", "c" * 64, "/x",
                            dependencies=(("python-environment", "1", hashlib.sha256(pid.encode()).hexdigest()),))
    identity = ProviderExecutionIdentity.from_content(status, adapter_id="a", adapter_version="1", problem={pid: 1},
                                                      configuration={}, output_request=("t",))
    return ProviderExecutionRecord(identity, True, "", scalars={"t": value})


DECLARATION = ComparisonDeclaration("t", "K", "identity", Quantity(0.01, "K"), 0.0, "demo")


def test_corroboration_derives_identity_from_the_canonical_problems_not_a_verdict():
    a, b = _record("alpha", Quantity(300.0, "K")), _record("beta", Quantity(300.0, "K"))
    pa, pb = _problem("a"), _problem("b", materials="another material")
    forged = ProblemEquivalence(pa.digest, pb.digest, ProblemIdentityVerdict.SAME_PROBLEM, (), (), ())
    bindings = (ProblemBinding(a.identity.digest, pa.digest, "x"), ProblemBinding(b.identity.digest, pb.digest, "y"))
    with pytest.raises(InvalidScientificProblem, match="CanonicalProblem records"):
        corroborate(DECLARATION, a, "t", b, "t", problems=forged, bindings=bindings)
    with pytest.raises(InvalidScientificProblem, match="different_problem"):
        corroborate(DECLARATION, a, "t", b, "t", problems=(pa, pb), bindings=bindings)


def test_a_narrowed_equivalence_is_still_a_verdict_but_establishes_nothing_downstream():
    pa = CanonicalProblem("a", {ProblemAspect.QUANTITIES_OF_INTEREST: ["T"]})
    pb = CanonicalProblem("b", {ProblemAspect.QUANTITIES_OF_INTEREST: ["T"]})
    narrowed = compare_problems(pa, pb, required=(ProblemAspect.QUANTITIES_OF_INTEREST,))
    assert narrowed.verdict is ProblemIdentityVerdict.SAME_PROBLEM
    a, b = _record("alpha", Quantity(300.0, "K")), _record("beta", Quantity(300.0, "K"))
    bindings = (ProblemBinding(a.identity.digest, pa.digest, "x"), ProblemBinding(b.identity.digest, pb.digest, "y"))
    with pytest.raises(InvalidScientificProblem, match="undetermined"):
        corroborate(DECLARATION, a, "t", b, "t", problems=(pa, pb), bindings=bindings)


# ---- 3. canonical numbers ------------------------------------------------------------------------------------------


def test_numbers_are_canonical_by_value_and_never_equal_to_text():
    as_int = _problem("p", time_interval={"steps": 1})
    as_float = _problem("q", time_interval={"steps": 1.0})
    as_text = _problem("r", time_interval={"steps": "1.0"})
    assert compare_problems(as_int, as_float).verdict is ProblemIdentityVerdict.SAME_PROBLEM
    assert compare_problems(as_float, as_text).verdict is ProblemIdentityVerdict.DIFFERENT_PROBLEM


# ---- 4. a fresh participant pins the build its restored state came from -----------------------------------------


def test_a_restored_fresh_participant_refuses_to_continue_on_another_build():
    from engcore.coupling.adapters import CouplingRefusal, provider_participant, scalar_port
    from engcore.execution.multiphysics import AdvanceRequest
    from engcore.scientific.multiphysics import ParticipantSpec

    spec = ParticipantSpec("cell", "m", "1", "r", "1", "s", "1", "a", "1", (scalar_port("heat", "output", "power", "W"),),
                           transient=True, checkpointable=True, deterministic_restore=True)

    def make(version):
        identity = SimpleNamespace(provider_id="prov", provider_version=version, provider_digest="d" * 64,
                                   adapter_id="adapter", adapter_version="1")
        solve = lambda inputs, start, end, uq, state: (  # noqa: E731
            SimpleNamespace(identity=identity, succeeded=True, reason="", execution_identity="e", digest="r"),
            {"heat": Quantity(1.0, "W")})
        return provider_participant(spec, solve=solve, initial_outputs=lambda: {"heat": Quantity(0.0, "W")},
                                    store=InMemoryBulkStore())

    request = AdvanceRequest(Quantity(0, "s"), Quantity(1, "s"), {}, {})
    first = make("1.0")
    first.advance(request)
    checkpoint = first.checkpoint(Quantity(1, "s"))
    fresh = make("2.0")
    fresh.restore(checkpoint)  # nothing has executed on it yet: the restore pins build 1.0
    with pytest.raises(CouplingRefusal, match="restored state of another provider build"):
        fresh.advance(request)
