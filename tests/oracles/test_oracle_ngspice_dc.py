"""Forge's DC solve against ngspice — a program that shares nothing with it.

This is the only oracle in the suite that is independent in the strongest
sense available: a different program, written by different people over four
decades, solving the same circuit from a netlist this file writes and parsing
output this file reads. Forge's own ngspice adapter is deliberately NOT used --
going through it would put Forge's netlist builder on both sides of the
comparison and reduce this to a self-check.

ngspice is invoked through WSL because that is where it lives on this machine.
When it is absent the tests SKIP with a message saying coverage was lost, never
pass quietly.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from src.engcore.domains.electrical.dc.circuit import DCCircuit
from src.engcore.domains.electrical.dc.components import (
    DCVoltageSource,
    ElectricalNode,
    Resistor,
)
from src.engcore.domains.electrical.dc.solver import solve_circuit
from src.engcore.scientific.units.quantity import Quantity

from .oracle_ids import oracle

ORACLE_ID = "ORA-NGSPICE-DC"

#: ngspice's DC solve is exact for a linear resistive network up to its
#: internal conditioning. What limits this comparison is not its arithmetic but
#: the PRINTED OUTPUT: `print` emits about six significant figures, so a value
#: read back carries a quantisation of half a unit in its last printed place.
#:
#: The bound is therefore computed per value from the string ngspice actually
#: wrote, rather than being a round number chosen here. A first attempt used a
#: flat 1e-6 and one case failed at 1.6e-6 -- which is exactly half an ulp of
#: the sixth figure for a mantissa near 3, i.e. the format's limit and not a
#: disagreement. Deriving it removes the judgement call.
def _print_quantisation(printed: str) -> float:
    """Half a unit in the last decimal place ngspice printed."""
    text = printed.strip().lower()
    if "e" in text:
        mantissa, _, exponent = text.partition("e")
        decimals = len(mantissa.partition(".")[2])
        return 0.5 * 10.0 ** (-decimals) * 10.0 ** int(exponent)
    return 0.5 * 10.0 ** (-len(text.partition(".")[2]))


def _ngspice_argv():
    """How to reach ngspice, or None."""
    if shutil.which("ngspice"):
        return ["ngspice"]
    if shutil.which("wsl.exe") or shutil.which("wsl"):
        wsl = shutil.which("wsl.exe") or shutil.which("wsl")
        probe = subprocess.run(
            [wsl, "which", "ngspice"], capture_output=True, text=True, timeout=60
        )
        if probe.returncode == 0 and probe.stdout.strip():
            return [wsl, "ngspice"]
    return None


ARGV = _ngspice_argv()
requires_ngspice = pytest.mark.skipif(
    ARGV is None,
    reason=(
        "ngspice is not reachable, so the only INDEPENDENT_EXECUTABLE oracle "
        "in this suite did not run and the electrical DC domain is covered "
        "by internal checks alone"
    ),
)


def _run_ngspice(netlist: str) -> str:
    completed = subprocess.run(
        ARGV + ["-b"],
        input=netlist,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, (
        f"ngspice failed:\n{completed.stdout[-2000:]}\n{completed.stderr[-2000:]}"
    )
    return completed.stdout


def _parse_op(stdout: str) -> dict[str, float]:
    """Read `print` lines out of an ngspice batch operating-point run.

    Written here rather than imported, so a change to Forge's parser cannot
    change what this oracle believes ngspice said.
    """
    values: dict[str, tuple[float, str]] = {}
    pattern = re.compile(
        r"^([a-zA-Z_][\w()#.\-]*)\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*$"
    )
    for line in stdout.splitlines():
        match = pattern.match(line.strip())
        if match:
            values[match.group(1).lower()] = (
                float(match.group(2)), match.group(2)
            )
    return values


def _forge_solution(resistance_ohm: float, source_volt: float):
    circuit = DCCircuit(
        circuit_id="oracle",
        nodes=(ElectricalNode("gnd", is_reference=True), ElectricalNode("n1")),
        resistors=(
            Resistor(
                component_id="R1",
                node_a="n1",
                node_b="gnd",
                resistance=Quantity(resistance_ohm, "ohm"),
            ),
        ),
        voltage_sources=(
            DCVoltageSource(
                component_id="V1",
                positive_node="n1",
                negative_node="gnd",
                voltage=Quantity(source_volt, "volt"),
            ),
        ),
    )
    return solve_circuit(circuit, run_id="oracle")


def _netlist(resistance_ohm: float, source_volt: float) -> str:
    """A netlist this file writes, in ngspice's own syntax."""
    return "\n".join(
        [
            "* forge oracle: single resistor across an ideal source",
            f"V1 n1 0 DC {source_volt!r}",
            f"R1 n1 0 {resistance_ohm!r}",
            ".control",
            "op",
            "print v(n1)",
            "print i(V1)",
            ".endc",
            ".end",
            "",
        ]
    )


