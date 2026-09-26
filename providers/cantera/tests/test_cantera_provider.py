"""Proof B: real Cantera equilibrium and transient reactor executions with bound mechanism identity."""

from __future__ import annotations

import pytest

from engcore.providers import ProviderRefusal, ProviderRegistry
from engcore.scenarios import TimePoint, TimeWindow
from engcore.scientific.units.quantity import Quantity
from forge_cantera import CanteraProvider, Mechanism, descriptor

REG = ProviderRegistry()
descriptor.register(REG)
OK = REG.status("cantera").available
pytestmark = pytest.mark.skipif(not OK, reason="Cantera unavailable")
STOICH_CH4_AIR = {"CH4": 1 / 10.52, "O2": 2 / 10.52, "N2": 7.52 / 10.52}


def test_proof_b_adiabatic_equilibrium_with_mechanism_bytes_bound():
    gri = Mechanism.from_cantera_data("gri30.yaml")
    prov = CanteraProvider(REG)
    rec = prov.equilibrium(gri, STOICH_CH4_AIR, Quantity(300, "K"), Quantity(101325, "Pa"), constraint="HP", species=("CO2", "H2O", "CO"))
    assert rec.succeeded and ("mechanism", gri.sha256) in [tuple(x) for x in rec.identity.input_digests]
    # adiabatic flame temperature of stoichiometric methane/air ~2225 K (integration check, not validation)
    assert 2150 < rec.scalars["temperature"].magnitude < 2300
    assert rec.scalars["X_H2O"].magnitude > rec.scalars["X_CO2"].magnitude > 0
    assert rec.to_dict()["classification"] == "provider_computation_not_evidence"
    # a different mechanism CONTENT is a different execution even with the same file name
    altered = Mechanism("gri30.yaml", gri.content + b"\n# forge: edited copy\n", "")
    assert prov.equilibrium(altered, STOICH_CH4_AIR, Quantity(300, "K"), Quantity(101325, "Pa"), constraint="HP").identity.digest != rec.identity.digest
    with pytest.raises(ProviderRefusal, match="sum to one"):
        prov.equilibrium(gri, {"CH4": 0.5, "O2": 0.2}, Quantity(300, "K"), Quantity(101325, "Pa"))
    with pytest.raises(ProviderRefusal, match="not defined by the mechanism"):
        prov.equilibrium(gri, {"CH4": 0.5, "XY9": 0.5}, Quantity(300, "K"), Quantity(101325, "Pa"))


def test_proof_b_transient_constant_pressure_reactor_on_a_big2_window():
    gri = Mechanism.from_cantera_data("gri30.yaml")
    w = TimeWindow(TimePoint("lab", Quantity(0, "s")), TimePoint("lab", Quantity(0.05, "s")))
    rec = CanteraProvider(REG).constant_pressure_reactor(gri, STOICH_CH4_AIR, Quantity(1400, "K"), Quantity(101325, "Pa"), w,
                                                         samples=51, rtol=1e-9, atol=1e-15, species=("CH4", "CO2"))
    T = rec.series_for("temperature").values
    ch4 = rec.series_for("X_CH4").values
    assert rec.succeeded and T[0] == pytest.approx(1400) and T[-1] > 2400 and ch4[-1] < 1e-6 * ch4[0]  # ignited and burned out
    assert rec.identity.window == w
    assert rec.series_for("temperature").times_s[-1] == pytest.approx(0.05)


def test_a_mechanism_that_pulls_species_from_another_file_is_refused():
    text = "phases:\n- name: gas\n  thermo: ideal-gas\n  species: [{gri30.yaml/species: [O2, N2]}]\n"
    with pytest.raises(ProviderRefusal, match="another file"):
        CanteraProvider(REG).equilibrium(Mechanism("partial.yaml", text.encode(), "gas"), {"O2": 0.21, "N2": 0.79},
                                         Quantity(300, "K"), Quantity(101325, "Pa"))
