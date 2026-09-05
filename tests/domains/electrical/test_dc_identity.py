"""Problem <-> circuit identity, topology provenance and active model sets.

The property under test: a ScientificResult, the circuit that was solved, the
recorded provenance and the active scientific models must all refer to the
same physical system — and any disagreement must be refused before a single
number is computed.
"""

from __future__ import annotations

import json
import sys

from src.engcore.domains.electrical.dc import (
    CircuitBindingError,
    DCCircuit,
    DCCurrentSource,
    DCValidationSettings,
    DCVoltageSource,
    ElectricalDCError,
    ElectricalDCSolver,
    ElectricalNode,
    Resistor,
    assumptions_for_models,
    build_dc_problem,
    models_for_circuit,
    problem_fingerprint,
    solve_circuit,
    verify_problem_matches_circuit,
)
from src.engcore.scientific import Quantity, ScientificProblem

GND = ElectricalNode("gnd", is_reference=True)


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


def _circuit(
    *,
    r1=Quantity(1.0, "kohm"),
    r2=Quantity(3.0, "kohm"),
    v1=Quantity(12.0, "volt"),
    r2_nodes=("mid", "gnd"),
    circuit_id="divider",
) -> DCCircuit:
    return DCCircuit(
        circuit_id=circuit_id,
        nodes=(GND, ElectricalNode("top"), ElectricalNode("mid")),
        resistors=(
            Resistor("R1", "top", "mid", r1),
            Resistor("R2", r2_nodes[0], r2_nodes[1], r2),
        ),
        voltage_sources=(DCVoltageSource("V1", "top", "gnd", v1),),
    )


# =====================================================================
# Fingerprint behaviour
# =====================================================================

def test_fingerprint_is_deterministic_and_hex_sha256():
    circuit = _circuit()
    first, second = circuit.fingerprint(), circuit.fingerprint()
    assert first == second
    assert len(first) == 64 and int(first, 16) >= 0


def test_fingerprint_is_independent_of_insertion_order():
    """CASE E: same physics, different declaration order -> same identity."""
    ordered = _circuit()
    shuffled = DCCircuit(
        circuit_id="divider",
        nodes=(ElectricalNode("mid"), ElectricalNode("top"), GND),
        resistors=tuple(reversed(ordered.resistors)),
        voltage_sources=ordered.voltage_sources,
    )
    assert shuffled.fingerprint() == ordered.fingerprint()
    assert shuffled.canonical_dict() == ordered.canonical_dict()


def test_fingerprint_is_unit_normalised():
    """1 kohm and 1000 ohm are the same physical resistance, so a cosmetic
    unit choice must not create a different scientific identity."""
    a = _circuit(r1=Quantity(1.0, "kohm"))
    b = _circuit(r1=Quantity(1000.0, "ohm"))
    assert a.fingerprint() == b.fingerprint()

    c = _circuit(v1=Quantity(0.5, "volt"))
    d = _circuit(v1=Quantity(500.0, "millivolt"))
    assert c.fingerprint() == d.fingerprint()


def test_fingerprint_ignores_labels_but_tracks_physics():
    """A renamed circuit is the same physical system; a rewired one is not."""
    named = _circuit(circuit_id="divider")
    renamed = _circuit(circuit_id="totally_different_name")
    assert named.fingerprint() == renamed.fingerprint()


def test_fingerprint_detects_a_changed_element_value():
    """CASE A: same topology, different resistor value."""
    assert _circuit(r1=Quantity(1.0, "kohm")).fingerprint() != (
        _circuit(r1=Quantity(5.0, "kohm")).fingerprint()
    )


def test_fingerprint_detects_a_changed_source_voltage():
    """CASE B: same topology, different source voltage."""
    assert _circuit(v1=Quantity(12.0, "volt")).fingerprint() != (
        _circuit(v1=Quantity(9.0, "volt")).fingerprint()
    )


def test_fingerprint_detects_changed_connectivity():
    """CASE D: identical component ids and values, different wiring."""
    wired = _circuit(r2_nodes=("mid", "gnd"))
    rewired = _circuit(r2_nodes=("top", "gnd"))
    assert wired.fingerprint() != rewired.fingerprint()


