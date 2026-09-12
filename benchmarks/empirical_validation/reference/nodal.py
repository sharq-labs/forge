"""Modified nodal analysis assembled here, solved by the elimination in linalg.

THE FORMULATION, derived rather than copied.

Kirchhoff's current law at every non-reference node says the currents leaving
it sum to zero. A resistor between nodes p and q carries (v_p - v_q)/R from p
to q, which contributes +1/R to the (p,p) and (q,q) entries and -1/R to the
(p,q) and (q,p) entries of the conductance matrix G. A current source carries a
known current inside itself from its `from` node to its `to` node, so it removes
that current from the `from` node's balance and adds it to the `to` node's; it
appears on the right-hand side only.

An ideal voltage source has no conductance to contribute and cannot be written
in terms of node voltages, so its branch current is carried as an extra unknown.
For source m between p (positive) and n (negative) the unknown i_m leaves p and
enters n, and one extra row states v_p - v_n = V_m. That is the standard
"modified" part of modified nodal analysis and it is what makes an ideal source
exact rather than a small resistance pretending to be one.

    [ G   B ] [ v ]   [ i_inj ]
    [ B^T 0 ] [ i ] = [ v_src ]

WHAT IS AND IS NOT INDEPENDENT HERE. The Core also solves DC circuits by
modified nodal analysis, and so does ngspice; it is the formulation the field
uses. What is independent is everything below the formulation: this file
assembles its own matrix from the raw fixture, orders its own unknowns, and is
solved by a hand-written elimination rather than by LAPACK. The problem
statement is built from the fixture and never from an engcore circuit object.
That is recorded honestly in INDEPENDENCE_GRAPH.json rather than claimed to be
more than it is.
"""

from __future__ import annotations

from .linalg import condition_number, lu_solve, residual_infinity_norm


def solve(problem: dict) -> dict:
    """Solve one SI problem dict as produced by adapter B.

    Expects ``nodes``, ``reference_node``, ``resistors`` (id, node_a, node_b,
    resistance_ohm), ``voltage_sources`` (id, positive_node, negative_node,
    voltage_v) and ``current_sources`` (id, from_node, to_node, current_a).
    """
    reference = problem["reference_node"]
    unknown_nodes = [n for n in problem["nodes"] if n != reference]
    index = {name: i for i, name in enumerate(unknown_nodes)}
    n_nodes = len(unknown_nodes)
    sources = list(problem["voltage_sources"])
    size = n_nodes + len(sources)

    matrix = [[0.0] * size for _ in range(size)]
    rhs = [0.0] * size

    for resistor in problem["resistors"]:
        conductance = 1.0 / resistor["resistance_ohm"]
        a = index.get(resistor["node_a"])
        b = index.get(resistor["node_b"])
        if a is not None:
            matrix[a][a] += conductance
        if b is not None:
            matrix[b][b] += conductance
        if a is not None and b is not None:
            matrix[a][b] -= conductance
            matrix[b][a] -= conductance

    for source in problem["current_sources"]:
        current = source["current_a"]
        # Inside the source the current runs from -> to, so it is drawn out of
        # the `from` node and pushed into the `to` node.
        f = index.get(source["from_node"])
        t = index.get(source["to_node"])
        if f is not None:
            rhs[f] -= current
        if t is not None:
            rhs[t] += current

    for m, source in enumerate(sources):
        row = n_nodes + m
        p = index.get(source["positive_node"])
        q = index.get(source["negative_node"])
        if p is not None:
            matrix[p][row] += 1.0
            matrix[row][p] += 1.0
        if q is not None:
            matrix[q][row] -= 1.0
            matrix[row][q] -= 1.0
        rhs[row] = source["voltage_v"]

    solution = lu_solve(matrix, rhs)
    voltages = {reference: 0.0}
    for name, i in index.items():
        voltages[name] = solution[i]
    branch_currents = {
        source["id"]: solution[n_nodes + m] for m, source in enumerate(sources)
    }

    return {
        "node_voltages_v": voltages,
        "voltage_source_currents_a": branch_currents,
        "condition_number": condition_number(matrix),
        "residual_infinity_norm": residual_infinity_norm(matrix, rhs, solution),
        "unknown_count": size,
    }


def branch_report(problem: dict, solved: dict) -> dict:
    """Resistor currents and powers, and the conservation residuals.

    Written from the solved node voltages, so it is a check on the solve rather
    than a repetition of it.
    """
    voltages = solved["node_voltages_v"]
    resistor_currents = {}
    dissipated = 0.0
    for resistor in problem["resistors"]:
        drop = voltages[resistor["node_a"]] - voltages[resistor["node_b"]]
        current = drop / resistor["resistance_ohm"]
        resistor_currents[resistor["id"]] = current
        dissipated += drop * current

    # KCL at every node, reference included: the reference node's balance is
    # not one of the equations that was solved, so checking it there is a real
    # test rather than a restatement.
    balances = {name: 0.0 for name in problem["nodes"]}
    largest_branch = 0.0
    for resistor in problem["resistors"]:
        current = resistor_currents[resistor["id"]]
        largest_branch = max(largest_branch, abs(current))
        balances[resistor["node_a"]] += current
        balances[resistor["node_b"]] -= current
    for source in problem["current_sources"]:
        largest_branch = max(largest_branch, abs(source["current_a"]))
        # Inside the source the current runs from -> to, so at the `from`
        # node it LEAVES into the branch and at the `to` node it arrives.
        balances[source["from_node"]] += source["current_a"]
        balances[source["to_node"]] -= source["current_a"]
    for source in problem["voltage_sources"]:
        current = solved["voltage_source_currents_a"][source["id"]]
        largest_branch = max(largest_branch, abs(current))
        balances[source["positive_node"]] += current
        balances[source["negative_node"]] -= current

    delivered = 0.0
    for source in problem["voltage_sources"]:
        current = solved["voltage_source_currents_a"][source["id"]]
        drop = (
            voltages[source["positive_node"]] - voltages[source["negative_node"]]
        )
        # i leaves the positive terminal, so the source delivers -v*i.
        delivered += -drop * current
    for source in problem["current_sources"]:
        drop = voltages[source["to_node"]] - voltages[source["from_node"]]
        delivered += drop * source["current_a"]

    worst_kcl = max(abs(v) for v in balances.values())
    return {
        "resistor_currents_a": resistor_currents,
        "resistor_powers_w": {
            r["id"]: (voltages[r["node_a"]] - voltages[r["node_b"]]) ** 2
            / r["resistance_ohm"]
            for r in problem["resistors"]
        },
        "dissipated_w": dissipated,
        "delivered_w": delivered,
        "worst_kcl_residual_a": worst_kcl,
        "largest_branch_current_a": largest_branch,
        "normalised_kcl_residual": (
            worst_kcl / largest_branch if largest_branch > 0.0 else worst_kcl
        ),
        "normalised_power_imbalance": (
            abs(delivered - dissipated) / abs(dissipated)
            if dissipated != 0.0
            else abs(delivered - dissipated)
        ),
    }
