"""BIG 9 gate J: real preCICE execution from a Forge coupling contract.

Runs two separate participant processes over preCICE sockets.  The result is
accepted only when the iteration log shows convergence within the limit AND
Forge's own fixed-point check passes.  Agreement with Forge's analytic fixed
point is numerical corroboration, not validation.
"""

from __future__ import annotations

import pytest
from scipy.optimize import brentq

from engcore.domains.electrical.heater_circuit import HeaterCircuit
from engcore.scientific.units.quantity import Quantity
from forge_precice import ExchangedQuantity, ScalarTwoWayContract, execute, precice_available

OK, VERSION = precice_available()
pytestmark = pytest.mark.skipif(not OK, reason=f"preCICE unavailable: {VERSION}")

T_AMB, R_TH = 293.15, 13.0
CIRCUIT = dict(V=10.0, Rs_ohm=1.0, R0_ohm=10.0, T0_K=293.15, alpha_per_K=0.004)


def contract(*, relaxation=0.7, max_iterations=50, alpha=0.004, limit_T=1e-9):
    return ScalarTwoWayContract(
        "joule-lumped", "Electrical", "Thermal",
        (ExchangedQuantity("Power", "electrical_power", "W", "Electrical", 1e-9),
         ExchangedQuantity("Temperature", "temperature", "K", "Thermal", limit_T)),
        max_iterations, relaxation, 1.0, 1.0,
        {"Electrical": dict(model="heater_circuit", initial_written=1.0, **dict(CIRCUIT, alpha_per_K=alpha)),
         "Thermal": dict(model="lumped_thermal", initial_written=300.0, ambient_K=T_AMB, thermal_resistance_K_per_W=R_TH)},
    )


def circuit(alpha=0.004):
    return HeaterCircuit(Quantity(10, "V"), Quantity(1, "ohm"), Quantity(10, "ohm"), Quantity(293.15, "K"), Quantity(alpha, "1/K"))


def fixed_point_check(alpha=0.004):
    def check(values):
        t, p = values["temperature"], values["electrical_power"]
        _, p_model = circuit(alpha).solve(Quantity(t, "K"))
        rt = abs(t - (T_AMB + p * R_TH))
        rp = abs(p - p_model.to("W").magnitude)
        return (rt < 1e-6 and rp < 1e-6), f"|T - model| = {rt:.2e} K, |P - model| = {rp:.2e} W"
    return check


def test_precice_two_way_coupling_really_runs_and_matches_forge_fixed_point():
    c = contract()
    rec = execute(c, fixed_point_check())
    assert rec.succeeded, rec.reason
    assert rec.iterations and rec.iterations[0] >= 2 and rec.iterations[0] < c.max_iterations
    # Forge's own fixed point (independent of preCICE): T = T_amb + P(T) R_th
    t_star = brentq(lambda t: t - T_AMB - circuit().solve(Quantity(t, "K"))[1].to("W").magnitude * R_TH, 293.15, 600)
    assert rec.values["temperature"] == pytest.approx(t_star, abs=1e-6)
    assert rec.to_dict()["classification"] == "coupling_execution_not_scientific_evidence"


def test_config_is_generated_from_the_contract_and_changes_identity():
    a, b = contract(), contract(relaxation=0.5)
    assert "serial-implicit" in a.render("/tmp/x") and 'relaxation value="0.7"' in a.render("/tmp/x")
    assert a.render("/tmp/x") != b.render("/tmp/x")
    with pytest.raises(ValueError, match="absolute convergence limit"):
        contract(limit_T=0.0)


def test_precice_iteration_limit_is_refused_even_though_precice_continues():
    rec = execute(contract(max_iterations=3, relaxation=0.2), fixed_point_check())
    assert not rec.succeeded and "max-iterations" in rec.reason and rec.to_dict()["values"] == {}
