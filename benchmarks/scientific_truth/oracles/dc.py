"""Oracles for linear resistive DC circuits.

TWO oracles, one of them fully external.

1. ``ngspice_solve`` shells out to ngspice, an independently written circuit
   simulator that has existed since the 1990s and shares no line of code, no
   constant and no algebra with this repository. It is the strongest oracle
   available anywhere in this audit: a disagreement with it is a disagreement
   with the rest of the field.

2. ``mesh_solve`` solves the same circuit by a DIFFERENT formulation. The
   production code stamps a modified-nodal-analysis matrix. This solves the
   nodal system too, but assembles it from an incidence matrix and a branch
   conductance matrix -- G = A Y A^T -- rather than by element stamping, and
   handles voltage sources by the superposition/substitution argument written
   out below rather than by MNA's extra current unknowns. Two routes to the
   same linear algebra, built from different objects.

   For a network of resistors plus ideal voltage sources, fixing the source
   branches means the unknown node potentials satisfy A_r Y_r A_r^T v = -I_inj,
   where the voltage-source-imposed potentials are eliminated by substitution.
   Rather than reimplement that elimination in general, this oracle takes the
   simplest fully general route that is still independent of MNA: it treats
   each ideal voltage source as a Thevenin source of vanishing internal
   resistance (eps = 1e-9 ohm) and solves the resulting pure-conductance
   nodal system. The limit is exact to within eps/R, which is checked.

CONVENTIONS, stated because a sign error is exactly what this hunts for.

  * Node potentials are relative to the reference node, which is at 0 V.
  * A resistor between a and b carries I_ab = (v_a - v_b)/R, positive from a
    to b, and absorbs P = I_ab^2 R >= 0.
  * A current source from f to t drives current f -> t INSIDE the source, so
    it extracts I at f and injects I at t.
  * A voltage source imposes v_pos - v_neg = V.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile

import numpy as np

IDEAL_SOURCE_EPS_OHM = 1e-9


def ngspice_available() -> bool:
    return shutil.which("ngspice") is not None


def ngspice_solve(
    *,
    nodes: list[str],
    reference: str,
    resistors: list[tuple[str, str, str, float]],
    voltage_sources: list[tuple[str, str, str, float]],
    current_sources: list[tuple[str, str, str, float]],
) -> dict:
    """Solve one DC operating point with ngspice and return node potentials.

    The netlist is emitted here rather than by the repository's own ngspice
    module, so that a bug in that module cannot make the two agree.
    """
    index = {name: (0 if name == reference else i + 1)
             for i, name in enumerate(n for n in nodes if n != reference)}
    index[reference] = 0

    lines = ["* scientific-truth DC oracle"]
    for component_id, a, b, ohms in resistors:
        lines.append(f"R{component_id} {index[a]} {index[b]} {ohms!r}")
    for component_id, pos, neg, volts in voltage_sources:
        lines.append(f"V{component_id} {index[pos]} {index[neg]} DC {volts!r}")
    for component_id, frm, to, amps in current_sources:
        # SPICE convention: a current source I<name> n+ n- drives current from
        # n+ THROUGH THE SOURCE to n-, i.e. out of n+ externally. The domain's
        # convention is current from_node -> to_node inside the source, which
        # is the same statement with n+ = from_node.
        lines.append(f"I{component_id} {index[frm]} {index[to]} DC {amps!r}")
    lines += [".control", "op", "print all", ".endc", ".end", ""]
    netlist = "\n".join(lines)

    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as handle:
        handle.write(netlist)
        path = handle.name
    completed = subprocess.run(
        ["ngspice", "-b", path], capture_output=True, text=True, timeout=120
    )
    potentials: dict[str, float] = {reference: 0.0}
    reverse = {value: key for key, value in index.items() if key != reference}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) != 3 or parts[1] != "=":
            continue
        label = parts[0]
        # With exactly one unknown node ngspice's `print all` collapses to the
        # literal name `all` instead of `v(1)`. Handled explicitly: guessing
        # would be worse than failing, and dropping it silently left a
        # current-source circuit with no oracle at all.
        if label == "all" and len(reverse) == 1:
            potentials[next(iter(reverse.values()))] = float(parts[2])
            continue
        if label.startswith("v(") and label.endswith(")"):
            label = label[2:-1]
        try:
            number = int(label)
        except ValueError:
            continue
        if number in reverse:
            potentials[reverse[number]] = float(parts[2])
    return {
        "potentials": potentials,
        "netlist": netlist,
        "stdout": completed.stdout,
        "returncode": completed.returncode,
    }


def mesh_solve(
    *,
    nodes: list[str],
    reference: str,
    resistors: list[tuple[str, str, str, float]],
    voltage_sources: list[tuple[str, str, str, float]],
    current_sources: list[tuple[str, str, str, float]],
    eps_ohm: float = IDEAL_SOURCE_EPS_OHM,
) -> dict:
    """Solve by incidence-matrix assembly, G = A Y A^T, independent of MNA."""
    unknowns = [name for name in nodes if name != reference]
    position = {name: i for i, name in enumerate(unknowns)}
    n = len(unknowns)

    branches: list[tuple[str, str, float]] = [
        (a, b, 1.0 / ohms) for _, a, b, ohms in resistors
    ]
    injections = np.zeros(n, dtype=float)

    for _, pos, neg, volts in voltage_sources:
        # Thevenin with a vanishing internal resistance: a branch of
        # conductance 1/eps between the terminals, plus a Norton current
        # V/eps injected at the positive terminal.
        branches.append((pos, neg, 1.0 / eps_ohm))
        norton = volts / eps_ohm
        if pos in position:
            injections[position[pos]] += norton
        if neg in position:
            injections[position[neg]] -= norton

    for _, frm, to, amps in current_sources:
        # Current leaves the network at `frm` and enters at `to`.
        if frm in position:
            injections[position[frm]] -= amps
        if to in position:
            injections[position[to]] += amps

    incidence = np.zeros((n, len(branches)), dtype=float)
    admittance = np.zeros(len(branches), dtype=float)
    for column, (a, b, y) in enumerate(branches):
        admittance[column] = y
        if a in position:
            incidence[position[a], column] += 1.0
        if b in position:
            incidence[position[b], column] -= 1.0

    conductance = incidence @ np.diag(admittance) @ incidence.T
    solution = np.linalg.solve(conductance, injections)
    potentials = {reference: 0.0}
    for name, i in position.items():
        potentials[name] = float(solution[i])
    return {"potentials": potentials, "condition_number": float(np.linalg.cond(conductance))}


def kcl_residuals(
    *,
    potentials: dict[str, float],
    reference: str,
    resistors: list[tuple[str, str, str, float]],
    voltage_source_currents: dict[str, tuple[str, str, float]],
    current_sources: list[tuple[str, str, str, float]],
) -> dict[str, float]:
    """Signed sum of currents LEAVING each non-reference node. Must be ~0.

    Written from the conservation law directly, so it is an oracle over
    whatever produced the potentials rather than a re-solve of the circuit.
    """
    residual = {name: 0.0 for name in potentials if name != reference}
    for _, a, b, ohms in resistors:
        current = (potentials[a] - potentials[b]) / ohms
        if a in residual:
            residual[a] += current
        if b in residual:
            residual[b] -= current
    for _component, (pos, neg, current) in voltage_source_currents.items():
        # `current` is the current leaving the positive node through the source.
        if pos in residual:
            residual[pos] += current
        if neg in residual:
            residual[neg] -= current
    for _, frm, to, amps in current_sources:
        if frm in residual:
            residual[frm] += amps
        if to in residual:
            residual[to] -= amps
    return residual
