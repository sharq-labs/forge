"""SECOND ORACLE for the electrical channel: a different program entirely.

The strongest independence available in this repository. ngspice is a
general-purpose circuit simulator written by other people over four decades; it
shares no line of code, no unit library and no algorithm with either Forge or
the analytic oracle beside it. The netlist is written here and the output is
parsed here, so nothing of Forge's is on either side of the comparison.

**What it can and cannot check.** It checks the DC solve: given the series
resistances the coupled fixed point converged to, does the loop current agree.
It cannot check the *thermal* half of the coupling, because there is no
temperature in a netlist — the resistances handed to it are already the
oracle's answer to the thermal question. So this oracle bounds a transcription
or arithmetic error in the electrical solve and nothing else, and saying so is
the point of the entry.

**Absence is recorded, never passed over.** If ngspice cannot be reached the
dual-oracle count for the electrical channel is zero and the manifest says so.
A missing oracle is lost coverage, not a satisfied check.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess

__all__ = [
    "SPICE_ORACLE_ID",
    "available",
    "series_current",
]

SPICE_ORACLE_ID = "blind.oracle.electrical.ngspice"

_PATTERN = re.compile(
    r"^([a-zA-Z_][\w()#.\-]*)\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*$"
)


def _argv() -> list[str] | None:
    if shutil.which("ngspice"):
        return ["ngspice"]
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if wsl:
        probe = subprocess.run([wsl, "which", "ngspice"], capture_output=True,
                               text=True, timeout=60)
        if probe.returncode == 0 and probe.stdout.strip():
            return [wsl, "ngspice"]
    return None


ARGV = _argv()


def available() -> bool:
    return ARGV is not None


def _quantisation(printed: str) -> float:
    """Half a unit in the last decimal place ngspice printed.

    ``print`` emits about six significant figures, so a value read back
    carries a quantisation of half a unit in its last printed place. The
    comparison bound is derived from the string ngspice actually wrote rather
    than being a round number chosen here, which removes the judgement call
    about what counts as agreement.
    """
    text = printed.strip().lower()
    if "e" in text:
        mantissa, _, exponent = text.partition("e")
        decimals = len(mantissa.partition(".")[2])
        return 0.5 * 10.0 ** (-decimals) * 10.0 ** int(exponent)
    return 0.5 * 10.0 ** (-len(text.partition(".")[2]))


def series_current(resistances: list[float], source_volt: float) -> dict:
    """Solve one series loop in ngspice and compare with ``V / sum(R)``.

    Returns the measured current, the analytic one, the disagreement, and the
    printing quantisation that bounds how closely they could possibly agree.
    """
    if ARGV is None:
        return {"status": "unavailable",
                "why": "ngspice is not reachable; the electrical channel has "
                       "no independent executable oracle in this run"}
    if not resistances or any(r <= 0.0 or not math.isfinite(r)
                              for r in resistances):
        return {"status": "not_applicable",
                "why": "a non-positive resistance is not a linear network"}
    if not math.isfinite(source_volt) or source_volt == 0.0:
        return {"status": "not_applicable", "why": "no source drive"}

    lines = ["* blind challenge oracle: series loop",
             f"V1 n0 0 DC {source_volt!r}"]
    for index, resistance in enumerate(resistances):
        node_a = f"n{index}"
        node_b = "0" if index == len(resistances) - 1 else f"n{index + 1}"
        lines.append(f"R{index + 1} {node_a} {node_b} {resistance!r}")
    lines += [".control", "op", "print i(V1)", ".endc", ".end", ""]
    netlist = "\n".join(lines)

    try:
        completed = subprocess.run(ARGV + ["-b"], input=netlist,
                                   capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "failed", "why": f"{type(exc).__name__}: {exc}"}
    if completed.returncode != 0:
        return {"status": "failed",
                "why": f"ngspice exit {completed.returncode}",
                "stderr": completed.stderr[-400:]}

    printed: dict[str, tuple[float, str]] = {}
    for line in completed.stdout.splitlines():
        match = _PATTERN.match(line.strip())
        if match:
            printed[match.group(1).lower()] = (float(match.group(2)),
                                               match.group(2))
    if "i(v1)" not in printed:
        return {"status": "failed", "why": "ngspice printed no i(V1)",
                "stdout": completed.stdout[-400:]}

    # ngspice reports source current with the passive sign convention, so the
    # loop current out of the positive terminal is its negation.
    measured = -printed["i(v1)"][0]
    analytic = source_volt / sum(resistances)
    scale = max(abs(analytic), abs(measured))
    return {
        "status": "compared",
        "oracle_a": "blind.oracle.electrothermal.analytic",
        "oracle_b": SPICE_ORACLE_ID,
        "quantity": "series loop current",
        "analytic_a": analytic,
        "measured_a": measured,
        "absolute_gap": abs(measured - analytic),
        "relative_gap": abs(measured - analytic) / scale if scale else 0.0,
        "print_quantisation": _quantisation(printed["i(v1)"][1]),
    }
