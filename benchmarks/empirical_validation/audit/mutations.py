"""EV-19: seven mutations of the PROBLEM CONSTRUCTION, not of the solver.

The previous round planted defects in the physics. These are different: the
physics is left alone and the statement of the problem is corrupted on one
branch only. If the comparison cannot see that, then agreement between the two
branches was never evidence that the Core received the right problem, which is
exactly the blindness this round exists to test for.

Five of the seven are expected to be caught. Two are expected NOT to be, and
their non-detection is the finding rather than a failure of the harness:

  IPM-6  a derived quantity pre-computed once in the fixture and consumed by
         both branches. Nothing can see a fault in a number neither branch
         computed.
  IPM-7  the external solver's problem generated from the Core's own
         declaration. ngspice then reproduces the Core's mistake faithfully and
         reports agreement.

IPM-7 is the one the round description calls out as especially important, and
it is the reason reference/spice.py reads the raw fixture and refuses to accept
an engcore object.
"""

from __future__ import annotations

import copy

from adapters import adapter_a as A
from adapters import adapter_b as B
from reference import nodal, physics, spice

from . import construction
from .loader import fixture


def _detected(construction_rows, disagreements) -> bool:
    altered = any(
        row["classification"] in ("ALTERED", "LOST", "AMBIGUOUS")
        for row in construction_rows
    )
    return altered or bool(disagreements)


def _relative(a: float, b: float) -> float:
    return abs(a - b) / abs(b) if b != 0.0 else abs(a - b)


# ---------------------------------------------------------------------------
# IPM-1: a unit scale error on one branch only
# ---------------------------------------------------------------------------


def ipm_1() -> dict:
    raw = fixture("battery_cell")
    # Branch A is handed the capacity in amp-hours while the field still says
    # milliamp-hours: the classic "2.6 not 2600" paste.
    core = A.battery(raw, nominal_capacity_mAh=2.6)
    reference = B.battery(raw)
    rows = construction.compare("ipm-1", core["received"], reference)
    computed = physics.battery(reference)
    disagreements = [
        name
        for name, core_value, reference_value in (
            (
                "final_state_of_charge",
                core["final_state_of_charge"],
                computed["final_state_of_charge"],
            ),
            (
                "terminal_voltage",
                core["terminal_voltage_v"],
                computed["terminal_voltage_v"],
            ),
        )
        if _relative(core_value, reference_value) > 1e-12
    ]
    return _record(
        "IPM-1",
        "unit scale error: capacity given in Ah through a field declared in mAh",
        rows,
        disagreements,
        expected_detected=True,
    )


# ---------------------------------------------------------------------------
# IPM-2: a temperature SCALE confusion on one branch only
# ---------------------------------------------------------------------------


def ipm_2() -> dict:
    raw = fixture("lumped_body")
    # An absolute temperature pasted into a field declared on the Celsius
    # scale. The number is plausible; the scale is not.
    core = A.lumped(raw, initial_degC=358.15)
    reference = B.lumped(raw)
    rows = construction.compare("ipm-2", core["received"], reference)
    closed = physics.lumped_closed_form(reference)
    disagreements = (
        ["final_temperature"]
        if _relative(core["final_temperature_k"], closed["final_temperature_k"]) > 1e-9
        else []
    )
    return _record(
        "IPM-2",
        "temperature scale confusion: a kelvin value placed in a degC field",
        rows,
        disagreements,
        expected_detected=True,
    )


# ---------------------------------------------------------------------------
# IPM-3: a geometry error inside a derived quantity
# ---------------------------------------------------------------------------


def ipm_3() -> dict:
    raw = fixture("conductor")
    # The wire length read in metres through a field declared in millimetres.
    core = A.conductor(raw, length_mm=2.5)
    reference = B.conductor(raw)
    rows = construction.compare("ipm-3", core["received"], reference)
    expected = physics.linear_tcr(reference, reference["operating_temperature_k"])
    disagreements = (
        ["resistance"] if _relative(core["resistance_ohm"], expected) > 1e-12 else []
    )
    return _record(
        "IPM-3",
        "geometry error in a derived quantity: R_ref = rho L / A built from a "
        "length a thousand times too small",
        rows,
        disagreements,
        expected_detected=True,
    )


# ---------------------------------------------------------------------------
# IPM-4: a sign convention inverted on one branch only
# ---------------------------------------------------------------------------