CASES = [
    (1000.0, 5.0),
    (69.12925707, 19.6884926),      # U00204's conductor, cold
    (2.49469785, 7.654942855),      # U01001's conductor, cold
    (1e-3, 1.0),
    (1e6, 250.0),
]


@requires_ngspice
@pytest.mark.parametrize("resistance,voltage", CASES)
def test_forge_and_ngspice_agree_on_node_voltage_and_current(resistance, voltage):
    assert oracle(ORACLE_ID).independent and oracle(ORACLE_ID).executable
    external = _parse_op(_run_ngspice(_netlist(resistance, voltage)))
    assert "v(n1)" in external, external

    result = _forge_solution(resistance, voltage)
    forge_v = result.value("node_voltage:n1").magnitude_in("volt")

    voltage_value, voltage_text = external["v(n1)"]
    assert forge_v == pytest.approx(
        voltage_value, abs=_print_quantisation(voltage_text)
    ), f"node voltage: forge {forge_v!r} vs ngspice {voltage_text!r}"

    # ngspice reports source current with the passive sign convention, so its
    # magnitude is what compares to the branch current.
    forge_i = result.value("source_current:V1").magnitude_in("ampere")
    current_value, current_text = external["i(v1)"]
    assert abs(forge_i) == pytest.approx(
        abs(current_value), abs=_print_quantisation(current_text)
    ), f"current: forge {forge_i!r} vs ngspice {current_text!r}"


@requires_ngspice
@pytest.mark.parametrize("resistance,voltage", CASES)
def test_forge_and_ngspice_agree_on_dissipated_power(resistance, voltage):
    """Power is what the electro-thermal coupling actually transports.

    Computed on the ngspice side as v*i from ITS OWN printed values, so the
    comparison never borrows Forge's arithmetic.
    """
    external = _parse_op(_run_ngspice(_netlist(resistance, voltage)))
    (voltage_value, voltage_text) = external["v(n1)"]
    (current_value, current_text) = external["i(v1)"]
    external_power = abs(voltage_value * current_value)

    result = _forge_solution(resistance, voltage)
    forge_power = result.value("resistor_power:R1").magnitude_in("watt")

    # A product carries both factors' quantisation, propagated as
    # |v| dI + |i| dV -- first order, which is exact enough at these sizes.
    budget = (
        abs(voltage_value) * _print_quantisation(current_text)
        + abs(current_value) * _print_quantisation(voltage_text)
    )
    assert forge_power == pytest.approx(external_power, abs=budget), (
        f"power: forge {forge_power!r} vs ngspice {external_power!r} "
        f"(quantisation budget {budget:.3e})"
    )


@requires_ngspice
def test_the_oracle_would_notice_a_wrong_answer():
    """A comparison that cannot fail proves nothing.

    Feed ngspice a DIFFERENT circuit from the one Forge solved and confirm the
    two disagree far outside the tolerance. Without this, a parser returning
    Forge's own number would look like agreement.
    """
    external = _parse_op(_run_ngspice(_netlist(2000.0, 5.0)))
    forge_v = _forge_solution(1000.0, 5.0).value("node_voltage:n1").magnitude_in("volt")
    # Same node voltage (ideal source), so compare the current instead.
    result = _forge_solution(1000.0, 5.0)
    forge_i = abs(result.value("source_current:V1").magnitude_in("ampere"))
    assert forge_v == pytest.approx(external["v(n1)"][0], rel=1e-9)
    other_current = abs(external["i(v1)"][0])
    assert abs(forge_i - other_current) / other_current > 0.5, (
        "halving the resistance must halve the current; if this passes the "
        "comparison is not reading two different circuits"
    )