def test_fingerprint_detects_current_source_direction():
    """CASE C: reversing a current source reverses the physics."""
    def build(from_node, to_node):
        return DCCircuit(
            circuit_id="c",
            nodes=(GND, ElectricalNode("n1")),
            resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
            current_sources=(
                DCCurrentSource("I1", from_node, to_node, Quantity(1.0, "milliampere")),
            ),
        )

    assert build("gnd", "n1").fingerprint() != build("n1", "gnd").fingerprint()


def test_fingerprint_detects_swapped_resistor_terminals():
    """Terminal order is preserved, never sorted: swapping it flips the sign
    of the reported resistor metrics, so it is a different measurement
    convention."""
    def build(a, b):
        return DCCircuit(
            circuit_id="c",
            nodes=(GND, ElectricalNode("n1")),
            resistors=(Resistor("R1", a, b, Quantity(1.0, "kohm")),),
        )

    assert build("n1", "gnd").fingerprint() != build("gnd", "n1").fingerprint()


def test_fingerprint_detects_a_changed_reference_node():
    def build(reference):
        return DCCircuit(
            circuit_id="c",
            nodes=tuple(
                ElectricalNode(n, is_reference=(n == reference))
                for n in ("gnd", "n1")
            ),
            resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        )

    assert build("gnd").fingerprint() != build("n1").fingerprint()


def test_canonical_dict_is_json_serialisable_and_stable():
    canonical = _circuit().canonical_dict()
    assert json.loads(json.dumps(canonical, sort_keys=True)) == canonical
    assert canonical["resistors"][0]["resistance_ohm"] == 1000.0   # normalised
    assert "circuit_id" not in canonical and "description" not in canonical


# =====================================================================
# Problem <-> circuit verification
# =====================================================================

def test_problem_records_the_fingerprint_of_its_circuit():
    circuit = _circuit()
    problem = build_dc_problem(circuit)
    assert problem_fingerprint(problem) == circuit.fingerprint()
    verify_problem_matches_circuit(problem, circuit)      # no raise


def test_verification_rejects_a_different_resistor_value():
    problem = build_dc_problem(_circuit(r1=Quantity(1.0, "kohm")))
    _raises(
        CircuitBindingError, verify_problem_matches_circuit,
        problem, _circuit(r1=Quantity(5.0, "kohm")),
    )


def test_verification_rejects_different_connectivity():
    problem = build_dc_problem(_circuit(r2_nodes=("mid", "gnd")))
    _raises(
        CircuitBindingError, verify_problem_matches_circuit,
        problem, _circuit(r2_nodes=("top", "gnd")),
    )


def test_verification_accepts_a_reordered_but_identical_circuit():
    ordered = _circuit()
    problem = build_dc_problem(ordered)
    shuffled = DCCircuit(
        circuit_id=ordered.circuit_id,
        nodes=tuple(reversed(ordered.nodes)),
        resistors=tuple(reversed(ordered.resistors)),
        voltage_sources=ordered.voltage_sources,
    )
    verify_problem_matches_circuit(problem, shuffled)     # no raise


def test_verification_rejects_a_foreign_problem():
    foreign = ScientificProblem(problem_id="not_a_circuit")
    _raises(
        CircuitBindingError, verify_problem_matches_circuit, foreign, _circuit()
    )


def test_binding_error_names_the_problem_and_short_digests_only():
    problem = build_dc_problem(_circuit(r1=Quantity(1.0, "kohm")))
    other = _circuit(r1=Quantity(5.0, "kohm"))
    try:
        verify_problem_matches_circuit(problem, other)
        raise AssertionError("expected CircuitBindingError")
    except CircuitBindingError as exc:
        message = str(exc)
        assert problem.problem_id in message
        assert problem_fingerprint(problem)[:12] in message
        assert other.fingerprint()[:12] in message
        # no serialized circuit dumped into the traceback
        assert "resistance_ohm" not in message and len(message) < 400


# =====================================================================
# Solver-level enforcement
# =====================================================================

def test_solve_circuit_rejects_a_mismatched_problem_before_solving():
    circuit = _circuit(r1=Quantity(5.0, "kohm"))
    problem = build_dc_problem(_circuit(r1=Quantity(1.0, "kohm")))
    _raises(
        CircuitBindingError, solve_circuit, circuit,
        run_id="mismatch", problem=problem,
    )


