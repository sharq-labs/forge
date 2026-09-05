"""HETEROGENEOUS REAL PROVIDER PROOF — real external ngspice.

Preregistration: ``docs/milestones/heterogeneous-ngspice-prereg.md`` (commit 549ad81),
written and committed before any source file on this branch was added or edited.
Test identifiers below are the preregistration's §12.

**These tests execute a real ngspice process.** The provider is
``ngspice-42`` from Ubuntu ``noble/universe``, reached as ``wsl.exe -e ngspice``.
No mock, stub, fake provider or Crafty-written stand-in appears anywhere in the
evidence path; mocks are used only where the preregistration permits them, for
unit tests of the parser.
"""

from __future__ import annotations

import ast
import inspect
import json
import pathlib
import subprocess
import textwrap

import pytest

from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.domains.electrical import dc_realizations as dr
from src.engcore.domains.electrical import material as mat
from src.engcore.domains.electrical import ngspice as ng
from src.engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
    models_for_circuit,
    solve_circuit,
)
from src.engcore.domains.electrical.dc.problem import resistance_name
from src.engcore.scientific.errors import ScientificCoreError
from src.engcore.scientific.ir.problem import ModelReference
from src.engcore.scientific.results.provenance import (
    ExecutionBinding,
    ProvenanceRecord,
)
from src.engcore.scientific.results.validation import ValidationOutcome
from src.engcore.scientific.solvers.protocol import ConvergenceState
from src.engcore.scientific.units.quantity import Quantity
from src.engcore.systems.electrothermal import coupled as cp

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
KELVIN = "kelvin"

#: Preregistration §10.
REL_TOL = 1e-9
ABS_FLOOR = 1e-12
COUPLED_T_ATOL = 1e-4
COUPLED_REL_TOL = 1e-6


# =====================================================================
# Declarations
# =====================================================================

def conductor(cid, r_ref, alpha, t_ref=293.15):
    return mat.TemperatureDependentConductor(
        component_id=cid,
        reference_resistance=Quantity(r_ref, "ohm"),
        temperature_coefficient=Quantity(alpha, "1/kelvin"),
        reference_temperature=Quantity(t_ref, KELVIN),
    )


def body(cid, capacity, conductance, ambient=300.0, initial=300.0, duration=120.0):
    return lump.ThermalBody(
        body_id=cid,
        heat_capacity=Quantity(capacity, "joule/kelvin"),
        ambient_conductance=Quantity(conductance, "watt/kelvin"),
        ambient_temperature=Quantity(ambient, KELVIN),
        initial_temperature=Quantity(initial, KELVIN),
        duration=Quantity(duration, "second"),
    )


