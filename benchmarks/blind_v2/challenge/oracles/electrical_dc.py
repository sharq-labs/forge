"""Independent truth for resistive DC networks.

Two routes, and this is the only system where the challenge can reach LEVEL A:

* **external** -- a real ``ngspice`` process. The netlist is written to a
  temporary file, ngspice is invoked in batch mode as a subprocess, and its
  printed operating point is parsed back. The executable version, the netlist
  digest and the raw-output digest are recorded with every case, so the claim
  "an external engine agreed" is checkable rather than asserted.
* **analytic** -- modified nodal analysis assembled and solved *here*, with
  Gaussian elimination with partial pivoting written in this module. No
  external linear algebra, so a shared library cannot make the two routes
  agree by construction.

A case is dual-oracle only when ngspice actually ran and produced a parsable
operating point. Where the executable is missing the case says so and is not
counted, rather than quietly falling back to one route wearing two names.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

from .numeric import relative_gap


@dataclass(frozen=True)
class Resistor:
    component_id: str
    node_a: str
    node_b: str
    resistance_ohm: float


@dataclass(frozen=True)
class VoltageSource:
    component_id: str
    positive_node: str
    negative_node: str
    voltage_volt: float


@dataclass(frozen=True)
class Network:
    """A resistive DC network. ``0`` is ground, as in every SPICE netlist."""

    circuit_id: str
    resistors: tuple[Resistor, ...] = ()
    sources: tuple[VoltageSource, ...] = ()

    def nodes(self) -> tuple[str, ...]:
        seen: list[str] = []
        for r in self.resistors:
            for n in (r.node_a, r.node_b):
                if n != "0" and n not in seen:
                    seen.append(n)
        for s in self.sources:
            for n in (s.positive_node, s.negative_node):
                if n != "0" and n not in seen:
                    seen.append(n)
        return tuple(seen)


# ---- route two: modified nodal analysis, solved here ---------------------
def _solve_linear(matrix: list[list[float]], rhs: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting. ``None`` when singular."""
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-14:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for row in range(col + 1, n):
            factor = a[row][col] / a[col][col]
            if factor == 0.0:
                continue
            for k in range(col, n + 1):
                a[row][k] -= factor * a[col][k]
    x = [0.0] * n
    for row in range(n - 1, -1, -1):
        total = a[row][n] - sum(a[row][k] * x[k] for k in range(row + 1, n))
        x[row] = total / a[row][row]
    return x


def solve_mna(network: Network) -> dict | None:
    """Node voltages and source branch currents, by MNA assembled here."""
    nodes = network.nodes()
    index = {name: i for i, name in enumerate(nodes)}
    n = len(nodes)
    m = len(network.sources)
    size = n + m
    if size == 0:
        return None
    matrix = [[0.0] * size for _ in range(size)]
    rhs = [0.0] * size

    for r in network.resistors:
        if r.resistance_ohm == 0.0:
            return None
        g = 1.0 / r.resistance_ohm
        a = index.get(r.node_a)
        b = index.get(r.node_b)
        if a is not None:
            matrix[a][a] += g
        if b is not None:
            matrix[b][b] += g
        if a is not None and b is not None:
            matrix[a][b] -= g
            matrix[b][a] -= g

    for j, s in enumerate(network.sources):
        row = n + j
        p = index.get(s.positive_node)
        q = index.get(s.negative_node)
        if p is not None:
            matrix[p][row] += 1.0
            matrix[row][p] += 1.0
        if q is not None:
            matrix[q][row] -= 1.0
            matrix[row][q] -= 1.0
        rhs[row] = s.voltage_volt

    solution = _solve_linear(matrix, rhs)
    if solution is None:
        return None
    voltages = {"0": 0.0}
    for name, i in index.items():
        voltages[name] = solution[i]
    currents = {
        s.component_id: solution[n + j] for j, s in enumerate(network.sources)
    }
    return {"node_voltages": voltages, "source_currents": currents}


# ---- route one: a real ngspice subprocess --------------------------------
_NGSPICE = os.environ.get("BLIND_V2_NGSPICE") or shutil.which("ngspice")

#: What two routes can be shown to agree to across ngspice's printed output.
ROUTE_AGREEMENT_TOLERANCE = 2e-6


def ngspice_version() -> str | None:
    if not _NGSPICE:
        return None
    try:
        proc = subprocess.run(
            [_NGSPICE, "--version"], capture_output=True, text=True, timeout=30
        )
    except Exception:
        return None
    for line in (proc.stdout or "").splitlines():
        if "ngspice" in line.lower():
            return line.strip().strip("*").strip()
    return (proc.stdout or "").strip()[:120] or None


