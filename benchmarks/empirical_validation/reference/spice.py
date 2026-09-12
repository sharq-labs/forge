"""An ngspice netlist written from the raw fixture, and the run that reads it.

THE RULE THIS FILE EXISTS TO OBEY. ngspice is only an independent check if the
problem it is given was stated independently. A netlist emitted from an engcore
circuit object would inherit every parsing, unit and sign decision the Core
made, and the two would then agree about a circuit neither of them had built
correctly. So this file reads ``fixtures/circuits.json`` and nothing else. It
does not import the adapters, and it converts kohm to ohm and mV to V with the
factors written below rather than with anyone else's.

ngspice is a separate program, in a separate process, written by other people
over three decades. It is the strongest external evidence available in this
environment, and it covers exactly one of the six domains.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess

# This file's own unit factors. Deliberately not imported from anywhere.
KOHM_TO_OHM = 1.0e3
MV_TO_V = 1.0e-3
MA_TO_A = 1.0e-3

def _argv() -> list[str] | None:
    """How to launch ngspice here, or ``None`` if it cannot be launched.

    An argv PREFIX rather than a path, because on some hosts -- this one -- the
    provider is not directly executable from Windows at all and is reached as
    ``wsl.exe -e ngspice``. The previous form was
    ``shutil.which("ngspice") or "/usr/bin/ngspice"``, which on such a host
    produced a POSIX path that Windows cannot execute: `available()` correctly
    answered False and the rebuild called `run()` anyway, so the round died
    with WinError 2 instead of reporting an unavailable channel.

    Resolution order matches the production adapter
    (``src/engcore/domains/electrical/ngspice.py``) and the blind round's
    oracle, so all three agree about where the provider is. This is runtime
    configuration, never science: nothing here reaches a record, and the file's
    independence rule is untouched -- no adapter is imported, and the netlist
    is still written from the raw fixture by this file's own factors.
    """
    raw = os.environ.get("CRAFTY_NGSPICE_ARGV", "").strip()
    if raw:
        return shlex.split(raw)
    if shutil.which("ngspice"):
        return ["ngspice"]
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if wsl:
        probe = subprocess.run(
            [wsl, "which", "ngspice"], capture_output=True, text=True, timeout=60
        )
        if probe.returncode == 0 and probe.stdout.strip():
            return [wsl, "ngspice"]
    return None


ARGV = _argv()

_VALUE = re.compile(r"^\s*([a-zA-Z0-9_()#.\-]+)\s*=\s*([-+0-9.eE]+)\s*$")


def available() -> bool:
    return ARGV is not None


def version() -> str:
    if ARGV is None:
        return "unavailable"
    out = subprocess.run(
        [*ARGV, "-v"], capture_output=True, text=True, timeout=60
    )
    for line in (out.stdout + out.stderr).splitlines():
        if "ngspice-" in line:
            return line.lstrip("* ").strip()
    return "unknown"


def _spice_node(name: str, reference: str) -> str:
    """ngspice's ground is the node literally named 0."""
    return "0" if name == reference else name


#: ngspice solves even a purely linear DC operating point by Newton iteration,
#: and stops on its defaults ``reltol = 1e-3`` and ``vntol = 1e-6`` volts. On a
#: five-volt node that absolute floor, not the seven-figure print format, is
#: what limits how closely two correct solvers can be seen to agree. Tightening
#: it is not tuning a tolerance to make anything pass -- the preregistered 2e-6
#: is unchanged and was already met on the defaults -- it is refining the
#: oracle so the comparison measures the physics instead of ngspice's stopping
#: rule. Both settings are reported.
TIGHT_OPTIONS = ".options reltol=1e-13 vntol=1e-13 abstol=1e-16 gmin=1e-15"

#: ngspice's default ``print`` format carries six decimal places, which on a
#: two-volt node is about 1e-6 relative -- and that, not any disagreement
#: between the two solvers, is what an audit reading the default output
#: measures. ``set numdgt=12`` asks for twelve significant figures instead.
#: Raising the printed precision cannot make a wrong answer look right; it can
#: only stop a right one from being rounded into looking wrong.
PRINT_DIGITS = "set numdgt=12"