def test_prepare_rejects_a_mismatched_bound_circuit():
    """Bypassing solve_circuit must not bypass the integrity gate."""
    problem = build_dc_problem(_circuit(r1=Quantity(1.0, "kohm")))
    solver = ElectricalDCSolver()
    # Bind a different physical system directly under the same problem id.
    solver._circuits[problem.problem_id] = _circuit(r1=Quantity(5.0, "kohm"))
    _raises(CircuitBindingError, solver.prepare, problem)


def test_rebinding_is_idempotent_for_the_same_circuit():
    circuit = _circuit()
    problem = build_dc_problem(circuit)
    solver = ElectricalDCSolver()
    solver.bind_circuit(circuit, problem.problem_id)
    solver.bind_circuit(circuit, problem.problem_id)             # same system
    reordered = DCCircuit(
        circuit_id=circuit.circuit_id,
        nodes=tuple(reversed(circuit.nodes)),
        resistors=tuple(reversed(circuit.resistors)),
        voltage_sources=circuit.voltage_sources,
    )
    solver.bind_circuit(reordered, problem.problem_id)           # still same
    assert solver.bound_circuit(problem.problem_id).fingerprint() == (
        circuit.fingerprint()
    )


def test_rebinding_a_different_circuit_is_refused():
    problem = build_dc_problem(_circuit())
    solver = ElectricalDCSolver()
    solver.bind_circuit(_circuit(), problem.problem_id)
    _raises(
        CircuitBindingError, solver.bind_circuit,
        _circuit(r1=Quantity(5.0, "kohm")), problem.problem_id,
    )


# =====================================================================
# Topology provenance
# =====================================================================

def test_provenance_identifies_the_exact_topology():
    circuit = _circuit()
    result = solve_circuit(circuit, run_id="prov-1")
    provenance = result.provenance
    assert provenance.metadata["circuit_fingerprint"] == circuit.fingerprint()
    canonical = provenance.metadata["circuit_canonical"]
    assert canonical == circuit.canonical_dict()
    # the record is complete enough to reconstruct what was solved
    assert canonical["reference_node"] == "gnd"
    assert {r["component_id"] for r in canonical["resistors"]} == {"R1", "R2"}
    assert result.metadata["circuit_fingerprint"] == circuit.fingerprint()


def test_same_values_different_wiring_produce_different_provenance_identity():
    """Mandatory reproducibility test: element values alone do not identify a
    circuit, so provenance must distinguish two differently wired systems."""
    wired = solve_circuit(_circuit(r2_nodes=("mid", "gnd")), run_id="wired")
    rewired = solve_circuit(_circuit(r2_nodes=("top", "gnd")), run_id="rewired")

    assert (
        wired.provenance.metadata["circuit_fingerprint"]
        != rewired.provenance.metadata["circuit_fingerprint"]
    )
    assert (
        wired.provenance.metadata["circuit_canonical"]
        != rewired.provenance.metadata["circuit_canonical"]
    )
    # the recorded element values are identical, which is exactly why the
    # topology record is necessary
    assert wired.provenance.inputs == rewired.provenance.inputs


def test_provenance_round_trips_with_nested_topology():
    from src.engcore.scientific import ProvenanceRecord

    result = solve_circuit(_circuit(), run_id="prov-rt")
    payload = result.provenance.to_dict()
    restored = ProvenanceRecord.from_dict(json.loads(json.dumps(payload)))
    assert restored.metadata["circuit_canonical"] == (
        result.provenance.metadata["circuit_canonical"]
    )


# =====================================================================
# Active model selection
# =====================================================================

def _ids(models):
    return {m.model_id for m in models}


def test_resistor_only_circuit_activates_kcl_and_resistor_models():
    circuit = DCCircuit(
        circuit_id="r_only",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
    )
    assert _ids(models_for_circuit(circuit)) == {
        "electrical.dc.kcl", "electrical.dc.resistor_ohm",
    }


def test_current_source_circuit_activates_the_current_source_model():
    circuit = DCCircuit(
        circuit_id="i_src",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        current_sources=(
            DCCurrentSource("I1", "gnd", "n1", Quantity(1.0, "milliampere")),
        ),
    )
    assert _ids(models_for_circuit(circuit)) == {
        "electrical.dc.kcl",
        "electrical.dc.resistor_ohm",
        "electrical.dc.ideal_current_source",
    }
    assert "electrical.dc.ideal_voltage_source" not in _ids(
        models_for_circuit(circuit)
    )


