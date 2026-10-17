"""Heater KVL: a declared hybr -> lm root-method chain, opt-in (ERT V1, Big Rock 8).

Circuits without a chain keep their identity, operator digest and records
byte-for-byte (the BIG 9 default and the ``root_method="lm"`` workaround are
unchanged).  With a chain, every state's result is exactly what the accepted
method gives on its own, and the chain succeeds whenever either method alone
does.  NOT YET EXECUTED (build phase): see docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import itertools

import pytest

from engcore.domains.electrical.heater_circuit import HeaterCircuit
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity


def _circuit(volts, **kw):
    return HeaterCircuit(Quantity(volts, "V"), Quantity(2.0, "ohm"), Quantity(10.0, "ohm"), Quantity(293.15, "K"),
                         Quantity(0.004, "1/K"), **kw)


STATES = list(itertools.product((5.0, 7.3, 12.0, 18.5, 24.0), [293.15 + 3.7 * k for k in range(40)]))


def test_circuits_without_a_chain_keep_their_identity():
    assert "root_methods" not in _circuit(12.0).identity()
    assert "root_methods" not in _circuit(12.0, root_method="lm").identity()
    assert _circuit(12.0, root_method="lm").identity()["root_method"] == "lm"


def test_single_method_paths_report_no_chain_and_run_their_one_method():
    for method in ("hybr", "lm"):
        chain, record, _ = _circuit(12.0, root_method=method).solve_with_attempts(Quantity(330.0, "K"))
        assert chain is None and record.method.method == method


def test_a_declared_chain_is_part_of_the_circuit_identity():
    assert _circuit(12.0, root_methods=("hybr", "lm")).identity()["root_methods"] == ["hybr", "lm"]


@pytest.mark.parametrize("kwargs", [dict(root_methods=("hybr", "newton")), dict(root_methods=("lm", "lm")),
                                    dict(root_method="lm", root_methods=("hybr", "lm"))])
def test_chain_declarations_are_checked(kwargs):
    with pytest.raises(InvalidScientificProblem):
        _circuit(12.0, **kwargs)


def test_each_chain_result_is_exactly_the_accepted_methods_own_result_and_never_worse():
    for volts, kelvin in STATES:
        temperature = Quantity(kelvin, "K")
        chain, record, power = _circuit(volts, root_methods=("hybr", "lm")).solve_with_attempts(temperature)
        alone = {m: _circuit(volts, root_method=m).solve(temperature) for m in ("hybr", "lm")}
        if any(p is not None for _, p in alone.values()):
            assert power is not None, (volts, kelvin)  # the chain succeeds whenever either method alone does
        if power is None:
            continue
        accepted = record.method.method
        assert record.outputs["current"].to("A").magnitude == alone[accepted][0].outputs["current"].to("A").magnitude
        assert power.to("W").magnitude == alone[accepted][1].to("W").magnitude
        if accepted == "lm":
            # lm is reached only after hybr refused this very state, and that refusal is kept
            assert [a.method for a in chain.attempts] == ["hybr", "lm"] and alone["hybr"][1] is None


def test_the_sweep_exercises_the_hybr_false_refusal_with_scipy_1_18():
    # project memory: SciPy 1.18 hybr refuses ~6% of states of this linear residual at machine precision.
    # If a SciPy upgrade removes that behaviour this test fails loudly rather than the chain silently going untested.
    fallbacks = 0
    for volts, kelvin in STATES:
        chain, record, _ = _circuit(volts, root_methods=("hybr", "lm")).solve_with_attempts(Quantity(kelvin, "K"))
        fallbacks += record.method.method == "lm"
    assert fallbacks > 0