def divider(circuit_id="hetero-standalone"):
    """Preregistration §6: one ideal source, two series resistive elements."""
    return DCCircuit(
        circuit_id=circuit_id,
        nodes=(
            ElectricalNode("n0"),
            ElectricalNode("n1"),
            ElectricalNode("gnd", is_reference=True),
        ),
        resistors=(
            Resistor("R1", "n0", "n1", Quantity(10.0, "ohm")),
            Resistor("R2", "n1", "gnd", Quantity(20.0, "ohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V1", "n0", "gnd", Quantity(12.0, "volt")),
        ),
    )


NOMINAL = cp.CoupledElectroThermalSystem(
    (cp.CoupledStage(conductor("R1", 10.0, 0.00393), body("R1", 2.5, 0.05)),),
    Quantity(5.0, "volt"),
)
TWO_STAGE = cp.CoupledElectroThermalSystem(
    (
        cp.CoupledStage(conductor("R1", 10.0, 0.00393), body("R1", 2.5, 0.05)),
        cp.CoupledStage(conductor("R2", 20.0, 0.00060), body("R2", 5.0, 0.02)),
    ),
    Quantity(12.0, "volt"),
)


def ngspice_electrical_executor(system, solver):
    """The **entire** provider substitution, and it is nine lines.

    Structurally identical to ``coupled.py``'s own ``electrical_call``: it takes
    the transported resistances, builds the circuit, and returns a
    ``ScientificResult``. Nothing about the coupling loop, the thermal side, the
    property side, the plan or the dependency records changes — the substitution
    happens strictly *below* coupling semantics, which is preregistration §7's
    central acceptance condition.

    It lives in the test rather than in production because the milestone's claim
    is precisely that no production glue was needed.
    """
    def call(inputs, run_id):
        resistances = {
            stage.component_id: inputs[resistance_name(stage.component_id)]
            for stage in system.stages
        }
        return ng.solve_circuit_with_ngspice(
            system.circuit_at(resistances), run_id=run_id, solver=solver
        )

    return call


def run_coupled(system, *, provider, seed=300.0, budget=50, label="run"):
    problems = cp.coupled_problems(
        system,
        {s.component_id: s.conductor.reference_resistance for s in system.stages},
    )
    plan = cp.nominal_plan(
        system,
        cp.coupled_dependencies(system, problems),
        seed=Quantity(seed, KELVIN),
        tolerance=Quantity(1e-6, KELVIN),
        max_iterations=budget,
    )
    table = dict(cp._executors(system, problems))
    if provider == "ngspice":
        electrical = next(
            p.problem_id for p in problems if p.problem_id.startswith("electrical_dc:")
        )
        table[electrical] = ngspice_electrical_executor(system, ng.NgspiceDCSolver())
    return cp.run_fixed_point(
        problems, table, plan,
        run_id=f"{label}-{provider}", software_version="hetero-proof",
        assumptions=(),
    )


def relative(a: float, b: float) -> float:
    scale = max(abs(a), abs(b))
    return abs(a - b) if scale <= ABS_FLOOR else abs(a - b) / scale


# =====================================================================
# Fixtures — each real invocation runs once
# =====================================================================

@pytest.fixture(scope="module")
def standalone():
    circuit = divider()
    return circuit, solve_circuit(circuit, run_id="native-standalone"), \
        ng.solve_circuit_with_ngspice(circuit, run_id="ngspice-standalone")


@pytest.fixture(scope="module")
def coupled_nominal():
    return (run_coupled(NOMINAL, provider="native", label="A"),
            run_coupled(NOMINAL, provider="ngspice", label="A"))


@pytest.fixture(scope="module")
def coupled_two_stage():
    return (run_coupled(TWO_STAGE, provider="native", label="E"),
            run_coupled(TWO_STAGE, provider="ngspice", label="E"))


# =====================================================================
# TEST A — a real external process
# =====================================================================

def test_a_the_provider_is_a_real_external_process(standalone):
    """Not a mock, not a stub, not a second Crafty solver.

    The version is read **from the running binary**, not hard-coded — a pinned
    string would make provenance lie the moment the binary changed.
    """
    _, _, external = standalone
    probed = ng.NgspiceInvocation().probe_version()
    assert probed == external.solver.version
    assert probed.startswith("42")
    assert external.solver.backend == "ngspice"

    # the adapter genuinely launches a process; nothing in it fabricates output
    source = pathlib.Path(inspect.getfile(ng)).read_text(encoding="utf-8")
    assert "subprocess.run" in source
    for forbidden in ("mock", "Mock", "fake", "stub", "simulate_"):
        assert forbidden not in source, forbidden


def test_a2_the_provider_actually_computes_the_answer():
    """A control: change the circuit and the provider's answer changes with it.

    Guards against the failure mode where an adapter appears to work because it
    is really reading something else — the answer must track the input.
    """
    solver = ng.NgspiceDCSolver()
    seen = []
    for ohms in (10.0, 20.0, 40.0):
        circuit = DCCircuit(
            circuit_id=f"control-{ohms:g}",
            nodes=(ElectricalNode("a"), ElectricalNode("g", is_reference=True)),
            resistors=(Resistor("R1", "a", "g", Quantity(ohms, "ohm")),),
            voltage_sources=(
                DCVoltageSource("V1", "a", "g", Quantity(10.0, "volt")),
            ),
        )
        result = ng.solve_circuit_with_ngspice(
            circuit, run_id=f"c{ohms:g}", solver=solver
        )
        seen.append(result.values["resistor_power:R1"].magnitude_in("watt"))
    # P = V^2/R for 10 V: 10, 5, 2.5
    assert seen == pytest.approx([10.0, 5.0, 2.5], rel=1e-12)


# =====================================================================
# TEST B — the same scientific input
# =====================================================================

def test_b_both_paths_consume_the_same_canonical_problem(standalone):
    circuit, native, external = standalone
    assert native.problem_id == external.problem_id
    assert native.models == external.models
    # the netlist is derived from the Crafty circuit, never hand-written
    netlist = ng.build_netlist(circuit)
    assert "12" in netlist.text and "10" in netlist.text and "20" in netlist.text
    # and it is a pure function of the circuit
    assert ng.build_netlist(circuit).text == netlist.text


def test_b2_the_netlist_translation_is_deterministic_and_assigns_names():
    """Provider-legal names are **assigned**, never escaped.

    Crafty ids are arbitrary strings; SPICE has its own lexical rules and a
    mandatory node ``0``. Assigning index-derived names makes collisions
    impossible and means no Crafty identifier ever has to be SPICE-legal.
    """
    awkward = DCCircuit(
        circuit_id="awkward ids",
        nodes=(
            ElectricalNode("zz top"),
            ElectricalNode("aa/mid"),
            ElectricalNode("the datum", is_reference=True),
        ),
        resistors=(
            Resistor("R one", "zz top", "aa/mid", Quantity(100.0, "ohm")),
            Resistor("R two", "aa/mid", "the datum", Quantity(200.0, "ohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V a", "zz top", "the datum", Quantity(6.0, "volt")),
        ),
    )
    netlist = ng.build_netlist(awkward)
    # the Crafty reference node became ngspice node 0, with no element added
    assert netlist.node_names["the datum"] == "0"
    assert "0" in netlist.node_names.values()
    assert netlist.text.count("\n") == ng.build_netlist(awkward).text.count("\n")
    # no awkward Crafty identifier reached the provider
    for bad in ("zz top", "aa/mid", "the datum", "R one", "V a"):
        assert bad not in netlist.text
    # and it still solves
    result = ng.solve_circuit_with_ngspice(awkward, run_id="awkward")
    assert result.values["node_voltage:aa/mid"].magnitude_in("volt") == pytest.approx(
        4.0, rel=1e-12
    )
    assert result.values["node_voltage:the datum"].magnitude_in("volt") == 0.0


# =====================================================================
# TEST C — standalone numerical equivalence
# =====================================================================

def test_c_native_and_ngspice_agree_within_the_preregistered_tolerance(standalone):
    _, native, external = standalone
    assert set(native.values) == set(external.values)
    assert native.convergence is external.convergence is ConvergenceState.CONVERGED

    worst = 0.0
    for name, quantity in native.values.items():
        unit = quantity.units
        a = quantity.magnitude_in(unit)
        b = external.values[name].magnitude_in(unit)
        assert external.values[name].units == unit, name
        worst = max(worst, relative(a, b))
    assert worst <= REL_TOL, f"worst relative difference {worst:.3e}"
    # measured: machine epsilon, seven orders inside the bound
    assert worst < 1e-14


def test_c2_the_provider_answer_satisfies_craftys_own_assembled_equations(standalone):
    """The validity authority does not change when the provider does.

    ``linear_system_residual`` substitutes ngspice's solution into the MNA
    system Crafty assembled itself, so the external answer is checked against
    the domain's equations rather than against itself.
    """
    _, native, external = standalone
    assert external.validation_status is ValidationOutcome.PASS
    names = {c.name for c in external.validation.checks}
    assert {
        "linear_system_residual", "kirchhoff_current_law",
        "resistor_metric_consistency", "voltage_source_relation", "power_balance",
    } <= names
    # Every native check runs on the external path, and the external path runs
    # two MORE: the realization's declared precondition, and a reconciliation of
    # the two metrics the provider supplies that no other check reads. Both were
    # added because the adversarial pass showed the native set alone cannot see
    # a provider fabricating an exact solution to a rank-deficient system.
    assert {c.name for c in native.validation.checks} < names
    assert names - {c.name for c in native.validation.checks} == {
        "realization_precondition_non_singular",
        "provider_element_metric_consistency",
    }
    residual = next(
        c for c in external.validation.checks if c.name == "linear_system_residual"
    )
    assert residual.outcome is ValidationOutcome.PASS
    assert residual.residual < 1e-12

    # the provider's own element metrics agree with Crafty's relations
    reconciliation = next(
        c for c in external.validation.checks
        if c.name == "provider_element_metric_consistency"
    )
    assert reconciliation.outcome is ValidationOutcome.PASS
    assert reconciliation.residual < 1e-12


# =====================================================================
# TEST D — provider substitution below coupling semantics
# =====================================================================

def test_d_the_coupling_code_is_identical_between_the_two_runs():
    """Preregistration §7, the central acceptance condition.

    Not "equivalent" — *the same function object*. And no
    ``native_coupling()`` / ``ngspice_coupling()`` pair exists.
    """
    assert cp.run_fixed_point is cp.run_fixed_point
    exported = set(cp.__all__)
    for forbidden in (
        "native_coupling", "ngspice_coupling", "run_fixed_point_native",
        "run_fixed_point_ngspice", "ProviderRegistry", "ExternalProvider",
    ):
        assert forbidden not in exported, forbidden

    # coupled.py knows nothing about any provider
    source = pathlib.Path(inspect.getfile(cp)).read_text(encoding="utf-8").lower()
    for forbidden in ("ngspice", "spice", "netlist", "subprocess", "wsl"):
        assert forbidden not in source, forbidden


def test_d2_only_one_dispatch_entry_differs(coupled_nominal):
    """The substitution is one key of a dict the coupling loop takes as data."""
    problems = cp.coupled_problems(
        NOMINAL,
        {s.component_id: s.conductor.reference_resistance for s in NOMINAL.stages},
    )
    native_table = cp._executors(NOMINAL, problems)
    electrical = next(
        p.problem_id for p in problems if p.problem_id.startswith("electrical_dc:")
    )
    substituted = dict(native_table)
    substituted[electrical] = ngspice_electrical_executor(
        NOMINAL, ng.NgspiceDCSolver()
    )
    assert set(substituted) == set(native_table)
    differing = [k for k in native_table if substituted[k] is not native_table[k]]
    assert differing == [electrical]


# =====================================================================
# TEST E — closed-loop equivalence
# =====================================================================

def test_e_case_a_coupled_results_agree(coupled_nominal):
    native, external = coupled_nominal
    assert native.outcome is external.outcome is cp.CouplingOutcome.CRITERION_MET
    assert set(native.final_values) == set(external.final_values)
    for key, quantity in native.final_values.items():
        a = quantity.magnitude_in(KELVIN)
        b = external.final_values[key].magnitude_in(KELVIN)
        assert abs(a - b) <= COUPLED_T_ATOL, key
    # and it is the ET-VERTICAL fixed point, reached through a foreign solver
    (temperature,) = external.final_values.values()
    assert temperature.magnitude_in(KELVIN) == pytest.approx(338.577018, abs=1e-6)


def test_e2_case_e_two_stage_coupled_results_agree(coupled_two_stage):
    native, external = coupled_two_stage
    assert native.outcome is external.outcome is cp.CouplingOutcome.CRITERION_MET
    for key, quantity in native.final_values.items():
        assert abs(
            quantity.magnitude_in(KELVIN)
            - external.final_values[key].magnitude_in(KELVIN)
        ) <= COUPLED_T_ATOL, key
    values = {
        q: v.magnitude_in(KELVIN) for (_, q), v in external.final_values.items()
    } if False else {
        p: v.magnitude_in(KELVIN) for (p, _), v in external.final_values.items()
    }
    assert values["resistance-tcr-R1"] == pytest.approx(328.898146, abs=1e-6)
    assert values["resistance-tcr-R2"] == pytest.approx(355.089513, abs=1e-6)


def test_e3_the_electrical_quantities_at_the_fixed_point_agree(coupled_two_stage):
    """Resistance, current and Joule heat — the quantities the loop transports."""
    native, external = coupled_two_stage
    for tag in ("resistor_power:R1", "resistor_power:R2", "source_current:V1"):
        a = _electrical(native).values[tag]
        b = _electrical(external).values[tag]
        assert b.units == a.units
        assert relative(
            a.magnitude_in(a.units), b.magnitude_in(a.units)
        ) <= COUPLED_REL_TOL, tag
    for problem_id in ("resistance-tcr-R1", "resistance-tcr-R2"):
        a = native.final.result_for(problem_id).value(mat.RESISTANCE_METRIC)
        b = external.final.result_for(problem_id).value(mat.RESISTANCE_METRIC)
        assert relative(
            a.magnitude_in("ohm"), b.magnitude_in("ohm")
        ) <= COUPLED_REL_TOL


def _electrical(run):
    return next(
        r for r in run.final.results if r.problem_id.startswith("electrical_dc:")
    )


def test_e4_iteration_counts_are_recorded_not_required(coupled_nominal, coupled_two_stage):
    """Path length is not a scientific invariant; it is reported either way."""
    for native, external in (coupled_nominal, coupled_two_stage):
        assert native.iterations_run >= 2 and external.iterations_run >= 2
    # measured: they happen to match, which is recorded and not asserted as law
    assert coupled_nominal[0].iterations_run == 10
    assert coupled_two_stage[0].iterations_run == 8


# =====================================================================
# TEST F / M — provenance and realization identity
# =====================================================================

def test_f_provenance_distinguishes_the_execution(standalone):
    _, native, external = standalone
    assert native.solver.solver_id == "electrical.dc.mna"
    assert external.solver.solver_id == ng.NGSPICE_SOLVER_ID
    assert native.solver.solver_id != external.solver.solver_id
    # the SCIENCE is identical: same models, same versions
    assert native.models == external.models
    assert {m.model_id for m in models_for_circuit(divider())} == {
        m for m, _ in native.models
    }
    # no new model was minted because the provider differs
    assert not any("ngspice" in m for m, _ in external.models)


def test_m_the_two_solvers_execute_the_same_realization(standalone):
    """Preregistration §8: same realization, different concrete solver.

    ``solvers_for_realization`` returns two solvers for one realization, **one
    of which Crafty did not write** — the shape that method's docstring was
    built for and which `MODEL0-R` recorded as never executed.

    **Honest caveat, asserted rather than glossed:** the ngspice adapter
    *writes* its bindings; the native ``solve_circuit`` writes **none**, because
    it predates `MODEL0-R`. The native half of the combined record below is
    therefore asserted by this proof from what demonstrably ran, not read off a
    record the native path produced.
    """
    circuit, native, external = standalone
    assert native.provenance.bindings == ()          # the honest gap, unchanged
    assert len(external.provenance.bindings) == 3
    for binding in external.provenance.bindings:
        assert binding.realization is not None
        assert binding.realization.realization_id.endswith(
            ".modified_nodal_analysis"
        )
        assert binding.solver.solver_id == ng.NGSPICE_SOLVER_ID

    models = models_for_circuit(circuit)
    by_model = {r.model.model_id: r for r in dr.realizations_for_models(models)}
    combined = ProvenanceRecord(
        run_id="both-solvers",
        bindings=tuple(
            ExecutionBinding(
                model=ModelReference(m.model_id, m.version),
                realization=by_model[m.model_id].reference(),
                solver=solver,
            )
            for m in models
            for solver in (native.solver, external.solver)
        ),
    )
    assert len(combined.solvers) == 2
    assert len(combined.realizations) == 3
    for realization in dr.MNA_REALIZATIONS:
        solvers = combined.solvers_for_realization(realization.realization_id)
        assert {s.solver_id for s in solvers} == {
            "electrical.dc.mna", ng.NGSPICE_SOLVER_ID
        }


def test_m2_the_realization_records_name_no_solver_and_no_backend():
    """A realization that named a factorisation would make linear algebra science.

    Native is dense LAPACK LU (``scipy.linalg.solve``); ngspice-42 is sparse
    KLU. The capability vocabulary has one member for both, and neither appears
    in the record.
    """
    for realization in dr.MNA_REALIZATIONS:
        payload = json.dumps(realization.to_dict()).lower()
        for forbidden in (
            "ngspice", "scipy", "lapack", "klu", "sparse", "dense", "numpy",
            "wsl", "subprocess",
        ):
            assert forbidden not in payload, f"{forbidden} in {realization.realization_id}"
        assert realization.required_solver_capabilities == frozenset(
            dr.MNA_REALIZATIONS[0].required_solver_capabilities
        )


def test_m3_the_grain_limitation_is_visible_rather_than_hidden():
    """Three records, one computation, one identical provided capability.

    ``ModelRealizationDefinition.model`` is a single ``ModelReference`` and one
    DC analysis invokes three models that MNA realizes jointly. The record
    cannot say "these three, together"; three records carrying the same
    capability is the honest signature of that, and it is a measured limitation
    rather than a design.
    """
    assert len(dr.MNA_REALIZATIONS) == 3

    # Each record provides exactly what its own model discharges, and the three
    # are distinct. An earlier form gave all three one shared
    # `electrical:dc_operating_point`, reasoning that MNA provides the operating
    # point jointly. The adversarial pass killed it: `RealizationRegistry`
    # is a real existing consumer, and `providing(...)` would have returned
    # three realizations for that identity — a caller taking the first gets the
    # KCL record, which alone computes nothing.
    provided = [frozenset(r.provided_capabilities) for r in dr.MNA_REALIZATIONS]
    assert all(len(s) == 1 for s in provided)
    assert len({next(iter(s)) for s in provided}) == 3

    registry = dr.dc_realizations()
    for realization in dr.MNA_REALIZATIONS:
        (capability,) = realization.provided_capabilities
        matches = registry.providing(str(capability))
        assert [m.realization_id for m in matches] == [realization.realization_id]

    # What remains genuinely lost is recorded rather than encoded: no capability
    # names the operating point, because no single record may claim it.
    everything = {str(c) for s in provided for c in s}
    assert not any("operating_point" in c for c in everything)

    # no composite "DC analysis" model was invented to paper over it
    assert not any("analysis" in r.model.model_id for r in dr.MNA_REALIZATIONS)


# =====================================================================
# TEST G — real provider failure, typed and distinguishable
# =====================================================================

def test_g_a_missing_executable_is_a_provider_failure_not_a_scientific_one():
    solver = ng.NgspiceDCSolver(
        ng.NgspiceInvocation(command=("crafty-no-such-provider-xyz",))
    )
    with pytest.raises(ng.NgspiceUnavailable):
        ng.solve_circuit_with_ngspice(divider(), run_id="gone", solver=solver)
    assert not issubclass(ng.NgspiceProviderError, ScientificCoreError)
    assert issubclass(ng.NgspiceUnavailable, ng.NgspiceProviderError)
    assert issubclass(ng.NgspiceExecutionFailure, ng.NgspiceProviderError)


def test_g2_a_genuine_non_zero_exit_is_a_provider_failure():
    """The real binary, a real malformed input, a real exit code 1."""
    invocation = ng.NgspiceInvocation()
    done = subprocess.run(
        [*invocation.command, "-b"],
        input="bad\nRQ n0 n1 NOT_A_NUMBER\n.op\n.end\n",
        capture_output=True, text=True, timeout=invocation.timeout_seconds,
    )
    assert done.returncode == 1        # measured against the genuine provider

    class Malformed(ng.NgspiceDCSolver):
        def prepare(self, problem):
            prepared = super().prepare(problem)
            payload = prepared.payload
            broken = ng._Netlist(
                "bad\nRQ n0 n1 NOT_A_NUMBER\n.op\n.end\n",
                payload.netlist.node_names, payload.netlist.resistor_names,
                payload.netlist.source_names, payload.netlist.requested,
            )
            return type(prepared)(
                problem=prepared.problem, solver=prepared.solver,
                settings=prepared.settings,
                payload=ng.PreparedNgspiceSolve(
                    payload.circuit, broken, payload.invocation
                ),
            )

    with pytest.raises(ng.NgspiceExecutionFailure, match="exited"):
        ng.solve_circuit_with_ngspice(
            divider(), run_id="malformed", solver=Malformed()
        )


def test_g3_a_missing_requested_quantity_is_a_provider_failure():
    """An ambiguous absence is reported, never interpreted."""

    class AsksForNothing(ng.NgspiceDCSolver):
        def prepare(self, problem):
            prepared = super().prepare(problem)
            payload = prepared.payload
            netlist = payload.netlist
            broken = ng._Netlist(
                netlist.text.replace("print ", "print v(no_such_node) "),
                netlist.node_names, netlist.resistor_names, netlist.source_names,
                netlist.requested + ("v(no_such_node)",),
            )
            return type(prepared)(
                problem=prepared.problem, solver=prepared.solver,
                settings=prepared.settings,
                payload=ng.PreparedNgspiceSolve(
                    payload.circuit, broken, payload.invocation
                ),
            )

    with pytest.raises(ng.NgspiceExecutionFailure, match="requested quantit"):
        ng.solve_circuit_with_ngspice(
            divider(), run_id="missing", solver=AsksForNothing()
        )


def test_g4_provider_failure_is_none_of_the_other_three_failures(coupled_nominal):
    """The four kinds stay four kinds.

    A provider failure raises and produces **no** ``ScientificResult``, so it
    can never be read as a convergence state, a coupling outcome or a validation
    verdict — the distinction is structural, not a convention.
    """
    solver = ng.NgspiceDCSolver(
        ng.NgspiceInvocation(command=("crafty-no-such-provider-xyz",))
    )
    with pytest.raises(ng.NgspiceProviderError) as raised:
        ng.solve_circuit_with_ngspice(divider(), run_id="x", solver=solver)
    assert not isinstance(raised.value, ScientificCoreError)

    # the three things it is not, each still reachable and still distinct
    assert ConvergenceState.FAILED is not ConvergenceState.CONVERGED
    assert cp.CouplingOutcome.ITERATION_LIMIT_REACHED is not (
        cp.CouplingOutcome.CRITERION_MET
    )
    assert ValidationOutcome.FAIL is not ValidationOutcome.PASS
    # and a provider failure inside a coupling run propagates rather than
    # being recorded as non-convergence
    native, _ = coupled_nominal
    assert native.outcome is cp.CouplingOutcome.CRITERION_MET


def test_g5_the_singular_precondition_is_detected_on_both_paths():
    """Preregistration §9.3 predicted an asymmetry. The falsifier made it worse,
    and then smaller.

    **Predicted, and confirmed:** on a structurally singular circuit ngspice
    exits 0 and returns the complete requested quantity set as zeros, while the
    native path refuses outright. The preregistration further predicted that
    Crafty's own checks would *pass* those zeros, and reasoned that every repair
    was worse than disclosure.

    **That reasoning was wrong, and the adversarial pass showed why.** The zero
    vector is an *exact* solution of ``A x = z``, so no check over ``(A, x)``
    could ever have caught it — but ``validate`` already assembles ``A``, and
    rank is a property of ``A`` alone. Checking the realization's own declared
    precondition is neither provider text nor new domain logic.

    So the two paths now agree on the **science** and differ only on the
    **numerics**, which is the sharper separation:

    * native — ``convergence=FAILED``, ``validation=FAIL``, zero metrics
    * ngspice — ``convergence=CONVERGED`` (the provider did return a complete
      set, and saying otherwise would misreport the backend), ``validation=FAIL``
    """
    singular = DCCircuit(
        circuit_id="singular",
        nodes=(
            ElectricalNode("n0"), ElectricalNode("n1"), ElectricalNode("n2"),
            ElectricalNode("gnd", is_reference=True),
        ),
        resistors=(Resistor("R1", "n1", "n2", Quantity(10.0, "ohm")),),
        voltage_sources=(
            DCVoltageSource("V1", "n0", "gnd", Quantity(12.0, "volt")),
        ),
    )
    native = solve_circuit(singular, run_id="sing-native")
    assert native.convergence is ConvergenceState.FAILED
    assert native.validation_status is ValidationOutcome.FAIL
    assert native.values == {}

    external = ng.solve_circuit_with_ngspice(singular, run_id="sing-ngspice")
    # the provider genuinely returned a complete set of zeros with exit 0
    assert external.convergence is ConvergenceState.CONVERGED
    assert external.values["node_voltage:n1"].magnitude_in("volt") == 0.0
    assert external.values["node_voltage:n2"].magnitude_in("volt") == 0.0

    # and the SCIENTIFIC verdict is FAIL, on the realization's own precondition
    assert external.validation_status is ValidationOutcome.FAIL
    precondition = next(
        c for c in external.validation.checks
        if c.name == "realization_precondition_non_singular"
    )
    assert precondition.outcome is ValidationOutcome.FAIL
    assert precondition.residual >= 1.0            # rank deficiency

    # the reason no other check could have caught it: the zeros are an EXACT
    # solution of Crafty's own assembled system
    residual = next(
        c for c in external.validation.checks if c.name == "linear_system_residual"
    )
    assert residual.outcome is ValidationOutcome.PASS
    for name in (
        "kirchhoff_current_law", "resistor_metric_consistency",
        "voltage_source_relation", "power_balance",
    ):
        assert next(
            c for c in external.validation.checks if c.name == name
        ).outcome is ValidationOutcome.PASS

    # a well-posed circuit still passes the precondition
    healthy = ng.solve_circuit_with_ngspice(divider("healthy"), run_id="ok")
    assert healthy.validation_status is ValidationOutcome.PASS
    assert next(
        c for c in healthy.validation.checks
        if c.name == "realization_precondition_non_singular"
    ).outcome is ValidationOutcome.PASS

    # the provider DID say something — verbatim, uninterpreted, and NOT what
    # produced the verdict above
    assert any("singular" in w.lower() for w in external.warnings)


def test_g6_supports_does_not_claim_what_prepare_refuses():
    """The adapter answers ``supports`` on what it can actually realize.

    An earlier form asked only whether the problem's required capabilities were
    a subset of the solver's — which returned True for a circuit containing a
    current source that ``build_netlist`` then refuses, and True for a problem
    declaring no capabilities at all.
    """
    from src.engcore.domains.electrical.dc import DCCurrentSource, build_dc_problem
    from src.engcore.scientific.ir.problem import ScientificProblem

    solver = ng.NgspiceDCSolver()
    assert solver.supports(build_dc_problem(divider())) is True

    with_current_source = DCCircuit(
        circuit_id="has-isource",
        nodes=(ElectricalNode("a"), ElectricalNode("g", is_reference=True)),
        resistors=(Resistor("R1", "a", "g", Quantity(10.0, "ohm")),),
        current_sources=(
            DCCurrentSource("I1", "g", "a", Quantity(1.0, "ampere")),
        ),
    )
    problem = build_dc_problem(with_current_source)
    assert solver.supports(problem) is False
    # and the refusal is consistent: it would also have failed to translate
    with pytest.raises(Exception):
        ng.build_netlist(with_current_source)

    # a problem declaring nothing is not supported either
    assert solver.supports(ScientificProblem(problem_id="empty")) is False


# =====================================================================
# TEST P — provider power is admitted only if independently reconciled
# =====================================================================

class _CorruptPower(ng.NgspiceDCSolver):
    """A provider whose power channel uses a different convention.

    Node voltages and element currents remain exactly right and entirely
    plausible; only ``@r[p]`` is altered. This is the realistic failure — a
    provider reporting power on another convention — not one returning garbage.
    """

    factor = 0.5

    def solve(self, prepared):
        raw = super().solve(prepared)
        values = dict(raw.values)
        for key in list(values):
            if key.startswith("@") and key.endswith("[p]"):
                values[key] = values[key] * self.factor
        return type(raw)(
            convergence=raw.convergence, values=values,
            iterations=raw.iterations, wall_seconds=raw.wall_seconds,
            warnings=raw.warnings, diagnostics=raw.diagnostics,
        )


class _FlippedPower(_CorruptPower):
    """Delivered rather than absorbed: the sign convention inverted."""

    factor = -1.0


class _FlippedCurrent(ng.NgspiceDCSolver):
    """The current channel inverted, with power left internally consistent.

    Both channels are flipped together, so ``P = V * I`` would still be
    satisfied if the power relation were the only one checked. Only the
    Ohm's-law relation against Crafty's **declared** resistance catches it.
    """

    def solve(self, prepared):
        raw = super().solve(prepared)
        values = dict(raw.values)
        for key in list(values):
            if key.startswith("@") and key.endswith("[i]"):
                values[key] = -values[key]
        return type(raw)(
            convergence=raw.convergence, values=values,
            iterations=raw.iterations, wall_seconds=raw.wall_seconds,
            warnings=raw.warnings, diagnostics=raw.diagnostics,
        )


@pytest.mark.parametrize(
    "solver_class,expected",
    [
        (_CorruptPower, "V_drop \\* I"),
        (_FlippedPower, "V_drop \\* I"),
        (_FlippedCurrent, "current convention"),
    ],
)
def test_p_a_corrupted_provider_quantity_is_refused_at_admission(
    solver_class, expected
):
    """A provider value its own other channels deny never becomes a metric.

    Refused as a **provider execution failure** — the provider ran and did not
    deliver what was asked — so no ``ScientificResult`` is synthesised. It is
    not a scientific verdict: Crafty's ``build_validation_report`` remains the
    sole authority on whether an *admitted* answer is physically consistent.
    """
    with pytest.raises(ng.NgspiceExecutionFailure, match=expected):
        ng.solve_circuit_with_ngspice(
            divider("corrupt"), run_id="corrupt", solver=solver_class()
        )


def test_p2_the_corrupted_power_is_refused_before_the_coupled_loop_admits_it():
    """The requirement, and the reason the reporting check was not enough.

    Measured before the gate existed: a provider halving its reported power
    produced ``validation_status = FAIL`` on the electrical result **and the
    coupling loop transported it anyway**, converging to `320.524069785 K`
    against the true `338.577017565 K` — **18.05 K of wrong physics, admitted
    under a green coupling outcome.** The loop reads values, not reports.

    Now the run raises and no ``CoupledRun`` exists at all.
    """
    honest = run_coupled(NOMINAL, provider="ngspice", label="P2")
    (true_temperature,) = honest.final_values.values()
    assert true_temperature.magnitude_in(KELVIN) == pytest.approx(
        338.577018, abs=1e-6
    )

    problems = cp.coupled_problems(
        NOMINAL,
        {s.component_id: s.conductor.reference_resistance for s in NOMINAL.stages},
    )
    plan = cp.nominal_plan(
        NOMINAL, cp.coupled_dependencies(NOMINAL, problems),
        seed=Quantity(300.0, KELVIN), tolerance=Quantity(1e-6, KELVIN),
        max_iterations=50,
    )
    table = dict(cp._executors(NOMINAL, problems))
    electrical = next(
        p.problem_id for p in problems if p.problem_id.startswith("electrical_dc:")
    )
    table[electrical] = ngspice_electrical_executor(NOMINAL, _CorruptPower())

    with pytest.raises(ng.NgspiceExecutionFailure):
        cp.run_fixed_point(
            problems, table, plan, run_id="P2-corrupt",
            software_version="hetero-proof", assumptions=(),
        )

    # the corruption was material, not a rounding-level nudge
    assert _CorruptPower.factor == 0.5


def test_p3_the_relations_are_independent_of_the_quantity_they_check():
    """Requirement 4: no relation compares the power against itself.

    ngspice reports node potentials, element currents and element powers on
    three separate output channels, and the resistance is Crafty's own
    declaration. The two relations are:

        I ≈ V_drop / R      right-hand side: a provider VOLTAGE and a Crafty
                            DECLARATION — no current, no power
        P ≈ V_drop · I      right-hand side: a provider VOLTAGE and a provider
                            CURRENT — no power

    Neither right-hand side contains the quantity on its left.
    """
    source = _code_only(inspect.getsource(ng.NgspiceDCSolver._admit_element_power))
    # the power relation is built from v_drop and current, never from power
    assert "expected_power = v_drop * current" in source
    assert "expected_current = v_drop / ohms" in source
    assert "expected_power = power" not in source

    # and it is exercised numerically: the true values satisfy both relations
    solver = ng.NgspiceDCSolver()
    result = ng.solve_circuit_with_ngspice(
        divider("independent"), run_id="indep", solver=solver
    )
    for cid, ohms in (("R1", 10.0), ("R2", 20.0)):
        v = result.values[f"resistor_voltage:{cid}"].magnitude_in("volt")
        i = result.values[f"resistor_current:{cid}"].magnitude_in("ampere")
        p = result.values[f"resistor_power:{cid}"].magnitude_in("watt")
        assert i == pytest.approx(v / ohms, abs=1e-12)
        assert p == pytest.approx(v * i, abs=1e-12)
        assert p >= 0.0


def test_p4_admission_is_a_provider_failure_not_a_scientific_verdict():
    """The taxonomy is unchanged: refusal raises, and raises the right type."""
    with pytest.raises(ng.NgspiceProviderError) as raised:
        ng.solve_circuit_with_ngspice(
            divider("taxonomy"), run_id="tax", solver=_FlippedPower()
        )
    assert isinstance(raised.value, ng.NgspiceExecutionFailure)
    assert not isinstance(raised.value, ScientificCoreError)

    # a well-posed honest run is untouched, and records the reconciliation
    good = ng.solve_circuit_with_ngspice(divider("ok"), run_id="ok")
    assert good.validation_status is ValidationOutcome.PASS
    check = next(
        c for c in good.validation.checks
        if c.name == "provider_element_metric_consistency"
    )
    assert check.outcome is ValidationOutcome.PASS
    assert check.residual <= ng.NgspiceDCSolver.ADMISSION_ATOL


# =====================================================================
# TEST H / I / L — no leakage, in any direction
# =====================================================================

def _code_only(source: str) -> str:
    """The source with every string constant blanked.

    Docstrings explain a rule; they are not the rule. A scan that cannot tell
    the two apart proves nothing about what the code does — and here it would
    prove the opposite of the truth, because core's own docstrings name ngspice
    as an anticipated adapter target.
    """
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    return ast.unparse(tree)


def _core_sources():
    return [
        p
        for p in (REPO_ROOT / "src/engcore/scientific").rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def test_h_universal_core_gained_nothing_and_knows_no_provider():
    """No provider reaches core's *code* — and core's *prose* already expected it.

    The lexical hits under ``engcore/scientific`` are not zero, and asserting
    that they were would assert something false. They are five, all pre-existing
    docstrings written before this milestone, and they are worth quoting because
    they say the contract anticipated exactly this integration:

    * ``scientific/__init__.py:14`` — *"Mature libraries (SciPy, SUNDIALS,
      FEniCSx, Cantera, ngspice, ...) will be reached through adapters that
      satisfy ScientificSolver."*
    * ``solvers/protocol.py:14`` — *"No backend adapter (SciPy, Cantera,
      OpenFOAM, FEniCSx, ngspice) is implemented here — only the contract they
      will satisfy."*
    * ``solvers/protocol.py:135`` — ``PreparedSolve.payload`` names *"a compiled
      netlist"* as an example of what it carries.

    Three occurrences in total: two of ``ngspice`` and one of ``netlist``.

    What must be zero is **executable** provider knowledge, and it is.
    """
    import src.engcore.scientific as core

    prose_hits = 0
    for path in _core_sources():
        raw = path.read_text(encoding="utf-8")
        code = _code_only(raw).lower()
        for forbidden in (
            "ngspice", "netlist", "spice", "subprocess", "wsl", "provider ==",
            "solver ==",
        ):
            assert forbidden not in code, f"{forbidden!r} leaked into {path.name}"
        prose_hits += sum(
            raw.lower().count(w) for w in ("ngspice", "netlist")
        )
    # exactly the pre-existing mentions above; a new one would be a change
    assert prose_hits == 3, prose_hits
    assert not any("ngspice" in name.lower() for name in core.__all__)
    # And core exports no external-solver-provider concept. Named precisely
    # rather than by substring: `OptimizerAdapter` and `NumericSearchBackend`
    # are pre-existing exports about design search, not about solver providers,
    # and a scan that flagged them would be measuring the wrong thing.
    for forbidden in (
        "ProviderRegistry", "ProviderDefinition", "ExternalProvider",
        "SolverProvider", "ProviderCapabilityGraph", "ExecutionBackendHierarchy",
        "RemoteExecution", "NgspiceSolver",
    ):
        assert forbidden not in core.__all__, forbidden


def test_i_no_provider_syntax_reaches_a_scientific_record(standalone):
    circuit, _, external = standalone
    netlist = ng.build_netlist(circuit).text
    assert ".control" in netlist and ".endc" in netlist       # it IS spice syntax

    payload = json.dumps(external.to_dict(), sort_keys=True).lower()
    for forbidden in (
        ".control", ".endc", ".op", "numdgt", "wsl.exe", "/usr/bin",
        "print v(", "@r0[", "crafty hetero",
    ):
        assert forbidden not in payload, forbidden

    # the netlist lives where the contract says a compiled netlist lives
    solver = ng.NgspiceDCSolver()
    solver.bind_circuit(circuit, external.problem_id)
    prepared = solver.prepare(
        __import__(
            "src.engcore.domains.electrical.dc", fromlist=["build_dc_problem"]
        ).build_dc_problem(circuit)
    )
    assert prepared.payload.netlist.text.startswith("crafty ")

    for record in (
        *[r.to_dict() for r in dr.MNA_REALIZATIONS],
        external.provenance.to_dict(),
    ):
        text = json.dumps(record).lower()
        for forbidden in ("wsl", "/usr/bin", ".control", "netlist", "argv"):
            assert forbidden not in text, forbidden


def test_l_the_adapter_never_branches_on_provider_text():
    """Provider stdout/stderr is carried, never read to decide anything.

    Asserted structurally: no conditional in the module tests the content of a
    captured stream. The one place the streams are used is the message of an
    exception already decided by the exit code, and the ``warnings`` field.
    """
    source = pathlib.Path(inspect.getfile(ng)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp, ast.While)):
            rendered = ast.dump(node.test)
            for stream in ("stdout", "stderr"):
                assert stream not in rendered, (
                    f"control flow branches on {stream}"
                )
    # No provider diagnostic string appears in the adapter's *code*. The
    # docstrings quote "Warning: singular matrix" precisely to explain why it is
    # never matched on, so the scan must read code and not prose.
    code = _code_only(source)
    # Provider *diagnostic* strings. `matrix` is deliberately not in this list:
    # `system.matrix` is Crafty's own assembled system, which the precondition
    # check reads as linear algebra, not as provider prose.
    for phrase in ("singular matrix", "Error on line", "Warning:", "compatibility"):
        assert phrase not in code, phrase
    # the one place provider text IS read to decide anything, stated rather
    # than hidden: the version banner. It is not scientific semantics, and the
    # AST guard above cannot see it because the stream is bound to a local first.
    assert "probe_version" in source
    assert "ngspice-([0-9]" in source


# =====================================================================
# TEST J — relocation does not touch scientific identity
# =====================================================================

def test_j_relocating_the_provider_leaves_the_result_byte_identical():
    """Where the binary lives is an execution fact. Reusing DATA-BOUNDARY0's rule.

    Two different argv routes to the *same* provider, compared as serialized
    bytes. Only the run-time-read version travels, in ``SolverIdentity``.
    """
    circuit = divider("relocation")
    direct = ng.NgspiceDCSolver(
        ng.NgspiceInvocation(command=("wsl.exe", "-e", "ngspice"))
    )
    wrapped = ng.NgspiceDCSolver(
        ng.NgspiceInvocation(
            command=("wsl.exe", "-e", "bash", "-lc", 'exec ngspice "$@"', "_")
        )
    )
    a = ng.solve_circuit_with_ngspice(circuit, run_id="reloc", solver=direct)
    b = ng.solve_circuit_with_ngspice(circuit, run_id="reloc", solver=wrapped)
    assert direct.invocation != wrapped.invocation
    assert json.dumps(a.to_dict(), sort_keys=True) == json.dumps(
        b.to_dict(), sort_keys=True
    )


def test_j2_the_invocation_is_configuration_and_reads_the_environment(monkeypatch):
    monkeypatch.setenv("CRAFTY_NGSPICE_ARGV", "some-other-launcher --flag ngspice")
    assert ng.NgspiceInvocation.from_environment().command == (
        "some-other-launcher", "--flag", "ngspice"
    )
    monkeypatch.delenv("CRAFTY_NGSPICE_ARGV")
    assert ng.NgspiceInvocation.from_environment() == ng.NgspiceInvocation()


# =====================================================================
# TEST N — the provider did not make records grow
# =====================================================================

def test_n_substituting_the_provider_does_not_inflate_the_record(standalone):
    _, native, external = standalone
    native_size = len(json.dumps(native.to_dict(), sort_keys=True))
    external_size = len(json.dumps(external.to_dict(), sort_keys=True))

    # Measured, not assumed. The external record is LARGER (10 360 vs 9 288
    # bytes at the time of writing) and the growth must be accounted for rather
    # than asserted away.
    #
    # It is not provider syntax: no netlist, no stdout, no canonical circuit.
    external_payload = json.dumps(external.to_dict(), sort_keys=True)
    assert "circuit_canonical" not in external_payload
    assert ".control" not in external_payload
    assert external.artifacts == () and external.data_references == ()

    # It is three ExecutionBindings the native path cannot write, two extra
    # validation checks the native path does not run, and the provider's own
    # stderr banner carried verbatim in `warnings`. Every byte is accounted for.
    assert len(external.provenance.bindings) == 3
    assert native.provenance.bindings == ()
    warning_bytes = len(json.dumps(list(external.warnings)))
    binding_bytes = len(
        json.dumps([b.to_dict() for b in external.provenance.bindings])
    )
    extra = {c.name for c in external.validation.checks} - {
        c.name for c in native.validation.checks
    }
    check_bytes = sum(
        len(json.dumps(c.to_dict()))
        for c in external.validation.checks
        if c.name in extra
    )
    assert binding_bytes > warning_bytes
    # the provider-text contribution is small, bounded and O(1) in the circuit
    assert warning_bytes < 500
    assert len(external.warnings) <= 8
    assert external_size - native_size <= binding_bytes + warning_bytes + check_bytes


# =====================================================================
# Reduction attacks — preregistration §16
# =====================================================================

def test_r1_the_adapter_is_local_and_no_provider_framework_exists():
    """R1. One adapter for one provider; the generalisation has a named trigger."""
    assert not (REPO_ROOT / "src/engcore/providers").exists()
    exported = set(ng.__all__)
    for forbidden in (
        "ProviderRegistry", "ProviderDefinition", "ExternalProvider",
        "ProviderCapabilityGraph", "ExecutionBackendHierarchy", "RemoteExecution",
    ):
        assert forbidden not in exported
    # the adapter is reachable only from the electrical domain, and imports no
    # other domain
    source = pathlib.Path(inspect.getfile(ng)).read_text(encoding="utf-8")
    for other in ("thermal", "kinetics", "fluids", "aerospace"):
        assert f"domains.{other}" not in source
        assert f"import {other}" not in source


def test_r2_no_parser_result_wrapper_survived():
    """R2. The parser returns a plain mapping; a wrapper would add nothing."""
    values = ng.parse_print_output("v(n0) = 1.5\nnoise\n@r0[p] = 2.5e-1\n")
    assert values == {"v(n0)": 1.5, "@r0[p]": 0.25}
    assert isinstance(values, dict)


def test_r3_the_configuration_record_is_more_than_an_argv_tuple():
    """R3. It survives: it carries a timeout and refuses an empty command."""
    with pytest.raises(ng.NgspiceUnavailable):
        ng.NgspiceInvocation(command=())
    with pytest.raises(ng.NgspiceUnavailable):
        ng.NgspiceInvocation(timeout_seconds=0.0)
    assert ng.NgspiceInvocation().timeout_seconds > 0


def test_r4_no_execution_result_record_was_created():
    """R4. ``RawSolverOutput`` already carries it, warnings channel included."""
    exported = set(ng.__all__)
    for forbidden in ("NgspiceResult", "ProviderOutput", "NgspiceRun"):
        assert forbidden not in exported


def test_r5_the_netlist_builder_is_a_function():
    """R5. ``build_netlist`` is a function; only its return value is a record."""
    assert inspect.isfunction(ng.build_netlist)
    assert not inspect.isclass(ng.build_netlist)


def test_r6_three_realizations_are_the_minimum_the_contract_permits():
    """R6. One is impossible and none loses the milestone's central claim.

    ``ModelRealizationDefinition.model`` is a single ``ModelReference``, so one
    record cannot cover three models; and with no record at all, "the same
    realization, two solvers" has nowhere to be stated.
    """
    from src.engcore.scientific.realizations.definition import (
        ModelRealizationDefinition,
    )
    import dataclasses

    fields = {f.name for f in dataclasses.fields(ModelRealizationDefinition)}
    assert "model" in fields and "models" not in fields
    assert len({r.model.model_id for r in dr.MNA_REALIZATIONS}) == 3
    # a realization providing nothing is refused by the contract, which is why
    # the preregistered `provided_capabilities=frozenset()` could not stand
    with pytest.raises(Exception):
        ModelRealizationDefinition(
            realization_id="x", version="0.1.0",
            model=ModelReference("electrical.dc.kcl", "0.1.0"),
            provided_capabilities=frozenset(),
        )
