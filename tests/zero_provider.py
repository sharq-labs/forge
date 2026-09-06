"""A controlled provider that answers every requested channel with zero.

**A real external program**, launched as a child process by the same
``NgspiceInvocation`` machinery that reaches ngspice. It is not a stub, a
monkeypatch or an in-process subclass, because the finding it reproduces is
about what crosses a *process* boundary and is admitted on the other side. A
fake would have proved something about a fake.

Why zeros specifically
----------------------
Zero is the one wrong answer that satisfies the adapter's admission gate
without any conspiracy. That gate reconciles three provider channels against
Crafty's own declaration::

    I  ==  V_drop / R          0 == 0 / 10
    P  ==  V_drop * I          0 == 0 * 0

Both hold exactly. A provider halving its power is caught there; a provider
returning nothing at all is caught by the missing-quantity check. Zeros pass
both, reach ``extract_metrics``, and are then found wanting by Crafty's *own*
validation — ``linear_system_residual`` and ``voltage_source_relation`` both
FAIL, because a circuit with a 5 V source does not have zero volts at every
node.

That is the case the finding is about: not an execution failure, but an
executed result that Crafty checked and rejected, whose zero power was
transported into the coupling regardless — where a body receiving zero heat sits
at ambient and the loop reports ``criterion_met`` at 300 K.

Not marked ``expensive``: it prints a dozen lines and exits, and the tier
markers live in ``tests/conftest.py``, which this round does not modify.
"""

from __future__ import annotations

import sys

#: A banner shaped like the one ``NgspiceInvocation.probe_version`` reads. The
#: version has to parse, because provenance records what actually answered.
VERSION_BANNER = (
    "******\n"
    "** ngspice-42 : Circuit level simulation program\n"
    "** controlled zero provider (Crafty test support)\n"
)

PRINT_PREFIX = "print "


def requested_expressions(netlist: str) -> list[str]:
    """The expressions the netlist's own ``print`` line asks for.

    Read out of the input rather than reconstructed, so this program stays
    honest about answering exactly what it was asked for: the adapter refuses a
    reply that omits a requested quantity, and being refused there would test
    the wrong thing.
    """
    for line in netlist.splitlines():
        stripped = line.strip()
        if stripped.startswith(PRINT_PREFIX):
            return stripped[len(PRINT_PREFIX):].split()
    return []


def main(argv: list[str]) -> int:
    if "--version" in argv:
        sys.stdout.write(VERSION_BANNER)
        return 0
    for expression in requested_expressions(sys.stdin.read()):
        sys.stdout.write(f"{expression} = 0.000000000000e+00\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