def test_mixed_circuit_activates_only_present_component_models():
    circuit = DCCircuit(
        circuit_id="mixed",
        nodes=(GND, ElectricalNode("n1"), ElectricalNode("n2")),
        resistors=(
            Resistor("R1", "n1", "n2", Quantity(1.0, "kohm")),
            Resistor("R2", "n2", "gnd", Quantity(1.0, "kohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V1", "n1", "gnd", Quantity(10.0, "volt")),
        ),
        current_sources=(
            DCCurrentSource("I1", "gnd", "n2", Quantity(1.0, "milliampere")),
        ),
    )
    assert _ids(models_for_circuit(circuit)) == {
        "electrical.dc.kcl",
        "electrical.dc.resistor_ohm",
        "electrical.dc.ideal_voltage_source",
        "electrical.dc.ideal_current_source",
    }


def test_kcl_is_always_active():
    circuit = DCCircuit(
        circuit_id="bare",
        nodes=(GND, ElectricalNode("n1")),
        current_sources=(
            DCCurrentSource("I1", "gnd", "n1", Quantity(1.0, "milliampere")),
        ),
    )
    assert "electrical.dc.kcl" in _ids(models_for_circuit(circuit))


def test_model_sets_agree_across_problem_result_and_provenance():
    circuit = DCCircuit(
        circuit_id="agreement",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        current_sources=(
            DCCurrentSource("I1", "gnd", "n1", Quantity(2.0, "milliampere")),
        ),
    )
    problem = build_dc_problem(circuit)
    result = solve_circuit(circuit, run_id="agree", problem=problem)

    expected = {(m.model_id, m.version) for m in models_for_circuit(circuit)}
    assert {(m.model_id, m.version) for m in problem.models} == expected
    assert set(result.models) == expected
    assert set(result.provenance.models) == expected
    assert "electrical.dc.ideal_voltage_source" not in {
        model_id for model_id, _ in result.models
    }


def test_assumptions_are_the_deterministic_union_of_active_models():
    circuit = DCCircuit(
        circuit_id="assumptions",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        current_sources=(
            DCCurrentSource("I1", "gnd", "n1", Quantity(1.0, "milliampere")),
        ),
    )
    result = solve_circuit(circuit, run_id="assume")
    expected = assumptions_for_models(models_for_circuit(circuit))

    assert result.assumptions == expected
    assert result.provenance.assumptions == expected
    assert len(set(expected)) == len(expected)            # de-duplicated
    # current-source specific assumptions are present, voltage-source ones not
    assert "infinite output impedance" in expected
    assert "zero internal impedance" not in expected
    # deterministic across repeated construction
    assert assumptions_for_models(models_for_circuit(circuit)) == expected


# =====================================================================
# Validation settings hardening
# =====================================================================

def test_validation_settings_reject_invalid_tolerances():
    for bad in (-1e-9, float("nan"), float("inf"), float("-inf")):
        _raises(ElectricalDCError, DCValidationSettings, residual_atol=bad)
        _raises(ElectricalDCError, DCValidationSettings, kcl_atol_ampere=bad)
        _raises(ElectricalDCError, DCValidationSettings, residual_rtol=bad)


def test_validation_settings_accept_zero_and_positive():
    exact = DCValidationSettings(
        residual_atol=0.0, residual_rtol=0.0, kcl_atol_ampere=0.0,
        ohm_atol_volt=0.0, source_atol_volt=0.0, power_atol_watt=0.0,
    )
    assert all(v == 0.0 for v in exact.as_mapping().values())
    assert DCValidationSettings(kcl_atol_ampere=1e-6).kcl_atol_ampere == 1e-6


def test_resistor_check_is_named_for_what_it_proves():
    result = solve_circuit(_circuit(), run_id="naming")
    names = {c.name for c in result.validation.checks}
    assert "resistor_metric_consistency" in names
    assert "resistor_constitutive_relation" not in names
    check = {c.name: c for c in result.validation.checks}[
        "resistor_metric_consistency"
    ]
    assert "not independent" in check.detail


def _all_tests():
    module = sys.modules[__name__]
    return [
        (n, getattr(module, n))
        for n in sorted(dir(module))
        if n.startswith("test_") and callable(getattr(module, n))
    ]


def main() -> int:
    failures = 0
    for name, test in _all_tests():
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    total = len(_all_tests())
    print(f"dc identity: {'FAIL' if failures else 'PASS'} "
          f"({total - failures}/{total})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