def ipm_4() -> dict:
    raw_file = fixture("circuits")
    raw = next(c for c in raw_file["circuits"] if c["circuit_id"] == "current_injection")
    mutated = copy.deepcopy(raw)
    source = mutated["current_sources"][0]
    source["from_node"], source["to_node"] = source["to_node"], source["from_node"]

    core = A.circuit(raw)  # the honest circuit
    reference_problem = B.circuit(mutated)  # the inverted one
    hand = nodal.solve(reference_problem)
    disagreements = [
        node
        for node, value in hand["node_voltages_v"].items()
        if _relative(core["values"][f"node_voltage:{node}"], value) > 1e-9
    ]
    return _record(
        "IPM-4",
        "sign convention inversion: the current source's direction reversed on "
        "the reference branch",
        [],
        disagreements,
        expected_detected=True,
    )


# ---------------------------------------------------------------------------
# IPM-5: the reference node misassigned on one branch only
# ---------------------------------------------------------------------------


def ipm_5() -> dict:
    raw_file = fixture("circuits")
    raw = next(c for c in raw_file["circuits"] if c["circuit_id"] == "floating_reference")
    mutated = copy.deepcopy(raw)
    # The mistake a route makes when it assumes the first node listed is ground.
    mutated["reference_node"] = mutated["nodes"][0]

    core = A.circuit(raw)
    reference_problem = B.circuit(mutated)
    hand = nodal.solve(reference_problem)
    disagreements = [
        node
        for node, value in hand["node_voltages_v"].items()
        if _relative(core["values"][f"node_voltage:{node}"], value) > 1e-9
    ]
    return _record(
        "IPM-5",
        "reference node misassignment: the reference taken as the first node "
        "listed rather than the one declared",
        [],
        disagreements,
        expected_detected=True,
    )


# ---------------------------------------------------------------------------
# IPM-6: the blindness itself -- one pre-computed number, both branches
# ---------------------------------------------------------------------------


def ipm_6() -> dict:
    """A derived quantity computed once, wrongly, and handed to both branches.

    The lumped body's conductance is computed here as h * A with the area read
    in square metres when it is stated in square centimetres -- a factor of
    10000. Both branches then consume the same wrong hA, so both produce the
    same wrong answer and every comparison passes.

    That is not a harness failure. It is the reason the fixtures in this round
    carry a film coefficient and an area rather than a conductance, and the
    reason the derivation is written out twice. The demonstration is here so
    the claim is evidenced rather than asserted.
    """
    raw = fixture("lumped_body")
    quantities = raw["quantities"]
    wrong_conductance = (
        quantities["convection_coefficient_W_per_m2_K"] * quantities["surface_area_cm2"]
    )  # the cm2 -> m2 factor omitted, once, for both

    from engcore.scientific.units.quantity import Quantity as Q
    from engcore.domains.thermal_models.lumped import (
        LumpedThermalSolver,
        ThermalBody,
        build_lumped_thermal_problem,
    )

    body = ThermalBody(
        body_id="IPM6",
        heat_capacity=Q(224.0, "joule / kelvin"),
        ambient_conductance=Q(wrong_conductance, "watt / kelvin"),
        ambient_temperature=Q(quantities["ambient_degC"], "degC"),
        initial_temperature=Q(quantities["initial_degC"], "degC"),
        duration=Q(quantities["duration_min"], "minute"),
    )
    problem = build_lumped_thermal_problem(body)
    solver = LumpedThermalSolver()
    solver.bind_body(
        body, problem.problem_id, heat_input=Q(quantities["heat_input_mW"], "milliwatt")
    )
    prepared = solver.prepare(problem)
    metrics = solver.extract_metrics(prepared, solver.solve(prepared))
    core_final = metrics["final_temperature"].magnitude_in("kelvin")

    shared_problem = {
        "heat_capacity_j_per_k": 224.0,
        "ambient_conductance_w_per_k": wrong_conductance,
        "ambient_temperature_k": quantities["ambient_degC"] + 273.15,
        "initial_temperature_k": quantities["initial_degC"] + 273.15,
        "heat_input_w": quantities["heat_input_mW"] * 1e-3,
        "duration_s": quantities["duration_min"] * 60.0,
    }
    reference_final = physics.lumped_closed_form(shared_problem)["final_temperature_k"]

    honest = B.lumped(raw)
    honest_final = physics.lumped_closed_form(honest)["final_temperature_k"]
    disagreements = (
        ["final_temperature"] if _relative(core_final, reference_final) > 1e-9 else []
    )
    record = _record(
        "IPM-6",
        "shared pre-computation: hA derived once, wrongly, and consumed by both "
        "branches",
        [],
        disagreements,
        expected_detected=False,
    )
    record["what_the_two_branches_agreed_on_k"] = core_final
    record["what_the_physics_actually_gives_k"] = honest_final
    record["size_of_the_undetected_error_k"] = abs(core_final - honest_final)
    record["why_this_matters"] = (
        "The two branches agreed to round-off about a body whose conductance "
        "was wrong by a factor of 10000. Agreement between two solvers is a "
        "statement about the solvers, not about the problem, whenever a number "
        "reaches both of them already derived."
    )
    return record


