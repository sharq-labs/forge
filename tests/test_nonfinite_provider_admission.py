"""GUARD 7, across a real process boundary: NaN and inf cannot be admitted.

The finding is that every admission gate is a tolerance comparison and
``abs(nan - x) > tol`` is False, so a provider returning NaN disagreed with
nothing and walked straight through a gate written to catch exactly the
provider that disagrees. Both relations and the sign check underneath them are
comparisons, and a comparison is the one thing that cannot see this.

**What actually happened next, stated exactly.** The value did not reach a
``ScientificResult``: ``Quantity`` refuses a non-finite magnitude, so
``extract_metrics`` died one layer further on with a
``UnitCompatibilityError``. That is a backstop and it worked, and it is not
what this guard is about. Three things were still wrong:

* The refusal came from the units layer and said "a unit problem", when the
  truth is *the provider ran and did not deliver what was asked* --
  ``NgspiceExecutionFailure``, which is the category this adapter documents and
  the one a caller catches.
* ``total_dissipation`` accumulated the NaN before anything wrapped it, so the
  backstop caught the sum rather than the value.
* ``_admit_element_power`` is the method the next provider adapter will be
  written from, and it admitted NaN. A backstop that happens to sit downstream
  today is not a gate, and the next adapter that computes anything from an
  admitted number before wrapping it loses even that.

So the tests below assert the *category* of the refusal, not merely that
something refused.

**The provider here is a real external program.** ``tests/nonfinite_provider.py``
is launched as a child process by the same ``NgspiceInvocation`` machinery that
reaches ngspice — the sibling of ``tests/zero_provider.py``, written the same
way and for the same reason. No mock, no monkeypatch, no in-process subclass:
the finding is about what crosses a process boundary and is admitted on the
other side, and a fake would have proved something about a fake.

Two spellings, because a provider emits what its C locale prints: ``nan`` and
``inf``.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from engcore.domains.electrical import ngspice as ng
from engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
)
from engcore.scientific.results.validation import ValidationOutcome
from engcore.scientific.units.quantity import Quantity

#: The provider script, reached the way any external provider is: as an argv
#: prefix. ``sys.executable`` is this interpreter, so no toolchain is assumed.
_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "nonfinite_provider.py"
)
NAN_PROVIDER = (sys.executable, _SCRIPT, "--nan")
INF_PROVIDER = (sys.executable, _SCRIPT, "--inf")


def _divider() -> DCCircuit:
    """A 5 V source across two series resistors. Nothing exotic is needed."""
    return DCCircuit(
        circuit_id="guard7-divider",
        nodes=(
            ElectricalNode("gnd", is_reference=True),
            ElectricalNode("n1"),
            ElectricalNode("n2"),
        ),
        resistors=(
            Resistor(
                component_id="R1",
                node_a="n1",
                node_b="n2",
                resistance=Quantity(1000.0, "ohm"),
            ),
            Resistor(
                component_id="R2",
                node_a="n2",
                node_b="gnd",
                resistance=Quantity(1000.0, "ohm"),
            ),
        ),
        voltage_sources=(
            DCVoltageSource(
                component_id="V1",
                positive_node="n1",
                negative_node="gnd",
                voltage=Quantity(5.0, "volt"),
            ),
        ),
    )


@pytest.mark.parametrize(
    "command, spelling",
    [(NAN_PROVIDER, "nan"), (INF_PROVIDER, "inf")],
    ids=["nan", "inf"],
)
def test_the_provider_really_is_an_external_program(command, spelling):
    """It answers a version probe and prints what it was asked for.

    Asserted before the admission test, so a refusal below is a refusal of what
    the provider said rather than a failure to launch it — which would pass the
    admission test for the wrong reason.
    """
    banner = subprocess.run(
        [*command, "--version"], capture_output=True, text=True, timeout=60
    )
    assert banner.returncode == 0
    assert "ngspice" in banner.stdout

    answered = subprocess.run(
        command,
        input="print v(n1) @r1[i]\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert answered.returncode == 0
    lines = [l for l in answered.stdout.splitlines() if l.strip()]
    assert len(lines) == 2
    assert all(line.endswith(f"= {spelling}") for line in lines), lines

    # And the adapter's own parser turns them into non-finite floats, so the
    # numbers really do reach admission rather than being dropped as unparsable.
    parsed = ng.parse_print_output(answered.stdout)
    assert len(parsed) == 2
    assert all(value != value or abs(value) == float("inf") for value in parsed.values())


@pytest.mark.parametrize(
    "command", [NAN_PROVIDER, INF_PROVIDER], ids=["nan", "inf"]
)
def test_a_non_finite_provider_answer_is_refused_at_admission(command):
    """No result is synthesised, so there is nothing downstream to transport.

    A :class:`NgspiceExecutionFailure` is the existing category for *the
    provider ran and did not deliver what was asked*, which is what a NaN is.
    It is not a scientific verdict: a refused solve produces no
    ``ScientificResult`` at all, rather than one carrying a FAIL that a coupling
    loop would not read.
    """
    solver = ng.NgspiceDCSolver(
        invocation=ng.NgspiceInvocation(command=command)
    )
    with pytest.raises(ng.NgspiceExecutionFailure, match="non-finite"):
        ng.solve_circuit_with_ngspice(
            _divider(), run_id="guard7-nonfinite", solver=solver
        )


def test_the_zero_provider_still_reaches_a_result():
    """The control: the guard refuses non-finite answers, not every answer.

    ``tests/zero_provider.py`` returns the one *wrong* answer that satisfies
    the admission relations exactly, and it is admitted -- and then found
    wanting by Crafty's own validation, which is the behaviour the earlier
    finding established. A finiteness guard that also refused zero would have
    broken that, and would have been a different guard.
    """
    zero_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "zero_provider.py"
    )
    solver = ng.NgspiceDCSolver(
        invocation=ng.NgspiceInvocation(command=(sys.executable, zero_script))
    )
    result = ng.solve_circuit_with_ngspice(
        _divider(), run_id="guard7-zero", solver=solver
    )
    assert result.value("resistor_power:R1").magnitude_in("watt") == 0.0
    # Admitted, and then found wanting by Crafty's own validation -- the two
    # gates answer different questions and this test is what keeps them apart.
    assert result.validation.status is ValidationOutcome.FAIL


@pytest.mark.parametrize(
    "command", [NAN_PROVIDER, INF_PROVIDER], ids=["nan", "inf"]
)
def test_the_refusal_is_an_execution_failure_and_not_a_units_error(command):
    """The substantive change: which gate refuses, and what it says.

    Before this guard the non-finite value passed both admission relations and
    was stopped one layer on by ``Quantity``, arriving as a
    ``UnitCompatibilityError`` -- "a unit problem", about a provider that had
    not delivered what was asked. It is refused at admission now, in the
    category this adapter documents for exactly that.
    """
    from engcore.scientific.errors import UnitCompatibilityError

    solver = ng.NgspiceDCSolver(
        invocation=ng.NgspiceInvocation(command=command)
    )
    with pytest.raises(ng.NgspiceExecutionFailure) as refusal:
        ng.solve_circuit_with_ngspice(
            _divider(), run_id="guard7-category", solver=solver
        )
    assert not isinstance(refusal.value, UnitCompatibilityError)
    assert "non-finite" in str(refusal.value)
    # And it names where the number came from, so a reader is not left to guess
    # whether the adapter or the provider produced it.
    assert "provider" in str(refusal.value)
