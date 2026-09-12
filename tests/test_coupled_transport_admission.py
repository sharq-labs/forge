"""What may cross a coupling edge, and what may not (F08).

A value is transported out of one result and into another problem's inputs.
That transfer is where a coupled run stops being a set of independent solves
and becomes one claim, and it is the point at which the loop was reading
``result.value(...)`` and nothing else.

The finding, reproduced below with a **real child process**: a controlled
provider returning zero on every channel of a non-zero circuit produced an
electrical result whose ``linear_system_residual`` and
``voltage_source_relation`` both FAILED — and its zero power was transported
into the coupling anyway. A body receiving zero heat sits at ambient, so the
loop reported ``criterion_met`` at 300 K: a clean, converged, confidently wrong
answer assembled out of a result Crafty had already checked and rejected.

The provider is genuinely external — ``tests/zero_provider.py``, launched by the
same ``NgspiceInvocation`` machinery that reaches ngspice — because the finding
is about what crosses a process boundary and is admitted on the other side.
Nothing here is monkeypatched and no solver is subclassed.

Why zeros. They are the one wrong answer that satisfies the adapter's own
admission gate without conspiracy: ``I == V/R`` and ``P == V*I`` both hold
exactly at zero. The provider therefore gets past the gate that catches a
halved or sign-flipped power, and is caught instead by Crafty's own validation
report — which is exactly the case the transfer boundary was not consulting.
"""

from __future__ import annotations

import os
import sys

import pytest

from engcore.domains.electrical import ngspice as ng
from engcore.domains.electrical.dc.problem import resistance_name
from engcore.mcp import example_electrothermal_payload
from engcore.mcp.problem import build_electrothermal_system
from engcore.scientific.results.validation import ValidationOutcome
from engcore.scientific.units.quantity import Quantity
from engcore.systems.electrothermal import coupled as cp

K = "kelvin"

#: The provider script, reached the way any external provider is: as an argv
#: prefix. ``sys.executable`` is this interpreter, so no toolchain is assumed.
ZERO_PROVIDER = (
    sys.executable,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "zero_provider.py"),
)


@pytest.fixture(scope="module")
def zero_solver():
    """One solver instance, so the version is probed once for the module."""
    return ng.NgspiceDCSolver(
        invocation=ng.NgspiceInvocation(command=ZERO_PROVIDER)
    )


@pytest.fixture(scope="module")
def system():
    return build_electrothermal_system(example_electrothermal_payload())


def _problems(system):
    return cp.coupled_problems(
        system,
        {s.component_id: s.conductor.reference_resistance for s in system.stages},
    )


def _plan(system, problems):
    return cp.nominal_plan(
        system,
        cp.coupled_dependencies(system, problems),
        seed=Quantity(300.0, K),
        tolerance=Quantity(1e-6, K),
        max_iterations=50,
    )


def _table_with_zero_provider(system, problems, solver):
    def call(inputs, run_id):
        resistances = {
            stage.component_id: inputs[resistance_name(stage.component_id)]
            for stage in system.stages
        }
        return ng.solve_circuit_with_ngspice(
            system.circuit_at(resistances), run_id=run_id, solver=solver
        )

    table = dict(cp._executors(system, problems))
    electrical = next(
        p.problem_id for p in problems if p.problem_id.startswith("electrical_dc:")
    )
    table[electrical] = call
    return table


# =====================================================================
# The provider really is external, and really does produce a FAIL
# =====================================================================

def test_the_controlled_provider_is_a_real_child_process(zero_solver):
    """It answers ``--version`` from its own process, and the version is read."""
    assert zero_solver.version == "42"
    assert zero_solver.identity.backend == "ngspice"


def test_zeros_pass_admission_and_fail_craftys_own_validation(
    zero_solver, system
):
    """The result exists, is preserved, and says of itself that it failed.

    Not an execution failure: the provider ran, answered every requested
    quantity, and its answers reconcile with each other. It is Crafty's own
    checks that reject them — which is the distinction the transfer boundary
    has to act on, and the reason a solver-level guard could not have caught
    this one.
    """
    circuit = system.circuit_at(
        {s.component_id: s.conductor.reference_resistance for s in system.stages}
    )
    result = ng.solve_circuit_with_ngspice(
        circuit, run_id="f08-standalone", solver=zero_solver
    )
    assert result.validation_status is ValidationOutcome.FAIL
    assert set(result.validation.failures) and {
        c.name for c in result.validation.failures
    } >= {"linear_system_residual", "voltage_source_relation"}
    assert result.value("resistor_power:R1").magnitude_in("watt") == 0.0