# ---------------------------------------------------------------------------
# IPM-7: the external solver's problem generated from the Core's declaration
# ---------------------------------------------------------------------------


def ipm_7() -> dict:
    """ngspice fed a netlist built from the engcore circuit rather than the fixture.

    The fixture states resistances in kilohms. The mutated construction reads
    them as ohms -- a thousandfold fault in the problem, not in the solver. Two
    netlists are then produced for the same mutated circuit:

      * one from the raw fixture, which still says kilohms;
      * one from the engcore declaration, which now says ohms.

    Against the first, ngspice disagrees with the Core and the fault is visible.
    Against the second, ngspice reproduces the Core exactly and reports
    agreement. Same simulator, same circuit, opposite conclusions -- decided
    entirely by where the problem statement came from.
    """
    raw_file = fixture("circuits")
    # A current-driven network, deliberately: in a pure resistive divider every
    # node voltage depends only on the RATIO of the resistances, so scaling
    # them all by a thousand changes nothing and the mutation would be
    # undetectable by either netlist. Here the node voltages are I R and the
    # scale is visible -- which is what makes the two netlists disagree with
    # each other.
    raw = next(
        c for c in raw_file["circuits"] if c["circuit_id"] == "current_injection"
    )

    from engcore.scientific.units.quantity import Quantity as Q
    from engcore.domains.electrical.dc.circuit import DCCircuit
    from engcore.domains.electrical.dc.components import (
        DCCurrentSource,
        DCVoltageSource,
        ElectricalNode,
        Resistor,
    )
    from engcore.domains.electrical.dc.solver import solve_circuit

    reference_node = raw["reference_node"]
    mutated_circuit = DCCircuit(
        circuit_id="ipm7",
        nodes=tuple(
            ElectricalNode(node_id=n, is_reference=(n == reference_node))
            for n in raw["nodes"]
        ),
        resistors=tuple(
            # THE FAULT: the fixture's kilohms read as ohms.
            Resistor(
                component_id=r["id"],
                node_a=r["node_a"],
                node_b=r["node_b"],
                resistance=Q(r["resistance_kohm"], "ohm"),
            )
            for r in raw["resistors"]
        ),
        voltage_sources=tuple(
            DCVoltageSource(
                component_id=s["id"],
                positive_node=s["positive_node"],
                negative_node=s["negative_node"],
                voltage=Q(s["voltage_mV"], "millivolt"),
            )
            for s in raw["voltage_sources"]
        ),
        current_sources=tuple(
            DCCurrentSource(
                component_id=s["id"],
                from_node=s["from_node"],
                to_node=s["to_node"],
                current=Q(s["current_mA"], "milliampere"),
            )
            for s in raw["current_sources"]
        ),
    )
    result = solve_circuit(mutated_circuit, run_id="ipm7")
    core_values = {
        key: value.magnitude_in(value.units) for key, value in result.values.items()
    }

    honest_netlist_run = spice.run(raw)

    # The netlist this round forbids: emitted from the engcore object.
    derived_lines = [f"* ipm7 -- emitted from the engcore declaration"]
    for resistor in mutated_circuit.resistors:
        derived_lines.append(
            f"R{resistor.component_id} "
            f"{'0' if resistor.node_a == reference_node else resistor.node_a} "
            f"{'0' if resistor.node_b == reference_node else resistor.node_b} "
            f"{resistor.resistance.magnitude_in('ohm')!r}"
        )
    for source in mutated_circuit.voltage_sources:
        derived_lines.append(
            f"V{source.component_id} "
            f"{'0' if source.positive_node == reference_node else source.positive_node} "
            f"{'0' if source.negative_node == reference_node else source.negative_node} "
            f"DC {source.voltage.magnitude_in('volt')!r}"
        )
    for source in mutated_circuit.current_sources:
        derived_lines.append(
            f"I{source.component_id} "
            f"{'0' if source.from_node == reference_node else source.from_node} "
            f"{'0' if source.to_node == reference_node else source.to_node} "
            f"DC {source.current.magnitude_in('ampere')!r}"
        )
    unknown = [n for n in raw["nodes"] if n != reference_node]
    derived_lines += [
        ".control",
        "op",
        "print " + " ".join(f"v({n})" for n in unknown),
        ".endc",
        ".end",
        "",
    ]
    derived_netlist = "\n".join(derived_lines)

    import subprocess

    # stdin, and `spice.ARGV`, for the reason `spice.run` uses them: the
    # provider may live in another filesystem namespace (here it is reached as
    # `wsl.exe ngspice`), where a temp-file path written by this process is not
    # resolvable. The netlist built above is unchanged.
    if spice.ARGV is None:
        raise RuntimeError(
            "IPM-7 needs the ngspice provider and it is not reachable on this "
            "host; the mutation cannot be run, which is an execution fact"
        )
    completed = subprocess.run(
        [*spice.ARGV, "-b"],
        input=derived_netlist,
        capture_output=True,
        text=True,
        timeout=120,
    )
    derived_voltages = {}
    for line in completed.stdout.splitlines():
        match = spice._VALUE.match(line)
        if match and match.group(1).lower().startswith("v("):
            derived_voltages[match.group(1)[2:-1]] = float(match.group(2))

    node = "n2"
    against_fixture = _relative(
        core_values[f"node_voltage:{node}"], honest_netlist_run["node_voltages_v"][node]
    )
    against_derived = _relative(
        core_values[f"node_voltage:{node}"], derived_voltages[node]
    )
    record = _record(
        "IPM-7",
        "the external solver's netlist generated from the Core's own "
        "declaration instead of the raw fixture",
        [],
        [],
        expected_detected=False,
    )
    record |= {
        "core_node_voltage_v": core_values[f"node_voltage:{node}"],
        "ngspice_from_raw_fixture_v": honest_netlist_run["node_voltages_v"][node],
        "ngspice_from_engcore_declaration_v": derived_voltages[node],
        "relative_difference_against_the_fixture_netlist": against_fixture,
        "relative_difference_against_the_derived_netlist": against_derived,
        "detected_by_the_fixture_netlist": against_fixture > 2e-6,
        "detected_by_the_derived_netlist": against_derived > 2e-6,
        "why_this_matters": (
            "The same simulator, on the same circuit, reaches opposite "
            "conclusions depending only on where its problem came from. A "
            "netlist generated from the Core's declaration inherits the Core's "
            "construction faults and can only ever confirm them, which is why "
            "reference/spice.py reads the fixture and never an engcore object."
        ),
    }
    record["detected"] = record["detected_by_the_derived_netlist"]
    record["verdict"] = (
        "BLIND_AS_EXPECTED"
        if not record["detected_by_the_derived_netlist"]
        and record["detected_by_the_fixture_netlist"]
        else "UNEXPECTED"
    )
    return record


def _record(identifier, description, rows, disagreements, *, expected_detected) -> dict:
    detected = _detected(rows, disagreements)
    return {
        "id": identifier,
        "mutation": description,
        "expected_detected": expected_detected,
        "detected": detected,
        "altered_construction_fields": [
            row["field"]
            for row in rows
            if row["classification"] in ("ALTERED", "LOST", "AMBIGUOUS")
        ],
        "disagreeing_quantities": disagreements,
        "verdict": (
            "DETECTED"
            if detected and expected_detected
            else "BLIND_AS_EXPECTED"
            if not detected and not expected_detected
            else "UNEXPECTED"
        ),
    }


MUTATIONS = [ipm_1, ipm_2, ipm_3, ipm_4, ipm_5, ipm_6, ipm_7]


def run_all() -> list[dict]:
    return [mutation() for mutation in MUTATIONS]
