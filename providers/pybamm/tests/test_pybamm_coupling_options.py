"""The coupled PyBaMM cell's added model options and active-material balance (BIG 14 flagship A, DFN switch).

Defaults keep the earlier identities byte for byte; a non-default option or balance enters the execution and state
identity; the isothermal contract cannot be overridden; a malformed balance is refused; the heat of mixing adds heat.
"""

from __future__ import annotations

import hashlib
import math
import pytest

from engcore.coupling import scalar_port
from engcore.execution.multiphysics.participant import AdvanceRequest
from engcore.providers import ProviderRefusal, ProviderRegistry
from engcore.scientific.multiphysics import ParticipantSpec
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

REG = ProviderRegistry()
from forge_pybamm import descriptor as pbd  # first-party: a defect fails, it never reads as a missing provider
pbd.register(REG)
OK = REG.status("pybamm").available
assert not ("pybamm" in {c.capability.provider_id for c in REG.discover()} and REG.status("pybamm").found_but_refused), "PyBaMM present but refused"
pytestmark = pytest.mark.skipif(not OK, reason="PyBaMM is required")


def _spec():
    ports = (scalar_port("temperature", "input", "temperature", "K"), scalar_port("heat", "output", "heat_rate", "W"))
    return ParticipantSpec("cell", "cell-model", "1", "cell-real", "1", "pybamm", REG.status("pybamm").version, "forge.coupling", "1", ports,
                           transient=True, checkpointable=True, deterministic_restore=True)


def _cell(log=None, **kw):
    from forge_pybamm.coupling import cell_participant
    return cell_participant(REG, _spec(), parameter_set_name="Chen2020", model=kw.pop("model", "SPM"), initial_soc=0.8, capacity_fade=0.0,
                            current_at=lambda _start: Quantity(2.5, "A"), log=log, **kw)


def _advance(cell):
    req = AdvanceRequest(Quantity(0, "s"), Quantity(1800, "s"), {"temperature": Quantity(298.15, "K")},
                         {"temperature": Uncertainty.unknown("test input")})
    return cell.advance(req)


def test_defaults_keep_the_earlier_initial_state_identity():
    from forge_pybamm import parameter_set
    pset, _ = parameter_set("Chen2020")
    expected = hashlib.sha256(f"initial:{pset.digest}:{0.8!r}:{0.0!r}".encode()).hexdigest()
    assert _cell().state_identity(None) == expected
    assert _cell(model_options={}, balance=(1.0, 1.0)).state_identity(None) == expected


def test_defaults_keep_the_earlier_execution_problem():
    log = []
    _advance(_cell(log))
    plain = log[-1]["execution_identity"]
    log2 = []
    _advance(_cell(log2, model_options=None, balance=(1, 1)))
    assert log2[-1]["execution_identity"] == plain


@pytest.mark.parametrize("kw", [{"balance": (0.98, 0.85)}, {"model_options": {"heat of mixing": "true"}}])
def test_a_declared_option_or_balance_changes_both_identities(kw):
    base_log, log = [], []
    base = _cell(base_log)
    other = _cell(log, **kw)
    assert other.state_identity(None) != base.state_identity(None)
    _advance(base)
    _advance(other)
    assert log[-1]["execution_identity"] != base_log[-1]["execution_identity"]


@pytest.mark.parametrize("opts", [{"thermal": "lumped"}, {"calculate heat source for isothermal models": "false"}, {"heat of mixing": True}])
def test_the_isothermal_contract_and_string_options_are_enforced(opts):
    with pytest.raises(ProviderRefusal):
        _cell(model_options=opts)


@pytest.mark.parametrize("balance", [(0.0, 1.0), (1.0, -0.5), (math.nan, 1.0), (1.0, math.inf), (True, 1.0), ("1", 1.0), (1.0,), (1.0, 1.0, 1.0)])
def test_a_malformed_balance_is_refused(balance):
    with pytest.raises(ProviderRefusal):
        _cell(balance=balance)


def test_the_balance_reaches_the_cell():
    """A smaller positive active-material fraction delivers the same charge from a smaller electrode: the voltage falls further."""
    log_a, log_b = [], []
    _advance(_cell(log_a))
    _advance(_cell(log_b, balance=(1.0, 0.85)))
    assert log_b[-1]["voltage_V_end"] < log_a[-1]["voltage_V_end"] - 1e-3


@pytest.mark.parametrize("model", ["SPM", "DFN"])
def test_the_heat_of_mixing_adds_heat(model):
    log_a, log_b = [], []
    _advance(_cell(log_a, model=model))
    _advance(_cell(log_b, model=model, model_options={"heat of mixing": "true"}))
    assert log_b[-1]["heat_W"] > log_a[-1]["heat_W"] * 1.05
