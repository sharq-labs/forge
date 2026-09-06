"""A controlled provider that answers every requested channel with NaN or inf.

**A real external program**, launched as a child process by the same
``NgspiceInvocation`` machinery that reaches ngspice — the sibling of
``tests/zero_provider.py`` and written for the same reason it was. It is not a
stub, a monkeypatch or an in-process subclass, because the finding it
reproduces is about what crosses a *process* boundary and is admitted on the
other side. A fake would have proved something about a fake.

Why non-finite specifically
---------------------------
``tests/zero_provider.py`` returns the one *wrong* answer that satisfies the
adapter's admission relations exactly::

    I  ==  V_drop / R          0 == 0 / 10
    P  ==  V_drop * I          0 == 0 * 0

This one returns the answers that satisfy them **without being numbers at all**.
The relations are tolerance comparisons::

    abs(actual - expected) > atol + rtol * abs(expected)

and ``nan - x`` is ``nan``, ``abs(nan)`` is ``nan``, and ``nan > anything`` is
False. A NaN therefore *disagrees with nothing*: it passes the current
relation, the power relation, and the ``power < -atol`` sign check underneath,
which is a comparison too. Infinity does the same whenever both operands are
infinite, because ``abs(inf - inf)`` is ``nan``.

That is the whole finding. The gate is written to catch a provider whose
numbers are wrong, and a provider whose numbers are not numbers is the one case
a comparison cannot see.

Where the value would have gone
-------------------------------
Straight into ``resistor_power``, which the electro-thermal composition
transports into ``heat_input``. A body receiving NaN heat has a NaN
temperature, and a loop comparing NaN against a tolerance does not converge and
does not report that it failed to — it compares, gets False, and stops.

Which channels
--------------
``--nan`` answers every requested expression with ``nan``; ``--inf`` with
``inf``. Both spellings are what a C-locale ``printf("%g")`` produces, which is
what a real provider's output would carry.

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
    "** controlled non-finite provider (Crafty test support)\n"
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
    answer = "inf" if "--inf" in argv else "nan"
    for expression in requested_expressions(sys.stdin.read()):
        sys.stdout.write(f"{expression} = {answer}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
