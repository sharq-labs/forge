"""The series heater KVL through the BIG 6 root provider: no false refusals, and an identity that says how it solved.

Until 2026-10-13 the default method was ``hybr``, which SciPy 1.18 reports as failed ("not making good progress")
on 6-8% of states of this LINEAR residual after it has reached machine precision. BIG 6 rightly refuses a backend
non-success, so a coupled run died mid-window for no physical reason. The default is ``lm`` now; a record that
names no method still means ``hybr``, because that is what every record written before the change solved with.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.domains.electrical.heater_circuit import HeaterCircuit
from engcore.scientific.units.quantity import Quantity


def _circuit(volts: float, **kw) -> HeaterCircuit:
    return HeaterCircuit(
        Quantity(volts, "V"), Quantity(1.0, "ohm"), Quantity(10.0, "ohm"), Quantity(293.15, "K"), Quantity(0.004, "1/K"), **kw
    )


def test_the_default_solve_refuses_no_state_and_matches_the_closed_form() -> None:
    refused, worst = [], 0.0
    for volts in np.linspace(0.5, 24.0, 15):
        circuit = _circuit(float(volts))
        for kelvin in np.linspace(250.0, 450.0, 12):
            record, power = circuit.solve(Quantity(float(kelvin), "K"))
            if power is None:
                refused.append((float(volts), float(kelvin), record.reason))
                continue
            rh = circuit.heater_resistance(Quantity(float(kelvin), "K"))
            exact = (volts / (1.0 + rh)) ** 2 * rh
            worst = max(worst, abs(power.magnitude_in("W") - exact) / exact)
    assert refused == []
    assert worst < 1e-12


def test_the_identity_names_the_method_except_for_records_that_never_named_one() -> None:
    assert _circuit(10.0).root_method == "lm"
    assert _circuit(10.0).identity()["root_method"] == "lm"
    # A record written before the default changed carries no method and was a hybr solve; it still reads as one.
    assert "root_method" not in _circuit(10.0, root_method="hybr").identity()
    assert _circuit(10.0).identity() != _circuit(10.0, root_method="hybr").identity()


def test_a_heater_outside_the_tcr_law_is_refused_not_solved() -> None:
    from engcore.scientific.errors import InvalidScientificProblem

    cold = HeaterCircuit(Quantity(10, "V"), Quantity(1, "ohm"), Quantity(10, "ohm"), Quantity(293.15, "K"), Quantity(-0.02, "1/K"))
    with pytest.raises(InvalidScientificProblem, match="outside the linear TCR law"):
        cold.solve(Quantity(400.0, "K"))