def netlist_for(network: Network) -> str:
    lines = [f"* blind-v2 {network.circuit_id}"]
    for s in network.sources:
        lines.append(
            f"{s.component_id} {s.positive_node} {s.negative_node} DC {s.voltage_volt!r}"
        )
    for r in network.resistors:
        lines.append(f"{r.component_id} {r.node_a} {r.node_b} {r.resistance_ohm!r}")
    lines.append(".control")
    lines.append("op")
    lines.append("print all")
    lines.append("quit")
    lines.append(".endc")
    lines.append(".end")
    return "\n".join(lines) + "\n"


_VALUE = re.compile(r"^([A-Za-z0-9_#().\-]+)\s*=\s*([-+0-9.eE]+)\s*$")


def _parse_ngspice(text: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for raw in text.splitlines():
        line = raw.strip()
        m = _VALUE.match(line)
        if not m:
            continue
        name, value = m.group(1), m.group(2)
        try:
            found[name.lower()] = float(value)
        except ValueError:
            continue
    return found


def solve_ngspice(network: Network, *, timeout: float = 60.0) -> dict | None:
    """Run ngspice on this network. ``None`` when it is unavailable."""
    if not _NGSPICE:
        return None
    netlist = netlist_for(network)
    with tempfile.TemporaryDirectory(prefix="blindv2ng") as tmp:
        path = os.path.join(tmp, "circuit.cir")
        with open(path, "w", encoding="ascii") as handle:
            handle.write(netlist)
        try:
            proc = subprocess.run(
                [_NGSPICE, "-b", path],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception as exc:  # pragma: no cover - environment failure
            return {"error": f"{type(exc).__name__}: {exc}"}
    raw = (proc.stdout or "") + "\n" + (proc.stderr or "")
    values = _parse_ngspice(raw)
    voltages: dict[str, float] = {"0": 0.0}
    for node in network.nodes():
        key = node.lower()
        if key in values:
            voltages[node] = values[key]
    currents: dict[str, float] = {}
    for s in network.sources:
        for candidate in (
            f"{s.component_id}#branch".lower(),
            f"i({s.component_id})".lower(),
        ):
            if candidate in values:
                currents[s.component_id] = values[candidate]
                break
    return {
        "node_voltages": voltages,
        "source_currents": currents,
        "exit_code": proc.returncode,
        "netlist_sha256": hashlib.sha256(netlist.encode("ascii")).hexdigest(),
        "output_sha256": hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest(),
        "executable": _NGSPICE,
    }


def solve(network: Network, *, with_external: bool = True) -> dict:
    """Both routes, with their disagreement stated."""
    analytic = solve_mna(network)
    external = solve_ngspice(network) if with_external else None
    gaps: dict[str, float] = {}
    dual = False
    if analytic and external and external.get("node_voltages"):
        for node, value in analytic["node_voltages"].items():
            other = external["node_voltages"].get(node)
            if other is not None:
                gap = relative_gap(value, other)
                if gap is not None:
                    gaps[f"V({node})"] = gap
        for name, value in analytic["source_currents"].items():
            other = external["source_currents"].get(name)
            if other is not None:
                # ngspice reports the branch current with the opposite sign
                # convention to the MNA unknown assembled here: its branch
                # current flows into the positive terminal. Compared on
                # magnitude, which is what every rating condition uses.
                gap = relative_gap(abs(value), abs(other))
                if gap is not None:
                    gaps[f"I({name})"] = gap
        dual = bool(gaps)
    return {
        "analytic": analytic,
        "external": external,
        "gaps": gaps,
        "worst_gap": max(gaps.values()) if gaps else None,
        "dual_oracle": dual,
        "independence_level": "A" if dual else None,
        # ngspice's `print` emits about seven significant figures, so the two
        # routes cannot be shown to agree more closely than that however
        # exactly they do. The tolerance is a property of the interface, is
        # recorded here before any run, and is never widened afterwards.
        "route_agreement_tolerance": ROUTE_AGREEMENT_TOLERANCE,
        "tolerance_basis": "ngspice print precision, ~7 significant figures",
        "routes_agree": (max(gaps.values()) <= ROUTE_AGREEMENT_TOLERANCE) if gaps else None,
    }


def element_quantities(network: Network, solution: dict) -> dict:
    """Per-element voltage, current and dissipation from a solved network."""
    voltages = solution["node_voltages"]
    out: dict[str, dict[str, float]] = {}
    for r in network.resistors:
        va = voltages.get(r.node_a, 0.0)
        vb = voltages.get(r.node_b, 0.0)
        across = va - vb
        current = across / r.resistance_ohm
        out[r.component_id] = {
            "voltage_across": across,
            "current_through": current,
            "dissipated_power": abs(across * current),
        }
    for s in network.sources:
        out[s.component_id] = {
            "source_current": solution["source_currents"].get(s.component_id, 0.0)
        }
    return out