def netlist(circuit: dict, *, tight: bool = True) -> str:
    """Emit a netlist for one raw-fixture circuit.

    Sign conventions are taken from the fixture's own stated conventions and
    mapped onto ngspice's:

      * ``Vname p n DC value`` sets V(p) - V(n) = value, which is the fixture's
        voltage_mV convention directly.
      * ``Iname a b DC value`` drives current from a THROUGH THE SOURCE to b,
        which is again the fixture's from_node -> to_node convention. ngspice
        documents this as current flowing from the first node, through the
        source, to the second; the mapping is one to one and no sign is
        flipped here.
    """
    reference = circuit["reference_node"]
    lines = [f"* {circuit['circuit_id']} -- emitted from the raw fixture"]
    for resistor in circuit["resistors"]:
        lines.append(
            f"R{resistor['id']} "
            f"{_spice_node(resistor['node_a'], reference)} "
            f"{_spice_node(resistor['node_b'], reference)} "
            f"{resistor['resistance_kohm'] * KOHM_TO_OHM!r}"
        )
    for source in circuit["voltage_sources"]:
        lines.append(
            f"V{source['id']} "
            f"{_spice_node(source['positive_node'], reference)} "
            f"{_spice_node(source['negative_node'], reference)} "
            f"DC {source['voltage_mV'] * MV_TO_V!r}"
        )
    for source in circuit["current_sources"]:
        lines.append(
            f"I{source['id']} "
            f"{_spice_node(source['from_node'], reference)} "
            f"{_spice_node(source['to_node'], reference)} "
            f"DC {source['current_mA'] * MA_TO_A!r}"
        )
    if tight:
        lines.append(TIGHT_OPTIONS)
    unknown = [n for n in circuit["nodes"] if n != reference]
    prints = " ".join(f"v({n})" for n in unknown)
    currents = " ".join(f"i(V{s['id']})" for s in circuit["voltage_sources"])
    lines += [
        ".control",
        PRINT_DIGITS if tight else "",
        "op",
        f"print {prints}".rstrip(),
    ]
    lines = [line for line in lines if line != ""]
    if currents:
        lines.append(f"print {currents}")
    lines += [".endc", ".end", ""]
    return "\n".join(lines)


def run(circuit: dict, *, tight: bool = True) -> dict:
    """Run ngspice on one circuit and return node voltages and source currents.

    Every unknown node is printed by name, one per ``print`` statement group.
    Printing by name rather than asking for everything avoids the case where a
    single-unknown circuit collapses its output to a bare ``all = value`` with
    no node label attached.
    """
    if ARGV is None:
        raise RuntimeError(
            "ngspice is not reachable on this host, so it cannot be used as an "
            "independent check. Callers must consult available() first: a "
            "missing provider is an execution fact, not a scientific one"
        )
    text = netlist(circuit, tight=tight)
    # The netlist goes in on STDIN rather than as a temp file, because the
    # provider may be in a different filesystem namespace than this process:
    # under `wsl.exe -e ngspice` a Windows path is not resolvable inside the
    # guest. Nothing crosses the boundary but the netlist itself, so there is
    # no path to translate and no host convention to leak. The bytes are
    # identical either way -- `netlist()` is unchanged and still builds them
    # from the raw fixture.
    completed = subprocess.run(
        [*ARGV, "-b"],
        input=text,
        capture_output=True,
        text=True,
        timeout=120,
    )
    voltages: dict[str, float] = {circuit["reference_node"]: 0.0}
    currents: dict[str, float] = {}
    for line in completed.stdout.splitlines():
        match = _VALUE.match(line)
        if not match:
            continue
        name, raw = match.group(1), match.group(2)
        try:
            value = float(raw)
        except ValueError:
            continue
        lowered = name.lower()
        if lowered.startswith("v(") and lowered.endswith(")"):
            voltages[name[2:-1]] = value
        elif lowered.startswith("i(v") and lowered.endswith(")"):
            currents[name[3:-1]] = value
        elif lowered in {n.lower() for n in circuit["nodes"]}:
            voltages[name] = value
    missing = [
        n
        for n in circuit["nodes"]
        if n != circuit["reference_node"] and n not in voltages
    ]
    return {
        "netlist": text,
        "node_voltages_v": voltages,
        "voltage_source_currents_a": currents,
        "missing_nodes": missing,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