# =====================================================================
# The transfer boundary
# =====================================================================

def test_the_coupling_refuses_rather_than_converging_at_ambient(
    zero_solver, system
):
    """The finding, and the fix.

    Before: ``criterion_met`` at 300.0 K — the seed, untouched, because a body
    given zero heat never leaves ambient. The run reported success about a
    number no model here was entitled to.
    """
    problems = _problems(system)
    with pytest.raises(cp.TransportRefused) as raised:
        cp.run_fixed_point(
            problems,
            _table_with_zero_provider(system, problems, zero_solver),
            _plan(system, problems),
            run_id="f08-coupled",
            software_version="f08",
            assumptions=(),
        )

    refusal = raised.value
    message = str(refusal)
    assert "linear_system_residual" in message
    assert "voltage_source_relation" in message
    assert "resistor_power:R1" in message


def test_the_failed_result_is_preserved_as_evidence_not_dropped(
    zero_solver, system
):
    """"Do not silently substitute or drop it" — so the refusal carries it.

    The result is the evidence that an execution failed, and it is the only
    record of what the provider actually returned. A refusal that discarded it
    would leave a reader with a coupling that stopped and no way to see why.
    """
    problems = _problems(system)
    with pytest.raises(cp.TransportRefused) as raised:
        cp.run_fixed_point(
            problems,
            _table_with_zero_provider(system, problems, zero_solver),
            _plan(system, problems),
            run_id="f08-evidence",
            software_version="f08",
            assumptions=(),
        )

    result = raised.value.result
    assert result.validation_status is ValidationOutcome.FAIL
    assert result.value("resistor_power:R1").magnitude_in("watt") == 0.0
    assert result.provenance.run_id.startswith("f08-evidence")
    # and the failed checks are reachable from the refusal, named
    assert raised.value.failed_checks == (
        "linear_system_residual",
        "voltage_source_relation",
    )
    # the edge it was refused on is named too
    assert raised.value.dependency.source_quantity == "resistor_power:R1"
    assert raised.value.iteration == 1


def test_an_honest_run_through_the_same_boundary_is_untouched(system):
    """The guard refuses a failed result and nothing else.

    The native electrical solver over the same composition still reaches the
    same fixed point it always did. A gate that also stopped this would have
    been a gate on coupling rather than on admission.
    """
    run = cp.run_fixed_point_coupling(system, _plan(system, _problems(system)))
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    (temperature,) = run.final_values.values()
    assert temperature.magnitude_in(K) == pytest.approx(338.577018, abs=1e-6)


def test_a_warning_still_crosses_the_boundary(system):
    """FAIL is the bar, and it is the bar the platform already set.

    ``ValidationReport.status`` ranks WARNING below FAIL deliberately: a check
    that ran and flagged something produced its evidence. Refusing on WARNING
    would make the transfer boundary stricter than the report it reads, and
    would silently redefine what a warning means everywhere else.
    """
    assert ValidationOutcome.WARNING is not ValidationOutcome.FAIL
    assert cp.transportable(_stub(ValidationOutcome.WARNING)) is True
    assert cp.transportable(_stub(ValidationOutcome.PASS)) is True
    assert cp.transportable(_stub(ValidationOutcome.NOT_RUN)) is True
    assert cp.transportable(_stub(ValidationOutcome.FAIL)) is False


def _stub(outcome):
    """A minimal result carrying one check with the given outcome."""
    from engcore.scientific.results.provenance import ProvenanceRecord
    from engcore.scientific.results.result import ScientificResult
    from engcore.scientific.results.validation import (
        ValidationCheck,
        ValidationReport,
    )

    return ScientificResult(
        result_id="stub",
        problem_id="stub",
        values={"x": Quantity(1.0, "watt")},
        validation=ValidationReport(
            checks=(ValidationCheck(name="c", outcome=outcome),)
        ),
        provenance=ProvenanceRecord(run_id="stub"),
    )
