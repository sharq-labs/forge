"""Modified Nodal Analysis assembly for linear resistive DC circuits.

Formulation
-----------
Unknown vector ``x`` of length ``N + M``:

* ``x[0 .. N-1]``  — voltages of the non-reference nodes, ordered by node id
* ``x[N .. N+M-1]`` — branch currents of the ideal voltage sources, ordered
  by component id

The reference node is eliminated (its voltage is 0 by definition), so no
equation or unknown is created for it.

Ordering is derived by sorting ids, so the same circuit always assembles the
same matrix regardless of the order components were added.

Stamps
------
Resistor ``R`` between ``a`` and ``b``, conductance ``G = 1/R`` — the usual
nodal conductance stamp, with rows/columns for the reference node dropped::

    A[a,a] += G   A[b,b] += G   A[a,b] -= G   A[b,a] -= G

Current source ``I`` flowing ``from_node -> to_node`` inside the source. Each
KCL row states *sum of currents leaving the node = 0*, so the source removes
``I`` at ``from_node`` and injects ``I`` at ``to_node``::

    z[from] -= I   z[to] += I

Voltage source ``k`` between ``p`` (positive) and ``n`` (negative), with
branch current ``i_k`` defined as the current **leaving p through the
source**::

    A[p, N+k] += 1    A[n, N+k] -= 1        (i_k appears in the KCL rows)
    A[N+k, p] += 1    A[N+k, n] -= 1        (the constraint row)
    z[N+k]     = Vs                          -> V_p - V_n = Vs

A source that delivers power to the circuit therefore reports a negative
``i_k``.

No custom linear algebra lives here: assembly only. The solve is delegated to
SciPy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

from .circuit import DCCircuit
from .components import DCVoltageSource


@dataclass(frozen=True)
class PreparedDCSystem:
    """The assembled MNA system plus the maps needed to interpret it.

    This is the domain-specific payload carried by
    :class:`~engcore.scientific.solvers.protocol.PreparedSolve`. Topology
    reaches the solver through here, never through the universal IR.
    """

    circuit: DCCircuit
    node_order: tuple[str, ...]
    voltage_source_order: tuple[str, ...]
    matrix: np.ndarray
    rhs: np.ndarray
    node_index: Mapping[str, int] = field(default_factory=dict)
    source_index: Mapping[str, int] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.node_order) + len(self.voltage_source_order)

    @property
    def n_nodes(self) -> int:
        return len(self.node_order)

    @property
    def n_sources(self) -> int:
        return len(self.voltage_source_order)

    def node_voltage(self, solution: np.ndarray, node_id: str) -> float:
        """Voltage of any node, including the reference node (exactly 0)."""
        if node_id == self.circuit.reference_node:
            return 0.0
        return float(solution[self.node_index[node_id]])

    def source_current(self, solution: np.ndarray, source_id: str) -> float:
        return float(solution[self.n_nodes + self.source_index[source_id]])


def assemble(circuit: DCCircuit) -> PreparedDCSystem:
    """Build ``A x = z`` for a circuit. Pure assembly, no solving."""
    node_order = circuit.non_reference_node_ids
    sources: tuple[DCVoltageSource, ...] = circuit.ordered_voltage_sources
    source_order = tuple(s.component_id for s in sources)

    node_index = {node_id: i for i, node_id in enumerate(node_order)}
    source_index = {source_id: k for k, source_id in enumerate(source_order)}

    n = len(node_order)
    m = len(source_order)
    size = n + m
    matrix = np.zeros((size, size), dtype=np.float64)
    rhs = np.zeros(size, dtype=np.float64)

    # --- resistor conductance stamps ---------------------------------
    for resistor in sorted(circuit.resistors, key=lambda r: r.component_id):
        conductance = resistor.conductance_siemens
        a = node_index.get(resistor.node_a)
        b = node_index.get(resistor.node_b)
        if a is not None:
            matrix[a, a] += conductance
        if b is not None:
            matrix[b, b] += conductance
        if a is not None and b is not None:
            matrix[a, b] -= conductance
            matrix[b, a] -= conductance

    # --- independent current source stamps ---------------------------
    for source in sorted(circuit.current_sources, key=lambda s: s.component_id):
        current = source.current_ampere
        origin = node_index.get(source.from_node)
        target = node_index.get(source.to_node)
        if origin is not None:
            rhs[origin] -= current
        if target is not None:
            rhs[target] += current

    # --- independent voltage source stamps ---------------------------
    for source in sources:
        k = n + source_index[source.component_id]
        positive = node_index.get(source.positive_node)
        negative = node_index.get(source.negative_node)
        if positive is not None:
            matrix[positive, k] += 1.0
            matrix[k, positive] += 1.0
        if negative is not None:
            matrix[negative, k] -= 1.0
            matrix[k, negative] -= 1.0
        rhs[k] = source.voltage_volt

    return PreparedDCSystem(
        circuit=circuit,
        node_order=node_order,
        voltage_source_order=source_order,
        matrix=matrix,
        rhs=rhs,
        node_index=node_index,
        source_index=source_index,
    )
